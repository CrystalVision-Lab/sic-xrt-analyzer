import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "imageViewer"
    property QtObject theme
    property QtObject uiState
    property var actions
    property real panX: 0
    property real panY: 0
    property real pressX: 0
    property real pressY: 0
    property real pressPanX: 0
    property real pressPanY: 0
    readonly property real fitScale: Math.max(0, Math.min((viewport.width - 48) / Math.max(1, uiState.contentWidth), (viewport.height - 48) / Math.max(1, uiState.contentHeight)))
    readonly property real viewportWidth: viewport.width
    signal fileDropped(string url)
    color: theme.viewer
    function resetPan() { panX = 0; panY = 0 }
    function fitView() { resetPan(); uiState.zoom = 1; uiState.statusText = "화면 맞춤 기준 100%" }
    function zoomIn() { if (uiState.canNavigateImage) uiState.zoom = Math.min(8, uiState.zoom * 1.25) }
    function zoomOut() { if (uiState.canNavigateImage) uiState.zoom = Math.max(0.1, uiState.zoom / 1.25) }
    function imagePoint(x, y) {
        return Qt.point(Math.max(0, Math.min(1, (x - imageFrame.x) / imageFrame.width)), Math.max(0, Math.min(1, (y - imageFrame.y) / imageFrame.height)))
    }
    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 52
            color: theme.viewerHeader
            RowLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 14
                ColumnLayout {
                    spacing: 3; Layout.fillWidth: true
                    Text { text: "XRT VIEWER"; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: 11 }
                    Text { text: uiState.demoMode ? "SYNTHETIC DEMO · 실제 XRT 데이터 아님" : uiState.fileName || "No XRT image loaded"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 12; elide: Text.ElideMiddle; Layout.fillWidth: true }
                }
                Text { text: uiState.hasImage ? uiState.contentWidth + " × " + uiState.contentHeight + (uiState.demoMode ? " · DEMO" : " · " + uiState.bitDepth + "-bit") : "TIFF / TIF"; color: theme.muted; font.family: theme.monoFontFamily; font.pixelSize: 11 }
                StatusIndicator { theme: root.theme; text: uiState.activeTool === "이동" ? "PAN" : "ROI"; ink: theme.accent; visible: uiState.canNavigateImage }
            }
        }
        Rectangle {
            id: viewport
            objectName: "viewerViewport"
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true; color: uiState.viewerBackground
            Item {
                id: imageFrame
                objectName: "imageFrame"
                visible: uiState.hasImage
                width: uiState.contentWidth * root.fitScale * uiState.zoom
                height: uiState.contentHeight * root.fitScale * uiState.zoom
                x: (viewport.width - width) / 2 + root.panX
                y: (viewport.height - height) / 2 + root.panY
                DemoImage { theme: root.theme; anchors.fill: parent; visible: uiState.demoMode }
                Image { objectName: "tiffImage"; anchors.fill: parent; source: uiState.imageSource; visible: uiState.hasLoadedImage && !uiState.demoMode; smooth: uiState.smoothImages; cache: false }
                Rectangle {
                    visible: uiState.hasRoi && uiState.roiLayerVisible
                    x: Math.min(uiState.roiStartX, uiState.roiEndX) * parent.width
                    y: Math.min(uiState.roiStartY, uiState.roiEndY) * parent.height
                    width: Math.abs(uiState.roiEndX - uiState.roiStartX) * parent.width
                    height: Math.abs(uiState.roiEndY - uiState.roiStartY) * parent.height
                    color: "#1645c3cf"; border.color: theme.accent; border.width: 1
                }
            }
            MouseArea {
                objectName: "viewerMouseArea"
                anchors.fill: parent; enabled: uiState.canNavigateImage; hoverEnabled: true
                cursorShape: uiState.activeTool === "이동" ? (pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor) : Qt.CrossCursor
                onPressed: function(mouse) {
                    root.pressX = mouse.x; root.pressY = mouse.y; root.pressPanX = root.panX; root.pressPanY = root.panY
                    if (uiState.activeTool !== "이동") {
                        var p = root.imagePoint(mouse.x, mouse.y)
                        uiState.roiStartX = p.x; uiState.roiStartY = p.y
                        uiState.roiEndX = p.x; uiState.roiEndY = p.y; uiState.hasRoi = false
                    }
                }
                onPositionChanged: function(mouse) {
                    var inside = mouse.x >= imageFrame.x && mouse.x < imageFrame.x + imageFrame.width && mouse.y >= imageFrame.y && mouse.y < imageFrame.y + imageFrame.height
                    var p = root.imagePoint(mouse.x, mouse.y)
                    uiState.cursorX = inside ? Math.min(uiState.contentWidth - 1, Math.floor(p.x * uiState.contentWidth)) : -1
                    uiState.cursorY = inside ? Math.min(uiState.contentHeight - 1, Math.floor(p.y * uiState.contentHeight)) : -1
                    if (!pressed) return
                    if (uiState.activeTool === "이동") {
                        root.panX = root.pressPanX + mouse.x - root.pressX
                        root.panY = root.pressPanY + mouse.y - root.pressY
                    } else {
                        uiState.roiEndX = p.x; uiState.roiEndY = p.y
                        uiState.hasRoi = uiState.roiWidth > 0 && uiState.roiHeight > 0
                    }
                }
                onExited: { uiState.cursorX = -1; uiState.cursorY = -1 }
                onWheel: function(wheel) { if (wheel.angleDelta.y > 0) root.actions.zoomIn.trigger(); else root.actions.zoomOut.trigger() }
            }
            ColumnLayout {
                anchors.centerIn: parent; spacing: 10
                visible: !uiState.hasImage && !uiState.loading
                Text { text: "No XRT image loaded"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 17 }
                Text { text: "TIFF / TIF · 16-bit grayscale supported"; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: 12 }
                AppButton { theme: root.theme; action: root.actions.open; text: "Open XRT Image"; iconName: "open"; Layout.alignment: Qt.AlignHCenter }
                Text { text: "또는 TIFF 파일을 이 영역에 놓으세요"; color: theme.muted; font.pixelSize: 11; Layout.alignment: Qt.AlignHCenter }
            }
            Rectangle {
                anchors.fill: parent; visible: uiState.loading; color: "#db111518"
                ColumnLayout { anchors.centerIn: parent
                    BusyIndicator { running: uiState.loading; Layout.alignment: Qt.AlignHCenter }
                    Text { text: "Loading image…"; color: theme.text }
                }
            }
            DropArea { anchors.fill: parent; onDropped: function(drop) { if (drop.hasUrls && drop.urls.length > 0) root.fileDropped(drop.urls[0].toString()) } }
        }
        Rectangle {
            visible: uiState.loadError.length > 0
            Layout.fillWidth: true; Layout.preferredHeight: errorText.implicitHeight + 18
            color: "#332427"
            Text { id: errorText; anchors.fill: parent; anchors.margins: 9; text: "FILE ERROR · " + uiState.loadError + (uiState.hasImage ? "\n이전 이미지를 유지했습니다." : ""); color: theme.error; font.pixelSize: 11; wrapMode: Text.Wrap }
        }
    }
}
