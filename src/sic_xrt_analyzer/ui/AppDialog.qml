import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Dialog {
    id: root
    property QtObject theme
    property string bodyText: ""
    property string acceptText: "확인"
    property bool cancelVisible: false
    modal: true
    padding: 18
    width: 460
    background: Rectangle { color: theme.panel; border.color: theme.border; radius: 5 }
    header: Rectangle {
        implicitHeight: 46; color: theme.toolbar
        Text { anchors.fill: parent; anchors.margins: 16; text: root.title; color: theme.text; font.family: theme.fontFamily; font.pixelSize: theme.titleSize; verticalAlignment: Text.AlignVCenter; font.weight: Font.DemiBold }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border }
    }
    contentItem: Text { text: root.bodyText; color: theme.text; font.family: theme.fontFamily; font.pixelSize: theme.bodySize; wrapMode: Text.WordWrap; lineHeight: 1.4 }
    footer: Rectangle {
        implicitHeight: 52; color: theme.toolbar
        Rectangle { width: parent.width; height: 1; color: theme.border }
        RowLayout {
            anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; spacing: 8
            AppButton { visible: root.cancelVisible; theme: root.theme; text: "취소"; onClicked: root.reject() }
            AppButton { theme: root.theme; text: root.acceptText; primary: true; onClicked: root.accept() }
        }
    }
}
