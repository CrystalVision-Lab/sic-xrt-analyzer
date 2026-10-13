# 연구원 배포·실제 화면 가이드 — Issue #122

## 범위
한국세라믹기술원 연구원에게 전달하는 배포 사이트와 Windows 앱 0.1.1을 개선했다. 기준은 feat/120-distribution-portal @ 569d383310328d15a8a09a13c129a0b85b4e7c93이며 새 브랜치는 feat/122-researcher-guide-2d-formats이다. 기존 stacked PR은 병합·rebase·retarget하지 않았다.

## 앱 수정
- 기존 0.1.0에는 imagecodecs._shared만 있고 원본 JPEG 디코더 _jpeg8이 누락되어 있었다. 기존 실행 파일의 codec 모듈 호출은 DelayedImportError를 재현했다. 동적 codec 하위 모듈을 패키징한다.
- 실제 파일 시그니처와 페이지 수로 판별한다. JPG 및 단일 페이지 TIFF는 분석 준비·원본 ROI·결과 저장·개인 검수를 지원한다. 여러 페이지 TIFF와 스택에서 만든 작업 복사본은 모델 분석을 차단한다.
- 모델의 dtype·채널 계약은 유지한다. uint16 단일 TIFF가 RGB8 모델과 호환된다고 간주하거나 몰래 변환하지 않는다. 표시 대비·미리보기는 분석 입력이 아니다.
- 기존 ImageJ TIFF 도구는 유지한다. 원본 픽셀, 좌표, ROI geometry, 추론·분류 계약, 원본 저장 형식, Native Dialog 구현과 sources/를 변경하지 않았다.
- Wafer Map·전후 정합 및 Crop 동기화의 JPG 계약은 유지한다. 2D TIFF의 로컬 분석·프로젝트·검수 확장과 구분한다.

## 실제 사용 가이드
14개 작업 영역, 64개 탭, 실제 UI 화면 57개를 제공한다. 설치·실행, 2D 보기, ROI, 분석, 결과, 검수, 프로젝트, TIFF 스택, ImageJ, 페이지 기반 3D, 정합, Wafer Map, 모델 업데이트와 동기화를 포함한다. 왼쪽 작업 목록 → 상단 화면 탭 → 실제 화면과 번호·화살표·설명으로 구성하며 화면 확대와 키보드 탭 이동을 지원한다. 라이트·다크 선택은 우측 상단에 있고 브라우저에는 xrt-theme:v1만 저장한다.

실제 화면은 Git·웹 빌드·설치 파일에 넣지 않는다. artifacts/sync106-private/research-guide의 PNG·manifest만 portal에 read-only로 마운트한다. 캡처용 프로젝트·Outbox·보고서는 해당 마운트에 포함하지 않는다. API는 PNG 파일명, 경로, 크기 ≤8 MiB와 SHA를 확인한다.

### 연구원 로그인·권한
프로그램에서 사용하던 client ID·인증키로 가이드에 로그인한다. 별도 HttpOnly/SameSite=Strict 세션을 사용하고 인증키는 SQLite에 암호화한다. 기존 연구 API 인증과 PostgreSQL 스키마는 바꾸지 않았다. 매 이미지 요청에서 health와 기존 프로젝트 summary 권한을 다시 확인하므로 Credential·프로젝트 권한 철회가 반영된다. 관리자 API는 기존 ADMIN 검사로 보호한다.

현재 가이드 접근 프로젝트 UUID는 4e8a246e-e9d2-4d97-989a-eedabe500088이다. 관리자는 기존 /admin/grants 운영 절차로 실제 연구원에게 해당 프로젝트 권한을 부여한다. 자동 계정 생성이나 자동 권한 부여는 하지 않는다. 인증키를 URL·Git·채팅·브라우저 저장소에 넣지 않는다.

### 데이터 해석
화면 배경과 원본은 실제 자료다. 결과 화면의 모델 해시는 로컬 연구 모델과 대조했다. 모델 제안과 기능 검증용 개인 검수 예시는 연구원 정답 승인이 아니다. 실제 전후 이미지의 정합은 검증되지 않았으므로 정합 실패/미준비 화면을 표시하고 겹침·차이 분석이 확정된 것처럼 꾸미지 않는다. Wafer 위치는 임시 상대 배치이고 3D는 페이지 인덱스 기준으로 실제 Z·간격·연속성을 확정하지 않는다.

## 검증
- 새 frozen 실행 파일: 대형 JPEG codec·정밀 캐시, uint16 ROI volume, Main.qml, D3D11/QtQuick3D, 포함 OpenJDK/ImageJ worker, 작업 복사본, 모델 검증 helper PASS. 실제 After annealing_1.jpg(12349×12273 RGB8), 단일 TIFF(동일 크기 RGB8), N119 TIFF(3072×3012 uint16 158페이지)에서 분석 버튼 true/true/false와 원본 SHA 보존 확인. QML 경고 0.
- 실제 가이드 촬영: 14 영역/64 탭/57 화면, 원본·기존 프로젝트·모델 SHA 보존, 모델 새 추론 0, 서버 전송 0, QML 경고 0.
- Windows 전체 첫 실행: 736 PASS/2 FAIL/5 SKIP, 1845.81초. 하나는 TIFF 전체 차단이라는 기존 기대이며 새 2D 정책으로 수정했다. 하나는 동시 빌드 중 JVM 준비 30초 초과였다. 해당 TIFF/JPG 분석·내보내기 및 Wand를 순차 재실행하여 3 PASS/24.14초. 실패 로그는 artifacts/distribution122/full-regression.log와 retry-sequential.log에 남겼다.
- Windows 가상 메모리 압박이 관찰돼 실제 배포 검사와 화면 촬영을 순차로 실행했다. Frozen 재검사의 Java 512 MiB 설정은 QA 프로세스에만 적용했다. 앱 기본 Java 설정은 바꾸지 않았다.
- 가이드 BFF 13 PASS(기존 Starlette/httpx deprecation warning 1), React 6 PASS, TypeScript/Vite build PASS, Ruff PASS.
- 브라우저: 실제 서버 인증·원본 PNG·64개 탭·화살표 응답 확인. 최초 모바일 목록의 가로 넘침을 발견해 수정했다. 최종 테마/화면 확대/로그아웃 결과와 CI는 최종 갱신한다.

## 배포·실행
사이트는 기존 PC의 127.0.0.1:18770, 연구 API는 127.0.0.1:18766이다. 기존 Cloudflare 임시 터널을 유지한다. Windows 다운로드는 0.1.1 설치 파일과 동일 소스·GPLv3 빌드 자료를 함께 제공한다. 코드 서명은 없다. 실제 연구 원본·모델·Credential은 배포 파일에 포함하지 않는다.

개발 실행: D:\capstone\sic-xrt-analyzer에서 .\.venv\Scripts\python.exe -m sic_xrt_analyzer. 기존 설치 사용자는 프로그램을 종료한 뒤 새 설치 프로그램을 실행한다. 기존 0.1.0 사용자의 설치/실행 상태를 QA용 설치로 덮어쓰지 않았다. 새 번들의 실제 실행 검증과 구분한다.

운영 갱신: .\.venv\Scripts\python.exe tools/portal_ops.py start. 가이드 host 폴더는 별도 private 백업에 PNG·manifest 및 SHA를 함께 보관한다. portal_ops backup의 기본 DB/installer/source 백업과 구분한다. 임시 URL은 PC·Docker·터널이 켜진 동안 유지된다.
