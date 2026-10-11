# XRT-UX-TD-01 — 화면 정보구조와 책임

작업 기준: `feat/52-candidate-roi`, `e49e4be59ea8c16fa27750fa46940dd57829ee2e`. Issue #55.

## 1. 기존 구조 조사

| 영역 | 기존 구현 | 조사 결과 |
| --- | --- | --- |
| Main Window | Main.qml | Action·파일 대화상자·브리지 이벤트·전체 레이아웃을 한 파일에서 관리 |
| Menu | AppMenuBar.qml | 파일/편집/이미지/처리/분석/플러그인/창/도움말, 스택 조건부 고급 기능 |
| Toolbar | TopToolbar.qml, ToolPalette.qml | 파일·뷰어·분석 명령과 ImageJ 도구·Dev/Stk/LUT가 혼재 |
| Workspace / Recent | NavigationPanel.qml | 작업 영역 4개, 최근 이미지 5개, 현재 파일의 명시적 진입점 없음 |
| Viewer / Header | ImageViewer.qml | 헤더, 좌표 변환, 이미지, ROI·측정·후보 Overlay, Loading Overlay |
| Right Inspector | InspectorPanel.qml | 5개 탭의 Form·모델/좌표/결과 대화상자·결과 탐색이 한 파일에 결합 |
| Status | StatusBar.qml | 상태·도구·배율·원본 좌표/값·해상도·장치 |
| ImageJ / Fiji | ImageJDialog.qml, MeasurementDialog.qml, PluginWindowHost.qml | 스택에서만 노출, Main 이벤트·브리지와 연결 |
| Wafer Map / 정합 / 3D | Main의 StackLayout 안내 화면 | 진입 가능하지만 실제 기능 미연결. 이번 작업에서도 안내 상태 유지 |
| 분석 / ROI / 저장 | Main의 Action, ResultExplorer, RoiEditor | 공통 Action과 직접 브리지 호출이 공존. 분석 탭에는 실행 버튼이 없었음 |

### 주요 문제

- 레이아웃 변경에 Main의 명령 연결까지 함께 검토해야 한다.
- 우측의 서로 다른 5개 작업이 하나의 컴포넌트에 있어 개별 변경의 영향 범위가 크다.
- 분석 설정의 소유 영역과 분석 실행 진입점이 떨어져 있다.
- Toolbar의 도구/분석/고급 기능을 독립적으로 정리하기 어렵다.
- Context 상태가 숫자 탭만으로 표현되고 정보 위계 경계가 없다.

## 2. 새로운 6개 영역

| 영역 | 한 문장 책임 | 구현 |
| --- | --- | --- |
| Global Menu | 전체 명령의 최종 접근점 | AppMenuBar |
| Primary Toolbar | 현재 이미지의 빈번한 직접 조작 | PrimaryToolbar, ViewerToolGroup, StackViewerToolGroup |
| Left Navigation | 작업 공간·현재 파일·최근 파일 탐색 | NavigationPanel, CurrentFileNavigation |
| Central Viewer | 이미지·페이지·좌표 기반 Overlay 표시 | MainWorkspace의 가변 중앙 StackLayout, ImageViewer, ViewerHeader |
| Right Context | 현재 작업의 설정·정보·결과 | RightContextPanel과 5개 Context |
| Bottom Status | 계속 확인하는 간결한 현재 상태 | StatusBar |

```text
Main (명령·브리지 이벤트·대화상자 조정)
└ AppShell (창과 6개 영역의 배치)
  ├ AppMenuBar
  ├ PrimaryToolbar
  │ ├ FileToolGroup
  │ ├ ViewerToolGroup
  │ ├ ModelStatusGroup
  │ ├ AnalysisToolGroup
  │ └ ToolPalette [스택에서만]
  │   ├ StackViewerToolGroup
  │   └ AdvancedToolGroup [Dev / Stk / LUT / >>]
  ├ MainWorkspace
  │ ├ NavigationPanel
  │ │ ├ Workspace 전환
  │ │ ├ CurrentFileNavigation
  │ │ └ Recent files
  │ ├ Central StackLayout [가변 폭·높이 Main Content]
  │ │ ├ ImageViewer
  │ │ │ ├ ViewerHeader
  │ │ │ └ 기존 이미지·Overlay·Loading 영역
  │ │ └ Wafer / 정합 / 3D 안내 화면
  │ └ RightContextPanel
  │   ├ ContextState
  │   ├ ImageContext
  │   ├ AnalysisContext → ModelDetails
  │   ├ ResultContext → ResultExplorer
  │   ├ ViewerContext → StackControls
  │   └ RoiContext → RoiEditor
  └ StatusBar
```

