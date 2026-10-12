# Server API v1 / Sync Protocol 1

모든 요청은 `Authorization: Bearer <issued credential>`이 필요하다. POST는 `application/json`, 최대 32MiB. 외부 origin은 HTTPS 필수다. OpenAPI는 ADMIN이 `GET /api/v1/admin/openapi`로 조회한다. public `/docs`는 없다.

| Method / Path | 권한 / 동작 |
| --- | --- |
| GET `/health` | 인증된 기기와 실제 DB 상태 |
| GET `/sync/status` | 본인 기기의 최근 20 Batch |
| POST `/sync/batches` | 해당 Project membership, 원자적 초기/증분 수집 |
| GET `/sync/batches/{batch_id}` | 본인 actor/client Batch의 ACK |
| GET `/projects/{id}/summary` | Project scope, 실제 후보/검수/충돌/HUMAN/Asset 집계 |
| GET `/projects/{id}/entities/{kind}` | Project scope, payload + authenticated_actor_id/client_id/received_at |
| POST `/projects/{id}/crops` | Project + Crop permission + explicit consent |
| GET `/admin/statistics` | ADMIN, 실제 DB project/entities/review/audit 통계 |
| POST `/admin/users` | ADMIN, 사용자 + client 발급 (credential 한 번 반환) |
| POST `/admin/grants` | ADMIN, project membership/crops 설정 |
| POST `/admin/credentials/{id}/revoke` | ADMIN, credential 폐기 |
| POST `/admin/devices/{client_id}/credentials` | ADMIN, 같은 기기 새 credential 발급 |
| GET `/admin/openapi` | ADMIN, 인증된 OpenAPI schema |

모든 경로 앞에 `/api/v1`을 붙인다. entities kind는 image_sources/analysis_runs/observations/predictions/defect_instances/geometries/review_events/image_relationships/model_provenance다. 읽기 API는 임의 외부 JSON을 로컬 프로젝트에 병합하지 않는다.

## 관리자 요청 예시

```json
{"name":"Researcher A","role":"RESEARCHER","client_id":"device-a"}
```

`POST /admin/users` 응답의 user_id/client_id/credential_id/credential은 안전하게 저장한다. 이후:

```json
{"user_id":"issued-user-id","project_id":"local-project-uuid","crops":false}
```

`POST /admin/grants`로 권한을 설정한다. 이름 또는 Reviewer ID만으로 사용자 인증을 처리하지 않는다. 자동 Project 등록/권한 부여는 없다.

## Batch와 ACK

`sync.protocol.make_batch()`가 생성하는 실제 DTO 필드:

```json
{
  "sync_protocol_version":1,
  "batch_id":"unique-batch-id",
  "client_id":"device-a",
  "project_id":"project-id",
  "project_revision":12,
  "project_schema_version":"1.1.0",
  "project":{"project_id":"project-id","project_name":"Study","schema_version":"1.1.0","revision":12,"created_at":"timestamp","updated_at":"timestamp"},
  "entities":{"review_events":{"review-id":{"review_id":"review-id","parent_review_ids":[]}}},
  "inventory":{"review_events":{"review-id":"sha256"}},
  "snapshot_hash":"sha256",
  "payload_hash":"sha256"
}
```

위는 구조 설명용 발췌다. 실제 entities/inventory는 9개 kind 모두 있어야 하고 각 payload는 기존 도메인 전체 필드를 요구한다. encode는 UTF8, sorted keys, compact JSON, nonfinite 금지다. payload_hash는 자기 자신을 제외한 전체 canonical JSON, snapshot_hash는 project+inventory의 SHA256다. 누락된 부모/Source/Run/도형/모델을 ACK하지 않는다.

ACK는 batch_id/project_id/client_id/project_revision/payload_hash/snapshot_hash/inventory를 그대로 확인하고 `status: ACKNOWLEDGED`, accepted kind별 신규 수, received_at과 원본 루트 `project_snapshot`을 추가한다. 저장 트랜잭션 성공 전에 완료를 반환하지 않는다. 동일 요청은 같은 receipt, 같은 ID의 다른 내용은 409다. HTTP 성공만으로 Desktop 완료를 표시하지 않고 ACK 전체를 검증한다.

Project summary는 project_name/schema_version/created_at/updated_at/server_received_at 및 `source_version`을 제공한다. source_version은 기기별 마지막 확인 snapshot의 revision/hash/루트 metadata/수집 시각 목록이다. 여러 기기의 revision 숫자를 비교해 마지막 승자를 선택하지 않는다. 루트 metadata 추가 이전 QA snapshot은 없는 값을 null로 보존한다. 프로젝트 이름·created_at과 기존 Source metadata는 immutable이며 변경 충돌은 409다. Schema 1.0.0→1.1.0은 검수 의미를 보존하는 승격만 허용한다.

## Crop

`sync.client.make_crop()`는 `metadata`, `image_base64`(PNG), `consent:true`를 생성한다. metadata에는 source/run/target/type, 원본 crop_x/y/width/height, source_dtype/channels/hash, crop_hash/pixel_hash, linked_review_ids, ORIGINAL coordinate space, image/png MIME가 필요하다. filename/path 입력은 받지 않는다. 서버는 `asset_id = SHA256(canonical metadata)`, `crop_hash`, `status: ACKNOWLEDGED`를 반환한다.

## 오류·재시도

400 malformed/duplicate JSON; 401 인증; 403 project/device/role; 404 resource; 409 immutable/revision/storage/quota conflict; 413 oversized; 415 MIME; 422 contract; 503 DB/storage. 인증 실패·충돌·검증 거부를 네트워크 성공으로 표시하지 않는다. Desktop은 안전한 코드만 표시한다.

Transport는 connect 3초/read-write-pool 10초, 최대 3회, 0.25/0.5초 backoff다. network/502/503/504만 재시도한다. 취소는 worker token으로 확인하며 이미 시작한 HTTP block은 timeout 이내에 종료된다. 서버가 이미 commit했다면 취소가 이를 되돌리지 않는다. 이후 같은 Outbox Batch를 재전송하여 ACK를 확인한다. 앱 종료는 bounded worker 완료를 기다릴 수 있다.
