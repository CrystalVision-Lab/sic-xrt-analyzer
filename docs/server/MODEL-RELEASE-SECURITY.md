# Model Release 보안 및 신뢰 계약

## 서명과 Trust

`xrt_signed_model_release/v1` metadata의 정확한 필드 집합에 Ed25519 detached signature를 적용한다. UTF8, JSON sort_keys, separators=(',',':'), ensure_ascii=False, allow_nan=False를 canonical serialization으로 사용한다. 중복 JSON key, 비유한 숫자는 거부한다. schema, release_id/sequence, registry/candidate/model/version ID, Model/Manifest SHA·byte size, channel, artifact_identity, 앱 최소/최대 Version, RELEASED 상태, created_at/expires_at, signing_key_id, 변경 설명을 모두 서명한다.

다운로드 URL을 서버에서 전달받지 않는다. 인증된 origin과 고정 relative route + 안전한 Release ID를 사용한다. Artifact identity는 modelsha:manifestsha. origin은 로컬 Trust의 Registry ID·Key namespace에 결합한다. 서버가 응답한 공개키를 자동으로 신뢰하지 않는다.

Desktop packaged `model_updates/trusted-keys.json`의 초기 origins는 비어 있다. 첫 운영 서명키는 아직 발급하지 않았다. 관리자에게서 **별도 신뢰 경로**로 공개키를 배포하고 `SIC_XRT_MODEL_TRUST_FILE` 또는 패키지 Trust를 배포한다. 예제 형식:

```json
{"schema":"xrt_release_trust/v1","origins":{"http://127.0.0.1:18766":{"registry_id":"xrt-local-production","keys":{"<key-id>":{"public_key":"<base64 Ed25519 32-byte public key>","status":"TRUSTED"}}}}}
```

Private Key는 32-byte raw 파일, 공개키는 Base64 raw32bytes. 일회성 `key-create --output <new-directory> --key-id <id>`는 새 private/public 파일을 만든다. 개인 서명 관리자만 Private Key를 보관한다. 일반 API ADMIN 권한에는 키 접근이 포함되지 않는다. API에 Private Key·관리자 파일을 마운트하지 않는다. sign CLI는 네트워크 배포 작업을 하지 않는다.

키 교체: 새 ID로 생성 → 별도 검증 경로로 Desktop Trust에 새 공개키 추가 → 서버에 공개키 등록 → 새 Release를 새 키로 서명 → 관찰 → 필요 시 이전 키 revoke. 폐기 시 서버의 키 Event와 Desktop Trust의 status를 모두 REVOKED로 바꾼다. 신뢰 설정은 자동 다운로드하지 않는다. API DB를 복원해도 Private Key는 복원되지 않는다. 키 유출은 기존 Release 폐기·별도 Trust 배포·새 키 발급과 재서명이 필요하다.

## Replay와 오프라인

전역 sequence는 DB publish 시 max+1, unique로 직렬화한다. Desktop은 origin|channel 별 high water를 atomic state에 보존해 신규 다운로드 역행을 거부한다. 동일 Release 재설치는 Hash를 재검사하고 기존 디렉터리를 재사용한다. 원격의 낮은 sequence로 임의 되돌리기를 허용하지 않는다.

사용자 **이전 모델 복원**은 로컬에 이미 검증된 직전 모델만 다시 CPU 로딩하며 알려진 철회·키 폐기·파일 손상을 검사한다. high water를 낮추지 않는다. 운영자가 모든 사용자에게 이전 Artifact를 재배포하려면 새로운 높은 sequence와 새로운 버전/승인/서명을 사용한다. 같은 Candidate/channel의 중복 Release는 거부하므로 명시적인 새 버전 승인 절차가 필요하다.

신규 Release 유효기간14일, 현재 앱 지원0.1.0–0.1.0. 신규 다운로드는 시간과 앱 버전을 검사한다. 이미 설치된 모델의 오프라인 로딩은 서명 만료를 허용하지만 알려진 key/release 폐기와 Hash 손상은 거부한다. 서버에 접속하지 않은 동안 새로운 철회를 알아낼 수는 없다. 기본 자동 확인/다운로드/적용은 OFF. 업데이트 확인에서 unavailable 상태를 본 모델은 로컬에서도 사용 불가로 기록하며 기존/이전 검증 모델로 복구한다. 현재 Adapter는 실행 중에 제거하지 않고 다음 명시적 변경/재시작 때 사용 제한을 적용한다. 이 보수적 정책은 Dataset 검토 상태도 포함한다.

## ONNX·네트워크·파일 경계

ONNX를 `load_external_data=False`로 읽고 모든 nested Tensor의 external data, functions/training/control flow graph, custom domain, 과도한 노드를 거부한다. checker와 CPU ORT 실제 name/type/shape/dynamic batch, batch1/7의 유한 출력·합1을 검사한다. FrozenClassifier/v1의 RGB128+내부 local contrast 정책을 유지한다. 새 local contrast architecture는 실제 graph의 관련 연산 존재를 검사한다. 이 검사는 수학적 동등성 또는 연구 정확도의 증명이 아니며 검토된 ML provenance와 독립 평가가 추가로 필요하다.

검증은 disposable 프로세스에서45초, RSS2GiB, CPU thread2로 실행하고 Credential 환경변수를 전달하지 않는다. 외부 data URL/path는 해석하지 않는다. 로컬 CLI ADMIN 등록만 허용하고 persistent API에서 ONNX parser를 실행하지 않는다. 프로세스 제한은 완전한 OS sandbox가 아니다. ONNX/ORT native parser의 알려지지 않은 취약점이나 OS 전체 장애를 무조건 방지한다고 주장하지 않는다.

HTTP는 기존 Sync Credential vault를 공유하며 origin에는 userinfo/query/path가 없다. localhost HTTP, 외부 HTTPS만 허용한다. 환경 proxy/trust_env, redirect, compressed model response, 임의 외부 URL을 사용하지 않는다. 크기·시간·stream Hash·서명·상태를 검증한다. 취소는 수신 chunk 및 CPU 검증 대기에서도 검사한다. 요청 재시도는 새 staging부터 수동으로 시작한다. Range resume는 없다.

모델 AppData와 CAS 경로는 symlink/Windows junction을 거부한다. OS lock은 같은 설치 저장소의 동시 다운로드/포인터 변경을 거부한다. 검증된 staging rename 전에는 설치 모델로 표시하지 않는다. state는 fsync+atomic replace. 이전 모델을 먼저 지우지 않는다. 권한/디스크/상태 저장 오류는 기존 Adapter를 유지한다. 원자성은 동일 filesystem의 정상 동작을 전제로 하며 전원 장애·디스크 물리 손상에 대한 전체 filesystem transaction은 아니다.

보안 참고: [cryptography Ed25519](https://cryptography.io/en/46.0.4/hazmat/primitives/asymmetric/ed25519/), [ONNX External Data Security](https://onnx.ai/onnx/repo-docs/ExternalDataSecurity.html), [ONNX External Data](https://onnx.ai/onnx/repo-docs/ExternalData.html).
