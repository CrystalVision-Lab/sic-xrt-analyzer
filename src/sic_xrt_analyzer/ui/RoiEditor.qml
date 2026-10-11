import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property QtObject theme
    property QtObject uiState
    property var actions
    property var selected: uiState.importedRois.items.filter(function(r) { return r.selected })[0] || null
    readonly property bool editable: !!selected && selected.active && selected.visible && !uiState.loading && !uiState.importedRois.busy
    signal saveRequested()
    spacing: 8
    SectionHeader { theme: root.theme; text: "좌표 · 기록 설정"; Layout.fillWidth: true }
    RowLayout {
        Layout.fillWidth: true
        AppButton { objectName: "newPointRoiButton"; theme: root.theme; text: "새 점 ROI"; enabled: uiState.hasLoadedImage && !uiState.loading && !uiState.importedRois.busy; onClicked: { fileBridge.newPointRoi(); uiState.roiEditMode = true } }
        AppButton { objectName: "roiUndoButton"; theme: root.theme; text: "실행 취소"; tip: "ROI 실행 취소"; enabled: uiState.importedRois.canUndo && !uiState.loading && !uiState.importedRois.busy; onClicked: fileBridge.roiHistory(false) }
        AppButton { objectName: "roiRedoButton"; theme: root.theme; text: "다시"; enabled: uiState.importedRois.canRedo && !uiState.loading && !uiState.importedRois.busy; onClicked: fileBridge.roiHistory(true) }
    }
    AppCheckBox { objectName: "roiEditModeCheck"; theme: root.theme; text: "점 / 꼭짓점 편집 모드"; action: root.actions.advanced.editRoi }
    Text { text: "점을 드래그하여 이동 · 빈 곳 드래그는 Pan\n더블클릭으로 점 추가 · Delete로 선택 점 삭제\nCtrl+Z / Ctrl+Shift+Z로 취소 / 다시 실행"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.muted; font.pixelSize: 11 }
    ColumnLayout {
        visible: root.editable; Layout.fillWidth: true; spacing: 6
        TextField {
            objectName: "roiNameField"; Layout.fillWidth: true; implicitHeight: 28
            text: root.selected ? root.selected.name : ""; color: theme.text; selectByMouse: true
            background: Rectangle { color: theme.surface; border.color: theme.border }
            onEditingFinished: if (root.selected && text !== root.selected.name) fileBridge.renameRoi(text)
        }
        RowLayout {
            Text { text: "점 번호"; color: theme.muted; font.pixelSize: 11; Layout.fillWidth: true }
            SpinBox { objectName: "roiVertexSpin"; from: 1; to: root.selected ? root.selected.pointCount : 1; value: Math.max(1, uiState.importedRois.vertex + 1); editable: true; onValueModified: fileBridge.selectRoiVertex(value - 1) }
        }
        RowLayout {
            Layout.fillWidth: true
            Text { text: "X"; color: theme.muted }
            TextField { id: xField; objectName: "roiPointXField"; Layout.fillWidth: true; implicitHeight: 28; text: Number(uiState.importedRois.pointX).toFixed(2); selectByMouse: true; color: theme.text; background: Rectangle { color: theme.surface; border.color: theme.border } }
            Text { text: "Y"; color: theme.muted }
            TextField { id: yField; objectName: "roiPointYField"; Layout.fillWidth: true; implicitHeight: 28; text: Number(uiState.importedRois.pointY).toFixed(2); selectByMouse: true; color: theme.text; background: Rectangle { color: theme.surface; border.color: theme.border } }
        }
        RowLayout {
            AppButton { objectName: "applyRoiPointButton"; theme: root.theme; text: "좌표 적용"; onClicked: fileBridge.moveRoiVertex(Number(xField.text), Number(yField.text)) }
            AppButton { theme: root.theme; text: "점 추가"; onClicked: fileBridge.addRoiVertex(Number(xField.text), Number(yField.text)) }
            AppButton { theme: root.theme; text: "점 삭제"; onClicked: fileBridge.deleteRoiVertex() }
        }
        Text { text: "전체 이동 (원본 픽셀 ΔX / ΔY)"; color: theme.muted; font.pixelSize: 11 }
        RowLayout {
            TextField { id: dx; Layout.fillWidth: true; implicitHeight: 28; text: "0"; color: theme.text; selectByMouse: true; background: Rectangle { color: theme.surface; border.color: theme.border } }
            TextField { id: dy; Layout.fillWidth: true; implicitHeight: 28; text: "0"; color: theme.text; selectByMouse: true; background: Rectangle { color: theme.surface; border.color: theme.border } }
            AppButton { theme: root.theme; text: "이동"; onClicked: fileBridge.translateRoi(Number(dx.text), Number(dy.text)) }
        }
    }
    AppButton { objectName: "saveRoiCopyButton"; theme: root.theme; text: "ROI ZIP 복사본 저장…"; Layout.fillWidth: true; enabled: uiState.importedRois.items.length > 0 && !uiState.loading && !uiState.importedRois.busy; onClicked: root.saveRequested() }
    Text { text: uiState.importedRois.dirty ? "저장하지 않은 ROI 변경이 있습니다." : "원본 ROI는 덮어쓰지 않습니다. 새 ZIP으로 저장하세요."; color: uiState.importedRois.dirty ? theme.warning : theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
    Text { visible: uiState.importedRois.editError.length > 0; text: uiState.importedRois.editError; color: theme.warning; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
}
