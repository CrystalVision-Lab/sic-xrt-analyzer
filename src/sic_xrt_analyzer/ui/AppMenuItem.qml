import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
MenuItem {
    id: root
    property string shortcutLabel: ""
    property string iconName: ""
    leftPadding: checkable ? 30 : 12
    rightPadding: 14
    implicitHeight: 30
    contentItem: RowLayout {
        spacing: 18
        AppIcon { name: root.iconName; visible: root.iconName.length > 0; ink: root.enabled ? root.palette.windowText : "#77828a" }
        Text { text: root.text; color: !root.enabled ? root.palette.disabled.windowText : root.palette.windowText; font: root.font; elide: Text.ElideRight; Layout.fillWidth: true }
        Text { visible: root.shortcutLabel.length > 0; text: root.shortcutLabel; color: root.enabled ? "#929da6" : "#77828a"; font: root.font; horizontalAlignment: Text.AlignRight }
    }
}
