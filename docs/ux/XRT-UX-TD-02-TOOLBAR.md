# XRT-UX-TD-02 — Primary Toolbar와 도구 위계

Issue #58. 기준: [TD-01](XRT-UX-TD-01-IA.md), PR #56의 `refactor/55-ui-information-architecture`, `62cd18f9e97f49389d3681d9cde7c1142c227e21`. 작업 브랜치: `refactor/58-toolbar-simplification`.

## 1. 조사와 결정

TD-01 Toolbar는 첫 줄에 열기·저장·Pan·ROI·축소·배율·확대·Fit·모델 상태·분석 실행, 스택의 두 번째 줄에 17개 선택/그리기 도구·측정·Dev·Stk·LUT·추가 도구를 표시했다. 직접 조작, 설정, 전문 명령과 실행 CTA가 한 영역에 섞여 있고 스택을 열면 높이가 40px에서 80px로 증가했다.

변경 후 실제 순서:

```text
[열기] | [Pan] [Zoom] [화면 맞춤] | [ROI ▾] [측정 ▾] | [⋯]
```

상시 버튼은 파일 형식과 무관하게 **7개**, Toolbar 높이는 **40px**다. 파일·Navigation·ROI/측정·Overflow 사이에만 구분선을 사용한다. 비활성 도구에도 위치와 Tooltip을 유지한다. 스택에서 이미지 표시 영역은 이전보다 40px 높아졌다.

## 2. 도구 구성

| 그룹 | 직접 노출 | 드롭다운 / 대체 진입점 |
| --- | --- | --- |
| 파일 | 열기 | 저장은 ⋯ / 파일 메뉴 / Ctrl+S |
| Navigation | Pan, Zoom, 화면 맞춤 | ⋯ → 확대/축소에서 +/−/1:1, 기존 이미지 메뉴·단축키 |
| ROI | 현재 도구 이름·형상 / 기본 ROI | 분석 영역 선택(R), 사각형, 타원, 다각형, 자유영역, 다중 점, 완드, ROI 관리자, ImageJ ROI 가져오기 |
| Measurement / Annotation | 현재 도구 이름·형상 / 기본 측정 | 스케일·측정 창, 직선, 분할선, 자유선, 각도, 다중 점, 텍스트, 화살표, 도구 옵션 |
| More | ⋯ | 아래 전문 명령과 저장·배율·ROI 편집 |

ROI 메뉴의 **분석 영역 선택(R)**은 기존 분석용 사각형 범위다. **사각형 ROI** 등 ImageJ 도구는 기존 ROI Manager의 레코드를 생성한다. 계산이나 분석 범위를 합치지 않았다. Point는 두 메뉴가 같은 Action을 사용하며 상단에서는 ROI 그룹 하나만 활성 표시한다.

More 구성:

- 이미지 복사본 저장, 확대/축소/1:1, ROI 편집/관리, 측정 TSV 저장.
- 스택: 첫/이전/다음/마지막 페이지, 페이지 축 투영, 스택 복제, 반전.
- LUT: Grays, Fire, Ice, Spectrum, Red, Green, Blue, Cyan, Magenta, Yellow, Red/Green, Invert LUT.
- 그리기/색 추출: Picker, Brush, Fill.
- 색상·브러시·완드·텍스트 옵션, 모든 ImageJ 명령, 매크로, Java 플러그인, Fiji/ImageJ2 명령, 결과/로그, 명령 기록.

Dev/Stk/LUT 약어는 상시 도구에서 제거했다. 기존 Dev의 매크로·플러그인·명령 기록은 명확한 이름으로 More에 배치했다. 기존 스택 기능 조건 `stackFeaturesVisible`을 유지한다. JPG·단일 TIFF·데모에서는 ImageJ 전용 메뉴 항목을 숨기고 측정 버튼은 비활성화한다. 스택에서 만든 작업 복사본의 전문 도구는 유지한다. 파일명이나 frames로 공간 Z를 단정하지 않는다.

이번에 Menu-only로 새롭게 제한한 기능은 없다. 기존 Menu-only 명령은 유지하며, Toolbar에서 뺀 모든 기능에 아래 진입점이 있다.

## 3. 기능 진입점

