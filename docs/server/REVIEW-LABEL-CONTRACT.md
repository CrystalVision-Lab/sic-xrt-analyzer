# 후보 검수 라벨 계약 — `review_label/v1` (#179)

데스크톱 "빠른 검수"에서 연구원이 내린 판정 하나가 이벤트 하나입니다. 이벤트는 이 PC의 outbox(SQLite)에 먼저 저장한 뒤 연구 서버로 보냅니다. 서버는 받은 이벤트를 **추가만** 하고 수정·삭제하지 않습니다(DB 트리거로 강제).

## 판정 값

| 값 | 뜻 | 키 |
|---|---|---|
| `BPD` / `TED` / `TSD` | 이 종류의 결함이다. 모델 예측과 같으면 수락, 다르면 정정 | 1 / 2 / 3, Space(모델 분류 수락) |
| `NOT_DEFECT` | 결함이 아니다. 재학습에 쓰는 negative(background) 라벨 | 0, X |
| `UNSURE` | 판단할 수 없다. 학습에 쓰지 않음 | S |
| `RETRACTED` | 이전 판정 취소(실행 취소). `parent_event_id` 필수 | Z |

판정을 바꾸면 이전 이벤트를 `parent_event_id`로 가리키는 새 이벤트가 쌓입니다. `RETRACTED`는 자신이 가리키는 이벤트 하나만 무효로 만듭니다. 그래서 실행 취소를 하면 바로 앞의 판정이 다시 유효해집니다. 이 해석은 `sic_xrt_analyzer.sync.labels.resolve`가 맡고, 데스크톱과 서버가 같은 함수를 씁니다.

## 이벤트 필드

```
schema            "review_label/v1"
event_id          UUID4 (멱등 키)
parent_event_id   이전 판정 UUID 또는 null
session_id        검수 세션 UUID
created_at        ISO-8601 UTC
reviewer          사용자가 입력한 표시 이름. 서버의 인증된 actor와 별개로 보관
source            {sha256, width, height, page}  원본 파일 SHA-256, 원본 픽셀 크기
run_id            분석 실행 ID
model             {version: 모델 ID, sha256: 모델 파일 SHA-256 또는 ""}
candidate         {id, x, y(원본 픽셀), predicted: BPD|TED|TSD|"", scores: [BPD,TED,TSD] 또는 []}
decision          위 표의 값
mode              key | batch_explicit | batch_implicit(페이지 일괄 확정)
queue             {kind: uncertain|class|random|list, seed: 무작위 표본 seed 또는 null, rank}
dwell_ms          후보가 표시된 뒤 판정까지 걸린 시간
crop              null 또는 {rect:[x,y,w,h], png(base64), sha256}  ≤128×128 원본 픽셀, ≤96 KiB
```

- `crop`은 사용자가 검수 화면에서 "128px 원본 조각을 함께 보내기"를 켠 경우에만 포함합니다. 기본값은 꺼짐입니다.
- 원본 전체 이미지와 모델 파일은 보내지 않습니다.
- `queue.kind = random`은 원본 SHA에서 유도한 고정 seed로 뽑은 50개 표본입니다. 사람이 고른 순서에 따른 선택 편향 없이 모델 정확도를 추정하는 데 씁니다.
- `batch_implicit`은 "이 페이지 모델대로 확정"으로 기록된 라벨입니다. 학습에서는 가중치를 낮추거나 제외할 수 있도록 구분해 둡니다.

## 서버 API

| 경로 | 권한 | 내용 |
|---|---|---|
| `POST /api/v1/labels/batches` | 등록된 연구원 기기 | `{"schema":"review_label_batch/v1","labels":[…]}`, 1–100건. 응답 `{status:"ACKNOWLEDGED", accepted, receipts:[{event_id,payload_hash}]}` |
| `GET /api/v1/admin/labels/summary` | ADMIN | 유효 판정 수(클래스·결함 아님·보류), 예측×판정 혼동표, 모델 일치율, 무작위 표본 일치율, 주별 처리량, 연구원별 활동, 연구원 간 충돌 |

- 같은 `event_id`를 같은 내용으로 다시 보내면 성공으로 응답하고 행을 추가하지 않습니다(전송 확인이 유실된 뒤의 재시도).
- 내용이 다르거나 다른 사용자가 같은 ID를 쓰면 `409 LABEL_ID_CONFLICT`를 돌려줍니다.
- 포털 BFF는 `admin/labels/summary`를 읽기 전용 허용 목록에 포함합니다(관리자 대시보드용).

## 저장과 호환성

- **DB**: Alembic `0004`가 `review_labels` 테이블과 append-only 트리거를 만듭니다. `0001`의 일괄 생성 목록에서는 이 테이블을 제외했습니다. 이미 `0001`–`0003`을 적용한 운영 DB에서는 `0004`만 실행되므로 기존 데이터에 영향이 없습니다.
- **기존 계약과의 관계**
  - 프로젝트 동기화(`/sync/batches`), `xrt_correction/v1` 신고, `verified_xrt_dataset/v1` 반출은 바꾸지 않았습니다.
  - 기존 결과 패널의 확인/보류 기록(`area-review`)은 그대로 로컬에만 남습니다.
- **데스크톱 outbox**: 설정 폴더의 `labels/labels.sqlite3`에 저장합니다(`SIC_XRT_LABEL_DIR`로 변경 가능). 전송에 실패한 이벤트는 그대로 남아 다시 보낼 수 있습니다.

## 남은 작업

- `verified_xrt_dataset` v2 반출은 #189에서 구현했습니다. 합의 규칙, background 클래스, 분할, API는 [VERIFIED-DATASET-V2-CONTRACT.md](VERIFIED-DATASET-V2-CONTRACT.md)를 봅니다. 학습 쪽 소비 변경은 `sic-xrt-ml` 저장소의 별도 Issue로 요청합니다.
- 웹 관리자 "라벨 데이터 현황" 대시보드(`admin/labels/summary` 사용)
- 저장된 프로젝트 결과에서 검수 큐 열기, 위치 수정·누락 결함 추가
