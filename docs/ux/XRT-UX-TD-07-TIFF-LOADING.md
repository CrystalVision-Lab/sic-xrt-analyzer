# XRT-UX-TD-07 — TIFF / Stack Loading 및 단계별 준비

Issue #68. 기준: TD-01~06 / PR #67 / `refactor/66-roi-ux` / `a1d615356de8ce78842bf2a2703cc4ca042b8a87`.

## 1. 변경 전 실제 구조 조사 (구현 전)

- `Main.startImageLoad`는 `opening=true` 후 `FileBridge.requestImage`를 호출한다. 기존 화면은 성공 전까지 유지하고 pipeline generation을 무효화한다.
- `StackController`의 단일 QThreadPool worker가 signature 확인 → `open_stack` → OriginalImageSource metadata/page count → 첫 `frame(0)`을 수행한다. JPEG는 Qt QImageReader, TIFF는 기존 tifffile을 사용한다.
- 일반 TIFF `TiffStack.frame`은 현재 원본 페이지를 읽고, 필요하면 해당 페이지의 기존 DisplayPyramid를 준비한 뒤 frameReady를 GUI thread에 전달한다. 전체 stack decode가 첫 frame의 전제 조건이 아니다.
- JPEG와 read budget을 넘는 단일 TIFF는 SampledImageStack이다. 큰 JPEG는 기존 원본 임시 mmap/DisplayPyramid, 큰 단일 TIFF는 warm_tiff와 DisplayPyramid 준비를 끝내고 첫 frame을 전달한다. 이 준비를 건너뛰면 기존 확대 품질 요구를 만족하지 못하므로 유지한다.
- 성공한 first frame은 FileBridge의 provider/original_source/pipeline source 및 Main의 메타데이터·Viewer source에 즉시 연결된다. Context는 기존 OPEN_IMAGE로 IMAGE가 된다.
- 이후 동일 worker가 남은 페이지의 prepare_browse를 순차 수행한다. 전체 원본 stack ndarray를 만들지 않는다. 원본은 page-on-demand / 제한 LRU, 탐색 샘플은 기존 전체 페이지 캐시, 필요한 정밀 표시 계층은 기존 임시 디스크 캐시다.
- 그러나 `initial_loading`은 탐색 캐시 전체가 ready가 될 때까지 true다. UiState.loading은 opening OR initialLoading이어서 이미 연결된 첫 frame도 full Overlay가 덮고 Pan/Zoom/Fit/ROI/Analysis를 전부 막는다.
- 페이지 변경/빠른 요청은 기존 serial·epoch·Event 취소와 단일 pending 슬롯을 사용한다. 파일 교체는 epoch를 증가시키며 실패 시 이전 frame의 표시 캐시를 유지한다. shutdown은 취소 token을 설정하고 worker 종료를 기다린다.
- browse prepared는 실제 put 성공한 페이지 수다. prepare_native의 progress는 chunk/표시 계층 단계이며 페이지 수가 아니다.
- 원본 raw cache 3페이지/96 MiB, frame 표시 cache 32 MiB, 전체 browse cache 512 MiB를 유지한다. retained 현재 frame은 LRU 밖에 남을 수 있으므로 이 수치는 프로세스 RAM 한도가 아니다.

## 2. 구현 전 측정

`tools/benchmark_tiff_loading.py`는 생성 3/32/158페이지 uint16 TIFF에서 metadata, 첫 정밀 frame callback, 차단 Overlay가 없는 첫 Qt frameSwapped, 전체 browse ready를 측정한다. 파일 생성은 측정 밖이며 artifacts/에만 저장한다. 절대 시간은 PASS 기준이 아니다. 변경 전/후 결과와 나머지 구현·검증은 아래에 이어 기록한다.

## 3. 기존 UX 문제와 변경 전 Lifecycle

