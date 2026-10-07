import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property QtObject theme
    property QtObject uiState
    property var actions
    spacing: theme.spacingXs
    RowLayout {
        Layout.fillWidth: true
        BusyIndicator { implicitWidth: 22; implicitHeight: 22; visible: uiState.analysisRunning; running: visible }
        Text { objectName: "analysisLifecycleState"; text: uiState.analysisFlow.summary; color: uiState.analysis.state === "FAILED" ? theme.error : theme.text; font.pixelSize: theme.bodySize; font.weight: Font.Medium; wrapMode: Text.Wrap; Layout.fillWidth: true; Accessible.name: text }
    }
    Text { objectName: "analysisReadinessReasons"; text: uiState.analysisFlow.explanation; color: theme.muted; font.pixelSize: theme.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true; Accessible.name: text }
    RowLayout {
        objectName: "analysisPrimaryActions"; Layout.fillWidth: true
        AppButton { objectName: "contextRunAnalysis"; theme: root.theme; action: root.actions.run; text: uiState.analysis.state === "FAILED" || uiState.analysis.state === "CANCELED" ? "다시 분석" : "분석 실행"; iconName: "run"; primary: true; Layout.fillWidth: true; tip: uiState.analysisFlow.explanation; Accessible.name: text; Accessible.description: tip }
        AppButton { objectName: "contextCancelAnalysis"; theme: root.theme; action: root.actions.cancelAnalysis; text: "분석 취소"; visible: uiState.analysisRunning; Accessible.name: text }
    }
}
