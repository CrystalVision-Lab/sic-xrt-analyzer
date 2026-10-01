import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property QtObject theme
    property QtObject uiState
    property bool collapsed: false
    signal collapseRequested()
    signal workspaceRequested(int index)

    implicitWidth: collapsed ? 54 : theme.navigationWidth
    color: theme.panel
    border.color: theme.border
    border.width: 1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: collapsed ? 6 : 12
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 38
            Text {
                visible: !root.collapsed
                text: "작업 영역"
                color: theme.muted
                font.family: theme.fontFamily
                font.pixelSize: theme.smallSize
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
            AppButton {
                theme: root.theme
                text: root.collapsed ? ">" : "<"
                quiet: true
                implicitWidth: 34
                tip: root.collapsed ? "탐색 패널 펼치기" : "탐색 패널 접기"
                onClicked: root.collapseRequested()
            }
        }

        Repeater {
            model: [
                { name: "이미지 분석", shortName: "분석" },
                { name: "Wafer Map", shortName: "맵" },
                { name: "이미지 정합", shortName: "정합" },
                { name: "3D 보기", shortName: "3D" }
            ]
            delegate: AppButton {
                required property var modelData
                required property int index
                theme: root.theme
                text: root.collapsed ? modelData.shortName : modelData.name
                tip: modelData.name
                quiet: true
                checked: root.uiState.workspaceIndex === index
                Layout.fillWidth: true
                implicitHeight: 42
                onClicked: root.workspaceRequested(index)
            }
        }
        Item { Layout.fillHeight: true }
        Text {
            visible: !root.collapsed
            text: "분석 기능은 순차적으로 연결됩니다."
            color: theme.muted
            font.family: theme.fontFamily
            font.pixelSize: theme.captionSize
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
