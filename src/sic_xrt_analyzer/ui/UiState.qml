import QtQuick
QtObject {
    property string filePath: ""
    property string fileName: ""
    property int workspaceIndex: 0
    property string activeTool: "이동"
    property real zoom: 1
    property bool demoMode: false
    property string imageSource: ""
    property int imageWidth: 0
    property int imageHeight: 0
    property int bitDepth: 0
    property int pageCount: 0
    property bool sampledPreview: false
    property bool loading: false
    property string loadError: ""
    property bool hasRoi: false
    property bool roiLayerVisible: true
    property real roiStartX: 0
    property real roiStartY: 0
    property real roiEndX: 0
    property real roiEndY: 0
    property int cursorX: -1
    property int cursorY: -1
    property bool smoothImages: true
    property string viewerBackground: "#111518"
    property real defaultZoom: 1
    property string statusText: "TIFF 이미지를 열거나 합성 데모를 확인하세요"
    readonly property bool modelAvailable: false
    readonly property bool analysisRunning: false
    readonly property bool hasResult: false
    readonly property bool projectModified: false
    readonly property bool hasSelectedFile: filePath.length > 0
    readonly property bool hasLoadedImage: imageSource.length > 0 && hasSelectedFile
    readonly property bool hasImage: demoMode || hasLoadedImage
    readonly property int contentWidth: demoMode ? 960 : imageWidth
    readonly property int contentHeight: demoMode ? 600 : imageHeight
    readonly property bool canNavigateImage: workspaceIndex === 0 && hasImage && !loading
    readonly property bool canAnalyze: hasLoadedImage && modelAvailable && !analysisRunning && !loading
    readonly property string analysisReason: "승인된 모델과 분석 파이프라인이 연결되지 않았습니다"
    readonly property string workflowLabel: loading ? "LOADING" : loadError ? "FILE ERROR" : hasImage ? (hasRoi ? "ROI SELECTED" : "IMAGE READY") : "IDLE"
    readonly property string zoomLabel: canNavigateImage ? Math.round(zoom * 100) + "%" : "—"
    readonly property int roiX: Math.floor(Math.min(roiStartX, roiEndX) * contentWidth)
    readonly property int roiY: Math.floor(Math.min(roiStartY, roiEndY) * contentHeight)
    readonly property int roiWidth: Math.ceil(Math.max(roiStartX, roiEndX) * contentWidth) - roiX
    readonly property int roiHeight: Math.ceil(Math.max(roiStartY, roiEndY) * contentHeight) - roiY
}
