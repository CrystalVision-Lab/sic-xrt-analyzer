# XRT-RESULT-TD-07 — Dataset Readiness

## Overall Status

로컬 엔지니어링 PASS, 최종 CI 확인 중. 실제 정답 DATA_NOT_READY / 실제 학습 NOT_RUN / 독립 평가 NOT_AVAILABLE / 성능 향상 NOT_VERIFIED. 합성 Fixture의 학습·평가·ONNX 산출은 기능 확인이며 과학적 성능 검증이 아니다.

## Analyzer Dataset Pipeline

개인 검수와 별도의 ADMIN 승인·철회 이벤트, Source Group Mapping, Crop 적격성 검사, immutable Dataset Version, local private Export를 구현했다. 기존 API·idempotent 수집·Reviewer ID·ModelPrediction·ReviewEvent·분석 Geometry는 유지한다. Dataset ADMIN과 로컬 Reviewer는 구분한다. [v1 Artifact 계약](../server/VERIFIED-DATASET-CONTRACT.md), [API](../server/API.md), [반출 방법](../server/DEPLOYMENT.md)을 참고한다.

## ML Training Pipeline

ML Issue #45에서 원격 main의 빈 구조를 기반으로 새 로더·소형 CNN·CPU/CUDA 학습·validation·checkpoint/resume·독립 평가·기존 ONNX 비교·ONNX checker/CPU parity·후보 registry를 구현했다. 계약은 정확한 RGB8 128×128 / BPD,TED,TSD / float32 NCHW /255와 모델 내부 contrast다. 분석 프로그램에서 학습하지 않으며 기존 모델을 자동 교체하지 않는다. 상대 저장소 코드를 이 PR에 포함하지 않는다.

## Git / PR

Analyzer 시작 feat/106-central-research-sync@a6605088eb6cf54526da5d07f82a61433e83d926, Issue #108, branch feat/108-verified-dataset-export. 기존 Draft #107과 stacked parent를 merge/rebase/retarget하지 않았다. ML 시작 원격 main@cc0cbabb6640ddd2899ecee9b9195ee450f45f4f, Issue #45, branch feat/45-training-evaluation-pipeline. 미병합 로컬 ML feat/43@446d7fb는 보존했다. 사용자 AGENTS.md 변경은 stage하지 않았다. Analyzer Draft [#109](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/109), ML Draft [#46](https://github.com/CrystalVision-Lab/sic-xrt-ml/pull/46). 최종 HEAD와 CI는 각 PR에 기록한다.

## Current Ground Truth Availability

localhost 127.0.0.1:18766의 현재 PostgreSQL/API를 실제 조회했다. TD06 백업 숫자를 현재 상태라고 가정하지 않았다. 현재도 1 project, 5 source, 4 run, 7,474 observations/predictions, 35 instances, 7,545 geometries, 16 reviews, Crop2, 검수 대상5, 충돌 대상2, 실제 승인0, Dataset Version0이다. 이전 QA 검수를 전문가 정답으로 승격하지 않았다.

## Dataset Eligibility

현재 사용 가능한 승인 Crop 0. 제외: IMAGE_ASSET_MISSING 4 targets, PATCH_CONTRACT_MISMATCH 1 crop(64×64), GROUP_NOT_READY 1 crop(128×128). 제외 단계는 첫 실패 사유를 보고하므로 충돌·승인 누락 등이 별도 중복 집계되지는 않는다. 검수 이벤트·후보·Crop 수는 정답 수와 다르다. 실제 학습 최소 기준은 train10/class·validation5/class·test5/class와 각 split 독립 그룹이다. 기준은 실제 학습 전에 고정했다. 충분한 실데이터가 없어 학습·accuracy 비교를 수행하지 않았다.

## Adjudication / Versioning

