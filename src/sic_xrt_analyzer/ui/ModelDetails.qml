import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "analysisModelDetails"
    property QtObject theme
    property QtObject uiState
    readonly property string informationPriority: "technical"
    spacing: 5
    InfoRow { theme: root.theme; label: "모델"; value: uiState.analysis.modelName || "—"; Layout.fillWidth: true }
    InfoRow { theme: root.theme; label: "버전"; value: uiState.analysis.modelVersion || "—"; Layout.fillWidth: true }
    InfoRow { theme: root.theme; label: "장치"; value: uiState.analysis.device || "—"; Layout.fillWidth: true }
}
