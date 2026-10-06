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
    signal exportRequested()
    signal overviewRequested()
    signal reviewRequested()
    spacing: 8
    function colorFor(kind) { return kind === "BPD" ? "#ffad42" : kind === "TED" ? "#50e0ee" : "#ff78c4" }
    function filter(kind, low, query) { fileBridge.research.setFilter(kind, low, query) }
    onResultsChanged: Qt.callLater(function() {
        if (results.selectedIndex >= 0 && Math.floor(results.selectedIndex / 100) === results.page)
            candidates.positionViewAtIndex(results.selectedIndex % 100, ListView.Contain)
    })
    RowLayout {
        Layout.fillWidth: true
        Text { text: "후보 탐색"; color: theme.text; font.pixelSize: 16; font.bold: true; Layout.fillWidth: true }
        Text { text: results.filteredTotal + " / " + results.total; color: theme.accent; font.pixelSize: 12 }
    }
    Text { text: "예측 후보 · 정답 검수 아님 / 점수는 정답 확률이 아닙니다"; color: theme.warning; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true }
    RowLayout {
        spacing: 3; Layout.fillWidth: true
        Repeater {
            model: ["ALL", "BPD", "TED", "TSD"]
            AppButton {
                required property string modelData
                objectName: "resultFilter" + modelData
                theme: root.theme; Layout.fillWidth: true
                text: (modelData === "ALL" ? "전체" : modelData) + " " + (modelData === "ALL" ? results.total : results.counts[modelData] || 0)
                checked: results.filterKind === modelData
                onClicked: root.filter(modelData, results.filterLow, results.query)
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        TextField { objectName: "candidateSearch"; Layout.fillWidth: true; placeholderText: "번호 또는 후보 ID 검색"; placeholderTextColor: theme.muted; color: theme.text; font.pixelSize: 11; selectByMouse: true; text: results.query; onTextEdited: root.filter(results.filterKind, results.filterLow, text) }
        CheckBox { objectName: "lowScoreFilter"; text: "낮은 점수"; checked: results.filterLow; onToggled: root.filter(results.filterKind, checked, results.query) }
    }
    RowLayout {
        Layout.fillWidth: true
        CheckBox { objectName: "autoCandidateRoi"; text: "자동 ROI"; checked: uiState.autoCandidateRoi; onToggled: uiState.autoCandidateRoi = checked }
        ComboBox {
            objectName: "candidateRoiSize"; Layout.fillWidth: true
            model: ["128 × 128 px", "256 × 256 px", "512 × 512 px"]
            currentIndex: [128, 256, 512].indexOf(uiState.candidateRoiSize)
            onActivated: {
                uiState.candidateRoiSize = [128, 256, 512][currentIndex]
                if (uiState.autoCandidateRoi && selected.id) fileBridge.research.selectCandidate(selected.id)
            }
        }
    }
    Text {
        Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.muted; font.pixelSize: 10
        text: uiState.candidateRoiId ? "탐색 ROI: (" + uiState.roiX + ", " + uiState.roiY + ") · " + uiState.roiWidth + " × " + uiState.roiHeight + " px · 결함 윤곽 아님" : "후보 선택 시 사각 ROI 생성 · 수동 선택 시 자동 추적 해제"
    }
    Rectangle {
        Layout.fillWidth: true; Layout.preferredHeight: selected.id ? 266 : 58
        color: theme.viewer; border.color: selected.id ? root.colorFor(selected.type) : theme.border; radius: 5
        Text { anchors.centerIn: parent; visible: !selected.id; text: uiState.hasResult ? "목록이나 영상의 원을 눌러 후보를 살펴보세요" : "분석을 실행하면 후보가 여기에 표시됩니다"; color: theme.muted; font.pixelSize: 11 }
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 10; spacing: 6; visible: !!selected.id
            RowLayout {
                Text { text: selected.id ? "#" + selected.number + "  " + selected.type + " 후보" : ""; color: selected.id ? root.colorFor(selected.type) : theme.text; font.bold: true; font.pixelSize: 14; Layout.fillWidth: true }
                AppButton { objectName: "refocusCandidate"; theme: root.theme; text: "위치로"; onClicked: fileBridge.research.selectCandidate(selected.id) }
            }
            RowLayout {
                Layout.fillWidth: true; spacing: 12
                Rectangle {
                    Layout.preferredWidth: 136; Layout.preferredHeight: 136; color: theme.surface; clip: true
                    Image { objectName: "candidateThumbnail"; anchors.fill: parent; source: results.thumbnailSource; cache: false; smooth: false }
                    Rectangle { visible: !!results.thumbnailSource; width: 19; height: 1; color: "#ffff40"; x: parent.width * results.thumbnailCenter[0] - width/2; y: parent.height * results.thumbnailCenter[1] }
                    Rectangle { visible: !!results.thumbnailSource; width: 1; height: 19; color: "#ffff40"; x: parent.width * results.thumbnailCenter[0]; y: parent.height * results.thumbnailCenter[1] - height/2 }
                    BusyIndicator { anchors.centerIn: parent; width: 32; height: 32; running: !!selected.id && !results.thumbnailSource && !results.thumbnailError }
                    Text { anchors.fill: parent; anchors.margins: 6; visible: !!results.thumbnailError; text: "패치를 읽지 못했습니다"; color: theme.warning; wrapMode: Text.Wrap }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 6
                    Text { text: "모델 점수"; color: theme.muted; font.pixelSize: 11 }
                    Repeater {
                        model: ["BPD", "TED", "TSD"]
                        ColumnLayout {
                            required property string modelData
                            required property int index
                            property real score: selected.scores && selected.scores.length === 3 ? selected.scores[index] : -1
                            spacing: 3; Layout.fillWidth: true
                            RowLayout {
                                Text { text: modelData; color: root.colorFor(modelData); font.pixelSize: 11; Layout.fillWidth: true }
                                Text { text: score >= 0 ? score.toFixed(4) : "—"; color: theme.text; font.pixelSize: 11; font.family: theme.monoFontFamily }
                            }
                            Rectangle { Layout.fillWidth: true; height: 4; color: theme.border; radius: 2
                                Rectangle { width: parent.width * Math.max(0, Math.min(1, score)); height: 4; radius: 2; color: root.colorFor(modelData) }
                            }
                        }
                    }
                }
            }
            RowLayout {
                Text { text: selected.id ? "X " + selected.x.toFixed(2) + "   Y " + selected.y.toFixed(2) + " px" : ""; font.family: theme.monoFontFamily; color: theme.text; font.pixelSize: 11; Layout.fillWidth: true }
                AppButton { theme: root.theme; text: "복사"; onClicked: fileBridge.copyText(selected.id + "\n" + selected.point_id + "\nX=" + selected.x + ", Y=" + selected.y + "\n예측=" + selected.type) }
            }
            Text { text: selected.point_id || ""; color: theme.muted; elide: Text.ElideMiddle; font.pixelSize: 10; Layout.fillWidth: true }
            Text { text: "원본 128px 패치 · " + (selected.low_score ? "낮은 점수 / " : "") + "사람 검수 미확정"; color: selected.low_score ? theme.warning : theme.muted; font.pixelSize: 10 }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        AppButton { objectName: "previousCandidate"; theme: root.theme; text: "← 이전"; enabled: results.selectedIndex > 0; onClicked: fileBridge.research.stepCandidate(-1) }
        Text { text: results.filteredTotal ? (results.selectedIndex + 1) + " / " + results.filteredTotal : "0 / 0"; horizontalAlignment: Text.AlignHCenter; color: theme.text; Layout.fillWidth: true }
        AppButton { objectName: "nextCandidate"; theme: root.theme; text: "다음 →"; enabled: results.filteredTotal > 0 && results.selectedIndex < results.filteredTotal - 1; onClicked: fileBridge.research.stepCandidate(1) }
        AppButton { objectName: "resultOverview"; theme: root.theme; text: "전체 보기"; onClicked: root.overviewRequested() }
    }
    AppButton { objectName: "reviewSelectedCandidate"; theme: root.theme; text: "선택 후보 검수하기"; Layout.fillWidth: true; enabled: !!selected.id && uiState.feedback.ready; onClicked: root.reviewRequested() }
    RowLayout {
        Text { text: "후보 목록"; color: theme.muted; font.pixelSize: 11; Layout.fillWidth: true }
        Text { text: "이번 결과에서 살펴봄 " + results.viewedCount; color: theme.muted; font.pixelSize: 10 }
    }
    ListView {
        id: candidates; objectName: "candidateList"
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 80; clip: true; spacing: 3
        model: results.displayRows
        ScrollBar.vertical: ScrollBar {}
        delegate: ItemDelegate {
            required property var modelData
            width: candidates.width; height: 45
            objectName: "candidateRow" + modelData.number
            onClicked: fileBridge.research.selectCandidate(modelData.id)
            background: Rectangle { color: selected.id === modelData.id ? theme.accentPale : parent.hovered ? theme.hover : theme.surface; radius: 3; border.width: selected.id === modelData.id ? 1 : 0; border.color: theme.accent }
            contentItem: RowLayout {
                spacing: 8
                Rectangle { width: 5; Layout.fillHeight: true; radius: 2; color: root.colorFor(modelData.type) }
                ColumnLayout { Layout.fillWidth: true; spacing: 2
                    Text { text: "#" + modelData.number + "  " + modelData.type + (modelData.low_score ? " · 낮은 점수" : ""); color: theme.text; font.pixelSize: 12 }
                    Text { text: "(" + modelData.x.toFixed(1) + ", " + modelData.y.toFixed(1) + ")"; color: theme.muted; font.pixelSize: 10 }
                }
                Text { text: typeof modelData.score === "number" ? modelData.score.toFixed(3) : "—"; color: theme.text; font.family: theme.monoFontFamily; font.pixelSize: 11 }
                Text { text: modelData.viewed ? "●" : "○"; color: modelData.viewed ? theme.accent : theme.muted; font.pixelSize: 10 }
            }
        }
        Text { anchors.centerIn: parent; visible: results.filteredTotal === 0; text: uiState.hasResult ? "조건에 맞는 후보가 없습니다" : "분석 결과 없음"; color: theme.muted; font.pixelSize: 12 }
        Connections { target: fileBridge.research
            function onFocusRequested(x, y) { candidates.positionViewAtIndex(results.selectedIndex % 100, ListView.Contain) }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        AppButton { theme: root.theme; text: "‹"; enabled: results.page > 0; onClicked: fileBridge.research.setResultPage(results.page - 1) }
        Text { text: (results.page + 1) + " / " + results.pages + " 페이지 · 100개씩"; color: theme.muted; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
        AppButton { theme: root.theme; text: "›"; enabled: results.page + 1 < results.pages; onClicked: fileBridge.research.setResultPage(results.page + 1) }
        CheckBox { text: "위치 표시"; checked: uiState.analysisLayerVisible; onToggled: uiState.analysisLayerVisible = checked }
    }
    Text { visible: results.limited || results.excluded > 0; text: (results.limited ? "자동 후보 상한 도달 · " : "") + "경계·범위 등 제외 " + results.excluded; color: theme.warning; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true }
    RowLayout {
        Layout.fillWidth: true
        AppButton { objectName: "analysisExportButton"; theme: root.theme; text: "전체 결과 저장…"; Layout.fillWidth: true; enabled: uiState.hasResult; onClicked: root.exportRequested() }
        AppButton { theme: root.theme; text: "실행 정보"; enabled: uiState.hasResult; onClicked: info.open() }
    }
    Text { visible: !!results.error || !!results.exportPath; text: results.error || "저장 완료: " + results.exportPath; color: results.error ? theme.warning : theme.muted; font.pixelSize: 10; elide: Text.ElideMiddle; Layout.fillWidth: true }
    Dialog {
        id: info; parent: Overlay.overlay; title: "분석 실행 정보"; modal: true; width: Math.min(560, parent.width - 40); x: (parent.width - width)/2; y: (parent.height - height)/2; standardButtons: Dialog.Close
        contentItem: TextArea { readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; text: "원본: " + results.runInfo.source + "\n페이지: " + results.runInfo.page + "\n좌표: 원시 픽셀 (EXIF 자동 회전 미적용)\n방식: " + (results.runInfo.mode === "provided_coordinates" ? "제공 좌표 분류" : "밝기 대비 자동 후보") + "\n소요 시간: " + results.runInfo.seconds + "초\n완료: " + results.runInfo.completed + "\n실행 ID: " + results.runInfo.analysisId + "\n모델: " + results.runInfo.model + "\n모델 해시: " + results.runInfo.modelHash + "\n\n살펴봄 표시는 이번 실행의 탐색 기록이며 정답 검수 기록이 아닙니다." }
    }
}
