import QtQuick
import QtQuick.Controls

MenuBar {
    id: root
    property QtObject theme
    property QtObject uiState
    property var hostWindow
    property var inspectorPanel
    property var fileBridge
    property var actions

    objectName: "appMenuBar"
    background: Rectangle { color: theme.panel; border.color: theme.border; border.width: 1 }
    delegate: MenuBarItem {
        id: barItem
        implicitHeight: 34
        implicitWidth: contentItem.implicitWidth + 24
        contentItem: Text {
            text: barItem.text
            color: barItem.enabled ? theme.text : theme.disabled
            font.family: theme.fontFamily
            font.pixelSize: theme.bodySize
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignHCenter
        }
        background: Rectangle { color: barItem.highlighted ? theme.accentPale : theme.panel }
    }

    Shortcut { sequence: "Alt+F"; onActivated: fileMenu.open() }
    Shortcut { sequence: "Alt+E"; onActivated: editMenu.open() }
    Shortcut { sequence: "Alt+V"; onActivated: viewMenu.open() }
    Shortcut { sequence: "Alt+A"; onActivated: analysisMenu.open() }
    Shortcut { sequence: "Alt+T"; onActivated: toolsMenu.open() }
    Shortcut { sequence: "Alt+H"; onActivated: helpMenu.open() }

    Menu {
        id: fileMenu
        objectName: "fileMenu"
        title: "파일"
        width: 280
        AppMenuItem { objectName: "menuOpenItem"; action: root.actions.open; shortcutLabel: "Ctrl+O" }
        Menu {
            id: recentMenu
            objectName: "recentMenu"
            title: "최근 파일"
            width: 420
            Instantiator {
                model: root.fileBridge.recentFiles
                delegate: MenuItem {
                    text: root.fileBridge.fileName(modelData) + " — " + modelData
                    ToolTip.text: modelData
                    ToolTip.visible: hovered
                    onTriggered: root.hostWindow.selectImagePath(modelData)
                }
                onObjectAdded: function(index, object) { recentMenu.insertItem(index, object) }
                onObjectRemoved: function(index, object) { recentMenu.removeItem(object) }
            }
            MenuItem { text: "최근 파일 없음"; enabled: false; visible: root.fileBridge.recentFiles.length === 0 }
            MenuSeparator {}
            MenuItem { text: "최근 파일 목록 비우기"; enabled: root.fileBridge.recentFiles.length > 0; onTriggered: root.fileBridge.clearRecentFiles() }
        }
        MenuSeparator {}
        AppMenuItem { text: "새 분석 프로젝트"; shortcutLabel: "Ctrl+N"; enabled: false; ToolTip.text: "프로젝트 형식 준비 중" }
        MenuItem { text: "프로젝트 열기…"; enabled: false; ToolTip.text: "프로젝트 형식 준비 중" }
        MenuSeparator {}
        AppMenuItem { text: "프로젝트 저장"; shortcutLabel: "Ctrl+S"; enabled: false; ToolTip.text: "프로젝트 형식 준비 중" }
        AppMenuItem { text: "다른 이름으로 저장…"; shortcutLabel: "Ctrl+Shift+S"; enabled: false; ToolTip.text: "프로젝트 형식 준비 중" }
        Menu {
            title: "결과 내보내기"
            enabled: false
            MenuItem { text: "분석 결과 CSV…"; enabled: false }
            MenuItem { text: "현재 화면 PNG…"; enabled: false }
            MenuItem { text: "분석 보고서…"; enabled: false }
        }
        MenuSeparator {}
        AppMenuItem { action: root.actions.closeImage; shortcutLabel: "Ctrl+W" }
        AppMenuItem { action: root.actions.quit; shortcutLabel: "Ctrl+Q" }
    }
    Menu {
        id: editMenu
        title: "편집"
        width: 260
        AppMenuItem { text: "실행 취소"; shortcutLabel: "Ctrl+Z"; enabled: false; ToolTip.text: "편집 이력 없음" }
        AppMenuItem { text: "다시 실행"; shortcutLabel: "Ctrl+Y"; enabled: false; ToolTip.text: "편집 이력 없음" }
        MenuSeparator {}
        MenuItem { action: root.actions.selectRoi; checkable: true; checked: root.uiState.activeTool === "영역 선택" }
        MenuItem { action: root.actions.clearRoi }
        MenuItem { action: root.actions.copyRoi }
    }
    Menu {
        id: viewMenu
        title: "보기"
        width: 240
        AppMenuItem { action: root.actions.zoomIn; shortcutLabel: "Ctrl++" }
        AppMenuItem { action: root.actions.zoomOut; shortcutLabel: "Ctrl+-" }
        AppMenuItem { action: root.actions.fit; shortcutLabel: "Ctrl+0" }
        MenuItem { text: "실제 크기 100%"; enabled: false; ToolTip.text: "현재 100%는 화면 맞춤 기준" }
        MenuSeparator {}
        Menu {
            title: "표시 레이어"
            width: 220
            MenuItem { action: root.actions.roiLayer; checkable: true; checked: root.uiState.roiLayerVisible }
            MenuItem { text: "결함 표시"; checkable: true; enabled: false; ToolTip.text: "결함 데이터 없음" }
            MenuItem { text: "스케일 바"; checkable: true; enabled: false; ToolTip.text: "물리 스케일 없음" }
            MenuItem { text: "좌표 격자"; checkable: true; enabled: false; ToolTip.text: "좌표 격자 미구현" }
        }
        Menu {
            title: "패널 표시"
            width: 230
            MenuItem { objectName: "navigationPanelMenuItem"; action: root.actions.navigationPanel; checkable: true; checked: !root.hostWindow.navigationCollapsed }
            MenuItem {
                objectName: "infoPanelMenuItem"
                text: "이미지 정보 패널"
                checkable: true
                checked: !root.hostWindow.inspectorCollapsed && root.inspectorPanel.tabIndex === 0
                onTriggered: {
                    if (root.hostWindow.inspectorCollapsed || root.inspectorPanel.tabIndex !== 0) root.hostWindow.openInspectorTab(0)
                    else root.actions.inspectorPanel.trigger()
                }
            }
            MenuItem {
                text: "분석 결과 패널"
                checkable: true
                checked: !root.hostWindow.inspectorCollapsed && root.inspectorPanel.tabIndex === 2
                onTriggered: {
                    if (root.hostWindow.inspectorCollapsed || root.inspectorPanel.tabIndex !== 2) root.hostWindow.openInspectorTab(2)
                    else root.actions.inspectorPanel.trigger()
                }
            }
            MenuItem { objectName: "statusBarMenuItem"; action: root.actions.statusBar; checkable: true; checked: root.hostWindow.statusBarVisible }
        }
        MenuSeparator {}
        AppMenuItem { action: root.actions.fullScreen; shortcutLabel: "F11"; checkable: true; checked: root.hostWindow.visibility === Window.FullScreen }
        MenuItem { action: root.actions.resetLayout }
    }
    Menu {
        id: analysisMenu
        title: "분석"
        width: 250
        MenuItem { text: "전체 이미지 분석"; enabled: false; ToolTip.text: "모델 분석 기능 미연결" }
        MenuItem { text: "선택 영역 분석"; enabled: false; ToolTip.text: "모델 분석 기능 미연결" }
        MenuItem { action: root.actions.analysisSettings }
        MenuItem { text: "분석 취소"; enabled: false; ToolTip.text: "실행 중인 분석 없음" }
        MenuSeparator {}
        MenuItem { text: "분석 결과 보기"; enabled: false; ToolTip.text: "분석 결과 없음" }
    }
    Menu {
        id: toolsMenu
        title: "도구"
        width: 220
        MenuItem { text: "픽셀·거리 측정"; enabled: false; ToolTip.text: "측정 도구 미구현" }
        MenuItem { text: "스케일 설정…"; enabled: false; ToolTip.text: "물리 스케일 미연결" }
        MenuSeparator {}
        MenuItem { action: root.actions.modelInfo }
        MenuItem { text: "환경설정…"; enabled: false; ToolTip.text: "적용 가능한 설정 미구현" }
    }
    Menu {
        id: helpMenu
        title: "도움말"
        width: 200
        MenuItem { action: root.actions.guide }
        MenuItem { action: root.actions.shortcutGuide }
        MenuItem { action: root.actions.reportIssue }
        MenuSeparator {}
        MenuItem { action: root.actions.about }
    }
}
