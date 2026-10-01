import QtQuick
import QtQuick.Controls

MenuBar {
    id: root
    property QtObject theme
    property QtObject uiState
    property var hostWindow
    property var fileBridge
    property var actions
    objectName: "appMenuBar"
    background: Rectangle { color: theme.panel; border.color: theme.border }
    delegate: MenuBarItem {
        id: barItem
        implicitHeight: 30; implicitWidth: contentItem.implicitWidth + 24
        contentItem: Text { text: barItem.text; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignHCenter }
        background: Rectangle { color: barItem.highlighted ? theme.accentPale : theme.panel }
    }
    Shortcut { sequence: "Alt+F"; onActivated: fileMenu.open() }
    Shortcut { sequence: "Alt+E"; onActivated: editMenu.open() }
    Shortcut { sequence: "Alt+V"; onActivated: viewMenu.open() }
    Shortcut { sequence: "Alt+W"; onActivated: workspaceMenu.open() }
    Shortcut { sequence: "Alt+A"; onActivated: analysisMenu.open() }
    Shortcut { sequence: "Alt+T"; onActivated: toolsMenu.open() }
    Shortcut { sequence: "Alt+S"; onActivated: settingsMenu.open() }
    Shortcut { sequence: "Alt+H"; onActivated: helpMenu.open() }
    AppMenu {
        id: fileMenu; objectName: "fileMenu"; title: "파일"; width: 280
        AppMenuItem { objectName: "menuOpenItem"; action: root.actions.open; shortcutLabel: "Ctrl+O"; iconName: "open" }
        AppMenu {
            id: recentMenu; objectName: "recentMenu"; title: "최근 파일"; width: 440
            Instantiator {
                model: root.fileBridge.recentFiles
                delegate: AppMenuItem { required property string modelData; text: root.fileBridge.fileName(modelData) + " — " + modelData; ToolTip.text: modelData; ToolTip.visible: hovered; onTriggered: root.hostWindow.selectImagePath(modelData) }
                onObjectAdded: function(index, object) { recentMenu.insertItem(index, object) }
                onObjectRemoved: function(index, object) { recentMenu.removeItem(object) }
            }
            AppMenuItem { text: "최근 파일 없음"; enabled: false; visible: root.fileBridge.recentFiles.length === 0 }
            MenuSeparator {}
            AppMenuItem { text: "목록 비우기"; enabled: root.fileBridge.recentFiles.length > 0; onTriggered: root.fileBridge.clearRecentFiles() }
        }
        AppMenuItem { action: root.actions.demo }
        AppMenuItem { action: root.actions.importRois; iconName: "roi" }
        MenuSeparator {}
        AppMenuItem { text: "새 분석 프로젝트"; enabled: false }
        AppMenuItem { text: "프로젝트 열기…"; enabled: false }
        AppMenuItem { action: root.actions.save; shortcutLabel: "Ctrl+S" }
        AppMenuItem { text: "다른 이름으로 저장…"; enabled: false }
        AppMenu { title: "내보내기…"; enabled: false
            AppMenuItem { text: "분석 결과 CSV…"; enabled: false }
            AppMenuItem { text: "현재 화면 PNG…"; enabled: false }
            AppMenuItem { text: "분석 보고서…"; enabled: false }
        }
        MenuSeparator {}
        AppMenuItem { action: root.actions.closeImage; shortcutLabel: "Ctrl+W" }
        AppMenuItem { action: root.actions.quit; shortcutLabel: "Ctrl+Q" }
    }
    AppMenu {
        id: editMenu; objectName: "editMenu"; title: "편집"
        AppMenuItem { text: "실행 취소"; shortcutLabel: "Ctrl+Z"; enabled: false }
        AppMenuItem { text: "다시 실행"; shortcutLabel: "Ctrl+Y"; enabled: false }
        MenuSeparator {}
        AppMenuItem { action: root.actions.copyRoi }
    }
    AppMenu {
        id: viewMenu; objectName: "viewMenu"; title: "보기"
        AppMenuItem { action: root.actions.fit; shortcutLabel: "Ctrl+0" }
        AppMenuItem { action: root.actions.zoomIn; shortcutLabel: "Ctrl++" }
        AppMenuItem { action: root.actions.zoomOut; shortcutLabel: "Ctrl+-" }
        AppMenuItem { action: root.actions.actualSize; shortcutLabel: "Ctrl+1" }
        MenuSeparator {}
        AppMenuItem { objectName: "navigationPanelMenuItem"; action: root.actions.navigationPanel; checkable: true; checked: !root.hostWindow.navigationCollapsed }
        AppMenuItem { objectName: "infoPanelMenuItem"; action: root.actions.inspectorPanel; checkable: true; checked: !root.hostWindow.inspectorCollapsed }
        AppMenuItem { objectName: "statusBarMenuItem"; action: root.actions.statusBar; checkable: true; checked: root.hostWindow.statusBarVisible }
        AppMenu {
            title: "표시 레이어"
            AppMenuItem { action: root.actions.roiLayer; checkable: true; checked: root.uiState.roiLayerVisible }
            AppMenuItem { text: "결함 표시"; checkable: true; enabled: false }
            AppMenuItem { text: "스케일 바"; checkable: true; enabled: false }
            AppMenuItem { text: "좌표 격자"; checkable: true; enabled: false }
        }
        MenuSeparator {}
        AppMenuItem { action: root.actions.fullScreen; shortcutLabel: "F11"; checkable: true; checked: root.hostWindow.visibility === Window.FullScreen }
        AppMenuItem { action: root.actions.resetLayout }
    }
    AppMenu {
        id: workspaceMenu; objectName: "workspaceMenu"; title: "작업 영역"
        AppMenuItem { text: "이미지 분석"; checkable: true; checked: root.uiState.workspaceIndex === 0; onTriggered: root.hostWindow.selectWorkspace(0) }
        AppMenuItem { text: "Wafer Map"; checkable: true; checked: root.uiState.workspaceIndex === 1; onTriggered: root.hostWindow.selectWorkspace(1) }
        AppMenuItem { text: "이미지 정합"; checkable: true; checked: root.uiState.workspaceIndex === 2; onTriggered: root.hostWindow.selectWorkspace(2) }
        AppMenuItem { text: "3D 뷰어"; checkable: true; checked: root.uiState.workspaceIndex === 3; onTriggered: root.hostWindow.selectWorkspace(3) }
    }
    AppMenu {
        id: analysisMenu; objectName: "analysisMenu"; title: "분석"
        AppMenuItem { action: root.actions.roi; shortcutLabel: "R"; checkable: true; checked: root.uiState.activeTool === "ROI" }
        AppMenuItem { action: root.actions.clearRoi }
        MenuSeparator {}
        AppMenuItem { action: root.actions.run; iconName: "run"; ToolTip.text: root.uiState.analysisReason; ToolTip.visible: hovered }
        AppMenuItem { action: root.actions.cancelAnalysis }
        AppMenuItem { text: "결과 보기"; enabled: root.uiState.hasResult; onTriggered: root.hostWindow.openInspectorTab(2) }
    }
    AppMenu {
        id: toolsMenu; objectName: "toolsMenu"; title: "도구"
        AppMenuItem { text: "픽셀·거리 측정"; enabled: false }
        AppMenuItem { text: "스케일 설정"; enabled: false }
        MenuSeparator {}
        AppMenuItem { action: root.actions.modelInfo }
    }
    AppMenu {
        id: settingsMenu; objectName: "settingsMenu"; title: "설정"
        AppMenuItem { action: root.actions.settings; iconName: "settings" }
    }
    AppMenu {
        id: helpMenu; objectName: "helpMenu"; title: "도움말"
        AppMenuItem { action: root.actions.guide }
        AppMenuItem { action: root.actions.shortcutGuide }
        AppMenuItem { action: root.actions.reportIssue }
        MenuSeparator {}
        AppMenuItem { action: root.actions.about }
    }
}
