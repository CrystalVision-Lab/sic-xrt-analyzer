import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    Layout.minimumWidth: 0
    objectName: "resultContext"
    property QtObject theme
    property QtObject uiState
    property string phase: "empty"
    property string message: "아직 분석 결과가 없습니다."
    readonly property string informationPriority: "primary"
    signal exportRequested()
    signal overviewRequested()
    signal reviewRequested()
    spacing: theme.spacingSm
    Text {
        objectName: "resultLifecycleMessage"
        visible: !root.uiState.hasResult || !root.uiState.research.total
        text: root.uiState.pageCount > 1 && !root.uiState.hasResult ? "TIFF는 스택 탐색·3D용 데이터입니다." : root.message; color: root.theme.muted; font.pixelSize: theme.bodySize
        wrapMode: Text.Wrap; Layout.fillWidth: true
    }
    ResultExplorer {
        visible: root.uiState.hasLoadedImage && root.uiState.hasResult; theme: root.theme; uiState: root.uiState
        Layout.fillWidth: true; Layout.fillHeight: true
        onExportRequested: root.exportRequested(); onOverviewRequested: root.overviewRequested(); onReviewRequested: root.reviewRequested()
    }
    Item { visible: !root.uiState.hasLoadedImage; Layout.fillHeight: true }
}
