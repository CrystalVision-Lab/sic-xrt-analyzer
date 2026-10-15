import QtQuick
import QtQuick.Controls

TextField {
    id: root
    property QtObject visualTheme: Theme {}
    implicitHeight: visualTheme.controlHeight
    font.family: visualTheme.fontFamily
    font.pixelSize: visualTheme.bodySize
    leftPadding: visualTheme.spacingMd
    rightPadding: visualTheme.spacingMd
    color: enabled ? visualTheme.text : visualTheme.disabled
    placeholderTextColor: visualTheme.muted
    selectByMouse: true
}
