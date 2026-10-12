# verified_xrt_dataset/v1 — 승인된 RGB 패치 Artifact 계약

Producer: Analyzer Issue #108 / Consumer: ML Issue #45. 다른 저장소의 소스를 가져오지 않고 이 버전·스키마·해시 계약으로 연결한다. Data Tools의 원본 식별자·좌표·데이터 타입 보존 계약을 확인했다. 이번 버전에는 TIFF 변환, Resize, Center Crop이 없어 추가 변환 Issue는 필요하지 않다.

## 정답 승인과 출처

개인 ReviewEvent와 ModelPrediction은 변경하지 않는다. ADMIN Credential만 Group Mapping과 Approval을 기록할 수 있다. 로컬 Reviewer ID는 서버 계정이 아니다. CURATOR 역할은 아직 없다. 이벤트는 UUID, revision, previous_event_id로 연결되며 현재 헤드를 지정하지 않으면 409다. PostgreSQL trigger가 이벤트·버전의 UPDATE/DELETE를 거부한다.

Approval 상태: PENDING / APPROVED / REJECTED / REVOKED / NEEDS_ADJUDICATION. 승인에는 현재 모든 검수 leaf ID, 명시적 BPD/TED/TSD 라벨, 사유가 필요하다. 불확실·미확정·존재하지 않는 결함은 제외한다. 충돌은 기본 제외하며 관리자가 모든 leaf를 확인하고 resolve_conflict=true와 판정 사유를 입력한 경우만 별도 adjudication으로 승인한다. 이 판정은 원래 검수 충돌 이력을 없애지 않는다.

Mapping에는 source_id/source_hash, 검증된 group_id/provider_group, wafer_id, before_after_group, duplicate_group, evaluation_only, 사용 권한, 출처와 evidence가 필요하다. 파일명으로 Wafer를 추정하지 않는다. wafer_id는 명시적으로 입력한 정규 십진 문자열 또는 null이며 `8`은 evaluation_only=true로만 허용한다. null Wafer라도 독립 촬영 그룹을 증거로 확인해야 한다. synthetic_fixture 출처는 후속 Mapping에서 real_research로 바꿀 수 없다. 실제 연구 자료에 사용 권한·독립성이 확인됐다는 관리자 증거가 필요하며 QA 이력을 전문가 정답으로 자동 승격하지 않는다.

서버는 Crop PNG의 SHA-256, 디코딩한 RGB pixel SHA-256, 128×128 크기, Source/Run/Target/Review 관계와 등록된 원본 hash를 재검사한다. 원본 JPG 전체가 서버에 없으므로 원본 픽셀과 Crop의 직접 대응·촬영 조건은 독립 검증하지 못한다. Source hash는 수집 시 원본 확인 결과와 연결한 식별자다. 관리자가 근거를 확인해야 한다.

## 파일 구성과 입력

```
manifest.json
eligibility-report.json
splits/train.jsonl
splits/validation.jsonl
splits/test.jsonl
images/<PNG-SHA256>.png
```

최대 4,096 samples/version, Crop 파일 최대 4 MiB, 정확히 RGB8 PNG 128×128. 그 외 크기는 PATCH_CONTRACT_MISMATCH로 제외하며 자동 리샘플링하지 않는다. Manifest 밖의 파일, 경로 탈출, symlink/junction, 손상·과대 이미지와 잘못된 SHA는 ML이 거부한다. 전송 중 실패한 반출에는 manifest를 마지막에 쓰므로 미완성 디렉터리는 로드할 수 없다.

class_mapping: {BPD:0,TED:1,TSD:2}. preprocessing_contract는 다음 객체와 정확히 일치해야 한다.

```json
{"shape":[3,128,128],"source":"uint8_RGB","conversion":"uint8_RGB_to_NCHW_div255","crop_policy":"exact_128_no_resize","local_contrast_inside_model":true}
```

