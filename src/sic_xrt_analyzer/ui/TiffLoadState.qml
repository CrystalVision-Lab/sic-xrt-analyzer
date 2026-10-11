import QtQuick

QtObject {
    id: root
    objectName: "tiffLoadState"
    property QtObject uiState
    readonly property bool hasViewableFrame: uiState.hasLoadedImage && !uiState.opening && !!uiState.stack.frameViewable
    readonly property bool isOpening: uiState.opening || (!!uiState.stack.initialLoading && !hasViewableFrame)
    readonly property bool hasError: !isOpening && !!(uiState.loadError || uiState.stack.error || uiState.stack.preloadError)
    readonly property int preparedPages: isOpening ? 0 : uiState.stack.preload.prepared
    readonly property int totalPages: isOpening ? 0 : uiState.stack.preload.total
    readonly property bool fullStackReady: hasViewableFrame && totalPages > 1 && !!uiState.stack.preload.ready
    readonly property bool isStackPreparing: hasViewableFrame && totalPages > 1 && !fullStackReady && !uiState.stack.preloadError
    readonly property bool currentPageReady: hasViewableFrame && !uiState.stack.busy
    // Preserve the existing whole-browse gate for requests/contrast/ImageJ work.
    readonly property bool pageNavigationReady: hasViewableFrame && !uiState.stack.initialLoading
    readonly property bool displayRangeReady: pageNavigationReady
    readonly property bool recordReady: pageNavigationReady
    readonly property string phase: isOpening ? "OPENING" : hasError ? "ERROR"
        : !uiState.hasImage ? "EMPTY" : isStackPreparing ? preparedPages <= 1 ? "FIRST_FRAME_READY" : "STACK_PREPARING" : "READY"
    readonly property bool blocking: isOpening || (hasError && !hasViewableFrame && !uiState.demoMode)
    readonly property string currentPageLabel: uiState.hasLoadedImage ? "현재 페이지 " + (uiState.pageIndex + 1) + " / " + uiState.pageCount : ""
    readonly property string stackLabel: totalPages > 1 ? "Stack " + (fullStackReady ? "준비 완료" : uiState.stack.preloadError ? "준비 실패" : "준비 중") + " · " + preparedPages + " / " + totalPages + " 페이지 준비" : ""
    readonly property string pageRequestLabel: "페이지 " + (uiState.stack.requestedPage + 1) + " 준비 중 · 현재 " + (uiState.pageIndex + 1) + " 유지"
    readonly property string openingName: uiState.stack.openingPath ? fileBridge.fileName(uiState.stack.openingPath) : "이미지"
    readonly property string message: isOpening ? openingName + " · 파일 여는 중"
        : hasError ? uiState.stack.preloadError ? "Stack 준비 실패 · 현재 페이지는 사용할 수 있습니다." : "이미지를 열거나 페이지를 준비할 수 없습니다."
        : uiState.pageLoading ? pageRequestLabel : isStackPreparing ? stackLabel : uiState.hasImage ? "준비 완료" : "이미지 없음"
    readonly property string statusLabel: isOpening ? "파일 여는 중" : hasError ? uiState.stack.preloadError ? "Stack 준비 실패" : "파일 오류"
        : uiState.pageLoading ? "현재 페이지 준비 중" : isStackPreparing ? "Stack 준비 · " + preparedPages + "/" + totalPages : uiState.hasImage ? "준비 완료" : "이미지 없음"
    readonly property string navigationReason: pageNavigationReady ? "" : hasViewableFrame ? "전체 페이지 준비 후 페이지 이동·밝기/대비·ImageJ 작업을 사용할 수 있습니다." : "현재 페이지가 준비되면 사용할 수 있습니다."
    readonly property string openingHint: uiState.hasImage ? "이전 이미지를 표시하고 있습니다. 새 파일이 준비되면 교체합니다." : "첫 페이지가 준비되면 이미지를 표시합니다."
    readonly property string availableHint: "현재 페이지의 Pan·Zoom·Fit·픽셀 확인·분석 영역을 사용할 수 있습니다. 분석 실행은 기존 준비 조건을 따릅니다."
    readonly property string errorDetails: [uiState.loadError, uiState.stack.error, uiState.stack.preloadError].filter(function(value, index, values) { return value && values.indexOf(value) === index }).join("\n\n")
    // Presentation-only delay. It never delays readiness or stores TIFF data.
    property bool indicatorElapsed: false
    property Timer openingDelay: Timer { interval: 150; onTriggered: root.indicatorElapsed = true }
    onIsOpeningChanged: { openingDelay.stop(); indicatorElapsed = false; if (isOpening) openingDelay.start() }
}
