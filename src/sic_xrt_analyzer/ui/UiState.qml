import QtQuick

QtObject {
    property string filePath: ""
    property string fileName: ""
    property int workspaceIndex: 0
    property string activeTool: "이동"
    // 100% means the demo image is fitted to the available viewer area.
    property real zoom: 1.0
    property bool demoMode: false
    property bool hasRoi: false
    property bool roiLayerVisible: true
    property real roiStartX: 0
    property real roiStartY: 0
    property real roiEndX: 0
    property real roiEndY: 0
    property string statusText: "이미지를 열거나 데모 이미지를 확인하세요"
    readonly property bool hasSelectedFile: filePath.length > 0
    readonly property bool canNavigateImage: workspaceIndex === 0 && demoMode
    readonly property string zoomLabel: canNavigateImage ? Math.round(zoom * 100) + "%" : "—"
}
