import QtQuick
import QtQuick.Controls

ScrollView {
    id: root
    objectName: "resultContext"
    property QtObject theme
    property QtObject uiState
    readonly property string informationPriority: "primary"
    signal exportRequested()
    signal overviewRequested()
    signal reviewRequested()
    clip: true; contentWidth: availableWidth; contentHeight: Math.max(780, availableHeight)
    ResultExplorer { theme: root.theme; uiState: root.uiState; width: root.availableWidth; height: Math.max(780, root.availableHeight); onExportRequested: root.exportRequested(); onOverviewRequested: root.overviewRequested(); onReviewRequested: root.reviewRequested() }
}
