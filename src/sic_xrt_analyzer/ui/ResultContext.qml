import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    objectName: "resultContext"
    property QtObject theme
    property QtObject uiState
    property string phase: "empty"
    property string message: "아직 분석 결과가 없습니다."
    readonly property string informationPriority: "primary"
    signal exportRequested()
    signal overviewRequested()
    clip: true; contentWidth: availableWidth; contentHeight: Math.max(780, availableHeight)
    ColumnLayout {
        width: root.availableWidth; spacing: 10
        Text { objectName: "resultLifecycleMessage"; text: root.message; color: root.theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
        ResultExplorer { visible: root.uiState.hasResult; theme: root.theme; uiState: root.uiState; Layout.fillWidth: true; Layout.preferredHeight: Math.max(780, root.availableHeight); onExportRequested: root.exportRequested(); onOverviewRequested: root.overviewRequested() }
    }
}
