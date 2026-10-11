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
    signal modelRequested()
    signal coordinatesRequested()
    spacing: 10
    ScrollView {
        objectName: "analysisSettingsScroll"
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 80
        clip: true; contentWidth: availableWidth
        ColumnLayout {
            width: parent.width; spacing: 10
            SectionHeader { theme: root.theme; text: "분석 설정"; Layout.fillWidth: true }
            AnalysisSettings { objectName: "analysisSettings"; theme: root.theme; uiState: root.uiState; actions: root.actions; Layout.fillWidth: true; onModelRequested: root.modelRequested(); onCoordinatesRequested: root.coordinatesRequested() }
            SectionHeader { theme: root.theme; text: "분석 영역"; Layout.fillWidth: true }
            AnalysisRegion { objectName: "analysisRegion"; theme: root.theme; uiState: root.uiState; Layout.fillWidth: true }
        }
    }
    SectionHeader { theme: root.theme; text: "실행"; Layout.fillWidth: true }
    AnalysisExecution { objectName: "analysisExecution"; theme: root.theme; uiState: root.uiState; actions: root.actions; Layout.fillWidth: true }
}
