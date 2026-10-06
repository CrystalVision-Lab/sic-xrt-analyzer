import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    property QtObject theme
    property QtObject uiState
    property var hostWindow
    spacing: 3
    objectName: "stackViewerToolGroup"
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
            action: root.hostWindow.commands.tools.forTool(modelData.tool)
            contentItem: ToolGlyph { tool: modelData.tool; ink: parent.enabled ? root.theme.text : root.theme.disabled }
            background: Rectangle { color: parent.checked ? root.theme.accentPale : parent.hovered ? root.theme.hover : root.theme.toolbar; border.color: parent.checked ? root.theme.accent : root.theme.border; radius: 2 }
            ToolTip.visible: hovered; ToolTip.text: modelData.tip
        }
    }
    AppButton { theme: root.theme; text: "측정"; tip: "기준 길이 / 길이·면적·개수 측정"; action: root.hostWindow.commands.advanced.measurement }
}
