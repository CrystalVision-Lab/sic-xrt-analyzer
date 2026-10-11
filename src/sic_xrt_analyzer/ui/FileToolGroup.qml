import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    objectName: "fileToolGroup"
    property QtObject theme
    property var actions
    spacing: 5
    ToolbarButton { objectName: "toolbarOpen"; theme: root.theme; action: root.actions.open; text: "열기"; iconName: "open"; tip: "TIFF/JPG 열기 · Ctrl+O" }

}
