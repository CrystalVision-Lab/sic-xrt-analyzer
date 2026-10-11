import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "viewerContext"
    property QtObject theme
    property QtObject uiState
    property var actions
    readonly property string informationPriority: "secondary"
    spacing: theme.spacingMd
    Text {
        visible: !uiState.hasLoadedImage; Layout.fillWidth: true
        text: "TIFF/JPG를 열면 페이지 탐색과 밝기·대비를 조절할 수 있습니다."
        color: theme.muted; font.pixelSize: theme.bodySize; wrapMode: Text.Wrap
    }
    StackControls { theme: root.theme; uiState: root.uiState; actions: root.actions; Layout.fillWidth: true }
    Text { visible: uiState.stack.pixelError.length > 0; text: "원본 픽셀 읽기 실패: " + uiState.stack.pixelError; color: theme.warning; font.pixelSize: theme.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
}
