import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property QtObject theme
    property QtObject uiState
    property var openAction
    property var demoAction
    property var fitAction
    property var zoomInAction
    property var zoomOutAction

    implicitHeight: theme.toolbarHeight
    color: theme.panel
    border.color: theme.border
    border.width: 1

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 18
        anchors.rightMargin: 18
        spacing: 8

        ColumnLayout {
            spacing: 0
            Layout.preferredWidth: 182
            Text {
                text: "SiC XRT Analyzer"
                color: theme.text
                font.family: theme.fontFamily
                font.pixelSize: theme.titleSize
                font.weight: Font.DemiBold
            }
            Text {
                text: "연구용 이미지 분석"
                color: theme.muted
                font.family: theme.fontFamily
                font.pixelSize: theme.captionSize
            }
        }

        Rectangle { width: 1; height: 28; color: theme.border }

        Text {
            text: uiState.fileName || (uiState.demoMode ? "데모 이미지" : "선택된 파일 없음")
            color: uiState.fileName ? theme.text : theme.muted
            font.family: theme.fontFamily
            font.pixelSize: theme.bodySize
            elide: Text.ElideMiddle
            Layout.fillWidth: true
            Layout.minimumWidth: 110
            ToolTip.visible: fileHover.containsMouse && uiState.filePath.length > 0
            ToolTip.text: uiState.filePath
            MouseArea { id: fileHover; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
        }

        AppButton {
            theme: root.theme
            text: "이미지 열기"
            primary: true
            onClicked: root.openAction.trigger()
        }
        AppButton {
            theme: root.theme
            text: "데모 보기"
            tip: "실제 검사 데이터가 아닌 합성 샘플입니다"
            onClicked: root.demoAction.trigger()
        }
        Rectangle { width: 1; height: 28; color: theme.border }
        AppButton {
            theme: root.theme
            text: "화면 맞춤"
            enabled: root.fitAction.enabled
            onClicked: root.fitAction.trigger()
        }
        AppButton {
            theme: root.theme
            text: "-"
            implicitWidth: 36
            enabled: root.zoomOutAction.enabled
            tip: "축소"
            onClicked: root.zoomOutAction.trigger()
        }
        AppButton {
            theme: root.theme
            text: "+"
            implicitWidth: 36
            enabled: root.zoomInAction.enabled
            tip: "확대"
            onClicked: root.zoomInAction.trigger()
        }
        AppButton {
            theme: root.theme
            text: "분석 실행"
            enabled: false
            tip: "모델 연결 후 사용할 수 있습니다"
        }
    }
}
