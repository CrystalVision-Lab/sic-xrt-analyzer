import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property QtObject theme
    property QtObject uiState
    property bool collapsed: false
    property int tabIndex: 0
    signal collapseRequested()

    implicitWidth: collapsed ? 54 : theme.panelWidth
    color: theme.panel
    border.color: theme.border
    border.width: 1

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 50
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            AppButton {
                theme: root.theme
                text: root.collapsed ? "<" : ">"
                quiet: true
                implicitWidth: 34
                tip: root.collapsed ? "정보 패널 펼치기" : "정보 패널 접기"
                onClicked: root.collapseRequested()
            }
            Text {
                visible: !root.collapsed
                text: "정보 및 설정"
                color: theme.text
                font.family: theme.fontFamily
                font.pixelSize: theme.sectionSize
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
        }

        RowLayout {
            visible: !root.collapsed
            Layout.fillWidth: true
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            spacing: 3
            Repeater {
                model: ["이미지", "분석", "결과"]
                delegate: AppButton {
                    required property int index
                    required property string modelData
                    theme: root.theme
                    text: modelData
                    quiet: true
                    checked: root.tabIndex === index
                    Layout.fillWidth: true
                    onClicked: root.tabIndex = index
                }
            }
        }

        Flickable {
            visible: !root.collapsed
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: panelContent.implicitHeight + 28
            boundsBehavior: Flickable.StopAtBounds

            ColumnLayout {
                id: panelContent
                x: 14
                y: 16
                width: parent.width - 28
                spacing: 12

                ColumnLayout {
                    visible: root.tabIndex === 0
                    Layout.fillWidth: true
                    spacing: 6
                    Text { text: "이미지 정보"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: theme.sectionSize; font.weight: Font.DemiBold }
                    InfoRow { theme: root.theme; label: "파일"; value: uiState.fileName || "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "형식"; value: uiState.hasSelectedFile ? "TIFF (파일명 기준)" : "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "이미지 크기"; value: "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "물리 스케일"; value: "—"; Layout.fillWidth: true }
                    Text {
                        text: uiState.hasSelectedFile ? "이미지 데이터와 메타데이터는 아직 읽지 않았습니다." : "파일을 열면 선택한 파일 정보가 표시됩니다."
                        color: theme.muted
                        font.family: theme.fontFamily
                        font.pixelSize: theme.smallSize
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Rectangle { Layout.fillWidth: true; Layout.topMargin: 8; height: 1; color: theme.border }
                    Text { text: "표시 설정"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: theme.sectionSize; font.weight: Font.DemiBold; Layout.topMargin: 6 }
                    Text { text: "TIFF 표시 연결 후 사용할 수 있습니다."; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: theme.smallSize }
                    Text { text: "밝기"; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: theme.smallSize }
                    Slider { enabled: false; from: -100; to: 100; value: 0; Layout.fillWidth: true }
                    Text { text: "대비"; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: theme.smallSize }
                    Slider { enabled: false; from: -100; to: 100; value: 0; Layout.fillWidth: true }
                    CheckBox { text: "결함 표시 레이어"; enabled: false; Layout.fillWidth: true }
                }

                ColumnLayout {
                    visible: root.tabIndex === 1
                    Layout.fillWidth: true
                    spacing: 10
                    Text { text: "분석 설정"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: theme.sectionSize; font.weight: Font.DemiBold }
                    InfoRow {
                        theme: root.theme
                        label: "관심 영역"
                        value: uiState.hasRoi && uiState.demoMode ? "데모 영역 선택됨" : "선택 없음"
                        Layout.fillWidth: true
                    }
                    Text {
                        text: "관심 영역은 데모 이미지에서 선택 도구로 시험할 수 있습니다. 실제 이미지 좌표 연결은 준비 중입니다."
                        color: theme.muted
                        font.family: theme.fontFamily
                        font.pixelSize: theme.smallSize
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }
                    InfoRow { theme: root.theme; label: "분석 방식"; value: "—"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "모델"; value: "모델 미연결"; Layout.fillWidth: true }
                    AppButton {
                        theme: root.theme
                        text: "분석 실행"
                        enabled: false
                        Layout.fillWidth: true
                    }
                    Text {
                        text: "승인된 모델과 이미지 로더가 연결되면 분석을 실행할 수 있습니다."
                        color: theme.muted
                        font.family: theme.fontFamily
                        font.pixelSize: theme.smallSize
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }

                ColumnLayout {
                    visible: root.tabIndex === 2
                    Layout.fillWidth: true
                    spacing: 10
                    Text { text: "결과 요약"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: theme.sectionSize; font.weight: Font.DemiBold }
                    Text {
                        text: "분석 결과가 없습니다"
                        color: theme.text
                        font.family: theme.fontFamily
                        font.pixelSize: theme.sectionSize
                        Layout.topMargin: 10
                    }
                    Text {
                        text: "분석 기능이 연결되면 이곳에서 결과와 관심 영역을 검토할 수 있습니다."
                        color: theme.muted
                        font.family: theme.fontFamily
                        font.pixelSize: theme.smallSize
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }
        }
        Item { visible: root.collapsed; Layout.fillHeight: true }
    }
}
