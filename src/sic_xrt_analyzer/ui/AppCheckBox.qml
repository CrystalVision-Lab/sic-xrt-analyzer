import QtQuick
import QtQuick.Controls
CheckBox {
    property QtObject theme
    implicitHeight: theme.controlHeight
    font.family: theme.fontFamily
    font.pixelSize: theme.bodySize
    spacing: theme.spacingSm
}
