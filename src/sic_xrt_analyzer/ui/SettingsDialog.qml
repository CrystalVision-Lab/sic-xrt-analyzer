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
    property string draftView: "fit"
    property string draftBackground: "#111518"
    readonly property var categories: ["일반", "뷰어", "이미지", "분석", "AI / 모델", "보정", "성능", "내보내기", "단축키", "진단"]
    signal preferencesApplied(var preferences)
    title: "설정"
    width: 760; height: 550
    function loadDraft(p) {
        draftSmooth = p.smoothImages; draftRoi = p.roiVisible; draftRemember = p.rememberRecentFiles
        draftStartup = p.startupDemo; draftLimit = p.recentFileLimit; draftView = p.defaultView; draftBackground = p.viewerBackground
    }
    function openPreferences() { loadDraft(fileBridge.preferences()); category = 0; open() }
    function applyDraft() {
        var p = fileBridge.applyPreferences({smoothImages: draftSmooth, roiVisible: draftRoi, rememberRecentFiles: draftRemember, startupDemo: draftStartup, recentFileLimit: draftLimit, defaultView: draftView, viewerBackground: draftBackground})
        loadDraft(p); preferencesApplied(p)
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
                    InfoRow { theme: root.theme; label: "언어"; value: "한국어"; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "테마"; value: "산업용 다크 그레이"; Layout.fillWidth: true }
                    AppCheckBox { theme: root.theme; objectName: "startupDemoCheck"; text: "시작 시 합성 데모 표시"; checked: root.draftStartup; onToggled: root.draftStartup = checked }
                    AppCheckBox { theme: root.theme; objectName: "rememberRecentCheck"; text: "최근 파일 목록을 다음 실행에 보관"; checked: root.draftRemember; onToggled: root.draftRemember = checked }
                    RowLayout {
                        Label { text: "최근 파일 개수"; color: theme.text }
                        SpinBox { implicitHeight: 28; objectName: "recentLimitSpin"; from: 1; to: 10; value: root.draftLimit; onValueModified: root.draftLimit = value }
                    }
                    Text { text: "보관을 끄면 저장된 목록은 삭제됩니다. 이번 세션의 최근 파일은 유지됩니다."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
                ColumnLayout {
                    visible: root.category === 1; Layout.fillWidth: true; spacing: 10
                    Label { text: "기본 보기"; color: theme.text }
                    AppComboBox { theme: root.theme; objectName: "defaultZoomCombo"; model: ["화면 맞춤", "100% (1:1)", "125%", "200%"]; currentIndex: ["fit", "actual", "125", "200"].indexOf(root.draftView); onActivated: root.draftView = ["fit", "actual", "125", "200"][currentIndex]; Layout.fillWidth: true }
                    AppCheckBox { theme: root.theme; text: "이미지 보간 · 부드럽게 표시"; checked: root.draftSmooth; onToggled: root.draftSmooth = checked }
                    Label { text: "뷰어 배경"; color: theme.text }
                    AppComboBox { theme: root.theme; model: ["다크 그레이", "짙은 다크 그레이"]; currentIndex: root.draftBackground === "#111518" ? 0 : 1; onActivated: root.draftBackground = currentIndex === 0 ? "#111518" : "#080b0e"; Layout.fillWidth: true }
                    AppCheckBox { theme: root.theme; text: "ROI 기본 표시"; checked: root.draftRoi; onToggled: root.draftRoi = checked }
                    Text { text: "기본 보기는 다음 이미지·데모 열기에 적용됩니다. 100%는 원본 픽셀과 화면 픽셀의 1:1 배율입니다."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
                ColumnLayout {
                    visible: root.category >= 2 && root.category <= 7; Layout.fillWidth: true; spacing: 12
                    Text { text: "아직 연결되지 않은 기능입니다."; color: theme.text; font.pixelSize: 12 }
                    Text {
                        text: [
                            "", "",
                            "밝기·대비·LUT 조정 연결 후 사용할 수 있습니다.\n현재 TIFF 표시용 정규화 정책은 유지합니다.",
                            "승인된 모델 연결 후 ROI 기본 좌표와 분석 파라미터를 설정할 수 있습니다.",
                            "승인된 모델 연결 후 모델·버전·장치와 추론 설정을 확인할 수 있습니다.",
                            "물리 스케일과 보정 프로필 연결 후 사용할 수 있습니다.",
                            "분석 실행 환경 연결 후 CPU·GPU와 메모리 설정을 사용할 수 있습니다.",
                            "분석 결과와 내보내기 연결 후 저장 위치·파일 이름·형식을 설정할 수 있습니다."
                        ][root.category] || ""
                        color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                }
                ColumnLayout {
                    visible: root.category === 8; Layout.fillWidth: true; spacing: 10
                    Text { text: "파일 열기                         Ctrl+O\n이미지 닫기                      Ctrl+W\n프로그램 종료                    Ctrl+Q\n화면 맞춤                         Ctrl+0\n실제 크기 (1:1)                  Ctrl+1\n확대 / 축소                       Ctrl++ / Ctrl+-\nPan / ROI                         H / R\n전체 화면                         F11\n메뉴                       Alt+F/E/V/W/A/T/S/H"; color: theme.text; font.family: theme.monoFontFamily; font.pixelSize: 12; lineHeight: 1.5 }
                    Text { text: "분석 실행 단축키는 모델 연결 전 사용할 수 없습니다."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
                ColumnLayout {
                    visible: root.category === 9; Layout.fillWidth: true; spacing: 12
                    Text { text: root.fileBridge.systemInfo; color: theme.text; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    InfoRow { theme: root.theme; label: "앱 버전"; value: root.fileBridge.appVersion; Layout.fillWidth: true }
                }
                Text { visible: root.category === 1; text: "픽셀 격자와 스케일 바는 관련 데이터 연결 후 제공됩니다."; color: theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                Text { visible: root.category === 9; text: "로그 설정은 진단 기능 연결 후 제공됩니다."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                Item { Layout.fillHeight: true }
            }
        }
    }
    footer: Item {
        implicitHeight: 54
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 18; spacing: 8
            AppButton { objectName: "resetDefaultsButton"; theme: root.theme; text: "기본값 복원"; onClicked: resetConfirmation.open() }
            Item { Layout.fillWidth: true }
            AppButton { objectName: "cancelSettingsButton"; theme: root.theme; text: "취소"; onClicked: root.reject() }
            AppButton { objectName: "applySettingsButton"; theme: root.theme; text: "적용"; onClicked: root.applyDraft() }
            AppButton { objectName: "okSettingsButton"; theme: root.theme; text: "확인"; primary: true; onClicked: { root.applyDraft(); root.accept() } }
        }
    }
    AppDialog {
        id: resetConfirmation
        objectName: "resetConfirmation"
        theme: root.theme
        title: "기본값 복원"
        bodyText: "모든 적용 가능한 설정을 기본값으로 복원하고 즉시 적용할까요?"
        cancelVisible: true
        acceptText: "복원 및 적용"
        x: (root.width - width) / 2; y: (root.height - height) / 2
        onAccepted: { root.loadDraft(root.fileBridge.defaultPreferences()); root.applyDraft() }
    }
}
