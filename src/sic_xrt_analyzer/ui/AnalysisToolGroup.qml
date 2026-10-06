import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    objectName: "analysisToolGroup"
    property QtObject theme
    property var actions
    property QtObject uiState
    spacing: 5
        AppButton { theme: root.theme; action: root.actions.run; text: "분석 실행"; iconName: "run"; primary: true; tip: uiState.analysisReason }
}
