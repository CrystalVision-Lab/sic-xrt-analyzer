import QtQuick
import QtQuick.Controls

Dialog {
    id: root
    property QtObject visualTheme: Theme {}
    padding: visualTheme.spacingMd
    font.pixelSize: visualTheme.bodySize
    background: Rectangle {
        color: root.visualTheme.panel; border.color: root.visualTheme.border
        radius: root.visualTheme.radiusDialog
    }
    header: Label {
        text: root.title; padding: root.visualTheme.spacingMd
        font.pixelSize: root.visualTheme.titleSize; font.weight: Font.DemiBold
        color: root.visualTheme.text; wrapMode: Text.Wrap
        background: Rectangle { color: root.visualTheme.panel }
    }
}
