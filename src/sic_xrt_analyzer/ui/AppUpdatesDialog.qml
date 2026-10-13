import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    objectName: "appUpdatesDialog"
    title: "프로그램 업데이트"
    modal: true
    width: Math.min(680, parent.width - 40)
    height: Math.min(640, parent.height - 40)
    anchors.centerIn: parent
    property var controller: fileBridge.appUpdates
    property var update: controller.state
    standardButtons: Dialog.Close
    contentItem: ScrollView {
        ColumnLayout {
            width: root.availableWidth - 20
            spacing: 12
            Label { text: "현재 버전 " + root.update.currentVersion; font.bold: true }
            Label { text: root.update.version ? "새 버전 " + root.update.version + " · " + root.update.sizeMiB + " MiB" : ""; visible: text.length > 0; font.bold: true }
            Label { textFormat: Text.PlainText; text: root.update.status; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Label { textFormat: Text.PlainText; text: root.update.error; color: "#ffb35a"; visible: text.length > 0; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Label { textFormat: Text.PlainText; text: root.update.notes; visible: text.length > 0; wrapMode: Text.Wrap; Layout.fillWidth: true }
            ProgressBar { visible: root.update.busy; value: root.update.progress / 100; Layout.fillWidth: true }
            RowLayout {
                Button { objectName: "checkAppUpdatesButton"; text: "새 버전 확인"; enabled: !root.update.busy; onClicked: root.controller.checkUpdates() }
                Button { objectName: "downloadAppUpdateButton"; text: "업데이트"; enabled: !root.update.busy && !!root.update.version; onClicked: root.controller.update() }
                Button { objectName: "installAppUpdateButton"; text: "업데이트 적용"; visible: false; enabled: !root.update.busy && root.update.canInstall; onClicked: root.controller.verifyInstall() }
                Button { text: "취소"; enabled: root.update.busy; onClicked: root.controller.cancel() }
            }
            Label { textFormat: Text.PlainText; text: "업데이트를 누르면 검증 후 프로그램을 종료하고 새 버전으로 다시 실행합니다. 원본·프로젝트·모델은 유지합니다."; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Label { text: "소스로 실행 중입니다. 다운로드한 설치 파일로 설치한 프로그램에서 자동 설치 연결을 사용할 수 있습니다."; visible: !root.update.frozen; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Label { text: "배포 사이트 주소 (HTTPS)"; font.bold: true }
            TextField { id: origin; objectName: "appUpdateOrigin"; text: root.update.origin; enabled: !root.update.busy; Layout.fillWidth: true; placeholderText: "https://배포사이트" }
            CheckBox { id: startup; text: "프로그램 시작 시 새 버전 확인"; checked: root.update.startup; enabled: !root.update.busy }
            CheckBox { id: beta; text: "연구용 BETA 버전 포함"; checked: root.update.beta; enabled: !root.update.busy }
            Button { text: "설정 저장·확인"; enabled: !root.update.busy; onClicked: root.controller.configure(origin.text, startup.checked, beta.checked) }
            Label { text: "임시 접속 주소가 바뀌면 연구 담당자가 알려준 새 주소를 입력하세요. 모델 버전은 분석 메뉴의 AI 모델 관리에서 별도로 관리합니다."; wrapMode: Text.Wrap; Layout.fillWidth: true }
        }
    }
}
