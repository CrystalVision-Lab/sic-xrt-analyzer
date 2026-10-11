# XRT-UX-TD-06 — ROI 상태와 생성·편집·관리

Issue #66. 기준: TD-01~05, PR #65 / `refactor/64-result-ux` / `fa109ca19f98956775b6ba56f8f5c4941547d4e8`. 작업: `refactor/66-roi-ux`.

## 1. 기존 ROI UX 문제와 코드 조사

RoiContext는 분석 사각형 설명·가져오기·외접 사각형 변환·RoiEditor의 모든 필드·긴 기록 Repeater·오류 목록을 하나의 외부 Scroll에 표시했다. 분석 영역을 지정/제거하는 진입점이 없고, 기록 개수/현재 선택이 편집 필드보다 뒤에 있었다. 분석 영역과 ImageJ 기록의 역할을 설명했지만 생성 중 상태와 다음 행동이 불명확했다.

조사한 실제 파일: `UiState.qml`, `ImageViewer.qml`, `Main.qml`, `ToolActions.qml`, `AdvancedActions.qml`, `RoiContext.qml`, `RoiEditor.qml`, `roi_manager.py`, `bridge.py`, `imagej_workbench.py`, `ImportedRoiOverlay.qml`, `imaging/imagej_roi.py`, `imaging/roi_edit.py`.

## 2. 분석 영역과 ImageJ ROI 차이

| 구분 | 분석 영역 | ImageJ ROI |
| --- | --- | --- |
| 목적 | 어디를 분석할 것인가 | 도형/점/선 기록과 편집·관리 |
| 자료 | 정규화된 사각형 끝점과 원본 픽셀 사각형 | 기존 ImportedRoi records, paths, bbox, page_index |
| 생성 | 공통 R Action, Viewer drag | 기존 ImageJ Tool gesture / .roi·ZIP import |
| 분석 영향 | scope가 ROI일 때 사각형을 AnalysisRequest에 전달 | 자동 분석 범위가 아님 |
| 명시적 연결 | 없음 | 세부 설정의 “분석 영역으로 외접 사각형 선택”만 사각형 복사 |

두 자료를 한 목록으로 합치지 않는다. 외접 사각형은 도형 mask가 아니며 기존 명시적 변환만 유지한다. FULL_IMAGE 분석은 영역을 지정하지 않아도 된다.

## 3. Source of Truth

- 분석 영역: 기존 `UiState.roiStartX/Y`, `roiEndX/Y`, `hasRoi`, `selectingRoi`. `pixelEdge()`와 floor/ceil에서 파생되는 `roiX/Y/Width/Height` 및 `syncCurrentRoi()` → pipeline.current_roi를 그대로 사용한다.
- ImageJ 기록: 기존 Python `RoiManager.records`, `selected`, `hidden`, `vertex`, `busy`, `errors`, 편집/history 상태. `FileBridge.roiState` → `UiState.importedRois`는 기존 facade다.
- 도구/편집: 기존 `UiState.activeTool`, `roiEditMode`.
- ImageJ 입력 초안: 기존 Viewer의 `toolPoints`, `drawingTool`. `roiInteraction`은 Viewer 객체 참조이며 geometry 복사본이 아니다.
- 신규 `RoiFlowState`는 읽기 전용 presentation만 계산한다. 새 좌표·records·선택 ID·분석 영역을 저장하지 않는다. selectedIndex는 표시 순번만 계산하며 선택 명령은 기존 record ID를 사용한다.

## 4. 변경 후 ROI Context 역할

고정 **분석 영역 상태/다시 지정·제거 → ImageJ 기록 개수/현재 선택/도구 안내 → 가져오기·관리·편집 → 독립 스크롤 목록 → ZIP 저장** 순서다. 패널 폭은 282px 유지한다.

생성 Tool은 Toolbar ROI/측정 메뉴에 둔다. 원본 좌표·이름·꼭짓점·전체 이동·기존 history·새 점·외접 사각형 변환은 **세부 설정…**에서 기존 RoiEditor를 사용한다. 목록 Row는 표시 체크·순번/shape·다른 페이지 여부·기록 제거만 표시한다. 좌표 전체/pointCount/기술 ID를 Row에 반복하지 않는다. Border 카드를 새로 쌓지 않는다.

## 5. 분석 영역 Lifecycle

| 파생 상태 | 화면 | Action |
| --- | --- | --- |
| NONE | 지정된 분석 영역이 없습니다. 전체 이미지 분석에서는 필요 없음 | 공통 영역 지정(R) |
| DRAWING | 분석 영역 지정 중, drag/release 안내 | 기존 입력 진행 |
| READY | 지정 영역 · W×H px, X/Y는 Secondary | 다시 지정(R), 공통 제거 |
| LOCKED | 분석 중에는 영역을 변경할 수 없습니다. | 지정/제거 비활성 |
| DISABLED | 이미지 없음 또는 준비 중 | 지정 비활성, 이미지 열기/준비 안내 |

