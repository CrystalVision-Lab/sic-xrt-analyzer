"""One style entry point for desktop launch and installed-package verification."""
from PySide6.QtCore import Qt
from PySide6.QtQuickControls2 import QQuickStyle

DEFAULT_STYLE = "FluentWinUI3"


def configure_style(app):
    # The current workspace uses a dark palette; Fluent also consults styleHints.
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    QQuickStyle.setStyle(DEFAULT_STYLE)
