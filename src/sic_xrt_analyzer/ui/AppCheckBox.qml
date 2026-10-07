import QtQuick
import QtQuick.Controls
CheckBox {
    id: root
    property QtObject theme
    implicitHeight: theme.controlHeight
    spacing: theme.spacingSm
    indicator: Rectangle {
        x: root.leftPadding; y: (root.height - height) / 2; width: 18; height: 18; radius: root.theme.radiusSm
        color: root.enabled ? root.theme.surface : root.theme.panel
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus || (root.enabled && root.checked) ? root.theme.accent : root.theme.border
        Text { anchors.centerIn: parent; text: "✓"; visible: root.checked; color: root.enabled ? root.theme.accent : root.theme.disabled; font.pixelSize: 13 }
    }
    contentItem: Text {
        leftPadding: root.indicator.width + root.spacing; text: root.text
        color: root.enabled ? root.theme.text : root.theme.disabled
        font.family: root.theme.fontFamily; font.pixelSize: root.theme.bodySize; verticalAlignment: Text.AlignVCenter
    }
}
