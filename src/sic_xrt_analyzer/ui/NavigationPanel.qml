import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Rectangle {
    id: root
    property QtObject theme
    property QtObject uiState
    property var recentFiles: []
    property bool collapsed: false
    signal collapseRequested()
    signal workspaceRequested(int index)
    signal recentRequested(string path)
    implicitWidth: collapsed ? 42 : theme.navigationWidth
    color: theme.panel
    border.color: theme.border
    ColumnLayout {
        anchors.fill: parent; spacing: 0
        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 38; Layout.leftMargin: 10; Layout.rightMargin: 6
            Text { visible: !root.collapsed; text: "WORKSPACE"; color: theme.muted; font.pixelSize: theme.sectionSize; font.letterSpacing: 1; Layout.fillWidth: true }
            AppButton { theme: root.theme; text: root.collapsed ? "›" : "‹"; quiet: true; implicitWidth: 28; tip: "Navigator 접기 / 펼치기"; onClicked: root.collapseRequested() }
        }
        Repeater {
            model: [{name:"이미지 분석",icon:"image"},{name:"Wafer Map",icon:"wafer"},{name:"이미지 정합",icon:"align"},{name:"3D Viewer",icon:"cube"}]
            delegate: Rectangle {
                required property int index
                required property var modelData
                Layout.fillWidth: true; Layout.preferredHeight: 34
                color: root.uiState.workspaceIndex === index ? "#252d33" : itemHover.containsMouse ? theme.hover : "transparent"
                Rectangle { visible: root.uiState.workspaceIndex === index; width: 2; height: parent.height; color: theme.accent }
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 13; anchors.rightMargin: 8; spacing: 8
                    AppIcon { name: modelData.icon; ink: root.uiState.workspaceIndex === index ? theme.accent : theme.muted }
                    Text { visible: !root.collapsed; text: modelData.name; color: root.uiState.workspaceIndex === index ? theme.text : theme.muted; font.pixelSize: theme.bodySize; Layout.fillWidth: true }
                    Text { visible: !root.collapsed && index > 0; text: "준비"; color: theme.disabled; font.pixelSize: 10 }
                }
                MouseArea { id: itemHover; anchors.fill: parent; hoverEnabled: true; onClicked: root.workspaceRequested(index) }
                ToolTip.visible: itemHover.containsMouse && root.collapsed
                ToolTip.text: modelData.name
            }
        }
        ColumnLayout {
            visible: !root.collapsed; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; spacing: 4
            SectionHeader { theme: root.theme; text: "RECENT IMAGES" }
            Text { visible: root.recentFiles.length === 0; text: "최근 이미지 없음"; color: theme.disabled; font.pixelSize: theme.smallSize; Layout.topMargin: 4 }
            Repeater {
                model: root.recentFiles.slice(0,5)
                delegate: Text {
                    required property string modelData
                    Layout.fillWidth: true; Layout.preferredHeight: 25
                    text: modelData.split(/[\\/]/).pop(); color: recentHover.containsMouse ? theme.accent : theme.muted
                    elide: Text.ElideMiddle; font.pixelSize: theme.smallSize; verticalAlignment: Text.AlignVCenter
                    MouseArea { id: recentHover; anchors.fill: parent; hoverEnabled: true; onClicked: root.recentRequested(modelData) }
                    ToolTip.text: modelData; ToolTip.visible: recentHover.containsMouse
                }
            }
        }
        Item { Layout.fillHeight: true }
        ColumnLayout {
            visible: !root.collapsed; Layout.fillWidth: true; Layout.margins: 12; spacing: 6
            Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }
            Text { text: "SiC XRT ANALYZER"; color: theme.muted; font.pixelSize: 10; font.letterSpacing: 0.8 }
            Text { text: "LOCAL WORKSPACE"; color: theme.disabled; font.pixelSize: 10 }
        }
    }
}