R을 선택한 것만으로 Drawing이라고 표시하지 않는다. 실제 `selectingRoi`를 사용한다. R Action 자체는 기존 영역을 유지하고, 다음 mouse press에서 hasRoi=false와 새 시작점으로 교체를 시작한다. drag 중 유효 영역이 갱신되고 release에서 selectingRoi=false가 된다. 별도 완료 확인 Modal은 없다.

## 6. ImageJ ROI Lifecycle

| 파생 상태 | 근거 / 화면 |
| --- | --- |
| EMPTY | 기록 없음. Toolbar에서 도구 선택 안내 |
| DRAWING | Viewer의 실제 미완성 도형 초안 또는 Wand worker 진행 |
| AVAILABLE | 기록이 있으나 선택 없음 |
| SELECTED | 기존 manager.selected에 대응하는 record, shape/순번/name 표시 |
| EDITING | 기존 roiEditMode=true, 편집 모드와 종료 Action |
| IMPORTING | 실제 manager.busy=true, 가져오는 중 안내 |
| ERROR | 실제 import errors 또는 editError, 짧은 사용자용 안내와 오류 정보 |

Tool 선택만으로 DRAWING을 만들지 않는다. Point/Text는 클릭 즉시 기록되므로 지속 Drawing 단계를 만들지 않는다. Wand는 기존 async ImageJ bridge를 사용하며 결과가 기존 Polygon record로 저장되는 표현도 유지한다. 승인/검수/새 persistence 상태는 추가하지 않는다.

## 7. 실제 Tool interaction과 Drawing 상태

| Tool | 기존 완료 방식 | 취소/추가 |
| --- | --- | --- |
| 분석 영역 R | drag 후 release | Esc 취소는 기존에 없으므로 안내하지 않음 |
| Rectangle / Oval | drag 후 release | 미완성 입력은 Esc |
| Freehand / FreeLine | drag 후 release | 이동 지점 기록, Esc |
| Polygon / Polyline | 클릭으로 점 추가, Enter 또는 double click | Esc는 미완성 초안 제거 |
| Angle | 세 번째 클릭에서 완료 | 그 전에는 Esc |
| Point | 클릭 즉시 생성 | 선택한 Point record에 후속 클릭하면 점 추가 |
| Wand | 클릭 후 기존 async 연결 영역 계산 | worker 상태는 기존 ImageJ 작업 상태 |
| Line / Arrow | drag 후 release | Esc |
| Text | 클릭한 위치에 기록 | 별도 완료 버튼 없음 |

Backspace 완료/삭제는 지원하지 않으므로 안내하지 않는다. Esc는 편집 종료를 하지 않는다. 실제 pointer cancel은 기존 edit drag rollback과 tool draft 정리를 유지한다.

Tool·edit mode·stack page·새 이미지 loading 시작 시 **미완성 ImageJ 입력 초안만** 정리해 다른 Tool/page에서 합쳐 기록되는 것을 막는다. 저장된 record/완료 geometry, 분석 영역 좌표 계산, rendering 함수는 바꾸지 않는다. 부분 입력을 새 record로 저장하지 않는다.

## 8. Edit mode

기존 `advanced.editRoi`를 공통 checkable Action으로 정리한다. 시작/종료 모두 기존 `roiEditMode`를 토글하고 `ROI_EDIT`로 ROI Context를 유지한다. 진입 시 현재 페이지의 표시된 단일 경로 record가 필요하며, 종료는 선택이 없어져도 가능하다. 기존 Tool checked 조건 `activeTool && !roiEditMode`를 유지한다. Action 후 Main Window 활성화 요청과 기존 Qt.callLater Viewer focus 복귀를 사용한다.

Viewer의 꼭짓점 drag, double click 추가, Delete 삭제, Ctrl+Z/Ctrl+Shift+Z와 기존 10단계 bounded history를 유지한다. 새 undo/redo 시스템은 만들지 않았다. 편집 종료 버튼 또는 H/다른 도구 선택으로 종료한다. 세부 설정의 checkbox도 동일 Action을 사용한다.

## 9. Import / 오류

가져오기 버튼은 기존 `importRoisAction`과 `roiFileDialog`를 사용한다. .roi/ZIP loader와 기존 부분 성공·오류·한도·read-only 정책은 그대로다. 성공하면 실제 count/첫 가져온 record 선택/Overlay가 갱신된다. OS dialog Cancel은 loader를 호출하지 않으며 오류나 record 변경을 만들지 않는다.

