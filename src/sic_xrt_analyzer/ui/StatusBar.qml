import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    property QtObject theme
    property QtObject uiState

    implicitHeight: theme.statusHeight
    color: theme.panel
    border.color: theme.border
    border.width: 1

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        spacing: 18
        Text {
            text: uiState.statusText
            color: theme.text
            font.family: theme.fontFamily
            font.pixelSize: theme.smallSize
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
        Text {
            text: "도구  " + (uiState.canNavigateImage ? uiState.activeTool : "—")
            color: theme.muted
            font.family: theme.fontFamily
            font.pixelSize: theme.smallSize
        }
        Text {
            text: "배율  " + uiState.zoomLabel
            color: theme.muted
            font.family: theme.monoFontFamily
            font.pixelSize: theme.smallSize
        }
        Text {
            text: "좌표  —"
            color: theme.muted
            font.family: theme.monoFontFamily
            font.pixelSize: theme.smallSize
        }
        Text {
            text: "이미지 크기  —"
            color: theme.muted
            font.family: theme.monoFontFamily
            font.pixelSize: theme.smallSize
        }
    }
}
