import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "analysisContext"
    property QtObject theme
    property QtObject uiState
    readonly property string informationPriority: "primary"
    property var actions
    signal modelRequested()
    signal coordinatesRequested()
    spacing: 5
    SectionHeader { theme: root.theme; text: "ROI"; Layout.fillWidth: true }
    Text { visible: !uiState.hasRoi; text: "선택된 ROI 없음\n도구 모음의 ROI로 영역을 선택하세요."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
    Repeater {
        model: ["X", "Y", "너비", "높이"]
        InfoRow { required property int index; required property string modelData; theme: root.theme; label: modelData; value: uiState.hasRoi ? [uiState.roiX, uiState.roiY, uiState.roiWidth, uiState.roiHeight][index] + " px" : "—"; Layout.fillWidth: true }
    }
    SectionHeader { theme: root.theme; text: "모델"; Layout.fillWidth: true; Layout.topMargin: 12 }
    AppButton { objectName: "researchModelButton"; theme: root.theme; text: uiState.research.loading ? "모델 불러오는 중…" : "연구 모델 폴더 선택…"; enabled: !uiState.analysisRunning && !uiState.research.loading; Layout.fillWidth: true; onClicked: root.modelRequested() }
    ModelDetails { theme: root.theme; uiState: root.uiState; Layout.fillWidth: true }
    ModelStatusGroup { theme: root.theme; uiState: root.uiState; Layout.fillWidth: true }
    Text { text: uiState.analysisReason; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
    Text { visible: !!uiState.research.error; text: uiState.research.error; color: theme.warning; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
    Text { text: "연구용 후보 분류 · BPD 오탐 주의\n확정 라벨·실제 결함 전체 수가 아닙니다."; color: theme.warning; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
    AppComboBox {
        objectName: "analysisPointModeCombo"; theme: root.theme; Layout.fillWidth: true
        model: ["밝기 대비 후보 찾기", "제공 좌표 CSV 분류"]
        enabled: !uiState.analysisRunning
        currentIndex: uiState.analysisPointMode === "provided_coordinates" ? 1 : 0
        onActivated: uiState.analysisPointMode = currentIndex === 1 ? "provided_coordinates" : "contrast_proposals"
    }
    AppButton { objectName: "analysisCoordinatesButton"; theme: root.theme; text: "현재 영상 좌표 CSV…"; visible: uiState.analysisPointMode === "provided_coordinates"; enabled: uiState.hasLoadedImage && !uiState.analysisRunning; Layout.fillWidth: true; onClicked: root.coordinatesRequested() }
    Text { visible: uiState.analysisPointMode === "provided_coordinates"; text: "불러온 좌표 " + uiState.research.coordinatesCount + "개 · x,y 원본 좌표"; color: theme.muted; font.pixelSize: 11; Layout.fillWidth: true }
    InfoRow { theme: root.theme; label: "입력 원본"; value: uiState.analysis.inputSource || "—"; Layout.fillWidth: true }
    AppComboBox {
        objectName: "analysisScopeCombo"; theme: root.theme; Layout.fillWidth: true
        model: ["분석 범위 선택", "전체 이미지", "ROI"]
        enabled: uiState.modelAvailable && !uiState.analysisRunning
        currentIndex: uiState.analysisScope === "FULL_IMAGE" ? 1 : uiState.analysisScope === "ROI" ? 2 : 0
        onActivated: uiState.analysisScope = ["", "FULL_IMAGE", "ROI"][currentIndex]
    }
    RowLayout {
        objectName: "analysisPrimaryActions"
        Layout.fillWidth: true
        AppButton { objectName: "contextRunAnalysis"; theme: root.theme; action: root.actions.run; text: "분석 실행"; iconName: "run"; primary: true; Layout.fillWidth: true; tip: uiState.analysisReason }
        AppButton { objectName: "contextCancelAnalysis"; theme: root.theme; action: root.actions.cancelAnalysis; text: "취소"; visible: uiState.analysisRunning }
    }
    SectionHeader { theme: root.theme; text: "작업 상태"; Layout.fillWidth: true; Layout.topMargin: 12 }
    InfoRow { theme: root.theme; label: "이미지"; value: uiState.hasLoadedImage ? "준비 완료" : uiState.demoMode ? "합성 데모" : "이미지 없음"; Layout.fillWidth: true }
    InfoRow { theme: root.theme; label: "ROI"; value: uiState.hasRoi ? "선택됨" : "미선택"; Layout.fillWidth: true }
    InfoRow { theme: root.theme; label: "분석"; value: uiState.analysis.statusLabel; valueColor: uiState.analysis.state === "FAILED" || !uiState.modelAvailable ? theme.warning : theme.text; Layout.fillWidth: true }
}
