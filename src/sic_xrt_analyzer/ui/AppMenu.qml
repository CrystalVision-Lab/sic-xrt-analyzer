import QtQuick
import QtQuick.Controls
Menu {
    id: root
    property bool available: true
    property QtObject visualTheme: Theme {}
    enabled: available
    width: 250
    topPadding: visualTheme.spacingXs; bottomPadding: visualTheme.spacingXs
    background: Rectangle { color: root.palette.window; border.color: root.palette.mid; radius: root.visualTheme.radiusControl }
    delegate: AppMenuItem {}
}
