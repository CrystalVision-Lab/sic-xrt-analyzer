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
        Text { text: "정보 및 분석"; color: theme.muted; font.pixelSize: 11; font.family: theme.fontFamily }
        RowLayout {
            spacing: 2; Layout.fillWidth: true
            Repeater {
                model: ["이미지", "분석", "결과"]
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
                    SectionHeader { theme: root.theme; text: "이미지 정보"; Layout.fillWidth: true }
                    Text { text: uiState.demoMode ? "합성 데모 이미지" : uiState.fileName || "이미지 없음"; color: theme.text; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "형식"; value: uiState.demoMode ? "합성 데모" : uiState.hasLoadedImage ? "TIFF" : "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "해상도"; value: uiState.hasImage ? uiState.contentWidth + " × " + uiState.contentHeight + " px" : "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "비트 깊이"; value: uiState.hasLoadedImage ? uiState.bitDepth + " bit" : "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "페이지"; value: uiState.hasLoadedImage ? uiState.pageCount + " · 첫 페이지" : "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "픽셀 크기"; value: "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "물리 크기"; value: "—"; Layout.fillWidth: true }
                    Text { text: uiState.sampledPreview ? "원본 좌표 기준 · 표시용 미리보기 축소" : "원본 좌표 기준 · 물리 스케일 미연결"; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    SectionHeader { theme: root.theme; text: "표시"; Layout.fillWidth: true; Layout.topMargin: 12 }
                    Text { text: "표시용 정규화 · 원본 데이터 유지"; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    AppCheckBox { theme: root.theme; text: "ROI 표시"; checked: uiState.roiLayerVisible; enabled: uiState.hasImage; onToggled: uiState.roiLayerVisible = checked }
                }
                ColumnLayout {
                    visible: root.tabIndex === 1; Layout.fillWidth: true; spacing: 5
                    SectionHeader { theme: root.theme; text: "ROI"; Layout.fillWidth: true }
                    Text { visible: !uiState.hasRoi; text: "선택된 ROI 없음\n도구 모음의 ROI로 영역을 선택하세요."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Repeater {
                        model: ["X", "Y", "너비", "높이"]
                        InfoRow { required property int index; required property string modelData; theme: root.theme; label: modelData; value: uiState.hasRoi ? [uiState.roiX, uiState.roiY, uiState.roiWidth, uiState.roiHeight][index] + " px" : "—"; Layout.fillWidth: true }
                    }
                    SectionHeader { theme: root.theme; text: "모델"; Layout.fillWidth: true; Layout.topMargin: 12 }
                    InfoRow { theme: root.theme; label: "모델"; value: "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "버전"; value: "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "장치"; value: "—"; Layout.fillWidth: true }
                    StatusIndicator { theme: root.theme; text: "모델 미연결"; ink: theme.warning }
                    Text { text: "승인된 모델과 분석 파이프라인이 연결되지 않아 분석을 실행할 수 없습니다."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    SectionHeader { theme: root.theme; text: "작업 상태"; Layout.fillWidth: true; Layout.topMargin: 12 }
                    InfoRow { theme: root.theme; label: "이미지"; value: uiState.hasLoadedImage ? "준비 완료" : uiState.demoMode ? "합성 데모" : "이미지 없음"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "ROI"; value: uiState.hasRoi ? "선택됨" : "미선택"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "분석"; value: "사용 불가"; valueColor: theme.warning; Layout.fillWidth: true }
                }
                ColumnLayout {
                    visible: root.tabIndex === 2; Layout.fillWidth: true; spacing: 12
                    SectionHeader { theme: root.theme; text: "분석 결과"; Layout.fillWidth: true }
                    Text { text: "분석 결과 없음"; color: theme.text; font.pixelSize: 14 }
                    Text { text: "분석 모델 연결 후 결함 검출 결과가 이곳에 표시됩니다."; color: theme.muted; wrapMode: Text.Wrap; font.pixelSize: 12; Layout.fillWidth: true }
                    AppButton { theme: root.theme; text: "검출 결함 보기"; enabled: false; iconName: "roi"; Layout.fillWidth: true }
                    AppButton { theme: root.theme; text: "결과 내보내기"; enabled: false; iconName: "export"; Layout.fillWidth: true }
                }
            }
        }
    }
}
