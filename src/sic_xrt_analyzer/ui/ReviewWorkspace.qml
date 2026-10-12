import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    objectName: "reviewWorkspace"
    property QtObject theme
    property QtObject uiState
    readonly property var review: uiState.projectReview
    clip: true; contentWidth: availableWidth
    ColumnLayout {
        width: root.availableWidth; spacing: root.theme.spacingSm
        Text { text: review.editing ? "결함 영역 편집" : "프로젝트 검수"; color: theme.text; font.pixelSize: theme.titleSize }
        Text { objectName: "reviewTargetLabel"; text: review.manual ? "수동 누락 결함 · 모델 점수 없음" : (review.selected.manual ? "수동 결함" : "모델 원본: " + (review.selected.label || "선택 전")) + " · " + (review.selected.badge || ""); color: theme.text; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Text { text: "개인 검수 · 학습 정답 승인 아님"; color: theme.muted; font.pixelSize: theme.captionSize }
        RowLayout {
            Layout.fillWidth: true
            TextField { id: reviewer; objectName: "projectReviewerInput"; Layout.fillWidth: true; text: review.reviewer; placeholderText: "로컬 연구원 ID"; maximumLength: 120 }
            AppButton { objectName: "projectReviewerApply"; theme: root.theme; text: "설정"; enabled: !review.pending; onClicked: fileBridge.reviews.setReviewer(reviewer.text) }
        }
        Text { visible: !review.ready; text: "원본 JPG·Run 연결과 SHA 검증이 필요합니다. 이력은 확인할 수 있습니다."; color: theme.warning; wrapMode: Text.Wrap; Layout.fillWidth: true }
        AppButton { objectName: "reviewVerifySource"; theme: root.theme; text: "현재 원본 SHA 검증"; visible: !review.ready && !!review.sourceId; enabled: !uiState.project.busy; onClicked: fileBridge.projects.verifySource(review.sourceId) }
        Image { objectName: "projectReviewCrop"; Layout.preferredWidth: 112; Layout.preferredHeight: 112; fillMode: Image.PreserveAspectFit; smooth: false; cache: false; source: review.ready ? (review.selected.type === "OBSERVATION" ? uiState.research.thumbnailSource : review.crop || "") : "" }
        Text { objectName: "projectReviewModelScore"; visible: review.selected.type === "OBSERVATION"; text: "모델 점수 " + uiState.resultPresentation.confidence(review.selected.score) + " · 원점수 " + JSON.stringify(review.selected.scores || []); color: theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Text { text: "결함 여부"; color: theme.text }
        RowLayout {
            Layout.fillWidth: true
            Repeater {
                model: [{value:"PRESENT",label:"있음"},{value:"ABSENT",label:"없음"},{value:"UNCERTAIN",label:"판단 어려움"}]
                AppButton { required property var modelData; objectName: "reviewExistence"+modelData.value; theme: root.theme; text: modelData.label; checked: review.existence===modelData.value; enabled: review.ready; Layout.fillWidth: true; onClicked: fileBridge.reviews.decisions(modelData.value, modelData.value === "ABSENT" ? "UNKNOWN" : review.classification, review.geometryDecision, review.comment) }
            }
        }
        Text { text: "연구원 종류 판정"; color: theme.text }
        RowLayout {
            Layout.fillWidth: true
            Repeater {
                model: ["BPD","TED","TSD","UNKNOWN"]
                AppButton { required property string modelData; objectName: "reviewClass"+modelData; theme: root.theme; text: modelData==="UNKNOWN" ? "미확정" : modelData; checked: review.classification===modelData; enabled: review.ready && review.existence!=="ABSENT"; Layout.fillWidth: true; onClicked: fileBridge.reviews.decisions(review.existence,modelData,review.geometryDecision,review.comment) }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            AppComboBox { objectName: "reviewGeometryDecision"; theme: root.theme; Layout.fillWidth: true; model:["영역 미검수","영역 확인","영역 판단 어려움","영역 보정 기록"]; currentIndex: ["NOT_REVIEWED","ACCEPTED","UNCERTAIN","CORRECTED"].indexOf(review.geometryDecision); enabled: review.ready && !review.editing; onActivated: fileBridge.reviews.decisions(review.existence,review.classification,["NOT_REVIEWED","ACCEPTED","UNCERTAIN","CORRECTED"][currentIndex],review.comment) }
            AppButton { objectName: "reviewEditGeometry"; theme: root.theme; text: "영역 수정"; visible: !review.editing; enabled: review.ready && !!review.targetId; onClicked: { uiState.roiEditMode=false; uiState.feedbackVisible=false; fileBridge.reviews.edit() } }
        }
        ColumnLayout {
            visible: review.editing; Layout.fillWidth: true
            Text { text: (review.draft.kind || "") + " · 원본 px · Ctrl+Z 되돌리기"; color: theme.accent; Layout.fillWidth: true; wrapMode: Text.Wrap }
            RowLayout {
                Layout.fillWidth: true
                AppButton { objectName: "reviewMoveTool"; theme: root.theme; text: "점 이동"; checked: review.tool==="move"; onClicked: fileBridge.reviews.setTool("move") }
                AppButton { objectName: "reviewAddTool"; theme: root.theme; text: "점 추가"; checked: review.tool==="add"; onClicked: fileBridge.reviews.setTool("add") }
                AppButton { objectName: "reviewPanTool"; theme: root.theme; text: "이동"; checked: review.tool==="pan"; onClicked: fileBridge.reviews.setTool("pan") }
            }
            RowLayout {
                Layout.fillWidth: true
                AppButton { objectName: "reviewDeleteVertex"; theme: root.theme; text: "선택점 삭제"; enabled: !!review.vertex; onClicked: fileBridge.reviews.deleteVertex() }
                AppButton { objectName: "reviewUndo"; theme: root.theme; text: "Undo"; onClicked: fileBridge.reviews.undo() }
                AppButton { objectName: "reviewRestore"; theme: root.theme; text: "초안 복원"; onClicked: fileBridge.reviews.restore() }
            }
            Text { text: review.draft.kind==="BRANCHED_GRAPH" ? "점 추가: 선택 Node에서 새 Edge. 이동: Node 또는 Edge 제어점 선택." : "점 추가: 선택점 다음에 삽입. 이동: 꼭짓점을 드래그. 완성 후 검수 기록."; color: theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
            ColumnLayout {
                visible: review.draft.kind==="BRANCHED_GRAPH"; Layout.fillWidth: true
                AppComboBox { id: nodeA; objectName: "reviewGraphNodeA"; theme: root.theme; model: review.draft.nodes || []; textRole: "node_id"; Layout.fillWidth: true }
                AppComboBox { id: nodeB; objectName: "reviewGraphNodeB"; theme: root.theme; model: review.draft.nodes || []; textRole: "node_id"; Layout.fillWidth: true }
                AppButton { objectName: "reviewGraphAddEdge"; theme: root.theme; text: "선택 Node 간 Edge 추가"; enabled: nodeA.currentIndex>=0 && nodeB.currentIndex>=0 && nodeA.currentIndex!==nodeB.currentIndex; onClicked: fileBridge.reviews.edge(review.draft.nodes[nodeA.currentIndex].node_id,review.draft.nodes[nodeB.currentIndex].node_id,false) }
                AppComboBox { id: edges; objectName: "reviewGraphEdge"; theme: root.theme; model: review.draft.edges || []; textRole: "edge_id"; Layout.fillWidth: true }
                RowLayout {
                    AppButton { objectName: "reviewGraphPath"; theme: root.theme; text: "Edge 경로 점 추가"; enabled: edges.currentIndex>=0; onClicked: fileBridge.reviews.selectEdge(review.draft.edges[edges.currentIndex].edge_id) }
                    AppButton { objectName: "reviewGraphDeleteEdge"; theme: root.theme; text: "Edge 삭제"; enabled: edges.currentIndex>=0; onClicked: fileBridge.reviews.edge(review.draft.edges[edges.currentIndex].edge_id,"",true) }
                }
            }
        }
        TextArea { id: note; objectName: "reviewComment"; Layout.fillWidth: true; Layout.preferredHeight: 64; placeholderText: "검수 메모"; text: review.comment; wrapMode: TextEdit.Wrap; onTextChanged: if (activeFocus && text !== review.comment) fileBridge.reviews.decisions(review.existence,review.classification,review.geometryDecision,text) }
        Text { objectName: "reviewHumanDecision"; text: "연구원: " + review.existence + " / " + review.classification + " / " + review.geometryDecision; color: theme.text; wrapMode: Text.Wrap; Layout.fillWidth: true }
        RowLayout {
            Layout.fillWidth: true
            AppButton { objectName: "reviewCommit"; theme: root.theme; text: "검수 기록"; enabled: review.ready && !!review.reviewer && review.pending; onClicked: fileBridge.reviews.commit(false) }
            AppButton { objectName: "reviewCommitNext"; theme: root.theme; text: "기록 → 다음"; enabled: review.ready && !!review.reviewer && review.pending; onClicked: fileBridge.reviews.commit(true) }
            AppButton { objectName: "reviewCancel"; theme: root.theme; text: "취소·탐색"; onClicked: fileBridge.reviews.cancel() }
        }
        AppButton { objectName: "reviewSaveProject"; theme: root.theme; text: uiState.project.dirty ? "프로젝트 디스크 저장 · 미저장" : "프로젝트 저장됨"; enabled: uiState.project.dirty && !!uiState.project.path && !uiState.project.busy && !review.pending; Layout.fillWidth: true; onClicked: fileBridge.projects.save("", "") }
        AppButton { objectName: "reviewSaveDiskNext"; theme: root.theme; text: "디스크 저장 → 다음"; enabled: review.ready && !!review.reviewer && !!uiState.project.path && !uiState.project.busy; Layout.fillWidth: true; onClicked: fileBridge.reviews.saveAndNext() }
        Text { objectName: "reviewError"; text: review.error || uiState.project.error || review.message; color: review.error || uiState.project.error ? theme.warning : theme.muted; visible: text.length>0; wrapMode: Text.Wrap; Layout.fillWidth: true }
        AppComboBox { objectName: "reviewCompare"; theme: root.theme; model:["원본 + 보정 비교","원본만","보정만"]; currentIndex:["BOTH","ORIGINAL","CORRECTED"].indexOf(review.compare); onActivated: fileBridge.reviews.setCompare(["BOTH","ORIGINAL","CORRECTED"][currentIndex]); Layout.fillWidth: true }
        Text { text: "원본: 청색 점선 ◇ / 보정: 황색 실선 ○ / 초안: 분홍 실선 □"; color: theme.muted; font.pixelSize: theme.captionSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Text { text: "검수 이력 · " + review.history.length + "개"; color: theme.text }
        Repeater {
            model: review.history
            Text { required property var modelData; objectName:"reviewHistory"+modelData.revision+modelData.reviewer_id; text: modelData.reviewer_id + " · r" + modelData.revision + " · " + modelData.review_status + "
" + modelData.existence + " / " + modelData.class_decision + " / " + modelData.geometry_decision + "
" + modelData.created_at + "
" + modelData.comment + "
부모 " + JSON.stringify(modelData.parent_review_ids); color: theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: theme.captionSize }
        }
        Text { text: "Legacy Feedback " + review.legacyEvents + "개 · 별도 출처, 자동 이전 없음"; color: theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: theme.captionSize }
        AppComboBox { objectName: "reviewStatusFilter"; theme: root.theme; model:["전체","미검수","완료","수정","결함 아님","보류","충돌"]; currentIndex:["ALL","UNREVIEWED","COMPLETE","CORRECTED","ABSENT","UNCERTAIN","CONFLICT"].indexOf(review.filter); onActivated: fileBridge.reviews.setFilter(["ALL","UNREVIEWED","COMPLETE","CORRECTED","ABSENT","UNCERTAIN","CONFLICT"][currentIndex]); Layout.fillWidth: true }
        RowLayout {
            AppButton { objectName: "reviewPrevious"; theme: root.theme; text: "← 이전"; enabled: !review.pending; onClicked: fileBridge.reviews.step(-1) }
            Text { text: review.total + "개"; color: theme.text }
            AppButton { objectName: "reviewNext"; theme: root.theme; text: "다음 →"; enabled: !review.pending; onClicked: fileBridge.reviews.step(1) }
        }
        Repeater {
            model: review.rows
            AppButton { required property var modelData; objectName: "reviewRow"+modelData.id; theme: root.theme; quiet: true; text: (modelData.manual ? "수동" : "모델 " + modelData.label) + " #" + modelData.number + " · " + modelData.badge; enabled: !review.pending; Layout.fillWidth: true; onClicked: fileBridge.reviews.select(modelData.type,modelData.id) }
        }
        Text { visible: review.total>100; text:"앞 100개 표시 · 다음/이전으로 계속 탐색"; color:theme.muted }
    }
}
