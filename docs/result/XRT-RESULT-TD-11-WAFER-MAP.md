# XRT-RESULT-TD-11 — Wafer Map 작업공간 및 결함 공간 분포

## Overall Status

**PARTIAL**. 구현과 임시 상대 배치 탐색은 검증했다. 실제 Wafer 위치·크기·촬영 방향·픽셀 간격·독립 기준점은 제공되지 않아 실제 물리 분포의 정확성은 검증하지 않았다. 사용자는 **“실제 좌표 근거 없음 — 임시 배치로 진행”**을 확인했다.

- Engineering Status: **ENGINEERING_VERIFIED** — 좌표 계약, 작업공간, 저장 이력, 기존 과학 데이터 보존과 자동 회귀 검사.
- Temporary Layout Status: **TEMPORARY_LAYOUT_VERIFIED** — 합성 및 실제 JPG의 단위 없는 상대 배치.
- Physical Wafer Mapping Status: **PHYSICAL_WAFER_MAPPING_NOT_READY** — 실제 물리 좌표 검증 자료 없음. 합성 기준점 검사 성공은 실제 Wafer 검증이 아니다.
- Windows 물리 마우스·OS Native Dialog 수동 Acceptance: 기존 **PENDING** 유지. 아래 GUI 검사는 Qt 자동 입력이다.

## Git

