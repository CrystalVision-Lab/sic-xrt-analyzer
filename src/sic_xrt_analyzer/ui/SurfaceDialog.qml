import QtQuick
import QtQuick.Controls

Dialog {
    id: root
    leftInset: 0; rightInset: 0; topInset: 0; bottomInset: 0
    property QtObject visualTheme: Theme {}
    implicitWidth: 480
    onOpened: { if (footer && footer.standardButton) { var close=footer.standardButton(DialogButtonBox.Close);if(close)close.text="닫기" } }
    padding: visualTheme.spacingXl
    font.family: visualTheme.fontFamily
    font.pixelSize: visualTheme.bodySize
    background: Rectangle {
        color: root.visualTheme.panel
        border.color: root.visualTheme.border
        radius: root.visualTheme.radiusDialog
    }
    header: Label {
        text: root.title
        padding: root.visualTheme.spacingLg
        bottomPadding: root.visualTheme.spacingSm
        font.pixelSize: root.visualTheme.titleSize
        font.weight: Font.DemiBold
        color: root.visualTheme.text
        wrapMode: Text.Wrap
    }
}
