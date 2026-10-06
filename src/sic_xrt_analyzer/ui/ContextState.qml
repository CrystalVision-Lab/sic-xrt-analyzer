import QtQuick

QtObject {
    // One tab selection is the source of truth. No new automatic context switching.
    property QtObject uiState
    property int tabIndex: 0
    readonly property var keys: ["image", "analysis", "result", "viewer", "roi", "feedback"]
    readonly property string requestedContext: keys[tabIndex] || "image"
    readonly property string activeContext: requestedContext === "image" && !uiState.hasImage ? "idle" : requestedContext
    readonly property string detailContext: requestedContext === "result" && !!uiState.research.selected.id ? "candidate" : activeContext
    function showContext(key) {
        var index = keys.indexOf(key)
        if (index < 0) return false
        tabIndex = index
        return true
    }
}
