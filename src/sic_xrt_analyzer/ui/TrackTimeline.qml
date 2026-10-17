import QtQuick
import QtQuick.Layouts

// Per-page link timeline. Colour (Okabe–Ito) is always paired with a glyph.
ColumnLayout {
    id: root
    property QtObject theme
    property var items: []
    property int page: 0
    signal pageRequested(int k)
    spacing: 4
    function colorOf(state) {
        return ({start: "#0072B2", linked: "#009E73", low: "#E69F00", accepted: "#56B4E9",
                 manual: "#CC79A7", gap: "#7f7f7f"})[state] || root.theme.surface
    }
    Item {
        objectName: "trackTimeline"
        Layout.fillWidth: true; implicitHeight: 34
        readonly property real cell: width / Math.max(1, root.items.length)
        Repeater {
            model: root.items
            Item {
                required property var modelData
                required property int index
                x: index * parent.cell; width: Math.max(1, parent.cell); height: parent.height
                Text { anchors.horizontalCenter: parent.horizontalCenter; y: 0; visible: !!parent.modelData.candidateMarker
                    text: parent.modelData.candidateMarker; color: root.theme.text; font.pixelSize: 10; font.bold: true }
                Rectangle {
                    y: 12; width: parent.width; height: parent.height - 12
                    color: root.colorOf(parent.modelData.state)
                    border.width: parent.modelData.state === "gap" ? 1 : 0; border.color: root.theme.muted
                    // outside the track span: neutral base, no marker
                    opacity: parent.modelData.state === "gap" ? .45 : 1
                    Text { anchors.centerIn: parent; visible: parent.width >= 7; text: parent.parent.modelData.marker; color: "#111"; font.pixelSize: Math.min(11, parent.width) }
                }
                Rectangle { visible: parent.index === root.page; y: 10; width: parent.width; height: parent.height - 10; color: "transparent"; border.color: root.theme.text; border.width: 2 }
                MouseArea { anchors.fill: parent; onClicked: root.pageRequested(parent.index) }
            }
        }
    }
    Flow {
        Layout.fillWidth: true; spacing: 10
        Repeater {
            model: [{s: "start", m: "▶", l: "시작"}, {s: "linked", m: "●", l: "링크"}, {s: "low", m: "!", l: "저신뢰 링크"},
                    {s: "accepted", m: "✓", l: "수락"}, {s: "manual", m: "+", l: "수동 병합"}, {s: "gap", m: "–", l: "공백"},
                    {s: "", m: "< >", l: "분기·합류 후보"}]
            Row {
                required property var modelData
                spacing: 4
                Rectangle { width: 16; height: 14; color: modelData.s ? root.colorOf(modelData.s) : "transparent"; border.color: root.theme.muted; border.width: modelData.s ? 0 : 1
                    Text { anchors.centerIn: parent; text: modelData.m; font.pixelSize: 10; color: modelData.s ? "#111" : root.theme.text } }
                Text { text: modelData.l; color: root.theme.muted; font.pixelSize: 11 }
            }
        }
    }
}
