import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
ToolbarButton {
 id:root;objectName:"layerTools";property QtObject uiState;property var hostWindow;text:"레이어 ▾";enabled:uiState.hasLoadedImage;onClicked:layers.open()
 StructureLayersDialog{id:structures;theme:root.theme;uiState:root.uiState;hostWindow:root.hostWindow}
 Popup {id:layers;objectName:"displayLayerPopup";x:root.width-width;y:root.height;width:280;padding:14
  background:Rectangle{color:root.theme.panel;border.color:root.theme.border;radius:8}
  contentItem: ColumnLayout {spacing:8
   AppCheckBox{objectName:"resultLayerVisibility";theme:root.theme;text:"모든 후보";checked:root.uiState.analysisLayerVisible;visible:root.uiState.hasResult;onToggled:root.uiState.analysisLayerVisible=checked}
   Repeater{model:[{key:"BPD",label:"BPD 영역"},{key:"TED",label:"TED"},{key:"TSD",label:"TSD"}]
    AppCheckBox{required property var modelData;objectName:modelData.key.toLowerCase()+"Layer";theme:root.theme;text:modelData.label;visible:root.uiState.hasResult;checked:root.uiState.candidateLayer(modelData.key);onToggled:{if(modelData.key==="BPD")root.uiState.bpdLayerVisible=checked;else if(modelData.key==="TED")root.uiState.tedLayerVisible=checked;else root.uiState.tsdLayerVisible=checked}}
   }
   AppCheckBox{theme:root.theme;text:"선택 강조";checked:root.uiState.selectedLayerVisible;visible:root.uiState.hasResult;onToggled:root.uiState.selectedLayerVisible=checked}
   AppCheckBox{theme:root.theme;text:"현재 ROI";checked:root.uiState.roiLayerVisible;onToggled:root.uiState.roiLayerVisible=checked}
   AppButton{objectName:"addRoiLayer";theme:root.theme;text:"선택 ROI를 레이어로 추가";enabled:root.uiState.hasRoi||!!root.uiState.roiFlow.selected;Layout.fillWidth:true;onClicked:{if(root.uiState.hasRoi)fileBridge.displayLayers.add(root.uiState.roiX,root.uiState.roiY,root.uiState.roiWidth,root.uiState.roiHeight);else fileBridge.displayLayers.addSelected()}}
   AppButton{objectName:"browseStructures";theme:root.theme;text:"구조 레이어…";enabled:root.uiState.analysisEligible;Layout.fillWidth:true;onClicked:{layers.close();structures.open()}}
   ScrollView{Layout.fillWidth:true;Layout.preferredHeight:Math.min(220,fileBridge.displayLayers.rows.length*42);clip:true
    ColumnLayout {width:parent.width
     Repeater{model:fileBridge.displayLayers.rows
      RowLayout{required property var modelData;Layout.fillWidth:true
       AppCheckBox{theme:root.theme;text:modelData.name;checked:modelData.visible;Layout.fillWidth:true;onToggled:fileBridge.displayLayers.toggle(modelData.id,checked)}
       AppButton{theme:root.theme;text:"×";tip:"레이어 삭제";onClicked:fileBridge.displayLayers.remove(modelData.id)}
      }
     }
    }
   }
  }
 }
}
