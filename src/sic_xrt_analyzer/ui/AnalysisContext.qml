import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "analysisContext"
    property QtObject theme
    property QtObject uiState
    property var actions
    readonly property string informationPriority: "primary"
    property bool advancedExpanded: false
    signal modelRequested()
    signal coordinatesRequested()
    spacing: theme.spacingXs
    AnalysisSettings { objectName: "analysisSettings"; theme: root.theme; uiState: root.uiState; actions: root.actions; Layout.fillWidth: true; onModelRequested: root.modelRequested() }
    AnalysisRegion { objectName: "analysisRegion"; theme: root.theme; uiState: root.uiState; actions: root.actions; Layout.fillWidth: true }
    RowLayout {
        Layout.fillWidth: true
        Text { objectName: "analysisInputSummary"; text: "입력 · " + uiState.inputPreflight.currentInputSummary; Accessible.name: uiState.inputPreflight.accessibleSummary; color: theme.muted; font.pixelSize: theme.bodySize; elide: Text.ElideRight; Layout.fillWidth: true }
        AppButton { objectName: "analysisInputInfo"; theme: root.theme; text: "상세"; quiet: true; action: root.actions.analysisInputInfo; Accessible.name: "분석 입력 상세 정보" }
    }
    Text {
        objectName: "analysisModelInputRequirement"
        visible: uiState.inputCompatibilityState === "INCOMPATIBLE"
        text: "모델 요구 · " + uiState.inputPreflight.modelExpectedSummary
        color: theme.warning; font.pixelSize: theme.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true
        Accessible.name: uiState.inputPreflight.accessibleSummary
    }
    Text { visible: uiState.analysisPointMode === "provided_coordinates"; text: "제공 좌표 CSV · " + uiState.research.coordinatesCount + "개 (고급 설정)"; color: theme.muted; font.pixelSize: theme.smallSize; Layout.fillWidth: true }
    AppButton {
        objectName: "analysisAdvancedToggle"; theme: root.theme; quiet: true; Layout.fillWidth: true
        text: "고급 설정 " + (root.advancedExpanded ? "▾" : "▸"); checkable: true; checked: root.advancedExpanded
        Accessible.name: "분석 고급 설정"; Accessible.description: "후보 찾기 방식과 좌표 CSV"
        onClicked: root.advancedExpanded = !root.advancedExpanded
    }
    ScrollView {
        objectName: "analysisSettingsScroll"; visible: root.advancedExpanded; enabled: !uiState.analysisRunning
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 20
        clip: true; contentWidth: availableWidth
        ColumnLayout {
            width: parent.width; spacing: theme.spacingXs
            Text { text: "후보 찾기 방식"; color: theme.muted; font.pixelSize: theme.smallSize; Layout.fillWidth: true }
            AppComboBox {
                objectName: "analysisPointModeCombo"; theme: root.theme; Layout.fillWidth: true
                model: ["밝기 대비 후보 찾기", "제공 좌표 CSV 분류"]; enabled: !uiState.analysisRunning
                currentIndex: uiState.analysisPointMode === "provided_coordinates" ? 1 : 0
                Accessible.name: "분석 후보 찾기 방식"
                onActivated: uiState.analysisPointMode = currentIndex === 1 ? "provided_coordinates" : "contrast_proposals"
            }
            AppButton { objectName: "analysisCoordinatesButton"; theme: root.theme; text: "현재 영상 좌표 CSV…"; visible: uiState.analysisPointMode === "provided_coordinates"; enabled: uiState.hasLoadedImage && !uiState.analysisRunning; Layout.fillWidth: true; onClicked: root.coordinatesRequested() }
            Text { visible: uiState.analysisPointMode === "provided_coordinates"; text: "불러온 좌표 " + uiState.research.coordinatesCount + "개 · x,y 원본 좌표"; color: theme.muted; font.pixelSize: theme.smallSize; Layout.fillWidth: true }
            Text { visible: !!uiState.research.error; text: uiState.research.error; color: theme.warning; font.pixelSize: theme.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
        }
    }
    Item { visible: !root.advancedExpanded; Layout.fillHeight: true }
    Text { text: "연구용 후보 분류 · BPD 오탐 주의\n확정 라벨·실제 결함 전체 수가 아닙니다."; color: theme.muted; font.pixelSize: theme.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
    AnalysisExecution { objectName: "analysisExecution"; theme: root.theme; uiState: root.uiState; actions: root.actions; Layout.fillWidth: true }
}
