# XRT-UX-TD-03 — 작업 중심 Right Context Panel

Issue #60. 기준: [TD-01 IA](XRT-UX-TD-01-IA.md), [TD-02 Toolbar](XRT-UX-TD-02-TOOLBAR.md), PR #59 / `refactor/58-toolbar-simplification` / `6a13501a66f201a9bf4c27fd7be07daaf883dab5`. 작업: `refactor/60-context-panel-workflow`.

후속 [TD-04 분석 Flow](XRT-UX-TD-04-ANALYSIS-FLOW.md)는 이 전환 정책을 유지하고, Analysis의 모델·범위·입력을 기본 화면에 모으며 후보 방식/CSV만 고급 설정 Scroll로 옮겼다. 실행·상태 하단 유지와 ROI 관리 Context의 역할은 그대로다. 아래 테스트 수와 화면은 TD-03 당시 기록이다.

## 1. 기존 구조 조사

후속 [TD-05 Result](XRT-UX-TD-05-RESULT.md)는 Result의 전체 Scroll을 고정 요약·탐색·선택 상세와 독립 목록 Scroll로 변경하고, raw/검색/ROI 설정을 상세 진입으로 정리했다. 전환 규칙과 단일 선택/필터 상태는 유지하며, 후보 0개 문구는 “후보가 발견되지 않았습니다.”로 정리했다.

RightContextPanel은 같은 크기의 이미지/분석/결과/뷰어/ROI 5개 버튼을 표시하고 ContextState.tabIndex 하나로 본문을 선택했다. Main의 직접 숫자 탭 변경, 메뉴와 AdvancedActions의 openInspectorTab 호출이 섞여 있었다. 정보·설정·실행·결과·ROI 관리를 같은 탭 위계로 표현하고 완료 단계의 연결이 약했다.

| 기존 이벤트 | TD-02 동작 |
| --- | --- |
| 이미지 열기 성공 | VIEWER(3); ImageJ 작업 복사본도 동일 |
| Candidate 명시 선택 / focusRequested | RESULT(2), 기존 후보 Focus와 자동 탐색 ROI |
| ROI import 요청 / 완료 | ROI(4) |
| ROI Manager / More의 편집 | ROI(4) |
| 밝기/대비 메뉴 | VIEWER(3) |
| 분석 시작/완료/실패/취소 | 별도 Context 전환 없음 |
| 도구 선택, Pan/Zoom, 페이지 이동, hover/상태/픽셀 | 전환 없음 |
| 배치 초기화 | IMAGE(0) |

## 2. 선택: Option A — Context Switcher

```text
현재 Context 이름 ▾
현재 작업 / 데이터 상태 설명
────────────────────────────
해당 Context 본문
```

현재 Context를 헤더에서 표시하고 같은 자리의 메뉴로 **이미지 정보 / 분석 / 결과 / 뷰어·스택 / ROI 관리**를 직접 선택한다. Qt Menu의 방향키/Enter/Escape와 기존 ToolbarMenuItem 체크 gutter를 재사용하여 별도 Navigation framework 없이 접근성과 실제 마우스/키보드 검사를 유지한다. 5개 고정 탭은 제거하고 5개 Context 자체는 유지한다. 새 전환 애니메이션은 없다.

Switcher에는 명확한 한글 label, Accessible.name/description, Tooltip과 현재 선택 체크를 제공한다. 재선택 시 checked를 유지한다. 메뉴를 닫거나 취소한 뒤 Viewer 포커스를 복구한다. 모든 Context는 이미지가 없어도 선택하여 안내를 볼 수 있으며 실행·페이지·ROI 버튼은 기존 데이터/Action 조건에 따라 비활성화된다.

## 3. 책임과 내부 상태

| Context | 책임 | 상태 표현 |
| --- | --- | --- |
| IMAGE | 현재 파일·형식·해상도·dtype·페이지·원본 메타데이터 | 시작/닫기 후 idle 안내, 파일 열기 후 정보 |
| ANALYSIS | 모델/입력/범위·분석 영역, 실행/취소와 상태 | 기존 READY/RUNNING/COMPLETED/FAILED/CANCELED, 실제 실행 조건 |
| RESULT | 현재 유효 결과·후보 검토·선택·Export | empty / zero / list / candidate-selected |
| VIEWER | 페이지 탐색·표시 범위·스택 상태 | 기존 StackControls, 원본 표시·frames/Z 미확정 안내 |
| ROI | 분석 영역 및 ImageJ ROI 목록·import·편집·관리 | 분석 영역 없음/있음, ImageJ 목록 없음/있음, import busy/error, 편집 모드 |

