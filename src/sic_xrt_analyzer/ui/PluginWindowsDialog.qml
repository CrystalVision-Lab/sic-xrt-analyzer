import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import XrtViewer 1.0

SurfaceDialog {
    id: root
    objectName: "pluginWindowsDialog"
    property QtObject theme
    property var backend
    property var nativeWindows: backend.pluginWindows
    readonly property var activeHost: nativeHosts.itemAt(tabs.currentIndex)
    title: "플러그인 설정 / 결과"
    modal: false
    width: Math.min(parent.width - 40, Math.max(500, activeWindow.width + 24))
    height: Math.min(parent.height - 60, Math.max(300, activeWindow.height + 100))
    property var activeWindow: nativeWindows.length ? nativeWindows[Math.max(0,Math.min(tabs.currentIndex, nativeWindows.length-1))] : ({width:500,height:300})
    closePolicy: Popup.NoAutoClose
    onNativeWindowsChanged: {
        if (nativeWindows.length) open(); else close()
        if (tabs.currentIndex >= nativeWindows.length) tabs.currentIndex = Math.max(0,nativeWindows.length-1)
    }
    contentItem: ColumnLayout {
        TabBar {
            id: tabs; Layout.fillWidth: true
            Repeater { model: root.nativeWindows
                TabButton { required property var modelData; text: modelData.title || "플러그인 창" }
            }
        }
        StackLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; currentIndex: tabs.currentIndex
            Repeater { id: nativeHosts; model: root.nativeWindows
                NativePluginWindow {
                    id: host; objectName: "nativePluginHost"; required property var modelData; nativeId: String(modelData.id)
                    Component.onDestruction: host.release()
                    Timer { interval: 80; running: host.visible; repeat: true; onTriggered: host.synchronize() }
                }
            }
        }
        RowLayout {
            Text { Layout.fillWidth: true; color: theme.muted; text: "플러그인의 설정을 입력하고 확인 버튼을 누르세요." }
            AppButton { theme: root.theme; text: "작업 취소 / 창 닫기"; onClicked: backend.cancel() }
        }
    }
}
