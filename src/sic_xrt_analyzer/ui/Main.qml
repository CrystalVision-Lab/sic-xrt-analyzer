import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: window
    objectName: "mainWindow"
    visible: true; width: 1440; height: 900; minimumWidth: 1100; minimumHeight: 700
    title: "SiC XRT Analyzer"
    color: theme.window; font.family: theme.fontFamily; font.pixelSize: theme.bodySize
    palette.window: theme.panel
    palette.windowText: theme.text
    palette.base: theme.surface
    palette.alternateBase: theme.panel
    palette.text: theme.text
    palette.button: theme.surface
    palette.buttonText: theme.text
    palette.highlight: theme.accentPale
    palette.highlightedText: theme.text
    palette.mid: theme.border
    palette.dark: theme.border
    palette.light: theme.hover
    palette.toolTipBase: theme.surface
    palette.toolTipText: theme.text
    palette.disabled.text: theme.disabled
    palette.disabled.windowText: theme.disabled
    palette.disabled.buttonText: theme.disabled
    property var desktopBridge: fileBridge
    property bool navigationCollapsed: false
    property bool inspectorCollapsed: false
    property bool statusBarVisible: true
    property var commands: ({
        open: openAction, save: saveAction, demo: demoAction, closeImage: closeImageAction, quit: quitAction,
        pan: panAction, roi: roiAction, clearRoi: clearRoiAction, copyRoi: copyRoiAction,
        zoomIn: zoomInAction, zoomOut: zoomOutAction, fit: fitAction, actualSize: actualSizeAction,
        roiLayer: roiLayerAction, navigationPanel: navigationPanelAction, inspectorPanel: inspectorPanelAction,
        statusBar: statusBarAction, fullScreen: fullScreenAction, resetLayout: resetLayoutAction,
        run: runAction, settings: settingsAction, modelInfo: modelInfoAction, guide: guideAction,
        shortcutGuide: shortcutGuideAction, reportIssue: reportIssueAction, about: aboutAction
    })
    Theme { id: theme }
    UiState { id: uiState; objectName: "uiState"; displayPixelRatio: window.Screen.devicePixelRatio }
    function applyPreferences(p) {
        uiState.smoothImages = p.smoothImages; uiState.viewerBackground = p.viewerBackground
        uiState.roiLayerVisible = p.roiVisible; uiState.defaultView = p.defaultView
    }
    Component.onCompleted: {
        var p = fileBridge.preferences(); applyPreferences(p)
        if (p.startupDemo) showDemo()
    }
    function openImageDialog() { openDialog.open() }
    function selectWorkspace(index) {
        uiState.workspaceIndex = index
        uiState.statusText = index === 0 ? "이미지 분석 화면" : ["", "Wafer Map", "이미지 정합", "3D 뷰어"][index] + " · 미연결"
    }
    function openInspectorTab(index) { inspectorCollapsed = false; inspector.tabIndex = index }
    function clearImageState() {
        uiState.filePath = ""; uiState.fileName = ""; uiState.imageSource = ""
        uiState.imageWidth = 0; uiState.imageHeight = 0; uiState.bitDepth = 0; uiState.pageCount = 0
        uiState.sampledPreview = false; uiState.demoMode = false; uiState.hasRoi = false
        uiState.cursorX = -1; uiState.cursorY = -1; uiState.loadError = ""; uiState.activeTool = "Pan"
        uiState.selectingRoi = false; uiState.fitMode = true
        viewer.resetPan(); fileBridge.clearImage()
    }
    function closeImage() { if (uiState.loading) return; clearImageState(); uiState.zoom = 1; uiState.statusText = "현재 이미지를 닫았습니다" }
    function showDemo() {
        if (uiState.loading) return
        clearImageState(); uiState.workspaceIndex = 0; uiState.demoMode = true; viewer.defaultView()
        uiState.statusText = "합성 데모 · 실제 XRT 데이터 및 분석 결과 아님"
    }
    function selectImagePath(path) { selectImageFile(fileBridge.localUrl(path)) }
    function selectImageFile(url) {
        if (uiState.loading) return
        uiState.loading = true; uiState.loadError = ""; uiState.statusText = "TIFF 로딩 중…"
        fileBridge.requestImage(url)
    }
    Connections {
        target: window.desktopBridge
        function onImageOpened(result) {
            uiState.loading = false
            if (!result.ok) { uiState.loadError = result.error; uiState.statusText = "TIFF 열기 실패: " + result.error; return }
            uiState.filePath = result.path; uiState.fileName = result.name
            uiState.imageWidth = result.width; uiState.imageHeight = result.height
            uiState.bitDepth = result.bitDepth; uiState.pageCount = result.pageCount; uiState.sampledPreview = result.sampled
            uiState.imageSource = result.source; uiState.workspaceIndex = 0; uiState.demoMode = false
            uiState.activeTool = "Pan"; uiState.hasRoi = false; uiState.cursorX = -1; uiState.cursorY = -1
            viewer.defaultView()
            uiState.statusText = result.sampled ? "TIFF 로드 완료 · 표시용 축소 미리보기 / 원본 좌표" : "TIFF 로드 완료 · 첫 페이지 / 원본 좌표"
        }
    }
    function clearRoi() { uiState.hasRoi = false; uiState.statusText = "ROI를 초기화했습니다" }
    function copyRoiInfo() {
        if (!uiState.hasRoi) return
        fileBridge.copyText((uiState.demoMode ? "SYNTHETIC DEMO" : uiState.fileName) + "\nROI (original pixels): X=" + uiState.roiX + ", Y=" + uiState.roiY + ", Width=" + uiState.roiWidth + ", Height=" + uiState.roiHeight)
        uiState.statusText = "ROI 원본 픽셀 좌표를 복사했습니다"
    }
    function resetLayout() {
        navigationCollapsed = false; inspectorCollapsed = false; statusBarVisible = true; inspector.tabIndex = 0
        if (visibility === Window.FullScreen) showNormal()
        if (uiState.canNavigateImage) viewer.fitView()
    }
    function showInfo(heading, body) { infoDialog.title = heading; infoDialog.bodyText = body; infoDialog.open() }
    Action { id: openAction; objectName: "openAction"; text: "이미지 열기…"; shortcut: StandardKey.Open; enabled: !uiState.loading; onTriggered: window.openImageDialog() }
    Action { id: saveAction; text: "프로젝트 저장"; enabled: false }
    Action { id: demoAction; text: "합성 데모 이미지 보기"; enabled: !uiState.loading; onTriggered: window.showDemo() }
    Action { id: closeImageAction; objectName: "closeImageAction"; text: "현재 이미지 닫기"; shortcut: StandardKey.Close; enabled: uiState.hasImage && !uiState.loading; onTriggered: window.closeImage() }
    Action { id: quitAction; text: "종료"; shortcut: "Ctrl+Q"; onTriggered: window.close() }
    Action { id: panAction; objectName: "panAction"; text: "Pan"; shortcut: "H"; enabled: uiState.canNavigateImage; onTriggered: uiState.activeTool = "Pan" }
    Action { id: roiAction; objectName: "roiAction"; text: "ROI 선택"; shortcut: "R"; enabled: uiState.canNavigateImage; onTriggered: uiState.activeTool = "ROI" }
    Action { id: clearRoiAction; objectName: "clearRoiAction"; text: "ROI 초기화"; enabled: uiState.hasRoi && !uiState.loading; onTriggered: window.clearRoi() }
    Action { id: copyRoiAction; objectName: "copyRoiAction"; text: "ROI 좌표 복사"; enabled: uiState.hasRoi && !uiState.loading; onTriggered: window.copyRoiInfo() }
    Action { id: zoomInAction; objectName: "zoomInAction"; text: "확대"; shortcut: "Ctrl++"; enabled: uiState.canNavigateImage && uiState.effectiveZoom < 16; onTriggered: viewer.zoomIn() }
    Action { id: zoomOutAction; text: "축소"; shortcut: "Ctrl+-"; enabled: uiState.canNavigateImage && uiState.effectiveZoom > 0.01; onTriggered: viewer.zoomOut() }
    Action { id: fitAction; objectName: "fitAction"; text: "화면 맞춤"; shortcut: "Ctrl+0"; enabled: uiState.canNavigateImage; onTriggered: viewer.fitView() }
    Action { id: actualSizeAction; objectName: "actualSizeAction"; text: "실제 크기 100% (1:1)"; shortcut: "Ctrl+1"; enabled: uiState.canNavigateImage; onTriggered: viewer.setActualZoom(1) }
    Action { id: roiLayerAction; text: "ROI 표시"; enabled: uiState.hasImage; onTriggered: uiState.roiLayerVisible = !uiState.roiLayerVisible }
    Action { id: navigationPanelAction; objectName: "navigationPanelAction"; text: "작업 영역 패널"; onTriggered: window.navigationCollapsed = !window.navigationCollapsed }
    Action { id: inspectorPanelAction; objectName: "inspectorPanelAction"; text: "정보 및 분석 패널"; onTriggered: window.inspectorCollapsed = !window.inspectorCollapsed }
    Action { id: statusBarAction; objectName: "statusBarAction"; text: "상태 표시줄"; onTriggered: window.statusBarVisible = !window.statusBarVisible }
    Action { id: fullScreenAction; objectName: "fullScreenAction"; text: "전체 화면"; shortcut: "F11"; onTriggered: window.visibility === Window.FullScreen ? window.showNormal() : window.showFullScreen() }
    Action { id: resetLayoutAction; text: "화면 배치 초기화"; onTriggered: window.resetLayout() }
    Action { id: runAction; objectName: "runAction"; text: "분석 실행"; enabled: uiState.canAnalyze }
    Action { id: settingsAction; objectName: "settingsAction"; text: "설정…"; onTriggered: settingsDialog.openPreferences() }
    Action { id: modelInfoAction; text: "모델 정보"; onTriggered: window.showInfo("모델 정보", uiState.analysisReason + "\n모델 / 버전 / 장치: —") }
    Action { id: guideAction; text: "사용 안내"; onTriggered: window.showInfo("뷰어 사용 안내", "파일 메뉴에서 TIFF 또는 합성 데모를 여세요.\n도구 모음에서 Pan / ROI를 선택하세요. 휠로 확대·축소합니다.\nFIT은 화면 맞춤, 100%는 원본 픽셀과 화면 픽셀의 1:1 배율입니다.\nTIFF는 첫 페이지만 표시합니다. 모델 분석은 미연결 상태입니다.") }
    Action { id: shortcutGuideAction; text: "단축키"; onTriggered: window.showInfo("단축키", "파일\n열기  Ctrl+O     닫기  Ctrl+W     종료  Ctrl+Q\n\n보기\n화면 맞춤  Ctrl+0     실제 크기  Ctrl+1\n확대·축소  Ctrl++ / Ctrl+-     전체 화면  F11\n\n도구\nPan  H     ROI  R\n\n메뉴\nAlt+F / E / V / W / A / T / S / H") }
    Action { id: reportIssueAction; text: "문제 보고"; onTriggered: { if (!fileBridge.openIssueTracker()) window.showInfo("문제 보고", "브라우저를 열지 못했습니다. GitHub 저장소의 Issues에서 보고해 주세요.") } }
    Action { id: aboutAction; objectName: "aboutAction"; text: "프로그램 정보"; onTriggered: window.showInfo("SiC XRT Analyzer", "XRT 이미지 검사·분석\n버전 " + fileBridge.appVersion + "\n" + fileBridge.systemInfo + "\n\nTIFF 뷰어 · 모델 분석 미연결\nCrystalVision-Lab") }
    menuBar: AppMenuBar { theme: theme; uiState: uiState; hostWindow: window; fileBridge: window.desktopBridge; actions: window.commands }
    header: TopToolbar { objectName: "topToolbar"; theme: theme; uiState: uiState; actions: window.commands; height: theme.toolbarHeight }
    RowLayout {
        anchors.fill: parent; spacing: 0
        NavigationPanel { theme: theme; uiState: uiState; collapsed: window.navigationCollapsed; recentFiles: fileBridge.recentFiles; Layout.preferredWidth: implicitWidth; Layout.fillHeight: true; onCollapseRequested: window.navigationCollapsed = !window.navigationCollapsed; onWorkspaceRequested: function(index) { window.selectWorkspace(index) }; onRecentRequested: function(path) { window.selectImagePath(path) } }
        StackLayout {
            currentIndex: uiState.workspaceIndex; Layout.fillWidth: true; Layout.fillHeight: true
            ImageViewer { id: viewer; theme: theme; uiState: uiState; actions: window.commands; onFileDropped: function(url) { window.selectImageFile(url) } }
            Repeater {
                model: ["Wafer Map", "이미지 정합", "3D 뷰어"]
                Rectangle { required property string modelData; color: theme.viewer
                    ColumnLayout { anchors.centerIn: parent; spacing: 10
                        Text { text: modelData; color: theme.text; font.pixelSize: 17 }
                        Text { text: "해당 작업 영역은 아직 연결되지 않았습니다"; color: theme.muted; font.pixelSize: 12 }
                    }
                }
            }
        }
        InspectorPanel { id: inspector; theme: theme; uiState: uiState; visible: !window.inspectorCollapsed; Layout.preferredWidth: theme.panelWidth; Layout.fillHeight: true }
    }
    footer: StatusBar { theme: theme; uiState: uiState; height: visible ? theme.statusHeight : 0; visible: window.statusBarVisible }
    FileDialog { id: openDialog; objectName: "openImageDialog"; title: "XRT TIFF 이미지 열기"; nameFilters: ["TIFF 이미지 (*.tif *.tiff)", "모든 파일 (*)"]; onAccepted: window.selectImageFile(selectedFile.toString()) }
    AppDialog { id: infoDialog; objectName: "infoDialog"; theme: theme; x: (window.width - width) / 2; y: (window.height - height) / 2 }
    SettingsDialog { id: settingsDialog; theme: theme; fileBridge: window.desktopBridge; x: (window.width - width) / 2; y: (window.height - height) / 2; onApplied: function(preferences) { window.applyPreferences(preferences) } }
}
