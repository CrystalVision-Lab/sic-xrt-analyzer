import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property QtObject theme
    property QtObject uiState
    property var actions
    spacing: 5
    signal modelRequested()
    signal coordinatesRequested()
    SectionHeader { theme: root.theme; text: "모델"; Layout.fillWidth: true; Layout.topMargin: 12 }
    AppButton { objectName: "researchModelButton"; theme: root.theme; text: uiState.research.loading ? "모델 불러오는 중…" : "연구 모델 폴더 선택…"; enabled: !uiState.analysisRunning && !uiState.research.loading; Layout.fillWidth: true; onClicked: root.modelRequested() }
    ModelDetails { theme: root.theme; uiState: root.uiState; Layout.fillWidth: true }
    AppButton { objectName: "contextModelInfo"; theme: root.theme; action: root.actions.modelInfo; text: "모델 상세 정보…"; quiet: true; Layout.fillWidth: true }
    ModelStatusGroup { theme: root.theme; uiState: root.uiState; Layout.fillWidth: true }
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
}
