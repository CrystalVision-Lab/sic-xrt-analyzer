# 중앙 연구 서버 아키텍처

## 데이터 흐름

저장된 ProjectStore → Sync Projection v1 → 영속 SQLite Outbox → 인증된 HTTP → FastAPI → PostgreSQL → ACK → Outbox Receipt. 로컬 ProjectStore가 과학적 기록의 원본이다. 서버 상태를 로컬 예측·도형·검수에 덮어쓰지 않는다.

- Desktop: `sync/{protocol,client,credentials}.py`, `ui/sync_controller.py`, `SyncPanel.qml`. 네트워크·디스크 스냅샷·Crop 작업은 LatestReader worker에서 수행한다. 자동 업로드는 OFF다.
- Server: `server/xrt_server/`. FastAPI, SQLAlchemy 2, psycopg, PostgreSQL 17, Alembic. GUI, Java, Fiji, ONNX 모델을 설치하거나 실행하지 않는다.
- Compose: API만 `127.0.0.1:18766`에 바인딩한다. PostgreSQL 포트는 호스트에 공개하지 않는다. DB와 PNG는 별도 named volume에 보관한다.
- 운영: `tools/server_ops.py`. 별도 복원 스택을 만들고 원래 볼륨을 보존한다.

## 계약과 출처

Project Schema 1.0.0/1.1.0, Sync Protocol 1, Server API v1은 서로 다른 버전이다. 기존 1.0.0의 검수 의미를 1.1.0으로 암묵적으로 바꾸지 않는다.

9개 엔터티 계층을 별도 테이블에 저장한다: ImageSource, AnalysisRun, CandidateObservation, ModelPrediction, DefectInstance, Geometry, ReviewEvent, ImageRelationship, ModelProvenance. `(project_id, entity_id)`와 payload digest로 불변성을 검사한다. 원본 과학적 구조는 JSONB에 보존하고 Source/Run/Geometry/Target/Provenance 관계 열을 색인한다. 서버 사용자·기기·권한·Batch·Receipt·Asset·Audit는 별도 테이블이다.

Projection은 절대 원본 경로, acquisition metadata, wafer placement 및 로컬 참조 경로를 제외한다. 파일명, 원본 크기/타입/역할/파일 크기/mtime, 검증된 SHA, 후보 좌표, raw scores, 도형, 검수 원본 판정/부모/수정 도형, 모델 SHA 및 허용된 scientific parameters/provenance를 전달한다. TD02의 opaque ID mapping도 보존한다. MASK_REFERENCE는 참조/encoding을 보존하며 mask blob을 자동 업로드하지 않는다. 로컬 원본 프로젝트를 이 DTO에서 복원한다고 주장하지 않는다. 서버는 로컬 파일 경로를 열지 않는다.

JSON 객체/SQL 결과 순서는 기록 순서가 아니므로 검수는 부모 DAG 순서로 재구성하여 기존 도메인 검증을 수행한다. 각 이벤트 내용과 부모 ID는 변경하지 않는다. 누락 부모·중복 부모·순환·다른 검수자/대상 부모는 거부한다.

## 전송·충돌

처음에는 전체 엔터티, 이후에는 ACK inventory와 달라진 객체만 전송한다. 증분 요청에도 전체 ID→SHA inventory가 포함된다. 최대 요청 32MiB, 최대 inventory 100,000객체다. 초대형 프로젝트의 chunk protocol은 후속 범위다.

PostgreSQL 트랜잭션 advisory lock으로 동시 Batch/Project 요청을 직렬화한다. 전체 참조 검증 후 엔터티·Receipt·감사를 같은 트랜잭션으로 저장한다. 동일 Batch/객체 ID의 동일 내용은 중복 저장하지 않는다. 다른 내용은 409다. 동일 기기의 같은 revision에서 분기되거나 더 오래된 미확인 revision은 409다. 다른 기기의 독립적 새 검수 이벤트는 공존한다. Last Write Wins와 양방향 병합은 없다.

프로젝트 이름/생성 시각과 이미 동기화한 Source 등도 불변 정책에 포함된다. 같은 ID의 원본 SHA/metadata를 바꾸면 자동 갱신하지 않고 충돌한다. 첫 동기화 전에 JPG Source SHA를 확정해야 한다. 서버 Project payload는 최초 수집 root 및 지원 schema를 보관하며 기기별 revision/updated_at은 Batch receipt의 project_snapshot으로 조회한다. Project summary의 source_version은 기기별 확인된 최신 snapshot 목록이며 단일 최신 revision을 자동 채택하지 않는다. 기존 초기 실험 Batch의 미기록 snapshot metadata는 null로 명시한다.

Outbox는 immutable payload, PENDING/SENT/RETRY/ACKNOWLEDGED, delivery cycle 횟수, 안전한 오류 코드와 ACK를 저장한다. ACK의 ID/기기/프로젝트/revision/hash/inventory가 정확히 일치해야 확인 처리한다. 재시작과 ACK 유실 때 같은 pending Batch ID를 다시 쓴다. Outbox는 연구 데이터와 Crop을 포함할 수 있는 민감한 로컬 전송 장부다.

## 국소 Crop

명시적 동의 + 프로젝트 Crop 권한 + 검수된 JPG 대상만 허용한다. 원본 파일 identity/SHA를 재검증한 뒤 RGB8 원본 픽셀을 crop하여 lossless PNG로 저장한다. EXIF 자동 회전·리사이즈·정규화·색상 변환·화면 캡처를 하지 않는다. PNG bytes SHA와 디코딩한 RGB pixels SHA를 각각 기록한다.

요청당 1개, 최대 1024×1024, PNG 4MiB, 프로젝트당 1,000 Asset records, 연결 검수 최대 100개. 전체 원본 영역, TIFF, bounds 밖, 다른 Source/Run/Target/Review 및 잘못된 MIME/SHA는 거부한다. SHA 기반 서버 파일명만 사용한다. 같은 PNG bytes는 공유 blob, 서로 다른 검수 연결은 별도 metadata Asset이다. 같은 pending Crop은 앱 재시작 후 명시적으로 같은 범위/대상에 동의하여 재시도한다. Metadata 동기화 버튼은 Crop을 자동 재전송하지 않는다. 전송 상태 확인 후 현재 프로젝트의 대기 Crop에 다시 동의하여 재전송할 수도 있다. 한 번의 명시적 작업은 최대 20개 pending Batch/Crop을 처리하며 잔여 큐가 있으면 완료 대신 재시도 필요 상태를 반환한다.

파일을 fsync/atomic replace한 후 DB를 commit한다. 저장 실패는 ACK하지 않는다. DB commit 직전 실패하면 참조되지 않은 blob이 남을 수 있으나 승인된 Asset으로 집계되지 않는다. 운영자는 임의 삭제하지 않고 후속 orphan GC에서 DB 참조·동시 요청을 검증해야 한다.
