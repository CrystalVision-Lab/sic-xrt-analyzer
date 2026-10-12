# 중앙 Model Registry (TD-08)

Registry는 배포 엔진이다. `validated_export`는 Artifact 검사 결과이며 과학적 성능 승인이나 STABLE Release를 뜻하지 않는다. 실제 승인 Ground Truth 0건: **SCIENTIFIC_MODEL_NOT_READY**. 운영 모델은 기존 SHA를 유지한다.

## 저장 구조와 계약

PostgreSQL 17 Alembic `0003`: `model_candidates`, `model_events`, `model_releases`. UPDATE/DELETE 금지 trigger, FK, 모델 계열+버전 unique, subject+revision unique, Release Sequence unique. 모든 변경은 인증된 ADMIN과 audit, advisory lock 11008, 기대 Event ID로 직렬화한다. 등록·검증 실패는 DB transaction을 rollback한다. DB 이전 0001/0002 기록은 유지한다. 모델 Volume은 Crop Volume과 별개이며 상시 API는 모델 Volume을 read-only로 마운트한다.

ML TD-07의 실제 필수 파일은 `model.onnx`, `manifest.json`, `candidate-registry.json` 세 개다. 평가 JSON은 candidate-registry에 내장돼 있으며 canonical SHA를 검사한다. 추가 외부 평가 파일을 요구하지 않는다. ML 코드를 복사하거나 수정하지 않았다. Model/Manifest/Registry/Dataset/Checkpoint/Config/Evaluation SHA, 코드 Revision, 입력·출력, architecture, 평가 상태를 보존한다. 같은 모델 계열·버전에 다른 Manifest 또는 Registry를 등록하면 409. 같은 Artifact 재등록은 기존 Candidate를 반환한다.

CAS 키는 Model+Manifest+Candidate Registry hash의 canonical digest다. `models/<64hex>/{model.onnx,manifest.json,candidate-registry.json}`. 같은 Model SHA라도 평가·Manifest가 다르면 별도 불변 Bundle이다. staging copy 후 hash를 다시 검사하고 rename한다. DB commit 실패 후 참조 없는 완성 CAS가 남을 수 있으나 배포 목록에 나타나지 않고 quota에 포함된다. 자동 삭제하지 않는다.

## 등록·승인·서명

관리자 바이너리 업로드 HTTP route는 제공하지 않는다. ONNX parser를 상시 API에서 실행하지 않도록 **인증된 로컬 일회성 CLI**로 등록한다. API 관리자 후보 목록/적격성/승인/철회와 CLI 목록/감사/통계를 지원한다.

```powershell
Set-Location D:\capstone\sic-xrt-analyzer
.\.venv\Scripts\python.exe tools/server_ops.py model-admin --input <candidate-directory> --model-command register --bundle /input --model-id <family> --version <version> --dataset-id <dataset-UUID>
.\.venv\Scripts\python.exe tools/server_ops.py model-admin --model-command list
.\.venv\Scripts\python.exe tools/server_ops.py model-admin --model-command gate --candidate-id <UUID> --channel STABLE
.\.venv\Scripts\python.exe tools/server_ops.py model-admin --input <baseline-directory> --model-command measure --candidate-id <UUID> --baseline-bundle /input --previous-event-id <latest-event-ID>
.\.venv\Scripts\python.exe tools/server_ops.py model-admin --model-command approve --candidate-id <UUID> --channel STABLE --reason "전문가 평가 근거 및 배포 제한" --previous-event-id <latest-event-ID>
```

`measure`는 기존 SHA의 baseline과 Candidate를 같은 CPU2 threads, batch1/7, warmup1/repeat5, random float32 입력으로 재검사하고 실제 시간·SHA를 별도 Event에 기록한다. 이 시간은 독립 Test Set의 정확도 지표가 아니다. CPU 측정 후 새 Event ID로 승인한다. prepare는 승인 head를 변경하지 않고 별도 audit를 작성한다.

```powershell
.\.venv\Scripts\python.exe tools/server_ops.py model-admin --input <protected-public-key-directory> --model-command key-register --public-key-file /input/public.json
.\.venv\Scripts\python.exe tools/server_ops.py model-admin --output artifacts/sync106-private/releases/<new-prepare> --model-command prepare --candidate-id <UUID> --channel STABLE --key-id <trusted-key-id> --reason "실제 변경 및 제한" --output /operation/prepared.json
.\.venv\Scripts\python.exe tools/server_ops.py model-admin --input artifacts/sync106-private/releases/<new-prepare> --output artifacts/sync106-private/releases/<new-sign> --signing-key <protected-private-key> --model-command sign --metadata /input/prepared.json --key-file /signing/private.key --output /operation/release.json
.\.venv\Scripts\python.exe tools/server_ops.py model-admin --input artifacts/sync106-private/releases/<new-sign> --model-command publish --metadata /input/release.json
```

