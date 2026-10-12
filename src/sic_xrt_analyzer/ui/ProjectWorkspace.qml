import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

Item {
    id: root
    property QtObject theme
    property QtObject uiState
    property var hostWindow
    readonly property var project: uiState.project
    property var nextAction: null
    property var afterSave: null
    property bool afterCaptureSave: false
    property bool creating: false
    property string chosenSource: ""
    property string relinkId: ""
    function guard(action) { hostWindow.confirmReviewDiscard(function() { root.guardProject(action) }) }
    function guardProject(action) {
        if (uiState.analysisRunning) { hostWindow.showInfo("분석 진행 중", "분석을 완료하거나 취소한 뒤 프로젝트를 전환하세요."); return }
        if (project.busy) { hostWindow.showInfo("프로젝트 작업 중", "작업이 완료되거나 취소된 뒤 다시 시도하세요."); return }
        if (!project.dirty) { action(); return }
        nextAction = action; dirty.open()
    }
    function newProject() { guard(function() { hostWindow.confirmRoiDiscard(function() { root.creating = true; editor.open() }) }) }
    function openProject() { guard(function() { hostWindow.confirmRoiDiscard(function() { opener.open() }) }) }
    function recentProject(path) { guard(function() { hostWindow.confirmRoiDiscard(function() { fileBridge.projects.open(path) }) }) }
    function closeProject() { guard(function() { hostWindow.confirmRoiDiscard(function() { fileBridge.projects.close() }) }) }
    function saveProject() {
        if (uiState.projectReview.pending) { hostWindow.showInfo("검수 초안 작성 중", "판정·도형을 검수 기록으로 확정하거나 취소한 뒤 프로젝트를 저장하세요."); return }
        if (!project.active) { afterCaptureSave = true; fileBridge.projects.captureCurrent(); return }
        if (project.path) fileBridge.projects.save("", "")
        else { creating = false; editor.open() }
    }
    function saveAs() { if (uiState.projectReview.pending) { hostWindow.showInfo("검수 초안 작성 중", "검수 기록을 먼저 확정하거나 취소하세요."); return }; creating = false; editor.open() }
    function picked() { return project.sources.find(function(s) { return s.id === root.chosenSource }) || ({}) }
    function selectImage(id, run) {
        hostWindow.confirmRoiDiscard(function() { if (run) fileBridge.projects.selectRun(run); else fileBridge.projects.selectSource(id, "") })
        workspace.close()
    }
    function openRecentManager() { recentManager.open() }
    function show() { if (!project.sources.some(function(s) { return s.id === root.chosenSource }) && project.sources.length) chosenSource = project.sources[0].id; workspace.open() }
    Connections {
        target: fileBridge.projects
        function onSourceRequested(path) { hostWindow.clearImageState(); if (path) hostWindow.startImageLoad(fileBridge.localUrl(path)) }
        function onResultRequested() { hostWindow.requestContext("result", "MANUAL"); hostWindow.inspectorCollapsed = false }
        function onOperationFinished(job, ok) {
            if (root.afterCaptureSave && job === "capture") { root.afterCaptureSave = false; if (ok) { root.creating = false; editor.open() } }
            if (root.afterSave && ok) {
                if (project.busy) return
                if (project.dirty) { if (project.path) fileBridge.projects.save("", ""); return }
                var action = root.afterSave; root.afterSave = null; action()
            }
            if (!ok) root.afterSave = null
        }
    }
    SurfaceDialog {
        id: dirty; objectName: "projectDirtyDialog"; parent: Overlay.overlay; modal: true
        title: "저장되지 않은 분석 프로젝트"; width: 480; x: (parent.width-width)/2; y: (parent.height-height)/2
        standardButtons: Dialog.NoButton
        ColumnLayout {
            anchors.fill: parent; spacing: theme.spacingMd
            Text { text: "저장되지 않은 분석 데이터가 있습니다."; color: theme.text; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                AppButton { objectName: "projectDirtySave"; theme: root.theme; text: "저장"; onClicked: { dirty.close(); root.afterSave = root.nextAction; root.nextAction = null; root.saveProject() } }
                AppButton { objectName: "projectDirtyDiscard"; theme: root.theme; text: "저장하지 않고 계속"; onClicked: { dirty.close(); var action = root.nextAction; root.nextAction = null; if (action) action() } }
                AppButton { objectName: "projectDirtyCancel"; theme: root.theme; text: "취소"; onClicked: { root.nextAction = null; dirty.close() } }
            }
        }
    }
    SurfaceDialog {
        id: editor; objectName: "projectSaveDialog"; parent: Overlay.overlay; modal: true
        title: root.creating ? "새 분석 프로젝트" : "분석 프로젝트 저장"; width: 620; x: (parent.width-width)/2; y: (parent.height-height)/2
        standardButtons: Dialog.NoButton
        onOpened: { nameInput.text = project.name || "새 분석 프로젝트"; pathInput.text = root.creating ? "" : project.path }
        onRejected: root.afterSave = null
        ColumnLayout {
            anchors.fill: parent; spacing: theme.spacingSm
            Text { text: "프로젝트 이름"; color: theme.text }
            TextField { id: nameInput; objectName: "projectNameInput"; Layout.fillWidth: true; maximumLength: 200; color: theme.text; background: Rectangle { color: theme.panel; border.color: theme.border } }
            Text { text: "저장 위치 (.json)"; color: theme.text }
            RowLayout {
                Layout.fillWidth: true
                TextField { id: pathInput; objectName: "projectPathInput"; Layout.fillWidth: true; color: theme.text; background: Rectangle { color: theme.panel; border.color: theme.border } }
                AppButton { objectName: "projectChoosePath"; theme: root.theme; text: "찾아보기…"; onClicked: destination.open() }
            }
            Text { Layout.fillWidth: true; text: "원본 JPG/TIFF는 포함하지 않습니다. 최초 JPG SHA 검증과 실험 종속 자산 저장을 수행합니다. 다른 위치 저장은 동일 프로젝트의 복사본이며 새 파일 경로가 필요합니다."; wrapMode: Text.Wrap; color: theme.muted; font.pixelSize: theme.smallSize }
            RowLayout {
                AppButton { objectName: "projectCommitSave"; theme: root.theme; text: root.creating ? "프로젝트 생성" : "프로젝트 저장"; enabled: nameInput.text.trim().length > 0 && pathInput.text.length > 0 && !project.busy; onClicked: { editor.close(); if (root.creating) fileBridge.projects.create(nameInput.text, pathInput.text); else fileBridge.projects.save(pathInput.text, nameInput.text) } }
                AppButton { objectName: "projectCancelSave"; theme: root.theme; text: "취소"; onClicked: { root.afterSave = null; editor.close() } }
            }
        }
    }
    SafeFileDialog { id: opener; objectName: "projectOpenFileDialog"; title: "분석 프로젝트 열기"; nameFilters: ["분석 프로젝트 (*.json)"]; onAccepted: fileBridge.projects.open(selectedFile.toString()) }
    SafeFileDialog { id: destination; objectName: "projectSaveFileDialog"; title: "프로젝트 저장 위치"; fileMode: FileDialog.SaveFile; nameFilters: ["분석 프로젝트 (*.json)"]; defaultSuffix: "json"; onAccepted: pathInput.text = selectedFile.toString() }
    SafeFileDialog { id: relinkPicker; objectName: "projectRelinkFileDialog"; title: "동일한 원본 다시 연결 (SHA 검증 필수)"; nameFilters: ["XRT 원본 (*.jpg *.jpeg *.tif *.tiff)"]; onAccepted: fileBridge.projects.relink(root.relinkId, selectedFile.toString()) }
    SurfaceDialog {
        id: workspace; objectName: "projectWorkspaceDialog"; parent: Overlay.overlay; modal: true
        title: "분석 프로젝트 · 이미지와 이력"; width: Math.min(850,parent.width-40); height: Math.min(610,parent.height-40); x: (parent.width-width)/2; y: (parent.height-height)/2
        standardButtons: Dialog.Close
        ColumnLayout {
            anchors.fill: parent; spacing: theme.spacingSm
            Text { textFormat: Text.PlainText; text: project.name + " · 이미지 " + project.sourceCount + "개 · 분석 실행 " + project.runCount + "회"; color: theme.text; font.pixelSize: theme.titleSize; Layout.fillWidth: true }
            Text { text: project.path || "저장 위치 미지정"; color: theme.muted; elide: Text.ElideMiddle; Layout.fillWidth: true; font.pixelSize: theme.smallSize }
            RowLayout {
                AppButton { objectName: "projectRegisterImage"; theme: root.theme; text: "현재 원본 등록"; enabled: uiState.hasLoadedImage && !project.busy; onClicked: fileBridge.projects.registerCurrent() }
                AppButton { objectName: "projectCaptureLive"; theme: root.theme; text: "현재 분석 추가"; enabled: uiState.analysis.hasResult && uiState.imageFormat === "JPEG" && !project.busy; onClicked: fileBridge.projects.captureCurrent() }
                AppButton { objectName: "projectCaptureExperiment"; theme: root.theme; text: "실험 근거 추가"; enabled: uiState.experiment.total > 0 && uiState.imageFormat === "JPEG" && !project.busy; onClicked: fileBridge.projects.importCurrentExperiment() }
                AppButton { objectName: "projectRestoreView"; theme: root.theme; text: "마지막 열람 복원"; enabled: !!project.lastView.source_id && !project.busy; onClicked: { hostWindow.confirmRoiDiscard(function() { fileBridge.projects.restoreView() }); workspace.close() } }
                AppButton { objectName: "projectShowLive"; theme: root.theme; text: "현재 분석 보기"; enabled: !project.busy; onClicked: { fileBridge.research.show_live(); workspace.close(); hostWindow.requestContext("result", "MANUAL") } }
            }
            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: true
                ListView {
                    objectName: "projectSourceList"; Layout.preferredWidth: 230; Layout.fillHeight: true; clip: true; model: project.sources; ScrollBar.vertical: ScrollBar {}
                    delegate: ItemDelegate {
                        required property var modelData; required property int index
                        width: ListView.view.width; height: 56; objectName: "projectSource" + index
                        highlighted: modelData.id === root.chosenSource; onClicked: root.chosenSource = modelData.id
                        ToolTip.visible: hovered; ToolTip.text: modelData.path
                        contentItem: Column {
                            spacing: 3
                            Text { width: parent.width; textFormat: Text.PlainText; text: modelData.name; elide: Text.ElideMiddle; color: theme.text; font.pixelSize: theme.bodySize }
                            Text { width: parent.width; text: modelData.format === "TIFF" ? "스택 데이터 · " + modelData.pages + "페이지" : "분석 이력 " + modelData.runs + "회"; color: theme.muted; font.pixelSize: theme.captionSize }
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    Text { textFormat: Text.PlainText; text: root.picked().name || "원본을 선택하세요"; color: theme.text; Layout.fillWidth: true; elide: Text.ElideMiddle }
                    Text { objectName: "projectSourceStatus"; text: (root.picked().status || "") + "\n" + (root.picked().detail || ""); wrapMode: Text.Wrap; color: theme.muted; font.pixelSize: theme.smallSize; Layout.fillWidth: true }
                    ComboBox {
                        objectName: "projectImageRole"; Layout.fillWidth: true; model: ["미지정", "열처리 전", "열처리 후", "기준 이미지"]
                        readonly property var values: ["UNKNOWN","BEFORE_ANNEALING","AFTER_ANNEALING","REFERENCE"]
                        currentIndex: Math.max(0,values.indexOf(root.picked().role || "UNKNOWN")); enabled: !!root.picked().id && !project.busy
                        onActivated: fileBridge.projects.setRole(root.picked().id,values[currentIndex])
                    }
                    RowLayout {
                        AppButton { objectName: "projectViewSource"; theme: root.theme; text: "영상 열기"; enabled: !!root.picked().id && !project.busy; onClicked: root.selectImage(root.picked().id, "") }
                        AppButton { objectName: "projectVerifySource"; theme: root.theme; text: "SHA 확인…"; enabled: !!root.picked().id && !project.busy; onClicked: fileBridge.projects.verifySource(root.picked().id) }
                        AppButton { objectName: "projectRelinkSource"; theme: root.theme; text: "원본 다시 연결…"; enabled: !!root.picked().hashAvailable && !project.busy; onClicked: { root.relinkId = root.picked().id; relinkPicker.open() } }
                    }
                    Text { text: "저장된 분석 이력 · 선택해도 모델을 재실행하지 않습니다."; color: theme.muted; font.pixelSize: theme.captionSize; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    ListView {
                        objectName: "projectRunList"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; ScrollBar.vertical: ScrollBar {}
                        model: project.runs.filter(function(r) { return r.sourceId === root.chosenSource })
                        delegate: ItemDelegate {
                            required property var modelData; required property int index; width: ListView.view.width; height: 64; objectName: "projectRun" + index
                            text: modelData.date.slice(0,19) + " " + modelData.date.slice(-6) + " · " + modelData.scope + " · 후보 " + modelData.count + "개\n모델 " + modelData.model.slice(0,16) + " · Run " + modelData.id.slice(0,8) + " · " + modelData.status
                            enabled: !project.busy && root.picked().format !== "TIFF"
                            onClicked: root.selectImage(modelData.sourceId,modelData.id)
                        }
                    }
                    Text { text: "구조 제안 " + project.structureCount + "개 · 실제 정확도 미검증"; color: theme.muted; font.pixelSize: theme.captionSize }
                }
            }
            RowLayout {
                AppButton { objectName: "projectSaveWorkspace"; theme: root.theme; text: "프로젝트 저장"; enabled: !project.busy; onClicked: root.saveProject() }
                AppButton { theme: root.theme; text: "다른 위치에 저장…"; enabled: !project.busy; onClicked: root.saveAs() }
                AppButton { theme: root.theme; text: "프로젝트 닫기"; enabled: !project.busy; onClicked: { workspace.close(); root.closeProject() } }
            }
        }
    }
    SurfaceDialog {
        id: recentManager; objectName: "recentProjectManager"; parent: Overlay.overlay; modal: true
        title: "최근 프로젝트"; width: 650; height: 350; x: (parent.width-width)/2; y: (parent.height-height)/2; standardButtons: Dialog.Close
        ListView {
            anchors.fill: parent; clip: true; model: project.recent; ScrollBar.vertical: ScrollBar {}
            delegate: RowLayout {
                required property var modelData; width: ListView.view.width; height: 56
                Text { textFormat: Text.PlainText; text: modelData.name + "\n" + modelData.path; color: theme.text; Layout.fillWidth: true; elide: Text.ElideMiddle; font.pixelSize: theme.smallSize }
                AppButton { theme: root.theme; text: "열기"; onClicked: { recentManager.close(); root.recentProject(modelData.path) } }
                AppButton { theme: root.theme; text: "목록에서 제거"; onClicked: fileBridge.projects.removeRecent(modelData.path) }
            }
        }
    }
    SurfaceDialog {
        id: status; objectName: "projectOperationDialog"; parent: Overlay.overlay; modal: true
        title: project.error ? "프로젝트 작업 오류" : "프로젝트 작업 중"; width: 520; x: (parent.width-width)/2; y: (parent.height-height)/2
        standardButtons: Dialog.Close
        closePolicy: Popup.NoAutoClose
        ColumnLayout {
            anchors.fill: parent
            Text { text: project.error || project.job + " · 원본 참조·이력·자산을 확인하고 있습니다."; wrapMode: Text.Wrap; color: project.error ? theme.warning : theme.text; Layout.fillWidth: true }
            ProgressBar { Layout.fillWidth: true; visible: project.busy; indeterminate: !project.total; from: 0; to: project.total || 1; value: project.done }
            AppButton { theme: root.theme; text: "취소"; visible: project.canCancel; onClicked: { fileBridge.projects.cancel(); status.close() } }
            Text { visible: !!project.error; text: "기존 파일과 현재 변경 내용은 보존됩니다. Revision 충돌은 재로드하거나 새 경로에 복사 저장하세요."; color: theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
        }
    }
    Connections {
        target: fileBridge.projects
        function onChanged() { if ((project.busy && project.job !== "capture" && project.job !== "register") || project.error) status.open(); else status.close() }
    }
}
