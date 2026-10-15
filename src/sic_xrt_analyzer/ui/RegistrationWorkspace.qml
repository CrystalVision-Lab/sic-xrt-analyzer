import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Rectangle {
 id:root;objectName:"registrationWorkspace";property QtObject theme;property QtObject uiState;property var actions
 property var controller:fileBridge.registration;property var state:controller.state
 property string observedResult:"";property string mode:"side";property real opacityValue:.5;property real divider:.5;property bool manual:false;property bool beforeOverlay:true;property bool afterOverlay:true;property string coordinateText:"";property real dpr:uiState.displayPixelRatio
 color:theme.viewer
 function sourceIndex(id){for(var i=0;i<state.sources.length;i++)if(state.sources[i].id===id)return i;return -1}
 function choose(){controller.select(beforeChoice.currentIndex>=0?state.sources[beforeChoice.currentIndex].id:"",afterChoice.currentIndex>=0?state.sources[afterChoice.currentIndex].id:"")}
 function updateFrame(){if(visible&&state.ready)controller.requestFrame(Math.round(viewport.width*(mode==="side"?.5:1)*dpr),Math.round(viewport.height*dpr))}
 onVisibleChanged:if(visible)frameTimer.restart()
 onModeChanged:frameTimer.restart()
 Timer{id:frameTimer;interval:20;onTriggered:root.updateFrame()}
 Connections{target:root.controller;function onChanged(){if(beforeLayer)beforeLayer.requestPaint();if(afterLayer)afterLayer.requestPaint();if(compareLayer)compareLayer.requestPaint();if(root.visible&&!root.state.busy&&root.state.asset.registration_id&&root.observedResult!==root.state.asset.registration_id){root.observedResult=root.state.asset.registration_id;result.open()}}}
 ColumnLayout{anchors.fill:parent;anchors.margins:14;spacing:12
  RowLayout{Layout.fillWidth:true
   Text{text:"전·후 비교";color:root.theme.text;font.pixelSize:20;Layout.fillWidth:true}
   AppButton{objectName:"registrationOpenProject";theme:root.theme;text:"저장 데이터 불러오기";onClicked:root.actions.projectOpen.trigger()}
   AppButton{objectName:"registrationRun";theme:root.theme;text:"분석하기";primary:true;enabled:!!root.state.beforeId&&!!root.state.afterId&&root.state.beforeId!==root.state.afterId&&!root.state.busy;onClicked:root.controller.analyzePair()}
   AppButton{theme:root.theme;text:"화면 맞춤";enabled:root.state.ready;onClicked:root.controller.fit()}
   AppButton{objectName:"registrationResult";theme:root.theme;text:"결과";enabled:!!root.state.asset.registration_id;onClicked:result.open()}
  }
  RowLayout{Layout.fillWidth:true
   Text{text:"전";color:root.theme.text;font.pixelSize:15}
   AppComboBox{id:beforeChoice;objectName:"registrationBefore";theme:root.theme;Layout.fillWidth:true;model:root.state.sources;textRole:"name";currentIndex:root.sourceIndex(root.state.beforeId);onActivated:root.choose()}
   Text{text:"후";color:root.theme.text;font.pixelSize:15}
   AppComboBox{id:afterChoice;objectName:"registrationAfter";theme:root.theme;Layout.fillWidth:true;model:root.state.sources;textRole:"name";currentIndex:root.sourceIndex(root.state.afterId);onActivated:root.choose()}
  }
  Text{text:root.state.error;visible:!!text;color:root.theme.warning;Layout.fillWidth:true;wrapMode:Text.Wrap}
  Item{id:viewport;objectName:"registrationViewport";Layout.fillWidth:true;Layout.fillHeight:true;clip:true;onWidthChanged:frameTimer.restart();onHeightChanged:frameTimer.restart()
            Component {
                id: imagePane
                Item {
                    id: pane
                    property string side: "after"
                    property bool composed: false
                    property alias marksItem: marks
                    Image { anchors.fill:parent; source:root.state.ready && root.state.mapping.length===2?"image://tiff/registration-after?"+root.state.revision:""; cache:false; visible: pane.composed || pane.side==="after"; smooth:root.state.zoom<1 }
                    Item {
                        width:pane.width*(pane.composed && root.mode==="split"?root.divider:1); height:pane.height; clip:true
                        Image { width:pane.width; height:pane.height; source:root.state.ready && root.state.mapping.length===2?"image://tiff/registration-before?"+root.state.revision:""; cache:false; visible:pane.composed?root.mode==="overlay"||root.mode==="split":pane.side==="before"; opacity:pane.composed&&root.mode==="overlay"?root.opacityValue:1; smooth:root.state.zoom<1 }
                    }
                    Image { anchors.fill:parent; source:root.state.ready && root.state.mapping.length===2?"image://tiff/registration-difference?"+root.state.revision:""; cache:false; visible:pane.composed&&root.mode==="difference"; smooth:root.state.zoom<1 }
                    Canvas {
                        id:marks;anchors.fill:parent
                        function drawPoints(ctx, side, color) {
                            var index=side==="before"?0:1, mappings=root.state.mapping
                            if(mappings.length!==2)return
                            var m=mappings[index]
                            ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=1.5
                            function point(p) { return [(m[0][0]*p[0]+m[0][1]*p[1]+m[0][2])/root.dpr,(m[1][0]*p[0]+m[1][1]*p[1]+m[1][2])/root.dpr] }
                            for(var i=0;i<root.state.landmarks.length;i++) { var row=root.state.landmarks[i],q=point(row[side]); if(q[0]<-10||q[0]>width+10||q[1]<-10||q[1]>height+10)continue;ctx.beginPath();ctx.arc(q[0],q[1],4,0,Math.PI*2);ctx.stroke();ctx.fillText(""+(i+1),q[0]+6,q[1]-6)
                                if(pane.composed && side==="before") { var t=point(row.before), am=mappings[1],ap=row.after;ctx.beginPath();ctx.moveTo(t[0],t[1]);ctx.lineTo((am[0][0]*ap[0]+am[0][1]*ap[1]+am[0][2])/root.dpr,(am[1][0]*ap[0]+am[1][1]*ap[1]+am[1][2])/root.dpr);ctx.stroke() }
                            }
                            var rows=root.state.overlays||[]
                            for(var j=0;j<rows.length;j++) { var r=rows[j];if(r.side!==side)continue;var ps=r.points;if(ps.length===0)continue;var q0=point(ps[0]);ctx.beginPath();ctx.moveTo(q0[0],q0[1]);for(var k=1;k<ps.length;k++){var qk=point(ps[k]);ctx.lineTo(qk[0],qk[1])}if(ps.length===1)ctx.arc(q0[0],q0[1],3,0,Math.PI*2);ctx.stroke() }
                        }
                        onPaint: { var ctx=getContext("2d");ctx.clearRect(0,0,width,height); if((pane.composed||pane.side==="before")&&root.beforeOverlay)drawPoints(ctx,"before","#4dd4df");if((pane.composed||pane.side==="after")&&root.afterOverlay)drawPoints(ctx,"after","#ffbb55") }
                    }
                    Label { anchors.left:parent.left; anchors.top:parent.top; anchors.margins:5; text:pane.composed?(root.mode==="difference"?"절대 명암 차이 · 결함 변화 판정 아님":"After 기준 · Before 정합 표시"):(pane.side==="before"?"Before · 청록":"After · 주황"); color:theme.text; style:Text.Outline; styleColor:theme.viewer }
                    MouseArea {
                        anchors.fill:parent;hoverEnabled:true;property point last;property bool moved:false
                        onPressed: function(mouse){ last=Qt.point(mouse.x,mouse.y);moved=false }
                        onPositionChanged:function(mouse){root.coordinateText=root.controller.cursor(pane.side,mouse.x*root.dpr,mouse.y*root.dpr);if(pressed){var dx=mouse.x-last.x,dy=mouse.y-last.y;if(Math.abs(dx)+Math.abs(dy)>2)moved=true;if(!root.manual)root.controller.pan(dx*root.dpr,dy*root.dpr);last=Qt.point(mouse.x,mouse.y)} }
                        onReleased:function(mouse){if(root.manual&&!moved&&!pane.composed)root.controller.addPoint(pane.side,mouse.x*root.dpr,mouse.y*root.dpr) }
                        onWheel:function(wheel){root.controller.zoomAt(wheel.angleDelta.y>0?1.2:1/1.2,wheel.x*root.dpr,wheel.y*root.dpr);wheel.accepted=true }
                    }
                }
            }

   Row{anchors.fill:parent;visible:root.mode==="side";spacing:2
    Loader{id:beforePane;width:(parent.width-2)/2;height:parent.height;sourceComponent:imagePane;onLoaded:item.side="before"}
    Loader{id:afterPane;width:(parent.width-2)/2;height:parent.height;sourceComponent:imagePane;onLoaded:item.side="after"}
   }
   Loader{id:comparePane;anchors.fill:parent;visible:root.mode!=="side";sourceComponent:imagePane;onLoaded:item.composed=true}
   BusyIndicator{anchors.centerIn:parent;running:root.state.busy;visible:running}
   AppButton{anchors.centerIn:parent;visible:!root.state.sources.length;theme:root.theme;text:"저장 데이터 불러오기";onClicked:root.actions.projectOpen.trigger()}
  }
  RowLayout{Layout.fillWidth:true
   Repeater{model:[{key:"side",label:"좌우"},{key:"overlay",label:"겹침"},{key:"difference",label:"차이"}]
    AppButton{required property var modelData;theme:root.theme;text:modelData.label;checked:root.mode===modelData.key;enabled:root.state.ready&&(modelData.key==="side"||!!root.state.asset.matrix);onClicked:root.mode=modelData.key}
   }
   Item{Layout.fillWidth:true}
   AppButton{theme:root.theme;text:"취소";visible:root.state.busy;onClicked:root.controller.cancel()}
  }
 }
 property var beforeLayer:beforePane.item?beforePane.item.marksItem:null
 property var afterLayer:afterPane.item?afterPane.item.marksItem:null
 property var compareLayer:comparePane.item?comparePane.item.marksItem:null
 SurfaceDialog{id:result;parent:Overlay.overlay;title:"정합 결과";modal:true;width:500;x:(parent.width-width)/2;y:(parent.height-height)/2;standardButtons:Dialog.Close
  ColumnLayout{width:parent.width;spacing:16
   Text{text:root.state.asset.status==="REJECTED"?"정합 실패":"정합 추정 완료";color:root.theme.text;font.pixelSize:20}
   Text{text:"대응점 "+(root.state.asset.quality?root.state.asset.quality.inlier_count||0:0)+"개";color:root.theme.text;font.pixelSize:16}
   Text{text:"정합 오차 "+(root.state.asset.quality&&typeof root.state.asset.quality.median_error_after_px==="number"?root.state.asset.quality.median_error_after_px.toFixed(2):"—")+" px";color:root.theme.text;font.pixelSize:16}
   Text{text:root.state.asset.quality?(root.state.asset.quality.reasons||[]).join(" · "):"";visible:!!text;color:root.theme.warning;font.pixelSize:13;wrapMode:Text.Wrap;Layout.fillWidth:true}
  }
 }
}
