import QtQuick
import QtQuick.Layouts
RowLayout {
    id: row
    property QtObject theme
    property string label: ""
    property string value: "—"
    property color valueColor: theme.text
    spacing: 8
    implicitHeight: 23
    Text { text: row.label; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: theme.smallSize; Layout.preferredWidth: 86 }
    Text { text: row.value; color: row.valueColor; font.family: theme.monoFontFamily; font.pixelSize: theme.bodySize; horizontalAlignment: Text.AlignRight; elide: Text.ElideMiddle; Layout.fillWidth: true }
}
