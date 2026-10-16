import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "resultCandidateShelf"
    required property QtObject theme
    required property QtObject uiState
    readonly property var navigator: fileBridge.research.regions
    readonly property var area: navigator.state
    readonly property bool comparing: uiState.resultViewMode === "compare"
    readonly property var rows: comparing ? area.compareRows : area.rows
    signal candidateRequested(string ident)
    onRowsChanged: Qt.callLater(root.revealSelection)
    function revealSelection() {
        var index = rows.findIndex(function(p) { return p.id===root.uiState.research.selected.id })
        if (index>=0) grid.positionViewAtIndex(index, GridView.Contain)
    }
    Connections { target:fileBridge.research; function onChanged() { Qt.callLater(root.revealSelection) } }
    color: theme.panel; radius: theme.radiusPanel
    implicitHeight: comparing ? 280 : 152
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 12; spacing: 8
        RowLayout {
            Layout.fillWidth: true
            Text { text: root.comparing ? "후보 이미지 비교 · 동일한 128 px 범위" : "이 영역의 주변 후보 · "+root.rows.length+"개"; color: root.theme.text; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideRight }
            AppButton { theme: root.theme; compact: true; text: "‹"; tip: "이전 비교 페이지"; visible: root.comparing; enabled: root.area.comparePage>0; onClicked:root.navigator.setComparePage(root.area.comparePage-1) }
            Text { visible: root.comparing; text: (root.area.comparePage+1)+" / "+root.area.comparePages; color: root.theme.muted; font.pixelSize: 12 }
            AppButton { theme: root.theme; compact: true; text: "›"; tip: "다음 비교 페이지"; visible: root.comparing; enabled: root.area.comparePage+1<root.area.comparePages; onClicked:root.navigator.setComparePage(root.area.comparePage+1) }
        }
        GridView {
            id: grid; objectName: "resultCandidateGrid"
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            cellWidth: Math.max(115, width / Math.max(1,Math.floor(width/135))); cellHeight: 105
            model: root.rows; ScrollBar.vertical: ScrollBar {}
            delegate: Rectangle {
                required property var modelData
                width: grid.cellWidth-8; height: 99; radius: root.theme.radiusControl
                color: root.uiState.research.selected.id===modelData.id ? root.theme.accentPale : root.theme.surface
                border.width: root.uiState.research.selected.id===modelData.id ? 1 : 0; border.color: root.theme.accent
                Button {
                    objectName: "shelfCandidate"+modelData.number
                    anchors.fill: parent; padding: 6; background: Item {}
                    Accessible.name: "후보 "+modelData.number+" "+modelData.type+" 원본에서 보기"
                    Accessible.selected: root.uiState.research.selected.id===modelData.id
                    onClicked: root.candidateRequested(modelData.id)
                    contentItem: ColumnLayout {
                        spacing: 3
                        Item { Layout.fillWidth:true; Layout.preferredHeight:50
                            Image { anchors.fill:parent; source:modelData.thumbnail||""; cache:false; smooth:false; fillMode:Image.PreserveAspectFit }
                            Text { anchors.centerIn:parent; visible:!modelData.thumbnail; text:root.area.thumbnailError?"읽기 실패":modelData.thumbnailOmitted?"선택하여 원본 보기":"미리보기 준비 중"; color:root.theme.muted; font.pixelSize:11 }
                        }
                        Text { text:"#"+modelData.number+" · "+modelData.type; color:root.uiState.resultPresentation.colorFor(modelData.type); font.pixelSize:12; Layout.fillWidth:true; elide:Text.ElideRight }
                        Text { text:modelData.review==="CONFIRMED"?"확인됨":modelData.review==="HOLD"?"보류":"미검토"; color:root.theme.muted; font.pixelSize:11 }
                    }
                }
                AppCheckBox { visible:root.comparing; anchors.right:parent.right; anchors.top:parent.top; theme:root.theme; checked:modelData.checked; Accessible.name:"후보 "+modelData.number+" 선택"; onClicked:root.navigator.check(modelData.id,checked) }
            }
            Text { anchors.centerIn:parent; visible:root.rows.length===0; text:"표시할 후보가 없습니다"; color:root.theme.muted; font.pixelSize:13 }
        }
    }
}
