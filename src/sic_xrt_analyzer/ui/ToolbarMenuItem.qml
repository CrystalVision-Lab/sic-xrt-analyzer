import QtQuick

AppMenuItem {
    id: root
    leftPadding: checkable ? Math.max(30, (indicator ? indicator.width : 0) + 14) : 12
    // AppMenuItem replaces the style's content layout. Reserve a separate
    // gutter for the existing style indicator in Toolbar popups only.
    Binding {
        target: root.indicator
        property: "x"
        value: root.mirrored ? root.width - root.indicator.width - 8 : 8
    }
}
