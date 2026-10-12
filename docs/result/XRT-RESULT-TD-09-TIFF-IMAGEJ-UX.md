# XRT-RESULT-TD-09 — TIFF ImageJ Workbench & Context-Aware Toolbar

## Overall Status

**PASS — 구현·자동 검증**.

Windows 617 PASS / Linux 618 PASS, 실제 TIFF 4개 × 3페이지와 선행 JPG Export byte 비교 PASS. 물리적 마우스·모니터 간 Native DPI Acceptance는 PENDING이다. 구현된 항목과 실행 검증 결과를 구분한다. 연구원의 물리적 마우스 Acceptance는 미완료다.

## Git

- Start Branch: `feat/110-model-registry-updater` / Draft #111
- Start HEAD: `eed81c2898a3b9615130b989b7e4ed710918b0e9`
- Work Branch: `feat/112-tiff-imagej-workbench`
- Issue: [#112](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/112)
- 구현·실행 검증 HEAD: `e74f1a5766fbc7f7bb0555e82f185f0af34a99fe`
- Final HEAD: 보고서·스크린샷 docs 커밋을 포함하는 [PR 최신 HEAD](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/113/commits)
- Draft PR: [#113](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/113), base `feat/110-model-registry-updater`
- CI: 최초 [실행 38260777410](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/38260777410)는 위와 같은 기존 기대값 3개로 실패했다 (614 PASS / 3 FAIL / 4 SKIP, 471.67초). Linux X11 Native 4 PASS, 서버 PostgreSQL job PASS. 수정 후 [실행 38263260494](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/38263260494)은 **PASS**다. 마지막 보고서·스크린샷 docs 커밋의 체크는 [PR checks](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/113/checks)에서 확인한다. 구현·테스트 코드는 이 검증 HEAD 이후 변경하지 않았다.
- 선행 stacked PR의 merge / rebase / retarget을 하지 않는다.

## 기존 Toolbar 문제 / Before UI

`StackViewerToolGroup`은 구현되어 있었지만 Primary Toolbar에는 연결되지 않았다. ROI/측정 드롭다운과 고급 명령이 분리되어 있었고, 기본 기능까지 `stackFeaturesVisible`와 전체 탐색 준비 조건에 묶여 단일 TIFF에서 사용할 수 없었다. TIFF에서 JPG용 분석 버튼과 분석 ROI가 함께 노출됐다.

## JPG/TIFF UX 분리 / After UI

Reader가 판별한 `imageFormat`으로 전환한다. 확장자를 바꾼 파일도 실제 형식으로 처리한다.

- JPG: 기존 Pan/Zoom/Fit, 분석 ROI, 분석하기, 후보·검수·프로젝트·동기화·모델 관리 유지.
- TIFF: Pan/Zoom/Fit, ImageJ 선택 아이콘, 측정, 밝기·대비, 처리, 더보기, 다중 페이지의 스택 메뉴.
- TIFF의 `imagePrepareAnalysis`는 숨긴다. ML 메뉴/Context/R 분석 ROI와 직접 Backend 요청도 차단한다. ImageJ Measure는 유지한다.
- TIFF를 JPG로 바꾸면 활성 도구 Pan/이전 파일 ROI 초기화. 기존 미저장 검수·ROI 보호 흐름 유지.
- 기본 오른쪽 패널은 닫힌 넓은 Viewer. 필요한 작업만 사용자가 연다.

## TIFF ImageJ Toolbar / Tool Mapping

외부 ImageJ 아이콘 리소스를 복사하지 않고 기존 `ToolGlyph`/`ToolActions`/exclusive ActionGroup을 재사용한다.

| 도구 | 위치 | 실제 실행 경로 | 결과 / 제한 |
| --- | --- | --- | --- |
| Rectangle | 기본 아이콘 | Viewer drag → workbench.gesture → ROI Manager | 원본 XY 사각형 |
| Oval | 기본 아이콘 | 동일 | ImageJ Oval, 편집 overlay는 128점 |
| Polygon | 기본 아이콘 | 클릭 + Enter/더블클릭 | 원본 XY polygon |
| Freehand | 기본, 1100 더보기 | drag | 자유 영역 |
| Line | 기본 아이콘 | drag | 직선, XY 길이 |
| Polyline | 기본, 1100 더보기 | 클릭 + Enter/더블클릭 | 분할선 길이 |
| Point | 기본 아이콘 | 클릭 | 선택 Point에 점 추가, 개수 |
| Wand | 기본 아이콘 | 기존 비동기 ImageJ Wand | 연결 영역, 도구 옵션의 허용오차 |
| FreeLine | 더보기 | drag | 자유선 길이 |
| Angle | 더보기 | 세 점 클릭 | XY 각도 |
| Text | 더보기 | 클릭 | ImageJ TEXT ROI, 옵션의 내용 |
| Arrow | 더보기 | drag | ImageJ ARROW ROI |
| Picker | 더보기 | 원본 1-pixel 읽기 | 색 옵션 변경 |
| Brush | 더보기 | drag → 기존 ImageJ worker | 픽셀 변경 작업 복사본 |
| Fill | 더보기 | 클릭 → 기존 ImageJ worker | 연결 영역 채움 작업 복사본 |
| Pan | 기존 Viewer 그룹 | drag | 기존 렌더링 이동 |
| Zoom | 기존 Viewer 그룹 | 클릭 / Alt 클릭 | 기존 anchor 확대/축소 |

측정 아이콘은 이름만 있는 기능이 아니다. 현재 표시된 선택의 원본 XY geometry를 기존 `StackMeasurements`로 실제 측정하며, 결과·단위·페이지를 표시한다. 복합 ROI 측정은 ImageJ Measure를 사용한다.

## Tool State

- 선택 배경/테두리, exclusive checked state, 강한 키보드 focus, Accessible 이름·설명.
- Tooltip에 이름/조작법/준비 조건. 현재 도구 설명은 TIFF 작업 패널과 Viewer 상태에 표시.
- 도구 선택 후 Viewer focus 복귀. 도구 클릭으로 설정창이 매번 열리지 않는다.
- H: Pan; JPG R: 분석 ROI; TIFF R: Rectangle. TextInput/TextEdit에서 단축키 제외.
- Enter/더블클릭 완료, Esc 취소, 기존 편집 Ctrl+Z 유지.
- 페이지 요청 즉시 미완성 gesture 취소. 페이지 완료 후 기존 취소도 유지.
- 검수 geometry 편집 중 ImageJ 도구 활성화 금지, 도구 변경 시 ROI 편집/feedback 모드 정리.

## ROI Interface Changes / ImageJ Selection

TIFF `RoiContext`의 분석 영역과 외접 사각형을 분석 영역에 복사하는 UI는 숨긴다. ImageJ ROI 가져오기/목록/선택/편집/표시·숨김/ZIP 저장/미저장 보호는 유지한다. 기본 작업 패널에는 현재 선택 bbox, 도구 조작법, 측정 요약만 제공한다. 선택 해제는 기록을 삭제하지 않는다.

ROI Geometry, 원본 좌표계, 페이지 속성, ImageJ ROI serialization 계약은 변경하지 않는다. 다른 페이지 ROI는 기존 active/visible 규칙대로 표시한다.

## ImageJ Measurement

`측정`: 표시된 현재 페이지 선택 → 면적/길이/각도/개수. 기본 pixel / pixel², 별도 명시한 XY 눈금 적용 가능. 원본 파일에 눈금을 쓰지 않는다. TSV는 새 파일만 저장한다.

`처리 → 선택 픽셀 측정`: 기존 ImageJ Measure와 옵션 확인창. Histogram/Profile은 기존 실제 원본 기반 통계 결과표·그래프를 사용한다. ImageJ 결과 TSV와 geometry 측정 TSV는 기존 별도 경로를 유지한다.

## Image Processing

- 밝기·대비: 기존 표시 범위 설정, 원본 픽셀 불변.
- LUT: 기존 ImageJ LUT 명령으로 표시 팔레트 변경. 엔진이 임시 TIFF를 만들더라도 원본 픽셀을 바꾸지 않는 표시 작업으로 구분.
- 가우시안 흐림: sigma 확인 후 현재 페이지 작업 복사본.
- 임계값: 원본 값의 최소/최대를 확인, 기존 IJM/Convert to Mask로 8-bit 0/255 작업 마스크 생성. 원본 uint16는 유지.
- 배경 제거: rolling ball 반경 확인 후 현재 페이지 작업 복사본.
- 필터/이진/입자 분석: 기존 전체 명령 검색과 Process 메뉴. 매개변수는 기존 실행창에서 사용자가 확인.
- 선택 ROI를 엔진에 전달하지만 일부 명령은 전체 페이지/Dataset을 처리한다. 적용 범위 안내 유지.
- 원본은 읽기 전용. 명시적으로 새 동일 확장자 파일명에 저장, 기존 파일 덮어쓰기 금지.

명령 의미 참고: [ImageJ Process](https://imagej.net/ij/docs/menus/process), [ImageJ User Guide](https://imagej.net/ij/docs/guide/146-29.html). Sharpness/AI 보정으로 원본 정보를 변경하는 별도 기능은 추가하지 않았다.

## Fiji/Plugin Advanced UI

더보기 → ImageJ 고급 기능: 명령 검색/매크로/Java 플러그인/Fiji·ImageJ2/로그·결과/명령 기록. 기존 명시적 코드 선택·실행과 경고 유지. 임의 JAR 자동 설치/실행 없음.

모든 Fiji/플러그인 호환을 보장하지 않는다. ROI Manager 양방향 동기화·임의 자체 마우스 도구 콜백·ROI를 무시하는 Dataset 명령 제약은 유지한다. Native 창 연결 코드는 수정하지 않는다.

## TIFF Stack Navigation

스택 슬라이더/버튼/휠/키보드와 페이지 캐시/Prepared View/정밀 원본/메모리 예산은 유지한다. Toolbar 변경으로 대용량 원본을 다시 처리하지 않는다.

현재 페이지 준비 `imagejReady`와 전체 탐색·스택 준비 `pageNavigationReady`를 분리했다. 현재 페이지의 선택·측정·작업은 다른 페이지 준비를 기다리지 않는다. 전체 스택 전달은 다중 페이지·전체 준비가 필요하다. Fiji 전체 복사 512 MiB 한도를 Backend에서 실행 전에 확인하며 현재 페이지 처리를 안내한다. 기존 엔진의 나머지 용량 제한 유지.

Z Project는 페이지 축 연산이다. frames를 물리 Z로 해석하지 않고 3D 재구성과 구분한다.

## Single-page TIFF

TIFF Backend 형식 확인, 준비된 현재 프레임, 실제 ImageJ 작업 복사본과 geometry 측정을 명시적으로 연결한다. UI만 활성화하지 않는다. 다중 페이지 메뉴는 별도 조건으로 노출. 전체 스택 요청은 단일 TIFF에서 거부한다.

## Native Window Compatibility

Windows 네이티브 플랫폼의 별도 검사: AWT Dialog / Swing JDialog / ImageJ GenericDialog 및 실제 QML host 총 **4 PASS**, 23.98초. DPR 1.25에서는 **4 PASS**, 27.84초, DPR 1.5에서는 **4 PASS**, 22.79초. 부모 item 이동, 설정 값으로 처리된 원본 복사본, 반복 실행, 파일 교체 중 JVM 창 종료, 앱 정리를 검사했다. 이번 세 프로세스에서 최초 실패는 없었다. 운영체제의 물리적 모니터 간 DPI 전환 및 실제 마우스 Acceptance는 미완료다. 과거의 Native 간헐 실패가 해결됐다고 해석하지 않는다.

## 1100/1440/1920 Layout / DPI

Windows Qt 실제 렌더링과 클릭 영역을 확인한다. 100/125/150%는 별도 프로세스의 QT_SCALE_FACTOR와 실제 DPR로 검사하며 OS 디스플레이 설정을 변경한 검증은 아니다. 1100에서는 Freehand/Polyline을 더보기 메뉴에 배치한다. 가로 스크롤 없이 아이콘 클릭 영역 34×32를 유지한다. `layout.json`에서 버튼 위치·크기·겹침·경계 및 실제 DPR를 검증했다. 100% 주요 시나리오 14장과 추가 DPI별 3장씩을 저장했다.

| DPR | 1100×700 | 1440×900 | 1920×1080 |
| --- | --- | --- | --- |
| 1.0 | [PASS](../screenshots/tiff-workbench/tiff-1100.png) | [PASS](../screenshots/tiff-workbench/tiff-1440.png) | [PASS](../screenshots/tiff-workbench/tiff-1920.png) |
| 1.25 | [PASS](../screenshots/tiff-workbench/dpr125/tiff-1100.png) | [PASS](../screenshots/tiff-workbench/dpr125/tiff-1440.png) | [PASS](../screenshots/tiff-workbench/dpr125/tiff-1920.png) |
| 1.5 | [PASS](../screenshots/tiff-workbench/dpr150/tiff-1100.png) | [PASS](../screenshots/tiff-workbench/dpr150/tiff-1440.png) | [PASS](../screenshots/tiff-workbench/dpr150/tiff-1920.png) |

최초 offscreen 캡처는 글꼴이 네모로 표시되어 결과 이미지로 채택하지 않았다. Windows 플랫폼으로 재캡처한 결과만 포함했다.

## Actual TIFF Validation / Original Data Preservation

**PASS**. `tools/validate_tiff_workbench.py`로 Windows QML에서 파일을 열어 전체 탐색 준비를 완료한 후 실제 페이지를 전환했다. 아이콘은 QTest로 클릭하고 원본 XY geometry는 Backend gesture로 전달했다. 물리적 드래그 Acceptance를 대체하지 않는다.

| 실제 원본 | 크기 | 확인 페이지 (1-based) | 결과 |
| --- | --- | --- | --- |
| N119_220_Section_stack_flipped.tif | 3072×3012, 158장 | 1 / 80 / 158 | PASS |
| No107_SectionTopo-beforeAnnealing.tif | 2922×2895, 156장 | 1 / 79 / 156 | PASS |
| No107_SectionTopo-afterAnnealing .tif | 2922×2895, 156장 | 1 / 79 / 156 | PASS |
| No22_220_Section_stack_flipped.tif | 2944×2745, 156장 | 1 / 79 / 156 | PASS |

네 파일 모두 TIFF byte order `>`인 uint16이다. 12페이지에서 Viewer 원본 전체 픽셀과 직접 `tifffile` decode를 비교했다. Rectangle [10,10]→[42,42]는 면적 1024 pixel²와 원본 페이지 번호를 유지한다. ImageJ Multiply(value=1)의 작업 TIFF는 전체 픽셀·uint16가 원본과 일치한다. 마지막 페이지 작업 복사본을 Viewer에 실제 표시하고 ROI ID/path/page_index 불변을 확인했다.

원본 네 파일과 private 프로젝트 SHA-256 불변. 자동 ONNX 0회 / 자동 BPD 0회 / 자동 동기화·Crop 업로드 0회 / JPG 검수 자동 활성화 없음 / QML 경고 0개. 원본·모델·private 프로젝트는 Git에 포함하지 않았다.

최초 두 실행은 N119 전체 준비가 240초를 초과했고, 두 번째에는 8/158페이지였다. 새 검증 스크립트의 반복 `QTest.qWait`를 기존 검사와 동일한 `processEvents + sleep(.005)`로 바꾸어 Python worker 실행 시간을 확보한 세 번째 실행에서 네 파일이 통과했다. 앱의 페이지 캐시·렌더러·디코더는 바꾸지 않았다. 최초 실패 보고서와 로그를 `artifacts/td112-real-workbench{,-v2}` 및 `artifacts/td112-tests/real-workbench-{first,second}.log`에 보존한다. 통과 보고서는 `artifacts/td112-real-workbench-v3/report.json`이다. 이 변화에서 앱의 실사용 로딩 성능 개선을 주장하지 않는다.

## JPG Regression

**PASS**, `tools/validate_dataset_regression.py`, `artifacts/td112-real-dataset-regression/report.json`.

저장된 Full 2회는 각 2946 candidates (BPD 245 / TED 1398 / TSD 1303), ROI 2회는 각 791 (BPD 3 / TED 779 / TSD 9)였다. 저장된 AnalysisRun/Observation/Prediction/ModelProvenance를 비교해 Candidate ID/Raw Score 등 과학 데이터를 보존했고, 각 실행의 두 번 Export byte가 일치했고 선행 TD-08에 보존한 네 Export 파일 집합과도 byte 단위로 일치했다 (`baseline-export-comparison.json`). 재검증 중 새로운 추론 0회, 원본·모델·프로젝트 SHA 불변, QML 경고 0개. 검수·저장·동기화·모델 업데이트의 UI/계약은 전체 회귀에 포함한다. 새 운영 서버 쓰기·업로드·Registry 모델 승인은 수행하지 않았다.

## Windows Tests

최초 전체 Windows 회귀: **613 PASS / 3 FAIL / 5 SKIP**, 887.15초. 실패는 TIFF의 JPG Result Context 진입, RGB TIFF를 ML Export fixture로 사용, TIFF 탐색 중 분석/결과 Context가 열릴 것이라는 이전 기대값이었다. 실제 TIFF 차단·JPEG Export fixture를 반영한 대상 재검사는 각각 1 PASS (3.83 / 2.53 / 2.37초)였다. **최종 전체 Windows 회귀: 617 PASS / 5 SKIP**, 848.36초 (`full-windows-second.log`). 제외는 offscreen Native 4개와 Windows symlink 권한 검사 1개다. Native는 Windows 별도 프로세스로 세 DPR에서 각 4 PASS를 확인했다. Picker·Brush·Fill 메뉴→Viewer 입력→작업 복사본의 픽셀과 원본 불변 검사도 1 PASS (5.44초)다.

Windows 11 build 26200 / Python 3.13.7 / PySide6·Qt 6.11.2, QSG_RENDER_LOOP=basic. 기본 전체 검사는 offscreen, Native 4개는 Windows 별도 프로세스, 실제 화면 캡처는 Windows 플랫폼이다. 초기 UI 회귀의 TIFF ML 전제는 JPEG 분석 fixture와 TIFF 선택/측정 검사로 변경했다. 원본 Source 타입을 검사하는 TIFF 단위 검사는 TIFF로 유지한다. 최초 실패 로그는 `artifacts/td112-tests`에 보존한다. 초기 실패에는 TIFF를 ML 입력으로 사용한 이전 UI 테스트 전제, 좌표 조회 전 layout 정착/프로젝트 worker 대기 누락, 작은 화면 Result Footer 밀림, 측정 테스트 bbox 명칭 및 초기 준비 flag 오타가 있었다. 전제·검증 대기를 실제 정책과 맞추고 1100 화면 결과 간격을 정리했다. 별도 UI 묶음 39 PASS, Backend/UI 76 PASS 후 오타 대상 2 PASS, 핵심 Stack 호환 5 PASS를 확인했다. 최종 전체 회귀가 통과했다.

## Linux CI

검증 코드 HEAD `e74f1a5766fbc7f7bb0555e82f185f0af34a99fe`, [CI 38263260494](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/38263260494):

- Ubuntu / Python 3.11 / Qt 6.11.2: **618 PASS / 4 SKIP**, 601.81초.
- 별도 Xvfb/X11 실제 AWT/Swing/ImageJ 창: **4 PASS**, 24.10초.
- 독립 server-postgres job: **79 PASS / 1 warning**, 19.54초. TestClient httpx 사용에 대한 Starlette deprecation warning이며 구현 실패가 아니다.
- Ruff/import/compile/wheel/PR 커밋 규칙 검사 PASS.
- 운영 PostgreSQL·Registry·데이터셋은 수정하지 않았다. Linux Compose 실사용·물리적 Desktop Acceptance를 수행했다고 주장하지 않는다.

후속 문서·캡처 커밋의 CI 상태는 PR checks에 남긴다. 결과를 확정할 때 이 HEAD와 마지막 문서 HEAD를 구분한다.

## Screenshots

모두 합성 데이터의 실제 QML 화면이며 QTest/Backend로 조작했다. 물리적 마우스 Acceptance가 아니다.

- [JPG Toolbar](../screenshots/tiff-workbench/jpg-toolbar.png)
- [TIFF 1440 / 기본 도구](../screenshots/tiff-workbench/tiff-1440.png)
- [Rectangle](../screenshots/tiff-workbench/rectangle.png)
- [Polygon](../screenshots/tiff-workbench/polygon.png)
- [Line](../screenshots/tiff-workbench/line.png) / [Polyline](../screenshots/tiff-workbench/polyline.png)
- [Wand](../screenshots/tiff-workbench/wand.png)
- [측정 결과](../screenshots/tiff-workbench/measurement.png)
- [고급 메뉴](../screenshots/tiff-workbench/advanced-menu.png)
- [처리 확인](../screenshots/tiff-workbench/processing-confirmation.png)
- [1100](../screenshots/tiff-workbench/tiff-1100.png) / [1920](../screenshots/tiff-workbench/tiff-1920.png)
- [TIFF→JPG](../screenshots/tiff-workbench/tiff-to-jpg.png) / [재열기](../screenshots/tiff-workbench/tiff-reopened.png)

## Remaining Limitations / Next TD

- ImageJ 전체 플러그인 호환을 보장하지 않는다. 기존 AWT/Swing 간헐 문제를 해결했다고 주장하지 않는다.
- 물리적 마우스로 TIFF 도구/Native Dialog를 확인하는 Acceptance는 별도로 필요하다. 다음 작업은 이 수동 검증과 원본 페이지→단일 작업 복사본 ROI 표시 대응을 별도 계약으로 정리하는 것이다.
- 3D 재구성·TIFF ML·Registry/중앙 서버 변경은 이번 TD의 범위 밖이다.
- 현재의 간단한 임계값 확인창은 8/16-bit 픽셀 범위를 검증한다. float 임계값·복잡한 처리 옵션은 고급 ImageJ 명령으로 지정한다.
- 다중 TIFF 마지막 페이지에서 만든 단일 작업 복사본에는 원본 ROI의 page_index를 자동으로 0으로 다시 쓰지 않는다. 해당 ROI는 기록에 유지되지만 단일 복사본에서 숨겨질 수 있으므로 원본 재열기/ROI 관리가 필요하다.
- 측정하지 않은 성능 개선/FPS는 주장하지 않는다. 렌더링 경로를 유지한다.

## 실행 / 재현

```powershell
Set-Location D:\capstone\sic-xrt-analyzer
.\.venv\Scripts\python.exe -m sic_xrt_analyzer
.\.venv\Scripts\python.exe -m pytest -q tests/test_toolbar.py tests/test_tiff_workbench.py
$env:QT_QPA_PLATFORM = 'windows'
.\.venv\Scripts\python.exe tools/capture_tiff_workbench.py
```
