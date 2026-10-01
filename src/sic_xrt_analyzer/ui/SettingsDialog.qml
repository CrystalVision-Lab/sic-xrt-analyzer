import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AppDialog {
    id: root
    objectName: "settingsDialog"
    property var fileBridge
    property int category: 0
    property bool draftSmooth: true
    property bool draftRoi: true
    property bool draftRemember: true
    property bool draftStartup: false
    property int draftLimit: 10
    property real draftZoom: 1
    property string draftBackground: "#111518"
    readonly property var categories: ["General", "Viewer", "Image", "Analysis", "AI / Model", "Calibration", "Performance", "Export", "Shortcuts", "Diagnostics"]
    signal applied(var preferences)
    title: "Settings"
    width: 760; height: 550
    function loadDraft(p) {
        draftSmooth = p.smoothImages; draftRoi = p.roiVisible; draftRemember = p.rememberRecentFiles
        draftStartup = p.startupDemo; draftLimit = p.recentFileLimit; draftZoom = p.defaultZoom; draftBackground = p.viewerBackground
    }
    function openPreferences() { loadDraft(fileBridge.preferences()); category = 0; open() }
    function applyDraft() {
        var p = fileBridge.applyPreferences({smoothImages: draftSmooth, roiVisible: draftRoi, rememberRecentFiles: draftRemember, startupDemo: draftStartup, recentFileLimit: draftLimit, defaultZoom: draftZoom, viewerBackground: draftBackground})
        loadDraft(p); applied(p)
    }
    contentItem: RowLayout {
        spacing: 18
        Rectangle {
            Layout.preferredWidth: 142; Layout.fillHeight: true
            color: theme.window; border.color: theme.border
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 6; spacing: 3
                Repeater {
                    model: root.categories
                    AppButton { required property int index; required property string modelData; theme: root.theme; text: modelData; checked: root.category === index; Layout.fillWidth: true; onClicked: root.category = index }
                }
                Item { Layout.fillHeight: true }
            }
        }
        ScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
            ColumnLayout {
                width: parent.width; spacing: 10
                SectionHeader { theme: root.theme; text: root.categories[root.category].toUpperCase(); Layout.fillWidth: true }
                ColumnLayout {
                    visible: root.category === 0; Layout.fillWidth: true; spacing: 10
                    InfoRow { theme: root.theme; label: "Language"; value: "한국어"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "Theme"; value: "Industrial Dark Gray"; Layout.fillWidth: true }
                    AppCheckBox { theme: root.theme; objectName: "startupDemoCheck"; text: "시작 시 합성 데모 표시"; checked: root.draftStartup; onToggled: root.draftStartup = checked }
                    AppCheckBox { theme: root.theme; objectName: "rememberRecentCheck"; text: "최근 파일 목록을 다음 실행에 보관"; checked: root.draftRemember; onToggled: root.draftRemember = checked }
                    RowLayout {
                        Label { text: "Recent file limit"; color: theme.text }
                        SpinBox { implicitHeight: 28; objectName: "recentLimitSpin"; from: 1; to: 10; value: root.draftLimit; onValueModified: root.draftLimit = value }
                    }
                    Text { text: "보관을 끄면 저장된 목록은 삭제됩니다. 이번 세션의 최근 파일은 유지됩니다."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
                ColumnLayout {
                    visible: root.category === 1; Layout.fillWidth: true; spacing: 10
                    Label { text: "Default zoom · 화면 맞춤 기준"; color: theme.text }
                    AppComboBox { theme: root.theme; objectName: "defaultZoomCombo"; model: ["100%", "125%", "200%"]; currentIndex: [1, 1.25, 2].indexOf(root.draftZoom); onActivated: root.draftZoom = [1, 1.25, 2][currentIndex]; Layout.fillWidth: true }
                    AppCheckBox { theme: root.theme; text: "Image interpolation · Smooth"; checked: root.draftSmooth; onToggled: root.draftSmooth = checked }
                    Label { text: "Viewer background"; color: theme.text }
                    AppComboBox { theme: root.theme; model: ["Dark Gray", "Deep Dark"]; currentIndex: root.draftBackground === "#111518" ? 0 : 1; onActivated: root.draftBackground = currentIndex === 0 ? "#111518" : "#080b0e"; Layout.fillWidth: true }
                    AppCheckBox { theme: root.theme; text: "ROI Overlay 기본 표시"; checked: root.draftRoi; onToggled: root.draftRoi = checked }
                    AppCheckBox { theme: root.theme; text: "Pixel Grid · 준비 중"; enabled: false }
                    AppCheckBox { theme: root.theme; text: "Scale Bar · 물리 스케일 미연결"; enabled: false }
                    Text { text: "기본 확대율은 다음 이미지 열기/데모 열기에 적용됩니다."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
                ColumnLayout {
                    visible: root.category >= 2 && root.category <= 7; Layout.fillWidth: true; spacing: 12
                    StatusIndicator { theme: root.theme; text: "준비 중 · NOT CONNECTED"; ink: theme.warning }
                    Text {
                        text: [
                            "", "",
                            "Brightness / Contrast / LUT / Bit-depth processing\n표시 조정 기능이 연결되지 않았습니다. TIFF 표시용 정규화 정책을 유지합니다.",
                            "ROI 기본 좌표 / Threshold / 분석 파라미터\n승인된 분석 파이프라인이 연결되지 않았습니다.",
                            "Model / Version / Device / Confidence / Model Path\n승인된 모델이 연결되지 않았습니다.",
                            "Pixel Scale / Calibration Profile\n물리 스케일과 보정 프로필이 연결되지 않았습니다.",
                            "CPU / GPU / Worker / Memory Cache\n사용자가 적용할 성능 제어 기능이 연결되지 않았습니다.",
                            "Result Directory / Filename / Export Format\n분석 결과 및 내보내기 기능이 연결되지 않았습니다."
                        ][root.category] || ""
                        color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    AppComboBox { theme: root.theme; model: ["연결 후 설정 가능"]; enabled: false; Layout.fillWidth: true }
                    TextField { implicitHeight: 28; placeholderText: "설정 값 없음"; enabled: false; Layout.fillWidth: true }
                }
                ColumnLayout {
                    visible: root.category === 8; Layout.fillWidth: true; spacing: 10
                    Text { text: "파일 열기                         Ctrl+O\n이미지 닫기                      Ctrl+W\n프로그램 종료                    Ctrl+Q\n화면 맞춤                         Ctrl+0\n확대 / 축소                       Ctrl++ / Ctrl+-\nPan / ROI                         H / R\n전체 화면                         F11\n메뉴                       Alt+F/E/V/W/A/T/S/H"; color: theme.text; font.family: theme.monoFontFamily; font.pixelSize: 12; lineHeight: 1.5 }
                    Text { text: "분석 실행 단축키는 모델 연결 전 사용할 수 없습니다."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
                ColumnLayout {
                    visible: root.category === 9; Layout.fillWidth: true; spacing: 12
                    Text { text: root.fileBridge.systemInfo; color: theme.text; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "App version"; value: root.fileBridge.appVersion; Layout.fillWidth: true }
                    AppComboBox { theme: root.theme; model: ["Log Level · 준비 중"]; enabled: false; Layout.fillWidth: true }
                    TextField { implicitHeight: 28; placeholderText: "Log Directory · 준비 중"; enabled: false; Layout.fillWidth: true }
                }
                Item { Layout.fillHeight: true }
            }
        }
    }
    footer: Item {
        implicitHeight: 54
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 18; spacing: 8
            AppButton { objectName: "resetDefaultsButton"; theme: root.theme; text: "Reset Defaults"; onClicked: resetConfirmation.open() }
            Item { Layout.fillWidth: true }
            AppButton { objectName: "cancelSettingsButton"; theme: root.theme; text: "Cancel"; onClicked: root.reject() }
            AppButton { objectName: "applySettingsButton"; theme: root.theme; text: "Apply"; onClicked: root.applyDraft() }
            AppButton { objectName: "okSettingsButton"; theme: root.theme; text: "OK"; primary: true; onClicked: { root.applyDraft(); root.accept() } }
        }
    }
    AppDialog {
        id: resetConfirmation
        objectName: "resetConfirmation"
        theme: root.theme
        title: "Reset Defaults"
        bodyText: "모든 적용 가능한 설정을 기본값으로 복원하고 즉시 적용할까요?"
        cancelVisible: true
        acceptText: "복원 및 적용"
        x: (root.width - width) / 2; y: (root.height - height) / 2
        onAccepted: { root.loadDraft(root.fileBridge.defaultPreferences()); root.applyDraft() }
    }
}



