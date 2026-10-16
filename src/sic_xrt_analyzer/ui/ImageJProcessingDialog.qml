import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SurfaceDialog {
    id: root
    objectName: "imagejProcessingDialog"
    property QtObject theme
    property QtObject uiState
    property var backend
    property string kind: "Gaussian"
    property bool valid: true
    modal: true; width: Math.min(500, parent.width - 40)
    height: Math.min(470, parent.height - 60)
    x: (parent.width - width)/2; y: (parent.height - height)/2
    title: kind === "Gaussian" ? "가우시안 흐림" : kind === "Threshold" ? "임계값 · 이진화" : "배경 제거"
    standardButtons: Dialog.Cancel
    function showKind(value) { valid = true; kind = value; radius.text = value === "Background" ? "50" : "2"; lower.text = String(uiState.stack.low); upper.text = String(uiState.stack.high); open() }
    function apply() {
        var a = Number(radius.text), lo = Number(lower.text), hi = Number(upper.text)
        valid = kind === "Threshold" ? isFinite(lo) && isFinite(hi) && lo >= 0 && hi >= lo && hi <= (uiState.bitDepth === 16 ? 65535 : 255) : radius.text.trim().length > 0 && isFinite(a) && a > 0 && a <= 1000
        if (!valid) return
        if (kind === "Threshold") backend.execute("macro", 'setThreshold(' + lo + ',' + hi + '); setOption("BlackBackground", true); run("Convert to Mask");', "", false)
        else if (kind === "Gaussian") backend.executeNative("Gaussian Blur...", {sigma: a})
        else backend.executeNative("Subtract Background...", {rolling: a, light: false, sliding: false, disable: false, separate: false})
        if (!backend.state.error) close()
    }
    contentItem: ColumnLayout {
        spacing: theme.spacingMd
        Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.text; text: "현재 페이지 " + (uiState.pageIndex + 1) + " / " + uiState.pageCount + (kind === "Background" ? " · 페이지 전체의 배경을 제거합니다. 선택 ROI를 해제해 주세요." : " · 선택된 ImageJ 영역\n선택이 없으면 현재 페이지 전체를 처리합니다.") }
        Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.muted; text: kind === "Threshold" ? "확인한 범위를 8-bit 이진 마스크 작업 복사본으로 만듭니다. 원본 uint16는 보존합니다." : "픽셀을 처리한 작업 복사본을 표시합니다. 원본은 수정하지 않습니다. 전체 스택 처리는 고급 명령에서 명시적으로 선택하세요." }
        Text { visible: kind !== "Threshold"; color: theme.text; text: kind === "Gaussian" ? "표준편차 σ (pixel)" : "Rolling ball 반경 (pixel)" }
        AppTextField { id: radius; objectName: "processingRadius"; visible: kind !== "Threshold"; Layout.fillWidth: true; text: "2" }
        Text { visible: kind === "Threshold"; color: theme.text; text: "원본 픽셀 임계값 최소 / 최대" }
        RowLayout { visible: kind === "Threshold"; Layout.fillWidth: true
            AppTextField { id: lower; objectName: "processingLower"; Layout.fillWidth: true }
            AppTextField { id: upper; objectName: "processingUpper"; Layout.fillWidth: true }
        }
        Text { Layout.fillWidth: true; color: theme.muted; font.pixelSize: theme.smallSize; wrapMode: Text.Wrap; text: "밝기·대비와 LUT는 표시 설정입니다. 필터·이진화는 작업 픽셀을 변경하며 새 파일명으로만 저장할 수 있습니다." }
        Text { visible: !root.valid; Layout.fillWidth: true; color: theme.warning; wrapMode: Text.Wrap; text: "임계값은 데이터 범위 내 최소 ≤ 최대, 반경은 0 초과 1000 이하로 입력하세요." }
        Text { visible: !!backend.state.error; Layout.fillWidth: true; color: theme.warning; wrapMode: Text.Wrap; text: backend.state.error }
        Item { Layout.fillHeight: true }
        AppButton { objectName: "processingApply"; theme: root.theme; text: "현재 페이지 작업 복사본 생성"; primary: true; Layout.fillWidth: true; enabled: uiState.loadFlow.imagejReady; onClicked: root.apply() }
    }
}
