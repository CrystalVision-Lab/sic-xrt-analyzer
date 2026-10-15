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

API: `http://127.0.0.1:18766`. 기존 host port 충돌을 피하기 위해 8766 대신 18766을 사용한다. `XRT_API_PORT`로 loopback port를 지정할 수 있다. Compose의 `XRT_DB_PASSWORD_PATH` override는 운영자가 별도 private secret을 직접 준비한 경우만 사용한다. 이 도구의 init/bootstrap/기본 backup 폴더는 프로젝트 아래 `artifacts/sync106-private`이다. `.env.example`만 Git에 포함한다. 비밀은 `artifacts/sync106-private/db-password.txt`, bootstrap Credential은 같은 폴더 `admin.json`에 기록한다. 원문을 콘솔·Git·채팅에 출력하지 않는다. bootstrap은 이미 ADMIN이 있으면 거부한다.

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

## 외부 HTTPS — 고정 Tailscale Funnel

배포·사용 가이드·업데이트 주소는 **https://pc1.tail23f008.ts.net** 이다. 사용자가 기존 사이트 대신 XRT로 교체하는 것을 승인했다. Funnel은 loopback 웹 `http://127.0.0.1:18770`을 가리키며 웹이 인증된 연구 API와 포털을 기존 경로로 연결한다. PostgreSQL은 공개하지 않는다. 연구 데이터와 관리자 기능은 기존 인증·프로젝트 권한 검사를 유지한다.

```powershell
& 'C:\Program Files\Tailscale\tailscale.exe' funnel --bg --yes http://127.0.0.1:18770
& 'C:\Program Files\Tailscale\tailscale.exe' funnel status --json
```

`--bg` 설정은 Tailscale 재시작·재부팅 후 자동 복구된다. 이 PC의 Tailscale 서비스는 자동 시작 상태다. Docker Desktop과 XRT 서비스도 실행 중이어야 접속할 수 있다. 노드/도메인 삭제·변경까지 방지하는 영구 도메인 보장은 아니다. [공식 동작](https://tailscale.com/docs/reference/tailscale-cli/funnel#effects-of-rebooting-and-restarting)을 참고한다.

0.3.1부터 프로그램 기본 업데이트 주소와 저장된 이전 Quick Tunnel 주소를 고정 주소로 연결한다. 별도 사용자 지정 HTTPS 주소는 보존한다. 이전 앱이 실행 중이라면 주소를 바꾼 뒤 다시 실행하거나 업데이트 대화상자에서 고정 주소를 저장한다. 과거 Cloudflare 주소는 현재 공식 배포 주소가 아니다.

Linux CI에서 독립 서버 패키지와 PostgreSQL 검사를 통과시키지만 Linux Compose 실사용 검증은 별도다. Linux에서는 0600 secret bind 파일을 컨테이너 xrt(uid 10001)가 읽을 수 있도록 소유자/ACL을 설정해야 한다. Windows ACL 검증 결과를 Linux 권한 검증으로 간주하지 않는다.


## 승인 데이터셋 로컬 반출 (TD-07)

먼저 기존 백업 명령으로 새 private 백업을 생성한다. start 시 Alembic 0002가 이벤트·버전 테이블과 append-only trigger를 추가한다. 기존 0001 데이터는 보존한다. 관리자만 API로 Group Mapping과 정답 승인을 작성한다. 사용 권한·독립 촬영 그룹·라벨 근거를 확인한 후 새 Dataset Version을 만든다. 이번 실제 승인 수는 0개여서 기존 QA 자료로 학습 버전을 만들지 않았다.

```powershell
.\.venv\Scripts\python.exe tools/server_ops.py dataset-export --dataset-id <dataset-UUID> --output artifacts/sync106-private/exports/<new-version>
```

출력은 새 경로이며 ACL 보호 private 폴더 아래여야 한다. Artifact는 지정한 폴더의 dataset/ 아래에 생성된다. 일회성 관리 컨테이너에 관리자 Credential 파일은 read-only, 지정 출력 폴더만 writable로 마운트한다. 상시 API에는 관리자 파일·반출 폴더를 마운트하지 않는다. 인증값을 출력하지 않는다. 반출 실패 시 partial 폴더를 재사용하지 않고 새 경로를 지정한다. public 다운로드·자동 업로드는 없다.

학습 전 GET datasets/<id>의 usage_status=AVAILABLE을 다시 확인한다. 철회 시 이전 사본은 불변으로 보존하되 사용을 중단한다. 학습은 별도 ML 프로세스로 실행한다. [Artifact 계약](VERIFIED-DATASET-CONTRACT.md)과 ML TD-07 문서를 따른다.


## 모델 Registry 및 업데이트 (TD-08)

start 시 Alembic 0003이 불변 모델 테이블을 추가한다. 기존 연구·Dataset 자료는 보존한다. 상시 API는 Model Volume read-only, ONNX 검증은 별도 model-admin 일회성 프로세스다. 운영 신규 승인 모델은0개다. [모델 Registry 운영](MODEL-REGISTRY.md), [Release 보안](MODEL-RELEASE-SECURITY.md), [Desktop 모델 관리](../desktop/MODEL-UPDATES.md)를 따른다. 백업은 xrt-server-backup-2로 DB/Crop/모델·서명을 포함하며 Private Key는 별도 보호한다.


## 다운로드 사이트 및 연구 관리자 포털 (DEPLOY-TD-01)

기존 연구 API18766과 PostgreSQL0003은 유지한다. 웹18770과 독립 포털은 deploy/portal.compose.yml overlay로 운영한다. tools/portal_ops.py start/status/stop/backup을 사용한다. 새로운 포털 키는 private 폴더에 보호하며 상시 서비스에 admin.json을 노출하지 않는다. 연구 백업과 포털 백업을 각각 생성한다. [구성·임시 URL·라이선스 보류·검증](../deploy/XRT-DEPLOY-TD-01.md)을 따른다.
