import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    objectName: "viewerToolGroup"
    property QtObject theme
    property var actions
    property QtObject uiState
    spacing: 5
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

}
