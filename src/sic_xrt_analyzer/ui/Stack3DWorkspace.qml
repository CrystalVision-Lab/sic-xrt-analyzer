import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
ColumnLayout {
 id:root;objectName:"stack3dWorkspace";property QtObject theme;property QtObject uiState
 property var controller:fileBridge.defect3d;property var state:controller.state;signal projectRequested()
 property bool showFull:true;property bool excludeMode:false;property bool includeMode:false
 onVisibleChanged:controller.setPresented(visible)
 RowLayout{Layout.fillWidth:true
  AppButton{objectName:"stack3dBack";theme:root.theme;text:"← 이미지";onClicked:root.uiState.workspaceIndex=0}
  Text{text:"선택 결함 3D";color:root.theme.text;font.pixelSize:18;Layout.fillWidth:true}
  Text{text:root.state.ready?root.state.pages+"장":"";color:root.theme.muted;font.pixelSize:12}
  AppButton{theme:root.theme;text:"과정 다시 보기";visible:root.state.ready&&!root.state.visual;onClicked:root.controller.replay()}
  AppButton{objectName:"defect3dReselect";theme:root.theme;text:"다시 선택";onClicked:{root.uiState.workspaceIndex=0;root.uiState.activeTool="Defect3D"}}
  AppButton{objectName:"stack3dReset";theme:root.theme;text:"화면 맞춤";onClicked:if(scene.item)scene.item.reset()}
 }
 RowLayout{Layout.fillWidth:true;Layout.fillHeight:true;spacing:10
  Rectangle{visible:root.state.visual;Layout.preferredWidth:root.width*.42;Layout.fillHeight:true;color:root.theme.viewer;clip:true
   ColumnLayout{anchors.fill:parent;anchors.margins:10
    RowLayout{Layout.fillWidth:true
     Text{text:root.state.frameRevision?root.state.framePage+" 페이지":"원본 읽는 중";color:root.theme.text;Layout.fillWidth:true}
     AppButton{theme:root.theme;text:root.showFull?"결함 확대":"전체 사진";onClicked:root.showFull=!root.showFull}
     AppButton{theme:root.theme;text:root.excludeMode?"제외 취소":"다른 결함 제외";onClicked:{root.excludeMode=!root.excludeMode;if(root.excludeMode&&!root.state.paused)root.controller.togglePause()}}
    }
    RowLayout{Layout.fillWidth:true
     AppButton{theme:root.theme;text:root.includeMode?"연결 지정 취소":"같은 결함 지정";onClicked:{root.includeMode=!root.includeMode;root.excludeMode=false;if(root.includeMode&&!root.state.paused)root.controller.togglePause()}}
     AppButton{theme:root.theme;text:"이 페이지 건너뛰기";onClicked:root.controller.skipCurrent()}
    }
    Item{Layout.fillWidth:true;Layout.fillHeight:true
     Image{id:photo;objectName:"defectTraceSource";anchors.fill:parent;fillMode:Image.PreserveAspectFit;cache:false;smooth:false
      source:root.state.frameRevision?"image://tiff/stack3d-trace-"+(root.showFull?"full":"crop")+"?"+root.state.frameRevision:""
     }
     Rectangle{visible:root.showFull&&root.state.frameRevision>0;anchors.right:parent.right;anchors.bottom:parent.bottom;width:Math.min(200,parent.width*.42);height:width;color:root.theme.viewer;border.color:root.theme.accent
      Image{anchors.fill:parent;anchors.margins:2;fillMode:Image.PreserveAspectFit;smooth:false;cache:false;source:parent.visible?"image://tiff/stack3d-trace-crop?"+root.state.frameRevision:""}
     }
     MouseArea{anchors.fill:parent;enabled:(root.excludeMode||root.includeMode)&&root.state.frameRevision>0;cursorShape:Qt.CrossCursor
      onClicked:function(m){var left=(width-photo.paintedWidth)/2,top=(height-photo.paintedHeight)/2,u=(m.x-left)/photo.paintedWidth,v=(m.y-top)/photo.paintedHeight;if(u<0||u>1||v<0||v>1)return;var r=root.showFull?[0,0,root.state.sourceSize[0],root.state.sourceSize[1]]:root.state.cropRect;if(root.includeMode){root.includeMode=false;root.controller.include(r[0]+u*r[2],r[1]+v*r[3])}else{root.excludeMode=false;root.controller.exclude(r[0]+u*r[2],r[1]+v*r[3])}}
     }
    }
    Text{text:root.includeMode?"이어갈 같은 결함을 클릭하세요":root.excludeMode?"제외할 다른 결함을 클릭하세요":root.state.frameReason==="ACCEPTED"?(root.state.phase===0?"인식 영역":"3D에 쌓는 중"):root.state.frameReason==="NO_CONTACT"?"연결 없음 · 여기까지":root.state.frameReason?"연결 모호 · 자동 합치기 중단":"";color:root.state.frameReason==="ACCEPTED"?root.theme.accent:root.theme.warning}
   }
  }
  Text{visible:root.state.visual;text:"→";color:root.theme.accent;font.pixelSize:26}
  Item{Layout.fillWidth:true;Layout.fillHeight:true
   Loader{id:scene;objectName:"stack3dSceneLoader";anchors.fill:parent;active:root.visible&&(root.state.ready||root.state.visual)&&root.state.rhi_available;sourceComponent:Component{Defect3DScene{controller:root.controller;theme:root.theme}}}
   BusyIndicator{anchors.centerIn:parent;running:root.state.busy&&!root.state.frameRevision;visible:running}
   Text{anchors.centerIn:parent;text:root.state.error||(root.state.ready&&!root.state.rhi_available?"GPU 3D 표시를 사용할 수 없습니다":"")||(!root.state.ready&&!root.state.busy?"이미지에서 검은 결함을 선택하세요":"");visible:!!text;color:root.theme.warning;wrapMode:Text.Wrap;width:parent.width*.75;horizontalAlignment:Text.AlignHCenter}
  }
 }
 RowLayout{visible:root.state.visual;Layout.fillWidth:true
  AppButton{theme:root.theme;text:root.state.paused?"▶ 계속":"Ⅱ 일시정지";onClicked:root.controller.togglePause()}
  AppButton{theme:root.theme;text:"다음 단계";enabled:root.state.frameRevision>0;onClicked:root.controller.stepFrame()}
  Item{Layout.fillWidth:true}
  AppButton{theme:root.theme;text:root.state.busy?"빠르게 완료":"결과 보기";onClicked:root.controller.fastFinish()}
 }
 Text{text:"직접 지정 "+root.state.manualAnchors+"곳 · 건너뛴 페이지 "+root.state.skippedPages.join(", ");visible:root.state.manualAnchors>0||root.state.skippedPages.length>0;color:root.theme.muted;Layout.fillWidth:true}
 Text{text:"분기·교차 가능성 "+root.state.junctionPages.length+"페이지 · 같은 결함인지 확인하세요";visible:root.state.junctionPages.length>0;color:root.theme.warning;Layout.fillWidth:true}
 Text{text:root.state.warning;visible:!!text&&!root.state.visual;color:root.theme.warning;Layout.fillWidth:true}
 RowLayout{visible:!root.state.visual&&(root.state.ready||!!root.state.error);Layout.fillWidth:true
  Text{text:"드래그 회전 · 우클릭 이동 · 휠 확대";color:root.theme.muted;font.pixelSize:12;Layout.fillWidth:true}
  AppButton{theme:root.theme;text:"분할 조절";onClicked:options.open()}
  Text{text:"XY 픽셀 / 페이지 간격";color:root.theme.muted;font.pixelSize:11;ToolTip.visible:unitsHover.hovered;ToolTip.text:"실제 깊이·동일 결함 여부는 미검증 · 표시 간격 "+root.state.xyStep;HoverHandler{id:unitsHover}}
 }
 Popup{id:options;parent:Overlay.overlay;anchors.centerIn:parent;padding:18;contentItem:ColumnLayout{
  Text{text:"검은 영역 감도";color:root.theme.text}
  Slider{id:strength;from:.4;to:2.5;value:root.state.sensitivity;Layout.preferredWidth:260}
  AppButton{theme:root.theme;text:"다시 생성";onClicked:{root.controller.reconstruct(strength.value);options.close()}}
 }}
 RowLayout{visible:root.state.busy;Layout.fillWidth:true
  ProgressBar{Layout.fillWidth:true;from:0;to:Math.max(1,root.state.progress[1]);value:root.state.progress[0]}
  AppButton{objectName:"stack3dCancel";theme:root.theme;text:"취소";onClicked:root.controller.cancel()}
 }
}