EMPTY → OPENING → 내부 first frame/source 연결 → initialLoading/full Overlay 유지 → 모든 페이지 browse/pyramid 준비 → READY. first frame과 전체 준비는 다른 event지만 UI.loading 하나로 묶였다. 원본과 정밀 표시가 준비된 현재 페이지에서도 입력이 막혔다. 숫자·기술 문구가 혼재하고 오류 exception을 Viewer에 길게 표시했다.

## 4. 변경 후 Lifecycle / Source of Truth

`TiffLoadState.qml`는 기존 UiState와 FileBridge.stackState만 읽는 presentation이다. pixel/cache/page index/generation을 새로 저장하지 않는다. Controller의 readonly opening_request는 기존 pending/active 요청에서 파생하며 pending 새 파일이 이전 worker보다 우선한다. bridge의 frameViewable은 실제 frame 존재와 opening request 부재에서 파생한다.

UiState.loading은 **opening OR (initialLoading AND 현재 frame 미준비)**다. backend initialLoading 자체와 decoder/preload 흐름은 그대로다.

| 상태 | 실제 근거 |
| --- | --- |
| EMPTY | 이미지 없음 |
| OPENING | 실제 open 요청 또는 첫 frame 미준비 |
| FIRST_FRAME_READY | 첫 정밀 frame 연결, browse 준비 1페이지, 나머지 있음 |
| STACK_PREPARING | 현재 frame 연결, 실제 browse 준비 2페이지 이상, 전체 미완료 |
| READY | 단일 이미지 또는 browse 전체 준비 완료 |
| ERROR | 실제 open/page 오류 또는 preloadError; 이전/current frame 유무에 따라 차단/비차단 |

빠른 단일 TIFF/JPEG는 OPENING → READY다. 작은 stack의 중간 상태는 event 순서로 존재해도 실제 render 전에 완료될 수 있다. 완료를 인위적으로 늦추지 않는다.

## 5. First Viewable Frame 정의

현재 원본 source, 정확한 dimensions/dtype/page, window와 그 frame의 기존 정밀 표시 준비가 끝나 frameReady가 Main의 imageSource로 연결된 상태다. 전체 browse/pyramid 준비는 전제가 아니다. 일반 TIFF는 source.read_full의 uint16 등 원본 ndarray를 유지한다. 큰 JPEG/큰 단일 TIFF의 원본 준비·표시 pyramid가 끝나기 전에는 공개하지 않는다.

첫 frame에서 Pan/Zoom/Fit/원본 픽셀 확인과 기존 분석 사각형 입력을 사용할 수 있다. 기존 `UiState.canAnalyze` 조건식은 수정하지 않았다. pipeline은 현재 OriginalPixelSource를 필요로 하며 전체 browse cache를 입력으로 사용하지 않는다. backend source와 모델/scope/영역 조건이 충족될 때만 분석을 실행한다. 표시용 8bit frame을 분석 입력으로 연결하지 않는다.

## 6. Full Stack Ready 정의

기존 browse cache의 실제 indices 개수가 metadata page_count와 같고 initialLoading이 해제된 상태다. 각 탐색 entry는 원본 dtype 샘플과 QImage를 가지고, browse 축소가 있는 페이지는 기존 DisplayPyramid도 준비돼 있다. 전체 원본 stack을 RAM에 올렸다는 뜻이 아니다.

## 7. Interaction readiness matrix

| 상태 | Pan / Zoom / Fit | Pixel | Page | 분석 영역 | ImageJ ROI / 처리 | Analysis |
| --- | --- | --- | --- | --- | --- | --- |
| EMPTY / OPENING | 비활성 | 없음 | 비활성 | 비활성 | 비활성 | 비활성 |
| FIRST_FRAME_READY / STACK_PREPARING | 가능 | 현재 원본 | 전체 준비까지 잠금 | 기존 R, Running이면 잠금 | 기존 backend 전체 준비 조건 유지 | 기존 canAnalyze/source/model/scope/영역 조건 |
| READY | 가능 | 기존 raw/정밀 조회 정책 | 기존 전체 탐색/최신 요청 | 기존 조건 | 기존 조건 | 기존 canAnalyze |
| ERROR + retained/current frame | 가능 | 기존 frame | 준비 실패는 잠금 | 기존 좌표/Running 조건 | 실제 기존 backend 조건 | 기존 canAnalyze |
| ERROR + frame 없음 | 비활성 | 없음 | 비활성 | 비활성 | 비활성 | 비활성 |

