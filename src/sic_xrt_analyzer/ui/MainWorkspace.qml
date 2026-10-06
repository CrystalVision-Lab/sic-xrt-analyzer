import QtQuick
import QtQuick.Layouts

RowLayout {
    id: root
    objectName: "mainWorkspace"
    property QtObject theme
    property QtObject uiState
    property var actions
    property var recentFiles: []
    property bool navigationCollapsed: false
    property bool contextCollapsed: false
    property alias viewer: viewer
    property alias contextPanel: contextPanel
    signal navigationToggleRequested()
    signal workspaceRequested(int index)
    signal recentRequested(string path)
    signal fileDropped(string url)
    signal importRequested()
    signal boundsRequested()
    signal roiSaveRequested()
    signal modelRequested()
    signal coordinatesRequested()
    signal resultExportRequested()
    spacing: 0
    NavigationPanel {
        theme: root.theme; uiState: root.uiState
        collapsed: root.navigationCollapsed; recentFiles: root.recentFiles
        Layout.preferredWidth: implicitWidth; Layout.fillHeight: true
        onCollapseRequested: root.navigationToggleRequested()
        onWorkspaceRequested: function(index) { root.workspaceRequested(index) }
        onRecentRequested: function(path) { root.recentRequested(path) }
    }
    StackLayout {
        objectName: "centralWorkspace"
        currentIndex: root.uiState.workspaceIndex
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumWidth: 0
        ImageViewer {
            id: viewer; theme: root.theme; uiState: root.uiState; actions: root.actions
            onFileDropped: function(url) { root.fileDropped(url) }
        }
        Repeater {
            model: ["Wafer Map", "이미지 정합", "3D 뷰어"]
            Rectangle {
                required property int index
                required property string modelData
                objectName: "workspacePlaceholder" + (index + 1)
                color: root.theme.viewer
                ColumnLayout {
                    anchors.centerIn: parent; spacing: 10
                    Text { text: modelData; color: root.theme.text; font.pixelSize: 17 }
                    Text { text: "해당 작업 영역은 아직 연결되지 않았습니다"; color: root.theme.muted; font.pixelSize: 12 }
                }
            }
        }
    }
    RightContextPanel {
        id: contextPanel; theme: root.theme; uiState: root.uiState; actions: root.actions
        visible: !root.contextCollapsed
        Layout.preferredWidth: tabIndex === 2 ? 380 : root.theme.panelWidth
        Layout.fillHeight: true
        onOverviewRequested: viewer.fitView()
        onImportRequested: root.importRequested()
        onBoundsRequested: root.boundsRequested()
        onSaveRequested: root.roiSaveRequested()
        onModelRequested: root.modelRequested()
        onCoordinatesRequested: root.coordinatesRequested()
        onResultExportRequested: root.resultExportRequested()
    }
}
