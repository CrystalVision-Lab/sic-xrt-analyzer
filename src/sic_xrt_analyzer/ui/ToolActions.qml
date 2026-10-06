import QtQuick
import QtQuick.Controls

QtObject {
    id: root
    property QtObject uiState
    property var baseActions
    property var hostWindow
    readonly property bool stackEnabled: uiState.stackFeaturesVisible && uiState.canNavigateImage
    // Selection is derived from the existing Viewer state, never duplicated.
    function selected(tool) { return uiState.activeTool === tool && !uiState.roiEditMode }
    function forTool(tool) {
        if (tool === "Pan") return baseActions.pan
        if (tool === "ROI") return baseActions.roi
        return root[tool.charAt(0).toLowerCase() + tool.slice(1)]
    }
    function selectTool(tool) {
        uiState.roiEditMode = false
        uiState.activeTool = tool
        Qt.callLater(function() { root.hostWindow.viewer.focusView() })
    }
    readonly property var roiChoices: [
        {tool: "Rectangle", label: "사각형 ROI", action: rectangle},
        {tool: "Oval", label: "타원 ROI", action: oval},
        {tool: "Polygon", label: "다각형 ROI", action: polygon},
        {tool: "Freehand", label: "자유 영역 ROI", action: freehand},
        {tool: "Point", label: "다중 점", action: point},
        {tool: "Wand", label: "완드 · 연결 영역", action: wand}
    ]
    readonly property var measurementChoices: [
        {tool: "Line", label: "직선", action: line},
        {tool: "Polyline", label: "분할선", action: polyline},
        {tool: "FreeLine", label: "자유선", action: freeLine},
        {tool: "Angle", label: "각도 · 3점", action: angle},
        {tool: "Point", label: "다중 점", action: point},
        {tool: "Text", label: "텍스트 주석", action: text},
        {tool: "Arrow", label: "화살표 주석", action: arrow}
    ]
    readonly property var drawingChoices: [
        {tool: "Picker", label: "원본 픽셀 색 추출", action: picker},
        {tool: "Brush", label: "브러시 · 작업 복사본", action: brush},
        {tool: "Fill", label: "영역 채우기 · 작업 복사본", action: fill}
    ]
    property Action zoom: Action { objectName: "toolZoomAction"; text: "확대 도구"; checkable: true; checked: root.selected("Zoom"); enabled: root.uiState.canNavigateImage; onTriggered: root.selectTool("Zoom") }
    property Action rectangle: Action { objectName: "toolRectangleAction"; text: "사각형 ROI"; checkable: true; checked: root.selected("Rectangle"); enabled: root.stackEnabled; onTriggered: root.selectTool("Rectangle") }
    property Action oval: Action { objectName: "toolOvalAction"; text: "타원 ROI"; checkable: true; checked: root.selected("Oval"); enabled: root.stackEnabled; onTriggered: root.selectTool("Oval") }
    property Action polygon: Action { objectName: "toolPolygonAction"; text: "다각형 ROI"; checkable: true; checked: root.selected("Polygon"); enabled: root.stackEnabled; onTriggered: root.selectTool("Polygon") }
    property Action freehand: Action { objectName: "toolFreehandAction"; text: "자유 영역 ROI"; checkable: true; checked: root.selected("Freehand"); enabled: root.stackEnabled; onTriggered: root.selectTool("Freehand") }
    property Action point: Action { objectName: "toolPointAction"; text: "다중 점"; checkable: true; checked: root.selected("Point"); enabled: root.stackEnabled; onTriggered: root.selectTool("Point") }
    property Action wand: Action { objectName: "toolWandAction"; text: "완드 · 연결 영역"; checkable: true; checked: root.selected("Wand"); enabled: root.stackEnabled; onTriggered: root.selectTool("Wand") }
    property Action line: Action { objectName: "toolLineAction"; text: "직선"; checkable: true; checked: root.selected("Line"); enabled: root.stackEnabled; onTriggered: root.selectTool("Line") }
    property Action polyline: Action { objectName: "toolPolylineAction"; text: "분할선"; checkable: true; checked: root.selected("Polyline"); enabled: root.stackEnabled; onTriggered: root.selectTool("Polyline") }
    property Action freeLine: Action { objectName: "toolFreeLineAction"; text: "자유선"; checkable: true; checked: root.selected("FreeLine"); enabled: root.stackEnabled; onTriggered: root.selectTool("FreeLine") }
    property Action angle: Action { objectName: "toolAngleAction"; text: "각도 · 3점"; checkable: true; checked: root.selected("Angle"); enabled: root.stackEnabled; onTriggered: root.selectTool("Angle") }
    property Action text: Action { objectName: "toolTextAction"; text: "텍스트 주석"; checkable: true; checked: root.selected("Text"); enabled: root.stackEnabled; onTriggered: root.selectTool("Text") }
    property Action arrow: Action { objectName: "toolArrowAction"; text: "화살표 주석"; checkable: true; checked: root.selected("Arrow"); enabled: root.stackEnabled; onTriggered: root.selectTool("Arrow") }
    property Action picker: Action { objectName: "toolPickerAction"; text: "원본 픽셀 색 추출"; checkable: true; checked: root.selected("Picker"); enabled: root.stackEnabled; onTriggered: root.selectTool("Picker") }
    property Action brush: Action { objectName: "toolBrushAction"; text: "브러시 · 작업 복사본"; checkable: true; checked: root.selected("Brush"); enabled: root.stackEnabled; onTriggered: root.selectTool("Brush") }
    property Action fill: Action { objectName: "toolFillAction"; text: "영역 채우기 · 작업 복사본"; checkable: true; checked: root.selected("Fill"); enabled: root.stackEnabled; onTriggered: root.selectTool("Fill") }
    property ActionGroup exclusiveTools: ActionGroup {
        exclusive: true
        actions: [root.baseActions.pan, root.baseActions.roi, root.zoom, root.rectangle, root.oval, root.polygon, root.freehand, root.point, root.wand, root.line, root.polyline, root.freeLine, root.angle, root.text, root.arrow, root.picker, root.brush, root.fill]
    }
}
