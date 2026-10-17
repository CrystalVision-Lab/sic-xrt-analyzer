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
    visible: uiState.workspaceIndex === 0
    color: theme.toolbar
    implicitHeight: theme.commandBarHeight
    RowLayout {
        objectName: "primaryToolbarRow"
        anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
        spacing: theme.spacingXs
        FileToolGroup { theme: root.theme; actions: root.actions }
        Rectangle { width: 1; height: 22; color: theme.borderSubtle; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        ViewerToolGroup { theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow }
        Rectangle { width: 1; height: 22; color: theme.borderSubtle; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        RoiToolGroup { visible: !root.uiState.tiffMode; theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow }
        MeasurementToolGroup { visible: !root.uiState.tiffMode; theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow }
        Rectangle { width: 1; height: 22; color: theme.borderSubtle; Layout.leftMargin: 6; Layout.rightMargin: 6 }
        AdvancedToolGroup { visible: !root.uiState.tiffMode; theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow }
        StackViewerToolGroup { visible: root.uiState.tiffMode; theme: root.theme; uiState: root.uiState; hostWindow: root.hostWindow; compact: root.width < 1250 }
        TiffWorkbenchControls { visible: root.uiState.tiffMode; theme: root.theme; uiState: root.uiState; actions: root.actions; hostWindow: root.hostWindow; compact: root.width < 1250 }
        Item { Layout.fillWidth: true }
        LayerTools {theme:root.theme;uiState:root.uiState;hostWindow:root.hostWindow}
        AppButton {objectName:"openStackRoi3d";theme:root.theme;visible:root.uiState.stackFeaturesVisible;text:root.uiState.activeTool==="StackTrack"?"추적할 결함을 클릭":"스택 추적";tip:"클릭한 결함 주변 256×256 영역에서 페이지 간 같은 결함을 추적합니다";enabled:root.uiState.canNavigateImage;onClicked:{root.uiState.roiEditMode=false;root.uiState.activeTool="StackTrack";root.hostWindow.viewer.focusView()}}
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
