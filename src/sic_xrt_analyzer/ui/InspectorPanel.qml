import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "inspectorPanel"
    property QtObject theme
    property QtObject uiState
    property int tabIndex: 0
    signal importRequested()
    signal boundsRequested()
    signal saveRequested()
    color: theme.panel; border.color: theme.border
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 12; spacing: 12
        Text { text: "정보 및 분석"; color: theme.muted; font.pixelSize: 11; font.family: theme.fontFamily }
        RowLayout {
            objectName: "inspectorTabs"
            spacing: 2; Layout.fillWidth: true
            Repeater {
                model: ["이미지", "분석", "결과", "뷰어", "ROI"]
                AppButton { required property int index; required property string modelData; objectName: "inspectorTab" + index; theme: root.theme; text: modelData; checked: root.tabIndex === index; Layout.fillWidth: true; onClicked: root.tabIndex = index }
            }
        }
        ScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: 12
                ColumnLayout {
                    visible: root.tabIndex === 4; Layout.fillWidth: true; spacing: 10
                    SectionHeader { theme: root.theme; text: "ImageJ ROI"; Layout.fillWidth: true }
                    Text { text: "대응하는 이미지를 먼저 열고 .roi 또는 RoiSet.zip을 가져오세요. 원본 좌표를 그대로 표시합니다."; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    AppButton { objectName: "importRoisButton"; theme: root.theme; text: "ROI / ZIP 가져오기…"; iconName: "roi"; Layout.fillWidth: true; enabled: uiState.hasLoadedImage && !uiState.loading && !uiState.importedRois.busy; onClicked: root.importRequested() }
                    Text { visible: uiState.importedRois.busy; text: "ROI 불러오는 중…"; color: theme.accent; font.pixelSize: 11 }
                    RoiEditor { theme: root.theme; uiState: root.uiState; Layout.fillWidth: true; onSaveRequested: root.saveRequested() }
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "가져온 ROI " + uiState.importedRois.items.length + "개"; color: theme.text; font.pixelSize: 12; Layout.fillWidth: true }
                        AppButton { theme: root.theme; text: "목록 비우기"; enabled: uiState.importedRois.items.length > 0 || uiState.importedRois.busy; onClicked: fileBridge.clearImportedRois() }
                    }
                    Repeater {
                        model: uiState.importedRois.items
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true; implicitHeight: roiRow.implicitHeight + 12
                            color: modelData.selected ? theme.accentPale : theme.surface
                            border.color: modelData.selected ? theme.accent : theme.border; radius: 3
                            RowLayout {
                                id: roiRow; anchors.fill: parent; anchors.margins: 6; spacing: 6
                                AppCheckBox { theme: root.theme; text: ""; checked: modelData.visible; onToggled: fileBridge.setImportedRoiVisible(modelData.id, checked) }
                                Item {
                                    Layout.fillWidth: true; implicitHeight: roiLabels.implicitHeight
                                    ColumnLayout {
                                        id: roiLabels; anchors.fill: parent; spacing: 3
                                        Text { text: modelData.name; color: modelData.color; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                        Text { text: (modelData.kind === "point" ? "점 " : modelData.kind === "line" ? "선 좌표 " : "도형 좌표 ") + modelData.pointCount + "개 · " + (modelData.page ? "페이지 " + modelData.page : "모든 페이지") + (modelData.active ? "" : " · 현재 페이지 미표시"); color: theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                    }
                                    MouseArea { anchors.fill: parent; onClicked: fileBridge.selectImportedRoi(modelData.id) }
                                }
                                AppButton { theme: root.theme; text: "×"; tip: "뷰어 목록에서 제거"; onClicked: fileBridge.removeImportedRoi(modelData.id) }
                            }
                        }
                    }
                    AppButton { objectName: "selectImportedBoundsButton"; theme: root.theme; text: "외접 사각형으로 선택"; Layout.fillWidth: true; enabled: !uiState.loading && uiState.importedRois.items.some(function(r) { return r.selected && r.active }); onClicked: root.boundsRequested() }
                    Text { visible: uiState.importedRois.items.length > 0; text: "위 선택은 점/다각형의 외접 사각형입니다. ROI 도형 마스크 분석은 아직 연결되지 않았습니다."; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Text { visible: uiState.importedRois.errors.length > 0; text: "불러오기 오류 " + uiState.importedRois.errors.length + "개"; color: theme.warning; font.pixelSize: 12 }
                    Repeater {
                        model: uiState.importedRois.errors.slice(0, 100)
                        Text { required property string modelData; text: modelData; color: theme.warning; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    }
                }
                ColumnLayout {
                    visible: root.tabIndex === 3; Layout.fillWidth: true; spacing: 12
                    Text {
                        visible: !uiState.hasLoadedImage; Layout.fillWidth: true
                        text: "TIFF/JPG를 열면 페이지 탐색과 밝기·대비를 조절할 수 있습니다."
                        color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap
                    }
                    StackControls { theme: root.theme; uiState: root.uiState; Layout.fillWidth: true }
                    Text { visible: uiState.stack.pixelError.length > 0; text: "원본 픽셀 읽기 실패: " + uiState.stack.pixelError; color: theme.warning; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
                ColumnLayout {
                    visible: root.tabIndex === 0; Layout.fillWidth: true; spacing: 5
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
                ColumnLayout {
                    visible: root.tabIndex === 1; Layout.fillWidth: true; spacing: 5
                    SectionHeader { theme: root.theme; text: "ROI"; Layout.fillWidth: true }
                    Text { visible: !uiState.hasRoi; text: "선택된 ROI 없음\n도구 모음의 ROI로 영역을 선택하세요."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Repeater {
                        model: ["X", "Y", "너비", "높이"]
                        InfoRow { required property int index; required property string modelData; theme: root.theme; label: modelData; value: uiState.hasRoi ? [uiState.roiX, uiState.roiY, uiState.roiWidth, uiState.roiHeight][index] + " px" : "—"; Layout.fillWidth: true }
                    }
                    SectionHeader { theme: root.theme; text: "모델"; Layout.fillWidth: true; Layout.topMargin: 12 }
                    InfoRow { theme: root.theme; label: "모델"; value: uiState.analysis.modelName || "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "버전"; value: uiState.analysis.modelVersion || "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "장치"; value: uiState.analysis.device || "—"; Layout.fillWidth: true }
                    StatusIndicator { theme: root.theme; text: uiState.modelAvailable ? "모델 연결됨" : "모델 미연결"; ink: uiState.modelAvailable ? theme.muted : theme.warning }
                    Text { text: uiState.analysisReason; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "입력 원본"; value: uiState.analysis.inputSource || "—"; Layout.fillWidth: true }
                    AppComboBox {
                        objectName: "analysisScopeCombo"; theme: root.theme; Layout.fillWidth: true
                        model: ["분석 범위 선택", "전체 이미지", "ROI"]
                        enabled: uiState.modelAvailable && !uiState.analysisRunning
                        currentIndex: uiState.analysisScope === "FULL_IMAGE" ? 1 : uiState.analysisScope === "ROI" ? 2 : 0
                        onActivated: uiState.analysisScope = ["", "FULL_IMAGE", "ROI"][currentIndex]
                    }
                    SectionHeader { theme: root.theme; text: "작업 상태"; Layout.fillWidth: true; Layout.topMargin: 12 }
                    InfoRow { theme: root.theme; label: "이미지"; value: uiState.hasLoadedImage ? "준비 완료" : uiState.demoMode ? "합성 데모" : "이미지 없음"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "ROI"; value: uiState.hasRoi ? "선택됨" : "미선택"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "분석"; value: uiState.analysis.statusLabel; valueColor: uiState.analysis.state === "FAILED" || !uiState.modelAvailable ? theme.warning : theme.text; Layout.fillWidth: true }
                }
                ColumnLayout {
                    visible: root.tabIndex === 2; Layout.fillWidth: true; spacing: 12
                    SectionHeader { theme: root.theme; text: "분석 결과"; Layout.fillWidth: true }
                    Text { text: uiState.hasResult ? "분석 완료" : "분석 결과 없음"; color: theme.text; font.pixelSize: 14 }
                    Text { text: uiState.hasResult ? "결과 표시 기능은 다음 단계에서 연결됩니다." : "분석 모델 연결 후 결함 검출 결과가 이곳에 표시됩니다."; color: theme.muted; wrapMode: Text.Wrap; font.pixelSize: 12; Layout.fillWidth: true }
                    Text { visible: uiState.hasResult && uiState.analysis.resultRoiMismatch; text: "현재 ROI와 다른 분석 결과"; color: theme.warning; wrapMode: Text.Wrap; font.pixelSize: 12; Layout.fillWidth: true }
                    AppButton { theme: root.theme; text: "검출 결함 보기"; enabled: false; iconName: "roi"; Layout.fillWidth: true }
                    AppButton { theme: root.theme; text: "결과 내보내기"; enabled: false; iconName: "export"; Layout.fillWidth: true }
                }
            }
        }
    }
}