Context 선택, 새 파일 열기와 close/cancel은 준비 중에도 접근한다. 기존 ImageJ busy/workspace gate도 유지한다.

밝기/대비, Page, ImageJ 작업은 Controller.display_range/page, FileBridge.importRois, ImageJWorkbench.frame, StackMeasurements.require_frame이 실제 initialLoading을 검사한다. 이 backend gate를 UI만 풀지 않았다. ToolActions/AdvancedActions/Import/Edit/StackControls는 같은 파생 readiness로 비활성 이유와 일치시켰다. 분석 영역은 정규화 좌표와 원본 dimensions가 준비돼 있어 안전하게 사용할 수 있다.

## 8. Loading UI / Vocabulary / Accessibility

- OPENING: 중앙 파일명·“파일 여는 중”·실제 취소/닫기 Action. 이전 이미지가 보이면 명시적으로 안내한다. 이전 파일 Header와 metadata를 새 파일 이름으로 덮지 않는다.
- FIRST_FRAME_READY / STACK_PREPARING: 중앙 Overlay 제거. Status Bar에서 “Stack 준비 · N/T”, ViewerContext에서 “현재 페이지 P/T”와 “Stack 준비 중 · N/T 페이지 준비”, 가능한 조작과 잠금 이유를 표시한다.
- READY: “준비 완료”, 완료 확인 Modal/Toast 없음.
- ERROR: 고정된 짧은 안내·다시 열기/다시 준비와 상세 Dialog. frame이 있으면 유지하고 비차단 안내, 없으면 중앙 오류. 원래 diagnostic 문자열은 read-only 상세 창에 유지한다.
- Spinner는 OPENING 중앙 한 곳이며 150ms 표시 지연만 적용한다. 준비 완료 자체는 지연하지 않는다. 짧은 작업에서 불필요한 중앙 flicker를 줄이는 presentation Timer일 뿐 TIFF 상태가 아니다.
- Accessible.name에 실제 상태·숫자 의미를 제공한다. 매 progress마다 별도 announce/live-region 호출은 하지 않는다.
- 별도 cache/decode/memory 환경설정이나 새 Loading 패널은 없다.

## 9. Progress 의미

현재 페이지 P/T는 실제 **표시된 frame**의 index+1이다. prepared N/T는 기존 browse.put이 완료한 실제 indices 수다. metadata를 모르는 OPENING은 indeterminate이며 prepare_native의 chunk/단계 progress를 page count 또는 percent로 해석하지 않는다. 가짜 percent·ETA를 추가하지 않았다.

Header는 기존 두 줄 구조에서 숫자에 “현재”만 추가했다. 준비 count는 Status Bar/ViewerContext에서 확인한다. 상세 오류에 path가 있어도 Primary 문구에 긴 exception을 복제하지 않는다.

## 10. Page Request 정책 / 빠른 이동

정책 C: 전체 탐색 준비 후 페이지 이동을 활성화하는 기존 정책을 유지한다. 현재 frame 조작과 page navigation을 분리했다. 준비된 일부 페이지도 전체 준비 전에는 이동하지 않는다. Slider/버튼/keyboard/wheel/API 모두 Controller의 실제 guard를 따른다. 건너뛰기나 대체 페이지 표시가 없다.

backend guard로 **거절될 요청은 pipeline.invalidate 이전에 반환**하도록 FileBridge.requestPage에 initialLoading 확인을 추가했다. 따라서 first frame의 분석/결과가 End/휠/직접 거절된 page 요청 때문에 사라지지 않는다.

