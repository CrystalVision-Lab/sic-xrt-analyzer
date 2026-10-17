# verified_xrt_dataset/v2 — 검수 라벨 합의 데이터셋 계약 (#189)

Producer: Analyzer `server/xrt_server/label_datasets.py`. Consumer: sic-xrt-ml(별도 Issue). 다른 저장소의 소스를 가져오지 않고 이 문서의 버전·스키마·해시로 연결합니다.

`review_label/v1`(빠른 검수, [REVIEW-LABEL-CONTRACT.md](REVIEW-LABEL-CONTRACT.md)) 이벤트를 후보별 합의 라벨로 정리해 반출합니다. `verified_xrt_dataset/v1`(관리자 승인 기반 RGB 패치, [VERIFIED-DATASET-CONTRACT.md](VERIFIED-DATASET-CONTRACT.md))은 **그대로 유지**하며 테이블·API·파일 구성도 따로 둡니다.

## 이름을 v2로 정한 이유

`review_label_dataset/v1`이라는 별도 이름도 검토했습니다. 그래도 `schema=verified_xrt_dataset`, `schema_version=2`를 택했습니다.

- 학습 쪽 입장에서는 같은 "패치 + 클래스 라벨 + 원본 단위 split" 데이터셋입니다. 로더 하나가 `schema_version`으로 분기하면 됩니다.
- 기존 v1 로더는 `schema_version == 1`만 받습니다. 따라서 v2 manifest를 실수로 v1로 읽는 일이 없습니다.
- "verified"의 근거는 v1과 다릅니다. v1은 관리자 1인의 승인이고, v2는 검수자 합의입니다. 이 차이는 `label_schema="review_label/v1"`과 `parameters` 필드로 manifest에 명시합니다.

## 합의 규칙

1. **검수자별 유효 판정**
   - 서버 인증 계정(actor) 기준으로 후보마다 유효 판정을 하나씩 정합니다.
   - 해석은 데스크톱과 같은 `sic_xrt_analyzer.sync.labels.resolve()`가 맡습니다. 그래서 `RETRACTED`를 하면 바로 앞 판정이 복원됩니다.
   - 후보 키는 `(source_sha256, page, candidate_id)`입니다.
2. **투표**
   - `BPD`/`TED`/`TSD`/`NOT_DEFECT`만 투표합니다. `UNSURE`는 투표하지 않고 `n_unsure`로만 셉니다.
   - `mode=batch_implicit`("이 페이지 모델대로 확정") 표는 가중치 `implicit_weight`(0–1, 기본 1)를 받습니다. 0이면 표에서 빠집니다.
3. **채택**
   - `majority`(기본): 최다 득표 라벨이 하나이고 가중 득표가 전체의 절반을 넘으면 채택합니다.
   - `unanimous`: 의견이 하나라도 다르면 제외합니다.
4. **제외와 충돌**
   - 동률은 `TIE`, 과반 미달은 `NO_MAJORITY`, 만장일치 위반은 `DISAGREEMENT`입니다. 이 경우 표본에서 빼고 `conflicts`에 득표 수와 이벤트 ID를 남깁니다.
   - 다음 사유는 `excluded`와 `exclusion_counts`에 기록합니다.
     - `UNSURE_ONLY`
     - `IMPLICIT_EXCLUDED`
     - `BELOW_MIN_REVIEWERS`: 투표자가 `min_reviewers`(기본 1)보다 적음
     - `CONFLICT_*`
     - `USE_RIGHTS_MISSING`: v1 Group Mapping에서 `training_use_authorized=false`
     - `DUPLICATE_PIXELS`
     - `DUPLICATE_LABEL_CONFLICT`
5. **표본 가중치**: `weight`는 채택 라벨에 투표한 표 가운데 가장 큰 가중치입니다. 명시 판정이 하나라도 있으면 1이고, `batch_implicit` 표만 있으면 `implicit_weight`입니다.

## 클래스 매핑

```json
{"BPD":0,"TED":1,"TSD":2,"NOT_DEFECT":3}
```

- v1 인덱스와 모델 점수 순서 `[BPD,TED,TSD]`를 그대로 두고, background를 3으로 덧붙였습니다.
- manifest의 `background_class="NOT_DEFECT"`이고, 각 행에 `is_background`가 있습니다.

## 표본(row) 필드

