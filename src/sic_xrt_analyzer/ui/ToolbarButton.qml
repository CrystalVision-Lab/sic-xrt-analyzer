import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AppButton {
    id: control
    property string toolName: ""
    property real labelSize: theme.bodySize
    quiet: true
    implicitHeight: 32
    implicitWidth: Math.max(32, toolbarContent.implicitWidth + 16)
    Accessible.name: text || tip
    Accessible.description: tip
    contentItem: Item {
        implicitWidth: toolbarContent.implicitWidth
        implicitHeight: toolbarContent.implicitHeight
        RowLayout {
            id: toolbarContent
            anchors.centerIn: parent; spacing: 6
            ToolGlyph { visible: !!control.toolName; tool: control.toolName; ink: !control.enabled ? control.theme.disabled : control.checked ? control.theme.accent : control.theme.text; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
            AppIcon { visible: !control.toolName && !!control.iconName; name: control.iconName; ink: !control.enabled ? control.theme.disabled : control.checked ? control.theme.accent : control.theme.text; Layout.preferredWidth: 16; Layout.preferredHeight: 16 }
            Text { visible: !!control.text; text: control.text; color: !control.enabled ? control.theme.disabled : control.checked ? control.theme.accent : control.theme.text; font.family: control.theme.fontFamily; font.pixelSize: control.labelSize; font.weight: control.checked ? Font.DemiBold : Font.Normal }
        }
    }
}
