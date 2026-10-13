import QtQuick
import QtQuick.Controls

ToolbarButton {
    id: root
    objectName: "toolbarContextTools"
    property QtObject uiState
    property var actions
    property var hostWindow
    text: "패널 ▾"; tip: "이미지 정보 · 표시 설정 · ROI · 결과"
    onClicked: menu.open()
    ToolTip.visible: hovered && !menu.visible
    AppMenu {
        id: menu; objectName: "toolbarContextMenu"; y: root.height
        width: 220; x: root.width - width
        onClosed: Qt.callLater(function() { root.hostWindow.viewer.focusView() })
        Repeater {
            model: root.hostWindow.contextPanel ? ["image", "viewer", "roi", "analysis", "result", "feedback"] : []
            ToolbarMenuItem {
                required property int index
                required property string modelData
                objectName: "toolbarContext" + modelData
                rowAvailable: !root.uiState.stackFeaturesVisible || ["analysis", "result", "feedback"].indexOf(modelData) < 0
                text: ["이미지 정보", "뷰어 · 스택", "ROI 관리", "분석", "결과", "검수"][index]
                checkable: true
                checked: !root.hostWindow.inspectorCollapsed && root.hostWindow.contextPanel.requestedContext === modelData
                onTriggered: root.hostWindow.openContext(modelData)
            }
        }
        MenuSeparator {}
        ToolbarMenuItem { action: root.actions.roiLayer; checkable: true; checked: root.uiState.roiLayerVisible }
        ToolbarMenuItem {
            objectName: "toolbarCloseContext"; text: "패널 닫기"; enabled: !root.hostWindow.inspectorCollapsed
            onTriggered: root.actions.inspectorPanel.trigger()
        }
    }
}
