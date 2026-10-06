import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    property QtObject theme
    property QtObject uiState
    property var hostWindow
    spacing: 3
    objectName: "advancedToolGroup"
    readonly property string informationPriority: "advanced"
    AppButton { theme: root.theme; text: "Dev"; tip: "개발자: 매크로·플러그인"; onClicked: dev.open() }
    AppButton { theme: root.theme; text: "Stk"; tip: "스택"; onClicked: stack.open() }
    AppButton { theme: root.theme; text: "LUT"; tip: "색상 표시표"; onClicked: lut.open() }
    AppButton { theme: root.theme; text: ">>"; tip: "추가 도구 / 도구 옵션"; onClicked: more.open() }
    AppMenu { id: dev; title: "개발자"; y: parent.height
        AppMenuItem { text: "매크로 편집 / 실행…"; onTriggered: root.hostWindow.imagejMacro() }
        AppMenuItem { text: "Java 플러그인 실행…"; onTriggered: root.hostWindow.imagejPlugin() }
        AppMenuItem { text: "Fiji / ImageJ2 명령…"; onTriggered: root.hostWindow.imagejModern() }
        AppMenuItem { text: "명령 기록"; checkable: true; checked: fileBridge.imagej.state.recording; onTriggered: fileBridge.imagej.record(checked) }
        AppMenuItem { text: "모든 ImageJ 명령…"; onTriggered: root.hostWindow.imagejCatalog() }
    }
    AppMenu { id: stack; title: "스택"; y: parent.height
        AppMenuItem { text: "첫 페이지"; enabled: root.uiState.pageCount > 1; onTriggered: fileBridge.requestPage(0) }
        AppMenuItem { text: "이전 페이지"; enabled: root.uiState.pageCount > 1; onTriggered: fileBridge.requestPage(Math.max(0, root.uiState.pageIndex - 1)) }
        AppMenuItem { text: "다음 페이지"; enabled: root.uiState.pageCount > 1; onTriggered: fileBridge.requestPage(Math.min(root.uiState.pageCount - 1, root.uiState.pageIndex + 1)) }
        AppMenuItem { text: "마지막 페이지"; enabled: root.uiState.pageCount > 1; onTriggered: fileBridge.requestPage(root.uiState.pageCount - 1) }
        MenuSeparator {}
        AppMenuItem { text: "페이지 축으로 투영…"; enabled: root.uiState.pageCount > 1; onTriggered: root.hostWindow.imagejStackCommand("Z Project...", "projection=[Max Intensity]") }
        AppMenuItem { text: "스택 복제…"; enabled: root.uiState.pageCount > 1; onTriggered: root.hostWindow.imagejStackCommand("Duplicate...", "duplicate") }
        AppMenuItem { text: "스택 반전"; enabled: root.uiState.pageCount > 1; onTriggered: root.hostWindow.imagejStackCommand("Reverse", "") }
    }
    AppMenu { id: lut; title: "LUT"; y: parent.height
        Repeater { model: ["Grays", "Fire", "Ice", "Spectrum", "Red", "Green", "Blue", "Cyan", "Magenta", "Yellow", "Red/Green"]
            AppMenuItem { required property string modelData; text: modelData; onTriggered: root.hostWindow.imagejCommand(modelData, "") }
        }
        AppMenuItem { text: "Invert LUT"; onTriggered: root.hostWindow.imagejCommand("Invert LUT", "") }
    }
    AppMenu { id: more; title: "추가 도구"; y: parent.height
        AppMenuItem { text: "색상·브러시·완드·텍스트 옵션…"; onTriggered: root.hostWindow.imagejTools() }
        AppMenuItem { text: "ROI 편집 / 관리"; onTriggered: { root.uiState.roiEditMode = true; root.hostWindow.openInspectorTab(4) } }
        AppMenuItem { text: "매크로 도구 파일 실행…"; onTriggered: root.hostWindow.imagejMacro() }
        AppMenuItem { text: "Java 도구 플러그인…"; onTriggered: root.hostWindow.imagejPlugin() }
    }
}
