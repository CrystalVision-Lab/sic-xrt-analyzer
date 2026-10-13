import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
SurfaceDialog {
 id:root; objectName:"analysisDialog"; property QtObject theme; property QtObject uiState; property var actions; property var hostWindow
 parent:Overlay.overlay; title:"이미지 분석"; modal:true; width:480; x:(parent.width-width)/2; y:(parent.height-height)/2; standardButtons:Dialog.NoButton
 ColumnLayout { width:parent.width; spacing:16
  Text { text:root.uiState.fileName; color:root.theme.text; font.pixelSize:16; wrapMode:Text.Wrap; Layout.fillWidth:true }
  RowLayout { Layout.fillWidth:true
   AppButton { theme:root.theme; text:"전체 이미지"; checked:root.uiState.analysisScope==="FULL_IMAGE"; onClicked:root.uiState.analysisScope="FULL_IMAGE"; Layout.fillWidth:true }
   AppButton { theme:root.theme; text:"선택 ROI"; checked:root.uiState.analysisScope==="ROI"; enabled:root.uiState.hasRoi; onClicked:root.uiState.analysisScope="ROI"; Layout.fillWidth:true }
  }
  AppButton {objectName:"analysisSpecifyArea";theme:root.theme;action:root.actions.roi;text:"ROI 지정";onClicked:root.close()}
  Text { text:root.uiState.analysisFlow.regionLabel; color:root.theme.muted; font.pixelSize:13; Layout.fillWidth:true; wrapMode:Text.Wrap }
  AppButton { objectName:"analysisInputInfo"; theme:root.theme; text:"상세 정보"; onClicked:root.actions.analysisInputInfo.trigger() }
  Text { visible:!root.uiState.canAnalyze; text:root.uiState.analysisReason; color:root.theme.warning; Layout.fillWidth:true; wrapMode:Text.Wrap }
  RowLayout { Layout.fillWidth:true
   AppButton { theme:root.theme; text:"결과 보기"; visible:root.uiState.hasResult; onClicked:{root.close();root.hostWindow.openContext("result")} }
   Item { Layout.fillWidth:true }
   AppButton { theme:root.theme; text:"취소"; onClicked:root.close() }
   AppButton { objectName:"confirmAnalysis"; theme:root.theme; text:root.uiState.hasResult?"다시 분석":"확인 · 분석"; primary:true; enabled:root.uiState.canAnalyze; onClicked:{root.close();root.actions.run.trigger()} }
  }
 }
 Connections { target:root.uiState; function onHasLoadedImageChanged(){if(!root.uiState.hasLoadedImage)root.close()} }
}
