import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SurfaceDialog {
    id: root
    objectName: "appUpdatesDialog"
    title: update.version ? "새 버전이 준비됐어요" : "프로그램 업데이트"
    modal: true
    width: Math.min(560, parent.width - 40)
    height: Math.min(parent.height - 40, updateContent.implicitHeight + topPadding + bottomPadding + header.implicitHeight + 12)
    anchors.centerIn: parent
    property var controller: fileBridge.appUpdates
    property var update: controller.state
    property bool settingsExpanded: false
    closePolicy: update.busy ? Popup.NoAutoClose : Popup.CloseOnEscape
    contentItem: ScrollView {
        ColumnLayout {
            id: updateContent
            width: root.availableWidth - 20
            spacing: 12
            RowLayout {
                spacing: 12; Layout.fillWidth:true
                Rectangle { width:40; height:40; radius:11; color:root.visualTheme.accentPale; AppIcon { anchors.centerIn:parent; width:20; height:20; name:"download"; ink:root.visualTheme.accent } }
                Label { text: root.update.version ? root.update.version + " 업데이트" : "현재 버전 " + root.update.currentVersion; font.pixelSize: 23; font.bold: true; color:root.visualTheme.text; Layout.fillWidth:true; wrapMode:Text.Wrap }
            }
            Label { text: "현재 " + root.update.currentVersion + "  →  " + root.update.version; visible: !!root.update.version }
            ColumnLayout {
                visible: root.update.highlights.length > 0
                Layout.fillWidth: true
                spacing: 8
                Label { text: "이번 버전의 주요 변경 사항"; font.bold: true }
                Repeater {
                    model: root.update.highlights
                    Label {
                        required property string modelData
                        textFormat: Text.PlainText
                        text: "• " + modelData
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                }
            }
            Label { textFormat: Text.PlainText; text: root.update.status; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Label { textFormat: Text.PlainText; text: root.update.error; color: "#ffb35a"; visible: text.length > 0; wrapMode: Text.Wrap; Layout.fillWidth: true }
            ProgressBar { visible: root.update.busy; indeterminate: root.update.operation !== "download"; value: root.update.progress / 100; Layout.fillWidth: true }
            Label { text: root.update.progress + "%"; visible: root.update.busy && root.update.operation === "download" }
            Label { text: "다운로드 후 프로그램을 다시 실행합니다."; visible: !!root.update.version; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                Item {Layout.fillWidth:true}
                AppButton { objectName: "dismissAppUpdateButton"; theme:root.visualTheme; text: root.update.version ? "나중에" : "닫기"; visible: !root.update.busy; onClicked: root.close() }
                AppButton { objectName: "downloadAppUpdateButton"; theme:root.visualTheme; text: "업데이트하기"; primary: true; visible:!!root.update.version; enabled: !root.update.busy && !!root.update.version; onClicked: root.controller.update() }
                AppButton { objectName: "cancelAppUpdateButton"; theme:root.visualTheme; text: "취소"; visible: root.update.busy; onClicked: root.controller.cancel() }
            }
            Label { text: "소스로 실행 중입니다. 설치된 프로그램에서 업데이트를 적용할 수 있습니다."; visible: !root.update.frozen; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                AppButton { objectName: "checkAppUpdatesButton"; theme:root.visualTheme; text: "다시 확인"; quiet:true; compact:true; enabled: !root.update.busy; onClicked: root.controller.checkUpdates() }
                AppButton { theme:root.visualTheme; text: root.settingsExpanded ? "연결 설정 ▴" : "연결 설정 ▾"; quiet:true; compact:true; onClicked: root.settingsExpanded = !root.settingsExpanded }
            }
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
