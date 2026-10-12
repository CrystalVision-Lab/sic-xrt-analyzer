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
    Text { visible: uiState.tiffMode; Layout.fillWidth: true; elide: Text.ElideMiddle; text: uiState.fileName; color: theme.text; font.pixelSize: theme.bodySize }
    Text { visible: uiState.tiffMode; Layout.fillWidth: true; text: uiState.imageWidth + " × " + uiState.imageHeight + " · " + uiState.dtype + " · " + uiState.zoomLabel; color: theme.muted; font.pixelSize: theme.smallSize }
    ColumnLayout {
        visible: uiState.tiffMode; Layout.fillWidth: true; spacing: theme.spacingXs
        SectionHeader { theme: root.theme; text: "ImageJ 선택"; Layout.fillWidth: true }
        Text { objectName: "tiffToolHint"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.text; font.pixelSize: theme.smallSize; text: root.actions.tools.forTool(uiState.activeTool) ? root.actions.tools.forTool(uiState.activeTool).text + " · " + root.actions.tools.hint(uiState.activeTool) : uiState.activeTool }
        Text { objectName: "tiffSelectionSummary"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.muted; font.pixelSize: theme.smallSize; text: uiState.roiFlow.selected && uiState.roiFlow.selected.active ? "X / Y / W / H: " + uiState.roiFlow.selected.bbox.join(" / ") : "현재 페이지에 선택이 없습니다." }
        RowLayout {
            AppButton { theme: root.theme; text: "선택 해제"; quiet: true; enabled: !!uiState.roiFlow.selected; onClicked: fileBridge.selectImportedRoi("") }
            AppButton { theme: root.theme; text: "ROI 관리…"; quiet: true; action: root.actions.advanced.roiManager }
        }
        Text { objectName: "tiffMeasurementSummary"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.text; font.pixelSize: theme.smallSize
            property var measurements: fileBridge.stackMeasurements.state
            text: measurements.error || (measurements.rows.length ? "측정 · " + measurements.rows[measurements.rows.length - 1].metric + " " + Number(measurements.rows[measurements.rows.length - 1].value).toFixed(3) + " " + measurements.rows[measurements.rows.length - 1].unit + " · 페이지 " + measurements.rows[measurements.rows.length - 1].page : "측정은 원본 XY 좌표 기준 · 눈금 미설정 시 pixel 단위")
        }
        AppButton { theme: root.theme; action: root.actions.advanced.measurement; text: "측정 결과 · 눈금 설정…"; quiet: true }
        AppButton { theme: root.theme; action: root.actions.advanced.catalog; text: "ImageJ 고급 도구…"; quiet: true }
    }
    StackControls { theme: root.theme; uiState: root.uiState; actions: root.actions; Layout.fillWidth: true }
    Text { visible: uiState.stack.pixelError.length > 0; text: "원본 픽셀 읽기 실패: " + uiState.stack.pixelError; color: theme.warning; font.pixelSize: theme.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
}
