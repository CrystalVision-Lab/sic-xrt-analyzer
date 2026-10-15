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
    readonly property color foreground: !enabled ? theme.disabled : (primary || checked) ? theme.accentText : theme.text
    flat: quiet && !checked && !primary
    highlighted: primary
    font.family: theme.fontFamily
    font.pixelSize: labelSize
    Accessible.name: text || tip
    Accessible.description: tip
    implicitHeight: primary ? theme.primaryHeight : compact ? theme.compactHeight : theme.controlHeight
    implicitWidth: Math.max(theme.compactHeight, buttonContent.implicitWidth + 2 * theme.spacingMd)
    padding: 0
    leftPadding: theme.spacingMd
    rightPadding: theme.spacingMd
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
                ink: control.foreground
                Layout.minimumWidth: theme.iconSize; Layout.maximumWidth: theme.iconSize
                Layout.minimumHeight: theme.iconSize; Layout.maximumHeight: theme.iconSize
                Layout.alignment: Qt.AlignVCenter
            }
            Text {
                visible: control.text.length > 0
                text: control.text
                color: control.foreground
                font.family: theme.fontFamily; font.pixelSize: control.labelSize
                font.weight: control.checked ? Font.DemiBold : control.primary ? Font.Medium : control.labelWeight
                horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
            }
        }
    }
}
