import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Rectangle {
 id:root;objectName:"waferMapWorkspace";property QtObject theme;property QtObject uiState;signal projectRequested()
 property var controller:fileBridge.folderMap;property var state:controller.state
 property real scale:1;property real px:0;property real py:0
 color:theme.viewer
 function fit(){scale=1;px=0;py=0}
 onStateChanged:if(state.revision>0)fit()
 SafeFolderDialog{id:folder;objectName:"waferFolderDialog";title:"이미지 폴더 선택";onAccepted:root.controller.open(selectedFolder.toString())}
 ColumnLayout{anchors.fill:parent;anchors.margins:14;spacing:12
  RowLayout{Layout.fillWidth:true
   Text{text:"Wafer Map";color:root.theme.text;font.pixelSize:20}
   Text{text:root.state.rows.length?root.state.rows.length+"개 · 임시 배치":"";color:root.theme.muted;font.pixelSize:12;Layout.fillWidth:true}
   AppButton{objectName:"chooseWaferFolder";theme:root.theme;text:"폴더 선택";primary:true;onClicked:folder.open()}
   AppButton{objectName:"mapFit";theme:root.theme;text:"화면 맞춤";onClicked:root.fit()}
  }
  Item{id:viewport;Layout.fillWidth:true;Layout.fillHeight:true;clip:true
   property real unit:Math.min(width,height)*.85/((root.state.radius||1)*2+2)
   Rectangle{x:viewport.width/2+root.px-width/2;y:viewport.height/2+root.py-height/2;width:viewport.unit*((root.state.radius||1)*2+2)*root.scale;height:width;radius:width/2;color:"transparent";border.color:root.theme.border;border.width:2}
   Repeater{model:root.state.rows
    Image{required property var modelData;source:"image://tiff/folder-"+modelData.id+"?"+root.state.revision;x:viewport.width/2+root.px+(modelData.x-.48)*viewport.unit*root.scale;y:viewport.height/2+root.py+(modelData.y-.48)*viewport.unit*root.scale;width:viewport.unit*.96*root.scale;height:width;fillMode:Image.PreserveAspectFit;cache:false
     ToolTip.visible:hover.hovered;ToolTip.text:modelData.name;HoverHandler{id:hover}
     TapHandler{onDoubleTapped:root.controller.openImage(modelData.id)}
    }
   }
   MouseArea{anchors.fill:parent;acceptedButtons:Qt.LeftButton|Qt.MiddleButton|Qt.RightButton;property real oldX;property real oldY
    onPressed:function(m){oldX=m.x;oldY=m.y}
    onPositionChanged:function(m){if(pressed){root.px+=m.x-oldX;root.py+=m.y-oldY;oldX=m.x;oldY=m.y}}
    onDoubleClicked:function(m){
     var x=(m.x-viewport.width/2-root.px)/(viewport.unit*root.scale),y=(m.y-viewport.height/2-root.py)/(viewport.unit*root.scale)
     for(var i=0;i<root.state.rows.length;i++){var r=root.state.rows[i];if(Math.abs(x-r.x)<.48&&Math.abs(y-r.y)<.48){root.controller.openImage(r.id);break}}
    }
    onWheel:function(w){var old=root.scale;var next=Math.max(.05,Math.min(32,old*Math.pow(1.15,w.angleDelta.y/120)));var ratio=next/old;root.px=(w.x-viewport.width/2)-(w.x-viewport.width/2-root.px)*ratio;root.py=(w.y-viewport.height/2)-(w.y-viewport.height/2-root.py)*ratio;root.scale=next;w.accepted=true}
   }
   AppButton{anchors.centerIn:parent;theme:root.theme;text:"이미지 폴더 선택";visible:!root.state.rows.length&&!root.state.busy;onClicked:folder.open()}
   BusyIndicator{anchors.centerIn:parent;running:root.state.busy;visible:running}
  }
  Text{text:root.state.error;visible:!!text;color:root.theme.warning;Layout.fillWidth:true;wrapMode:Text.Wrap}
 }
}