`schema=verified_xrt_dataset`, `schema_version=1`. Manifest에는 dataset_id/version, created_at/by, project/source/review/approval/group ID inventory, seed, rows, files, split_class_counts, eligibility_report, readiness, dataset_hash, file_manifest_hash를 저장한다. Row에는 sample/project/asset/source/run/target/review ID, 승인 ID·revision·관리자·시각·사유·상태·검수 헤드 hash, Mapping ID·revision·evidence, class_label, source/crop/pixel SHA, source 크기, 원본 crop[x,y,128,128], image_path, ModelProvenance, 그룹 메타데이터, data_origin, 권한, evaluation_only, split/split_group_id, dHash를 저장한다.

Canonical JSON: UTF-8, ensure_ascii=false, sort_keys=true, separators=(",",":"), allow_nan=false. dataset_hash는 해당 필드만 제외한 전체 Manifest SHA-256. file_manifest_hash는 상대경로→PNG SHA dictionary의 canonical SHA-256. Manifest row는 sample_id 순서로 정렬하며 inventory는 정렬·중복 제거한다. JSONL은 Manifest의 해당 split row와 정확히 일치한다.

## 분할과 적격성

같은 source_hash, run_id, target_id, wafer_id, group_id, provider_group, before_after_group, duplicate_group, pixel_hash를 union한다. 원본 동일 이미지의 ROI는 분리하지 않는다. 64-bit grayscale dHash Hamming distance ≤4도 같은 그룹으로 합친다. 연결된 그룹은 함께 이동하며 어느 하나가 평가 전용이면 전체를 test에 둔다. exact pixel 중복은 하나만 포함하고 서로 다른 승인 라벨이 붙은 중복은 모두 DUPLICATE_LABEL_CONFLICT로 제외한다.

그룹은 seed와 정렬된 sample ID hash로 결정적으로 정렬한다. 비고정 그룹의 약 15%를 validation, 전체 그룹의 약 15%에서 고정 test 그룹 수를 뺀 수를 추가 test, 나머지를 train으로 배정한다(필요한 split은 최소 한 그룹). 작은 표본은 클래스별 비율이나 충분한 train을 보장하지 않으므로 적격성 검사를 통과하지 못할 수 있다. seed 변경은 새 버전을 요구한다.

실제 학습의 사전 최소 기준은 train 10/class, validation 5/class, test 5/class이며 각 split에 독립 그룹이 있어야 한다. 실무 통계적 충분성을 보장하는 기준은 아니며 향후 전문가 설계가 필요하다. 3개 클래스가 없는 split은 NOT_READY다. 합성 smoke에는 별도 명시 옵션과 전부 synthetic_fixture라는 조건에서만 1/class/split 기준을 사용한다.

## 철회와 로컬 반출

새 Review 헤드, 승인 철회·변경, Mapping 변경·권한 회수, 이미지 손상이 발생하면 기존 버전의 usage_status는 RESTRICTED가 된다. 이미 저장한 버전·라벨·파일은 변경하지 않는다. 새 승인을 확인한 새 버전을 생성한다. 새 반출은 RESTRICTED 버전에 대해 거부한다.

오프라인으로 이미 반출한 사본과 학습 결과를 서버가 원격 삭제하거나 자동 무효화할 수는 없다. 관리자는 학습·평가 시작 전 현재 버전의 usage_status를 다시 확인하고 승인 철회 시 사본 사용을 중단해야 한다. Artifact hash는 위변조 검출·재현성 수단이며 전문가 신원·원본 촬영 조건에 대한 디지털 서명이 아니다. ML은 신뢰하는 관리자가 반출한 버전만 소비한다.

외부 다운로드 API, 자동 전송, 모델 자동 교체는 없다. ADMIN 인증된 로컬 관리 도구로 지정한 private 폴더에 반출하며 감사 기록을 남긴다. Linux 출력은 0700 부모를 사용하고, Windows는 기존 private 폴더의 사용자 전용 ACL을 상속한다. 운영 DB 백업은 기존 pg_dump+PNG+SHA 도구로 수행하며 새 테이블도 dump에 포함된다.