`TopToolbar`와 `InspectorPanel` 이름은 호환 wrapper로 유지한다. 기존 UI automation objectName도 유지한다.

## 3. State / Command / Event 경계

- 기존 UiState와 Main의 `commands`/Action 객체가 단일 원본이다. 컴포넌트마다 명령이나 분석 상태를 복제하지 않는다.
- AppShell은 theme/state/actions/bridge를 전달하고 MainWorkspace가 탐색·파일 드롭·Context의 의도를 signal로 올린다.
- 파일/모델/좌표 CSV/결과 폴더 대화상자는 Main에서 관리한다. Context는 열기 요청을 발행한다.
- 분석 Context의 실행·취소는 Toolbar/Menu와 **동일 Action**이다. enabled, 옵션, 분석 호출, 취소 규칙을 재구현하지 않는다.
- AppShell의 viewer/contextPanel alias는 Main의 기존 명령 대상을 보존한다. 기존 `openInspectorTab(index)`를 유지하고 `openContext(key)`를 추가한다.
- ImageJ 도구의 기존 hostWindow·fileBridge 접근은 유지한다. 전체 backend 추상화는 이번 범위가 아니다.

### Context 준비

ContextState의 `tabIndex`가 유일한 선택 상태다. `requestedContext`: image / analysis / result / viewer / roi. 이미지 탭에 열린 이미지가 없으면 `activeContext=idle`, 결과 탭에 후보가 선택되면 `detailContext=candidate`다.

새 자동 전환 규칙을 추가하지 않았다. 기존 이미지 열기→뷰어 탭, ROI 가져오기→ROI 탭, 후보 focusRequested→결과 탭은 유지한다. ROI 도구 선택·분석 완료 자체만으로 탭을 바꾸지 않는다. TD-03에서 이 정책을 별도로 설계한다.

### 정보 위계

| 단계 | 소유 경계 | 예 |
| --- | --- | --- |
| Primary | Viewer, Analysis/Roi/Result Context, 직접 도구 | 이미지, 분석 실행, ROI 생성, 후보 선택 |
| Secondary | Image/Viewer Context, ViewerHeader, ModelStatusGroup, Status | 해상도·페이지·원본값·배율·연결 상태 |
| Technical / Advanced | ModelDetails, AdvancedToolGroup, 설정·ImageJ 작업창 | 모델 버전/장치, Dev/Stack/LUT, 플러그인 옵션 |

각 Context와 상세 그룹의 `informationPriority`는 다음 TD가 해당 영역만 변경할 수 있는 경계다. 새 색상·폰트·패딩·애니메이션으로 위계를 재디자인하지 않았다.

## 4. 기능 중복 Inventory와 진입점

여러 진입점은 접근 빈도·전문 기능·키보드 조작을 위한 것이다. 이번 단계에서 기존 버튼은 제거하지 않는다. 아래 Primary는 후속 TD의 기준이며 실제 기본 진입점도 유지한다.

