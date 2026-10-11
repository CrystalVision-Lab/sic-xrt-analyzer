import QtQuick

QtObject {
    id: root
    enum Context { Image, Analysis, Result, Viewer, Roi }
    property QtObject uiState
    // Compatibility index; production requests use names and reasons.
    property int tabIndex: ContextState.Image
    readonly property var keys: ["image", "analysis", "result", "viewer", "roi"]
    readonly property var labels: ["이미지 정보", "분석", "결과", "뷰어 · 스택", "ROI 관리"]
    readonly property string requestedContext: keys[tabIndex] || "image"
    readonly property string activeContext: requestedContext === "image" && !uiState.hasImage ? "idle" : requestedContext
    readonly property string detailContext: requestedContext === "result" && !!uiState.research.selected.id ? "candidate" : activeContext
    property string lastReason: "STARTUP"
    property string observedAnalysisPhase: ""
    property string completedAnalysisId: ""
    signal contextRequested(string reason)
    readonly property var events: ({
        OPEN_IMAGE: "image", CLOSE_IMAGE: "image", DEMO_OPEN: "image", RESET_LAYOUT: "image",
        ANALYSIS_START: "analysis", ANALYSIS_COMPLETE: "result", ANALYSIS_FAILED: "analysis", ANALYSIS_CANCELED: "analysis",
        CANDIDATE_SELECTED: "result", ROI_MANAGER_OPEN: "roi", ROI_IMPORT: "roi", ROI_EDIT: "roi", VIEWER_SETTINGS: "viewer"
    })
    function requestContext(key, reason) {
        var index = keys.indexOf(key)
        if (index < 0 || (reason !== "MANUAL" && events[reason] !== key)) return false
        tabIndex = index
        lastReason = reason
        contextRequested(reason)
        return true
    }
    function showContext(key) { return requestContext(key, "MANUAL") }
    function handleAnalysis() {
        var analysis = uiState.analysis, phase = analysis.state, before = observedAnalysisPhase
        observedAnalysisPhase = phase
        // Source/generation validity belongs to the pipeline. Accept only its
        // current terminal result once, never progress/ROI snapshots.
        if (!uiState.hasLoadedImage || uiState.loading) return
        if (phase === "COMPLETED" && analysis.sourceReady && analysis.hasResult && analysis.analysisId && analysis.analysisId !== completedAnalysisId) {
            completedAnalysisId = analysis.analysisId
            requestContext("result", "ANALYSIS_COMPLETE")
        } else if (phase !== before) {
            if (phase === "RUNNING") requestContext("analysis", "ANALYSIS_START")
            else if (phase === "FAILED") requestContext("analysis", "ANALYSIS_FAILED")
            else if (phase === "CANCELED") requestContext("analysis", "ANALYSIS_CANCELED")
        }
    }
    Component.onCompleted: {
        observedAnalysisPhase = uiState.analysis.state
        completedAnalysisId = uiState.analysis.analysisId || ""
    }
    property Connections lifecycle: Connections {
        target: root.uiState
        function onAnalysisChanged() { root.handleAnalysis() }
    }
    readonly property string title: labels[tabIndex] || labels[0]
    readonly property string resultPhase: !uiState.hasResult ? "empty" : !uiState.research.total ? "zero" : uiState.research.selected.id ? "candidate-selected" : "list"
    readonly property string resultMessage: !uiState.hasResult
        ? uiState.analysisRunning ? "분석 중입니다. 완료 후 결과가 표시됩니다."
          : uiState.analysis.state === "FAILED" ? "분석에 실패했습니다. 이번 분석의 결과가 없습니다."
          : uiState.analysis.state === "CANCELED" ? "분석이 취소되었습니다. 검토할 결과가 없습니다."
          : "아직 분석 결과가 없습니다."
        : !uiState.research.total ? "후보가 발견되지 않았습니다."
          : "후보 " + uiState.research.total + "개 · " + (uiState.research.selected.id ? "선택한 후보를 검토하세요." : "검토할 후보를 선택하세요.")
    readonly property string subtitle: requestedContext === "image"
        ? uiState.hasImage ? uiState.fileName || "합성 데모 이미지" : "이미지를 열어 작업을 시작하세요."
        : requestedContext === "analysis" ? "현재 원본에서 BPD · TED · TSD 후보를 분석합니다."
        : requestedContext === "result" ? "분류별로 후보를 선택해 영상에서 검토합니다."
        : requestedContext === "viewer" ? uiState.hasImage ? "페이지 탐색과 원본 표시 범위" : "이미지를 열면 표시 설정을 사용할 수 있습니다."
        : "분석 영역과 ImageJ ROI를 구분하여 관리합니다."
}
