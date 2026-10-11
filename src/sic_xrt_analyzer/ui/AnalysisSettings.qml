import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property QtObject theme
    property QtObject uiState
    property var actions
    spacing: theme.spacingXs
    signal modelRequested()
    SectionHeader { theme: root.theme; text: "모델"; Layout.fillWidth: true }
    Text { objectName: "analysisModelName"; text: uiState.analysis.modelName || "BPD · TED · TSD 연구 모델"; color: theme.text; font.pixelSize: theme.bodySize; elide: Text.ElideRight; Layout.fillWidth: true }
    ModelStatusGroup { theme: root.theme; uiState: root.uiState; Layout.fillWidth: true }
    RowLayout {
        Layout.fillWidth: true
        AppButton { objectName: "researchModelButton"; theme: root.theme; quiet: true; text: uiState.modelAvailable ? "모델 변경…" : "모델 연결…"; enabled: !uiState.analysisRunning && !uiState.research.loading; Layout.fillWidth: true; Accessible.name: text; onClicked: root.modelRequested() }
        AppButton { objectName: "contextModelInfo"; theme: root.theme; action: root.actions.modelInfo; text: "상세 정보…"; quiet: true; Layout.fillWidth: true; Accessible.name: "모델 상세 정보" }
    }
}
