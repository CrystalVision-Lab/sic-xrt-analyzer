import QtQuick
import QtQuick.Controls

Button {
    id: control
    property QtObject theme
    property bool primary: false
    property bool quiet: false
    property bool dark: false
    property string tip: ""

    implicitHeight: theme ? theme.controlHeight : 34
    implicitWidth: Math.max(52, label.implicitWidth + 24)
    padding: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    ToolTip.visible: hovered && tip.length > 0
    ToolTip.text: tip

    contentItem: Text {
        id: label
        text: control.text
        font.family: theme.fontFamily
        font.pixelSize: theme ? theme.bodySize : 13
        font.weight: control.primary || control.checked ? Font.DemiBold : Font.Normal
        color: !control.enabled ? (control.dark ? "#84969e" : theme.disabled)
               : control.primary && !control.quiet ? "#ffffff"
               : control.dark ? (control.checked ? "#b7f0f1" : theme.viewerText)
               : control.checked ? theme.accent : theme.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: 5
        color: control.dark ? (!control.enabled ? "#354249"
               : control.down ? "#145a64"
               : control.primary ? theme.accent
               : control.checked ? "#16515b"
               : control.hovered ? "#3b4b53" : (control.quiet ? "transparent" : "#314047"))
               : !control.enabled ? theme.window
               : control.down ? (control.primary ? "#086b76" : theme.accentPale)
               : control.primary ? theme.accent
               : control.checked ? theme.accentPale
               : control.hovered ? "#e8eff1" : (control.quiet ? "transparent" : theme.surface)
        border.width: control.activeFocus ? 2 : (control.quiet ? 0 : 1)
        border.color: control.activeFocus ? (control.dark ? "#66d6de" : theme.accent)
                      : (control.dark ? "#52636b" : theme.border)
    }
}
