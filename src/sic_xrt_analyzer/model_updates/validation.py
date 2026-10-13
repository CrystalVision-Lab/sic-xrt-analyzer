"""Bounded, standard-operator ONNX checks run in a disposable process."""

import json
import subprocess
import sys
import time
from pathlib import Path

from sic_xrt_analyzer.runtime_process import worker_command

from .contracts import MAX_METADATA, file_sha, frozen_manifest, read_json, safe_path


def validate_in_process(bundle):
    import numpy as np
    import onnx
    import onnxruntime as ort

    bundle = safe_path(bundle)
    m = frozen_manifest(read_json((bundle / "manifest.json").read_bytes()))
    if file_sha(bundle / "model.onnx") != m["model_sha256"]:
        raise ValueError("MODEL_HASH")
    graph = onnx.load(str(bundle / "model.onnx"), load_external_data=False)
    if graph.functions or graph.training_info or len(graph.graph.node) > 20000:
        raise ValueError("ONNX_COMPLEXITY")

    # Prohibit external tensors, custom domains and control-flow/nested graphs before checker/ORT.
    def tensors(message):
        for descriptor, value in message.ListFields():
            if descriptor.message_type:
                for child in value if descriptor.is_repeated else [value]:
                    if child.DESCRIPTOR.full_name == "onnx.TensorProto" and (
                        child.external_data
                        or child.data_location == onnx.TensorProto.EXTERNAL
                    ):
                        raise ValueError("EXTERNAL_ONNX_DATA")
                    tensors(child)

    tensors(graph)
    if any(
        n.domain not in ("", "ai.onnx")
        or any(
            a.type in (onnx.AttributeProto.GRAPH, onnx.AttributeProto.GRAPHS)
            for a in n.attribute
        )
        for n in graph.graph.node
    ):
        raise ValueError("CUSTOM_ONNX_OPERATOR")
    onnx.checker.check_model(graph)
    if m.get("architecture") == "xrt_local_contrast_cnn/v1":
        ops = [n.op_type for n in graph.graph.node]
        if not all(x in ops for x in ("AveragePool", "Sub", "Div", "Sqrt")):
            raise ValueError("LOCAL_CONTRAST_GRAPH")
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    opts.inter_op_num_threads = 1
    session = ort.InferenceSession(
        str(bundle / "model.onnx"),
        sess_options=opts,
        providers=["CPUExecutionProvider"],
    )
    inputs = session.get_inputs()
    outputs = session.get_outputs()
    if (
        len(inputs) != 1
        or inputs[0].name != "images"
        or inputs[0].type != "tensor(float)"
        or len(inputs[0].shape) != 4
        or not isinstance(inputs[0].shape[0], str)
        or not inputs[0].shape[0]
        or inputs[0].shape[1:] != [3, 128, 128]
        or len(outputs) != 1
        or outputs[0].name != "probabilities"
        or outputs[0].type != "tensor(float)"
        or outputs[0].shape != [inputs[0].shape[0], 3]
    ):
        raise ValueError("ACTUAL_ONNX_CONTRACT")
    results = []
    for batch in (1, 7):
        x = np.random.default_rng(2026).random((batch, 3, 128, 128), dtype=np.float32)
        y = session.run(["probabilities"], {"images": x})[0]
        if (
            y.shape != (batch, 3)
            or not np.isfinite(y).all()
            or (y < 0).any()
            or not np.allclose(y.sum(1), 1, atol=1e-4)
        ):
            raise ValueError("MODEL_OUTPUT")
        samples = []
        for _ in range(5):
            start = time.perf_counter()
            session.run(["probabilities"], {"images": x})
            samples.append((time.perf_counter() - start) * 1000)
        results.append(
            {
                "batch": batch,
                "finite": True,
                "cpu_mean_ms": sum(samples) / len(samples),
                "repeats": 5,
                "threads": 2,
            }
        )
    return {
        "status": "ARTIFACT_VERIFIED",
        "model_sha256": m["model_sha256"],
        "batches": results,
    }


def validate_bundle(bundle, timeout=45, cancel=None):
    import os

    import psutil

    path = safe_path(bundle)
    file_sha(path / "model.onnx")
    file_sha(path / "manifest.json", MAX_METADATA)
    names = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "LD_LIBRARY_PATH",
    }
    env = {k: v for k, v in os.environ.items() if k.upper() in names}
    env.update(OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2")
    process = subprocess.Popen(
        worker_command("sic_xrt_analyzer.model_updates.validation", path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    deadline = time.monotonic() + timeout
    try:
        while process.poll() is None:
            if (cancel and cancel.is_set()) or time.monotonic() > deadline:
                raise ValueError("ONNX_VALIDATION_CANCELED_OR_TIMEOUT")
            try:
                if psutil.Process(process.pid).memory_info().rss > 2 * 1024**3:
                    raise ValueError("ONNX_VALIDATION_MEMORY")
            except psutil.NoSuchProcess:
                pass
            time.sleep(0.05)
        output, _error = process.communicate()
        if process.returncode or len(output) > MAX_METADATA:
            raise ValueError("ONNX_VALIDATION_FAILED")
        return read_json(output)
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


if __name__ == "__main__":
    try:
        print(json.dumps(validate_in_process(Path(sys.argv[1]))))
    except Exception:  # noqa: BLE001 -- isolated native parser failures must return no secrets
        sys.exit(1)
