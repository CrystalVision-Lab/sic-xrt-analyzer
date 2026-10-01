import QtQuick
import QtQuick.Controls
Slider {
    id: root
    property QtObject theme
    implicitHeight: 20
    background: Rectangle { x: root.leftPadding; y: (root.height - height) / 2; width: root.availableWidth; height: 3; color: root.theme.border }
    handle: Rectangle { x: root.leftPadding + root.visualPosition * (root.availableWidth - width); y: (root.height - height) / 2; width: 10; height: 10; radius: 2; color: root.enabled ? root.theme.accent : root.theme.disabled }
}
