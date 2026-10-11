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
    background: Rectangle { color: theme.panel }
    delegate: MenuBarItem {
        id: barItem
        visible: !menu || menu.available
        implicitHeight: 30; implicitWidth: visible ? contentItem.implicitWidth + 24 : 0
        contentItem: Text { text: barItem.text; color: theme.text; font.family: theme.fontFamily; font.pixelSize: theme.bodySize; verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignHCenter }
        background: Rectangle { color: barItem.highlighted ? theme.accentPale : theme.panel }
    }
    Shortcut { sequence: "Alt+F"; onActivated: fileMenu.open() }
    Shortcut { sequence: "Alt+E"; onActivated: editMenu.open() }
    Shortcut { sequence: "Alt+V"; onActivated: viewMenu.open() }
    Shortcut { sequence: "Alt+W"; onActivated: workspaceMenu.open() }
    Shortcut { sequence: "Alt+A"; onActivated: analysisMenu.open() }
    Shortcut { sequence: "Alt+T"; enabled: root.uiState.stackFeaturesVisible; onActivated: toolsMenu.open() }
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
            AppMenuItem { text: "최근 파일 없음"; enabled: false; rowAvailable: root.fileBridge.recentFiles.length === 0 }
            MenuSeparator {}
            AppMenuItem { text: "목록 비우기"; enabled: root.fileBridge.recentFiles.length > 0; onTriggered: root.fileBridge.clearRecentFiles() }
        }
        AppMenuItem { action: root.actions.demo }
        AppMenuItem { action: root.actions.importRois; iconName: "roi" }
        MenuSeparator {}
        AppMenuItem { text: "새 분석 프로젝트"; enabled: false }
        AppMenuItem { text: "프로젝트 열기…"; enabled: false }
        AppMenuItem { action: root.actions.save; shortcutLabel: "Ctrl+S" }
        AppMenuItem { text: "측정 결과 TSV 저장…"; rowAvailable: root.uiState.stackFeaturesVisible; action: root.actions.advanced.saveMeasurements }
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
        AppMenuItem { text: "ROI 실행 취소"; shortcutLabel: "Ctrl+Z"; enabled: root.uiState.importedRois.canUndo; onTriggered: root.fileBridge.roiHistory(false) }
        AppMenuItem { text: "ROI 다시 실행"; shortcutLabel: "Ctrl+Y"; enabled: root.uiState.importedRois.canRedo; onTriggered: root.fileBridge.roiHistory(true) }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "픽셀 그리기 실행 취소"; enabled: root.uiState.loadFlow.recordReady; onTriggered: root.fileBridge.imagej.execute("command", "Undo", "", false) }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "선택을 그리기"; onTriggered: root.hostWindow.imagejCommand("Draw", "") }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "선택을 채우기"; onTriggered: root.hostWindow.imagejCommand("Fill", "") }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "선택을 지우기"; onTriggered: root.hostWindow.imagejCommand("Clear", "") }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "선택 외부 지우기"; onTriggered: root.hostWindow.imagejCommand("Clear Outside", "") }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "도구 옵션…"; action: root.actions.advanced.tools }
        AppMenuItem { action: root.actions.settings; iconName: "settings" }
        MenuSeparator {}
        AppMenuItem { action: root.actions.copyRoi }
    }
    AppMenu {
        id: viewMenu; objectName: "viewMenu"; title: "이미지 (Image)"
        AppMenu { title: "형식 (Type)"; available: root.uiState.stackFeaturesVisible
            AppMenuItem { text: "8-bit"; onTriggered: root.hostWindow.imagejCommand("8-bit", "") }
            AppMenuItem { text: "16-bit"; onTriggered: root.hostWindow.imagejCommand("16-bit", "") }
            AppMenuItem { text: "32-bit"; onTriggered: root.hostWindow.imagejCommand("32-bit", "") }
            AppMenuItem { text: "RGB Color"; onTriggered: root.hostWindow.imagejCommand("RGB Color", "") }
        }
        AppMenu { title: "조정 (Adjust)"
            AppMenuItem { text: "밝기 / 대비…"; action: root.actions.viewerSettings }
            AppMenuItem { text: "자동 표시 범위"; onTriggered: root.fileBridge.autoDisplayRange() }
            AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "임계값 / 이진화…"; onTriggered: root.hostWindow.imagejCommand("Convert to Mask", "method=Default background=Dark") }
            AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "크기 변경…"; onTriggered: root.hostWindow.imagejCommand("Size...", "width=1024 height=1024 interpolation=Bilinear") }
        }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "복제…"; onTriggered: root.hostWindow.imagejCommand("Duplicate...", "") }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "ROI로 자르기"; onTriggered: root.hostWindow.imagejCommand("Crop", "") }
        AppMenu { title: "변환 (Transform)"; available: root.uiState.stackFeaturesVisible
            AppMenuItem { text: "수평 뒤집기"; onTriggered: root.hostWindow.imagejCommand("Flip Horizontally", "") }
            AppMenuItem { text: "수직 뒤집기"; onTriggered: root.hostWindow.imagejCommand("Flip Vertically", "") }
            AppMenuItem { text: "오른쪽 90° 회전"; onTriggered: root.hostWindow.imagejCommand("Rotate 90 Degrees Right", "") }
            AppMenuItem { text: "왼쪽 90° 회전"; onTriggered: root.hostWindow.imagejCommand("Rotate 90 Degrees Left", "") }
            AppMenuItem { text: "회전…"; onTriggered: root.hostWindow.imagejCommand("Rotate...", "angle=15 interpolation=Bilinear") }
        }
        MenuSeparator {}
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
        id: processMenu; objectName: "processMenu"; title: "처리 (Process)"; available: root.uiState.stackFeaturesVisible
        AppMenuItem { text: "Smooth"; onTriggered: root.hostWindow.imagejCommand("Smooth", "") }
        AppMenuItem { text: "Sharpen"; onTriggered: root.hostWindow.imagejCommand("Sharpen", "") }
        AppMenuItem { text: "Find Edges"; onTriggered: root.hostWindow.imagejCommand("Find Edges", "") }
        AppMenuItem { text: "Enhance Contrast…"; onTriggered: root.hostWindow.imagejCommand("Enhance Contrast...", "saturated=0.35 normalize") }
        AppMenu { title: "필터 (Filters)"
            AppMenuItem { text: "Gaussian Blur…"; onTriggered: root.hostWindow.imagejCommand("Gaussian Blur...", "sigma=2") }
            AppMenuItem { text: "Median…"; onTriggered: root.hostWindow.imagejCommand("Median...", "radius=2") }
            AppMenuItem { text: "Mean…"; onTriggered: root.hostWindow.imagejCommand("Mean...", "radius=2") }
            AppMenuItem { text: "Minimum…"; onTriggered: root.hostWindow.imagejCommand("Minimum...", "radius=2") }
            AppMenuItem { text: "Maximum…"; onTriggered: root.hostWindow.imagejCommand("Maximum...", "radius=2") }
            AppMenuItem { text: "Variance…"; onTriggered: root.hostWindow.imagejCommand("Variance...", "radius=2") }
            AppMenuItem { text: "Unsharp Mask…"; onTriggered: root.hostWindow.imagejCommand("Unsharp Mask...", "radius=2 mask=0.60") }
        }
        AppMenu { title: "이진 이미지 (Binary)"
            Repeater { model: ["Make Binary", "Erode", "Dilate", "Open", "Close-", "Outline", "Skeletonize", "Fill Holes", "Watershed", "Distance Map"]
                AppMenuItem { required property string modelData; text: modelData; onTriggered: root.hostWindow.imagejCommand(modelData, "") }
            }
        }
        AppMenu { title: "노이즈 / 배경"
            AppMenuItem { text: "Despeckle"; onTriggered: root.hostWindow.imagejCommand("Despeckle", "") }
            AppMenuItem { text: "Remove Outliers…"; onTriggered: root.hostWindow.imagejCommand("Remove Outliers...", "radius=2 threshold=50 which=Bright") }
            AppMenuItem { text: "Subtract Background…"; onTriggered: root.hostWindow.imagejCommand("Subtract Background...", "rolling=50") }
        }
        AppMenuItem { text: "Invert"; onTriggered: root.hostWindow.imagejCommand("Invert", "") }
        AppMenuItem { text: "이미지 계산…"; onTriggered: root.hostWindow.imagejMacro() }
        AppMenuItem { text: "FFT"; onTriggered: root.hostWindow.imagejCommand("FFT", "") }
        AppMenuItem { text: "모든 ImageJ 명령…"; action: root.actions.advanced.catalog }
    }
    AppMenu {
        id: analysisMenu; objectName: "analysisMenu"; title: "분석 (Analyze)"
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "측정 (Measure)"; enabled: root.uiState.loadFlow.recordReady; onTriggered: root.fileBridge.imagej.execute("command", "Measure", "", false) }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "측정 항목…"; onTriggered: root.hostWindow.imagejCommand("Set Measurements...", "area mean standard min centroid perimeter shape redirect=None decimal=3") }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "히스토그램"; enabled: root.uiState.loadFlow.recordReady; onTriggered: root.hostWindow.imagejStatistics("Histogram") }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "선 프로파일"; enabled: root.uiState.loadFlow.recordReady; onTriggered: root.hostWindow.imagejStatistics("Profile") }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "입자 분석…"; onTriggered: root.hostWindow.imagejCommand("Analyze Particles...", "size=0-Infinity circularity=0.00-1.00 show=Nothing display clear") }
        AppMenuItem { objectName: "stackMeasurementMenuItem"; rowAvailable: root.uiState.stackFeaturesVisible; text: "스케일 · 길이 / 면적 / 개수 측정…"; action: root.actions.advanced.measurement }
        AppMenuItem { text: "ROI 관리자"; action: root.actions.advanced.roiManager }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "결과표"; action: root.actions.advanced.results }
        MenuSeparator {}
        AppMenuItem { objectName: "menuRoiTool"; action: root.actions.roi; shortcutLabel: "R" }
        AppMenuItem { action: root.actions.clearRoi }
        MenuSeparator {}
        AppMenuItem { objectName: "menuRunAnalysis"; action: root.actions.run; iconName: "run"; ToolTip.text: root.uiState.analysisReason; ToolTip.visible: hovered }
        AppMenuItem { objectName: "menuCancelAnalysis"; action: root.actions.cancelAnalysis }
        AppMenuItem { text: "결과 보기"; enabled: root.uiState.hasResult; onTriggered: root.hostWindow.openContext("result") }
    }
    AppMenu {
        id: toolsMenu; objectName: "toolsMenu"; title: "플러그인 (Plugins)"; available: root.uiState.stackFeaturesVisible
        AppMenuItem { objectName: "menuMacroItem"; text: "매크로 편집 / 실행…"; action: root.actions.advanced.macro }
        AppMenuItem { objectName: "menuPluginItem"; text: "Java 플러그인 등록 / 실행…"; action: root.actions.advanced.plugin }
        AppMenuItem { objectName: "menuFijiItem"; text: "Fiji / ImageJ2 명령…"; action: root.actions.advanced.modern }
        AppMenuItem { objectName: "menuImagejCommandsItem"; text: "명령 검색…"; action: root.actions.advanced.catalog }
        AppMenuItem { text: "도구 옵션…"; action: root.actions.advanced.tools }
        AppMenuItem { action: root.actions.modelInfo }
    }
    AppMenu {
        id: settingsMenu; objectName: "settingsMenu"; title: "창 (Window)"
        AppMenu {
            id: workspaceMenu; objectName: "workspaceMenu"; title: "작업 영역"
            AppMenuItem { text: "이미지 분석"; onTriggered: root.hostWindow.selectWorkspace(0) }
            AppMenuItem { text: "Wafer Map"; onTriggered: root.hostWindow.selectWorkspace(1) }
            AppMenuItem { text: "이미지 정합"; onTriggered: root.hostWindow.selectWorkspace(2) }
            AppMenuItem { text: "3D 뷰어"; onTriggered: root.hostWindow.selectWorkspace(3) }
        }
        AppMenuItem { rowAvailable: root.uiState.stackFeaturesVisible; text: "ImageJ 작업창"; action: root.actions.advanced.results }
        AppMenuItem { action: root.actions.resetLayout }
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