READY 후 기존 cache hit/browse frame/80ms detail/latest pending 흐름은 그대로다. 비캐시 worker 요청 중엔 이전 표시 page를 유지하고 “페이지 Q 준비 중 · 현재 P 유지”로 구분한다. browse preview로 이미 요청 page를 표시한 경우에는 그 page 번호를 표시하고 원본 pixel 준비 정책을 유지한다.

## 11. Generation / Stale / 연속 파일 Open

Controller serial, epoch, cancellation Event, `_done`의 request.serial/epoch 검증을 변경하지 않았다. A의 첫 read 또는 preload 중 B를 열면 기존 token 취소 + pending B를 실행한다. 파생 openingPath는 B를 표시하며 A의 callback은 imageOpened/pageChanged로 공개되지 않는다.

FileBridge의 기존 pipeline.invalidate, ROI pending invalidation, pixel/detail cleanup도 유지했다. 새 성공 frame에서 기존 ROI/source/Result 초기화 정책을 사용한다. 파일 dialog Cancel과 이미 시작된 read의 close/cancel은 다른 동작이다. 후자는 기존 closeImage/clearImage/clear의 epoch·token과 캐시 정리를 사용하며 이전 파일 복구를 약속하지 않는다.

## 12. Partial Failure / Recovery / Cleanup

첫 frame 이후 prepare_browse가 실패하면 기존 preloadError가 남고 자동 준비를 멈춘다. 이 구조에서 실제 부분 실패가 가능하므로 current frame·정밀 표시를 유지하고 나머지 준비 실패/재시도를 제공한다. Page/contrast/ImageJ는 전체 준비 전처럼 잠긴다. retry_preload는 성공한 기존 entries를 유지하고 미완성 페이지부터 재개한다.

OPEN 오류는 initialLoading 해제 후 이전 frame을 유지하거나 빈 ERROR를 표시한다. 다른 파일을 열면 오류를 정리한다. native dialog OS Cancel은 picker 취소일 뿐 loading cancel이 아니다.

종료는 기존 waitForLoads/shutdown 경로다. 새로운 thread나 scheduler는 없으며 decoder 도중에는 기존 취소 체크 경계까지 기다릴 수 있다. 테스트에서 read를 barrier로 잡고 종료하면서 별도 thread에서 read를 풀어 worker 0/reader close/frame cleanup을 확인한다.

## 13. Cache / Memory 영향

decoder, cache 한도·schema·pyramid·preload algorithm은 변경하지 않았다. synthetic before/after의 decode count는 각각 3/32/158로 같고 cache bytes도 같다.

| fixture | browse bytes | raw LRU bytes | display LRU bytes |
| --- | ---: | ---: | ---: |
| 512×512×3 | 2,359,296 | 1,572,864 | 262,144 |
| 1024×1024×32 | 100,663,296 | 6,291,456 | 0 |
| 256×256×158 | 31,064,064 | 393,216 | 0 |

이 값은 완료 시 cache snapshot이며 peak RSS가 아니다. 0 display LRU는 해당 raw page eviction으로 기존 frame cache도 제거된 결과다. retained 현재 frame과 임시 디스크 표시 계층은 별도다. 분석을 더 일찍 실행하면 해당 기존 분석 작업의 메모리와 IO가 preload에 겹칠 수 있으며 이를 측정한 peak RAM 개선으로 주장하지 않는다.

## 14. Pixel/Data Integrity / ROI / Result

생성 uint16 ImageJ TIFF에서 dimensions, 16bit, page_count/frames, 첫/중간/마지막 페이지의 전체 ndarray를 원본 fixture와 비교한다. file SHA256를 표시 범위/탐색/import 작업 전후 비교한다. 표시 범위 1300~45000은 page 변경에도 유지된다.

FIRST_FRAME_READY에서 실제 R drag의 원본 좌표로 ROI 분석을 실행하고 adapter 입력을 원본 uint16 crop과 배열 비교한다. browse/QImage를 source로 사용하지 않는다. ROI 수식/floor·ceil/Manager geometry·import-export를 변경하지 않았다.

