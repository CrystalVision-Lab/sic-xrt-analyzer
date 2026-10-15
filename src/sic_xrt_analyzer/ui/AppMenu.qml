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
    background: Rectangle { color: root.palette.window; border.color: root.palette.mid; radius: root.visualTheme.radiusControl }
    delegate: AppMenuItem {}
}
