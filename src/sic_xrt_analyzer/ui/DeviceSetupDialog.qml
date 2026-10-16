import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SurfaceDialog {
    id: root
    objectName: "deviceSetupDialog"
    property QtObject theme
    property QtObject uiState
    readonly property var sync: uiState.centralSync
    parent: Overlay.overlay
    title: "처음 시작하기 · 기기 등록"
    width: Math.min(620, parent.width - 40)
    height: Math.min(640, parent.height - 40)
    x: (parent.width-width)/2; y: (parent.height-height)/2
    modal: true
    standardButtons: Dialog.NoButton
    onOpened: { server.text=sync.endpoint; device.text=sync.clientId; credential.clear() }
    onClosed: { credential.clear(); fileBridge.centralSync.dismissSetup() }
    ScrollView {
        anchors.fill: parent; contentWidth: availableWidth; clip: true
        ColumnLayout {
            width: parent.width; spacing: 16
            Text { text: "이 PC에서 연구를 시작하세요"; color: root.theme.text; font.pixelSize: 24; font.bold: true; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Text { text: "이미지 보기 · ImageJ 처리 · 로컬 3D는 기기 등록 없이 사용할 수 있습니다. 서버 동기화, 신고 전송, 승인 모델 받기는 연구용 기기 등록이 필요합니다."; color: root.theme.muted; font.pixelSize: 14; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Text { text: "1  관리자에게 이 PC의 기기 ID 전달"; color: root.theme.text; font.pixelSize: 16; font.bold: true }
            RowLayout {
                Layout.fillWidth: true
                AppTextField { visualTheme:root.theme; id: device; objectName: "setupDeviceId"; Layout.fillWidth: true; selectByMouse: true; enabled: !root.sync.busy; Accessible.name: "기기 ID" }
                AppButton { theme: root.theme; text: "복사"; onClicked: fileBridge.copyText(device.text) }
            }
            Text { text: "2  발급받은 서버 주소와 인증키 입력"; color: root.theme.text; font.pixelSize: 16; font.bold: true }
            AppTextField { visualTheme:root.theme; id: server; objectName: "setupServer"; Layout.fillWidth: true; placeholderText: "https://연구서버 주소"; enabled: !root.sync.busy; Accessible.name: "연구 서버 주소" }
            AppTextField { visualTheme:root.theme; id: credential; objectName: "setupCredential"; Layout.fillWidth: true; placeholderText: "기기 인증키 (xrt_…)"; echoMode: TextInput.Password; enabled: !root.sync.busy; Accessible.name: "기기 인증키" }
            Text { text: "인증키는 Windows 자격 증명 저장소에 보관됩니다. 관리자 웹 로그인 비밀번호와는 다릅니다. 이 화면은 파일 → 기기 등록에서 다시 열 수 있습니다."; color: root.theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                AppButton { objectName: "setupConnect"; theme: root.theme; primary: true; text: root.sync.busy ? "연결 확인 중…" : "저장하고 연결 확인"; enabled: !root.sync.busy && !!server.text && !!device.text; onClicked: { if(fileBridge.centralSync.configure(server.text, device.text, credential.text)) { credential.clear(); fileBridge.centralSync.testConnection() } } }
                BusyIndicator { running: root.sync.busy; visible: running; implicitWidth: 28; implicitHeight: 28 }
            }
            Text { text: root.sync.status==="CONNECTED" ? "연결 확인 완료 · 이 PC에서 서버 기능을 사용할 수 있습니다." : root.sync.error ? "연결을 확인하지 못했습니다: "+root.sync.error : "관리자 승인과 연결 확인 후 서버 기능을 사용할 수 있습니다."; color: root.sync.status==="CONNECTED" ? root.theme.accent : root.theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: root.theme.border }
            RowLayout {
                Text { text: "원본 파일은 자동으로 업로드되지 않습니다."; color: root.theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
                AppButton { objectName: "setupContinue"; theme: root.theme; text: root.sync.status==="CONNECTED" ? "시작하기" : "로컬 기능으로 시작"; enabled: !root.sync.busy; onClicked: root.close() }
            }
        }
    }
}
