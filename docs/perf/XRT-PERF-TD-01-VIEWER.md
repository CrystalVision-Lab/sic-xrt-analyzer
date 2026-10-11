# XRT-PERF-TD-01 Result

## Status

**PARTIAL** — Windows 소프트웨어 렌더링에서 큰 Zoom 지연의 원인을 확정하고 최소 수정했다.
검사한 원본 기반 표시 무결성은 **PASS**, 해당 조건의 성능 개선은 **PASS**다.
사용자가 보고한 화질 저하는 검사 영역에서는 재현되지 않았다. 기본 GPU 경로, 다른 DPI,
실제 마우스 입력의 반응과 대량 Candidate Overlay는 미검증이다.
사용자 요청에 따라 추가 Windows 화면 조작을 중단하고 CPU·화질 검사만 진행했다.
TD-13 수동 Acceptance와 최종 RC 판정은 계속 보류한다.

## 화질 문제 원인

- `ImageViewer.qml`의 준비된 이미지 경로는 `PreparedView`를 사용한다.
  `DisplayPyramid.region()`은 배율 × DPR에 따라 기존 표시 계층을 선택한다.
  100% 이상/DPR 1에서는 level 0, 즉 원본 해상도 영역을 사용한다.
- JPEG는 파일을 열 때 native 픽셀을 준비하고, TIFF는 읽기 전용 원본 mmap 또는 준비된
  native 표시 데이터를 사용한다. 매 Pan/Zoom마다 JPEG를 재디코딩하는 경로가 아니다.
- 축소 표시에는 기존 area-average 계층과 smooth interpolation을 사용한다.
  100% 이상에는 nearest neighbour 표시를 유지한다. 400%에서 원본 픽셀이 4×4 화면
  픽셀로 보이는 현상과 원본 노이즈 확대는 정보 손실의 증거가 아니다.
- 원본 직접 Crop과 Viewer의 표시 범위 변환 결과를 비교했을 때, 변경 전후 모두
  검사 영역의 채널 차이 0이었다. Preview만 확대하거나 정밀 표시 완료를 기다리는
  현상은 이 재현 조건에서 확인되지 않았다.
- GPU/DPI/특정 위치에서 발생하는 별도 화질 문제까지 해결됐다고 주장하지 않는다.
  Sharpen, AI Super Resolution, 원본 수정은 적용하지 않았다.

## 렉 문제 원인

### 1. 숨겨진 데모 Canvas의 확대 비용 — 확정

기존 `DemoImage`는 실제 이미지의 `imageFrame`에 `anchors.fill: parent`로 연결되어
`visible: false`인 상태에도 존재했다. `DemoImage.qml`의 Canvas는 크기 변경마다
`requestPaint()`를 호출하고 전체 캔버스를 채운다.
실제 JPG의 12,349×12,273 크기에 Zoom이 적용되면 숨겨진 Canvas도 커진다.
RGBA 평면 한 개만 계산해도 100% 약 606 MB, 200% 약 2.4 GB, 400% 약 9.7 GB다.
이는 실제 이미지의 viewport 크기로 그리는 `PreparedView`와 별개의 비용이다.

원래 paint 코드를 유지하고 숨겨진 Canvas의 크기만 0으로 만든 진단에서는
400% Zoom 중앙값이 **4,409 ms → 15.07 ms**로 바뀌었다.
최종 구현은 `Loader.active: uiState.demoMode`로 데모 모드에서만 Canvas를 생성한다.
실제 이미지 모드에는 숨겨진 데모 객체가 없음을 QML 테스트로 확인했다.

### 2. GUI paint마다 동일 영역 복사·변환 — 확정

`PreparedView.paint()`는 원래 동일한 영역도 매번 복사하고 표시 범위/LUT를 변환하여
QImage를 만들었다. RGB888/gray의 raster format 변환도 draw마다 반복될 수 있었다.
기존 Pyramid 선택을 유지하면서 변환된 viewport QImage 한 개를 재사용하도록 했다.
작은 Pan을 위한 128 physical pixel 여유와 **32 MiB 보유 한도**를 적용했다.
캐시를 벗어난 Pan, 계층/파일/페이지/표시 범위/LUT 변경은 새 영역을 변환한다.
따라서 큰 이동이나 캐시 miss 비용까지 없어진 것은 아니다.

### 구간별 확인

