import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "inspectorPanel"
    property QtObject theme
    property QtObject uiState
    property int tabIndex: 0
    color: theme.panel; border.color: theme.border
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 12; spacing: 12
        Text { text: "INSPECTOR"; color: theme.muted; font.pixelSize: 11; font.family: theme.fontFamily }
        RowLayout {
            spacing: 2; Layout.fillWidth: true
            Repeater {
                model: ["IMAGE", "ANALYSIS", "RESULT"]
                AppButton { required property int index; required property string modelData; theme: root.theme; text: modelData; checked: root.tabIndex === index; Layout.fillWidth: true; onClicked: root.tabIndex = index }
            }
        }
        ScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: 12
                ColumnLayout {
                    visible: root.tabIndex === 0; Layout.fillWidth: true; spacing: 5
                    SectionHeader { theme: root.theme; text: "IMAGE INFORMATION"; Layout.fillWidth: true }
                    Text { text: uiState.demoMode ? "합성 데모 이미지" : uiState.fileName || "No image selected"; color: theme.text; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "Format"; value: uiState.demoMode ? "SYNTHETIC" : uiState.hasLoadedImage ? "TIFF" : "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "Resolution"; value: uiState.hasImage ? uiState.contentWidth + " × " + uiState.contentHeight + " px" : "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "Bit depth"; value: uiState.hasLoadedImage ? uiState.bitDepth + " bit" : "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "Pages"; value: uiState.hasLoadedImage ? uiState.pageCount + " · 첫 페이지" : "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "Pixel size"; value: "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "Physical size"; value: "—"; Layout.fillWidth: true }
                    Text { text: uiState.sampledPreview ? "원본 좌표 기준 · 표시용 미리보기 축소" : "원본 좌표 기준 · 물리 스케일 미연결"; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    SectionHeader { theme: root.theme; text: "DISPLAY"; Layout.fillWidth: true; Layout.topMargin: 12 }
                    Text { text: "TIFF는 표시용 정규화를 적용합니다. 원본 데이터는 변경하지 않습니다."; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Label { text: "Brightness / Contrast · 준비 중"; color: theme.disabled; font.pixelSize: 11 }
                    AppSlider { theme: root.theme; enabled: false; Layout.fillWidth: true; value: 0.5 }
                    AppComboBox { theme: root.theme; enabled: false; model: ["LUT · 준비 중"]; Layout.fillWidth: true }
                    AppCheckBox { theme: root.theme; text: "ROI Overlay"; checked: uiState.roiLayerVisible; enabled: uiState.hasImage; onToggled: uiState.roiLayerVisible = checked }
                    AppCheckBox { theme: root.theme; text: "Defect Overlay · 준비 중"; enabled: false }
                    AppCheckBox { theme: root.theme; text: "Scale Bar · 스케일 미연결"; enabled: false }
                }
                ColumnLayout {
                    visible: root.tabIndex === 1; Layout.fillWidth: true; spacing: 5
                    SectionHeader { theme: root.theme; text: "REGION OF INTEREST"; Layout.fillWidth: true }
                    Text { visible: !uiState.hasRoi; text: "No region selected\nToolbar의 ROI 도구로 이미지에서 영역을 선택하세요."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Repeater {
                        model: ["X", "Y", "Width", "Height"]
                        InfoRow { required property int index; required property string modelData; theme: root.theme; label: modelData; value: uiState.hasRoi ? [uiState.roiX, uiState.roiY, uiState.roiWidth, uiState.roiHeight][index] + " px" : "—"; Layout.fillWidth: true }
                    }
                    SectionHeader { theme: root.theme; text: "MODEL"; Layout.fillWidth: true; Layout.topMargin: 12 }
                    InfoRow { theme: root.theme; label: "Model"; value: "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "Version"; value: "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "Device"; value: "—"; Layout.fillWidth: true }
                    StatusIndicator { theme: root.theme; text: "MODEL UNAVAILABLE"; ink: theme.warning }
                    Text { text: uiState.analysisReason + "\n분석 실행은 사용할 수 없습니다."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    SectionHeader { theme: root.theme; text: "WORKFLOW"; Layout.fillWidth: true; Layout.topMargin: 12 }
                    InfoRow { theme: root.theme; label: "Image"; value: uiState.hasLoadedImage ? "Loaded" : uiState.demoMode ? "Demo only" : "Not loaded"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "ROI"; value: uiState.hasRoi ? "Selected" : "Not selected"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "Analysis"; value: "Unavailable"; valueColor: theme.warning; Layout.fillWidth: true }
                }
                ColumnLayout {
                    visible: root.tabIndex === 2; Layout.fillWidth: true; spacing: 12
                    SectionHeader { theme: root.theme; text: "ANALYSIS RESULT"; Layout.fillWidth: true }
                    Text { text: "No analysis result"; color: theme.text; font.pixelSize: 14 }
                    Text { text: "승인된 모델과 분석 파이프라인이 연결된 후 분석을 실행하면 결함과 처리 결과를 이곳에서 확인할 수 있습니다."; color: theme.muted; wrapMode: Text.Wrap; font.pixelSize: 12; Layout.fillWidth: true }
                    AppButton { theme: root.theme; text: "View Detected Defects"; enabled: false; iconName: "roi"; Layout.fillWidth: true }
                    AppButton { theme: root.theme; text: "Export Result"; enabled: false; iconName: "export"; Layout.fillWidth: true }
                }
            }
        }
    }
}
