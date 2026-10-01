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
    function selectWorkspace(index) {
        uiState.workspaceIndex = index
        const names = ["이미지 분석", "Wafer Map", "이미지 정합", "3D 보기"]
        uiState.statusText = index === 0 ? "이미지 분석 화면" : names[index] + " 화면 준비 중"
    }
    function openInspectorTab(index) {
        inspectorCollapsed = false
        inspector.tabIndex = index
    }
    function clearRoi() {
        uiState.hasRoi = false
        uiState.statusText = "관심 영역을 지웠습니다"
    }
    function showInfo(titleText, bodyText) {
        infoDialog.title = titleText
        infoDialog.bodyText = bodyText
        infoDialog.open()
    }
    function showDemo() {
        uiState.filePath = ""
        uiState.fileName = ""
        uiState.imageSource = ""
        uiState.imageWidth = 0
        uiState.imageHeight = 0
        uiState.bitDepth = 0
        uiState.pageCount = 0
        uiState.sampledPreview = false
        uiState.loadError = ""
        uiState.workspaceIndex = 0
        uiState.demoMode = true
        uiState.activeTool = "이동"
        uiState.statusText = "합성 데모 이미지를 표시합니다"
    }
    function selectImageFile(fileUrl) {
        const result = fileBridge.openImage(fileUrl)
        if (!result.ok) {
            uiState.loadError = result.error
            uiState.statusText = "TIFF 열기 실패: " + result.error
            return
        }
        uiState.filePath = result.path
        uiState.fileName = result.name
        uiState.imageWidth = result.width
        uiState.imageHeight = result.height
        uiState.bitDepth = result.bitDepth
        uiState.pageCount = result.pageCount
        uiState.sampledPreview = result.sampled
        uiState.loadError = ""
        uiState.imageSource = result.source
        uiState.workspaceIndex = 0
        uiState.demoMode = false
        uiState.activeTool = "이동"
        uiState.statusText = result.sampled ? "TIFF를 열었습니다 · 큰 이미지의 축소 미리보기" : "TIFF를 열었습니다"
    }

    menuBar: MenuBar {
        id: appMenuBar
        objectName: "appMenuBar"
        background: Rectangle { color: theme.panel; border.color: theme.border; border.width: 1 }
        delegate: MenuBarItem {
            id: barItem
            implicitHeight: 34
            implicitWidth: contentItem.implicitWidth + 24
            contentItem: Text {
                text: barItem.text
                color: theme.text
                font.family: theme.fontFamily
                font.pixelSize: theme.bodySize
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignHCenter
            }
            background: Rectangle { color: barItem.highlighted ? theme.accentPale : theme.panel }
        }

        Menu {
            title: "파일"
            MenuItem { text: "이미지 열기…    Ctrl+O"; onTriggered: window.openImageDialog() }
            MenuItem { text: "데모 이미지 보기"; onTriggered: window.showDemo() }
            MenuSeparator {}
            MenuItem { text: "종료"; onTriggered: window.close() }
        }
        Menu {
            title: "편집"
            MenuItem {
                text: "이동 도구"
                checkable: true
                checked: uiState.activeTool === "이동"
                enabled: uiState.canNavigateImage
                onTriggered: uiState.activeTool = "이동"
            }
            MenuItem {
                text: "관심 영역 선택 도구"
                checkable: true
                checked: uiState.activeTool === "영역 선택"
                enabled: uiState.canNavigateImage
                onTriggered: uiState.activeTool = "영역 선택"
            }
            MenuSeparator {}
            MenuItem {
                text: "관심 영역 지우기"
                enabled: uiState.hasRoi
                onTriggered: window.clearRoi()
            }
        }
        Menu {
            title: "보기"
            MenuItem { text: "화면 맞춤    Ctrl+0"; enabled: uiState.canNavigateImage; onTriggered: viewer.fitView() }
            MenuItem { text: "확대    Ctrl++"; enabled: uiState.canNavigateImage && uiState.zoom < 3.99; onTriggered: viewer.zoomIn() }
            MenuItem { text: "축소    Ctrl+-"; enabled: uiState.canNavigateImage && uiState.zoom > 0.26; onTriggered: viewer.zoomOut() }
            MenuSeparator {}
            MenuItem {
                text: "탐색 패널"
                checkable: true
                checked: !window.navigationCollapsed
                onTriggered: window.navigationCollapsed = !window.navigationCollapsed
            }
            MenuItem {
                text: "정보·설정 패널"
                checkable: true
                checked: !window.inspectorCollapsed
                onTriggered: window.inspectorCollapsed = !window.inspectorCollapsed
            }
        }
        Menu {
            title: "작업 영역"
            MenuItem { text: "이미지 분석"; checkable: true; checked: uiState.workspaceIndex === 0; onTriggered: window.selectWorkspace(0) }
            MenuItem { text: "Wafer Map"; checkable: true; checked: uiState.workspaceIndex === 1; onTriggered: window.selectWorkspace(1) }
            MenuItem { text: "이미지 정합"; checkable: true; checked: uiState.workspaceIndex === 2; onTriggered: window.selectWorkspace(2) }
            MenuItem { text: "3D 보기"; checkable: true; checked: uiState.workspaceIndex === 3; onTriggered: window.selectWorkspace(3) }
        }
        Menu {
            title: "설정"
            MenuItem { text: "이미지 정보·표시 설정"; onTriggered: window.openInspectorTab(0) }
            MenuItem { text: "분석 설정"; onTriggered: window.openInspectorTab(1) }
            MenuItem { text: "결과 패널"; onTriggered: window.openInspectorTab(2) }
        }
        Menu {
            title: "분석"
            MenuItem { text: "분석 실행"; enabled: false }
            MenuItem { text: "결과 보기"; onTriggered: window.openInspectorTab(2) }
        }
        Menu {
            title: "도움말"
            MenuItem {
                text: "단축키"
                onTriggered: window.showInfo("단축키", "Ctrl+O  이미지 열기\nCtrl+0  화면 맞춤\nCtrl++  확대\nCtrl+-  축소")
            }
            MenuItem {
                text: "프로그램 정보"
                onTriggered: window.showInfo("SiC XRT Analyzer", "TIFF 이미지 탐색용 초기 뷰어입니다. 모델 분석과 일부 표시 설정은 준비 중입니다.")
            }
        }
    }

    Dialog {
        id: infoDialog
        property string bodyText: ""
        modal: true
        width: 420
        x: (window.width - width) / 2
        y: (window.height - height) / 2
        standardButtons: Dialog.Ok
        contentItem: Text {
            text: infoDialog.bodyText
            color: theme.text
            font.family: theme.fontFamily
            font.pixelSize: theme.bodySize
            wrapMode: Text.WordWrap
            topPadding: 12
            bottomPadding: 12
        }
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
                onWorkspaceRequested: function(index) { window.selectWorkspace(index) }
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
                objectName: "inspectorPanel"
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