분석 영역은 기존 pageChanged에서 초기화한다. ImageJ 생성 기록은 current page, imported global record는 모든 page에 active다. 기존 TD-06/Result 회귀를 함께 실행한다. progress는 Result invalidation/filter/selection 또는 Context 요청을 하지 않는다. 단 실제 분석 완료는 기존 whitelist에 따라 RESULT로 전환한다.

## 15. Benchmark (환경 의존 참고값)

Windows / Python 3.13 / Qt 6.11.2, 실제 Qt 창, 생성 uint16 TIFF. T0은 selectImagePath 호출 직전. T1은 기존 open_stack이 metadata를 확보한 직후, T2는 첫 frameReady, **T3는 첫 frame이 full Overlay 없이 frameSwapped된 시점**, T4는 실제 browse ready다. 생성/초기 앱 시작은 측정 밖이다.

| fixture | 변경 전 T1/T2/T3/T4 (초) | 변경 후 T1/T2/T3/T4 (초) |
| --- | --- | --- |
| 512×512×3 | 0.245 / 4.730 / **7.232** / 7.220 | 0.269 / 4.541 / **4.554** / 6.936 |
| 1024×1024×32 | 0.196 / 1.513 / **40.122** / 40.119 | 0.209 / 1.232 / **1.263** / 50.305 |
| 256×256×158 | 0.740 / 2.211 / **235.553** / 235.548 | 0.430 / 1.889 / **1.905** / 280.851 |

**첫 화면을 전체 준비 전에 사용하는 개선이며 전체 decode/preload 속도 개선은 아니다.** 전체 준비 시간은 이 실행에서 오히려 길었다. OS cache/동시 프로세스/Qt rendering/IO 등에 의존하는 단회 측정이다. 158페이지 fixture는 디스크 여유 부족으로 작게 사용했으며 실제 2.5~2.9GB XRT 성능을 대표하지 않는다. 1536×1536×158 생성 시도는 디스크 쓰기 실패 후 해당 합성 partial fixture만 정리하고 위 크기로 재측정했다.

PASS 기준은 절대 시간 비율이 아니라 **tail worker barrier가 걸린 상태에서 첫 frame render·Pan/Zoom/Fit·원본 입력 작업이 가능하고, 전체 ready는 그 이후에 발생함**이다.

재현:

```powershell
$env:QT_QPA_PLATFORM='windows'
$env:QSG_RENDER_LOOP='basic'
.\.venv\Scripts\python.exe tools/benchmark_tiff_loading.py --label observation
```

Linux 그래픽 세션에서도 같은 도구를 실행할 수 있다. `--output` 기본 artifacts/td07-benchmark에만 합성 데이터/JSON을 쓴다. 기존 실제 TIFF는 읽거나 수정하지 않는다.

## 16. Responsive / 테스트

1100×700과 1440×900에서 Header·현재 page·준비 count·Toolbar·Context·취소 접근의 bounds를 검사한다. 기존 패널 폭과 Theme/Font/Toolbar 구조는 유지한다. Status Bar의 count는 간결하게, 상세 안내는 기존 ViewerContext의 Scroll에 둔다.

새 `test_tiff_loading_ux.py` **15 passed (최종 10.24초)**. 기존 전체 준비 gate 테스트 3개는 첫 frame의 조작 가능과 page/range 잠금을 구분하도록 수정했으며 기존 Cancel/Retry/cache 정리·휠 검증을 유지했다. pressed drag 회귀를 포함한 해당 4개 **4 passed (4.10초)**. 기존 Toolbar/IA/ImageJ/stack QML 검사는 ImageJ/page 진입 전에 backend 전체 준비를 명시적으로 기다린다. backend 전체 준비가 필요한 ImageJ 실행·Undo·Measure·Histogram·Profile과 이미지 복사본 저장도 같은 gate를 사용한다.

