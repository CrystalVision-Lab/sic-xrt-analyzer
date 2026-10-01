import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property QtObject theme
    property QtObject uiState
    property real panX: 0
    property real panY: 0
    property real pressX: 0
    property real pressY: 0
    property real pressPanX: 0
    property real pressPanY: 0
    readonly property real fitScale: Math.max(0.1, Math.min(
        (viewport.width - 48) / 960, (viewport.height - 48) / 600))
    signal openRequested()
    signal demoRequested()

    color: theme.viewer

    function fitView() {
        uiState.zoom = 1
        panX = 0
        panY = 0
        uiState.statusText = "화면에 맞게 표시했습니다"
    }
    function zoomIn() {
        if (!uiState.canNavigateImage) return
        uiState.zoom = Math.min(4, Math.round(uiState.zoom * 125) / 100)
        uiState.statusText = "데모 이미지 확대"
    }
    function zoomOut() {
        if (!uiState.canNavigateImage) return
        uiState.zoom = Math.max(0.25, Math.round(uiState.zoom * 80) / 100)
        uiState.statusText = "데모 이미지 축소"
    }
    Connections {
        target: root.uiState
        function onDemoModeChanged() {
            root.panX = 0
            root.panY = 0
            uiState.zoom = 1
            uiState.hasRoi = false
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            color: theme.viewerHeader

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 8
                ColumnLayout {
                    spacing: 0
                    Layout.fillWidth: true
                    Text {
                        text: uiState.workspaceIndex === 0 ? "이미지 뷰어" :
                              ["", "Wafer Map", "이미지 정합", "3D 보기"][uiState.workspaceIndex]
                        color: theme.viewerText
                        font.family: theme.fontFamily
                        font.pixelSize: theme.sectionSize
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: uiState.workspaceIndex !== 0 ? "기능 연결 예정" :
                              uiState.fileName || (uiState.demoMode ? "데모 이미지 · 합성 샘플" : "선택된 이미지 없음")
                        color: theme.viewerMuted
                        font.family: theme.fontFamily
                        font.pixelSize: theme.captionSize
                        elide: Text.ElideMiddle
                        Layout.maximumWidth: 270
                    }
                }
                Text {
                    text: uiState.zoomLabel
                    visible: uiState.workspaceIndex === 0
                    color: theme.viewerText
                    font.family: theme.monoFontFamily
                    font.pixelSize: theme.smallSize
                    Layout.rightMargin: 6
                }
                AppButton {
                    theme: root.theme
                    text: "이동"
                    dark: true
                    quiet: true
                    checked: uiState.activeTool === "이동"
                    enabled: uiState.canNavigateImage
                    onClicked: uiState.activeTool = "이동"
                }
                AppButton {
                    theme: root.theme
                    text: "영역 선택"
                    dark: true
                    quiet: true
                    checked: uiState.activeTool === "영역 선택"
                    enabled: uiState.canNavigateImage
                    onClicked: uiState.activeTool = "영역 선택"
                }
                AppButton {
                    theme: root.theme
                    text: "화면 맞춤"
                    dark: true
                    quiet: true
                    enabled: uiState.canNavigateImage
                    onClicked: root.fitView()
                }
            }
        }

        Item {
            id: viewport
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            Item {
                id: content
                visible: uiState.canNavigateImage
                width: 960 * root.fitScale * uiState.zoom
                height: 600 * root.fitScale * uiState.zoom
                x: (viewport.width - width) / 2 + root.panX
                y: (viewport.height - height) / 2 + root.panY

                DemoImage { anchors.fill: parent; theme: root.theme }

                Rectangle {
                    visible: uiState.hasRoi
                    x: Math.min(uiState.roiStartX, uiState.roiEndX) * content.width
                    y: Math.min(uiState.roiStartY, uiState.roiEndY) * content.height
                    width: Math.abs(uiState.roiEndX - uiState.roiStartX) * content.width
                    height: Math.abs(uiState.roiEndY - uiState.roiStartY) * content.height
                    color: "#3320c0cc"
                    border.color: "#52dce5"
                    border.width: 2
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: uiState.canNavigateImage
                    hoverEnabled: true
                    cursorShape: uiState.activeTool === "이동" ? Qt.OpenHandCursor : Qt.CrossCursor
                    onPressed: function(mouse) {
                        const point = mapToItem(viewport, mouse.x, mouse.y)
                        root.pressX = point.x
                        root.pressY = point.y
                        root.pressPanX = root.panX
                        root.pressPanY = root.panY
                        if (uiState.activeTool === "영역 선택") {
                            uiState.roiStartX = Math.max(0, Math.min(1, mouse.x / width))
                            uiState.roiStartY = Math.max(0, Math.min(1, mouse.y / height))
                            uiState.roiEndX = uiState.roiStartX
                            uiState.roiEndY = uiState.roiStartY
                            uiState.hasRoi = false
                        }
                    }
                    onPositionChanged: function(mouse) {
                        if (!pressed) return
                        if (uiState.activeTool === "이동") {
                            const point = mapToItem(viewport, mouse.x, mouse.y)
                            root.panX = root.pressPanX + point.x - root.pressX
                            root.panY = root.pressPanY + point.y - root.pressY
                        } else {
                            uiState.roiEndX = Math.max(0, Math.min(1, mouse.x / width))
                            uiState.roiEndY = Math.max(0, Math.min(1, mouse.y / height))
                            uiState.hasRoi = true
                        }
                    }
                    onReleased: {
                        if (uiState.activeTool === "영역 선택") {
                            uiState.hasRoi = Math.abs(uiState.roiEndX - uiState.roiStartX) > 0.005 &&
                                           Math.abs(uiState.roiEndY - uiState.roiStartY) > 0.005
                            uiState.statusText = uiState.hasRoi ? "데모 이미지의 관심 영역을 선택했습니다" : "관심 영역 선택을 취소했습니다"
                        } else {
                            uiState.statusText = "데모 이미지 위치를 이동했습니다"
                        }
                    }
                    onWheel: function(wheel) {
                        if (wheel.angleDelta.y > 0) root.zoomIn()
                        else if (wheel.angleDelta.y < 0) root.zoomOut()
                        wheel.accepted = true
                    }
                }
            }

            ColumnLayout {
                visible: uiState.workspaceIndex === 0 && !uiState.demoMode && !uiState.hasSelectedFile
                anchors.centerIn: parent
                spacing: 12
                Text {
                    text: "분석할 XRT 이미지를 선택하세요."
                    color: theme.viewerText
                    font.family: theme.fontFamily
                    font.pixelSize: theme.emptyTitleSize
                    font.weight: Font.DemiBold
                    Layout.alignment: Qt.AlignHCenter
                }
                Text {
                    text: "TIFF 파일을 열어 이미지 탐색을 시작할 수 있습니다."
                    color: theme.viewerMuted
                    font.family: theme.fontFamily
                    font.pixelSize: theme.bodySize
                    Layout.alignment: Qt.AlignHCenter
                }
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 8
                    AppButton {
                        theme: root.theme
                        text: "이미지 열기"
                        dark: true
                        primary: true
                        onClicked: root.openRequested()
                    }
                    AppButton {
                        theme: root.theme
                        text: "데모 이미지 보기"
                        dark: true
                        onClicked: root.demoRequested()
                    }
                }
            }

            ColumnLayout {
                visible: uiState.workspaceIndex === 0 && !uiState.demoMode && uiState.hasSelectedFile
                anchors.centerIn: parent
                spacing: 10
                Text {
                    text: uiState.fileName
                    color: theme.viewerText
                    font.family: theme.fontFamily
                    font.pixelSize: theme.emptyTitleSize
                    font.weight: Font.DemiBold
                    Layout.alignment: Qt.AlignHCenter
                }
                Text {
                    text: "파일을 선택했습니다. TIFF 이미지 표시는 아직 연결되지 않았습니다."
                    color: theme.viewerMuted
                    font.family: theme.fontFamily
                    font.pixelSize: theme.bodySize
                    Layout.alignment: Qt.AlignHCenter
                }
                AppButton {
                    theme: root.theme
                    text: "다른 이미지 열기"
                    dark: true
                    Layout.alignment: Qt.AlignHCenter
                    onClicked: root.openRequested()
                }
            }

            ColumnLayout {
                visible: uiState.workspaceIndex !== 0
                anchors.centerIn: parent
                spacing: 10
                Text {
                    text: ["", "Wafer Map", "이미지 정합", "3D 보기"][uiState.workspaceIndex]
                    color: theme.viewerText
                    font.family: theme.fontFamily
                    font.pixelSize: theme.emptyTitleSize
                    font.weight: Font.DemiBold
                    Layout.alignment: Qt.AlignHCenter
                }
                Text {
                    text: "이 작업 영역은 준비 중입니다. 이미지 분석 화면에서 파일과 도구를 확인할 수 있습니다."
                    color: theme.viewerMuted
                    font.family: theme.fontFamily
                    font.pixelSize: theme.bodySize
                    Layout.alignment: Qt.AlignHCenter
                }
            }
        }
    }
}
