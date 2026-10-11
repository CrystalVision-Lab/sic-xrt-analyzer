import QtQuick
import QtQuick.Dialogs as PlatformDialogs

QtObject {
    id: root
    property string title: ""
    property int fileMode: PlatformDialogs.FileDialog.OpenFile
    property var nameFilters: []
    property string defaultSuffix: ""
    property int options: 0
    property url currentFolder
    property url selectedFile
    property var selectedFiles: []
    property url selectedFolder
    property bool folderMode: false
    property var parentWindow: null
    property bool visible: false
    readonly property bool managedNative: fileBridge.nativeDialogs.enabled && !(options & PlatformDialogs.FileDialog.DontUseNativeDialog)
    property var fallback: null
    signal accepted()
    signal rejected()
    function open() {
        if (visible) return
        if (managedNative) fileBridge.nativeDialogs.open(root, parentWindow)
        else {
            if (!fallback) fallback = (folderMode ? folderComponent : fileComponent).createObject(root)
            fallback.open()
        }
    }
    function reject() {
        if (managedNative) fileBridge.nativeDialogs.reject(root)
        else if (fallback) fallback.reject()
    }
    function close() { reject() }
    property Component fileComponent: Component {
        PlatformDialogs.FileDialog {
            title: root.title; fileMode: root.fileMode; nameFilters: root.nameFilters
            defaultSuffix: root.defaultSuffix; options: root.options
            currentFolder: root.currentFolder
            onVisibleChanged: root.visible = visible
            onAccepted: {
                root.selectedFile = selectedFile; root.selectedFiles = selectedFiles
                root.accepted()
            }
            onRejected: root.rejected()
        }
    }
    property Component folderComponent: Component {
        PlatformDialogs.FolderDialog {
            title: root.title; options: root.options; currentFolder: root.currentFolder
            onVisibleChanged: root.visible = visible
            onAccepted: { root.selectedFolder = selectedFolder; root.accepted() }
            onRejected: root.rejected()
        }
    }
}