ADMIN만 승인할 수 있고 researcher 자기 승인·반출을 거부한다. current leaf review IDs, 승인 라벨·사유, Source/Run/Target/Crop 관계를 확인한다. conflict는 기본 제외하며 ADMIN의 명시적 resolve_conflict와 사유가 있을 때만 별도 판정한다. uncertain/UNKNOWN/absent 검수는 제외한다. 기존 검수·예측을 덮어쓰지 않는다. PENDING/APPROVED/REJECTED/REVOKED/NEEDS_ADJUDICATION 이벤트를 append하며 과거 head를 사용한 경합은 409다.

Alembic 0002가 dataset_events와 dataset_versions, UPDATE/DELETE 거부 trigger를 추가한다. 0001은 기존 테이블만 생성하도록 고정했다. 승인·Mapping 변경 또는 새 검수·Crop 손상 시 과거 버전은 현재 usage_status=RESTRICTED가 된다. 그 버전의 라벨·Manifest·hash는 바뀌지 않고 새 반출은 거부한다. 새 버전 생성이 필요하다. 이미 오프라인으로 가져간 사본은 관리자가 서버 상태를 확인하고 사용을 중단해야 한다.

## Source / Label Provenance / Image Integrity

등록된 원본 Source hash와 Source/Run/Target/Review 연결, 실제 PNG SHA·decoded RGB pixel SHA·크기·dtype를 재검증한다. 원본 JPG 전체가 서버에 없으므로 원본 픽셀과의 직접 대응·촬영 조건·전문가 신원은 독립 검증했다고 주장하지 않는다. 관리자 근거를 별도로 기록한다. 128×128 이외 Crop는 변환하지 않고 제외한다. TIFF를 RGB로 바꾸거나 학습용 Crop를 자동 수집하지 않는다. exact 중복은 제외하고 서로 다른 정답 라벨의 동일 pixels는 모두 제외한다.

## Dataset Split / Leakage / Wafer Holdout

Source·Wafer·target·Run·전후·제공자·독립 촬영·중복 관계를 union하고 deterministic seed로 그룹 단위 분할한다. 원본의 여러 ROI를 독립 평가로 취급하지 않는다. dHash 거리≤4도 묶되 완전한 near-duplicate 검출을 주장하지 않는다. Split group 확인이 없으면 적격성이 부족하다. 기존 FeedbackPanel.qml의 wafer `8` 최종시험 정책을 유지한다. 새 Mapping에도 정규 십진 wafer_id=8→evaluation_only=true를 요구하고 그 그룹은 test 전용이다. 파일명으로 Wafer를 추정하지 않는다. synthetic_fixture 출처는 이후 real_research로 변경할 수 없다.

## Training / Checkpoint / Evaluation / Comparison

ML의 신규 baseline 구조·seed·optimizer·scheduler·validation-only selection·epoch resume·자원 제한은 ML TD07 문서에 기록한다. 2-epoch 연속 CPU 학습과 1+1 재개 결과의 모든 weight/history를 대조한다. 합성 검증은 실제 정확도가 아니다. absent class 지표는 N/A로 남긴다. 명시적 최종 평가만 test를 읽고 같은 run의 재평가·평가 이후 재개를 막는다. 기존 모델과 비교하려면 같은 승인된 독립 test sample/label/input을 사용한다. 이번 실데이터 비교는 정답 부족으로 NOT_AVAILABLE이다.

## ONNX Export / Contract Compatibility

새 후보만 별도 ignored/private 폴더에 산출한다. model hash·checkpoint·dataset·config·code·evaluation provenance와 ONNX checker·ORT CPU batch1/7 parity를 기록한다. classes/input/output/local_contrast 계약을 확인한다. 합성 후보는 FUNCTIONAL_TEST_ONLY, independent_test_passed=false, 자동 배포 NOT_AUTHORIZED다. 기존 Analyzer ONNX 파일과 model manifest는 교체하지 않는다.

## PostgreSQL Tests / Operational Preservation

