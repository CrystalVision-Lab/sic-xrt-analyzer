import QtQuick
Canvas {
    id: root
    objectName: "reviewGeometryOverlay"
    property var review
    property real imageX
    property real imageY
    property real imageScale: 1
    visible: review.mode !== "EXPLORE" && review.ready
    onReviewChanged: requestPaint()
    onImageXChanged: requestPaint()
    onImageYChanged: requestPaint()
    onImageScaleChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onVisibleChanged: requestPaint()
    function drawShape(ctx,g,color,dash,marker) {
        if (!g || !g.kind) return
        ctx.strokeStyle=color; ctx.fillStyle=color; ctx.lineWidth=2; ctx.setLineDash(dash)
        function path(points,closed) {
            if (!points || !points.length) return
            ctx.beginPath(); ctx.moveTo(imageX+points[0][0]*imageScale,imageY+points[0][1]*imageScale)
            for (var i=1;i<points.length;i++) ctx.lineTo(imageX+points[i][0]*imageScale,imageY+points[i][1]*imageScale)
            if (closed) ctx.closePath()
            ctx.stroke()
        }
        function mark(x,y) {
            x=imageX+x*imageScale; y=imageY+y*imageScale; ctx.setLineDash([]);ctx.beginPath()
            if (marker==="square") ctx.rect(x-4,y-4,8,8)
            else if (marker==="diamond") {ctx.moveTo(x,y-5);ctx.lineTo(x+5,y);ctx.lineTo(x,y+5);ctx.lineTo(x-5,y);ctx.closePath()}
            else ctx.arc(x,y,4,0,Math.PI*2)
            ctx.stroke();ctx.setLineDash(dash)
        }
        if (g.kind==="BRANCHED_GRAPH") {
            var nodes={};(g.nodes || []).forEach(function(n){nodes[n.node_id]=n})
            ;(g.edges || []).forEach(function(e){var a=nodes[e.start_node],b=nodes[e.end_node];if(a&&b)path(e.points && e.points.length ? e.points : [[a.x,a.y],[b.x,b.y]],false)})
            ;(g.nodes || []).forEach(function(n,i){mark(n.x,n.y);if(marker==="square"){ctx.font="11px sans-serif";ctx.fillText("N"+(i+1),imageX+n.x*imageScale+7,imageY+n.y*imageScale-7)}})
        } else if (g.kind==="MASK_REFERENCE" || g.kind==="BOUNDING_BOX") {
            if(g.bbox){var b=g.bbox;path([[b[0],b[1]],[b[0]+b[2],b[1]],[b[0]+b[2],b[1]+b[3]],[b[0],b[1]+b[3]]],true)}
        } else {
            path(g.points,g.kind==="POLYGON");(g.points || []).forEach(function(p){mark(p[0],p[1])})
        }
    }
    onPaint: {
        var ctx=getContext("2d");ctx.reset();ctx.clearRect(0,0,width,height)
        if(!visible || imageScale<=0)return
        if(review.compare!=="CORRECTED")drawShape(ctx,review.original,"#53c8ff",[5,4],"diamond")
        if(review.compare!=="ORIGINAL") (review.corrected || []).forEach(function(g){root.drawShape(ctx,g,"#ffdd52",[],"circle")})
        if(review.editing){drawShape(ctx,review.draft,"#ff68bc",[],"square");(review.handles || []).forEach(function(h){if(h.key===review.vertex){ctx.fillStyle="#ffffff";ctx.fillRect(imageX+h.x*imageScale-3,imageY+h.y*imageScale-3,6,6)}})}
    }
}
