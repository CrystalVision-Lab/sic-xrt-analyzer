"""Foreign AWT/Swing windows parented into this application's Qt Quick window."""
from PySide6.QtCore import Property, QPointF, QRect, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtQml import QQmlEngine, qmlRegisterType
from PySide6.QtQuick import QQuickItem


def native_windows_supported():
    return QGuiApplication.platformName() in ('windows', 'xcb')


class NativePluginWindow(QQuickItem):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._native_id = ''
        self.foreign = None
        self.container = None
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.sync_geometry)
        for signal in (self.windowChanged, self.xChanged, self.yChanged,
                       self.widthChanged, self.heightChanged, self.visibleChanged):
            signal.connect(self.sync_geometry)

    @Property(str, notify=changed)
    def nativeId(self):
        return self._native_id

    @nativeId.setter
    def nativeId(self, value):
        if value != self._native_id:
            self.release()
            self._native_id = str(value)
            if self._native_id and native_windows_supported():
                self.foreign = QWindow.fromWinId(int(self._native_id))
                if self.foreign is not None:
                    QQmlEngine.setObjectOwnership(self.foreign, QQmlEngine.CppOwnership)
                    # fromWinId already marks this as ForeignWindow. Preserve
                    # that type: setParent embeds it without taking native ownership.
                    self.timer.start()
            self.sync_geometry()
            self.changed.emit()

    @Slot()
    def sync_geometry(self):
        if self.foreign is None or self.window() is None:
            return
        window = self.window()
        QQmlEngine.setObjectOwnership(window, QQmlEngine.CppOwnership)
        if self.container is None:
            self.container = QWindow(window)
            self.container.setFlags(Qt.SubWindow)
            QQmlEngine.setObjectOwnership(self.container, QQmlEngine.CppOwnership)
            self.foreign.setParent(self.container)
        origin = self.mapToScene(QPointF())
        geometry = QRect(round(origin.x()), round(origin.y()), max(1, round(self.width())), max(1, round(self.height())))
        self.container.setGeometry(geometry)
        self.foreign.setGeometry(QRect(0, 0, geometry.width(), geometry.height()))
        self.container.setVisible(self.isVisible())
        self.foreign.setVisible(self.isVisible())

    @Slot()
    def synchronize(self):
        self.sync_geometry()

    @Slot()
    def release(self):
        self.timer.stop()
        if self.foreign is not None:
            self.foreign.setParent(None)
            self.foreign.deleteLater()
            self.foreign = None
        if self.container is not None:
            self.container.deleteLater()
            self.container = None


qmlRegisterType(NativePluginWindow, 'XrtViewer', 1, 0, 'NativePluginWindow')