| 기능 | Menu | Toolbar | Left | Right | Viewer | Shortcut | Primary Entry | Secondary Entry / 중복 이유 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 이미지 열기 | 파일 | 열기 | 최근 파일 | — | 드롭 | Ctrl+O | Toolbar | Menu/드롭/단축키; 최근 파일은 재열기 |
| 최근 파일 | 파일→최근 | — | 최근 이미지 | — | — | — | Left | Menu: 접힌 Navigator에서도 접근 |
| 현재 파일 복귀 | 창→작업 영역 | — | 현재 이미지 | — | — | — | Left | 작업 영역 전환; 재디코딩하지 않음 |
| Pan | — | Pan / 스택 손 도구 | — | — | 드래그 | H | Toolbar | Viewer/단축키, 스택 도구는 ImageJ 조작 체계 |
| Zoom / 1:1 | 이미지 | +/- / 스택 돋보기 | — | — | Ctrl+휠 | Ctrl++/-/1 | Toolbar | Menu/Viewer/단축키 |
| 화면 맞춤 | 이미지 | Fit | — | 결과→전체 보기 | — | Ctrl+0 | Toolbar | 결과 전체 보기는 후보 확대에서 복귀 |
| ROI 생성 | 분석→ROI / 초기화 | ROI / 스택 형상 도구 | — | ROI 편집 | 그리기 | R | Toolbar | Menu/Viewer, ROI Context는 편집·관리 |
| ROI 가져오기 / 저장 | 파일→가져오기 | — | — | ROI 가져오기 / 새 ZIP 복사본 | ROI Overlay | — | RoiContext | 파일 Menu는 가져오기, 저장은 RoiEditor |
| ROI 좌표 복사 | 편집 | — | — | 분석의 좌표 표시 | ROI Overlay | — | Edit Menu | Context의 좌표는 읽기 정보 |
| 분석 실행 / 취소 | 분석 | 실행 | — | 분석→실행/취소 | — | — | AnalysisContext | Toolbar/Menu, 모두 같은 Action |
| 결과 탐색 / 후보 선택 | 분석→결과 탭 | — | — | ResultExplorer | 후보 표시점 | — | ResultContext | Viewer 표시점으로 동일 후보 선택 |
| 연구 결과 내보내기 | 파일의 일반 내보내기는 미연결 | — | — | 결과 폴더 저장 | — | — | ResultContext | 일반 Menu의 미연결 CSV와 혼동 금지 |
| 이미지 복사본 저장 | 파일 | 저장 | — | — | — | Ctrl+S | File Menu | Toolbar/단축키로 동일 Action |
| 측정 TSV 저장 | 파일 [스택] | — | — | — | — | — | File Menu | ImageJ 작업창 결과와 동일 측정 데이터 |
| 기하 측정 / 보정 | 분석 | 측정 [스택] | — | — | 측정 Overlay | — | Toolbar | Menu/MeasurementDialog; 아래 ImageJ 측정과 별도 명령 |
| ImageJ 강도 측정 / Histogram / Profile | 분석 [스택] | Dev→명령 | — | — | 선택 ROI 전달 | — | Analyze Menu | ImageJ 작업창, 기하 측정과 합치지 않음 |
| Stack 페이지 | 이미지→스택 [스택] | Stk [스택] | — | Viewer 슬라이더 | 휠 / 방향키 | 방향키 | ViewerContext | Viewer/메뉴: 빠른 페이지 탐색 |
| Stack 투영 / 복제 / 반전 | 이미지 [스택] | Stk [스택] | — | — | — | — | Image Menu | 고급 Toolbar, 공간 Z 확정 아님 |
| 밝기·대비 | 이미지→조정 | — | — | Viewer 범위 | — | — | ViewerContext | Menu: 같은 표시 범위/자동 범위 |
| LUT | 이미지 [스택] | LUT [스택] | — | — | 표시 | — | Image Menu | AdvancedToolGroup: 빈번한 전문가 접근 |
| 매크로 / 플러그인 / 모든 명령 | 플러그인 [스택] | Dev / >> [스택] | — | — | — | Alt+T | Global Menu | 고급 Toolbar; 기존 작업창과 실행 backend 공유 |
| 작업 영역 전환 | 창 | — | Workspace | — | 해당 작업 영역 | Alt+W | Left | Menu, 미연결 영역의 안내 유지 |
| 모델 선택 / 상태 | 플러그인→모델 정보 [스택] | 상태 | — | Analysis / ModelDetails | — | — | AnalysisContext | Menu/Toolbar는 정보·간결한 상태 |
| 패널 / Status / 전체 화면 | 이미지 | — | 접기 | — | — | F11 | Global Menu | Left 접기, 지속 상태는 StatusBar |

## 5. 이번 변경의 제한

- Python 분석/모델/판정/Score/Overlay 좌표/ROI 계산/원본 TIFF·캐시/ImageJ·Fiji backend와 외부 계약을 수정하지 않는다.
- ImageViewer는 헤더를 추출했다. 나머지 좌표·확대·드래그·후보 애니메이션·렌더링·로딩 계산은 그대로다.
- 기존 Menu 구조·단축키·5개 탭·Theme·주요 크기 유지. 우측 제목을 작업 정보로 표기하고 분석 Context에 공통 Action 버튼, Left에 현재 파일 탐색만 추가했다.
- 소스 참조 파일(`sources/`)·실제 원본 이미지·모델은 수정/커밋하지 않는다. 새로운 runtime dependency는 없다.
- Wafer Map/정합/3D의 **기존 진입점만** 보존한다. 해당 엔진이 구현되었다고 보고하지 않는다.

## 6. 후속 TD 범위

| TD | 담당 변경 | 이번에 확보한 경계 |
| --- | --- | --- |
| TD-02 Toolbar 단순화 | 버튼 통합·우선순위·중복 노출 | PrimaryToolbar의 File/Viewer/Analysis/Advanced 그룹 |
| TD-03 Right Context Panel | 자동 전환 규칙·후보 Context·탭 UX | ContextState / 5개 Context |
| TD-04 분석 Flow | 준비→실행→상태→결과 흐름 | AnalysisContext + 공통 Action |
| TD-05 결과 UX | BPD/TED/TSD 후보·Score·Card·검토 | ResultContext / 기존 ResultExplorer |
| TD-06 ROI UX | 생성·편집·관리·분석 범위 | RoiContext / 기존 RoiEditor |
| TD-07 TIFF Loading | 초기 준비·진행률·취소·메모리 | 기존 Loader/Viewer Overlay, 이번 변경 없음 |
| TD-08 Visual Density | 정보 위계의 실제 시각 디자인 | informationPriority + 현행 Theme |
| TD-09 Menu / Advanced | 전문 기능 메뉴·고급 진입점 | AppMenuBar / AdvancedToolGroup |

