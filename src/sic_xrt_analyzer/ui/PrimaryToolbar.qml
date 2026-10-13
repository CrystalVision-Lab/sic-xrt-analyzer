import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Rectangle {
    id: root
    property QtObject theme
    property QtObject uiState
    property var actions
    property var hostWindow
    objectName: "primaryToolbar"
    color: theme.toolbar
    implicitHeight: 40
    RowLayout {
        objectName: "primaryToolbarRow"
        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
        spacing: theme.spacingXs
        FileToolGroup { theme: root.theme; actions: root.actions }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        ViewerToolGroup { theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        RoiToolGroup { visible: !root.uiState.tiffMode; theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow }
        MeasurementToolGroup { visible: !root.uiState.tiffMode; theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow }
        Rectangle { width: 1; height: 22; color: theme.border; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        AdvancedToolGroup { visible: !root.uiState.tiffMode; theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow }
        StackViewerToolGroup { visible: root.uiState.tiffMode; theme: root.theme; uiState: root.uiState; hostWindow: root.hostWindow; compact: root.width < 1250 }
        TiffWorkbenchControls { visible: root.uiState.tiffMode; theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow; compact: root.width < 1250 }
        Item { Layout.fillWidth: true }
        LayerTools {theme:root.theme;uiState:root.uiState;hostWindow:root.hostWindow}
        AppButton {objectName:"openStackRoi3d";theme:root.theme;visible:root.uiState.stackFeaturesVisible&&(root.uiState.hasRoi||!!root.uiState.roiFlow.selected);text:"3D 보기";enabled:root.uiState.hasRoi||!!root.uiState.roiFlow.selected;onClicked:root.hostWindow.openStackRoi()}
        AppButton {objectName:"showCachedResult";theme:root.theme;visible:root.uiState.hasResult;text:"결과 보기";onClicked:root.hostWindow.openContext("result")}
        ContextTools { theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow }
        AppButton {
            objectName: "imagePrepareAnalysis"; visible: root.uiState.analysisEligible; theme: root.theme; action: root.actions.prepareAnalysis
            text: "분석하기"; primary: true; implicitHeight: theme.toolbarButtonHeight
            Accessible.name: text; tip: "분석 범위와 모델을 확인하고 실행하세요."
        }
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border }
}
