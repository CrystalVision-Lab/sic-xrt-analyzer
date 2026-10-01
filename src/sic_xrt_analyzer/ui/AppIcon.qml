import QtQuick
Canvas {
    id: root
    property string name: ""
    property color ink: "#929da6"
    implicitWidth: 16; implicitHeight: 16
    onNameChanged: requestPaint()
    onInkChanged: requestPaint()
    onPaint: {
        const c = getContext("2d")
        c.reset(); c.strokeStyle = ink; c.lineWidth = 1.4; c.lineJoin = "round"; c.lineCap = "round"
        function line(x,y,a,b) { c.moveTo(x,y); c.lineTo(a,b) }
        c.beginPath()
        if (name === "open") { c.moveTo(2,13); c.lineTo(2,4); c.lineTo(6,4); c.lineTo(8,6); c.lineTo(14,6); c.lineTo(12,13); c.closePath() }
        else if (name === "save") { c.rect(2,2,12,12); c.rect(5,2,6,4); c.rect(5,9,6,5) }
        else if (name === "roi") { c.rect(3,3,10,10); line(1,5,1,1); line(1,1,5,1); line(11,15,15,15); line(15,15,15,11) }
        else if (name === "pan") { line(8,1,8,15); line(1,8,15,8); line(5,4,8,1); line(11,4,8,1); line(5,12,8,15); line(11,12,8,15); line(4,5,1,8); line(4,11,1,8); line(12,5,15,8); line(12,11,15,8) }
        else if (name === "plus" || name === "minus") { line(3,8,13,8); if(name === "plus") line(8,3,8,13) }
        else if (name === "fit") { line(1,5,1,1); line(1,1,5,1); line(11,1,15,1); line(15,1,15,5); line(1,11,1,15); line(1,15,5,15); line(11,15,15,15); line(15,15,15,11) }
        else if (name === "wafer") { c.arc(8,8,6,0,Math.PI*2); line(2,8,14,8); line(8,2,8,14) }
        else if (name === "align") { line(2,5,14,5); line(11,2,14,5); line(11,8,14,5); line(14,11,2,11); line(5,8,2,11); line(5,14,2,11) }
        else if (name === "cube") { c.moveTo(8,1); c.lineTo(14,4); c.lineTo(14,12); c.lineTo(8,15); c.lineTo(2,12); c.lineTo(2,4); c.closePath(); line(2,4,8,7); line(14,4,8,7); line(8,7,8,15) }
        else if (name === "run") { c.moveTo(4,2); c.lineTo(13,8); c.lineTo(4,14); c.closePath() }
        else if (name === "settings") { c.arc(8,8,3,0,Math.PI*2); for(let i=0;i<8;i++){ const a=i*Math.PI/4; line(8+Math.cos(a)*5,8+Math.sin(a)*5,8+Math.cos(a)*7,8+Math.sin(a)*7) } }
        else if (name === "export") { c.rect(2,8,12,6); line(8,11,8,1); line(5,4,8,1); line(11,4,8,1) }
        else { c.rect(2,2,12,12); line(4,11,7,8); line(7,8,10,11); line(10,11,13,6) }
        c.stroke()
    }
}
