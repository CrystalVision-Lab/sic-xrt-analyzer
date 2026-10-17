# XRT-TRACK-188 스택 추적 검토 화면

Issue: [#188](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/188) · 엔진: [XRT-TRACK-181](XRT-TRACK-181-ENGINE.md)

## 상태

**REVIEW_UI_CONNECTED**. #181 페이지 추적 엔진(`track_stack`, `track_from_seed`)을 스택 작업 공간에 연결했다. 기존 marching cubes 3D 메시와 3D 장면은 UI에서 제거했다. 화면에서 하는 보정은 append-only 이벤트로 프로젝트 3D 세션에 저장한다.

- 페이지는 section topography 스캔 순서다. 물리 Z, 깊이, 부피를 주장하지 않는다.
- 자동 트랙과 링크는 `AUTO`/`PROPOSED` 제안이다. 보정 이벤트는 `MANUAL`/`REVIEWED`이며, 향후 정답 데이터 후보로 사용한다. 이 PR에서 정확도를 주장하지 않는다.

## 진입

1. 여러 페이지 uint16 흑백 TIFF에서 도구 모음의 **스택 추적**을 누르고 결함을 클릭한다.
2. 클릭 위치를 중심으로 256×256 ROI Volume(전체 페이지, XY 샘플링 1)을 읽는다. 기존 `openViewerSelection` 경로를 사용하고, 원본 SHA 확인도 기존 방식 그대로 한다.
3. 작업 스레드에서 `track_stack`을 실행한다. 진행률을 표시하고 취소할 수 있다. 이어서 `track_from_seed(result=...)`로 클릭한 결함이 속한 트랙을 선택한다.
4. ROI로 Volume을 먼저 연 경우에는 **스택 추적 실행**을 누른다. XY 샘플링이 1이 아니거나 페이지 간격이 1이 아니면 실행하지 않는다.

## 화면

| 영역 | 내용 |
|---|---|
| 트랙 표 | 트랙 ID, 페이지 범위, 검출 수(+공백 수), 최소 링크 신뢰도, 상태(`! 검토`, `<>` 분기·합류 후보, `+ 보정`, `✕ 거부`). 기본 정렬은 **검토 우선**(검토 필요 → 최소 링크 신뢰도 오름차순)이며, 길이순과 시작 페이지순도 있다. 3페이지 미만 트랙은 기본으로 숨긴다. 클릭하면 선택하고, Ctrl+클릭하면 병합 대상(⇄)으로 지정한다. |
| XY 페이지 | 기존 `StackOrthogonalView`(XY 원본, 십자선, 휠로 페이지 이동, 픽셀 값 표시)를 재사용한다. 검출 overlay에서 선택 트랙은 채움, 다른 검출은 윤곽으로 그려 모양으로도 구분한다. 클릭하면 근처 트랙을 선택하고, Ctrl+클릭하면 병합 대상으로 지정한다. |
| Kymograph | 트랙 중심 경로(검출 사이는 선형 보간, 범위 밖은 끝값 유지)를 따라 자른 X–페이지 / Y–페이지 단면(±40 px)이다. 원본 uint16 픽셀을 표시 창으로만 변환한다. 행을 클릭하면 해당 페이지로 이동한다. |
| 링크 타임라인 | Volume의 페이지마다 셀 하나를 둔다. 색(Okabe–Ito)과 기호를 함께 쓴다: 시작 ▶, 링크 ●, 저신뢰 링크 !, 수락 ✓, 수동 병합 +, 공백 – (흐림·테두리), 분기·합류 후보는 셀 위에 `<` / `>`로 표시한다. 현재 페이지는 굵은 테두리로 표시한다. |
| 필름스트립 | 트랙 범위의 페이지마다 원본 crop(48–96 px 정사각형, 트랙 크기에 맞춤)을 둔다. 공백 페이지도 보간 위치로 포함한다. 페이지 번호, 타임라인 기호, 현재 페이지 강조를 표시하며, 클릭하면 XY 화면이 그 페이지로 이동한다. 최대 200페이지까지 표시한다. |

표시 창은 스택 화면의 uint16 window를 그대로 사용한다. 원본 픽셀은 바꾸지 않는다.

## 키

| 키 | 동작 |
|---|---|
| A | 현재 페이지로 들어오는 링크 수락 |
| S | 현재 페이지에서 분할(현재 페이지 이후 검출이 새 트랙이 됨) |
| M | 병합 대상과 병합(대상이 없으면 첫 후보: 분기·합류 후보 → 끝/시작이 gap+1페이지 이내이고 2×gate 이내인 트랙) |
| R | 트랙 거부(다음 트랙 선택) |
| Ctrl+Z | 저장하지 않은 마지막 보정 취소 |
| ←/→ | 이전/다음 페이지 |
| ↑/↓ | 표에서 이전/다음 트랙 |
| D | 검출 표시 켜기/끄기 |

텍스트 입력란에 포커스가 있으면 단축키는 동작하지 않는다. 보정을 하려면 검토자 ID가 필요하다.

### 병합 규칙

앞 트랙 끝 검출에서 뒤 트랙의 "앞 트랙 끝 페이지 이후 첫 검출"로 수동 링크를 만든다. 뒤 트랙에서 그 앞 부분은 원래 트랙에 남는다. 예를 들어 이웃 구조와 합류하는 MERGE 후보에서 점 결함 트랙 p18–42와 이웃 트랙 p10–77을 병합하면, 결과는 p18–77과 p10–42가 된다. 두 트랙이 같은 페이지 구간에 겹쳐서 이어질 수 없으면 거부한다.

## 저장 형식과 호환성

### 세션 `xrt_stack_3d_session/v2`

`v1`의 모든 필드에 `page_track_review`(참조 또는 `null`)를 더했다. 새로 저장하는 세션은 항상 v2다. **v1 세션은 그대로 읽고 검증한다.** v1→v2가 섞인 revision 체인도 유효하다. 수동 Track(`xrt_stack_track/v1`)과 세션 SHA, 원본 identity, revision 규칙은 바뀌지 않았다.

### 자동 결과 `xrt_page_track_result/v1`

`TrackResult.to_dict()`를 압축 JSON(공백 없음)으로 `assets/stack-3d/<sha256>.json`에 저장한다. 같은 결과는 같은 SHA를 가진다. 크기 한도는 기존과 같은 8 MiB다. 읽을 때 SHA, 스키마, 원점, 첫 페이지, 모양이 세션 selection과 일치하는지 검사한다.

### 보정 `xrt_page_track_review/v1`

```json
{
  "schema": "xrt_page_track_review/v1",
  "project_id": "...", "source_id": "...", "source_sha256": "...",
  "review_id": "uuid", "result_reference": "assets/stack-3d/<sha>.json",
  "result_schema": "xrt_page_track_result/v1", "algorithm_version": "1.0.0",
  "selection": {"roi": [x, y, w, h], "page_range": [first, last, 1], "xy_step": 1},
  "creator": "검토자", "created_at": "ISO8601+TZ", "revision": 3,
  "events": [
    {"revision": 1, "action": "SPLIT", "track_id": "t0", "other_track_id": "t0.1",
     "source_detection": "p5-d1", "target_detection": "p6-d0", "page_index": 6,
     "reviewer": "QA", "status": "REVIEWED", "method": "MANUAL", "created_at": "..."}
  ]
}
```

| action | track_id | other_track_id | source/target_detection | 의미 |
|---|---|---|---|---|
| `ACCEPT_LINK` | 트랙 | null | 트랙 안의 연속 검출 | 링크를 사람이 확인(신뢰도 1로 취급) |
| `SPLIT` | 원 트랙 | 새 트랙 ID | 끊는 링크 | target부터 새 트랙 |
| `MERGE` | 앞 트랙 | 뒤 트랙 | 앞 트랙 끝 → 뒤 트랙 검출 | 수동 링크 추가 |
| `REJECT_TRACK` | 트랙 | null | null | 트랙 거부 |

- 이벤트는 검출 ID로 링크를 기록하므로, 표시용 트랙 ID와 무관하게 링크 정답으로 쓸 수 있다.
- 불러올 때 head revision에서는 자동 결과에 이벤트를 순서대로 다시 적용(`ReviewState`)하고, 적용할 수 없는 이벤트가 있으면 프로젝트 로드를 거부한다.
- 같은 `review_id`의 이후 revision은 이전 이벤트를 접두로 유지해야 한다. 다시 쓰면 `chain()`이 거부한다. 다시 추적하면 새 `review_id`가 생기고, 이전 보정은 이전 세션 revision에 남는다.
- 다른 이름으로 저장할 때는 세션, 보정, 자동 결과를 SHA 확인 후 바이트 단위로 복사한다.
- 저장하지 않은 보정이 있으면 원본 전환, 다시 추적, 앱 업데이트를 막는다(기존 `manual_pending`).

## 제거한 코드

- `ui/defect3d_controller.py`, `ui/Defect3DScene.qml`, 사용하지 않던 `ui/Stack3DScene.qml`, `ui/stack3d_geometry.py`(QtQuick3D geometry), `stack3d/presentation.py`
- `Stack3DWorkspace.qml`의 3D 장면 Loader, 재생, 감도, 제외, 건너뛰기 UI. `ImageViewer`의 `Defect3D` 도구는 `StackTrack`(seed 클릭)로 바꿨다.
- `stack3d/defect.py`와 `continuity.py`는 #181 벤치마크 기준선(`benchmark.py`)이 참조하므로 엔진 테스트와 함께 남겼다. UI 테스트는 삭제했다.
- 설치 정책의 QtQuick3D 런타임 포함 여부는 이 PR에서 바꾸지 않았다(별도 경량화 Issue에서 검토).

## 테스트

- `tests/test_track_review_ui.py`: 합성 14페이지 스택에서 다음을 확인한다.
  - crop과 kymograph가 원본 픽셀과 같은지와 그 모양
  - 이벤트 재적용과 잘못된 이벤트 거부
  - Main.qml을 offscreen으로 열고 실제 키 입력(S/M/→/A/↑↓/R/Ctrl+Z)으로 보정
  - 저장, 다시 열기, 재적용, append-only 2번째 revision
  - seed 클릭 진입, 취소
  - v1 세션 호환, 이벤트 재작성 거부, 다른 이름으로 저장 복사
- 기존 `test_stack3d*.py`, `test_page_track_engine.py`, `test_tracking_continuity.py`, `test_defect_surface.py`(엔진 부분)

## 한계

- 추적은 ROI Volume 단위다(seed 진입 시 256×256). 158페이지 256×256에서 CPU 약 20초가 걸린다. 전체 페이지 추적은 하지 않는다.
- XY 샘플링 1, 페이지 간격 1인 Volume에서만 실행한다.
- 보정은 링크와 트랙 단위다. 검출 윤곽 자체(픽셀 마스크)는 고칠 수 없다. 거부를 되돌리는 이벤트는 없으며, 저장 전에는 Ctrl+Z로 취소한다.
- 분기·합류 후보는 표시하고 병합 대상 후보로 쓰지만, 한 트랙은 페이지마다 검출 하나인 사슬이므로 분기 구조 자체는 표현하지 않는다.
- 결과 JSON이 8 MiB를 넘으면 저장하지 않는다. 이 경우 ROI나 페이지를 줄여야 한다.
- 실제 데이터 정확도는 전문가 정답을 확보한 뒤 평가한다.
