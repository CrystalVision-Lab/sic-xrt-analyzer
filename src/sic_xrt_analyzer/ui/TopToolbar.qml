import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Rectangle {
    id: root
    property QtObject theme
    property QtObject uiState
    property var actions
    property var hostWindow
    color: theme.toolbar
    ToolPalette { visible: uiState.stackFeaturesVisible; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 8; height: 30; theme: root.theme; uiState: root.uiState; hostWindow: root.hostWindow }
    RowLayout {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 40; anchors.leftMargin: 10; anchors.rightMargin: 10
        spacing: 5
        AppButton { theme: root.theme; action: root.actions.open; text: "열기"; iconName: "open"; tip: "TIFF/JPG 열기 · Ctrl+O" }
        AppButton { theme: root.theme; action: root.actions.save; text: ""; iconName: "save"; tip: "이미지 파일의 새 복사본 저장 · Ctrl+S" }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        AppButton { theme: root.theme; action: root.actions.pan; text: "Pan"; iconName: "pan"; checked: uiState.activeTool === "Pan" && !uiState.roiEditMode; tip: "Pan · H" }
        AppButton { theme: root.theme; action: root.actions.roi; text: "ROI"; iconName: "roi"; checked: uiState.activeTool === "ROI" && !uiState.roiEditMode; tip: "ROI · R" }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        AppButton { theme: root.theme; action: root.actions.zoomOut; text: ""; iconName: "minus"; tip: "축소 · Ctrl+-" }
        Text {
            text: uiState.zoomLabel
            color: theme.text; font.family: theme.monoFontFamily; font.pixelSize: theme.bodySize
            horizontalAlignment: Text.AlignHCenter; Layout.preferredWidth: 64
            ToolTip.text: uiState.fitMode ? "화면 맞춤 · 실제 배율 " + (Math.round(uiState.effectiveZoom * 1000) / 10) + "%" : "원본 픽셀 기준 화면 배율 · 100%는 1:1"; ToolTip.visible: zoomHover.containsMouse
            MouseArea { id: zoomHover; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
        }
        AppButton { theme: root.theme; action: root.actions.zoomIn; text: ""; iconName: "plus"; tip: "확대 · Ctrl++" }
        AppButton { theme: root.theme; action: root.actions.fit; text: "화면 맞춤"; iconName: "fit"; tip: "화면 맞춤 · Ctrl+0" }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        StatusIndicator { objectName: "researchModelStatus"; theme: root.theme; text: uiState.research.loading ? "모델 준비 중" : uiState.modelAvailable ? "연구 모델 연결됨" : "모델 미연결"; ink: uiState.modelAvailable ? theme.accent : theme.warning }
        Item { Layout.fillWidth: true }
        AppButton { theme: root.theme; action: root.actions.run; text: "분석 실행"; iconName: "run"; primary: true; tip: uiState.analysisReason }
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border }
}
