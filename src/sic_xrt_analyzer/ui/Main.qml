import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: window
    objectName: "mainWindow"
    visible: true
    width: 1440
    height: 900
    minimumWidth: 1100
    minimumHeight: 700
    title: "SiC XRT Analyzer"
    color: theme.window
    font.family: theme.fontFamily
    font.pixelSize: theme.bodySize

    property bool navigationCollapsed: false
    property bool inspectorCollapsed: false
    Theme { id: theme }
    UiState { id: uiState; objectName: "uiState" }

    function openImageDialog() { openDialog.open() }
    function showDemo() {
        uiState.filePath = ""
        uiState.fileName = ""
        uiState.workspaceIndex = 0
        uiState.demoMode = true
        uiState.activeTool = "이동"
        uiState.statusText = "합성 데모 이미지를 표시합니다"
    }
    function selectImageFile(fileUrl) {
        const path = fileBridge.localPath(fileUrl)
        if (!path) return
        uiState.filePath = path
        uiState.fileName = fileBridge.fileName(path)
        uiState.workspaceIndex = 0
        uiState.demoMode = false
        uiState.activeTool = "이동"
        uiState.statusText = "파일을 선택했습니다 · 이미지 표시는 준비 중입니다"
    }

    FileDialog {
        id: openDialog
        objectName: "openImageDialog"
        title: "XRT 이미지 선택"
        nameFilters: ["TIFF 이미지 (*.tif *.tiff)"]
        onAccepted: window.selectImageFile(selectedFile.toString())
        onRejected: uiState.statusText = "파일 선택을 취소했습니다"
    }

    Shortcut { sequence: "Ctrl+O"; onActivated: window.openImageDialog() }
    Shortcut { sequence: "Ctrl+0"; enabled: uiState.canNavigateImage; onActivated: viewer.fitView() }
    Shortcut { sequence: "Ctrl++"; enabled: uiState.canNavigateImage; onActivated: viewer.zoomIn() }
    Shortcut { sequence: "Ctrl+-"; enabled: uiState.canNavigateImage; onActivated: viewer.zoomOut() }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        TopToolbar {
            theme: theme
            uiState: uiState
            Layout.fillWidth: true
            Layout.preferredHeight: theme.toolbarHeight
            onOpenRequested: window.openImageDialog()
            onDemoRequested: window.showDemo()
            onFitRequested: viewer.fitView()
            onZoomInRequested: viewer.zoomIn()
            onZoomOutRequested: viewer.zoomOut()
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            NavigationPanel {
                id: navigation
                theme: theme
                uiState: uiState
                collapsed: window.navigationCollapsed
                Layout.fillHeight: true
                Layout.preferredWidth: implicitWidth
                onCollapseRequested: window.navigationCollapsed = !window.navigationCollapsed
            }

            ImageViewer {
                id: viewer
                objectName: "imageViewer"
                theme: theme
                uiState: uiState
                Layout.fillWidth: true
                Layout.fillHeight: true
                onOpenRequested: window.openImageDialog()
                onDemoRequested: window.showDemo()
            }

            InspectorPanel {
                id: inspector
                theme: theme
                uiState: uiState
                collapsed: window.inspectorCollapsed
                Layout.fillHeight: true
                Layout.preferredWidth: implicitWidth
                onCollapseRequested: window.inspectorCollapsed = !window.inspectorCollapsed
            }
        }

        StatusBar {
            theme: theme
            uiState: uiState
            Layout.fillWidth: true
            Layout.preferredHeight: theme.statusHeight
        }
    }
}