| 필드 | 내용 |
|---|---|
| `sample_id` | canonical JSON `[source_sha256, page, candidate_id]`의 SHA-256 |
| `source_sha256`, `page`, `candidate_id`, `x`, `y`, `source_width`, `source_height` | 원본 식별과 원본 픽셀 좌표 |
| `label`, `class_index`, `is_background`, `weight` | 합의 결과 |
| `n_reviewers`, `n_unsure`, `agreement`, `votes` | 투표자 수, 보류 수, 채택 라벨 득표율(0–1), 라벨별 표 수 |
| `modes`, `batch_implicit_only` | 유효 판정의 입력 방식 |
| `queue_kinds`, `random_sample`, `random_seeds` | 검수 큐 종류. 무작위 표본(편향 없는 정확도 추정용) 여부와 seed |
| `predicted`, `scores`, `model_version`, `model_sha256`, `model_agrees`, `model_predictions` | 검수 당시 모델 예측. 대표 판정 기준이며, 검수자별로 다르면 `model_predictions`에 모두 기록 |
| `crop` | `null` 또는 `{sha256, rect:[x,y,w,h], event_id, image_path, pixel_hash, dhash}` |
| `reviewer_ids`, `effective_event_ids`, `history_event_ids` | 출처. 서버 계정 ID, 유효 판정 이벤트, 취소를 포함한 전체 이벤트 |
| `split`, `split_group_id`, `evaluation_only`, `group_mapping_ids`, `data_origin`, `wafer_id` | 분할과 v1 Group Mapping(있을 때만) |

### crop 계약

```json
{"format":"png","dtype":"uint8","modes":["L","RGB"],"max_edge":128,"geometry":"original_pixels_centered_shifted_inside_source","resize":"none"}
```

- 검수자가 동의한 경우에만 라벨 이벤트에 포함된 원본 픽셀 조각입니다. 리샘플링하지 않습니다.
- 원본이 128px보다 작으면 조각도 작아집니다. 회색(L) 또는 RGB이므로, **v1의 정확한 RGB 128×128 계약과 다릅니다.**
- 파일 이름은 PNG SHA-256입니다(content-addressed). 같은 후보에 조각이 여러 개면 가장 많이 나온 것, 그다음 SHA 순으로 하나를 고릅니다.
- 조각이 없는 표본도 포함하며 `crop_coverage`로 비율을 표시합니다. 학습 쪽은 조각이 없는 표본을 건너뛰거나, 원본 TIFF에서 `rect`로 직접 잘라야 합니다.

## 분할과 누수 방지

- **원본 단위로 분할합니다.** 같은 `source_sha256`의 표본은 항상 같은 split에 들어갑니다.
- 다음 원본들은 하나의 성분으로 묶습니다.
  - v1 Group Mapping의 `group_id`, `wafer_id`, `provider_group`, `before_after_group`, `duplicate_group`를 공유하는 원본
  - 같은 crop 픽셀(`pixel_hash`)을 가진 원본
  - crop dHash Hamming 거리가 4 이하인 원본. 단 회색 표준편차가 2 미만인 평탄한 조각은 dHash 비교에서 뺍니다(배경 조각 때문에 전체가 하나로 합쳐지는 것을 막기 위함).
- 성분은 `sha256(canonical({seed, source: 성분 내 최소 source_sha256}))`의 앞 48비트로 정합니다. 값이 0.15 미만이면 validation, 0.30 미만이면 test, 나머지는 train입니다.
  - v1과 달리 순위가 아니라 해시로 배정합니다. 그래서 데이터가 늘어도 기존 원본의 split이 바뀌지 않습니다(성분이 합쳐지는 경우는 예외).
- `evaluation_only` 매핑(예: Wafer 8)이 하나라도 있는 성분은 test에 고정합니다.
- 중복 제거보다 연결 계산을 먼저 합니다(v1과 같은 원칙).
- `readiness`
  - `READY`: 4개 클래스 모두 train 10, validation 5, test 5 이상
  - 그 밖에는 `DATA_NOT_READY`

## 버전·해시·불변성

- **manifest 필드**
  - `schema`, `schema_version=2`, `label_schema`
  - `parameters` `{seed, min_reviewers, consensus, implicit_weight, received_before}`
  - `label_events`, `label_event_set_hash`
  - `class_mapping`, `background_class`, `crop_contract`, `split_policy`
  - `included_source_sha256`, `split_group_ids`, `rows`, `files`, `file_manifest_hash`, `split_class_counts`
  - `conflicts`, `conflict_counts`, `excluded`, `exclusion_counts`, `crop_coverage`, `readiness`
  - `dataset_id`, `dataset_version`, `created_at`, `created_by`, `content_hash`, `dataset_hash`
- **해시**: Canonical JSON(UTF-8, ensure_ascii=false, sort_keys, separators=(",",":"), allow_nan=false)을 씁니다.
  - `dataset_hash`: `dataset_hash`를 뺀 manifest 전체의 SHA-256
  - `content_hash`: id·버전 이름·생성 시각·생성자·두 해시를 뺀 내용의 SHA-256
  - `label_event_set_hash`: 기준 시각 이전 `[event_id, payload_hash]` 정렬 목록의 SHA-256
