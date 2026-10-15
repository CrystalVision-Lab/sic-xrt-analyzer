import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    objectName: "tiffWorkbenchControls"
    property QtObject theme
    property QtObject uiState
    property var actions
    property var hostWindow
    property bool compact: false
    spacing: theme.spacingXs
    AppButton {
        objectName: "tiffMeasure"; theme: root.theme; text: "측정"; implicitHeight: theme.toolbarButtonHeight
        enabled: uiState.loadFlow.imagejReady && !!uiState.roiFlow.selected && uiState.roiFlow.selected.active && uiState.roiFlow.selected.visible
        tip: enabled ? "선택의 길이·면적·각도·개수 · 원본 좌표와 XY 단위" : "현재 TIFF 페이지에서 표시된 ImageJ 선택을 지정하세요."
        onClicked: root.hostWindow.measureSelection()
    }
    ToolbarButton { objectName: "tiffContrast"; theme: root.theme; text: root.compact ? "대비" : "밝기·대비"; action: root.actions.viewerSettings; tip: "표시 범위만 조절 · 원본 픽셀 유지" }
    ToolbarButton {
        objectName: "tiffProcess"; visible: !root.compact; theme: root.theme; text: "처리 ▾"; tip: "현재 페이지 · 설정 확인 후 작업 복사본 또는 측정 결과 생성"
        enabled: uiState.loadFlow.imagejReady
        onClicked: processMenu.open()
        AppMenu {
            id: processMenu; objectName: "tiffProcessMenu"; y: parent.height; width: 260
            ToolbarMenuItem { objectName: "tiffHistogram"; text: "히스토그램 · 측정 결과"; onTriggered: root.hostWindow.imagejStatistics("Histogram") }
            ToolbarMenuItem { text: "선택 픽셀 측정 (ImageJ Measure)"; onTriggered: root.hostWindow.imagejCommand("Measure", "") }
            ToolbarMenuItem { objectName: "tiffGaussian"; text: "가우시안 흐림…"; onTriggered: root.hostWindow.processTiff("Gaussian") }
            ToolbarMenuItem { objectName: "tiffThreshold"; text: "임계값 · 이진화…"; onTriggered: root.hostWindow.processTiff("Threshold") }
            ToolbarMenuItem { objectName: "tiffBackground"; text: "배경 제거…"; onTriggered: root.hostWindow.processTiff("Background") }
            ToolbarMenuItem { text: "필터·이진·입자 분석 명령…"; action: root.actions.advanced.catalog }
            AppMenu {
                objectName: "tiffLutMenu"; title: "색상 LUT · 표시만 변경"
                Repeater { model: root.actions.advanced.luts; ToolbarMenuItem { required property var modelData; action: modelData } }
                ToolbarMenuItem { action: root.actions.advanced.invertLut }
            }
        }
    }
    ToolbarButton {
        objectName: "tiffMore"; theme: root.theme; text: root.compact ? "더보기" : "더보기 ▾"; tip: "추가 도구 · ROI 관리 · ImageJ 고급 기능"
        onClicked: moreMenu.open()
        AppMenu {
            id: moreMenu; objectName: "tiffMoreMenu"; y: parent.height; width: 290
            Repeater {
                model: ["Oval", "Polygon", "Wand", "Freehand", "Polyline", "FreeLine", "Angle", "Text", "Arrow", "Picker", "Brush", "Fill"]
                ToolbarMenuItem {
                    required property string modelData
                    objectName: "tiffMore" + modelData
                    rowAvailable: root.compact || ["Oval", "Polygon", "Wand", "Freehand", "Polyline"].indexOf(modelData) < 0
                    action: root.actions.tools.forTool(modelData)
                    ToolTip.visible: hovered; ToolTip.text: root.actions.tools.tooltip(modelData)
                }
            }
            MenuSeparator {}
            ToolbarMenuItem { action: root.actions.advanced.tools }
            ToolbarMenuItem { action: root.actions.advanced.measurement }
            ToolbarMenuItem { action: root.actions.advanced.roiManager }
            ToolbarMenuItem { action: root.actions.importRois }
            ToolbarMenuItem { action: root.actions.advanced.editRoi }
            MenuSeparator {}
            AppMenu {
                title: "ImageJ 고급 기능"; objectName: "tiffAdvancedMenu"
                ToolbarMenuItem { objectName: "tiffCommands"; action: root.actions.advanced.catalog }
                ToolbarMenuItem { objectName: "tiffMacro"; action: root.actions.advanced.macro }
                ToolbarMenuItem { objectName: "tiffPlugin"; action: root.actions.advanced.plugin }
                ToolbarMenuItem { objectName: "tiffFiji"; action: root.actions.advanced.modern }
                ToolbarMenuItem { objectName: "tiffResults"; action: root.actions.advanced.results }
                ToolbarMenuItem { action: root.actions.advanced.record }
            }
            ToolbarMenuItem { action: root.actions.save }
        }
    }
    ToolbarButton {
        objectName: "tiffStack"; visible: uiState.stackFeaturesVisible && uiState.pageCount > 1
        theme: root.theme; text: "스택 ▾"; tip: "페이지 순서의 연산 · 물리 Z 미확정 · 전체 준비 후 실행"
        onClicked: stackMenu.open()
        AppMenu {
            id: stackMenu; objectName: "tiffStackMenu"; y: parent.height; width: 240
            ToolbarMenuItem { action: root.actions.advanced.first }
            ToolbarMenuItem { action: root.actions.advanced.previous }
            ToolbarMenuItem { action: root.actions.advanced.next }
            ToolbarMenuItem { action: root.actions.advanced.last }
            MenuSeparator {}
            ToolbarMenuItem { action: root.actions.advanced.project }
            ToolbarMenuItem { action: root.actions.advanced.duplicate }
            ToolbarMenuItem { action: root.actions.advanced.reverse }
        }
    }
}
