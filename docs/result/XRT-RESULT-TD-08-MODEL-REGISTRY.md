# XRT-RESULT-TD-08 Result

## Overall Status

**PASS — 엔지니어링 완료. Scientific Release는 SCIENTIFIC_MODEL_NOT_READY.** 실제 승인 Ground Truth 0건으로 신규 연구원용 모델을 발행하지 않았다.

## Engineering Status

중앙 Registry, 과학적 배포 Gate, 관리자 승인·서명, 인증 다운로드, Desktop 설치·명시적 활성화·롤백을 구현했다. 실제 PostgreSQL·HTTP·CPU ONNX·QML과 격리된 ML E2E로 검증했다. 기존 검사 기준·Native Dialog 안정화·분석 계약은 유지한다.

## Scientific Release Status

| 상태 | 판정 |
|---|---|
| REGISTRY_READY | 구현 및 PostgreSQL 검증 완료 |
| UPDATER_VERIFIED | 격리 QA의 실제 다운로드·설치·활성화·롤백 검증 완료 |
| SCIENTIFIC_MODEL_NOT_READY | 해당: 실제 승인 Ground Truth 0건 |
| REAL_RELEASE_APPROVED | 해당 없음: 실제 승인 신규 모델 없음 |
| RESEARCHER_DEPLOYMENT_VERIFIED | 해당 없음: 실제 승인 Release의 연구원 배포 대기 |

합성 모델은 FUNCTIONAL_TEST_ONLY로 유지했다. 정확도 향상, 실제 신규 학습 또는 연구원용 STABLE 출시를 주장하지 않는다. 운영 Candidate/Event/Release와 서명 키는 모두 0개다.

## Git

