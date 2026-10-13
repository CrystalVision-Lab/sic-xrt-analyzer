import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Rectangle {
    id: root
    objectName: "workspaceNavigation"
    property QtObject theme
    property QtObject uiState
    property var recentFiles: []
    property bool collapsed: false
    signal projectRequested()
    signal collapseRequested()
    signal workspaceRequested(int index)
    signal recentRequested(string path)
    implicitWidth: collapsed ? 42 : theme.navigationWidth
    color: theme.panel
    ColumnLayout {
        anchors.fill: parent; spacing: 0
        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 38; Layout.leftMargin: 10; Layout.rightMargin: 6
            Text { visible: !root.collapsed; text: "작업 영역"; color: theme.muted; font.pixelSize: theme.sectionSize; font.letterSpacing: 1; Layout.fillWidth: true }
            AppButton { theme: root.theme; text: root.collapsed ? "›" : "‹"; quiet: true; implicitWidth: 28; tip: "작업 영역 접기 / 펼치기"; onClicked: root.collapseRequested() }
        }
        Repeater {
            model: [{name:"이미지 뷰어",icon:"image"},{name:"Wafer Map",icon:"wafer"},{name:"이미지 정합",icon:"align"}]
            delegate: Rectangle {
                required property int index
                required property var modelData
                Layout.fillWidth: true; Layout.preferredHeight: theme.listRowHeight
                color: root.uiState.workspaceIndex === index ? "#252d33" : itemHover.containsMouse ? theme.hover : "transparent"
                Rectangle { visible: root.uiState.workspaceIndex === index; width: 2; height: parent.height; color: theme.accent }
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 13; anchors.rightMargin: 8; spacing: theme.spacingSm
                    AppIcon { name: modelData.icon; ink: root.uiState.workspaceIndex === index ? theme.accent : theme.muted }
                    Text { objectName: index === 0 ? "workspaceViewerLabel" : ""; visible: !root.collapsed; text: modelData.name; color: root.uiState.workspaceIndex === index ? theme.text : theme.muted; font.pixelSize: theme.bodySize; Layout.fillWidth: true }
                }
                MouseArea { id: itemHover; anchors.fill: parent; hoverEnabled: true; onClicked: root.workspaceRequested(index) }
                ToolTip.visible: itemHover.containsMouse && (root.collapsed || index > 0)
                ToolTip.text: modelData.name
            }
        }
        CurrentFileNavigation {
            visible: !root.collapsed; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
            theme: root.theme; uiState: root.uiState; onActivated: root.workspaceRequested(0)
        }
        ColumnLayout {
            visible: !root.collapsed; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; spacing: theme.spacingXs
            SectionHeader { theme: root.theme; text: "최근 이미지" }
            Text { visible: root.recentFiles.length === 0; text: "최근 이미지 없음"; color: theme.disabled; font.pixelSize: theme.smallSize; Layout.topMargin: 4 }
            Repeater {
                model: root.recentFiles.slice(0,5)
                delegate: Text {
                    required property string modelData
                    Layout.fillWidth: true; Layout.preferredHeight: theme.controlHeight
                    text: modelData.split(/[\\/]/).pop(); color: recentHover.containsMouse ? theme.accent : theme.muted
                    elide: Text.ElideMiddle; font.pixelSize: theme.smallSize; verticalAlignment: Text.AlignVCenter
                    MouseArea { id: recentHover; anchors.fill: parent; hoverEnabled: true; onClicked: root.recentRequested(modelData) }
                    ToolTip.text: modelData; ToolTip.visible: recentHover.containsMouse
                }
            }
        }
        ColumnLayout {
            visible: !root.collapsed && root.uiState.project.active; Layout.fillWidth: true; Layout.margins: 12; spacing: theme.spacingXs
            Text { objectName: "activeProjectName"; textFormat: Text.PlainText; text: root.uiState.project.name; color: theme.text; elide: Text.ElideRight; Layout.fillWidth: true; font.pixelSize: theme.smallSize }
            Text { objectName: "activeProjectStatus"; text: (root.uiState.project.readOnly ? "읽기 전용" : root.uiState.project.dirty ? "저장하지 않은 변경" : "저장됨") + (root.uiState.project.needsSource ? " · 원본 연결 필요" : "") + " · 원본 " + root.uiState.project.sourceCount + " · Run " + root.uiState.project.runCount; color: root.uiState.project.dirty ? theme.warning : theme.muted; font.pixelSize: theme.captionSize; Layout.fillWidth: true; wrapMode: Text.Wrap }
            AppButton { objectName: "projectWorkspaceButton"; theme: root.theme; text: "프로젝트 · 이력…"; quiet: true; Layout.fillWidth: true; onClicked: fileBridge.projects.state.active && root.projectRequested() }
        }
        Item { Layout.fillHeight: true }
        ColumnLayout {
            visible: !root.collapsed; Layout.fillWidth: true; Layout.margins: 12; spacing: theme.spacingXs
            Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }
            Text { text: "SiC XRT Analyzer"; color: theme.muted; font.pixelSize: theme.captionSize; font.letterSpacing: 0.8 }
            Text { text: "로컬 작업 공간"; color: theme.disabled; font.pixelSize: theme.captionSize }
        }
    }
}