Context와 workflow phase는 분리한다. `ContextState.Context`는 Image/Analysis/Result/Viewer/Roi 5개이며, 분석 단계는 UiState.analysis.state를 읽는다. IDLE/RUNNING용 Context enum을 늘리지 않는다. IMAGE의 idle과 RESULT의 candidate detail은 기존 파생 상태로 유지한다.

### Analysis: 설정 / 영역 / 실행·상태

AnalysisContext는 AnalysisSettings, AnalysisRegion, AnalysisExecution으로 논리 그룹을 분리했다. 모델·입력·CSV/범위·원본 ROI 의미, run/cancel Action과 enabled 조건은 그대로다. 설정/영역은 내부 ScrollView, 실행/취소·현재 상태는 하단에 유지하여 1100×700에서도 접근한다. 실제 progress API가 없으므로 RUNNING BusyIndicator를 사용하며 퍼센트나 시간을 만들어 표시하지 않는다. 취소는 기존 즉시 CANCELED 상태를 그대로 표시한다.

긴 모델 해시 형식의 버전은 기본 ModelDetails에서 숨기고, **모델 상세 정보**가 기존 modelInfo Action/Dialog를 연다. 일반 버전·모델명·장치는 유지한다. hash·backend·ID 정보를 헤더의 작업 상태와 같은 중요도로 추가하지 않는다.

### Result lifecycle

- 분석 전: “아직 분석 결과가 없습니다.”
- 실행 중 수동 진입: 완료 후 결과가 표시된다는 안내.
- 분석 완료/0개: “분석이 완료되었지만 후보가 없습니다.”
- 유효 결과/미선택: 후보 N개와 선택 안내.
- 후보 선택: 기존 Candidate Detail·점수·원본 패치·Focus·자동 탐색 ROI.
- 실패/취소: 이번 작업의 유효 결과가 없다는 안내. 이전 결과를 새 결과처럼 표시하지 않는다.

ResultExplorer의 카드·필터·색·Score·목록·Export 구현은 유지하고 empty 문구만 구분했다. 원본 변경/페이지 전환/새 분석 시 결과 무효화는 기존 pipeline/research controller가 담당한다.

### ROI lifecycle

상단에 분석용 사각형(R)의 원본 좌표·크기와 별도 ImageJ ROI 개수·편집 상태를 표시한다. 그 아래 기존 import/외접 사각형 선택/점·꼭짓점 편집/목록/새 ZIP 저장을 유지한다. 가져오거나 생성한 ImageJ 기록은 기존 Manager 목록이며 분석 영역과 데이터를 병합하지 않는다. 도형 마스크 분석이 구현됐다고 표시하지 않는다. ROI Tool 버튼은 우측에 복제하지 않는다.

## 4. 중앙 전환 정책

ContextState.requestContext(key, reason)가 이름과 event whitelist를 검증하고 선택과 lastReason을 기록한다. 요청 event가 아닌 state observer는 분석 lifecycle 한 곳에만 있다. Main은 bridge 이벤트를 이름/사유로 전달하며 UI 경계를 통해 패널을 펼친다.

| Event / Reason | 이전 Context | 이후 | 정책 |
| --- | --- | --- | --- |
| OPEN_IMAGE | 임의 | IMAGE | 원본 새 파일의 성공 시점; 로딩 진행/실패는 전환하지 않음 |
| CLOSE_IMAGE / DEMO_OPEN / RESET_LAYOUT | 임의 | IMAGE | 기존 닫기·데모·초기화 행위 |
| ANALYSIS_START | 임의 | ANALYSIS | 기존 실행 Action, 실제 RUNNING 단계 진입 |
| ANALYSIS_COMPLETE | 임의 | RESULT | 유효한 완료 결과, 후보 0개 포함 |
| ANALYSIS_FAILED | 임의 | ANALYSIS | 실패 메시지와 기존 재시도 조건 |
| ANALYSIS_CANCELED | 임의 | ANALYSIS | 취소, Result로 이동하지 않음 |
| CANDIDATE_SELECTED | 임의 | RESULT | 기존 명시 선택/focusRequested 연결과 Focus 유지 |
| ROI_MANAGER_OPEN | 임의 | ROI | 명시적 관리 요청 |
| ROI_IMPORT | 임의 | ROI | import 명령/완료, 기존 전환 유지 |
| ROI_EDIT | 임의 | ROI | More 편집 요청, 기존 전환 유지 |
| VIEWER_SETTINGS | 임의 | VIEWER | 이미지→밝기/대비 또는 More→뷰어·스택 설정 |
| MANUAL | 임의 | 사용자 선택 | 항상 5개 Context 접근 가능 |

