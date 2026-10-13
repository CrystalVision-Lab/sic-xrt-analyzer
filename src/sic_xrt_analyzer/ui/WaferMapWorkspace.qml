import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "waferMapWorkspace"
    property QtObject theme
    property QtObject uiState
    property var controller: fileBridge.waferMap
    property var state: controller.state
    property bool editTiles: false
    property var loadedUrls: []
    signal projectRequested()
    color: theme.viewer
    function indexOf(model,key,value) { for(var i=0;i<model.length;i++)if(model[i][key]===value)return i;return -1 }
    function refresh() { if(visible)controller.requestFrame(map.width,map.height) }
    onVisibleChanged: {controller.activate(visible);if(visible)Qt.callLater(refresh)}
    Component.onCompleted: {controller.activate(visible);if(visible)Qt.callLater(refresh)}
    onStateChanged: {
        map.requestPaint()
        var tiles=state.tiles||[]
        var urls=[]
        for(var i=0;i<tiles.length;i++)if(tiles[i].preview)urls.push("image://tiff/wafer-"+tiles[i].source_id+"?r="+state.revision)
        for(i=0;i<loadedUrls.length;i++)if(urls.indexOf(loadedUrls[i])<0)map.unloadImage(loadedUrls[i])
        loadedUrls=urls
        for(i=0;i<urls.length;i++)if(!map.isImageLoaded(urls[i]))map.loadImage(urls[i])
    }
    ColumnLayout {
        anchors.fill: parent;anchors.margins:10;spacing:8
        RowLayout {
            Layout.fillWidth:true
            Text { text:"Wafer Map";color:root.theme.text;font.pixelSize:18 }
            Text { text:root.state.mode==="PHYSICAL" ? "물리 좌표 · 미검증 배치는 별도 표시" : "임시 배치 · 물리 좌표 미검증";color:root.theme.warning;Layout.fillWidth:true;elide:Text.ElideRight }
            Button {objectName:"mapFit";text:"화면 맞춤";onClicked:root.controller.fit()}
            Button {text:"프로젝트…";onClicked:root.projectRequested()}
        }
        RowLayout {
            Layout.fillWidth:true
            ComboBox {objectName:"mapGroup";Layout.fillWidth:true;model:root.state.groups||[];textRole:"label";currentIndex:root.indexOf(model,"id",root.state.group_id);onActivated:root.controller.selectGroup(model[currentIndex].id)}
            Button {objectName:"mapAddGroup";text:"관측 그룹 추가";enabled:root.state.available&&!root.state.busy;onClicked:groupDialog.open()}
            ComboBox {objectName:"mapHistory";Layout.preferredWidth:180;model:root.state.history||[];textRole:"label";displayText:"배치 이력 ▾";onActivated:root.controller.restoreHistory(model[currentIndex].ref)}
            Button {objectName:"mapSave";text:root.state.dirty ? "배치 저장 *" : "배치 저장";enabled:root.state.available&&root.state.job!=="save";onClicked:saveDialog.open()}
        }
        RowLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;spacing:8
            Rectangle {
                color:root.theme.panel;Layout.preferredWidth:225;Layout.fillHeight:true
                ScrollView {
                    anchors.fill:parent;anchors.margins:8;clip:true
                    ColumnLayout {
                        width:225-16;spacing:6
                        Text {text:"프로젝트 이미지 · 미배치 포함";color:root.theme.text;font.bold:true;Layout.fillWidth:true;wrapMode:Text.Wrap}
                        Repeater {
                            model:root.state.sources||[]
                            Button {
                                required property var modelData
                                objectName:"mapSource-"+modelData.id
                                Layout.fillWidth:true;checkable:true;checked:root.state.selected===modelData.id
                                text:modelData.name+"\n"+modelData.format+" · "+modelData.width+"×"+modelData.height+" · Run "+modelData.run_count+"\n"+(modelData.format==="TIFF"?"Stack / 향후 3D 원본":modelData.status==="UNPLACED"?"미배치":modelData.status==="VERIFIED"?"좌표 근거 검증됨":"임시/미검증 배치")
                                contentItem:Text {text:parent.text;color:root.theme.text;font.pixelSize:11;wrapMode:Text.Wrap;elide:Text.ElideRight}
                                onClicked:root.controller.select(modelData.id)
                            }
                        }
                        Text {text:"표시 Run · 이미지당 하나";color:root.theme.muted;Layout.topMargin:8}
                        ComboBox {objectName:"mapRun";Layout.fillWidth:true;model:root.state.runs||[];textRole:"label";currentIndex:root.indexOf(model,"id",root.state.run_id);onActivated:root.controller.setRun(root.state.selected,model[currentIndex].id)}
                        Button {text:"선택 이미지 결과 숨김";Layout.fillWidth:true;enabled:!!root.state.selected;onClicked:root.controller.setRun(root.state.selected,"")}
                        Text {text:"모델 후보 · 실제 결함 수 아님";color:root.theme.muted;font.pixelSize:11;Layout.fillWidth:true;wrapMode:Text.Wrap}
                        Repeater {
                            model:[{key:"BPD",label:"BPD 후보",color:"#f6b85b"},{key:"TED",label:"TED 후보",color:"#58ced6"},{key:"TSD",label:"TSD 후보",color:"#c798f9"},{key:"reviews",label:"검수 / 수정 Geometry",color:"#92db7a"},{key:"human",label:"HUMAN 결함 객체",color:"#f4efff"},{key:"experimental",label:"실험적 구조 제안",color:"#fa8bad"},{key:"model_geometry",label:"원본 모델 Geometry",color:"#7b8d99"}]
                            CheckBox {required property var modelData;objectName:"mapLayer-"+modelData.key;text:modelData.label;checked:root.state.layers ? !!root.state.layers[modelData.key] : false;Layout.fillWidth:true;onToggled:root.controller.setLayer(modelData.key,checked);contentItem:Text {text:parent.text;color:modelData.color;font.pixelSize:11;leftPadding:27;verticalAlignment:Text.AlignVCenter}}
                        }
                        Text {Layout.fillWidth:true;wrapMode:Text.Wrap;color:root.theme.text;font.pixelSize:11;text:"선택 그룹 관측 후보\nBPD "+((root.state.summary||{}).BPD||0)+" · TED "+((root.state.summary||{}).TED||0)+" · TSD "+((root.state.summary||{}).TSD||0)+"\nHUMAN "+((root.state.summary||{}).human||0)+" · 실험 객체 "+((root.state.summary||{}).experimental||0)+"\n검수 충돌 "+((root.state.review_summary||{}).conflicts||0)}
                        Text {text:"선택 위치 / 좌표 근거";color:root.theme.text;font.bold:true;Layout.topMargin:8}
                        Text {Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:10;color:root.theme.muted;text:"그룹: "+(root.state.group ? root.state.group.label : "—")+"\nWafer: "+(root.state.group && root.state.group.wafer_id || "미확정")+" · "+(root.state.unit || "relative")+"\n좌표계: "+(root.state.group ? root.state.group.coordinate_system : "—")+"\n축: "+(root.state.group ? root.state.group.axes : "—")+"\n원점: "+(root.state.group ? root.state.group.origin : "—")}
                        Text {Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:10;color:root.theme.warning;text:root.state.placement && root.state.placement.source_id ? root.state.placement.status+" · "+root.state.placement.editor+"\n위치 "+root.state.params[0].toFixed(3)+", "+root.state.params[1].toFixed(3)+" · 회전 "+root.state.params[2].toFixed(2)+"°\n원본 px 크기 "+root.state.params[3].toPrecision(5)+" × "+root.state.params[4].toPrecision(5) : "선택 이미지 미배치"}
                        Text {Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:10;color:root.theme.text;text:root.state.target && root.state.target.target_id ? "선택: "+root.state.target.target_type+" · "+root.state.target.label+"\nID "+root.state.target.target_id+"\nGeometry "+root.state.target.geometry_id : "후보·객체를 누르면 원본 결과 위치로 이동할 수 있습니다."}
                        Text {text:"Run 중복 합산·물리 결함 Merge 없음\n빈 영역은 미관측 / 결과 없음\n물리 위치·Coverage 검증 전 Density/Heatmap 비활성";Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:10;color:root.theme.muted}
                    }
                }
            }
            Rectangle {
                Layout.fillWidth:true;Layout.fillHeight:true;color:root.theme.viewer;clip:true
                Canvas {
                    id:map;objectName:"waferMapCanvas";anchors.fill:parent
                    onWidthChanged:root.refresh();onHeightChanged:root.refresh();onImageLoaded:requestPaint()
                    onPaint: {
                        var c=getContext("2d");c.reset();c.fillStyle=root.theme.viewer;c.fillRect(0,0,width,height)
                        var zoom=root.state.zoom||1,centre=root.state.centre||[0,0],step=Math.pow(10,Math.floor(Math.log(80/zoom)/Math.LN10));var pixels=step*zoom
                        c.strokeStyle="#253037";c.lineWidth=1
                        for(var x=(width/2-centre[0]*zoom)%pixels;x<width;x+=pixels){c.beginPath();c.moveTo(x,0);c.lineTo(x,height);c.stroke()}
                        for(var y=(height/2-centre[1]*zoom*(root.state.group && root.state.group.axes==="X_RIGHT_Y_UP"?-1:1))%pixels;y<height;y+=pixels){c.beginPath();c.moveTo(0,y);c.lineTo(width,y);c.stroke()}
                        var outline=root.state.outline
                        if(outline){c.strokeStyle="#93c2d0";c.beginPath();c.arc(outline.centre[0],outline.centre[1],outline.radius,0,2*Math.PI);c.stroke()}
                        var tiles=root.state.tiles||[]
                        for(var i=0;i<tiles.length;i++){
                            var t=tiles[i],b=t.border,m=t.matrix,url="image://tiff/wafer-"+t.source_id+"?r="+root.state.revision
                            if(t.preview&&isImageLoaded(url)){c.save();c.setTransform(m[0][0],m[1][0],m[0][1],m[1][1],m[0][2],m[1][2]);c.globalAlpha=.65;c.drawImage(url,-.5,-.5,t.width,t.height);c.restore()}
                            c.strokeStyle=t.source_id===root.state.selected ? "#4ad2df" : t.status==="VERIFIED" ? "#8cdb9d" : "#dfb260";c.lineWidth=t.source_id===root.state.selected?3:1.5
                            c.beginPath();c.moveTo(b[0][0],b[0][1]);for(var j=1;j<b.length;j++)c.lineTo(b[j][0],b[j][1]);c.closePath();c.stroke()
                            c.fillStyle=c.strokeStyle;c.font="11px sans-serif";c.fillText(t.name+(t.preview?"":" · "+t.availability),b[0][0]+4,b[0][1]+14)
                        }
                        var rows=root.state.paths||[],colours={BPD:"#f6b85b",TED:"#58ced6",TSD:"#c798f9",reviews:"#92db7a",human:"#f4efff",experimental:"#fa8bad",model_geometry:"#7b8d99"}
                        for(i=0;i<rows.length;i++){
                            var r=rows[i];c.strokeStyle=colours[r.layer]||"#eee";c.fillStyle=c.strokeStyle;c.lineWidth=r.layer==="reviews"?2:1
                            for(j=0;j<r.paths.length;j++){
                                var p=r.paths[j]
                                c.beginPath();if(p.length===1){c.arc(p[0][0],p[0][1],r.layer==="reviews"?4:2.5,0,2*Math.PI);if(r.layer==="reviews")c.stroke();else c.fill()}
                                else {c.moveTo(p[0][0],p[0][1]);for(var k=1;k<p.length;k++)c.lineTo(p[k][0],p[k][1]);c.stroke()}
                            }
                        }
                        c.fillStyle=root.theme.muted;c.font="11px sans-serif";c.fillText(root.state.mode==="PHYSICAL" ? "단위 "+root.state.unit+" · "+root.state.group.coordinate_system : "상대 좌표 · 물리 위치 아님",10,height-28)
                        c.fillText("표시 생략 "+(root.state.omitted||0)+"점 · 대형 형상 생략 "+((root.state.summary||{}).omitted_large_shapes||0)+"개 · 원본 집계 유지 · Mask는 외접 영역",10,height-12)
                    }
                    MouseArea {
                        anchors.fill:parent;acceptedButtons:Qt.LeftButton|Qt.RightButton;preventStealing:true
                        property real px:0;property real py:0;property bool tileDrag:false
                        onPressed:function(mouse){px=mouse.x;py=mouse.y;tileDrag=root.editTiles&&mouse.button===Qt.LeftButton&&root.controller.hit(mouse.x,mouse.y);if(tileDrag)root.controller.beginMove();if(!root.editTiles&&mouse.button===Qt.LeftButton)root.controller.hit(mouse.x,mouse.y)}
                        onPositionChanged:function(mouse){if(pressed){var dx=mouse.x-px,dy=mouse.y-py;px=mouse.x;py=mouse.y;if(tileDrag)root.controller.move(dx,dy);else root.controller.pan(dx,dy)}}
                        onReleased:root.controller.endMove()
                        onCanceled:root.controller.endMove()
                        onDoubleClicked:function(mouse){if(root.controller.hit(mouse.x,mouse.y))root.controller.openSelected(true)}
                        onWheel:function(wheel){root.controller.zoomAt(Math.pow(1.15,wheel.angleDelta.y/120),wheel.x,wheel.y);wheel.accepted=true}
                    }
                }
                Text {anchors.centerIn:parent;text:root.state.available ? ((root.state.tiles||[]).length?"":"배치된 JPG가 없습니다 · 왼쪽 이미지 선택 후 배치") : "분석 프로젝트를 열어주세요";color:root.theme.muted;wrapMode:Text.Wrap;width:parent.width-30;horizontalAlignment:Text.AlignHCenter}
                BusyIndicator {anchors.right:parent.right;anchors.top:parent.top;width:30;height:30;running:root.state.busy;visible:running}
            }
        }
        Flow {
            Layout.fillWidth:true;spacing:6
            Layout.preferredHeight:childrenRect.height
            Button {objectName:"mapEdit";text:"타일 이동";checkable:true;checked:root.editTiles;onToggled:root.editTiles=checked}
            Button {objectName:"mapPlace";text:"위치·회전·크기";enabled:!!root.state.selected;onClicked:placementDialog.open()}
            Button {objectName:"mapVerify";text:"물리 기준점 검증";enabled:root.state.mode==="PHYSICAL"&&!!root.state.placement.source_id;onClicked:verifyDialog.open()}
            Button {objectName:"mapUnplace";text:"미배치로";enabled:!!root.state.placement.source_id;onClicked:root.controller.unplace()}
            Button {objectName:"mapReset";text:"저장 위치로";enabled:!!root.state.selected;onClicked:root.controller.resetPlacement()}
            Button {objectName:"mapUndo";text:"Undo";onClicked:root.controller.undo()}
            Button {objectName:"mapDiscard";text:"취소";enabled:root.state.job!=="save";onClicked:root.controller.discard()}
            Button {objectName:"mapOpen";text:"원본";enabled:!!root.state.selected;onClicked:root.controller.openSelected(false)}
            Button {objectName:"mapResult";text:"결과·선택 위치";enabled:!!root.state.selected;onClicked:root.controller.openSelected(true)}
            Button {objectName:"mapCompare";text:"전·후 비교";enabled:!!root.state.selected;onClicked:compareDialog.open()}
        }
        Text {Layout.fillWidth:true;color:root.state.error ? root.theme.error : root.theme.muted;font.pixelSize:11;wrapMode:Text.Wrap;text:root.state.error||root.state.message||""}
    }
    Dialog {
        id:saveDialog;objectName:"mapSaveDialog";title:"배치와 선택 Run·레이어 저장";modal:true;anchors.centerIn:parent;standardButtons:Dialog.Save|Dialog.Cancel
        ColumnLayout {Text {text:"로컬 편집자 ID · 공식 과학 검증/서버 업로드 아님";color:root.theme.muted} TextField {id:editor;objectName:"mapEditor";placeholderText:"배치 편집자 식별값";Layout.fillWidth:true}}
        onAccepted:root.controller.save(editor.text)
    }
    Dialog {
        id:placementDialog;objectName:"mapPlacementDialog";title:"원본 픽셀 → 지도 배치";modal:true;anchors.centerIn:parent;width:390;standardButtons:Dialog.Apply|Dialog.Cancel
        onOpened:{var p=root.state.params||[0,0,0,.025,.025];positionX.text=p[0];positionY.text=p[1];angle.text=p[2];scaleX.text=p[3];scaleY.text=p[4]}
        GridLayout {columns:2;width:parent.width
            Text {text:"원본 (0,0)의 지도 X";color:root.theme.text} TextField {id:positionX;objectName:"mapX";Layout.fillWidth:true}
            Text {text:"원본 (0,0)의 지도 Y";color:root.theme.text} TextField {id:positionY;objectName:"mapY";Layout.fillWidth:true}
            Text {text:"회전 각도 °";color:root.theme.text} TextField {id:angle;objectName:"mapAngle";Layout.fillWidth:true}
            Text {text:"원본 1px의 X축 크기";color:root.theme.text} TextField {id:scaleX;objectName:"mapScaleX";Layout.fillWidth:true}
            Text {text:"원본 1px의 Y축 크기";color:root.theme.text} TextField {id:scaleY;objectName:"mapScaleY";Layout.fillWidth:true}
            Text {Layout.columnSpan:2;text:root.state.mode==="PHYSICAL" ? "단위 "+root.state.unit+" · 독립 기준점 검증 전 미검증" : "단위 없는 표시 크기 · Calibration 아님";color:root.theme.warning;wrapMode:Text.Wrap;Layout.fillWidth:true}
        }
        onApplied:{root.controller.place(Number(positionX.text),Number(positionY.text),Number(angle.text),Number(scaleX.text),Number(scaleY.text));close();Qt.callLater(function(){root.controller.fit()})}
    }
    Dialog {
        id:groupDialog;objectName:"mapGroupDialog";title:"관측 그룹 / 좌표계";modal:true;anchors.centerIn:parent;width:490;height:Math.min(600,root.height-20);standardButtons:Dialog.Ok|Dialog.Cancel
        ScrollView {anchors.fill:parent;clip:true
            GridLayout {columns:2;width:groupDialog.width-45
                Text {text:"이름";color:root.theme.text} TextField {id:groupName;objectName:"mapGroupName";Layout.fillWidth:true;placeholderText:"명시적으로 지정한 관측 그룹"}
                Text {text:"좌표 모드";color:root.theme.text} ComboBox {id:groupMode;objectName:"mapGroupMode";model:["TEMPORARY","PHYSICAL"];Layout.fillWidth:true}
                Text {text:"Wafer ID";color:root.theme.text} TextField {id:waferId;objectName:"mapWaferId";Layout.fillWidth:true;enabled:groupMode.currentIndex===1}
                Text {text:"좌표계 ID";color:root.theme.text} TextField {id:coordinateId;objectName:"mapCoordinateId";Layout.fillWidth:true;enabled:groupMode.currentIndex===1}
                Text {text:"단위";color:root.theme.text} ComboBox {id:unit;model:["mm","um"];Layout.fillWidth:true;enabled:groupMode.currentIndex===1}
                Text {text:"원점 정의";color:root.theme.text} TextField {id:origin;objectName:"mapOrigin";Layout.fillWidth:true;placeholderText:"측정 기준점 / 중심 등"}
                Text {text:"축 방향";color:root.theme.text} ComboBox {id:axes;model:["X_RIGHT_Y_DOWN","X_RIGHT_Y_UP"];Layout.fillWidth:true;enabled:groupMode.currentIndex===1}
                Text {text:"좌표계·측정 근거";color:root.theme.text} TextArea {id:evidence;objectName:"mapEvidence";Layout.fillWidth:true;Layout.preferredHeight:75;wrapMode:TextArea.Wrap}
                Text {text:"실측 원형 외곽 (선택)";color:root.theme.text} TextField {id:geometry;objectName:"mapOutline";Layout.fillWidth:true;placeholderText:"중심 X Y 반경 · 단위 동일";enabled:groupMode.currentIndex===1}
                Text {text:"외곽 검수자";color:root.theme.text} TextField {id:geometryReviewer;objectName:"mapOutlineReviewer";Layout.fillWidth:true;enabled:groupMode.currentIndex===1}
                Text {Layout.columnSpan:2;Layout.fillWidth:true;wrapMode:Text.Wrap;text:"실제 측정 근거가 없으면 임시 그룹을 사용하세요. 물리 그룹 생성만으로 이미지 위치가 검증되지는 않습니다.";color:root.theme.warning}
            }
        }
        onAccepted:root.controller.addGroup(groupName.text,groupMode.currentText,waferId.text,coordinateId.text,unit.currentText,origin.text,axes.currentText,evidence.text,geometry.text,geometryReviewer.text)
    }
    Dialog {
        id:verifyDialog;objectName:"mapVerifyDialog";title:"독립 기준점으로 배치 검증";modal:true;anchors.centerIn:parent;width:460;standardButtons:Dialog.Ok|Dialog.Cancel
        ColumnLayout {width:parent.width
            Text {text:"최소 비공선 3쌍 · 각 줄: 원본 X Y 지도 X Y";color:root.theme.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
            TextArea {id:landmarks;objectName:"mapCalibrationPoints";Layout.preferredHeight:125;Layout.fillWidth:true;placeholderText:"10 10 0.1 0.1\n…";wrapMode:TextArea.Wrap}
            TextField {id:calibrationSource;objectName:"mapCalibrationSource";placeholderText:"독립 측정 출처 / Calibration 근거";Layout.fillWidth:true}
            TextField {id:calibrationReviewer;objectName:"mapCalibrationReviewer";placeholderText:"검수자 식별값";Layout.fillWidth:true}
            TextField {id:calibrationTolerance;objectName:"mapCalibrationTolerance";placeholderText:"지도 단위 허용 오차 (최대 10px 크기)";Layout.fillWidth:true}
            Text {text:"로컬 근거 검사는 공식 전문가 과학 검증을 자동 증명하지 않습니다.";color:root.theme.warning;wrapMode:Text.Wrap;Layout.fillWidth:true}
        }
        onAccepted:root.controller.verifyPlacement(calibrationSource.text,calibrationReviewer.text,landmarks.text,Number(calibrationTolerance.text))
    }
    Dialog {
        id:compareDialog;objectName:"mapCompareDialog";title:"전후 JPG 비교 연결";modal:true;anchors.centerIn:parent;width:420;standardButtons:Dialog.Close
        ColumnLayout {width:parent.width
            ComboBox {id:otherSource;Layout.fillWidth:true;model:(root.state.sources||[]).filter(function(s){return s.format==="JPEG"&&s.id!==root.state.selected});textRole:"name"}
            Button {objectName:"mapCompareOpen";text:"TD-10 정합 작업공간";Layout.fillWidth:true;enabled:otherSource.currentIndex>=0;onClicked:{root.controller.compare(otherSource.model[otherSource.currentIndex].id);compareDialog.close()}}
            ComboBox {id:relation;Layout.fillWidth:true;model:root.state.registrations||[];textRole:"label"}
            TextField {id:sameTarget;Layout.fillWidth:true;placeholderText:"동일 Wafer·관측 대상 독립 근거"}
            Button {text:"검증 Target 배치와 합성 제안";Layout.fillWidth:true;enabled:relation.currentIndex>=0;onClicked:{root.controller.composeRegistration(relation.model[relation.currentIndex].ref,sameTarget.text);compareDialog.close()}}
            Text {text:"실패·미승인 정합은 합성 불가. 합성 후에도 Source 기준점 검증 전 UNVERIFIED.";color:root.theme.warning;Layout.fillWidth:true;wrapMode:Text.Wrap}
        }
    }
}
