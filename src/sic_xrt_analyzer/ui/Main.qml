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
    property var discardNext: null
    property bool allowQuit: false
    function imagejCommand(command, options) { if (uiState.stackFeaturesVisible) imagejDialog.showCommand(command, options) }
    function imagejTools() { if (uiState.stackFeaturesVisible) { imagejDialog.tabsIndex = 3; imagejDialog.open() } }
    function imagejMacro() { if (uiState.stackFeaturesVisible) imagejDialog.showMacro() }
    function imagejPlugin() { if (uiState.stackFeaturesVisible) imagejDialog.showPlugin() }
    function stackMeasurement() { if (uiState.stackFeaturesVisible) measurementDialog.open() }
    function imagejCatalog() { if (uiState.stackFeaturesVisible) { imagejDialog.tabsIndex = 1; imagejDialog.open(); fileBridge.imagej.loadCommands() } }
    function imagejModern() { if (uiState.stackFeaturesVisible) { imagejDialog.tabsIndex = 4; imagejDialog.open() } }
    function imagejResults() { if (uiState.stackFeaturesVisible) { imagejDialog.tabsIndex = 2; imagejDialog.open() } }
    function saveImageCopy() { imageSaveDialog.open() }
    function saveMeasurements() { measurementsSaveDialog.open() }
    function imagejStatistics(kind) { if (uiState.stackFeaturesVisible) { imagejResults(); fileBridge.imagej.statistics(kind) } }
    function imagejStackCommand(command, options) { if (uiState.stackFeaturesVisible) { imagejDialog.showCommand(command, options); imagejDialog.wholeStack = true } }
    function confirmRoiDiscard(callback) {
        if (!uiState.importedRois.dirty) { callback(); return }
        discardNext = callback; roiDiscardDialog.open()
    }
    onClosing: function(close) {
        if (uiState.importedRois.dirty && !allowQuit) {
            close.accepted = false
            confirmRoiDiscard(function() { window.allowQuit = true; window.close() })
        }
    }
    property var commands: ({
        open: openAction, save: saveAction, demo: demoAction, closeImage: closeImageAction, quit: quitAction,
        pan: panAction, roi: roiAction, clearRoi: clearRoiAction, copyRoi: copyRoiAction,
        zoomIn: zoomInAction, zoomOut: zoomOutAction, fit: fitAction, actualSize: actualSizeAction,
        roiLayer: roiLayerAction, navigationPanel: navigationPanelAction, inspectorPanel: inspectorPanelAction,
        statusBar: statusBarAction, fullScreen: fullScreenAction, resetLayout: resetLayoutAction,
        run: runAction, cancelAnalysis: cancelAnalysisAction, settings: settingsAction, modelInfo: modelInfoAction, guide: guideAction,
        shortcutGuide: shortcutGuideAction, reportIssue: reportIssueAction, about: aboutAction,
        importRois: importRoisAction
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
        uiState.opening = false
        uiState.filePath = ""; uiState.fileName = ""; uiState.imageSource = ""
        uiState.imageWidth = 0; uiState.imageHeight = 0; uiState.bitDepth = 0; uiState.pageCount = 0; uiState.workingStackContext = false
        uiState.pageIndex = 0; uiState.dtype = ""; uiState.imageFormat = ""
        uiState.previewWidth = 0; uiState.previewHeight = 0
        uiState.sampledPreview = false; uiState.demoMode = false; uiState.hasRoi = false
        uiState.cursorX = -1; uiState.cursorY = -1; uiState.loadError = ""; uiState.activeTool = "Pan"
        uiState.selectingRoi = false; uiState.fitMode = true
        viewer.resetPan(); fileBridge.clearImage()
    }
    function closeImage() { confirmRoiDiscard(function() { clearImageState(); uiState.roiEditMode = false; uiState.zoom = 1; uiState.statusText = "현재 이미지를 닫았습니다" }) }
    function showDemo() {
        if (uiState.loading) return
        confirmRoiDiscard(function() {
            clearImageState(); uiState.roiEditMode = false; uiState.workspaceIndex = 0; uiState.demoMode = true; viewer.defaultView()
            uiState.statusText = "합성 데모 · 실제 XRT 데이터 및 분석 결과 아님"
        })
    }
    function selectImagePath(path) { selectImageFile(fileBridge.localUrl(path)) }
    function selectImageFile(url) {
        confirmRoiDiscard(function() { window.startImageLoad(url) })
    }
    function startImageLoad(url) {
        uiState.roiEditMode = false
        uiState.opening = true; uiState.loadError = ""; uiState.statusText = "이미지 불러오는 중…"
        fileBridge.requestImage(url)
    }
    Connections {
        target: window.desktopBridge
        function onRoiSaved(result) {
            if (result.ok) uiState.statusText = "ROI 복사본 저장 완료: " + result.path
            else window.showInfo("ROI 저장 실패", result.error)
        }
        function onImageOpened(result) {
            uiState.opening = false
            if (!result.ok) { uiState.loadError = result.error; uiState.statusText = "이미지 열기 실패: " + result.error; return }
            var sizeChanged = uiState.imageWidth !== result.width || uiState.imageHeight !== result.height
            uiState.filePath = result.path; uiState.fileName = result.name
            uiState.imageWidth = result.width; uiState.imageHeight = result.height
            uiState.previewWidth = result.previewWidth; uiState.previewHeight = result.previewHeight
            uiState.bitDepth = result.bitDepth; uiState.pageCount = result.pageCount; uiState.sampledPreview = result.sampled
            uiState.workingStackContext = !!result.stackContext
            uiState.pageIndex = result.pageIndex; uiState.dtype = result.dtype
            uiState.imageFormat = result.format
            uiState.imageSource = result.source; uiState.workspaceIndex = 0; uiState.demoMode = false
            if (!result.workingCopy) uiState.activeTool = "Pan"
            if (!result.workingCopy || sizeChanged) uiState.hasRoi = false
            uiState.cursorX = -1; uiState.cursorY = -1
            window.openInspectorTab(3)
            if (!result.workingCopy || sizeChanged) viewer.defaultView()
            viewer.focusView()
            uiState.statusText = result.format + " · " + result.pageCount + " 페이지 / " + (result.pageCount > 1 ? "전체 준비 후 탐색" : "화면 맞춤")
        }
        function onRoiImportFinished(result) {
            window.openInspectorTab(4)
            uiState.statusText = "ROI " + result.count + "개 · " + (result.errors.length ? "불러오기 오류 " + result.errors.length + "개" : "원본 좌표로 표시")
        }
        function onPageChanged(result) {
            if (!result.ok) { uiState.loadError = result.error; return }
            var changedPage = uiState.pageIndex !== result.pageIndex
            var changedSize = uiState.imageWidth !== result.width || uiState.imageHeight !== result.height
            uiState.imageWidth = result.width; uiState.imageHeight = result.height
            uiState.previewWidth = result.previewWidth; uiState.previewHeight = result.previewHeight
            uiState.pageIndex = result.pageIndex; uiState.dtype = result.dtype
            uiState.bitDepth = result.bitDepth; uiState.sampledPreview = result.sampled
            uiState.imageSource = result.source; uiState.loadError = ""
            if (changedPage) { uiState.hasRoi = false; uiState.selectingRoi = false }
            if (changedSize) viewer.defaultView()
            uiState.statusText = "페이지 " + (result.pageIndex + 1) + " / " + result.pageCount
                                 + (result.browsePreview ? " · 탐색 미리보기 / 원본 준비 중" : " · 원본 픽셀")
        }
    }
    Connections {
        target: fileBridge.imagej
        function onResultReady(path) { uiState.opening = true; fileBridge.requestWorkingCopy(path) }
        function onSaveFinished(result) { uiState.statusText = "복사본 저장 완료: " + result.path }
    }
    function clearRoi() { uiState.hasRoi = false; uiState.statusText = "ROI를 초기화했습니다" }
    function selectImportedBounds() {
        var selected = uiState.importedRois.items.filter(function(r) { return r.selected && r.active })
        if (!selected.length) return
        var b = selected[0].bbox
        uiState.roiStartX = b[0] / uiState.contentWidth; uiState.roiStartY = b[1] / uiState.contentHeight
        uiState.roiEndX = (b[0] + b[2]) / uiState.contentWidth; uiState.roiEndY = (b[1] + b[3]) / uiState.contentHeight
        uiState.hasRoi = true; uiState.selectingRoi = false
        uiState.statusText = "가져온 ROI의 외접 사각형 선택"
    }
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
    Action { id: openAction; objectName: "openAction"; text: "이미지 열기…"; shortcut: StandardKey.Open; onTriggered: window.openImageDialog() }
    Action { id: importRoisAction; objectName: "importRoisAction"; text: "ImageJ ROI 가져오기…"; enabled: uiState.hasLoadedImage && !uiState.loading; onTriggered: { window.openInspectorTab(4); roiDialog.open() } }
    Action { id: saveAction; text: "이미지 복사본 저장…"; shortcut: StandardKey.Save; enabled: uiState.hasLoadedImage && !uiState.loading && !fileBridge.imagej.state.busy; onTriggered: window.saveImageCopy() }
    Action { id: demoAction; text: "합성 데모 이미지 보기"; enabled: !uiState.loading; onTriggered: window.showDemo() }
    Action { id: closeImageAction; objectName: "closeImageAction"; text: "현재 이미지 닫기"; shortcut: StandardKey.Close; enabled: uiState.hasImage || uiState.loading; onTriggered: window.closeImage() }
    Action { id: quitAction; text: "종료"; shortcut: "Ctrl+Q"; onTriggered: window.close() }
    Action { id: panAction; objectName: "panAction"; text: "Pan"; shortcut: "H"; enabled: uiState.canNavigateImage; onTriggered: { uiState.roiEditMode = false; uiState.activeTool = "Pan" } }
    Action { id: roiAction; objectName: "roiAction"; text: "ROI 선택"; shortcut: "R"; enabled: uiState.canNavigateImage; onTriggered: { uiState.roiEditMode = false; uiState.activeTool = "ROI" } }
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
    Action { id: runAction; objectName: "runAction"; text: "분석 실행"; enabled: uiState.canAnalyze; onTriggered: fileBridge.requestAnalysis(uiState.analysisScope, uiState.roiX, uiState.roiY, uiState.roiWidth, uiState.roiHeight, {}) }
    Action { id: cancelAnalysisAction; objectName: "cancelAnalysisAction"; text: "분석 취소"; enabled: uiState.analysisRunning; onTriggered: fileBridge.cancelAnalysis() }
    Action { id: settingsAction; objectName: "settingsAction"; text: "설정…"; onTriggered: settingsDialog.openPreferences() }
    Action { id: modelInfoAction; text: "모델 정보"; onTriggered: window.showInfo("모델 정보", uiState.analysisReason + "\n모델: " + (uiState.analysis.modelName || "—") + "\n버전: " + (uiState.analysis.modelVersion || "—") + "\n장치: " + (uiState.analysis.device || "—")) }
    Action { id: guideAction; text: "사용 안내"; onTriggered: window.showInfo("뷰어 사용 안내", "파일 메뉴에서 TIFF/JPG 또는 합성 데모를 여세요.\n오른쪽 뷰어 탭: 페이지 이동과 밝기·대비. 스택은 휠/방향키로 탐색하고 Ctrl+휠로 확대합니다.\nROI 탭: 대응하는 이미지의 .roi/RoiSet.zip 가져오기 및 표시.\nPan / ROI 도구, FIT 화면 맞춤, 100% 원본 픽셀 배율을 지원합니다. 확대 시 보이는 영역을 정밀 읽습니다.\nImageJ frames는 공간 Z축으로 해석하지 않습니다. 모델 분석은 미연결입니다.") }
    Action { id: shortcutGuideAction; text: "단축키"; onTriggered: window.showInfo("단축키", "파일\n열기  Ctrl+O     닫기  Ctrl+W     종료  Ctrl+Q\n\n보기\n화면 맞춤  Ctrl+0     실제 크기  Ctrl+1\n확대·축소  Ctrl++ / Ctrl+-     전체 화면  F11\n\n도구\nPan  H     ROI  R\n\n메뉴\nAlt+F / E / V / W / A / T / S / H") }
    Action { id: reportIssueAction; text: "문제 보고"; onTriggered: { if (!fileBridge.openIssueTracker()) window.showInfo("문제 보고", "브라우저를 열지 못했습니다. GitHub 저장소의 Issues에서 보고해 주세요.") } }
    Action { id: aboutAction; objectName: "aboutAction"; text: "프로그램 정보"; onTriggered: window.showInfo("SiC XRT Analyzer", "XRT 이미지 검사·분석\n버전 " + fileBridge.appVersion + "\n" + fileBridge.systemInfo + "\n\nTIFF/JPG · ImageJ ROI 뷰어\n모델 분석 미연결\nCrystalVision-Lab") }
    menuBar: AppMenuBar { theme: theme; uiState: uiState; hostWindow: window; fileBridge: window.desktopBridge; actions: window.commands }
    header: TopToolbar { objectName: "topToolbar"; theme: theme; uiState: uiState; actions: window.commands; hostWindow: window; height: uiState.stackFeaturesVisible ? theme.toolbarHeight : 40 }
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
        InspectorPanel { id: inspector; theme: theme; uiState: uiState; visible: !window.inspectorCollapsed; Layout.preferredWidth: theme.panelWidth; Layout.fillHeight: true; onImportRequested: importRoisAction.trigger(); onBoundsRequested: window.selectImportedBounds(); onSaveRequested: roiSaveDialog.open() }
    }
    footer: StatusBar { theme: theme; uiState: uiState; height: visible ? theme.statusHeight : 0; visible: window.statusBarVisible }
    FileDialog { id: openDialog; objectName: "openImageDialog"; title: "XRT 이미지 열기"; nameFilters: ["XRT 이미지 (*.tif *.tiff *.jpg *.jpeg)", "TIFF 이미지 (*.tif *.tiff)", "JPEG 이미지 (*.jpg *.jpeg)", "모든 파일 (*)"]; onAccepted: window.selectImageFile(selectedFile.toString()) }
    FileDialog { id: roiDialog; objectName: "roiFileDialog"; title: "대응하는 이미지의 ImageJ ROI 가져오기"; fileMode: FileDialog.OpenFiles; nameFilters: ["ImageJ ROI (*.roi *.zip)", "ROI 파일 (*.roi)", "ROI ZIP (*.zip)"]; onAccepted: fileBridge.importRois(selectedFiles) }
    FileDialog { id: roiSaveDialog; objectName: "roiSaveDialog"; title: "새 ROI ZIP 복사본 저장 (기존 파일 덮어쓰기 불가)"; fileMode: FileDialog.SaveFile; nameFilters: ["ROI ZIP (*.zip)"]; defaultSuffix: "zip"; onAccepted: fileBridge.saveRoiCopy(selectedFile.toString()) }
    FileDialog { id: imageSaveDialog; title: "이미지 전체 파일의 새 복사본 저장 (기존 파일 덮어쓰기 불가)"; fileMode: FileDialog.SaveFile; nameFilters: uiState.imageFormat === "JPEG" ? ["JPEG (*.jpg *.jpeg)"] : ["TIFF (*.tif *.tiff)"]; defaultSuffix: uiState.imageFormat === "JPEG" ? "jpg" : "tif"; onAccepted: fileBridge.imagej.saveImageCopy(selectedFile.toString()) }
    FileDialog { id: measurementsSaveDialog; title: "측정 결과 TSV 저장"; fileMode: FileDialog.SaveFile; nameFilters: ["TSV (*.tsv)"]; defaultSuffix: "tsv"; onAccepted: fileBridge.imagej.saveResults(selectedFile.toString()) }
    Dialog {
        id: roiDiscardDialog; objectName: "roiDiscardDialog"; modal: true; title: "저장하지 않은 ROI 변경"
        x: (window.width - width) / 2; y: (window.height - height) / 2
        standardButtons: Dialog.Discard | Dialog.Cancel
        Label { text: "ROI ZIP 복사본을 저장하지 않은 변경이 있습니다.\n변경을 버리고 계속할까요? 취소 후 ROI 탭에서 저장할 수 있습니다." }
        onDiscarded: { var next = window.discardNext; window.discardNext = null; if (next) next() }
        onRejected: window.discardNext = null
    }
    AppDialog { id: infoDialog; objectName: "infoDialog"; theme: theme; x: (window.width - width) / 2; y: (window.height - height) / 2 }
    SettingsDialog { id: settingsDialog; theme: theme; fileBridge: window.desktopBridge; x: (window.width - width) / 2; y: (window.height - height) / 2; onApplied: function(preferences) { window.applyPreferences(preferences) } }
    ImageJDialog { id: imagejDialog; parent: Overlay.overlay; theme: theme; backend: fileBridge.imagej; x: (window.width - width) / 2; y: (window.height - height) / 2 }
    StackMeasurementDialog { id: measurementDialog; parent: Overlay.overlay; theme: theme; backend: fileBridge.stackMeasurements; uiState: uiState; x: (window.width-width)/2; y: (window.height-height)/2 }
    PluginWindowsDialog { parent: Overlay.overlay; theme: theme; backend: fileBridge.imagej; x: (window.width-width)/2; y: (window.height-height)/2 }
    Connections { target: uiState; function onStackFeaturesVisibleChanged() { if (!uiState.stackFeaturesVisible) { imagejDialog.close(); measurementDialog.close() } } }
}
