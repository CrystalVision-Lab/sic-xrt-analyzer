import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
SurfaceDialog {
 id:root; objectName:"reportDialog"; property QtObject theme; property QtObject uiState
 parent:Overlay.overlay; title:"신고 대기열에 추가"; modal:true; width:480; x:(parent.width-width)/2; y:(parent.height-height)/2; standardButtons:Dialog.NoButton
 onOpened:{fileBridge.reports.resetNotice();note.text="";reason.currentIndex=0;attachCrops.checked=false}
 ColumnLayout { width:parent.width; spacing:14
  Text { text:fileBridge.research.regions.state.checked.length ? "선택 후보 "+fileBridge.research.regions.state.checked.length+"개" : "후보 #"+(root.uiState.research.selected.number||"")+" · "+(root.uiState.research.selected.type||""); color:root.theme.text; font.pixelSize:16 }
  AppComboBox { id:reason; model:["결함 아님","종류가 다름","위치가 다름","영역이 다름","중복 후보","누락 결함","기타"]; theme:root.theme; Layout.fillWidth:true }
  AppComboBox { id:correction; theme:root.theme; model:["미확정","BPD","TED","TSD"]; visible:reason.currentText==="종류가 다름"; Layout.fillWidth:true }
  TextArea { id:note; Layout.fillWidth:true; Layout.preferredHeight:100; placeholderText:"메모 (선택)"; wrapMode:TextEdit.Wrap; color:root.theme.text }
  AppCheckBox { id:withRoi; theme:root.theme; text:"선택 ROI 첨부"; enabled:root.uiState.hasRoi||!!root.uiState.roiFlow.selected; checked:enabled }
  AppCheckBox {id:attachCrops;theme:root.theme;text:"선택 위치의 상세·주변 원본 이미지 첨부"}
  Text {text:"지금은 기기에 저장합니다. 서버 전송은 대기열에서 따로 확인합니다. 여러 후보 신고의 이미지 첨부는 선택 위치 1곳을 기준으로 합니다.";color:root.theme.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
  Text { visible:!!fileBridge.reports.state.error; text:fileBridge.reports.state.error; color:root.theme.warning; Layout.fillWidth:true; wrapMode:Text.Wrap }
  RowLayout { Layout.fillWidth:true; Item{Layout.fillWidth:true}
   AppButton {theme:root.theme;text:"취소";enabled:!fileBridge.reports.state.busy;onClicked:root.close()}
   AppButton {objectName:"submitReport";theme:root.theme;text:fileBridge.reports.state.busy?"저장 중…":"대기열에 추가";primary:true;enabled:!fileBridge.reports.state.busy;onClicked:{if(withRoi.checked&&!root.uiState.hasRoi){fileBridge.reports.submitSelected(reason.currentText,note.text);return}fileBridge.reports.stageSelection(reason.currentText,note.text,reason.currentText==="종류가 다름"?correction.currentText:"",attachCrops.checked,withRoi.checked?root.uiState.roiX:0,withRoi.checked?root.uiState.roiY:0,withRoi.checked?root.uiState.roiWidth:0,withRoi.checked?root.uiState.roiHeight:0)}}
  }
 }
 Connections {target:root.uiState;function onHasResultChanged(){if(!root.uiState.hasResult)root.close()}}
 Connections {target:fileBridge.reports;function onChanged(){if(root.visible&&fileBridge.reports.state.saved&&!fileBridge.reports.state.busy)root.close()}}
}
