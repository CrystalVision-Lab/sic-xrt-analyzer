import QtQuick
import QtQuick.Controls
ComboBox {
    id: root
    property QtObject theme
    hoverEnabled: true
    implicitHeight: theme.controlHeight
    leftPadding: theme.spacingSm; rightPadding: theme.spacingXl
    font.family: theme.fontFamily
    font.pixelSize: theme.bodySize
    delegate: AppMenuItem {
        required property int index
        required property var modelData
        width: root.width; text: modelData; highlighted: root.highlightedIndex === index
    }
    popup: Popup {
        y: root.height; width: root.width; padding: root.theme.spacingXs
        implicitHeight: Math.min(320, contentItem.implicitHeight + 2 * padding)
        background: Rectangle { color: root.theme.panel; border.color: root.theme.border; radius: root.theme.radiusControl }
        contentItem: ListView { clip: true; implicitHeight: contentHeight; ScrollBar.vertical: ScrollBar {}
            model: root.popup.visible ? root.delegateModel : null; currentIndex: root.highlightedIndex }
    }
}
