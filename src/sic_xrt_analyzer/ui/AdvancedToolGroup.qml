import QtQuick
import QtQuick.Controls

ToolbarButton {
    id: root
    objectName: "advancedToolGroup"
    property QtObject uiState
    property var actions
    property var hostWindow
    readonly property string informationPriority: "advanced"
    text: "⋯"; tip: "추가 도구 · 저장, 확대·축소, 스택, 색상표, ImageJ"
    labelSize: 20
    ToolTip.visible: hovered && !more.visible
    onClicked: more.open()
    AppMenu {
        id: more; objectName: "toolbarMoreMenu"; title: "추가 도구"; y: root.height; width: 290
        ToolbarMenuItem { objectName: "toolbarSaveItem"; action: root.actions.save; shortcutLabel: "Ctrl+S" }
        ToolbarMenuItem { objectName: "toolbarViewerSettings"; action: root.actions.viewerSettings }
        AppMenu { objectName: "toolbarZoomMenu"; title: "확대 / 축소"
            ToolbarMenuItem { action: root.actions.zoomIn; shortcutLabel: "Ctrl++" }
            ToolbarMenuItem { action: root.actions.zoomOut; shortcutLabel: "Ctrl+-" }
            ToolbarMenuItem { action: root.actions.actualSize; shortcutLabel: "Ctrl+1" }
        }
        ToolbarMenuItem { action: root.actions.advanced.editRoi }
        ToolbarMenuItem { action: root.actions.advanced.saveMeasurements; rowAvailable: root.uiState.stackFeaturesVisible }
        MenuSeparator { visible: root.uiState.stackFeaturesVisible; height: root.uiState.stackFeaturesVisible ? implicitHeight : 0 }
        AppMenu {
            objectName: "toolbarStackMenu"; title: "스택"; available: root.uiState.stackFeaturesVisible
            ToolbarMenuItem { objectName: "toolbarFirstPage"; action: root.actions.advanced.first }
            ToolbarMenuItem { objectName: "toolbarPreviousPage"; action: root.actions.advanced.previous }
            ToolbarMenuItem { objectName: "toolbarNextPage"; action: root.actions.advanced.next }
            ToolbarMenuItem { objectName: "toolbarLastPage"; action: root.actions.advanced.last }
            MenuSeparator {}
            ToolbarMenuItem { action: root.actions.advanced.project }
            ToolbarMenuItem { action: root.actions.advanced.duplicate }
            ToolbarMenuItem { action: root.actions.advanced.reverse }
        }
        AppMenu {
            objectName: "toolbarLutMenu"; title: "색상 표시표 (LUT)"; available: root.uiState.stackFeaturesVisible
            Repeater { model: root.actions.advanced.luts
                ToolbarMenuItem { required property var modelData; objectName: "toolbarLut" + modelData.text; action: modelData }
            }
            ToolbarMenuItem { action: root.actions.advanced.invertLut }
        }
        AppMenu {
            objectName: "toolbarDrawingMenu"; title: "그리기 / 색 추출"; available: root.uiState.stackFeaturesVisible
            Repeater { model: root.actions.tools.drawingChoices
                ToolbarMenuItem { required property var modelData; objectName: "tool" + modelData.tool; action: modelData.action }
            }
        }
        ToolbarMenuItem { action: root.actions.advanced.tools; rowAvailable: root.uiState.stackFeaturesVisible }
        ToolbarMenuItem { objectName: "toolbarImagejCommands"; action: root.actions.advanced.catalog; rowAvailable: root.uiState.stackFeaturesVisible }
        ToolbarMenuItem { objectName: "toolbarMacro"; action: root.actions.advanced.macro; rowAvailable: root.uiState.stackFeaturesVisible }
        ToolbarMenuItem { objectName: "toolbarPlugin"; action: root.actions.advanced.plugin; rowAvailable: root.uiState.stackFeaturesVisible }
        ToolbarMenuItem { objectName: "toolbarFiji"; action: root.actions.advanced.modern; rowAvailable: root.uiState.stackFeaturesVisible }
        ToolbarMenuItem { action: root.actions.advanced.results; rowAvailable: root.uiState.stackFeaturesVisible }
        ToolbarMenuItem { objectName: "toolbarRecordCommands"; action: root.actions.advanced.record; rowAvailable: root.uiState.stackFeaturesVisible }
    }
}
