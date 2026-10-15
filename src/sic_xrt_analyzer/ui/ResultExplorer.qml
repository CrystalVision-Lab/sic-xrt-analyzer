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
    signal exportRequested()
    signal overviewRequested()
    signal reviewRequested()
    spacing: theme.spacingSm
    Connections {
        target: fileBridge.research
        function onChanged() { Qt.callLater(function() { if (root.results.selectedIndex >= 0) candidates.positionViewAtIndex(root.results.selectedIndex % 100, ListView.Contain) }) }
    }
    Text { objectName: "resultOrigin"; visible: results.savedActive; text: "저장된 이력"; color: theme.muted; font.pixelSize: theme.smallSize }
    RowLayout {
        Layout.fillWidth: true
        Text { objectName: "resultTotal"; text: "결과 " + presentation.count(results.total); color: root.theme.text; font.pixelSize: 24; font.weight: Font.DemiBold; Layout.fillWidth: true }
        AppButton { objectName: "resultOverview"; theme: root.theme; text: "전체 보기"; quiet: true; compact: true; onClicked: root.overviewRequested() }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 4
        Repeater {
            model: ["ALL", "BPD", "TED", "TSD"]
            AppButton {
                required property string modelData
                objectName: "resultFilter" + modelData
                theme: root.theme
                compact: true
                labelSize: 13
                leftPadding: 8; rightPadding: 8
                text: modelData === "ALL" ? "전체" : modelData + " " + presentation.count(root.results.counts[modelData] || 0)
                checked: root.results.filterKind === modelData
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                onClicked: {
                    fileBridge.research.setFilter(modelData, false, "")
                    root.uiState.bpdLayerVisible = modelData === "ALL" || modelData === "BPD"
                    root.uiState.tedLayerVisible = modelData === "ALL" || modelData === "TED"
                    root.uiState.tsdLayerVisible = modelData === "ALL" || modelData === "TSD"
                }
            }
        }
    }
    Text { visible: results.limited; text: "후보 생성 한도 도달"; color: theme.warning; font.pixelSize: theme.smallSize; Layout.fillWidth: true }
    Rectangle {
        visible: !!root.selected.id
        Layout.fillWidth: true
        implicitHeight: selectionContent.implicitHeight + 24
        radius: root.theme.radiusDialog
        color: root.theme.surface
        border.color: root.theme.borderSubtle
        RowLayout {
            id: selectionContent
            anchors.fill: parent; anchors.margins: 12
            spacing: root.theme.spacingMd
            Image { objectName: "candidateThumbnail"; source: root.results.thumbnailSource; cache: false; smooth: false; Layout.preferredWidth: 88; Layout.preferredHeight: 88 }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                Text { objectName: "selectedCandidateHeader"; text: "#" + root.selected.number + " · " + root.selected.type; color: root.theme.text; font.pixelSize: 18; font.weight: Font.DemiBold; Layout.fillWidth: true }
                Text { objectName: "candidateConfidence"; text: "모델 점수 " + root.presentation.confidence(root.selected.score); color: root.theme.text; font.pixelSize: 14; Layout.fillWidth: true }
                Text { text: Math.round(root.selected.x || 0) + ", " + Math.round(root.selected.y || 0) + " px"; color: root.theme.muted; font.pixelSize: root.theme.smallSize; Layout.fillWidth: true }
                RowLayout {
                    Layout.alignment: Qt.AlignLeft
                    spacing: 6
                    AppButton { objectName: "candidateDetails"; theme: root.theme; text: "상세"; compact: true; onClicked: details.open() }
                    AppButton { objectName: "reportCandidate"; theme: root.theme; text: "신고"; compact: true; enabled: root.results.pixelsAvailable; onClicked: report.open() }
                }
            }
        }
    }
    RowLayout {
        visible: results.filteredTotal > 0
        Layout.fillWidth: true
        AppButton { objectName: "previousCandidate"; theme: root.theme; text: "← 이전"; compact: true; enabled: results.selectedIndex > 0; onClicked: fileBridge.research.stepCandidate(-1) }
        Text { objectName: "candidateIndex"; font.pixelSize: 13; text: selected.id ? "후보 " + presentation.count(results.selectedIndex + 1) + " / " + presentation.count(results.filteredTotal) : "후보 선택 전"; color: theme.muted; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
        AppButton { objectName: "nextCandidate"; theme: root.theme; text: "다음 →"; compact: true; enabled: results.filteredTotal > 0 && results.selectedIndex < results.filteredTotal - 1; onClicked: fileBridge.research.stepCandidate(1) }
    }
    Text { objectName: "emptyCandidateDetail"; visible: results.filteredTotal > 0 && !selected.id; text: "후보를 선택하세요"; color: theme.muted; font.pixelSize: theme.bodySize }
    ListView {
        id: candidates
        objectName: "candidateList"
        visible: results.filteredTotal > 0
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 80
        clip: true
        spacing: 6
        model: results.displayRows
        ScrollBar.vertical: ScrollBar {}
        delegate: ItemDelegate {
            required property var modelData
            width: candidates.width; height: 52
            objectName: "candidateRow" + modelData.number
            background: Rectangle {
                color: root.selected.id === parent.modelData.id ? root.theme.accentPale : parent.hovered ? root.theme.hover : root.theme.surface
                radius: root.theme.radiusControl
                border.width: parent.activeFocus ? 1 : 0
                border.color: root.theme.accent
            }
            contentItem: RowLayout {
                Text { text: "#" + modelData.number; color: root.theme.text; Layout.fillWidth: true; font.pixelSize: root.theme.bodySize }
                Text { text: modelData.type; color: root.presentation.colorFor(modelData.type); font.pixelSize: root.theme.bodySize }
                Text { text: root.presentation.confidence(modelData.score); color: root.theme.muted; font.pixelSize: 13 }
            }
            Accessible.name: "후보 " + modelData.number + " " + modelData.type
            Accessible.selected: root.selected.id === modelData.id
            onClicked: fileBridge.research.selectCandidate(modelData.id)
        }
    }
    RowLayout {
        Layout.fillWidth: true
        AppButton { theme: root.theme; text: "‹"; compact: true; visible: results.pages > 1; enabled: results.page > 0; onClicked: fileBridge.research.setResultPage(results.page - 1) }
        Text { visible: results.pages > 1; text: (results.page + 1) + " / " + Math.max(1, results.pages); color: theme.muted; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
        AppButton { theme: root.theme; text: "›"; compact: true; visible: results.pages > 1; enabled: results.page + 1 < results.pages; onClicked: fileBridge.research.setResultPage(results.page + 1) }
        Item { visible: results.pages <= 1; Layout.fillWidth: true }
        AppButton { objectName: "analysisExportButton"; theme: root.theme; text: "내보내기"; iconName: "export"; compact: true; onClicked: root.exportRequested() }
    }
    ReportDialog { id: report; theme: root.theme; uiState: root.uiState }
    SurfaceDialog {
        id: details
        objectName: "candidateDetailDialog"
        parent: Overlay.overlay
        title: "후보 상세"
        modal: true
        width: 440
        x: (parent.width - width) / 2
        y: (parent.height - height) / 2
        standardButtons: Dialog.Close
        ColumnLayout {
            width: parent.width
            spacing: 16
            Text { text: "#" + root.selected.number + " · " + root.selected.type; color: root.theme.text; font.pixelSize: 22; font.weight: Font.DemiBold }
            Repeater {
                model: ["BPD", "TED", "TSD"]
                Text { required property int index; required property string modelData; objectName: "rawScore" + modelData; text: modelData + "  " + root.presentation.confidence(root.selected.scores ? root.selected.scores[index] : undefined) + "   /   " + root.presentation.raw(root.selected.scores ? root.selected.scores[index] : undefined); color: root.theme.text; font.pixelSize: 16 }
            }
            Text { text: "X " + (root.selected.x || 0).toFixed(2) + "    Y " + (root.selected.y || 0).toFixed(2) + " px"; color: root.theme.muted; font.pixelSize: 14 }
            AppButton { objectName: "copyCandidate"; theme: root.theme; text: "좌표 복사"; onClicked: fileBridge.copyText("X=" + root.selected.x + " Y=" + root.selected.y + " " + root.selected.type) }
            Text { visible: root.selected.type === "BPD"; text: "영역: 구조 기반 제안"; color: root.theme.muted; font.pixelSize: root.theme.smallSize }
        }
    }
}
