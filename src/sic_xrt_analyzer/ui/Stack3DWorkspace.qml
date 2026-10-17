import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 스택 추적 검토: track table, XY page view, kymographs, link timeline, filmstrip.
// Pages are section-scan order, not verified physical depth.
ColumnLayout {
    id: root
    objectName: "stack3dWorkspace"
    property QtObject theme
    property QtObject uiState
    signal projectRequested()
    property var review: fileBridge.trackReview
    property var rs: review.state
    property var ss: fileBridge.stack3d.state
    readonly property bool active: visible && rs.ready && !rs.stale
    readonly property var track: rs.track || ({})
    spacing: 8

    Shortcut { sequence: "A"; enabled: root.active; onActivated: root.review.acceptLink() }
    Shortcut { sequence: "S"; enabled: root.active; onActivated: root.review.splitAtPage() }
    Shortcut { sequence: "M"; enabled: root.active; onActivated: root.review.mergeWithTarget() }
    Shortcut { sequence: "R"; enabled: root.active; onActivated: root.review.rejectTrack() }
    Shortcut { sequence: "D"; enabled: root.active; onActivated: root.review.setOverlay(!root.rs.overlay) }
    Shortcut { sequence: "Left"; enabled: root.active; onActivated: root.review.stepPage(-1) }
    Shortcut { sequence: "Right"; enabled: root.active; onActivated: root.review.stepPage(1) }
    Shortcut { sequence: "Up"; enabled: root.active; onActivated: root.review.selectRelative(-1) }
    Shortcut { sequence: "Down"; enabled: root.active; onActivated: root.review.selectRelative(1) }
    Shortcut { sequences: [StandardKey.Undo]; enabled: root.active; onActivated: root.review.undo() }

    RowLayout {
        Layout.fillWidth: true
        AppButton { objectName: "stack3dBack"; theme: root.theme; text: "← 이미지"; onClicked: root.uiState.workspaceIndex = 0 }
        Text { text: "스택 추적"; color: root.theme.text; font.pixelSize: 18 }
        Text { objectName: "trackReviewMessage"; text: root.rs.error || root.rs.message || root.ss.error || ""; color: root.rs.error ? root.theme.warning : root.theme.muted; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true; Layout.preferredWidth: 0 }
        AppButton { objectName: "trackReviewReselect"; theme: root.theme; text: "다시 선택"; tip: "이미지에서 다른 결함을 클릭합니다"; onClicked: { root.uiState.workspaceIndex = 0; root.uiState.activeTool = "StackTrack" } }
        AppButton { objectName: "trackReviewRun"; theme: root.theme; primary: !root.rs.ready; text: root.rs.ready ? "다시 추적" : "스택 추적 실행"; enabled: root.rs.volumeReady && !root.rs.busy && !root.ss.busy; onClicked: root.review.run() }
        AppTextField { id: reviewerField; objectName: "trackReviewer"; visualTheme: root.theme; placeholderText: "검토자 ID"; text: root.rs.reviewer; maximumLength: 120; Layout.preferredWidth: 130; onEditingFinished: root.review.setReviewer(text) }
        AppButton { objectName: "trackReviewSave"; theme: root.theme; text: root.rs.pending > 0 ? "프로젝트에 저장 (" + root.rs.pending + ")" : "프로젝트에 저장"
            enabled: root.ss.project && root.ss.ready && !root.ss.busy && !root.rs.busy && !!reviewerField.text
            tip: "보정 이벤트와 자동 결과를 3D 세션에 추가 기록합니다 (원본 SHA 확인)"
            onClicked: { root.review.setReviewer(reviewerField.text); fileBridge.stack3d.save(reviewerField.text) } }
    }
    RowLayout {
        visible: root.rs.busy || root.ss.busy; Layout.fillWidth: true
        Text { text: root.rs.busy ? root.rs.progress[2] : (root.ss.progress[2] || "Volume 준비"); color: root.theme.muted }
        ProgressBar { Layout.fillWidth: true; from: 0; to: Math.max(1, root.rs.busy ? root.rs.progress[1] : root.ss.progress[1]); value: root.rs.busy ? root.rs.progress[0] : root.ss.progress[0] }
        AppButton { objectName: "trackReviewCancel"; theme: root.theme; text: "취소"; onClicked: { root.review.cancel(); if (root.ss.busy) fileBridge.stack3d.cancel() } }
    }
    Text {
        Layout.fillWidth: true; Layout.preferredWidth: 0; wrapMode: Text.Wrap; font.pixelSize: 12; color: root.theme.muted
        text: "페이지는 스캔 순서이며 물리 깊이가 아닙니다. 자동 트랙과 링크는 제안이고, 보정은 이벤트로 추가 기록됩니다."
    }

    Text {
        objectName: "trackReviewEmpty"
        visible: !root.rs.ready || root.rs.stale
        Layout.fillWidth: true; Layout.preferredWidth: 0; Layout.fillHeight: !root.rs.ready || root.rs.stale
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap; color: root.theme.muted
        text: root.rs.busy || root.ss.busy ? "준비 중…" : root.rs.stale ? "Volume 선택이 저장된 추적 결과와 다릅니다 · 같은 선택으로 Volume을 다시 열거나 다시 추적하세요"
              : root.rs.volumeReady ? "‘스택 추적 실행’으로 이 ROI의 모든 페이지에서 트랙을 찾습니다"
              : "이미지 도구 모음의 ‘스택 추적’을 누르고 추적할 결함을 클릭하세요"
    }

    SplitView {
        visible: root.rs.ready && !root.rs.stale
        Layout.fillWidth: true; Layout.fillHeight: true; orientation: Qt.Horizontal

        // Track table
        ColumnLayout {
            SplitView.preferredWidth: 330; SplitView.minimumWidth: 260; spacing: 4
            RowLayout {
                Layout.fillWidth: true; spacing: 4
                Text { text: "트랙 " + root.review.tracks.length + " / " + root.rs.trackCount; color: root.theme.text; elide: Text.ElideRight; Layout.fillWidth: true; Layout.preferredWidth: 0 }
                Repeater {
                    model: [{k: "review", l: "검토 우선"}, {k: "length", l: "길이"}, {k: "start", l: "시작"}]
                    AppButton { required property var modelData; objectName: "trackSort_" + modelData.k; theme: root.theme; compact: true; text: modelData.l; checked: root.rs.sort === modelData.k; onClicked: root.review.setSort(modelData.k) }
                }
            }
            AppCheckBox { objectName: "trackHideShort"; theme: root.theme; text: "3페이지 미만 숨김"; checked: root.rs.hideShort; onToggled: root.review.setHideShort(checked) }
            RowLayout {
                Layout.fillWidth: true
                Repeater {
                    model: [{l: "트랙", w: 64}, {l: "페이지", w: 78}, {l: "검출", w: 36}, {l: "최소 링크", w: 56}, {l: "상태", w: 60}]
                    Text { required property var modelData; text: modelData.l; color: root.theme.muted; font.pixelSize: 11; Layout.preferredWidth: modelData.w }
                }
            }
            ListView {
                id: table
                objectName: "trackTable"
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                model: root.review.tracks
                currentIndex: { for (var i = 0; i < count; ++i) if (model[i].id === root.rs.selected) return i; return -1 }
                onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, ListView.Contain)
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width; height: 26
                    readonly property bool selected: modelData.id === root.rs.selected
                    readonly property bool target: modelData.id === root.rs.mergeTarget
                    color: selected ? root.theme.accentPale : target ? root.theme.hover : "transparent"
                    border.width: target ? 1 : 0; border.color: root.theme.accent
                    opacity: modelData.status === "REJECTED" ? .5 : 1
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 4
                        Text { text: (parent.parent.target ? "⇄ " : "") + modelData.id; color: root.theme.text; font.pixelSize: 12; Layout.preferredWidth: 64; elide: Text.ElideRight }
                        Text { text: (modelData.first + 1) + "–" + (modelData.last + 1); color: root.theme.text; font.pixelSize: 12; Layout.preferredWidth: 78 }
                        Text { text: modelData.detections + (modelData.gaps ? "+" + modelData.gaps : ""); color: root.theme.text; font.pixelSize: 12; Layout.preferredWidth: 36 }
                        Text { text: modelData.minConfidence.toFixed(2); color: modelData.pendingLinks ? "#E69F00" : root.theme.text; font.pixelSize: 12; font.bold: modelData.pendingLinks > 0; Layout.preferredWidth: 56 }
                        Text {
                            Layout.fillWidth: true; font.pixelSize: 11; elide: Text.ElideRight
                            text: modelData.status === "REJECTED" ? "✕ 거부" : modelData.review ? "! 검토" + (modelData.candidates ? " <>" : "") : modelData.source === "MANUAL" ? "+ 보정" : "● 자동"
                            color: modelData.review ? "#E69F00" : root.theme.muted
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: function(m) { if (m.modifiers & Qt.ControlModifier) root.review.setMergeTarget(modelData.id); else root.review.selectTrack(modelData.id) }
                    }
                }
            }
        }

        // XY page view with detection overlay
        ColumnLayout {
            SplitView.fillWidth: true; SplitView.minimumWidth: 300; spacing: 4
            RowLayout {
                Layout.fillWidth: true
                Text { objectName: "trackPageLabel"; text: "페이지 " + root.rs.pageNumber + " / 트랙 " + (root.track.id || "-") + (root.track.id ? " · 페이지 " + (root.track.first + 1) + "–" + (root.track.last + 1) : ""); color: root.theme.text; elide: Text.ElideRight; Layout.fillWidth: true; Layout.preferredWidth: 0 }
                AppCheckBox { theme: root.theme; text: "검출 표시 (D)"; checked: root.rs.overlay; onToggled: root.review.setOverlay(checked) }
            }
            StackOrthogonalView {
                Layout.fillWidth: true; Layout.fillHeight: true
                controller: fileBridge.stack3d; theme: root.theme; kind: "xy"; overlaySource: root.rs.pageOverlay
                onPicked: function(kind, u, v, modifiers) { root.review.pickXY(u, v, (modifiers & Qt.ControlModifier) !== 0) }
            }
            Text { text: "채움 = 선택 트랙 · 윤곽 = 다른 검출 · 클릭 트랙 선택 · Ctrl+클릭 병합 대상 · 휠 페이지"; color: root.theme.muted; font.pixelSize: 11; Layout.fillWidth: true; Layout.preferredWidth: 0; wrapMode: Text.Wrap }
        }

        // Kymographs
        ColumnLayout {
            SplitView.preferredWidth: 240; SplitView.minimumWidth: 160; spacing: 6
            TrackKymograph { theme: root.theme; kind: "xp"; kymo: root.review.kymograph; page: root.rs.page; Layout.fillWidth: true; Layout.fillHeight: true; onPageRequested: function(k) { root.review.setPage(k) } }
            TrackKymograph { theme: root.theme; kind: "yp"; kymo: root.review.kymograph; page: root.rs.page; Layout.fillWidth: true; Layout.fillHeight: true; onPageRequested: function(k) { root.review.setPage(k) } }
        }
    }

    TrackTimeline {
        visible: root.rs.ready && !root.rs.stale
        Layout.fillWidth: true
        theme: root.theme; items: root.review.timeline; page: root.rs.page
        onPageRequested: function(k) { root.review.setPage(k) }
    }

    ListView {
        id: film
        objectName: "trackFilmstrip"
        visible: root.rs.ready && !root.rs.stale
        Layout.fillWidth: true; implicitHeight: 118; orientation: ListView.Horizontal; spacing: 4; clip: true
        model: root.review.filmstrip
        currentIndex: { for (var i = 0; i < count; ++i) if (model[i].k === root.rs.page) return i; return -1 }
        onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, ListView.Contain)
        ScrollBar.horizontal: ScrollBar {}
        delegate: Rectangle {
            required property var modelData
            readonly property var cell: root.review.timeline[modelData.k] || ({})
            width: 92; height: 112; color: root.theme.viewer; radius: 4
            border.width: modelData.k === root.rs.page ? 2 : 0; border.color: root.theme.accent
            Image { id: thumb; x: 4; y: 4; width: 84; height: 84; source: modelData.url; smooth: false; cache: false; fillMode: Image.PreserveAspectFit }
            Image { anchors.fill: thumb; visible: root.rs.overlay && !!modelData.overlay; source: modelData.overlay; smooth: false; cache: false; fillMode: Image.PreserveAspectFit }
            Text { x: 4; y: 92; text: "페이지 " + (modelData.page + 1); color: root.theme.viewerText; font.pixelSize: 11 }
            Text { anchors.right: parent.right; anchors.rightMargin: 4; y: 92; text: (parent.cell.marker || "") + (parent.cell.candidateMarker || ""); color: parent.cell.state === "low" ? "#E69F00" : root.theme.viewerText; font.pixelSize: 12; font.bold: true }
            MouseArea { anchors.fill: parent; onClicked: root.review.setPage(modelData.k) }
        }
    }

    RowLayout {
        visible: root.rs.ready && !root.rs.stale
        Layout.fillWidth: true; spacing: 6
        AppButton { objectName: "trackAccept"; theme: root.theme; text: "링크 수락 (A)"; onClicked: root.review.acceptLink() }
        AppButton { objectName: "trackSplit"; theme: root.theme; text: "이 페이지에서 분할 (S)"; onClicked: root.review.splitAtPage() }
        AppButton { objectName: "trackMerge"; theme: root.theme; text: "병합 (M)" + ((root.rs.mergeTarget || (root.rs.mergeCandidates || [])[0]) ? " → " + (root.rs.mergeTarget || root.rs.mergeCandidates[0]) : ""); onClicked: root.review.mergeWithTarget() }
        AppButton { objectName: "trackReject"; theme: root.theme; text: "트랙 거부 (R)"; onClicked: root.review.rejectTrack() }
        AppButton { objectName: "trackUndo"; theme: root.theme; text: "되돌리기 (Ctrl+Z)"; enabled: root.rs.pending > 0; onClicked: root.review.undo() }
        Text { text: "←/→ 페이지 · ↑/↓ 트랙 · 보정 " + root.rs.events + "건 (미저장 " + root.rs.pending + ")"; color: root.theme.muted; font.pixelSize: 12; horizontalAlignment: Text.AlignRight; elide: Text.ElideLeft; Layout.fillWidth: true; Layout.preferredWidth: 0 }
    }
}
