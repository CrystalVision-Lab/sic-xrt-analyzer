import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
MenuItem {
    id: root
    property string shortcutLabel: ""
    property string iconName: ""
    property QtObject visualTheme: Theme {}
    visible: !subMenu || subMenu.available
    leftPadding: checkable ? 30 : 12
    rightPadding: visualTheme.spacingMd
    implicitHeight: visible ? visualTheme.menuRowHeight : 0
    font.pixelSize: visualTheme.bodySize
    ToolTip.text: text
    ToolTip.visible: hovered && menuText.truncated
    contentItem: RowLayout {
        spacing: root.visualTheme.spacingLg
        AppIcon { name: root.iconName; visible: root.iconName.length > 0; ink: root.enabled ? root.palette.windowText : root.visualTheme.disabled; Layout.preferredWidth: root.visualTheme.iconSize; Layout.preferredHeight: root.visualTheme.iconSize }
        Text { id: menuText; text: root.text; color: !root.enabled ? root.palette.disabled.windowText : root.palette.windowText; font: root.font; elide: Text.ElideRight; Layout.fillWidth: true }
        Text { visible: root.shortcutLabel.length > 0; text: root.shortcutLabel; color: root.enabled ? root.visualTheme.muted : root.visualTheme.disabled; font.family: root.font.family; font.pixelSize: root.visualTheme.captionSize; horizontalAlignment: Text.AlignRight }
    }
}
