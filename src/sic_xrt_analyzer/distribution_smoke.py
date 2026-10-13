"""Frozen-package QA on temporary synthetic data; never load private models or settings."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path


def main(output, image_paths=()):
    report = {
        "status": "FAIL",
        "frozen": bool(getattr(sys, "frozen", False)),
        "models_bundled": False,
        "tests": [],
    }
    try:
        import numpy as np
        import tifffile
        from PIL import Image
        from PySide6.QtCore import QObject, QSettings, QUrl
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuickControls2 import QQuickStyle
        from PySide6.QtWidgets import QApplication

        from sic_xrt_analyzer.imaging.image_stack import JpegImageSource, open_stack
        from sic_xrt_analyzer.imaging.imagej_client import ImageJClient
        from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
        from sic_xrt_analyzer.runtime_process import worker_command
        from sic_xrt_analyzer.stack3d.volume import extract, plan
        from sic_xrt_analyzer.ui.bridge import FileBridge

        app = QApplication([])
        QQuickStyle.setStyle("Basic")
        with tempfile.TemporaryDirectory(prefix="xrt-installed-qa-") as folder:
            folder = Path(folder)
            pixels = np.arange(6 * 48 * 64, dtype=np.uint16).reshape(6, 48, 64)
            source = folder / "synthetic-stack.tif"
            tifffile.imwrite(
                source,
                pixels,
                photometric="minisblack",
                imagej=True,
                metadata={"axes": "TYX"},
            )
            reader = OriginalImageSource(source)
            volume = extract(reader, plan(reader, (3, 4, 32, 28), 0, 5))
            assert np.array_equal(volume.pixels, pixels[:, 4:32, 3:35])
            report["tests"].append("uint16 ROI volume")
            jpeg = folder / "synthetic.jpg"
            Image.new("RGB", (2050, 2049), (12, 34, 56)).save(jpeg)
            assert JpegImageSource(jpeg).metadata.channels == 3
            jpeg_stack = open_stack(jpeg)
            try:
                assert jpeg_stack.prepare_native()
                assert jpeg_stack.first_source.read_region(10, 20, 2, 3).shape == (3, 2, 3)
            finally:
                jpeg_stack.close()
            report["tests"].append("large JPEG native codec and prepared cache")
            engine = QQmlApplicationEngine()
            bridge = FileBridge(
                parent=engine,
                settings=QSettings(str(folder / "qa.ini"), QSettings.IniFormat),
            )
            engine.addImageProvider("tiff", bridge.provider)
            engine.rootContext().setContextProperty("fileBridge", bridge)
            warnings = []
            engine.warnings.connect(
                lambda es: warnings.extend(e.toString() for e in es)
            )
            import sic_xrt_analyzer

            engine.load(
                QUrl.fromLocalFile(
                    str(Path(sic_xrt_analyzer.__file__).parent / "ui/Main.qml")
                )
            )
            assert engine.rootObjects(), warnings
            window = engine.rootObjects()[0]
            window.setTitle("Installed SiC XRT — synthetic package validation")
            window.findChild(QObject, "uiState").setProperty("workspaceIndex", 3)
            bridge.stack_viewer._preload_enabled = False
            bridge.stack_viewer._reader.preload_enabled = False
            bridge.openImage(QUrl.fromLocalFile(str(source)).toString())

            def spin(condition, timeout=60):
                until = time.monotonic() + timeout
                while not condition():
                    if time.monotonic() > until:
                        raise RuntimeError("Frozen QA timeout")
                    app.processEvents()
                    time.sleep(0.01)

            spin(lambda: bridge.original_source is not None)
            window.findChild(QObject, "uiState").setProperty("workspaceIndex", 3)
            c = bridge.stack3d
            c.setActive(True)
            c.selectSource("CURRENT")
            c.configure(3, 4, 32, 28, 0, 5, 1, 1)
            c.generate()
            spin(lambda: not c.busy and c.volume is not None)
            assert np.array_equal(c.volume.pixels, pixels[:, 4:32, 3:35])
            report["backend"] = c.state["backend"]
            report["tests"].append("Main.qml and 3D workspace")
            for _ in range(25):
                app.processEvents()
                time.sleep(0.01)
            if c.state["rhi_available"]:
                assert window.findChild(QObject, "stack3dPerspective")
                report["tests"].append("QtQuick3D runtime")
            client = ImageJClient()
            client.configure(False, os.environ.get("SIC_XRT_FIJI_HOME", ""))
            try:
                commands = client.commands()
                assert commands
                report["tests"].append("bundled OpenJDK ImageJ worker")
                stack = open_stack(source)
                try:
                    frame = stack.frame(0)
                finally:
                    stack.close()
                result = client.run(frame, command="Multiply...", options="value=1")
                assert result
                report["tests"].append("ImageJ working copy")
            finally:
                client.close()
            assert Path(
                worker_command("sic_xrt_analyzer.model_updates.validation")[0]
            ).is_file()
            report["tests"].append("model validation worker path")
            assert not warnings, warnings
            report["qml_warnings"] = warnings
            report["actual_images"] = []
            for image_path in image_paths:
                path = Path(image_path).resolve(strict=True)
                import hashlib
                with path.open("rb") as stream:
                    before = hashlib.file_digest(stream, "sha256").hexdigest()
                window.findChild(QObject, "uiState").setProperty("workspaceIndex", 0)
                bridge.requestImage(QUrl.fromLocalFile(str(path)).toString())
                spin(lambda: not bridge.stack_viewer.busy and (bridge.stack_viewer.frame is not None or bool(bridge.stack_viewer.error)), 180)
                assert not bridge.stack_viewer.error, bridge.stack_viewer.error
                source = bridge.original_source
                assert source is not None and source.path == str(path)
                meta = source.metadata
                pixels = source.read_region(min(6000,meta.width-8), min(6000,meta.height-8), 8, 8)
                assert pixels.dtype.name == meta.dtype
                state = window.findChild(QObject, "uiState")
                for _ in range(10): app.processEvents();time.sleep(.01)
                assert state.property("analysisEligible") == (meta.page_count == 1)
                shot = output.with_name(output.stem + "-" + str(len(report["actual_images"])) + ".png")
                assert window.grabWindow().save(str(shot))
                with path.open("rb") as stream:
                    after = hashlib.file_digest(stream, "sha256").hexdigest()
                assert before == after
                report["actual_images"].append({"name":path.name,"width":meta.width,"height":meta.height,"dtype":meta.dtype,"pages":meta.page_count,"sha256":before,"analysis_button":state.property("analysisEligible"),"screenshot":shot.name})
            bridge.waitForLoads()
            window.hide()
            engine.deleteLater()
        report["status"] = "PASS"
    except Exception as exc:  # noqa: BLE001 - QA must write failure evidence for all native/package errors.
        report["error"] = type(exc).__name__ + ": " + str(exc)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if report["status"] == "PASS" else 1
