import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SurfaceDialog {
    id: root
    objectName: "centralSyncDialog"
    property QtObject theme
    property QtObject uiState
    readonly property var sync: uiState.centralSync
    parent: Overlay.overlay
    title: "중앙 연구 서버 · 명시적 동기화"
    width: Math.min(610,parent.width-40); height: Math.min(660,parent.height-40)
    x: (parent.width-width)/2; y: (parent.height-height)/2
    standardButtons: Dialog.Close
    onOpened: { server.text=sync.endpoint; device.text=sync.clientId; consent.checked=false; fileBridge.centralSync.refresh() }
    ScrollView {
        id: scroll
        objectName: "syncScroll"
        anchors.fill: parent; contentWidth: availableWidth; clip: true
        ColumnLayout {
            width: scroll.availableWidth; spacing: root.theme.spacingSm
            Text { text: "자동 업로드 OFF · 저장된 프로젝트 → 서버"; color: theme.text; Layout.fillWidth: true }
            Text { textFormat: Text.PlainText; text: ({UNCONFIGURED:"서버 미설정",DISCONNECTED:"연결 확인 필요",CONNECTED:"연결됨",SYNCING:"작업 중",ACKNOWLEDGED:"동기화 완료",CROP_ACKNOWLEDGED:"국소 Crop 전송 완료",AUTH_FAILED:"인증 실패",OFFLINE:"오프라인",CONFLICT:"동기화 충돌",RETRY:"재시도 필요"})[sync.status] || sync.status; color: theme.text; Layout.fillWidth: true }
            TextField { id: server; objectName: "syncServerInput"; Layout.fillWidth: true; placeholderText: "http://127.0.0.1:18766 또는 승인된 HTTPS origin"; enabled: !sync.busy }
            TextField { id: device; objectName: "syncClientInput"; Layout.fillWidth: true; placeholderText: "관리자가 등록한 기기 ID"; enabled: !sync.busy }
            TextField { id: credential; objectName: "syncCredentialInput"; Layout.fillWidth: true; placeholderText: "발급된 API Credential (OS Vault에 저장)"; echoMode: TextInput.Password; enabled: !sync.busy }
            RowLayout {
                AppButton { objectName: "syncConfigure"; theme: root.theme; text: "설정 저장"; enabled: !sync.busy; onClicked: { if(fileBridge.centralSync.configure(server.text,device.text,credential.text)) credential.clear() } }
                AppButton { objectName: "syncTestConnection"; theme: root.theme; text: "연결 테스트"; enabled: !sync.busy && !!sync.endpoint; onClicked: fileBridge.centralSync.testConnection() }
                AppButton { theme: root.theme; text: "Credential 제거"; enabled: !sync.busy; onClicked: fileBridge.centralSync.forgetCredential() }
            }
            Text { textFormat: Text.PlainText; text: uiState.project.name + " · 저장 revision " + uiState.project.revision; color: theme.text; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Text { text: "미전송 검수: " + (sync.pendingReviews<0 ? "확인 필요" : sync.pendingReviews) + " · 전송 대기 batch: " + sync.pendingBatches + "\n마지막 ACK: " + (sync.last || "없음"); color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Text { visible: uiState.project.dirty || uiState.projectReview.pending; text: "검수 기록을 확정하고 프로젝트를 디스크에 저장한 뒤 동기화하세요."; color: theme.warning; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                AppButton { objectName: "syncExecute"; theme: root.theme; text: "서버와 동기화"; enabled: sync.canSync; onClicked: fileBridge.centralSync.synchronize() }
                AppButton { objectName: "syncCancel"; theme: root.theme; text: "취소"; enabled: sync.busy; onClicked: fileBridge.centralSync.cancel() }
                AppButton { theme: root.theme; text: "전송 상태 확인"; enabled: !sync.busy; onClicked: fileBridge.centralSync.refresh() }
            }
            Text { text: "국소 Crop · 원본 JPG 픽셀에서 lossless PNG 생성"; color: theme.text }
            Text { text: "선택된 검수 대상에만 연결합니다. 원본 전체·TIFF·화면 캡처는 보내지 않습니다. 좌표는 원본 픽셀입니다."; color: theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Text { textFormat: Text.PlainText; text: "대상: " + (uiState.projectReview.targetId || "선택 없음") + " · 범위: " + root.rectangle.join(", "); color: theme.text; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                Repeater { model: ["X","Y","너비","높이"]
                    ColumnLayout { required property string modelData; required property int index
                        Text { text: modelData; color: theme.muted }
                        SpinBox { objectName: ["syncCropX","syncCropY","syncCropWidth","syncCropHeight"][index]; from: index<2 ? 0 : 1; to: index<2 ? 100000 : 1024; value: index<2 ? 0 : 128; editable:true; Layout.preferredWidth:130; onValueModified: root.rectangle[index]=value }
                    }
                }
            }
            CheckBox { id: consent; objectName: "syncCropConsent"; text: "선택 범위의 픽셀·검수 정보 전송에 동의"; checked:false; enabled: !sync.busy }
            AppButton { objectName: "syncUploadCrop"; theme: root.theme; text: "이 국소 Crop 업로드"; enabled: sync.canSync && consent.checked && uiState.projectReview.ready && !!uiState.projectReview.targetId; onClicked: { var r=uiState.projectReview; fileBridge.centralSync.uploadCrop(r.sourceId,r.runId || uiState.project.selectedRun,r.selected.type,r.targetId,root.rectangle[0],root.rectangle[1],root.rectangle[2],root.rectangle[3],consent.checked); consent.checked=false } }
            AppButton { objectName: "syncRetryCrops"; theme: root.theme; text: "이 프로젝트 대기 Crop 동의해서 재전송 ("+sync.pendingCrops+")"; enabled: sync.canSync && consent.checked && sync.pendingCrops>0; onClicked: { fileBridge.centralSync.retryCrops(consent.checked); consent.checked=false } }
            Text { textFormat: Text.PlainText; text: sync.error; visible: !!sync.error; color: theme.warning; wrapMode:Text.Wrap; Layout.fillWidth:true }
        }
    }
    property var rectangle: [0,0,128,128]
}
