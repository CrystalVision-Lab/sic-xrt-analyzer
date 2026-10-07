import QtQuick
import QtQuick.Controls
Slider {
    id: root
    property QtObject theme
    implicitHeight: theme.compactHeight
    hoverEnabled: true
    background: Rectangle { x: root.leftPadding; y: (root.height - height) / 2; width: root.availableWidth; height: 3; color: root.theme.border }
    handle: Rectangle { x: root.leftPadding + root.visualPosition * (root.availableWidth - width); y: (root.height - height) / 2; width: 12; height: 12; radius: theme.radiusSm; color: root.enabled ? root.pressed ? Qt.lighter(root.theme.accent, 1.2) : root.theme.accent : root.theme.disabled; border.width: root.activeFocus ? 2 : 0; border.color: root.theme.text }
}
