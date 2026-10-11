import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "currentFileNavigation"
    property QtObject theme
    property QtObject uiState
    signal activated()
    spacing: 4
    SectionHeader { theme: root.theme; text: "현재 이미지" }
    Text {
        objectName: "currentFileName"
        Layout.fillWidth: true; Layout.preferredHeight: 25
        text: uiState.demoMode ? "합성 데모" : uiState.fileName || "열린 이미지 없음"
        color: hover.containsMouse && uiState.hasImage ? theme.accent : theme.muted
        elide: Text.ElideMiddle; font.pixelSize: theme.smallSize; verticalAlignment: Text.AlignVCenter
        MouseArea { id: hover; anchors.fill: parent; enabled: root.uiState.hasImage; hoverEnabled: true; onClicked: root.activated() }
        ToolTip.text: uiState.filePath; ToolTip.visible: hover.containsMouse && !!uiState.filePath
    }
}
