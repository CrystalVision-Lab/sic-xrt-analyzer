import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "contextHeader"
    property QtObject theme
    property var controller
    property var actions
    signal focusRequested()
    spacing: theme.spacingXs
    RowLayout {
        Layout.fillWidth: true; spacing: root.theme.spacingXs
        AppButton {
            objectName: "contextSwitcher"; theme: root.theme
            text: root.controller.title + " ▾"; tip: "작업 Context 선택 · 방향키와 Enter로 선택"
            Accessible.name: "작업 Context 선택: " + root.controller.title
            Accessible.description: "이미지 정보, 분석, 결과, 뷰어·스택, ROI 관리, 검수"
            Layout.fillWidth: true; implicitHeight: theme.controlHeight; labelSize: theme.titleSize; labelWeight: Font.Medium; quiet: true
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
                        rowAvailable: root.controller.available(modelData)
                        text: root.controller.labels[index]; checkable: true
                        autoExclusive: true
                        checked: root.controller.requestedContext === modelData
                        Accessible.name: text
                        onTriggered: root.controller.requestContext(modelData, "MANUAL")
                    }
                }
            }
        }
        AppButton {
            objectName: "closeContextPanel"; theme: root.theme; text: "×"; quiet: true
            implicitWidth: theme.controlHeight; implicitHeight: theme.controlHeight
            Accessible.name: "작업 패널 닫기"; tip: "패널을 닫고 이미지를 넓게 봅니다."
            onClicked: { root.actions.inspectorPanel.trigger(); root.focusRequested() }
        }
    }
    Text {
        objectName: "contextSubtitle"; text: root.controller.subtitle
        visible: root.controller.requestedContext !== "image" || !root.controller.uiState.hasImage
        color: root.theme.muted; font.family: root.theme.fontFamily; font.pixelSize: theme.smallSize
        wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; Layout.fillWidth: true
    }
}
