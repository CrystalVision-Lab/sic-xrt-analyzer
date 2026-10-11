import QtQuick
import QtQuick.Controls
ComboBox {
    id: root
    property QtObject theme
    hoverEnabled: true
    implicitHeight: theme.controlHeight
    leftPadding: theme.spacingSm; rightPadding: theme.spacingXl
    background: Rectangle { color: root.pressed ? root.theme.accentPale : root.hovered ? root.theme.hover : root.theme.surface; border.width: root.activeFocus ? 2 : 1; border.color: root.activeFocus ? root.theme.accent : root.theme.border; radius: root.theme.radiusSm }
    contentItem: Text { text: root.displayText; color: root.enabled ? root.theme.text : root.theme.disabled; font.family: root.theme.fontFamily; font.pixelSize: root.theme.bodySize; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
    indicator: Text { x: root.width - width - 9; y: (root.height - height) / 2; text: "⌄"; color: root.enabled ? root.theme.muted : root.theme.disabled; font.pixelSize: 14 }
    delegate: AppMenuItem {
        required property int index
        required property var modelData
        width: root.width; text: modelData; highlighted: root.highlightedIndex === index
    }
    popup: Popup {
        y: root.height; width: root.width; padding: root.theme.spacingXs
        implicitHeight: contentItem.implicitHeight + 2 * padding
        background: Rectangle { color: root.theme.panel; border.color: root.theme.border; radius: root.theme.radiusControl }
        contentItem: ListView { clip: true; implicitHeight: contentHeight; model: root.popup.visible ? root.delegateModel : null; currentIndex: root.highlightedIndex }
    }
}
