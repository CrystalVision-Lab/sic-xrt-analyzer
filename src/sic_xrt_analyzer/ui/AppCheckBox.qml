import QtQuick
import QtQuick.Controls
CheckBox {
    id: root
    property QtObject theme
    implicitHeight: 28
    spacing: 8
    indicator: Rectangle {
        x: root.leftPadding; y: (root.height - height) / 2; width: 16; height: 16; radius: 2
        color: root.enabled ? root.theme.surface : root.theme.panel
        border.color: root.enabled && root.checked ? root.theme.accent : root.theme.border
        Text { anchors.centerIn: parent; text: "✓"; visible: root.checked; color: root.enabled ? root.theme.accent : root.theme.disabled; font.pixelSize: 13 }
    }
    contentItem: Text {
        leftPadding: root.indicator.width + root.spacing; text: root.text
        color: root.enabled ? root.theme.text : root.theme.disabled
        font.family: root.theme.fontFamily; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter
    }
}
