# XRT-RESULT-TD-01 Result

### Status

**PASS** — 로컬 계약·실제 RGB·전체 회귀·Windows Native 검사를 통과했다. 최종 GitHub CI 결과와 실행 URL은 연결된 Draft PR의 테스트 항목을 함께 확인한다.

### 작업 기준

- Start Branch: `feat/94-viewer-loading-ux`
- Start HEAD: `243155a3dbf58d015eaf08cca2202bd2b7b9dab9` (Draft PR #95)
- Work Branch: `feat/96-result-domain-foundation`
- Final HEAD: 이 보고서를 포함한 Draft PR의 최종 커밋. 전체 SHA는 PR의 Git 항목에 기록한다.
- 환경: D:/capstone/sic-xrt-analyzer. 기존 stacked PR은 merge/rebase/retarget하지 않았다.

### 기존 분석 데이터 구조

원본 → 국소 대비 후보/제공 좌표 → 128×128 RGB Patch → Frozen ONNX → AnalysisResult → Result UI/JSON/CSV. 원본 좌표·파라미터·Detection metadata에 원본 점수를 보존한다. 기존 Geometry는 POINT/BOUNDING_BOX/POLYGON/MASK이다. ROI는 분석 범위이며 실측 결함 형상은 아니다.

### 기존 구조의 한계

후보 수는 실제 결함 수가 아니며 모델은 패치 분류기다. BPD 선·Y 분기·배경 판정·분할 경계를 얻을 수 없다. 같은 결함에 여러 후보가 생길 수 있다. 점수는 보정된 정답 확률이 아니다.

### 새로운 Domain Model

AnalysisProject / ImageSourceRecord / AnalysisRunRecord / CandidateObservation / ModelPrediction / ModelProvenance / DefectInstance / DefectGeometry / ReviewEvent / ImageRelationship을 frozen dataclass로 구현했다. 기존 계약은 변경하지 않았다. [설계·API 문서](XRT-RESULT-TD-01-DOMAIN.md)에 상세 관계를 기록했다.

### Project Structure

한 versioned project.json에 메타데이터를 저장한다. 원본 이미지·model.onnx·Mask를 복사하지 않는다. 여러 Source·Run·Observation·Prediction·명시적 Instance·Geometry·Review·Relationship을 담는다. UUID4/namespace UUID5와 revision을 사용한다.

### CandidateObservation

원본 candidate/point ID, 좌표, page, class/class_id, raw_scores, displayed_score, low_score, proposal_method와 모든 metadata를 보존한다. 읽기 전용 Adapter는 같은 Run ID/내용의 재입력에 멱등적이며, 같은 ID로 내용이 바뀌면 거부한다.

### DefectInstance

명시적으로 생성하는 독립 객체다. 한 객체에 여러 Observation을 연결할 수 있고 모호한 후보는 여러 객체에 AMBIGUOUS로 연결할 수 있다. Adapter는 후보를 결함으로 변환하지 않는다. 실제 데이터 검증에서 3,737 Observation에 대해 Instance는 **0개**다.

### Geometry Types

| Geometry | 지원 여부 | 데이터 형태 | 비고 |
|---|---|---|---|
| POINT | 지원 | x,y | 원본 좌표 |
| BOUNDING_BOX | 지원 | x,y,w,h | 기존 Geometry 검증 재사용 |
| POLYLINE | 지원 | ordered points | 선·곡선 근사 |
| POLYGON | 지원 | ordered vertices | 0 아닌 면적·좌표 범위 |
| MASK_REFERENCE | 참조 지원 | bbox/path/encoding | 경로 검증, mask binary는 읽지 않음 |
| BRANCHED_GRAPH | 지원 | nodes/edges/path | 연결·참조·원본 범위 검증 |

### BPD 선형/Y자형 지원 구조

Polyline과 branched graph로 형상을 기록·저장할 수 있다. Y는 중심 node·세 끝점·세 edge로 표현한다. 합성 계약 예시와 roundtrip을 검증했다. 실제 이미지에서 Y자형 BPD를 자동 검출했다는 의미는 아니다.

### Prediction과 Review 분리

ModelPrediction과 original_prediction snapshot을 보존하며 수정 분류·형상은 Review의 별도 필드다. LabelAssessment와 ground_truth_eligible도 별도다. CONFIRMED는 개별 검수자의 판단이며 승인된 정답 데이터를 생성하지 않는다.

### ReviewEvent

다섯 상태를 구현했다. UUID review_id, reviewer/target, 시간, revision/parents, source_run, 원본 예측·수정·comment를 보존한다. 이력은 append-only다. 같은 ID/내용은 중복 추가하지 않고 다른 내용은 오류다. 부모 이벤트로 현재 상태를 파생하며 이력 분기나 연구원 간 판단 차이는 conflict/NEEDS_REVIEW로 반환한다. 마지막 값으로 덮어쓰지 않는다.

### ImageSource / AnalysisRun

Source의 path와 content identity를 구별한다. SHA는 기본 None이며 명시적 streaming 검증에서만 계산한다. 재연결은 기존에 검증된 SHA와 후보 파일의 SHA/header가 일치할 때만 가능하다. 같은 source_id에 새 위치를 연결해도 이전 Run의 원본 path/stat snapshot은 남는다.

Run은 기존 scope/ROI/page, parameters/summary/preprocessing, model ID/version/hash, 시작·완료, status/error/duration, result ID를 보존한다. 존재하지 않는 dataset version이나 실행 정보를 만들지 않는다.

### Serialization

고정 타입 JSON codec이다. 모든 정의 필드가 필요하다. 중복 key·미지/누락 필드·잘못된 타입·NaN/Infinity·손상 JSON·미지원 schema를 거부한다. pickle이나 임의 타입 import/코드 실행을 하지 않는다. 메타데이터 크기 제한은 64 MiB다.

### Local Persistence

임시 JSON write/flush/fsync → 재불러오기·내용 동일성 확인 → atomic os.replace를 수행한다. OS writer lock과 expected_revision을 사용한다. 과거 Run/Observation/Prediction/Geometry/Review/Instance/Relationship 삭제·덮어쓰기를 거부한다. 원본 경로 대상 저장·symlink manifest/lock·외부 참조 경로 탈출을 거부한다. 원본 픽셀·Crop은 저장 서비스에서 읽지 않는다.

### 저장/재불러오기 검증

별도 프로세스에서 동일 데이터를 복원하고 원본이 없어도 메타데이터를 읽는 것을 확인했다. fsync/replace의 모의 OSError에서 이전 파일 바이트 보존·tmp 정리·다음 정상 저장을 확인했다. 다른 프로세스의 동시 writer는 lock으로 차단했다. stat/header/hash 불일치와 검증된 원본 경로 변경을 확인했다. 전원 장애·네트워크 파일 시스템 내구성은 미검증이다.

### Schema Version

`1.0.0`. Envelope와 Project 버전이 일치해야 한다. 미지원 major/minor/patch를 거부한다. 기존 신규 schema 파일이 아직 없으므로 migration 함수는 없으며 앞으로 명시적으로 추가해야 한다.

### 기존 결과 호환

기존 AnalysisResult·JSON/CSV·xrt_feedback_v1은 독립 계약으로 유지한다. 기존 JSON 파일 자동 migration이나 feedback 동기화는 구현하지 않았다. 기존 Geometry를 점으로 축소하지 않고 대응하는 형상을 보존한다.

### 실제 RGB 결과

측정 환경: Windows 11 10.0.26200 / Python 3.13.7 / Qt 6.11.2 / NumPy 2.5.3 / ONNX Runtime 1.30.0 CPU / Java 24.0.2.

원본: After annealing_1.jpg, 12349×12273 RGB8, 106,125,836 bytes.
모델: spatial64-c4-24368b8f6613. 기존 Desktop의 model_version은 semantic version이 아닌 모델 SHA 문자열을 그대로 보존한다.

| 범위 | Total | BPD | TED | TSD |
|---|---:|---:|---:|---:|
| FULL_IMAGE | 2946 | 245 | 1398 | 1303 |
| ROI x1003,y1011,w1495,h1495 | 791 | 3 | 779 | 9 |

`tools/validate_result_domain.py --expect-baseline`을 실제 데이터와 기존 모델로 실행해 PASS했다. 각 후보 ID·좌표·분류·raw score·metadata를 변환 전후 비교했다. 두 Run/3,737 Observation 저장·재불러오기와 검증용 UNCERTAIN 이벤트 추가 후 원본 예측 보존을 확인했다. 실제 연구원의 검수나 정답 라벨은 아니다.

- Original JPG SHA256: `c864ce2410e940ee0e5c11faf4bec2f38fa66cf1f8d5ecc4cc15bfa5b60f1c47`
- Model SHA256 / version: `24368b8f6613cba5251c0bd8e63d7ddec726d6343a35ed878e823a0091369694`
- Manifest SHA256: `a5a8a3536a491da0f17e39985186957a2bab098acf312d797f8e702dea621a6d`

실행 전후 해시가 모두 일치했다. 로컬 로그·private result는 ignored `artifacts/result96-real/`와 `artifacts/result96-real.log`다. 원본·모델·private JSON은 Git에 넣지 않았다. 실제 모델 검증은 RGB JPG이며 대형 uint16 TIFF 분류를 실행한 것이 아니다.

### 기존 Export 무결성

실제 FULL/ROI 양쪽에서 변환·저장·재불러오기 전후 JSON/CSV를 바이트 비교해 일치했다. 기존 UI controller Export도 신규 Review 추가 전후 동일성을 검증했다. 점수 재반올림·필드·정렬 변경은 없다.

### 서버 동기화 확장

고유 ID·이벤트 멱등성·parent/revision/fork가 동기화 기반이다. 서버·통신·인증·중앙 conflict resolver는 미구현이며 원본/Crop 자동 업로드도 없다.

### 모델 학습 확장

개별 Review와 adjudication/GT eligibility를 구분한다. 승인 근거·시점·담당자를 기록할 수 있지만 이 서비스가 실제 승인 절차를 수행하지 않는다. dataset 추출·학습·평가·배포·자동 weight 업데이트는 없다.

### 이미지 정합 확장

ImageRole, registration ID, transform ref, quality, verification status를 기록한다. SIFT·결함 대응 탐색은 미구현이다.

### Wafer Map 확장

wafer/tile/alignment/coordinate system/calibration status를 기록한다. 배치·좌표 변환 알고리즘은 미구현이다.

### 3D 확장

page/acquisition order/axis/spacing/orientation/calibration 근거를 기록한다. ImageJ frames를 공간 Z로 추정하지 않는다. 페이지별 2D Observation을 연결할 수 있으나 3D 표면·volume은 생성하지 않는다.

### 변경한 파일

- 신규 `src/sic_xrt_analyzer/results/` 9개 모듈
- 신규 `tests/test_result_domain.py`, `tools/validate_result_domain.py`
- 신규 `docs/result/XRT-RESULT-TD-01-DOMAIN.md`와 본 보고서
- README에 서비스·설계·검증 안내 추가
- 기존 analysis/UI/QML/Native Dialog, sources/, 원본·모델은 변경하지 않음
- 사용자 AGENTS.md는 수정·stage하지 않고 보존

### 테스트

| 항목 | 결과 |
|---|---|
| Lint | Ruff PASS |
| Compile | compileall src PASS |
| Build | wheel PASS, results 9개 모듈 포함 확인 |
| Unit / Geometry / Review / Serialization / Persistence / Export | 59 passed, 1 skipped, 4.92s |
| 실제 RGB Integration | FULL 2946 / ROI 791 PASS |
| Windows Native Plugin | 4 passed, 5 deselected, 33.14s |
| Windows 전체 Regression | 407 passed, 5 skipped, 592.19s |
| GitHub CI | 연결된 Draft PR 최종 HEAD의 결과 참조 |

Windows에서 symlink 생성 권한이 없어 외부 asset symlink 탈출 검사 1개를 skip했다. 경로 탈출·절대 경로·동시 writer 검사는 실행했다. Linux CI에서 symlink 검사를 실행한다. Native는 Windows QPA, 일반 pytest는 offscreen, TEMP/TMP는 D:/Temp/PC-1을 사용했다.

### Regression

Analysis/Result/ROI/TIFF Loading/Model Preflight/ImageJ-Fiji/Export/Viewer의 기존 전체 검사를 유지한다. Native Dialog 안정화 코드는 변경하지 않았다. OS 파일창의 사람이 직접 수행하는 Acceptance를 이번 작업에서 완료했다고 주장하지 않는다.

### 남은 문제

프로젝트 저장 UI·실시간 Run 상태 저장·Instance 편집 revision/승인 UI·기존 feedback migration·서버 동기화는 후속 TD다. Polygon 전체 topology·mask 내용·graph의 물리적 근거는 검증하지 않는다. 64 MiB snapshot 상한이 있다. stat 일치가 SHA 일치를 보장하지는 않는다.

### 후속 TD

TD-02 선형·분기 탐색과 후보 그룹화. 03 Instance Result UI. 04 Project 관리 UI. 05 Review/형상 편집. 06 Server/sync. 07 승인 dataset/평가. 08 승인 모델 배포. 09 TIFF ImageJ tools. 상세 의존성은 설계 문서 25절에 기록했다.

### Git

- Issue: [#96](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/96)
- Branch: `feat/96-result-domain-foundation`
- Commit: `22cd5a6` domain / `bda1edd` adapter-review / `ae85b34` persistence / `0379d64` tests / 설계·결과 보고 커밋
- Push / Draft PR / Final HEAD / CI URL: 연결 PR 본문에 실제 값을 기록한다.
- Working Tree: 본 TD 변경은 모두 commit하고 기존 사용자 AGENTS.md 변경만 남긴다.
