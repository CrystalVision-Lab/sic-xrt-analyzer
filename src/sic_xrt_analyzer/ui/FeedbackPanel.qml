import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ScrollView {
    id: root
    objectName: "feedbackPanel"
    property QtObject theme
    property QtObject uiState
    readonly property var review: uiState.feedback
    readonly property var selected: review.selected || ({})
    readonly property var target: selected.target || ({})
    readonly property bool configured: review.ready && !!review.wafer
    readonly property bool canRecord: configured && !!selected.id
    clip: true; contentWidth: availableWidth
    FolderDialog { id: exportDialog; title: "검수 기록 내보내기"; onAccepted: fileBridge.feedback.exportFeedback(selectedFolder.toString()) }
    FileDialog { id: importDialog; title: "같은 원본의 검수 기록 불러오기"; nameFilters: ["검수 기록 (*.json)"]; onAccepted: fileBridge.feedback.importFeedback(selectedFile.toString()) }
    onSelectedChanged: noteField.text = selected.note || ""
    ColumnLayout {
        width: root.availableWidth; spacing: 8
        Text { text: "분석 결과 검수"; color: theme.text; font.pixelSize: 16; font.bold: true }
        Text { Layout.fillWidth: true; text: "확실한 항목만 확인하세요. 종류를 몰라도 결함 유무·위치를 기록할 수 있습니다. 검수는 자동 저장되며 모델은 별도로 학습합니다."; color: theme.muted; wrapMode: Text.Wrap; font.pixelSize: 11 }
        RowLayout {
            Layout.fillWidth: true
            TextField { id: reviewerField; objectName: "feedbackReviewer"; Layout.fillWidth: true; text: review.reviewer || ""; placeholderText: "검수자명"; color: theme.text }
            ComboBox { id: waferField; objectName: "feedbackWafer"; model: ["웨이퍼 선택", "1", "2", "3", "4", "5", "6", "7", "8", "9"]; currentIndex: review.wafer ? Number(review.wafer) : 0; enabled: !review.eventsCount }
            AppButton { objectName: "configureFeedback"; theme: root.theme; text: "설정"; enabled: review.ready; onClicked: fileBridge.feedback.configure(reviewerField.text, waferField.currentIndex ? waferField.currentText : "") }
        }
        Text { Layout.fillWidth: true; visible: review.wafer === "8"; text: "웨이퍼 8은 최종 시험용입니다. 이 검수는 학습 자료로 변환할 수 없습니다."; color: theme.warning; wrapMode: Text.Wrap; font.pixelSize: 11 }
        Text { Layout.fillWidth: true; visible: !review.ready; text: review.loading ? "원본과 검수 이력을 확인하는 중…" : "원본 TIFF/JPG를 여세요."; color: theme.muted }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: previewRow.implicitHeight + 16
            color: theme.viewer; border.color: theme.border; radius: 4
            RowLayout {
                id: previewRow; anchors.fill: parent; anchors.margins: 8; spacing: 12
                Rectangle {
                    Layout.preferredWidth: 144; Layout.preferredHeight: 144; color: theme.surface; clip: true
                    Image { objectName: "feedbackPreview"; anchors.fill: parent; source: review.preview || ""; cache: false; smooth: false }
                    Rectangle { visible: !!review.preview; width: 23; height: 2; color: "#fff04a"; x: parent.width * review.previewCenter[0] - width/2; y: parent.height * review.previewCenter[1] - 1 }
                    Rectangle { visible: !!review.preview; width: 2; height: 23; color: "#fff04a"; x: parent.width * review.previewCenter[0] - 1; y: parent.height * review.previewCenter[1] - height/2 }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { Layout.fillWidth: true; wrapMode: Text.Wrap; text: selected.id ? selected.status : "후보를 선택하세요"; color: theme.text; font.bold: true; font.pixelSize: 12 }
                    Text { Layout.fillWidth: true; text: selected.id ? "원래 예측: " + (selected.original.predicted_type || "수동 추가") : ""; color: theme.muted; font.pixelSize: 11 }
                    Text { Layout.fillWidth: true; wrapMode: Text.Wrap; text: selected.id ? "X " + selected.x.toFixed(2) + "\nY " + selected.y.toFixed(2) + " px" : ""; color: theme.text; font.pixelSize: 11 }
                    Text { Layout.fillWidth: true; wrapMode: Text.Wrap; text: target.location_confirmed ? "위치 확인됨" : "위치 미확인"; color: theme.muted; font.pixelSize: 11 }
                    AppButton { theme: root.theme; text: "위치로 줌"; enabled: !!selected.id; onClicked: fileBridge.feedback.selectRecord(selected.id) }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            AppButton { objectName: "feedbackConfirm"; theme: root.theme; text: "O · 결함 있음"; Layout.fillWidth: true; enabled: root.canRecord; onClicked: fileBridge.feedback.record("confirm", "", noteField.text, "") }
            AppButton { objectName: "feedbackBackground"; theme: root.theme; text: "X · 결함 아님"; Layout.fillWidth: true; enabled: root.canRecord; onClicked: fileBridge.feedback.record("background", "", noteField.text, "") }
            AppButton { objectName: "feedbackDefer"; theme: root.theme; text: "보류"; enabled: root.canRecord; onClicked: fileBridge.feedback.record("defer", "", noteField.text, "") }
        }
        RowLayout {
            Layout.fillWidth: true
            ComboBox { id: typeField; objectName: "feedbackType"; model: ["종류 미확정", "BPD", "TED", "TSD"]; Layout.fillWidth: true; currentIndex: Math.max(0, model.indexOf(root.target.label || "종류 미확정")) }
            AppButton { objectName: "feedbackSetType"; theme: root.theme; text: "종류 저장"; enabled: root.canRecord; onClicked: fileBridge.feedback.record(typeField.currentIndex ? "type" : "type_unknown", typeField.currentIndex ? typeField.currentText : "", noteField.text, "") }
        }
        RowLayout {
            Layout.fillWidth: true
            AppButton { objectName: "feedbackConfirmLocation"; theme: root.theme; text: "이 위치 맞음"; Layout.fillWidth: true; enabled: root.canRecord; onClicked: fileBridge.feedback.confirmLocation(noteField.text) }
            AppButton { objectName: "feedbackMove"; theme: root.theme; text: "위치 수정"; Layout.fillWidth: true; enabled: root.canRecord; checked: review.mode === "location"; onClicked: fileBridge.feedback.setMode(review.mode === "location" ? "" : "location") }
            AppButton { objectName: "feedbackAdd"; theme: root.theme; text: "누락 추가"; Layout.fillWidth: true; enabled: root.configured; checked: review.mode === "add"; onClicked: fileBridge.feedback.setMode(review.mode === "add" ? "" : "add") }
        }
        Text { Layout.fillWidth: true; visible: !!review.mode; text: review.mode === "add" ? "원본 영상에서 빠진 결함의 중심을 누르세요. Esc: 취소" : "원본 영상에서 올바른 중심을 누르세요. Esc: 취소"; color: theme.accent; wrapMode: Text.Wrap; font.pixelSize: 11 }
        RowLayout {
            Layout.fillWidth: true
            ComboBox { id: duplicateField; Layout.fillWidth: true; model: review.rows || []; textRole: "id"; displayText: currentIndex >= 0 && model[currentIndex] ? "중복 대상 · " + model[currentIndex].type + " (" + model[currentIndex].x.toFixed(1) + ", " + model[currentIndex].y.toFixed(1) + ")" : "중복 대상 선택" }
            AppButton { objectName: "feedbackDuplicate"; theme: root.theme; text: "중복"; enabled: root.canRecord && duplicateField.currentIndex >= 0; onClicked: fileBridge.feedback.record("duplicate", "", noteField.text, duplicateField.model[duplicateField.currentIndex].id) }
            AppButton { objectName: "feedbackUndo"; theme: root.theme; text: "되돌리기"; enabled: root.canRecord && !!selected.revision; onClicked: fileBridge.feedback.record("undo", "", noteField.text, "") }
        }
        TextField { id: noteField; objectName: "feedbackNote"; Layout.fillWidth: true; placeholderText: "수정 이유 / 불확실한 점"; color: theme.text; maximumLength: 2000 }
        RowLayout {
            Layout.fillWidth: true
            Repeater {
                model: [{value:"ALL",label:"전체"},{value:"BPD",label:"BPD"},{value:"TED",label:"TED"},{value:"TSD",label:"TSD"},{value:"UNKNOWN",label:"종류 미확정"}]
                AppButton { required property var modelData; theme: root.theme; Layout.fillWidth: true; text: modelData.label; checked: review.typeFilter === modelData.value; onClicked: fileBridge.feedback.setTypeFilter(modelData.value) }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Repeater {
                model: [{value:"ALL",label:"전체"},{value:"unreviewed",label:"미검수"},{value:"reviewed",label:"기록 있음"},{value:"deferred",label:"보류"}]
                AppButton { required property var modelData; theme: root.theme; Layout.fillWidth: true; text: modelData.label; checked: review.filter === modelData.value; onClicked: fileBridge.feedback.setReviewFilter(modelData.value) }
            }
        }
        Text { text: "기록 " + (review.reviewedCount || 0) + " / " + (review.total || 0) + " · 표시 " + (review.rows || []).length; color: theme.muted; font.pixelSize: 11 }
        RowLayout {
            Layout.fillWidth: true
            AppButton { objectName: "feedbackPrevious"; theme: root.theme; text: "← 이전"; Layout.fillWidth: true; enabled: !!review.rows.length; onClicked: fileBridge.feedback.stepRecord(-1) }
            AppButton { objectName: "feedbackNext"; theme: root.theme; text: "다음 →"; Layout.fillWidth: true; enabled: !!review.rows.length; onClicked: fileBridge.feedback.stepRecord(1) }
        }
        ListView {
            id: records; objectName: "feedbackRecords"; Layout.fillWidth: true; Layout.preferredHeight: 210; clip: true
            model: review.rows || []; spacing: 3; ScrollBar.vertical: ScrollBar {}
            delegate: ItemDelegate {
                required property var modelData; required property int index
                width: records.width; height: 45
                background: Rectangle { color: selected.id === modelData.id ? theme.accentPale : theme.surface; radius: 3 }
                contentItem: Column {
                    Text { text: (index+1) + " · " + modelData.status; color: theme.text; font.pixelSize: 12 }
                    Text { text: modelData.x.toFixed(2) + ", " + modelData.y.toFixed(2) + " · " + (modelData.labelConfirmed ? "확인 종류 " : "예측/미확정 ") + modelData.type; color: theme.muted; font.pixelSize: 10 }
                }
                onClicked: fileBridge.feedback.selectRecord(modelData.id)
            }
        }
        RowLayout {
            Layout.fillWidth: true
            AppButton { objectName: "exportFeedback"; theme: root.theme; text: "검수 자료 내보내기"; Layout.fillWidth: true; enabled: !!review.eventsCount; onClicked: exportDialog.open() }
            AppButton { theme: root.theme; text: "불러오기"; enabled: review.ready; onClicked: importDialog.open() }
        }
        Text { Layout.fillWidth: true; wrapMode: Text.Wrap; text: review.error || (review.exportPath ? "내보낸 파일: " + review.exportPath : "자동 저장: " + (review.sessionPath || "준비 중")); color: review.error ? theme.error : theme.muted; font.pixelSize: 10 }
        Text { Layout.fillWidth: true; text: "종류와 위치 확인은 별도입니다. 표시되지 않은 배경은 학습 정답으로 만들지 않습니다."; color: theme.muted; wrapMode: Text.Wrap; font.pixelSize: 10 }
    }
}
