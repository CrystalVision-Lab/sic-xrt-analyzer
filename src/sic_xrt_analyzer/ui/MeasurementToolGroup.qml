import QtQuick
import QtQuick.Controls

ToolbarButton {
    id: root
    objectName: "measurementToolDropdown"
    property QtObject uiState
    property var actions
    property var hostWindow
    readonly property var choices: actions.tools.measurementChoices
    // Point shares one Action with ROI; only ROI represents the active group.
    readonly property var current: choices.filter(function(choice) { return choice.tool === root.uiState.activeTool && choice.tool !== "Point" })[0]
    text: (current ? current.label : "측정") + " ▾"
    toolName: current ? current.tool : "Line"
    checked: !!current && !uiState.roiEditMode
    enabled: uiState.stackFeaturesVisible
    tip: uiState.stackFeaturesVisible ? "선·각도·점 측정 및 텍스트·화살표 주석" : "측정 도구 · 여러 페이지 TIFF 스택에서 사용"
    ToolTip.visible: hovered && !measurementMenu.visible
    onClicked: measurementMenu.open()
    AppMenu {
        id: measurementMenu; objectName: "toolbarMeasurementMenu"; y: root.height
        ToolbarMenuItem { objectName: "toolbarMeasureItem"; action: root.actions.advanced.measurement }
        MenuSeparator {}
        Repeater {
            model: root.choices
            ToolbarMenuItem { required property var modelData; objectName: "measurement" + modelData.tool; action: modelData.action }
        }
        MenuSeparator {}
        ToolbarMenuItem { action: root.actions.advanced.tools }
    }
}
