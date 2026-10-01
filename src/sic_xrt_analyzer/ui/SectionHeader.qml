import QtQuick
import QtQuick.Layouts
ColumnLayout {
    property QtObject theme
    property string text: ""
    spacing: 6
    Layout.fillWidth: true
    Layout.topMargin: 12
    Text { text: parent.text; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: theme.sectionSize; font.weight: Font.DemiBold; font.letterSpacing: 0.8 }
    Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }
}
