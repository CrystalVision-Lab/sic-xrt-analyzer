import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
Rectangle{
 id:root;objectName:"waferMapWorkspace";property QtObject theme;property QtObject uiState;signal projectRequested()
 property var controller:fileBridge.folderMap;property var state:controller.state
 property real scale:1;property real px:0;property real py:0;property int lastRevision:-1
 color:theme.viewer
 onScaleChanged:detailTimer.restart()
 onPxChanged:detailTimer.restart()
 onPyChanged:detailTimer.restart()
 onVisibleChanged:if(visible)detailTimer.restart()
 Timer{id:detailTimer;interval:100;onTriggered:{if(root.visible&&root.state.ready){var d=viewport.fitScale*root.scale;root.controller.requestDetail(-mosaic.x/d,-mosaic.y/d,viewport.width/d,viewport.height/d,d*Screen.devicePixelRatio)}}}
 function fit(){scale=1;px=0;py=0}
 onStateChanged:if(state.revision!==lastRevision){lastRevision=state.revision;if(state.ready){fit();detailTimer.restart()}}
 SafeFolderDialog{id:folder;objectName:"waferFolderDialog";title:"같은 촬영의 사진 폴더 선택";onAccepted:root.controller.open(selectedFolder.toString())}
 ColumnLayout{anchors.fill:parent;anchors.margins:14;spacing:12
  RowLayout{Layout.fillWidth:true
   Text{text:"Wafer Map";color:root.theme.text;font.pixelSize:20}
   ComboBox{objectName:"waferCaptureGroup";visible:root.state.groups.length>1;model:root.state.groups;textRole:"label";currentIndex:root.state.group;Layout.fillWidth:true;onActivated:function(index){root.controller.selectGroup(index)}}
   Item{Layout.fillWidth:true;visible:root.state.groups.length<=1}
   Text{text:root.state.ready?root.state.aligned+" / "+root.state.count+"장":"";color:root.theme.muted;font.pixelSize:12}
   AppButton{objectName:"chooseWaferFolder";theme:root.theme;text:"폴더 선택";primary:true;onClicked:folder.open()}
   AppButton{objectName:"mapFit";theme:root.theme;text:"화면 맞춤";onClicked:root.fit()}
  }
  Item{id:viewport;Layout.fillWidth:true;Layout.fillHeight:true;clip:true
   property real fitScale:Math.min(width/Math.max(1,root.state.size[0]),height/Math.max(1,root.state.size[1]))*.94
   Image{id:mosaic;objectName:"waferMosaicImage";visible:root.state.ready;source:root.state.ready?"image://tiff/folder-mosaic?"+root.state.revision:"";cache:false;smooth:true
    width:root.state.size[0]*viewport.fitScale*root.scale;height:root.state.size[1]*viewport.fitScale*root.scale;x:viewport.width/2+root.px-width/2;y:viewport.height/2+root.py-height/2
   }
   Image{objectName:"waferNativeDetail";visible:root.state.ready&&root.state.detailRevision>0;cache:false;asynchronous:true;smooth:false
    source:visible?"image://tiff/folder-detail?"+root.state.detailRevision:""
    x:mosaic.x+root.state.detailRect[0]*viewport.fitScale*root.scale;y:mosaic.y+root.state.detailRect[1]*viewport.fitScale*root.scale
    width:root.state.detailRect[2]*viewport.fitScale*root.scale;height:root.state.detailRect[3]*viewport.fitScale*root.scale
   }
   onWidthChanged:detailTimer.restart()
   onHeightChanged:detailTimer.restart()
   MouseArea{anchors.fill:parent;acceptedButtons:Qt.LeftButton|Qt.MiddleButton|Qt.RightButton;property real oldX;property real oldY
    onPressed:function(m){oldX=m.x;oldY=m.y}
    onPositionChanged:function(m){if(pressed){root.px+=m.x-oldX;root.py+=m.y-oldY;oldX=m.x;oldY=m.y}}
    onDoubleClicked:function(m){if(root.state.ready)root.controller.openAt((m.x-mosaic.x)/(viewport.fitScale*root.scale),(m.y-mosaic.y)/(viewport.fitScale*root.scale))}
    onWheel:function(w){var old=root.scale,next=Math.max(.05,Math.min(4096,old*Math.pow(1.15,w.angleDelta.y/120))),ratio=next/old;root.px=(w.x-viewport.width/2)-(w.x-viewport.width/2-root.px)*ratio;root.py=(w.y-viewport.height/2)-(w.y-viewport.height/2-root.py)*ratio;root.scale=next;w.accepted=true}
   }
   AppButton{anchors.centerIn:parent;theme:root.theme;text:"이미지 폴더 선택";visible:!root.state.rows.length&&!root.state.busy;onClicked:folder.open()}
   BusyIndicator{anchors.centerIn:parent;running:root.state.busy;visible:running}
   ColumnLayout{anchors.horizontalCenter:parent.horizontalCenter;anchors.bottom:parent.bottom;visible:root.state.busy;width:Math.min(420,parent.width-40)
    Text{text:root.state.progress[2];color:root.theme.text;Layout.alignment:Qt.AlignHCenter}
    ProgressBar{from:0;to:Math.max(1,root.state.progress[1]);value:root.state.progress[0];Layout.fillWidth:true}
   }
  }
  Text{text:root.state.detailError||root.state.error;visible:!!text;color:root.theme.warning;Layout.fillWidth:true;wrapMode:Text.Wrap}
 }
}
