"""Generated synthetic ONNX/packages/keys only; no research data or exported models."""

import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import numpy as np
import onnx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from sic_xrt_analyzer.model_updates.contracts import (
    INPUT,
    OUTPUT,
    canonical,
    digest,
    file_sha,
    sign_release,
)


def bundle(root, dataset_hash="a" * 64, checkpoint="b" * 64):
    root.mkdir()
    h = onnx.helper
    nodes = [
        h.make_node(
            "AveragePool",
            ["images"],
            ["mean"],
            kernel_shape=[9, 9],
            pads=[4, 4, 4, 4],
            strides=[1, 1],
        ),
        h.make_node("Sub", ["images", "mean"], ["delta"]),
        h.make_node("Mul", ["delta", "delta"], ["squared"]),
        h.make_node(
            "AveragePool",
            ["squared"],
            ["variance"],
            kernel_shape=[9, 9],
            pads=[4, 4, 4, 4],
            strides=[1, 1],
        ),
        h.make_node("Add", ["variance", "epsilon"], ["varplus"]),
        h.make_node("Sqrt", ["varplus"], ["std"]),
        h.make_node("Div", ["delta", "std"], ["normalized"]),
        h.make_node("GlobalAveragePool", ["normalized"], ["pooled"]),
        h.make_node("Flatten", ["pooled"], ["flat"], axis=1),
        h.make_node("Softmax", ["flat"], ["probabilities"], axis=1),
    ]
    graph = h.make_graph(
        nodes,
        "Synthetic test classifier",
        [
            h.make_tensor_value_info(
                "images", onnx.TensorProto.FLOAT, ["N", 3, 128, 128]
            )
        ],
        [h.make_tensor_value_info("probabilities", onnx.TensorProto.FLOAT, ["N", 3])],
        [onnx.numpy_helper.from_array(np.array([1e-4], np.float32), "epsilon")],
    )
    model = h.make_model(graph, opset_imports=[h.make_opsetid("", 17)])
    model.ir_version = 8
    onnx.save(model, root / "model.onnx")
    evaluation = {
        "status": "SYNTHETIC_FUNCTIONAL_EVALUATION",
        "scientific_metrics": False,
        "dataset_hash": dataset_hash,
        "checkpoint_sha256": checkpoint,
        "same_inputs_and_labels": False,
        "candidate": {},
        "baseline": None,
    }
    m = {
        "schema": "frozen_xrt_patch_classifier",
        "schema_version": 1,
        "status": "validated_export",
        "model_file": "model.onnx",
        "classes": ["BPD", "TED", "TSD"],
        "input": INPUT,
        "output": OUTPUT,
        "model_sha256": file_sha(root / "model.onnx"),
        "research_only": True,
        "independent_test_passed": False,
        "background_class": False,
        "localizes_defects": False,
        "architecture": "synthetic_qa/v1",
        "dataset_hash": dataset_hash,
        "checkpoint_sha256": checkpoint,
        "config_hash": "c" * 64,
        "evaluation_hash": digest(evaluation),
        "code_revision": "d" * 40,
        "synthetic_smoke": True,
        "candidate_status": "FUNCTIONAL_TEST_ONLY",
    }
    (root / "manifest.json").write_bytes(canonical(m))
    reg = {
        "schema": "xrt_model_candidate/v1",
        "candidate_id": m["model_sha256"],
        "manifest_sha256": file_sha(root / "manifest.json"),
        "dataset_hash": dataset_hash,
        "evaluation": evaluation,
        "status": "FUNCTIONAL_TEST_ONLY",
        "distribution": "NOT_AUTHORIZED",
        "replaces_existing_model": False,
    }
    (root / "candidate-registry.json").write_bytes(canonical(reg))
    return m


def signing(
    root, origin="http://127.0.0.1:18766", sequence=1, channel="STABLE", key_id="qa-key"
):
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(
        key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()
    trust = {
        "schema": "xrt_release_trust/v1",
        "origins": {
            origin: {
                "registry_id": "qa-registry",
                "keys": {key_id: {"status": "TRUSTED", "public_key": public}},
            }
        },
    }
    now = datetime.now(UTC)
    m = {
        "schema": "xrt_signed_model_release/v1",
        "release_id": str(uuid4()),
        "candidate_id": str(uuid4()),
        "release_sequence": sequence,
        "registry_id": "qa-registry",
        "model_id": "qa-classifier",
        "model_version": "0.1.0",
        "model_sha256": file_sha(root / "model.onnx"),
        "manifest_sha256": file_sha(root / "manifest.json"),
        "model_bytes": (root / "model.onnx").stat().st_size,
        "manifest_bytes": (root / "manifest.json").stat().st_size,
        "channel": channel,
        "minimum_app_version": "0.1.0",
        "maximum_app_version": "0.1.0",
        "artifact_identity": file_sha(root / "model.onnx")
        + ":"
        + file_sha(root / "manifest.json"),
        "release_status": "RELEASED",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=14)).isoformat(),
        "signing_key_id": key_id,
        "change_notes": "Synthetic updater fixture, not research deployment",
    }
    raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    return sign_release(m, raw), trust, raw
