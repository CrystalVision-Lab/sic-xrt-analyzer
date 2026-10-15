# 인증·데이터 보호 및 운영 정책

## 접근 경계

Loopback 기본 배포는 인터넷 공개가 아니다. HTTP는 Desktop에서 literal `127.0.0.1`/`::1` origin에만 허용한다. 외부는 검증된 HTTPS만 가능하며 URL credential/query/fragment/path, redirect, 환경 proxy 자동 사용은 거부한다. PostgreSQL 호스트 포트를 공개하지 않는다. Cloudflare Tunnel도 애플리케이션 인증을 대체하지 않는다.

관리자 일회성 bootstrap은 ADMIN이 없는 DB에서만 가능하다. 사용자와 기기는 고유 random 256-bit API Credential을 사용한다. DB에는 SHA256 검증값만 저장하고 원문은 발급 시 한 번만 반환한다. 관리자 역할, 활성 사용자, 유효 Credential, 기기, 프로젝트 membership, Crop 권한을 각각 확인한다. Reviewer ID는 로컬 주장으로 보존하며 authenticated actor/device와 분리한다. Reviewer 이름을 입력하여 관리자 권한을 얻을 수 없다. Credential 재발급 전 기존 Credential을 명시적으로 revoke한다.

Windows Desktop은 native keyring OS Credential Vault를 사용한다. QSettings/Outbox/로그에 credential을 넣지 않는다. 허용 OS backend가 없으면 평문 fallback 없이 오류를 표시한다. `pip install -e ".[sync]"`로 의존성을 설치한다.

## 비밀과 로그

`artifacts/sync106-private/`는 현재 Windows 사용자·SYSTEM·Administrators만 허용하는 전용 폴더다. `server_ops.py init`은 이 폴더만 ACL을 조정한다. 생성 후 bootstrap 파일도 동일 접근 경계를 유지한다. 운영자는 Windows ACL과 Docker mount 읽기를 확인한다. Linux에서는 폴더 0700, 비밀 파일 0600을 사용한다.

API는 인증 없는 health/docs/관리자 정보 조회를 허용하지 않는다. 오류에 SQL·호스트 경로·Credential을 반환하지 않는다. Uvicorn access log는 비활성화한다. 감사 DB는 인증 실패, 접근 거부, 검증 거부, Batch 접수/성공/충돌, Credential 등록/폐기/재발급, 관리자 작업, Asset 업로드를 기록한다. DB 자체가 사용 불가하면 감사 쓰기도 실패할 수 있다. 실패 응답은 503이며 정상 수집으로 처리하지 않는다.

Outbox, QA 캡처, 백업에는 연구 데이터와 검수자 식별자가 있다. Git에 넣지 않는다. 전용 접근 제한 디렉터리에 보관한다. 로컬 OS 관리자와 Docker 관리자 권한은 전체 DB/볼륨에 접근 가능한 운영 경계이며 API 역할만으로 이를 차단하지 않는다.

## 검증과 한계

중복 JSON key, nonfinite number, unknown DTO field, unsupported schema, ID/hash/size/MIME/Source/Run/Target/parent/Geometry/Model 관계를 검증한다. 같은 불변 객체 ID를 다른 내용으로 보내면 409다. Crop은 raw PNG 및 RGB pixels 해시를 서버에서 재계산한다. 서버에 원본 전체 파일이 없으므로 클라이언트가 주장한 원본 SHA와 Crop의 출처를 독립적으로 대조할 수는 없다. 이 데이터는 수집된 연구 사본이며 인증만으로 모델 또는 Ground Truth를 승인하지 않는다.

이번 API는 adjudicated label/ground_truth_eligible 입력을 승인하지 않는다. 검수 이벤트 개수·고유 대상·충돌·HUMAN 객체를 각각 집계한다. 학습·모델 다운로드·학습 승인 기능은 없다.

Backup은 로컬 운영자만 실행하고 외부 클라우드로 자동 전송하지 않는다. DB credential hashes와 식별자가 포함되므로 private folder 안에 보관한다. SHA manifest는 손상 검출용이며 전자 서명은 아니다. 신뢰할 수 있는 운영자 백업만 복원한다. 보관 기간/담당자/오프라인 암호화·키 복구 정책은 연구소 운영자가 확정해야 한다. 무제한 외부 운영·다수 악성 사용자에 대한 rate limiting/배포 hardening은 이번 localhost acceptance와 별도다.
