import QtQuick

Canvas {
    id: root
    objectName: "importedRoiOverlay"
    property var rois: []
    property real imageX: 0
    property real imageY: 0
    property real imageScale: 1
    property bool layerVisible: true
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
        }
    }
}