분석 완료는 분석 ID별로 한 번만 처리한다. 같은 완료 snapshot의 ROI 변경/상태 갱신/Export·thumbnail 등의 업데이트는 수동 선택을 빼앗지 않는다. 유효한 결과·현재 이미지·sourceReady·로딩 상태를 확인하고, 늦은 결과의 generation/source 검증은 기존 pipeline을 재사용한다. terminal 이벤트를 RUNNING Context enum으로 바꾸지 않는다.

### 전환하지 않는 이벤트

Pan, Zoom, Fit, 단순 ROI/측정/그리기 도구 선택, 메뉴 열기·hover, Overlay hover, 마우스 이동, 픽셀 읽기, 창 resize, frame redraw, 표시 범위 변경, 로딩 진행, status snapshot, 페이지 이동은 Context를 바꾸지 않는다. Stack More의 페이지 버튼도 동일하다. Viewer 설정을 요청할 때만 VIEWER로 전환한다.

ROI Tool 선택은 빈번한 Pan↔ROI 전환에서 패널이 튀지 않도록 유지했다. 실제 드롭다운 선택·R·그리기 검사에서 현재 Context를 유지하며 **관리/import/edit** 명령에서 ROI로 이동한다. 후보가 자동으로 만드는 탐색 ROI도 ROI Context 전환을 유발하지 않는다.

ImageJ 작업 복사본 표시도 새로운 원본 파일 열기 event로 해석하지 않고 Context를 유지한다. 사용자는 분석 중에도 다른 Context를 볼 수 있다. RUNNING snapshot 갱신은 선택을 유지하고 성공/실패/취소 같은 작업 완료 milestone에서만 전환한다.

### Magic index와 호환성

본문 visibility와 패널 폭, 생산 코드의 전환은 Context 이름을 사용한다. ContextState.tabIndex 및 Main.openInspectorTab(index)는 기존 호출자의 호환 API로 유지하고 이름으로 변환한다. 숫자 선택 쓰기는 ContextState 한 곳으로 제한했다. 기존 초기/완료 전환 기대값을 가진 회귀 검사는 TD-03 정책과 실제 Switcher 사용 검사로 갱신했다.

## 5. Responsive와 실창 검토

패널 폭은 일반 **282px**, 결과 **380px**로 유지한다. 1100×700의 중앙 폭은 일반 **634px**, 결과 **536px**이며, 1440×900에서도 동일한 패널 폭이다. 긴 파일명/설명은 기존 줄바꿈·elide로 제한한다. Header와 팝업이 화면 내부에 표시되고 설정 스크롤과 별도로 분석 실행/취소·상태에 접근한다. TD-02의 상시 Toolbar 7개/높이 40px는 유지한다.

캡처는 실제 Windows Qt 창을 QTest로 조작한 **합성 512×512 RGB TIFF 3페이지·테스트 adapter 231개 후보**다. 실제 XRT 원본·모델 정확도 자료가 아니다.

| 캡처 | 확인 |
| --- | --- |
| [초기 1440×900](../screenshots/context-td03/empty-1440.png) | idle, 이미지 정보 Context |
| [스택 이미지 정보 1440×900](../screenshots/context-td03/stack-image-1440.png) | 새 파일의 IMAGE 진입 |
| [뷰어 1100×700](../screenshots/context-td03/viewer-1100.png) | 페이지·밝기/대비 |
| [Switcher 1100×700](../screenshots/context-td03/switcher-1100.png) | 5개 수동 진입점, 현재 선택 |
| [분석 준비](../screenshots/context-td03/analysis-ready-1100.png) / [분석 중](../screenshots/context-td03/analysis-running-1100.png) | 설정 스크롤과 실행/취소·상태 |
| [결과 목록](../screenshots/context-td03/result-list-1100.png) / [후보 선택](../screenshots/context-td03/candidate-1100.png) | 완료 milestone·기존 후보 검토 |
| [ROI 관리](../screenshots/context-td03/roi-1100.png) | 분석 영역과 별도 ImageJ 기록·편집 |
| [후보 0개](../screenshots/context-td03/zero-result-1100.png) / [분석 실패](../screenshots/context-td03/analysis-error-1100.png) | 정상 empty와 오류 구분 |

## 6. 검증

