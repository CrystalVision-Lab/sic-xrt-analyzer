import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    objectName: "fileToolGroup"
    property QtObject theme
    property var actions
    spacing: 5
        AppButton { theme: root.theme; action: root.actions.open; text: "열기"; iconName: "open"; tip: "TIFF/JPG 열기 · Ctrl+O" }
        AppButton { theme: root.theme; action: root.actions.save; text: ""; iconName: "save"; tip: "이미지 파일의 새 복사본 저장 · Ctrl+S" }

}
