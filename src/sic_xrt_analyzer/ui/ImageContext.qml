import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "imageContext"
    property QtObject theme
    property QtObject uiState
    readonly property string informationPriority: "secondary"
    spacing: 5
    SectionHeader { theme: root.theme; text: "이미지 정보"; Layout.fillWidth: true }
    Text { text: uiState.demoMode ? "합성 데모 이미지" : uiState.fileName || "이미지 없음"; color: theme.text; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
    InfoRow { theme: root.theme; label: "형식"; value: uiState.demoMode ? "합성 데모" : uiState.imageFormat || "—"; Layout.fillWidth: true }
    Text { visible: uiState.imageFormat === "JPEG"; text: "JPEG 디코딩 RGB 8-bit · 손실 압축 이미지\n파일 픽셀 방향 유지 (EXIF 자동 회전 미적용)"; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
    InfoRow { theme: root.theme; label: "원본 해상도"; value: uiState.hasImage ? uiState.contentWidth + " × " + uiState.contentHeight + " px" : "—"; Layout.fillWidth: true }
    InfoRow { objectName: "previewSizeRow"; theme: root.theme; visible: uiState.sampledPreview; label: "표시 미리보기"; value: uiState.previewWidth + " × " + uiState.previewHeight + " px"; Layout.fillWidth: true }
    InfoRow { theme: root.theme; label: "비트 깊이"; value: uiState.hasLoadedImage ? uiState.bitDepth + " bit" : "—"; Layout.fillWidth: true }
    InfoRow { theme: root.theme; label: "페이지"; value: uiState.hasLoadedImage ? (uiState.pageIndex + 1) + " / " + uiState.pageCount : "—"; Layout.fillWidth: true }
    InfoRow { theme: root.theme; label: "데이터 타입"; value: uiState.dtype || "—"; Layout.fillWidth: true }
    InfoRow { theme: root.theme; label: "픽셀 크기"; value: "—"; Layout.fillWidth: true }
    InfoRow { theme: root.theme; label: "물리 크기"; value: "—"; Layout.fillWidth: true }
    Text { text: uiState.sampledPreview ? "원본 좌표 기준 · 표시용 미리보기 축소" : "원본 좌표 기준 · 물리 스케일 미연결"; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
    SectionHeader { theme: root.theme; text: "표시"; Layout.fillWidth: true; Layout.topMargin: 12 }
    Text { text: "표시용 정규화 · 원본 데이터 유지"; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
    AppCheckBox { theme: root.theme; text: "ROI 표시"; checked: uiState.roiLayerVisible; enabled: uiState.hasImage; onToggled: uiState.roiLayerVisible = checked }
}
