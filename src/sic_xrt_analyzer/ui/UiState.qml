import QtQuick
QtObject {
    property string filePath: ""
    property string fileName: ""
    property int workspaceIndex: 0
    property string activeTool: "Pan"
    property real zoom: 1
    property bool fitMode: true
    property real fitZoom: 1
    property real displayPixelRatio: 1
    property bool demoMode: false
    property string imageSource: ""
    property int imageWidth: 0
    property int imageHeight: 0
    property int bitDepth: 0
    property int pageCount: 0
    property int previewWidth: 0
    property int previewHeight: 0
    property bool sampledPreview: false
    property bool loading: false
    property string loadError: ""
    property bool hasRoi: false
    property bool selectingRoi: false
    property bool roiLayerVisible: true
    property real roiStartX: 0
    property real roiStartY: 0
    property real roiEndX: 0
    property real roiEndY: 0
    property int cursorX: -1
    property int cursorY: -1
    property bool smoothImages: true
    property string viewerBackground: "#111518"
    property string defaultView: "fit"
    property string statusText: "TIFF 이미지를 열거나 합성 데모를 확인하세요"
    property var analysis: fileBridge.analysis
    property string analysisScope: ""
    readonly property bool modelAvailable: analysis.modelAvailable
    readonly property bool analysisRunning: analysis.state === "RUNNING"
    readonly property bool hasResult: analysis.hasResult
    function syncCurrentRoi() {
        fileBridge.setCurrentRoi(hasRoi && hasLoadedImage, roiX, roiY, roiWidth, roiHeight)
    }
    onHasRoiChanged: Qt.callLater(syncCurrentRoi)
    onRoiXChanged: Qt.callLater(syncCurrentRoi)
    onRoiYChanged: Qt.callLater(syncCurrentRoi)
    onRoiWidthChanged: Qt.callLater(syncCurrentRoi)
    onRoiHeightChanged: Qt.callLater(syncCurrentRoi)
    readonly property bool projectModified: false
    readonly property bool hasSelectedFile: filePath.length > 0
    readonly property bool hasLoadedImage: imageSource.length > 0 && hasSelectedFile
    readonly property bool hasImage: demoMode || hasLoadedImage
    readonly property int contentWidth: demoMode ? 960 : imageWidth
    readonly property int contentHeight: demoMode ? 600 : imageHeight
    readonly property bool canNavigateImage: workspaceIndex === 0 && hasImage && !loading
    readonly property bool canAnalyze: hasLoadedImage && analysis.sourceReady && modelAvailable && !analysisRunning && !loading && analysis.supportedScopes.indexOf(analysisScope) >= 0 && (analysisScope === "FULL_IMAGE" || (analysisScope === "ROI" && hasRoi && roiWidth > 0 && roiHeight > 0))
    readonly property string analysisReason: analysis.errorMessage || (!modelAvailable ? "승인된 모델이 연결되지 않았습니다" : !analysis.sourceReady ? "원본 TIFF를 여세요" : analysisRunning ? "분석 중입니다" : !analysisScope ? "분석 범위를 선택하세요" : analysis.supportedScopes.indexOf(analysisScope) < 0 ? "모델이 선택한 분석 범위를 지원하지 않습니다" : analysisScope === "ROI" && !hasRoi ? "ROI를 선택하세요" : "원본 TIFF 분석")
    readonly property string workflowLabel: loading ? "로딩 중" : loadError ? "파일 오류" : hasImage ? (hasRoi ? "ROI 선택됨" : "이미지 준비 완료") : "이미지 없음"
    readonly property string viewerStatus: loading ? "로딩 중" : loadError ? "파일 오류" : hasImage ? "준비 완료" : "이미지 없음"
    readonly property real effectiveZoom: fitMode ? fitZoom : zoom
    readonly property string zoomLabel: canNavigateImage ? (fitMode ? "FIT" : (Math.round(effectiveZoom * 1000) / 10) + "%") : "—"
    readonly property int roiX: Math.floor(Math.min(roiStartX, roiEndX) * contentWidth)
    readonly property int roiY: Math.floor(Math.min(roiStartY, roiEndY) * contentHeight)
    readonly property int roiWidth: Math.ceil(Math.max(roiStartX, roiEndX) * contentWidth) - roiX
    readonly property int roiHeight: Math.ceil(Math.max(roiStartY, roiEndY) * contentHeight) - roiY
}
