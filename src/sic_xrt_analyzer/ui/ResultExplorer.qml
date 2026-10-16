import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "resultExplorer"
    property QtObject theme
    property QtObject uiState
    readonly property var results: uiState.research
    readonly property var navigator: fileBridge.research.regions
    readonly property var area: navigator.state
    readonly property var visibleRows: area.enabled ? area.rows : results.displayRows
    readonly property bool spatialNavigation: area.enabled && uiState.resultViewMode !== "compare"
    readonly property int navigationIndex: spatialNavigation ? area.candidateIndex : results.selectedIndex
    readonly property int navigationTotal: spatialNavigation ? area.rows.length : results.filteredTotal
    readonly property var selected: results.selected || ({})
    readonly property QtObject presentation: uiState.resultPresentation
    readonly property bool optionsExpanded: settings.visible
    property bool batchMode: false
    readonly property bool distribution: uiState.resultViewMode === "distribution"
    readonly property bool shelfVisible: uiState.resultViewMode === "area" || uiState.resultViewMode === "compare"
    signal exportRequested()
    signal overviewRequested()
    signal reviewRequested()
    Layout.minimumWidth: 0
    spacing: height<650 ? 5 : 10
    Component.onCompleted: navigator.activate(true)
    Connections {
        target: fileBridge.research
        function onChanged() { Qt.callLater(function() { if (root.results.selectedIndex >= 0) candidates.positionViewAtIndex(root.visibleRows.findIndex(function(p){return p.id===root.selected.id}), ListView.Contain) }) }
    }
    Text { objectName: "resultOrigin"; visible: results.savedActive; text: "저장된 이력"; color: theme.muted; font.pixelSize: theme.smallSize }
    RowLayout {
        Layout.fillWidth: true
        ColumnLayout {
            Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 2
            Text { text: "결함 후보"; color: root.theme.muted; font.pixelSize: 13 }
            Text { objectName: "resultTotal"; text: root.presentation.count(root.results.total); color: root.theme.text; font.pixelSize: 26; font.weight: Font.DemiBold }
        }
        AppButton { objectName: "resultOverview"; theme: root.theme; text: "전체 분포"; quiet: true; compact: true; onClicked: { root.uiState.resultViewMode="distribution"; root.overviewRequested() } }
        AppButton { objectName:"resultSettings"; theme: root.theme; text: "설정"; compact: true; checked: root.optionsExpanded; onClicked: settings.open() }
    }
    RowLayout {
        Layout.fillWidth: true; spacing: 4
        Repeater {
            model: ["ALL", "BPD", "TED", "TSD"]
            AppButton {
                required property string modelData
                objectName: "resultFilter" + modelData
                theme: root.theme; compact: true; labelSize: 12; leftPadding: 6; rightPadding: 6
                text: modelData === "ALL" ? "전체" : modelData + " " + root.presentation.count(root.results.counts[modelData] || 0)
                checked: root.results.filterKind === modelData
                Layout.fillWidth: true; Layout.minimumWidth: 0
                onClicked: {
                    fileBridge.research.setFilter(modelData, false, "")
                    root.uiState.bpdLayerVisible = modelData === "ALL" || modelData === "BPD"
                    root.uiState.tedLayerVisible = modelData === "ALL" || modelData === "TED"
                    root.uiState.tsdLayerVisible = modelData === "ALL" || modelData === "TSD"
                }
            }
        }
    }
    Text {
        visible: results.limited || results.excluded>0
        text: results.limited ? "일부 영역은 분석이 제한됐습니다 · 설정에서 확인" : "분류 제외 " + results.excluded + "개 · 설정에서 확인"
        color: theme.warning; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true
    }
    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: root.theme.borderSubtle }
    ColumnLayout {
        visible: root.distribution; Layout.fillWidth: true; spacing: 14
        Text { text: "분포부터 살펴보세요"; color: root.theme.text; font.pixelSize: 18; font.weight: Font.DemiBold }
        Text { text: "이미지에서 영역을 선택하면 주변 결함을 함께 검토할 수 있습니다."; color: root.theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 14 }
        Text { text: "표시 후보 "+root.presentation.count(root.results.filteredTotal)+"개 · "+root.area.total+"개 영역"; color: root.theme.text; font.pixelSize: 13; wrapMode:Text.Wrap; Layout.fillWidth:true }
        Text { text: "밝을수록 후보가 많습니다. 색의 밝기는 결함 위험도나 모델의 확신 정도가 아닙니다."; color: root.theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12 }
        AppButton { objectName:"beginAreaReview"; theme:root.theme; primary:true; text:"영역 검토 시작"; enabled:root.area.total>0; onClicked:{root.uiState.resultViewMode="area";root.navigator.activate(true);root.navigator.stepArea(0)} }
        Text { text: root.results.limited ? "후보 한도에 도달하여 일부 후보가 제외됐습니다. 전체 결함 수로 해석하지 마세요." : "검출 후보는 모델의 제안입니다. 원본에서 확인한 뒤 검토 상태를 기록하세요."; color:root.results.limited?root.theme.warning:root.theme.muted; wrapMode:Text.Wrap; Layout.fillWidth:true; font.pixelSize:12 }
    }
    RowLayout {
        visible: root.spatialNavigation && !root.distribution; Layout.fillWidth: true
        AppButton { objectName: "previousReviewArea"; theme: root.theme; text: "‹"; tip: "이전 영역"; compact: true; enabled: root.area.index>0; onClicked: root.navigator.stepArea(-1) }
        ColumnLayout {
            Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 2
            Text { text: "현재 영역 · " + root.area.rows.length + "개 후보"; color: root.theme.text; font.pixelSize: 15; font.weight: Font.DemiBold; Layout.fillWidth:true; Layout.minimumWidth:0; elide:Text.ElideRight }
            Text { text: (root.area.index+1)+" / "+root.area.total+"   ·   "+root.area.label; color: root.theme.muted; font.pixelSize: 11; Layout.fillWidth:true; Layout.minimumWidth:0; elide:Text.ElideRight }
        }
        AppButton { objectName: "nextReviewArea"; theme: root.theme; text: "›"; tip: "다음 영역"; compact: true; enabled: root.area.index+1<root.area.total; onClicked: root.navigator.stepArea(1) }
    }
    RowLayout {
        visible: !root.distribution && !root.shelfVisible; Layout.fillWidth: true
        Text { text: root.area.enabled ? "주변 후보" : "후보 목록"; color: root.theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
        AppButton { theme: root.theme; text: root.batchMode ? "선택 완료" : "여러 개 선택"; quiet: true; compact: true; checked: root.batchMode; onClicked: root.batchMode=!root.batchMode }
        CheckBox { visible: root.batchMode && root.area.enabled; checked: root.area.allChecked; enabled: root.area.rows.length>0; onClicked:root.navigator.checkArea(checked); Accessible.name:"현재 영역 후보 모두 선택" }
    }
    Text { objectName:"emptyCandidateDetail"; visible:!root.distribution && results.filteredTotal>0 && !root.selected.id; text:"아래 썸네일을 선택해 원본에서 확인하세요"; color:theme.muted; font.pixelSize:12; wrapMode:Text.Wrap; Layout.fillWidth:true }
    ListView {
        id: candidates; objectName: "candidateList"
        visible: results.filteredTotal>0 && !root.distribution && !root.shelfVisible
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 100
        clip: true; spacing: 6; model: root.visibleRows
        ScrollBar.vertical: ScrollBar {}
        delegate: ItemDelegate {
            required property var modelData
            objectName: "candidateRow"+modelData.number
            width: candidates.width; height: root.height<650 ? 66 : 86
            background: Rectangle {
                color: root.selected.id===parent.modelData.id ? root.theme.accentPale : parent.hovered ? root.theme.hover : root.theme.surface
                radius: 8; border.width: root.selected.id===parent.modelData.id || parent.activeFocus ? 1 : 0
                border.color: root.theme.accent
            }
            contentItem: RowLayout {
                spacing: 10
                Rectangle { Layout.preferredWidth:3; Layout.fillHeight:true; radius:1; color:root.presentation.colorFor(modelData.type) }
                Image { visible:!!modelData.thumbnail; source:modelData.thumbnail||""; cache:false; smooth:false; Layout.preferredWidth:root.height<650?48:66; Layout.preferredHeight:root.height<650?48:66; fillMode:Image.PreserveAspectFit }
                ColumnLayout {
                    Layout.fillWidth:true; spacing:4
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:modelData.type; color:root.presentation.colorFor(modelData.type); font.pixelSize:15; font.weight:Font.DemiBold }
                        Text { text:"#"+modelData.number; color:root.theme.muted; font.pixelSize:12; Layout.fillWidth:true }
                        Text { text:root.presentation.confidence(modelData.score); color:root.theme.muted; font.pixelSize:12 }
                    }
                    Text { text:modelData.review==="CONFIRMED"?"확인 완료":modelData.review==="HOLD"?"보류":modelData.type==="BPD" ? (modelData.region && modelData.region.length>=3 ? (modelData.regionClipped?"경계 일부 · 상세 확인":"영역 윤곽") : "윤곽 없음 · 상세 확인") : "미검토"; color:root.theme.muted; font.pixelSize:12 }
                }
                CheckBox { visible:root.batchMode; checked:modelData.checked||false; onClicked:root.navigator.check(modelData.id,checked); Accessible.name:"후보 "+modelData.number+" 검토 대상으로 선택" }
            }
            Accessible.name:"후보 "+modelData.number+" "+modelData.type
            Accessible.selected:root.selected.id===modelData.id
            onClicked:fileBridge.research.selectCandidate(modelData.id)
        }
        Text { anchors.centerIn:parent; visible:root.visibleRows.length===0; text:root.area.enabled?"이 영역에는 검출 후보가 없습니다":"표시할 후보가 없습니다"; color:root.theme.muted; font.pixelSize:13 }
    }
    RowLayout {
        Layout.fillWidth:true; visible:results.filteredTotal>0 && !root.distribution
        AppButton { objectName:"previousCandidate"; theme:root.theme; text:"‹ 후보"; compact:true; enabled:root.navigationIndex>0; onClicked:root.spatialNavigation?root.navigator.stepCandidate(-1):fileBridge.research.stepCandidate(-1) }
        Text { objectName:"candidateIndex"; text:root.selected.id?"후보 "+root.presentation.count(root.navigationIndex+1)+" / "+root.presentation.count(root.navigationTotal):"후보 선택 전"; color:root.theme.muted; horizontalAlignment:Text.AlignHCenter; Layout.fillWidth:true; Layout.minimumWidth:0; elide:Text.ElideRight; font.pixelSize:12 }
        AppButton { objectName:"nextCandidate"; theme:root.theme; text:"후보 ›"; compact:true; enabled:root.navigationIndex<root.navigationTotal-1; onClicked:root.spatialNavigation?root.navigator.stepCandidate(1):fileBridge.research.stepCandidate(1) }
    }
    RowLayout {
        visible:!!root.selected.id && !root.distribution; Layout.fillWidth:true
        Image { objectName:"candidateThumbnail"; source:root.results.thumbnailSource; cache:false; smooth:false; Layout.preferredWidth:44; Layout.preferredHeight:44 }
        ColumnLayout {
            Layout.fillWidth:true; spacing:2
            Text { objectName:"selectedCandidateHeader"; text:"#"+root.selected.number+" · "+root.selected.type; color:root.theme.text; font.pixelSize:14; font.weight:Font.DemiBold }
            Text { objectName:"candidateConfidence"; text:"모델 점수 "+root.presentation.confidence(root.selected.score); color:root.theme.muted; font.pixelSize:12 }
        }
        AppButton { objectName:"candidateDetails"; theme:root.theme; text:"상세"; compact:true; onClicked:details.open() }
    }
    RowLayout {
        visible:!root.distribution; Layout.fillWidth:true
        AppButton { theme:root.theme; text:root.area.checked.length ? root.area.checked.length+"개 확인" : "확인"; primary:true; compact:true; Layout.fillWidth:true; Layout.minimumWidth:0; enabled:!!root.selected.id || root.area.checked.length>0; onClicked:root.navigator.mark("CONFIRMED") }
        AppButton { theme:root.theme; text:"보류"; compact:true; enabled:!!root.selected.id || root.area.checked.length>0; onClicked:root.navigator.mark("HOLD") }
        AppButton { objectName:"reportCandidate"; theme:root.theme; text:"신고 대기"; tip:root.area.checked.length ? root.area.checked.length+"개 선택한 후보 신고 작성" : "선택한 후보 신고 작성"; compact:true; enabled:root.results.pixelsAvailable && (!!root.selected.id || root.area.checked.length>0); onClicked:report.open() }
    }
    Text { visible:!root.distribution; text:"모델 점수는 정답 확률이 아닙니다."; color:theme.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.Wrap }
    ProgressBar { visible:!root.distribution && root.area.rows.length>0; Layout.fillWidth:true; from:0; to:Math.max(1,root.area.rows.length); value:root.area.areaReviewed }
    Text { visible:!root.distribution; text:"현재 영역 직접 확인 "+root.area.areaReviewed+" / "+root.area.rows.length; color:theme.muted; font.pixelSize:12 }
    AppButton { theme:root.theme; visible:!root.distribution; text:"다음 미검토 영역"; enabled:root.area.total>0; onClicked:root.navigator.nextUnreviewed() }
    AppButton { theme:root.theme; visible:root.area.checked.length>0; text:"선택 "+root.area.checked.length+"개 해제"; quiet:true; compact:true; onClicked:root.navigator.clearChecked() }
    Item { Layout.fillHeight: true; visible: root.distribution || root.shelfVisible; Layout.minimumHeight: 4 }
    Text { visible:!!root.area.error; text:root.area.error; color:theme.warning; wrapMode:Text.Wrap; Layout.fillWidth:true }
    Text { text:"직접 확인 "+root.area.reviewed+"개 · 열어본 영역 "+root.area.opened; color:theme.muted; font.pixelSize:11 }
    Rectangle { Layout.fillWidth:true; implicitHeight:1; color:root.theme.borderSubtle }
    RowLayout {
        Layout.fillWidth:true
        AppButton { theme:root.theme; text:"신고 대기열 ("+fileBridge.reports.state.pending+")"; quiet:true; compact:true; Layout.fillWidth:true; Layout.minimumWidth:0; onClicked:reportQueue.open() }
        AppButton { objectName:"analysisExportButton"; theme:root.theme; text:"내보내기"; iconName:"export"; compact:true; onClicked:root.exportRequested() }
    }
    SurfaceDialog {
        id:settings; objectName:"resultSettingsDialog"; parent:Overlay.overlay
        title:"검토 설정"; modal:true; width:Math.min(440,parent.width-32)
        x:(parent.width-width)/2; y:(parent.height-height)/2; standardButtons:Dialog.Close
    ColumnLayout {
        width:parent.width; spacing:10
        Text { visible: results.limited; text: "후보 생성 한도에 도달했습니다. 작은 ROI로 나누어 다시 분석하세요."; color: root.theme.warning; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12 }
        Text { visible: results.excluded>0; text: "분류 제외 " + results.excluded + "개 · " + results.exclusionSummary; color: root.theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12 }
        RowLayout {
            Layout.fillWidth: true
            AppComboBox { theme: root.theme; Layout.fillWidth: true; Layout.minimumWidth: 0; currentIndex:root.area.enabled?["AREA","PRIORITY","SAMPLE","SCAN"].indexOf(root.area.mode):4; model:["영역별 검토","우선 검토","분산 표본 순서","원본 전체 훑기","개별 후보"]; onActivated:function(index){root.navigator.activate(index!==4);if(index!==4)root.navigator.setMode(["AREA","PRIORITY","SAMPLE","SCAN"][index])} }
            AppComboBox { theme: root.theme; model:["256 px","512 px","1024 px"]; currentIndex:[256,512,1024].indexOf(root.area.edge); onActivated:function(index){root.navigator.setEdge([256,512,1024][index])} }
        }
        Text { text: "모델 점수는 정답 확률이 아닙니다. BPD 윤곽은 원본 대비에 따른 영역 제안입니다."; color: root.theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12 }
    RowLayout {
        Layout.fillWidth:true
        AppButton { theme:root.theme; text:"누락 결함 신고"; compact:true; enabled:root.uiState.hasRoi; onClicked:{report.missingDefect=true;report.open()} }
        AppButton { theme:root.theme; text:"‹ 페이지"; compact:true; visible:!root.area.enabled && results.pages>1; enabled:results.page>0; onClicked:fileBridge.research.setResultPage(results.page-1) }
        AppButton { theme:root.theme; text:"페이지 ›"; compact:true; visible:!root.area.enabled && results.pages>1; enabled:results.page+1<results.pages; onClicked:fileBridge.research.setResultPage(results.page+1) }
    }
    }
    }
    ReportQueueDialog { id:reportQueue; theme:root.theme }
    ReportDialog { id:report; theme:root.theme; uiState:root.uiState }
    SurfaceDialog {
        id:details; objectName:"candidateDetailDialog"; parent:Overlay.overlay
        title:"후보 상세"; modal:true; width:Math.min(440,parent.width-32)
        x:(parent.width-width)/2; y:(parent.height-height)/2; standardButtons:Dialog.Close
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"#"+root.selected.number+" · "+root.selected.type; color:root.theme.text; font.pixelSize:22; font.weight:Font.DemiBold }
            Image { source:root.results.thumbnailSource; cache:false; smooth:false; Layout.preferredWidth:160; Layout.preferredHeight:160; Layout.alignment:Qt.AlignHCenter }
            Repeater {
                model:["BPD","TED","TSD"]
                Text { required property int index; required property string modelData; objectName:"rawScore"+modelData; text:modelData+"  "+root.presentation.confidence(root.selected.scores?root.selected.scores[index]:undefined)+"   /   "+root.presentation.raw(root.selected.scores?root.selected.scores[index]:undefined); color:root.presentation.colorFor(modelData); font.pixelSize:14 }
            }
            Text { text:"모델 점수는 정답 확률이 아닙니다."; color:root.theme.muted; font.pixelSize:12 }
            Text { text:"X "+(root.selected.x||0).toFixed(2)+"    Y "+(root.selected.y||0).toFixed(2)+" px"; color:root.theme.muted; font.pixelSize:14 }
            Text { visible:root.selected.type==="BPD"; text:root.selected.region && root.selected.region.length>=3 ? (root.selected.regionClipped?"읽기 범위 경계에 닿은 영역입니다. 전체 윤곽인지 원본에서 확인하세요.":"원본 대비에 따른 영역 제안 · 정답 윤곽 아님") : "이 결과에는 영역 윤곽이 없습니다. 원본을 다시 분석해 확인하세요."; color:root.theme.muted; font.pixelSize:12; wrapMode:Text.Wrap; Layout.fillWidth:true }
            AppButton { objectName:"copyCandidate"; theme:root.theme; text:"좌표 복사"; onClicked:fileBridge.copyText("X="+root.selected.x+" Y="+root.selected.y+" "+root.selected.type) }
        }
    }
}
