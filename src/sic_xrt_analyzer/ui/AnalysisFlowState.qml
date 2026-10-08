import QtQuick

QtObject {
    property QtObject uiState
    readonly property bool ready: uiState.canAnalyze
    readonly property bool running: uiState.analysisRunning
    readonly property string phase: uiState.analysis.state
    // Display the exact existing Run gates; do not introduce another validator.
    readonly property var blockers: {
        var items = []
        if (!uiState.hasLoadedImage) items.push("원본 TIFF 또는 JPG 이미지를 여세요.")
        else if (!uiState.analysis.sourceReady) items.push("분석할 원본이 준비되지 않았습니다. 파일을 다시 여세요.")
        if (!uiState.modelAvailable) items.push(uiState.research.loading ? "모델을 준비하고 있습니다." : "연구 모델을 연결하세요.")
        if (uiState.loading) items.push("이미지 준비가 끝날 때까지 기다리세요.")
        else if (uiState.pageLoading) items.push("현재 페이지를 준비하고 있습니다.")
        if (!uiState.analysisScope) items.push("분석 범위를 선택하세요.")
        else if (uiState.modelAvailable && uiState.inputCompatibilityState !== "ERROR" && uiState.analysis.supportedScopes.indexOf(uiState.analysisScope) < 0) items.push("모델이 선택한 분석 범위를 지원하지 않습니다.")
        if (uiState.analysisScope === "ROI" && (!uiState.hasRoi || uiState.roiWidth <= 0 || uiState.roiHeight <= 0)) items.push("분석 영역을 지정하세요.")
        if (uiState.hasLoadedImage && uiState.analysis.sourceReady && uiState.modelAvailable && !uiState.loading && !uiState.pageLoading) {
            if (uiState.inputCompatibilityState === "INCOMPATIBLE" || uiState.inputCompatibilityState === "ERROR") items.push(uiState.inputPreflight.message)
            else if (uiState.inputCompatibilityState === "UNKNOWN") items.push("입력 호환성을 확인하고 있습니다.")
        }
        return items
    }
    readonly property string summary: running ? "분석 중"
        : phase === "FAILED" ? "분석 실패"
        : phase === "CANCELED" ? "분석 취소됨"
        : phase === "COMPLETED" ? "분석 완료"
        : ready ? "분석 준비 완료" : "분석 준비 필요"
    readonly property string explanation: running ? "설정 잠금 · 취소할 수 있습니다."
        : (phase === "FAILED" ? uiState.analysis.errorMessage + "\n" : "")
          + (blockers.length ? "• " + blockers.join("\n• ")
             : phase === "CANCELED" ? "설정을 유지했습니다. 다시 분석할 수 있습니다."
             : phase === "FAILED" ? "입력과 모델을 확인한 뒤 다시 분석할 수 있습니다."
             : phase === "COMPLETED" ? "결과 Context에서 후보를 확인하세요."
             : "아래 분석 실행을 누르면 시작합니다.")
    readonly property string modelStatus: uiState.research.loading ? "모델 준비 중" : uiState.modelAvailable ? "모델 준비됨" : "모델 연결 필요"
    readonly property string sourceLabel: uiState.analysis.inputSource || "원본 이미지 없음"
    readonly property string regionLabel: uiState.analysisScope === "FULL_IMAGE"
        ? uiState.hasLoadedImage ? uiState.imageWidth + " × " + uiState.imageHeight + " px · 현재 원본 페이지" : "이미지를 열면 전체 크기가 표시됩니다."
        : uiState.hasRoi ? uiState.roiWidth + " × " + uiState.roiHeight + " px · X " + uiState.roiX + " / Y " + uiState.roiY : "분석 영역이 없습니다."
    readonly property var scopeKeys: [""].concat(uiState.analysis.supportedScopes.length ? uiState.analysis.supportedScopes : ["FULL_IMAGE", "ROI"])
    readonly property var scopeLabels: scopeKeys.map(function(key) { return key === "FULL_IMAGE" ? "전체 이미지" : key === "ROI" ? "지정 영역 (분석용)" : "분석 범위 선택" })
}
