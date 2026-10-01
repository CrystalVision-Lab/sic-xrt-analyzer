import QtQuick
import QtQuick.Layouts
RowLayout {
    property QtObject theme
    property string text: ""
    property color ink: theme.muted
    spacing: 6
    Rectangle { width: 5; height: 5; radius: 2; color: parent.ink; Layout.alignment: Qt.AlignVCenter }
    Text { text: parent.text; color: parent.ink; font.family: theme.fontFamily; font.pixelSize: theme.smallSize; font.weight: Font.DemiBold }
}
