import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "stackPreparationOverlay"
    property QtObject theme
    property QtObject loadFlow
    property var closeAction
    visible: loadFlow.isStackPreparing
    width: Math.min(360, parent.width - 40)
    height: contents.implicitHeight + 32
    color: theme.panel; border.color: theme.border; radius: theme.radiusSm
    // This status card is nonmodal: the current image remains usable while preparing.
    ColumnLayout {
        id: contents; anchors.fill: parent; anchors.margins: 16; spacing: root.theme.spacingSm
        RowLayout {
            Layout.alignment: Qt.AlignHCenter; spacing: root.theme.spacingSm
            BusyIndicator { objectName: "stackPreparationSpinner"; implicitWidth: 24; implicitHeight: 24; running: root.visible }
            Text { text: "TIFF 스택 준비 중…"; color: root.theme.text; font.pixelSize: root.theme.bodySize }
        }
        ProgressBar {
            id: progress; objectName: "stackPreparationProgress"; Layout.fillWidth: true
            from: 0; to: Math.max(1, root.loadFlow.totalPages); value: root.loadFlow.preparedPages
            background: Rectangle { implicitHeight: 6; color: root.theme.border; radius: 3 }
            contentItem: Item { implicitHeight: 6
                Rectangle { width: parent.width * progress.visualPosition; height: parent.height; color: root.theme.accent; radius: 3 }
            }
        }
        Text {
            objectName: "stackPreparationText"; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter
            text: root.loadFlow.preparedPages + " / " + root.loadFlow.totalPages + " 페이지 · " + Math.round(progress.position * 100) + "%"
            color: root.theme.text; font.pixelSize: root.theme.bodySize; Accessible.name: text
        }
        AppButton {
            objectName: "cancelStackOverlay"; Layout.alignment: Qt.AlignHCenter
            theme: root.theme; action: root.closeAction; text: "준비 취소·닫기"; quiet: true
        }
    }
}
