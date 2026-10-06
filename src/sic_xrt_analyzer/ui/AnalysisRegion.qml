import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property QtObject theme
    property QtObject uiState
    spacing: 5
    SectionHeader { theme: root.theme; text: "ROI"; Layout.fillWidth: true }
    Text { visible: !uiState.hasRoi; text: "선택된 ROI 없음\n도구 모음의 ROI로 영역을 선택하세요."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
    Repeater {
        model: ["X", "Y", "너비", "높이"]
        InfoRow { required property int index; required property string modelData; theme: root.theme; label: modelData; value: uiState.hasRoi ? [uiState.roiX, uiState.roiY, uiState.roiWidth, uiState.roiHeight][index] + " px" : "—"; Layout.fillWidth: true }
    }
    AppComboBox {
        objectName: "analysisScopeCombo"; theme: root.theme; Layout.fillWidth: true
        model: ["분석 범위 선택", "전체 이미지", "ROI"]
        enabled: uiState.modelAvailable && !uiState.analysisRunning
        currentIndex: uiState.analysisScope === "FULL_IMAGE" ? 1 : uiState.analysisScope === "ROI" ? 2 : 0
        onActivated: uiState.analysisScope = ["", "FULL_IMAGE", "ROI"][currentIndex]
    }
}
