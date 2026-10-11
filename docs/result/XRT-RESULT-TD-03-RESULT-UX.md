# XRT-RESULT-TD-03 — Defect-Centric Result Explorer & Geometry Overlay

## Status

**PARTIAL — 실제 RGB/합성 JPG GUI·DPI 검증 완료; TIFF 범위 정정 후 최종 전체 회귀 진행 중.**
자동 구조 제안의 실제 검출 정확도는 미검증이다. 이는 UI의 검증 결과와 별개다.
물리적 마우스 조작 Acceptance는 PENDING이며 Qt QTest 자동 입력과 구분한다.

## Git

- 시작 Branch: `feat/98-bpd-region-detection`
- 시작 HEAD: `cb8d43059f9929f3c3346f3eed2e37a8da80667b`
- 작업 Branch: `feat/100-defect-result-explorer`
- Issue: [#100](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/100)
- Draft PR: [#101](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/101)
- Base: `feat/98-bpd-region-detection`; 기존 Draft PR #97/#99 merge/rebase/retarget 없음
- Final HEAD/CI: 최종 검증 후 PR 본문에 기록 (문서 자신의 SHA를 자기 커밋에 넣을 수 없으므로 PR이 기준)
- 사용자 `AGENTS.md` SHA256: `97fd9e0886957e532cfd5bafd525263462dc6e90652cf2b43ce6d3404fc04eaf`, 수정·스테이징하지 않음
- 실제 원본/번들/모델/연구 결과는 ignored `artifacts/`에만 기록. `sources/` 변경 없음.

## Before UI / 조사한 데이터 흐름

`FileBridge.pipeline` 완료 → `ResearchController._pipeline_changed()` → 기존 Detection의 ID,
원본 좌표, assigned class, raw score를 `rows`에 옮겨 `UiState.research`로 제공했다.
`ResultExplorer.qml`은 380px Context에서 요약·필터·선택·128px 패치·100개 목록·설정·Export를
동시에 보여줬다. `ImageViewer.analysisOverlay.points`는 `filteredPoints`를 사용했다.
따라서 목록 필터가 Overlay를 함께 줄였으며 Geometry를 읽는 GUI 경로는 없었다.

`ResultContext`, `ResultPresentation`, `RightContextPanel`, `UiState`, `ContextState`,
`FeedbackPanel`, `DatasetReview`, 기존 Result/ROI/좌표 테스트를 조사했다.
FeedbackController는 별도 source-bound feedback session이다. DatasetReview는 data-tools의
버전/해시 검증된 라벨 자료를 소비하는 별도 화면이다. TD01 ReviewEvent와 동일 저장소라고
가정하거나 자동 마이그레이션하지 않았다.

TD02 `bpd_structure`, `skeleton_graph`, `bpd_experiment.load_experiment_bundle()`와
TD01 contracts/geometry/persistence/reviews를 재사용하며 검출 알고리즘은 변경하지 않았다.
기존 Pan/Zoom 원본 변환은 `frame origin + source coordinate * displayScale`이다.
새 Geometry도 동일한 변환을 사용한다.

## After UI / UX 개선 요약

- 중앙 원본 Viewer와 기존 380px Context를 유지한다.
- 고정 상단: **분류 후보 N개**, BPD/TED/TSD 실제 분포, 전체 검수 미확정.
- 기존 클래스 버튼은 목록 필터다. **결과 표시…**에서 Overlay 레이어를 별도로 설정한다.
- 선택 후보: 원본 Crop, class/모델 점수/위치/실제 개별 검수 이력. Raw score/ID는 상세에서 확인한다.
- 100개씩 목록은 기본 접힘. 펼치기·검색·낮은 점수·페이지·이전/다음·살펴봄 기록을 유지한다.
- **실험 영역 불러오기… → 구조 제안 목록 → 선택/위치/상세**가 실제 Qt에서 작동한다.
- 메타데이터/알고리즘/관계 증거는 상세 대화상자에 둔다.
- **전체 결과 내보내기…**는 기존 CSV/JSON Export이다. 프로젝트 저장과 구분한다.

## 데이터 상태 구분 / Summary

분류 후보 수는 실제 결함 수가 아니다. 모델 score는 정답 확률 또는 검출 정확도가 아니다.
assigned class를 최대 score로 다시 계산하지 않는다. 화면의 반올림 값은 원본 값에 쓰지 않는다.

ONNX 점 후보, 자동 구조 제안, 실제 Feedback 이력은 각각 다른 근거다.
구조 레이어/패널에는 **자동 구조 제안 · 실제 정확도 미검증**을 표시한다.
제안 수는 `구조 제안 N개 / 검수 필요 N개`이고 확정 BPD 수로 표시하지 않는다.
`살펴봄`은 탐색 기록이다. 실제 개별 검수는 Feedback의 revision/기록을 확인한 경우만 표시하며
전체 결과의 정답 확정이나 adjudicated ground truth로 승격하지 않는다.

## Candidate vs DefectInstance / Result Selection

ResearchController의 canonical `selection`은 kind/id/source key/page/origin을 제공한다.
OBSERVATION이면 기존 selected candidate/thumbnail이 활성화되고 instance 선택을 지운다.
DEFECT_INSTANCE이면 기존 candidate 선택/thumbnail을 지우고 해당 구조 전체를 선택한다.
목록·Viewer·상세가 같은 canonical kind를 사용한다. 목록 필터에서 제외된 점을 이미지에서
선택해도 해당 목록 필터를 바꾸지 않으며 ‘목록 필터 밖’으로 표시한다.

source key는 현재 앱의 canonical 원본 경로이며 TD01 project UUID와 혼동하지 않는다.
실험 row에는 번들의 domain sourceId/page를 별도로 보존한다.
사용자 추가 지시(2026-10-12)에 따라 TIFF는 스택 탐색·향후 3D용이며 이 GUI 실험 결과 기능의 대상에서 제외했다.
기존 `focusCandidate()`와 cursor anchored zoom은 유지한다.
구조는 전체 Bounds+여백을 기준으로 focusGeometry()를 실행한다. 첫 노드만 줌하지 않는다.
모델/원본 범위/픽셀 좌표에 의해 bounds가 검증되며 focus 중심은 이미지 안에 제한한다.

실험 번들의 연결 후보를 현재 결과로 이동하려면 candidate ID/원본 좌표/assigned class/
raw score vector/model version까지 일치해야 한다. 동일 ID만으로 다른 모델 결과에 연결하지 않는다.
후보 상세에는 연결 구조 제안 진입을 제공한다. 모호한 관계는 ⚠와 경고 문구로 구분한다.

## Overlay Layer

독립 상태: 전체 분류 점/BPD/TED/TSD/실험 구조/선택 강조/ImageJ ROI.
목록의 class/search/low-score filter와 레이어는 독립이다. 원본 데이터를 삭제·축약하지 않는다.
기본 점은 반경 2.5 logical px, opacity .35로 낮추고 선택에 명확한 표시를 둔다.
전체 점을 숨겨도 선택 강조를 별도로 유지하거나 끌 수 있다.
파일을 바꿔도 표시 선호/목록 필터를 유지하며 결과·선택·Mask는 초기화한다.

- POINT: 기존 BPD/TED/TSD 원본 좌표 점. TED/TSD의 없는 윤곽을 생성하지 않는다.
- POLYLINE: 점선, 선 두께 1–4 logical px, 선택 시 전체 선 강조.
- BRANCHED_GRAPH: 한 instance의 모든 edge 표시. junction은 사각형, endpoint는 원형.
- MASK_REFERENCE: 검증된 binary PNG를 원본 bbox/crop origin에 반투명 fill 또는 boundary로 표시.
- 선택 형상은 다른 구조 위에 마지막으로 그린다. 색상 외 점선/노드 모양/경고 문구를 사용한다.

`GeometryOverlay`는 viewport 크기의 QQuickPaintedItem이다. 후보 Canvas도 viewport 크기다.
원본 좌표 bbox 교차로 객체/edge를 제외하며, 양 끝이 화면 밖이어도 선분 bbox가 viewport와
교차하면 그린다. 거대한 원본 크기 Canvas를 만들지 않는다.
작은 선의 클릭 오차는 8 logical px이며 Mask는 표시된 자산의 실제 alpha 픽셀을 검사한다.

## BPD Mask / Cache

선택된 Mask → 현재 보이는 Mask 순으로 비동기 LatestReader 작업을 요청한다.
viewport crop+작은 pan margin을 원본 bbox 안으로 제한하고 cache key에는 path/SHA/crop/mode를 포함한다.
최대 8개 visible mask, QImage cache/worker 반환 이미지 합계 최대 32 MiB.
더 많은 자산은 `Mask 일부 표시 (캐시 제한)`으로 알린다. 모든 중심선은 별도로 탐색할 수 있다.
표시용 큰 Mask만 최대 2048px로 축소하며 원본 mask/ROI/분석 입력을 바꾸지 않는다.
PNG codec은 압축 Mask를 내부적으로 디코딩한다. RGBA 변환/texture 표시에는 필요한 crop만 사용한다.
QQuickPaintedItem의 viewport texture에 합성하므로 모든 Mask를 별도 GPU texture로 올리지 않는다.
숨김/파일·page 전환에서 cache를 비우며 늦은 요청은 reader generation으로 무효화한다.
읽는 순간 SHA를 재검사하므로 로드 후 변경된 자산을 무조건 사용하지 않는다.

## Experimental Bundle Loading / Source Identity Validation

명시적 폴더 선택만 지원한다. 이미지 열기 후 자동 검출/자동 연결/ONNX 재실행은 없다.
기존 `load_experiment_bundle()`의 JSON/schema/project reference/path/PNG budget/binary/SHA 검증을
그대로 수행하고, GUI에서 현재 OriginalPixelSource의 canonical path/size/mtime/header/page까지 비교한다.
원본 ROI bytes의 SHA도 비교하며 project에 verified content hash가 있으면 전체 원본 SHA를 확인한다.
primary geometry source/page/kind도 확인한다. TIFF의 GUI 실험 bundle 요청은 reader 실행 전에 거부한다.
실제 uint16 스택의 RGB preflight와 뷰어·ImageJ는 유지한다. TIFF 원본을 JPG로 자동 변환하지 않는다.

검증은 worker에서 수행하며 로딩·취소·오류를 표시한다. 완전한 유효 snapshot만 GUI에 반영한다.
잘못된 bundle은 기존 이미지/분석/이전 유효 구조/선택을 보존한다.
취소/new image/page/unload는 generation을 무효화한다. 파일/page 요청 때 기존 구조도 정리한다.
이미 진행 중인 PNG/hash native I/O를 강제로 중단하지는 않지만 결과를 게시하지 않는다.
앱 종료는 소유 worker 완료와 자원 정리를 기다린다. bundle 안의 코드를 실행하지 않는다.

## Selected Detail / Existing Feedback Integration / ROI

구조 상세는 원본 Crop/픽셀 길이/분기점/관련 후보/알고리즘/flags/PRELIMINARY 증거를 보여준다.
검증하지 않은 µm/mm를 생성하지 않는다. 선택만으로 ReviewEvent/CONFIRMED/classification을 만들지 않는다.
기존 후보의 ‘선택 후보 검수하기’는 FeedbackPanel의 실제 source-bound 기록으로 이동한다.
구조는 `영역 검수는 후속 버전에서 지원합니다.` 안내만 제공한다.
TD01 ReviewEvent와 기존 Feedback history 사이의 자동 migration/검수 편집은 추가하지 않았다.

탐색용 ROI 자동 생성 옵션과 128/256/512px 탐색을 보존한다. 실제 결함 윤곽으로 표현하지 않는다.
구조 선택은 새로운 ROI를 만들지 않는다. candidate 자동 추적 ROI만 안전하게 초기화하고
수동 분석 ROI/ImageJ ROI는 유지한다. 연구 Mask는 원본 분석 ROI와 별도 자산이다.

## Existing Export / TD04 API 경계

ResearchController.exportResult()의 저장 코드·field ordering·raw precision·전체 rows를 보존한다.
표시/filter/selection/실험 bundle 로드가 기존 CSV/JSON에 geometry나 임의 review를 섞지 않는다.
기존 Export JSON의 research_only/human_verified 정책도 유지한다.
TD01 ProjectStore.save/load, import_legacy_result와 ReviewRepository가 별도 프로젝트 API다.
TD04는 File 메뉴에 프로젝트 저장/불러오기 진입을 추가하고 exact source resolution 후 project
snapshot을 별도 controller에서 적용해야 한다. 현재 Export 버튼을 프로젝트 저장으로 바꾸거나
미연결 비활성 프로젝트 버튼을 추가하지 않았다.

## Rendering Performance / Large Image / DPI Test

- Windows 11 build 26200, Python 3.13.7, Qt/PySide6 6.11.2, basic render loop.
- D checkout/TEMP; 원본은 C OneDrive에 읽기 전용. 실제 RGB 12349×12273, 2946개 후보.
- `tools/validate_defect_result_ui.py`는 별도 process에서 DPI별 Qt QTest Pan/Zoom 입력을 계측한다.
- 비교 모드: 전체 점/BPD 점/선택만/Geometry+boundary mask. Fit/100%/400%, 각 입력 8회.
- frameSwapped는 Qt 제출이며 모니터 FPS 또는 input-to-photon이 아니다.
- candidate Canvas JS paint: Date.now() 기반 1ms 해상도. Geometry paint: perf_counter CPU 구간.
- RSS는 input cache/pyramid/Qt runtime까지 포함한다. Mask cache limit과 전체 RSS는 다르다.
- maskLoadMs는 worker SHA/read/crop/color 총합; native texture upload/GPU 완료 시간은 별도 분리하지 않았다.
- 물리적 마우스 입력은 PENDING. 백그라운드 사용자 PC 활동은 제어하지 않았다.

세 DPI 모두 Windows platform/D3D11, QML warning 0, 원본 SHA/결과 객체/Export bytes 보존 PASS.
각 셀은 **median / p95 ms**, 각 case Pan 8회 + Zoom 8회다. 일부 실행은 회귀 검사와 겹쳤으므로 독립된 성능 개선율 또는 다른 DPI 간 속도 비교 근거로 사용하지 않는다.

| DPI | 배율 | 표시 | Pan 제출 ms | Zoom 제출 ms | RSS MiB |
|---:|---|---|---:|---:|---:|
| 100% | Fit | ALL | 29.09 / 52.53 | 44.29 / 52.16 | 1304.6 |
| 100% | Fit | BPD | 23.53 / 43.10 | 30.79 / 43.20 | 1302.0 |
| 100% | Fit | SELECTED | 23.71 / 32.45 | 26.20 / 35.90 | 1300.2 |
| 100% | Fit | GEOMETRY | 14.54 / 22.61 | 16.09 / 19.20 | 1319.3 |
| 100% | 100% | ALL | 15.61 / 20.05 | 15.38 / 16.80 | 1319.7 |
| 100% | 100% | BPD | 15.53 / 18.65 | 15.07 / 23.08 | 1319.7 |
| 100% | 100% | SELECTED | 15.18 / 17.32 | 15.51 / 16.82 | 1319.9 |
| 100% | 100% | GEOMETRY | 16.58 / 28.55 | 15.43 / 17.59 | 1318.1 |
| 100% | 400% | ALL | 15.35 / 20.03 | 15.07 / 20.15 | 1318.3 |
| 100% | 400% | BPD | 15.37 / 16.16 | 15.53 / 16.04 | 1318.3 |
| 100% | 400% | SELECTED | 14.29 / 15.22 | 16.40 / 17.04 | 1321.1 |
| 100% | 400% | GEOMETRY | 15.40 / 19.49 | 14.76 / 16.59 | 1320.8 |
| 125% | Fit | ALL | 33.14 / 57.31 | 32.17 / 33.75 | 1330.5 |
| 125% | Fit | BPD | 15.65 / 18.60 | 16.54 / 16.90 | 1330.5 |
| 125% | Fit | SELECTED | 15.35 / 18.36 | 14.86 / 16.18 | 1331.5 |
| 125% | Fit | GEOMETRY | 16.30 / 18.42 | 14.36 / 15.33 | 1332.0 |
| 125% | 100% | ALL | 23.97 / 27.19 | 21.97 / 25.88 | 1326.4 |
| 125% | 100% | BPD | 24.18 / 39.78 | 23.22 / 24.32 | 1308.2 |
| 125% | 100% | SELECTED | 15.88 / 35.43 | 15.12 / 17.53 | 1300.9 |
| 125% | 100% | GEOMETRY | 37.16 / 53.37 | 34.00 / 54.91 | 1276.3 |
| 125% | 400% | ALL | 22.29 / 31.78 | 19.24 / 23.84 | 1273.2 |
| 125% | 400% | BPD | 17.88 / 47.25 | 16.42 / 17.85 | 1270.8 |
| 125% | 400% | SELECTED | 15.43 / 17.90 | 14.87 / 16.92 | 1292.6 |
| 125% | 400% | GEOMETRY | 15.06 / 16.64 | 15.28 / 15.86 | 1295.4 |
| 150% | Fit | ALL | 62.64 / 65.49 | 34.13 / 45.14 | 1412.7 |
| 150% | Fit | BPD | 25.43 / 41.23 | 23.59 / 24.99 | 1406.9 |
| 150% | Fit | SELECTED | 15.25 / 19.02 | 15.46 / 16.46 | 1408.0 |
| 150% | Fit | GEOMETRY | 15.21 / 17.54 | 15.53 / 16.16 | 1395.5 |
| 150% | 100% | ALL | 14.79 / 22.51 | 16.61 / 17.47 | 1395.7 |
| 150% | 100% | BPD | 14.95 / 22.42 | 16.01 / 16.60 | 1395.5 |
| 150% | 100% | SELECTED | 20.03 / 29.90 | 27.01 / 31.03 | 1397.8 |
| 150% | 100% | GEOMETRY | 20.90 / 49.96 | 26.14 / 33.75 | 1397.3 |
| 150% | 400% | ALL | 15.52 / 38.75 | 15.45 / 22.74 | 1397.4 |
| 150% | 400% | BPD | 15.12 / 24.63 | 15.50 / 16.63 | 1397.4 |
| 150% | 400% | SELECTED | 15.12 / 16.11 | 15.54 / 16.20 | 1394.5 |
| 150% | 400% | GEOMETRY | 15.41 / 24.55 | 15.20 / 16.67 | 1378.5 |

Geometry CPU paint median 범위 0.083–8.438 ms. 전체 점 Canvas JS paint median 범위 2–4 ms (1ms 양자화).
CPU는 해당 process의 한 core=100% 환산 35.1–129.4%; 시스템 전체 점유율이 아니다.
Geometry case의 채취 시점 Mask cache는 0–24,884 bytes다. Fit에서는 cache=0인 표본도 있으므로 이 값을 full-mask 렌더 비용으로 주장하지 않는다. 실제 fill/선택 표시와 cache 해제는 별도 GUI 검사로 확인했다.
실제 bundle은 34개 구조이며 수십만 Geometry/장시간 지속 입력의 성능을 검증한 것은 아니다.
사전 offscreen/Software 측정은 진단용으로만 보관하며 네이티브 D3D11 수치와 섞지 않는다.

## Actual RGB Regression

`tools/validate_result_domain.py --expect-baseline`:

| Scope | Total | BPD | TED | TSD | 좌표·ID·raw score / Export bytes / SHA |
|---|---:|---:|---:|---:|---|
| Full image | 2946 | 245 | 1398 | 1303 | PASS |
| ROI (1003,1011,1495,1495) | 791 | 3 | 779 | 9 | PASS |

RGB 실제 Qt에서 TD02 ROI3 sato 번들(선형 11, 분기형 23)을 로드했다.
원본/모델/결과 객체를 보존하고 기존 Export before/after bytes가 같다. 실제 검출 정확도 증거는 아니다.
이 회귀 도구의 저장소 검수 테스트는 합성 UNCERTAIN event이며 실제 연구원 판정이 아니다.
GUI는 해당 합성 이력을 실제 사람 검수로 가져오지 않았다.

## TIFF 범위 정정 / Viewer-only Regression

사용자는 TIFF가 결함 분석 대상이 아닌 3D·스택용 데이터임을 추가로 명시했다. 따라서 GUI의 실험 bundle 불러오기는 TIFF에서 숨기고 backend controller도 reader 실행 전에 거부한다.
TIFF의 기존 Viewer·Stack·ImageJ를 유지하며 공간 Z/간격을 추정하거나 3D 재구성을 실행하지 않는다. 도메인/TD02 CLI 계약은 변경하지 않았다.
처음에는 기존 TD02의 TIFF bundle 표시 호환성을 검사했으나 이는 새 ONNX 추론이나 detector 실행이 아니었다. 범위 정정 후 해당 GUI 동작을 제거하고 아래 viewer-only 검사로 대체했다.

| 실제 원본 | 확인 페이지 (1-based) | 모델 실행 | 실험 불러오기 차단 | 원본 SHA |
|---|---|---:|---|---|
| N119_220_Section_stack_flipped.tif | 1 / 80 / 158 | 0 | PASS | 동일 |
| No107_SectionTopo-afterAnnealing .tif | 1 / 79 / 156 | 0 | PASS | 동일 |
| No107_SectionTopo-beforeAnnealing.tif | 1 / 79 / 156 | 0 | PASS | 동일 |
| No22_220_Section_stack_flipped.tif | 1 / 79 / 156 | 0 | PASS | 동일 |

네 파일 모두 uint16 원본 dtype·Viewer가 유지되며 QML warnings 0. TIFF 화면은 ignored `artifacts/result100-tiff-viewer-only/`에만 보관한다. 파일 원본을 수정·복사 변환·새 분석하지 않는다.

## Screenshots

Git에는 [result100 합성 화면](../screenshots/result100/)만 포함한다. 원본과 후보는 명시적 SYNTHETIC UI QA JPG.
TIFF 용도 정정 후 JPG fixture로 native 캡처를 다시 만들었고 같은 UI·Export·원본 보존 검사가 PASS했다.
실제 XRT 화면은 ignored artifacts/result100-native-* 및 result100-real-*에 보관한다.

| 시나리오 | 합성 Qt 캡처 |
|---|---|
| 전체/BPD/TED/TSD | 1100-ALL / BPD / TED / TSD.png |
| 선택 후보 Crop | 1100-candidate.png |
| 선형 구조 | 1100-POLYLINE.png |
| Y자형 전체 Graph | 1100-BRANCHED_GRAPH.png, 1440-BRANCHED_GRAPH.png |
| Mask | 1100-mask.png, 1440-mask.png |
| 구조 상세 | 1100-structure-detail.png |
| 최소/중간/큰 창 | 1100×700, 1440×900, 1920×1080 (각 ALL 캡처) |
| 결과 0개 / 파일 없음 | zero-results.png / empty.png |

## Regression / 최초 실패 구분

- 새 bundle/geometry/selection GUI 검사 22 PASS (20.30s).
- TIFF 차단 + 실제 JPG fixture로 바꾼 새 결과 GUI 검사 **23 PASS (33.87s)**. 기존 scientific pixel/dtype 테스트는 변경하지 않았다.
- 핵심 Result/ROI 검사 22 PASS (38.33s); 이전 layout/Export 좁은 창 검사 3 PASS (21.16s).
- 최초 전체 Windows 검사: **478 PASS / 4 FAIL / 5 SKIP**, 452.93s.
  - 세 건: 구 정책의 ‘목록 필터=Overlay’와 ‘점 숨김=선택도 숨김’ 기대값. 독립 레이어 정책 검사를
    추가하고 원래 선택/좌표/Export assertion은 유지했다.
  - 한 건: 분석 완료 직후 Qt polish 전 Context 버튼 좌표로 QTest가 클릭했다.
    진단 x=1170,width=222 → 렌더 후 x=1072,width=320. 실제 렌더 뒤 버튼 좌표를 사용하도록 했다.
    임의 sleep 증가/Native 코드 변경은 하지 않았다.
- 중간 재실행: **483 PASS / 1 FAIL / 5 SKIP / 1 ERROR**, 750.80s. TIFF 용도 변경 중의 기존 안내 문구 기대값 불일치와 ignored 임시 진단 파일 `test_result100_polish.py`의 잘못된 수집이었다. 문구 기대값만 수정하고 임시 파일을 `result100_polish_diagnostic.py`로 이름 변경했다. 기존 product 테스트를 제거하거나 skip하지 않았다.
- TIFF 범위 수정 커밋 CI에서 ROI Context 조작 1 FAIL / 485 PASS / 4 SKIP (279.67s), Linux X11 native 4 PASS (20.06s). Windows 동일 ROI 검사를 개별 재실행해 같은 미렌더 좌표 오류를 재현했다. 공통 Context 선택 helper가 렌더 후 좌표를 쓰도록 보완한 뒤 Context 전체 **11 PASS (31.95s)**. assertion/ROI 동작/Native 코드를 변경하지 않았다.
- 최종 전체 Windows/CI는 이후 기록. 기존 검사를 삭제/skip하지 않았다.
- QML warnings: 최종 합성 JPG Windows/실제 RGB native 세 DPI/TIFF viewer-only에서 모두 0.
- Ruff/compileall 및 desktop wheel build PASS.
- 최종 runtime code HEAD: `ea810714ea3fcf83d1d11e0fcfc9e7b17d811e63`; 이후 Context 테스트 helper 보완 및 검증 결과 기록 커밋은 runtime을 변경하지 않는다. 최종 test HEAD/CI는 PR 본문을 기준으로 확인한다.

## Native Swing Retest

기존 TD02 최초 Swing 1 FAIL → 동일 코드 재실행 4 PASS 이력의 원인은 미확정이다.
이번 작업은 Native Dialog/AWT/Swing 안정화 코드를 변경하지 않았다.
Windows native 기존 4개 × 3회 = **12 PASS / 0 FAIL**, 각 32.85 / 26.08 / 25.32s. 관측된 실패 빈도 0/12이며 이전 간헐 실패의 원인 해결을 의미하지 않는다. 로그 `artifacts/result100-native-swing-{1,2,3}.log`를 모두 보존한다. 물리적 mouse Acceptance는 여전히 PENDING이다.

## Known Limitations / Next TD

- TD02 구조 과다 분기/노이즈/연결 모호함/정답 데이터 없음은 그대로다. UI가 정확도를 개선하지 않는다.
- Mask는 visible/selected 일부를 bounded cache로 표시한다. 전체 세그멘테이션 엔진/새 tile renderer가 아니다.
- CPU segment/path culling과 painting을 사용한다. 대규모 수십만 Geometry의 spatial index/GPU 전용 renderer는 별도 계측 후 결정한다.
- 8회 입력 측정은 제한된 표본이며 monitor FPS/장시간 안정성/물리적 마우스 Acceptance를 대신하지 않는다.
- bundle import cancel은 publication 무효화이며 현재 native I/O 강제 중단이 아니다.
- instance 검수 UI, 프로젝트 전체 저장/재불러오기, server, TED/TSD segmentation, WaferMap/정합/3D는 범위 밖이다.
- TD04: 프로젝트 snapshot UI/명시적 source resolution 및 저장; 그 이후 geometry review와 검수 계약 연계.

## 실행 / 사용

```powershell
cd D:\capstone\sic-xrt-analyzer
.\.venv\Scripts\python.exe -m sic_xrt_analyzer
```

1. 2D JPG를 연 뒤 승인 모델로 기존 분석을 실행한다. TIFF는 이 결과 분석 기능의 대상이 아니며 기존 스택 뷰어·ImageJ에서 탐색한다.
2. 결과 Context에서 분류 후보 Summary, 목록 필터와 ‘결과 표시…’를 사용한다.
3. TD02 출력 폴더를 ‘실험 영역 불러오기…’로 선택한다.
4. ‘구조 제안 N개’ 목록이나 이미지의 선/Mask를 클릭한다. 위치/상세에서 원본 영역을 확인한다.
5. 분류 후보 검수는 기존 검수 화면으로 이동한다. CSV/JSON은 ‘전체 결과 내보내기…’를 사용한다.

자동 QA는 explicit `--synthetic` 또는 `--image --model --experiment`와 새 `--output`을 요구한다.
아무 이미지도 자동으로 검출/업로드/수정하지 않는다.
