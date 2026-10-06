import QtQuick

QtObject {
    id: root
    objectName: "roiFlowState"
    property QtObject uiState
    readonly property var records: uiState.importedRois.items
    readonly property var selected: records.filter(function(r) { return r.selected })[0] || null
    readonly property int selectedIndex: records.findIndex(function(r) { return r.selected })
    readonly property int count: records.length
    readonly property bool hasArea: uiState.hasRoi && uiState.roiWidth > 0 && uiState.roiHeight > 0
    readonly property string areaPhase: uiState.analysisRunning ? "LOCKED"
        : !uiState.hasImage || uiState.loading || uiState.pageLoading ? "DISABLED"
        : uiState.selectingRoi ? "DRAWING" : hasArea ? "READY" : "NONE"
    readonly property string areaSummary: areaPhase === "DRAWING" ? "분석 영역 지정 중"
        : hasArea ? "지정 영역 · " + uiState.roiWidth + " × " + uiState.roiHeight + " px"
        : "지정된 분석 영역이 없습니다."
    readonly property string areaHint: areaPhase === "LOCKED" ? "분석 중에는 영역을 변경할 수 없습니다."
        : areaPhase === "DISABLED" ? uiState.hasImage ? "이미지 준비가 끝나면 지정할 수 있습니다." : "이미지를 먼저 여세요."
        : areaPhase === "DRAWING" ? "드래그한 뒤 마우스를 놓으면 완료됩니다."
        : "전체 이미지 분석에서는 영역을 지정하지 않아도 됩니다."
    readonly property var recordTools: ["Rectangle", "Oval", "Polygon", "Freehand", "Point", "Wand", "Line", "Polyline", "FreeLine", "Angle", "Arrow", "Text"]
    readonly property bool recordToolActive: !uiState.roiEditMode && recordTools.indexOf(uiState.activeTool) >= 0
    readonly property bool isDrawing: recordToolActive && ((!!uiState.roiInteraction && (uiState.roiInteraction.drawingTool || uiState.roiInteraction.toolPoints.length > 0)) || (uiState.activeTool === "Wand" && fileBridge.imagej.state.busy))
    readonly property bool canEdit: !!selected && selected.active && selected.visible && selected.paths.length === 1 && uiState.hasLoadedImage && !uiState.loading && !uiState.importedRois.busy
    readonly property string imagejPhase: uiState.importedRois.busy ? "IMPORTING"
        : uiState.importedRois.errors.length || uiState.importedRois.editError ? "ERROR"
        : uiState.roiEditMode ? "EDITING" : isDrawing ? "DRAWING"
        : selected ? "SELECTED" : count ? "AVAILABLE" : "EMPTY"
    function shape(record) { return record ? record.tool || ({point: "Point", line: "Line", polygon: "Polygon"})[record.kind] || record.kind : "" }
    readonly property string selectionLabel: selected ? shape(selected) + " #" + (selectedIndex + 1) + (selected.name !== shape(selected) ? " · " + selected.name : "") : "선택된 ROI 없음"
    readonly property string imagejSummary: "ImageJ ROI " + count + "개" + (imagejPhase === "EDITING" ? " · 편집 모드" : imagejPhase === "DRAWING" ? " · 생성 중" : imagejPhase === "IMPORTING" ? " · 가져오는 중" : "")
    readonly property string toolHint: uiState.activeTool === "Polygon" || uiState.activeTool === "Polyline" ? "클릭으로 점 추가 · Enter 또는 더블클릭으로 완료 · Esc로 미완성 도형 취소"
        : uiState.activeTool === "Angle" ? "세 위치를 클릭하면 완료 · Esc로 미완성 도형 취소"
        : uiState.activeTool === "Point" ? "클릭으로 점 생성 · 선택한 Point ROI에 클릭하면 점 추가"
        : uiState.activeTool === "Wand" ? "클릭으로 연결 영역 선택 · 작업 상태는 ImageJ 창에서 확인"
        : uiState.activeTool === "Text" ? "클릭한 위치에 텍스트 기록"
        : "드래그 후 마우스를 놓으면 완료 · Esc로 미완성 도형 취소"
    readonly property string imagejHint: !uiState.hasLoadedImage ? "이미지를 먼저 여세요."
        : uiState.importedRois.busy ? "가져오기가 끝나면 목록이 갱신됩니다."
        : uiState.roiEditMode ? canEdit ? "점을 드래그하여 편집 · 편집 종료 또는 H로 종료" : "편집 모드 · 현재 페이지의 표시된 ROI를 선택하세요."
        : recordToolActive ? "현재 도구: " + uiState.activeTool + "\n" + toolHint
        : !count ? "아직 저장된 ROI가 없습니다.\nToolbar의 ROI 메뉴에서 도형을 선택하여 그리세요."
        : selected && !selected.active ? "현재 페이지에 표시되지 않는 ROI입니다."
        : selected && !selected.visible ? "숨겨진 ROI입니다. 표시를 켜면 편집할 수 있습니다."
        : "목록에서 기록을 선택하여 관리하세요."
    readonly property string viewerMode: uiState.roiEditMode ? "ROI 편집"
        : uiState.activeTool === "ROI" ? "분석 영역" + (uiState.selectingRoi ? " · 지정 중" : "")
        : recordToolActive ? "ROI · " + uiState.activeTool + (isDrawing ? " · 생성 중" : "") : uiState.activeTool.toUpperCase()
}
