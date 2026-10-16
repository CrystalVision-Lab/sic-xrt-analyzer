import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SurfaceDialog {
    id: root
    objectName: "workflowGuideDialog"
    property QtObject theme
    property int topic: 0
    readonly property var groups: fileBridge.workflowGuide.groups
    readonly property var current: groups[topic]
    parent: Overlay.overlay
    title: "사용 가이드 · 작업 순서"
    width: Math.min(960, parent.width-40); height: Math.min(700, parent.height-40)
    x: (parent.width-width)/2; y: (parent.height-height)/2
    modal: true; standardButtons: Dialog.Close
    RowLayout {
        anchors.fill: parent; spacing: 24
        ColumnLayout {
            Layout.preferredWidth: 200; Layout.alignment: Qt.AlignTop; spacing: 8
            Repeater {
                model: root.groups
                AppButton { required property var modelData; required property int index; theme: root.theme; text: modelData.title; checked: root.topic===index; Layout.fillWidth: true; onClicked: root.topic=index }
            }
        }
        ScrollView {
            id: scroll; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            ColumnLayout {
                width: scroll.availableWidth; spacing: 20
                Text { text: root.current.title; color: root.theme.text; font.pixelSize: 26; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Text { text: root.current.subtitle; color: root.theme.muted; font.pixelSize: 15; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Repeater {
                    model: root.current.tabs
                    ColumnLayout {
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true; spacing: 8
                        Text { text: (parent.index+1)+"  "+parent.modelData.title; color: root.theme.accent; font.pixelSize: 17; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        Text { text: parent.modelData.steps.join("\n"); color: root.theme.text; font.pixelSize: 14; lineHeight: 1.4; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    }
                }
            }
        }
    }
}
