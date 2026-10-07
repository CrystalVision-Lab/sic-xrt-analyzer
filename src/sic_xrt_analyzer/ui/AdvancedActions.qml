import QtQuick
import QtQuick.Controls

QtObject {
    id: root
    property QtObject uiState
    property var hostWindow
    property var bridge
    readonly property bool enabled: uiState.stackFeaturesVisible && uiState.loadFlow.recordReady
    readonly property bool hasPages: enabled && uiState.pageCount > 1 && uiState.loadFlow.pageNavigationReady
    property Action measurement: Action { objectName: "advancedMeasurementAction"; text: "스케일 · 길이 / 면적 / 개수 측정…"; enabled: root.enabled; onTriggered: root.hostWindow.stackMeasurement() }
    property Action tools: Action { objectName: "advancedToolsAction"; text: "색상·브러시·완드·텍스트 옵션…"; enabled: root.enabled; onTriggered: root.hostWindow.imagejTools() }
    property Action macro: Action { objectName: "advancedMacroAction"; text: "매크로 편집 / 실행…"; enabled: root.enabled; onTriggered: root.hostWindow.imagejMacro() }
    property Action plugin: Action { objectName: "advancedPluginAction"; text: "Java 플러그인 등록 / 실행…"; enabled: root.enabled; onTriggered: root.hostWindow.imagejPlugin() }
    property Action modern: Action { objectName: "advancedModernAction"; text: "Fiji / ImageJ2 명령…"; enabled: root.enabled; onTriggered: root.hostWindow.imagejModern() }
    property Action catalog: Action { objectName: "advancedCatalogAction"; text: "모든 ImageJ 명령…"; enabled: root.enabled; onTriggered: root.hostWindow.imagejCatalog() }
    property Action results: Action { objectName: "advancedResultsAction"; text: "ImageJ 결과 / 로그…"; enabled: root.enabled; onTriggered: root.hostWindow.imagejResults() }
    property Action roiManager: Action { objectName: "advancedRoiManagerAction"; text: "ROI 관리자"; enabled: true; onTriggered: root.hostWindow.requestContext("roi", "ROI_MANAGER_OPEN") }
    property Action editRoi: Action { objectName: "advancedEditRoiAction"; text: root.uiState.roiEditMode ? "편집 종료" : "ROI 편집"; checkable: true; checked: root.uiState.roiEditMode; enabled: root.uiState.roiEditMode || root.uiState.roiFlow.canEdit; onTriggered: { root.uiState.roiEditMode = !root.uiState.roiEditMode; root.hostWindow.requestContext("roi", "ROI_EDIT"); root.hostWindow.requestActivate(); Qt.callLater(function() { root.hostWindow.viewer.focusView() }) } }
    property Action saveMeasurements: Action { objectName: "advancedSaveMeasurementsAction"; text: "측정 결과 TSV 저장…"; enabled: root.enabled && root.bridge.imagej.state.rows.length > 0 && !root.bridge.imagej.state.busy; onTriggered: root.hostWindow.saveMeasurements() }
    property Action first: Action { objectName: "advancedFirstAction"; text: "첫 페이지"; enabled: root.hasPages; onTriggered: root.bridge.requestPage(0) }
    property Action previous: Action { objectName: "advancedPreviousAction"; text: "이전 페이지"; enabled: root.hasPages; onTriggered: root.bridge.requestPage(Math.max(0, root.uiState.pageIndex - 1)) }
    property Action next: Action { objectName: "advancedNextAction"; text: "다음 페이지"; enabled: root.hasPages; onTriggered: root.bridge.requestPage(Math.min(root.uiState.pageCount - 1, root.uiState.pageIndex + 1)) }
    property Action last: Action { objectName: "advancedLastAction"; text: "마지막 페이지"; enabled: root.hasPages; onTriggered: root.bridge.requestPage(root.uiState.pageCount - 1) }
    property Action project: Action { objectName: "advancedProjectAction"; text: "페이지 축으로 투영…"; enabled: root.hasPages; onTriggered: root.hostWindow.imagejStackCommand("Z Project...", "projection=[Max Intensity]") }
    property Action duplicate: Action { objectName: "advancedDuplicateAction"; text: "스택 복제…"; enabled: root.hasPages; onTriggered: root.hostWindow.imagejStackCommand("Duplicate...", "duplicate") }
    property Action reverse: Action { objectName: "advancedReverseAction"; text: "스택 반전"; enabled: root.hasPages; onTriggered: root.hostWindow.imagejStackCommand("Reverse", "") }
    property Action record: Action { objectName: "recordCommandsAction"; text: "명령 기록"; enabled: root.enabled; checkable: true; checked: root.bridge.imagej.state.recording; onTriggered: root.bridge.imagej.record(checked) }
    readonly property var luts: [grays, fire, ice, spectrum, red, green, blue, cyan, magenta, yellow, redGreen]
    property Action grays: Action { objectName: "lutGraysAction"; text: "Grays"; enabled: root.enabled; onTriggered: root.hostWindow.imagejCommand(text, "") }
    property Action fire: Action { objectName: "lutFireAction"; text: "Fire"; enabled: root.enabled; onTriggered: root.hostWindow.imagejCommand(text, "") }
    property Action ice: Action { objectName: "lutIceAction"; text: "Ice"; enabled: root.enabled; onTriggered: root.hostWindow.imagejCommand(text, "") }
    property Action spectrum: Action { objectName: "lutSpectrumAction"; text: "Spectrum"; enabled: root.enabled; onTriggered: root.hostWindow.imagejCommand(text, "") }
    property Action red: Action { objectName: "lutRedAction"; text: "Red"; enabled: root.enabled; onTriggered: root.hostWindow.imagejCommand(text, "") }
    property Action green: Action { objectName: "lutGreenAction"; text: "Green"; enabled: root.enabled; onTriggered: root.hostWindow.imagejCommand(text, "") }
    property Action blue: Action { objectName: "lutBlueAction"; text: "Blue"; enabled: root.enabled; onTriggered: root.hostWindow.imagejCommand(text, "") }
    property Action cyan: Action { objectName: "lutCyanAction"; text: "Cyan"; enabled: root.enabled; onTriggered: root.hostWindow.imagejCommand(text, "") }
    property Action magenta: Action { objectName: "lutMagentaAction"; text: "Magenta"; enabled: root.enabled; onTriggered: root.hostWindow.imagejCommand(text, "") }
    property Action yellow: Action { objectName: "lutYellowAction"; text: "Yellow"; enabled: root.enabled; onTriggered: root.hostWindow.imagejCommand(text, "") }
    property Action redGreen: Action { objectName: "lutRedGreenAction"; text: "Red/Green"; enabled: root.enabled; onTriggered: root.hostWindow.imagejCommand(text, "") }
    property Action invertLut: Action { objectName: "lutInvertLutAction"; text: "Invert LUT"; enabled: root.enabled; onTriggered: root.hostWindow.imagejCommand(text, "") }
}
