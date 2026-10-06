import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    // Compatibility surface; PrimaryToolbar now uses grouped dropdowns.
    id: root
    property QtObject theme
    property QtObject uiState
    property var hostWindow
    spacing: 3
    StackViewerToolGroup { theme: root.theme; uiState: root.uiState; hostWindow: root.hostWindow }
    AdvancedToolGroup { theme: root.theme; uiState: root.uiState; actions: root.hostWindow.commands; hostWindow: root.hostWindow }
    Item { Layout.fillWidth: true }
    Text { text: fileBridge.imagej.state.busy ? "ImageJ 처리 중…" : "ImageJ 도구"; color: root.theme.muted; font.pixelSize: 11 }
}
