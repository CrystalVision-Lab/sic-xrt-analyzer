"""Closed popups retain row geometry; feature-hidden rows still collapse."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from test_desktop_research import create_source
from test_toolbar import (
    workbench as workbench,  # noqa: PLC0414 - pytest fixture reexport
)
from test_ui_analysis_contract import invoke


def test_closed_menu_keeps_available_row_height(workbench):
    w = workbench
    run = w.item("menuRunAnalysis")
    menu = w.item("analysisMenu")
    assert not menu.property("visible")
    # Ancestor visibility must not change an available row's intrinsic size.
    assert run.property("implicitHeight") == 32
    invoke(menu, "open")
    QTest.qWait(30)
    center = run.mapToItem(
        menu.property("contentItem"), QPointF(run.width() / 2, run.height() / 2)
    )
    assert 0 <= center.y() < menu.property("contentItem").height()
    y, height = run.y(), menu.property("height")
    invoke(menu, "close")
    assert run.property("implicitHeight") == 32
    invoke(menu, "open")
    QTest.qWait(30)
    assert (run.y(), menu.property("height")) == (y, height)
    invoke(menu, "close")


def test_disabled_action_and_feature_hidden_rows(workbench):
    w = workbench
    menu, run, action = (
        w.item("analysisMenu"),
        w.item("menuRunAnalysis"),
        w.item("runAction"),
    )
    triggered = []
    action.triggered.connect(lambda *args: triggered.append(True))
    # Gray uint16 remains blocked by the model preflight, with a real hit target.
    assert not action.property("enabled")
    invoke(menu, "open")
    QTest.qWait(30)
    point = run.mapToScene(QPointF(run.width() / 2, run.height() / 2)).toPoint()
    QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, point)
    assert triggered == []
    invoke(menu, "close")
    w.open(create_source(w.path.parent).path)
    hidden = w.item("stackMeasurementMenuItem")
    assert (
        not hidden.property("rowAvailable") and hidden.property("implicitHeight") == 0
    )
    assert run.property("rowAvailable") and run.property("implicitHeight") == 32
    assert action.property("enabled")
