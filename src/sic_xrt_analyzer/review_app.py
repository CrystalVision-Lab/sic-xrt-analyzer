"""Standalone local review window; does not modify the existing analyzer session."""
import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from .ui.dataset_review import ReviewBridge, ReviewImageProvider, ReviewStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'candidates', 'session'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    os.environ.setdefault('QSG_RENDER_LOOP', 'basic')
    app = QGuiApplication(sys.argv)
    app.setApplicationName('전체 웨이퍼 라벨 검수')
    QQuickStyle.setStyle('Basic')
    store = ReviewStore(args.workspace, args.candidates, args.session)
    engine = QQmlApplicationEngine()
    bridge = ReviewBridge(store)
    engine.rootContext().setContextProperty('reviewBridge', bridge)
    engine.rootContext().setContextProperty('reviewSessionPath', str(store.session))
    engine.addImageProvider('review', ReviewImageProvider(store, bridge))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent/'ui/DatasetReview.qml')))
    if not engine.rootObjects():
        return 1
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
