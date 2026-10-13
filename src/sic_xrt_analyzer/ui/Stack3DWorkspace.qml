import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
ColumnLayout {
 id:root;objectName:"stack3dWorkspace";property QtObject theme;property QtObject uiState;property var controller:fileBridge.stack3d;property var state:controller.state;signal projectRequested()
 onVisibleChanged:controller.setActive(visible)
 RowLayout{Layout.fillWidth:true
  AppButton{objectName:"stack3dBack";theme:root.theme;text:"← 이미지";onClicked:root.uiState.workspaceIndex=0}
  Text{text:"선택 영역 3D";color:root.theme.text;font.pixelSize:18;Layout.fillWidth:true}
  Text{text:"페이지 좌표";color:root.theme.muted;font.pixelSize:12}
  AppButton{objectName:"stack3dReset";theme:root.theme;text:"화면 맞춤";onClicked:root.controller.resetView()}
 }
 TabBar{id:tabs;objectName:"stack3dTabs";Layout.fillWidth:true;TabButton{text:"3D"}TabButton{text:"XY"}TabButton{text:"X–페이지"}TabButton{text:"Y–페이지"}}
 StackLayout{currentIndex:tabs.currentIndex;Layout.fillWidth:true;Layout.fillHeight:true
  Item{
   Loader{objectName:"stack3dSceneLoader";anchors.fill:parent;active:root.visible&&root.state.ready&&root.state.rhi_available;sourceComponent:Component{Stack3DScene{controller:root.controller;theme:root.theme}}}
   BusyIndicator{anchors.centerIn:parent;running:root.state.busy;visible:running}
   Text{anchors.centerIn:parent;text:root.state.error||(!root.state.rhi_available&&root.state.ready?"3D GPU 준비 실패 · 단면 보기 사용":"");visible:!!text;color:root.theme.warning;wrapMode:Text.Wrap;width:parent.width*.8}
  }
  StackOrthogonalView{controller:root.controller;theme:root.theme;kind:"xy"}
  StackOrthogonalView{controller:root.controller;theme:root.theme;kind:"xp"}
  StackOrthogonalView{controller:root.controller;theme:root.theme;kind:"yp"}
 }
 RowLayout{Layout.fillWidth:true
  Text{text:root.state.position.length?"페이지 "+(root.state.position[2]+1)+" / "+root.state.source.pages:"";color:root.theme.text}
  Slider{objectName:"stack3dPageSlider";Layout.fillWidth:true;from:0;to:Math.max(0,root.state.shape[0]-1);value:root.state.cursor[0];stepSize:1;enabled:root.state.ready;onMoved:root.controller.setPage(Math.round(value))}
  AppButton{objectName:"stack3dCancel";theme:root.theme;text:"취소";visible:root.state.busy;onClicked:root.controller.cancel()}
 }
 ProgressBar{Layout.fillWidth:true;visible:root.state.busy;from:0;to:Math.max(1,root.state.progress[1]);value:root.state.progress[0]}
}