- 전체 로컬 회귀 **237 passed, 4 skipped (183.83초)**. offscreen에서 native GUI 4개만 건너뛴다. 첫 실행에서는 236 passed / 4 skipped / 1 failed였으며 기존 측정 테스트가 새 UI.loading 해제 직후 backend 전체 준비를 기다리지 않고 ImageJ를 호출했다. 해당 테스트의 대기를 실제 initialLoading으로 수정하고 전체를 다시 실행했다.
- Ruff / compileall / wheel PASS. QML **64개**를 포함하며 sources/·artifacts/·실제 데이터·모델을 포함하지 않는다. QML fixture/capture 경고 0.
- Windows Qt 실제 창 **합성 화면 13장**. 파이프라인 barrier로 OPENING/첫 frame/부분 준비/실패를 구분했으며 완료를 기다리는 캡처 helper timeout은 기존 직렬 IO에 맞춰 120초로 늘렸다. 이는 앱 준비 속도를 바꾸는 변경이 아니다. 마지막 고의 손상 fixture의 tifffile diagnostic은 예상한 ERROR 검증이다.
- Windows AWT/Swing/ImageJ plugin 실제 창: `tests/test_stack_compatibility.py -k gui_plugin` **4 passed, 5 deselected (58.34초)**. 전체 로컬 고유 검사 **241개**를 확인했다. TIFF worker 종료 검사는 active read 취소·pool/reader/frame 정리를 별도로 검사한다.
- OS 파일 선택 창의 사람 마우스 조작·실제 대형 XRT·실제 모델은 이 TD에서 재검증하지 않았다. 기존 native dialog/engine teardown COM `0x80010108` 장시간 재현·수정은 이 4개 plugin 검사 통과와 별개다.

| 상태 / 크기 | 실제 Windows Qt 화면 (합성 데이터) |
| --- | --- |
| 빈 화면 / OPENING | [EMPTY](../screenshots/loading-td07/empty-1100.png) · [OPENING](../screenshots/loading-td07/opening-1100.png) |
| 첫 frame / 조작 조건 | [첫 frame](../screenshots/loading-td07/first-frame-1100.png) · [현재 페이지 조작](../screenshots/loading-td07/first-frame-controls-1100.png) |
| 부분 준비 / 두 크기 | [1100×700](../screenshots/loading-td07/stack-preparing-1100.png) · [1440×900](../screenshots/loading-td07/stack-preparing-1440.png) |
| 부분 오류 / 상세 | [현재 frame 유지](../screenshots/loading-td07/partial-error-1100.png) · [오류 상세](../screenshots/loading-td07/error-details-1100.png) |
| 준비 완료 / 탐색 / JPEG | [READY](../screenshots/loading-td07/ready-1100.png) · [중간 page](../screenshots/loading-td07/middle-page-1100.png) · [JPEG](../screenshots/loading-td07/jpeg-ready-1100.png) |
| 다른 파일 여는 중 / 실패 | [이전 파일과 새 요청 구분](../screenshots/loading-td07/replace-opening-1100.png) · [열기 실패·이전 frame 유지](../screenshots/loading-td07/open-error-retained-1100.png) |

## 17. 제약 / 범위 / 후속

일반 stack은 첫 frame을 사용할 수 있지만 페이지 이동·대비·ImageJ 작업은 기존 전체 준비 조건을 유지한다. 미준비 page on-demand navigation은 이번 단계에 추가하지 않았다. 큰 단일 TIFF/JPEG는 기존 정밀 계층 준비 시간을 먼저 기다린다. 원본 decode 중 즉시 interrupt는 보장하지 않는다.

decoder/원본 파일/dtype/bit-depth/order/orientation/metadata/분석 입력/ROI geometry/계약 버전·스키마·해시/ImageJ/Fiji/macros/plugins/cache format 변경 없음. sources/와 다른 저장소를 수정하지 않는다. 원본 XRT·모델은 commit하지 않는다.

TD-08 Visual Density와 최종 통합 검증(실제 대형 XRT·실제 모델·장시간 native dialog/종료)은 별도 범위다. TD-05의 Windows COM `0x80010108` 진단을 해결했다고 주장하지 않는다. 이번 worker 종료 테스트는 그 native dialog 경로와 별개다.
