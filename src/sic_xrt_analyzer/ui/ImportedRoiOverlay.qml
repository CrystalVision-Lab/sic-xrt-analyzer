import QtQuick

Canvas {
    id: root
    objectName: "importedRoiOverlay"
    property var rois: []
    property real imageX: 0
    property real imageY: 0
    property real imageScale: 1
    property bool layerVisible: true
    property bool editMode: false
    property int selectedVertex: -1
    onEditModeChanged: requestPaint()
    onSelectedVertexChanged: requestPaint()
    onRoisChanged: requestPaint()
    onImageXChanged: requestPaint()
    onImageYChanged: requestPaint()
    onImageScaleChanged: requestPaint()
    onLayerVisibleChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        var c = getContext("2d")
        c.reset()
        if (!layerVisible || imageScale <= 0) return
        c.translate(imageX, imageY)
        c.scale(imageScale, imageScale)
        c.lineCap = "round"; c.lineJoin = "round"
        for (var i = 0; i < rois.length; ++i) {
            var roi = rois[i]
            if (!roi.visible || !roi.active) continue
            c.strokeStyle = roi.color
            c.lineWidth = (roi.selected ? 2 : 1.2) / imageScale
            var radius = (roi.selected ? 3.5 : 2.5) / imageScale
            c.beginPath()
            for (var j = 0; j < roi.paths.length; ++j) {
                var path = roi.paths[j]
                for (var k = 0; k < path.length; ++k) {
                    var x = path[k][0], y = path[k][1]
                    if (roi.kind === "point") {
                        c.moveTo(x - radius, y); c.lineTo(x + radius, y)
                        c.moveTo(x, y - radius); c.lineTo(x, y + radius)
                    } else if (k === 0) c.moveTo(x, y)
                    else c.lineTo(x, y)
                }
                if (roi.kind === "polygon") c.closePath()
            }
            c.stroke()
            if (roi.tool === "Text") {
                c.fillStyle = roi.color; c.font = roi.strokeWidth + "px sans-serif"
                c.fillText(roi.text, roi.bbox[0], roi.bbox[1] + roi.strokeWidth)
            }
            if (roi.tool === "Arrow") {
                var a = roi.paths[0][0], b = roi.paths[0][roi.paths[0].length - 1]
                var angle = Math.atan2(b[1] - a[1], b[0] - a[0]), len = 12 / imageScale
                c.beginPath(); c.moveTo(b[0] - len * Math.cos(angle - 0.5), b[1] - len * Math.sin(angle - 0.5))
                c.lineTo(b[0], b[1]); c.lineTo(b[0] - len * Math.cos(angle + 0.5), b[1] - len * Math.sin(angle + 0.5)); c.stroke()
            }
            if (editMode && roi.selected) {
                var handle = 4 / imageScale
                for (var v = 0; v < roi.paths[0].length; ++v) {
                    var point = roi.paths[0][v]
                    c.fillStyle = v === selectedVertex ? "#ffffff" : roi.color
                    c.fillRect(point[0] - handle, point[1] - handle, handle * 2, handle * 2)
                }
            }
        }
    }
}
