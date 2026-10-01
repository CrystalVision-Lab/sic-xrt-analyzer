import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Rectangle {
    id: root
    property QtObject theme
    property QtObject uiState
    property var actions
    color: theme.toolbar
    RowLayout {
        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
        spacing: 5
        AppButton { theme: root.theme; action: root.actions.open; text: "열기"; iconName: "open"; tip: "TIFF 열기 · Ctrl+O" }
        AppButton { theme: root.theme; action: root.actions.save; text: ""; iconName: "save"; tip: "프로젝트 저장 형식 준비 중" }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        AppButton { theme: root.theme; action: root.actions.pan; text: "Pan"; iconName: "pan"; checked: uiState.activeTool === "이동"; tip: "이동 도구 · H" }
        AppButton { theme: root.theme; action: root.actions.roi; text: "ROI"; iconName: "roi"; checked: uiState.activeTool === "영역 선택"; tip: "관심 영역 선택 · R" }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        AppButton { theme: root.theme; action: root.actions.zoomOut; text: ""; iconName: "minus"; tip: "축소 · Ctrl+-" }
        Text {
            text: uiState.zoomLabel
            color: theme.text; font.family: theme.monoFontFamily; font.pixelSize: theme.bodySize
            horizontalAlignment: Text.AlignHCenter; Layout.preferredWidth: 52
            ToolTip.text: "화면 맞춤을 100%로 표시"; ToolTip.visible: zoomHover.containsMouse
            MouseArea { id: zoomHover; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
        }
        AppButton { theme: root.theme; action: root.actions.zoomIn; text: ""; iconName: "plus"; tip: "확대 · Ctrl++" }
        AppButton { theme: root.theme; action: root.actions.fit; text: "Fit"; iconName: "fit"; tip: "화면 맞춤 · Ctrl+0" }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        StatusIndicator { theme: root.theme; text: "MODEL UNAVAILABLE"; ink: theme.warning }
        Item { Layout.fillWidth: true }
        Text { text: uiState.loading ? "Loading TIFF…" : uiState.hasRoi ? "ROI SELECTED" : uiState.hasImage ? "IMAGE READY" : "NO IMAGE"; color: theme.muted; font.pixelSize: theme.smallSize; visible: root.width > 1200 }
        AppButton { theme: root.theme; action: root.actions.run; text: "분석 실행"; iconName: "run"; primary: true; tip: uiState.analysisReason }
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border }
}
