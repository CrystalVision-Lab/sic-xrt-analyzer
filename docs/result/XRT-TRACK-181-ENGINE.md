# XRT-TRACK-181 페이지 기반 동일 결함 추적 엔진

Issue: [#181](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/181)

## 상태

**ENGINE_AND_SYNTHETIC_BENCHMARK**. 새 엔진 `sic_xrt_analyzer.stack3d.tracking`과 GT id가 있는 합성 벤치마크를 추가했다. UI는 아직 기존 `stack3d/defect.trace`를 사용하며, 기존 엔진은 삭제하지 않았다. 전환은 후속 PR에서 한다.

- 페이지는 section topography 스캔 순서(프레임)다. 물리 Z 간격은 검증되지 않았으므로 깊이·길이·부피를 주장하지 않는다.
- 결과는 모두 `source=AUTO`, `status=PROPOSED`인 제안이다. 확정된 결함이나 학습 정답이 아니다.
- 합성 점수는 회귀 근거다. 실제 정확도는 전문가 GT를 확보한 뒤 평가한다.

## 기존 엔진의 실패 원인

| 원인 | 결과 |
|---|---|
| 한 페이지에서 검출이 약해지면 즉시 종료(gap closing 없음) | 실제 점 결함은 약 115페이지 동안 보이지만 20페이지만 추적 |
| `dark_mask` 배경 커널이 crop 크기에 따라 바뀜 | 추적 상태(crop)에 따라 검출 결과가 바뀌고 인접 결함이 지워짐 |
| seed 페이지에서 정한 고정 baseline | 감도 조절이 사실상 효과 없음, 페이지 gain 변화에 취약 |
| 연결 성분 단위 선택 | 접촉한 구조가 하나로 합쳐짐 |
| seed 하나에서 출발한 greedy 전파 | 전역 최적 할당이 아니어서 교차·평행 구조에서 전환 |

## 알고리즘

### 1. 페이지별 결정적 검출 (`detection.py`)

각 페이지를 다른 페이지나 추적 상태와 무관하게 처리한다.

1. **정규화**: 고정 커널(`background_px=31` 원본 px) median 배경을 빼고, σ=1 평활 후 MAD로 나눠 z 맵을 만든다. 커널이 crop 크기와 무관하고, 페이지 gain이 바뀌어도 신호와 잡음이 같이 바뀌어 z가 유지된다.
2. **극성**: `DARK`(기본), `BRIGHT`, `BOTH`.
3. **세 채널 + hysteresis**
   - 픽셀 z (`low_z=2.5`, `high_z=5`)
   - 방향성 선 적분(길이 15 px, 12방향, 방향별 MAD 정규화) — 약한 직선을 길이 방향으로 모아 감지한다. 선형 필터라 페이지별 MAD 정규화가 정확하므로 Sato 대신 사용했다.
   - LoG blob 응답(σ=2, MAD 정규화)
   - 필터 채널은 픽셀 z > `support_z`인 곳에서만 인정하고, 7×7 국소 최대값의 25% 미만인 halo는 잘라서 가까운 평행선이 붙지 않게 한다.
4. **분할**
   - 작고 둥근 성분은 `BLOB`으로 둔다.
   - 긴 구조에 붙은 점 결함은 Hessian 등방성 ≥ 0.6이고 구조의 일반 반폭보다 두꺼운 LoG 최대점으로 `BLOB`을 떼어 낸다. 이 영역은 skeleton에서 뺀다.
   - 나머지는 skeleton으로 만들고, spur를 제거한 다음 junction에서 자른다(`analysis/skeleton_graph.trace_skeleton`, `prune_spurs` 재사용). 끝점 간격이 6 px 이하이고 방향이 25° 이내인 조각은 다시 합친다. 교차점을 지나는 같은 직선은 한 `SEGMENT`로 남고, 다른 방향의 가지는 분리된다.
5. **수락**: BLOB은 최대 z ≥ `low_z`이면서 (z ≥ `high_z` 또는 LoG z ≥ `blob_high_z`)를 만족해야 한다. SEGMENT는 평균 z ≥ `low_z` 또는 선 적분 z ≥ `line_high_z`를 만족해야 한다.

### 2. 연결 (`linking.py`)

1. **프레임 간 LAP**: `scipy.optimize.linear_sum_assignment`에 birth/death 대안을 붙인 행렬을 쓴다. 링크가 채택되려면 비용이 `2 × no_link_cost`보다 작아야 한다.
   - 거리: SEGMENT 또는 큰 BLOB은 양방향 chamfer 평균 중 작은 값을 쓴다. 성장하거나 줄어드는 선도 자기 자신과 맞는다. 작은 BLOB끼리는 중심 거리를 쓴다. 이전 tracklet 속도(EMA 0.5)로 위치를 예측한다.
   - 비용 = 거리 + `orientation_weight·|sin Δθ|` + `contrast_weight·|log(c₁/c₂)|` + BLOB↔SEGMENT 전환 패널티(`kind_penalty=1`)
   - 게이트: 예측 후 거리 ≤ `gate_px=12`
2. **Gap closing**: tracklet 끝 → 시작을 `max_gap=3` 페이지 결측까지 두 번째 LAP로 잇는다. 게이트는 결측 페이지마다 25%씩 넓히고, 결측 페이지마다 `gap_penalty`를 더한다.
3. **분기·합류 후보**: 시작 직전 페이지 또는 끝 다음 페이지에 계속 이어지는 다른 트랙이 `split_merge_px=4` 이내에 있으면 `SPLIT`/`MERGE` 링크를 만든다. 트랙 구성에는 넣지 않고 항상 `review=true`로 둔다.
4. **신뢰도**: `1 − exp(−margin / confidence_scale)`로 계산한다. margin은 채택 비용과 가장 가까운 경쟁 대안(같은 행·열의 다음 후보 또는 no-link) 사이의 차이다. gap 링크는 결측 페이지마다 0.85배를 한다. `review_below=0.5` 미만인 링크는 검토 대상으로 표시하고, 트랙은 최소 링크 신뢰도와 검토 여부를 가진다.

### 3. 공개 API (`engine.py`)

```python
from sic_xrt_analyzer.stack3d.tracking import track_stack, track_from_seed, TrackSettings
result = track_stack(volume_kyx, TrackSettings(), origin=(x0, y0), first_page=k0,
                     cancelled=cb, progress=cb)
seed = track_from_seed(volume_kyx, page, x, y, origin=(x0, y0), first_page=k0)
seed.track.pages, seed.detection, seed.result
```

좌표는 원본 페이지 좌표(`origin` 포함)이고, 페이지는 원본 페이지 인덱스(`first_page` 포함)다. 취소하면 `InterruptedError`가 발생한다.

## 데이터 모델과 호환성

- 스키마는 `xrt_page_track_result/v1`, `algorithm_version=1.0.0`이다.
- `Detection`: id, page, kind(BLOB|SEGMENT), centroid, points(원본 좌표 정수 x,y), orientation, length, contrast_z, polarity
- `Link`: source_id, target_id, kind(CONTINUE|GAP|SPLIT|MERGE), cost, confidence, review, status, source
- `Track`: id, detection_ids, pages, min_confidence, review, status, source
- `TrackResult.to_dict()` / `from_dict()`로 JSON 왕복한다. 알 수 없는 스키마는 거부한다.

**호환성**: 기존 append-only 세션 계약(`xrt_stack_3d_session/v1`, `xrt_stack_track/v1`, `method=MANUAL`)은 바꾸지 않았다. 새 결과는 독립 스키마이며 이 PR에서는 프로젝트 파일에 저장하지 않으므로 기존 프로젝트 파일에 영향이 없다. 후속 PR에서 세션에 붙일 때 별도 참조 키로 추가하고, 검토된 결과만 기존 수동 Track 이벤트로 옮기는 방식을 검토한다. 외부 저장소와 맺은 계약은 바뀌지 않았다.

## 매개변수 (기본값)

| 이름 | 값 | 의미 |
|---|---:|---|
| background_px | 31 | median 배경 커널(원본 px, 고정) |
| low_z / high_z | 2.5 / 5 | 픽셀 z hysteresis |
| line_length_px / line_orientations | 15 / 12 | 방향성 선 적분 |
| line_low_z / line_high_z | 3 / 5.5 | 선 채널 hysteresis |
| blob_sigma, blob_low_z / blob_high_z | 2, 3 / 6 | LoG 채널 |
| relative_floor | 0.25 | 7×7 국소 최대 대비 halo 절단 |
| gate_px | 12 | 페이지당 최대 예측 오차 |
| no_link_cost | 7 | 링크 채택 기준은 2×7 미만 |
| max_gap / gap_penalty | 3 / 1.5 | gap closing |
| kind_penalty | 1 | BLOB↔SEGMENT 전환 |
| split_merge_px | 4 | 분기·합류 후보 거리 |
| confidence_scale / review_below | 2 / 0.5 | 신뢰도와 검토 기준 |

## 합성 벤치마크

실행: `python -m sic_xrt_analyzer.stack3d.tracking.benchmark`. 테스트는 `tests/test_page_track_engine.py`에 있다. 24페이지 × 128×128, 고정 seed이고 실제 데이터는 쓰지 않는다.

- **seed 지표**(기존 엔진과 비교 가능): 두 엔진 모두 같은 GT 픽셀에서 시작한다. `page-recall`은 정답 id로 판정된 추적 페이지 수 ÷ GT 페이지 수, `purity`는 정답 id 페이지 수 ÷ 추적 페이지 수다. 새 엔진에서 검출 1개의 라벨은 GT를 5×5 팽창한 뒤 점의 50% 이상이 가진 id다.
- **전역 지표**(새 엔진만 해당. 기존 엔진은 seed 1개만 추적한다):
  - link P/R: 트랙 링크의 같은 id 비율 / GT 연속 페이지 쌍의 회수율
  - IDF1(단순화): 3페이지 이상 트랙과 GT id의 페이지 단위 Hungarian 매칭
  - ID 전환, 조각 수
  - 분기·합류 후보 수

| 시나리오 | GT 페이지 | 기존 page-recall | 기존 purity | 신규 page-recall | 신규 purity | 신규 seed 전환 | link P | link R | IDF1 | ID 전환 | 조각 | 분기·합류 후보 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gap_1 | 19 | 0.53 | 1.00 | 1.00 | 1.00 | 0 | 0.86 | 1.00 | 1.00 | 0 | 0 | 0 |
| gap_2 | 18 | 0.56 | 1.00 | 1.00 | 1.00 | 0 | 1.00 | 1.00 | 1.00 | 0 | 0 | 0 |
| gap_3 | 17 | 0.59 | 1.00 | 1.00 | 1.00 | 0 | 0.94 | 1.00 | 1.00 | 0 | 0 | 0 |
| drift_3px | 20 | 0.00 | 0.00 | 1.00 | 1.00 | 0 | 0.95 | 1.00 | 1.00 | 0 | 0 | 0 |
| drift_6px | 20 | 0.75 | 1.00 | 1.00 | 1.00 | 0 | 1.00 | 1.00 | 1.00 | 0 | 0 | 0 |
| drift_10px | 12 | 0.08 | 1.00 | 0.92 | 0.92 | 1 | 0.83 | 0.91 | 0.92 | 1 | 1 | 0 |
| fade_15pct | 20 | 0.80 | 1.00 | 1.00 | 1.00 | 0 | 0.95 | 1.00 | 1.00 | 0 | 0 | 0 |
| texture_snr4 | 20 | 0.25 | 1.00 | 1.00 | 1.00 | 0 | 1.00 | 1.00 | 1.00 | 0 | 0 | 1 |
| texture_snr3 | 20 | 0.00 | 0.00 | 0.85 | 0.94 | 1 | 0.95 | 1.00 | 0.79 | 1 | 1 | 1 |
| texture_snr2 | 20 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 1.00 | 0.11 | 0.26 | 2 | 2 | 0 |
| crossing | 20 | 0.25 | 1.00 | 0.90 | 1.00 | 0 | 0.95 | 0.92 | 0.97 | 0 | 0 | 0 |
| branching | 20 | 0.50 | 1.00 | 1.00 | 1.00 | 1 | 0.93 | 0.93 | 0.64 | 1 | 1 | 1 |
| dot_touched_by_line | 20 | 1.00 | 1.00 | 1.00 | 1.00 | 0 | 0.92 | 0.92 | 0.95 | 0 | 0 | 0 |
| dense_parallel | 20 | 0.00 | 0.00 | 1.00 | 1.00 | 0 | 1.00 | 1.00 | 1.00 | 0 | 0 | 0 |
| page_gain | 20 | 1.00 | 1.00 | 1.00 | 1.00 | 0 | 0.90 | 1.00 | 1.00 | 0 | 0 | 0 |
| point_jitter_fade | 20 | 1.00 | 1.00 | 1.00 | 1.00 | 0 | 1.00 | 1.00 | 1.00 | 0 | 0 | 0 |

기존 엔진에서 `0.00 / 0.00`은 seed 단계에서 예외(ValueError)가 나서 아무것도 추적하지 못한 경우다.

`branching`은 GT에서 갈라진 오른쪽 가지에 새 id를 준다. 그래서 IDF1 0.64는 정의상 생긴 값이고, 엔진은 이 가지를 `SPLIT` 후보 1건(검토 필요)으로 제시한다.

### 테스트 기준값 (과적합을 피하기 위해 현재 점수보다 낮게 설정)

- `texture_snr2`를 제외한 모든 시나리오: 신규 page-recall ≥ 0.80, purity ≥ 0.90, link P ≥ 0.80, link R ≥ 0.85
- gap, crossing, texture, dense 범주: 신규 page-recall ≥ 기존 + 0.25
- branching: SPLIT/MERGE 후보 ≥ 1건
- `texture_snr2`(상관 질감 잡음에서 SNR 2인 선)는 두 엔진 모두 실패한다. 알려진 한계로 기록하고, 테스트에서는 제외한다.

## 실제 TIFF 확인 (읽기 전용, 숫자만 기록)

로컬 N119 section stack(158페이지)을 256×256 ROI로 잘라 확인했다. 이전 분석과 같은 점 결함 seed를 썼다. 파생 이미지와 데이터는 커밋하지 않았다.

| 방식 | 연속 추적 페이지 |
|---|---|
| 기존 `defect.trace` (이전 분석) | 20 |
| 이전 scratch 프로토타입 (이전 분석) | 64 |
| 신규 엔진 seed 트랙 | 25 (p18–42, 검토 링크 2) |
| 신규 엔진 + MERGE 후보 1건 승인 시 | p18–77 (약 60) |

- 처리 시간은 158×256×256 기준 약 23초(CPU)였다. 검출 1,866건, 트랙 290개, 10페이지 이상 트랙은 55개였다.
- 실패 지점은 p42→p43이다. 점 결함이 이웃 구조와 합쳐진 SEGMENT로 바뀌는 구간이고, 이웃 트랙의 비용(2.97)이 점 결함 트랙의 비용(3.26+전환)보다 낮았다. 엔진은 이 지점을 자동으로 합치지 않고, `MERGE` 후보(신뢰도 0.47, review)로 제시한다.
- 전문가 GT가 없으므로 위 숫자는 정확도가 아니라 동작을 확인한 결과다.

## 한계

- 물리 Z 간격과 Z 방향이 검증되지 않았다. 페이지는 스캔 순서로만 다룬다.
- 전문가 GT가 없다. 합성 시나리오는 직선과 원판 위주이고 곡선, 넓은 판상 결함, 실제 질감은 충분히 반영하지 못한다.
- 상관 질감에서 SNR 2 이하인 약한 선은 검출하지 못한다.
- 실제 데이터에서는 검출 모양(BLOB↔SEGMENT)이 페이지마다 바뀌고, 이웃 구조와 합쳐지는 경우가 남은 병목이다. 이 경우 합류·분기 후보와 검토 링크로 넘긴다.
- 처리 시간은 Python skeleton 그래프 처리에 많이 쓰인다. 전체 페이지(수천 px)를 처리하려면 ROI·타일링 또는 최적화가 필요하다.
- 결과 JSON은 아직 프로젝트 세션에 저장하지 않는다.

## 다음 단계 (후속 PR)

1. UI 진입점을 `track_from_seed`로 전환한다. ROI 볼륨은 기존 `stack3d/volume`으로 읽는다.
2. 트랙 표(페이지 범위, 최소 신뢰도, 검토 링크 수)
3. 페이지 필름스트립(검출 윤곽 오버레이)
4. Kymograph(트랙 축을 따라 자른 페이지×거리 단면)
5. 링크 보정: 끊기, 잇기, MERGE/SPLIT 후보 승인·거절. 결과는 `source=MANUAL`과 `REVIEWED`로 바꾸고 세션 계약에 버전을 붙여 저장한다.
6. 전문가 GT 수집 후 실제 데이터 지표를 산출한다.
