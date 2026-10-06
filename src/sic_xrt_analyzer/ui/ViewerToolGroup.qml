import QtQuick
import QtQuick.Layouts

RowLayout {
    id: root
    objectName: "viewerToolGroup"
    property QtObject theme
    property var actions
    property QtObject uiState
    property var hostWindow
    spacing: 5
    ToolbarButton { objectName: "toolbarPan"; theme: root.theme; action: root.actions.pan; text: "Pan"; iconName: "pan"; tip: "이미지 이동 · H"; onClicked: Qt.callLater(function() { root.hostWindow.viewer.focusView() }) }
    ToolbarButton { objectName: "toolbarZoom"; theme: root.theme; action: root.actions.tools.zoom; text: "Zoom"; toolName: "Zoom"; tip: "확대 도구 · 이미지 클릭: 확대 / Alt+클릭: 축소 · Ctrl+휠: 확대·축소" }
    ToolbarButton { objectName: "toolbarFit"; theme: root.theme; action: root.actions.fit; text: "화면 맞춤"; iconName: "fit"; tip: "화면에 맞춤 · Ctrl+0"; onClicked: Qt.callLater(function() { root.hostWindow.viewer.focusView() }) }
}
