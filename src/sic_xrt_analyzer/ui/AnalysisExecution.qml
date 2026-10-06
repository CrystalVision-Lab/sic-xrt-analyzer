import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property QtObject theme
    property QtObject uiState
    spacing: 5
    property var actions
    Text { text: uiState.analysisReason; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
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
    RowLayout {
        Layout.fillWidth: true
        BusyIndicator { implicitWidth: 22; implicitHeight: 22; visible: uiState.analysisRunning; running: visible }
        Text {
            objectName: "analysisLifecycleState"; Layout.fillWidth: true; wrapMode: Text.Wrap
            text: uiState.analysisRunning ? "분석 중 · 취소할 수 있습니다."
                : uiState.analysis.state === "FAILED" ? "분석 실패 · 입력 조건을 확인하고 다시 실행하세요."
                : uiState.analysis.state === "CANCELED" ? "분석이 취소되었습니다."
                : uiState.analysis.state === "COMPLETED" ? "분석 완료 · 결과 Context에서 후보를 검토하세요."
                : uiState.canAnalyze ? "분석 실행 준비 완료" : "모델·입력·분석 범위를 확인하세요."
            color: uiState.analysis.state === "FAILED" ? theme.warning : theme.muted; font.pixelSize: 12
        }
    }
}
