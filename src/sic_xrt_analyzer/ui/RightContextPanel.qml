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
    readonly property string lastReason: context.lastReason
    readonly property string resultPhase: context.resultPhase
    signal activateRequested(string reason)
    signal focusRequested()
    signal importRequested()
    signal boundsRequested()
    signal saveRequested()
    signal overviewRequested()
    signal modelRequested()
    signal coordinatesRequested()
    signal resultExportRequested()
    function showContext(key) { return context.showContext(key) }
    function requestContext(key, reason) { return context.requestContext(key, reason) }
    color: theme.panel
    ContextState { id: context; objectName: "contextState"; uiState: root.uiState; onContextRequested: function(reason) { root.activateRequested(reason) } }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: theme.spacingMd; spacing: theme.spacingMd
        ContextHeader { theme: root.theme; controller: context; Layout.fillWidth: true; onFocusRequested: root.focusRequested() }
        ResultContext { visible: root.requestedContext === "result"; Layout.fillWidth: true; Layout.fillHeight: true; theme: root.theme; uiState: root.uiState; phase: context.resultPhase; message: context.resultMessage; onExportRequested: root.resultExportRequested(); onOverviewRequested: root.overviewRequested() }
        AnalysisContext { visible: root.requestedContext === "analysis"; Layout.fillWidth: true; Layout.fillHeight: true; theme: root.theme; uiState: root.uiState; actions: root.actions; onModelRequested: root.modelRequested(); onCoordinatesRequested: root.coordinatesRequested() }
        RoiContext { visible: root.requestedContext === "roi"; Layout.fillWidth: true; Layout.fillHeight: true; theme: root.theme; uiState: root.uiState; actions: root.actions; onImportRequested: root.importRequested(); onBoundsRequested: root.boundsRequested(); onSaveRequested: root.saveRequested() }
        ScrollView {
            visible: root.requestedContext !== "result" && root.requestedContext !== "analysis" && root.requestedContext !== "roi"
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: theme.spacingMd
                ViewerContext { visible: root.requestedContext === "viewer"; Layout.fillWidth: true; theme: root.theme; uiState: root.uiState; actions: root.actions }
                ImageContext { visible: root.requestedContext === "image"; Layout.fillWidth: true; theme: root.theme; uiState: root.uiState; actions: root.actions }
            }
        }
    }
}
