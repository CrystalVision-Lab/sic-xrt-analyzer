import QtQuick

Item {
    id:root
    property var controller
    property QtObject theme
    property string kind:"xy"
    property string overlaySource:""
    property var state:controller.state
    property var scene:controller.scene
    property string hoverText:""
    signal picked(string kind, real u, real v, int modifiers)
    Image {id:image;objectName:"stack3dSliceImage";anchors.fill:parent;source:(root.scene.urls||({}))[root.kind]||"";fillMode:Image.PreserveAspectFit;smooth:false;cache:false}
    Item {
        anchors.centerIn:parent;width:image.paintedWidth;height:image.paintedHeight
        property real u:root.kind==="yp" ? (root.state.cursor[1]+.5)/Math.max(1,root.state.shape[1]) : (root.state.cursor[2]+.5)/Math.max(1,root.state.shape[2])
        property real v:root.kind==="xy" ? (root.state.cursor[1]+.5)/Math.max(1,root.state.shape[1]) : (root.state.cursor[0]+.5)/Math.max(1,root.state.shape[0])
        Image {objectName:"stack3dSliceOverlay";anchors.fill:parent;visible:!!root.overlaySource;source:root.overlaySource;smooth:false;cache:false}
        Rectangle {x:parent.u*parent.width;width:1;height:parent.height;color:root.theme.accent;opacity:.8}
        Rectangle {y:parent.v*parent.height;height:1;width:parent.width;color:root.theme.accent;opacity:.8}
        MouseArea {
            objectName:"stack3dSliceInput";anchors.fill:parent;hoverEnabled:true
            onPositionChanged:function(mouse){if(width>0&&height>0)root.hoverText=root.controller.hover(root.kind,mouse.x/width,mouse.y/height)}
            onClicked:function(mouse){if(width>0&&height>0){root.controller.pick(root.kind,mouse.x/width,mouse.y/height);root.picked(root.kind,mouse.x/width,mouse.y/height,mouse.modifiers)}}
            onWheel:function(wheel){root.controller.setPage(Math.max(0,Math.min(root.state.shape[0]-1,root.state.cursor[0]+(wheel.angleDelta.y>0?1:-1))));wheel.accepted=true}
        }
    }
    Text {anchors.left:parent.left;anchors.top:parent.top;anchors.margins:12;color:root.theme.text;text:root.kind==="xy"?"XY · 원본 픽셀":root.kind==="xp"?"X–페이지 · 가로 X / 세로 페이지":"Y–페이지 · 가로 Y / 세로 페이지"}
    Text {objectName:"stack3dPixelCursor";anchors.left:parent.left;anchors.bottom:parent.bottom;anchors.margins:12;color:root.theme.accent;text:root.hoverText}
}
