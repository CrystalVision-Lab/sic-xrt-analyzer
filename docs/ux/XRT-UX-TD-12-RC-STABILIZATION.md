# XRT-UX-TD-12 — Windows UI 이벤트 안정화 및 최종 RC 검증

Issue [#78](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/78), stacked Draft PR [#79](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/79).
**Status: PARTIAL. RC CODE READY — MANUAL VALIDATION PENDING. Merge Readiness: PENDING.**
자동 검사·실제 데이터 검증은 완료했고 실제 native mouse/focus gate는 미검증이다.

## 1. TD-11 기준 상태

- 시작 branch `fix/76-model-input-preflight`, exact HEAD `76eecc7941c47d1ee52d694fbb9cabdcb9cc00a3`, PR #77.
- 작업 branch `fix/78-windows-ui-rc-stabilization`. Production 수정 `beaf959`, 검사/계측/CI HEAD `31a6629ac38e5388154cf6094a080bda8f083113`.
- 최종 제출 HEAD는 PR #79 최신 head 및 `git rev-parse HEAD`로 확인한다. 본문/최종 응답에 exact SHA를 기록한다.
- TD-11: Windows 전체 Toolbar 1 fail, Linux CI success, TD-10 native 완화/실제 mouse pending. 이 실패를 출발점으로 유지했다.
- D 작업본/venv, D TEMP/TMP/basetemp/ImageJ temporary 및 pip cache 사용. 시작 D free322.46GiB/C13.05GiB.
- Python3.13.7, PySide6/Qt6.11.2, Qt Basic, QSG basic. 자동 suite offscreen, native 직렬 windows. pytest 순서는 기본 수집 순서.
- pytest synthetic만 Java512MiB 제한; 실제 데이터/모델/native stress에는 제거. production JVM 설정 변경 없음.

## 2. Windows Toolbar 실패

기존 `test_toolbar_layout_and_analysis_menu_entry[size0]`를 수정 없이 재현: **1 failed /3 passed,16.40s**.
1100×700에서 분석 메뉴를 열고 클릭하자 Action0회. 독립 재실행이 PASS여도 해결로 결론내리지 않았다.

## 3. 기존 실패 로그

- TD-10 D 최초:267pass/1fail/4skip → 독립 Toolbar4pass → 같은 전체268pass/4skip.
- TD-11 전체290pass/1fail/4skip, 재검사도 같은 Toolbar 실패. 당시 관측 center(392,76) 또는(392,172).
- TD-12 `artifacts/td12/baseline-toolbar.log` 및 JSON/after-failure screenshot 보존.
- refined observer 재실행4pass/6.73s도 보존. observer/스케줄 영향 가능성이 있어 PASS만으로 원인 확정하지 않았다.
- 원인 회귀 `root-before.log`: closed available row implicitHeight0을 결정적으로 검출(1fail). 수정 후 `root-after2.log`:5pass/6.97s.
- 초기 수정 시 separator에 존재하지 않는 property를 적용한 QML setup5errors(`root-after.log`)는 바로 되돌려 해결했으며 로그 유지. 최종 코드는 로딩/전체 회귀로 별도 검증.
- fixture reexport lint F811/PLC0414/I001도 새 검사 module만 정리. 기존 tests의 대기/입력/assertion 변경 없음.

## 4. Popup Geometry 조사

| 값 | 수정 전 실패 | 수정 후 RGB 분석 메뉴 |
|---|---|---|
| Window | x/y2/2,1100×700 | 동일 |
| Menu x/y,width,height | 0/30,250×34 | 0/30,250×226 |
| Menu visible/opened | true/true | true/true |
| ListView height/contentHeight,count |26/26,15 |218/218,15 |
| Run local y/height |26/32 |122/32 |
| Run scene/window center |392,76 |392,172 |
| Run global center |394,78 |394,174 |
| DPR / active / enabled |1/true/true |동일 |
| Closed row implicitHeight |0 |32 |
| Mouse press / release |press후 popup닫힘, release미관측 |press+release, itemfocus |
| Action triggered |0 |1 |

`mapToScene`의 QQuickWindow 좌표를 QTest에 사용했고 `mapToGlobal`에서 window origin2/2가 확인됐다.
Menu top30+height34=bottom64, clickY76은 clipped viewport 밖. 수정 후 clickY172는 viewport 안.
사진은 실패 직전 grab이 layout을 바꿀 위험 때문에 **실패 후** 저장했다. 실패 직전 실제 화면 캡처라고 주장하지 않는다.

## 5. 이벤트 전달 경로

`tools/windows_ui_probe.py`는 기존 test의 click을 그대로 호출하고 window event filter, Item에서 제공되는 pressed/clicked/triggered signal 및 Action triggered를 기록한다. 최종 full trace에서 menuRunAnalysis pressed=true→false 및 Action1회를 확인했다. 메모리 snapshot은 call 종료 후 JSON에 저장하며 layout/event/wait를 강제로 변경하지 않는다.
실패는 press→popup 외부 클릭 처리→닫힘, Run에 release가 도달하기 전이다. Run disabled나 연결된 backend 실패가 아니다.
기존 Context/Menu의 동일 Action 객체 검사 유지. 새로운 gray16 disabled 실제 hit test는 Action0회, 기존 RGB click은1회; 중복 실행 없음.

## 6. 테스트 순서 의존성

| 새 프로세스 Case | 결과 |
|---|---|
| isolated-1 | 6 passed / 0 failed / 0 errors / 0 skipped (7.753s) |
| isolated-2 | 6 passed / 0 failed / 0 errors / 0 skipped (7.230s) |
| isolated-3 | 6 passed / 0 failed / 0 errors / 0 skipped (7.476s) |
| after-context | 15 passed / 0 failed / 0 errors / 0 skipped (19.124s) |
| after-analysis | 21 passed / 0 failed / 0 errors / 0 skipped (18.375s) |
| after-result | 18 passed / 0 failed / 0 errors / 0 skipped (29.263s) |
| after-roi | 27 passed / 0 failed / 0 errors / 0 skipped (29.947s) |
| after-loading | 19 passed / 0 failed / 0 errors / 0 skipped (16.505s) |
| after-dialog | 11 passed / 0 failed / 0 errors / 0 skipped (7.095s) |
| after-preflight | 27 passed / 0 failed / 0 errors / 0 skipped (13.945s) |
| reordered | 109 passed / 0 failed / 0 errors / 0 skipped (94.280s) |

C는 각 module→Toolbar 순서, E는 Preflight→Loading→ROI→Result→Analysis→Context→Toolbar→새 geometry 순서.
모든 trace에 window/focus/DPR/geometry/Action 횟수 기록. 닫힌 row 높이0→open 후 ListView 갱신 시점에 따라 첫 clickgeometry가 달라졌다. 이전 module의 어떤 이벤트가 갱신을 늦췄는지는 별도 미확정이며 race 제거의 원인은 높이 의존성 분리이다.

## 7. Root Cause 및 분류

공통 AppMenuItem `implicitHeight: visible ? menuRowHeight : 0`은 기능 숨김과 ancestor effective visibility를 혼동했다. closed popup이 descendant visible=false로 만들면서 available row까지0px이 되고 ListView의 contentHeight가 separator26만 남았다. open때 row32가 복원되어도 ListView geometry가 같은 script/event 시점에 반드시 갱신되지 않는다.
[Qt Item visible 공식 설명](https://doc.qt.io/qt-6.8/qml-qtquick-item.html#visible-prop)과 [ListView forceLayout 설명](https://doc.qt.io/qt-6.8/qml-qtquick-listview.html#forceLayout-method)의 전파·프레임별 갱신 동작과 계측이 일치한다.

- **ENVIRONMENT / ORDER DEPENDENCY:** offscreen/QTest에서 geometry 준비 시점 의존성 재현 및 원인 확인.
- **QML component 결함:** closed available row 자체가0이라는 결정적 회귀로 확인, 제품 component 최소 수정.
- **PRODUCT BUG(실제 사람 클릭 실패): UNKNOWN / MANUAL PENDING**. 실제 사용 실패까지 확정할 수 없다.
- **TEST BUG:** scene/global/DPR 변환 오류 근거 없음. helper의 window bounds/visible만으로 clipped popup hit를 보장하지 못하는 한계는 확인. 기존 test를 느리게 하거나 보정하지 않았다.

## 8. 수정 내용

- AppMenuItem `rowAvailable`이 submenu availability/기존 feature 조건을 소유. visible은 이를 사용하고 implicitHeight도 이 독립 조건을 사용.
- AppMenuBar/ROI/Advanced의 기존 visibility 식을 rowAvailable로 전달. 숨겨야 하는 feature는 여전히0px.
- Advanced separator height도 feature 조건을 직접 사용하여 ancestor visibility feedback 제거.
- Toolbar 디자인/Theme/Context/Analysis/Result/ROI 계산/decoder/cache/모델/외부 계약은 변경하지 않음.
- 새 closed/reopen/feature-hidden/disabled 회귀2개, 기존 테스트는 변경하지 않음.
- Native stress 도구의 sequence+action 분기에서 ROI/Result까지 unrelated Save를 호출하던 경로를 각 facade open으로 정리. Open/Save는 기존 Action dispatch, 나머지는 QML open이며 mouse 검증 아님. production dialog 변경 없음.

## 9. 수정하지 않은 대안

임의 ±96px offset, fixed sleep/timeout 증가, forceLayout로 첫 click 우회, skip/assertion 삭제, non-native picker 전환, Qt version pin, 직접 COM init/uninit, 광범위 rendering/ROI/분석 변경을 적용하지 않았다. 기존 Action/준비 조건을 유지했다.

## 10. Native Dialog 실제 조작

**MANUAL NATIVE VALIDATION PENDING**.
computer-use skill의 지정 runtime initializer가 실행 전 `failed to write kernel assets: os error3`으로 실패. reset 후 같은 실패. 승인된 runtime 대체 우회 입력을 사용하지 않았다.
OpenCancel20/SaveCancel20/OpenSelect10/SaveConfirm10/교차 조작은 **각각 실제 mouse0회, PENDING**. QTest/queued reject/accepted callback을 실제 mouse PASS로 계산하지 않는다.

자동 HWND 반복(직렬):
- open: 100cycles/100native HWND, exit0, QML warnings0.
- save: 100cycles/100native HWND, exit0, QML warnings0.
- sequence: 10cycles/40native HWND, exit0, QML warnings0.

자동 Open sample1→100: handles1938→1916, USER70→59, GDI80→82, RSS923.0→929.3MiB.
Save sample1→100: handles1912→1891, USER69→59, GDI79→81, RSS917.5→925.8MiB.
Shell warm-up 후 해당 샘플에서 뚜렷한 선형 handle 증가 없음. 모든 사용 조건의 leak 부재를 보장하지 않음.

## 11. Focus 복귀

Toolbar/Context 메뉴 후 Viewer Qt focus 및 H/R/drag/Zoom/Fit은 기존 QTest 회귀에서 검사한다. **OS native dialog를 사람이 닫은 직후의 focus는 PENDING**.
수동 항목: main window active, Viewer keyboard focus, Pan/Zoom/Fit/H/R/drag/stack arrows/AnalysisContext/Result candidate가 첫 입력에 반응하는지, dialog뒤에 가려짐/두 번 클릭 요구 여부.

## 12. COM 진단

자동 Open100/Save100/교차10 로그의0x80010108 **0회**, CoGetApartmentType HRESULT 전 sample0x0. 기능 오류/AV도 관측되지 않았다. 다른 Shell/사용 조건에서의 HRESULT 의미를 일반화하지 않는다. TD-09 AV는 COM warning 없이도 발생해 직접 인과관계는 미확정이다. diagnostic HRESULT/사용 기능 이상/AV를 서로 구분한다. warning을 숨기거나 exception handling을 완화하지 않았다.

## 13. 접근 위반 여부

전체3회/plugin/stress3process/실제데이터2process 모두 exit0. 이번 자동 native HWND240개에서0xC0000005 **0회**. 실제 mouse 반복 AV는 미검증. TD-10 C++ root cause/PDB causal proof는 UNKNOWN이고 기존 QApplication/GUI STA/modal owner/reuse/cleanup 완화 구조 유지.

## 14. ROI 안정성

기존 row/details/edit/Polygon complete+cancel/import/manager/ZIP 흐름 회귀 유지. after-ROI27pass.
이전 ROI details center가 window밖인 failure, async Wand deadline 이력은 보존. 이번 menu 문제와 동일 원인이라고 확정하지 않음. 현재 반복 통과는 재현되지 않음을 뜻하며 역사적 원인 해결을 주장하지 않는다.

## 15. 전체 Windows 반복 검증

| 검사 | Run1 | Run2 | Run3 |
|---|---|---|---|
| Toolbar | 4 PASS | 4 PASS | 4 PASS |
| Analysis | 17 PASS | 17 PASS | 17 PASS |
| ROI | 23 PASS | 23 PASS | 23 PASS |
| Full Suite | 293 passed / 0 failed / 0 errors / 4 skipped (224.961s) | 293 passed / 0 failed / 0 errors / 4 skipped (218.466s) | 293 passed / 0 failed / 0 errors / 4 skipped (214.475s) |

새 프로세스 직렬, 동일 production/test source; full suite 안에서 Toolbar/Analysis/ROI/Context/Preflight 포함. Native 4skip은 windows plugin 별도 검사로 분리하며 새 skip 없음.
Ruff/compileall/diff check PASS. wheel build PASS, QML69개와 native controller 포함, 원본/모델/artifacts/sources 제외.

## 16. Linux CI

PR #79 [code CI 37732978820](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/37732978820) **success**: Linux 전체293pass/4skip(244.14s), X11 plugin4pass/5deselected(29.79s), lint/import/compile/wheel/커밋2개 policy PASS.
최종 문서·stress tool 커밋 포함 head의 CI run/job/로그는 PR checks와 최종 PR 본문/응답에서 별도로 기록한다. 문서 작성 후 final SHA/CI를 자기 참조 commit 안에 넣지 않는다.
lint/import/compile/wheel/전체offscreen/X11 plugin/PR policy gate를 사용. 기존 CI에 실제 wheel build step만 추가. 최종 head CI와 jobs/logs를 별도로 확인한다. 이후 source/tests/QML/계측 plugin은 검사 HEAD31a6629와 동일하며, native stress tool 수정은 별도 실행으로 확인했다.

## 17. 실제 XRT

- `N119_220_Section_stack_flipped.tif`: 3072×3012, 158페이지, uint16. 첫/중간/마지막 및 전체 탐색·표시 범위·확대/Pan·Fiji ROI 검증, SHA-256 전후 동일.
- `No107_SectionTopo-afterAnnealing .tif`: 2922×2895, 156페이지, uint16. 첫/중간/마지막 및 전체 탐색·표시 범위·확대/Pan·Fiji ROI 검증, SHA-256 전후 동일.
- `No107_SectionTopo-beforeAnnealing.tif`: 2922×2895, 156페이지, uint16. 첫/중간/마지막 및 전체 탐색·표시 범위·확대/Pan·Fiji ROI 검증, SHA-256 전후 동일.
- `No22_220_Section_stack_flipped.tif`: 2944×2745, 156페이지, uint16. 첫/중간/마지막 및 전체 탐색·표시 범위·확대/Pan·Fiji ROI 검증, SHA-256 전후 동일.

실제 windows/DPR1/1920×1080에서 T3 first-view0.207~0.370s, T4 full-stack14.629~47.425s. 사전 hash로 warmed OS cache인 단회 참고값이며 FPS가 아님.
ImageJ frames를 공간Z로 자동 해석하지 않음. 원본은 읽기 전용, sources/ diff없음. 실제 캡처·개인 경로·모델·대형 Export는 ignored artifacts에만 보관한다.

## 18. 실제 연구 모델

실제 RGB JPG 12349×12273: 전체 후보 2946, counts `{'TSD': 1303, 'BPD': 245, 'TED': 1398}`. 동일 ROI x1003/y1011,1495×1495×3: 791개. TD-09 원본·모델 hash/후보/ROI 비교 PASS. 모델 정확도·승인 판정은 수행하지 않음.

모델 `spatial64-c4-24368b8f6613`, SHA `24368b8f6613cba5251c0bd8e63d7ddec726d6343a35ed878e823a0091369694`, 계약 frozen_xrt_patch_classifier v1. 모델·normalization·threshold·preprocessing 변경 없음.

## 19. Model Preflight

실제 RGB8 COMPATIBLE/Run enabled→inference, gray uint16 단일채널 INCOMPATIBLE/Run disabled/FULL+ROI inference0/backend direct INVALID_INPUT **PASS**. TIFF4개 header descriptor도 일치. RGB 복귀 후 compatible recovery PASS. 음수 case에서도 Viewer/Stack/ROI/ImageJ/저장 사용 유지. 새 uint16→uint8/gray→RGB 변환 없음. 기존 JPEG RGB888 decode 정책 유지.

## 20. E2E

`validate_rc_session.py`의 같은 Qt session: 실제 파일 open→탐색/contrast/Pan/Zoom/Fit→ROI→ImageJ→상태 정리/종료.
`validate_input_preflight.py`: 실제 JPG→모델 전체+ROI→필터/overlay/candidate→JSON/CSV/copy→취소/재실행→gray16 gate→ROI/ZIP/macro→RGB recovery→종료.
Native mouse Open/Save가 포함된 단일 사용자 session 완결은 **PENDING**, slot으로 대체하지 않음. 실제 stacks/model session exit0, QML warnings0. Stacks shutdown0.032s/restart0.002s, model session0.169s. 종료 이후 이전 창/worker 응답에 의한 QML warning 없음.

## 21. 저장 / Export

같은 actual-model flow에서 result JSON 전체 비교/CSV2946행/원본 JPG copy SHA/ROI ZIP 재읽기·geometry/page tags **PASS**. TIFF4개/JPG/manifest/ONNX SHA 전후 동일. ROI 4종 생성·Point 이동·미완료 Polygon 취소·macro 및 페이지 이동 PASS. Native Save 확정/cancel은 실제 mouse PENDING, 자동 callback/취소 의미는 기존 회귀로 분리.
기존 rectangle integer bounds 및 float32 ROI serialization quantization은 유지; float64 bitwise roundtrip을 주장하지 않음.

## 22. Known Issues

| Severity | 내용 | 재현/해결 | RC 영향 |
|---|---|---|---|
| Validation gate | 실제 native mouse/focus | runtime os3, PENDING | RC READY 선언 금지 |
| P0 history | TD-09 native AV | TD-10 완화 유지, C++ 원인 UNKNOWN | 새 AV면 blocker, 자동 결과만으로 실제 사용 해결 확정 불가 |
| P2 history | ROI details/Wand event | 이번 반복 결과 별도; 같은 menu원인 미확정 | 재발 여부 확인 |
| Scope | gray16→RGB8 모델 | expected incompatible/inference0 | 기능 제약, 변환 추가하지 않음 |
| Scope | 실제 모델 정확도/3D Z | 이번 평가 범위 밖 | 후보 수 regression만 검증 |

## 23. RC Verdict

**RC CODE READY — MANUAL VALIDATION PENDING**. Windows 전체3회 및 plugin/native 자동 반복, 실제 TIFF4개·RGB 모델/Export·preflight 및 code CI가 안정적이다. 최종 head CI도 제출 후 확인한다.
**Technical RC: NOT READY (manual gate pending)**. 실제 mouse/focus/사용 session이 미검증이므로 RC READY를 선언하지 않는다. 역사적 native C++ causal proof도 UNKNOWN. 새로운 P0/P1은 자동 검증 범위에서 관측되지 않았다.

## 24. Merge Readiness 및 Stacked PR

**PENDING**, Draft/reviews0/선행stack 의존. GitHub mergeable=true는 충돌 계산만 의미하며 리뷰/보호조건 충족을 뜻하지 않음. Branch protection 상세는 미확인.

| PR | Base | Head | Head CI | State | Reviews | Mergeable |
|---|---|---|---|---|---:|---|
| [#56](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/56) | `feat/52-candidate-roi` | `refactor/55-ui-information-architecture` | [success](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/37448160374) | Draft | 0 | true |
| [#59](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/59) | `refactor/55-ui-information-architecture` | `refactor/58-toolbar-simplification` | [success](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/37460753747) | Draft | 0 | true |
| [#61](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/61) | `refactor/58-toolbar-simplification` | `refactor/60-context-panel-workflow` | [success](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/37466740073) | Draft | 0 | true |
| [#63](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/63) | `refactor/60-context-panel-workflow` | `refactor/62-analysis-flow` | [success](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/37470961153) | Draft | 0 | true |
| [#65](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/65) | `refactor/62-analysis-flow` | `refactor/64-result-ux` | [success](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/37475188402) | Draft | 0 | true |
| [#67](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/67) | `refactor/64-result-ux` | `refactor/66-roi-ux` | [success](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/37481798962) | Draft | 0 | true |
| [#69](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/69) | `refactor/66-roi-ux` | `refactor/68-tiff-loading-ux` | [success](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/37554175119) | Draft | 0 | true |
| [#71](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/71) | `refactor/68-tiff-loading-ux` | `refactor/70-visual-density` | [success](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/37560097893) | Draft | 0 | true |
| [#73](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/73) | `refactor/70-visual-density` | `test/72-ux-integration-rc` | [success](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/37566749461) | Draft | 0 | true |
| [#75](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/75) | `test/72-ux-integration-rc` | `fix/74-windows-native-dialog-crash` | [success](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/37626939701) | Draft | 0 | true |
| [#77](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/77) | `fix/74-windows-native-dialog-crash` | `fix/76-model-input-preflight` | [success](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/37719906164) | Draft | 0 | true |
| [#79](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/79) | `fix/76-model-input-preflight` | `fix/78-windows-ui-rc-stabilization` | code CI success; final head는 PR checks | Draft | 0 | true(재조회) |

선행 의존 순서 #56→59→61→63→65→67→69→71→73→75→77→79, #56 자체의 base는 #53 브랜치. 병합/rebase/retarget/review 요청/승인 변경 없음. 실제 병합 권고는 manual 검증 및 선행 review 후 결정.

## 25. 후속 작업 / 수동 검증 절차

1. D launcher `run-analyzer.cmd`로 앱을 실행하고 D의 별도 출력 폴더를 준비한다. 원본/모델/source 폴더에 저장하지 않는다.
2. 실제 mouse로 Open→Cancel20, Save→Cancel20을 반복하고 매 회 dialog/main 상태를 기록한다.
3. 실제 JPG/TIFF 선택10회, 새 위치 Save 확정10회. TIFF 첫/중간/마지막, original SHA 및 사본 readback 확인.
4. Open→Save→ROI Import→Result Export 교차 실행. OS 창 경로 반환·저장·닫힘 확인.
5. 매 native닫힘 직후 Pan/Zoom/Fit/H/R/Viewer drag/stack arrows/AnalysisContext/Result candidate를 첫 입력으로 확인한다.
6. 단일 session 전체 flow를 완료하고 정상 종료, exitcode/COM/AV를 기록한다. COM warning은 별도 기록하고 기능 이상과 연결 여부를 관찰한다.
7. AV 발생 시 마지막 조작/owner/Qt warning/exitcode/fault module을 보존, RC를 NOT RC READY로 되돌린다. private dump/log/rawdata는 Git 제외.
8. 수동 PASS 후 technical RC/merge readiness를 다시 판정하고 선행stack 순서로 review한다. 병합은 별도 사용자 승인 후 수행한다.

재현 명령(환경변수 TEMP/TMP/ImageJ_TMP 및 basetemp는 D로 설정):

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:QSG_RENDER_LOOP='basic'
$env:PYTHONPATH="$PWD\tools"
$env:TD12_TRACE_DIR="$PWD\artifacts\td12\reproduce"
.\.venv\Scripts\python.exe -m pytest -q -p windows_ui_probe tests/test_toolbar.py tests/test_menu_geometry.py --basetemp D:\Temp\sic-xrt-td12-reproduce
```

최종 작업은 source fix / regression+probe+CI / native sequence probe / 보고서의4개 커밋으로 나눈다. 전체3회는31a6629의 source/tests에서 완료했고 이후에는 문서와 별도 stress tool만 변경했다.
Working tree의 기존 사용자 AGENTS.md whitespace를 보존하고 stage하지 않았다. 실제 데이터/모델/source 파일 수정·삭제 없음.
