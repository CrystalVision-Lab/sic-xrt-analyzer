import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "resultContext"
    property QtObject theme
    property QtObject uiState
    property string phase: "empty"
    property string message: "아직 분석 결과가 없습니다."
    readonly property string informationPriority: "primary"
    signal exportRequested()
    signal overviewRequested()
    spacing: theme.spacingSm
    Text {
        objectName: "resultLifecycleMessage"
        visible: !root.uiState.hasResult || !root.uiState.research.total
        text: root.message; color: root.theme.muted; font.pixelSize: theme.bodySize
        wrapMode: Text.Wrap; Layout.fillWidth: true
    }
    ResultExplorer {
        visible: root.uiState.hasResult; theme: root.theme; uiState: root.uiState
        Layout.fillWidth: true; Layout.fillHeight: true
        onExportRequested: root.exportRequested(); onOverviewRequested: root.overviewRequested()
    }
    Item { visible: !root.uiState.hasResult; Layout.fillHeight: true }
}
