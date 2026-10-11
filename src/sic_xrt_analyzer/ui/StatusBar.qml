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
        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: theme.spacingMd
        StatusIndicator { objectName: "loadingStatus"; Accessible.name: uiState.loadFlow.message; theme: root.theme; text: uiState.viewerStatus; ink: uiState.loadFlow.hasError ? theme.error : uiState.loading || uiState.loadFlow.isStackPreparing ? theme.warning : theme.muted }
        Text { visible: uiState.canNavigateImage; text: uiState.roiEditMode ? "ROI 편집" : uiState.activeTool; color: theme.text; font.pixelSize: theme.captionSize }
        Text { objectName: "statusZoomLabel"; text: uiState.zoomLabel; color: theme.text; font.family: theme.monoFontFamily; font.pixelSize: theme.smallSize }
        Text { text: uiState.cursorX >= 0 ? "X " + uiState.cursorX + "  Y " + uiState.cursorY : "X —  Y —"; color: theme.muted; font.family: theme.monoFontFamily; font.pixelSize: theme.smallSize; Layout.preferredWidth: 125 }
        Text { objectName: "pixelValueLabel"; text: "값 " + (uiState.cursorValue || "—"); color: theme.muted; font.family: theme.monoFontFamily; font.pixelSize: theme.smallSize; Layout.preferredWidth: 160; elide: Text.ElideRight }
        Text { text: uiState.hasImage ? uiState.contentWidth + " × " + uiState.contentHeight : "— × —"; color: theme.muted; font.family: theme.monoFontFamily; font.pixelSize: theme.smallSize }
        Text { text: uiState.hasLoadedImage ? uiState.bitDepth + "-bit" : uiState.demoMode ? "합성" : "—"; color: theme.muted; font.pixelSize: theme.smallSize }
        Text { visible: uiState.loading || uiState.loadFlow.hasError; text: uiState.loadFlow.hasViewableFrame ? "현재 페이지 유지" : ""; color: theme.muted; font.pixelSize: theme.smallSize; elide: Text.ElideRight; Layout.fillWidth: true }
        Item { visible: !uiState.loading && !uiState.loadFlow.hasError; Layout.fillWidth: true }
        Text { visible: uiState.modelAvailable; text: "연구 모델 · " + uiState.analysis.device; color: theme.muted; font.pixelSize: theme.captionSize }
    }
    ToolTip.text: uiState.loadFlow.message + "\n" + uiState.statusText + "\n원본 픽셀값: " + (uiState.cursorValue || "—") + "\n물리 스케일·장비는 미연결 상태입니다"
    ToolTip.visible: statusHover.containsMouse
    MouseArea { id: statusHover; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
}
