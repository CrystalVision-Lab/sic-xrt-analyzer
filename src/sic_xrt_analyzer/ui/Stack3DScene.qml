import QtQuick
import QtQuick3D
import XrtStack3D 1.0

Item {
    id:root
    objectName:"stack3dPerspective"
    property var controller
    property QtObject theme
    property var scene:controller ? controller.scene : ({})
    property real rx:-25
    property real ry:35
    property real px:0
    property real py:0
    property real distance:650
    property string hoverText:""
    function resetCamera() {var c=controller.state.camera;rx=c[0];ry=c[1];px=c[2];py=c[3];distance=c[4]}
    Component.onCompleted:resetCamera()
    Connections {target:root.controller;function onCameraReset(){root.resetCamera()}}
    View3D {
        id:view;objectName:"stack3dView";anchors.fill:parent
        environment:SceneEnvironment {backgroundMode:SceneEnvironment.Color;clearColor:root.theme.viewer}
        PerspectiveCamera {position:Qt.vector3d(root.px,root.py,root.distance);clipNear:1;clipFar:6000}
        Node {
            eulerRotation:Qt.vector3d(root.rx,root.ry,0)
            Repeater3D {
                model:root.scene.planes||[]
                delegate:Model {
                    required property var modelData
                    source:"#Rectangle";pickable:true
                    position:Qt.vector3d(0,0,modelData.z)
                    scale:Qt.vector3d(root.scene.size[0]/100,root.scene.size[1]/100,1)
                    materials:DefaultMaterial {
                        lighting:DefaultMaterial.NoLighting;cullMode:Material.NoCulling
                        opacity:modelData.selected?1:.23
                        diffuseMap:Texture {
                            minFilter:Texture.Nearest;magFilter:Texture.Nearest
                            sourceItem:Image {source:modelData.url;width:512;height:512;visible:false;smooth:false;cache:false}
                        }
                    }
                }
            }
            Model {
                visible:(root.scene.segments||[]).length>0
                geometry:TrackLines {vertices:root.scene.segments||[]}
                materials:DefaultMaterial {lighting:DefaultMaterial.NoLighting;diffuseColor:root.theme.warning;cullMode:Material.NoCulling}
            }
            Repeater3D {
                model:root.scene.markers||[]
                delegate:Model {required property var modelData;source:"#Sphere";position:Qt.vector3d(modelData.position[0],modelData.position[1],modelData.position[2]);scale:Qt.vector3d(.035,.035,.035);materials:DefaultMaterial {lighting:DefaultMaterial.NoLighting;diffuseColor:modelData.status==="UNCERTAIN"?"#e69c45":"#48c2cd"}}
            }
            Model {
                source:"#Sphere";visible:!!root.scene.selected_world
                position:root.scene.selected_world ? Qt.vector3d(root.scene.selected_world[0],root.scene.selected_world[1],root.scene.selected_world[2]) : Qt.vector3d(0,0,0)
                scale:Qt.vector3d(.05,.05,.05)
                materials:DefaultMaterial {lighting:DefaultMaterial.NoLighting;diffuseColor:"#f26e63"}
            }
            Model {source:"#Cylinder";eulerRotation:Qt.vector3d(0,0,90);position:Qt.vector3d(170,-170,-95);scale:Qt.vector3d(.01,.4,.01);materials:DefaultMaterial {lighting:DefaultMaterial.NoLighting;diffuseColor:"#e75d57"}}
            Model {source:"#Cylinder";position:Qt.vector3d(150,-190,-95);scale:Qt.vector3d(.01,.4,.01);materials:DefaultMaterial {lighting:DefaultMaterial.NoLighting;diffuseColor:"#69bc79"}}
            Model {source:"#Cylinder";eulerRotation:Qt.vector3d(90,0,0);position:Qt.vector3d(150,-170,-75);scale:Qt.vector3d(.01,.4,.01);materials:DefaultMaterial {lighting:DefaultMaterial.NoLighting;diffuseColor:"#559fd4"}}
        }
    }
    MouseArea {
        objectName:"stack3dOrbitInput";anchors.fill:parent;acceptedButtons:Qt.LeftButton|Qt.RightButton|Qt.MiddleButton
        property point previous:Qt.point(0,0)
        property real moved:0
        hoverEnabled:true
        onPressed:function(mouse){previous=Qt.point(mouse.x,mouse.y);moved=0}
        onPositionChanged:function(mouse){
            if(!pressed){var hit=view.pick(mouse.x,mouse.y);if(hit.objectHit&&hit.objectHit.modelData)root.hoverText=root.controller.hover("plane:"+hit.objectHit.modelData.ik,hit.position.x/100+.5,.5-hit.position.y/100);return}
            var dx=mouse.x-previous.x,dy=mouse.y-previous.y
            moved+=Math.abs(dx)+Math.abs(dy)
            if(pressedButtons&Qt.LeftButton){root.ry+=dx*.4;root.rx=Math.max(-85,Math.min(85,root.rx+dy*.4))}
            else {root.px-=dx*.5;root.py+=dy*.5}
            previous=Qt.point(mouse.x,mouse.y)
        }
        onClicked:function(mouse){if(moved<5&&mouse.button===Qt.LeftButton){var hit=view.pick(mouse.x,mouse.y);if(hit.objectHit&&hit.objectHit.modelData){var p=hit.objectHit.modelData;root.controller.pickPlane(p.ik,hit.position.x/100+.5,.5-hit.position.y/100,p.volume_revision)}}}
        onReleased:root.controller.setCamera(root.rx,root.ry,root.px,root.py,root.distance)
        onWheel:function(wheel){root.distance=Math.max(200,Math.min(3000,root.distance*Math.pow(1.001,-wheel.angleDelta.y)));root.controller.setCamera(root.rx,root.ry,root.px,root.py,root.distance);wheel.accepted=true}
        onDoubleClicked:root.controller.resetView()
    }
    Text {anchors.left:parent.left;anchors.top:parent.top;anchors.margins:12;color:root.theme.text;font.pixelSize:11;wrapMode:Text.Wrap;width:parent.width-24;text:"왼쪽 드래그 Orbit · 오른쪽/가운데 Pan · 휠 Zoom
X/Y 원본 픽셀 · +Page Index · 선택 단면 불투명\n축: 빨강 +X · 초록 +Y(원본 아래) · 파랑 +Page"}
    Text {anchors.left:parent.left;anchors.bottom:parent.bottom;anchors.margins:12;color:root.theme.warning;font.pixelSize:11;wrapMode:Text.Wrap;width:parent.width-24;text:root.hoverText+"\n표시 평면 "+(root.scene.planes||[]).length+"개 (시각화 샘플) · 원본 Volume 페이지는 별도 유지
수동 연결선은 관측 보조 표현 · 빈 페이지 구간은 점선 · 동일 물리 결함 미확정"}
}
