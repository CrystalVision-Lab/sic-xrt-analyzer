import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Keyboard-first candidate review. One key = one decision; every decision is stored
// locally first (append-only) and sent to the research server on request.
Popup {
    id: root
    objectName: "reviewQueueDialog"
    property QtObject theme
    property QtObject queue: fileBridge.reviewQueue
    readonly property var s: queue.state
    readonly property var current: s.current || ({})
    parent: Overlay.overlay
    x: 0; y: 0; width: parent ? parent.width : 1100; height: parent ? parent.height : 700
    modal: true; focus: true; padding: 0
    closePolicy: Popup.CloseOnEscape
    visible: s.active
    onClosed: if (s.active) queue.stop()
    onOpened: keyCatcher.forceActiveFocus()
    background: Rectangle { color: root.theme.window }

    function colorFor(kind) { return kind === "BPD" ? "#E69F00" : kind === "TED" ? "#56B4E9" : kind === "TSD" ? "#CC79A7" : root.theme.muted }
    function shapeFor(kind) { return kind === "BPD" ? "◆" : kind === "TED" ? "▲" : kind === "TSD" ? "■" : "●" }
    function decisionText(d) { return ({BPD: "BPD", TED: "TED", TSD: "TSD", NOT_DEFECT: "결함 아님", UNSURE: "보류"})[d] || "" }
    function percent(v) { return (typeof v === "number" && isFinite(v)) ? Math.round(v * 100) + "%" : "—" }

    Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true
        Keys.onPressed: function(event) {
            if (reviewerField.activeFocus) return
            var k = event.key, handled = true
            if (k === Qt.Key_1) queue.decide("BPD")
            else if (k === Qt.Key_2) queue.decide("TED")
            else if (k === Qt.Key_3) queue.decide("TSD")
            else if (k === Qt.Key_0 || k === Qt.Key_X) queue.decide("NOT_DEFECT")
            else if (k === Qt.Key_Question || k === Qt.Key_S) queue.decide("UNSURE")
            else if (k === Qt.Key_Space) queue.acceptPrediction()
            else if (k === Qt.Key_Return || k === Qt.Key_Enter) queue.acceptPage()
            else if (k === Qt.Key_Z) queue.undo()
            else if (k === Qt.Key_Right || k === Qt.Key_J) queue.move(1)
            else if (k === Qt.Key_Left || k === Qt.Key_K) queue.move(-1)
            else if (k === Qt.Key_Down) queue.move(6)
            else if (k === Qt.Key_Up) queue.move(-6)
            else handled = false
            event.accepted = handled
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: root.theme.spacingLg
            spacing: root.theme.spacingMd

            // Header: queue choice, progress, server status
            RowLayout {
                Layout.fillWidth: true
                spacing: root.theme.spacingMd
                Label { text: "후보 검수"; color: root.theme.text; font.pixelSize: root.theme.titleSize; font.weight: Font.DemiBold }
                Repeater {
                    model: [{kind: "uncertain", cls: "", text: "불확실한 순"}, {kind: "class", cls: "BPD", text: "BPD"},
                            {kind: "class", cls: "TED", text: "TED"}, {kind: "class", cls: "TSD", text: "TSD"},
                            {kind: "random", cls: "", text: "무작위 표본 50"}]
                    delegate: AppButton {
                        required property var modelData
                        theme: root.theme; compact: true; checkable: true
                        objectName: "reviewQueueKind-" + modelData.kind + modelData.cls
                        checked: s.kind === modelData.kind && (modelData.kind !== "class" || s.cls === modelData.cls)
                        text: modelData.text
                        tip: modelData.kind === "random" ? "고정된 무작위 표본입니다. 모델 정확도를 편향 없이 추정하는 데 쓰입니다." : modelData.kind === "uncertain" ? "모델이 가장 헷갈려 한 후보부터 보여줍니다." : modelData.text + "로 분류된 후보만 보여줍니다."
                        onClicked: { queue.start(modelData.kind, modelData.cls || "TED"); keyCatcher.forceActiveFocus() }
                    }
                }
                Item { Layout.fillWidth: true }
                ProgressBar {
                    Layout.preferredWidth: 160
                    from: 0; to: Math.max(1, s.total); value: s.reviewed
                }
                Label { objectName: "reviewQueueProgress"; color: root.theme.text; text: "검수 " + s.reviewed + " / " + s.total }
                AppButton {
                    objectName: "reviewQueueSync"; theme: root.theme; compact: true
                    enabled: !s.syncing && s.pending > 0
                    text: s.syncing ? "보내는 중…" : "서버로 보내기 (" + s.pending + ")"
                    tip: s.serverReady ? "판정을 연구 서버로 보냅니다. 이미 보낸 판정: " + s.sent + "건" : "서버가 등록되지 않았습니다. 판정은 이 PC에 보관됩니다."
                    onClicked: { queue.sync(); keyCatcher.forceActiveFocus() }
                }
                AppButton { theme: root.theme; compact: true; text: "닫기"; objectName: "reviewQueueClose"; onClicked: root.close() }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: root.theme.spacingMd
                Label { text: "검수자"; color: root.theme.muted }
                TextField {
                    id: reviewerField; objectName: "reviewQueueReviewer"
                    Layout.preferredWidth: 180; text: s.reviewer; placeholderText: "이름 또는 ID"
                    onEditingFinished: { queue.setReviewer(text); keyCatcher.forceActiveFocus() }
                }
                CheckBox {
                    objectName: "reviewQueueSendCrops"
                    checked: s.sendCrops; text: "판정한 후보의 128px 원본 조각을 함께 보내기 (재학습용)"
                    onToggled: { queue.setSendCrops(checked); keyCatcher.forceActiveFocus() }
                }
                Item { Layout.fillWidth: true }
                Label {
                    objectName: "reviewQueueMessage"
                    color: s.error ? root.theme.error : root.theme.muted
                    text: s.error || s.message || ""
                    elide: Text.ElideRight; Layout.maximumWidth: 420
                }
            }

            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: true
                spacing: root.theme.spacingLg

                // Gallery of original-pixel crops for the current page of the queue
                Rectangle {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    color: root.theme.panel; radius: root.theme.radiusPanel
                    GridView {
                        id: gallery; objectName: "reviewQueueGallery"
                        anchors.fill: parent; anchors.margins: root.theme.spacingMd
                        clip: true
                        cellWidth: Math.max(120, Math.floor(width / Math.max(1, Math.floor(width / 150))))
                        cellHeight: cellWidth + 34
                        model: s.items || []
                        delegate: Item {
                            required property var modelData
                            width: gallery.cellWidth; height: gallery.cellHeight
                            readonly property bool isCurrent: modelData.position === s.index
                            Rectangle {
                                anchors.fill: parent; anchors.margins: 4
                                radius: 8
                                color: isCurrent ? root.theme.accentPale : root.theme.surface
                                border.width: isCurrent ? 2 : 1
                                border.color: isCurrent ? root.theme.accent : root.theme.borderSubtle
                                opacity: modelData.decision && !isCurrent ? 0.55 : 1
                                Image {
                                    id: crop
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 6 }
                                    height: width
                                    source: modelData.image; smooth: false; fillMode: Image.PreserveAspectFit
                                    asynchronous: false
                                    Rectangle { anchors.fill: parent; color: "transparent"; border.color: root.theme.borderSubtle; visible: !modelData.image }
                                    Text { anchors.centerIn: parent; text: root.shapeFor(modelData.type); color: root.colorFor(modelData.type); opacity: 0.85; font.pixelSize: 11 }
                                }
                                Row {
                                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 6 }
                                    spacing: 4
                                    Text { text: root.shapeFor(modelData.type) + " " + modelData.type; color: root.colorFor(modelData.type); font.pixelSize: root.theme.smallSize; font.weight: Font.DemiBold }
                                    Text { text: root.percent(modelData.score); color: root.theme.muted; font.pixelSize: root.theme.smallSize }
                                    Text {
                                        text: modelData.decision ? "→ " + root.decisionText(modelData.decision) : ""
                                        color: modelData.decision === "NOT_DEFECT" ? root.theme.error : modelData.decision === "UNSURE" ? root.theme.warning : root.theme.success
                                        font.pixelSize: root.theme.smallSize; font.weight: Font.DemiBold
                                    }
                                }
                            }
                            MouseArea { anchors.fill: parent; onClicked: { queue.goTo(modelData.position); keyCatcher.forceActiveFocus() } }
                        }
                    }
                    Label {
                        anchors.centerIn: parent; visible: !s.busy && s.total === 0
                        color: root.theme.muted; text: "이 큐에 검수할 후보가 없습니다."
                    }
                    BusyIndicator { anchors.centerIn: parent; running: s.busy; visible: s.busy }
                }

                // Focus panel: enlarged crop, model scores and decision keys
                Rectangle {
                    Layout.preferredWidth: 340; Layout.fillHeight: true
                    color: root.theme.panel; radius: root.theme.radiusPanel
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: root.theme.spacingLg
                        spacing: root.theme.spacingMd
                        Label {
                            text: current.id ? "#" + current.number + "  ·  큐 " + (s.index + 1) + "번째" : "후보 없음"
                            color: root.theme.text; font.weight: Font.DemiBold
                        }
                        Image {
                            objectName: "reviewQueueFocusImage"
                            Layout.fillWidth: true; Layout.preferredHeight: width
                            source: current.image || ""; smooth: false; fillMode: Image.PreserveAspectFit
                            Rectangle { // centre mark: the candidate location
                                anchors.centerIn: parent; width: 18; height: 18; radius: 9
                                color: "transparent"; border.width: 1.5; border.color: "#ffffff"; opacity: 0.8
                            }
                        }
                        Repeater {
                            model: ["BPD", "TED", "TSD"]
                            delegate: RowLayout {
                                required property string modelData
                                required property int index
                                Layout.fillWidth: true
                                Text { text: root.shapeFor(modelData) + " " + modelData; color: root.colorFor(modelData); Layout.preferredWidth: 56; font.pixelSize: root.theme.smallSize }
                                Rectangle {
                                    Layout.fillWidth: true; height: 8; radius: 4; color: root.theme.surface
                                    Rectangle {
                                        width: parent.width * ((current.scores && current.scores.length === 3) ? current.scores[index] : 0)
                                        height: parent.height; radius: 4; color: root.colorFor(modelData)
                                    }
                                }
                                Text { text: (current.scores && current.scores.length === 3) ? root.percent(current.scores[index]) : "—"; color: root.theme.muted; Layout.preferredWidth: 38; font.pixelSize: root.theme.smallSize }
                            }
                        }
                        Label {
                            text: "모델 점수는 보정된 확률이 아닙니다." + (current.decision ? "  현재 판정: " + root.decisionText(current.decision) : "")
                            color: root.theme.muted; font.pixelSize: root.theme.captionSize; wrapMode: Text.Wrap; Layout.fillWidth: true
                        }
                        GridLayout {
                            Layout.fillWidth: true; columns: 3; columnSpacing: 6; rowSpacing: 6
                            Repeater {
                                model: [{d: "BPD", k: "1"}, {d: "TED", k: "2"}, {d: "TSD", k: "3"}]
                                delegate: AppButton {
                                    required property var modelData
                                    theme: root.theme; Layout.fillWidth: true
                                    objectName: "reviewDecide-" + modelData.d
                                    primary: current.type === modelData.d
                                    text: modelData.k + "  " + root.shapeFor(modelData.d) + " " + modelData.d
                                    enabled: !!current.id
                                    onClicked: { queue.decide(modelData.d); keyCatcher.forceActiveFocus() }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 6
                            AppButton { objectName: "reviewDecide-NOT_DEFECT"; theme: root.theme; Layout.fillWidth: true; text: "0  결함 아님"; enabled: !!current.id; onClicked: { queue.decide("NOT_DEFECT"); keyCatcher.forceActiveFocus() } }
                            AppButton { objectName: "reviewDecide-UNSURE"; theme: root.theme; Layout.fillWidth: true; text: "S  판단 보류"; enabled: !!current.id; onClicked: { queue.decide("UNSURE"); keyCatcher.forceActiveFocus() } }
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 6
                            AppButton { objectName: "reviewAcceptPage"; theme: root.theme; Layout.fillWidth: true; text: "Enter  이 페이지 모델대로 확정"; tip: "아직 판정하지 않은 이 페이지의 후보를 모델 분류대로 확정합니다. 틀린 것만 먼저 고치고 누르세요."; enabled: s.total > 0; onClicked: { queue.acceptPage(); keyCatcher.forceActiveFocus() } }
                            AppButton { objectName: "reviewUndo"; theme: root.theme; text: "Z  되돌리기"; onClicked: { queue.undo(); keyCatcher.forceActiveFocus() } }
                        }
                        Item { Layout.fillHeight: true }
                        Label {
                            Layout.fillWidth: true; wrapMode: Text.Wrap
                            color: root.theme.muted; font.pixelSize: root.theme.captionSize
                            text: "Space 모델 분류 수락 · ←/→ 이동 · ↑/↓ 한 줄 이동 · Esc 닫기\n판정은 이 PC에 먼저 저장되고, '서버로 보내기'로 연구 서버에 모입니다."
                        }
                    }
                }
            }
        }
    }
}
