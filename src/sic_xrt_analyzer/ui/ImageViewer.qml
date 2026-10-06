import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import XrtViewer 1.0

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
    property real focusZoom: 1
    property real focusPanX: 0
    property real focusPanY: 0
    function focusCandidate(x, y) {
        if (!uiState.hasLoadedImage || uiState.loading || !uiState.hasResult || !uiState.research.selected.id || uiState.research.selected.x !== x || uiState.research.selected.y !== y) return
        focusAnimation.stop()
        var current = displayScale
        uiState.zoom = current * uiState.displayPixelRatio
        uiState.fitMode = false
        var span = uiState.candidateRoiId ? Math.max(192, uiState.candidateRoiSize * 1.3) : 192
        var target = Math.max(fitScale, Math.min(4, Math.min(viewport.width, viewport.height) / span))
        focusZoom = target * uiState.displayPixelRatio
        focusPanX = (uiState.contentWidth / 2 - x) * target
        focusPanY = (uiState.contentHeight / 2 - y) * target
        uiState.analysisLayerVisible = true
        focusAnimation.start()
    }
    ParallelAnimation {
        id: focusAnimation; objectName: "candidateFocusAnimation"
        NumberAnimation { target: root.uiState; property: "zoom"; to: root.focusZoom; duration: 450; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "panX"; to: root.focusPanX; duration: 450; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "panY"; to: root.focusPanY; duration: 450; easing.type: Easing.InOutCubic }
    }
    property bool draggingVertex: false
    property var toolPoints: []
    property bool drawingTool: false
    function finishTool() {
        if (toolPoints.length) fileBridge.imagej.gesture(uiState.activeTool, toolPoints)
        toolPoints = []; drawingTool = false; toolPreview.requestPaint()
    }
    function toolPoint(mouse) {
        return [Math.max(0, Math.min(uiState.contentWidth - 1, (mouse.x - imageFrame.x) / displayScale)),
                Math.max(0, Math.min(uiState.contentHeight - 1, (mouse.y - imageFrame.y) / displayScale))]
    }
    readonly property real fitScale: Math.max(0, Math.min((viewport.width - 16) / Math.max(1, uiState.contentWidth), (viewport.height - 16) / Math.max(1, uiState.contentHeight)))
    readonly property real viewportWidth: viewport.width
    readonly property real displayScale: uiState.fitMode ? fitScale : uiState.zoom / uiState.displayPixelRatio
    Binding { target: root.uiState; property: "fitZoom"; value: root.fitScale * root.uiState.displayPixelRatio }
    signal fileDropped(string url)
    color: theme.viewer
    function resetPan() { focusAnimation.stop(); panX = 0; panY = 0 }
    function focusView() { viewerMouse.forceActiveFocus() }
    function syncDetailView() {
        if (uiState.stack.preparedDisplay || !uiState.hasLoadedImage || uiState.loading || !uiState.sampledPreview || uiState.pageCount !== 1 || displayScale <= 0) { fileBridge.clearDetail(); return }
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
        function onResearchChanged() { if (!uiState.research.selected.id) focusAnimation.stop() }
        function onHasResultChanged() { if (!uiState.hasResult) focusAnimation.stop() }
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
    function zoomIn() { focusAnimation.stop(); if (uiState.canNavigateImage) { uiState.zoom = Math.min(16, uiState.effectiveZoom * 1.25); uiState.fitMode = false } }
    function zoomOut() { focusAnimation.stop(); if (uiState.canNavigateImage) { uiState.zoom = Math.max(0.01, uiState.effectiveZoom / 1.25); uiState.fitMode = false } }
    function imagePoint(x, y) {
        return Qt.point(Math.max(0, Math.min(1, (x - imageFrame.x) / imageFrame.width)), Math.max(0, Math.min(1, (y - imageFrame.y) / imageFrame.height)))
    }
    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        ViewerHeader {
            Layout.fillWidth: true; Layout.preferredHeight: 52
            theme: root.theme; uiState: root.uiState
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
                z: 1
                objectName: "imageFrame"
                visible: uiState.hasImage
                width: uiState.contentWidth * root.displayScale
                height: uiState.contentHeight * root.displayScale
                x: (viewport.width - width) / 2 + root.panX
                y: (viewport.height - height) / 2 + root.panY
                onXChanged: Qt.callLater(root.syncDetailView)
                onYChanged: Qt.callLater(root.syncDetailView)
                DemoImage { theme: root.theme; anchors.fill: parent; visible: uiState.demoMode }
                Image { objectName: "tiffImage"; anchors.fill: parent; source: uiState.imageSource; visible: uiState.hasLoadedImage && !uiState.demoMode && !uiState.stack.preparedDisplay; smooth: uiState.smoothImages; cache: false }
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
            PreparedView {
                objectName: "preparedImageView"; anchors.fill: parent
                visible: uiState.hasLoadedImage && uiState.stack.preparedDisplay
                bridge: fileBridge; viewTransform: [imageFrame.x, imageFrame.y, root.displayScale]
                revision: uiState.stack.revision
            }
            MouseArea {
                id: viewerMouse
                z: 2
                objectName: "viewerMouseArea"
                anchors.fill: parent; enabled: uiState.canNavigateImage; hoverEnabled: true
                focus: true
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Escape) { root.toolPoints = []; root.drawingTool = false; toolPreview.requestPaint(); event.accepted = true; return }
                    if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && root.toolPoints.length) { root.finishTool(); event.accepted = true; return }
                    if (uiState.roiEditMode && event.key === Qt.Key_Delete) { fileBridge.deleteRoiVertex(); event.accepted = true; return }
                    if (uiState.roiEditMode && event.key === Qt.Key_Z && (event.modifiers & Qt.ControlModifier)) { fileBridge.roiHistory(!!(event.modifiers & Qt.ShiftModifier)); event.accepted = true; return }
                    if (uiState.pageCount > 1 && [Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End].indexOf(event.key) >= 0) {
                        if (event.key === Qt.Key_Home) fileBridge.requestPage(0)
                        else if (event.key === Qt.Key_End) fileBridge.requestPage(uiState.pageCount - 1)
                        else root.stepPage([Qt.Key_Right, Qt.Key_Down, Qt.Key_PageDown].indexOf(event.key) >= 0 ? 1 : -1)
                        event.accepted = true
                    }
                }
                cursorShape: uiState.roiEditMode ? Qt.CrossCursor : uiState.activeTool === "Pan" ? (pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor) : Qt.CrossCursor
                onPressed: function(mouse) {
                    focusAnimation.stop()
                    forceActiveFocus()
                    root.pressX = mouse.x; root.pressY = mouse.y; root.pressPanX = root.panX; root.pressPanY = root.panY
                    if (uiState.roiEditMode) {
                        var editPoint = root.imagePoint(mouse.x, mouse.y)
                        root.draggingVertex = fileBridge.beginRoiDrag(editPoint.x * uiState.contentWidth, editPoint.y * uiState.contentHeight, 8 / root.displayScale)
                        return
                    }
                    if (uiState.activeTool === "Zoom") { if (mouse.modifiers & Qt.AltModifier) root.zoomOut(); else root.zoomIn(); return }
                    if (["Pan", "ROI"].indexOf(uiState.activeTool) < 0) {
                        var t = root.toolPoint(mouse)
                        if (["Polygon", "Polyline", "Angle"].indexOf(uiState.activeTool) >= 0) {
                            root.toolPoints = root.toolPoints.concat([t])
                            if (uiState.activeTool === "Angle" && root.toolPoints.length === 3) root.finishTool()
                        } else if (["Point", "Wand", "Picker", "Fill", "Text"].indexOf(uiState.activeTool) >= 0) {
                            fileBridge.imagej.gesture(uiState.activeTool, [t])
                        } else { root.toolPoints = [t]; root.drawingTool = true }
                        toolPreview.requestPaint(); return
                    }
                    if (uiState.activeTool !== "Pan") {
                        uiState.stopCandidateRoiTracking()
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
                    if (root.drawingTool) {
                        var t = root.toolPoint(mouse)
                        if (["Rectangle", "Oval", "Line", "Arrow"].indexOf(uiState.activeTool) >= 0) root.toolPoints = [root.toolPoints[0], t]
                        else if (root.toolPoints.length < 10000) root.toolPoints = root.toolPoints.concat([t])
                        toolPreview.requestPaint(); return
                    }
                    if (["Pan", "ROI"].indexOf(uiState.activeTool) < 0 && !uiState.roiEditMode) return
                    if (uiState.roiEditMode) {
                        if (root.draggingVertex) fileBridge.dragRoiVertex(p.x * uiState.contentWidth, p.y * uiState.contentHeight)
                        else { root.panX = root.pressPanX + mouse.x - root.pressX; root.panY = root.pressPanY + mouse.y - root.pressY }
                        return
                    }
                    if (uiState.activeTool === "Pan") {
                        root.panX = root.pressPanX + mouse.x - root.pressX
                        root.panY = root.pressPanY + mouse.y - root.pressY
                    } else {
                        uiState.roiEndX = p.x; uiState.roiEndY = p.y
                        uiState.hasRoi = uiState.roiWidth > 0 && uiState.roiHeight > 0
                    }
                }
                onExited: { uiState.cursorX = -1; uiState.cursorY = -1 }
                onDoubleClicked: function(mouse) {
                    if (["Polygon", "Polyline"].indexOf(uiState.activeTool) >= 0) { root.finishTool(); return }
                    if (uiState.roiEditMode) {
                        var p = root.imagePoint(mouse.x, mouse.y)
                        fileBridge.finishRoiDrag(true); root.draggingVertex = false
                        fileBridge.addRoiVertex(p.x * uiState.contentWidth, p.y * uiState.contentHeight)
                    }
                }
                onReleased: function(mouse) {
                    if (uiState.activeTool === "Pan" && !uiState.roiEditMode && uiState.hasResult && uiState.analysisLayerVisible && Math.hypot(mouse.x-root.pressX, mouse.y-root.pressY) < 4) {
                        var points = uiState.research.filteredPoints, best = null, distance = 12
                        for (var i=0; i<points.length; i++) {
                            var p=points[i], d=Math.hypot(mouse.x-imageFrame.x-p.x*root.displayScale, mouse.y-imageFrame.y-p.y*root.displayScale)
                            if (d < distance) { best=p; distance=d }
                        }
                        if (best) fileBridge.research.selectCandidate(best.id)
                    }
                    if (root.drawingTool) root.finishTool(); uiState.selectingRoi = false; if (root.draggingVertex) fileBridge.finishRoiDrag(false); root.draggingVertex = false
                }
                onCanceled: { root.toolPoints = []; root.drawingTool = false; toolPreview.requestPaint(); uiState.selectingRoi = false; if (root.draggingVertex) fileBridge.finishRoiDrag(true); root.draggingVertex = false }
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
                z: 3
                anchors.fill: parent
                rois: uiState.importedRois.items
                imageX: imageFrame.x; imageY: imageFrame.y; imageScale: root.displayScale
                layerVisible: uiState.roiLayerVisible && uiState.hasLoadedImage
                editMode: uiState.roiEditMode; selectedVertex: uiState.importedRois.vertex
            }
            Canvas {
                id: analysisOverlay; objectName: "analysisOverlay"; anchors.fill: parent; z: 3
                property var points: uiState.research.filteredPoints
                property var selected: uiState.research.selected
                property real imageX: imageFrame.x
                property real imageY: imageFrame.y
                property real imageScale: root.displayScale
                visible: uiState.hasResult && uiState.analysisLayerVisible && uiState.hasLoadedImage
                onPointsChanged: requestPaint()
                onSelectedChanged: requestPaint()
                onImageXChanged: requestPaint()
                onImageYChanged: requestPaint()
                onImageScaleChanged: requestPaint()
                onVisibleChanged: requestPaint()
                onPaint: {
                    var c = getContext("2d"); c.reset(); c.lineWidth = 1.5
                    for (var i = 0; i < points.length; i++) {
                        var p = points[i], x = imageX + p.x * imageScale, y = imageY + p.y * imageScale
                        if (x < -6 || y < -6 || x > width + 6 || y > height + 6) continue
                        c.strokeStyle = p.low_score ? "#ffffff" : p.type === "BPD" ? "#ffad42" : p.type === "TED" ? "#50e0ee" : "#ff78c4"
                        c.beginPath(); c.arc(x, y, 5, 0, Math.PI * 2); c.stroke()
                    }
                    if (selected.id) {
                        var sx=imageX+selected.x*imageScale, sy=imageY+selected.y*imageScale
                        c.strokeStyle="#fff04a"; c.lineWidth=2
                        c.beginPath(); c.arc(sx,sy,11,0,Math.PI*2); c.stroke()
                        c.beginPath(); c.moveTo(sx-20,sy); c.lineTo(sx-13,sy); c.moveTo(sx+13,sy); c.lineTo(sx+20,sy); c.moveTo(sx,sy-20); c.lineTo(sx,sy-13); c.moveTo(sx,sy+13); c.lineTo(sx,sy+20); c.stroke()
                        c.fillStyle="#14191e"; c.fillRect(sx+15,sy-30,110,22)
                        c.fillStyle="#fff04a"; c.font="12px sans-serif"; c.fillText("#"+selected.number+"  "+selected.type,sx+20,sy-15)
                    }
                }
            }
            Canvas {
                id: toolPreview; anchors.fill: parent
                z: 3
                onPaint: {
                    var c = getContext("2d"); c.reset(); var p = root.toolPoints
                    if (!p.length) return
                    c.strokeStyle = fileBridge.imagej.state.color; c.lineWidth = 2
                    c.translate(imageFrame.x, imageFrame.y); c.scale(root.displayScale, root.displayScale)
                    c.lineWidth = 2 / root.displayScale; c.beginPath()
                    var a = p[0], b = p[p.length - 1]
                    if (uiState.activeTool === "Rectangle") c.rect(a[0], a[1], b[0]-a[0], b[1]-a[1])
                    else if (uiState.activeTool === "Oval") c.ellipse(Math.min(a[0],b[0]), Math.min(a[1],b[1]), Math.abs(b[0]-a[0]), Math.abs(b[1]-a[1]))
                    else { c.moveTo(a[0],a[1]); for (var i=1;i<p.length;++i) c.lineTo(p[i][0],p[i][1]) }
                    c.stroke()
                }
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
                z: 10
                anchors.fill: parent; visible: uiState.loading; color: "#db111518"
                ColumnLayout { anchors.centerIn: parent; width: Math.min(380, parent.width - 40); spacing: 12
                    BusyIndicator { running: uiState.loading && !uiState.stack.preloadError; Layout.alignment: Qt.AlignHCenter }
                    Text {
                        objectName: "initialLoadingText"; Layout.fillWidth: true; wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter; color: uiState.stack.preloadError ? theme.error : theme.text
                        text: uiState.stack.preloadError ? "전체 페이지 로딩 실패\n" + uiState.stack.preloadError
                              : uiState.stack.preparing.label && uiState.opening ? uiState.stack.preparing.label
                              : uiState.stack.preload.total > 0 ? "전체 페이지 불러오는 중 · " + uiState.stack.preload.prepared + " / " + uiState.stack.preload.total
                              : "이미지 정보를 읽는 중…"
                    }
                    ProgressBar {
                        id: preloadProgress
                        objectName: "initialLoadingProgress"; Layout.fillWidth: true
                        implicitHeight: 6; padding: 0
                        visible: uiState.stack.preload.total > 0 || uiState.stack.preparing.total > 0
                        from: 0; to: Math.max(1, uiState.opening ? uiState.stack.preparing.total || 1 : uiState.stack.preload.total); value: uiState.opening ? uiState.stack.preparing.done || 0 : uiState.stack.preload.prepared
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
