import QtQuick
import QtQuick.Controls
Menu {
    id: root
    width: 250
    topPadding: 4; bottomPadding: 4
    background: Rectangle { color: root.palette.window; border.color: root.palette.mid; radius: 3 }
    delegate: AppMenuItem {}
}
