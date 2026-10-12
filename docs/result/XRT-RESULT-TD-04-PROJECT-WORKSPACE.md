# XRT-RESULT-TD-04 Result — 분석 프로젝트 Workspace

## Status

**PASS — 프로젝트 기능·저장 계약·실제 데이터·자동 GUI·Windows 전체·코드 기준 CI.** 물리적 마우스 Acceptance는 **MANUAL PENDING**이다. 기존 Windows AWT 호스팅 반복 검사에서 간헐 실패 1건이 관측됐으므로 해결됐다고 주장하지 않는다.

## Git

- Start Branch: `feat/100-defect-result-explorer` (TD-03 Draft #101)
- Start HEAD: `1afc4f73b0152a484fd31cd7cd56fadf62c72667`
- New Branch: `feat/102-project-workspace`
- Issue: [#102](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/102)
- Draft PR: [#103](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/103), base `feat/100-defect-result-explorer`
- Final code/test HEAD: `dcb3219bcdd37aa90367cf7f0322f6a47db12340`
- Final HEAD/CI: 문서 자신의 커밋 SHA는 자기 커밋에 넣을 수 없어 최종 PR 본문이 기준이다.
- 기존 stacked PR merge/rebase/retarget 없음. 다른 저장소, `sources/`, Native Dialog 안정화 코드 미변경.
- 사용자 `AGENTS.md` SHA256 `97fd9e0886957e532cfd5bafd525263462dc6e90652cf2b43ce6d3404fc04eaf` 보존; 스테이징하지 않았다.
- 실제 원본·모델·사적 분석 결과/화면은 ignored `artifacts/`에만 보관. 공개 스크린샷은 합성 자료다.

## 기존 프로젝트 저장 구조

TD-01의 `AnalysisProject`, `ProjectStore`, `ProjectReader`, serialization/validation, ReviewRepository, Source 검증을 조사하고 재사용했다. Schema **1.0.0**과 scientific entity의 구조를 유지했다. Source/Run/Observation/Prediction/Geometry/DefectInstance/ReviewEvent/ModelProvenance/ImageRelationship은 원래 계약을 따른다.

프로젝트 저장은 JSON manifest, 64 MiB 제한, 같은 디렉터리 임시 파일 + flush/fsync + replace, OS writer lock과 expected_revision 검사를 사용한다. 다른 프로젝트 overwrite 및 과거 Run/Prediction/Review/Geometry 삭제·수정 보호를 UI에서 우회하지 않는다. 이미지 복사본/기존 Export/Feedback 저장소를 프로젝트 저장으로 대체하지 않았다.

## 추가한 UI 구조

`ProjectWorkspace.qml`은 새 프로젝트 이름/경로, 원본·Run 목록, 최근 프로젝트 관리, Save/SaveAs, Hash/Relink, 저장 보호와 작업 상태를 제공한다. Main/AppMenuBar/Navigation/AppShell/UiState의 기존 연결을 확장했다. 중앙 Viewer 면적을 늘리지도 줄이지도 않고 별도 프로젝트 작업창을 열어 관리한다.

파일 메뉴: 새 분석 프로젝트, 프로젝트 열기, 최근 프로젝트, 프로젝트 저장, 다른 이름으로 프로젝트 저장, 프로젝트·이미지와 이력. `Ctrl+Alt+S`는 프로젝트 저장; 기존 `Ctrl+S`는 이미지 작업 복사본 저장을 유지한다. 좌측 활성 프로젝트 표시에는 이름, 변경/읽기 전용/원본 연결 상태, 이미지 수와 Run 수를 표시한다. 원본 목록은 JPG의 분석 이력 수와 TIFF의 스택 페이지 수를 두 줄로 구분한다.

## ProjectController

별도 QObject가 immutable 도메인 snapshot, saved revision, dirty/path/recent, source availability, 선택 이력과 dependency 상태를 소유한다. LatestReader 작업은 GUI thread 밖에서 수행한다. 작업 종류·진행·취소·오류를 QML에 전달하며 epoch/작업별 Event로 취소한 오래된 load/hash 결과를 무효화한다. GUI publication은 Slot에서만 수행한다.

SHA 진행은 10 Hz 이하로 제한한다. Source/Run/count DTO는 프로젝트 객체가 바뀔 때만 다시 만들어 진행 알림마다 전체 후보를 재검색하지 않는다. 분석 RUNNING 중에는 프로젝트/저장 이력 전환을 막아 다른 프로젝트에 Run이 섞이지 않게 한다. 저장 중 완료된 Live Run은 큐에서 캡처한 뒤 저장 보호를 해제한다.

## 프로젝트 생성

이름은 공백 제거 후 1–200자, 경로는 기존 파일이 없는 `.json` 목적지다. 새 프로젝트는 빈 원본/Run 목록으로 실제 원자적 저장을 완료한 뒤 활성화한다. 기존 파일·symlink로 생성하지 않는다. 실패하면 이전 프로젝트를 유지한다. 프로젝트를 먼저 만들지 않은 최초 완료 JPG 분석도 메모리 초안으로 캡처해 이름/저장 위치를 나중에 정할 수 있다.

## 프로젝트 저장

모든 성공 표시와 dirty 해제는 ProjectStore 저장 성공 이후다. 최초 JPG 원본의 SHA 검증도 worker에서 수행한다. 이미지 pixels/모델을 manifest에 넣지 않으며 TIFF의 전체 SHA는 평소 자동 계산하지 않는다. 미저장 source·Run·role·실험 import를 동일 도메인 snapshot에 저장한다. 오류가 나면 memory snapshot과 dirty를 유지한다.

## Live Result Capture

실제 `COMPLETED` JPG `AnalysisResult`만 기존 `import_legacy_result` adapter로 캡처한다. source snapshot, source candidate/point ID, 원본 좌표, class, raw scores, 표시 score/low flag, request/scope/ROI, model version/hash/manifest, summary/provenance를 그대로 보존한다. 완료된 TIFF 결과를 새 JPG 분석으로 변환하거나 기록하지 않는다. 같은 result_id의 캡처 반복은 idempotent다.

## Multiple Analysis Runs

같은 이미지에서 다른 실행 ID로 완료한 결과는 별도 Run으로 남는다. 새 결과로 이전 Run을 덮어쓰지 않는다. 서로 다른 JPG 원본도 동일 프로젝트에 등록한다. 원본별 Run 목록은 날짜(시간대 포함), 모델 버전, FULL_IMAGE/ROI 범위, 후보 수, 실행 ID 축약과 상태를 표시한다. 합성 2 JPG, 같은 이미지 반복 실행, 원본별 이력과 duplicate capture를 검사했다. 실제 프로젝트는 새 Full/ROI 2 Run과 TD-02 bundle의 기존 2 Run을 함께 보존한다.

## Saved Result Viewer

`SavedResultPresentation`은 저장된 Run의 읽기 전용 presentation DTO다. ResearchController는 Live pipeline과 별개의 provider를 선택하며 `AnalysisPipeline.result/state`를 가짜 완료로 설정하지 않는다. 기존 ResultExplorer/Overlay/Crop/점수·원본 좌표 표시 경로를 재사용한다.

검증된 Source를 연결한 후에만 원본 Overlay/Crop/Focus/Export를 허용한다. 누락된 Source에서도 후보 목록·점수·Run provenance와 선택은 유지한다. Saved 후보의 기존 Feedback 수정 버튼은 비활성화하며 ReviewRepository의 저장된 ReviewEvent 상태만 표시한다. 이전 Feedback 파일을 연구원 정답으로 자동 전환하지 않는다.

독립된 새 OS 프로세스에서 모델 adapter 없이 실제 프로젝트의 **4 Run**을 열고 원본 Crop을 표시했다. 재추론 **0회**, manifest SHA 유지, QML 경고 **0개**다. 단순 새 engine 검증과 별도 프로세스 검증을 각각 기록했다.

## 원본 이미지 목록

파일별 format, Source UUID, 원본 경로, 역할, 페이지 수, 이력과 availability를 관리한다. UNKNOWN/BEFORE_ANNEALING/AFTER_ANNEALING/REFERENCE는 사용자가 명시적으로 선택한다. 파일명을 통해 역할·픽셀 간격·촬영 방향을 추정하지 않는다. 원본 경로는 목록 tooltip에서도 확인할 수 있다.

## TIFF Source 정책

TIFF는 스택/3D 관련 원본 등록·선택·기존 스택 탐색만 제공한다. TIFF를 JPG로 변환하거나 RGB ONNX 분류하지 않는다. 신규 BPD 실험 import/분석 UI도 제공하지 않는다. 저장된 오래된 TIFF Run을 새 JPG 결과 Viewer로 재해석하지 않는다.

ImageJ header의 frames/slices/channels/images/unit/hyperstack 메타데이터를 읽어 기록하되 spatial_axis_type는 **UNKNOWN**으로 유지한다. 입력마다 TIFF 전체 SHA를 재계산하지 않는다. 등록 자체는 header/identity 읽기이며, 실제 화면을 열 때의 기존 stack 준비 정책은 유지한다.

## 최근 프로젝트

QSettings의 별도 `recentAnalysisProjects`에 이름·경로만 최대 10개 보관한다. 이미지 recent와 분리하며 manifest/scientific 데이터/원본 pixels를 복제하지 않는다. 누락 경로는 사용자에게 load error를 표시하고 목록에서 제거할 수 있다.

별도 `projectView/<project_uuid>` 설정에는 마지막 Source/Run과 선택 ID를 기록한다. **마지막 열람 복원**은 명시 버튼이며 잘못된 Source를 자동 실행하지 않는다. Pan/Zoom/검색/필터/후보 선택은 JSON scientific dirty를 만들지 않는다. 동일 프로젝트 SaveAs는 UUID가 같으므로 같은 로컬 view key를 공유한다.

## 원본 누락 및 Relink

원본이 없어도 프로젝트·Run·Prediction·Review·Geometry 메타데이터를 열 수 있다. 이미지·Crop·Overlay·해당 원본의 새 분석은 막고 연결 필요 상태를 표시한다. 단순 filename/size match로 신뢰하지 않는다. 재연결은 기록된 **content_hash가 이미 있는 Source**만 가능하며 선택 파일을 스트리밍 SHA로 검증하고 header 정보도 검사한다. 다른 내용은 거부하고 기존 참조를 유지한다. 성공 시 Source 참조만 갱신하고 과거 Run의 original source_identity는 변경하지 않는다.

원래 hash가 없는 오래된 프로젝트는 메타데이터를 보여주고 원본이 아직 존재할 때 명시 SHA 확인을 요구한다. 이미 사라진 파일의 정답 SHA를 추정하지 않는다. 취소한 작업의 늦은 progress/publication은 현재 선택을 덮어쓰지 않는다.

## Hash Verification

1 MiB 청크, stat before/after, 취소 체크, 진행 표시를 사용한다. 전체 파일을 bytes로 한 번에 읽지 않는다. SHA 검증 결과는 dirty Source metadata로 저장한다. Saved source를 여는 경우 저장된 SHA가 있으면 그 파일을 확인한 뒤 pixels를 연결하므로 큰 JPG의 반복 열람에는 재검증 비용이 있다. 파일 content를 신뢰할 수 없는 상태의 임의 캐시 우회는 구현하지 않았다.

## Dirty Tracking

완료 Live capture, Source 추가, 역할/이름 변경, 검증 hash/relink, 명시 experiment import가 dirty다. Preview interaction, 후보 선택, 목록 필터는 dirty가 아니다. 새 프로젝트/열기/최근 전환/닫기/앱 종료는 Save/Discard/Cancel을 거친다. 프로젝트 보호를 먼저 처리하고 기존 ROI discard 보호를 다음에 처리한다. failed save 후 memory/dirty 유지, cancel 후 프로젝트/ROI 유지와 dirty app-close cancel을 검사했다.

## Atomic Save

기존 ProjectStore atomic path를 재사용한다. 실험 dependency 준비·검증은 manifest publish 전에 완료한다. 파일/권한/fsync/replace 오류를 성공으로 표시하지 않으며 기존 JSON byte가 유지되는지 검사했다. 빈 디렉터리·완성된 immutable 자산이 orphan으로 남을 수는 있으나 참조되지 않은 자산 때문에 과거 manifest가 손상되지는 않는다.

## Revision Conflict

현재 path의 saved revision을 expected_revision으로 전달한다. 외부 writer가 바꾸면 conflict error로 멈추고 dirty/current memory를 유지한다. 사용자에게 재로드 또는 새 경로 SaveAs를 안내한다. 다른 project_id overwrite와 원본/기존 연구 이력 rewrite도 authoritative storage가 거부한다.

SaveAs는 **동일 프로젝트 복사본**이다. project/source/run/observation/geometry UUID와 revision을 임의 변경하지 않으며 기존 목적지를 덮어쓰지 않는다. 두 복사본을 별개 프로젝트/자동 merge 가능한 fork로 설명하지 않는다.

## Experiment Geometry/Mask Persistence

TD-02의 검증된 원래 bundle을 immutable dependency로 보관하는 전략 B를 적용했다. `experiment.json`, 원래 `project.json`, PNG mask/skeleton/comparison 등 추적 자산을 `assets/<project_uuid 앞 12자>/<bundle SHA 앞 16자>/`에 저장한다. 전체 SHA와 실제 TD-02 loader로 매번 무결성을 확인해 짧은 경로 이름 충돌을 신뢰하지 않는다. 원본 JPG/TIFF pixels는 복사하지 않는다.

임시 dependency 디렉터리에서 파일별 exclusive write/fsync·bundle 검증 후 rename하고 최종 경로에서 다시 검증한 뒤 manifest를 저장한다. Windows 긴 경로 문제 때문에 full UUID/SHA를 파일 경로에 모두 붙이지 않는다. SaveAs에는 같은 relative assets 경로를 준비한다. PNG가 없으면 metadata only, 변조/hash mismatch/unsafe path는 load를 거부하고 기존 프로젝트를 유지한다. symlink/path escape는 허용하지 않는다.

`import_experiment` adapter는 foreign project UUID를 대상 namespace에 명시 remap하고 Source/Run/Observation/Prediction/Geometry/Instance/Review/Relationship 참조를 일관되게 갱신한다. 같은 원래 Run은 exact snapshot 일치 시만 reuse한다. POLYLINE/BRANCHED_GRAPH의 local node/edge와 수치, ObservationLinks, evidence, quality_flags, confidence_meaning, LabelAssessment, mask refs를 보존한다. 반복 import는 동일 descriptor ID로 중복되지 않는다. Transform asset import는 아직 거부한다.

추가 EXPERIMENT_IMPORT provenance에 original_project_id와 ID mapping, full bundle SHA/reference/validation status를 보관한다. bundle digest를 모델 hash로 위장하지 않는다. 현재 페이지/Source compatible evidence만 기존 TD-03 renderer에 전달한다. 저장된 geometry 선택도 local view restore 후 복원한다. 실제 실험 구조 **34개(Polyline 11 + Graph 23)**는 실험 제안이며 연구원 정답/실제 정확도 검증 자료가 아니다.

## 기존 Export 호환성

Live Export API/CSV/JSON을 유지한다. 이번 UI에서 캡처한 Saved 결과의 original request/summary map key 순서는 Source acquisition metadata의 `workspace_export_order`에 구조만 보존한다. pixels·score 값을 복제하지 않고 Schema 1.0.0의 extension mapping을 사용한다. 이를 이용해 newly captured result의 JSON/CSV bytes를 원래 Live Export와 **동일하게** 재생한다.

이전 TD-01 manifest에는 원래 map 삽입 순서가 저장되지 않았으므로, 그 순서가 없는 오래된 결과의 값은 유지하지만 과거 Export의 byte order를 복구한다고 주장하지 않는다. schema version/좌표계/score 의미/ONNX 결과 계약 변경 없음.

## 실제 JPG 회귀

승인된 모델과 `After annealing_1.jpg`(12349×12273 RGB8)에서 다음을 확인했다.

| 범위 | 후보 | BPD | TED | TSD |
|---|---:|---:|---:|---:|
| Full | 2,946 | 245 | 1,398 | 1,303 |
| ROI (1003,1011,1495,1495) | 791 | 3 | 779 | 9 |

Live capture → 프로젝트 저장 → 자산 import → SaveAs → engine 재시작 → Source/Run 선택 → Saved candidate Crop/Overlay → 3개 화면 크기별 Export에서 ID/원본 좌표/raw scores/class/low flag와 기존 Export bytes 일치다. 새 OS 프로세스에서도 모델 adapter 없이 4 Run을 확인했다.

TD-03 기준과 source candidate ID/Geometry payload/원점수/model/source/summary를 대조해 동일했다. 새 프로젝트 namespace의 domain UUID는 별개이며 자기 save/reopen에서는 그대로 유지된다. 이전 QA는 `point_mode=contrast_proposals`를 명시했고 이번 QA는 같은 자동 default를 사용했다. request 인수 JSON은 그 차이를 정직하게 보존하며 각 Run 자체의 저장/Export roundtrip은 정확히 동일하다.

JPG SHA256 `c864ce2410e940ee0e5c11faf4bec2f38fa66cf1f8d5ecc4cc15bfa5b60f1c47`, 승인 weights SHA256 `24368b8f6613cba5251c0bd8e63d7ddec726d6343a35ed878e823a0091369694`. 도구 실행 전/후 원본·weights·manifest SHA 유지다.

## TIFF 4개 검증

| 실제 파일 | 해상도 | 페이지 | dtype | 새 모델 실행 |
|---|---|---:|---|---:|
| N119_220_Section_stack_flipped.tif | 3072×3012 | 158 | uint16 | 0 |
| No107_SectionTopo-afterAnnealing .tif | 2922×2895 | 156 | uint16 | 0 |
| No107_SectionTopo-beforeAnnealing.tif | 2922×2895 | 156 | uint16 | 0 |
| No22_220_Section_stack_flipped.tif | 2944×2745 | 156 | uint16 | 0 |

실제 file open/기존 stack 준비, project source 등록, page_count/header, UNKNOWN 공간축, TIFF의 분석·새 BPD 실험 UI 차단을 검사했다. QA 전후 네 원본 전체 SHA 유지. 이번 TD는 기존 TIFF 페이지/ROI/ImageJ 경로를 변경하지 않았으며 전체 회귀로 유지 여부를 확인한다. 기존 스택 데이터를 물리 공간 3D로 재구성했다고 주장하지 않는다.

## Native Dialog 검증

Windows/Python 3.13.7/PySide6·Qt **6.11.2**, 기본 QQuickStyle, basic render loop, D3D11, scale 1에서 검사했다.

- project Open/Save/Relink 각각 **10회**, 총 **30회** 실제 Native HWND를 관찰한 후 GUI queued Signal로 reject. production NativeFileDialogs 경로 사용; Native 안정화 코드 미변경.
- 정상 accepted payload를 주입한 서로 다른 프로젝트 전환 **20회**. Qt actual Action/Save button, new/Save/SaveAs/최근/dirty cancel/window close/app shutdown 경로 확인. payload injection을 물리적 Explorer 파일 클릭으로 설명하지 않는다.
- 새로운 프로젝트 Native 도구 최초 timer 취소는 HWND를 보기 전에 실행돼 검사 실패. 두 번째 polling QTimer 방식은 Windows native modal의 timer 제약으로 도구가 정체돼 해당 도구 프로세스만 종료했다. 기존 진단 도구처럼 read-only HWND 관찰 worker + GUI queued reject로 바꾼 최종 30회는 PASS. 제품 Native 코드는 변경하지 않았다.
- 기존 AWT/Swing/Fiji native 4개 × 3회: **11 PASS / 1 FAIL**. 첫 회 ImageJ host parent 이동 geometry가 100ms 후 30→50으로 갱신되지 않은 기존 간헐 실패; 이후 2회는 각각 4 PASS. 첫 로그와 실패 빈도 **1/12**를 보존한다. 원인 미확정이며 해결됐다고 주장하지 않는다.
- 다른 GUI 검증 창을 닫은 최종 반복 4개 × 3회: **12 PASS / 0 FAIL**, 22.25 / 22.72 / 21.83s. 전체 관측은 **23 PASS / 1 FAIL (1/24)**이며 최초 실패를 지우거나 재실행을 원인 해결로 해석하지 않았다.
- 물리적 마우스 Native acceptance: **MANUAL PENDING**. 자동 GUI 통과와 구분한다.

## UI Screenshots

모든 공개 화면은 합성 RGB/스택/기하만 사용한다. 실제 연구 화면은 ignored artifacts에 있다.

- [새 프로젝트](../screenshots/project-td04/new-project.png), [열기 메뉴](../screenshots/project-td04/project-opening-menu.png), [최근 프로젝트](../screenshots/project-td04/recent-projects.png)
- [저장](../screenshots/project-td04/save-dialog.png), [SaveAs](../screenshots/project-td04/save-as.png), [미저장 보호](../screenshots/project-td04/dirty-confirmation.png)
- [다중 이미지와 Run](../screenshots/project-td04/image-run-list.png), [Saved 후보](../screenshots/project-td04/saved-candidate.png)
- [원본 누락](../screenshots/project-td04/missing-original.png), [TIFF 프로젝트](../screenshots/project-td04/tiff-project.png), [load 오류](../screenshots/project-td04/load-error.png)
- [1100×700 workspace](../screenshots/project-td04/1100-workspace.png), [1440×900 workspace](../screenshots/project-td04/1440-workspace.png), [1920×1080 workspace](../screenshots/project-td04/1920-workspace.png)
- [1100 Saved](../screenshots/project-td04/1100-saved-FULL_IMAGE.png), [1440 Saved](../screenshots/project-td04/1440-saved-FULL_IMAGE.png), [1920 Saved](../screenshots/project-td04/1920-saved-FULL_IMAGE.png)

3개 크기의 프로젝트 작업창과 Saved 후보 Crop/Overlay가 화면 안에 표시되는지 자동 GUI와 렌더 후 좌표 click으로 확인했다. 최종 합성 GUI와 실제 GUI의 QML 경고는 0개다. 실제 native Explorer 창은 Qt Quick screenshot에 포함되지 않으므로 HWND 증거와 공개 열기 메뉴 화면을 구분한다.

## Windows Full Tests

- 신규 프로젝트 **26개 PASS** (최초 전체의 실패 5개는 모두 기존 검사). 계약 묶음 검사 **75 PASS / 1 SKIP**, SHA/취소 focus **3 PASS**.
- 최초 전체: **506 PASS / 5 FAIL / 5 SKIP**, 1046.11s. Source 존재 판정의 Live regression 3개, 병렬 real GUI/전체 검사 중 발생한 기존 준비 timeout 2개였다. 후자는 isolation에서 2 PASS이며 제품 원인이 확정됐다고 주장하지 않는다.
- Live Source guard는 기존 pipeline.source 계약으로 복원했다. 기존 direct pipeline API export/candidate/feedback 검사를 되살리고 Saved provider의 SHA 검증은 유지했다. 수정 focus **2 PASS**, 0.87s.
- Windows 최종 전체: **511 PASS / 0 FAIL / 5 SKIP**, **553.43s**, code/test HEAD `dcb3219bcdd37aa90367cf7f0322f6a47db12340`. 다른 실제 GUI 부하 검사를 마친 후 실행했다. 기존 485개와 신규 26개가 통과했다.
- ruff/compileall/import/wheel: PASS. Qt/plugin 검사 삭제·새 skip·assertion 약화 없음.

## Linux CI

최종 code/test HEAD CI [38186563204](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/38186563204) 성공. Ubuntu/Python 3.11/Java21/Qt6.11.2, **512 PASS / 4 SKIP (464.73s)**, **X11 native plugin 4 PASS (25.49s)**, ruff/import/compile/wheel/PR policy PASS. 최종 문서 커밋 CI도 PR에 기록한다.

## 남은 기술적 한계

- 기존 Windows native AWT parent 이동 간헐 실패 원인 미확정 및 물리적 마우스 acceptance PENDING.
- 모델 없이 Saved 결과를 볼 수 있지만 verified source가 없으면 crop/overlay/새 분석은 사용할 수 없다. 기존 hash 없는 누락 원본을 안전하게 relink할 수는 없다.
- `.json`과 dependency `assets/`는 함께 옮겨야 한다. 외부 원본은 별도 보관하며 이 앱이 복사/업로드하지 않는다.
- 대량 project manifest 제한 64 MiB, JSON 기반 전체 serialization/revision 단위다. 수백만 후보용 DB·페이지별 저장은 이번 범위가 아니다.
- Asset missing은 metadata-only; content corruption은 load fail. 임시 준비 중 실패하면 참조되지 않은 완성 자산이 남을 수 있고 자동 garbage collection은 하지 않는다.
- SaveAs는 동일 UUID copy, 동시 분기 merge·server sync를 제공하지 않는다. 여러 복사본은 마지막 로컬 view settings를 공유한다.
- 기존 Feedback와 domain ReviewEvent는 별개 계약이다. 이번 단계에서 새 Saved review editor/ground truth adjudication/전후 정합/WaferMap/3D 분석을 추가하지 않았다.
- 과거 manifest의 original Export key order가 없으면 byte order는 복구 불가; scientific 값은 보존한다.

## 후속 TD

Windows native 호스팅 간헐 실패의 별도 재현·계측과 물리적 Native acceptance, Saved ReviewEvent 편집·검수 흐름을 별도로 진행할 수 있다. 서버 확장은 유지한 project/source/run UUID, provenance, append-only ReviewEvent/revision과 명시 자산 SHA를 소비하도록 구성해야 한다. 현재 server upload·계정·API·training은 구현하지 않았다.

## 실행·검증 명령

```powershell
cd D:\capstone\sic-xrt-analyzer
.\.venv\Scripts\python.exe -m sic_xrt_analyzer
$env:TEMP='D:\Temp\PC-1'; $env:TMP=$env:TEMP
$env:QT_QPA_PLATFORM='offscreen'; $env:QSG_RENDER_LOOP='basic'
.\.venv\Scripts\python.exe -m pytest -q
$env:QT_QPA_PLATFORM='windows'
.\.venv\Scripts\python.exe tools/validate_project_workspace.py --synthetic --output artifacts/project-new-qa
.\.venv\Scripts\python.exe tools/validate_workspace_routes.py --cycles 10 --output artifacts/project-routes-new-qa
.\.venv\Scripts\python.exe tools/validate_workspace_routes.py --project <saved-workspace.json> --output artifacts/project-replay-new-qa
```

Actual QA는 `--image <JPG> --model <approved bundle> --experiment <TD02 bundle> --tiff <TIFF>`(반복 가능)와 새 output을 명시한다. 생성 fixture와 private 결과의 경로는 기존 파일을 덮어쓰지 않는다.

## Private evidence (Git에 넣지 않음)

| 경로 | 내용 |
|---|---|
| `artifacts/project102-real-native/report.json` | 실제 Full/ROI, TIFF4, engine restart, Export bytes, 원본/model SHA |
| `artifacts/project102-real-process-replay/report.json` | 독립 새 OS process, model adapter 없음, Run4, manifest SHA |
| `artifacts/project102-prior-contract.json` | TD-03 기준 scientific 필드 동등성 및 request 인수 차이 |
| `artifacts/project102-routes-native-v4/report.json`, `native-observations.json` | native30/프로젝트 switch20, 누락/relink/dirty/오류 |
| `artifacts/project102-final-synthetic/report.json`, `project102-final-routes/report.json` | 최종 UI 합성 검사, 3개 크기, warning0 |
| `artifacts/project102-full-windows.log`, `project102-failure-isolation.log` | 최초 전체 실패·isolation 보존 |
| `artifacts/project102-final-windows.log` | 최종 전체 회귀 |
| `artifacts/project102-native-plugin-{1,2,3}.log`, `project102-native-isolated-{1,2,3}.log` | 기존 Native 24 검사, 최초 1 FAIL·최종 12 PASS |
| `artifacts/project102-wheel.log` | 최종 wheel 빌드 |
