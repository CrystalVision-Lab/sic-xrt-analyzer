import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    objectName: "overviewMap"
    property QtObject theme
    property url imageSource
    property real imageWidth: 1
    property real imageHeight: 1
    property var viewRect: [0,0,1,1]
    property var selectedPoint: []
    property var coverage: []
    signal navigate(real x, real y)
    width: 190; height: 160
    radius: theme.radiusControl
    color: theme.panel; border.color: theme.border
    Text { x: 10; y: 6; text: "전체 지도 · 현재 위치"; color: root.theme.text; font.pixelSize: 12 }
    Image {
        id: overview
        anchors { left: parent.left; right: parent.right; top: parent.top; bottom: parent.bottom; margins: 8; topMargin: 28 }
        source: root.imageSource
        fillMode: Image.PreserveAspectFit
        smooth: true
        Item {
            id: map
            x: (overview.width-overview.paintedWidth)/2; y: (overview.height-overview.paintedHeight)/2
            width: overview.paintedWidth; height: overview.paintedHeight; clip: true
            Repeater {model:root.coverage
                Rectangle {required property var modelData;x:modelData.rect[0]/Math.max(1,root.imageWidth)*map.width;y:modelData.rect[1]/Math.max(1,root.imageHeight)*map.height;width:modelData.rect[2]/Math.max(1,root.imageWidth)*map.width;height:modelData.rect[3]/Math.max(1,root.imageHeight)*map.height;color:modelData.checked?"#6657ba88":"#334fa2c4"}
            }
            Rectangle {
                objectName: "overviewViewport"
                x: Math.max(0,root.viewRect[0])/Math.max(1,root.imageWidth)*map.width
                y: Math.max(0,root.viewRect[1])/Math.max(1,root.imageHeight)*map.height
                width: Math.max(0,Math.min(root.imageWidth,root.viewRect[0]+root.viewRect[2])-Math.max(0,root.viewRect[0]))/Math.max(1,root.imageWidth)*map.width
                height: Math.max(0,Math.min(root.imageHeight,root.viewRect[1]+root.viewRect[3])-Math.max(0,root.viewRect[1]))/Math.max(1,root.imageHeight)*map.height
                color: "#2245c3cf"; border.color: root.theme.accent; border.width: 2
            }
            Rectangle {
                visible: root.selectedPoint.length === 2
                x: (root.selectedPoint[0]||0)/Math.max(1,root.imageWidth)*map.width-3
                y: (root.selectedPoint[1]||0)/Math.max(1,root.imageHeight)*map.height-3
                width: 6; height: 6; radius: 3; color: "#ffd65a"
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.OpenHandCursor
                function move(m) { root.navigate(Math.max(0,Math.min(1,m.x/width))*root.imageWidth,Math.max(0,Math.min(1,m.y/height))*root.imageHeight) }
                onPressed: function(m) { move(m) }
                onPositionChanged: function(m) { if (pressed) move(m) }
            }
        }
    }
}
