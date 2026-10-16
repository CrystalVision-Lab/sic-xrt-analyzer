"""Capture actual QML with synthetic data; never evidence of model accuracy."""

import argparse
import os
from pathlib import Path

import numpy as np
from benchmark_viewer import spin
from benchmark_viewer_interaction import Session
from PIL import Image, ImageDraw
from PySide6.QtCore import Q_ARG, QMetaObject
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from validate_defect_result_ui import SyntheticAdapter

from sic_xrt_analyzer.analysis.contracts import (
    AdapterOutput,
    CoordinateSpace,
    Detection,
    Geometry,
    GeometryKind,
)
from sic_xrt_analyzer.ui.style import configure_style


class SpatialAdapter(SyntheticAdapter):
    def analyze_source(self, request, token):
        rows = []
        for i in range(192):
            x, y = 90 + (i % 16) * 86, 75 + (i // 16) * 110
            kind = ("BPD", "TED", "TSD")[i % 3]
            scores = [0.1, 0.1, 0.1]
            scores[i % 3] = 0.8
            polygon = (
                (x - 4, y - 27),
                (x + 6, y - 12),
                (x + 10, y + 10),
                (x + 22, y + 38),
                (x + 15, y + 41),
                (x + 3, y + 12),
                (x - 2, y - 9),
                (x - 10, y - 23),
            )
            rows.append(
                Detection(
                    f"candidate_{i:06d}",
                    i % 3,
                    kind,
                    0.8,
                    Geometry(
                        GeometryKind.POINT,
                        ((x, y),),
                        coordinate_space=CoordinateSpace.ORIGINAL,
                    ),
                    {"scores": scores, "bpd_region": polygon if kind == "BPD" else ()},
                )
            )
        return AdapterOutput(
            tuple(rows), {"counts": {"BPD": 64, "TED": 64, "TSD": 64}}, {}
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    for name in ("segoeui.ttf", "malgun.ttf"):
        QFontDatabase.addApplicationFont(
            str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name)
        )
    app.setFont(QFont("Malgun Gothic"))
    configure_style(app)
    session = Session(app, out)
    try:
        rng = np.random.default_rng(154)
        pixels = np.clip(
            rng.normal(133, 3, (1536, 1536, 1)) + [3, 7, -12], 0, 255
        ).astype(np.uint8)
        image = Image.fromarray(pixels)
        draw = ImageDraw.Draw(image)
        for i in range(192):
            x, y = 90 + (i % 16) * 86, 75 + (i // 16) * 110
            if i % 3 == 0:
                draw.line(
                    [
                        (x - 7, y - 25),
                        (x + 2, y - 10),
                        (x + 7, y + 11),
                        (x + 19, y + 40),
                    ],
                    fill=(42, 49, 35),
                    width=7,
                )
            else:
                draw.ellipse((x - 5, y - 7, x + 5, y + 7), fill=(53, 61, 44))
                draw.ellipse((x - 7, y - 1, x - 2, y + 5), fill=(197, 204, 179))
        source = out / "SYNTHETIC_ONLY.jpg"
        image.save(source, quality=95)
        session.open(source)
        session.bridge.pipeline.adapter = SpatialAdapter()
        assert session.bridge.requestAnalysis("FULL_IMAGE", 0, 0, 0, 0, {})
        spin(app, lambda: session.bridge.analysis["hasResult"])
        assert QMetaObject.invokeMethod(
            session.window,
            "requestContext",
            Q_ARG("QVariant", "result"),
            Q_ARG("QVariant", "MANUAL"),
        )
        for width, height in ((1440, 900), (1100, 700)):
            session.window.resize(width, height)
            for mode in ("distribution", "area", "compare"):
                session.ui.setProperty("resultViewMode", mode)
                if mode == "area":
                    session.bridge.research.regions.selectArea(
                        session.bridge.research.regions.groups[4]["id"]
                    )
                if mode == "compare":
                    spin(
                        app,
                        lambda: all(
                            p["thumbnail"]
                            for p in session.bridge.research.regions.state[
                                "compareRows"
                            ]
                        ),
                        60,
                    )
                QTest.qWait(650)
                assert session.window.grabWindow().save(
                    str(out / f"{mode}-{width}.png")
                )
        updates = session.item("appUpdatesDialog")
        assert QMetaObject.invokeMethod(updates, "open")
        QTest.qWait(150)
        assert session.window.grabWindow().save(str(out / "updates.png"))
        assert not session.warnings, session.warnings
        print(
            "Captured actual QML: 3 result views, 2 window sizes, update dialog; no QML warnings."
        )
    finally:
        session.timer.stop()
        session.bridge.waitForLoads()
        session.window.setProperty("allowQuit", True)
        session.window.close()
        session.engine.deleteLater()


if __name__ == "__main__":
    main()