오류는 Primary UI에 “ROI 작업 오류 · 상세 정보를 확인하세요.”로 표시한다. 원래 오류 자료는 크기가 제한된 Scroll Dialog에서 확인한다. 긴 exception/path를 본문에 나열하지 않는다. 새 오류 backend나 로그 형식은 추가하지 않았다.

## 10. ROI Manager / 선택·삭제·저장

**기존 ROI 관리자는 별도 Window가 아니라 ROI Context의 목록/편집과 Python RoiManager다.** 기존 `advanced.roiManager`는 `ROI_MANAGER_OPEN`으로 해당 Context를 연다. 새 Manager Window를 만들거나 목록 복사본을 두지 않았다.

Context Row 선택 → 기존 `selectImportedRoi(id)` → manager.selected → 동일 roiState의 selected flags → Viewer Overlay와 편집 필드가 함께 갱신된다. 기록 제거는 해당 ID만, 목록 비우기는 기존 clear_list와 history를 사용한다. 기존 ZIP 복사본 저장/원본 덮어쓰기 금지/dirty 및 새 이미지·종료 discard 확인은 유지한다.

## 11. Context 전환 정책

자동 요청은 기존 whitelist만 사용한다: 명시적 Manager `ROI_MANAGER_OPEN`, Import 요청/완료 `ROI_IMPORT`, 편집 시작/종료 `ROI_EDIT` → ROI. 새 파일은 IMAGE, 분석 완료/후보 선택은 기존 RESULT 정책이다.

Tool 선택·R/H·drag/release·record 생성·hover·page 변경·상태 갱신은 Context를 강제 변경하지 않는다. ImageJ record 생성은 현재 IMAGE/ANALYSIS/RESULT/ROI를 유지한다. 명시적 관리 작업의 전환과 그리기 완료를 구분한다.

## 12. AnalysisContext / Result 연결

AnalysisContext의 기존 영역 지정 Action과 Ready 조건을 그대로 사용한다. 지정 영역 선택 → R → Viewer drag → **ANALYSIS 유지** → 같은 roiX/Y/Width/Height로 Ready 재평가. ROI Context에서의 지정/제거도 즉시 같은 AnalysisFlowState에 반영된다. 전체 이미지 분석에는 ImageJ 기록이 필요하지 않다.

RUNNING의 분석 사각형 변경/제거/명시적 imported bounds 변환은 기존 잠금을 유지한다. ImageJ 기록은 별도 자료이며 기존 편집·import backend semantics를 합치지 않았다. ImageJ import/edit/delete에 새 Result invalidate/filter/selection 호출을 추가하지 않았다. 기존 Candidate 자동 사각형·수동 추적 해제 정책도 유지한다.

## 13. Toolbar / Viewer 연결

TD-02의 7개 Toolbar 버튼과 ROI/측정 메뉴 구조는 그대로다. 분석 영역 지정은 Toolbar/AnalysisContext/ROI Context에서 **같은 R Action**을 재사용한다. 제거/Import/Manager/Edit도 기존 공통 Action을 사용한다.

기존 ViewerHeader StatusIndicator 한 곳만 “분석 영역 · 지정 중”, “ROI · Polygon · 생성 중”, “ROI 편집”으로 확장했다. 별도 중복 Viewer indicator를 만들지 않았다. 분석 Area의 Accent 사각형과 ImageJ record의 기존 색/선/꼭짓점 geometry는 그대로다. Context의 이름·상태·선택 배경/Accessible.name/selected도 함께 제공한다.

## 14. Stack scope / 새 이미지

- 기존 분석 사각형은 **현재 페이지** 기준. pageChanged에서 초기화한다.
- 생성 ImageJ record는 multipage stack의 현재 page_index를 저장한다.
- imported ROI는 기존 ImageJ position/frame/slice 태그 해석에 따라 page-specific 또는 page_index=None(모든 페이지)이다. 다른 페이지 record는 목록에 유지되지만 active=false, Overlay/편집은 현재 페이지의 visible/active record만 사용한다.
- page 변경 시 기존 edit mode와 record 선택 자체는 유지한다. inactive 선택은 편집 진입 비활성/현재 페이지 미표시 안내를 한다. 미완성 입력 초안은 정리한다.
- 새 원본 파일 성공 시 기존 records/hidden/selection/history/edit mode/분석 영역 초기화와 IMAGE 전환을 유지한다. dirty record는 기존 discard 확인을 거친다. working copy의 기존 보존 정책은 바꾸지 않는다.
- ImageJ frames를 물리 공간 Z로 해석하지 않는다.

## 15. Responsive / 실제 화면

1100×700 / 1440×900에서 분석 영역 상태/주요 Action, ImageJ count/현재 선택, Import/Manager/Edit/저장 접근을 확인했다. ROI 패널 폭 282px 유지, List 최소 60px 및 독립 Scroll. 긴 좌표 편집은 bounded Dialog 내부 Scroll로 이동했다.

