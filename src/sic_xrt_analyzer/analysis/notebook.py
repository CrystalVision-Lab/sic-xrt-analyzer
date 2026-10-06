"""Small Jupyter interface; algorithms remain callable without a notebook."""
from __future__ import annotations

import html
import json
from pathlib import Path

from sic_xrt_analyzer.analysis.research import FrozenClassifier, analyze_image
from sic_xrt_analyzer.registration.research import load_analysis, track_analyses


def show_result(result):
    from IPython.display import HTML, Image, display

    path = Path(result["output_dir"])
    if result["schema"] == "xrt_research_analysis":
        counts = result["counts_by_predicted_type"]
        message = (f"분류한 후보 {result['classified_count']:,}개 · 제외 {result['excluded_count']:,}개 · "
                   f"낮은 점수 {result['low_score_count']:,}개<br>"
                   + " / ".join(f"{key}: {counts.get(key, 0):,}" for key in ("BPD", "TED", "TSD")))
        image = path / "overlay.png"
        note = "후보 좌표에 대한 분류 수입니다. 전체 결함 수나 전문가 정답을 뜻하지 않습니다."
    else:
        passed = result["status"] == "completed_tentative"
        if passed:
            message = (f"잠정 연결 {result['tentative_match_count']:,}쌍 · "
                       f"종류 변화 후보 {result['type_change_candidate_count']:,}쌍 · "
                       f"모호한 점 {result['ambiguous_point_count']:,}개")
        else:
            message = "자동 정렬 기준을 통과하지 못했습니다. 연결을 생성하지 않았습니다.<br>" + html.escape(
                ", ".join(result["registration"]["reasons"]))
        image = path / "tracking_overlay.png"
        note = "연결과 종류 변화는 후보입니다. 실제 BPD→TED 전환이나 생성·소멸을 확정하지 않습니다."
    display(HTML(f"<h3>{message}</h3><p>{note}</p><p>저장 폴더: {html.escape(str(path))}</p>"))
    if image.exists():
        display(Image(filename=str(image), width=950))
    examples = path / "matched_examples.png"
    if examples.exists():
        display(HTML("<p>아래는 분산 추출한 연결 예시입니다. 왼쪽은 전, 오른쪽은 후 원본 패치입니다.</p>"))
        display(Image(filename=str(examples), width=840))


def build_workbench(config_path="research_analysis.local.json"):
    import ipywidgets as widgets
    from IPython.display import HTML, display

    path = Path(config_path)
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    layout = widgets.Layout(width="98%")
    style = {"description_width": "135px"}

    def field(key, name):
        return widgets.Text(value=config.get(key, ""), description=name, layout=layout, style=style)

    bundle = field("bundle", "고정 모델 폴더")
    output = field("output_root", "결과 저장 폴더")
    before = field("before_image", "열처리 전 영상")
    after = field("after_image", "열처리 후 영상")
    before_points = field("before_points", "전 좌표 CSV")
    after_points = field("after_points", "후 좌표 CSV")
    mode = widgets.Dropdown(options=[("제공된 좌표 분류", "provided"), ("밝기 대비 후보 찾기", "auto")],
                            value="provided", description="좌표 선택", style=style)
    score = widgets.FloatSlider(value=.6, min=0, max=1, step=.05, description="낮은 점수 표시", style=style)
    contrast = widgets.FloatText(value=12, description="대비 후보 기준", style=style)
    limit = widgets.IntText(value=3000, description="최대 후보 수", style=style)
    radius = widgets.FloatText(value=25, description="연결 반경(px)", style=style)
    landmarks = field("landmarks_csv", "수동 대응점 CSV")
    before_result = field("before_result", "전 분석 result.json")
    after_result = field("after_result", "후 분석 result.json")
    b1 = widgets.Button(description="① 전 영상 분석", button_style="primary")
    b2 = widgets.Button(description="② 후 영상 분석", button_style="primary")
    b3 = widgets.Button(description="③ 전후 정렬·추적", button_style="success")
    out = widgets.Output()
    buttons = [b1, b2, b3]

    def busy(value):
        for button in buttons:
            button.disabled = value

    def classify(which):
        busy(True)
        with out:
            out.clear_output(wait=True)
            try:
                locator = before.value if which == "before" else after.value
                points = before_points.value if which == "before" else after_points.value
                if not output.value.strip() or not locator.strip() or not bundle.value.strip():
                    raise ValueError("영상·고정 모델·결과 저장 폴더를 입력하세요.")
                if mode.value == "provided" and not points.strip():
                    raise ValueError("제공된 좌표 모드에서는 좌표 CSV가 필요합니다.")
                print("분석 중입니다. 원본 크기에 따라 몇 분 걸릴 수 있습니다.", flush=True)
                result = analyze_image(locator, FrozenClassifier(bundle.value), output.value,
                                       points_csv=points if mode.value == "provided" else None,
                                       score_threshold=score.value, proposal_threshold=contrast.value,
                                       max_candidates=limit.value)
                target = before_result if which == "before" else after_result
                target.value = str(Path(result["output_dir"]) / "result.json")
                show_result(result)
            except Exception as exc:  # noqa: BLE001 -- keep the notebook usable after callback errors
                print(f"분석 중단: {exc}")
            finally:
                busy(False)

    def track(_):
        busy(True)
        with out:
            out.clear_output(wait=True)
            try:
                if not output.value.strip():
                    raise ValueError("결과 저장 폴더를 입력하세요.")
                print("전후 영상 정렬과 연결 후보를 계산합니다.", flush=True)
                result = track_analyses(load_analysis(before_result.value), load_analysis(after_result.value),
                                        output.value, radius=radius.value,
                                        landmarks_csv=landmarks.value or None)
                show_result(result)
            except Exception as exc:  # noqa: BLE001 -- report failure without accepting partial results
                print(f"추적 중단: {exc}")
            finally:
                busy(False)

    b1.on_click(lambda _: classify("before"))
    b2.on_click(lambda _: classify("after"))
    b3.on_click(track)
    display(HTML("<h2>고정 연구 모델 · 웨이퍼 분석</h2><p>① → ② → ③ 순서로 실행합니다. "
                 "저장된 분석 결과가 있으면 ③만 실행할 수 있습니다. 학습은 실행하지 않습니다.</p>"))
    display(widgets.VBox([bundle, output, before, after, mode, before_points, after_points,
                          score, contrast, limit, widgets.HBox([b1, b2]),
                          before_result, after_result, radius, landmarks, b3, out]))
    return {"before_result": before_result, "after_result": after_result, "output": out}
