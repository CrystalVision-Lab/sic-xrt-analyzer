import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "roiContext"
    property QtObject theme
    property QtObject uiState
    property var actions
    readonly property QtObject flow: uiState.roiFlow
    readonly property string informationPriority: "primary"
    signal importRequested()
    signal boundsRequested()
    signal saveRequested()
    spacing: 6
    ColumnLayout {
        Layout.fillWidth: true; spacing: 4
        SectionHeader { theme: root.theme; text: "분석 영역"; Layout.fillWidth: true }
        Text { objectName: "analysisRoiState"; text: flow.areaSummary; Accessible.name: text; color: theme.text; font.bold: true; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Text { visible: flow.hasArea; text: "X " + uiState.roiX + " · Y " + uiState.roiY; color: theme.muted; font.pixelSize: 10; Layout.fillWidth: true }
        Text { objectName: "analysisAreaHint"; text: flow.areaHint; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
        RowLayout {
            Layout.fillWidth: true
            AppButton { objectName: "roiSpecifyArea"; theme: root.theme; action: root.actions.roi; text: flow.hasArea ? "다시 지정 (R)" : "영역 지정 (R)"; primary: !flow.hasArea; enabled: root.actions.roi.enabled && flow.areaPhase !== "DISABLED" }
            AppButton { objectName: "roiRemoveArea"; theme: root.theme; action: root.actions.clearRoi; text: "제거"; quiet: true; visible: flow.hasArea }
        }
    }
    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.border }
    ColumnLayout {
        Layout.fillWidth: true; spacing: 4
        SectionHeader { theme: root.theme; text: "ImageJ ROI"; Layout.fillWidth: true }
        Text { objectName: "imagejRoiState"; text: flow.imagejSummary; Accessible.name: text + ", " + flow.selectionLabel; color: theme.text; font.bold: true; font.pixelSize: 12; Layout.fillWidth: true }
        Text { objectName: "selectedRoiSummary"; text: flow.selectionLabel; color: theme.text; font.pixelSize: 12; elide: Text.ElideMiddle; Layout.fillWidth: true }
        Text { objectName: "roiToolHint"; text: flow.imagejHint; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Text {
            visible: !!flow.selected; objectName: "selectedRoiBounds"; Layout.fillWidth: true; elide: Text.ElideRight; color: theme.muted; font.pixelSize: 10
            text: flow.selected ? "X " + flow.selected.bbox[0] + "–" + (flow.selected.bbox[0] + flow.selected.bbox[2]) + " · Y " + flow.selected.bbox[1] + "–" + (flow.selected.bbox[1] + flow.selected.bbox[3]) + " · " + (flow.selected.page ? "페이지 " + flow.selected.page : "모든 페이지") : ""
        }
        RowLayout {
            Layout.fillWidth: true
            AppButton { objectName: "importRoisButton"; theme: root.theme; action: root.actions.importRois; text: "가져오기…"; quiet: true; enabled: root.actions.importRois.enabled && !uiState.importedRois.busy }
            AppButton { objectName: "roiManagerButton"; theme: root.theme; action: root.actions.advanced.roiManager; text: "ROI 관리자"; quiet: true; onClicked: roiList.forceActiveFocus() }
        }
        RowLayout {
            Layout.fillWidth: true
            AppButton { objectName: "roiEditButton"; theme: root.theme; action: root.actions.advanced.editRoi; text: uiState.roiEditMode ? "편집 종료" : "편집" }
            AppButton { objectName: "roiEditorDetails"; theme: root.theme; text: "세부 설정…"; quiet: true; enabled: uiState.hasLoadedImage && !uiState.loading && !uiState.importedRois.busy; onClicked: editDialog.open() }
        }
        RowLayout {
            visible: flow.imagejPhase === "ERROR"; Layout.fillWidth: true
            Text { objectName: "roiErrorSummary"; text: "ROI 작업 오류 · 상세 정보를 확인하세요."; color: theme.warning; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
            AppButton { objectName: "roiErrorDetails"; theme: root.theme; text: "오류 정보"; quiet: true; onClicked: errorDialog.open() }
        }
    }
    Text { visible: flow.count > 0; text: "기록 목록"; color: theme.muted; font.pixelSize: 11 }
    ListView {
        id: roiList; objectName: "roiRecordList"
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 60
        clip: true; spacing: 2; model: uiState.importedRois.items
        ScrollBar.vertical: ScrollBar {}
        delegate: ItemDelegate {
            required property var modelData
            required property int index
            objectName: "roiRecord" + index
            width: roiList.width; height: 36
            Accessible.name: "ImageJ ROI " + (index + 1) + ", " + flow.shape(modelData) + ", " + modelData.name
            Accessible.selected: modelData.selected
            onClicked: fileBridge.selectImportedRoi(modelData.id)
            background: Rectangle { color: modelData.selected ? theme.accentPale : parent.hovered ? theme.hover : "transparent"; radius: 3 }
            contentItem: RowLayout {
                spacing: 6
                AppCheckBox { objectName: "roiVisible" + index; theme: root.theme; text: ""; checked: modelData.visible; onToggled: fileBridge.setImportedRoiVisible(modelData.id, checked) }
                Text { text: "#" + (index + 1) + " " + flow.shape(modelData); color: theme.text; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                Text { visible: !modelData.active; text: modelData.page && modelData.page !== uiState.pageIndex + 1 ? "다른 페이지" : "미표시"; color: theme.muted; font.pixelSize: 10 }
                AppButton { objectName: "roiRemoveRecord" + index; theme: root.theme; quiet: true; text: "×"; tip: modelData.name + " 기록 제거"; Accessible.name: modelData.name + " ROI 기록 제거"; onClicked: fileBridge.removeImportedRoi(modelData.id) }
            }
        }
        onModelChanged: Qt.callLater(function() {
            var index = uiState.importedRois.items.findIndex(function(r) { return r.selected })
            if (index >= 0) roiList.positionViewAtIndex(index, ListView.Contain)
        })
    }
    RowLayout {
        Layout.fillWidth: true
        AppButton { objectName: "roiSaveEntry"; theme: root.theme; quiet: true; text: "ROI ZIP 저장…"; enabled: flow.count > 0 && !uiState.loading && !uiState.importedRois.busy; onClicked: root.saveRequested() }
        Item { Layout.fillWidth: true }
        AppButton { objectName: "clearRoiRecords"; theme: root.theme; quiet: true; text: "목록 비우기"; enabled: flow.count > 0 || uiState.importedRois.busy; onClicked: fileBridge.clearImportedRois() }
    }
    Text { Layout.fillWidth: true; text: uiState.importedRois.dirty ? "저장하지 않은 ROI 변경이 있습니다." : "분석 범위와 별도 기록 · 원본은 덮어쓰지 않습니다."; color: uiState.importedRois.dirty ? theme.warning : theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap }
    Dialog {
        id: editDialog; objectName: "roiEditorDialog"; parent: Overlay.overlay; title: "ImageJ ROI 세부 설정"
        modal: true; width: Math.min(540, parent.width - 40); height: Math.min(parent.height - 60, editorContent.implicitHeight + 100)
        x: (parent.width - width)/2; y: (parent.height - height)/2; standardButtons: Dialog.Close
        onClosed: Qt.callLater(function() { if (root.uiState.roiInteraction) root.uiState.roiInteraction.focusView() })
        contentItem: ScrollView {
            id: editScroll; clip: true; contentWidth: availableWidth; contentHeight: editorContent.implicitHeight
            ColumnLayout {
                id: editorContent
                width: editScroll.availableWidth; spacing: 10
                RoiEditor { id: editor; theme: root.theme; uiState: root.uiState; actions: root.actions; Layout.fillWidth: true; onSaveRequested: root.saveRequested() }
                AppButton { objectName: "selectImportedBoundsButton"; theme: root.theme; text: "분석 영역으로 외접 사각형 선택"; Layout.fillWidth: true; enabled: !uiState.loading && !uiState.analysisRunning && uiState.importedRois.items.some(function(r) { return r.selected && r.active }); onClicked: root.boundsRequested() }
                Text { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "명시적으로 선택한 외접 사각형만 분석 영역에 복사합니다. ROI 도형 마스크 분석은 연결되지 않았습니다."; color: theme.muted; font.pixelSize: 11 }
            }
        }
    }
    Dialog {
        id: errorDialog; objectName: "roiErrorDialog"; parent: Overlay.overlay; title: "ROI 오류 정보"
        modal: true; width: Math.min(540, parent.width - 40); height: Math.min(420, parent.height - 60); x: (parent.width - width)/2; y: (parent.height - height)/2; standardButtons: Dialog.Close
        contentItem: ScrollView {
            id: errorScroll; clip: true; contentWidth: availableWidth
            TextArea { objectName: "roiErrorText"; width: errorScroll.availableWidth; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; text: uiState.importedRois.errors.join("\n") + (uiState.importedRois.editError ? "\n" + uiState.importedRois.editError : "") }
        }
    }
}