## 7. 검증

2026-10-06 Windows, Python 3.13 / Qt 6.11.2 / Java 24. 실제 XRT 원본/모델을 바꾸지 않고 생성 TIFF/JPEG 및 테스트 전용 분석 adapter를 사용했다.

| 항목 | 결과 | 근거 |
| --- | --- | --- |
| build | PASS | setuptools wheel 생성, 신규 QML은 기존 `ui/*.qml` package-data에 포함 |
| lint | PASS | `python -m ruff check .`, `git diff --check` |
| typecheck | 정적 검사 설정 없음 | 프로젝트에 별도 typecheck 명령 없음. QML 엔진 로딩·바인딩 검증 PASS, 경고 0개 |
| unit / integration | PASS | 전체 `pytest -q`: **153 passed, 4 skipped** (offscreen에서 네이티브 창 검사 제외) |
| native plugin integration | PASS | windows platform `test_stack_compatibility.py -k gui_plugin`: **4 passed**, AWT/Swing/ImageJ 설정창 |
| 화면 검토 | PASS | 실제 Windows Qt 창을 QTest로 조작하고 아래 4개 캡처를 육안 검토 |

검사한 동작: 앱·8개 Menu·메뉴 키보드·단축키·TIFF/JPEG·스택 페이지·밝기/대비·Pan/Zoom/Fit·ROI 편집/불러오기·분석/취소·결과/231개 생성 후보·원본 좌표 Overlay·후보 ROI·새 복사본 저장·결과 폴더 내보내기·패널 접기·설정·Workspace 진입. 기존 스택/Fiji/매크로/플러그인 테스트도 전체 검사에 포함한다.

새 `test_ui_ia.py`는 우측 실행 버튼을 실제 마우스 좌표로 클릭하고 공통 Action의 객체 일치, 기존 후보 Focus 전환, 새로운 자동 전환 없음, 1100×700의 5개 Context 배치와 패널 숨김을 검사한다. 최소 크기에서 중앙 폭은 일반 탭 **634 px**, 결과 탭 **536 px**다. 실창 보조 검증에서는 3페이지 uint16 생성 TIFF의 첫/중간/마지막 페이지와 JPEG, Ctrl+1/0, 밝기 범위, 분석 클릭, 후보 표시, JPEG 복사본의 바이트 일치와 결과 Export를 확인했다.

| 캡처 | 내용 |
| --- | --- |
| [빈 화면 1440×900](../screenshots/ia/empty-1440.png) | 6개 영역, 현재 파일 탐색, idle Context |
| [스택 1100×700](../screenshots/ia/stack-viewer-1100.png) | 전체 고급 도구 유지, 페이지/표시 범위는 Viewer Context |
| [결과 1100×700](../screenshots/ia/candidate-result-1100.png) | 기존 후보·Score·Overlay·자동 ROI, 가변 중앙 영역 |
| [분석 1100×700](../screenshots/ia/analysis-1100.png) | 모델/ROI/분석 범위와 공유 실행 Action |

캡처의 파일·후보·모델은 모두 **합성 테스트 데이터**다. 실제 BPD/TED/TSD 정확도를 검증한 결과가 아니다. OS 파일 선택 창을 사람의 마우스로 열기/취소하는 수동 검증과 실제 대형 XRT 4개/실제 모델 재추론은 이번 단계에서 수행하지 않았다. 기존 관련 엔진을 수정하지 않았으며 기존 자동 검사를 재실행했다.

### 재현

설치된 가상환경에서 실행한다. Java는 PATH, Fiji 라이브러리는 기존 설치 경로에 있어야 한다.

```powershell
$env:SIC_XRT_FIJI_HOME = 'artifacts/fiji-runtime'
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q src
.\.venv\Scripts\python.exe -m pip wheel --no-cache-dir --no-deps --no-build-isolation --wheel-dir artifacts/ia-dist .
$env:QT_QPA_PLATFORM = 'windows'
.\.venv\Scripts\python.exe -m pytest -q tests/test_stack_compatibility.py -k gui_plugin
```

Build용 setuptools/wheel은 개발 가상환경에 설치했다. 앱 dependency 및 외부 계약에는 변경이 없다.
