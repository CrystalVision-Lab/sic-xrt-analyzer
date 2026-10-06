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
        Text { text: uiState.hasImage ? uiState.contentWidth + " × " + uiState.contentHeight + (uiState.demoMode ? " · 데모" : " · " + uiState.dtype + " · " + (uiState.pageIndex + 1) + "/" + uiState.pageCount) : "TIFF / JPG"; color: theme.muted; font.family: theme.monoFontFamily; font.pixelSize: 11 }
        StatusIndicator { theme: root.theme; text: uiState.roiEditMode ? "ROI 편집" : uiState.activeTool.toUpperCase(); ink: theme.accent; visible: uiState.canNavigateImage }
    }
}
