import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Button {
    id: control
    property QtObject theme
    property bool primary: false
    property bool quiet: false
    property bool dark: false
    property string iconName: ""
    property string tip: ""
    implicitHeight: theme.controlHeight
    implicitWidth: Math.max(28, buttonContent.implicitWidth + 16)
    padding: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    ToolTip.visible: hovered && tip.length > 0
    ToolTip.text: tip
    contentItem: RowLayout {
        id: buttonContent
        spacing: 6
        AppIcon { visible: control.iconName.length > 0; name: control.iconName; ink: !control.enabled ? theme.disabled : control.checked ? theme.accent : theme.text; Layout.alignment: Qt.AlignVCenter }
        Text {
            visible: control.text.length > 0
            text: control.text
            color: !control.enabled ? theme.disabled : control.checked ? theme.accent : theme.text
            font.family: theme.fontFamily; font.pixelSize: theme.bodySize
            font.weight: control.checked ? Font.DemiBold : Font.Normal
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            Layout.fillWidth: true
        }
    }
    background: Rectangle {
        radius: 3
        color: !control.enabled ? theme.toolbar : control.down ? theme.hover : control.checked ? theme.accentPale : control.hovered ? theme.hover : control.quiet ? "transparent" : theme.surface
        border.width: 1
        border.color: control.activeFocus || (control.primary && control.enabled) || control.checked ? theme.accent : control.quiet && control.enabled ? "transparent" : theme.border
    }
}
