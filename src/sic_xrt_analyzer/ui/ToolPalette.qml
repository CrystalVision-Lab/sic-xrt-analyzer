import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    property QtObject theme
    property QtObject uiState
    property var hostWindow
    spacing: 3
    Repeater {
        model: [
            {tool:"Rectangle", tip:"사각형 선택"}, {tool:"Oval", tip:"타원 선택"}, {tool:"Polygon", tip:"다각형 선택"},
            {tool:"Freehand", tip:"자유 영역 선택"}, {tool:"Line", tip:"직선"}, {tool:"Polyline", tip:"분할선"},
            {tool:"FreeLine", tip:"자유선"}, {tool:"Angle", tip:"각도 (3점)"}, {tool:"Point", tip:"다중 점"},
            {tool:"Wand", tip:"완드 (연결 영역)"}, {tool:"Text", tip:"텍스트 ROI"}, {tool:"Zoom", tip:"확대 (Alt: 축소)"},
            {tool:"Pan", tip:"이동"}, {tool:"Picker", tip:"원본 픽셀에서 색 추출"}, {tool:"Brush", tip:"브러시 (작업 복사본)"},
            {tool:"Fill", tip:"영역 채우기 (작업 복사본)"}, {tool:"Arrow", tip:"화살표 ROI"}
        ]
        ToolButton {
            required property var modelData
            objectName: "tool" + modelData.tool
            implicitWidth: 31; implicitHeight: 30
            checked: root.uiState.activeTool === modelData.tool && !root.uiState.roiEditMode
            enabled: root.uiState.hasLoadedImage && root.uiState.canNavigateImage
            contentItem: ToolGlyph { tool: modelData.tool; ink: parent.enabled ? root.theme.text : root.theme.disabled }
            background: Rectangle { color: parent.checked ? root.theme.accentPale : parent.hovered ? root.theme.hover : root.theme.toolbar; border.color: parent.checked ? root.theme.accent : root.theme.border; radius: 2 }
            ToolTip.visible: hovered; ToolTip.text: modelData.tip
            onClicked: { root.uiState.roiEditMode = false; root.uiState.activeTool = modelData.tool }
        }
    }
    AppButton { theme: root.theme; text: "측정"; tip: "기준 길이 / 길이·면적·개수 측정"; onClicked: root.hostWindow.stackMeasurement() }
    AppButton { theme: root.theme; text: "Dev"; tip: "개발자: 매크로·플러그인"; onClicked: dev.open() }
    AppButton { theme: root.theme; text: "Stk"; tip: "스택"; onClicked: stack.open() }
    AppButton { theme: root.theme; text: "LUT"; tip: "색상 표시표"; onClicked: lut.open() }
    AppButton { theme: root.theme; text: ">>"; tip: "추가 도구 / 도구 옵션"; onClicked: more.open() }
    Item { Layout.fillWidth: true }
    Text { text: fileBridge.imagej.state.busy ? "ImageJ 처리 중…" : "ImageJ 도구"; color: root.theme.muted; font.pixelSize: 11 }
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
