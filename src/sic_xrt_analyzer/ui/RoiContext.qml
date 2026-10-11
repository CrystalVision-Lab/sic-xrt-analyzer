import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "roiContext"
    property QtObject theme
    property QtObject uiState
    readonly property string informationPriority: "primary"
    signal importRequested()
    signal boundsRequested()
    signal saveRequested()
    spacing: 10
    SectionHeader { theme: root.theme; text: "ImageJ ROI"; Layout.fillWidth: true }
    Text { text: "대응하는 이미지를 먼저 열고 .roi 또는 RoiSet.zip을 가져오세요. 원본 좌표를 그대로 표시합니다."; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
    AppButton { objectName: "importRoisButton"; theme: root.theme; text: "ROI / ZIP 가져오기…"; iconName: "roi"; Layout.fillWidth: true; enabled: uiState.hasLoadedImage && !uiState.loading && !uiState.importedRois.busy; onClicked: root.importRequested() }
    Text { visible: uiState.importedRois.busy; text: "ROI 불러오는 중…"; color: theme.accent; font.pixelSize: 11 }
    AppButton { objectName: "selectImportedBoundsButton"; theme: root.theme; text: "외접 사각형으로 선택"; Layout.fillWidth: true; enabled: !uiState.loading && uiState.importedRois.items.some(function(r) { return r.selected && r.active }); onClicked: root.boundsRequested() }
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
    Text { visible: uiState.importedRois.items.length > 0; text: "위 선택은 점/다각형의 외접 사각형입니다. ROI 도형 마스크 분석은 아직 연결되지 않았습니다."; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
    Text { visible: uiState.importedRois.errors.length > 0; text: "불러오기 오류 " + uiState.importedRois.errors.length + "개"; color: theme.warning; font.pixelSize: 12 }
    Repeater {
        model: uiState.importedRois.errors.slice(0, 100)
        Text { required property string modelData; text: modelData; color: theme.warning; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
    }
}
