import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "resultExplorer"
    property QtObject theme
    property QtObject uiState
    readonly property var results: uiState.research
    readonly property var selected: results.selected || ({})
    readonly property QtObject presentation: uiState.resultPresentation
    readonly property string filterLabel: results.filterKind === "ALL" ? "전체 후보" : results.filterKind + " 후보"
    signal exportRequested()
    signal overviewRequested()
    spacing: 6
    function filter(kind, low, query) {
        fileBridge.research.setFilter(kind, low, query)
        // Retained selections on later list pages must remain reachable.
        var index = fileBridge.research.state.selectedIndex
        if (index >= 0) fileBridge.research.setResultPage(Math.floor(index / 100))
    }
    onResultsChanged: Qt.callLater(function() {
        if (!selected.id) detail.close()
        if (results.selectedIndex >= 0 && Math.floor(results.selectedIndex / 100) === results.page)
            candidates.positionViewAtIndex(results.selectedIndex % 100, ListView.Contain)
    })
    RowLayout {
        Layout.fillWidth: true
        Text { objectName: "resultTotal"; text: "총 후보 " + presentation.count(results.total) + "개"; color: theme.text; font.pixelSize: 21; font.bold: true; Layout.fillWidth: true }
        AppButton { objectName: "resultOverview"; theme: root.theme; quiet: true; text: "전체 보기"; onClicked: root.overviewRequested() }
    }
    RowLayout {
        spacing: 4; Layout.fillWidth: true
        AppButton {
            objectName: "resultFilterALL"; theme: root.theme; quiet: true
            text: "전체"; checked: results.filterKind === "ALL"
            Accessible.name: "전체 후보 " + presentation.count(results.total) + "개"
            onClicked: root.filter("ALL", results.filterLow, results.query)
        }
        Repeater {
            model: ["BPD", "TED", "TSD"]
            AppButton {
                required property string modelData
                objectName: "resultFilter" + modelData
                theme: root.theme; quiet: true; Layout.fillWidth: true
                text: modelData + " " + presentation.count(results.counts[modelData])
                checked: results.filterKind === modelData
                Accessible.name: modelData + " 후보 " + presentation.count(results.counts[modelData]) + "개"
                contentItem: RowLayout {
                    spacing: 4
                    Rectangle { Layout.preferredWidth: 6; Layout.preferredHeight: 6; radius: 3; color: presentation.colorFor(modelData) }
                    Text { text: parent.parent.text; color: theme.text; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
                }
                onClicked: root.filter(modelData, results.filterLow, results.query)
            }
        }
    }
    Text {
        objectName: "resultFilterSummary"; Layout.fillWidth: true; color: theme.muted; font.pixelSize: 11
        text: root.filterLabel + " · " + presentation.count(results.filteredTotal) + "개" + (results.query ? " · 검색 적용" : "") + (results.filterLow ? " · 낮은 점수만" : "")
    }
    RowLayout {
        visible: results.total > 0; Layout.fillWidth: true
        AppButton { objectName: "previousCandidate"; theme: root.theme; text: "← 이전"; enabled: results.selectedIndex > 0; onClicked: fileBridge.research.stepCandidate(-1) }
        Text {
            objectName: "candidateIndex"; horizontalAlignment: Text.AlignHCenter; color: theme.text; font.pixelSize: 12; Layout.fillWidth: true
            text: selected.id ? "후보 " + presentation.count(results.selectedIndex + 1) + " / " + presentation.count(results.filteredTotal) : "후보 선택 전"
        }
        AppButton { objectName: "nextCandidate"; theme: root.theme; text: "다음 →"; enabled: results.filteredTotal > 0 && results.selectedIndex < results.filteredTotal - 1; onClicked: fileBridge.research.stepCandidate(1) }
    }
    Rectangle { visible: results.total > 0; Layout.fillWidth: true; implicitHeight: 1; color: theme.border }
    Text {
        objectName: "emptyCandidateDetail"; visible: results.total > 0 && !selected.id
        Layout.fillWidth: true; Layout.preferredHeight: 58; verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap; color: theme.muted; font.pixelSize: 12
        text: results.filteredTotal ? presentation.count(results.filteredTotal) + "개의 " + root.filterLabel + "가 있습니다.\n검토할 후보를 선택하세요." : "조건에 맞는 후보가 없습니다. 필터를 변경하세요."
    }
    ColumnLayout {
        visible: !!selected.id; Layout.fillWidth: true; spacing: 4
        RowLayout {
            Layout.fillWidth: true
            Text { objectName: "selectedCandidateHeader"; text: selected.id ? "후보 #" + selected.number + " · " + selected.type : ""; color: selected.id ? presentation.colorFor(selected.type) : theme.text; font.bold: true; font.pixelSize: 15; Layout.fillWidth: true }
            AppButton { objectName: "refocusCandidate"; theme: root.theme; quiet: true; text: "위치로"; onClicked: fileBridge.research.selectCandidate(selected.id) }
            AppButton { objectName: "candidateDetails"; theme: root.theme; quiet: true; text: "상세…"; onClicked: detail.open() }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 10
            Rectangle {
                Layout.preferredWidth: 88; Layout.preferredHeight: 88; color: theme.viewer; clip: true
                Image { objectName: "candidateThumbnail"; anchors.fill: parent; source: results.thumbnailSource; cache: false; smooth: false }
                Rectangle { visible: !!results.thumbnailSource; width: 19; height: 1; color: "#ffff40"; x: parent.width * results.thumbnailCenter[0] - width/2; y: parent.height * results.thumbnailCenter[1] }
                Rectangle { visible: !!results.thumbnailSource; width: 1; height: 19; color: "#ffff40"; x: parent.width * results.thumbnailCenter[0]; y: parent.height * results.thumbnailCenter[1] - height/2 }
                BusyIndicator { anchors.centerIn: parent; width: 24; height: 24; running: !!selected.id && !results.thumbnailSource && !results.thumbnailError }
                Text { anchors.fill: parent; anchors.margins: 4; visible: !!results.thumbnailError; text: "패치 읽기 실패"; color: theme.warning; wrapMode: Text.Wrap; font.pixelSize: 11 }
            }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 3
                Text { objectName: "candidateConfidence"; text: presentation.confidence(selected.score); color: theme.text; font.pixelSize: 25; font.bold: true }
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    Repeater {
                        model: ["BPD", "TED", "TSD"]
                        Text {
                            required property string modelData
                            required property int index
                            visible: modelData !== selected.type
                            text: modelData + " " + presentation.confidence(selected.scores && selected.scores.length === 3 ? selected.scores[index] : undefined)
                            color: theme.muted; font.pixelSize: 11
                        }
                    }
                }
                Text { objectName: "candidatePosition"; text: selected.id ? "위치 (" + selected.x.toFixed(2) + ", " + selected.y.toFixed(2) + ") px" : ""; color: theme.muted; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                Text { text: selected.low_score ? "낮은 점수 · 사람 검수 미확정" : "사람 검수 미확정"; color: selected.low_score ? theme.warning : theme.muted; font.pixelSize: 10 }
            }
        }
    }
    RowLayout {
        visible: results.total > 0; Layout.fillWidth: true
        Text { text: "후보 목록"; color: theme.muted; font.pixelSize: 11; Layout.fillWidth: true }
        Text { text: "살펴봄 " + presentation.count(results.viewedCount) + "개"; color: theme.muted; font.pixelSize: 10 }
    }
    ListView {
        id: candidates; objectName: "candidateList"
        visible: results.total > 0
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 80; clip: true; spacing: 2
        model: results.displayRows
        ScrollBar.vertical: ScrollBar {}
        delegate: ItemDelegate {
            required property var modelData
            width: candidates.width; height: 40
            objectName: "candidateRow" + modelData.number
            Accessible.name: "후보 " + modelData.number + ", " + modelData.type + ", 신뢰도 " + presentation.confidence(modelData.score)
            Accessible.selected: selected.id === modelData.id
            Accessible.description: "모델 점수이며 정답 확률이나 사람 검수 결과가 아닙니다."
            onClicked: fileBridge.research.selectCandidate(modelData.id)
            background: Rectangle { color: selected.id === modelData.id ? theme.accentPale : parent.hovered ? theme.hover : "transparent"; radius: 3 }
            contentItem: RowLayout {
                spacing: 8
                Rectangle { width: 3; Layout.fillHeight: true; color: selected.id === modelData.id ? theme.accent : "transparent" }
                Text { text: "#" + modelData.number; color: theme.text; font.pixelSize: 12; font.bold: selected.id === modelData.id; Layout.fillWidth: true }
                Text { text: modelData.type + " · " + presentation.confidence(modelData.score); color: theme.text; font.pixelSize: 12 }
                Text { text: modelData.viewed ? "●" : "○"; color: modelData.viewed ? theme.accent : theme.muted; font.pixelSize: 10 }
            }
        }
    }
    Item { visible: !results.total; Layout.fillHeight: true }
    RowLayout {
        visible: results.filteredTotal > 0; Layout.fillWidth: true
        AppButton { objectName: "previousResultPage"; theme: root.theme; quiet: true; text: "‹"; enabled: results.page > 0; onClicked: fileBridge.research.setResultPage(results.page - 1) }
        Text { objectName: "candidateListPage"; text: "목록 " + presentation.count(results.page + 1) + " / " + presentation.count(results.pages) + " 페이지 · 100개씩"; color: theme.muted; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
        AppButton { objectName: "nextResultPage"; theme: root.theme; quiet: true; text: "›"; enabled: results.page + 1 < results.pages; onClicked: fileBridge.research.setResultPage(results.page + 1) }
    }
    Text { visible: results.limited || results.excluded > 0; text: (results.limited ? "자동 후보 상한 도달 · " : "") + "경계·범위 등 제외 " + presentation.count(results.excluded); color: theme.warning; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true }
    Text { text: "모델 점수 · 정답 확률 아님 / 사람 검수 미확정"; color: theme.warning; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true }
    RowLayout {
        Layout.fillWidth: true
        AppButton { objectName: "analysisExportButton"; theme: root.theme; quiet: true; text: "전체 결과 저장…"; enabled: uiState.hasResult; onClicked: root.exportRequested() }
        Item { Layout.fillWidth: true }
        AppButton { objectName: "resultOptions"; theme: root.theme; quiet: true; text: "탐색 설정…"; onClicked: options.open() }
        AppButton { objectName: "resultRunInfo"; theme: root.theme; quiet: true; text: "실행 정보"; onClicked: info.open() }
    }
    Text { visible: !!results.error || !!results.exportPath; text: results.error || "저장 완료: " + results.exportPath; color: results.error ? theme.warning : theme.muted; font.pixelSize: 10; elide: Text.ElideMiddle; Layout.fillWidth: true }
    Dialog {
        id: detail; objectName: "candidateDetailDialog"; parent: Overlay.overlay
        title: selected.id ? "후보 #" + selected.number + " · " + selected.type + " 상세" : "후보 상세"
        modal: true; width: Math.min(520, parent.width - 40); x: (parent.width - width)/2; y: (parent.height - height)/2; standardButtons: Dialog.Close
        ColumnLayout {
            width: parent.width; spacing: 10
            Text { text: "모델 점수 (Confidence) / Raw score"; color: theme.text; font.pixelSize: 14 }
            Repeater {
                model: ["BPD", "TED", "TSD"]
                Text {
                    required property string modelData
                    required property int index
                    objectName: "rawScore" + modelData
                    property var score: selected.scores && selected.scores.length === 3 ? selected.scores[index] : undefined
                    text: modelData + "  " + presentation.confidence(score) + "   /   " + presentation.raw(score)
                    color: modelData === selected.type ? theme.text : theme.muted; font.bold: modelData === selected.type; font.pixelSize: 13
                }
            }
            Text { objectName: "rawAssignedScore"; text: "Assigned " + (selected.type || "") + " · Raw score " + presentation.raw(selected.score); color: theme.muted; font.pixelSize: 12 }
            TextArea { Layout.fillWidth: true; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; text: selected.id ? "ID: " + selected.id + "\nPoint ID: " + selected.point_id + "\nX=" + selected.x + ", Y=" + selected.y + " (원시 픽셀)\n원본 128px 패치 · 사람 검수 미확정" : "" }
            AppButton { objectName: "copyCandidate"; theme: root.theme; text: "좌표와 ID 복사"; onClicked: fileBridge.copyText(selected.id + "\n" + selected.point_id + "\nX=" + selected.x + ", Y=" + selected.y + "\n예측=" + selected.type) }
        }
    }
    Dialog {
        id: options; objectName: "resultOptionsDialog"; parent: Overlay.overlay; title: "후보 탐색 설정"
        modal: true; width: Math.min(520, parent.width - 40); x: (parent.width - width)/2; y: (parent.height - height)/2; standardButtons: Dialog.Close
        ColumnLayout {
            width: parent.width; spacing: 10
            TextField { objectName: "candidateSearch"; Layout.fillWidth: true; placeholderText: "번호 또는 후보 ID 검색"; placeholderTextColor: theme.muted; color: theme.text; selectByMouse: true; text: results.query; onTextEdited: root.filter(results.filterKind, results.filterLow, text) }
            CheckBox { objectName: "lowScoreFilter"; text: "낮은 점수 후보만"; checked: results.filterLow; onToggled: root.filter(results.filterKind, checked, results.query) }
            CheckBox { objectName: "autoCandidateRoi"; text: "자동 ROI"; checked: uiState.autoCandidateRoi; onToggled: uiState.autoCandidateRoi = checked }
            ComboBox {
                objectName: "candidateRoiSize"; Layout.fillWidth: true
                model: ["128 × 128 px", "256 × 256 px", "512 × 512 px"]
                currentIndex: [128, 256, 512].indexOf(uiState.candidateRoiSize)
                onActivated: { uiState.candidateRoiSize = [128, 256, 512][currentIndex]; if (uiState.autoCandidateRoi && selected.id) fileBridge.research.selectCandidate(selected.id) }
            }
            Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.muted; font.pixelSize: 11; text: uiState.candidateRoiId ? "탐색 ROI: (" + uiState.roiX + ", " + uiState.roiY + ") · " + uiState.roiWidth + " × " + uiState.roiHeight + " px · 결함 윤곽 아님" : "후보 선택 시 사각 ROI 생성 · 수동 선택 시 자동 추적 해제" }
            CheckBox { objectName: "resultLayerVisibility"; text: "영상에 후보 위치 표시"; checked: uiState.analysisLayerVisible; onToggled: uiState.analysisLayerVisible = checked }
            Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.muted; font.pixelSize: 11; text: "현재 필터 후보만 표시 · 낮은 점수 후보는 기존 흰색 원 · 선택 후보는 노란 강조선\n색상과 Class 이름은 결과 필터에서 함께 확인합니다." }
        }
    }
    Dialog {
        id: info; objectName: "resultInfoDialog"; parent: Overlay.overlay; title: "분석 실행 정보"; modal: true; width: Math.min(560, parent.width - 40); x: (parent.width - width)/2; y: (parent.height - height)/2; standardButtons: Dialog.Close
        contentItem: TextArea { readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; text: "원본: " + results.runInfo.source + "\n페이지: " + results.runInfo.page + "\n좌표: 원시 픽셀 (EXIF 자동 회전 미적용)\n방식: " + (results.runInfo.mode === "provided_coordinates" ? "제공 좌표 분류" : "밝기 대비 자동 후보") + "\n소요 시간: " + results.runInfo.seconds + "초\n완료: " + results.runInfo.completed + "\n실행 ID: " + results.runInfo.analysisId + "\n모델: " + results.runInfo.model + "\n모델 해시: " + results.runInfo.modelHash + "\n\n살펴봄 표시는 이번 실행의 탐색 기록이며 정답 검수 기록이 아닙니다." }
    }
}
