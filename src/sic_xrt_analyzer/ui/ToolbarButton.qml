import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AppButton {
    id: control
    property string toolName: ""
    quiet: true
    implicitHeight: theme.toolbarButtonHeight
    implicitWidth: Math.max(32, toolbarContent.implicitWidth + 16)
    Accessible.name: text || tip
    Accessible.description: tip
    contentItem: Item {
        implicitWidth: toolbarContent.implicitWidth
        implicitHeight: toolbarContent.implicitHeight
        RowLayout {
            id: toolbarContent
            anchors.centerIn: parent; spacing: theme.spacingXs
            ToolGlyph { visible: !!control.toolName; tool: control.toolName; ink: !control.enabled ? control.theme.disabled : control.checked ? control.theme.accent : control.theme.text; Layout.preferredWidth: theme.toolbarIconSize; Layout.preferredHeight: theme.toolbarIconSize }
            AppIcon { visible: !control.toolName && !!control.iconName; name: control.iconName; ink: !control.enabled ? control.theme.disabled : control.checked ? control.theme.accent : control.theme.text; Layout.preferredWidth: theme.toolbarIconSize; Layout.preferredHeight: theme.toolbarIconSize }
            Text { visible: !!control.text; text: control.text; color: !control.enabled ? control.theme.disabled : control.checked ? control.theme.accent : control.theme.text; font.family: control.theme.fontFamily; font.pixelSize: control.labelSize; font.weight: control.checked ? Font.DemiBold : Font.Normal }
        }
    }
}
