import QtQuick

Item {
    id: root
    objectName: "resultDensityOverlay"
    required property QtObject theme
    required property QtObject uiState
    property real imageX: 0
    property real imageY: 0
    property real imageScale: 1
    readonly property var navigator: fileBridge.research.regions
    readonly property var cells: navigator.state.mapCells || []
    property string hoveredLabel: ""
    Canvas {
        id: density; anchors.fill: parent
        onPaint: {
            var c = getContext("2d"); c.reset()
            if (!root.visible || root.imageScale <= 0) return
            var maxCount = 1, cells = root.cells
            for (var i = 0; i < cells.length; i++) maxCount = Math.max(maxCount, cells[i].count)
            for (var j = 0; j < cells.length; j++) {
                var cell = cells[j], r = cell.rect
                if (!cell.count) continue
                var x = root.imageX + r[0]*root.imageScale, y = root.imageY + r[1]*root.imageScale
                var w = r[2]*root.imageScale, h = r[3]*root.imageScale
                if (x+w<0 || y+h<0 || x>width || y>height) continue
                // Equal-area cells: density of current filtered proposals, not severity.
                c.fillStyle = "#dfc78d"
                c.globalAlpha = .08 + .47*Math.sqrt(cell.count/maxCount)
                c.fillRect(x, y, w, h)
                if (cell.id === root.navigator.state.current) {
                    c.globalAlpha = 1; c.strokeStyle = root.theme.accent; c.lineWidth = 2
                    c.strokeRect(x+1, y+1, Math.max(0,w-2), Math.max(0,h-2))
                }
            }
        }
    }
    onCellsChanged: density.requestPaint()
    onImageXChanged: density.requestPaint()
    onImageYChanged: density.requestPaint()
    onImageScaleChanged: density.requestPaint()
    onVisibleChanged: density.requestPaint()
    function cellAt(x, y) {
        var sx = (x-imageX)/imageScale, sy = (y-imageY)/imageScale
        for (var i=0; i<cells.length; i++) {
            var r=cells[i].rect
            if (sx>=r[0] && sy>=r[1] && sx<r[0]+r[2] && sy<r[1]+r[3]) return cells[i]
        }
        return null
    }
    MouseArea {
        anchors.fill: parent; hoverEnabled: true
        onPositionChanged: function(mouse) { var cell=root.cellAt(mouse.x,mouse.y); root.hoveredLabel=cell ? cell.label+" · 후보 "+cell.count+"개" : "후보가 없는 영역" }
        onExited: root.hoveredLabel=""
        onClicked: function(mouse) {
            var cell=root.cellAt(mouse.x,mouse.y)
            if (cell) { root.uiState.resultViewMode="area"; root.navigator.activate(true); root.navigator.selectArea(cell.id) }
        }
    }
    Rectangle {
        anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 16
        width: Math.min(parent.width-32, legend.implicitWidth+28); height: legend.implicitHeight+22
        radius: root.theme.radiusPanel; color: root.theme.panel
        Text { id: legend; anchors.fill: parent; anchors.margins: 11; wrapMode: Text.Wrap; color: root.theme.text; font.pixelSize: 12
            text: root.hoveredLabel || "후보 분포 · 영역을 눌러 검토\n밝을수록 후보가 많음 · 위험도 아님"
        }
    }
}
