import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    property QtObject theme
    property QtObject uiState
    property var hostWindow
    property bool compact: false
    spacing: 3
    objectName: "stackViewerToolGroup"
    Repeater {
        model: ["Rectangle", "Oval", "Polygon", "Freehand", "Line", "Polyline", "Point", "Wand"]
        ToolButton {
            required property string modelData
            objectName: "tiffTool" + modelData
            visible: !root.compact || ["Rectangle", "Line", "Point"].indexOf(modelData) >= 0
            implicitWidth: 34; implicitHeight: 32
            padding: 7; focusPolicy: Qt.StrongFocus; hoverEnabled: true
            action: root.hostWindow.commands.tools.forTool(modelData)
            Accessible.name: action.text
            Accessible.description: root.hostWindow.commands.tools.tooltip(modelData)
            contentItem: ToolGlyph { tool: modelData; ink: parent.enabled ? root.theme.text : root.theme.disabled }
            background: Rectangle {
                color: parent.checked ? root.theme.accentPale : parent.hovered ? root.theme.hover : "transparent"
                border.width: parent.checked || parent.activeFocus ? 1 : 0
                border.color: root.theme.accent; radius: root.theme.radiusSm
            }
            ToolTip.visible: hovered; ToolTip.delay: 350
            ToolTip.text: root.hostWindow.commands.tools.tooltip(modelData)
        }
    }
}
