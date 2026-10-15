import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SurfaceDialog {
    id: root
    objectName: "analysisDialog"
    property QtObject theme
    property QtObject uiState
    property var actions
    property bool detailsExpanded: false
    property var hostWindow
    parent: Overlay.overlay
    title: "이미지 분석"
    modal: true
    width: Math.min(500, parent.width - 40)
    x: (parent.width - width) / 2
    y: (parent.height - height) / 2
    standardButtons: Dialog.NoButton
    ColumnLayout {
        width: parent.width
        spacing: root.theme.spacingLg
        RowLayout {
            Layout.fillWidth: true
            spacing: root.theme.spacingMd
            AppIcon { name: "image"; ink: root.theme.accent; Layout.preferredWidth: 24; Layout.preferredHeight: 24 }
            Text {
                text: root.uiState.fileName
                color: root.theme.text
                font.pixelSize: root.theme.bodySize
                font.weight: Font.DemiBold
                elide: Text.ElideMiddle
                Layout.fillWidth: true
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: root.theme.spacingSm
            AppButton { theme: root.theme; text: "전체 이미지"; checked: root.uiState.analysisScope === "FULL_IMAGE"; Layout.fillWidth: true; onClicked: root.uiState.analysisScope = "FULL_IMAGE" }
            AppButton { theme: root.theme; text: "선택 ROI"; checked: root.uiState.analysisScope === "ROI"; enabled: root.uiState.hasRoi; Layout.fillWidth: true; onClicked: root.uiState.analysisScope = "ROI" }
        }
        Text {
            text: root.uiState.analysisFlow.regionLabel
            color: root.theme.muted
            font.pixelSize: root.theme.smallSize
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
        RowLayout {
            Layout.fillWidth: true
            AppButton { objectName: "analysisSpecifyArea"; theme: root.theme; action: root.actions.roi; text: "ROI 지정"; iconName: "roi"; quiet: true; compact: true; onClicked: root.close() }
            Item { Layout.fillWidth: true }
            AppButton { objectName: "analysisInputInfo"; theme: root.theme; text: root.detailsExpanded ? "상세 접기 ▴" : "상세 정보 ▾"; quiet: true; compact: true; onClicked: root.detailsExpanded=!root.detailsExpanded }
        }
        Text {visible:root.detailsExpanded;text:root.uiState.inputPreflight.currentInputDetail+"\n표시 밝기·배율과 별개로 원본 픽셀을 사용합니다.";color:root.theme.muted;wrapMode:Text.Wrap;Layout.fillWidth:true}
        Text { visible: !root.uiState.canAnalyze; text: root.uiState.analysisReason; color: root.theme.warning; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Rectangle { Layout.fillWidth: true; height: 1; color: root.theme.borderSubtle }
        RowLayout {
            Layout.fillWidth: true
            spacing: root.theme.spacingSm
            AppButton { theme: root.theme; text: "결과 보기"; quiet: true; visible: root.uiState.hasResult; onClicked: { root.close(); root.hostWindow.openContext("result") } }
            Item { Layout.fillWidth: true }
            AppButton { theme: root.theme; text: "취소"; onClicked: root.close() }
            AppButton { objectName: "confirmAnalysis"; theme: root.theme; text: root.uiState.hasResult ? "다시 분석" : "분석 시작"; iconName: "run"; primary: true; enabled: root.uiState.canAnalyze; onClicked: { root.close(); root.actions.run.trigger() } }
        }
    }
    Connections { target: root.uiState; function onHasLoadedImageChanged() { if (!root.uiState.hasLoadedImage) root.close() } }
}
