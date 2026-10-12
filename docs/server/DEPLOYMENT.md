# Windows localhost 배포 및 백업

## 준비 및 시작

Docker Desktop Linux engine과 프로젝트의 `.venv`가 필요하다. PowerShell:

```powershell
Set-Location D:\capstone\sic-xrt-analyzer
.\.venv\Scripts\python.exe -m pip install -e ".[sync]"
.\.venv\Scripts\python.exe tools/server_ops.py init
.\.venv\Scripts\python.exe tools/server_ops.py start
.\.venv\Scripts\python.exe tools/server_ops.py status
.\.venv\Scripts\python.exe tools/server_ops.py migrate
.\.venv\Scripts\python.exe tools/server_ops.py bootstrap
```

API: `http://127.0.0.1:18766`. 기존 host port 충돌을 피하기 위해 8766 대신 18766을 사용한다. `XRT_API_PORT`, `XRT_PRIVATE_DIR`, `XRT_DB_PASSWORD_PATH`는 승인된 전용 경로로 설정할 수 있다. `.env.example`만 Git에 포함한다. 비밀은 `artifacts/sync106-private/db-password.txt`, bootstrap Credential은 같은 폴더 `admin.json`에 기록한다. 원문을 콘솔·Git·채팅에 출력하지 않는다. bootstrap은 이미 ADMIN이 있으면 거부한다.

API는 비특권 xrt 사용자, read-only root filesystem, `/tmp` tmpfs, no-new-privileges, 모든 Linux capabilities 제거를 사용한다. 비밀 password 파일은 read-only Docker secret bind mount이다. 전체 private 폴더는 bootstrap 일회성 컨테이너에만 마운트하며 상시 API에는 관리자 Credential·백업 폴더를 노출하지 않는다. ACL 변경 후 비특권 사용자 읽기와 API 정상 시작을 확인한다. DB/Asset named volume은 영속 유지된다.

## 연구원 등록과 Desktop

관리자가 private `admin.json`의 Credential을 사용해 인증된 `/admin/users`에서 RESEARCHER + 고유 client_id를 발급하고 `/admin/grants`에서 project UUID와 Crop 권한을 부여한다. 발급 응답은 private 파일/OS vault에만 저장한다. [API 예시](API.md)를 참고한다. 개인 Reviewer ID는 별도 로컬 식별자다.

Desktop 실행:

```powershell
.\.venv\Scripts\python.exe -m sic_xrt_analyzer
```

프로젝트 작업 영역 → 중앙 서버 → origin/client ID/Credential 입력 → 설정 저장 → 연결 테스트. 검수 확정과 프로젝트 디스크 저장 후 **서버와 동기화**를 누른다. 자동 전송은 OFF다. Crop은 검수 대상과 원본 범위 확인 후 별도 체크박스에 동의하여 전송한다. 서버 미설정/중단 상태에서도 로컬 검수·저장은 가능하다.

Outbox 기본 위치는 Qt AppLocalDataLocation/sync이다. D에 고정하려면 프로그램 실행 전:

```powershell
$env:SIC_XRT_SYNC_DIR = 'D:\capstone\private-sync'
```

이 디렉터리도 현재 사용자 전용 ACL로 운영해야 한다. Outbox의 기기 ID는 첫 queued Batch 이후 바꿀 수 없다. 다른 기기는 별도 Outbox를 사용한다.

## 상태·중지·검사

```powershell
.\.venv\Scripts\python.exe tools/server_ops.py logs
.\.venv\Scripts\python.exe tools/server_ops.py stop
.\.venv\Scripts\python.exe tools/server_ops.py start
.\.venv\Scripts\python.exe tools/server_ops.py test
```

테스트는 전용 `xrt_td106_test` PostgreSQL DB만 초기화한다. 운영 `xrt` DB를 초기화하지 않는다. 컨테이너에 PySide6/Java/Fiji/ONNX runtime이 없어도 서버 검사가 동작해야 한다. TestClient의 httpx deprecation warning은 테스트 의존성 경고이며 기록한다.

## 백업·별도 복원

```powershell
.\.venv\Scripts\python.exe tools/server_ops.py backup --output artifacts/sync106-private/backups/acceptance
.\.venv\Scripts\python.exe tools/server_ops.py restore --project xrt-restore-td106 --backup artifacts/sync106-private/backups/acceptance --port 18767
```

백업 출력 폴더는 새 경로여야 한다. API를 잠시 멈추고 pg_dump custom-format + PNG tar + Asset digest inventory + DB가 참조하는 `asset_refs.json` + SHA manifest를 만든 뒤 API를 재시작한다. DB/Asset을 같은 수집 중지 구간에서 백업한다. 실패 시 로그를 확인하고 완성되지 않은 백업을 사용하지 않는다.

복원은 `xrt-restore-*` 별도 프로젝트와 빈 DB에만 허용한다. 파일 SHA, archive의 regular file/64hex.png/bounds, 실제 PNG SHA, inventory를 검사한다. 원래 서버와 볼륨은 삭제하지 않는다. 복원된 서버의 project/entities/statistics 및 PNG 해시를 원본 서버와 비교한 뒤 운영자가 채택 여부를 결정한다. 기존 Credential 검증값도 DB와 함께 복원되므로 노출된 Credential은 revoke/reissue한다. `docker compose down -v`를 정상 운영/검증 명령에 포함하지 않는다.

## 외부 HTTPS 준비 — NOT DEPLOYED

현재 외부 서버 공개와 Tunnel 실행은 하지 않았다. 향후 관리자 승인 후 Cloudflare Tunnel의 public hostname은 loopback API `http://127.0.0.1:18766`만 가리키고, Access 정책으로 연구원/조직/기기 접근을 제한한다. Tunnel token은 OS secret storage로 보관하며 설정 저장소에 커밋하지 않는다. PostgreSQL Tunnel은 만들지 않는다. public HTTPS 인증서/접근 정책/앱 Credential·프로젝트 권한/외부 재시도/백업을 별도로 acceptance한 후 Desktop origin을 변경한다. 공개 URL 생성은 별도 승인 작업이다.

Linux CI에서 독립 서버 패키지와 PostgreSQL 검사를 통과시키지만 Linux Compose 실사용 검증은 별도다. Linux에서는 0600 secret bind 파일을 컨테이너 xrt(uid 10001)가 읽을 수 있도록 소유자/ACL을 설정해야 한다. Windows ACL 검증 결과를 Linux 권한 검증으로 간주하지 않는다.
