# XRT-RESULT-TD-06 Result

## Overall Status

**검증 마무리 중.** Local E2E **PASS**, External Deployment **NOT DEPLOYED**. 최종 TIFF 페이지 대조와 GitHub CI 결과는 아래 완료 기록에서 확정한다.

실제 Windows Desktop → localhost FastAPI → PostgreSQL 영속 저장 → ACK → 재시작 조회를 검증했다. Mock DB/HTTP만으로 판정하지 않았다. 연구 데이터와 Credential은 Git에 넣지 않았다.

## Git

- Start: `feat/104-researcher-review-workspace` @ `b3569b9e2e4958431f1e06f59792dc8aac25fb3d` (TD-05 Draft #105).
- Work: `feat/106-central-research-sync`, [Issue #106](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/106).
- 기존 stacked PR에 merge/rebase/retarget 하지 않았다. 사용자 AGENTS.md는 stage하지 않았고 SHA256 `97fd9e0886957e532cfd5bafd525263462dc6e90652cf2b43ce6d3404fc04eaf`를 유지했다.
- 기능별 커밋: 과학적 동기화 계약/Outbox, 인증 서버/백업, Desktop UI, 기기 출처/비밀 격리, 최종 문서/검증 도구.
- Final HEAD, Draft PR, 최종 CI는 이 문서의 마지막 Git 검증 기록 및 PR에서 확인한다.

## System Architecture / Server Components / Docker Compose

```text
Qt Project/Review Workspace
   └─ explicit action → SyncController worker
       ├─ OS Credential Store
       ├─ SQLite durable Outbox + immutable receipt/inventory
       └─ authenticated HTTP(loopback) / HTTPS(remote)
            └─ FastAPI → PostgreSQL 17 + bounded PNG asset volume
```

FastAPI/SQLAlchemy 2/psycopg/Alembic 서버 패키지는 Desktop GUI 의존성과 분리했다. 실제 API 컨테이너에 PySide6/onnxruntime/jpype 모듈과 Java 실행 파일이 없음을 확인했다. 서버 추론/모델 학습은 없다.

현재 PC는 `D:\capstone\sic-xrt-analyzer`, Docker Desktop Linux engine이다. API는 `127.0.0.1:18766`만 publish, DB port publish 없음. API 비특권 xrt 사용자, read-only root, tmpfs, no-new-privileges, cap_drop ALL. 상시 컨테이너는 asset volume과 readonly DB secret만 mount하며 `/private` 접근은 없다. 관리자 Credential·백업 폴더는 bootstrap 일회성 컨테이너에만 mount한다. 기존 다른 Docker 서비스는 건드리지 않았다.

실행·중지·상태·로그·migration·bootstrap·test·backup·restore 명령은 [DEPLOYMENT](../server/DEPLOYMENT.md)에 있다. 전체 구조/계약은 [ARCHITECTURE](../server/ARCHITECTURE.md), [API](../server/API.md), [SECURITY](../server/SECURITY.md)를 따른다.

## Database Schema / Alembic Migration

실제 PostgreSQL 전용, SQLite 대체 서버 없음. user/device/credential hash/project membership/project/batch/snapshot/crop asset/audit 테이블과 9개 과학적 엔터티 테이블을 분리했다. project/id composite PK 및 Source/Run/actor/device/reference index, 원본 과학 payload는 JSONB에 보존한다. 단일 거대 JSON 문자열 테이블로 저장하지 않는다.

Alembic `0001`으로 빈 DB를 초기화했다. 운영 `xrt`와 `xrt_td106_test`를 분리했다. 테스트용 파괴적 초기화는 이름이 `_test`인 전용 DB만 허용한다. 서버 재시작과 별도 새 PostgreSQL 복원을 실제 수행했다. named DB/Asset volume을 삭제하는 명령은 정상 운영 도구에 넣지 않았다.

## Authentication / Project Authorization

일회성 bootstrap이 난수 관리자 Credential을 private 파일에 기록한다. 출력 파일 존재 및 DB ADMIN 존재를 각각 재초기화 거부로 확인했다. 원문을 stdout/Git/QSettings에 저장하지 않는다. Windows 실제 keyring backend는 `keyring.backends.Windows`다. plaintext keyring fallback을 허용하지 않는다.

ADMIN은 연구원/기기 발급, project membership/crop 권한, revoke/reissue 및 실제 통계를 관리한다. RESEARCHER는 허용된 Project만 업로드/조회한다. 다른 Project와 기기의 Batch ACK는 거부한다. 인증 actor/client와 원본 local reviewer_id를 각각 보존하며 사용자 이름/Reviewer ID 입력만으로 인증된 검수자나 GT로 승격하지 않는다.

## Sync Protocol / Initial Sync / Incremental Sync

Project Schema 1.0.0/1.1.0, Sync Protocol 1, API v1을 구분한다. 엄격한 루트/필드 allowlist, ID/reference/schema/hash/finite validation을 적용한다. Source의 절대 경로는 제외하고 치수/dtype/bit depth/page count/role/identity/SHA/numeric calibration을 보존한다. opaque TD-02 후보 ID mapping 11,319쌍도 보존했다.

최초에는 전체 엔터티를, 이후에는 마지막 ACK 대비 변한 엔터티 body만 전송한다. 매번 전체 ID→SHA inventory로 snapshot을 확인하므로 증분이라도 inventory 비용은 남는다. max request 32MiB / inventory 100,000개. 최신 기기별 project revision/hash/root metadata/server_received_at을 조회하되 여러 기기의 revision으로 마지막 승자를 결정하지 않는다.

## Idempotency / Conflict Handling / Local Outbox

SQLite Outbox의 immutable canonical payload/digest/BatchID와 PENDING/SENT/RETRY/ACKNOWLEDGED/attempt/receipt를 영속 보존한다. HTTP 성공만으로 완료하지 않고 project/client/revision/payload SHA/snapshot SHA/inventory를 모두 확인한 ACK만 완료한다. ACK 유실은 같은 BatchID로 재전송한다.

서버는 PostgreSQL transaction + project/batch advisory lock으로 동일 요청 재전송/동시 요청을 한 번 저장한다. 같은 entity/event/BatchID의 다른 body, 같은 기기의 동일 revision 다른 snapshot은 409이며 기존 데이터는 유지한다. 부모 Review DAG를 검증하고 payload 순서와 무관하게 복원한다. 서로 다른 연구원의 모순된 새 Review는 모두 저장하고 충돌 대상 수를 조회한다. 양방향 병합/자동 adjudication은 없다.

메타데이터/대기 Crop은 명시적 동작당 최대 20건 처리하며 남으면 추가 재전송 상태를 표시한다. 취소·project switch 시 epoch/fingerprint로 늦은 ACK가 새 project UI에 적용되지 않는다. 시작한 HTTP 요청은 timeout까지 걸릴 수 있으며 서버 commit 뒤 취소는 commit을 되돌리지 않는다.

## Desktop UI

프로젝트 작업 영역의 중앙 서버 버튼 → origin/client/Credential 설정 → 연결 테스트 → 디스크 저장 후 서버와 동기화. 자동 동기화 OFF, 미저장/dirty/pending review/read-only 상태는 전송하지 않는다. Credential 입력은 저장 후 지운다. QSettings에는 origin만 저장하고 sync()로 새 OS 프로세스에도 유지한다.

서버 미설정/중지/인증 실패/권한 거부/충돌/재시도 대기/ACK 상태를 구분한다. network/encode/SQLite 작업은 worker에서 수행한다. 로컬 검수·저장과 독립적이다. 실제 창 캡처에서 Crop 숫자 입력 폭 부족으로 첫 자릿수가 잘리는 것을 확인하여 입력 폭을 130px로 늘렸다. Crop 동의는 자동 체크하지 않으며 앱 재시작 후에도 다시 명시적으로 동의하여 대기 건을 전송한다.

## Geometry Preservation / ReviewEvent Preservation / Source Metadata

POINT/BOUNDING_BOX/POLYLINE/POLYGON/MASK_REFERENCE/BRANCHED_GRAPH 계약과 HUMAN/자동 출처, 모델 Prediction/raw score/좌표/해시, existence/class/geometry decision, parent reviews/corrected geometry와 provenance를 보존했다. 원본 Geometry/Prediction은 overwrite하지 않는다. 수동 객체와 CandidateObservation 수를 구분한다. MaskReference metadata는 전달하지만 mask binary는 자동 업로드하지 않는다.

TIFF는 원본 metadata 등록/Stack 탐색 전용이며 JPG 검수·Crop·ONNX 자동 실행에 사용하지 않는다. ImageJ frames를 공간 Z로 확정하지 않는다.

## Crop Upload

명시적 동의 + Project crop permission + 검수된 JPG 대상 + Source/Run/reference/SHA 확인이 필요하다. 원본 encoded 좌표의 RGB8 crop을 lossless PNG로 전송한다. EXIF rotate/resize/normalize/sharpen 없음. 원본 전체, TIFF crop, 경계 밖/다른 Source/변경된 원본/잘못된 review/변조 bytes는 거부한다.

한 요청 한 crop, max 1024×1024 / PNG 4MiB / project asset record 1,000개. 원본 압축 파일 SHA, crop PNG SHA, decoded RGB pixel SHA와 provenance를 보존한다. 안전한 64hex.png storage key를 사용하고 byte blob은 SHA로 dedup, metadata 관계는 별도다. temp fsync + atomic replace 후 DB 성공만 ACK한다.

실제 128×128 JPG crop의 Pillow PNG decoded RGB를 기존 Viewer의 Qt JpegImageSource.read_region 원본 RGB와 byte별 비교하여 동일함을 확인했다. 동일 crop 재전송은 asset 중복 없음. 64×64 crop은 offline queue→새 OS process→새 동의→같은 queued ID ACK로 검증했다. 서버는 전체 원본을 보유하지 않으므로 등록된 source_hash를 넘어 원본과 crop의 공간적 일치를 독립 검증할 수는 없다.

## Security Validation / Audit Logs

실제 PostgreSQL 검사: 무인증/무효·폐기 Credential/기기·Project scope/사칭 reviewer의 actor 분리/교차 Project 참조/임의 asset 경로/과대 payload/중복 JSON key/MIME/변조 SHA/DB 중단 safe503/transaction rollback/asset 저장 실패/동시 요청. localhost 외 HTTP, URL userinfo/query/fragment/path, redirects와 환경 proxy를 차단하고 HTTPS TLS 검증을 유지한다.

감사 이벤트는 인증 실패/거부/credential/grant/sync 접수·성공·충돌/asset/admin 조회를 DB에 기록한다. Credential, source 절대경로, 원본 pixel array를 일반 로그에 기록하지 않는다. 오류에 내부 SQL/파일 경로를 반환하지 않는다. API docs/OpenAPI도 ADMIN 인증이 필요하다. OS private ACL과 secret bind 읽기를 실제 확인했다.

## Backup / Restore

`acceptance-v1`: API 일시 중지→pg_dump custom + PNG tar + asset digest/DB reference inventory + file SHA manifest→API 재시작. 외부 클라우드 업로드 없음. 새 `xrt-restore-td106`의 빈 PostgreSQL/별도 volume/API18767로 실제 복원했다. archive path/type/size/PNG SHA/DB asset reference를 검증한다.

복원 직후 모든 9개 엔터티의 payload/actor/device/시각까지 해시 동일, 관리자 statistics 동일, 실제 복원 PNG 2개의 SHA도 backup inventory와 동일했다. 이후 메인 서버의 새 QA 계정/Batch 추가는 해당 과거 backup snapshot과 비교 대상이 아니다.

복원 snapshot: project1/source5/run4/observation7,474/prediction7,474/instance35/geometry7,545/review16/provenance5/crop2. reviewed targets5/conflict targets2/HUMAN instance1/GT approved0. QA account 9명은 실제 연구원 운영 계정 수가 아니다.

## Local E2E Test / Multi-user Test / Offline Retry Test

실제 Windows QML 버튼으로 설정/연결/초기 동기화/동의 crop을 수행했다. 기존 4개 저장 Run을 열고 후보 검수→프로젝트 저장→실제 HTTP ACK→DB 조회→원본 과학 payload 일치를 검사했다. 새 ONNX 추론은 필요하지 않다.

서버 중지 중 새 검수를 로컬 저장했고 offline Batch를 같은 ID로 복구 후 ACK했다. 다른 RESEARCHER 계정/기기의 같은 대상 모순 판정은 별도 authenticated actor/local reviewer로 보존되고 충돌2, GT0이었다. crop app-close/restart 검사는 새 OS subprocess/native credential vault/동의 초기 OFF/Outbox receipt를 직접 확인했다.

비공개 증거는 ignored artifacts 아래 report/log/screenshot/backup에 보존했다. 저장소에는 실제 source 경로/이미지/model/credential/outbox를 올리지 않는다. 검증 도구는 `tools/validate_central_sync.py`, `tools/validate_central_sync_retry.py`이며 자동 실행이 아닌 명시적 private QA용이다.

## Performance / Capacity

Windows Python3.13.7 / Qt6.11.2 / Docker29.7.2 / PostgreSQL17 / FastAPI0.143.0 / SQLAlchemy2.0.54 / Alembic1.20.0. native GUI는 windows/basic/D3D11, 전체 회귀는 TD05와 동일 offscreen/basic. 실제 E2E 중 다른 heavy test가 일부 병행됐다.

| 측정 | 단회 실제 결과 | 조건 |
| --- | --- | --- |
| 전체 body | 13,484,919 bytes / 22,551 objects | 저장된 기존 4 Runs + 검수9 |
| 첫 빈 server E2E v2 | 9.90s | 단회, 초기 수집 |
| v4 전체 sync | 12.72s | core entity가 앞선 QA로 이미 존재 |
| v4 반복 sync | 7.06s | ACK/inventory 처리 |
| 신규 Review delta | 2,392,324 bytes | 신규 body + 전체 inventory |
| v4 crop128 | 4.72s | full source SHA 포함 |
| Qt5ms timer 최대 간격 | 230.98ms | 동시 heavy regression, 단회 |

UI worker async 경로가 동작하나 CPU/GIL serialization 및 동시 작업으로 timer 지연이 관측됐다. 무차단/0ms/FPS 개선을 주장하지 않는다. 반복 성능 baseline이나 외부망 throughput 판정은 아니다. 향후 용량 증가 시 chunked protocol/process 분리를 별도 검증한다.

## Real JPG Validation

2개 Full Runs 각각 2,946 candidates (BPD245/TED1,398/TSD1,303), 2개 ROI Runs 각각791 (BPD3/TED779/TSD9). 7,474 전체 Candidate ID/Coordinate/RawScores/ModelVersion/Prediction/Geometry와 서버 projection이 일치했다. 4 Runs의 legacy export byte 동일, source JPG/model/manifest/input project SHA 보존. 모델 추론 0회 계측은 최종 retry 도구의 pipeline.start guard로 별도 확인한다.

## TIFF 4 Files Validation

N119 3072×3012/158, No107 before/after 2922×2895/156, No22 2944×2745/156, 모두 uint16. 기존 실제 ImageJ/Fiji 회귀와 Stack 탐색을 유지했다. 최종 첫/중간/마지막 raw 픽셀 대조 결과는 마지막 완료 기록에 추가한다. 원본 SHA는 선행 TD05 reference와 비교한다. TIFF JPG 검수/Crop 차단, 자동 분석/전체 원본 업로드 없음.

## Windows Full Tests / PostgreSQL Integration Tests / GitHub CI

- 최종 Windows 전체: **574 PASS / 기존 5 SKIP, 849.15s**, offscreen/basic, 임시파일 D. 새 skip 없음.
- Native AWT/Swing plugin: **4 PASS / 5 deselected, 24.71s**, windows/basic/D3D11.
- 실제 PostgreSQL integration: **33 PASS, 2.74s**, 전용 DB. TestClient httpx deprecation warning1은 기록하며 숨기지 않는다.
- Ruff/compileall/desktop wheel: **PASS**. 독립 server Docker build/runtime: **PASS**.
- Linux CI: desktop quality + native X11 plugin 및 별도 PostgreSQL17 job을 추가했다. 최종 head 결과는 완료 기록/PR에서 확정한다.

### 초기 실패와 해결 근거

실패 로그도 비공개 artifacts에 보존했다. 첫 전체 Windows 시도는 기존 Wand async test timeout1: 573 PASS/1 FAIL/기존5 SKIP,1484.59s. 기본 native/threaded 환경과 실제 TIFF QA 동시 실행 조건이었다. TD05의 offscreen/basic 전체 검사 조건으로 다시 실행하여574 PASS, native plugin은 별도 실제 windows 검사4 PASS였다. 테스트/timeout/skip/native dialog 코드를 바꾸지 않았다. 조건이 여러 개 바뀌었으므로 timeout 원인을 측정으로 확정했다고 주장하지 않는다.

실제 초기 수집은 canonical sorted key로 child Review가 parent보다 앞서 domain validation422가 났다. DAG topological validation 복원으로 payload를 변경하지 않고 수정, 부모/순환/누락 회귀 검사로 확인했다. 서버 fixture metadata 누락, QA observation source lookup 및 selection을 취소하여 crop 버튼이 비활성화된 helper 오류도 수정했다. pending batch fixture는 같은 snapshot을 재사용하도록 고쳤고 asset quota test는 해당 Project count를 검사하도록 고쳤다. TIFF helper의 파일 전환 대기는 frame path/page까지 확인하도록 강화했다. No107 Big-endian uint16을 native-endian numpy 타입과 직접 비교하던 QA 조건은 원본 byte order를 유지한 unsigned 2-byte 판정으로 수정했다. 최초 GitHub PostgreSQL job은 운영 URL 변수만 설정하여 전용 `_test` DB 명시 guard가32건을 차단했다(1 PASS/32 ERROR). CI를 XRT_TEST_DATABASE_URL로 수정했고 guard/테스트는 완화하지 않았다. 이는 실패를 PASS로 숨기거나 검사를 삭제한 것이 아니다.

## Known Limitations / Operational Readiness

- 현재 **로컬 개발/연구용 수집 서버**. 외부 Tunnel/HTTPS 연구원 PC 접속은 NOT DEPLOYED, 운영 승인 및 접근통제 acceptance 필요.
- 개인 검수는 학습 후보 데이터다. GT 승인/학습/추론/배포/양방향 merge 없음.
- Outbox/backup 연구 payload는 plaintext이며 OS ACL·기관 보관/암호화 정책 필요. API Credential만 native vault/DB hash에 보관한다.
- Source/root metadata immutable 정책으로 최초 sync 뒤 동일 ID rename/rehash는409. 명시적 metadata revision/reconciliation은 후속 단계다.
- 전체 inventory는 매번 전송, 32MiB/100k 계약 상한. delta라고 unlimited/memory-free가 아니다.
- 취소/종료는 이미 시작한 bounded HTTP/worker 완료를 기다릴 수 있다. 서버 commit 뒤 ACK 유실은 같은 ID로 복구한다.
- file write 뒤 DB commit 실패 시 참조 없는 PNG가 남을 수 있다. 권위 있는 asset/GT로 집계하지 않으며 future GC는 DB references를 대조해야 한다.
- SHA backup integrity는 signature/독립 승인 대체가 아니다. private backup 운영자와 ACL을 신뢰한다.
- Linux Compose의 secret 파일 uid/ACL 실사용은 별도 검증. Linux CI 서버 의존성 분리 결과와 구분한다.
- TD13 물리적 마우스 Native File Dialog acceptance는 선행 PENDING이며 이번 TD에서 완료했다고 주장하지 않는다. 기존 안정화 코드는 수정하지 않았다.

## Next TD

승인된 HTTPS/기관 접근통제·키 rotation·백업 보관 운영 acceptance, 명시적인 연구원 신원/검수 adjudication/GT 승인 계약, 용량 기반 chunked sync 및 worker profiling을 후속 검증한다. ML dataset 생성/재학습은 sic-xrt-ml 책임이며 이번 PR에서 구현하지 않는다.
