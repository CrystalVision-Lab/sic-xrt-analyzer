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
        StatusIndicator { id: indicator; anchors.left: parent.left; objectName: "researchModelStatus"; theme: root.theme; text: uiState.analysisFlow.modelStatus; ink: uiState.modelAvailable ? theme.muted : theme.warning }
}
