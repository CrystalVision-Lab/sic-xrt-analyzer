import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    // Preserve the public object name for existing UI automation.
    objectName: "inspectorPanel"
    property QtObject theme
    property QtObject uiState
    property var actions
    property alias tabIndex: context.tabIndex
    readonly property string activeContext: context.activeContext
    readonly property string requestedContext: context.requestedContext
    readonly property string detailContext: context.detailContext
    signal importRequested()
    signal boundsRequested()
    signal saveRequested()
    signal overviewRequested()
    signal modelRequested()
    signal coordinatesRequested()
    signal resultExportRequested()
    function showContext(key) { return context.showContext(key) }
    color: theme.panel; border.color: theme.border
    ContextState { id: context; objectName: "contextState"; uiState: root.uiState }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 12; spacing: 12
        Text { text: "작업 정보"; color: theme.muted; font.pixelSize: 11; font.family: theme.fontFamily }
        RowLayout {
            objectName: "inspectorTabs"
            spacing: 2; Layout.fillWidth: true
            Repeater {
                model: ["이미지", "분석", "결과", "뷰어", "ROI"]
                AppButton { required property int index; required property string modelData; objectName: "inspectorTab" + index; theme: root.theme; text: modelData; checked: root.tabIndex === index; Layout.fillWidth: true; onClicked: root.tabIndex = index }
            }
        }
        ResultContext { visible: root.tabIndex === 2; Layout.fillWidth: true; Layout.fillHeight: true; theme: root.theme; uiState: root.uiState; onExportRequested: root.resultExportRequested(); onOverviewRequested: root.overviewRequested() }
        ScrollView {
            visible: root.tabIndex !== 2
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: 12
                RoiContext { visible: root.tabIndex === 4; Layout.fillWidth: true; theme: root.theme; uiState: root.uiState; onImportRequested: root.importRequested(); onBoundsRequested: root.boundsRequested(); onSaveRequested: root.saveRequested() }
                ViewerContext { visible: root.tabIndex === 3; Layout.fillWidth: true; theme: root.theme; uiState: root.uiState }
                ImageContext { visible: root.tabIndex === 0; Layout.fillWidth: true; theme: root.theme; uiState: root.uiState }
                AnalysisContext { visible: root.tabIndex === 1; Layout.fillWidth: true; theme: root.theme; uiState: root.uiState; actions: root.actions; onModelRequested: root.modelRequested(); onCoordinatesRequested: root.coordinatesRequested() }
            }
        }
    }
}
