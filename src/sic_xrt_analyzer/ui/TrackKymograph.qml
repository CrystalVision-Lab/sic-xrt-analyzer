import QtQuick

// Straightened X–page / Y–page slice along the selected track centroid path.
Rectangle {
    id: root
    property QtObject theme
    property var kymo: ({})
    property string kind: "xp"
    property int page: 0
    signal pageRequested(int k)
    color: theme.viewer
    radius: theme.radiusSm
    clip: true
    Text { id: title; anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 6; color: root.theme.viewerText; font.pixelSize: 12
        text: (root.kind === "xp" ? "X–페이지" : "Y–페이지") + " · 트랙 경로 기준 ±" + (root.kymo.radius || 0) + "px" }
    Item {
        id: plot
        anchors.fill: parent; anchors.topMargin: title.height + 10; anchors.margins: 6
        readonly property int pages: Math.max(1, root.kymo.pages || 1)
        Image { objectName: "trackKymograph_" + root.kind; anchors.fill: parent; source: root.kymo[root.kind] || ""; fillMode: Image.Stretch; smooth: false; cache: false }
        // Track span bracket and centre line (path is the centre column by construction).
        Rectangle { visible: !!root.kymo[root.kind]; x: parent.width / 2 - 0.5; width: 1
            y: (root.kymo.first || 0) / plot.pages * parent.height
            height: ((root.kymo.last || 0) - (root.kymo.first || 0) + 1) / plot.pages * parent.height
            color: "#56B4E9"; opacity: .7 }
        Rectangle { visible: !!root.kymo[root.kind]; width: parent.width; height: Math.max(1, parent.height / plot.pages); y: root.page / plot.pages * parent.height
            color: "transparent"; border.color: root.theme.accent; border.width: 1 }
        MouseArea { anchors.fill: parent; onClicked: function(m) { root.pageRequested(Math.floor(m.y / Math.max(1, height) * plot.pages)) } }
    }
}
