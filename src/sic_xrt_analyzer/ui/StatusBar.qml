import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Rectangle {
    id: root
    property QtObject theme
    property QtObject uiState
    color: theme.toolbar
    Rectangle { width: parent.width; height: 1; color: theme.border }
    RowLayout {
        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 12
        StatusIndicator { theme: root.theme; text: uiState.workflowLabel; ink: uiState.loadError ? theme.error : uiState.loading ? theme.warning : uiState.hasImage ? theme.success : theme.muted }
        Text { text: uiState.canNavigateImage ? (uiState.activeTool === "이동" ? "PAN" : "ROI") : "—"; color: theme.text; font.pixelSize: theme.smallSize }
        Text { text: "ZOOM " + uiState.zoomLabel; color: theme.muted; font.family: theme.monoFontFamily; font.pixelSize: theme.smallSize }
        Text { text: uiState.cursorX >= 0 ? "X " + uiState.cursorX + "  Y " + uiState.cursorY : "X —  Y —"; color: theme.muted; font.family: theme.monoFontFamily; font.pixelSize: theme.smallSize; Layout.preferredWidth: 125 }
        Text { text: uiState.hasImage ? uiState.contentWidth + " × " + uiState.contentHeight : "— × —"; color: theme.muted; font.family: theme.monoFontFamily; font.pixelSize: theme.smallSize }
        Text { text: uiState.hasLoadedImage ? uiState.bitDepth + "-bit" : uiState.demoMode ? "SYNTHETIC" : "—-bit"; color: theme.muted; font.pixelSize: theme.smallSize }
        Text { text: "GRAY —"; color: theme.disabled; font.family: theme.monoFontFamily; font.pixelSize: theme.smallSize; visible: root.width > 1200 }
        Text {
            text: uiState.statusText; color: theme.muted; font.pixelSize: theme.smallSize; elide: Text.ElideRight; Layout.fillWidth: true
            ToolTip.text: uiState.statusText + "\n원본 픽셀 조회·물리 스케일·장비 연결은 준비 중입니다"; ToolTip.visible: messageHover.containsMouse
            MouseArea { id: messageHover; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
        }
        StatusIndicator { theme: root.theme; text: "MODEL —"; ink: theme.warning }
    }
}
