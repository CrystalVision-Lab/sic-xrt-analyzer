import QtQuick
Canvas {
    property string tool: "Rectangle"
    property color ink: "#e4e8eb"
    onToolChanged: requestPaint()
    onInkChanged: requestPaint()
    onPaint: {
        var c = getContext("2d"); c.reset(); c.translate(width/2 - 10, height/2 - 10)
        c.strokeStyle = ink; c.fillStyle = ink; c.lineWidth = 1.4; c.lineJoin = "round"; c.lineCap = "round"
        c.beginPath()
        if (tool === "Rectangle") c.rect(2,4,16,12)
        else if (tool === "Oval") c.ellipse(2,3,16,14)
        else if (tool === "Polygon") { c.moveTo(2,16); c.lineTo(4,4); c.lineTo(16,2); c.lineTo(18,13); c.closePath() }
        else if (tool === "Freehand" || tool === "FreeLine" || tool === "Brush") { c.moveTo(2,14); c.bezierCurveTo(0,0,12,2,10,10); c.bezierCurveTo(7,20,20,18,18,4); if (tool === "Freehand") c.closePath(); if (tool === "Brush") c.lineWidth = 3 }
        else if (tool === "Line" || tool === "Arrow") { c.moveTo(2,17); c.lineTo(17,3); if (tool === "Arrow") { c.moveTo(9,4); c.lineTo(17,3); c.lineTo(16,11) } }
        else if (tool === "Polyline" || tool === "Angle") { c.moveTo(2,15); c.lineTo(9,4); c.lineTo(17,14); if (tool === "Polyline") c.lineTo(19,3) }
        else if (tool === "Point") { c.moveTo(1,10); c.lineTo(19,10); c.moveTo(10,1); c.lineTo(10,19); c.fillRect(13,2,3,3) }
        else if (tool === "Wand") { c.moveTo(2,18); c.lineTo(13,7); c.moveTo(13,1); c.lineTo(13,5); c.moveTo(16,6); c.lineTo(20,6); c.moveTo(5,3); c.lineTo(8,6) }
        else if (tool === "Text") { c.font = "bold 20px sans-serif"; c.fillText("A",3,18) }
        else if (tool === "Zoom") { c.ellipse(2,2,11,11); c.moveTo(12,12); c.lineTo(19,19); c.moveTo(5,7); c.lineTo(10,7); c.moveTo(7,5); c.lineTo(7,10) }
        else if (tool === "Pan") { c.moveTo(5,17); c.lineTo(2,10); c.lineTo(5,9); c.lineTo(7,12); c.lineTo(7,3); c.lineTo(10,3); c.lineTo(10,10); c.lineTo(12,2); c.lineTo(14,2); c.lineTo(14,11); c.lineTo(17,6); c.lineTo(19,7); c.lineTo(17,17); c.closePath() }
        else if (tool === "Picker") { c.moveTo(4,16); c.lineTo(12,5); c.lineTo(16,8); c.lineTo(7,18); c.closePath(); c.moveTo(12,3); c.lineTo(19,9) }
        else if (tool === "Fill") { c.moveTo(2,9); c.lineTo(9,2); c.lineTo(17,10); c.lineTo(10,17); c.closePath(); c.moveTo(16,10); c.lineTo(19,17) }
        c.stroke()
    }
}
