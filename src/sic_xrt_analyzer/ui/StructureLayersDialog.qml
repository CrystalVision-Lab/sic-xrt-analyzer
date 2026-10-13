import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
SurfaceDialog {
 id:root;objectName:"structureLayersDialog";property QtObject theme;property QtObject uiState;property var hostWindow
 parent:Overlay.overlay;modal:true;title:"구조 레이어";width:520;height:500;x:(parent.width-width)/2;y:(parent.height-height)/2;standardButtons:Dialog.Close
 readonly property var experiment:uiState.experiment
 ColumnLayout {anchors.fill:parent;spacing:12
  RowLayout {Layout.fillWidth:true
   AppButton{objectName:"importExperiment";theme:root.theme;text:"불러오기…";enabled:root.uiState.analysisEligible&&!root.experiment.loading;onClicked:picker.open()}
   Text{objectName:"experimentStatus";text:root.experiment.loading?"불러오는 중…":"구조 "+root.experiment.total+"개";color:root.theme.muted;Layout.fillWidth:true}
  }
  Text{visible:!!root.experiment.error;text:root.experiment.error;color:root.theme.warning;Layout.fillWidth:true;wrapMode:Text.Wrap}
  ListView {objectName:"structureList";Layout.fillWidth:true;Layout.fillHeight:true;clip:true;model:root.experiment.rows;ScrollBar.vertical:ScrollBar{}
   delegate:ItemDelegate {required property var modelData;required property int index;objectName:"structureRow"+(index+1);width:ListView.view.width;text:"구조 "+(index+1);onClicked:fileBridge.experiments.select(modelData.id)}
  }
  RowLayout{visible:!!root.experiment.selected.id;Layout.fillWidth:true
   Image{objectName:"structureThumbnail";source:root.experiment.preview||"";Layout.preferredWidth:100;Layout.preferredHeight:100;cache:false;smooth:false}
   Text{objectName:"selectedStructureHeader";text:"구조 기반 제안";color:root.theme.text;Layout.fillWidth:true}
   AppButton{objectName:"structureDetails";theme:root.theme;text:"상세";onClicked:details.open()}
  }
  AppComboBox {theme:root.theme;model:["Mask 숨김","영역","경계"];onActivated:root.uiState.maskMode=["off","fill","boundary"][currentIndex];Layout.fillWidth:true}
 }
 SafeFolderDialog{id:picker;objectName:"experimentFolderDialog";title:"구조 레이어 폴더";onAccepted:fileBridge.experiments.load(selectedFolder.toString())}
 SurfaceDialog{id:details;objectName:"structureDetailDialog";parent:Overlay.overlay;title:"구조 상세";modal:true;width:420;standardButtons:Dialog.Close;x:(parent.width-width)/2;y:(parent.height-height)/2
  ColumnLayout{width:parent.width;spacing:12
   Text{text:"구조 기반 제안";color:root.theme.text;font.pixelSize:18}
   Text{text:root.experiment.selected.kind||"";color:root.theme.muted}
   Text{text:JSON.stringify(root.experiment.selected.bounds||[])+" px";color:root.theme.muted}
  }
 }
}
