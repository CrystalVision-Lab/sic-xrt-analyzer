import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

AppShell {
    id: window
    objectName: "mainWindow"
    visible: true; width: 1440; height: 900; minimumWidth: 1100; minimumHeight: 700
    readonly property bool editingText: !!activeFocusItem && (activeFocusItem instanceof TextInput || activeFocusItem instanceof TextEdit)
    title: "SiC XRT Analyzer"
    shellTheme: theme; shellState: uiState; shellActions: window.commands; shellBridge: window.desktopBridge
    onProjectRequested: projectWorkflow.show()
    onWorkspaceRequested: function(index) { window.selectWorkspace(index) }
    onRecentRequested: function(path) { window.selectImagePath(path) }
    onFileDropped: function(url) { window.selectImageFile(url) }
    onImportRequested: importRoisAction.trigger()
    onBoundsRequested: window.selectImportedBounds()
    onRoiSaveRequested: roiSaveDialog.open()
    onModelRequested: researchModelDialog.open()
    onCoordinatesRequested: coordinatesDialog.open()
    onResultExportRequested: resultsDialog.open()
    property var desktopBridge: fileBridge
    property var discardNext: null
    property bool allowQuit: false
    function imagejCommand(command, options) { if (uiState.imagejFeaturesVisible) imagejDialog.showCommand(command, options) }
    function imagejTools() { if (uiState.imagejFeaturesVisible) { imagejDialog.tabsIndex = 3; imagejDialog.open() } }
    function imagejMacro() { if (uiState.imagejFeaturesVisible) imagejDialog.showMacro() }
    function imagejPlugin() { if (uiState.imagejFeaturesVisible) imagejDialog.showPlugin() }
    function stackMeasurement() { if (uiState.imagejFeaturesVisible) measurementDialog.open() }
    function imagejCatalog() { if (uiState.imagejFeaturesVisible) { imagejDialog.tabsIndex = 1; imagejDialog.open(); fileBridge.imagej.loadCommands() } }
    function imagejModern() { if (uiState.imagejFeaturesVisible) { imagejDialog.tabsIndex = 4; imagejDialog.open() } }
    function imagejResults() { if (uiState.imagejFeaturesVisible) { imagejDialog.tabsIndex = 2; imagejDialog.open() } }
    function changeTiffPage(index) { viewer.cancelToolDrawing(); fileBridge.requestPage(index) }
    function measureSelection() { if (!uiState.loadFlow.imagejReady) return; fileBridge.stackMeasurements.measure(); openContext("viewer"); viewer.focusView() }
    function processTiff(kind) { if (uiState.imagejFeaturesVisible && uiState.loadFlow.imagejReady) processingDialog.showKind(kind) }
    Shortcut { sequence: "R"; enabled: uiState.imagejFeaturesVisible && uiState.loadFlow.imagejReady && !window.editingText; onActivated: toolCommands.rectangle.trigger() }
    function saveImageCopy() { imageSaveDialog.open() }
    function saveMeasurements() { measurementsSaveDialog.open() }
    function imagejStatistics(kind) { if (uiState.imagejFeaturesVisible) { imagejResults(); fileBridge.imagej.statistics(kind) } }
    function imagejStackCommand(command, options) { if (uiState.stackFeaturesVisible) { imagejDialog.showCommand(command, options); imagejDialog.wholeStack = true } }
    property var reviewDiscardNext: null
    function confirmReviewDiscard(callback) {
        if (!uiState.projectReview.pending) { callback(); return }
        reviewDiscardNext=callback; reviewDiscardDialog.open()
    }
    SurfaceDialog {
        id: reviewDiscardDialog; objectName: "reviewDiscardDialog"; parent: Overlay.overlay; modal: true
        title: "작성 중인 검수·영역 초안"; width: 450; x:(parent.width-width)/2; y:(parent.height-height)/2
        standardButtons: Dialog.NoButton
        ColumnLayout {
            anchors.fill: parent
            Text { text: "작성 중인 판정과 도형을 버리고 이동할까요? 기록된 검수는 보존됩니다."; color: theme.text; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                AppButton { objectName: "reviewDiscardConfirm"; theme: theme; text: "초안 버리기"; onClicked: { fileBridge.reviews.cancel(); reviewDiscardDialog.close(); var action=window.reviewDiscardNext; window.reviewDiscardNext=null; if(action) action() } }
                AppButton { objectName: "reviewDiscardCancel"; theme: theme; text: "계속 작성"; onClicked: { window.reviewDiscardNext=null; reviewDiscardDialog.close() } }
            }
        }
    }
    function confirmRoiDiscard(callback) { confirmReviewDiscard(function() { window.confirmRoiOnly(callback) }) }
    function confirmRoiOnly(callback) {
        if (!uiState.importedRois.dirty) { callback(); return }
        discardNext = callback; roiDiscardDialog.open()
    }
    ProjectWorkspace { id: projectWorkflow; objectName: "projectWorkflow"; theme: theme; uiState: uiState; hostWindow: window }
    function openRecentManager() { projectWorkflow.openRecentManager() }
    function openRecentProject(path) { projectWorkflow.recentProject(path) }
    function exportResearchResult() { resultsDialog.open() }
    function openProjectWorkspace() { projectWorkflow.show() }
    onClosing: function(close) {
        if (!allowQuit && uiState.projectReview.pending) {
            close.accepted=false; confirmReviewDiscard(function() { window.close() }); return
        }
        if (!allowQuit && (uiState.project.dirty || uiState.project.busy)) {
            close.accepted = false
            projectWorkflow.guard(function() { window.confirmRoiDiscard(function() { window.allowQuit = true; window.close() }) })
            return
        }
        if (uiState.importedRois.dirty && !allowQuit) {
            close.accepted = false
            confirmRoiDiscard(function() { window.allowQuit = true; window.close() })
        }
    }
    property var commands: ({
        projectNew: projectNewAction, projectOpen: projectOpenAction, projectSave: projectSaveAction, projectSaveAs: projectSaveAsAction, projectWorkspace: projectWorkspaceAction,
        open: openAction, save: saveAction, demo: demoAction, closeImage: closeImageAction, quit: quitAction,
        pan: panAction, roi: roiAction, clearRoi: clearRoiAction, copyRoi: copyRoiAction,
        zoomIn: zoomInAction, zoomOut: zoomOutAction, fit: fitAction, actualSize: actualSizeAction,
        roiLayer: roiLayerAction, navigationPanel: navigationPanelAction, inspectorPanel: inspectorPanelAction,
        statusBar: statusBarAction, fullScreen: fullScreenAction, resetLayout: resetLayoutAction,
        run: runAction, cancelAnalysis: cancelAnalysisAction, settings: settingsAction, modelInfo: modelInfoAction, modelUpdates: modelUpdatesAction, appUpdates: appUpdatesAction, guide: guideAction,
        shortcutGuide: shortcutGuideAction, reportIssue: reportIssueAction, about: aboutAction,
        importRois: importRoisAction, viewerSettings: viewerSettingsAction, prepareAnalysis: prepareAnalysisAction, analysisInputInfo: analysisInputInfoAction, tools: toolCommands, advanced: advancedCommands
    })
    Theme { id: theme }
    UiState { id: uiState; objectName: "uiState"; displayPixelRatio: window.Screen.devicePixelRatio }
    ToolActions { id: toolCommands; uiState: uiState; baseActions: window.commands; hostWindow: window }
    AdvancedActions { id: advancedCommands; uiState: uiState; hostWindow: window; bridge: window.desktopBridge }
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
        uiState.statusText = index === 0 ? "이미지 뷰어 화면" : index === 1 ? "Wafer Map · 공간 배치와 관측 후보" : index === 2 ? "어닐링 전·후 JPG 정합" : "TIFF Indexed Stack 3D · 물리 깊이 미검증"
    }
    function openContext(key) { inspectorCollapsed = false; return contextPanel.showContext(key) }
    function requestContext(key, reason) { return contextPanel.requestContext(key, reason) }
    // Compatibility for plugins/tests; production entries use names.
    function openInspectorTab(index) {
        var key = ["image", "analysis", "result", "viewer", "roi", "feedback"][index]
        return key ? openContext(key) : false
    }
    Connections {
        target: window.contextPanel
        function onActivateRequested(reason) {
            // File milestones restore the roomy viewer; explicit tasks reveal their panel.
            window.inspectorCollapsed = ["OPEN_IMAGE", "OPEN_TIFF", "CLOSE_IMAGE", "DEMO_OPEN", "RESET_LAYOUT"].indexOf(reason) >= 0
        }
        function onFocusRequested() { viewer.focusView() }
    }
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
    function closeImage() { confirmRoiDiscard(function() { clearImageState(); uiState.roiEditMode = false; uiState.zoom = 1; window.requestContext("image", "CLOSE_IMAGE"); viewer.focusView(); uiState.statusText = "현재 이미지를 닫았습니다" }) }
    function showDemo() {
        if (uiState.loading) return
        confirmRoiDiscard(function() {
            clearImageState(); uiState.roiEditMode = false; uiState.workspaceIndex = 0; uiState.demoMode = true; window.requestContext("image", "DEMO_OPEN"); viewer.defaultView()
            uiState.statusText = "합성 데모 · 실제 XRT 데이터 및 분석 결과 아님"
        })
    }
    function selectImagePath(path) { selectImageFile(fileBridge.localUrl(path)) }
    function selectImageFile(url) {
        if (uiState.project.busy) return
        confirmRoiDiscard(function() { fileBridge.projects.manualImageRequested(); window.startImageLoad(url) })
    }
    function startImageLoad(url) {
        uiState.selectingRoi = false
        uiState.roiEditMode = false
        uiState.opening = true; uiState.loadError = ""; uiState.statusText = "파일 여는 중…"
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
            if (!result.ok) { uiState.loadError = result.error; uiState.statusText = "이미지 열기 실패 · 상세 정보를 확인하세요."; return }
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
            if (!result.workingCopy) {
                // The decoder's format is authoritative, even for a renamed file.
                var isTiff = result.format === "TIFF"
                window.requestContext(isTiff ? "viewer" : "image", isTiff ? "OPEN_TIFF" : "OPEN_IMAGE")
            }
            if (!result.workingCopy || sizeChanged) viewer.defaultView()
            viewer.focusView()
            uiState.statusText = result.format + " · 현재 페이지 준비 완료"
        }
        function onRoiImportFinished(result) {
            window.requestContext("roi", "ROI_IMPORT")
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
    function clearRoi() { uiState.stopCandidateRoiTracking(); uiState.hasRoi = false; uiState.statusText = "ROI를 초기화했습니다" }
    function selectImportedBounds() {
        if (!uiState.analysisEligible || uiState.analysisRunning) return
        var selected = uiState.importedRois.items.filter(function(r) { return r.selected && r.active })
        if (!selected.length) return
        uiState.stopCandidateRoiTracking()
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
        navigationCollapsed = false; inspectorCollapsed = true; statusBarVisible = true; window.requestContext("image", "RESET_LAYOUT")
        if (visibility === Window.FullScreen) showNormal()
        if (uiState.canNavigateImage) viewer.fitView()
    }
    function showInfo(heading, body) { infoDialog.title = heading; infoDialog.bodyText = body; infoDialog.open() }
    Action { id: projectNewAction; objectName: "projectNewAction"; text: "새 분석 프로젝트…"; onTriggered: projectWorkflow.newProject() }
    Action { id: projectOpenAction; objectName: "projectOpenAction"; text: "프로젝트 열기…"; onTriggered: projectWorkflow.openProject() }
    Action { id: projectSaveAction; objectName: "projectSaveAction"; text: "프로젝트 저장"; shortcut: "Ctrl+Alt+S"; enabled: (uiState.project.active || uiState.analysis.hasResult) && !uiState.project.busy; onTriggered: projectWorkflow.saveProject() }
    Action { id: projectSaveAsAction; objectName: "projectSaveAsAction"; text: "다른 이름으로 프로젝트 저장…"; enabled: uiState.project.active && !uiState.project.busy; onTriggered: projectWorkflow.saveAs() }
    Action { id: projectWorkspaceAction; objectName: "projectWorkspaceAction"; text: "프로젝트 · 이미지와 이력…"; enabled: uiState.project.active; onTriggered: projectWorkflow.show() }
    Action { id: openAction; objectName: "openAction"; text: "이미지 열기…"; shortcut: StandardKey.Open; onTriggered: window.openImageDialog() }
    Action { id: importRoisAction; objectName: "importRoisAction"; text: "ImageJ ROI 가져오기…"; enabled: uiState.loadFlow.recordReady && !uiState.loading; onTriggered: { window.requestContext("roi", "ROI_IMPORT"); roiDialog.open() } }
    Action { id: viewerSettingsAction; objectName: "viewerSettingsAction"; text: "뷰어 · 스택 표시 설정…"; enabled: uiState.hasImage; onTriggered: { uiState.workspaceIndex = 0; window.requestContext("viewer", "VIEWER_SETTINGS") } }
    Action { id: saveAction; text: "이미지 복사본 저장…"; shortcut: StandardKey.Save; enabled: uiState.loadFlow.recordReady && !uiState.loading && !fileBridge.imagej.state.busy; onTriggered: window.saveImageCopy() }
    Action { id: demoAction; text: "합성 데모 이미지 보기"; enabled: !uiState.loading; onTriggered: window.showDemo() }
    Action { id: closeImageAction; objectName: "closeImageAction"; text: "현재 이미지 닫기"; shortcut: StandardKey.Close; enabled: uiState.hasImage || uiState.loading; onTriggered: window.closeImage() }
    Action { id: quitAction; text: "종료"; shortcut: "Ctrl+Q"; onTriggered: window.close() }
    Action { id: panAction; objectName: "panAction"; text: "Pan"; shortcut: window.editingText ? "" : "H"; checkable: true; checked: uiState.activeTool === "Pan" && !uiState.roiEditMode; enabled: uiState.canNavigateImage; onTriggered: { uiState.roiEditMode = false; uiState.activeTool = "Pan" } }
    Action { id: roiAction; objectName: "roiAction"; text: "ROI 선택"; shortcut: window.editingText || uiState.tiffMode ? "" : "R"; checkable: true; checked: uiState.activeTool === "ROI" && !uiState.roiEditMode; enabled: !uiState.tiffMode && uiState.canNavigateImage && !uiState.analysisRunning; onTriggered: { uiState.roiEditMode = false; uiState.activeTool = "ROI"; Qt.callLater(function() { viewer.focusView() }) } }
    Action { id: clearRoiAction; objectName: "clearRoiAction"; text: "ROI 초기화"; enabled: uiState.hasRoi && !uiState.loading && !uiState.analysisRunning; onTriggered: window.clearRoi() }
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
    Action { id: runAction; objectName: "runAction"; text: "분석 실행"; enabled: uiState.canAnalyze; onTriggered: { if (!uiState.canAnalyze) return; window.requestContext("analysis", "ANALYSIS_START"); uiState.candidateRoiId = ""; fileBridge.requestAnalysis(uiState.analysisScope, uiState.roiX, uiState.roiY, uiState.roiWidth, uiState.roiHeight, {point_mode: uiState.analysisPointMode}) } }
    Action { id: cancelAnalysisAction; objectName: "cancelAnalysisAction"; text: "분석 취소"; enabled: uiState.analysisRunning; onTriggered: fileBridge.cancelAnalysis() }
    Action { id: settingsAction; objectName: "settingsAction"; text: "설정…"; onTriggered: settingsDialog.openPreferences() }
    Action { id: prepareAnalysisAction; objectName: "prepareAnalysisAction"; text: "분석하기"; enabled: uiState.analysisEligible && uiState.hasLoadedImage && !uiState.loading; onTriggered: { uiState.workspaceIndex = 0; window.openContext("analysis"); viewer.focusView() } }
    Action { id: analysisInputInfoAction; objectName: "analysisInputInfoAction"; text: "분석 입력 상세"; enabled: uiState.analysisEligible && uiState.hasLoadedImage; onTriggered: window.showInfo("분석 입력", uiState.inputPreflight.currentInputDetail + "\n" + uiState.fileName + "\n" + uiState.filePath + "\n표시 밝기·배율과 별개로 원본 픽셀을 사용합니다.") }
    Action { id: modelInfoAction; text: "모델 정보"; onTriggered: window.showInfo("모델 정보", uiState.analysisFlow.modelStatus + "\n모델: " + (uiState.analysis.modelName || "—") + "\n버전: " + (uiState.analysis.modelVersion || "—") + "\n장치: " + (uiState.analysis.device || "—") + "\n모델 폴더: " + (uiState.research.bundle || "—") + (uiState.research.error ? "\n안내: " + uiState.research.error : "") + "\n\n" + uiState.inputPreflight.modelExpectedDetail) }
    Action { id: modelUpdatesAction; objectName: "modelUpdatesAction"; text: "AI 모델 관리…"; onTriggered: modelUpdatesDialog.open() }
    Action { id: guideAction; text: "사용 안내"; onTriggered: window.showInfo("뷰어 사용 안내", "파일 메뉴에서 TIFF/JPG 또는 합성 데모를 여세요.\n상단 패널 메뉴의 뷰어·스택: 페이지 이동과 밝기·대비. ⋯ 메뉴에서도 표시 설정을 열 수 있습니다. 스택은 휠/방향키로 탐색하고 Ctrl+휠로 확대합니다.\nROI 관리: 대응하는 이미지의 .roi/RoiSet.zip 가져오기 및 표시.\nPan / ROI 도구, FIT 화면 맞춤, 100% 원본 픽셀 배율을 지원합니다. 확대 시 보이는 영역을 정밀 읽습니다.\nImageJ frames는 공간 Z축으로 해석하지 않습니다. 상단 분석하기를 누르면 분석 준비 패널을 엽니다. 전체 이미지 또는 ROI를 선택하고 연구 모델로 분석할 수 있습니다.") }
    Action { id: shortcutGuideAction; text: "단축키"; onTriggered: window.showInfo("단축키", "파일\n열기  Ctrl+O     닫기  Ctrl+W     종료  Ctrl+Q\n\n보기\n화면 맞춤  Ctrl+0     실제 크기  Ctrl+1\n확대·축소  Ctrl++ / Ctrl+-     전체 화면  F11\n\n도구\nPan  H     ROI  R\n\n메뉴\nAlt+F / E / V / W / A / T / S / H") }
    Action { id: reportIssueAction; text: "문제 보고"; onTriggered: { if (!fileBridge.openIssueTracker()) window.showInfo("문제 보고", "브라우저를 열지 못했습니다. GitHub 저장소의 Issues에서 보고해 주세요.") } }
    Action { id: aboutAction; objectName: "aboutAction"; text: "프로그램 정보"; onTriggered: window.showInfo("SiC XRT Analyzer", "XRT 이미지 검사·분석\n버전 " + fileBridge.appVersion + "\n" + fileBridge.systemInfo + "\n\nTIFF/JPG · ImageJ ROI 뷰어\n모델 입력 계약 확인 후 분석\nCrystalVision-Lab") }
    Connections {
        target:fileBridge.stack3d
        function onWorkspaceRequested(index) { window.selectWorkspace(index) }
        function onSourceRequested(path) { window.selectImagePath(path) }
        function onFocusRequested(x,y) {uiState.workspaceIndex=0;Qt.callLater(function(){viewer.focusCandidate(x,y)})}
    }
    Connections { target: fileBridge.waferMap; function onWorkspaceRequested(index) { window.selectWorkspace(index) } }
    Connections { target: fileBridge.feedback; function onFocusRequested(x, y) { window.requestContext("feedback", "REVIEW_REQUESTED"); uiState.workspaceIndex = 0; Qt.callLater(function() { viewer.focusCandidate(x, y) }) } }
    Connections { target: fileBridge.research; function onFocusRequested(x, y) { window.requestContext("result", "CANDIDATE_SELECTED"); uiState.workspaceIndex = 0; uiState.updateCandidateRoi(); Qt.callLater(function() { viewer.focusCandidate(x, y) }) } }
    Connections { target: fileBridge.experiments; function onFocusRequested(x, y, w, h) { window.requestContext("result", "CANDIDATE_SELECTED"); uiState.workspaceIndex = 0; Qt.callLater(function() { viewer.focusGeometry(x, y, w, h) }) } }
    ImageJProcessingDialog { id: processingDialog; theme: theme; uiState: uiState; backend: fileBridge.imagej }
    Action { id: appUpdatesAction; objectName: "appUpdatesAction"; text: "프로그램 업데이트…"; onTriggered: { updateNotice.close(); appUpdatesDialog.open() } }
    AppUpdatesDialog { id: appUpdatesDialog }
    Popup {
        id: updateNotice; objectName: "appUpdateNotice"; parent: Overlay.overlay
        x: Math.max(10, window.width - width - 20); y: 20; width: 380
        closePolicy: Popup.NoAutoClose
        ColumnLayout {
            anchors.fill: parent
            Label { text: "새 프로그램 버전 " + fileBridge.appUpdates.state.version + "이 있습니다."; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                Button { text: "업데이트 보기"; onClicked: appUpdatesAction.trigger() }
                Button { text: "나중에"; onClicked: updateNotice.close() }
            }
        }
    }
    Connections {
        target: fileBridge.appUpdates
        function onUpdateAvailable() { if (!appUpdatesDialog.opened) updateNotice.open() }
        function onInstallVerified() {
            projectWorkflow.guard(function() {
                window.confirmRoiDiscard(function() {
                    if (fileBridge.appUpdates.armInstall()) { window.allowQuit = true; window.close() }
                })
            })
        }
    }
    ModelUpdatesDialog { id: modelUpdatesDialog; onLocalModelRequested: researchModelDialog.open() }
    SafeFolderDialog { id: researchModelDialog; objectName: "researchModelDialog"; title: "고정 모델 폴더 선택"; onAccepted: fileBridge.research.loadModel(selectedFolder.toString()) }
    SafeFileDialog { id: coordinatesDialog; title: "현재 영상의 좌표 CSV"; nameFilters: ["좌표 CSV (*.csv)"]; onAccepted: fileBridge.research.setCoordinates(selectedFile.toString()) }
    SafeFolderDialog { id: resultsDialog; title: "결과를 저장할 폴더"; onAccepted: fileBridge.research.exportResult(selectedFolder.toString()) }
    SafeFileDialog { id: openDialog; objectName: "openImageDialog"; title: "XRT 이미지 열기"; nameFilters: ["XRT 이미지 (*.tif *.tiff *.jpg *.jpeg)", "TIFF 이미지 (*.tif *.tiff)", "JPEG 이미지 (*.jpg *.jpeg)", "모든 파일 (*)"]; onAccepted: window.selectImageFile(selectedFile.toString()) }
    SafeFileDialog { id: roiDialog; objectName: "roiFileDialog"; title: "대응하는 이미지의 ImageJ ROI 가져오기"; fileMode: FileDialog.OpenFiles; nameFilters: ["ImageJ ROI (*.roi *.zip)", "ROI 파일 (*.roi)", "ROI ZIP (*.zip)"]; onAccepted: fileBridge.importRois(selectedFiles) }
    SafeFileDialog { id: roiSaveDialog; objectName: "roiSaveDialog"; title: "새 ROI ZIP 복사본 저장 (기존 파일 덮어쓰기 불가)"; fileMode: FileDialog.SaveFile; nameFilters: ["ROI ZIP (*.zip)"]; defaultSuffix: "zip"; onAccepted: fileBridge.saveRoiCopy(selectedFile.toString()) }
    SafeFileDialog { id: imageSaveDialog; title: "이미지 전체 파일의 새 복사본 저장 (기존 파일 덮어쓰기 불가)"; fileMode: FileDialog.SaveFile; nameFilters: uiState.imageFormat === "JPEG" ? ["JPEG (*.jpg *.jpeg)"] : ["TIFF (*.tif *.tiff)"]; defaultSuffix: uiState.imageFormat === "JPEG" ? "jpg" : "tif"; onAccepted: fileBridge.imagej.saveImageCopy(selectedFile.toString()) }
    SafeFileDialog { id: measurementsSaveDialog; title: "측정 결과 TSV 저장"; fileMode: FileDialog.SaveFile; nameFilters: ["TSV (*.tsv)"]; defaultSuffix: "tsv"; onAccepted: fileBridge.imagej.saveResults(selectedFile.toString()) }
    SurfaceDialog {
        id: roiDiscardDialog; objectName: "roiDiscardDialog"; modal: true; title: "저장하지 않은 ROI 변경"
        x: (window.width - width) / 2; y: (window.height - height) / 2
        standardButtons: Dialog.Discard | Dialog.Cancel
        Label { text: "ROI ZIP 복사본을 저장하지 않은 변경이 있습니다.\n변경을 버리고 계속할까요? 취소 후 ROI 관리에서 저장할 수 있습니다." }
        onDiscarded: { var next = window.discardNext; window.discardNext = null; if (next) next() }
        onRejected: window.discardNext = null
    }
    AppDialog { id: infoDialog; objectName: "infoDialog"; theme: theme; x: (window.width - width) / 2; y: (window.height - height) / 2 }
    SettingsDialog { id: settingsDialog; theme: theme; fileBridge: window.desktopBridge; x: (window.width - width) / 2; y: (window.height - height) / 2; onPreferencesApplied: function(preferences) { window.applyPreferences(preferences) } }
    ImageJDialog { id: imagejDialog; parent: Overlay.overlay; theme: theme; backend: fileBridge.imagej; x: (window.width - width) / 2; y: (window.height - height) / 2 }
    StackMeasurementDialog { id: measurementDialog; parent: Overlay.overlay; theme: theme; backend: fileBridge.stackMeasurements; uiState: uiState; x: (window.width-width)/2; y: (window.height-height)/2 }
    PluginWindowsDialog { parent: Overlay.overlay; theme: theme; backend: fileBridge.imagej; x: (window.width-width)/2; y: (window.height-height)/2 }
    Connections { target: uiState; function onImagejFeaturesVisibleChanged() { if (!uiState.imagejFeaturesVisible) { imagejDialog.close(); measurementDialog.close() } } }
}
