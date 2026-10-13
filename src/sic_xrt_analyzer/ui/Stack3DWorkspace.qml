import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
ColumnLayout {
 id:root;objectName:"stack3dWorkspace";property QtObject theme;property QtObject uiState;property var controller:fileBridge.defect3d;property var state:controller.state;signal projectRequested()
 RowLayout{Layout.fillWidth:true
  AppButton{objectName:"stack3dBack";theme:root.theme;text:"← 이미지";onClicked:root.uiState.workspaceIndex=0}
  Text{text:"연결 결함 3D";color:root.theme.text;font.pixelSize:18;Layout.fillWidth:true}
  Text{text:root.state.ready?root.state.pages+"장 연결":"";color:root.theme.muted;font.pixelSize:12}
  AppButton{objectName:"defect3dReselect";theme:root.theme;text:"다시 선택";onClicked:{root.uiState.workspaceIndex=0;root.uiState.activeTool="Defect3D"}}
  AppButton{objectName:"stack3dReset";theme:root.theme;text:"화면 맞춤";onClicked:if(scene.item)scene.item.reset()}
 }
 Item{Layout.fillWidth:true;Layout.fillHeight:true
  Loader{id:scene;objectName:"stack3dSceneLoader";anchors.fill:parent;active:root.visible&&root.state.ready&&root.state.rhi_available;sourceComponent:Component{Defect3DScene{controller:root.controller;theme:root.theme}}}
  BusyIndicator{anchors.centerIn:parent;running:root.state.busy;visible:running}
  Text{anchors.centerIn:parent;text:root.state.error||(root.state.ready&&!root.state.rhi_available?"GPU 3D 표시를 사용할 수 없습니다":"")||(!root.state.ready&&!root.state.busy?"이미지에서 검은 결함을 선택하세요":"");visible:!!text;color:root.theme.warning;wrapMode:Text.Wrap;width:parent.width*.75;horizontalAlignment:Text.AlignHCenter}
 }
 Text{text:root.state.warning;visible:!!text;color:root.theme.warning;Layout.fillWidth:true}
 RowLayout{visible:root.state.ready;Layout.fillWidth:true
  Text{text:"드래그 회전 · 우클릭 이동 · 휠 확대";color:root.theme.muted;font.pixelSize:12;Layout.fillWidth:true}
  AppButton{theme:root.theme;text:"분할 조절";onClicked:options.open()}
  Text{text:"XY 픽셀 / 페이지 간격";color:root.theme.muted;font.pixelSize:11;ToolTip.visible:unitsHover.hovered;ToolTip.text:"실제 Z 간격 미확정 · 접촉한 검은 성분은 함께 연결될 수 있음 · 표시 간격 "+root.state.xyStep;HoverHandler{id:unitsHover}}
 }
 Popup{id:options;parent:Overlay.overlay;anchors.centerIn:parent;padding:18;contentItem:ColumnLayout{
  Text{text:"검은 영역 감도";color:root.theme.text}
  Slider{id:strength;from:.4;to:2.5;value:root.state.sensitivity;Layout.preferredWidth:260}
  AppButton{theme:root.theme;text:"다시 생성";onClicked:{root.controller.reconstruct(strength.value);options.close()}}
 }}
 RowLayout{visible:root.state.busy;Layout.fillWidth:true
  Text{text:root.state.progress[2];color:root.theme.text}
  ProgressBar{Layout.fillWidth:true;from:0;to:Math.max(1,root.state.progress[1]);value:root.state.progress[0]}
  AppButton{objectName:"stack3dCancel";theme:root.theme;text:"취소";onClicked:root.controller.cancel()}
 }
}
