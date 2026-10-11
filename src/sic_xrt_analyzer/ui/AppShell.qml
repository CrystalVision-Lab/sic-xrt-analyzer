import QtQuick
import QtQuick.Controls

ApplicationWindow {
    id: shell
    property QtObject shellTheme
    property QtObject shellState
    property var shellActions
    property var shellBridge
    property bool navigationCollapsed: false
    property bool inspectorCollapsed: false
    property bool statusBarVisible: true
    property alias viewer: workspace.viewer
    property alias inspector: workspace.contextPanel // Existing command callers keep their handle.
    property alias contextPanel: workspace.contextPanel
    signal workspaceRequested(int index)
    signal recentRequested(string path)
    signal fileDropped(string url)
    signal importRequested()
    signal boundsRequested()
    signal roiSaveRequested()
    signal modelRequested()
    signal coordinatesRequested()
    signal resultExportRequested()
    color: shellTheme.window; font.family: shellTheme.fontFamily; font.pixelSize: shellTheme.bodySize
    palette.window: shellTheme.panel
    palette.windowText: shellTheme.text
    palette.base: shellTheme.surface
    palette.alternateBase: shellTheme.panel
    palette.text: shellTheme.text
    palette.button: shellTheme.surface
    palette.buttonText: shellTheme.text
    palette.highlight: shellTheme.accentPale
    palette.highlightedText: shellTheme.text
    palette.mid: shellTheme.border
    palette.dark: shellTheme.border
    palette.light: shellTheme.hover
    palette.toolTipBase: shellTheme.surface
    palette.toolTipText: shellTheme.text
    palette.disabled.text: shellTheme.disabled
    palette.disabled.windowText: shellTheme.disabled
    palette.disabled.buttonText: shellTheme.disabled
    menuBar: AppMenuBar {
        theme: shell.shellTheme; uiState: shell.shellState; hostWindow: shell
        fileBridge: shell.shellBridge; actions: shell.shellActions
    }
    header: PrimaryToolbar {
        objectName: "topToolbar"
        theme: shell.shellTheme; uiState: shell.shellState; actions: shell.shellActions; hostWindow: shell
        height: 40
    }
    MainWorkspace {
        id: workspace; anchors.fill: parent
        theme: shell.shellTheme; uiState: shell.shellState; actions: shell.shellActions
        recentFiles: shell.shellBridge.recentFiles
        navigationCollapsed: shell.navigationCollapsed; contextCollapsed: shell.inspectorCollapsed
        onNavigationToggleRequested: shell.navigationCollapsed = !shell.navigationCollapsed
        onWorkspaceRequested: function(index) { shell.workspaceRequested(index) }
        onRecentRequested: function(path) { shell.recentRequested(path) }
        onFileDropped: function(url) { shell.fileDropped(url) }
        onImportRequested: shell.importRequested()
        onBoundsRequested: shell.boundsRequested()
        onRoiSaveRequested: shell.roiSaveRequested()
        onModelRequested: shell.modelRequested()
        onCoordinatesRequested: shell.coordinatesRequested()
        onResultExportRequested: shell.resultExportRequested()
    }
    footer: StatusBar {
        objectName: "bottomStatusBar"
        theme: shell.shellTheme; uiState: shell.shellState
        height: visible ? shell.shellTheme.statusHeight : 0; visible: shell.statusBarVisible
    }
}
