import QtQuick
import QtQuick.Controls

ToolbarButton {
    id: root
    objectName: "roiToolDropdown"
    property QtObject uiState
    property var actions
    property var hostWindow
    readonly property var choices: actions.tools.roiChoices
    readonly property var current: choices.filter(function(choice) { return choice.tool === root.uiState.activeTool })[0]
    text: (current ? current.label : "ROI") + " ▾"
    toolName: current ? current.tool : "Rectangle"
    checked: !uiState.roiEditMode && (uiState.activeTool === "ROI" || !!current)
    enabled: uiState.canNavigateImage
    tip: "분석 영역 및 ROI 도형 선택 · R: 분석 영역"
    ToolTip.visible: hovered && !roiMenu.visible
    onClicked: roiMenu.open()
    AppMenu {
        id: roiMenu; objectName: "toolbarRoiMenu"; y: root.height
        ToolbarMenuItem { objectName: "toolAnalysisRoi"; action: root.actions.roi; shortcutLabel: "R"; onTriggered: Qt.callLater(function() { root.hostWindow.viewer.focusView() }) }
        Repeater {
            model: root.choices
            ToolbarMenuItem { required property var modelData; objectName: "tool" + modelData.tool; action: modelData.action; rowAvailable: root.uiState.stackFeaturesVisible }
        }
        MenuSeparator {}
        ToolbarMenuItem { action: root.actions.advanced.roiManager }
        ToolbarMenuItem { action: root.actions.importRois }
    }
}
