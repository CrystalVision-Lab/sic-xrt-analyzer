import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    objectName: "imagejNativeForm"
    property QtObject theme
    property var specification: ({})
    property var values: ({})
    onSpecificationChanged: values = Object.assign({}, specification.values || {})
    function setParameter(key, value) {
        var next = Object.assign({}, values)
        next[key] = value
        values = next
    }
    spacing: theme.spacingSm
    Text {
        Layout.fillWidth: true
        text: root.specification.title || ""
        color: root.theme.text
        font.pixelSize: root.theme.bodySize
        font.bold: true
    }
    Repeater {
        model: root.specification.fields || []
        delegate: RowLayout {
            required property var modelData
            Layout.fillWidth: true
            Text {
                Layout.preferredWidth: 230
                Layout.maximumWidth: 230
                wrapMode: Text.Wrap
                text: modelData.label
                color: root.theme.text
                font.pixelSize: root.theme.bodySize
            }
            AppTextField {
                objectName: "imagejParameter_" + modelData.key
                visualTheme: root.theme
                Layout.fillWidth: true
                visible: modelData.kind === "number"
                text: String((root.specification.values || {})[modelData.key] ?? "")
                Accessible.name: modelData.label
                placeholderText: modelData.kind === "number" ? modelData.minimum + "–" + modelData.maximum : ""
                onTextEdited: root.setParameter(modelData.key, text)
            }
            AppCheckBox {
                objectName: "imagejParameter_" + modelData.key
                theme: root.theme
                visible: modelData.kind === "boolean"
                checked: (root.specification.values || {})[modelData.key] === true
                Accessible.name: modelData.label
                onClicked: root.setParameter(modelData.key, checked)
            }
            AppComboBox {
                objectName: "imagejParameter_" + modelData.key
                theme: root.theme
                Layout.fillWidth: true
                visible: modelData.kind === "choice"
                model: modelData.labels || []
                currentIndex: (modelData.choices || []).indexOf((root.specification.values || {})[modelData.key])
                Accessible.name: modelData.label
                onActivated: root.setParameter(modelData.key, modelData.choices[currentIndex])
            }
        }
    }
    Text {
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        color: root.theme.muted
        font.pixelSize: root.theme.smallSize
        text: root.specification.wholeImage
              ? "전체 페이지의 배경을 제거합니다. 선택 ROI가 있으면 해제해 주세요. 결과는 새 작업 이미지로 표시합니다."
              : "현재 페이지의 선택 ROI를 처리합니다. 선택 ROI가 없으면 전체 페이지를 처리합니다. 결과는 새 작업 이미지로 표시합니다."
    }
}
