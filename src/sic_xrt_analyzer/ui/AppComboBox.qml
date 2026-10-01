import QtQuick
import QtQuick.Controls
ComboBox {
    id: root
    property QtObject theme
    implicitHeight: 28
    leftPadding: 9; rightPadding: 24
    background: Rectangle { color: root.theme.surface; border.color: root.activeFocus ? root.theme.accent : root.theme.border; radius: 3 }
    contentItem: Text { text: root.displayText; color: root.enabled ? root.theme.text : root.theme.disabled; font.family: root.theme.fontFamily; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
    indicator: Text { x: root.width - width - 9; y: (root.height - height) / 2; text: "⌄"; color: root.enabled ? root.theme.muted : root.theme.disabled; font.pixelSize: 14 }
    delegate: AppMenuItem {
        required property int index
        required property var modelData
        width: root.width; text: modelData; highlighted: root.highlightedIndex === index
    }
    popup: Popup {
        y: root.height; width: root.width; padding: 3
        implicitHeight: contentItem.implicitHeight + 6
        background: Rectangle { color: root.theme.panel; border.color: root.theme.border; radius: 3 }
        contentItem: ListView { clip: true; implicitHeight: contentHeight; model: root.popup.visible ? root.delegateModel : null; currentIndex: root.highlightedIndex }
    }
}
