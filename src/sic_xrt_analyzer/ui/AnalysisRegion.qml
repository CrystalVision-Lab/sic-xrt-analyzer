import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property QtObject theme
    property QtObject uiState
    property var actions
    spacing: 5
    SectionHeader { theme: root.theme; text: "분석 범위"; Layout.fillWidth: true }
    AppComboBox {
        objectName: "analysisScopeCombo"; theme: root.theme; Layout.fillWidth: true
        model: uiState.analysisFlow.scopeLabels; enabled: uiState.modelAvailable && !uiState.analysisRunning
        currentIndex: Math.max(0, uiState.analysisFlow.scopeKeys.indexOf(uiState.analysisScope))
        Accessible.name: "분석 범위"; Accessible.description: "전체 이미지 또는 분석용 지정 영역"
        onActivated: uiState.analysisScope = uiState.analysisFlow.scopeKeys[currentIndex]
    }
    Text { objectName: "analysisAreaSummary"; text: uiState.analysisFlow.regionLabel; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
    AppButton { objectName: "analysisSpecifyArea"; visible: uiState.analysisScope === "ROI"; theme: root.theme; action: root.actions.roi; text: uiState.hasRoi ? "영역 다시 지정 (R)" : "영역 지정 (R)"; Accessible.name: text; Layout.fillWidth: true; tip: "이미지에서 드래그하세요. 분석 Context를 유지합니다." }
    Text { visible: uiState.analysisScope === "ROI" || uiState.importedRois.items.length > 0; text: "분석용 사각형 영역입니다. ImageJ ROI 기록은 자동 분석 범위가 아닙니다."; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
}
