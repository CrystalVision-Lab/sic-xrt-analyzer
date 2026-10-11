import QtQuick
import QtQuick.Controls

SpinBox {
    id: root
    property QtObject visualTheme: Theme {}
    implicitHeight: visualTheme.controlHeight
    font.pixelSize: visualTheme.bodySize
    background: Rectangle {
        color: root.visualTheme.surface; radius: root.visualTheme.radiusSm
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? root.visualTheme.accent : root.visualTheme.border
    }
}
