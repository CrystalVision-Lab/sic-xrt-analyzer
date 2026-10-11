import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "stackControls"
    property QtObject theme
    property QtObject uiState
    visible: uiState.hasLoadedImage
    spacing: 10

    SectionHeader { theme: root.theme; text: "페이지 탐색"; visible: uiState.pageCount > 1; Layout.fillWidth: true }
    RowLayout {
        visible: uiState.pageCount > 1; Layout.fillWidth: true; spacing: 6
        Text {
            text: "페이지 " + (uiState.pageIndex + 1) + " / " + uiState.pageCount
            color: theme.text; font.pixelSize: 12; Layout.fillWidth: true
        }
        AppButton { theme: root.theme; text: "‹"; tip: "이전 페이지"; enabled: !uiState.loading && uiState.stack.requestedPage > 0; onClicked: fileBridge.requestPage(uiState.stack.requestedPage - 1) }
        AppButton { theme: root.theme; text: "›"; tip: "다음 페이지"; enabled: !uiState.loading && uiState.stack.requestedPage < uiState.pageCount - 1; onClicked: fileBridge.requestPage(uiState.stack.requestedPage + 1) }
    }
    AppSlider {
        objectName: "pageSlider"; theme: root.theme; Layout.fillWidth: true
        visible: uiState.pageCount > 1
        from: 0; to: Math.max(1, uiState.pageCount - 1); stepSize: 1
        live: true
        value: uiState.stack.requestedPage; enabled: !uiState.loading
        onMoved: fileBridge.requestPage(Math.round(value))
        onPressedChanged: { if (pressed) fileBridge.beginScrub(); else fileBridge.endScrub() }
    }
    Text {
        objectName: "preloadStatus"; visible: uiState.pageCount > 1; Layout.fillWidth: true
        wrapMode: Text.Wrap; font.pixelSize: 11
        color: uiState.stack.preloadError ? theme.warning : theme.muted
        text: uiState.stack.preloadError ? "전체 페이지 준비 실패: " + uiState.stack.preloadError
              : uiState.stack.preload.ready ? "전체 탐색 준비 완료 · " + uiState.stack.preload.total + " 페이지"
              : "전체 페이지 미리 불러오는 중 " + uiState.stack.preload.prepared + " / " + uiState.stack.preload.total
    }
    Text {
        visible: uiState.stack.browsePreview; Layout.fillWidth: true; wrapMode: Text.Wrap
        text: "탐색 미리보기 · 놓으면 정밀 표시"; color: theme.muted; font.pixelSize: 11
    }
    AppButton { theme: root.theme; text: "다시 준비"; visible: !!uiState.stack.preloadError; onClicked: fileBridge.retryPreload() }

    SectionHeader { theme: root.theme; text: "밝기 · 대비"; Layout.fillWidth: true; Layout.topMargin: 8 }
    Text { Layout.fillWidth: true; text: "표시 범위 조절 · 원본 데이터 유지"; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap }
    RowLayout {
        Layout.fillWidth: true; spacing: 8
        Text { text: "표시 최소"; color: theme.muted; font.pixelSize: 11; Layout.fillWidth: true }
        TextField {
            objectName: "displayLowField"; Layout.preferredWidth: 90; implicitHeight: 28
            text: Number(uiState.stack.low).toFixed(uiState.dtype.indexOf("float") >= 0 ? 3 : 0)
            color: theme.text; font.pixelSize: 11; selectByMouse: true; enabled: !uiState.loading
            background: Rectangle { color: theme.surface; border.color: theme.border; radius: 2 }
            onEditingFinished: fileBridge.setDisplayRange(Number(text), uiState.stack.high)
        }
    }
    AppSlider {
        objectName: "displayLowSlider"; theme: root.theme; Layout.fillWidth: true
        from: uiState.stack.rangeMin; to: uiState.stack.rangeMax
        value: uiState.stack.low; enabled: !uiState.loading
        onMoved: fileBridge.setDisplayRange(Math.min(value, uiState.stack.high - Math.max(0.000001, (to - from) / 65535)), uiState.stack.high)
    }
    RowLayout {
        Layout.fillWidth: true; spacing: 8
        Text { text: "표시 최대"; color: theme.muted; font.pixelSize: 11; Layout.fillWidth: true }
        TextField {
            objectName: "displayHighField"; Layout.preferredWidth: 90; implicitHeight: 28
            text: Number(uiState.stack.high).toFixed(uiState.dtype.indexOf("float") >= 0 ? 3 : 0)
            color: theme.text; font.pixelSize: 11; selectByMouse: true; enabled: !uiState.loading
            background: Rectangle { color: theme.surface; border.color: theme.border; radius: 2 }
            onEditingFinished: fileBridge.setDisplayRange(uiState.stack.low, Number(text))
        }
    }
    AppSlider {
        objectName: "displayHighSlider"; theme: root.theme; Layout.fillWidth: true
        from: uiState.stack.rangeMin; to: uiState.stack.rangeMax
        value: uiState.stack.high; enabled: !uiState.loading
        onMoved: fileBridge.setDisplayRange(uiState.stack.low, Math.max(value, uiState.stack.low + Math.max(0.000001, (to - from) / 65535)))
    }
    RowLayout {
        Layout.fillWidth: true; spacing: 6
        AppButton { theme: root.theme; text: "자동 범위"; Layout.fillWidth: true; enabled: !uiState.loading; onClicked: fileBridge.autoDisplayRange() }
        AppButton { theme: root.theme; text: "초기 범위"; Layout.fillWidth: true; enabled: !uiState.loading; onClicked: fileBridge.resetDisplayRange() }
    }
    Text {
        Layout.fillWidth: true; font.pixelSize: 11; color: theme.muted; wrapMode: Text.Wrap
        text: "초기 범위: " + uiState.stack.rangeOrigin
    }
    SectionHeader { theme: root.theme; text: "조작 안내"; Layout.fillWidth: true; Layout.topMargin: 8 }
    Text {
        Layout.fillWidth: true; font.pixelSize: 11; color: theme.muted; wrapMode: Text.Wrap
        text: (uiState.pageCount > 1 ? "슬라이더 · 휠 · 방향키: 페이지 이동\nCtrl+휠: 확대·축소" : "휠: 확대·축소")
    }
    Text {
        Layout.fillWidth: true; font.pixelSize: 11; color: theme.muted; wrapMode: Text.Wrap
        text: uiState.stack.frames > 0 ? "ImageJ frames " + uiState.stack.frames + " · 공간 Z 미확정" : "페이지 순서, 공간 간격 미확정"
    }
}
