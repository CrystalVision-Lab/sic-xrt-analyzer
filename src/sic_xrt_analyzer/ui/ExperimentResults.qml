import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    visible: uiState.hasLoadedImage && uiState.imageFormat !== "TIFF"
    property QtObject theme
    property QtObject uiState
    readonly property var experiment: uiState.experiment
    readonly property var selected: experiment.selected || ({})
    spacing: theme.spacingXs
    Layout.fillWidth: true
    RowLayout {
        Layout.fillWidth: true
        AppButton { objectName: "importExperiment"; theme: root.theme; quiet: true; implicitHeight: 24; text: "실험 영역 불러오기…"; enabled: uiState.hasLoadedImage && !uiState.loading && !experiment.loading; onClicked: folder.open() }
        Item { Layout.fillWidth: true }
        AppButton { objectName: "cancelExperiment"; theme: root.theme; text: "취소"; visible: experiment.loading; onClicked: fileBridge.experiments.cancel() }
        AppButton { objectName: "browseStructures"; theme: root.theme; quiet: true; implicitHeight: 24; text: "구조 제안 " + experiment.total + "개 ›"; visible: !!experiment.folder; onClicked: structures.open() }
    }
    Text { objectName: "experimentStatus"; visible: experiment.loading || !!experiment.error || !!experiment.folder; Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: theme.captionSize; color: experiment.error ? theme.warning : "#d3bef8"; text: experiment.loading ? "원본·페이지·자산 검증 중…" : experiment.error || experiment.status + " · 검수 필요 " + experiment.total + "개" }
    ColumnLayout {
        visible: !!selected.id; Layout.fillWidth: true; spacing: theme.spacingXs
        RowLayout {
            Layout.fillWidth: true
            Text { objectName: "selectedStructureHeader"; Layout.fillWidth: true; text: "구조 제안 #" + (selected.number || "") + " · 검수 필요"; color: theme.text; font.pixelSize: theme.titleSize }
            AppButton { objectName: "refocusStructure"; theme: root.theme; quiet: true; text: "위치로"; onClicked: fileBridge.experiments.select(selected.id) }
            AppButton { objectName: "structureDetails"; theme: root.theme; quiet: true; text: "상세…"; onClicked: detail.open() }
        }
        RowLayout {
            Layout.fillWidth: true
            Rectangle {
                Layout.preferredWidth: 76; Layout.preferredHeight: 76; color: theme.viewer
                Image { objectName: "structureThumbnail"; anchors.fill: parent; source: experiment.preview || ""; fillMode: Image.PreserveAspectFit; cache: false; smooth: false }
                BusyIndicator { anchors.centerIn: parent; width: 22; height: 22; running: !!selected.id && !experiment.preview && !experiment.previewError }
                Text { anchors.centerIn: parent; text: "읽기 실패"; visible: !!experiment.previewError; color: theme.warning }
            }
            ColumnLayout {
                Layout.fillWidth: true
        Text { Layout.fillWidth: true; wrapMode: Text.Wrap; text: (selected.kind === "BRANCHED_GRAPH" ? "분기형 그래프" : "선형 구조") + " · " + Number(selected.length || 0).toFixed(1) + " px · 분기점 " + (selected.junctions || 0); color: theme.text; font.pixelSize: theme.bodySize }
        Text { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "연결 후보 " + (selected.links || []).length + "개" + (selected.ambiguous ? " · ⚠ 모호한 연결 / 추가 검토 필요" : " · 제안된 관계"); color: selected.ambiguous ? theme.warning : theme.muted; font.pixelSize: theme.smallSize }
            }
        }
        Text { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "영역 검수는 후속 버전에서 지원합니다."; color: theme.muted; font.pixelSize: theme.captionSize }
    }
    onSelectedChanged: if (!selected.id) detail.close()
    SafeFolderDialog { id: folder; objectName: "experimentFolderDialog"; title: "TD-02 실험 번들 폴더 선택"; onAccepted: fileBridge.experiments.load(selectedFolder.toString()) }
    SurfaceDialog {
        id: structures; objectName: "structureListDialog"; parent: Overlay.overlay; title: "자동 구조 제안 · 미검증"
        modal: true; width: Math.min(540, parent.width - 40); height: Math.min(540, parent.height - 40); x: (parent.width-width)/2; y: (parent.height-height)/2; standardButtons: Dialog.Close
        ColumnLayout {
            anchors.fill: parent
            ListView {
                objectName: "structureList"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: experiment.rows
                ScrollBar.vertical: ScrollBar {}
                delegate: ItemDelegate {
                    required property var modelData
                    objectName: "structureRow" + modelData.number; width: ListView.view.width; height: 40
                    text: "#" + modelData.number + " · " + modelData.kind + " · " + modelData.length.toFixed(1) + " px"
                    Accessible.name: text + " · 자동 제안 · 검수 필요"; Accessible.selected: root.selected.id === modelData.id
                    onClicked: { fileBridge.experiments.select(modelData.id); structures.close() }
                }
            }
            AppButton { objectName: "unloadExperiment"; theme: root.theme; text: "실험 영역 닫기"; onClicked: { fileBridge.experiments.unload(); structures.close() } }
        }
    }
    SurfaceDialog {
        id: detail; objectName: "structureDetailDialog"; parent: Overlay.overlay; title: "자동 구조 제안 상세"
        modal: true; width: Math.min(580, parent.width-40); height: Math.min(560, parent.height-40); x: (parent.width-width)/2; y: (parent.height-height)/2; standardButtons: Dialog.Close
        ColumnLayout {
            anchors.fill: parent
            Text { Layout.fillWidth: true; text: experiment.status; color: theme.warning; font.pixelSize: theme.bodySize; wrapMode: Text.Wrap }
            ScrollView {
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
                TextArea { width: parent.width; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; text: "ID: " + (selected.id || "") + "\nGeometry: " + (selected.kind || "") + "\n원본 범위: " + JSON.stringify(selected.bounds || []) + " px\n알고리즘: " + (selected.algorithm || "") + "\n플래그: " + JSON.stringify(selected.flags || []) + "\n\nPRELIMINARY_NO_GROUND_TRUTH\n구조는 분류 결과나 사람 검수 결과가 아닙니다. 픽셀 길이는 물리 길이가 아닙니다.\n\n관련 후보 (제안된 관계):\n" + JSON.stringify(selected.links || [], null, 2) }
            }
            Repeater {
                model: (selected.links || []).slice(0, 4)
                AppButton {
                    required property var modelData
                    theme: root.theme; text: "연결 후보 보기 · " + modelData.source_candidate_id
                    enabled: uiState.research.points.some(function(p) { return p.id === modelData.source_candidate_id && p.x === modelData.x && p.y === modelData.y && p.type === modelData.class && JSON.stringify(p.scores) === JSON.stringify(modelData.raw_scores) && uiState.research.runInfo.modelHash === modelData.model_version })
                    onClicked: { fileBridge.research.selectCandidate(modelData.source_candidate_id); detail.close() }
                }
            }
        }
    }
}
