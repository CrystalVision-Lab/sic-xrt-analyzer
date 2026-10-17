import QtQuick
QtObject {
    readonly property color window: "#12191c"
    // Defect classes: Okabe-Ito colours, always paired with a shape (BPD ◆/outline, TED ▲, TSD ■).
    readonly property color classBpd: "#e69f00"
    readonly property color classTed: "#56b4e9"
    readonly property color classTsd: "#cc79a7"
    readonly property color classOther: "#bbbbbb"
    // Selected candidate on the image; yellow stays visible on bright XRT backgrounds.
    readonly property color selection: "#fff04a"
    readonly property color panel: "#1b2429"
    readonly property color toolbar: "#1b2429"
    readonly property color surface: "#263239"
    readonly property color hover: "#35474c"
    readonly property color border: "#3a484f"
    readonly property color text: "#eaf0f2"
    readonly property color muted: "#a9b9bf"
    readonly property color disabled: "#95a2b0"
    readonly property color borderSubtle: "#2a3643"
    readonly property color accent: "#7cdecd"
    readonly property color accentText: "#092a2a"
    readonly property color accentPale: "#263e3d"
    readonly property color success: "#68ba8b"
    readonly property color warning: "#d6ac64"
    readonly property color error: "#e68181"
    readonly property color viewer: "#111518"
    readonly property color viewerHeader: "#181e23"
    readonly property color viewerText: text
    readonly property color viewerMuted: muted
    readonly property string fontFamily: "Segoe UI"
    readonly property string monoFontFamily: "Consolas"
    readonly property int space: 8
    readonly property int spacingXs: 4
    readonly property int spacingSm: 8
    readonly property int spacingMd: 12
    readonly property int spacingLg: 16
    readonly property int spacingXl: 24
    readonly property int radiusSm: 8
    readonly property int radiusControl: 9
    readonly property int radiusDialog: 18
    readonly property int radiusPanel: 12
    readonly property int compactHeight: 32
    readonly property int primaryHeight: 40
    readonly property int toolbarButtonHeight: 36
    readonly property int menuRowHeight: 36
    readonly property int listRowHeight: 44
    readonly property int iconSize: 18
    readonly property int toolbarIconSize: 20
    readonly property int metricSize: 22
    readonly property int panelWidth: 282
    readonly property int navigationWidth: 184
    readonly property int commandBarHeight: 52
    readonly property int toolbarHeight: 80
    readonly property int statusHeight: 28
    readonly property int controlHeight: 36
    readonly property int bodySize: 14
    readonly property int smallSize: 12
    readonly property int captionSize: 11
    readonly property int sectionSize: 14
    readonly property int emptyTitleSize: 17
    readonly property int titleSize: 18
}
