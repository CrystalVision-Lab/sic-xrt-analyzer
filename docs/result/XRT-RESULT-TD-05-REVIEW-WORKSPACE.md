# XRT-RESULT-TD-05 — Researcher Review Workspace & Manual Geometry Editing

## Status

**PARTIAL — 기능 구현과 자동 검증 PASS, 실물 Native Dialog·물리적 마우스 Acceptance PENDING.** 검수 기록·수동 보정·저장·재실행 복원을 구현했다. Windows Qt 이벤트 및 실제 데이터의 자동 검증을 수동 Acceptance로 주장하지 않는다. 실제 JPG 검증은 승인된 기존 Full/ROI Run의 복원·검수 회귀이며 이 TD에서 새 ONNX 추론이나 정확도 평가를 수행하지 않았다.

## Git / 저장소 경계

- 시작: `feat/102-project-workspace` / `15444dd7709bdc57972010f9633c14854e986dc4`
- Issue [#104](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/104)
- 작업: `feat/104-researcher-review-workspace`
- Draft [#105](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/105), base `feat/102-project-workspace` (#103)
- 검증된 기능 HEAD: `60183de8334b7091ef7dac343617d7fa06e5810b`; 이후 연결 후보 읽기 전용 표시와 최종 문서 커밋을 추가한다. 최종 전체 SHA는 [Draft PR #105의 마지막 커밋](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/105/commits) 및 PR 본문에 기록한다.
- 선행 stacked PR merge/rebase/retarget 없음.
- 사용자 AGENTS.md의 기존 공백 변경 보존·미스테이징. sources/·원본·모델·다른 저장소·Native Dialog 안정화 코드 미변경. 실제 원본 캡처·private artifacts는 Git에 게시하지 않음.

## Review Contract / 의미 / 마이그레이션

기존 ReviewStatus 하나로 존재·종류·Geometry 판정을 모두 표현할 수 없으므로 ReviewEvent에 typed `existence`, `class_decision`, `geometry_decision`을 추가했다. `1.1.0`에서만 새 판정을 저장하며 첫 신규 검수 명령에서 명시적으로 upgrade한다. 기존 `1.0.0` envelope/project 버전은 유지해 읽고 쓰고, read migration은 세 필드를 NOT_REVIEWED로만 확장한다. Legacy CONFIRMED/REJECTED/CORRECTED의 독립 의미를 추측하지 않는다. 구버전 JSON에 새 필드를 넣거나, envelope/project 버전이 다르거나, 판정이 있는 프로젝트를 강제로 1.0.0으로 내려 저장하면 거부한다. 1.1.0 manifest는 구버전 프로그램에서 읽을 수 없다.

- 존재: PRESENT / ABSENT / UNCERTAIN / NOT_REVIEWED
- 종류: BPD / TED / TSD / UNKNOWN / NOT_REVIEWED
- 영역: ACCEPTED / CORRECTED / UNCERTAIN / NOT_REVIEWED
- 기존 ReviewStatus enum 및 append-only ReviewRepository 유지.
- 개인 검수는 LabelAssessment의 adjudication/ground_truth_eligible을 변경하지 않는다. 학습·정확도·확정 정답·인증된 신원·서버 동기화 주장이 없다.

## Reviewer / Review History / Conflict

별도 QSettings `projectReviewer`에 제어문자 없는 1–120자 로컬 ID를 저장한다. 인증 계정이 아니며 새 이벤트에만 적용된다. 작성 중 Reviewer 변경은 막는다. 이벤트는 review UUID, Target Type/ID, Reviewer, 원본 prediction snapshot, 생성 UTC, revision, 같은 Reviewer/Target의 parent IDs, 원본 Run, 보정 Class/Geometry 참조를 보존한다. 같은 UUID·같은 이벤트는 idempotent, 다른 내용은 거부한다. Reviewer별 tips가 다르거나 fork가 있으면 NEEDS_REVIEW/충돌이며 마지막 기록으로 해결하지 않는다. 관리자 합의·승인은 제공하지 않는다.

## Review UI / Candidate / Instance / Live-Saved

Result Viewer 안에서 탐색 → 검수 → 영역 편집을 구분한다. 모델 원본 Class/score/raw scores와 사람 판정을 별도로 보여준다. 원본 Crop, 연구원, 존재/종류/영역, 메모, 기록/다음, 디스크 저장/다음, 상태 필터, 이력, 비교를 제공한다. 결과 목록에는 핵심 badge 하나를 추가했다. 목록은 현재 Source/Run을 기준으로 탐색하며 다른 이력은 기존 프로젝트 Run 선택으로 전환한다. 최초 100행을 표시하고 다음/이전으로 나머지 대상으로 계속 이동한다. 목록은 가상화한다.

Live는 완료된 실제 분석을 TD04가 캡처한 프로젝트 Run에 연결한다. Saved는 기존 읽기 전용 ResultPresentation의 Project/Run/Observation UUID를 연결하고 검수만 프로젝트에 추가한다. 신규 추론과 모델 예측 수정은 하지 않는다. 실험 Instance는 명시적으로 가져온 namespace mapping을 사용한다. 수동 Instance의 모델 점수는 없다. Instance에 연결된 원본 Observation의 Candidate ID·원본 Class를 보여주며, 연결이 없는 수동 결함은 없음으로 표시한다. 연결을 동일 결함 확정으로 취급하지 않는다.

## Geometry Editor / Polyline / Polygon / Branched Graph / Y

편집은 GeometryDraft 사본에서만 수행한다. 기존 Geometry·Prediction·Review·이미지는 편집 중 불변이다. 제어점 선택/이동/삽입/삭제, Undo(최대 100 작업), 초안 복원, 취소, 검증 후 새 HUMAN Geometry 생성을 지원한다. Ctrl+Z는 뷰어의 Geometry 편집 모드에서 초안에만 작동한다. 텍스트 입력 시 전역 R/H Viewer 단축키를 해제해 메모·연구원 입력과 충돌하지 않는다.

- Point: 원본 pixel 좌표의 단일점.
- Polyline: 원래 endpoints/중간 vertices 유지, 선택점 다음 삽입·삭제·이동.
- Polygon: 3개 이상 distinct vertices, nonzero area, bounds 검사. 자기 교차/중복/접촉하는 비인접 Edge를 거부하며 holes·복잡한 polygon repair를 지원하지 않는다.
- Graph: 기존 Node/Edge opaque IDs·연결 보존, Node 이동 시 incident Edge path endpoints 동시 갱신. Node 추가 시 선택 Node(없으면 마지막 Node)로 새 Edge 연결. 두 Node 연결, Edge 삭제, Edge path 중간 제어점 추가/이동/삭제. 저장 시 연결·참조·endpoint 검증으로 dangling/disconnected/duplicate/self Edge를 거부한다. 삭제로 연결이 끊어지면 Undo 또는 연결 복구가 필요하다.
- 원본 Mask asset은 readonly. 새 Polygon 경계를 작성할 수 있으며 brush segmentation은 제공하지 않는다. 원본 Mask 표시에는 기존 실험 renderer를 사용하고 새 비교 layer는 Mask bbox를 표시한다.
- 비교: 원본 청색 점선/◇, 보정 황색 실선/○, 초안 분홍 실선/□와 legend. 색상만으로 구분하지 않는다. 충돌하는 보정은 모두 표시한다.

## Manual Defect / Original Prediction / Geometry Revision

누락 추가는 새 HUMAN Geometry + `instance_status=HUMAN` DefectInstance + 개인 ReviewEvent다. linked_observations=[]이고 가짜 Observation/Prediction/model score를 만들지 않는다. 새 검수에서 보정 Geometry UUID를 참조하며 원본 도형을 덮어쓰지 않는다. 이미 보정된 개인 검수를 다시 기록하면 새 Geometry revision copy를 남긴다. 모호한 관련 후보를 자동 merge/split/delete하지 않는다.

## Project Persistence / Source Missing / TIFF

검수 기록은 메모리에 추가해 dirty를 표시한다. ProjectStore의 atomic temp/fsync/publish·OS writer lock·expected revision·이력 보존을 재사용한다. 실패하면 메모리/dirty/오류/현재 대상을 유지한다. ‘디스크 저장 → 다음’은 성공 후에만 이동한다. 작성 중 초안은 기록·취소하기 전 디스크 저장, 파일·프로젝트·Source/Run·Live 전환, 분석 실행, 앱 종료를 가드한다. 기존 ROI discard도 이어서 처리한다.

JPG 원본의 Source/Run/page/파일 identity 및 이 세션의 SHA verification이 일치해야 새 시각 검수·편집을 허용한다. 누락/미검증 원본은 metadata와 과거 이력만 보여준다. 다른 Source/Run에 기록하지 않는다. TIFF의 stack/ImageJ·원본 bit depth·page/frame 의미는 그대로이며 새 JPG 검수/편집과 ONNX 실행 대상이 아니다. 3D geometry 편집은 제외한다.

## 검증 / Windows GUI / Actual XRT / Screens / CI

측정 환경: Windows, Python 3.13.7, PySide6/Qt 6.11.2. 전체 회귀는 offscreen/basic, Windows GUI·플러그인 검사는 windows/D3D11/basic로 분리했다. TEMP/TMP·로그·QA 출력은 D 드라이브를 사용했다. 아래 시간은 검사 실행 시간이며 Pan/Zoom 성능 개선 측정이 아니다.

| 검사 | 결과 | 로컬 근거 |
| --- | --- | --- |
| Windows 전체 회귀, 코드 60183de | 552 PASS / 기존 5 SKIP, 689.50초 | `artifacts/review104-final-windows.log` |
| 신규 검수 검사 | 41개 포함; 위 전체 회귀에서 PASS | `tests/test_review_workspace.py` |
| 실제 QML 1100×700 / 1440×900 / 1920×1080 | 클릭·판정·메모 입력·기록·저장 PASS | 실제 데이터 report와 신규 GUI tests |
| Fit / 100% / 400%, 좌표 변환 | 제어점 이동·Undo·취소·ROI/Pan 분리 PASS | `test_viewer_geometry_drag_original_coords_undo_cancel_and_roi_isolation` |
| Windows Qt Scale 1.25 | 7 PASS / 34 deselected, 36.37초 | `artifacts/review104-native-dpi125.log` |
| Windows Qt Scale 1.5 | 7 PASS / 34 deselected, 34.97초 | `artifacts/review104-native-dpi150.log` |
| Windows AWT/Swing 최초 실행 | 4 PASS / 5 deselected, 23.48초 | `artifacts/review104-native-plugin-1.log` |
| Windows AWT/Swing 재실행 2 | 4 PASS / 5 deselected, 22.31초 | `artifacts/review104-native-plugin-2.log` |
| Windows AWT/Swing 재실행 3 | 4 PASS / 5 deselected, 23.59초 | `artifacts/review104-native-plugin-3.log` |
| 새 OS 프로세스 프로젝트 재열기 | 이벤트 8 / HUMAN Geometry 3 / 수동 Instance 1 / 충돌 복원 PASS | `artifacts/review104-fresh-replay/report.json` |
| Ruff / compileall / wheel | PASS, 최종 소스 재검사 로그 보관 | `artifacts/review104-final-build.log` |

Qt Scale은 해당 프로세스의 `QT_SCALE_FACTOR` 설정이다. 실제 모니터 DPI·물리적 입력을 바꾼 수동 검사를 의미하지 않는다. 연결 후보 표시 추가 이후 최종 전체 검사는 `artifacts/review104-final-all.log`에서 확인하며 마지막 결과를 PR 본문에 기록한다. 새 테스트 삭제·무조건 skip은 없다. final code 검사 후 문서만 바뀌면 동일 소스 검사 결과를 적용한다.

### 실제 JPG / Geometry / 원본 무결성

`artifacts/review104-real-native-v4/report.json`에서 **PASS**. 코드 893298c에서 원본 QA를 진행했고 후속 60183de에서는 동일 도메인·편집 구현과 수정된 목록·초안 가드를 전체 회귀 및 새 OS 프로세스에서 검증했다.

- `After annealing_1.jpg`: 12349×12273 RGB8. 기존 저장 프로젝트의 Full 2개 / ROI 2개 Run을 복원했다. 각 Full은 **2946 = BPD 245 / TED 1398 / TSD 1303**, 각 ROI는 **791 = 3 / 779 / 9**를 유지했다.
- 실제 BPD 후보의 원본 Class·점수는 유지하고 개인 TED 판정·메모를 기록했다. 다른 연구원의 BPD 판정으로 충돌을 생성했다.
- TD-02 실제 Polyline 및 분기점 degree=3인 Graph를 400% 화면의 실제 QML MouseArea에서 이동했다. Junction의 incident Edge endpoints·Node/Edge IDs를 보존하고 새 HUMAN Geometry를 저장했다. Edge path 제어점도 추가했다.
- 수동 Polyline Instance를 추가해 linked_observations=[]와 가짜 모델 Prediction 없음, 저장·재열기 동등성을 확인했다.
- 원본 Observation/Candidate ID·좌표·Prediction·raw score·Run·모델 provenance·자동 Geometry 및 기존 JSON/CSV Export bytes는 전후 동일했다.
- QA v2의 시작 SHA snapshot을 재사용했고 v4 종료 시 JPG·TIFF 4개·ONNX·manifest·입력 프로젝트를 모두 다시 읽어 SHA를 대조했다. **원본 해시 일치**, 새 추론 **0회**, QML 경고 **0개**.
- 실제 TIFF N119(158p), No107 after(156p), No107 before(156p), No22(156p)는 준비·Stack/ImageJ 표시를 유지하고 신규 검수·영역 편집을 차단했다. TIFF ONNX 실행 **0회**. frames를 공간 Z로 해석하지 않는다.
- 새 OS 프로세스 검사는 v4의 검수 프로젝트를 다시 열어 검수 8개·HUMAN 도형 3개·수동 객체 1개·충돌을 복원했다. manifest SHA 일치, QML 경고 0개다.

### GUI Screenshots / private artifacts

실제 QML 입력과 함께 `artifacts/review104-real-native-v4/session/{1100,1440,1920}-review.png`를 생성했고 1100 화면을 직접 확인했다. 작은 화면의 하단 기록·이력은 세로 스크롤로 접근한다. 연구 원본이 포함된 캡처·Crop·프로젝트·모델은 로컬에만 보관하고 Git에 올리지 않았다. 재현 도구는 `tools/validate_review_workspace.py`이며 정적 캡처만으로 PASS 처리하지 않았다.

### 개발 중 최초 실패 / 수정 / 재시험

초기 전체 UI fixture에서 empty GeometryDraft의 state 접근 오류가 발생해 실행을 중단하고 수정했다. `review104-initial-project.log`에 최초 1 ERROR를 보관했다. 이후 JPEG fixture에 TIFF 전용 원본 reader를 쓴 검사 오류, 실제 QML 기록 버튼의 viewport 좌표 오류, 개발 중 프로세스와 새 QML badge 버전 불일치를 각각 수정하고 새 프로세스에서 재검사했다. `review104-new-v2.log`는 23 PASS/1 FAIL, v4 로그는 32 PASS/1 FAIL/1 ERROR였다. 최종 전체 회귀는 위 표의 PASS다.

실제 데이터 도구의 initial/v1/v2/v3 실행은 helper import, QML Repeater 탐색, QWindow keyboard API 및 합성 문자 대소문자 가정 때문에 실패했다. 이를 수정하는 과정에서 **실제 R/H 전역 단축키가 검수 메모를 가로채는 결함**을 확인해 텍스트 입력 중 Viewer shortcut을 비활성화하고 QTest 문자 입력 회귀를 추가했다. 성공 결과는 v4다. 실패 로그를 삭제하거나 첫 실패를 PASS로 덮어쓰지 않았다.

이 TD의 Windows Native Plugin 첫 실행부터 3회 모두 PASS였다. 선행 TD04의 AWT 간헐 실패(첫 23/24 PASS, parent host 위치 타이밍 실패)는 선행 보고서에 남아 있으며 이 TD의 재실행 결과로 과거 실패를 지우지 않는다.

### CI

- 최초 기능 코드 893298c: [CI 38190675460](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/38190675460) PASS. Linux 전체 553 PASS/4 SKIP; X11 실제 플러그인 4 PASS/5 deselected.
- 코드 60183de: [CI 38191934699](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/38191934699) PASS. Linux 전체 **553 PASS / 4 SKIP**, 595.78초; X11 **4 PASS / 5 deselected**, 25.15초. Ruff·compile·wheel·PR 정책 모두 PASS.
- 최종 커밋 CI는 [Draft #105 Checks](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/105/checks) 및 PR 본문의 commit SHA·run 링크로 확인한다. 선행 커밋 CI를 최종 HEAD의 CI로 대체하지 않는다.


## Legacy Feedback Compatibility

기존 FeedbackPanel/FeedbackController/analysis.feedback/DatasetReview의 confirm/background/type/defer/move/add/duplicate/undo/import/export 계약과 세션 파일을 보존한다. 새 프로젝트 검수는 AnalysisProject.review_events가 권위 있는 저장소이고 Legacy JSON에 기록하지 않는다. Source/Run/Candidate와 독립 판단 의미의 일대일 mapping이 보장되지 않아 자동 이전하지 않는다. 기존 Legacy 검수의 wafer 1–9 허용·평가 데이터 제한을 유지하고, 프로젝트 개인 검수는 학습 데이터 승인/분할 API를 호출하지 않으므로 해당 규칙을 우회한 자동 학습 Export를 만들지 않는다. Legacy 출처·이벤트 수를 구분한다.

## 로컬 저장 위치 / 접근 정책

프로젝트 JSON·assets는 사용자가 선택한 경로에 저장한다. 이벤트의 Reviewer ID·메모는 해당 JSON의 로컬 연구 데이터이며 파일을 읽을 권한이 있는 OS 사용자에게 보인다. 로컬 ID 설정은 `QSettings("CrystalVision-Lab", "sic-xrt-analyzer")`의 `projectReviewer`에 저장한다. 인증·암호화·사용자별 권한 관리 기능은 추가하지 않았다. Legacy 세션은 기존 저장 위치를 그대로 사용한다. 검수 코드에 서버 업로드·네트워크 전송·학습 호출을 추가하지 않았다. 백업·공유 시 프로젝트의 ID/메모와 assets도 포함됨을 고려해야 한다.

## 실행 방법

```powershell
Set-Location D:\capstone\sic-xrt-analyzer
.\.venv\Scripts\python.exe -m sic_xrt_analyzer
```

JPG → 분석 완료 또는 프로젝트 Run → 후보/구조 선택 → 프로젝트 검수 → 로컬 ID 및 SHA 검증 → 독립 판정/영역 보정 → 검수 기록 → 프로젝트 디스크 저장. 프로젝트 JSON과 assets를 함께 보관하고 원본 JPG/TIFF는 별도로 유지한다.

검증 도구는 명시적 --project/--output 및 필요 시 --model/--tiff를 받는다. 원본 읽기 전용, QA 출력은 새 폴더다. --hash-baseline은 이전 QA의 시작 SHA 기록을 재사용하는 옵션이며 마지막 SHA 읽기·대조는 생략하지 않는다.

## Remaining Limitations / Next Step

로컬 ID 인증 없음, 서버·학습·자동 GT·adjudication 없음. mask brush/복잡한 merge/split/holes/3D editor 없음. 목록은 현재 Source/Run 범위이며 전역 검수 큐와 관리자 합의는 후속 단계다. 새 수동 인스턴스의 모델 점수·자동 Observation 연결을 만들지 않는다. 물리적 Windows Native mouse acceptance는 계속 PENDING. 최초 실패와 재실행 근거는 위 검증 절에 기록했다. 신규 검수 목록은 상태 기준이며 기존 탐색기의 모델 Class 필터와 연구원 판정을 혼동하지 않는다. 전역 Source/Run 큐·연구원 Class별 필터·관리자 충돌 합의와 물리적 마우스 검증은 다음 검수 UX 단계에서 다룬다.
