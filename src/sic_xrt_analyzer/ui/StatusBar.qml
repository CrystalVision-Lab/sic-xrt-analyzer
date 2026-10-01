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
        StatusIndicator { theme: root.theme; text: uiState.viewerStatus; ink: uiState.loadError ? theme.error : uiState.loading ? theme.warning : uiState.hasImage ? theme.success : theme.muted }
        Text { text: uiState.canNavigateImage ? uiState.activeTool : "—"; color: theme.text; font.pixelSize: theme.smallSize }
        Text { objectName: "statusZoomLabel"; text: uiState.zoomLabel; color: theme.text; font.family: theme.monoFontFamily; font.pixelSize: theme.smallSize }
        Text { text: uiState.cursorX >= 0 ? "X " + uiState.cursorX + "  Y " + uiState.cursorY : "X —  Y —"; color: theme.muted; font.family: theme.monoFontFamily; font.pixelSize: theme.smallSize; Layout.preferredWidth: 125 }
        Text { objectName: "pixelValueLabel"; text: "값 " + (uiState.cursorValue || "—"); color: theme.muted; font.family: theme.monoFontFamily; font.pixelSize: theme.smallSize; Layout.preferredWidth: 160; elide: Text.ElideRight }
        Text { text: uiState.hasImage ? uiState.contentWidth + " × " + uiState.contentHeight : "— × —"; color: theme.muted; font.family: theme.monoFontFamily; font.pixelSize: theme.smallSize }
        Text { text: uiState.hasLoadedImage ? uiState.bitDepth + "-bit" : uiState.demoMode ? "합성" : "—"; color: theme.muted; font.pixelSize: theme.smallSize }
        Text { visible: uiState.loading || uiState.loadError.length > 0; text: uiState.statusText; color: theme.muted; font.pixelSize: theme.smallSize; elide: Text.ElideRight; Layout.fillWidth: true }
        Item { visible: !uiState.loading && !uiState.loadError; Layout.fillWidth: true }
        Text { text: "모델 —"; color: theme.muted; font.pixelSize: theme.smallSize }
    }
    ToolTip.text: uiState.statusText + "\n원본 픽셀값: " + (uiState.cursorValue || "—") + "\n물리 스케일·장비는 미연결 상태입니다"
    ToolTip.visible: statusHover.containsMouse
    MouseArea { id: statusHover; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
}
