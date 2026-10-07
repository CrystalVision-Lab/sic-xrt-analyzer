import QtQuick
import QtQuick.Layouts
ColumnLayout {
    property QtObject theme
    property string text: ""
    spacing: theme.spacingXs
    Layout.fillWidth: true
    Layout.topMargin: theme.spacingMd
    Text { text: parent.text; color: theme.text; font.family: theme.fontFamily; font.pixelSize: theme.sectionSize; font.weight: Font.Medium }
}