| 구간 | 확인 결과 / 측정 한계 |
| --- | --- |
| 원본 읽기 / Decode | JPEG 준비 중 decode 1회, 이후 454 paint 중 decode 0회. TIFF의 중간·마지막 페이지 추가 검사도 paint 중 page read 0회 |
| 원본 영역 / Cache | 기존 `DisplayPyramid.region` 복사 횟수 454 → 2. 새 캐시는 원본 캐시를 대체하지 않음 |
| Pixel Format / LUT | 표시 변환 454 → 2. LUT + QImage 생성은 묶어서 계측; 내부 각각의 시간은 분리하지 않음 |
| Scaling / raster draw | 추가 10회 반복 검사에서 실제 `QPainter.drawImage` 호출을 별도로 계측 |
| Viewer 전달 | QML transform 변경 → paint/frameSwapped의 전체 지연으로 계측. Python/QML 전달만 별도로 분리하지 않음 |
| Texture Upload | Windows 검사는 Qt software backend. GPU 업로드 시간은 측정하지 못함 |
| 화면 Render | Windows command-to-frameSwapped 및 연속 Pan swap 간격. 모니터 input-to-photon 시간은 아님 |
| Overlay | 분석 영역 사각형 표시/숨김 비교. ROI 전체 종류나 대량 Candidate의 단독 render 비용은 미측정 |
| Mouse Event | 기존 QTest 제스처 회귀 + offscreen 계측 도구 smoke 검사. 실제 마우스 입력 지연은 미측정 |
| GUI Thread | 원래 Canvas의 수초 stall, 수정 후 gesture 구간 5 ms 타이머의 최대 간격 37.42 ms(JPG), 23.49 ms(N119) |
| 오래된 요청 | viewport는 paint 시 최신 transform을 직접 사용. 새 비동기 렌더 queue를 추가하지 않음. 기존 file/page worker의 무효화 계약 유지 |

## 측정 환경

- 2026-10-11, Windows 11 build 26200, Python 3.13.7, PySide6/Qt 6.11.2.
- `D:\capstone\sic-xrt-analyzer`, D 가상환경, TEMP/TMP도 D.
- RAM 32 GiB, logical CPU 24. 다른 애플리케이션이 실행 중인 사용자 PC이며 독점 환경 아님.
- Windows 화면: QPA `windows`, `QT_QUICK_BACKEND=software`, render loop `basic`, DPR 1,
  1440×900 창, viewer 약 974×750. CPU raster: QPA `offscreen`, 1200×800.
- Windows 입력은 bridge/property 변경으로 발생시켰다. Native Dialog Acceptance 아님.
- 각 배율별 stationary/Pan/Zoom 반복을 구분한다. CPU 기본 30회, Windows Before는
  **2회 진단 표본**, Canvas 제거 ablation은 **10회**, After는 **30회**다.
  Before와 After의 표본 수 차이 때문에 개선 비율이나 FPS 보장으로 일반화하지 않는다.
- 반복 Zoom은 해당 배율의 0.1% 교차 변경, Pan은 작은 위치 변화다.
  초기 준비, SHA 계산, 독립 원본 Crop decode는 gesture 시간에서 제외한다.
- CPU 사용률은 process CPU time / wall time으로 기록했다. 다중 스레드에서는 100%를
  넘을 수 있으며 짧은 반복/외부 부하 영향을 받는다. CPU 사용률 감소를 별도로 주장하지 않는다.
