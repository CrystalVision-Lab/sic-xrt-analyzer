# XRT-DEPLOY-TD-01 — Windows 설치 · 다운로드 포털 · 연구 관리자

## Status

**PARTIAL — 웹/관리자/현재 PC 배포 완료, 공개 설치 배포 라이선스 결정 대기.**

Issue [#120](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/120), Draft PR [#121](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/121). 기준 TD-12 `feat/118-tiff-3d-viewer` / `e32376f04f91a954c86d95b22d45535316b2791b`. 작업 브랜치 `feat/120-distribution-portal`. 기존 stacked PR을 병합·rebase·retarget하지 않았다.

## 구현

- React 19.3 / TypeScript / Vite 8.3.4 / Tailwind 4.3.3. 다운로드, 실제 게시 버전 목록·SHA·릴리스 노트, 요구사항, 설치·이미지·ROI·프로젝트·서버 연결 가이드. 반응형 390/1100/1440 화면.
- 관리자: 실제 서버 집계, 프로그램 버전 게시/철회·revision 이력, 기존 모델 평가 산출물·BPD/TED/TSD 지표·혼동 행렬·CPU 비교·Dataset/STABLE 요건, 프로젝트별 관측/예측/Geometry/검수 기록과 동의받은 Crop, 동기화 수신 이력, 연구원/기기/인증키 발급 ID, 서버 감사 기록.
- 모델 승인·재학습·재평가·활성화와 계정 권한 변경은 제공하지 않는다. 평가 산출물의 기존 근거를 조회하며, 운영 신규 승인 모델은 0개다. 기록 수와 정답 승인 수를 구분한다.
- 페이지당 연구 기록 최대100, 상류 응답 최대32MiB, Crop 최대4MiB + SHA. 동기화 원본 receipt의 수MB 프로젝트 snapshot을 목록에 반복 전달하던 문제를 요약 조회로 고쳤다. 원래 ACK·DB receipt는 보존한다.
- 공개 화면 이미지는 합성 TIFF/Track을 사용하는 실제 앱 화면이다. 연구 원본/Crop/비공개 화면을 정적 사이트와 Git에 넣지 않는다.

## 설치 프로그램

PyInstaller 6.22.3 onedir: `SiCXrtAnalyzer.exe` GUI와 `SiCXrtWorker.exe` 전용 콘솔 helper. 원래 ImageJ/모델 검증 모듈만 실행 허용. ImageJ·공개 Fiji JAR/Plugin·검증한 Eclipse Temurin21 런타임을 포함한다. 기존 Oracle JDK24를 재배포하지 않는다. Inno Setup7.1.0으로 사용자별 Windows10/11 x64 설치와 시작 메뉴·선택적 바탕화면 바로가기·제거를 제공한다. Python/Java 별도 설치가 필요하지 않다. 설치 밖 프로젝트와 원본을 제거하지 않는다.

실제 QA v1 파일은 약1.27GB(1,268,223,714bytes), SHA `d325612b72e661e95643feeee1b22d9dc04f79c9849af0735acd3a06eb01fa0b`, source `eb1a6a3965a6b9f7245dce58a2b20e5f054ef205`. 코드 서명은 없다. 최종 라이선스·고지·소스를 확정한 뒤 새 버전으로 다시 빌드해야 하며 QA 파일을 공개 배포로 사용하지 않는다.

### 공개 설치 파일 보류 사유

[Qt Quick 3D6.11.2 공식 라이선스](https://doc.qt.io/qt-6.11/qtquick3d-index.html#licenses-and-attributions)는 GPLv3 또는 상용이며 LGPL 모듈이 아니다. 게시자에게 **GPLv3+Corresponding Source 제공 / 상용 Qt 권리 보유 / 웹만 우선 배포** 선택을 요청했고 응답 대기 중이다. 저장소 라이선스를 임의로 변경하지 않았다. 개발 QA 빌드의 THIRD-PARTY-NOTICES를 바로잡고 PySide6 Addons/Essentials/shiboken metadata도 포함했다.

공개 계약 `xrt_app_release/v1`: version/platform/source_revision/filename/size/sha256/components/model_included/signature/notes/minimum_os/distribution_clearance. 모델 포함은 false만 허용. `distribution_clearance={status:PENDING,reference:...}`인 파일은 등록하더라도 게시를409로 거부한다. 웹에서 승인으로 바꾸는 기능은 없다. APPROVED의 근거는 게시자가 실제 배포 권리·소스 제공 방식·서드파티 의무를 확인한 기록이어야 한다. synthetic 테스트의 승인 값은 운영 승인 근거가 아니다. 코드 서명 인증서, 최종 GPL 소스 아카이브 또는 상용 빌드 준비는 미완료다.

## 현재 PC 배포

PowerShell, Docker Desktop Linux engine:

```powershell
Set-Location D:\capstone\sic-xrt-analyzer
.\.venv\Scripts\python.exe tools/portal_ops.py init
.\.venv\Scripts\python.exe tools/portal_ops.py start
.\.venv\Scripts\python.exe tools/portal_ops.py status
```

로컬 사이트 `http://127.0.0.1:18770`, 관리자 `/admin`. 기존 API `127.0.0.1:18766` 유지. 새 nginx는 같은 origin의 `/portal-api`를 별도 포털로, `/api/v1`을 기존 API로 전달한다. Desktop 서버 설정은 사이트 origin을 사용한다. 관리자 로그인은 기존 `artifacts/sync106-private/admin.json`의 client_id와 credential을 사용한다. 원문을 로그·채팅·Git에 출력하지 않는다. 운영자는 개인 연구원 Credential과 프로젝트 권한을 기존 API 절차로 발급한다.

사용자가 요청한 전용 임시 터널:

```powershell
.\.venv\Scripts\python.exe tools/portal_ops.py tunnel
```

현재 URL은 `https://gba-math-charlotte-lightweight.trycloudflare.com`. 기존 다른 cloudflared 설정·프로세스는 변경하지 않았다. 전용 pid와 로그는 `artifacts/distribution120/tunnel/`에 있다. Quick Tunnel은 PC/Docker/프로세스 종료에 따라 중단되며 재실행 시 URL이 바뀐다. [Cloudflare 문서](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)의 임시 서비스로 SLA·영구 도메인·200개 초과 동시 요청을 보장하지 않는다. 외부 DNS/영구 Tunnel/자동 Windows 서비스는 이번에 구성하지 않았다.

사이트 중지만 필요한 경우 `tools/portal_ops.py stop`은 portal/web만 중지한다. 기존 API/PostgreSQL 및 연구 볼륨을 중지·삭제하지 않는다. 다시 start로 올린다. `docker compose down -v`는 운영 절차가 아니다.

## 관리자 인증과 데이터 경계

기존 서버 Bearer 인증·PostgreSQL Alembic0003·연구 데이터·모델 계약은 보존했다. 서버에는 동일 ADMIN Depends를 사용하는 읽기 전용 조회만 추가했다. Cookie를 기존 API 인증으로 수용하지 않는다.

포털은 독립 SQLite WAL `portal_state` 볼륨에 프로그램 릴리스와 불변 revision을 저장한다. 앱 바이너리 CAS는 `application_releases` 볼륨이며 상시 포털에는 read-only. 등록은 `tools/portal_ops.py register --bundle artifacts/<new-build>` 로컬 일회성 작업에서만 가능하고 SHA를 검사한다. 관리자 파일은 그 일회성 작업에만 read-only 마운트한다. 상시 API·nginx에는 관리자 Credential이 마운트되지 않는다.

Opaque 세션2시간, HttpOnly/SameSiteStrict, 공개 HTTPS Secure Cookie, 서버 측 Fernet 암호화, CSRF+same-origin 검사, ADMIN/revocation 재검증. localStorage/sessionStorage에 인증키를 저장하지 않는다. 다운로드/공개 HTML 외의 연구 자료는 로그인 없이401이다. 로그인8회/10분/client ID 제한, 다운로드 동시4개·파일최대3GiB·HTTP Range. 다운로드 요청 수는 설치 사용자 수가 아니다. 연구 proxy는 GET만 허용한다. 모델 승인/철회/키 변경 POST는405이다.

초기 인증 변경·PG 세션 migration·모델 승인 web proxy는 자동 승인 검토에서 거부되어 적용하지 않았다. 독립 BFF+읽기 전용으로 범위를 줄였다. Tunnel 시작도 최초 검토에서 공개 범위 설명 부족으로 거부됐고 실제401·공개 리소스 검사와 명시적 사용자 요청을 제시한 재검토 후 허용됐다. 외부 HTTPS에 관리자 인증키를 보내는 자동 QA는 거부되어 수행하지 않았다. 우회하지 않았고 공개 익명 검사+로컬 관리자 검사+합성 HTTPS Cookie 검증으로 나눴다.

## 백업 · 복원 준비

연구 DB/Crop/모델은 기존 `tools/server_ops.py backup`을 사용한다. 배포 전 `artifacts/sync106-private/backups/distribution120-before-portal` 생성. 포털은 별도 백업:

```powershell
.\.venv\Scripts\python.exe tools/portal_ops.py backup --output artifacts/sync106-private/backups/<new-name>
```

새 private 폴더만 허용. portal만 잠시 중지하고 SQLite online backup·등록된 설치 CAS·SHA manifest를 생성한 뒤 재시작한다. 원본 볼륨은 유지한다. 백업 사본에서 sessions를 제거하여 복원 시 기존 브라우저 세션이 살아나지 않게 한다. 포털 key와 관리 Credential은 백업에 포함하지 않으며 별도 OS/private 보호 대상이다. 실패한 partial 폴더를 재사용하지 않는다.

실제 백업 `distribution120-portal-v1/snapshot` 생성 완료, 공개 설치 등록0개. 합성 설치 파일·불변 이력·세션 제거·원본 세션 유지·SHA를 별도 테스트했다. 복원 채택은 운영자가 새 empty portal_state/application_releases 볼륨에서 manifest·SHA·SQLite integrity 확인 후 수행한다. 운영 볼륨을 덮어쓰는 자동 restore는 제공하지 않는다. 연구 서버와 포털 백업을 모두 보관한다.

## 검증 기록

| 대상 | 결과 |
|---|---|
| 로컬 Chromium public4화면×3폭 + 관리자7화면 | 19 PASS, JS오류0, 가로넘침0 |
| 공개 HTTPS 익명 public12 + 보호API4 | 16 PASS,401 확인, 인증키 전송 없음 |
| 개발 QA 설치·설치 후 실제 frozen smoke | PASS, D3D11, QML경고0, TIFF16bit/JPG/ROI3D/ImageJ작업복사 |
| QA 설치 제거 | PASS, CURRENTUSER, 설치 밖 합성 프로젝트 SHA보존 |
| PostgreSQL 서버 회귀 | 82 PASS (최종 CI 모델 평가 조회 검사 포함 결과 별도 확인) |
| 포털 | 7 PASS, 암호화/역할/CSRF/revocation/range/이력/백업/배포보류 |
| 웹 Unit | 4 PASS, 최신요청·미게시·STABLE 선택·키보드 focus |
| Worker/모델+포털 집중 회귀 | 45 PASS |
| Windows 전체 회귀 | 최종 결과 수집 중 |
| Linux GitHub Actions | 최종 HEAD 결과 수집 중 |

로그·원본 Crop·로그인 후 캡처는 `artifacts/` private/ignored, 실제 인증값은 출력하지 않았다. 브라우저 검사는 자체 Chromium 자동 QA이며 물리 마우스의 설치 wizard 검사를 뜻하지 않는다. `web/qa.mjs`는 관리자 자동 검증을 localhost로 제한한다. 외부에서는 `XRT_QA_PUBLIC_ONLY=1`을 지정한다.

기존 Starlette/httpx TestClient deprecation 경고1개를 기록했다. Installer 빌드의 scipy optional hidden import `_cdflib` 경고는 보관했고 핵심 frozen smoke로 사용 경로를 확인했다. 기능·모델 과학적 정확도·GPL 배포 승인·코드 서명은 서로 다른 판정이다.

## 남은 범위

게시자의 라이선스 선택과 실제 의무 이행 후 최종 설치 버전을 새로 빌드·검증·게시해야 한다. 다른 깨끗한 PC에서 설치·GPU/Fiji plugin 실사용, Windows Authenticode 서명, 영구 hostname/Access 정책·서비스 자동 시작·외부 관리자 실사용 acceptance는 별도 운영 검증이다. 현재 웹은 실데이터 조회가 가능하지만 모델 신규 과학 성능을 만들거나 승인하지 않는다.

## 디자인 참조

[VS Code 다운로드](https://code.visualstudio.com/download)의 OS/버전/이력 연결과 [OBS 다운로드](https://obsproject.com/download)의 설치·요구사항·지원 동선을 참고했다. 텍스트·브랜드·화면을 복제하지 않고 연구 앱의 합성 실화면, 기술 범위와 실제 서버 기록을 사용했다.
