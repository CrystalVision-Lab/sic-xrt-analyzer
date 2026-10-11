import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

SurfaceDialog {
    id: root
    objectName: "stackMeasurementDialog"
    property QtObject theme
    property var backend
    property QtObject uiState
    property var measurements: backend.state
    title: "스택 측정 · 기준 눈금 / 길이 / 면적 / 개수"
    width: 850; height: 600; modal: false
    onOpened: { unit.text = measurements.unit; distance.text = String(measurements.distance); known.text = String(measurements.known); aspect.text = String(measurements.pixelHeight / measurements.pixelWidth) }
    contentItem: ColumnLayout {
        spacing: theme.spacingSm
        Text { Layout.fillWidth: true; color: theme.muted; wrapMode: Text.Wrap; text: "1. 실제 길이를 아는 눈금에 직선을 그리세요.  2. 기준 거리와 단위를 설정하세요.  3. 분할선·영역·점 ROI를 선택해 측정하세요.\n설정은 이 파일의 XY 평면에 적용됩니다. 페이지 간격이나 공간 Z축은 설정하지 않습니다." }
        RowLayout {
            AppButton { theme: root.theme; text: "기준선 그리기"; onClicked: { uiState.roiEditMode=false; uiState.activeTool="Line"; root.close() } }
            AppButton { theme: root.theme; text: "선택한 선의 픽셀 길이 가져오기"; onClicked: { backend.useReferenceLine(); if (measurements.reference > 0) distance.text=String(measurements.reference) } }
            Text { color: theme.text; text: "현재 " + Number(measurements.pixelsPerUnit).toPrecision(7) + " pixels/" + measurements.unit }
        }
        GridLayout {
            columns: 4; Layout.fillWidth: true
            Text { text: "픽셀 거리"; color: theme.text }
            AppTextField { id: distance; objectName: "calibrationPixels"; text: "100"; Layout.fillWidth: true }
            Text { text: "실제 거리"; color: theme.text }
            AppTextField { id: known; objectName: "calibrationKnown"; text: "1"; Layout.fillWidth: true }
            Text { text: "길이 단위"; color: theme.text }
            AppTextField { id: unit; objectName: "calibrationUnit"; text: measurements.unit; placeholderText: "mm / µm"; Layout.fillWidth: true }
            Text { text: "Y/X 픽셀 간격 비율"; color: theme.text }
            AppTextField { id: aspect; text: "1"; Layout.fillWidth: true }
        }
        RowLayout {
            AppButton { theme: root.theme; text: "눈금 적용"; onClicked: backend.setScale(Number(distance.text),Number(known.text),unit.text,Number(aspect.text)) }
            AppButton { theme: root.theme; text: "픽셀 단위로 초기화"; onClicked: backend.reset() }
            Item { Layout.fillWidth: true }
            AppButton { theme: root.theme; text: "분할선 그리기"; onClicked: { uiState.roiEditMode=false; uiState.activeTool="Polyline"; root.close() } }
            AppButton { theme: root.theme; text: "선택 ROI 측정"; primary: true; onClicked: backend.measure() }
        }
        Text { Layout.fillWidth: true; color: theme.muted; text: "직선·분할선·자유선: 길이 / 사각형·타원·다각형: 면적 / 점 ROI: 개수 / 각도 ROI: 각도" }
        ScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true
            TextArea { readOnly: true; selectByMouse: true; font.family: "Consolas"; text: backend.resultsText(); property var revision: root.measurements; onRevisionChanged: text = backend.resultsText() }
        }
        RowLayout {
            AppButton { theme: root.theme; text: "결과 복사 (Excel/TSV)"; onClicked: fileBridge.copyText(backend.resultsText()) }
            AppButton { theme: root.theme; text: "새 TSV 저장…"; enabled: measurements.rows.length > 0; onClicked: saveFile.open() }
            AppButton { theme: root.theme; text: "결과 지우기"; onClicked: backend.clearResults() }
            Item { Layout.fillWidth: true }
            AppButton { theme: root.theme; text: "닫기"; onClicked: root.close() }
        }
        Text { visible: measurements.error.length > 0; Layout.fillWidth: true; wrapMode: Text.Wrap; text: measurements.error; color: theme.error }
    }
    SafeFileDialog { id: saveFile; fileMode: FileDialog.SaveFile; nameFilters: ["측정 결과 (*.tsv)"]; onAccepted: backend.saveResults(selectedFile.toString()) }
}
