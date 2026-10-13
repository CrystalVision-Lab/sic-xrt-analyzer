import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
SurfaceDialog {
 id:root; objectName:"reportDialog"; property QtObject theme; property QtObject uiState
 parent:Overlay.overlay; title:"결과 신고"; modal:true; width:430; x:(parent.width-width)/2; y:(parent.height-height)/2; standardButtons:Dialog.NoButton
 onOpened:{note.text="";reason.currentIndex=0}
 ColumnLayout { width:parent.width; spacing:14
  Text { text:"후보 #"+(root.uiState.research.selected.number||"")+" · "+(root.uiState.research.selected.type||""); color:root.theme.text; font.pixelSize:16 }
  AppComboBox { id:reason; model:["결함 아님","종류가 다름","위치가 다름","영역이 다름","기타"]; theme:root.theme; Layout.fillWidth:true }
  TextArea { id:note; Layout.fillWidth:true; Layout.preferredHeight:100; placeholderText:"메모 (선택)"; wrapMode:TextEdit.Wrap; color:root.theme.text }
  AppCheckBox { id:withRoi; theme:root.theme; text:"선택 ROI 첨부"; enabled:root.uiState.hasRoi; checked:root.uiState.hasRoi }
  Text { visible:!!fileBridge.reports.state.error; text:fileBridge.reports.state.error; color:root.theme.warning; Layout.fillWidth:true; wrapMode:Text.Wrap }
  RowLayout { Layout.fillWidth:true; Item{Layout.fillWidth:true}
   AppButton {theme:root.theme;text:"취소";enabled:!fileBridge.reports.state.busy;onClicked:root.close()}
   AppButton {objectName:"submitReport";theme:root.theme;text:fileBridge.reports.state.busy?"저장 중…":"신고 저장";primary:true;enabled:!fileBridge.reports.state.busy;onClicked:fileBridge.reports.submit(reason.currentText,note.text,withRoi.checked?root.uiState.roiX:0,withRoi.checked?root.uiState.roiY:0,withRoi.checked?root.uiState.roiWidth:0,withRoi.checked?root.uiState.roiHeight:0)}
  }
 }
 Connections {target:fileBridge.reports;function onChanged(){if(root.visible&&fileBridge.reports.state.saved&&!fileBridge.reports.state.busy)root.close()}}
}