전용 xrt_td106_test에서 기존 수집 회귀와 새 승인·철회·권한·Crop·immutable version·export·deterministic split·Wafer 보호를 검사했다. 무작위 xrt_td108_*_test DB에서 populated 0001→0002 upgrade, 반복 upgrade, 논리 pg_dump/psql 복원, registry·event·기존 행 보존을 검사하고 해당 임시 DB만 정리했다. 실제 source/main DB는 초기화하지 않았다.

운영 stack은 별도 private 백업(td108-before)을 만든 뒤 추가 마이그레이션을 적용했다. 17개 기존 테이블의 모든 행 수와 정렬된 JSON row digest를 대조하여 모두 동일함을 확인했다. localhost API는 유지되며 실제 승인·학습 Dataset을 생성하지 않았다. 비밀은 콘솔·Git·문서에 출력하지 않는다. PostgreSQL TestClient httpx deprecation warning은 기록했다.

## ML Tests / Windows Regression / CI

현재 PostgreSQL 57 PASS, ML CPU 33 PASS. 기존 Windows offscreen/basic 전체 574 PASS / 기존 platform skip5(885.21s). 새 skip이나 기존 timeout 변경은 없다. 실제 saved JPG Full/ROI 각2회와 반복 Export PASS: Full2946(BPD245/TED1398/TSD1303), ROI791(BPD3/TED779/TSD9). TIFF4 first/mid/last(12 pages) 원본 uint16 대조 PASS, 분류 자동 실행0, 원본/model/project SHA 유지, QML warning0. Windows ImageJ/Fiji native GUI plugin4 PASS. Linux CI 최종 결과 확인 중이다.

## Scientific Validation Status / Known Limitations / Next TD

현재 실제 GT0: DATA_NOT_READY / REAL_TRAINING NOT_RUN / INDEPENDENT_EVALUATION NOT_AVAILABLE / IMPROVEMENT NOT_VERIFIED. 기능 PASS와 합치지 않는다. 실제 사용 권한·검증된 Wafer/독립 그룹·전문가 승인·충분한 클래스 표본을 축적한 후 새 Dataset Version에서 실제 학습·동일 독립셋 비교를 수행한다. 최소 표본 수가 충분한 과학적 검증 설계를 의미하지 않는다. 조직 차원의 test 접근 통제·offline 철회·원본 촬영 근거 검증은 운영 절차가 필요하다. CURATOR 역할·범용 Dataset 변환·배경 클래스·검출/Segmentation·3D·TD08 모델 배포는 포함하지 않는다.


## Producer / Consumer Acceptance

전용 PostgreSQL에서 생성·승인·반출한 synthetic_fixture 9개(각 split BPD/TED/TSD1개)를 ML의 strict 로더로 읽고 CPU 2-epoch 학습·명시적 평가·실제 기존 frozen ONNX의 같은 입력 비교·새 후보 산출을 검증했다. 초기 batch/N 심볼 호환 오류는 ML PR에서 수정했고 기존 ONNX 파일은 유지했다. checker와 CPU parity는 batch1 최대오차0, batch7 2.9802322387695312e-08. 같은 기간 localhost health GET12회 모두 HTTP200. 이는 합성 기능 검증이며 기존 모델 accuracy나 향상을 증명하지 않는다.

최종 검토에서 중복 제외가 원본 연결을 끊어 held-out 자료의 twin이 train으로 갈 수 있는 위험을 확인했다. 중복 제외 전에 관계 성분·holdout을 계산하고 ML에도 leakage_component 검증을 추가했다. duplicate alias·같은 원본의 다른 Crop가 test 밖으로 나가지 않는 회귀를 포함한다. 해당 최종 변경의 Producer→Consumer는 새 private Artifact로 재확인한다.

초기 Fixture 필드·review run/leaf 지정 오류, 전역 CONTRACT 공유 오류, helper import 오류, 버전 제한 비교 항목 추가 오류를 테스트로 찾아 수정했다. 초기 실패·최종 로그는 ignored artifacts에 남긴다. 운영 DB의 실제 검수를 수정한 실패가 아니다. Credential·실제 Dataset·모델 파일은 보고서/Git에 포함하지 않는다.
