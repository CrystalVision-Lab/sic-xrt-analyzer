import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Rectangle {
    id: root
    property QtObject theme
    property QtObject uiState
    property var actions
    property var hostWindow
    objectName: "primaryToolbar"
    color: theme.toolbar
    ToolPalette { visible: uiState.stackFeaturesVisible; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 8; height: 30; theme: root.theme; uiState: root.uiState; hostWindow: root.hostWindow }
    RowLayout {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 40; anchors.leftMargin: 10; anchors.rightMargin: 10
        spacing: 5
        FileToolGroup { theme: root.theme; actions: root.actions }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        ViewerToolGroup { theme: root.theme; uiState: root.uiState; actions: root.actions }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        ModelStatusGroup { theme: root.theme; uiState: root.uiState }

        Item { Layout.fillWidth: true }
        AnalysisToolGroup { theme: root.theme; uiState: root.uiState; actions: root.actions }
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border }
}
