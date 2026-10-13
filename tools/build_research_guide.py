"""Capture current Qt UI with actual originals into private runtime guide assets.

No synthetic pixels, invented model predictions, source writes or live sync.
Manual drafts and provisional registration demonstrate UI only, not expert truth.
"""

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

os.environ.setdefault("QSG_RENDER_LOOP", "basic")
from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from research_guide_content import WORKS
from test_analysis_pipeline import spin
from test_ui_analysis_contract import invoke
from validate_review_workspace import ReviewSession

from sic_xrt_analyzer.results import ProjectStore


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    p = argparse.ArgumentParser()
    for name in (
        "project",
        "single-tiff",
        "stack",
        "stack-project",
        "map-project",
        "registration-project",
        "model",
        "output",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--resume-from", type=Path)
    args = p.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise ValueError("Use a new private capture output")
    out.mkdir(parents=True)
    os.environ["SIC_XRT_SYNC_DIR"] = str(out / "private-outbox")
    app = QApplication([])
    QQuickStyle.setStyle("Basic")
    for font in ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if Path(font).exists():
            QFontDatabase.addApplicationFont(font)
    app.setFont(QFont("Segoe UI", 9))
    s = ReviewSession(app, out)
    b = s.bridge
    u = s.ui
    s.window.setTitle("SiC XRT Analyzer — 실제 데이터 사용 가이드 촬영")
    base = ProjectStore().load(args.project)
    jpg = Path(
        next(
            x.source_reference
            for x in base.image_sources
            if x.acquisition_metadata.get("format") == "JPEG"
        )
    )
    originals = [
        jpg,
        args.single_tiff,
        args.stack,
        args.project,
        args.stack_project,
        args.map_project,
        args.registration_project,
        args.model / "model.onnx",
    ]
    before = {str(x.resolve()): sha(x) for x in originals}
    images = {}
    report = {
        "status": "RUNNING",
        "synthetic_pixels": False,
        "new_inference": 0,
        "live_sync": 0,
        "screens": [],
        "qml_warnings": [],
        "source_before": before,
    }
    if args.resume_from:
        previous = json.loads(
            (args.resume_from / "capture-report.json").read_text(encoding="utf-8")
        )
        report["screens"] = previous["screens"]
        for f in args.resume_from.glob("*.png"):
            dest = out / f.name
            shutil.copy2(f, dest)
            images[f.stem] = {
                "filename": f.name,
                "sha256": sha(dest),
                "size": dest.stat().st_size,
            }

    def settle():
        app.processEvents()
        QTest.qWait(100)
        s.window.grabWindow()

    def cap(key):
        settle()
        image = s.window.grabWindow()
        assert not image.isNull(), key
        path = out / (key + ".png")
        assert image.save(str(path)), key
        images[key] = {
            "filename": path.name,
            "sha256": sha(path),
            "size": path.stat().st_size,
        }
        report["screens"].append(
            {
                "id": key,
                "width": image.width(),
                "height": image.height(),
                "source": b.original_source.path if b.original_source else "",
                "format": u.property("imageFormat"),
                "pages": u.property("pageCount"),
                "workspace": u.property("workspaceIndex"),
            }
        )
        print("captured", key, flush=True)

    def context(key):
        u.setProperty("workspaceIndex", 0)
        invoke(s.window, "openContext", key)
        settle()

    def dialog(name, method="open", *args):
        obj = s.item(name)
        invoke(obj, method, *args)
        settle()
        return obj

    def close(name):
        invoke(s.item(name), "close")
        settle()

    def open_image(path):
        b.reviews.cancel()
        b.roi_manager.clear()
        u.setProperty("hasRoi", False)
        u.setProperty("roiEditMode", False)
        b.projects.manualImageRequested()
        s.open(Path(path).resolve())
        assert not b.stack_viewer.error, b.stack_viewer.error
        assert not b.stack_viewer.preload_error, b.stack_viewer.preload_error
        settle()

    def wait_project():
        spin(app, lambda: not b.projects.busy, 300)
        assert not b.projects.error, b.projects.error

    def project_copy(path, name):
        target = out / name
        shutil.copytree(path.parent, target)
        copy = target / path.name
        b.projects.open(str(copy))
        wait_project()
        return copy

    def region(x, y, w, h):
        meta = b.original_source.metadata
        for key, value in {
            "roiStartX": x / meta.width,
            "roiStartY": y / meta.height,
            "roiEndX": (x + w) / meta.width,
            "roiEndY": (y + h) / meta.height,
            "hasRoi": True,
        }.items():
            u.setProperty(key, value)
        settle()

    try:
        if not args.resume_from:
            open_image(jpg)
            assert b.stackState["preparedDisplay"]
            cap("jpg-fit")
            dialog("settingsDialog", "openPreferences")
            cap("settings")
            close("settingsDialog")
            s.set_zoom(4)
            cap("jpg-zoom")
            s.set_zoom(1)
            s.viewer.setProperty("panX", float(s.viewer.property("panX")) + 80)
            cap("jpg-pan")
            point = s.viewport.mapToScene(
                QPointF(s.viewport.width() / 2, s.viewport.height() / 2)
            ).toPoint()
            QTest.mouseMove(s.window, point)
            spin(app, lambda: bool(u.property("cursorValue")), 30)
            cap("jpg-pixel")
            context("viewer")
            b.setDisplayRange(30, 220)
            spin(app, lambda: not b.stack_viewer.busy, 30)
            cap("jpg-contrast")
            b.setDisplayRange(0, 255)
            invoke(s.window, "fitToView") if hasattr(s.window, "fitToView") else invoke(
                s.item("fitAction"), "trigger"
            )
            region(5900, 6000, 256, 256)
            context("roi")
            cap("roi-area")
            roi_files = list(args.single_tiff.parent.glob("*.roi"))
            assert roi_files, "Actual ImageJ ROI files required"
            assert b.importRois([b.localUrl(str(roi_files[0]))])
            spin(app, lambda: not b.roi_manager.busy, 30)
            cap("roi-import")
            cap("roi-manager")
            selected = b.roi_manager.records[0]
            b.selectImportedRoi(selected.id)
            u.setProperty("roiEditMode", True)
            cap("roi-edit")
            u.setProperty("roiEditMode", False)
            cap("roi-save")
            b.research.loadModel(str(args.model.resolve()))
            spin(app, lambda: not b.research.loading, 120)
            assert b.pipeline.adapter.available, b.research.error
            context("analysis")
            cap("analysis-ready")
            invoke(
                s.window,
                "showInfo",
                "분석 입력",
                b.analysis["inputPreflight"]["currentInputDetail"]
                + "\n"
                + b.analysis["inputPreflight"]["modelExpectedDetail"],
            )
            cap("analysis-input")
            close("infoDialog")
            u.setProperty("analysisScope", "ROI")
            cap("analysis-roi")
            s.item("analysisContext").setProperty("advancedExpanded", True)
            cap("analysis-advanced")
            b.roi_manager.clear()
            u.setProperty("hasRoi", False)
            project_copy(args.project, "result-project")
            run = next(
                r
                for r in b.projects.project.analysis_runs
                if any(o.run_id == r.run_id for o in b.projects.project.observations)
            )
            b.projects.selectRun(run.run_id)
            wait_project()
            spin(
                app,
                lambda: (
                    b.research.saved is not None
                    and b.research.pixels_available
                    and not b.stack_viewer.initial_loading
                ),
                300,
            )
            context("result")
            b.research.setFilter("ALL", False, "")
            cap("result-all")
            for kind in ("BPD", "TED", "TSD"):
                b.research.setFilter(kind, False, "")
                cap("result-" + kind.lower())
            b.research.setFilter("ALL", False, "")
            rows = b.research.state["displayRows"]
            assert rows
            b.research.selectCandidate(rows[0]["id"])
            spin(app, lambda: bool(b.research.state["selected"]), 30)
            cap("result-candidate")
            u.setProperty("analysisLayerVisible", False)
            cap("result-layers")
            u.setProperty("analysisLayerVisible", True)
            b.reviews.setReviewer("guide-reviewer")
            assert b.reviews.enter(), b.reviews.error
            context("feedback")
            cap("review-decision")
            b.reviews.edit()
            cap("review-edit")
            b.reviews.cancel()
            b.reviews.addManual("POLYGON")
            cap("review-manual")
            b.reviews.cancel()
            b.reviews.enter()
            cap("review-history")
            b.reviews.cancel()
            dialog("projectWorkspaceDialog")
            cap("project-workspace")
            cap("project-history")
            close("projectWorkspaceDialog")
            dialog("projectSaveDialog")
            cap("project-save")
            close("projectSaveDialog")
            dialog("modelUpdatesDialog")
            cap("models")
            close("modelUpdatesDialog")
            dialog("centralSyncDialog")
            cap("sync-connect")
            scroll = s.item("syncScroll").property("contentItem")
            scroll.setProperty("contentY", 250)
            cap("sync-crop")
            close("centralSyncDialog")
            open_image(args.single_tiff)
            assert u.property("analysisEligible")
            cap("single-tiff")
            b.workbench.gesture("Rectangle", [[5900, 6000], [6156, 6256]])
            context("roi")
            invoke(s.window, "selectImportedBounds")
            cap("roi-tiff-area")
            open_image(args.stack)
            assert not u.property("analysisEligible")
            context("viewer")
            cap("stack-first")
            pages = b.original_source.metadata.page_count
            for name, page in (("middle", pages // 2), ("last", pages - 1)):
                assert b.requestPage(page)
                spin(
                    app,
                    lambda page=page: (
                        not b.stack_viewer.busy and b.original_source.page_index == page
                    ),
                    60,
                )
                cap("stack-" + name)
            b.autoDisplayRange()
            spin(app, lambda: not b.stack_viewer.busy, 30)
            cap("stack-contrast")
            b.workbench.gesture("Rectangle", [[1400, 1450], [1600, 1650]])
            context("roi")
            cap("tiff-selection")
            b.measurements.measure()
            cap("tiff-measure")
            invoke(s.window, "processTiff", "Gaussian")
            cap("tiff-process")
            close("imagejProcessingDialog")
            dialog("imagejDialog", "showCommand", "Gaussian Blur...", "sigma=2")
            cap("imagej-command")
            invoke(s.item("imagejDialog"), "showMacro")
            cap("imagej-macro")
            invoke(s.item("imagejDialog"), "showPlugin")
            cap("imagej-plugin")
            s.item("imagejDialog").setProperty("tabsIndex", 3)
            cap("imagej-options")
            close("imagejDialog")
            b.roi_manager.clear()
            u.setProperty("hasRoi", False)
            project_copy(args.stack_project, "stack-project")
            u.setProperty("workspaceIndex", 3)
            c = b.stack3d
            c.setActive(True)
            sid = next(
                x.source_id
                for x in b.projects.project.image_sources
                if Path(x.source_reference).name == args.stack.name
            )
            c.selectSource(sid)
            spin(app, lambda: not c.busy and c.source is not None, 300)
            cap("3d-prepare")
            assert c.configure(1400, 1450, 128, 128, 0, pages - 1, 2, 1)
            c.generate()
            spin(app, lambda: not c.busy and c.volume is not None, 300)
            assert not c.error, c.error
            cap("3d-volume")
            c.setPage(len(c.volume.pixels) // 2)
            c.setXY(64, 64)
            spin(app, lambda: not c.busy, 60)
            cap("3d-slices")
            c.newTrack("수동 관측 사용 예시", "guide-observer")
            assert not c.error, c.error
            cap("3d-track")
            cap("3d-session")
            # Do not save or sync provisional manual records made only to explain controls.
            c.discardTracks()
            spin(app, lambda: not c.busy, 60)
            c.setActive(False)
        project_copy(args.map_project, "map-project")
        u.setProperty("workspaceIndex", 1)
        b.waferMap.activate(True)
        spin(app, lambda: not b.waferMap.busy, 300)
        for index, source in enumerate(b.projects.project.image_sources):
            if source.acquisition_metadata.get("format") == "JPEG":
                b.waferMap.select(source.source_id)
                b.waferMap.place(index * 14000, 0, 0, 1, 1)
                spin(app, lambda: not b.waferMap.busy, 300)
        b.waferMap.fit()
        spin(app, lambda: not b.waferMap.busy, 300)
        cap("map-view")
        cap("map-placement")
        cap("map-export")
        project_copy(args.registration_project, "registration-project")
        u.setProperty("workspaceIndex", 2)
        r = b.registration
        records = [
            x
            for x in b.projects.project.image_sources
            if x.acquisition_metadata.get("format") == "JPEG"
        ]
        first = next(x for x in records if "before" in x.display_name.lower())
        last = next(x for x in records if "after" in x.display_name.lower())
        r.select(first.source_id, last.source_id)
        r.prepare()
        spin(app, lambda: not r.busy and r.session is not None, 300)
        cap("registration-pair")
        r.beginLandmarks()
        cap("registration-landmark")
        # The actual pair has no expert correspondence evidence. Preserve the real unready comparison state.
        cap("registration-overlay")
        cap("registration-split")
        cap("registration-difference")
        needed = {tab[1] for work in WORKS for tab in work[3]}
        assert needed <= images.keys(), needed - images.keys()
        manifest = {"schema": "xrt_research_guide/v1", "groups": [], "images": images}
        for key, title, subtitle, tabs in WORKS:
            group = {
                "id": key,
                "title": title,
                "subtitle": subtitle,
                "project_id": base.project_id,
                "tabs": [],
            }
            for i, (name, screen, instruction) in enumerate(tabs):
                target = (
                    [91, 38]
                    if key not in ("registration", "wafer", "stack3d")
                    else [20, 40]
                )
                if key in ("start", "viewer"):
                    target = [4, 3] if i == 0 else [40, 45]
                if key == "imagej":
                    target = [30, 3] if i == 0 else [65, 42]
                if screen in (
                    "models",
                    "settings",
                    "project-save",
                    "sync-connect",
                    "sync-crop",
                    "imagej-command",
                    "imagej-macro",
                    "imagej-plugin",
                    "imagej-options",
                    "tiff-process",
                ):
                    target = [52, 45]
                notes = "화면은 실제 원본 데이터로 촬영했습니다. 원본 파일은 읽기 전용으로 유지합니다."
                if key in ("results", "review"):
                    notes += " 모델 제안의 실제 정확도와 예시 검수 기록은 연구원 정답 승인으로 간주하지 않습니다."
                if key == "registration":
                    notes += " 이 실제 전·후 쌍은 정합 근거가 확보되지 않아 겹침·차이 화면을 활성화하지 않았습니다. 안내 화면의 실패/미준비 상태를 확인하고 실제 대응점을 검증한 뒤 사용하세요."
                if key == "wafer":
                    notes += " 실제 촬영 위치 근거가 없어 임시 상대 배치입니다."
                if key == "stack3d":
                    notes += " 실제 Z축·물리 간격·결함 연속성은 미검증이며 Track은 수동 관측 예시입니다."
                group["tabs"].append(
                    {
                        "id": "step-" + str(i + 1),
                        "title": name,
                        "image_id": screen,
                        "summary": instruction,
                        "steps": [
                            instruction,
                            "화면의 선택값과 대상 파일을 확인한 뒤 다음 작업으로 진행하세요.",
                        ],
                        "notes": notes,
                        "callouts": [
                            {
                                "title": name,
                                "text": instruction,
                                "target": target,
                                "label": [72, 72],
                            },
                            {
                                "title": "작업 상태 확인",
                                "text": "파일명·현재 페이지와 준비 상태를 확인합니다. 저장·전송은 필요한 때 직접 실행하세요.",
                                "target": [48, 97]
                                if key not in ("registration", "wafer")
                                else [58, 35],
                                "label": [35, 78],
                            },
                        ],
                    }
                )
            manifest["groups"].append(group)
        report["source_after"] = {str(x.resolve()): sha(x) for x in originals}
        assert before == report["source_after"]
        report["qml_warnings"] = s.warnings
        assert not s.warnings, s.warnings
        report.update(
            status="PASS",
            groups=len(WORKS),
            tabs=sum(len(g[3]) for g in WORKS),
            unique_screens=len(images),
        )
        (out / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    finally:
        (out / "capture-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        b.waitForLoads()
        s.window.hide()
        s.engine.deleteLater()
        app.processEvents()
    print(
        json.dumps(
            {k: report[k] for k in ("status", "groups", "tabs", "unique_screens")}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