- frameSwapped는 프레임 표시 경로의 완료 지표다. GPU fence나 실제 화면 도달 계측은 아니다.
  [Qt frameSwapped](https://doc.qt.io/qt-6/qquickwindow.html#frameSwapped),
  [QQuickPaintedItem](https://doc.qt.io/qt-6/qquickpainteditem.html) 문서 참고.

## Before Benchmark

실제 JPG, ROI Overlay OFF. 중앙값, ms / 메모리는 process RSS MiB.

| 배율 | Zoom 지연 | Pan 지연 | 연속 Pan 프레임 간격 | 메모리 |
| --- | ---: | ---: | ---: | ---: |
| Fit | 20.35 | 14.72 | 17.26 | 859.5 |
| 100% | 178.80 | 21.14 | 16.23 | 1,438.9 |
| 200% | 767.33 | 16.11 | 10.72 | 3,178.6 |
| 400% | 4,409.27 | 15.81 | 10.21 | 9,328.9 |
| 800% | 15.49* | 14.17* | 9.81* | 59.4* |

400% Zoom 최대 **8,808.21 ms**. Overlay ON의 400% 중앙값은 7,135.03 ms였다.
`*` 800%의 급격한 RSS 하락은 비정상 동작이며 원인을 분리하지 못했다.
이 행을 정상 동작/낮은 메모리의 증거로 사용하지 않는다.
초기 반복 계측은 timeout으로 중단된 기록도 보존했다. 다른 창의 가림과 큰 Canvas
stall이 관찰됐으며 모든 timeout을 하나의 원인으로 확정하지 않는다.

## After Benchmark

같은 JPG, Overlay OFF, 30회. 중앙값.

| 배율 | Zoom 지연 | Pan 지연 | 연속 Pan 프레임 간격 | 메모리 |
| --- | ---: | ---: | ---: | ---: |
| Fit | 14.18 | 13.96 | 15.39 | 859.0 |
| 100% | 14.34 | 13.78 | 15.44 | 861.5 |
| 200% | 15.53 | 13.20 | 15.22 | 861.8 |
| 400% | 15.39 | 13.39 | 15.37 | 862.1 |
| 800% | 15.31 | 13.37 | 15.31 | 862.4 |

Overlay ON Zoom 중앙값 범위 14.04–14.79 ms. 단일 사각형 Overlay는 큰 병목으로 확인되지 않았다.
N119 TIFF는 Fit/100/200/400/800% Zoom 중앙값 13.43/14.10/14.97/14.35/14.83 ms였다.
N119 전체 탐색 준비 후 RSS는 **4,517–4,521 MiB**로 높다. 기존 전체 페이지 표시 계층,
탐색 캐시와 file-backed mmap working set을 포함한다. 전체 스택 메모리가 해결됐다는 의미는 아니다.

### CPU paint 비교

30회 작은 Pan 중앙값(ms). full UI frame 지연과 다른 지표다.

| 배율 | JPG Before | JPG After | N119 Before | N119 After |
| --- | ---: | ---: | ---: | ---: |
| Fit | 19.51 | 0.367 | 4.542 | 0.271 |
| 100% | 8.41 | 0.291 | 3.728 | 0.259 |
| 200% | 3.83 | 0.440 | 2.158 | 0.375 |
| 400% | 1.76 | 1.039 | 1.948 | 0.389 |
| 800% | 1.83 | 0.494 | 1.451 | 0.413 |

추가 CPU 구간 검사(각 phase 10회, 150 timed draw + 4 quality paint):
JPG region copy/표시 변환 **154회 → 2회**, `drawImage` 중앙값 **1.146 → 0.754 ms**.
source identity stat 중앙값 **0.180 → 0.191 ms**로 그대로 검사한다.
After의 최초 두 변환은 Pan 여유가 있는 더 큰 영역이므로 cold miss 변환 비용은 낮아지지 않는다.
전체 배율을 합친 평균/중앙값을 특정 배율의 변환 비용으로 해석하지 않는다.

Baseline 관찰 후 확인 기준을 정했다: 이 소프트웨어 조건의 각 배율 Zoom/Pan 중앙값
50 ms 이내, JPG/N119 100% 작은 Pan CPU paint 중앙값 2 ms 이내,
gesture 중 GUI 타이머 최대 간격 100 ms 이내. 이 조건은 충족했다.
GPU/큰 Pan/실제 사용자 입력에 대한 보장이 아니다.

## 화질 비교

| 대상 | 원본 직접 Crop | Viewer 100% | 200% | 400% | 800% |
| --- | --- | --- | --- | --- | --- |
| JPG 첫 페이지 | 독립 imagecodecs decode | 정확 일치 | 정확 일치 | 정확 일치 | 정확 일치 |
| TIFF 네 파일 첫/중간/마지막 | 독립 tifffile read-only mmap | 정확 일치 | 정확 일치 | 정확 일치 | 정확 일치 |
| Windows JPG/N119 첫 페이지 scene readback | 독립 원본 Crop | 정확 일치 | 정확 일치 | 정확 일치 | 별도 scene readback 미실시 |

비교는 같은 원본 좌표(주로 x=1003, y=1011)의 영역에 대해 표시 범위를 적용한 값과
integer 확대 후 nearest neighbour 결과를 대조했다. CPU 영역 1200×800, Windows
scene readback 128×96. TIFF ImageJ 표시 범위/inversion을 적용하며, 분석 원본 값은 바꾸지 않는다.
모든 비교의 최대 채널 오차 **0**, 다른 채널 값 개수 **0**이었다.
합성 uint16의 비균일 패턴, LUT 변경, RGBA alpha coverage도 별도 회귀로 확인했다.
검사 영역 이외의 모든 좌표/모든 파일 형식/DPR을 검증한 것은 아니다.

실제 Crop/화면 PNG와 원시 JSON은 개인정보·연구 데이터이므로 ignored
`artifacts/perf-td01/`에만 보관하며 Git에 올리지 않는다.

## 원인 확정 여부

- **확정:** 숨겨진 Canvas의 전체 이미지 크기 Zoom, 중복 viewport 복사/변환.
- **이 조건에서 제외:** 반복 JPEG decode, 저해상도 Preview만 확대, 단일 ROI Overlay가 주원인이라는 가설.
- **미확정:** 사용자가 보고한 화질 저하의 특정 재현 조건, GPU upload/render,
  DPI 차이, 대량 Candidate Overlay, Before 800% RSS 급락.

## 적용한 최소 수정

1. `ImageViewer.qml`: 실제 파일 모드에서는 데모 Canvas를 생성하지 않는다.
2. `prepared_view.py`: 기존 Pyramid 영역의 변환된 QImage 한 개를 최대 32 MiB 재사용한다.
   native source 검사를 cache hit에서도 유지하고, 파일/페이지/범위/LUT/계층 변경과
   닫힌 Pyramid에는 캐시를 무효화한다. RGB32/필요시 premultiplied ARGB32 변환은 한 번 수행한다.
3. 표시 무결성, 작은 Pan/Zoom cache hit, 큰 이동 miss, budget, 파일 전환,
   원본 변경 감지, alpha, 데모 Loader를 검증하는 테스트 5개를 추가했다.
4. ROI 테스트 한 곳은 worker 상태 완료와 Qt layout 완료를 구별하여 실제 버튼 위치를
   기다린다. 클릭/화면 경계 assertion은 유지한다. ROI 제품 코드와 Geometry는 변경하지 않는다.
5. 재현용 `tools/benchmark_viewer.py`를 추가했다. Native Dialog 코드는 변경하지 않았다.

## 대규모 개선 필요 여부

확정된 지연 원인은 기존 구조의 두 수정으로 개선됐다. 신규 Tile/Pyramid Renderer는 만들지 않았다.
큰 Pan cold miss, GPU 환경, 전체 스택 RSS 문제는 이번 결과로 해결됐다고 판단할 수 없다.
이 조건에서 문제가 계속 재현될 때 해당 구간을 추가 계측한 후 별도 TD 필요성을 결정한다.

## 기존 기능 Regression

- 표시 캐시 + 전체 ROI 모듈: **28 passed**.
- Ruff 전체, import/compile, 변경 파일 whitespace 검사: PASS. 사용자가 이미 수정한
  `AGENTS.md`의 기존 whitespace는 유지하고 커밋하지 않았다.
- 전체 회귀 최종 결과: **298 passed, 4 skipped, 300.65 s**. 최종 로그
  `artifacts/perf-full-verified.log`, XML `artifacts/perf-td01/full-verified.xml`.
- 앞선 전체 검사: 1 failed / 296 passed / 4 skipped, 이후 1 failed / 297 passed / 4 skipped.
  둘 다 ROI 오류 행의 layout polish 이전에 버튼 경계를 검사한 실패였다.
  실패 직후 다음 이벤트에서 x=1475 → 1352, row width=386 → 263으로 정상화됐다.
  단독 검사는 PASS였고, ROI 모듈 전체 실행에서 재현했다. 기준 코드의 같은 모듈에서는
  해당 ROI 오류 테스트가 PASS였다. 따라서 기존 product 결함으로 단정하지 않는다.
  기준 비교 작업 트리의 ImageJ runtime 누락으로 wand 테스트가 실패한 로그도 보존했다.
- 원본 JPEG/TIFF, bit depth, ROI, 분석 입력/ONNX/분류/Candidate, ImageJ/Fiji,
  Export, Native Dialog 제품 코드를 수정하지 않았다.
- offscreen에서 외부 플러그인 창 embedding 검사 4개는 skip한다. Native 실사용 Acceptance로 대체하지 않는다.

## 실제 XRT 검증

| 파일 | 크기 / dtype | 검사 페이지(1-based) | 원본 SHA256 |
| --- | --- | --- | --- |
| After annealing_1.jpg | 12349×12273 RGB uint8 | 1 | `c864ce2410e940ee0e5c11faf4bec2f38fa66cf1f8d5ecc4cc15bfa5b60f1c47` |
| N119_220_Section_stack_flipped.tif | 3072×3012 uint16 | 1, 80, 158 | `434b86d180d1e7238540cde1a81a099670e145dd40ef7a114e75bae7e9b387bb` |
| No107_SectionTopo-beforeAnnealing.tif | 2922×2895 uint16 | 1, 79, 156 | `5d3aa50d204e118ca42ec7b54ff3444bde7406e9a548421042cd01e4272f47f4` |
| No107_SectionTopo-afterAnnealing .tif | 2922×2895 uint16 | 1, 79, 156 | `81d5c2a0f795f90a2db1ddee3debf3f570b0e2c8223ab76384d31f21bfcefeb7` |
| No22_220_Section_stack_flipped.tif | 2944×2745 uint16 | 1, 79, 156 | `e28cf99b4d482f24628cb87f9122b5ae505d73c9fdc5a8bd8b11380fc25542dd` |

각 CPU 검사 전후 SHA256 일치. 원본은 읽기 전용으로 사용했다.
TIFF pages는 ImageJ frames이며 공간 Z, 촬영 방향, 실제 간격을 추정하지 않았다.
첫/중간/마지막 페이지 CPU 검사는 페이지를 각각 준비한 뒤 수행했다.
전체 스택 UI 준비/반응성 검사는 N119에서 수행했으며 나머지 세 스택의 native UI 제스처를
이번 단계에서 재검증했다고 주장하지 않는다.

## 재현 방법

PowerShell에서 D 프로젝트의 가상환경 Python을 직접 사용한다. 원본 경로는 각자의 데이터 경로다.

```powershell
cd D:\capstone\sic-xrt-analyzer
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe tools/benchmark_viewer.py '원본.jpg' '원본.tif' --output artifacts/perf-local --repeats 30
.\.venv\Scripts\python.exe tools/benchmark_viewer.py '원본.tif' --page middle --output artifacts/perf-middle --repeats 2
.\.venv\Scripts\python.exe tools/benchmark_viewer.py '원본.tif' --page last --output artifacts/perf-last --repeats 2
```

`--baseline`은 지정된 TD-12 Git blob의 paint만 사용한다.
Windows 화면 계측은 사용자가 화면을 비워줄 수 있을 때 별도로 실행한다:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:QT_QUICK_BACKEND = 'software'
$env:QSG_RENDER_LOOP = 'basic'
.\.venv\Scripts\python.exe tools/benchmark_viewer.py '원본.jpg' --window-only --output artifacts/perf-window --repeats 30
```

Before 재현은 `--baseline --baseline-viewer`, Canvas만 제거하는 ablation에는 추가로
`--suppress-demo-canvas`를 사용한다. 대형 JPG의 원래 고배율 경로는 매우 큰 메모리와
stall을 유발할 수 있으므로 반복 수를 작게 시작한다.
측정 도구의 raw reference JPEG decode는 검증용 별도 메모리를 사용하며 Viewer의 실제 보유량과 구분한다.
JSON의 CPU %, RSS, 단계별 호출 수, median/p95/max/n, warnings, SHA 결과를 함께 확인한다.

프로그램 실행은 `D:\capstone\run-analyzer.cmd` 또는 D 가상환경의
`python -m sic_xrt_analyzer`를 사용한다.

## Git

- Issue: [#81](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/81)
- 시작 branch/HEAD: `fix/78-windows-ui-rc-stabilization` / `e9cad2b07027675225a6b4f89a57b0774eb22cb2`.
  세션 시작 checkout은 같은 HEAD의 `test/80-native-manual-acceptance`였다.
- 작업 branch: `perf/81-viewer-render-investigation`.
- 구현 commit: `5cf26e341b1c8b63d9665d793d38fcff3350d193`.
- 계측/회귀 commit: `1198fc1976736d32b4d0ce09f75d17c07f7e39d9`.
- 문서 commit은 이 보고서를 포함하는 Git history에서 확인한다.
- Push: `origin/perf/81-viewer-render-investigation` 게시 완료.
- Draft PR: [#82](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/82),
  base `fix/78-windows-ui-rc-stabilization` / head `perf/81-viewer-render-investigation`.
- GitHub Actions CI: 실행 결과는 PR Checks에서 확인한다. 로컬 회귀와 별도로 판정한다.
- 기존 stacked PR은 merge/rebase/retarget하지 않았다.

## 후속 TD

사용자가 Windows 화면 검사를 다시 허용하면 GPU/DPI별 동일 원본 영역과 실제 입력을 검증한다.
현재 결과만으로 신규 렌더링 엔진 TD를 요구하지 않는다. 특정 환경에서 지연이 남으면
cold miss, texture upload, Candidate Overlay를 분리한 추가 계측을 근거로 범위를 정한다.
