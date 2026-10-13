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
    signal projectRequested()
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
        onProjectRequested: root.projectRequested()
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
        WaferMapWorkspace { theme: root.theme; uiState: root.uiState; onProjectRequested: root.projectRequested() }
        RegistrationWorkspace { theme: root.theme; uiState: root.uiState }
        Rectangle {
            objectName: "workspacePlaceholder3"; color: root.theme.viewer
            Text { anchors.centerIn:parent; text:"3D 뷰어 · 미연결"; color:root.theme.muted }
        }
    }
    RightContextPanel {
        id: contextPanel; theme: root.theme; uiState: root.uiState; actions: root.actions
        visible: !root.contextCollapsed && root.uiState.workspaceIndex === 0
        Layout.preferredWidth: requestedContext === "feedback" ? 440 : requestedContext === "result" ? 380 : root.theme.panelWidth
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
