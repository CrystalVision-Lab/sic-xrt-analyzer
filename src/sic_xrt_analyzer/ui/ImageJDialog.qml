import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

Dialog {
    id: root
    objectName: "imagejDialog"
    property QtObject theme
    property var backend
    property var runtimeState: backend.state
    property string mode: "command"
    property string selectedCommand: "Invert"
    property alias tabsIndex: tabs.currentIndex
    property alias wholeStack: stackInput.checked
    modal: false; title: "ImageJ · 명령 / 매크로 / 플러그인 / 결과"
    width: 850; height: 640
    function showCommand(command, options) { mode = "command"; stackInput.checked = false; commandField.text = command; optionsField.text = options || ""; tabs.currentIndex = 0; open() }
    function showMacro() { mode = "macro"; tabs.currentIndex = 0; open() }
    function showPlugin() { mode = "plugin"; tabs.currentIndex = 0; open() }
    background: Rectangle { color: theme.panel; border.color: theme.border; radius: 4 }
    contentItem: ColumnLayout {
        spacing: 10
        TabBar { id: tabs; Layout.fillWidth: true
            TabButton { text: "실행" }
            TabButton { text: "모든 명령"; onClicked: if (!root.runtimeState.commands.length) backend.loadCommands() }
            TabButton { text: "결과표 / 로그" }
            TabButton { text: "도구 옵션" }
        }
        StackLayout { currentIndex: tabs.currentIndex; Layout.fillWidth: true; Layout.fillHeight: true
            ColumnLayout {
                RowLayout {
                    AppComboBox { theme: root.theme; model: ["명령", "매크로 (IJM)", "Java 플러그인"]
                        currentIndex: root.mode === "macro" ? 1 : root.mode === "plugin" ? 2 : 0
                        onActivated: root.mode = currentIndex === 1 ? "macro" : currentIndex === 2 ? "plugin" : "command"
                    }
                    AppButton { theme: root.theme; text: "매크로 열기…"; onClicked: macroFile.open() }
                    AppButton { theme: root.theme; text: "플러그인 경로 등록…"; enabled: !root.runtimeState.busy; onClicked: pluginFile.open() }
                }
                TextField { id: commandField; objectName: "imagejCommand"; Layout.fillWidth: true; visible: root.mode !== "macro"; placeholderText: root.mode === "plugin" ? "Java 클래스 전체 이름 (예: my.package.My_Filter)" : "ImageJ 명령 이름"; text: "Invert" }
                TextField { id: optionsField; objectName: "imagejOptions"; Layout.fillWidth: true; visible: root.mode !== "macro"; placeholderText: "매크로 옵션 (예: sigma=2) / 플러그인 인수" }
                ScrollView { Layout.fillWidth: true; Layout.fillHeight: true; visible: root.mode === "macro"
                    TextArea { id: macroText; objectName: "imagejMacro"; font.family: "Consolas"; text: 'run("Invert");\nrun("Gaussian Blur...", "sigma=1");\nrun("Measure");'; wrapMode: TextEdit.NoWrap; selectByMouse: true }
                }
                Text { visible: root.mode !== "macro"; Layout.fillWidth: true; Layout.fillHeight: true; wrapMode: Text.Wrap; color: theme.muted
                    text: "현재 페이지와 선택 ROI를 작업 복사본으로 처리합니다. 매크로 옵션으로 대화상자 값을 전달하세요.\nJava AWT 창을 직접 요구하는 플러그인과 Fiji/ImageJ2 전용 플러그인은 이 실행 모드에서 지원되지 않습니다."
                }
                AppCheckBox { id: stackInput; theme: root.theme; text: "전체 TIFF 스택을 ImageJ 가상 스택으로 전달 (페이지 순서, 공간 Z 미확정)" }
                RowLayout {
                    AppCheckBox { theme: root.theme; text: "명령 기록"; checked: root.runtimeState.recording; onClicked: backend.record(checked) }
                    AppButton { theme: root.theme; text: "기록 → 편집기"; onClicked: { root.mode = "macro"; macroText.text = root.runtimeState.recorded } }
                    Item { Layout.fillWidth: true }
                    AppButton { theme: root.theme; text: "취소"; enabled: root.runtimeState.busy; onClicked: backend.cancel() }
                    AppButton { objectName: "imagejRunButton"; theme: root.theme; text: root.runtimeState.busy ? "처리 중…" : "실행"; enabled: !root.runtimeState.busy; primary: true
                        onClicked: backend.execute(root.mode, root.mode === "macro" ? macroText.text : commandField.text, optionsField.text, stackInput.checked)
                    }
                }
            }
            ColumnLayout {
                TextField { id: search; Layout.fillWidth: true; placeholderText: "ImageJ 명령 검색" }
                ListView { Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: root.runtimeState.commands.filter(function(s) { return s.toLowerCase().indexOf(search.text.toLowerCase()) >= 0 })
                    delegate: ItemDelegate { required property string modelData; width: ListView.view.width; text: modelData; onClicked: root.showCommand(modelData, "") }
                    ScrollBar.vertical: ScrollBar {}
                }
            }
            ColumnLayout {
                AppButton { theme: root.theme; text: "결과표 복사 (TSV)"; onClicked: fileBridge.copyText(root.runtimeState.headings + "\n" + root.runtimeState.rows.join("\n")) }
                Canvas {
                    id: plot; Layout.fillWidth: true; Layout.preferredHeight: 140; visible: root.runtimeState.plot.length > 0
                    property var values: root.runtimeState.plot
                    onValuesChanged: requestPaint()
                    onWidthChanged: requestPaint()
                    onPaint: {
                        var c = getContext("2d"); c.reset(); c.fillStyle = "#111518"; c.fillRect(0,0,width,height)
                        if (!values.length) return
                        var min = Infinity, max = -Infinity
                        for (var i=0;i<values.length;++i) { min = Math.min(min,values[i]); max = Math.max(max,values[i]) }
                        c.strokeStyle = "#45c3cf"; c.lineWidth = 1; c.beginPath()
                        var stride = Math.max(1,Math.floor(values.length/width))
                        for (var j=0;j<values.length;j+=stride) { var x=j/Math.max(1,values.length-1)*(width-12)+6; var y=height-6-(values[j]-min)/Math.max(1,max-min)*(height-12); if (j===0) c.moveTo(x,y); else c.lineTo(x,y) }
                        c.stroke()
                    }
                }
                ScrollView { Layout.fillWidth: true; Layout.fillHeight: true
                    TextArea { readOnly: true; selectByMouse: true; font.family: "Consolas"; text: root.runtimeState.headings + "\n" + root.runtimeState.rows.join("\n") + "\n\n" + root.runtimeState.log }
                }
            }
            ColumnLayout {
                Text { text: "색상 / 브러시·글꼴 크기 / 완드 허용오차"; color: theme.text }
                TextField { id: color; text: root.runtimeState.color; placeholderText: "#RRGGBB"; Layout.fillWidth: true }
                SpinBox { id: size; from: 1; to: 1024; value: root.runtimeState.size; editable: true }
                SpinBox { id: tolerance; from: 0; to: 65535; value: root.runtimeState.tolerance; editable: true }
                TextField { id: annotation; text: root.runtimeState.text; placeholderText: "텍스트 내용"; Layout.fillWidth: true }
                AppButton { theme: root.theme; text: "도구 옵션 적용"; onClicked: backend.configure(color.text, size.value, tolerance.value, annotation.text) }
                Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.muted; text: "다각형·분할선은 클릭으로 점을 추가하고 더블클릭/Enter로 완료합니다. 각도는 세 번 클릭합니다. 점 도구는 선택한 점 ROI에 점을 추가합니다. Esc는 진행 중인 선택을 취소합니다. 브러시·채우기는 원본을 보존하고 작업 복사본을 표시합니다." }
                Item { Layout.fillHeight: true }
            }
        }
        Text { Layout.fillWidth: true; visible: root.runtimeState.error.length > 0; text: root.runtimeState.error; wrapMode: Text.Wrap; color: theme.error }
        ProgressBar { Layout.fillWidth: true; visible: root.runtimeState.busy; indeterminate: true }
    }
    FileDialog { id: macroFile; nameFilters: ["ImageJ macro (*.ijm *.txt)"]; onAccepted: { var code = backend.readMacro(selectedFile.toString()); if (code) { root.mode = "macro"; macroText.text = code } } }
    FileDialog { id: pluginFile; nameFilters: ["Java plugin (*.jar *.class)"]; onAccepted: backend.installPlugin(selectedFile.toString()) }
}
