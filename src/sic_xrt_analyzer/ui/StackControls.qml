import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "stackControls"
    property QtObject theme
    property QtObject uiState
    visible: uiState.hasLoadedImage
    implicitHeight: visible ? (uiState.pageCount > 1 ? 156 : 100) : 0
    color: theme.viewerHeader
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 10; spacing: 6
        RowLayout {
            visible: uiState.pageCount > 1; Layout.fillWidth: true; spacing: 8
            Text { text: "페이지 " + (uiState.pageIndex + 1) + " / " + uiState.pageCount; color: theme.text; font.pixelSize: 12; Layout.preferredWidth: 125 }
            AppButton { theme: root.theme; text: "‹"; enabled: !uiState.loading && uiState.stack.requestedPage > 0; onClicked: fileBridge.requestPage(uiState.stack.requestedPage - 1) }
            AppSlider {
                objectName: "pageSlider"; theme: root.theme; Layout.fillWidth: true
                from: 0; to: Math.max(1, uiState.pageCount - 1); stepSize: 1
                live: true
                value: uiState.stack.requestedPage; enabled: !uiState.loading
                onMoved: fileBridge.requestPage(Math.round(value))
                onPressedChanged: { if (pressed) fileBridge.beginScrub(); else fileBridge.endScrub() }
            }
            AppButton { theme: root.theme; text: "›"; enabled: !uiState.loading && uiState.stack.requestedPage < uiState.pageCount - 1; onClicked: fileBridge.requestPage(uiState.stack.requestedPage + 1) }
        }
        RowLayout {
            visible: uiState.pageCount > 1; Layout.fillWidth: true; spacing: 8
            Text {
                objectName: "preloadStatus"; Layout.fillWidth: true; elide: Text.ElideRight
                font.pixelSize: 11; color: uiState.stack.preloadError ? theme.warning : theme.muted
                text: uiState.stack.preloadError ? "전체 페이지 준비 실패: " + uiState.stack.preloadError
                      : uiState.stack.preload.ready ? "전체 탐색 준비 완료 · " + uiState.stack.preload.total + " 페이지 · 드래그로 연속 탐색"
                      : "전체 페이지 미리 불러오는 중 " + uiState.stack.preload.prepared + " / " + uiState.stack.preload.total + " · 완료 후 드래그 즉시 표시"
            }
            Text { visible: uiState.stack.browsePreview; text: "탐색 미리보기 · 놓으면 정밀 표시"; color: theme.muted; font.pixelSize: 10 }
            AppButton { theme: root.theme; text: "다시 준비"; visible: !!uiState.stack.preloadError; onClicked: fileBridge.retryPreload() }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            Text { text: "표시 최소"; color: theme.muted; font.pixelSize: 11; Layout.preferredWidth: 66 }
            AppSlider {
                objectName: "displayLowSlider"; theme: root.theme; Layout.fillWidth: true
                from: uiState.stack.rangeMin; to: uiState.stack.rangeMax
                value: uiState.stack.low; enabled: !uiState.loading
                onMoved: fileBridge.setDisplayRange(Math.min(value, uiState.stack.high - Math.max(0.000001, (to - from) / 65535)), uiState.stack.high)
            }
            TextField {
                objectName: "displayLowField"; Layout.preferredWidth: 84; implicitHeight: 24
                text: Number(uiState.stack.low).toFixed(uiState.dtype.indexOf("float") >= 0 ? 3 : 0)
                color: theme.text; font.pixelSize: 11; selectByMouse: true; enabled: !uiState.loading
                background: Rectangle { color: theme.surface; border.color: theme.border; radius: 2 }
                onEditingFinished: fileBridge.setDisplayRange(Number(text), uiState.stack.high)
            }
            AppButton { theme: root.theme; text: "자동"; enabled: !uiState.loading; onClicked: fileBridge.autoDisplayRange() }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            Text { text: "표시 최대"; color: theme.muted; font.pixelSize: 11; Layout.preferredWidth: 66 }
            AppSlider {
                objectName: "displayHighSlider"; theme: root.theme; Layout.fillWidth: true
                from: uiState.stack.rangeMin; to: uiState.stack.rangeMax
                value: uiState.stack.high; enabled: !uiState.loading
                onMoved: fileBridge.setDisplayRange(uiState.stack.low, Math.max(value, uiState.stack.low + Math.max(0.000001, (to - from) / 65535)))
            }
            TextField {
                objectName: "displayHighField"; Layout.preferredWidth: 84; implicitHeight: 24
                text: Number(uiState.stack.high).toFixed(uiState.dtype.indexOf("float") >= 0 ? 3 : 0)
                color: theme.text; font.pixelSize: 11; selectByMouse: true; enabled: !uiState.loading
                background: Rectangle { color: theme.surface; border.color: theme.border; radius: 2 }
                onEditingFinished: fileBridge.setDisplayRange(uiState.stack.low, Number(text))
            }
            AppButton { theme: root.theme; text: "초기"; enabled: !uiState.loading; onClicked: fileBridge.resetDisplayRange() }
        }
        Text {
            Layout.fillWidth: true; font.pixelSize: 10; color: theme.muted; elide: Text.ElideRight
            text: (uiState.pageCount > 1 ? "휠 / 방향키: 페이지 · Ctrl+휠: 확대 · " : "") + "초기 범위: " + uiState.stack.rangeOrigin + (uiState.stack.frames > 0 ? " · ImageJ frames " + uiState.stack.frames + " (공간 Z 미확정)" : " · 페이지 순서, 공간 간격 미확정")
        }
    }
}
