import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    objectName: "appUpdatesDialog"
    title: update.version ? "새 업데이트가 있습니다" : "프로그램 업데이트"
    modal: true
    width: Math.min(560, parent.width - 40)
    height: Math.min(540, parent.height - 40)
    anchors.centerIn: parent
    property var controller: fileBridge.appUpdates
    property var update: controller.state
    property bool settingsExpanded: false
    closePolicy: update.busy ? Popup.NoAutoClose : Popup.CloseOnEscape
    contentItem: ScrollView {
        ColumnLayout {
            width: root.availableWidth - 20
            spacing: 12
            Label { text: root.update.version ? "버전 " + root.update.version : "현재 버전 " + root.update.currentVersion; font.pixelSize: 22; font.bold: true }
            Label { text: "현재 " + root.update.currentVersion + "  →  " + root.update.version; visible: !!root.update.version }
            Label { textFormat: Text.PlainText; text: root.update.notes; visible: text.length > 0; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Label { textFormat: Text.PlainText; text: root.update.status; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Label { textFormat: Text.PlainText; text: root.update.error; color: "#ffb35a"; visible: text.length > 0; wrapMode: Text.Wrap; Layout.fillWidth: true }
            ProgressBar { visible: root.update.busy; indeterminate: root.update.operation !== "download"; value: root.update.progress / 100; Layout.fillWidth: true }
            Label { text: root.update.progress + "%"; visible: root.update.busy && root.update.operation === "download" }
            Label { text: "다운로드 후 프로그램을 다시 실행합니다."; visible: !!root.update.version; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                Button { objectName: "checkAppUpdatesButton"; text: "다시 확인"; enabled: !root.update.busy; onClicked: root.controller.checkUpdates() }
                Button { objectName: "downloadAppUpdateButton"; text: "업데이트"; highlighted: true; enabled: !root.update.busy && !!root.update.version; onClicked: root.controller.update() }
                Button { objectName: "cancelAppUpdateButton"; text: "취소"; visible: root.update.busy; onClicked: root.controller.cancel() }
                Button { objectName: "dismissAppUpdateButton"; text: root.update.version ? "나중에" : "닫기"; visible: !root.update.busy; onClicked: root.close() }
            }
            Label { text: "소스로 실행 중입니다. 설치된 프로그램에서 업데이트를 적용할 수 있습니다."; visible: !root.update.frozen; wrapMode: Text.Wrap; Layout.fillWidth: true }
            ToolButton { text: root.settingsExpanded ? "연결 설정 ▴" : "연결 설정 ▾"; onClicked: root.settingsExpanded = !root.settingsExpanded }
            ColumnLayout {
                visible: root.settingsExpanded
                Layout.fillWidth: true
                Label { text: "배포 사이트" }
                TextField { id: origin; objectName: "appUpdateOrigin"; text: root.update.origin; enabled: !root.update.busy; Layout.fillWidth: true }
                CheckBox { id: beta; text: "연구용 BETA 버전 포함"; checked: root.update.beta; enabled: !root.update.busy }
                Button { text: "설정 저장·확인"; enabled: !root.update.busy; onClicked: root.controller.configure(origin.text, true, beta.checked) }
            }
        }
    }
}