| 기능 | Primary Entry | Secondary Entry |
| --- | --- | --- |
| Open | Toolbar 열기 | 파일 메뉴, Ctrl+O, 드롭, 최근 파일 |
| Save | 파일 메뉴 | ⋯, Ctrl+S |
| Pan | Toolbar | H, Viewer 드래그 |
| Zoom | Toolbar Zoom | 이미지 메뉴, ⋯ → 확대/축소, Ctrl+휠, Ctrl++/−/1 |
| Fit | Toolbar 화면 맞춤 | 이미지 메뉴, Ctrl+0 |
| 분석 ROI / ImageJ 형상 | Toolbar ROI ▾ | R/분석 메뉴(분석 ROI), RoiContext(가져오기·편집) |
| 기하 측정·주석 | Toolbar 측정 ▾ | 분석 메뉴의 측정 창, 도구 옵션 |
| Analysis / Cancel | AnalysisContext | 분석 메뉴, 같은 run/cancel Action |
| Stack 페이지 | ViewerContext | ⋯ → 스택, Viewer 휠·방향키 |
| Stack 투영·복제·반전 | ⋯ → 스택 | ImageJ 명령 실행 창 |
| LUT | ⋯ → 색상 표시표 | ImageJ 명령 실행 창 |
| 그리기·색 추출 | ⋯ → 그리기 / 색 추출 | ImageJ 도구 옵션 |
| ImageJ 명령 / Macro / Plugin / Fiji | 플러그인 메뉴 | ⋯, 기존 작업창 / Alt+T |
| Dev 명령 기록 | ⋯ → 명령 기록 | ImageJ 실행 창의 명령 기록 |
| 모델 상태·정보 | AnalysisContext | 모델 정보 메뉴, 기존 Status |

