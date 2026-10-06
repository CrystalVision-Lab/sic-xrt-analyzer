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
    implicitHeight: 40
    RowLayout {
        objectName: "primaryToolbarRow"
        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
        spacing: 5
        FileToolGroup { theme: root.theme; actions: root.actions }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        ViewerToolGroup { theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        RoiToolGroup { theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow }
        MeasurementToolGroup { theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        AdvancedToolGroup { theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow }
        Item { Layout.fillWidth: true }
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border }
}