- **기준 시각 `received_before`**: 서버가 라벨을 받은 시각 기준입니다.
  - 생략하면 생성 시각에서 60초를 뺀 값을 씁니다.
  - 지정할 때도 현재보다 60초 이상 과거여야 합니다. 늦게 커밋된 라벨이 기준 시각 이전으로 끼어드는 것을 막기 위해서입니다.
- **저장**: `label_dataset_versions` 테이블(Alembic `0005`)에 저장하고, append-only 트리거로 UPDATE와 DELETE를 막습니다. `0001`의 일괄 생성 목록에서는 이 테이블을 제외했습니다.
- **멱등 생성**
  - 같은 `version`에 같은 파라미터로 다시 요청하면, 저장된 기준 시각으로 다시 계산합니다. `content_hash`가 같으면 기존 버전을 돌려줍니다(`created:false`).
  - 파라미터나 내용이 다르면 `409 DATASET_VERSION_EXISTS`입니다.
- **사용 상태 `usage_status`**
  - 다음 중 하나에 해당하면 `RESTRICTED`가 됩니다.
    - 기준 시각 이전 이벤트 집합이 바뀜(`LABEL_SET_CHANGED`)
    - 이후 판정이나 사용 권한 변경으로 포함된 표본의 현재 합의 라벨이 달라짐(`LABEL_CHANGED`)
  - 저장된 버전은 바뀌지 않습니다. 새 버전을 만들어야 합니다.
  - `new_samples_available`, `labels_since_cutoff`로 새 버전이 필요한지 판단할 수 있습니다.

## API와 반출

| 경로 | 권한 | 내용 |
|---|---|---|
| `GET /api/v1/admin/label-datasets/preview?seed&min_reviewers&consensus&implicit_weight&received_before` | ADMIN | 저장하지 않는 미리보기. rows·files·excluded 없이 집계와 conflicts |
| `POST /api/v1/admin/label-datasets` | ADMIN | `{version, seed?, min_reviewers?, consensus?, implicit_weight?, received_before?}` → 요약 `{created, dataset_id, dataset_hash, content_hash, samples, …}` |
| `GET /api/v1/admin/label-datasets` | ADMIN | 버전 목록, 사용 상태 |
| `GET /api/v1/admin/label-datasets/{id}` | ADMIN | `{manifest, usage_status, …}` |
| `GET /api/v1/admin/label-datasets/{id}/samples?split&label&offset&limit` | ADMIN | 표본 페이지(최대 500) |

- 포털 BFF는 위 GET 경로를 읽기 전용 허용 목록에 넣었습니다. 생성(POST)은 v1처럼 ADMIN 자격 증명으로 연구 서버 API를 직접 호출합니다.
- **이미지 다운로드 경로는 없습니다(v1과 같음).** 파일 반출은 로컬 관리 도구로만 합니다.

```
python -m xrt_server.label_dataset_admin --credential-file <private.json> --dataset-id <id> --output <새 private 폴더>
```

반출 폴더는 다음과 같습니다. `manifest.json`은 마지막에 씁니다.

```
manifest.json
consensus-report.json    {conflicts, conflict_counts, excluded, exclusion_counts, parameters}
splits/train.jsonl | validation.jsonl | test.jsonl
images/<PNG-SHA256>.png
```

- crop은 DB의 라벨 이벤트 payload에서 꺼내 SHA-256을 다시 확인한 뒤 씁니다.
- `RESTRICTED` 버전은 반출을 거부합니다(409).
- 표본은 버전당 최대 20,000개입니다.

## 호환성 영향

- **v1**: `dataset_versions`, `/api/v1/admin/datasets*`, `dataset_admin`, v1 manifest는 바뀌지 않습니다. ModelCandidate의 `dataset_id` FK도 v1 테이블만 가리킵니다. v2로 학습한 모델을 레지스트리에 등록하는 일은 후속 작업입니다.
- **review_label/v1**: 바뀌지 않습니다. 이 기능은 읽기만 합니다.
- **DB**: `0005`만 추가됩니다. 운영 DB에는 빈 테이블 하나가 생기며 기존 데이터에는 영향이 없습니다. 기존 pg_dump 백업에 함께 포함됩니다.
- **ML(sic-xrt-ml)**: v2를 소비하려면 로더 변경이 필요합니다(별도 Issue).
  - `schema_version` 분기
  - 4클래스 헤드(`NOT_DEFECT=3`)
  - `weight` 적용
  - 크기와 모드가 다른 crop 처리(패딩, 또는 TIFF에서 다시 잘라내기)
  - `random_sample` 표본으로 편향 없는 정확도 평가
  - 학습 전 `usage_status`가 `AVAILABLE`인지 확인
