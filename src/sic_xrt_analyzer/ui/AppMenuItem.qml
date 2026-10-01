import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

MenuItem {
    id: root
    property string shortcutLabel: ""
    leftPadding: checkable ? 32 : 12
    rightPadding: 14
    contentItem: RowLayout {
        spacing: 18
        Text {
            text: root.text
            color: root.enabled ? "#203038" : "#a5b1b7"
            font.family: "Segoe UI"
            font.pixelSize: 13
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
        Text {
            visible: root.shortcutLabel.length > 0
            text: root.shortcutLabel
            color: root.enabled ? "#647680" : "#a5b1b7"
            font.family: "Segoe UI"
            font.pixelSize: 12
            horizontalAlignment: Text.AlignRight
        }
    }
}