- Start Branch: `feat/108-verified-dataset-export`.
- Start HEAD: `ab50c9a5a5c34050f8276eab65004f5cd10afeb2`.
- Work Branch: `feat/110-model-registry-updater`.
- 검증 코드 HEAD: `02bb8cb49f4c73953afaabd34b8917f21196ac8c`. 문서 포함 최종 HEAD와 CI는 [Draft PR #111](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/111)에 기록한다.
- [Issue #110](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/110), base `feat/108-verified-dataset-export`.
- 구현 커밋: `b7c586d` Registry, `7a4cd64` Desktop, `d8abb25` 통합 검증, `254ca0b` 복원·오류 처리, `02bb8cb` 키 교체 목록 처리.
- 기존 Analyzer Draft #109와 ML Draft #46의 base/branch를 유지했다. merge/rebase/retarget 없음.
- ML `feat/45-training-evaluation-pipeline` @ `7dfc15cdad40e2933ec4a3585baea5fa0bcc785a`의 기존 CLI·Candidate를 소비했다. ML 두 체크아웃은 변경 없이 clean이다. 소스 복사 없음.
- 사용자 `AGENTS.md` 수정과 `sources/`, 실제 데이터·모델·비밀은 커밋하지 않았다.

## Registry Architecture

Alembic 0003에 `model_candidates`, `model_events`, `model_releases`를 추가했다. 기존 0001/0002 데이터를 유지한다. UPDATE/DELETE 금지 trigger와 append-only Event, expected head, revision·version·sequence unique 및 PostgreSQL advisory lock으로 변경을 직렬화한다. 모델 CAS는 Crop과 별도 Volume이며 상시 API에는 read-only로 연결한다.

## Model Artifact Contract

기존 ML Export의 `model.onnx`, `manifest.json`, `candidate-registry.json`을 그대로 사용한다. 평가 JSON은 Registry 내부 자료와 canonical digest로 연결한다. 존재하지 않는 별도 평가 파일을 요구하지 않는다.

FrozenClassifier/v1: `images` float32 `[N,3,128,128]`, `uint8_RGB_to_NCHW_div255`, 모델 내부 local contrast. 출력 `probabilities` float32 `[N,3]`, 클래스 순서 BPD/TED/TSD, uncalibrated·research_only·background 없음·localizes 없음. 새 ML Manifest에 bundle_id가 없으면 architecture+모델 SHA의 실제 식별자를 사용하며 기존 bundle_id는 유지한다.

## Model Versioning

Model ID+Version은 불변이다. 동일 버전의 다른 Model/Manifest/Registry는 409, 동일 Artifact 재등록은 기존 Candidate를 재사용한다. CAS identity는 세 파일의 해시로 계산한다. Release ID와 전역 증가 Sequence는 별도이며 같은 Candidate/channel의 중복 Release를 거부한다. 모델 계열 변경을 기존 모델 fine-tuning으로 표현하지 않는다.

## Dataset/Evaluation Provenance

실제 DatasetVersion FK·digest·현재 사용 상태, 학습/평가 Crop·label·sample 해시, Group Split, Checkpoint/Config/Evaluation SHA와 ML Revision을 보존한다. 단순 문자열을 신뢰하지 않고 Registry의 실제 승인 rows와 test 목록을 대조한다. 철회된 Dataset의 신규 승인·다운로드는 차단하며 과거 관계·Artifact는 삭제하지 않는다.

## Scientific Release Gate

STABLE/BETA는 AVAILABLE인 실제 승인 real_research Dataset, 비합성 모델, 독립 평가, 동일 조건 baseline, 기존 모델 SHA, 클래스별 support·지표·혼동행렬 및 실제 CPU 비교 Event를 요구한다. 정수 혼동행렬과 accuracy/balanced accuracy/macro F1/BPD precision·recall/클래스 F1을 대조한다. 초기 split 클래스 최소 수는 train/validation/test 10/5/5이며 이것만으로 연구 설계의 충분함을 증명하지 않는다.

전문가 상태를 모의한 적격성 조건은 격리 QA의 Gate 단위 검사에만 사용했다. 실제 운영 승인으로 등록하거나 STABLE/BETA를 발행하지 않았다. 합성 출처는 관리자 승인 버튼이나 상태 이름으로 해제되지 않는다.

## Candidate Registration

인증된 ADMIN의 일회성 로컬 `model-admin register`로 등록한다. 대형 ONNX parser를 상시 API에서 실행하지 않는다. 기존 TD07 실제 후보 SHA `616fe36fc5ce1741b7cb61ca5f902b4e52f53eeab80e7b24d1d47b37d97d2b80`를 변환 없이 호환 검사했다. 격리 E2E에서는 기존 ML CLI로 별도의 합성 후보를 생성했다.

## Artifact Validation

파일 크기·SHA·JSON schema·Manifest·출처·실제 ONNX checker와 CPU ORT를 검증한다. 실제 이름/dtype/동적 batch/shape 및 batch 1·7의 유한·비음수·합1 출력을 검사한다. external tensor, custom domain, function/training/control-flow graph와 과도한 노드를 거부한다. 새 local contrast 계열의 관련 graph 연산 존재도 검사한다.

검증 subprocess는 45초/RSS 2GiB/CPU thread2로 제한하고 Credential 환경을 전달하지 않는다. Model 64MiB, Metadata 1MiB, 저장소 1GiB. 파일명·확장자만으로 승인하지 않는다.

## Administrator Approval

검증·검토·승인·서명·publish는 구분된다. 인증 ADMIN, 사유, 최신 expected Event ID와 현재 Gate를 요구한다. 동시 승인 시 1건만 성공하며 이전 승인·철회·감사를 덮어쓰지 않는다. CLI 목록·감사·통계·CPU 비교·key/beta/revoke 작업과 관리자 API를 제공한다. 대규모 관리자 GUI는 포함하지 않았다.

## Release Channel

STABLE는 엄격한 과학적 승인, BETA는 동일 Gate에 별도 ADMIN grant와 Desktop 참가 선택을 추가한다. INTERNAL_TEST는 독립 QA DB/Asset/Model Volume의 ADMIN만 접근한다. 운영 연구원 조회403/개별 파일404, 운영 realm에서 INTERNAL_TEST 차단을 검증했다.

## Signing / Signature Verification

Ed25519 detached signature에 Release·Registry·Candidate·Model·Version ID, Sequence, 모든 SHA·size, channel, Artifact identity, 앱 범위, 상태·생성/만료 시간·Key ID·변경 설명을 포함한다. 정확한 canonical JSON 및 duplicate-key 거부를 적용한다.

Private Key는 별도 오프라인 서명 프로세스에서만 사용하고 API·일반 백업·Git에 넣지 않는다. Desktop origin/Registry ID/Key namespace의 공개 Trust를 별도 검증 경로로 배포한다. 서버의 공개키를 자동 신뢰하지 않는다. 초기 packaged trust는 비어 있으며 운영 키를 발급하지 않았다. 키 교체 시 폐기된 과거 항목을 건너뛰고 최신 정상 신뢰 모델을 선택한다. 현재 모델의 키·파일 이상은 경고한다.

## Desktop Model Updater

**분석 메뉴 → AI 모델 관리…**에서 현재/설치 모델·출처, 업데이트 확인, 진행·취소, 설치, 다음 분석에 적용, 이전 모델 복원을 제공한다. 기존 모델 상세창을 유지한다. Sync origin/client ID와 OS Credential vault를 공유한다. QML 버튼을 통해 확인→설치→명시적 활성화→재시작 복원→롤백을 실제 Controller로 검사했다.

## Secure Download

인증된 같은 origin의 고정 상대 경로만 사용한다. redirect·환경 proxy·압축 Model response·임의 외부 URL을 거부한다. localhost HTTP/외부 HTTPS, connect5/read10/전체120초, 크기 제한, streaming SHA와 서명·Manifest·최신 상태 확인을 적용한다. 서버 동시 stream4, chunk1MiB. 취소·끊김·부분 응답·오류는 staging만 정리하고 현재 모델을 유지한다.

## Atomic Installation

Qt AppLocalDataLocation/models 또는 `SIC_XRT_MODEL_DIR`의 새 staging에서 검증 후 같은 filesystem rename으로 게시한다. symlink/Windows junction과 동시 설치를 거부한다. 설치 Bundle은 불변이며 state는 fsync+atomic replace로 보존한다. SHA/서명/CPU 검사·디스크/권한/포인터 저장 실패는 현재 Adapter를 유지한다. 설치만으로 활성화하지 않는다.

## Model Activation

사용자의 명시적 선택과 새 Adapter 정상 준비·포인터 저장 후 전환한다. 분석 실행, loader/project 작업, 미저장 결과·검수·ROI/Geometry 편집은 차단한다. context 변경 후 늦게 도착한 응답은 폐기한다. env override → 직접 선택 Bundle → 활성 서명 Bundle → 기존 Bundle 순이다. 새 모델로 분석할 때 기존 Run을 덮어쓰지 않고 새 Run을 생성하는 기존 흐름을 유지한다.

## Rollback

직전 정상 모델을 삭제하지 않는다. 검증된 이전 설치 모델 또는 기존 모델의 경로·SHA를 보존하고 명시적 복원한다. rollback은 origin/channel의 high-water Sequence를 낮추지 않는다. 새로운 낮은 Sequence 다운로드는 거부한다. 운영자가 이전 Artifact를 재배포하려면 새로운 버전·승인·높은 Sequence·서명이 필요하다.

## Offline Behavior

현재 모델→검증된 이전 모델→기존 Bundle로 복구한다. 이미 설치된 모델의 서명 만료는 오프라인에서 허용하지만 알려진 철회·폐기 키·파일 손상은 거부한다. 업데이트 확인에서 현재 모델의 문제를 경고하며 실행 중 Adapter를 강제로 제거하지 않는다. 새 활성화·재시작에는 알려진 사용 제한을 적용한다. 서버 중단 시 로컬 분석·검수·저장은 유지한다.

## Synthetic QA E2E

독립 `xrt-restore-td110-qa-4910de` 및 별도 copy에서 실제 PostgreSQL Dataset Registry의 합성9개를 승인·반출했다. 변경 없는 ML CLI가 CPU 1epoch smoke 학습·baseline 평가·Candidate Export를 수행했다. 인증 Candidate 등록→STABLE 거부→INTERNAL_TEST 승인→오프라인 서명→실제 HTTP 다운로드→SHA/서명/CPU 설치→Adapter 로딩→기존 모델 롤백→서버 재시작→물리 백업·별도 복원→새 클라이언트 재다운로드를 통과했다.

- Dataset SHA: `53eabaca9c7659c5d547024cf4db7a44ee8227bea0a0136d6277c69fbe810de2`.
- Model SHA: `7b69a68036e737b6eb09a78379097db439af8c8756218b612fd0ec7d47dcfe07`.
- Manifest SHA: `b322a0d4306e6d2ace34774811030090873d76acf15af37769834315956315a5`.
- Candidate/Release: `22fe1fc8-cb4c-4b87-8b4f-6c8c73e37b28` / `90b82147-4062-46ad-90c1-2770d88157f9`.
- `artifacts/td110-ml-e2e.json`: PASS. Private signing key 백업 제외, production STABLE 생성0.

관리 CLI의 별도 실제 CPU_COMPARISON Event도 검증했다. random float32 RGB128, CPU2 threads, warmup1/repeat5: baseline batch1/7 평균3.324/17.945ms, 합성 후보0.217/1.567ms. 기능 검사 조건의 단회 비교이며 실제 연구 정확도·응답성 개선의 증거가 아니다. `artifacts/td110-cpu-comparison.json`.

## Real Model Availability

승인 Ground Truth·실제 신규 Release가 없다. 운영 ADMIN의 실제 인증 조회 STABLE0, 운영 INTERNAL 차단과 Controller의 ‘최신 승인 모델이 없습니다. 현재 모델을 유지합니다.’를 확인했다. 운영 연구원 vault Credential은 현재 없어 새 계정을 만들거나 기존 Credential을 변경하지 않았다. 연구원 역할 차단은 격리 PostgreSQL/실제 HTTP에서 검증했다.

## Existing Model Preservation

기존 모델 SHA `24368b8f6613cba5251c0bd8e63d7ddec726d6343a35ed878e823a0091369694` 유지. 원본 JPG/TIFF·기존 model/manifest·프로젝트 SHA와 저장된 과학적 데이터가 같다. QA 모델을 실제 데이터에 추론하지 않았다.

실제 프로젝트를 읽은 QML Controller에서 QA 모델 활성화와 기존 모델 롤백 후 4 Run, 7,474 observations/predictions, 로컬10 ReviewEvent, 7,545 Geometry의 전체 객체·좌표·점수·출처와 디스크 SHA 동일. 새 Run 생성0. `artifacts/td110-history-activation/report.json` PASS. 운영 DB ReviewEvent16개는 다른 기록까지 포함하므로 로컬10개와 구분한다.

## Real JPG Regression

저장된 Full 2개 Run은 각2,946(BPD245/TED1,398/TSD1,303), ROI 2개 Run은 각791(BPD3/TED779/TSD9)이다. Candidate ID·좌표·raw scores·Model Hash·Run·ReviewEvent·Geometry를 보존하고 반복 Export가 동일했다. 신규 추론0. 실제 JPG/원본 모델을 변경하지 않았다. `artifacts/td110-real-regression-v2/report.json` PASS.

## TIFF Regression

실제 N119는1/80/158, No107 before/after 및 No22는1/79/156 페이지를 내부 Viewer로 탐색했다. 읽기 전용 uint16 원본과 tifffile oracle이 동일하고 TIFF 모델 분석은 비활성 상태였다. 자동 추론0, 학습 Crop 자동 생성 없음, 원본 SHA 보존, QML warning0. 새 Updater는 Viewer/원본 좌표 경로를 변경하지 않았다.

Windows native 플러그인4개는 생성 TIFF를 사용하여 실제 AWT/Swing/GenericDialog와 QML 호스팅·결과 반환을 통과했다. 실제4개 TIFF의 같은 첫·중간·마지막12페이지를 기존 ImageJClient로 읽었다. ImageJ Multiply(value=1) 작업 복사본은 전체 uint16 oracle과 동일했고, Fiji MultiplyDataValuesBy(value=0.5)는 사각형 ROI의 half-up 정수 결과·영역 밖 모든 원본 픽셀과 정확히 일치했다. 검증 전후 전체 원본 SHA 동일. `artifacts/td110-real-tiff-engines/report.json` PASS. 작업 결과는 엔진 임시 폴더에서만 생성하고 종료 시 정리했다. 대용량 전체 TIFF의 Fiji editable Dataset은 기존512MiB 한도로 지원하지 않으며 현재 페이지 작업만 대상으로 한다.

## PostgreSQL Integration

실제 PostgreSQL17.11: **79 PASS**, 기존 Starlette/httpx TestClient deprecation warning1건. 새/기존 데이터 migration, append-only trigger, version 충돌, expected-head 동시 승인, 권한, 실제 Dataset/Science Gate, 손상·복사 실패 transaction rollback, 서명/철회/키 폐기, HTTP stream·Desktop installer·CPU, restore를 검사했다. 운영 DB 초기화 없음. `artifacts/td110-server-final.log`.

## Backup/Restore

운영 migration 전에 private `td110-before` 백업을 생성하고 별도 `xrt-restore-td110-before` 빈 DB·Volume로 복원했다. audit/alembic 제외22테이블의 count와 모든 행 canonical SHA가 운영 최종 상태와 일치했다. 기존 사용자/권한/프로젝트/검수/Dataset 기록 보존, 새 Registry3테이블은 빈 상태다. `artifacts/td110-operating-final.json` PASS.

backup-2는 DB·Crop·Model을 같은 수집 중지/Model mutator 잠금 구간에 수집한다. 서명·공개키·승인·감사는 DB로 복원하고 CAS 참조·SHA·archive 경로/regular file/크기/quota를 확인한다. 실제 합성 Release 백업→별도 복원 후 인증 다운로드·해시·서명·CPU 로딩까지 대조했다. Private Key와 관리자 Credential 원문은 일반 백업에 넣지 않았다. QA/복원 컨테이너는 검증 후 중지하며 Volume은 삭제하지 않는다.

## Windows Full Tests

환경: Windows11 Pro 10.0.26200, i7-13700, RAM 약31.75GiB, D 작업 경로, Python3.13.7, Qt6.11.2, ONNX1.23.2, ORT1.30.0, cryptography46.0.7, Docker Linux PG17.11.

| 검사 | 결과 | 근거 |
|---|---|---|
| Ruff / compileall | PASS | td110-quality-final.log / src·server·tools |
| Desktop·Server Wheel | PASS | td110-wheel-final.log |
| Updater·기존 분석 Flow/QML | 58 PASS | td110-updater-key-final.log |
| 기존 ROI 비동기 재검사 | 23 PASS | td110-roi-timeout-recheck.log |
| Windows native plugin | 4 PASS /5 deselected | td110-native-plugin.log |
| 전체 회귀 최종 | **610 PASS /기존5 SKIP /1080.83초** | td110-windows-full-v4.log |

실패 로그도 보존했다. 최초 전체603 PASS/2 FAIL은 기존 모델 상세창을 대체한 영향이었다. 상세창을 복원하고 메뉴를 분리한 뒤 전체605 PASS/기존5 SKIP를 확인했다. 보강 후 전체608 PASS/1 FAIL/기존5 SKIP는 기존 ImageJ Wand의5초 대기 초과였고 동일 기준 ROI23개 재검사는 PASS였다. 마지막 전체 검사는 최신 코드로610 PASS를 확인했다. 테스트 삭제/비활성화/타임아웃 완화 없음. 기존 SKIP5개는 Windows symlink 권한1개와 offscreen에서 실행할 수 없는 native 창4개다. native4개는 별도 Windows 플랫폼에서 모두 통과했고 symlink 검사는 Linux CI에서 통과했다. 일부 traceback에는 이전 C 경로가 표시됐으나 실제 interpreter/package/updater가 D 경로에서 로드됨을 확인했다.

실제 TIFF 초기 병행 검사에서 No22 준비가240초를 넘었다. 다른 리소스 검사 종료 후 원래 조건으로 재실행하여4개 전체 PASS를 확인했다. 자원 경합은 관찰된 조건이며 계측 없이 정확한 원인으로 단정하지 않는다.

## GitHub CI

검증 코드 `02bb8cb`의 [CI #135](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/38245412004)는 quality/server-postgres 모두 PASS. Ruff/compileall/wheel/core611 PASS/기존4 SKIP, Linux X11 native plugin4개, PostgreSQL79개, PR policy를 유지했다. 서버 CI는 PySide6/torch/jpype 없이 동작함을 확인한다. 최종 문서 커밋 CI는 PR에 기록한다.

## Operational Readiness

localhost `127.0.0.1:18766` 운영 서버를 유지한다. 모델 상시 API는 비특권·read-only이며 ONNX parser/Private Key를 포함하지 않는다. Registry0/GT0 상태에서 기존 모델 유지가 정상이다. 자동 확인/다운로드/설치/적용 없음. 공개 HTTPS·Tunnel·EXE 업데이트·새 실제 학습을 하지 않았다.

운영 절차: [Registry](../server/MODEL-REGISTRY.md), [서명·신뢰](../server/MODEL-RELEASE-SECURITY.md), [Desktop](../desktop/MODEL-UPDATES.md), [배포·백업](../server/DEPLOYMENT.md).

## Security Limitations

- 신뢰 공개키의 별도 운영 배포가 필요하며 현재 packaged origins는 비어 있다.
- ONNX subprocess 자원 제한은 완전한 OS sandbox가 아니고 graph 관련 연산 검사는 수학적/과학적 동등성의 증명이 아니다.
- 오프라인에서는 아직 수신하지 않은 새 철회를 알 수 없다. 현재 실행 중 Adapter는 확인 실패로 강제 제거하지 않는다.
- Range resume 없음: 실패 후 새 staging부터 수동 재시도. 최신100개·모델64MiB·저장1GiB 한도를 사용한다.
- fsync/rename은 정상 filesystem을 전제로 하며 물리 디스크 손상·모든 전원 장애를 보장하지 않는다.
- DB commit 실패 후 참조 없는 완성 CAS가 남을 수 있다. 배포되지는 않고 quota에 포함되며 자동 삭제하지 않는다.
- 앱 지원 범위0.1.0–0.1.0, 신규 Release 만료14일. 계약·용량·앱 범위 확장은 별도 검토한다.

## Pending Manual Acceptance

실제 승인 Dataset/독립 평가/전문가 성능 승인, 운영 서명키·별도 Trust 배포와 실제 승인 Release의 연구원 Credential·기기 실사용은 대기다. GT0 상태에서 이 단계가 완료됐다고 보고하지 않는다. 합성 E2E는 엔지니어링 검증으로만 사용했다. 외부 HTTPS·Linux Compose 운영 실사용도 이번 localhost Windows 검증으로 대신하지 않는다.

## Next TD

승인된 실제 Ground Truth와 독립 촬영 그룹을 확보한 뒤 ML 저장소의 학습·baseline 평가·전문가 검토를 진행한다. 과학적 Gate 통과 후 운영 키/Trust를 준비하고 승인 모델의 STABLE/BETA 및 연구원 실사용을 별도 acceptance한다. Installer/앱 바이너리 업데이트는 별도 TD다.
