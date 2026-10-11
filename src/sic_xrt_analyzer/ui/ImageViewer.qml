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
    readonly property real fitScale: Math.max(0, Math.min((viewport.width - 16) / Math.max(1, uiState.contentWidth), (viewport.height - 16) / Math.max(1, uiState.contentHeight)))
    readonly property real viewportWidth: viewport.width
    readonly property real displayScale: uiState.fitMode ? fitScale : uiState.zoom / uiState.displayPixelRatio
    Binding { target: root.uiState; property: "fitZoom"; value: root.fitScale * root.uiState.displayPixelRatio }
    signal fileDropped(string url)
    color: theme.viewer
    function resetPan() { panX = 0; panY = 0 }
    function focusView() { viewerMouse.forceActiveFocus() }
    function syncDetailView() {
        if (!uiState.hasLoadedImage || uiState.loading || !uiState.sampledPreview || uiState.pageCount !== 1 || displayScale <= 0) { fileBridge.clearDetail(); return }
        var left = Math.max(0, Math.floor(-imageFrame.x / displayScale))
        var top = Math.max(0, Math.floor(-imageFrame.y / displayScale))
        var right = Math.min(uiState.imageWidth, Math.ceil((viewport.width - imageFrame.x) / displayScale))
        var bottom = Math.min(uiState.imageHeight, Math.ceil((viewport.height - imageFrame.y) / displayScale))
        if (right <= left || bottom <= top) fileBridge.clearDetail()
        else fileBridge.requestDetail(left, top, right - left, bottom - top)
    }
    onDisplayScaleChanged: Qt.callLater(syncDetailView)
    Connections {
        target: root.uiState
        function onImageSourceChanged() { Qt.callLater(root.syncDetailView) }
        function onLoadingChanged() { Qt.callLater(root.syncDetailView) }
    }
    function stepPage(delta) {
        if (uiState.hasLoadedImage && uiState.pageCount > 1 && !uiState.loading)
            fileBridge.requestPage(Math.max(0, Math.min(uiState.pageCount - 1, uiState.stack.requestedPage + delta)))
    }
    function fitView() { resetPan(); uiState.fitMode = true; uiState.statusText = "화면 맞춤" }
    function setActualZoom(value) { resetPan(); uiState.zoom = value; uiState.fitMode = false }
    function defaultView() {
        if (uiState.defaultView === "fit") fitView()
        else setActualZoom(uiState.defaultView === "actual" ? 1 : uiState.defaultView === "125" ? 1.25 : 2)
    }
    function zoomIn() { if (uiState.canNavigateImage) { uiState.zoom = Math.min(16, uiState.effectiveZoom * 1.25); uiState.fitMode = false } }
    function zoomOut() { if (uiState.canNavigateImage) { uiState.zoom = Math.max(0.01, uiState.effectiveZoom / 1.25); uiState.fitMode = false } }
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
                    Text { text: uiState.demoMode ? "합성 데모 · 실제 XRT 데이터 아님" : uiState.fileName || "XRT 이미지 없음"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 12; elide: Text.ElideMiddle; Layout.fillWidth: true }
                }
                Text { text: uiState.hasImage ? uiState.contentWidth + " × " + uiState.contentHeight + (uiState.demoMode ? " · 데모" : " · " + uiState.dtype + " · " + (uiState.pageIndex + 1) + "/" + uiState.pageCount) : "TIFF / JPG"; color: theme.muted; font.family: theme.monoFontFamily; font.pixelSize: 11 }
                StatusIndicator { theme: root.theme; text: uiState.activeTool === "Pan" ? "PAN" : "ROI"; ink: theme.accent; visible: uiState.canNavigateImage }
            }
        }
        Rectangle {
            id: viewport
            objectName: "viewerViewport"
            Layout.fillWidth: true; Layout.fillHeight: true
            onWidthChanged: Qt.callLater(root.syncDetailView)
            onHeightChanged: Qt.callLater(root.syncDetailView)
            clip: true; color: uiState.viewerBackground
            Item {
                id: imageFrame
                objectName: "imageFrame"
                visible: uiState.hasImage
                width: uiState.contentWidth * root.displayScale
                height: uiState.contentHeight * root.displayScale
                x: (viewport.width - width) / 2 + root.panX
                y: (viewport.height - height) / 2 + root.panY
                onXChanged: Qt.callLater(root.syncDetailView)
                onYChanged: Qt.callLater(root.syncDetailView)
                DemoImage { theme: root.theme; anchors.fill: parent; visible: uiState.demoMode }
                Image { objectName: "tiffImage"; anchors.fill: parent; source: uiState.imageSource; visible: uiState.hasLoadedImage && !uiState.demoMode; smooth: uiState.smoothImages; cache: false }
                Image {
                    objectName: "detailImage"; visible: uiState.detail.ready
                    x: uiState.detail.x * root.displayScale; y: uiState.detail.y * root.displayScale
                    width: uiState.detail.width * root.displayScale; height: uiState.detail.height * root.displayScale
                    source: uiState.detail.source; smooth: uiState.smoothImages; cache: false
                }
                Rectangle {
                    objectName: "roiOverlay"
                    visible: uiState.hasRoi && uiState.roiLayerVisible
                    x: Math.min(uiState.roiStartX, uiState.roiEndX) * parent.width
                    y: Math.min(uiState.roiStartY, uiState.roiEndY) * parent.height
                    width: Math.abs(uiState.roiEndX - uiState.roiStartX) * parent.width
                    height: Math.abs(uiState.roiEndY - uiState.roiStartY) * parent.height
                    color: uiState.selectingRoi ? "#1445c3cf" : "#0a45c3cf"; border.color: theme.accent; border.width: uiState.selectingRoi ? 2 : 1
                }
            }
            MouseArea {
                id: viewerMouse
                objectName: "viewerMouseArea"
                anchors.fill: parent; enabled: uiState.canNavigateImage; hoverEnabled: true
                focus: true
                Keys.onPressed: function(event) {
                    if (uiState.pageCount > 1 && [Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End].indexOf(event.key) >= 0) {
                        if (event.key === Qt.Key_Home) fileBridge.requestPage(0)
                        else if (event.key === Qt.Key_End) fileBridge.requestPage(uiState.pageCount - 1)
                        else root.stepPage([Qt.Key_Right, Qt.Key_Down, Qt.Key_PageDown].indexOf(event.key) >= 0 ? 1 : -1)
                        event.accepted = true
                    }
                }
                cursorShape: uiState.activeTool === "Pan" ? (pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor) : Qt.CrossCursor
                onPressed: function(mouse) {
                    forceActiveFocus()
                    root.pressX = mouse.x; root.pressY = mouse.y; root.pressPanX = root.panX; root.pressPanY = root.panY
                    if (uiState.activeTool !== "Pan") {
                        uiState.selectingRoi = true
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
                    if (uiState.activeTool === "Pan") {
                        root.panX = root.pressPanX + mouse.x - root.pressX
                        root.panY = root.pressPanY + mouse.y - root.pressY
                    } else {
                        uiState.roiEndX = p.x; uiState.roiEndY = p.y
                        uiState.hasRoi = uiState.roiWidth > 0 && uiState.roiHeight > 0
                    }
                }
                onExited: { uiState.cursorX = -1; uiState.cursorY = -1 }
                onReleased: uiState.selectingRoi = false
                onCanceled: uiState.selectingRoi = false
                onWheel: function(wheel) {
                    var delta = wheel.angleDelta.y || wheel.pixelDelta.y
                    if (delta === 0) return
                    if (uiState.hasLoadedImage && uiState.pageCount > 1 && !(wheel.modifiers & Qt.ControlModifier)) root.stepPage(delta < 0 ? 1 : -1)
                    else if (delta > 0) root.actions.zoomIn.trigger()
                    else root.actions.zoomOut.trigger()
                    wheel.accepted = true
                }
            }
            ImportedRoiOverlay {
                anchors.fill: parent
                rois: uiState.importedRois.items
                imageX: imageFrame.x; imageY: imageFrame.y; imageScale: root.displayScale
                layerVisible: uiState.roiLayerVisible && uiState.hasLoadedImage
            }
            ColumnLayout {
                anchors.centerIn: parent; spacing: 10
                visible: !uiState.hasImage && !uiState.loading
                Text { text: "XRT 이미지 없음"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 17 }
                Text { text: "TIFF / JPG · 16-bit TIFF 및 RGB 지원"; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: 12 }
                AppButton { theme: root.theme; action: root.actions.open; text: "XRT 이미지 열기"; iconName: "open"; Layout.alignment: Qt.AlignHCenter }
                Text { text: "또는 TIFF/JPG 파일을 이 영역에 놓으세요"; color: theme.muted; font.pixelSize: 11; Layout.alignment: Qt.AlignHCenter }
            }
            Rectangle {
                objectName: "initialLoadingOverlay"
                anchors.fill: parent; visible: uiState.loading; color: "#db111518"
                ColumnLayout { anchors.centerIn: parent; width: Math.min(380, parent.width - 40); spacing: 12
                    BusyIndicator { running: uiState.loading && !uiState.stack.preloadError; Layout.alignment: Qt.AlignHCenter }
                    Text {
                        objectName: "initialLoadingText"; Layout.fillWidth: true; wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter; color: uiState.stack.preloadError ? theme.error : theme.text
                        text: uiState.stack.preloadError ? "전체 페이지 로딩 실패\n" + uiState.stack.preloadError
                              : uiState.stack.preload.total > 0 ? "전체 페이지 불러오는 중 · " + uiState.stack.preload.prepared + " / " + uiState.stack.preload.total
                              : "이미지 정보를 읽는 중…"
                    }
                    ProgressBar {
                        id: preloadProgress
                        objectName: "initialLoadingProgress"; Layout.fillWidth: true
                        implicitHeight: 6; padding: 0
                        visible: uiState.stack.preload.total > 0
                        from: 0; to: Math.max(1, uiState.stack.preload.total); value: uiState.stack.preload.prepared
                        background: Rectangle { color: theme.border; radius: 2 }
                        contentItem: Item {
                            Rectangle { width: parent.width * preloadProgress.visualPosition; height: parent.height; color: theme.accent; radius: 2 }
                        }
                    }
                    Text { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; color: theme.muted; text: "전체 로딩이 완료되면 스크롤과 드래그가 활성화됩니다." }
                    RowLayout { Layout.alignment: Qt.AlignHCenter
                        AppButton { theme: root.theme; text: "다시 준비"; visible: !!uiState.stack.preloadError; onClicked: fileBridge.retryPreload() }
                        AppButton { objectName: "cancelInitialLoading"; theme: root.theme; text: "취소"; onClicked: root.actions.closeImage.trigger() }
                    }
                }
            }
            DropArea { anchors.fill: parent; onDropped: function(drop) { if (drop.hasUrls && drop.urls.length > 0) root.fileDropped(drop.urls[0].toString()) } }
            Rectangle {
                visible: uiState.pageLoading; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12
                width: 178; height: 30; color: theme.panel; border.color: theme.border; radius: 3
                Text { anchors.centerIn: parent; text: "페이지 " + (uiState.stack.requestedPage + 1) + " 읽는 중…"; color: theme.text; font.pixelSize: 11 }
            }
            Rectangle {
                visible: uiState.detail.busy || uiState.detail.error.length > 0
                anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12
                width: Math.min(parent.width - 24, 280); height: detailText.implicitHeight + 16
                color: theme.panel; border.color: theme.border; radius: 3
                Text { id: detailText; anchors.fill: parent; anchors.margins: 8; text: uiState.detail.error ? "정밀 영역 읽기 실패: " + uiState.detail.error : "정밀 영역 읽는 중…"; color: uiState.detail.error ? theme.warning : theme.muted; wrapMode: Text.Wrap; font.pixelSize: 11 }
            }
        }
        Rectangle {
            visible: uiState.loadError.length > 0 || uiState.stack.error.length > 0
            Layout.fillWidth: true; Layout.preferredHeight: errorText.implicitHeight + 18
            color: "#332427"
            Text { id: errorText; anchors.fill: parent; anchors.margins: 9; text:  "파일 오류 · " + (uiState.loadError || uiState.stack.error) + (uiState.hasImage ? "\n이전 이미지를 유지했습니다." : ""); color: theme.error; font.pixelSize: 11; wrapMode: Text.Wrap }
        }
    }
}
