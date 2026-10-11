import QtQuick
import QtQuick.Controls

TextField {
    id: root
    property QtObject visualTheme: Theme {}
    implicitHeight: visualTheme.controlHeight
    font.pixelSize: visualTheme.bodySize
    leftPadding: visualTheme.spacingSm; rightPadding: visualTheme.spacingSm
    color: enabled ? visualTheme.text : visualTheme.disabled
    placeholderTextColor: visualTheme.muted
    background: Rectangle {
        color: root.visualTheme.surface; radius: root.visualTheme.radiusSm
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? root.visualTheme.accent : root.visualTheme.border
    }
}
