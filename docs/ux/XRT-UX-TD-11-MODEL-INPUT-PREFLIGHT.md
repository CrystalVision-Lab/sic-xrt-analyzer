# XRT-UX-TD-11 — Model Input Contract Preflight

Issue [#76](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/76) · Draft [PR #77](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/77), TD-10 PR #75 위의 stacked PR.
시작: `fix/74-windows-native-dialog-crash`, `89d253b51972357bfed3f9eaff2f227897b1d12b`.
TD-10: **PARTIAL / P0 MITIGATED / RC BLOCKER REMAINS**. TD-11 결과는 전체 RC READY 판정이 아니다.

## 1. 발견 문제와 실제 계약

TD-09에서 RGB8 JPG의 실제 분석은 정상이나 uint16 단일 채널 TIFF도 Run이 활성화되어
실행 이후 backend INVALID_INPUT으로 실패했다.

Source 입력의 권위는 `analysis/desktop_adapter.py`의 기존 `ModelInputContract`다:

- 원본 decoded sample dtype: `uint8`
- 원본 채널: `3` (RGB)
- 분석 범위: FULL_IMAGE / ROI
- 크기 정책: 128px original RGB patches; bounded source reads
- normalization: uint8 / 255; contrast inside model
- 비트 정책: uint8 only; no implicit conversion

로컬 모델 manifest는 `frozen_xrt_patch_classifier v1`이다.
ONNX tensor는 float32 `[N, 3, 128, 128]`, 기존 conversion은
`uint8_RGB_to_NCHW_div255`, local contrast는 모델 내부에 있다.
이 **tensor 계약**과 **원본 source 입력 계약**을 혼동하지 않는다.
manifest·ONNX·후보 threshold·patch/normalization/preprocessing은 변경하지 않았다.

## 2. 현재 입력 descriptor와 source of truth

`analysis/input_preflight.py`는 현재 `pipeline.source.metadata`와 `page_index`에서
(dtype, bitDepth, channels, colorMode, width, height, sourceKind, currentPage, pageCount,
sourceAvailable)을 파생한다. QImage 표시 버퍼·밝기/대비·미리보기 크기를 사용하지 않는다.

TIFF의 OriginalImageSource는 각 페이지의 header로 dtype/channels를 만든다.
TiffStack.read_page/BrowseCache도 현재 페이지 source를 사용하므로 heterogeneous TIFF는
페이지별 descriptor를 다시 계산한다. 파일 전체가 동일하다고 가정하지 않는다.

JPEG는 기존 JpegImageSource가 게시하고 실제 read_region으로 제공하는 RGB8 metadata를
그대로 사용한다. 기존 JPEG reader는 encoded grayscale JPEG도 RGB888로 decode한다.
이 정책은 이번 TD에서 추가하거나 변경한 변환이 아니다. preflight가 확장자에서
RGB를 추정하거나 encoded channel 수를 backend source channel 수 대신 쓰지 않는다.
RGB TIFF도 compatible이며 gray8/gray16/RGB16 TIFF는 실제 dtype/channels에 따라 판정한다.

## 3. 공유 validator와 backend defense

`ModelInputContract.incompatibility_reasons(metadata)`가 기존 dtype/channel predicate의
유일한 구현이다. UI presentation과 기존 `validate(request)`가 모두 호출한다.
backend의 scope 검사와 INVALID_INPUT 예외, pipeline.start 및 worker의 재검증을 유지한다.

현재 backend가 실제로 강제하는 metadata 규칙만 공유한다. color_space·크기·normalization은
기존 adapter의 preprocessing 정책 설명이며, 새로운 거부 규칙으로 해석하지 않는다.
UNSUPPORTED_COLOR_MODE 등 현재 계약에 없는 규칙과 format 이름별 차단을 추가하지 않는다.
향후 모델은 ModelInputContract의 허용 dtype/channels에서 파생하며 특정 모델 ID 분기 없음.
legacy manifest에 별도 preflight field가 없어도 기존 ModelInputContract를 사용한다.

Reason codes:

- UNSUPPORTED_DTYPE / UNSUPPORTED_CHANNEL_COUNT: 모델과 원본 sample 불일치
- SOURCE_NOT_READY: source 없음 또는 metadata/frame 전환 대기
- MODEL_NOT_AVAILABLE: 모델 없음
- MODEL_CONTRACT_UNAVAILABLE: 연결된 adapter에서 ModelInputContract를 확인할 수 없음

ModelAdapter Protocol은 input_contract를 요구한다. 결손 contract는 정상 bundle에서
발생하지 않으며 잘못된 adapter를 주입한 회귀 검사에서 ERROR와 Run 차단을 확인한다.
backend 기존 validation 및 사용자용 INVALID_INPUT error 처리는 제거하지 않는다.

## 4. 상태와 갱신

- UNKNOWN: 이미지/metadata/loading 또는 모델 연결 대기, Run 차단
- COMPATIBLE: metadata가 기존 모델 계약과 일치
- INCOMPATIBLE: dtype/channel 불일치, Run만 차단
- ERROR: 모델 입력 계약을 확인할 수 없음, Run 차단

pixel buffer·변환 이미지·변경된 contract·inference 결과를 preflight에 저장하지 않는다.
metadata와 캐시된 adapter contract만 읽으며 파일 I/O·inference·pixel copy 없음.

pipeline.changed는 모델/원본/오류 변경을, StackController.changed는 opening/page busy
전환을 analysisChanged에 전달한다. 로딩 중에는 이전 source의 호환성을 재사용하지 않는다.
UiState도 loading/pageLoading에서 UNKNOWN으로 파생해 QML loading snapshot을 일관되게 처리한다.
첫 frame 후 TD-07 progressive readiness 정책을 유지하고 준비 완료를 임의로 더 기다리지 않는다.
모델 load_saved/교체도 기존 pipeline invalidation으로 즉시 재계산된다.

## 5. Run gate와 UX

`UiState.generalReady`는 기존 이미지·source·모델·분석 상태·로딩·scope·ROI gate다.
`canAnalyze = generalReady && inputCompatible`로 두 준비 개념을 분리했다.
AnalysisContext/Analyze Menu는 동일 runAction을 공유하며 Action handler도 canAnalyze를 확인한다.
Run shortcut은 기존에도 정의하지 않았으며 새 shortcut/override/추가 클릭 없음.
직접 bridge.requestAnalysis/pipeline.start에는 backend authoritative validation이 유지된다.

기본 AnalysisContext 입력 요약: `8비트 RGB` / `16비트 단일 채널`.
불일치 시 `모델 요구 · 8비트 RGB`와 단일 준비 사유를 표시하고 Run 비활성화.
중립·warning 계층 및 Accessible.name에 현재 입력/모델 요구 설명을 사용한다.
기술 정보는 기존 입력 상세/모델 상세 InfoDialog에서 확인한다.
StatusBar 긴 경고·modal·file/page별 toast·Context 강제 이동·확인 버튼 없음.

RGB는 기존 Single-Screen Analysis의 Run 1회→Inference→Result를 유지한다.
uint16은 정상 Viewer/Zoom/Pan/Stack/밝기·대비/ROI/ImageJ/Save source로 남는다.
ROI crop은 dtype/channel을 바꾸지 않으므로 FULL_IMAGE/ROI 모두 같은 metadata 판정이다.

## 6. 검증

새 `tests/test_input_preflight.py` 23개:
metadata/backend 행렬(RGB8, gray16, gray8, RGB16, RGBA), RGB TIFF/JPEG decoded source,
무파일/무모델/loading/missing contract, 무읽기·무추론·원본 불변, 미래 gray16 모델 교체,
RGB→gray16→RGB/닫기 복구, heterogeneous page, backend 직접 INVALID_INPUT,
공유 Action disabled, 1100×700/1440×900, 접근성, uint16의 다른 도구 유지,
RGB full/ROI one-click 요청 및 파일 교체 후 ROI 재지정 readiness 분리.

기존 analysis/pipeline/AnalysisFlow/QML/native dialog 37개도 통과했다.
새 UI 검사 최초 실패는 resize 직후 이전 배치 좌표로 클릭한 테스트 초기화 문제였다.
기존 timeout/대기/production을 변경하지 않고 실제 panel bounds 조건을 기다려 수정했다.
초기 테스트/편집 도구 실패 로그는 ignored artifacts/td11에 보존했다.

실제 모델 검증 도구:

```powershell
.\.venv\Scripts\python.exe tools/validate_input_preflight.py --jpeg <RGB-JPG> --tiff <uint16-TIFF> --model <MODEL-BUNDLE> --baseline <TD09-REPORT> --output artifacts/td11/actual-inputs
```

출력은 원본/모델 디렉터리 밖이어야 한다. 모델·manifest 및 JPG/TIFF 원본 SHA 보존 검사,
실제 RGB full/ROI/Result JSON/CSV/image copy, uint16 Action disabled/호환성 복구/직접 backend
방어, TIFF header descriptor 및 Viewer/ROI/ImageJ 작업을 확인한다.
QTest는 application controls 검사이며 실제 native 파일창 mouse 검증으로 계산하지 않는다.
원시 로그·모델·원본/private 경로·결과 파일은 Git에 추가하지 않는다.

### 실제 데이터 검증: PASS

동일 모델·동일 RGB source로 TD-09 결과와 비교했다.

| 항목 | 결과 |
| --- | --- |
| 실제 RGB JPG (12349 × 12273, uint8, 3채널) | COMPATIBLE, 기존 Run 1회 분석 유지 |
| 전체 후보 | 2946 = BPD 245 + TED 1398 + TSD 1303; TD-09 동일 |
| 분석 ROI | x=1003, y=1011, 1495 × 1495 × 3; 후보 791, TD-09 동일 |
| 실제 uint16 단일 채널 TIFF | INCOMPATIBLE, FULL_IMAGE/ROI Action·Menu·Context disabled |
| uint16 inference 호출 | 0회; 직접 API도 INVALID_INPUT, worker 미시작 |
| 원본 stack/ROI/ImageJ | 페이지 탐색, 밝기·대비, ROI 생성/편집/ZIP roundtrip, ImageJ macro PASS |
| TIFF 4개 header | 모두 uint16/1 descriptor, 현재 RGB8 모델 INCOMPATIBLE |
| Export 및 image copy | JSON 일치·CSV 2946행·원본 JPG copy SHA 일치 |
| 원본·모델 보존 | JPG/TIFF 및 manifest/ONNX SHA 변경 없음 |
| 모델 복구 | RGB 재개방 COMPATIBLE; ROI scope 유지 시 새 영역 필요, FULL_IMAGE 선택 시 Run 복구 |
| 종료·QML | 정상 종료, warning 0 |

실제 검증의 첫 두 시도는 검증 도구의 호출 인자 오류와 ROI scope 유지에 대한 잘못된
readiness 기대값에서 중단됐다. 도구만 수정했고 production/기존 대기시간은 변경하지 않았다.
완료 로그 `artifacts/td11/actual-inputs-complete.log`, 결과·capture는 같은 이름의
ignored directory에 있다. 이전 중단 로그도 보존했다.

### 회귀 검사와 판정

- 새 preflight 23개 + 기존 toolbar 4개: **27 passed**, 12.98초.
- 기존 analysis/pipeline/AnalysisFlow/QML/native dialog: **37 passed**, 30.62초.
- Windows native plugin: **4 passed / 5 deselected**, 20.71초.
- 저장된 모델 복원: 실제 bundle을 설정에서 복원하고 source 없음 UNKNOWN → RGB COMPATIBLE
  → uint16 INCOMPATIBLE → RGB COMPATIBLE → 닫기 UNKNOWN 확인; inference 호출 없음.
- 전체 local pytest 첫 실행: **290 passed / 1 failed / 4 skipped**, 255.00초.
  실패는 기존 `test_toolbar_layout_and_analysis_menu_entry[size0]`의 menu click.
  전체 재실행에서도 같은 실패가 남았다(추가 진단 1개를 포함한 291 passed / 1 failed / 4 skipped).
  TD-10에도 같은 검사 실패 이력이 있다. 기준 89d253b에서 toolbar만 분리하면 4개 PASS,
  현재 코드에서 toolbar/preflight만 분리하면 27개 PASS다. 전체 회귀 성공으로 기록하지 않는다.
- 메뉴 진단에서는 동일 enabled Action의 항목 위치가 (392,76) 또는 (392,172)로 관찰됐다.
  layout/event 관련 가능성은 있으나 정확한 원인이나 TD-11과의 인과관계는 확정하지 않았다.
  기존 테스트, timeout, 클릭, assertion은 변경하지 않았다.
- 새 test module의 fixture 등록은 toolbar module의 수집 순서에 의존하지 않게 명시적으로
  reexport했다. 기존 테스트 파일 수정 없음. 첫 두 모듈 선택 실행의 fixture 오류 로그도 보존.
- TD-10 Windows managed native HWND mixed100: Open100 + Save100, exit0, QML warning0,
  COM HRESULT0, 정상 종료(67.22초). 실제 사람의 mouse/focus 확인을 대체하지 않는다.
- Ruff / compileall / UTF-8 환경 PR policy PASS. 모델·원본·sources 및 inference payload/preprocessing 변경 없음.

**TD-11 기능 검증 PASS / Windows 전체 회귀 PARTIAL / NOT RC READY.**
CI 최신 결과는 Draft PR #77에서 확인한다. Issue #76 작업 branch는
`fix/76-model-input-preflight`이며 선행 stack base를 유지한다.
local failure 로그는 `artifacts/td11/full-suite.log`, `full-recheck.log`에 보존했다.

## 7. 남은 RC blocker와 후속

TD-10 actual native mouse/focus 검증 PENDING, precise C++ root cause/최초 도입 commit UNKNOWN.
기존 ROI/Toolbar UI 이벤트 실패 이력과 native HWND deadline 불확실성도 그대로 유지한다.
TD-11 PASS와 전체 RC READY를 분리하며 **NOT RC READY** 상태를 유지한다.
다음은 실제 native 검증 및 TD-12 최종 RC 재검증/stacked PR merge readiness다.
기존 stack merge/rebase/retarget는 하지 않는다.
