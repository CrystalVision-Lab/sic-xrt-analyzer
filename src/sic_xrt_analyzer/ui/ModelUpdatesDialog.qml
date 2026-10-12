import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    objectName: "modelUpdatesDialog"
    title: "AI 모델 관리"
    modal: true
    width: Math.min(640, parent.width - 40)
    height: Math.min(620, parent.height - 40)
    anchors.centerIn: parent
    property var controller: fileBridge.modelUpdates
    property var updates: controller.state
    standardButtons: Dialog.Close
    contentItem: ScrollView {
        ColumnLayout {
            width: root.availableWidth - 20
            spacing: 14
            Label { textFormat: Text.PlainText; text: "현재 모델"; font.bold: true }
            Label { textFormat: Text.PlainText; text: root.updates.modelId || "연결된 모델 없음"; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { textFormat: Text.PlainText; text: "출처: " + root.updates.source; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { textFormat: Text.PlainText; text: root.updates.status; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { textFormat: Text.PlainText; text: root.updates.error; visible: text.length > 0; color: "#ffb35a"; Layout.fillWidth: true; wrapMode: Text.Wrap }
            RowLayout {
                Button { objectName: "checkModelUpdatesButton"; text: "업데이트 확인"; enabled: !root.updates.busy; onClicked: root.controller.checkUpdates() }
                CheckBox { text: "BETA 참여"; enabled: !root.updates.busy; onToggled: root.controller.selectBeta(checked) }
            }
            Label { textFormat: Text.PlainText; text: root.updates.release.model_version ? root.updates.release.model_id + " · " + root.updates.release.model_version : ""; visible: text.length > 0; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { textFormat: Text.PlainText; text: root.updates.release.change_notes || ""; visible: text.length > 0; Layout.fillWidth: true; wrapMode: Text.Wrap }
            ProgressBar { value: root.updates.progress / 100; visible: root.updates.busy; Layout.fillWidth: true }
            RowLayout {
                Button { objectName: "downloadModelButton"; text: "다운로드·설치"; enabled: !root.updates.busy && !!root.updates.release.release_id; onClicked: root.controller.download() }
                Button { text: "취소"; enabled: root.updates.busy; onClicked: root.controller.cancel() }
                Button { objectName: "activateModelButton"; text: "다음 분석에 적용"; enabled: !root.updates.busy && root.updates.canActivate; onClicked: root.controller.activate() }
            }
            Label { textFormat: Text.PlainText; text: "설치된 모델"; font.bold: true }
            Repeater {
                model: root.updates.installed
                RowLayout {
                    required property var modelData
                    Label { textFormat: Text.PlainText; text: modelData.model_id + " · " + modelData.version; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    Button { text: "적용"; enabled: !root.updates.busy; onClicked: root.controller.activateInstalled(modelData.release_id) }
                }
            }
            Button { objectName: "rollbackModelButton"; text: "이전 모델 복원"; enabled: !root.updates.busy && root.updates.canRollback; onClicked: root.controller.rollback() }
            Button { text: "로컬 모델 폴더 선택"; enabled: !root.updates.busy; onClicked: { root.close(); root.localModelRequested() } }
            Label { textFormat: Text.PlainText; text: "모델 변경은 완료된 분석 결과·검수 이력을 유지하며 다음 분석에 적용됩니다."; Layout.fillWidth: true; wrapMode: Text.Wrap }
        }
    }
    signal localModelRequested()
}
