import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "viewerHeader"
    property QtObject theme
    property QtObject uiState
    readonly property string informationPriority: "secondary"
    color: theme.viewerHeader
    RowLayout {
        anchors.fill: parent; anchors.margins: 12; spacing: 14
        ColumnLayout {
            spacing: 3; Layout.fillWidth: true
            Text { text: "XRT VIEWER"; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: 11 }
            Text { text: uiState.demoMode ? "합성 데모 · 실제 XRT 데이터 아님" : uiState.fileName || "XRT 이미지 없음"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 12; elide: Text.ElideMiddle; Layout.fillWidth: true }
        }
        Text { objectName: "viewerPageMetadata"; text: uiState.hasImage ? uiState.contentWidth + " × " + uiState.contentHeight + (uiState.demoMode ? " · 데모" : " · " + uiState.dtype + " · 현재 " + (uiState.pageIndex + 1) + "/" + uiState.pageCount) : "TIFF / JPG"; color: theme.muted; font.family: theme.monoFontFamily; font.pixelSize: 11 }
        StatusIndicator { objectName: "viewerToolMode"; theme: root.theme; text: uiState.roiFlow.viewerMode; ink: theme.accent; visible: uiState.canNavigateImage }
    }
}
