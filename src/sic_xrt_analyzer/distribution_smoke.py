"""Frozen-package QA on temporary synthetic data; never load private models or settings."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path


def main(output, image_paths=(), verify_updates=False):
    from sic_xrt_analyzer import __version__
    report = {
        "version":__version__,
        "status": "FAIL",
        "frozen": bool(getattr(sys, "frozen", False)),
        "models_bundled": False,
        "tests": [],
    }
    try:
        import numpy as np
        import tifffile
        from PIL import Image
        from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QSettings, QUrl
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtWidgets import QApplication

        from sic_xrt_analyzer.imaging.image_stack import JpegImageSource, open_stack
        from sic_xrt_analyzer.imaging.imagej_client import ImageJClient
        from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
        from sic_xrt_analyzer.runtime_process import worker_command
        from sic_xrt_analyzer.stack3d.volume import extract, plan
        from sic_xrt_analyzer.ui.bridge import FileBridge
        from sic_xrt_analyzer.ui.style import configure_style

        app = QApplication([])
        configure_style(app)
        report["ui_style"] = "FluentWinUI3"
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
            from sic_xrt_analyzer.imaging.imagej_commands import command_form
            native_cases = {
                "Gaussian Blur...": "sigma=2 slice",
                "Median...": "radius=2 slice",
                "Mean...": "radius=2 slice",
                "Minimum...": "radius=2 slice",
                "Maximum...": "radius=2 slice",
                "Variance...": "radius=2 slice",
                "Unsharp Mask...": "radius=2 mask=0.6 slice",
                "Remove Outliers...": "radius=2 threshold=50 which=Bright slice",
                "Subtract Background...": "rolling=50 slice",
            }
            dialog = window.findChild(QObject, "imagejDialog")
            for command in native_cases:
                assert QMetaObject.invokeMethod(dialog, "showCommand",
                    Q_ARG("QVariant", command), Q_ARG("QVariant", ""))
                app.processEvents()
                assert dialog.property("nativeControls"), command
                assert window.findChild(QObject, "imagejNativeForm")
            assert QMetaObject.invokeMethod(dialog, "close")
            report["tests"].append("nine bundled native ImageJ QML forms")
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
            defect_path=folder/'connected-defect.tif'
            connected=np.full((7,64,64),60000,np.uint16)
            connected[1:6,28:36,28:36]=3000
            tifffile.imwrite(defect_path,connected,photometric='minisblack')
            bridge.requestImage(QUrl.fromLocalFile(str(defect_path)).toString())
            spin(lambda:bridge.original_source is not None and bridge.original_source.path==str(defect_path))
            bridge.requestPage(3)
            spin(lambda:bridge.original_source.page_index==3)
            assert bridge.defect3d.startVisual(31,31)
            spin(lambda:bridge.defect3d.frame_revision>0 or not bridge.defect3d.busy)
            assert bridge.defect3d.frame_revision>0,bridge.defect3d.error
            assert not bridge.provider.stack3d_images['trace-full'].isNull()
            assert bridge.defect3d.layers_data[1].size
            bridge.defect3d.fastFinish()
            report['tests'].append('real observation mask and bounded layer presentation')
            spin(lambda:not bridge.defect3d.busy)
            assert bridge.defect3d.state['ready'],bridge.defect3d.error
            window.findChild(QObject,'uiState').setProperty('workspaceIndex',3)
            for _ in range(25):app.processEvents();time.sleep(.01)
            report['tests'].append('seed-connected closed defect mesh')
            if c.state["rhi_available"]:
                assert window.findChild(QObject, "defect3dPerspective")
                report["tests"].append("QtQuick3D runtime")
            # Compiled UI lifecycle with a clearly synthetic classifier. This
            # tests packaging/signals/cache, not scientific model performance.
            from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter
            class QaClassifier:
                def __init__(self):
                    self.manifest={"architecture":"synthetic-package-qa","model_sha256":"0"*64}
                def predict(self,patches):
                    return np.tile(np.array([.8,.1,.1]),(len(patches),1))
            from PIL import ImageDraw
            qa_image=Image.open(jpeg)
            ImageDraw.Draw(qa_image).rectangle((250,250,260,260),fill=(255,255,255))
            qa_image.save(jpeg)
            bridge.pipeline.adapter=DesktopResearchAdapter(None,QaClassifier())
            window.findChild(QObject,"uiState").setProperty("workspaceIndex",0)
            bridge.requestImage(QUrl.fromLocalFile(str(jpeg)).toString())
            spin(lambda: bridge.original_source is not None and bridge.original_source.path==str(jpeg) and not bridge.stack_viewer.busy)
            action=window.findChild(QObject,"prepareAnalysisAction")
            action.trigger(None)
            dialog=window.findChild(QObject,"analysisDialog")
            assert dialog.property("visible")
            window.findChild(QObject,"confirmAnalysis").clicked.emit()
            spin(lambda:bridge.analysis["hasResult"] or bridge.analysis["state"]=="FAILED")
            assert bridge.analysis["hasResult"],bridge.analysis["errorMessage"]
            completed=bridge.pipeline.result
            assert completed.detections
            state=window.findChild(QObject,"uiState")
            assert state.property("hasResult")
            window.setProperty("inspectorCollapsed",True)
            assert bridge.pipeline.result is completed
            window.setProperty("inspectorCollapsed",False)
            assert bridge.pipeline.result is completed
            bridge.displayLayers.add(200,200,128,128)
            layer=bridge.displayLayers.rows[0]
            bridge.displayLayers.toggle(layer["id"],False)
            assert not bridge.displayLayers.rows[0]["visible"]
            bridge.pipeline.set_source(None)
            bridge.pipeline.set_source(bridge.original_source)
            assert bridge.pipeline.result.analysis_id==completed.analysis_id
            report["tests"].append("synthetic modal/progress/cache/ROI-layer lifecycle (not model accuracy)")
            import shutil
            wafer=folder/'wafer'
            wafer.mkdir()
            shutil.copyfile(jpeg,wafer/'capture.jpg')
            bridge.folderMap.open(str(wafer))
            spin(lambda:not bridge.folderMap.busy)
            assert bridge.folderMap.state['ready'],bridge.folderMap.error
            bridge.folderMap.requestDetail(0,0,128,128,4)
            spin(lambda:bridge.folderMap.detail_revision>0 or bool(bridge.folderMap.detail_error))
            assert not bridge.folderMap.detail_error,bridge.folderMap.detail_error
            assert bridge.provider.folder_images['detail'].size().width()==512
            assert bridge.folderMap.native.decodes==1
            report['tests'].append('wafer native ROI, JPEG disk cache and OpenCV warp runtime')
            spin(lambda:not bridge.projects.busy)
            if verify_updates:
                bridge.appUpdates.checkUpdates()
                spin(lambda: not bridge.appUpdates.busy, 30)
                assert not bridge.appUpdates.error, bridge.appUpdates.error
                state = bridge.appUpdates.state
                report["app_updates"] = {
                    "current_version": state["currentVersion"],
                    "origin": state["origin"],
                    "available_version": state["version"],
                    "automatic_download": False,
                }
                report["tests"].append("HTTPS application release lookup")
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
                original_bytes = source.read_bytes()
                for index, (command, options) in enumerate(native_cases.items()):
                    # A new source identity prevents the direct ImageJ session
                    # from reusing the previous command's modified working copy.
                    case_source = folder / f"native-command-{index}.tif"
                    shutil.copyfile(source, case_source)
                    case_stack = open_stack(case_source)
                    try:
                        case_frame = case_stack.frame(0)
                        expected = client.run(case_frame, command=command, options=options)
                        expected_pixels = tifffile.imread(expected["path"])
                        actual = client.run(case_frame, native=command,
                            parameters=command_form(command)["values"])
                        np.testing.assert_array_equal(tifffile.imread(actual["path"]), expected_pixels)
                    finally:
                        case_stack.close()
                    assert case_source.read_bytes() == original_bytes
                assert source.read_bytes() == original_bytes
                report["tests"].append("nine native ImageJ operations match direct engine; original preserved")
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
