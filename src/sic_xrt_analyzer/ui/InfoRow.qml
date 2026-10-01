import QtQuick
import QtQuick.Layouts

RowLayout {
    id: row
    property QtObject theme
    property string label: ""
    property string value: "—"
    spacing: 8
    implicitHeight: 28

    Text {
        text: row.label
        color: theme.muted
        font.family: theme.fontFamily
        font.pixelSize: theme.bodySize
        Layout.preferredWidth: 84
        elide: Text.ElideRight
    }
    Text {
        text: row.value
        color: theme.text
        font.family: theme.fontFamily
        font.pixelSize: theme.bodySize
        horizontalAlignment: Text.AlignRight
        elide: Text.ElideMiddle
        Layout.fillWidth: true
    }
}
