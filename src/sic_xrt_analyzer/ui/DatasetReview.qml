import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    objectName: "datasetReviewWindow"
    visible: true
    width: 1440; height: 940
    minimumWidth: 1150; minimumHeight: 820
    title: "전체 웨이퍼 · 원본 라벨 검수"
    color: "#111827"
    palette.window: "#111827"
    palette.windowText: "#f8fafc"
    palette.text: "#f8fafc"
    palette.base: "#1f2937"
    palette.button: "#334155"
    palette.buttonText: "#f8fafc"
    palette.highlight: "#2563eb"
    palette.highlightedText: "white"
    property var page: ({rows: [], total: 0, reviewed: 0, all: 0})
    property var selected: null
    property int offset: 0
    property string message: ""
    property bool cropFailed: false
    property bool rawReady: false
    property bool markedReady: false
    function reload() {
        page = reviewBridge.query(area.currentValue || "", phase.currentValue || "", origin.currentValue || "", state.currentValue || "", offset, scope.currentIndex===0)
        choose(page.rows.length ? page.rows[0] : null)
    }
    function choose(item) {
        selected = item
        checked.checked = false; notes.text = ""; message = ""; cropFailed=false; rawReady=false; markedReady=false
        label.currentIndex = item ? Math.max(0, label.model.indexOf(item.fine_label)) : 0
    }
    function saveDecision(decision) {
        if (!selected) return
        let result = reviewBridge.save(selected.item_id, decision, label.currentText, actor.text, checked.checked, notes.text)
        if (!result.ok) { message = result.error; return }
        reload(); message = "저장했습니다. 이전 결정은 이력에 남습니다."
    }
    Component.onCompleted: reload()
    Connections { target: reviewBridge; function onError(text) { root.message = text; checked.checked = false; root.cropFailed = true } }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 24; spacing: 14
        Label { text: "전체 웨이퍼 라벨 검수"; color: "#f8fafc"; font.pixelSize: 25; font.bold: true }
        Label { text: "원본 좌표의 패치를 확인하고 결정하세요. 세부 종류 기준·스케일·층 간격은 미확정입니다. 점 검수는 전체 영상 주석 완료를 뜻하지 않습니다."; color: "#fbbf24"; wrapMode: Text.Wrap; Layout.fillWidth: true }
        RowLayout {
            spacing: 12
            ComboBox { id:scope; objectName:"reviewScope"; model:["첫 검수 표본","전체 항목"]; enabled:root.page.priority_count>0; onActivated:{root.offset=0;root.reload()} }
            ComboBox { id: area; objectName: "areaFilter"; textRole: "text"; valueRole: "value"; model: [{text:"전체 웨이퍼",value:""},{text:"웨이퍼 1",value:"1"},{text:"웨이퍼 2",value:"2"},{text:"웨이퍼 3",value:"3"},{text:"웨이퍼 4",value:"4"},{text:"웨이퍼 5",value:"5"},{text:"웨이퍼 6",value:"6"},{text:"웨이퍼 7",value:"7"},{text:"웨이퍼 8",value:"8"},{text:"웨이퍼 9",value:"9"},{text:"3D 프레임",value:"3D"}]; onActivated: {root.offset=0; root.reload()} }
            ComboBox { id: phase; textRole:"text"; valueRole:"value"; model:[{text:"전·후 전체",value:""},{text:"열처리 전",value:"before"},{text:"열처리 후",value:"after"}]; onActivated:{root.offset=0;root.reload()} }
            ComboBox { id: origin; textRole:"text"; valueRole:"value"; model:[{text:"제공자 + 자동 후보",value:""},{text:"제공자 주석",value:"provider"},{text:"자동 대비 후보",value:"contrast"}]; onActivated:{root.offset=0;root.reload()} }
            ComboBox { id: state; textRole:"text"; valueRole:"value"; model:[{text:"미검수",value:"unreviewed"},{text:"보류",value:"hold"},{text:"확인",value:"confirm"},{text:"수정",value:"correct"},{text:"제외",value:"exclude"},{text:"전체 상태",value:""}]; onActivated:{root.offset=0;root.reload()} }
            Item { Layout.fillWidth: true }
            Label { text: "결정 " + root.page.reviewed + " / " + root.page.all; color: "#cbd5e1" }
        }
        Label { text: root.page.priority_count>0 && scope.currentIndex===0 ? "먼저 " + root.page.priority_count + "건만 확인합니다. 제공자 라벨은 유지됩니다. 표본 확인은 전체 정답 승인이 아닙니다. 세부 문자 근거가 없으면 TED·TSD·BPD 또는 보류로 기록하세요." : "전체 목록입니다. 자동 후보는 정답 라벨이 없습니다."; color:"#cbd5e1"; wrapMode:Text.Wrap; Layout.fillWidth:true }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 20
            Rectangle {
                color: "#1f2937"; radius: 10; Layout.preferredWidth: 250; Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 12
                    Label { text: "필터 결과 " + root.page.total + "건"; color: "white" }
                    ListView {
                        id: list; objectName: "reviewItems"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 4
                        model: root.page.rows
                        delegate: ItemDelegate {
                            required property var modelData
                            width: list.width
                            text: "웨이퍼 " + modelData.area_id + " · " + modelData.fine_label + "\n" + (modelData.source_kind==="provider"?"제공자":"자동 후보") + " · " + (modelData.frame_index==null?(modelData.phase==="before"?"열처리 전":modelData.phase==="after"?"열처리 후":"시점 미정"):"프레임 "+modelData.frame_index)
                            highlighted: root.selected && root.selected.item_id===modelData.item_id
                            background: Rectangle { color: parent.highlighted ? "#1d4ed8" : parent.hovered ? "#334155" : "transparent"; radius: 4 }
                            onClicked: root.choose(modelData)
                        }
                        ScrollBar.vertical: ScrollBar {}
                    }
                    RowLayout {
                        Button { text:"이전 100개"; enabled:root.offset>0; onClicked:{root.offset=Math.max(0,root.offset-100);root.reload()} }
                        Button { text:"다음 100개"; enabled:root.offset+100<root.page.total; onClicked:{root.offset+=100;root.reload()} }
                    }
                }
            }
            ColumnLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
                Label { text: root.selected ? "웨이퍼 " + root.selected.area_id + " · " + root.selected.fine_label + " · 원본 좌표 (" + root.selected.x.toFixed(2) + ", " + root.selected.y.toFixed(2) + ")" : "이 조건에 남은 항목이 없습니다"; color:"white"; font.pixelSize:18 }
                RowLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
                    Repeater {
                        model: ["raw", "marked"]
                        ColumnLayout {
                            required property string modelData
                            Layout.fillWidth: true; Layout.fillHeight: true
                            Label { text: modelData==="raw"?"원본 패치":"노란 십자가 중심이 검수할 위치입니다"; color:"#cbd5e1" }
                            Image {
                                objectName: modelData==="raw"?"rawCrop":"markedCrop"
                                Layout.fillWidth: true; Layout.fillHeight: true
                                source: root.selected ? "image://review/" + root.selected.item_id + "/" + modelData : ""
                                asynchronous: true; cache: false; fillMode: Image.PreserveAspectFit; smooth: false
                                onStatusChanged: { if(modelData==="raw") root.rawReady=status===Image.Ready; else root.markedReady=status===Image.Ready }
                            }
                        }
                    }
                }
                Label { text: root.selected ? root.selected.image_asset_id + " · " + root.selected.item_id : ""; color:"#94a3b8"; font.pixelSize:11; wrapMode:Text.Wrap; Layout.fillWidth:true }
                RowLayout {
                    Label { text:"확인한 종류"; color:"white" }
                    ComboBox { id: label; objectName:"reviewLabel"; Layout.preferredWidth:160; model:["종류 선택","BPD","TED","TSD","TED_a","TED_b","TED_c","TED_d","TED_e","TED_f","TSD_a","TSD_b","TSD_c","normal","dust","scratch"] }
                    Label { text:"실제 검수자"; color:"white" }
                    TextField { id: actor; objectName:"actualActor"; placeholderText:"직접 확인한 사람의 이름"; Layout.fillWidth:true }
                }
                CheckBox { id: checked; objectName:"directlyChecked"; enabled:root.rawReady && root.markedReady && !root.cropFailed; text:"이 항목의 원본 패치·좌표·종류를 직접 확인했습니다" }
                TextField { id: notes; objectName:"reviewNotes"; placeholderText:"확인 근거 또는 보류 이유"; Layout.fillWidth:true; maximumLength:2000 }
                RowLayout {
                    Button { objectName:"confirmButton"; text:"기존 라벨 확인"; enabled:root.selected && root.selected.source_kind==="provider"; onClicked:root.saveDecision("confirm") }
                    Button { objectName:"correctButton"; text:"선택 종류로 저장"; enabled:root.selected!==null; onClicked:root.saveDecision("correct") }
                    Button { objectName:"holdButton"; text:"보류"; enabled:root.selected!==null; onClicked:root.saveDecision("hold") }
                    Button { objectName:"excludeButton"; text:"제외"; enabled:root.selected!==null; onClicked:root.saveDecision("exclude") }
                }
                Label { objectName:"reviewMessage"; text:root.message; color:"#fbbf24"; wrapMode:Text.Wrap; Layout.fillWidth:true }
            }
        }
        Label { text:"검수자 표시: 양희승 · 저장 위치: " + reviewSessionPath + "\n원본·기존 학습 자료는 변경하지 않습니다. 자동 후보 수를 결함 개수로 사용하지 마세요."; color:"#94a3b8"; wrapMode:Text.Wrap; Layout.fillWidth:true; font.pixelSize:12 }
    }
}
