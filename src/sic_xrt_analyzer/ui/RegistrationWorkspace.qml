import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "registrationWorkspace"
    property QtObject theme
    property QtObject uiState
    property var controller: fileBridge.registration
    property var state: controller.state
    property string mode: "side"
    property real opacityValue: 0.5
    property real divider: 0.5
    property bool manual: method.currentIndex === 4
    property bool beforeOverlay: true
    property bool afterOverlay: true
    property string coordinateText: ""
    property real dpr: uiState.displayPixelRatio
    color: theme.viewer
    function sourceIndex(id) { for (var i=0;i<state.sources.length;i++) if(state.sources[i].id===id) return i; return -1 }
    function selected(side) { var id=side==="before"?state.beforeId:state.afterId; for(var i=0;i<state.sources.length;i++) if(state.sources[i].id===id)return state.sources[i]; return null }
    function choose() { controller.select(beforeChoice.currentIndex>=0 ? state.sources[beforeChoice.currentIndex].id : "", afterChoice.currentIndex>=0 ? state.sources[afterChoice.currentIndex].id : "") }
    function updateFrame() { if(visible && state.ready) controller.requestFrame(Math.round(viewport.width*(mode==="side"?0.5:1)*dpr), Math.round(viewport.height*dpr)) }
    onStateChanged: if(!state.asset.matrix && mode!=="side")mode="side"
    onVisibleChanged: if(visible) { frameTimer.restart() }
    onModeChanged: frameTimer.restart()
    Timer { id: frameTimer; interval: 20; onTriggered: root.updateFrame() }
    Connections { target: root.controller; function onChanged() { beforeLayer.requestPaint(); afterLayer.requestPaint(); compareLayer.requestPaint() } }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 10; spacing: 6
        RowLayout {
            Layout.fillWidth: true
            Label { text: "어닐링 전·후 정합"; color: theme.text; font.pixelSize: 17 }
            Item { Layout.fillWidth: true }
            ComboBox { objectName:"registrationHistory"; model:root.state.history; textRole:"id"; Layout.preferredWidth:180; visible:root.state.history.length>0; onActivated:root.controller.selectAttempt(root.state.history[currentIndex].id) }
            Label { text: "JPG · Before → After 원본 픽셀 좌표"; color: theme.muted }
            Button { text: "프로젝트…"; onClicked: root.Window.window.openProjectWorkspace() }
        }
        GridLayout {
            columns: 4; Layout.fillWidth: true; columnSpacing: 8; rowSpacing: 4
            Label { text: "Before"; color: theme.text }
            ComboBox { id: beforeChoice; objectName: "registrationBefore"; Layout.fillWidth: true; model: root.state.sources; textRole: "name"; currentIndex: root.sourceIndex(root.state.beforeId); onActivated: root.choose() }
            Label { text: "After"; color: theme.text }
            ComboBox { id: afterChoice; objectName: "registrationAfter"; Layout.fillWidth: true; model: root.state.sources; textRole: "name"; currentIndex: root.sourceIndex(root.state.afterId); onActivated: root.choose() }
            Label { Layout.columnSpan: 2; Layout.fillWidth:true; text: { var s=root.selected("before");return s?s.role+" · "+s.width+"×"+s.height+" · "+s.status+" · SHA "+(s.sha?"기록됨":"준비 시 확인")+" · Run "+s.runs:"Before JPG를 선택하세요" }  color:theme.muted; elide:Text.ElideRight }
            Label { Layout.columnSpan: 2; Layout.fillWidth:true; text: { var s=root.selected("after");return s?s.role+" · "+s.width+"×"+s.height+" · "+s.status+" · SHA "+(s.sha?"기록됨":"준비 시 확인")+" · Run "+s.runs:"After JPG를 선택하세요" }  color:theme.muted; elide:Text.ElideRight }
        }
        RowLayout {
            Layout.fillWidth: true
            Button { objectName:"registrationPrepare"; text:"비교 영상 준비"; enabled: !root.state.busy && !uiState.project.busy && !!root.state.beforeId && !!root.state.afterId && root.state.beforeId!==root.state.afterId; onClicked: root.controller.prepare() }
            ComboBox { id: method; objectName:"registrationMethod"; model:["자동 · SIFT", "자동 · ORB", "명암 · Phase", "명암 · ECC", "수동 Landmark"]; Layout.preferredWidth:145; onActivated: if(currentIndex===4)root.controller.beginLandmarks() }
            ComboBox { id: transform; objectName:"registrationModel"; model:["Auto", "Translation", "Rigid", "Similarity", "Affine"]; Layout.preferredWidth:115 }
            Button { objectName:"registrationRun"; text:root.manual?"대응점 계산":"정합 실행"; enabled:root.state.ready && !root.state.busy && !uiState.project.busy && (!root.manual || transform.currentIndex>0); onClicked: root.controller.run(["sift","orb","phase","ecc","manual"][method.currentIndex],["auto","translation","rigid","similarity","affine"][transform.currentIndex]) }
            Button { visible:root.manual; text:"새 대응점"; enabled:!root.state.busy; onClicked:root.controller.beginLandmarks() }
            Button { objectName:"registrationCancel"; text:"취소"; visible:root.state.busy; enabled:root.state.job!=="approve-save"; onClicked:root.controller.cancel() }
            Item { Layout.fillWidth:true }
            Button { text:"Fit"; enabled:root.state.ready; onClicked:root.controller.fit() }
            Button { text:"100%"; enabled:root.state.ready; onClicked:root.controller.zoomAt(1/root.state.zoom, viewport.width*dpr*(root.mode==="side"?.25:.5),viewport.height*dpr/2) }
            Button { text:"400%"; enabled:root.state.ready; onClicked:root.controller.zoomAt(4/root.state.zoom,viewport.width*dpr*(root.mode==="side"?.25:.5),viewport.height*dpr/2) }
        }
        Label { Layout.fillWidth:true; text: root.state.error || root.state.message; color:root.state.error?theme.warning:theme.muted; wrapMode:Text.Wrap; font.pixelSize:11 }
        Item {
            id: viewport; objectName:"registrationViewport"; Layout.fillWidth:true; Layout.fillHeight:true; Layout.minimumHeight:120; clip:true
            onWidthChanged: frameTimer.restart()
            onHeightChanged: frameTimer.restart()
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
            Row { anchors.fill:parent; visible:root.mode==="side"
                Loader { id:beforePane; width:parent.width/2;height:parent.height;sourceComponent:imagePane;onLoaded:item.side="before" }
                Loader { id:afterPane; width:parent.width/2;height:parent.height;sourceComponent:imagePane;onLoaded:item.side="after" }
            }
            Loader { id:comparePane;anchors.fill:parent;visible:root.mode!=="side";sourceComponent:imagePane;onLoaded:item.composed=true }
            Rectangle { x:parent.width*root.divider-2;width:4;height:parent.height;color:theme.accent;visible:root.mode==="split"
                MouseArea { anchors.fill:parent;anchors.margins:-8;cursorShape:Qt.SizeHorCursor;onPositionChanged:function(mouse){if(pressed)root.divider=Math.max(.02,Math.min(.98,(parent.x+mouse.x)/viewport.width))} }
            }
            Rectangle { anchors.fill:parent;visible:root.state.busy;color:"#dd111518"
                Column { anchors.centerIn:parent;spacing:8;BusyIndicator { anchors.horizontalCenter:parent.horizontalCenter;running:parent.parent.visible } Label {text:root.state.job==="prepare"?"원본 SHA 확인·캐시 준비 중…":root.state.job==="approve-save"?"승인 및 프로젝트 저장 중…":"정합 계산 중…";color:theme.text} }
            }
            Label { anchors.centerIn:parent;visible:!root.state.ready&&!root.state.busy;text:"프로젝트의 JPG 두 장을 선택하고 비교 영상을 준비하세요";color:theme.muted }
        }
        RowLayout {
            Layout.fillWidth:true
            Repeater { model:[{key:"side",label:"나란히"},{key:"overlay",label:"겹쳐 보기"},{key:"split",label:"분할 비교"},{key:"difference",label:"차이 보기"}]
                Button { required property var modelData; text:modelData.label;objectName:"registrationMode-"+modelData.key;checkable:true;checked:root.mode===modelData.key;enabled:root.state.ready&&(modelData.key==="side"||!!root.state.asset.matrix);onClicked:root.mode=modelData.key }
            }
            Slider { objectName:"registrationOpacity";Layout.fillWidth:true;visible:root.mode==="overlay";from:0;to:1;value:root.opacityValue;onMoved:root.opacityValue=value }
            CheckBox { text:"Before 근거";checked:root.beforeOverlay;onToggled:{root.beforeOverlay=checked;beforeLayer.requestPaint();compareLayer.requestPaint()} }
            CheckBox { text:"After 근거";checked:root.afterOverlay;onToggled:{root.afterOverlay=checked;afterLayer.requestPaint();compareLayer.requestPaint()} }
        }
        Label { Layout.fillWidth:true; text:Math.round(root.state.zoom*100)+"% · "+root.coordinateText+" · "+root.state.levels.join(" / ")+" · "+root.state.status+" · 이력 "+root.state.history.length; color:theme.muted;elide:Text.ElideRight }
        RowLayout {
            Layout.fillWidth:true
            Label { Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:11;color:theme.muted;text:{var q=root.state.asset.quality||{} return "대응 "+(q.candidate_count||0)+" · Inlier "+(q.inlier_count||0)+" · 중앙 오차 "+(q.median_error_after_px===undefined||q.median_error_after_px===null?"N/A":q.median_error_after_px.toFixed(2)+" After px")+" · 공통 영역 "+(q.overlap_target_fraction===undefined?"N/A":(100*q.overlap_target_fraction).toFixed(1)+"%")+" · 실제 정합 정확도는 독립 검증 필요"} }
            TextField { id:reviewer;objectName:"registrationReviewer";placeholderText:"로컬 검수자 ID";Layout.preferredWidth:130 }
            Button { objectName:"registrationApprove";text:"검토 승인·저장";enabled:root.state.status==="NEEDS_REVIEW"&&root.state.ready&&!root.state.busy&&!uiState.project.busy&&reviewer.text.trim().length>0;onClicked:root.controller.approveAndSave(reviewer.text) }
        }
        Frame {
            visible:root.manual;Layout.fillWidth:true;Layout.preferredHeight:105
            RowLayout { anchors.fill:parent
                Label { text:"Before 클릭 → After 클릭
역할은 사용자가 지정합니다
번호별 원본 좌표를 수정 가능";color:theme.muted;font.pixelSize:11 }
                ListView { id:points;Layout.fillWidth:true;Layout.fillHeight:true;clip:true;model:root.state.landmarks
                    delegate:RowLayout { required property int index;required property var modelData;spacing:4
                        Label { text:"#"+(index+1);color:theme.text }
                        Repeater { model:[{side:"before",axis:0},{side:"before",axis:1},{side:"after",axis:0},{side:"after",axis:1}]
                            TextField { required property var modelData;Layout.preferredWidth:70;text:points.model[index][modelData.side][modelData.axis].toFixed(2);validator:DoubleValidator {} onEditingFinished:{var p=points.model[index][modelData.side].slice();p[modelData.axis]=Number(text);root.controller.editPoint(index,modelData.side,p[0],p[1])} }
                        }
                        Button { text:"삭제";onClicked:root.controller.deletePoint(index) }
                    }
                    ScrollBar.vertical:ScrollBar {}
                }
            }
        }
    }
    property var beforeLayer: beforePane.item ? beforePane.item.marksItem : null
    property var afterLayer: afterPane.item ? afterPane.item.marksItem : null
    property var compareLayer: comparePane.item ? comparePane.item.marksItem : null
}
