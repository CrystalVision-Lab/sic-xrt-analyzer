import QtQuick
import QtQuick3D
import XrtStack3D 1.0
Item {
 id:root;objectName:"defect3dPerspective";property QtObject theme;property var controller
 property real rx:-20;property real ry:30;property real px:0;property real py:0;property real distance:450
 function reset(){rx=-20;ry=30;px=0;py=0;distance=Math.max(35,(controller.state.visual?controller.state.visualExtent:controller.state.displayExtent)*2.2)}
 Component.onCompleted:reset()
 Connections{target:root.controller;function onMeshChanged(){if(root.controller.state.ready)root.reset()} function onLayersChanged(){if(root.controller.state.visual)root.distance=Math.max(35,root.controller.state.visualExtent*2.2)}}
 View3D {
  anchors.fill:parent
  environment:SceneEnvironment{backgroundMode:SceneEnvironment.Color;clearColor:root.theme.viewer;antialiasingMode:SceneEnvironment.MSAA;antialiasingQuality:SceneEnvironment.High}
  PerspectiveCamera{position:Qt.vector3d(root.px,root.py,root.distance);clipNear:1;clipFar:5000}
  DirectionalLight{eulerRotation:Qt.vector3d(-35,-35,0);brightness:1.2;ambientColor:"#525252"}
  DirectionalLight{eulerRotation:Qt.vector3d(25,140,0);brightness:.6}
  Node{eulerRotation:Qt.vector3d(root.rx,root.ry,0)
   Model{objectName:"connectedDefectSurface";visible:!root.controller.state.visual;geometry:DefectSurface{sourceController:root.controller}
    materials:PrincipledMaterial{baseColor:"#63d8d0";metalness:.12;roughness:.42;cullMode:Material.NoCulling}}
   Model{visible:root.controller.state.visual;geometry:DefectLayer{sourceController:root.controller}
    materials:PrincipledMaterial{baseColor:"#399a96";lighting:PrincipledMaterial.NoLighting;cullMode:Material.NoCulling}}
   Model{objectName:"currentDefectLayer";visible:root.controller.state.visual;z:root.controller.state.phase===0?Math.min(70,root.controller.state.visualExtent*.3):0
    Behavior on z{NumberAnimation{duration:400;easing.type:Easing.InOutCubic}}
    geometry:DefectLayer{sourceController:root.controller;current:true}
    materials:PrincipledMaterial{baseColor:"#9affeb";lighting:PrincipledMaterial.NoLighting;cullMode:Material.NoCulling}}
  }
 }
 MouseArea{objectName:"defect3dOrbitInput";anchors.fill:parent;acceptedButtons:Qt.LeftButton|Qt.RightButton|Qt.MiddleButton;property point previous
  onPressed:function(m){previous=Qt.point(m.x,m.y)}
  onPositionChanged:function(m){if(!pressed)return;var dx=m.x-previous.x,dy=m.y-previous.y;if(pressedButtons&Qt.LeftButton){root.ry+=dx*.4;root.rx=Math.max(-89,Math.min(89,root.rx+dy*.4))}else{root.px-=dx*.5;root.py+=dy*.5}previous=Qt.point(m.x,m.y)}
  onWheel:function(w){root.distance=Math.max(20,Math.min(3000,root.distance*Math.pow(1.001,-w.angleDelta.y)));w.accepted=true}
  onDoubleClicked:root.reset()
 }
}