Windows / Python 3.13 / Qt 6.11.2에서 회귀 **168 passed, 4 skipped (117.47초)**, 별도 Windows AWT/Swing **4 passed (54.76초)**로 총 **172개**를 확인했다. skip 4개는 별도 실행한 네이티브 검사다. 새 Context 검사 11개는 자동 전환 후 메뉴 checked 상태까지 포함하여 다시 실행했고 **11 passed (11.47초)**다.

| 검사 | 결과 |
| --- | --- |
| Build | PASS — wheel 생성, 실제 소스와 QML **60개** 일치, sources/·데이터·모델·artifacts 제외 |
| Lint / compile | PASS — Ruff, Python compileall |
| QML loading | PASS — 실제 Qt 창 로딩, 검토 캡처 실행 중 QML 경고 0개 |
| Unit / Integration | PASS — 전체 168개, 기존 분석·좌표·파일·ROI·스택·ImageJ/Fiji 포함 |
| Native | PASS — Windows Java AWT/Swing 4개; 테스트 JVM 512 MiB 한도, 제품 설정 변경 없음 |
| Context transition | PASS — 새 11개 parametrized 검사 및 기존 IA/Toolbar 검사 |
| Visual | PASS — Windows 1100×700/1440×900 실창 합성 데이터 캡처 11장 검토 |

| 요구 Case | 확인 |
| --- | --- |
| 1 앱 시작 | IMAGE/idle, 실행 비활성 |
| 2 JPEG 열기 | 성공 시 IMAGE, 스택 전용 도구 숨김 |
| 3 TIFF Stack | 명시 표시 설정 진입, 기존 페이지/범위 조작 |
| 4 분석 실행 | ANALYSIS/RUNNING, Run 비활성, Cancel 접근 |
| 5 정상 완료 | RESULT, 후보 개수 |
| 6 후보 0개 | RESULT/zero, 분석 전과 다른 안내 |
| 7 실패 | ANALYSIS/error, 유효 결과 없음 |
| 8 취소 | ANALYSIS/canceled, 늦은 결과 반영 방지 |
| 9 후보 선택 | 명시 선택 시 RESULT, 동일 후보·기존 Focus |
| 10 ROI | 도구/R은 Context 유지; Manager/import/edit는 ROI, 분석 영역과 기록 분리 |
| 11 Pan/Zoom | RESULT 유지; Fit/hover/status도 유지 |
| 12 Stack Navigation | RESULT/ANALYSIS에서 페이지 변경 시 유지, 설정 요청 때 VIEWER |
| 13 수동 선택 | 5개 모두 마우스/방향키/Enter 접근, Escape/선택 후 Viewer 포커스 |
| 14 최소 화면 | 1100×700 Header/Popup/본문 스크롤/실행 버튼, 중앙 최소 536px |

같은 완료 ID의 재통지·ROI snapshot, 로딩 진행, 새 파일/닫기 뒤 늦은 분석 응답도 검사했다. 기존 스택 검사 두 개는 자동 VIEWER 진입 기대만 명시적 설정 Action 진입으로 변경했으며 실제 슬라이더 press/drag/release와 페이지·원본 범위 검사는 유지했다. 정적 타입 검사 도구는 저장소에 별도로 구성되어 있지 않다.

## 7. 범위와 남은 작업

Python backend, 분석 알고리즘·모델·inference·Score/후보·좌표·ROI 계산·TIFF/JPEG/Stack 로딩/캐시/렌더링·저장/Export·ImageJ/Fiji·매크로/플러그인·측정/주석은 수정하지 않았다. 외부 계약/스키마/모델 해시는 변경 없다. sources/·실제 데이터·모델·사용자 AGENTS.md 변경은 커밋하지 않는다.

| 후속 TD | 범위 |
| --- | --- |
| TD-04 | 분석 Flow 단일화, 준비/오류/재시도 안내 |
| TD-05 | Result Card·Legend·Score·필터·목록 UX |
| TD-06 | ROI 그리기/완료/취소·관리 UX |
| TD-08 | 전체 시각 밀도·Typography·Border·정보 위계 |

설정 영역은 작은 창에서 스크롤이 필요하다. ROI 목록의 생성/import provenance는 기존 Manager 데이터 범위를 따른다. 실행률 API가 없어 실제 퍼센트는 표시하지 않는다. 실제 대형 XRT 4개 및 실제 모델 재추론, 사람이 OS 파일 선택 창을 조작하는 검증은 이번 UI 단계에서 재수행하지 않았다. 기존 네이티브 창 검사에는 고정 시간 대기 민감성이 있으며 테스트용 JVM 한도는 제품 설정에 반영하지 않는다.
