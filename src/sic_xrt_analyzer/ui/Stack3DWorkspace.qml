import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id:root;objectName:"stack3dWorkspace"
    property QtObject theme
    property QtObject uiState
    property var controller:fileBridge.stack3d
    property var state:controller.state
    property var scene:controller.scene
    signal projectRequested()
    spacing:8
    function indexOf(model,id){for(var i=0;i<model.length;i++)if(model[i].id===id)return i;return -1}
    function syncFields(){var s=root.state;rx.text=s.roi[0];ry.text=s.roi[1];rw.text=s.roi[2];rh.text=s.roi[3];first.text=s.page_range[0]+1;last.text=s.page_range[1]+1;pageStep.text=s.page_range[2];xyStep.text=s.xy_step;minimum.text=s.window[0];maximum.text=s.window[1]}
    Component.onCompleted:{controller.setActive(visible);syncFields()}
    onVisibleChanged:controller.setActive(visible)
    Connections {target:root.controller;function onChanged(){if(!rx.activeFocus&&!ry.activeFocus&&!rw.activeFocus&&!rh.activeFocus&&!first.activeFocus&&!last.activeFocus&&!pageStep.activeFocus&&!xyStep.activeFocus)root.syncFields()}}
    RowLayout {
        Layout.fillWidth:true
        Text {text:"TIFF Stack 3D";color:root.theme.text;font.pixelSize:17}
        Text {Layout.fillWidth:true;wrapMode:Text.Wrap;text:root.state.physical?"검증된 기존 Source Calibration · "+((root.scene.mapping||({})).unit||"단위 준비 중"):"페이지 기반 3D 시각화 · 실제 깊이 간격 미검증";color:root.theme.warning;font.pixelSize:11}
        Button {text:"프로젝트…";onClicked:root.projectRequested()}
        Button {objectName:"stack3dReset";text:"Fit / View Reset";enabled:root.state.ready;onClicked:root.controller.resetView()}
    }
    RowLayout {
        Layout.fillWidth:true
        visible:root.state.busy||!!root.state.error
        BusyIndicator {running:root.state.busy;visible:running;Layout.preferredWidth:22;Layout.preferredHeight:22}
        Text {Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:11;color:root.state.error?root.theme.warning:root.theme.accent;text:root.state.error||(root.state.progress[2]+" · "+root.state.progress[0]+" / "+root.state.progress[1])}
    }
    RowLayout {
        Layout.fillWidth:true;Layout.fillHeight:true;spacing:8
        ScrollView {
            objectName:"stack3dControls"
            Layout.preferredWidth:260;Layout.minimumWidth:250;Layout.fillHeight:true;clip:true
            ColumnLayout {
                width:250;spacing:8
                Text {text:"TIFF 원본";color:root.theme.text}
                ComboBox {objectName:"stack3dSource";Layout.fillWidth:true;model:root.state.sources||[];textRole:"name";currentIndex:root.indexOf(model,root.state.selected);enabled:root.state.job!=="save";onActivated:root.controller.selectSource(model[currentIndex].id)}
                Text {Layout.fillWidth:true;wrapMode:Text.Wrap;color:root.theme.muted;font.pixelSize:11;text:(root.state.source.name||"원본 없음")+"
"+(root.state.source.width||0)+" × "+(root.state.source.height||0)+" · "+(root.state.source.pages||0)+" pages · "+(root.state.source.dtype||"—")+"
"+(root.state.source.status||"—")+" · Source "+(root.state.source.source_id||"—")+"
SHA "+(root.state.source.sha256||"생성 시 원본 확인")}
                Text {text:"ROI · 원본 픽셀 사각형";color:root.theme.text}
                GridLayout {columns:4;Layout.fillWidth:true
                    Text {text:"X";color:root.theme.muted} TextField {id:rx;objectName:"stack3dRoiX";Layout.preferredWidth:80;selectByMouse:true}
                    Text {text:"Y";color:root.theme.muted} TextField {id:ry;objectName:"stack3dRoiY";Layout.preferredWidth:80;selectByMouse:true}
                    Text {text:"W";color:root.theme.muted} TextField {id:rw;objectName:"stack3dRoiW";Layout.preferredWidth:80;selectByMouse:true}
                    Text {text:"H";color:root.theme.muted} TextField {id:rh;objectName:"stack3dRoiH";Layout.preferredWidth:80;selectByMouse:true}
                }
                Button {objectName:"stack3dViewerRoi";text:"현재 2D 사각형 ROI 사용";Layout.fillWidth:true;enabled:root.uiState.tiffMode&&root.uiState.hasRoi;onClicked:root.controller.useViewerRoi(root.uiState.roiX,root.uiState.roiY,root.uiState.roiWidth,root.uiState.roiHeight)}
                Button {text:"선택 ImageJ 사각형 ROI";Layout.fillWidth:true;enabled:root.uiState.tiffMode;onClicked:root.controller.useImportedRectangle()}
                Text {text:"Page Range · 1-based 입력";color:root.theme.text}
                GridLayout {columns:4;Layout.fillWidth:true
                    Text {text:"시작";color:root.theme.muted} TextField {id:first;objectName:"stack3dFirst";Layout.preferredWidth:70;selectByMouse:true}
                    Text {text:"마지막";color:root.theme.muted} TextField {id:last;objectName:"stack3dLast";Layout.preferredWidth:70;selectByMouse:true}
                    Text {text:"간격";color:root.theme.muted} TextField {id:pageStep;objectName:"stack3dPageStep";Layout.preferredWidth:70;selectByMouse:true}
                    Text {text:"XY 샘플";color:root.theme.muted} TextField {id:xyStep;objectName:"stack3dXYStep";Layout.preferredWidth:70;selectByMouse:true}
                }
                Button {objectName:"stack3dApplySelection";text:"선택·예상 크기 확인";Layout.fillWidth:true;enabled:!!root.state.selected&&!root.state.busy;onClicked:root.controller.configure(Number(rx.text),Number(ry.text),Number(rw.text),Number(rh.text),Number(first.text)-1,Number(last.text)-1,Number(pageStep.text),Number(xyStep.text))}
                Text {Layout.fillWidth:true;wrapMode:Text.Wrap;color:root.theme.muted;font.pixelSize:11;text:root.state.estimate_error||((root.state.estimate.shape||[]).join(" × ")+" [K,Y,X]
"+((root.state.estimate.raw_bytes||0)/1048576).toFixed(2)+" / 64 MiB 원본 · 단일 Volume
샘플링된 원본 페이지/픽셀 매핑 유지")}
                RowLayout {Layout.fillWidth:true
                    Button {objectName:"stack3dGenerate";text:"3D 생성";Layout.fillWidth:true;enabled:!!root.state.selected&&root.state.job!=="save";onClicked:{if(root.controller.configure(Number(rx.text),Number(ry.text),Number(rw.text),Number(rh.text),Number(first.text)-1,Number(last.text)-1,Number(pageStep.text),Number(xyStep.text)))root.controller.generate()}}
                    Button {objectName:"stack3dCancel";text:"취소";enabled:root.state.busy;onClicked:root.controller.cancel()}
                }
                ProgressBar {objectName:"stack3dProgress";Layout.fillWidth:true;visible:root.state.busy;from:0;to:Math.max(1,root.state.progress[1]);value:root.state.progress[0]}
                Text {Layout.fillWidth:true;wrapMode:Text.Wrap;visible:root.state.busy;color:root.theme.accent;text:root.state.progress[2]+" "+root.state.progress[0]+" / "+root.state.progress[1]}
                ComboBox {objectName:"stack3dMode";Layout.fillWidth:true;model:["Indexed Stack · 기본","Physical · 기존 검증 근거 필요"];currentIndex:root.state.physical?1:0;onActivated:root.controller.setPhysical(currentIndex===1)}
                Text {text:root.state.physical_status;Layout.fillWidth:true;wrapMode:Text.Wrap;color:root.theme.warning;font.pixelSize:10}
                Text {text:"표시 Window · 원본 uint16 유지";color:root.theme.text}
                RowLayout {Layout.fillWidth:true
                    TextField {id:minimum;objectName:"stack3dWindowMin";Layout.fillWidth:true;selectByMouse:true}
                    TextField {id:maximum;objectName:"stack3dWindowMax";Layout.fillWidth:true;selectByMouse:true}
                    Button {text:"적용";enabled:root.state.ready;onClicked:root.controller.setWindow(Number(minimum.text),Number(maximum.text))}
                }
                Text {text:"수동 페이지 관측 Track";color:root.theme.text}
                TextField {id:reviewer;objectName:"stack3dReviewer";placeholderText:"연구원 / 검수자 ID";Layout.fillWidth:true}
                TextField {id:trackName;objectName:"stack3dTrackName";placeholderText:"구조 이름 (결함 자동 확정 아님)";Layout.fillWidth:true}
                Button {objectName:"stack3dNewTrack";text:"새 수동 Track";Layout.fillWidth:true;enabled:root.state.project&&root.state.ready;onClicked:root.controller.newTrack(trackName.text,reviewer.text)}
                ComboBox {objectName:"stack3dTrack";Layout.fillWidth:true;model:root.state.tracks||[];textRole:"name";currentIndex:root.indexOf(model,root.state.track_id);onActivated:root.controller.selectTrack(model[currentIndex].id)}
                ComboBox {id:status;objectName:"stack3dLinkStatus";Layout.fillWidth:true;model:["PROPOSED","REVIEWED","UNCERTAIN"]}
                RowLayout {Layout.fillWidth:true
                    Button {objectName:"stack3dRecordPoint";text:"현재 점 기록";enabled:root.state.ready&&!!root.state.track_id;onClicked:root.controller.record("POINT",reviewer.text,status.currentText)}
                    Button {objectName:"stack3dRecordRoi";text:"ROI 기록";enabled:root.state.ready&&!!root.state.track_id;onClicked:root.controller.record("RECTANGLE",reviewer.text,status.currentText)}
                }
                RowLayout {Layout.fillWidth:true
                    Button {text:root.state.track_paused?"재개":"중단";enabled:!!root.state.track_id;onClicked:root.controller.trackAction(root.state.track_paused?"RESUME":"PAUSE",reviewer.text)}
                    Button {text:"현재 기록 제거";enabled:!!root.state.track_id&&root.state.ready;onClicked:root.controller.trackAction("REMOVE",reviewer.text)}
                }
                RowLayout {Layout.fillWidth:true
                    Button {objectName:"stack3dUndo";text:"Undo";enabled:root.state.undo;onClicked:root.controller.undo()}
                    Button {objectName:"stack3dDiscard";text:"초안 취소";enabled:!!root.state.track_id;onClicked:root.controller.discardTracks()}
                }
                Repeater {model:root.state.track_points||[];delegate:Button {required property var modelData;Layout.fillWidth:true;text:"Page "+(modelData.page+1)+" · "+modelData.status+" · "+modelData.type;onClicked:root.controller.goTrackPage(modelData.page)}}
                Text {Layout.fillWidth:true;wrapMode:Text.Wrap;color:root.theme.warning;font.pixelSize:10;text:"관측 연결은 동일 물리 결함의 증명이 아닙니다. 실제 길이·체적·밀도 계산은 제공하지 않습니다."}
                Button {objectName:"stack3dSave";text:"3D 세션·Track 저장"+(root.state.dirty?" *":"");Layout.fillWidth:true;enabled:root.state.project&&root.state.ready&&!root.state.busy;onClicked:root.controller.save(reviewer.text)}
                Text {Layout.fillWidth:true;wrapMode:Text.Wrap;color:root.theme.muted;font.pixelSize:10;text:"Revision "+root.state.history_revision+" · 원본 배열은 JSON에 저장하지 않음
raw "+(root.state.raw_bytes/1048576).toFixed(2)+" MiB / display "+(root.state.texture_bytes/1048576).toFixed(2)+" MiB
"+root.state.backend}
            }
        }
        ColumnLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0
            TabBar {id:tabs;objectName:"stack3dTabs";Layout.fillWidth:true;TabButton {text:"3D"} TabButton {text:"XY"} TabButton {text:"X–Page"} TabButton {text:"Y–Page"}}
            StackLayout {
                currentIndex:tabs.currentIndex;Layout.fillWidth:true;Layout.fillHeight:true
                Item {
                    Loader {objectName:"stack3dSceneLoader";anchors.fill:parent;active:root.visible&&root.state.ready&&root.state.rhi_available;sourceComponent:Component {Stack3DScene {controller:root.controller;theme:root.theme}}}
                    Text {anchors.centerIn:parent;width:parent.width-30;wrapMode:Text.Wrap;horizontalAlignment:Text.AlignHCenter;color:root.theme.muted;text:root.state.ready&&!root.state.rhi_available?"3D Perspective는 GPU RHI가 필요합니다.
현재 Software 환경에서는 직교 단면을 사용하세요.":root.state.busy?"원본 확인·제한 ROI 준비 중…":root.state.ready?"":"TIFF 원본 · ROI · 페이지 범위를 선택하고 3D를 생성하세요";visible:!root.state.ready||!root.state.rhi_available}
                }
                StackOrthogonalView {controller:root.controller;theme:root.theme;kind:"xy"}
                StackOrthogonalView {controller:root.controller;theme:root.theme;kind:"xp"}
                StackOrthogonalView {controller:root.controller;theme:root.theme;kind:"yp"}
            }
            RowLayout {
                Layout.fillWidth:true
                Text {text:root.state.position.length?"원본 Page "+(root.state.position[2]+1)+" / "+root.state.source.pages:"Page —";color:root.theme.text}
                Slider {objectName:"stack3dPageSlider";Layout.fillWidth:true;from:0;to:Math.max(0,root.state.shape[0]-1);value:root.state.cursor[0];stepSize:1;enabled:root.state.ready;onMoved:root.controller.setPage(Math.round(value))}
                Button {objectName:"stack3dOriginal";text:"원본 페이지로";enabled:root.state.ready&&!root.state.busy;onClicked:root.controller.openOriginal()}
            }
            Text {Layout.fillWidth:true;wrapMode:Text.Wrap;color:root.theme.accent;font.pixelSize:11;text:root.state.position.length?"X "+root.state.position[0]+" · Y "+root.state.position[1]+" · uint16 "+root.state.position[3]+" · "+(root.state.physical?"Physical calibration":"Indexed Stack · 실제 깊이 미검증"):"X/Y 원본 픽셀 · K 원본 페이지 인덱스"}
            Text {Layout.fillWidth:true;wrapMode:Text.Wrap;color:root.theme.muted;font.pixelSize:10;text:"Track 범위 밖/미샘플 페이지 "+(root.scene.outside_or_unsampled_track_points||0)+" · 표시 생략 "+(root.scene.omitted_track_points||0)+" · 3D Plane은 표시용 페이지 샘플"}
        }
    }
    Text {objectName:"stack3dMessage";Layout.fillWidth:true;wrapMode:Text.Wrap;color:root.state.error?root.theme.warning:root.theme.muted;text:root.state.error||root.state.message;font.pixelSize:11}
}
