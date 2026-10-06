import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "contextHeader"
    property QtObject theme
    property var controller
    signal focusRequested()
    spacing: 6
    AppButton {
        objectName: "contextSwitcher"; theme: root.theme
        text: root.controller.title + " ▾"; tip: "작업 Context 선택 · 방향키와 Enter로 선택"
        Accessible.name: "작업 Context 선택: " + root.controller.title
        Accessible.description: "이미지 정보, 분석, 결과, 뷰어·스택, ROI 관리"
        Layout.fillWidth: true; implicitHeight: 32
        onClicked: switcher.open()
        ToolTip.visible: hovered && !switcher.visible
        AppMenu {
            id: switcher; objectName: "contextMenu"; y: parent.height; width: parent.width
            onClosed: Qt.callLater(function() { root.focusRequested() })
            Repeater {
                model: root.controller.keys
                ToolbarMenuItem {
                    required property int index; required property string modelData
                    objectName: "contextChoice" + index
                    text: root.controller.labels[index]; checkable: true
                    autoExclusive: true
                    checked: root.controller.requestedContext === modelData
                    Accessible.name: text
                    onTriggered: root.controller.requestContext(modelData, "MANUAL")
                }
            }
        }
    }
    Text {
        objectName: "contextSubtitle"; text: root.controller.subtitle
        color: root.theme.muted; font.family: root.theme.fontFamily; font.pixelSize: 11
        wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; Layout.fillWidth: true
    }
}
