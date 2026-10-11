# XRT-PERF-TD-02 Result

## Status

**PARTIAL** — 화질 PASS(검사 영역), 자동 성능 PARTIAL, 실제 사용자 입력 PENDING.
고배율 원본 표시와 캐시 재사용은 확인했지만 Fit의 다량 후보/level 전환 비용은 남아 있다.
GPU upload 단독 시간과 물리 화면 반응은 미측정이다.
Issue [#84](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/84).

## 기준 Git 및 환경

- Start Branch: `perf/81-viewer-render-investigation`
- Start HEAD: `18b9b9cdc27332ada788097866507d05851aa012`
- Final Branch: `perf/84-viewer-interaction-validation`
- Windows 11 10.0.26200, Python 3.13.7, Qt **6.11.2**, D 드라이브 작업 환경.
- Intel Core i7-13700 (16 cores / 24 logical processors), RAM 34,088,583,168 bytes.
- Qt가 선택한 RTX 3050 / NVIDIA driver 591.86. 다른 앱이 실행 중인 환경이며 CPU·RSS·available memory를 case마다 기록한다.
- 제품 실행: `D:\capstone\run-analyzer.cmd`.
- 기본 설정, 기존 stacked PR #56~#82, 사용자 `AGENTS.md`, `sources/` 보존.

## 1. Viewer Architecture / TD-01 확인

| 역할 | 실제 구현 | 처리 방식 |
|---|---|---|
| 진입점 | `src/sic_xrt_analyzer/__main__.py` | Windows `QApplication`, 기본 `QSG_RENDER_LOOP=basic` |
| 파일·페이지 읽기 | `ui/stack_controller.py`, `imaging/image_stack.py`, `imaging/tiff_stack.py` | 단일 Python QRunnable worker, replaceable pending request, serial/epoch stale guard |
| JPEG 원본 | `imaging/prepared_image.py::PreparedPixels` | 읽기 전용 입력 → 1회 libjpeg decode → 임시 disk mmap RGB8 |
| TIFF 원본 | `imaging/display_pyramid.py::DisplayPyramid` | readonly TIFF mmap; 불가하면 기존 disk native-copy 경로 |
| 표시 계층 | `DisplayPyramid`, `DisplayGroup` | disk mmap area-average levels; 각 영역을 복사해서 표시 |
| 미리보기 | `ui/bridge.py::TiffImageProvider` | QImage provider; prepared 모드에서는 큰 Image 표시 대신 PreparedView 사용 |
| 정밀 표시 | `ui/prepared_view.py::PreparedView` | viewport-sized QQuickPaintedItem, 현재 원본 영역 계산 후 CPU QPainter |
| 변환 캐시 | `PreparedView._display_cache` | 한 QImage, 128 physical-pixel margin, **32MiB** 상한 |
| 원본 프레임·탐색 캐시 | `TiffStack` | 기존 raw 96MiB/3페이지, display 32MiB, browse 별도 제한 유지 |
| 전체 표시 계층 캐시 | `DisplayGroup` | 기존 임시 디스크 4GiB 상한 유지 |
| 좌표·배율 | `ui/ImageViewer.qml` | `displayScale = zoom / displayPixelRatio`; imageFrame 위치 + 원본 좌표 × scale |
| 후보 | `ImageViewer.qml::analysisOverlay` | viewport Canvas 한 개; filteredPoints 순회, 화면 밖 중심 skip |
| 가져온 ROI | `ui/ImportedRoiOverlay.qml` | 별도 viewport Canvas; 원본 좌표 transform, 기존 page/active 정책 |
| Header·Loading | `ViewerHeader.qml`, `ImageViewer.qml`, loadFlow | 메타데이터·blocking 로딩·오류; 기존 UX 유지 |

TD-01의 DemoImage `Loader.active=demoMode`와 기존 viewport QImage 캐시는 그대로다.
정밀 표시에서는 `syncDetailView` fallback을 사용하지 않고, paint 때 최신 transform으로
prepared 원본 영역을 사용한다. Zoom/Pan 동안 별도의 비동기 viewport decode queue는 없다.
Worker 취소/무효화는 파일·페이지 읽기 경로에 적용된다. TIFF의 ImageJ `frames`를 공간 Z로 해석하지 않는다.

## 2. Qt Graphics Backend / Software·Hardware / Thread

제품과 같은 Windows QApplication/basic loop를 쓰는 진단 프로세스에서
`rendererInterface().graphicsApi()` 및 `QSG_INFO=1` 로그를 함께 확인한다.
기본 backend는 **Direct3D11**, Qt RHI가 선택한 adapter는 **NVIDIA GeForce RTX 3050**.
OS 인벤토리에는 Intel UHD Graphics 770도 있지만 이번 실제 Qt 선택과 구분한다.
소프트웨어 비교는 새 테스트 프로세스에만 `QT_QUICK_BACKEND=software`를 준다.
제품 기본 설정을 강제로 바꾸지 않는다.

basic loop의 PreparedView paint thread ID는 기록한 Python GUI main-thread ID와 일치했다.
이 구성에서는 CPU paint/변환을 별도 render worker가 처리한다고 주장할 수 없다.
GPU는 별도로 명령을 실행한다. GUI timer gap은 이벤트 처리 지연의 관측치이며
OS scheduling/진단 event pumping도 포함하므로 전부 한 함수의 blocking 시간으로 단정하지 않는다.

PreparedView의 실제 renderTarget은 `Image`: CPU raster QImage → Qt scene graph texture 경로.
뷰포트 크기가 backing 크기이며 Zoom에 따라 12,349×12,273 원본 전체 크기로 커지지 않는다.
이는 코드·item 크기·Qt 문서에 근거한 경로 설명이다. GPU transfer byte 수나 fence 완료 실측은 아니다.

자료: [Qt 6.11 QQuickPaintedItem](https://doc.qt.io/qt-6.11/qquickpainteditem.html),
[Qt 6.11 QQuickWindow](https://doc.qt.io/qt-6.11/qquickwindow.html),
[Qt 6.11 Canvas](https://doc.qt.io/qt-6.11/qml-qtquick-canvas.html).

## 3. Mouse Input / Zoom·Pan Pipeline / 계측 의미

`tools/benchmark_viewer_interaction.py`는 제품 QML·bridge·원본 reader·model adapter를
실제로 실행하며, 모든 출력은 ignored `artifacts/perf-td02/`에 둔다.
테스트 QSettings를 사용해 사용자 설정을 바꾸지 않는다.

Pan은 QTest press/move/release로 기존 MouseArea의 `onPositionChanged`를 통과한다.
Zoom은 명시적인 physical zoom 값 변경이며 입력 장치 전달을 흉내냈다고 주장하지 않는다.
반복 Pan은 작은/큰 이동과 방향 반전을 포함하고, burst는 여러 상태 변경을 한꺼번에 전달한다.

| 계측 | 의미 / 제한 |
|---|---|
| command start | QTest 또는 programmatic command 직전 perf_counter |
| event reception | window eventFilter의 MouseMove 도착; 인간 입력 시점 아님 |
| state | panX/panY/zoom/fitMode signal 첫 도착; no-op이면 null |
| dispatch_process | 명령과 processEvents 반환; paint를 포함할 수 있어 state 시간과 구분 |
| region_ready | 이번 command의 region 반환 시점; hit의 0은 기존 cache가 준비됐음을 뜻함 |
| region | 기존 DisplayPyramid.region CPU 시간 (mmap crop copy 포함) |
| conversion | render_samples CPU 시간; QImage format conversion 별도 분리 불가 |
| paint | PreparedView.paint CPU 시간; GPU 시간 아님 |
| prepared | command → 해당 transform의 paint 완료 |
| sync / render submit | Qt before/after callbacks CPU 구간; GPU fence 시간 아님 |
| frameSwapped | paint 이후 Qt frame 제출; **물리 모니터 표시 시점 아님** |
| frame interval | 연속 Pan에서 완료된 Qt 제출 간격; idle FPS 아님 |
| GUI timer gap | 5ms timer 사이 gap; paint thread ID와 함께 판단 |
| CPU | process CPU time / elapsed, 1 core=100%; OS 전체 CPU% 아님 |
| Memory | process RSS; mmap working set 포함, Python heap만의 크기 아님 |
| GPU upload / render fence / usage / memory | 별도 계측하지 못한 값은 **NOT MEASURED** |

반복 표는 각 case N=30, median/P95/max/min와 50/100ms 초과 수를 보존한다.
Cold display-cache 1회 진단은 warm 반복 통계와 분리한다. OS 파일 캐시를 비우지 않으므로
첫 open을 물리 디스크 cold-read 벤치마크로 부르지 않는다. 타 앱·OS 스케줄링 영향도 포함한다.

계측은 명시적으로 view.update/window.update도 요청해 같은 transform의 실제 paint를 확인한다.
따라서 제출 간격에는 도구의 event pumping/추가 invalidation이 포함된다.
command 수와 paint 수의 차이만으로 제품의 불필요한 렌더 횟수를 단정하지 않는다.
각 command 이후 일치하는 transform의 paint 및 이후 frameSwapped를 요구하며,
추가 paint 중 가장 이른 유효 제출을 latency로 사용한다.

## 4. Texture Upload / CPU·GPU 병목 구분

PreparedView cache hit에서도 CPU QPainter는 viewport QImage backing을 다시 그린다.
하드웨어 backend에서 Qt가 그 backing을 texture로 전달하는 구조는 확인했다.
실제 upload 시간·범위·GPU residency는 NOT MEASURED이며, paint 횟수로 upload 횟수를 대체하지 않는다.
일반 QImage provider와 prepared 표시 경로를 혼동하지 않는다.
32MiB 변환 캐시가 GPU texture cache라고 주장하지 않는다.

## 5. Candidate Overlay / 정확성

실제 연구 모델을 다시 실행하고 기존 TD-12 export의 `predictions`와 **전체 값 동등성**을 확인한다.
전체 2,946 / BPD245 / TED1398 / TSD1303. 합성 후보로 이 수를 채우지 않는다.
Overlay OFF / ALL / BPD / TED / TSD / SELECTED를 동일 input trajectory와 zoom에서 비교한다.
선택 Focus는 기존 450ms animation이 끝난 뒤 화면 중심과 hit-test를 검사한다.

기존 코드에서 화면 밖 후보는 circle draw 전에 제외하지만 배열 순회는 O(N)이다.
후보마다 QML Item을 생성하지 않고 Canvas 한 개를 다시 그린다.
Mouse hover는 좌표·pixel status 갱신이며 후보 전체 hit-test는 release 시 작은 이동(<4px)의 클릭에서 수행한다.
선택 label/십자·반지름·index·filter·좌표·ROI는 변경하지 않는다.
별도 진단 복사본에서는 Canvas JS 그리기 명령 기록 시간을 계측한다(Date.now, 1ms 해상도).
이는 Canvas raster/texture upload 전체 시간이 아니다. GPU 시간은 전체 완료 프레임이며 Overlay만의 시간이 아니다.

Fit에서는 대부분의 후보가 화면 안에 있고(진단 이동 중 전체 2,845~2,946개), 400%에서는 대부분이 화면 밖이다.
따라서 Fit의 전체 후보 부하를 400% 수치로 대표하지 않는다.
이번 초기 반복에서는 125% DPI Fit↔80% Fit이 level 경계를 오가면서
30회 Zoom 모두 region/LUT cache miss였다. level0 안의 400%↔320%는 첫 refill 뒤
대부분 hit였다. 단일 bounded cache의 비용을 기록하며 임의의 확대는 하지 않는다.

## 6. 화질 / 원본 Crop / 정밀 표시

독립 imagecodecs JPEG decode 및 readonly tifffile mmap에서 동일 원본 영역을 읽고
원본 source.read_region과 대조한다. 실제 window.grabWindow() 픽셀은 화면 제출 수치와 별도로 검사한다.
100/200/400/800%에서 기존 low/high·invert·RGB를 적용한 nearest 원본 기준과 비교한다.
uint16 원본은 그대로 유지하고 표시 bytes만 uint8로 변환한다.
fractional DPI에서는 physical screen pixel과 logical viewport를 구분한다.

화면 좌상단 crop의 fractional clip 경계 2 physical pixels는 제외하고 **124×92 내부 픽셀**을
오차 허용 없이 비교한다. 125%에서는 viewport top이 y=152.5 physical pixels여서 맨 위 clip
경계가 배경으로 찍힐 수 있다. 이 기하학적 경계와 내부 bilinear blur를 분리한다.

본 경로는 고배율에서 level0 원본을 사용한다. Fit/reduction은 기존 area-average pyramid와 smooth reduction.
원본 픽셀 경계·노이즈가 확대되어 보이는 것은 실제 정보 손실과 구분한다.
새 sharp/denoise/AI/색 보정은 추가하지 않는다.
Burst 직후와 TIFF first/middle/last/first 이동 뒤 crop/pixel 값도 대조한다.
연속 입력 중 모든 물리 화면 frame 캡처는 못하므로 일시적 표시 현상의 인간 검증은 PENDING이다.

## 7. Cache / Memory / 파일·페이지 전환

Cache key는 pyramid identity, low/high, invert, palette bytes, level이며 viewport 포함 여부를 검사한다.
한 영역의 확대·축소·작은 pan은 재사용, cache margin 밖 이동·level/window/source 변경은 refill.
큰 영역에서 돌아와도 단일 cache이므로 이전 영역이 eviction되면 miss가 정상이다.
source.validate_identity는 hit에서도 호출된다. 실제 원본은 변경하지 않고 synthetic 회귀가 변경 감지를 검사한다.

파일 교체 시 old prepared pyramid는 close되고, 새 key만 사용하며 이전 분석 후보가 비워진다.
close 후 backing cache는 다음 paint/item destruction 때 해제; 숨겨진 item이라 paint가 없으면
최대 32MiB display cache가 잠시 남을 수 있다. OS RSS 반환은 allocator/working-set 정책 때문에 즉시 0이 아니다.
TIFF 페이지가 바뀌면 기존 ROI page 의미를 유지하는 정책과 serial/epoch guard를 확인한다.

## 8. DPI / 실제 사용자 입력

100/125/150%는 새 진단 프로세스의 `QT_SCALE_FACTOR`를 통해 검사한다.
OS monitor 설정을 직접 바꾼 테스트가 아니며 실제 DPR을 결과에 기록한다.
Sky Computer Use의 native pipe 접근이 2회 모두 `os error 2`로 실패했다.
반복 초기화 시도를 중단했다. **MANUAL INPUT VALIDATION PENDING**.
QTest 자동 이벤트를 실제 마우스 PASS로 올리지 않는다.

사용자 수동 체크:

1. `D:\capstone\run-analyzer.cmd` 실행, 실제 JPG 열기.
2. 100/200/400/800%에서 천천히·빠르게·좌우 반전 Pan 각각 10회.
3. 100→200→400→800→400→100 Zoom 순서를 10회.
4. 400%→오른쪽→아래→800%→왼쪽→200% 혼합을 10회.
5. 실제 2,946개 결과에서 OFF/ALL/BPD/TED/TSD 및 후보 선택·Focus로 반복.
6. 400% JPG→TIFF, first→middle→last→first에서 검은 frame·이전 이미지·좌표 튐·입력 무시 확인.
7. OS 125/150% 화면에서 반복하고, 체감 끊김 시 배율·필터·시각·파일·동작 기록.

Native file dialog Acceptance는 TD-13 별도이며 이 수동 Viewer 체크가 대신하지 않는다.

## 9. 적용 수정 / Before·After / 후속 작업

Baseline을 먼저 수집했다. 새 renderer·cache 확대·제품 backend 변경은 없다.
125% Direct3D11에서 CPU 원본 raster는 정확하지만 마지막 texture의 smooth=true 보간이
반 픽셀 origin에서 인접 샘플을 섞는 것을 확인했다. 동일 clip 제외 crop의 내부 최대 오차는
100/200/400/800%에서 14/13/10/9였다. 테스트에서 texture smooth만 끄면 모두 0이 됐다.
제품에 `smooth: displayScale * displayPixelRatio < 1` 한 binding을 추가해,
기존 QPainter의 native nearest / reduced smooth 정책을 최종 scene graph에도 맞췄다.
진단 강제 옵션 없이 제품 수정 상태의 같은 crop이 모두 정확히 일치한다.
원본 픽셀·좌표·배율·ROI·분석 입력은 변경하지 않았다.
새 계측 도구와 fractional DPI 원본 무결성 회귀를 추가한다.
TD-01의 4,409ms(n=2)를 이번 반복 Baseline이나 개선율 계산에 사용하지 않는다.

두 번째 원인도 별도로 확정했다. 숨긴 Candidate Canvas의 onPaint가 계속 후보를 순회하고
Fit에서 2,946개 명령을 기록했다(JS median 10ms, N=35). `c.reset()` 뒤 `if (!visible) return`을
추가해 숨긴 상태의 후보 읽기/명령을 중단한다. 다시 표시하면 기존 onVisibleChanged가 현재 후보를 그린다.
수정 후 같은 진단의 숨김 후보 처리 수는 0, JS median/max 0ms(1ms 해상도)다.
회귀는 후보 좌표 getter로 숨긴 Pan의 geometry 접근이 0이고 재표시 때 접근이 재개됨을 확인한다.
선택·hit-test·후보 값·좌표·캐시 크기를 변경하지 않는다.

### GPU 완료 프레임 진단

`tools/probe_viewer_gpu.py`는 새 테스트 창을 숨긴 상태에서 timestamps를 설정한 뒤 표시한다.
제품 backend/loop는 바꾸지 않는다. Qt render-thread callback에서 빌린 QRhi/SwapChain 포인터를
소유하거나 삭제하지 않고 읽는다. RTX 3050/Direct3D11 timestamps 지원을 실제 확인했다.
`lastCompletedGpuTime()`은 이전 완료 프레임의 값(여러 callback에서 같은 값일 수 있음)이므로
현재 입력의 GPU 지연이나 upload 시간으로 해석하지 않는다. 초기 5회 제외 후 30회 읽기다.
진단의 계측 복사본은 성능 표의 Before/After 반복 프로세스와 분리한다.

자료: [Qt 6.11 QSGRendererInterface](https://doc.qt.io/qt-6.11/qsgrendererinterface.html),
[Qt 6.11 QQuickGraphicsConfiguration](https://doc.qt.io/qt-6.11/qquickgraphicsconfiguration.html),
[Qt 6.11 QRhiCommandBuffer](https://doc.qt.io/qt-6.11/qrhicommandbuffer.html).

| 조건 | GPU 완료 프레임 median / P95 / max ms | JS 명령 median / max ms | 기록 후보 min~max |
|---|---:|---:|---:|
| Fit OFF | 3.77 / 4.11 / 4.56 | 0 / 0 | 0 |
| Fit ALL | 5.84 / 14.04 / 15.27 | 10 / 18 | 2,845~2,946 |
| Fit BPD | 1.97 / 10.10 / 12.13 | 1 / 2 | 239~245 |
| Fit TED | 1.55 / 6.03 / 9.15 | 5 / 7 | 1,348~1,398 |
| Fit TSD | 2.00 / 11.37 / 12.33 | 4 / 7 | 1,258~1,303 |
| 400% OFF | 3.71 / 9.57 / 10.12 | 0 / 0 | 0 |
| 400% ALL | 2.07 / 4.43 / 4.45 | 2 / 6 | 2~3 |

JS N=35. GPU adapter 주파수/이전 프레임/타 앱 부하 영향 때문에 ON/OFF GPU 차이만으로
최적화 개선율을 주장하지 않는다. GPU 사용률은 NOT MEASURED.
QRhi memory statistics가 이 backend에서 0을 반환하므로 GPU memory도 NOT MEASURED(실제 사용량 0이라는 뜻 아님).
upload 횟수·bytes·시간 및 Overlay GPU 단독 시간은 NOT MEASURED로 유지한다.

## 10. 원본·회귀·RC / Qt 6.12

실제 원본 SHA before/after, original dtype/bit depth/page order, candidate values, ROI geometry,
분석 입력·ONNX 모델·분류·Export·Image Copy·Native Dialog·Toolbar/Context/Analysis/Result/ROI/Preflight/Loading
계약을 보존한다. 모델과 원본·private logs·큰 captures는 커밋하지 않는다.

Issue [#83](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/83)의 Qt6.12 full-suite 종료
bool_dealloc은 별도 미확정 문제다. Qt6.11.2 기준이며 이 TD에 그 수정이나 테스트 삭제를 섞지 않는다.
전체 RC는 **RC CODE READY — MANUAL VALIDATION PENDING**이며 성능 자동 결과로 승격하지 않는다.

## 측정 결과 및 최종 Regression

측정일: 2026-10-11. raw JSON·tiny crop PNG·실패 로그는 ignored artifacts/perf-td02/에 보존한다.

### 판정 기준과 측정 범위

TD-01 final baseline의 고배율 제출 median 약 15ms와 Fit의 70~100ms를 먼저 확인했다.
이 환경의 자동 고배율(100~800%) 확인 기준은 command→Qt 제출 median ≤50ms,
P95 ≤100ms, max ≤250ms로 정한다. Fit도 같은 기준으로 보고하며 기준을 완화해 PASS로 만들지 않는다.
이 기준은 물리 마우스 지연/FPS 목표가 아니다. cold display-cache 단회는 warm 통계와 합치지 않는다.
window가 가려져 `isExposed=false`, paint/frame 증가가 없었던 실행은 완료 지연 수치를 만들지 않고
실패 로그를 보존한 뒤 재측정한다. 이 경우를 제품 crash 또는 GUI freeze로 판정하지 않는다.

초기 도구(`22bf8ff`)의 JPEG burst 후 100% 화질 행은 INVALID다. 선택 후보를 클릭하면 정상적인
두 번째 Focus 애니메이션이 시작되는데 도구가 기다리지 않았다. 캡처 당시 logical scale은 3.90625로,
요청한 100%와 달랐다. 원본 화질 저하로 판정하지 않고 해당 행을 제외한다.
도구(`b45a9ba`)에 재클릭 Focus 대기와 요청 배율/원본 비교 assertion을 추가했다.
6개 backend/DPI의 JPEG 완료 화질·burst 검사를 별도 quality-only 실행으로 다시 검증했고 모두 정확히 일치했다.
반복 성능 표는 이 단계 이전의 동일 `22bf8ff` 도구와 trajectory를 사용한 Before/After만 비교한다.
TIFF에는 이 후보 Focus 동작이 없으며 기존 burst 검사도 정확히 일치했다.

자동 화질 비교는 후보·ROI 그래픽을 숨긴 검사 영역의 완료 화면이다.
Overlay 표시 중 좌표/선택/focus는 별도 자동 회귀와 실제 모델 결과 동일성으로 검사하며,
연속 이동 중 모든 물리 프레임 및 Overlay와 겹친 영역의 화질은 수동 PENDING이다.
800%는 실제 파일로 확인한다. 1,600%는 작은 회귀 fixture의 binding 검사만 했으므로
실제 XRT 반응성 측정 결과로 올리지 않는다.


### Zoom Benchmark

실제 JPG / Direct3D11 / DPR 1.25 / viewport 974×750 logical / ALL 2,946.
command→일치하는 원본 영역 paint→Qt 제출(ms). Fit 행의 Zoom은 Fit↔80% Fit 반복이다.

| 배율 | Median | P95 | Max | Min | N | >100ms |
| --- | --- | --- | --- | --- | --- | --- |
| Fit | 66.91 | 85.11 | 94.80 | 52.48 | 30 | 0 |
| 100% | 15.32 | 18.31 | 35.42 | 10.18 | 30 | 0 |
| 200% | 15.33 | 16.63 | 18.94 | 10.21 | 30 | 0 |
| 400% | 15.24 | 16.13 | 16.51 | 14.11 | 30 | 0 |
| 800% | 15.10 | 16.62 | 16.80 | 13.58 | 30 | 0 |

### Pan Benchmark

동일 조건의 QTest Pan. Frame interval과 제출 latency는 서로 다른 값이다. 각 숫자 묶음은 median / P95 / max ms.

| 배율 | CPU paint median | 제출 간격 | 입력→Qt 제출 | event / state median | N |
| --- | --- | --- | --- | --- | --- |
| Fit | 0.83 | 54.41 / 67.28 / 68.63 | 53.39 / 65.63 / 67.32 | 0.06 / 0.31 | 30 |
| 100% | 0.49 | 16.71 / 17.96 / 18.92 | 15.50 / 17.05 / 20.87 | 0.06 / 0.36 | 30 |
| 200% | 0.45 | 16.57 / 17.73 / 18.02 | 15.21 / 16.43 / 16.88 | 0.06 / 0.33 | 30 |
| 400% | 0.42 | 16.61 / 17.74 / 17.76 | 15.35 / 16.39 / 17.46 | 0.07 / 0.37 | 30 |
| 800% | 0.50 | 16.53 / 17.99 / 18.40 | 15.35 / 16.96 / 17.88 | 0.07 / 0.39 | 30 |

### Overlay Benchmark — Fit

Direct3D11 / DPR 1.25. Pan·Zoom·Frame은 median / P95 / max ms, 각각 Pan/Zoom N=30, interval N=29. CPU는 1 core=100%.

| 조건 | 후보 수 | Pan | Zoom | Frame interval | CPU% | RSS MiB |
| --- | --- | --- | --- | --- | --- | --- |
| OFF | 0 | 15.31 / 16.50 / 16.69 | 28.66 / 32.36 / 42.04 | 16.62 / 17.77 / 17.89 | 70.12 | 1120.92 |
| ALL | 2946 | 53.39 / 65.63 / 67.32 | 66.91 / 85.11 / 94.80 | 54.41 / 67.28 / 68.63 | 122.50 | 1158.03 |
| BPD | 245 | 15.53 / 17.47 / 17.97 | 24.31 / 30.81 / 44.46 | 16.84 / 18.51 / 19.15 | 83.46 | 1162.70 |
| TED | 1398 | 31.98 / 33.63 / 33.88 | 45.13 / 64.52 / 74.27 | 33.45 / 34.90 / 35.47 | 110.97 | 1156.95 |
| TSD | 1303 | 32.36 / 47.19 / 53.52 | 41.25 / 61.83 / 76.42 | 33.76 / 48.90 / 53.62 | 109.08 | 1164.48 |
| SELECTED | 2946 | 48.04 / 52.91 / 53.33 | 70.95 / 87.15 / 117.05 | 49.66 / 54.64 / 54.92 | 121.61 | 1168.63 |

### Overlay Benchmark — 400%

Direct3D11 / DPR 1.25. Pan·Zoom·Frame은 median / P95 / max ms, 각각 Pan/Zoom N=30, interval N=29. CPU는 1 core=100%.

| 조건 | 후보 수 | Pan | Zoom | Frame interval | CPU% | RSS MiB |
| --- | --- | --- | --- | --- | --- | --- |
| OFF | 0 | 15.41 / 16.35 / 16.71 | 15.28 / 16.70 / 17.10 | 16.70 / 17.49 / 17.79 | 40.52 | 1161.14 |
| ALL | 2946 | 15.35 / 16.39 / 17.46 | 15.24 / 16.13 / 16.51 | 16.61 / 17.74 / 17.76 | 59.35 | 1162.73 |
| BPD | 245 | 15.29 / 17.06 / 17.72 | 15.45 / 16.31 / 16.70 | 16.61 / 17.70 / 18.76 | 48.31 | 1162.69 |
| TED | 1398 | 15.52 / 16.63 / 16.72 | 15.54 / 16.21 / 16.53 | 16.99 / 17.92 / 18.01 | 40.58 | 1162.88 |
| TSD | 1303 | 15.35 / 17.00 / 17.41 | 15.35 / 16.40 / 17.05 | 16.90 / 17.90 / 18.66 | 49.93 | 1163.09 |
| SELECTED | 2946 | 15.37 / 16.74 / 17.16 | 15.32 / 16.65 / 17.09 | 16.68 / 17.72 / 18.01 | 48.37 | 1165.77 |

### Software / Hardware

실제 JPG ALL / DPR 1.25 / 동일 trajectory·cache 초기화·모델 결과·계측 도구. 숫자는 median / P95 / max ms, 각 N=30.

| 조건 | Software | Direct3D11 |
| --- | --- | --- |
| 100% Zoom | 11.55 / 13.75 / 43.41 | 15.32 / 18.31 / 35.42 |
| 200% Zoom | 9.77 / 11.56 / 19.54 | 15.33 / 16.63 / 18.94 |
| 400% Zoom | 10.14 / 11.50 / 16.94 | 15.24 / 16.13 / 16.51 |
| 800% Zoom | 9.57 / 10.75 / 16.38 | 15.10 / 16.62 / 16.80 |
| 400% Pan OFF | 10.31 / 13.78 / 14.14 | 15.41 / 16.35 / 16.71 |
| 400% Pan ALL | 12.28 / 15.89 / 17.09 | 15.35 / 16.39 / 17.46 |
| 400% Pan BPD | 10.17 / 16.27 / 16.51 | 15.29 / 17.06 / 17.72 |
| 400% Pan TED | 10.70 / 14.56 / 15.26 | 15.52 / 16.63 / 16.72 |
| 400% Pan TSD | 10.74 / 14.95 / 15.30 | 15.35 / 17.00 / 17.41 |

### DPI / backend 확인

각 행은 독립 프로세스. 실제 모니터 설정 변경이 아닌 QT_SCALE_FACTOR 검사다. 모든 반복 조건/검사 crop이 완료된 실행만 사용한다.

| DPR | Backend | 400% ALL Pan | 400% ALL Zoom | JPG crop | 후보·Focus·latest transform |
| --- | --- | --- | --- | --- | --- |
| 1.25 | Direct3D11 | 15.35 / 16.39 / 17.46 | 15.24 / 16.13 / 16.51 | exact | PASS |
| 1.25 | Software | 12.28 / 15.89 / 17.09 | 10.14 / 11.50 / 16.94 | exact | PASS |
| 1.0 | Direct3D11 | 14.86 / 16.85 / 20.64 | 15.28 / 16.79 / 16.92 | exact | PASS |
| 1.0 | Software | 5.64 / 7.07 / 9.22 | 5.19 / 7.23 / 7.29 | exact | PASS |
| 1.5 | Direct3D11 | 15.09 / 17.76 / 21.42 | 15.11 / 17.08 / 17.53 | exact | PASS |
| 1.5 | Software | 12.53 / 16.97 / 17.63 | 10.24 / 10.87 / 19.24 | exact | PASS |

### Before / After — TD-01 final과 같은 조건

Baseline은 정확한 18b9b9c Viewer QML, After는 두 최소 수정 적용 제품 QML. JPG / hardware / 125% / N=30 / 계측 도구 SHA 동일.
cache 초기 상태/trajectory는 동일하지만 OS cache·타 앱 부하·GPU clock을 고정하지 않았다. 아래 차이를 전체 시스템 개선율로 일반화하지 않는다.

| 배율·Overlay | Before Pan | After Pan | Before Zoom | After Zoom |
| --- | --- | --- | --- | --- |
| Fit / OFF | 68.57 / 82.10 / 82.75 | 15.31 / 16.50 / 16.69 | 100.09 / 142.54 / 163.83 | 28.66 / 32.36 / 42.04 |
| Fit / ALL | 80.64 / 89.15 / 90.77 | 53.39 / 65.63 / 67.32 | 93.53 / 114.95 / 132.51 | 66.91 / 85.11 / 94.80 |
| 1 / OFF | 15.17 / 17.23 / 19.99 | 15.29 / 16.78 / 20.98 | 15.23 / 16.99 / 38.96 | 15.48 / 17.48 / 36.17 |
| 1 / ALL | 15.44 / 16.13 / 19.84 | 15.50 / 17.05 / 20.87 | 15.42 / 17.22 / 38.84 | 15.32 / 18.31 / 35.42 |
| 4 / OFF | 15.17 / 16.86 / 17.48 | 15.41 / 16.35 / 16.71 | 15.14 / 16.28 / 16.79 | 15.28 / 16.70 / 17.10 |
| 4 / ALL | 15.40 / 17.57 / 23.03 | 15.35 / 16.39 / 17.46 | 15.02 / 16.46 / 16.67 | 15.24 / 16.13 / 16.51 |

### Cache / CPU 구간

JPG ALL / DPR 1.25 / hardware. 각 case에는 Pan 30 + Zoom 30, cold sample 제외.

| 배율 | Pan hit | Zoom hit | region / conversion calls | decode calls | cold 1회 제출 ms | GUI timer gap max ms |
| --- | --- | --- | --- | --- | --- | --- |
| Fit | 30 | 0 | 30 / 30 | 0 | 32.28 | 84.66 |
| 1 | 30 | 29 | 1 / 1 | 0 | 28.80 | 31.16 |
| 2 | 30 | 29 | 1 / 1 | 0 | 16.04 | 13.88 |
| 4 | 30 | 29 | 1 / 1 | 0 | 15.80 | 12.92 |
| 8 | 30 | 29 | 1 / 1 | 0 | 14.00 | 14.74 |

### 실제 TIFF 반복

최종 두 수정 적용 / Direct3D11 / DPR 1.25 / OFF. 각 배율 Pan·Zoom N=30. 수치는 median / P95 / max ms.

| 파일 | 배율 | Pan | Zoom | Frame interval |
| --- | --- | --- | --- | --- |
| N119_220_Section_stack_flipped.tif | Fit | 15.07 / 16.74 / 17.24 | 22.36 / 28.47 / 34.04 | 16.55 / 18.19 / 18.49 |
| N119_220_Section_stack_flipped.tif | 1 | 15.45 / 16.19 / 28.40 | 15.63 / 18.55 / 31.34 | 16.75 / 17.53 / 29.55 |
| N119_220_Section_stack_flipped.tif | 2 | 15.26 / 16.74 / 16.89 | 15.10 / 16.66 / 17.40 | 16.60 / 18.02 / 18.31 |
| N119_220_Section_stack_flipped.tif | 4 | 15.35 / 16.95 / 17.63 | 15.21 / 16.30 / 17.17 | 16.58 / 17.90 / 18.50 |
| N119_220_Section_stack_flipped.tif | 8 | 15.38 / 16.33 / 17.43 | 15.20 / 16.60 / 17.40 | 16.58 / 17.70 / 18.07 |
| No107_SectionTopo-afterAnnealing .tif | Fit | 15.24 / 15.95 / 16.66 | 15.40 / 16.64 / 18.70 | 16.50 / 17.54 / 17.99 |
| No107_SectionTopo-afterAnnealing .tif | 1 | 15.35 / 16.25 / 16.53 | 15.48 / 16.29 / 32.69 | 16.81 / 17.55 / 17.77 |
| No107_SectionTopo-afterAnnealing .tif | 2 | 15.33 / 16.89 / 17.61 | 15.20 / 16.08 / 17.01 | 16.70 / 17.95 / 18.72 |
| No107_SectionTopo-afterAnnealing .tif | 4 | 15.24 / 17.02 / 17.64 | 15.23 / 16.78 / 17.58 | 16.79 / 18.23 / 18.72 |
| No107_SectionTopo-afterAnnealing .tif | 8 | 15.28 / 16.46 / 17.71 | 15.34 / 16.68 / 20.13 | 16.63 / 17.34 / 17.77 |
| No107_SectionTopo-beforeAnnealing.tif | Fit | 15.43 / 17.92 / 22.24 | 15.24 / 16.61 / 18.66 | 16.64 / 18.23 / 19.97 |
| No107_SectionTopo-beforeAnnealing.tif | 1 | 15.23 / 17.58 / 21.00 | 15.06 / 16.75 / 37.10 | 16.44 / 18.05 / 19.21 |
| No107_SectionTopo-beforeAnnealing.tif | 2 | 15.21 / 16.34 / 17.21 | 15.50 / 16.67 / 20.38 | 16.53 / 17.73 / 18.35 |
| No107_SectionTopo-beforeAnnealing.tif | 4 | 15.57 / 16.68 / 17.63 | 15.17 / 16.75 / 18.43 | 16.88 / 17.98 / 18.15 |
| No107_SectionTopo-beforeAnnealing.tif | 8 | 15.78 / 16.49 / 17.69 | 15.46 / 16.50 / 17.10 | 16.92 / 17.65 / 17.88 |
| No22_220_Section_stack_flipped.tif | Fit | 15.00 / 17.09 / 17.45 | 15.33 / 16.38 / 16.38 | 16.46 / 18.62 / 19.00 |
| No22_220_Section_stack_flipped.tif | 1 | 15.13 / 17.84 / 18.29 | 15.65 / 24.36 / 28.56 | 16.37 / 19.30 / 19.74 |
| No22_220_Section_stack_flipped.tif | 2 | 14.95 / 17.67 / 18.58 | 15.36 / 18.18 / 20.71 | 16.45 / 18.53 / 19.11 |
| No22_220_Section_stack_flipped.tif | 4 | 15.31 / 17.39 / 18.05 | 15.31 / 17.87 / 18.87 | 16.79 / 18.64 / 18.85 |
| No22_220_Section_stack_flipped.tif | 8 | 15.20 / 17.37 / 20.31 | 15.95 / 18.05 / 18.97 | 16.60 / 18.57 / 18.98 |

### 화질 / 원본 무결성 / 메모리

Crop 수는 100/200/400/800% 각각의 첫 화면·burst 후 및 TIFF middle/last/first 검사 합이다.
RSS는 반복 case 시점의 최대 관측값이며 초기 로딩 중 peak RAM 또는 heap 크기가 아니다. 최종 clear 이후 cache가 잠시 남는 것은 숨김 item의 next-paint 정책이다.

| 파일 | 원본 | Crop 검사 수 | 내부 max error | 최대 관측 RSS MiB | close 후 RSS MiB | display cache after close MiB |
| --- | --- | --- | --- | --- | --- | --- |
| After annealing_1.jpg | 12349×12273 / RGB uint8 / 1 pages | 8 | 0 | 1178.99 | 583.93 | 0.00 |
| N119_220_Section_stack_flipped.tif | 3072×3012 / uint16 / 158 pages | 20 | 0 | 4548.85 | 다음 파일 전·미close | 다음 파일 전·미close |
| No107_SectionTopo-afterAnnealing .tif | 2922×2895 / uint16 / 156 pages | 20 | 0 | 4124.95 | 다음 파일 전·미close | 다음 파일 전·미close |
| No107_SectionTopo-beforeAnnealing.tif | 2922×2895 / uint16 / 156 pages | 20 | 0 | 4106.49 | 다음 파일 전·미close | 다음 파일 전·미close |
| No22_220_Section_stack_flipped.tif | 2944×2745 / uint16 / 156 pages | 20 | 0 | 3932.36 | 324.55 | 0.00 |

### Source SHA256

| 파일 | Before = After |
| --- | --- |
| After annealing_1.jpg | `c864ce2410e940ee0e5c11faf4bec2f38fa66cf1f8d5ecc4cc15bfa5b60f1c47` |
| N119_220_Section_stack_flipped.tif | `434b86d180d1e7238540cde1a81a099670e145dd40ef7a114e75bae7e9b387bb` |
| No107_SectionTopo-afterAnnealing .tif | `81d5c2a0f795f90a2db1ddee3debf3f570b0e2c8223ab76384d31f21bfcefeb7` |
| No107_SectionTopo-beforeAnnealing.tif | `5d3aa50d204e118ca42ec7b54ff3444bde7406e9a548421042cd01e4272f47f4` |
| No22_220_Section_stack_flipped.tif | `e28cf99b4d482f24628cb87f9122b5ae505d73c9fdc5a8bd8b11380fc25542dd` |

### 수치 검증 범위

완료된 최종 반복 명령 12,300개(Pan+Zoom). 전체 최종 고배율 Pan max 39.24ms, Zoom max 93.82ms.
높은 배율의 각 case 기준 충족 여부는 아래 최종 판정에서 별도로 기록한다. synthetic 회귀를 실제 XRT benchmark에 섞지 않는다.

### Fit / DPI에서 남은 지연

ALL 2,946 / 동일 JPG. 각 Pan·Zoom N=30. 숫자는 median / P95 / max ms.

| DPR·backend | Fit Pan | Fit Zoom | GUI timer gap max |
|---|---|---|---|
| 1.0 D3D11 | 32.85 / 45.55 / 92.55 | 45.66 / 57.17 / 58.08 | 82.30 |
| 1.0 software | 24.69 / 27.28 / 27.80 | 22.23 / 32.89 / 34.66 | 35.72 |
| 1.25 D3D11 | 53.39 / 65.63 / 67.32 | 66.91 / 85.11 / 94.80 | 84.66 |
| 1.25 software | 56.28 / 63.13 / 65.24 | 67.48 / 77.08 / 82.80 | 82.90 |
| 1.5 D3D11 | 173.52 / 226.81 / 289.54 | 161.66 / 181.73 / 183.84 | 287.92 |
| 1.5 software | 65.20 / 74.58 / 80.51 | 64.03 / 72.77 / 80.54 | 80.91 |

150% D3D11 Fit ALL은 Pan/Zoom 모두 30/30회 100ms 초과였다. 이 결과를 고배율 약 15ms로 가리지 않는다.
DPI에 따른 backing pixel 수, Canvas raster/제출, 시스템 부하를 더 분리해야 한다.
독립 timestamp 진단은 125%에서만 수행했으므로 150%의 큰 지연을 GPU upload 탓으로 확정하지 않는다.

### 구간별 관측과 원인 확정 여부

125% hardware / JPG / 400% ALL Pan median:
event 0.066ms → state 0.367ms, dispatch+processEvents 0.460ms,
CPU paint 0.423ms, prepared 완료 13.731ms, Qt 제출 15.351ms.
같은 case의 sync median 0.840ms / CPU render-submit median 0.412ms(N=60).
이 구간들은 포함/겹침 관계가 있으므로 더해서 하나의 지연 합계로 만들지 않는다.
cache hit의 region_ready=0은 원본 영역 변환이 이미 완료됐다는 뜻이다.
visible-region 계산 / cache lookup / QImage format conversion / upload 각각의 단독 시간은 NOT MEASURED.
backend별 프레임 제출 스케줄링도 포함되므로 Software/Hardware 표를 CPU 속도 비교로 읽지 않는다.

- **확정:** fractional origin에서 최종 texture의 두 번째 보간으로 native 원본 내부 픽셀이 섞임.
- **확정:** 숨긴 Candidate Canvas도 후보 geometry와 그리기 명령을 처리함; 숨김 guard로 중단.
- **확정:** Fit↔80% Fit에서 level key 전환으로 매번 region/LUT 변환; 400↔320%는 level0 cache 재사용.
- **관측:** Fit ALL의 큰 제출 지연/GUI timer gap. Canvas JS 기록만으로 전부 설명할 수 없고 raster/upload/OS 구간의 분리 계측은 남음.
- **미확정:** GPU upload 단독 비용·횟수·bytes, GPU residency, 물리 frame drop/stutter, 실제 입력→photon.

### 화질·성능·실제 입력 최종 판정

| 항목 | 판정 | 근거·범위 |
|---|---|---|
| 완료 화면 화질 | **PASS** | JPEG 6개 backend/DPI, TIFF 4개 first/middle/last/first, 100~800% 내부 crop 오차 0; readonly 원본 crop 값 동등 |
| 자동 고배율 성능 | **PASS** | 100~800% 모든 최종 case median≤50ms/P95≤100ms/max≤250ms; decode 반복 0; 최신 transform 반영 |
| 전체 성능 | **PARTIAL** | Fit ALL 일부 기준 미충족; 150% D3D11 max 289.54ms, upload/물리 표시 단독 시간 미측정 |
| 실제 사용자 입력 | **PENDING** | Sky native pipe 접근 실패. QTest / property 입력 및 사용자의 창 가림 방지 협조는 실제 마우스 검증이 아님 |
| 전체 TD | **PARTIAL** | 두 원인 최소 수정/정밀 표시 검증 완료; 위 성능·수동 제한 보존 |

JPEG 초기 open은 실행에 따라 약 10~12초였다. 최종 hardware TIFF 초기 준비는 N119 57.07초,
No107 after 30.22초 / before 25.97초, No22 70.22초였다. 별도 software 150% N119는 149.04초였다.
OS cache·작업 중 메모리·기존 전체 준비 정책을 포함하며 초기 준비 성능을 이번 수정의 개선으로 주장하지 않는다.
RGB/uint16, 페이지 순서/표시 범위, raw 원본 값은 유지한다. ImageJ frames는 여전히 공간 Z 미확정이다.

### 전체 Regression / 최종 HEAD 게이트

최종 확정 결과·정확한 HEAD·CI run은 [Draft PR #85](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/85)에 기록한다.
[최종 HEAD CI Checks](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/85/checks)와 함께 확인한다.
Local gate JSON/XML/log는 ignored `artifacts/perf-td02/` 및 `artifacts/perf-td02-final-*.log`에 보존한다.
로컬 로그에는 실행 HEAD를 기록한다. 원본/모델/private log/tiny 원본 crop PNG는 Git에 넣지 않는다.

검증 대상은 기존 **298 passed / 4 skipped**에서 DPR 원본 픽셀 검사 3개와 hidden Canvas 동작 검사 1개를 추가한
**302개 회귀 + offscreen skip 4개**다. 별도 Windows native plugin GUI 4개는 windows QPA에서 실행한다.
skip 수나 기존 tests를 줄이지 않는다. targeted 최소 수정 회귀는 **23 passed**로 이미 확인했다.
Ruff / import / compileall / wheel / 전체 pytest / Windows native / CI의 최종 판정은 위 PR의 실행 결과로 확인한다.
Toolbar·Context·Analysis·Result·ROI·Model Preflight·TIFF Loading·Native Dialog controller·Export·Qt/QML 회귀가 전체 pytest에 포함된다.
최종 실제 데이터 benchmark/quality/GPU 진단의 QML warnings는 **0**이다.
실행 중 가림으로 중단된 두 125% final 실행과 앞선 software 150% TIFF 실행은 보존했고,
동일 조건의 완료 실행으로 교체했다. 최초 도구의 JPEG burst 100% 잘못된 배율 행은 그대로 보존하고 최종 화질 결과에 사용하지 않았다.
자동 Native Plugin 검사가 TD-13의 직접 파일창 열기/취소 Acceptance를 대신하지 않는다.

### 실행과 재현

제품 실행(가상환경 activate만으로 프로그램이 시작되지 않는다):

```powershell
D:\capstone\run-analyzer.cmd
```

프로젝트 `.venv`(Qt6.11.2/viewer/research + 진단용 psutil)에서 native 계측:

```powershell
Set-Location D:\capstone\sic-xrt-analyzer
$env:TEMP = 'D:\Temp\PC-1'
$env:TMP = $env:TEMP
$env:QSG_RENDER_LOOP = 'basic'
$env:QSG_INFO = '1'
$env:QT_SCALE_FACTOR = '1.25'
# $jpeg/$tiff는 읽기 전용 원본, $model은 기존 연구 모델,
# $reference는 기존 export result.json 경로를 지정한다.
.venv\Scripts\python.exe tools/benchmark_viewer_interaction.py $jpeg $tiff --output artifacts/perf-td02/reproduce --repeats 30 --pages --model $model --reference-result $reference
.venv\Scripts\python.exe tools/probe_viewer_gpu.py $jpeg --output artifacts/perf-td02/reproduce-gpu --model $model
```

Software 비교는 새 프로세스에만 `QT_QUICK_BACKEND=software`, hardware는 이 변수를 제거한다.
테스트 QSettings/URL interceptor를 사용한다. 실제 반복 표는 `22bf8ff` 계측 도구의 동일 SHA로 비교했으며,
현재 도구에는 이후 발견한 Focus 대기/화질 assertion 수정이 포함돼 있다.
정적/자동 gates는 Ruff, `compileall -q src tests tools`,
`pip wheel --no-deps --no-build-isolation .`, offscreen `pytest -q`,
windows `pytest -q tests/test_stack_compatibility.py -k gui_plugin` 순서다.
테스트 임시 디렉터리는 모두 D의 ignored artifacts에 둔다.

### 기존 기능 보존 / 후속 TD / RC

제품 변경은 ImageViewer.qml의 texture smooth binding과 숨김 Candidate Canvas guard뿐이다.
정밀 표시/원본 reader/모델/ROI/native dialog 구현을 교체하지 않았다.
original SHA / bit depth / RGB channels / ROI geometry / ImageJ ROI / 분석 영역 / 모델 입력 / ONNX 결과 / BPD·TED·TSD /
Candidate 좌표·score·id / Export·Copy·ImageJ/Fiji 계약과 cache 상한은 보존한다.
실제 모델의 2,946개 전체 predictions가 TD-12 export와 같고, 확대·필터 후에도 같았다.
확대 중 JPEG→TIFF에서 이전 pyramid close/새 cache identity/이전 후보 비움을 확인했다.
TIFF latest page 요청·원본 crop·raw 값과 일반 ROI page 의미는 실제 데이터/기존 회귀로 확인한다.

현재 고배율 cache hit 경로에 신규 Tile Renderer가 필요하다고 결론내리지 않는다.
**TD-03 후보는 Fit의 다량 Overlay raster/제출 및 level 경계 변환 구간**이다.
먼저 150% DPI에서 raster/upload를 분리하고 32MiB 이내의 기존 cache 재사용을 검토한다.
Spatial Index는 Fit에서 대부분이 보이므로 그 비용을 자동으로 해결한다고 가정하지 않는다.
더 큰 renderer 개편은 별도 근거·설계 후 결정한다.
Qt6.12 #83의 bool_dealloc은 별도 미확정 상태를 유지한다.
전체 RC는 **RC CODE READY — MANUAL VALIDATION PENDING**이다.

### Git

- Start: `perf/81-viewer-render-investigation` @ `18b9b9cdc27332ada788097866507d05851aa012`.
- Branch: `perf/84-viewer-interaction-validation`.
- 제품 수정: `d170b39` (DPI texture), `e325b55` (hidden Canvas).
- 계측: `22bf8ff`, `1a74ef2`, `799010a`; 계측 검증 수정 `b45a9ba`.
- Final HEAD: 이 보고서 커밋까지 포함한 **PR #85 head**. 최종 SHA와 gate 실행 결과는 PR 본문에 기록한다.
- Issue: [#84](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/84).
- Push/Draft PR: [#85](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/85), base `perf/81-viewer-render-investigation` 유지.
- Working tree: 사용자 `AGENTS.md` 변경만 보존한다. 원본/sources/모델/private artifacts는 커밋하지 않는다.
- 기존 stacked PR #56~#82 merge/rebase/retarget 없음. 이 PR도 병합하지 않는다.
