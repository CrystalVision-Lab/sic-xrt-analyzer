import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
SurfaceDialog {
 id:root; property QtObject theme; readonly property var state:fileBridge.reports.state
 parent:Overlay.overlay; title:"신고 대기열"; modal:true; width:Math.min(580,parent.width-32); height:Math.min(560,parent.height-48)
 x:(parent.width-width)/2; y:(parent.height-height)/2; standardButtons:Dialog.Close
 ColumnLayout {
  anchors.fill:parent
  Text {text:"전송 대기 "+root.state.pending+"건 · 전송 완료 "+root.state.sent+"건";color:root.theme.text;font.pixelSize:18}
  Text {text:"한 건에 여러 후보를 묶을 수 있습니다. 전송은 최대 20건씩 진행합니다.";color:root.theme.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
  ListView {
   Layout.fillWidth:true; Layout.fillHeight:true; clip:true; model:root.state.rows; spacing:8
   ScrollBar.vertical:ScrollBar{}
   delegate:Text {required property var modelData; width:ListView.view.width;wrapMode:Text.Wrap;color:root.theme.text
    text:modelData.reason+" · 후보 "+modelData.count+"개 · "+({PENDING:"대기",SENDING:"응답 확인 필요",SENT:"전송 완료",FAILED:"실패"}[modelData.state]||modelData.state)+(modelData.error?" / "+modelData.error:"")
   }
  }
  Text {visible:!!root.state.error;text:root.state.error;color:root.theme.warning;wrapMode:Text.Wrap;Layout.fillWidth:true}
  AppButton {theme:root.theme;text:root.state.busy?"전송 중…":"전송 내용 확인 / 실패 재시도";enabled:!root.state.busy&&root.state.pending>0;onClicked:{if(fileBridge.reports.prepareSend())preview.open()}}
 }
 SurfaceDialog {
  id:preview;parent:Overlay.overlay;title:"서버로 전송할 내용";modal:true;width:520;height:Math.min(650,parent.height-48);x:(parent.width-width)/2;y:(parent.height-height)/2;standardButtons:Dialog.NoButton
  ColumnLayout {anchors.fill:parent;spacing:14
   Text {text:"서버: "+root.state.previewEndpoint;color:root.theme.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
   Text {text:"신고 "+root.state.previewCount+"건 / 후보 "+root.state.previewCandidates+"개 / 첨부 이미지 "+root.state.previewCrops+"장\n사유: "+root.state.previewReasons.join(", ");color:root.theme.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
   Text {text:"메모, 원본 해시·좌표, 모델 버전과 선택한 이미지가 전송됩니다. 신고는 정답으로 자동 승인되지 않습니다.";color:root.theme.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
   ScrollView {Layout.fillWidth:true;Layout.fillHeight:true;clip:true
    ColumnLayout {width:parent.width;spacing:12
     Repeater {model:root.state.previewRows
      ColumnLayout {required property var modelData;Layout.fillWidth:true
       Text {text:modelData.reason+" · "+modelData.candidates.length+"개 · "+modelData.correction;color:root.theme.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
       Text {text:"메모: "+(modelData.comment||"없음")+"\n좌표: "+modelData.candidates.map(function(p){return p.id+" ("+p.x+", "+p.y+")"}).join(" / ")+"\nROI: "+JSON.stringify(modelData.roi);color:root.theme.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
       RowLayout {Repeater {model:modelData.crops;Image {required property var modelData;source:"data:image/png;base64,"+modelData.png;Layout.preferredWidth:120;Layout.preferredHeight:120;fillMode:Image.PreserveAspectFit}}}
       Rectangle {height:1;Layout.fillWidth:true;color:root.theme.border}
      }
     }
    }
   }
   RowLayout {Layout.alignment:Qt.AlignRight
    AppButton {theme:root.theme;text:"취소";onClicked:preview.close()}
    AppButton {theme:root.theme;text:"이 내용 전송";primary:true;onClicked:{fileBridge.reports.sendPrepared();preview.close()}}
   }
  }
 }
}