TD-01 Inventory의 Stack/LUT에 적힌 이미지 메뉴 하위 진입점은 실제 코드에 없었다. 메뉴 전체를 재설계하지 않고 이번 조사에 맞게 [Inventory](XRT-UX-TD-01-IA.md#4-기능-중복-inventory와-진입점)를 정정했다.

### Analysis Action: Option A

Toolbar에서 실행 CTA를 제거했다. 모델·입력·분석 범위·ROI와 실행 조건은 AnalysisContext가 소유하며, 같은 곳에서 실행/취소하는 TD-01 원칙을 따른다. 기존 run/cancel Action·enabled·실행 조건·취소·분석 호출은 그대로다. 메뉴 실행도 동일 Action이며 중복 실행하지 않는다. 기존 분석 실행 전용 단축키는 없었고 새로 만들지 않았다.

모델 상태 컴포넌트 `ModelStatusGroup`은 AnalysisContext의 기존 상태 표시 자리에 재사용했다. 연구 모델 준비/연결/미연결 표시와 `researchModelStatus` objectName을 보존했다.

## 4. 컴포넌트와 Action 재사용

```text
Main.commands
├ 기존 open/save/pan/roi/zoomIn/zoomOut/actualSize/fit/run/cancel/importRois
├ tools: ToolActions (기존 직접 선택 핸들러를 공통 Action으로 추출)
└ advanced: AdvancedActions (기존 전문 명령 핸들러를 공통 Action으로 추출)

PrimaryToolbar
├ FileToolGroup
├ ViewerToolGroup
├ RoiToolGroup
├ MeasurementToolGroup
└ AdvancedToolGroup (More)
```

- 열기/저장/Pan/분석 ROI/배율/Fit/분석·취소 Action과 단축키는 Main의 기존 객체를 재사용한다.
- 도구 선택은 `ToolActions`의 단일 Action으로 표현한다. 기존 선택 핸들러의 `roiEditMode=false; activeTool=tool`을 재사용하며 Viewer·ROI 계산에 변경이 없다. 남겨 둔 호환용 `StackViewerToolGroup`도 같은 Action을 참조한다.
- 측정/옵션/매크로/플러그인/Fiji/명령/결과/ROI관리/TSV는 Menu와 드롭다운이 `AdvancedActions` 객체를 공유한다. 기존 hostWindow 함수와 bridge 요청·인수를 그대로 호출한다.
- Stack/LUT/명령 기록도 공통 registry에 위치한다. 별도 backend, dependency, command palette는 추가하지 않았다.
- 사용하지 않는 기존 ToolPalette/AnalysisToolGroup/ModelStatusGroup 파일은 삭제하지 않는다. 실제 PrimaryToolbar는 17개 도구 Palette를 생성하지 않는다.

### Active Tool / Focus

유일한 상태는 기존 `UiState.activeTool` 및 `roiEditMode`다. Pan/분석 ROI/Zoom/형상/측정/그리기는 하나의 `ActionGroup`으로 연결하고 `checked`를 이 상태에서 읽는다. 메뉴가 닫혀도 도구는 유지되며 같은 항목을 다시 선택해도 활성 체크가 사라지지 않는다. H/R 등 외부 상태 변경도 메뉴와 상단에 반영한다.

Toolbar의 현재 도구 이름·형상·checked 강조는 기존 Theme Accent를 사용한다. Point 선택 시 두 상단 그룹을 동시에 강조하지 않는다. 도구 메뉴 선택 후 `Qt.callLater`로 Viewer 포커스를 복구하여 Enter/방향키로 이어서 조작한다. ROI 편집 모드에서는 그리기 도구 checked를 해제한다. Context 자동 전환은 추가하지 않았다.

`ToolbarButton`의 클릭 영역은 최소 **32×32px**, 아이콘/내용은 중앙 정렬하고 기본 enabled border는 최소화한다. Tooltip과 Accessible.name/description을 제공한다. 새 Toolbar 팝업의 체크 표시는 `ToolbarMenuItem`의 별도 gutter에 배치하여 도구 이름과 겹치지 않는다. 기존 AppMenuItem·Theme·전체 Menu 스타일은 수정하지 않았다.

## 5. Responsive와 화면 검토

1100×700 및 1440×900에서 7개 버튼과 긴 선택 이름(자유 영역 ROI·텍스트·화살표)을 검사한다. 모든 버튼은 32px 이상이며 한 줄 안에서 잘리지 않는다. More 팝업과 ROI/측정 메뉴는 1100×700 내부에 표시된다. 새 Overflow 전환 규칙 없이 이 두 목표 크기를 충족한다.

| 실창 캡처 | 확인 내용 |
| --- | --- |
| [빈 화면 1440×900](../screenshots/toolbar-td02/empty-1440.png) | idle / 비활성 도구 / 7개 버튼 |
| [스택 1440×900](../screenshots/toolbar-td02/stack-1440.png) | 40px Toolbar와 Viewer |
| [스택 1100×700](../screenshots/toolbar-td02/stack-1100.png) | 최소 창 크기의 한 줄 Toolbar |
| [ROI 메뉴 1100×700](../screenshots/toolbar-td02/roi-dropdown-1100.png) | 사각형 활성·대체 도구·체크 gutter |
| [측정 메뉴 1100×700](../screenshots/toolbar-td02/measurement-dropdown-1100.png) | 각도 활성·주석 도구 |
| [More 1100×700](../screenshots/toolbar-td02/more-1100.png) | 저장·스택·LUT·ImageJ 진입점 |

캡처는 실제 Windows Qt 창을 QTest로 조작했다. 파일은 512×512 uint16 합성 3페이지 TIFF이며 실제 XRT 데이터/모델을 Git에 추가하지 않는다.

## 6. 검증

2026-10-06 Windows / Python 3.13 / Qt 6.11.2 / Java 24. 기존 153개 회귀 검사에 Toolbar 통합 검사 4개를 추가했다.

| 항목 | 결과 | 근거 |
| --- | --- | --- |
| build | PASS | wheel 생성, 소스와 wheel의 QML **56개** 목록 일치, 원본/모델/artifacts 포함 없음 |
| lint | PASS | Ruff, 변경 대상 diff check, compileall |
| QML loading / binding | PASS | 통합 검사와 실창 로딩의 QML 경고 **0개** |
| unit / integration | PASS | 전체 pytest **157 passed, 4 skipped**, skip은 offscreen의 native 창 검사 |
| native plugin integration | PASS | Windows AWT/Swing/ImageJ 실창 **4 passed** (독립 재실행) |
| manual / visual | PASS | QTest 실창 캡처 6장과 드롭다운 체크/텍스트·최소 폭을 육안 검토 |

별도 정적 typecheck 설정은 없다. QML 엔진과 바인딩/마우스/키보드 동작으로 검사했다. 변경하지 않은 사용자 `AGENTS.md`에는 공백 diff가 있어 전체 working-tree diff check 대상에서 제외했으며 해당 파일을 커밋하지 않는다.

`test_toolbar.py`에서 실제 팝업 선택 후 이미지에서 사각형·타원·다각형·자유영역·점·직선·분할선·자유선·각도·텍스트·화살표를 생성하고 기존 ROI 레코드를 확인했다. 재선택, checked 동기화, H/R, ROI 편집, Zoom 클릭/Alt 클릭/Fit, Viewer 포커스, Context 유지, 체크 표시 gutter를 확인한다. More의 첫/이전/다음/마지막 페이지, LUT 진입, Brush, 명령 기록, Macro/Plugin/Fiji/측정 창과 Menu Action 객체 일치도 검사한다. JPEG에서 전문 메뉴가 숨겨지고 분석 ROI는 유지되는지 확인한다. 두 목표 크기에서 분석 메뉴를 실제 클릭하여 Action이 한 번만 실행되고 231개 합성 후보가 반환되는지 검사했다.

기존 전체 검사에는 TIFF/JPEG 표시·사전 준비·원본 픽셀·표시 범위·ROI import/편집/저장·ImageJ 매크로/플러그인/Fiji/ROI·분석/취소·후보 Overlay·저장/Export·메뉴/단축키·IA 검사가 포함된다.

초기 중단 로그의 Java 메모리 확보 오류는 테스트 프로세스에서만 `_JAVA_OPTIONS=-Xms32m -Xmx512m`을 지정하여 재검증했다. 앱의 JVM 설정, TIFF 메모리 정책이나 런타임 dependency는 변경하지 않았다. 개발용 진단 로그는 ignored artifacts에 보관한다.

네이티브 검사 최초 실행은 3 passed / 1 failed였다. 기존 ImageJ 창 검사에서 80ms 주기 위치 갱신을 100ms 기다린 후 x=50을 확인하는 지점이 x=30으로 관찰됐다. 다른 검사와 분리하여 **동일 코드로 4개 모두 재실행·통과(60.89s)**했다. NativePluginWindow나 해당 테스트 코드는 이번 TD에서 수정하지 않았다. 고정 시간 대기 검사의 타이밍 민감성은 남아 있다. 전체 회귀 검사는 157 passed / 4 skipped(114.16s), native 별도 통과까지 합계 **161개**다.

### 재현

기존 Java와 Fiji 라이브러리를 설치한 개발 환경에서 실행한다.

```powershell
$env:SIC_XRT_FIJI_HOME = 'artifacts/fiji-runtime'
$env:_JAVA_OPTIONS = '-Xms32m -Xmx512m' # 이 환경의 테스트용 한도
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q src
.\.venv\Scripts\python.exe -m pip wheel --no-cache-dir --no-deps --no-build-isolation --wheel-dir artifacts/toolbar-dist .
$env:QT_QPA_PLATFORM = 'windows'
.\.venv\Scripts\python.exe -m pytest -q tests/test_stack_compatibility.py -k gui_plugin
Remove-Item Env:_JAVA_OPTIONS
```

`_JAVA_OPTIONS`는 테스트 이후 해제한다. 실제 대형 이미지 처리용 JVM 메모리 설정을 줄이는 제품 변경은 아니다.

## 7. 범위와 후속 TD

변경 대상은 Toolbar·도구 Action 연결·기존 Menu Action 참조·분석 Context의 모델 상태 재사용·검사·문서다. 분석 알고리즘/모델/inference/좌표/ROI 계산/TIFF 읽기·캐시/Stack 처리/Rendering, sources/와 원본 데이터는 수정하지 않았다. 기존 연구 모델 RGB 입력 계약과 ImageJ/Fiji 호환 제한도 그대로다.

TD-03은 Right Context Panel, Context 자동 전환, 기존 5개 탭의 UX, 작업 상태 기반 Context 표시를 다룬다. 이번에는 새 자동 전환, Analysis/Result Flow 개편, Theme/글꼴 전면 변경, Menu 전체 재설계, Command Palette를 구현하지 않았다. 실제 대형 XRT 4개와 실제 모델 재추론, OS 파일 선택 창의 사람 마우스 조작은 이번 Toolbar 회귀 검증 범위에 포함하지 않았다.
