import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    objectName: "modelStatusGroup"
    property QtObject theme
    property QtObject uiState
    readonly property string informationPriority: "secondary"
    implicitWidth: indicator.implicitWidth
    implicitHeight: indicator.implicitHeight
        StatusIndicator { id: indicator; anchors.centerIn: parent; objectName: "researchModelStatus"; theme: root.theme; text: uiState.analysisFlow.modelStatus; ink: uiState.modelAvailable ? theme.accent : theme.warning }
}