- Start Branch: `feat/114-image-registration-workspace`.
- Start HEAD: `b39df05bbb8a50df3c6f8562664350095033affe` — TD-10 Draft PR #115 기준.
- Work Branch: `feat/116-wafer-map-workspace`.
- Issue: [#116](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/116).
- Draft PR: [#117](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/117), base는 TD-10 branch 유지.
- 구현/검사 커밋: `f8a8ad2`, `09ce4ce`, `0b6dfbf`, `ba45559`, `4ce57af`.
- 최종 구현 Source HEAD: `4ce57af65583788aa056c9031187258a4a15104a`. 이후 이 보고서/README 문서 커밋을 포함한 최종 HEAD·Push·CI는 Draft PR에 기록한다.
- 기존 stacked PR 병합·rebase·retarget 없음. 사용자가 변경한 `AGENTS.md`는 커밋에서 제외했다. 원본 XRT/모델/개인 프로젝트/비밀값은 Git에 넣지 않았다.

## 실행과 사용

PowerShell:

```powershell
Set-Location D:\capstone\sic-xrt-analyzer
.\.venv\Scripts\python.exe -m sic_xrt_analyzer
```

기존 개발 환경을 새로 준비할 경우 `.venv`에서 `python -m pip install -e ".[dev,viewer,research,imagej,sync]"`를 사용한다. 이번 지도 구현으로 새 외부 의존성을 추가하지 않았다.

1. 기존 **프로젝트**를 열거나 JPG 원본을 등록하고 저장한다. 왼쪽 **Wafer Map**으로 이동한다.
2. Source를 선택하고 **위치·회전·크기**에 상대 X/Y, 회전 각도, 원본 픽셀당 지도 X/Y 크기를 입력한다. 이미지 위치를 드래그할 수 있다. 화면 Pan/마우스 기준 Zoom/Fit을 제공한다.
3. Source마다 **하나의 완료 Run**을 선택한다. 최초 기본값은 최신 완료 Run이며 화면에 표시한다. Full과 ROI를 바꿔 비교할 수 있다. 결과 없음도 명시적으로 선택할 수 있다.
4. BPD/TED/TSD, 모델 원본 Geometry, 검수/HUMAN, 실험 Geometry 레이어를 각각 표시한다. 후보/영역을 선택한 뒤 Viewer 또는 결과로 이동하면 Source·Run·대상 ID에 맞는 원본 위치를 연다.
5. Undo는 드래그 한 번을 한 작업으로 취급한다. **초기 위치**는 선택 배치를 저장 상태로 돌리고, **취소**는 저장하지 않은 전체 지도 초안을 버린다. **미배치로**는 초안에서 해당 이미지 배치를 제거한다.
6. **배치 저장**에 편집자 ID를 입력하면 현재 배치·Run 선택·레이어 설정을 프로젝트와 함께 저장한다. 이력 선택으로 과거 배치를 불러오고 다시 저장하면 새로운 revision이 된다. 기존 이력 파일을 덮어쓰지 않는다.
7. 물리 좌표를 사용하려면 관측 그룹을 PHYSICAL로 직접 만들고 실제 Wafer ID, 좌표계 ID, mm/um, 원점·축·근거를 입력한다. 위치 입력만으로 VERIFIED가 되지 않는다. Source별 독립 측정 기준점을 검증해야 한다.
8. TIFF는 Source 목록에 스택/향후 3D용으로 구분한다. JPG 배치·정합·모델 후보 지도 대상으로 추가하지 않는다. TIFF-only 프로젝트는 지도 저장의 JPG 기준 Source가 없어 저장할 수 없다.

## Current Wafer Data Contract

`AnalysisProject`, `ImageSourceRecord`, `WaferPlacement`, `SpatialCalibration`, `ImageRelationship`, `ProjectStore`를 재사용한다. 프로젝트 schema **1.0.0/1.1.0**, 기존 Export, 분석 입력/출력, SyncProtocol은 바꾸지 않았다.

새 로컬 자산 계약은 **`xrt_wafer_placement/v1`**이다. `assets/wafer-maps/<sha256>.json`에 canonical JSON을 불변 저장한다. 기존 JPG Source의 `wafer_placement.alignment_reference`가 현재 지도 revision을 참조한다. 임시 관측 그룹 ID는 로컬 자산에만 있으며 **임시 Source의 `wafer_id`는 null**이다. 임시 배치를 실제 Wafer ID로 기록하지 않는다. 기존 Wafer 메타데이터는 `prior_wafer_metadata`와 이력으로 보존하며 기존 SpatialCalibration은 수정하지 않는다.

서버 동기화의 기존 Source allowlist는 이 로컬 배치 참조/메타데이터를 보내지 않는다. 승인 데이터셋·모델 Registry·분석·ONNX·재학습 계약과 서버 코드 변경 없음. 지도 편집은 자동 추론·자동 업로드를 실행하지 않는다.

## Wafer Map Architecture

- `wafer_map/mapping.py`: 원본 픽셀↔지도↔화면 변환, Footprint, 기준점 검증, 안전한 정합 합성.
- `wafer_map/assets.py`: strict 계약, immutable SHA 자산, revision/history, Source/group/범위 검증.
- `wafer_map/scene.py`: 선택 Run index, visible tile/Geometry culling, 표시 LOD, 작은 JPEG 미리보기 LRU.
- `ui/wafer_map_controller.py`: 초안·Undo·이력·비동기 저장·최신 요청 우선 처리·Source/Run 탐색.
- `ui/WaferMapWorkspace.qml`: 기존 Main.qml 안의 실제 지도 화면, 폼·레이어·Canvas·입력·상태·오류.
- 기존 ProjectController/ProjectStore에 로컬 자산 검증·SaveAs 복사를 연결했다. Native Dialog 안정화 코드는 변경하지 않았다.

작업공간이 활성화될 때만 지도 작업을 요청한다. worker는 현재 프로젝트와 Scene을 캡처하며, 파일/프로젝트 전환 후 오래된 결과를 버린다. 대기 요청은 최신 요청으로 교체한다. 디코더 native 호출 중간에 강제 종료하는 방식은 아니며 완료 결과의 무효화를 보장한다. SHA 읽기·preview decode·candidate index·화면 데이터 생성·저장은 worker에서 처리한다. GUI에는 현재 화면에 필요한 작은 표시 데이터가 전달된다.

## Coordinate Systems

원본 좌표는 픽셀 중심: `(0,0)`이 첫 픽셀 중심, +X 오른쪽/+Y 아래. Footprint는 `(-0.5,-0.5)`부터 `(width-0.5,height-0.5)`의 네 모서리를 affine matrix로 변환한다. 반폭·반높이의 암묵적 중심 이동을 추가하지 않는다.

열벡터를 사용한다: `p_map = M_source_to_map @ [x,y,1]`, `p_screen = V_map_to_screen @ p_map`. 역변환은 해당 행렬의 inverse다. 배치 X/Y는 원본 `(0,0)`의 지도 위치다. 회전은 행렬의 양의 각도이며 Y-down 상대 화면에서는 시계 방향으로 보인다. PHYSICAL `X_RIGHT_Y_UP`은 화면에서 Y를 반전한다. Source의 Y-down→물리 Y-up 반전은 명시된 축 조건에서만 허용한다.

균일/비균일 축 scale과 일반 affine을 보존한다. NaN/Infinity, singular matrix, 잘못된 마지막 행, 과도한 조건수/좌표/scale, 명시하지 않은 반사를 거부한다. 원본↔지도 roundtrip 오차는 합성 검사에서 `1e-9 px` 미만; 실제 QML wheel anchor 합성 검사의 원본 좌표 오차는 `1.18e-13 px` 미만이었다. 이 숫자는 물리 위치 정확도가 아니다.

## Image Placement / Temporary Layout

상대 모드는 **TEMPORARY / RELATIVE_LAYOUT / UNVERIFIED**, 단위 `relative`다. 기본 격자와 임시 배치는 관찰용이다. 실제 데이터에서 QA 담당자가 입력한 배치·5° 회전·축 scale은 촬영 위치/방향의 측정값이 아니다. 파일 이름으로 Before/After·WaferID·촬영 위치를 추정하지 않는다.

선택 테두리·배치 상태·원본 해상도·선택 Run ID/scope를 표시한다. 선택되지 않은 미배치 Source는 미배치로 유지한다. 서로 다른 그룹의 좌표를 자동으로 한 Wafer로 합치지 않는다.

## Verified Placement / Calibration & Evidence

PHYSICAL 관측 그룹에는 실제 WaferID, CoordinateSystemID, mm/um, 원점 설명, 축, 근거가 필요하다. Source 배치가 그룹에 속해도 처음에는 UNVERIFIED다.

VERIFIED는 Source별 **최소 3개 비공선 독립 측정 기준점**, 중복/범위/coverage/잔차 검사, 축별 pixel spacing과 matrix scale 일치, 양의 허용 오차, 출처·검수자 기록을 요구한다. 검증 후 배치를 이동/회전/scale하면 UNVERIFIED로 되돌린다. 합성 기준점 검증·실측 원형 외곽 표시만 자동 검사했으며 실제 Wafer Calibration은 0건이다.

검수자 ID/근거 입력은 로컬 진술이다. 외부 장비 측정의 진위나 검수자 인증을 이 UI가 증명하지 않는다. TD-10의 정합 검수 승인만으로 물리 VERIFIED가 되지 않는다.

## Image Footprint

회전·비균일 scale을 반영한 실제 네 모서리를 표시하고 hit-test/culling에 사용한다. 미리보기와 모든 Overlay가 같은 matrix를 사용한다. 물리 모드의 원형 외곽은 중심/반경/단위/측정 근거/검수자가 직접 제공된 경우만 표시하며 Fit도 외곽을 포함한다. 임시 모드에 원형 Wafer, 추정 직경, notch를 자동 생성하지 않았다. 미배치/누락 Source를 검은 이미지나 결함 0 영역으로 만들지 않는다.

## BPD/TED/TSD Overlay

모델 분류·score·원본 Candidate coordinates를 보존한다. 모델 Point/Polyline/Polygon/Graph 원본 Geometry와 검수 보정 Geometry를 별도 레이어로 표시한다. Graph는 실제 Edge 경로를 사용하며 node 연결 순서를 임의로 새로 만들지 않는다. Mask 원본은 보존하고 지도에는 **Mask bounding box**임을 표시한다. 전체 Mask를 저배율 지도 Canvas에 재래스터화하지 않는다.

LOD/culling은 화면 표시만 줄인다. 원본 좌표와 scientific counts는 바꾸지 않는다. 지도는 원본 정밀 뷰어를 대체하는 픽셀 검사 도구가 아니며, 미리보기 확대는 작은 sampled preview다. 세부 픽셀은 Source Viewer에서 확인한다.

## DefectInstance/Review Overlay

HUMAN DefectInstance, 검수 존재/분류/보정 Geometry, 충돌, legacy 검수, RULE_BASED 실험 구조를 모델 예측과 분리한다. 검수 표시만 바꿔도 모델 결과/score는 유지된다. 검수 충돌을 최종 결함 판정으로 숨기지 않는다. 선택 정보와 기존 결과/검수 화면으로 연결한다.

## Run Selection / Candidate vs Defect Counts

Source마다 **정확히 하나의 완료 Run** 또는 결과 없음. 최신 완료 Run 기본값을 화면에서 확인할 수 있고 Full/ROI/과거 Run을 명시적으로 바꿀 수 있다. Tile에도 scope와 Run ID가 보인다. Full 2,946 + ROI 791을 3,737개의 결함으로 합산하지 않는다.

CandidateObservation 수, 분류 예측 분포, HUMAN 객체, 실험 영역, 검수/충돌은 서로 다른 수다. 저해상도 LOD로 점이 합쳐 보여도 Candidate 수는 변하지 않는다. 실제 정확도 검증 정답이 없으므로 모델 후보를 실제 결함 총수·검출 정확도로 주장하지 않는다.

## Duplicate/Overlap Policy

다른 Source/Run의 동일해 보이는 후보를 자동 병합하지 않는다. 겹치는 Footprint도 물리적으로 같은 영역이라는 증거가 아니다. 미촬영/미배치/미검수 영역은 결함 0이 아니다. 실제 coverage, wafer surface area, 중복 정책, 정답 데이터가 없어 물리 결함 밀도·heatmap·완전 관측률을 계산하지 않는다.

## TD-10 Registration Integration

기존 Source/Target 선택·관계·정합 이력을 통해 TD-10 비교 작업공간으로 이동한다. 배치 제안 합성은 **`M_target_to_map @ M_source_to_target`**다. ACCEPTED 정합, VERIFIED Target 물리 배치, Source/Target ID/SHA, 동일 지도 그룹·좌표계, 동일 대상의 독립 근거를 확인한다. 합성 제안도 Source의 독립 Calibration 전에는 UNVERIFIED다.

실제 TD-10 Before/After pair의 자동 정합 **4건은 REJECTED** 상태로 보존했다. 이번 실제 임시 배치에 사용하지 않았고 Identity 성공/물리 위치로 바꾸지 않았다. 합성 accepted transform의 방향/그룹/역좌표는 자동 검사했다. 실제 정합 정확도는 여전히 PRELIMINARY다.

## Project Persistence

새 자산은 최대 8MiB canonical JSON, SHA 검증, 임시 파일 fsync 후 불변 생성이다. Source/hash/size/group/최신 Source metadata를 검사한다. 부모 chain은 같은 지도 ID, 증가 revision/time과 모든 SHA를 확인한다. 기존 ProjectStore atomic save/revision lock/충돌 검사와 함께 저장한다. 저장 중 프로젝트 변경/분석과 경합하는 쓰기는 차단한다. 변경 history를 삭제하거나 다른 최신 자산으로 바꾸는 저장을 거부한다.

SaveAs는 지도와 기존 registration/experiment 의존 자산을 복사한다. 이전 revision 복원은 새 revision 생성이며 과거 SHA 파일을 수정하지 않는다. 과거 wafer metadata와 SpatialCalibration을 보존한다. 최신 프로젝트 schema를 새 번호로 올리지 않았다.

## Source Integrity

미리보기 최초 접근·지도 저장·원본 탐색 시 Source SHA를 검사한다. cache hit는 파일 stat identity를 확인한다. Source가 누락/달라지면 Footprint와 오류만 표시하고 기존 프로젝트 재연결 절차를 사용한다. 잘못된 이미지를 보이거나 자동 추론하지 않는다. 원본 TIFF/JPG, 모델, 기존 private 프로젝트 SHA는 검증 전후 동일했다.

지도 저장 전후 8개 과학 테이블(`analysis_runs`, `observations`, `predictions`, `geometries`, `defect_instances`, `review_events`, `model_provenance`, `image_relationships`)이 동일하다. 실제 4개 Run의 기존 CSV/JSON Export는 바이트 단위로 동일했다. 새로운 분석은 0회, 자동 동기화는 0회다.

## UI Screenshots

실제 **Main.qml**, Qt 자동 mouse/keyboard/wheel, 합성 Source/결과로 캡처했다. 디자인 목업이 아니다. 실제 XRT 이미지와 개인 데이터를 Git에 넣지 않았다. 23 PNG × DPR 100/125/150 = **69 PNG**.

| 상태 | DPR 100 화면 |
| --- | --- |
| 빈 프로젝트 | [01](../screenshots/wafer-map/01-empty.png) |
| Source 미배치 | [02](../screenshots/wafer-map/02-unplaced.png) |
| 위치 폼 | [03](../screenshots/wafer-map/03-placement-dialog.png) |
| 상대 배치/회전 Footprint | [04](../screenshots/wafer-map/04-temporary-rotated-footprints.png) |
| 드래그 편집 | [05](../screenshots/wafer-map/05-dragged.png) |
| BPD/TED/TSD 레이어 | [BPD](../screenshots/wafer-map/06-layer-BPD.png), [TED](../screenshots/wafer-map/06-layer-TED.png), [TSD](../screenshots/wafer-map/06-layer-TSD.png) |
| 검수/HUMAN/Graph/Mask bounds | [07](../screenshots/wafer-map/07-review-human-graph-mask-bounds.png) |
| ROI Run | [08](../screenshots/wafer-map/08-roi-run.png) |
| 대상 선택 | [09](../screenshots/wafer-map/09-target-selected.png) |
| 원본 Viewer 위치 이동 | [10](../screenshots/wafer-map/10-candidate-viewer.png) |
| 비교 pair 폼 / 작업공간 | [11](../screenshots/wafer-map/11-comparison-dialog.png), [12](../screenshots/wafer-map/12-comparison-workspace.png) |
| 저장 / 재열기 | [13](../screenshots/wafer-map/13-save-dialog.png), [14](../screenshots/wafer-map/14-reopened.png) |
| 물리 모드 UNVERIFIED | [15](../screenshots/wafer-map/15-physical-unverified.png) |
| 기준점 검증 폼 | [16](../screenshots/wafer-map/16-physical-calibration-dialog.png) |
| 합성 물리 VERIFIED (실제 Wafer 아님) | [17](../screenshots/wafer-map/17-physical-synthetic-verified.png) |
| 원본 누락 Outline | [18](../screenshots/wafer-map/18-original-missing-outline.png) |

[1100×700](../screenshots/wafer-map/layout-1100x700.png), [1440×900](../screenshots/wafer-map/layout-1440x900.png), [1920×1080](../screenshots/wafer-map/layout-1920x1080.png). 같은 화면 세트는 [DPR125](../screenshots/wafer-map/dpr125/04-temporary-rotated-footprints.png), [DPR150](../screenshots/wafer-map/dpr150/04-temporary-rotated-footprints.png) 폴더에 있다. 9개 크기/DPR 조합에서 clipping/bounds와 QML 경고 0건을 검사했다. DPR은 Qt 설정값이며 실제 모니터/물리 마우스 acceptance와 구분한다.

## Performance

환경: Windows 11 build 26200, Intel i7-13700, RAM 약 32GiB, Python 3.13.7, PySide6/Qt 6.11.2. D 프로젝트·artifact, 실제 원본은 C OneDrive에서 읽기 전용 접근. 단독 native GPU frame benchmark가 아니다. 일부 이전 전체 회귀/화면 검사는 같은 PC에서 실행했으며 아래 숫자를 독점 하드웨어의 재현 가능한 성능 보장으로 사용하지 않는다.

`tools/validate_wafer_map.py`: 초기 Source SHA/preview decode/index/scene 생성 1회, warm Pan/Zoom 화면 데이터 생성 10회, Save 1회/reopen 5회, 프로세스 RSS 20ms sampling. **CPU worker 데이터 생성 시간**이며 GPU texture upload/Canvas paint/event-to-present/FPS 측정이 아니다. 이전 화면은 placeholder였으므로 동등한 before 성능 비교는 없다.

합성: 512×640 RGB JPEG 50개 중 **첫 Source에만 2,946개 후보**; 나머지는 image-only. 50×2,946 후보 또는 실제 대형 이미지 50개를 검증했다는 뜻이 아니다. 별도 genuine ROI Run은 791개다. 실제: 원본 대형 JPG 2개와 기존 저장 프로젝트; 분석 Run이 있는 Source의 Full/ROI를 별도로 선택했다.

| 데이터 | Tile | 후보 | 초기 ms | warm 중앙값 ms | warm 최대 ms | Decode 누계 | Preview cache MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 합성 | 1 | 2946 | 36.39 | 25.96 | 30.31 | 1 | 0.34 |
| 합성 | 10 | 2946 | 93.61 | 27.22 | 30.85 | 10 | 3.37 |
| 합성 | 50 | 2946 | 141.69 | 33.59 | 60.00 | 20 | 6.75 |
| 합성 | 50 | 791 | 235.95 | 17.29 | 39.06 | 20 | 6.75 |
| 실제 JPG | 2 | 2946 | 2148.27 | 27.97 | 59.45 | 2 | 0.84 |
| 실제 JPG | 2 | 791 | 1910.67 | 9.09 | 10.65 | 2 | 0.84 |

전체 프로세스 peak RSS: 합성 **150.50MiB**, 실제 **336.36MiB**. Save: 합성 **1,617.56ms**, 실제 **2,691.55ms**. Reopen 5회 중앙값: 합성 **451.60ms**, 실제 **946.57ms**. Source/자산 검증과 과학 테이블 저장을 포함하며 초기 SHA는 파일 크기/디스크에 따라 달라진다.

미리보기는 긴 변 384px sampled JPEG, LRU 최대 **20개 / 12MiB**. 측정된 50 tile cache는 20개/6.75MiB, 실제 2개/0.84MiB. visible preview budget을 넘는 Tile은 Outline로 남긴다. QImage cacheKey 기반 URL을 유지하여 같은 preview를 Pan/Zoom 때 다시 decode/load하지 않는다. 반복 20회 실제 QML Pan/wheel 입력에서 URL과 decode 수가 유지됐다.

`tools/capture_wafer_map.py`: offscreen **Software** backend의 Qt 입력→50ms 고정 wait→settle→grab 20회 중앙값은 DPR100 **182.88ms**, DPR125 **181.48ms**, DPR150 **210.89ms**. 이는 테스트 대기·Software paint·screenshot 비용을 포함한다. 이 값을 실제 Pan 입력 지연/GPU FPS로 주장하지 않는다. 실제 D3D11/물리 입력 frame 성능 검증은 별도다.

Culling/LOD는 고정 과학 count와 별개다. 3px cell point LOD, 최대 10,000 display points, 단일 Geometry 4,096점 초과 표시 생략을 상태에 알린다. 수천 점 Geometry의 원본 데이터/카운트는 보존한다. 오래된 요청 결과는 프로젝트 token과 최신 요청 검사로 버린다.

## Real JPG Validation

실제 저장 Run 4개: Full 2회 각각 **2,946(BPD245/TED1398/TSD1303)**, ROI 2회 각각 **791(BPD3/TED779/TSD9)**. 기존 Source/Run/Observation/Prediction/Geometry/Review/Model Provenance와 score, ROI 원본 좌표 보존. Full/ROI 화면별 count를 분리했고 이전 CSV/JSON과 지도 저장 후 Export의 byte equality를 확인했다. 실제 Full 표시에는 HUMAN 1/실험 34/충돌 1, ROI에는 HUMAN 1/실험 33이 따로 표시된다. 이 객체들은 후보 수에 더하지 않는다.

실제 배치는 전부 임시 상대 QA 배치다. 실제 Wafer ID는 null, 물리 좌표 생성 0건. TD-10 REJECTED 정합 4개 보존·미사용. 실제 모델 검출 정확도와 실제 물리 좌표 정확도는 평가할 정답이 없어 미검증이다.

## TIFF Regression

| 읽기 전용 원본 | 검사 페이지 (1-based) | 결과 |
| --- | --- | --- |
| N119_220_Section_stack_flipped.tif | 1 / 80 / 158 | PASS |
| No107_SectionTopo-afterAnnealing .tif | 1 / 79 / 156 | PASS |
| No107_SectionTopo-beforeAnnealing.tif | 1 / 79 / 156 | PASS |
| No22_220_Section_stack_flipped.tif | 1 / 79 / 156 | PASS |

12개 full page uint16 값과 endian 처리를 독립 tifffile oracle과 비교했다. ROI Geometry/Area 1,024px², ImageJ selection 및 Multiply 1 작업 복사본, 작업 복사본 Viewer 경로, 원본 SHA 보존 PASS. QML 경고 0, JPG 모델/실험 BPD/자동 Sync 호출 0. TIFF에 WaferPlacement 지도 anchor/배치 추가 0. ImageJ frames를 공간 Z로 해석하지 않았다. 외부 물리 GUI 클릭 acceptance는 수행하지 않았다.

## Windows Tests

| Gate | 결과 / 범위 |
| --- | --- |
| 기존 전체 Windows 회귀 | **695 PASS / 기존 5 SKIP**, 1,040.67s |
| 최종 구현 HEAD의 지도 집중 검사 | **43 PASS**, 42.76s |
| Native Plugin, Qt Windows DPR100/125/150 | **4 PASS ×3 =12 PASS**, 각 실행 5 deselected |
| Ruff / compileall / desktop wheel | PASS |
| 실제 JPG/TIFF/Export/SHA | 위 항목 PASS |
| 실제 Main.qml Qt input/9개 layout | PASS, QML 경고 0 |

전체 Windows 검사는 `0b6dfbf` 기반 구현에서 시작하여 완료했다. 그 뒤 표시 캐시/좌표 안정성/임시 WaferID null 보완은 최종 43개 집중 검사와 최신 Linux 전체 CI로 검증한다. **695개 전체 검사를 최종 HEAD에서 다시 실행했다고 주장하지 않는다.** 기존 테스트 삭제/skip 변경 없음. 5 SKIP은 기존 Windows symlink 권한 및 offscreen native 조건이다.

초기 실패는 fixture API/검수 enum·QML 숫자 scalar·teardown timer·표준 버튼 선택·비동기 transition 대기·검증 도구의 Source 미설정/존재하지 않는 close 호출이었다. 합성 ROI fixture를 실제 ROI scope로 수정했고 임시 group을 WaferID로 저장하던 필드를 null로 보완했다. 실패 로그와 partial artifact는 유지하고 새 폴더에서 재검증했다. 기존 검사를 약화하지 않았다. 이전 TD-10 DPR150 native 첫 실행 실패/수동 Acceptance PENDING을 이번 12회 성공만으로 원인 해결이라고 주장하지 않는다.

## GitHub CI

[구현 초기 CI](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/38334740345): Linux **696 PASS / 기존 4 SKIP**, 615.65s; Linux X11 native **4 PASS**; 독립 서버/PostgreSQL **79 PASS** (기존 httpx deprecation warning 1개); Ruff/import/compile/wheel/PR policy PASS. Desktop 의존성 없이 독립 서버 설치/검사를 유지했다.

[최종 구현 Source CI](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/38336748830)는 최종 Source HEAD `4ce57af` 검사다. 최종 문서 커밋을 포함한 HEAD CI 링크와 완료 판정은 [Draft PR #117](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/117)에 기록한다. 초기 CI 성공과 진행 중인 최신 CI를 혼동하지 않는다.

## 로컬 증거와 재현

원본/개인 프로젝트/모델·로그는 Git에 포함하지 않으며 D의 다음 artifact에 보존한다:

- `artifacts/td116-final-contract.log`, `artifacts/td116-full-windows.log`.
- `artifacts/td116-native-100.log`, `td116-native-125.log`, `td116-native-150.log`.
- `artifacts/td116-real-dataset-regression/report.json`: 기존 4 Run Export 반복/원본 SHA/TIFF 12 page.
- `artifacts/td116-real-tiff-workbench/report.json`: uint16/ImageJ/ROI/working-copy regressions.
- `artifacts/td116-synthetic-final/report.json`: 1/10/50 tile CPU bench.
- `artifacts/td116-real-map-final/report.json`: 실제 임시 배치와 과학 8테이블 보존.
- `artifacts/td116-map-export-preservation-final-v2/report.json`: 최종 Map 프로젝트의 4 Run CSV/JSON byte equality 및 WaferID null.
- `artifacts/td116-map-qt-{100,125,150}-cached/report.json`: QML 입력/화면/anchor/cache/bounds.

새 빈 출력 경로를 사용한다:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -q tests/test_wafer_map.py tests/test_wafer_map_ui.py
.\.venv\Scripts\python.exe tools/validate_wafer_map.py --output artifacts/wafer-map-new-synthetic
.\.venv\Scripts\python.exe tools/capture_wafer_map.py --output artifacts/wafer-map-new-ui
```

실제 프로젝트 검사는 `validate_wafer_map.py --project <existing-project.json> --output <new-private-path>`로 기존 자료를 읽고 별도 프로젝트에 임시 QA 배치를 저장한다. 실제 좌표 측정/추론을 수행하는 도구가 아니다.

## Scientific Limitations

- 실제 WaferID/측정 근거/방향/spacing/coverage 없음. PHYSICAL_WAFER_MAPPING_NOT_READY 유지.
- 후보는 결함 정답/동일 결함 연결/완전 관측률/밀도가 아니다. 자동 duplicate merge, tracking, density/heatmap 없음.
- Local VERIFIED는 근거 입력과 수학적 consistency 검증이다. 검수자 인증·장비 진위·전문가 ground truth와 별개다.
- 자산당 최대 500 placement/100 group/8MiB, history 최대 128 revision/누계 32MiB, Undo 32개. 무제한 보관/500개 대형 Run의 실측 성능은 검증하지 않았다.
- Preview LRU 20개/12MiB/384px. 지도에서 원본 정밀 픽셀 화질을 주장하지 않는다. 표시 생략/LOD를 scientific count와 구분한다.
- 일반 affine을 저장/합성/drag 때 보존한다. 위치 폼은 rotation+축 scale을 재구성하므로 shear가 있는 배치를 폼으로 재설정하면 shear를 유지하는 편집기가 아니다.
- 일부 이력 메타데이터 검증/읽기는 GUI 측에서도 이루어지며 최댓값 32MiB history에서 무정지 응답을 계측하지 않았다. 원본 decode 도중 native 호출을 강제 cancel하지 않는다.
- D3D11 GPU frame/물리 마우스·Native Dialog Acceptance는 이번 자동 Software QTest의 검증 범위가 아니다.
- Wafer Map 로컬 자산의 서버 전송/새 서버 schema/자동 upload 없음. TIFF 3D 재구성 없음.

## Next TD

실측 WaferID·origin·축·pixel spacing·독립 기준점·촬영 footprint/coverage와 연구원 정답을 확보한 뒤 **실제 물리 Calibration 및 분포 검증 TD**가 필요하다. 같은 물리 결함 병합/밀도/추적은 그 이후 별도 연구 계약으로 진행한다. 지도 서버 저장은 versioned asset/권한/SyncProtocol 계약을 별도 TD에서 정의한다. 실제 물리 입력·GPU 성능은 foreground D3D11 계측과 수동 acceptance로 분리한다.
