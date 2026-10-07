import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "stackControls"
    property QtObject theme
    property QtObject uiState
    property var actions
    visible: uiState.hasLoadedImage
    spacing: theme.spacingMd

    SectionHeader { theme: root.theme; text: "페이지 탐색"; visible: uiState.pageCount > 1; Layout.fillWidth: true }
    RowLayout {
        visible: uiState.pageCount > 1; Layout.fillWidth: true; spacing: theme.spacingXs
        Text {
            objectName: "currentPageLabel"; text: uiState.loadFlow.currentPageLabel
            color: theme.text; font.pixelSize: theme.bodySize; Layout.fillWidth: true
        }
        AppButton { objectName: "previousPageButton"; theme: root.theme; text: "‹"; tip: "이전 페이지"; enabled: uiState.loadFlow.pageNavigationReady && uiState.stack.requestedPage > 0; onClicked: fileBridge.requestPage(uiState.stack.requestedPage - 1) }
        AppButton { objectName: "nextPageButton"; theme: root.theme; text: "›"; tip: "다음 페이지"; enabled: uiState.loadFlow.pageNavigationReady && uiState.stack.requestedPage < uiState.pageCount - 1; onClicked: fileBridge.requestPage(uiState.stack.requestedPage + 1) }
    }
    AppSlider {
        objectName: "pageSlider"; theme: root.theme; Layout.fillWidth: true
        visible: uiState.pageCount > 1
        from: 0; to: Math.max(1, uiState.pageCount - 1); stepSize: 1
        live: true
        value: uiState.stack.requestedPage; enabled: uiState.loadFlow.pageNavigationReady
        onMoved: fileBridge.requestPage(Math.round(value))
        onPressedChanged: { if (pressed) fileBridge.beginScrub(); else fileBridge.endScrub() }
    }
    Text {
        objectName: "preloadStatus"; visible: uiState.pageCount > 1; Layout.fillWidth: true
        wrapMode: Text.Wrap; font.pixelSize: theme.smallSize
        color: uiState.stack.preloadError ? theme.warning : theme.muted
        text: uiState.loadFlow.stackLabel; Accessible.name: text
    }
    Text {
        objectName: "navigationReadyReason"; visible: !uiState.loadFlow.pageNavigationReady; Layout.fillWidth: true; wrapMode: Text.Wrap
        text: uiState.loadFlow.availableHint + "\n" + uiState.loadFlow.navigationReason; color: theme.muted; font.pixelSize: theme.smallSize
    }
    RowLayout {
        visible: uiState.stack.initialLoading; Layout.fillWidth: true
        AppButton { objectName: "retryStackPreparation"; theme: root.theme; text: "다시 준비"; visible: !!uiState.stack.preloadError; onClicked: fileBridge.retryPreload() }
        AppButton { objectName: "cancelStackPreparation"; theme: root.theme; action: root.actions.closeImage; text: "준비 취소·닫기"; quiet: true }
    }

    SectionHeader { theme: root.theme; text: "밝기 · 대비"; Layout.fillWidth: true; Layout.topMargin: 8 }
    Text { Layout.fillWidth: true; text: "표시 범위 조절 · 원본 데이터 유지"; color: theme.muted; font.pixelSize: theme.smallSize; wrapMode: Text.Wrap }
    RowLayout {
        Layout.fillWidth: true; spacing: theme.spacingSm
        Text { text: "표시 최소"; color: theme.muted; font.pixelSize: theme.smallSize; Layout.fillWidth: true }
        AppTextField {
            objectName: "displayLowField"; Layout.preferredWidth: 90; implicitHeight: theme.controlHeight
            text: Number(uiState.stack.low).toFixed(uiState.dtype.indexOf("float") >= 0 ? 3 : 0)
            color: theme.text; font.pixelSize: theme.smallSize; selectByMouse: true; enabled: uiState.loadFlow.displayRangeReady

            onEditingFinished: fileBridge.setDisplayRange(Number(text), uiState.stack.high)
        }
    }
    AppSlider {
        objectName: "displayLowSlider"; theme: root.theme; Layout.fillWidth: true
        from: uiState.stack.rangeMin; to: uiState.stack.rangeMax
        value: uiState.stack.low; enabled: uiState.loadFlow.displayRangeReady
        onMoved: fileBridge.setDisplayRange(Math.min(value, uiState.stack.high - Math.max(0.000001, (to - from) / 65535)), uiState.stack.high)
    }
    RowLayout {
        Layout.fillWidth: true; spacing: theme.spacingSm
        Text { text: "표시 최대"; color: theme.muted; font.pixelSize: theme.smallSize; Layout.fillWidth: true }
        AppTextField {
            objectName: "displayHighField"; Layout.preferredWidth: 90; implicitHeight: theme.controlHeight
            text: Number(uiState.stack.high).toFixed(uiState.dtype.indexOf("float") >= 0 ? 3 : 0)
            color: theme.text; font.pixelSize: theme.smallSize; selectByMouse: true; enabled: uiState.loadFlow.displayRangeReady

            onEditingFinished: fileBridge.setDisplayRange(uiState.stack.low, Number(text))
        }
    }
    AppSlider {
        objectName: "displayHighSlider"; theme: root.theme; Layout.fillWidth: true
        from: uiState.stack.rangeMin; to: uiState.stack.rangeMax
        value: uiState.stack.high; enabled: uiState.loadFlow.displayRangeReady
        onMoved: fileBridge.setDisplayRange(uiState.stack.low, Math.max(value, uiState.stack.low + Math.max(0.000001, (to - from) / 65535)))
    }
    RowLayout {
        Layout.fillWidth: true; spacing: theme.spacingXs
        AppButton { theme: root.theme; text: "자동 범위"; Layout.fillWidth: true; enabled: uiState.loadFlow.displayRangeReady; onClicked: fileBridge.autoDisplayRange() }
        AppButton { theme: root.theme; text: "초기 범위"; Layout.fillWidth: true; enabled: uiState.loadFlow.displayRangeReady; onClicked: fileBridge.resetDisplayRange() }
    }
    Text {
        Layout.fillWidth: true; font.pixelSize: theme.smallSize; color: theme.muted; wrapMode: Text.Wrap
        text: "초기 범위: " + uiState.stack.rangeOrigin
    }
    SectionHeader { theme: root.theme; text: "조작 안내"; Layout.fillWidth: true; Layout.topMargin: 8 }
    Text {
        Layout.fillWidth: true; font.pixelSize: theme.smallSize; color: theme.muted; wrapMode: Text.Wrap
        text: (uiState.pageCount > 1 ? "슬라이더 · 휠 · 방향키: 페이지 이동\nCtrl+휠: 확대·축소" : "휠: 확대·축소")
    }
    Text {
        Layout.fillWidth: true; font.pixelSize: theme.smallSize; color: theme.muted; wrapMode: Text.Wrap
        text: uiState.stack.frames > 0 ? "ImageJ frames " + uiState.stack.frames + " · 공간 Z 미확정" : "페이지 순서, 공간 간격 미확정"
    }
}
