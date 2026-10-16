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
    property string focusedArea: ""
    property var previousView: []
    function focusCandidate(x, y) {
        var candidate = uiState.research.selected || ({})
        var reviewed = uiState.feedback.selected || ({})
        if (!uiState.hasLoadedImage || uiState.loading || !((candidate.id && candidate.x === x && candidate.y === y) || (reviewed.id && reviewed.x === x && reviewed.y === y))) return
        if (uiState.resultViewMode === "distribution") uiState.resultViewMode = "area"
        var area = root.uiState.regionReview
        if (area.enabled && area.rect.length === 4) {
            var screenX = imageFrame.x + x * displayScale
            var screenY = imageFrame.y + y * displayScale
            if (focusedArea === area.key && !uiState.fitMode && screenX >= 0 && screenX <= viewport.width && screenY >= 0 && screenY <= viewport.height) return
            focusedArea = area.key
            focusGeometry(area.rect[0],area.rect[1],area.rect[2],area.rect[3])
            return
        }
        focusAnimation.stop()
        var current = displayScale
        uiState.zoom = current * uiState.displayPixelRatio
        uiState.fitMode = false
        var span = uiState.candidateRoiId ? Math.max(192, uiState.candidateRoiSize * 1.3) : 192
        var target = Math.max(fitScale, Math.min(4, Math.min(viewport.width, viewport.height) / span))
        focusZoom = target * uiState.displayPixelRatio
        focusPanX = (uiState.contentWidth / 2 - x) * target
        focusPanY = (uiState.contentHeight / 2 - y) * target
        focusAnimation.start()
    }
    function focusGeometry(x, y, w, h) {
        if (!uiState.hasLoadedImage || uiState.loading) return
        focusAnimation.stop()
        var target = Math.max(fitScale, Math.min(4, (viewport.width - 48) / Math.max(64, w * 1.25), (viewport.height - 48) / Math.max(64, h * 1.25)))
        var cx = Math.max(w / 2, Math.min(uiState.contentWidth - w / 2, x + w / 2))
        var cy = Math.max(h / 2, Math.min(uiState.contentHeight - h / 2, y + h / 2))
        uiState.zoom = displayScale * uiState.displayPixelRatio
        uiState.fitMode = false
        focusZoom = target * uiState.displayPixelRatio
        focusPanX = (uiState.contentWidth / 2 - cx) * target
        focusPanY = (uiState.contentHeight / 2 - cy) * target
        focusAnimation.start()
    }
    ParallelAnimation {
        id: focusAnimation; objectName: "candidateFocusAnimation"
        NumberAnimation { target: root.uiState; property: "zoom"; to: root.focusZoom; duration: 450; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "panX"; to: root.focusPanX; duration: 450; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "panY"; to: root.focusPanY; duration: 450; easing.type: Easing.InOutCubic }
    }
    property bool draggingVertex: false
    property bool reviewGesture: false
    property var toolPoints: []
    property bool drawingTool: false
    Binding { target: root.uiState; property: "roiInteraction"; value: root }
    function cancelToolDrawing() { toolPoints = []; drawingTool = false; toolPreview.requestPaint() }
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
        function onResultViewModeChanged() { if (root.uiState.resultViewMode === "distribution") root.fitView() }
        function onImageSourceChanged() { root.focusedArea=""; root.previousView=[]; Qt.callLater(root.syncDetailView) }
        function onLoadingChanged() { Qt.callLater(root.syncDetailView) }
        function onActiveToolChanged() { root.cancelToolDrawing() }
        function onRoiEditModeChanged() { root.cancelToolDrawing() }
        function onPageIndexChanged() { root.cancelToolDrawing() }
        function onStackChanged() { if (root.uiState.stack.requestedPage !== root.uiState.pageIndex || root.uiState.stack.busy) root.cancelToolDrawing() }
        function onOpeningChanged() { if (uiState.opening) root.cancelToolDrawing() }
        function onResearchChanged() { if (!uiState.research.selection.id) focusAnimation.stop() }
        function onHasResultChanged() { if (!uiState.hasResult) focusAnimation.stop() }
    }
    function stepPage(delta) {
        if (uiState.hasLoadedImage && uiState.pageCount > 1 && !uiState.loading)
            fileBridge.requestPage(Math.max(0, Math.min(uiState.pageCount - 1, uiState.stack.requestedPage + delta)))
    }
    function fitView() { if (!uiState.fitMode) previousView=[uiState.zoom,panX,panY]; focusedArea=""; resetPan(); uiState.fitMode = true; uiState.statusText = "화면 맞춤" }
    function restoreView() { if (previousView.length===3) { focusAnimation.stop(); uiState.fitMode=false; uiState.zoom=previousView[0]; panX=previousView[1]; panY=previousView[2]; previousView=[] } }
    function setActualZoom(value) { resetPan(); uiState.zoom = value; uiState.fitMode = false }
    function defaultView() {
        if (uiState.defaultView === "fit") fitView()
        else setActualZoom(uiState.defaultView === "actual" ? 1 : uiState.defaultView === "125" ? 1.25 : 2)
    }
    function zoomAt(value, x, y) {
        if (!uiState.canNavigateImage || displayScale <= 0) return
        focusAnimation.stop()
        // x/y are viewport logical pixels; zoom is physical pixels/source pixel.
        // Snapshot the source anchor BEFORE changing Fit/zoom or frame bindings.
        var sourceX = (x - imageFrame.x) / displayScale
        var sourceY = (y - imageFrame.y) / displayScale
        var zoom = Math.max(0.01, Math.min(16, value))
        var scale = zoom / uiState.displayPixelRatio
        // imageFrame origin = (viewport - originalExtent * scale)/2 + pan.
        // Solve that same transform for pan, independently on each axis.
        var nextPanX = x - viewport.width / 2 + (uiState.contentWidth / 2 - sourceX) * scale
        var nextPanY = y - viewport.height / 2 + (uiState.contentHeight / 2 - sourceY) * scale
        uiState.zoom = zoom
        uiState.fitMode = false
        panX = nextPanX
        panY = nextPanY
        if (viewerMouse.containsMouse) updateCursor(viewerMouse.mouseX, viewerMouse.mouseY)
    }
    function zoomIn() { zoomAt(uiState.effectiveZoom * 1.25, viewport.width / 2, viewport.height / 2) }
    function zoomOut() { zoomAt(uiState.effectiveZoom / 1.25, viewport.width / 2, viewport.height / 2) }
    function reviewPoint(x, y) { return Qt.point((x-imageFrame.x)/displayScale, (y-imageFrame.y)/displayScale) }
    Connections { target: fileBridge.reviews; function onFocusRequested(x,y,w,h) { root.focusGeometry(x,y,w,h) } }
    Connections { target: fileBridge.research.regions; function onFocusRequested(x,y,w,h) { root.focusGeometry(x,y,w,h) } }
    function imagePoint(x, y) {
        return Qt.point(Math.max(0, Math.min(1, (x - imageFrame.x) / imageFrame.width)), Math.max(0, Math.min(1, (y - imageFrame.y) / imageFrame.height)))
    }
    function updateCursor(x, y) {
        var inside = x >= imageFrame.x && x < imageFrame.x + imageFrame.width && y >= imageFrame.y && y < imageFrame.y + imageFrame.height
        var p = imagePoint(x, y)
        uiState.cursorX = inside ? Math.min(uiState.contentWidth - 1, Math.floor(p.x * uiState.contentWidth)) : -1
        uiState.cursorY = inside ? Math.min(uiState.contentHeight - 1, Math.floor(p.y * uiState.contentHeight)) : -1
    }
    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        ViewerHeader {
            Layout.fillWidth: true; Layout.preferredHeight: 52
            theme: root.theme; uiState: root.uiState
        }
        RowLayout {
            visible: root.uiState.hasResult && !root.uiState.projectReview.editing
            Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; Layout.topMargin: 8; Layout.bottomMargin: 8; spacing: 6
            Repeater {
                model: [{key:"distribution",label:"전체 분포"},{key:"area",label:"영역 검토"},{key:"compare",label:"후보 비교"},{key:"image",label:"검출 숨김"}]
                AppButton {
                    required property var modelData
                    objectName: "resultView"+modelData.key
                    theme: root.theme; text: modelData.label; compact: true; labelSize: 12; checked: root.uiState.resultViewMode===modelData.key
                    onClicked: { root.uiState.resultViewMode=modelData.key; if(modelData.key==="area") {fileBridge.research.regions.activate(true);fileBridge.research.regions.stepArea(0)} }
                }
            }
            Item { Layout.fillWidth: true }
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
                // A hidden Canvas still receives size changes/requestPaint.
                // Never allocate the synthetic demo's image-sized backing store
                // while a large real image is being zoomed.
                Loader {
                    objectName: "demoImageLoader"; anchors.fill: parent
                    active: uiState.demoMode
                    sourceComponent: Component { DemoImage { theme: root.theme } }
                }
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
                // Match native QPainter sampling at the final scene-graph texture.
                // Fractional-DPI item origins otherwise blur neighbouring pixels.
                smooth: root.displayScale * uiState.displayPixelRatio < 1
                bridge: fileBridge; viewTransform: [imageFrame.x, imageFrame.y, root.displayScale]
                revision: uiState.stack.revision
            }
            ResultDensityOverlay {
                anchors.fill: parent; z: 6
                theme: root.theme; uiState: root.uiState
                visible: uiState.hasResult && uiState.resultViewMode==="distribution" && !uiState.projectReview.editing
                imageX: imageFrame.x; imageY: imageFrame.y; imageScale: root.displayScale
            }
            MouseArea {
                id: viewerMouse
                z: 2
                objectName: "viewerMouseArea"
                anchors.fill: parent; enabled: uiState.canNavigateImage; hoverEnabled: true
                focus: true
                Keys.onPressed: function(event) {
                    if (uiState.projectReview.editing) {
                        if (event.key===Qt.Key_Z && (event.modifiers & Qt.ControlModifier)) { fileBridge.reviews.undo(); event.accepted=true; return }
                        if (event.key===Qt.Key_Delete) { fileBridge.reviews.deleteVertex(); event.accepted=true; return }
                        if (event.key===Qt.Key_Escape) { fileBridge.reviews.cancel(); event.accepted=true; return }
                        if ([Qt.Key_Left,Qt.Key_Right].indexOf(event.key)>=0) { event.accepted=true; return }
                    }

                    if (uiState.pageCount === 1 && uiState.hasResult && !uiState.roiEditMode && [Qt.Key_Left, Qt.Key_Right].indexOf(event.key) >= 0) {
                        var delta = event.key === Qt.Key_Right ? 1 : -1
                        if (root.uiState.regionReview.enabled) fileBridge.research.regions.stepCandidate(delta)
                        else fileBridge.research.stepCandidate(delta)
                        event.accepted = true; return
                    }
                    if (event.key === Qt.Key_Escape) { fileBridge.feedback.setMode(""); root.toolPoints = []; root.drawingTool = false; toolPreview.requestPaint(); event.accepted = true; return }
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
                cursorShape: uiState.feedback.mode || uiState.roiEditMode ? Qt.CrossCursor : uiState.activeTool === "Pan" ? (pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor) : Qt.CrossCursor
                onPressed: function(mouse) {
                    focusAnimation.stop()
                    forceActiveFocus()
                    if (uiState.analysisRunning && uiState.activeTool === "ROI" && !uiState.roiEditMode) return
                    root.pressX = mouse.x; root.pressY = mouse.y; root.pressPanX = root.panX; root.pressPanY = root.panY
                    if (uiState.projectReview.editing && uiState.projectReview.tool !== "pan") {
                        var rp=root.reviewPoint(mouse.x,mouse.y);fileBridge.reviews.press(rp.x,rp.y,8/root.displayScale);return
                    }
                    root.reviewGesture = !!uiState.feedback.mode
                    if (uiState.feedback.mode) {
                        if (mouse.x >= imageFrame.x && mouse.x < imageFrame.x + imageFrame.width && mouse.y >= imageFrame.y && mouse.y < imageFrame.y + imageFrame.height) {
                            var reviewPoint = root.toolPoint(mouse)
                            fileBridge.feedback.place(reviewPoint[0], reviewPoint[1])
                        }
                        return
                    }
                    if (uiState.roiEditMode) {
                        var editPoint = root.imagePoint(mouse.x, mouse.y)
                        root.draggingVertex = fileBridge.beginRoiDrag(editPoint.x * uiState.contentWidth, editPoint.y * uiState.contentHeight, 8 / root.displayScale)
                        return
                    }
                    if (uiState.activeTool === "Defect3D") {
                        var point=root.reviewPoint(mouse.x,mouse.y)
                        if(fileBridge.defect3d.startVisual(point.x,point.y)){uiState.activeTool="Pan";uiState.workspaceIndex=3}
                        return
                    }
                    if (uiState.activeTool === "Zoom") {
                        var click = mapToItem(viewport, mouse.x, mouse.y)
                        root.zoomAt(uiState.effectiveZoom * ((mouse.modifiers & Qt.AltModifier) ? 1 / 1.25 : 1.25), click.x, click.y)
                        root.updateCursor(click.x, click.y)
                        return
                    }
                    if (["Pan", "ROI"].indexOf(uiState.activeTool) < 0) {
                        if (!uiState.loadFlow.imagejReady) { uiState.statusText = "현재 페이지 준비 후 ImageJ 도구를 사용하세요."; return }
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
                    if (uiState.projectReview.editing && uiState.projectReview.tool !== "pan") {
                        if (pressed) { var rp=root.reviewPoint(mouse.x,mouse.y);fileBridge.reviews.drag(rp.x,rp.y) }
                        return
                    }
                    if (root.reviewGesture) return
                    root.updateCursor(mouse.x, mouse.y)
                    var p = root.imagePoint(mouse.x, mouse.y)
                    if (!pressed || (uiState.analysisRunning && uiState.activeTool === "ROI" && !uiState.roiEditMode)) return
                    if (root.drawingTool) {
                        var t = root.toolPoint(mouse)
                        if (["Rectangle", "Oval", "Line", "Arrow"].indexOf(uiState.activeTool) >= 0) root.toolPoints = [root.toolPoints[0], t]
                        else if (root.toolPoints.length < 10000) root.toolPoints = root.toolPoints.concat([t])
                        toolPreview.requestPaint(); return
                    }
                    if (["Pan", "ROI"].indexOf(uiState.activeTool) < 0 && !uiState.roiEditMode) return
                    if (uiState.roiEditMode) {
                        if (root.draggingVertex) fileBridge.dragRoiVertex(p.x * uiState.contentWidth, p.y * uiState.contentHeight)
                        else { root.panX = root.pressPanX + mouse.x - root.pressX; root.panY = root.pressPanY + mouse.y - root.pressY; root.updateCursor(mouse.x, mouse.y) }
                        return
                    }
                    if (uiState.activeTool === "Pan") {
                        root.panX = root.pressPanX + mouse.x - root.pressX
                        root.panY = root.pressPanY + mouse.y - root.pressY
                        root.updateCursor(mouse.x, mouse.y)
                    } else {
                        uiState.roiEndX = p.x; uiState.roiEndY = p.y
                        uiState.hasRoi = uiState.roiWidth > 0 && uiState.roiHeight > 0
                    }
                }
                onExited: { uiState.cursorX = -1; uiState.cursorY = -1 }
                onDoubleClicked: function(mouse) {
                    if (uiState.projectReview.editing) return
                    if (["Polygon", "Polyline"].indexOf(uiState.activeTool) >= 0) { root.finishTool(); return }
                    if (uiState.roiEditMode) {
                        var p = root.imagePoint(mouse.x, mouse.y)
                        fileBridge.finishRoiDrag(true); root.draggingVertex = false
                        fileBridge.addRoiVertex(p.x * uiState.contentWidth, p.y * uiState.contentHeight)
                    }
                }
                onReleased: function(mouse) {
                    if (uiState.projectReview.editing) { fileBridge.reviews.release(false); return }
                    if (root.reviewGesture) { root.reviewGesture = false; return }
                    if (uiState.feedbackVisible && uiState.activeTool === "Pan" && Math.hypot(mouse.x-root.pressX, mouse.y-root.pressY) < 4) {
                        var reviewPoints = uiState.feedback.rows, nearest = null, radius = 12
                        for (var ri=0; ri<reviewPoints.length; ri++) {
                            var rp=reviewPoints[ri], rd=Math.hypot(mouse.x-imageFrame.x-rp.x*root.displayScale, mouse.y-imageFrame.y-rp.y*root.displayScale)
                            if (rd < radius) { nearest=rp; radius=rd }
                        }
                        if (nearest) { fileBridge.feedback.selectRecord(nearest.id); return }
                    }
                    if (uiState.activeTool === "Pan" && !uiState.roiEditMode && Math.hypot(mouse.x-root.pressX, mouse.y-root.pressY) < 4) {
                        if (geometryOverlay.visible) {
                            var hit = geometryOverlay.hit((mouse.x-imageFrame.x)/root.displayScale, (mouse.y-imageFrame.y)/root.displayScale, 8/root.displayScale)
                            if (hit) { fileBridge.experiments.select(hit); return }
                        }
                        if (!uiState.hasResult || !uiState.analysisLayerVisible) return
                        var points = uiState.research.points, best = null, distance = root.displayScale<.15 && uiState.research.points.length>500 ? 28 : 12
                        for (var i=0; i<points.length; i++) {
                            var p=points[i]; if (!uiState.candidateLayer(p.type)) continue
                            var d=Math.hypot(mouse.x-imageFrame.x-p.x*root.displayScale, mouse.y-imageFrame.y-p.y*root.displayScale)
                            if (d < distance) { best=p; distance=d }
                        }
                        if (best) fileBridge.research.selectCandidate(best.id)
                    }
                    if (root.drawingTool) root.finishTool(); uiState.selectingRoi = false; if (root.draggingVertex) fileBridge.finishRoiDrag(false); root.draggingVertex = false
                }
                onCanceled: { if (uiState.projectReview.editing) fileBridge.reviews.release(true); root.reviewGesture = false; root.toolPoints = []; root.drawingTool = false; toolPreview.requestPaint(); uiState.selectingRoi = false; if (root.draggingVertex) fileBridge.finishRoiDrag(true); root.draggingVertex = false }
                onWheel: function(wheel) {
                    var delta = wheel.angleDelta.y || wheel.pixelDelta.y
                    if (delta === 0) return
                    if (uiState.hasLoadedImage && uiState.pageCount > 1 && !(wheel.modifiers & Qt.ControlModifier)) root.stepPage(delta < 0 ? 1 : -1)
                    else {
                        var anchor = mapToItem(viewport, wheel.x, wheel.y)
                        root.zoomAt(uiState.effectiveZoom * (delta > 0 ? 1.25 : 1 / 1.25), anchor.x, anchor.y)
                        root.updateCursor(anchor.x, anchor.y)
                    }
                    wheel.accepted = true
                }
            }
            ReviewGeometryOverlay {
                anchors.fill: parent; z: 5; review: uiState.projectReview
                imageX: imageFrame.x; imageY: imageFrame.y; imageScale: root.displayScale
            }
            ImportedRoiOverlay {
                z: 3
                anchors.fill: parent
                rois: uiState.importedRois.items
                imageX: imageFrame.x; imageY: imageFrame.y; imageScale: root.displayScale
                layerVisible: uiState.roiLayerVisible && uiState.imagejRoiLayerVisible && uiState.hasLoadedImage
                editMode: uiState.roiEditMode; selectedVertex: uiState.importedRois.vertex
            }
            Canvas {
                id:annotationLayers; objectName:"annotationLayers"; anchors.fill:parent; z:2
                property var rows:fileBridge.displayLayers.rows
                property var position:[imageFrame.x,imageFrame.y,root.displayScale]
                onRowsChanged:requestPaint();onPositionChanged:requestPaint()
                visible:uiState.hasLoadedImage
                onPaint:{var c=getContext("2d");c.reset();c.lineWidth=2;for(var i=0;i<rows.length;i++){var r=rows[i];if(!r.visible)continue;c.strokeStyle="#69dfcf";if(r.paths){c.beginPath();for(var j=0;j<r.paths.length;j++){var path=r.paths[j];for(var k=0;k<path.length;k++){var x=imageFrame.x+path[k][0]*root.displayScale,y=imageFrame.y+path[k][1]*root.displayScale;if(r.kind==="point"){c.moveTo(x-4,y);c.lineTo(x+4,y);c.moveTo(x,y-4);c.lineTo(x,y+4)}else if(k===0)c.moveTo(x,y);else c.lineTo(x,y)}if(r.kind==="polygon")c.closePath()}c.stroke()}else c.strokeRect(imageFrame.x+r.x*root.displayScale,imageFrame.y+r.y*root.displayScale,r.width*root.displayScale,r.height*root.displayScale);c.fillStyle=c.strokeStyle;c.font="12px sans-serif";c.fillText(r.name,imageFrame.x+r.x*root.displayScale+5,imageFrame.y+r.y*root.displayScale+16)}}
            }
            Canvas {
                id:analysisScan; anchors.fill:parent; z:2; visible:uiState.analysisRunning
                property var scan:uiState.analysis.progress
                property var position:[imageFrame.x,imageFrame.y,root.displayScale]
                onScanChanged:requestPaint();onPositionChanged:requestPaint();onVisibleChanged:requestPaint()
                onPaint:{var c=getContext("2d");c.reset();var r=scan.region||[];if(!visible||r.length!==4)return;c.fillStyle="#2949ced6";c.strokeStyle="#49ced6";c.lineWidth=2;c.fillRect(imageFrame.x+r[0]*root.displayScale,imageFrame.y+r[1]*root.displayScale,r[2]*root.displayScale,r[3]*root.displayScale);c.strokeRect(imageFrame.x+r[0]*root.displayScale,imageFrame.y+r[1]*root.displayScale,r[2]*root.displayScale,r[3]*root.displayScale)}
            }
            Rectangle {
                anchors.horizontalCenter:parent.horizontalCenter; anchors.top:parent.top; anchors.topMargin:16;z:8;visible:uiState.analysisRunning
                color:theme.panel;radius:8;width:330;height:72
                ColumnLayout{anchors.fill:parent;anchors.margins:10
                    RowLayout{Text{text:uiState.analysis.progress.stage||"분석 중";color:theme.text;Layout.fillWidth:true}Text{text:(uiState.research.livePoints||[]).length+"개";color:theme.accent}AppButton{theme:root.theme;text:"취소";onClicked:fileBridge.cancelAnalysis()}}
                    ProgressBar{Layout.fillWidth:true;from:0;to:Math.max(1,uiState.analysis.progress.total||1);value:uiState.analysis.progress.completed||0;indeterminate:!(uiState.analysis.progress.total>0)}
                }
            }
            Canvas {
                id: analysisOverlay; objectName: "analysisOverlay"; anchors.fill: parent; z: 3
                property var points: uiState.analysisRunning ? uiState.research.livePoints || [] : uiState.research.points
                property var selected: uiState.research.selected
                property bool reviewing: uiState.feedbackVisible
                property real paintMs: 0
                property int paintCount: 0
                readonly property real candidateOpacity: uiState.resultOverlayOpacity
                onCandidateOpacityChanged: requestPaint()
                readonly property real markerRadius: Math.max(6, Math.min(12, 6 + Math.log(Math.max(1,imageScale))/Math.LN2*2))
                property var layers: [uiState.bpdLayerVisible, uiState.tedLayerVisible, uiState.tsdLayerVisible, uiState.selectedLayerVisible]
                onLayersChanged: requestPaint()
                readonly property real selectedOpacity: 1
                property real imageX: imageFrame.x
                property real imageY: imageFrame.y
                property real imageScale: root.displayScale
                visible: (uiState.hasResult || uiState.analysisRunning) && (!uiState.hasResult || uiState.resultViewMode!=="image") && (uiState.analysisLayerVisible || (uiState.selectedLayerVisible && !!selected.id)) && uiState.hasLoadedImage
                onPointsChanged: requestPaint()
                onSelectedChanged: requestPaint()
                onReviewingChanged: requestPaint()
                onImageXChanged: requestPaint()
                onImageYChanged: requestPaint()
                onImageScaleChanged: requestPaint()
                onVisibleChanged: requestPaint()
                function outline(c, region) {
                    c.beginPath()
                    c.moveTo(imageX+region[0][0]*imageScale, imageY+region[0][1]*imageScale)
                    for (var j=1;j<region.length;j++) c.lineTo(imageX+region[j][0]*imageScale,imageY+region[j][1]*imageScale)
                    c.closePath(); c.stroke()
                }
                onPaint: {
                    var started=Date.now(), c=getContext("2d"); c.reset()
                    if (!visible) return
                    var overviewMode=imageScale<.25
                    for (var i=0;uiState.analysisLayerVisible && i<points.length;i++) {
                        var p=points[i]
                        if (!uiState.candidateLayer(p.type)) continue
                        var x=imageX+p.x*imageScale, y=imageY+p.y*imageScale
                        // Long BPD contours can enter the viewport while their
                        // classified anchor lies outside it; clip via Canvas.
                        var hasRegion=p.type==="BPD" && p.region && p.region.length>=3
                        if (!hasRegion && (x<0 || y<0 || x>width || y>height)) continue
                        c.strokeStyle=uiState.resultPresentation.colorFor(p.type)
                        c.fillStyle=c.strokeStyle; c.globalAlpha=candidateOpacity
                        c.lineWidth=overviewMode?1.6:2
                        if (hasRegion) {
                            outline(c,p.region)
                        } else if (p.type==="BPD") {
                            // A missing region is a location proposal, never a
                            // fabricated circular segmentation boundary.
                            c.beginPath(); c.moveTo(x-3,y); c.lineTo(x+3,y)
                            c.moveTo(x,y-3); c.lineTo(x,y+3); c.stroke()
                        } else {
                            c.beginPath(); c.arc(x,y,overviewMode?2.5:4.5,0,Math.PI*2)
                            if (overviewMode) c.fill(); else c.stroke()
                        }
                    }
                    if (selected.id && uiState.selectedLayerVisible && !reviewing) {
                        var sx=imageX+selected.x*imageScale, sy=imageY+selected.y*imageScale
                        c.globalAlpha=selectedOpacity; c.strokeStyle="#fff04a"; c.lineWidth=2
                        if (selected.type==="BPD" && selected.region && selected.region.length>=3) outline(c,selected.region)
                        c.beginPath(); c.moveTo(sx-12,sy); c.lineTo(sx-5,sy); c.moveTo(sx+5,sy); c.lineTo(sx+12,sy)
                        c.moveTo(sx,sy-12); c.lineTo(sx,sy-5); c.moveTo(sx,sy+5); c.lineTo(sx,sy+12); c.stroke()
                        var lx=Math.max(0,Math.min(width-110,sx+15)), ly=Math.max(0,Math.min(height-22,sy-28))
                        c.fillStyle="#14191e"; c.fillRect(lx,ly,110,22)
                        c.fillStyle="#fff04a"; c.font="12px sans-serif"; c.fillText("#"+selected.number+"  "+selected.type,lx+5,ly+15)
                    }
                    paintMs=Date.now()-started; paintCount+=1
                }
            }
            GeometryOverlay {
                id: geometryOverlay; objectName: "geometryOverlay"; anchors.fill: parent; z: 3
                controller: fileBridge.experiments
                rows: uiState.experiment.rows
                selectedId: uiState.experiment.selected.id || ""
                viewTransform: [imageFrame.x, imageFrame.y, root.displayScale]
                visible: uiState.hasLoadedImage && uiState.structureLayerVisible && uiState.experiment.total > 0
                maskMode: uiState.maskMode; lines: uiState.structureLinesVisible
                highlight: uiState.selectedLayerVisible; lineWidth: uiState.structureLineWidth
            }
            Text {
                anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 12; z: 5
                visible: geometryOverlay.visible
                text: uiState.experiment.status + (geometryOverlay.stats.maskError ? " · Mask 읽기 오류" : uiState.maskMode !== "off" && geometryOverlay.stats.maskLimited > 0 ? " · Mask 일부 표시 (캐시 제한)" : "")
                color: "#d3bef8"; font.pixelSize: 11; style: Text.Outline; styleColor: "#111518"
            }
            Canvas {
                id: feedbackOverlay; objectName: "feedbackOverlay"; anchors.fill: parent; z: 4
                property var review: uiState.feedback
                property real imageX: imageFrame.x
                property real imageY: imageFrame.y
                property real imageScale: root.displayScale
                visible: uiState.feedbackVisible && uiState.hasLoadedImage
                onReviewChanged: requestPaint()
                onImageXChanged: requestPaint()
                onImageYChanged: requestPaint()
                onImageScaleChanged: requestPaint()
                onVisibleChanged: requestPaint()
                onPaint: {
                    var c=getContext("2d"); c.reset()
                    if (!visible) return
                    c.lineWidth=2
                    var rows=review.overlay || []
                    for (var i=0;i<rows.length;i++) {
                        var p=rows[i], x=imageX+p.x*imageScale, y=imageY+p.y*imageScale
                        if (x < -20 || y < -20 || x > width+20 || y > height+20) continue
                        c.strokeStyle=p.objectness === false ? "#ff6578" : p.objectness === true ? "#80edac" : "#a3a9af"
                        c.beginPath(); c.arc(x,y,8,0,Math.PI*2); c.stroke()
                        if (p.objectness === false || p.duplicate) {
                            c.beginPath(); c.moveTo(x-6,y-6); c.lineTo(x+6,y+6); c.moveTo(x-6,y+6); c.lineTo(x+6,y-6); c.stroke()
                        }
                    }
                    var selected=review.selected || ({})
                    if (selected.id) {
                        var sx=imageX+selected.x*imageScale, sy=imageY+selected.y*imageScale
                        var ox=imageX+selected.original.x*imageScale, oy=imageY+selected.original.y*imageScale
                        c.strokeStyle="#ffffff"; c.lineWidth=1
                        c.beginPath(); c.arc(ox,oy,5,0,Math.PI*2); c.moveTo(ox,oy); c.lineTo(sx,sy); c.stroke()
                        c.strokeStyle="#fff04a"; c.lineWidth=2
                        c.beginPath(); c.moveTo(sx-18,sy); c.lineTo(sx+18,sy); c.moveTo(sx,sy-18); c.lineTo(sx,sy+18); c.stroke()
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
                anchors.centerIn: parent; spacing: theme.spacingMd
                visible: !uiState.hasImage && uiState.loadFlow.phase === "EMPTY"
                Text { text: "XRT 이미지 없음"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: theme.emptyTitleSize }
                Text { text: "TIFF / JPG · 16-bit TIFF 및 RGB 지원"; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: theme.bodySize }
                AppButton { theme: root.theme; action: root.actions.open; text: "XRT 이미지 열기"; iconName: "open"; Layout.alignment: Qt.AlignHCenter }
                Text { text: "또는 TIFF/JPG 파일을 이 영역에 놓으세요"; color: theme.muted; font.pixelSize: theme.smallSize; Layout.alignment: Qt.AlignHCenter }
            }
            StackPreparationOverlay {
                anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 16; z: 8
                theme: root.theme; loadFlow: uiState.loadFlow; closeAction: root.actions.closeImage
            }
            Rectangle {
                objectName: "initialLoadingOverlay"
                z: 10
                anchors.fill: parent; visible: uiState.loadFlow.blocking && (!uiState.loadFlow.isOpening || uiState.loadFlow.indicatorElapsed); color: "#db111518"
                ColumnLayout { anchors.centerIn: parent; width: Math.min(380, parent.width - 40); spacing: theme.spacingMd
                    BusyIndicator { visible: uiState.loadFlow.isOpening; running: visible && parent.parent.visible; Layout.alignment: Qt.AlignHCenter }
                    Text {
                        objectName: "initialLoadingText"; Layout.fillWidth: true; wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter; color: uiState.loadFlow.hasError ? theme.error : theme.text
                        text: uiState.loadFlow.message; Accessible.name: text
                    }
                    Text { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; color: theme.muted; text: uiState.loadFlow.isOpening ? uiState.loadFlow.openingHint : "다른 파일을 열거나 오류 상세를 확인하세요." }
                    RowLayout { Layout.alignment: Qt.AlignHCenter
                        AppButton { theme: root.theme; action: root.actions.open; text: "다시 열기…"; visible: uiState.loadFlow.hasError }
                        AppButton { objectName: "openingErrorDetails"; theme: root.theme; text: "상세 정보…"; visible: uiState.loadFlow.hasError; onClicked: loadErrorDialog.open() }
                        AppButton { objectName: "cancelInitialLoading"; theme: root.theme; text: "취소·닫기"; visible: uiState.loadFlow.isOpening; onClicked: root.actions.closeImage.trigger() }
                    }
                }
            }
            DropArea { anchors.fill: parent; onDropped: function(drop) { if (drop.hasUrls && drop.urls.length > 0) root.fileDropped(drop.urls[0].toString()) } }
            OverviewMap {
                width: Math.min(190, Math.max(140, viewport.width * .23))
                height: width * 160 / 190
                coverage:root.uiState.regionReview.coverage
                z: 7; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 12
                visible: uiState.hasLoadedImage && !uiState.loading && viewport.width > 300 && (!uiState.hasResult || uiState.resultViewMode!=="distribution")
                theme: root.theme; imageSource: uiState.imageSource
                imageWidth: uiState.contentWidth; imageHeight: uiState.contentHeight
                viewRect: [-imageFrame.x/Math.max(.0001,root.displayScale),-imageFrame.y/Math.max(.0001,root.displayScale),viewport.width/Math.max(.0001,root.displayScale),viewport.height/Math.max(.0001,root.displayScale)]
                selectedPoint: uiState.research.selected.id ? [uiState.research.selected.x,uiState.research.selected.y] : []
                onNavigate: function(x,y) { focusAnimation.stop(); root.panX=(uiState.contentWidth/2-x)*root.displayScale; root.panY=(uiState.contentHeight/2-y)*root.displayScale }
            }
            AppButton { z: 7; anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 12; theme: root.theme; text: "이전 확대 위치"; visible: root.previousView.length===3; onClicked:root.restoreView() }
            Rectangle {
                visible: uiState.pageLoading; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12
                width: Math.min(parent.width - 24, 320); height: 30; color: theme.panel; border.color: theme.border; radius: theme.radiusSm
                Text { objectName: "pageRequestStatus"; anchors.centerIn: parent; text: uiState.loadFlow.pageRequestLabel; color: theme.text; font.pixelSize: theme.smallSize; Accessible.name: text }
            }
            Rectangle {
                visible: uiState.detail.busy || uiState.detail.error.length > 0
                anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12
                width: Math.min(parent.width - 24, 280); height: detailText.implicitHeight + 16
                color: theme.panel; border.color: theme.border; radius: theme.radiusSm
                Text { id: detailText; anchors.fill: parent; anchors.margins: 8; text: uiState.detail.error ? "정밀 영역 읽기 실패: " + uiState.detail.error : "정밀 영역 읽는 중…"; color: uiState.detail.error ? theme.warning : theme.muted; wrapMode: Text.Wrap; font.pixelSize: theme.smallSize }
            }
        }
        ResultCandidateShelf {
            Layout.fillWidth: true; Layout.preferredHeight: implicitHeight; Layout.margins: 10
            visible: uiState.hasResult && (uiState.resultViewMode==="area" || uiState.resultViewMode==="compare") && !uiState.projectReview.editing
            theme: root.theme; uiState: root.uiState
            onCandidateRequested: function(ident) { fileBridge.research.selectCandidate(ident) }
        }
        Rectangle {
            objectName: "loadingErrorNotice"; visible: uiState.loadFlow.hasError && uiState.loadFlow.hasViewableFrame
            Layout.fillWidth: true; Layout.preferredHeight: errorNotice.implicitHeight + 12
            color: "#332427"
            RowLayout {
                id: errorNotice; anchors.fill: parent; anchors.margins: 6
                Text { text: uiState.loadFlow.message; color: theme.error; font.pixelSize: theme.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
                AppButton { objectName: "retryPreparationNotice"; theme: root.theme; text: "다시 준비"; visible: !!uiState.stack.preloadError; onClicked: fileBridge.retryPreload() }
                AppButton { theme: root.theme; action: root.actions.open; text: "다시 열기…"; visible: !uiState.stack.preloadError }
                AppButton { objectName: "loadingErrorDetails"; theme: root.theme; text: "상세 정보…"; onClicked: loadErrorDialog.open() }
            }
        }
    }
    SurfaceDialog {
        id: loadErrorDialog; objectName: "loadingErrorDialog"; parent: Overlay.overlay; title: "이미지 준비 오류 상세"
        modal: true; width: Math.min(600, parent.width - 40); height: Math.min(420, parent.height - 60)
        x: (parent.width - width)/2; y: (parent.height - height)/2; standardButtons: Dialog.Close
        onClosed: Qt.callLater(root.focusView)
        contentItem: ScrollView {
            id: loadErrorScroll; clip: true; contentWidth: availableWidth
            TextArea { objectName: "loadingErrorText"; width: loadErrorScroll.availableWidth; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; text: uiState.loadFlow.errorDetails }
        }
    }
}