Private Key는 명시적인 sign 일회성 프로세스에만 RO 마운트한다. API는 키를 갖지 않는다. `--admin-credential`은 별도 격리 QA ADMIN 파일 선택용이며 기본은 기존 private admin.json이다. 관리자 파일·토큰을 콘솔이나 Git에 출력하지 않는다. 새 출력 폴더만 허용한다. Windows private 상위 폴더 ACL, Linux 파일 0600/디렉터리 0700을 확인한다. Container UID10001이 공개키와 승인 입력을 읽고 출력에 쓸 수 있어야 한다.

## 배포 승인 Gate

STABLE와 BETA 모두 실제 DatasetVersion digest, 현재 사용 상태 AVAILABLE, 실제 승인 `real_research` rows, 비합성 Manifest, 독립 평가, 동일 입력/라벨 baseline 비교를 요구한다. test sample/label/crop hash를 Registry rows로 재계산한다. train/validation/test 각 클래스 최소10/5/5는 초기 보수적 등록 정책이며 실제 연구 설계·독립 촬영 수의 충분함을 보장하지 않는다. Metric의 class order, sample/support, accuracy/balanced accuracy/macro F1, BPD precision/recall 및 모든 클래스 F1을 검사하고 정수 혼동행렬로 지표를 대조한다. 기존 모델 SHA와 실제 Candidate CPU comparison Event도 필요하다.

과학적 Gate 통과와 ADMIN 승인 Event, 별도 신뢰 키의 서명, Release publish는 각각 필요한 단계다. 상태 문자열이나 ADMIN 버튼만으로 Synthetic 출처를 해제하지 않는다. Dataset 승인·촬영 Group 변경/철회 시 새 승인을 차단하고 기존 Release는 DATASET_REVIEW_REQUIRED로 표시한다. 명시적 REVOKED/DEPRECATED Event로 신규 다운로드를 차단한다. 과거 이력과 파일을 삭제하지 않는다.

## 채널·API

| 채널 | 대상 | 조건 |
|---|---|---|
| STABLE | 일반 연구원 | PRODUCTION, 전체 과학적 Gate+승인+서명 |
| BETA | 명시적으로 가입한 연구원 | 같은 과학적 Gate, ADMIN beta-grant와 Desktop BETA 선택 |
| INTERNAL_TEST | 격리 ADMIN만 | 별도 DB/Asset/Model Volume + INTERNAL_TEST realm; Synthetic 기능 QA |

Realm 환경변수만 바꿔 운영 DB를 QA로 재사용하지 않는다. QA의 독립 Compose 프로젝트와 DB·Volume을 사용한다. 일반 연구원은 INTERNAL_TEST 조회403, 개별 파일404. 실제 운영 후보·Release·서명 Key는 현재0개다.

- `GET /api/v1/models/releases?channel=STABLE`: 최신100개 서명 Envelope와 최신 상태.
- `GET /api/v1/models/releases/{id}`: 동일 Envelope + Revocation/Dataset 현재 상태.
- `GET .../{id}/manifest`, `GET .../{id}/download`: AVAILABLE만 인증된 stream.
- `GET /api/v1/admin/models/candidates`, `/audit`, `/statistics`.
- `POST .../validate`, `/approvals`, `/revocations`: ADMIN, 기대 head Event ID와 이유.

키 등록/폐기, 베타 권한, prepare/sign/publish는 로컬 CLI로만 수행한다. CLI `key-revoke`는 공개키 파일+이전 key Event ID, `revoke`는 Release ID+이전 Release Event ID+이유를 요구한다. Key ID 재사용으로 다른 공개키를 덮어쓸 수 없다. 새로운 Key ID를 등록한다.

Model64MiB/Metadata1MiB/Volume1GiB, 동시 다운로드4, stream1MiB chunks. 현재 baseline2,553,568bytes보다 충분히 큰 상한이다. Desktop HTTP connect5/read10/전체120초, ONNX 검증45초/RSS2GiB로 제한한다. 큰 모델·외부 tensor/다른 입력 계약은 별도 TD다. 공개 URL·redirect·앱 바이너리 업데이트는 없다.

## 백업·복원

기존 server_ops backup은 Model mutator와 같은 DB 잠금을 유지하고 API 수집을 잠시 멈춘다. pg_dump, Crop, CAS를 같은 중지 구간에서 수집한다. `xrt-server-backup-2`: 기존4개 파일 + models.tar/models.json/model_refs.json. DB는 서명 Envelope·공개 Key Event·승인·철회·감사를 포함한다. Private Key와 admin.json 원문은 백업 대상이 아니다.

SHA manifest, DB→Blob 참조, regular-file/path/size/quota를 검사하고 새 `xrt-restore-*` 빈 DB·Volume에만 복원한다. 이전 backup-1도 지원한다. 운영 Volume 삭제 없이 별도 복원본의 인증된 Release 조회·다운로드·SHA·CPU 로딩을 대조한다. Private Key는 별도 오프라인 보관/복구 체계가 필요하다.
