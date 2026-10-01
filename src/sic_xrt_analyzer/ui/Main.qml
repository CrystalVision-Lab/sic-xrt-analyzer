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
    property bool statusBarVisible: true
    Theme { id: theme }
    UiState { id: uiState; objectName: "uiState" }

    function openImageDialog() { openDialog.open() }
    function selectImagePath(path) {
        if (!fileBridge.isAccessible(path)) {
            uiState.statusText = "파일을 열 수 없습니다: " + path
            return
        }
        uiState.filePath = path
        uiState.fileName = fileBridge.fileName(path)
        uiState.workspaceIndex = 0
        uiState.demoMode = false
        uiState.activeTool = "이동"
        uiState.zoom = 1
        uiState.hasRoi = false
        fileBridge.recordRecentFile(path)
        uiState.statusText = "파일을 선택했습니다 · TIFF 이미지 표시는 준비 중입니다"
    }
    function closeImage() {
        uiState.filePath = ""
        uiState.fileName = ""
        uiState.demoMode = false
        uiState.zoom = 1
        uiState.hasRoi = false
        uiState.activeTool = "이동"
        viewer.panX = 0
        viewer.panY = 0
        uiState.statusText = "현재 이미지를 닫았습니다"
    }
    function clearRoi() {
        uiState.hasRoi = false
        uiState.statusText = "관심 영역을 해제했습니다"
    }
    function copyRoiInfo() {
        if (!uiState.hasRoi || !uiState.demoMode) return
        const x = Math.min(uiState.roiStartX, uiState.roiEndX)
        const y = Math.min(uiState.roiStartY, uiState.roiEndY)
        const w = Math.abs(uiState.roiEndX - uiState.roiStartX)
        const h = Math.abs(uiState.roiEndY - uiState.roiStartY)
        fileBridge.copyText("데모 이미지 관심 영역 (뷰어 비율)\nx=" + x.toFixed(4) +
                            ", y=" + y.toFixed(4) + ", 너비=" + w.toFixed(4) + ", 높이=" + h.toFixed(4))
        uiState.statusText = "관심 영역 정보를 복사했습니다"
    }
    function openInspectorTab(index) {
        inspectorCollapsed = false
        inspector.tabIndex = index
    }
    function resetLayout() {
        navigationCollapsed = false
        inspectorCollapsed = false
        statusBarVisible = true
        inspector.tabIndex = 0
        if (visibility === Window.FullScreen) showNormal()
        if (uiState.canNavigateImage) viewer.fitView()
        uiState.statusText = "화면 배치를 초기화했습니다"
    }
    function showInfo(titleText, bodyText) {
        infoDialog.title = titleText
        infoDialog.bodyText = bodyText
        infoDialog.open()
    }
    function showDemo() {
        uiState.filePath = ""
        uiState.fileName = ""
        uiState.workspaceIndex = 0
        uiState.demoMode = true
        uiState.activeTool = "이동"
        uiState.hasRoi = false
        viewer.fitView()
        uiState.statusText = "합성 데모 이미지를 표시합니다"
    }
    function selectImageFile(fileUrl) {
        const path = fileBridge.localPath(fileUrl)
        if (!path) return
        selectImagePath(path)
    }

    Action { id: openAction; objectName: "openAction"; text: "이미지 열기…"; shortcut: StandardKey.Open; onTriggered: window.openImageDialog() }
    Action { id: demoAction; text: "데모 이미지 보기"; onTriggered: window.showDemo() }
    Action { id: closeImageAction; text: "현재 이미지 닫기"; shortcut: StandardKey.Close; enabled: uiState.hasSelectedFile || uiState.demoMode; onTriggered: window.closeImage() }
    Action { id: quitAction; text: "종료"; shortcut: StandardKey.Quit; onTriggered: window.close() }
    Action { id: selectRoiAction; text: "관심 영역 선택"; enabled: uiState.canNavigateImage; onTriggered: uiState.activeTool = "영역 선택" }
    Action { id: moveAction; text: "이동 도구"; enabled: uiState.canNavigateImage; onTriggered: uiState.activeTool = "이동" }
    Action { id: clearRoiAction; text: "관심 영역 해제"; enabled: uiState.hasRoi; onTriggered: window.clearRoi() }
    Action { id: copyRoiAction; text: "선택 영역 정보 복사"; enabled: uiState.hasRoi && uiState.demoMode; onTriggered: window.copyRoiInfo() }
    Action { id: zoomInAction; text: "확대"; shortcut: "Ctrl++"; enabled: uiState.canNavigateImage && uiState.zoom < 3.99; onTriggered: viewer.zoomIn() }
    Action { id: zoomOutAction; text: "축소"; shortcut: "Ctrl+-"; enabled: uiState.canNavigateImage && uiState.zoom > 0.26; onTriggered: viewer.zoomOut() }
    Action { id: fitAction; text: "화면에 맞춤"; shortcut: "Ctrl+0"; enabled: uiState.canNavigateImage; onTriggered: viewer.fitView() }
    Action { id: navigationPanelAction; objectName: "navigationPanelAction"; text: "이미지 탐색 패널"; onTriggered: window.navigationCollapsed = !window.navigationCollapsed }
    Action { id: inspectorPanelAction; objectName: "inspectorPanelAction"; text: "이미지 정보 패널"; onTriggered: window.inspectorCollapsed = !window.inspectorCollapsed }
    Action { id: statusBarAction; objectName: "statusBarAction"; text: "상태 표시줄"; onTriggered: window.statusBarVisible = !window.statusBarVisible }
    Action { id: roiLayerAction; text: "관심 영역"; enabled: uiState.canNavigateImage; onTriggered: uiState.roiLayerVisible = !uiState.roiLayerVisible }
    Action { id: fullScreenAction; text: "전체 화면"; shortcut: "F11"; onTriggered: window.visibility === Window.FullScreen ? window.showNormal() : window.showFullScreen() }
    Action { id: resetLayoutAction; text: "화면 배치 초기화"; onTriggered: window.resetLayout() }
    Action { id: analysisSettingsAction; text: "분석 설정…"; onTriggered: window.openInspectorTab(1) }
    Action { id: guideAction; text: "사용 안내"; onTriggered: window.showInfo("사용 안내", "파일 > 이미지 열기로 TIFF 파일을 선택할 수 있습니다. 현재 TIFF 픽셀 표시는 연결되지 않았습니다. 파일 > 데모 이미지 보기에서 확대·이동·관심 영역 선택을 시험하세요. 오른쪽 패널에서 이미지 정보와 분석 준비 상태를 확인할 수 있습니다.") }
    Action { id: shortcutGuideAction; text: "단축키 안내"; onTriggered: window.showInfo("단축키 안내", "Alt+F/E/V/A/T/H  파일/편집/보기/분석/도구/도움말 메뉴\nCtrl+O  이미지 열기\nCtrl+W  현재 이미지 닫기\nCtrl+0  화면에 맞춤\nCtrl++  확대\nCtrl+-  축소\nF11  전체 화면\nCtrl+Q  종료") }
    Action { id: reportIssueAction; text: "문제 보고"; onTriggered: if (!fileBridge.openIssueTracker()) uiState.statusText = "문제 보고 페이지를 열지 못했습니다" }
    Action { id: aboutAction; text: "프로그램 정보"; onTriggered: window.showInfo("프로그램 정보", "SiC XRT Analyzer\n버전 " + fileBridge.appVersion) }
    Action { id: modelInfoAction; text: "모델 정보…"; onTriggered: window.showInfo("모델 정보", "연결된 모델이 없습니다") }

    menuBar: AppMenuBar {
        theme: theme
        uiState: uiState
        hostWindow: window
        inspectorPanel: inspector
        fileBridge: fileBridge
        actions: ({
            open: openAction, demo: demoAction, closeImage: closeImageAction, quit: quitAction,
            selectRoi: selectRoiAction, clearRoi: clearRoiAction, copyRoi: copyRoiAction,
            zoomIn: zoomInAction, zoomOut: zoomOutAction, fit: fitAction,
            navigationPanel: navigationPanelAction, inspectorPanel: inspectorPanelAction,
            statusBar: statusBarAction, roiLayer: roiLayerAction, fullScreen: fullScreenAction,
            resetLayout: resetLayoutAction, analysisSettings: analysisSettingsAction,
            guide: guideAction, shortcutGuide: shortcutGuideAction,
            reportIssue: reportIssueAction, about: aboutAction, modelInfo: modelInfoAction
        })
    }

    FileDialog {
        id: openDialog
        objectName: "openImageDialog"
        title: "XRT 이미지 선택"
        nameFilters: ["TIFF 이미지 (*.tif *.tiff)"]
        onAccepted: window.selectImageFile(selectedFile.toString())
        onRejected: uiState.statusText = "파일 선택을 취소했습니다"
    }

    Dialog {
        id: infoDialog
        objectName: "infoDialog"
        property string bodyText: ""
        modal: true
        width: 460
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

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        TopToolbar {
            objectName: "topToolbar"
            theme: theme
            uiState: uiState
            openAction: openAction
            demoAction: demoAction
            fitAction: fitAction
            zoomInAction: zoomInAction
            zoomOutAction: zoomOutAction
            Layout.fillWidth: true
            Layout.preferredHeight: theme.toolbarHeight
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
                onCollapseRequested: navigationPanelAction.trigger()
            }

            ImageViewer {
                id: viewer
                objectName: "imageViewer"
                theme: theme
                uiState: uiState
                openAction: openAction
                demoAction: demoAction
                moveAction: moveAction
                selectRoiAction: selectRoiAction
                fitAction: fitAction
                zoomInAction: zoomInAction
                zoomOutAction: zoomOutAction
                Layout.fillWidth: true
                Layout.fillHeight: true
            }

            InspectorPanel {
                id: inspector
                objectName: "inspectorPanel"
                theme: theme
                uiState: uiState
                collapsed: window.inspectorCollapsed
                Layout.fillHeight: true
                Layout.preferredWidth: implicitWidth
                onCollapseRequested: inspectorPanelAction.trigger()
            }
        }

        StatusBar {
            theme: theme
            uiState: uiState
            visible: window.statusBarVisible
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? theme.statusHeight : 0
        }
    }
}