Windows 실제 창 합성 캡처 **13장**, QML 경고 0개. 실제 XRT/모델/사용자 ROI는 포함하지 않았다.

| 상태 | 캡처 |
| --- | --- |
| 이미지 없음 / 비어 있음 | [없음](../screenshots/roi-td06/no-image-1100.png) · [빈 상태](../screenshots/roi-td06/empty-1100.png) |
| 분석 영역 | [생성 중](../screenshots/roi-td06/area-drawing-1100.png) · [완료](../screenshots/roi-td06/area-ready-1100.png) · [실행 중 잠금](../screenshots/roi-td06/running-locked-1100.png) |
| ImageJ ROI | [Polygon 생성 중](../screenshots/roi-td06/polygon-drawing-1100.png) · [선택](../screenshots/roi-td06/selected-1100.png) · [1440×900](../screenshots/roi-td06/selected-1440.png) |
| 편집 | [편집 중](../screenshots/roi-td06/editing-1100.png) · [세부 설정](../screenshots/roi-td06/details-1100.png) |
| 가져오기 / 페이지 | [가져온 기록](../screenshots/roi-td06/imported-1100.png) · [오류](../screenshots/roi-td06/import-error-1100.png) · [다른 페이지](../screenshots/roi-td06/other-page-1100.png) |

## 16. 테스트 결과

Windows / Python 3.13 / Qt 6.11.2 / Java 24. 생성 TIFF/JPEG·ROI와 테스트 adapter로 검증한다.

- 신규 `test_roi_ux.py` **23 passed**: 이미지/empty, 분석 영역 drag/좌표/재지정/제거/공통 Action/두 Context 유지/Ready/Running 잠금, Rectangle/Oval/Freehand/Polygon/Line/Polyline/Angle/Point 및 다중 점, 실제 Wand bridge, Esc·Pan·Zoom·다른 Tool·page의 초안 정리, Import Cancel·성공·오류, 단일 선택/Overlay/Manager, 편집 toggle·focus·checked, 원본 보존·ZIP roundtrip, page scope·숨김·새 파일/기존 discard, 두 창 크기, Result filter/candidate/분석 사각형 보존.
- 기존 JPEG import/Overlay 테스트는 **새 세부 설정 진입 후 기존 외접 사각형 버튼을 실제 클릭**하도록 경로만 수정했다. X=40/Y=50 및 rendering/원본 확인은 유지한다.
- Ruff / compileall / wheel PASS. QML 63개, sources/artifacts/실제 데이터·모델 제외.
- 전체 회귀 **222 passed, 4 skipped (168.29초)**. offscreen에서 제외되는 native GUI 4개는 실제 Windows 창으로 별도 실행하여 **4 passed (53.56초)**. 총 **226개**를 확인했다.
- OS ROI 파일 선택 창 Cancel은 QML Dialog reject 연결로 검증했다. 사람이 마우스로 OS 선택 창을 조작하는 검사는 재수행하지 않았다. 실제 화면 캡처는 Qt Windows 세션에서 수행했다.
- 기존 좌표·geometry·history·serialization·Fiji ROI·Viewer hit-test·TD-02~05 회귀 검사를 유지한다.

## 17. 보존·제약·후속 범위

Python RoiManager/ROI loader·serializer/geometry/분석 pipeline/원본·TIFF 처리/ImageJ·Fiji bridge/ImportedRoiOverlay rendering/Result/Toolbar 구조·Context whitelist는 수정하지 않았다. 계약 버전·스키마·해시 영향 없음. geometry 생성 수식과 분석 사각형 floor/ceil은 그대로이며 화면 drag의 반올림 오차를 테스트에서 ±1px로 확인한 뒤 제출 사각형과 UiState 값은 정확히 비교한다.

분석 영역 Esc 취소와 새로운 multi-shape 분석·mask·snapping·undo system은 제공하지 않는다. 별도 Manager Window도 기존에 없었다. 임의 record 종류·복합 경로 편집 한계는 기존 backend 그대로다. 사용자 이해 시간/실제 대형 XRT 성능/실제 모델 inference는 이번 UX TD에서 새로 측정하지 않았다.

- [TD-07](XRT-UX-TD-07-TIFF-LOADING.md): 첫 정밀 frame의 Pan·Zoom·분석 영역을 전체 스택 준비와 분리한다. ImageJ 도형 생성·편집·가져오기는 기존 backend 전체 준비 조건을 유지하며 ROI 좌표/geometry 정책은 동일하다.
- TD-08: 전체 Visual Density.
- 추후 통합 검증: Windows native dialog cleanup / TD-05의 engine teardown `0x80010108` 진단 재확인. 이번 TD에서는 해당 platform/backend 경로를 수정하거나 해결됐다고 보고하지 않는다.
