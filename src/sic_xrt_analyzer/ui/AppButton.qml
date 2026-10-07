import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Button {
    id: control
    property QtObject theme
    property bool primary: false
    property bool quiet: false
    property bool dark: false
    property bool compact: false
    property real labelSize: theme.bodySize
    property int labelWeight: Font.Normal
    property string iconName: ""
    property string tip: ""
    implicitHeight: primary ? theme.primaryHeight : compact ? theme.compactHeight : theme.controlHeight
    implicitWidth: Math.max(theme.compactHeight, buttonContent.implicitWidth + 2 * theme.spacingSm)
    padding: 0
    leftPadding: theme.spacingSm
    rightPadding: theme.spacingSm
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    ToolTip.visible: hovered && tip.length > 0
    ToolTip.text: tip
    contentItem: Item {
        implicitWidth: buttonContent.implicitWidth
        implicitHeight: buttonContent.implicitHeight
        RowLayout {
            id: buttonContent
            anchors.centerIn: parent
            width: Math.min(implicitWidth, parent.width)
            spacing: theme.spacingXs
            AppIcon {
                visible: control.iconName.length > 0
                name: control.iconName
                ink: !control.enabled ? theme.disabled : control.primary ? theme.window : control.checked ? theme.accent : theme.text
                Layout.minimumWidth: theme.iconSize; Layout.maximumWidth: theme.iconSize
                Layout.minimumHeight: theme.iconSize; Layout.maximumHeight: theme.iconSize
                Layout.alignment: Qt.AlignVCenter
            }
            Text {
                visible: control.text.length > 0
                text: control.text
                color: !control.enabled ? theme.disabled : control.primary ? theme.window : control.checked ? theme.accent : theme.text
                font.family: theme.fontFamily; font.pixelSize: control.labelSize
                font.weight: control.checked ? Font.DemiBold : control.primary ? Font.Medium : control.labelWeight
                horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
            }
        }
    }
    background: Rectangle {
        radius: theme.radiusControl
        color: !control.enabled ? (control.quiet ? "transparent" : theme.toolbar) : control.primary ? (control.down ? Qt.darker(theme.accent, 1.2) : control.hovered ? Qt.lighter(theme.accent, 1.1) : theme.accent) : control.down ? theme.accentPale : control.checked ? theme.accentPale : control.hovered ? theme.hover : control.quiet ? "transparent" : theme.surface
        border.width: control.activeFocus ? 2 : 0
        border.color: control.primary && control.enabled ? theme.text : theme.accent
    }
}
