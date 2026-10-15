import QtQuick
import QtQuick.Controls
Menu {
    id: root
    leftInset: 0; rightInset: 0; topInset: 0; bottomInset: 0
    property bool available: true
    property QtObject visualTheme: Theme {}
    enabled: available
    width: 250
    padding: visualTheme.spacingXs
    height: Math.min(contentItem.implicitHeight + topPadding + bottomPadding, Overlay.overlay ? Overlay.overlay.height - 24 : 680)
    contentItem: ListView {
        implicitHeight: contentHeight
        model: root.contentModel
        currentIndex: root.currentIndex
        clip: true
        interactive: contentHeight > height
        boundsBehavior: Flickable.StopAtBounds
        highlightMoveDuration: 0
        ScrollIndicator.vertical: ScrollIndicator {}
    }
    background: Rectangle { color: root.palette.window; border.color: root.palette.mid; radius: root.visualTheme.radiusControl }
    delegate: AppMenuItem {}
}
