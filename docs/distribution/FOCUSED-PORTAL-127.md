# 다운로드·사용 가이드·개발노트 — Issue #127

## 화면 구성
- `/`: 설치 다운로드 버튼과 Windows/현재 버전만 표시한다. 가이드·FAQ·전체 버전 목록·체크섬·빌드 정보 카드를 제거했다. GPLv3 대응 소스는 하단의 작은 다운로드 링크로 제공한다.
- `/guide`: 실제 화면 기반 사용 가이드만 표시한다. 작업 선택과 화면 탭·화살표·확대 보기 구조를 유지한다. 사용자가 전달했던 화면 구성 지시 문구를 제거했다.
- `/notes`: 최신 앱 버전의 주요 변화만 표시한다. 현재 0.1.1은 JPG 열기 수정, 단일 페이지 TIFF 분석 연결, 앱 업데이트 기능을 설명한다. 모델 정확도 향상은 주장하지 않는다. 과거 `/releases` 링크는 이 페이지로 이동한다. 기존 릴리스 목록 API·설치 파일·업데이트 계약은 그대로다.

## 배경과 로고
[React Bits Aurora](https://reactbits.dev/backgrounds/aurora)와 [Dark Veil](https://reactbits.dev/backgrounds/dark-veil)을 참고한 자체 CSS 구현이다. 전체 viewport에 고정된 청록·파랑빛과 넓은 곡선·입자 배경을 모든 공개 페이지에서 사용한다. 첫 hero에만 적용되던 mask는 제거했다. 다크/라이트 테마에서 html/body/root와 짧은 페이지까지 채우고 첫 paint 전에 테마를 적용한다. 모션 정지/재생, 비활성 탭 정지, OS reduced-motion과 listener 정리를 유지한다. 프레임별 React 갱신·WebGL·추가 의존성은 없다. FPS 개선 수치를 주장하지 않는다.

KICET 공식 로고 파일은 이미 RGBA(520×126), 모서리 alpha=0인 투명 PNG였다. 흰 사각형은 CSS 배경이었다. 이를 제거하여 원본 로고 파일·한글·심볼 색상은 변경하지 않았다. 다크 모드에서는 CSS mask로 한글 wordmark 부분만 밝게 표시한다. imagegen 재생성은 필요하지 않았다. [로고 출처](BRANDING.md).

## 승인한 실제 화면 공개
이번 요청에서 사용자는 **실제 연구 화면도 로그인 없이 공개**하는 선택을 명시했다. 기존 로그인 필수 정책을 다음과 같이 바꿨다.

- `/portal-api/guide/public`과 `/portal-api/guide/public/images/{id}`는 승인된 가이드 캡처만 익명 GET으로 제공한다.
- runtime manifest의 `public_tabs`에 group_id/tab_id/image_id/SHA를 명시한다. 새 탭·새 이미지와 SHA가 변경된 이미지는 자동 공개하지 않는다. 공개 응답에서 private project UUID·파일명·전체 이미지 inventory는 제거한다.
- 현재 14개 작업, 65개 탭이 참조하는 **57개 PNG**를 공개한다. 원래 inventory에는 58개 PNG가 있고 참조되지 않은 1개는 공개되지 않는다. 58개 SHA를 모두 보존 확인했다.
- 가이드 PNG/manifest는 기존 runtime 폴더에서 read-only 마운트한다. Git·웹 번들·설치 파일에 실제 연구 화면을 넣지 않는다. 원본 XRT 파일·분석 프로젝트·인증키도 공개하지 않는다.
- 기존 private guide API·관리자·연구 수집 자료 API의 세션/권한 계약을 유지한다. 관리자 인증키를 가이드 검증에 사용하지 않았다.
- PNG 서명/크기 ≤8 MiB/SHA/파일명·경로 제한을 공개 경로에서도 검사한다. 공개 철회는 manifest에서 해당 public_tabs 항목을 제거한다. runtime `public_tabs`를 빈 배열로 바꾸면 모든 공개 캡처를 내릴 수 있다.

공개 승인 전에 manifest를 `artifacts/sync106-private/backups/site-127-publication/manifest-before.json`에 백업했고, 이미지 inventory SHA도 별도로 기록했다. 파일 변경 없이 운영 마운트만 사용했다.

## 검증
- TypeScript/Vite production build PASS, React 기존 6개 회귀 PASS.
- Portal 16개 회귀 PASS. 기존 private guide 권한 철회·관리자 role 격리, 새 공개 allowlist·새 캡처 비공개·SHA 변경·파일 손상·경로 제한을 확인했다. 기존 Starlette/httpx deprecation warning 1개를 기록했다.
- Chrome: 다운로드/개발노트/가이드 × 라이트/다크 × 390/1100/1440 폭, 18개 캡처. 가로 넘침 없음, background fixed/inset=viewport와 테마 루트 색 확인.
- 전체 65개 탭에서 실제 이미지 로드·화살표/설명·확대/Escape 확인. 익명 공개 PNG 57개 200; 관리자·private guide·연구 자료 API 401; 허용 목록에 없는 이미지 404.
- 설치 EXE와 대응 GPL 소스 ZIP의 Range 응답 206, MZ/PK 확인. 기존 0.1.1 파일을 유지했다. 전체 설치 파일의 재다운로드·앱 재설치는 이번 웹 수정에서 반복하지 않았다.
- 모션 정지 시 transform 고정, 재생 시 변경, live OS reduced-motion 전환 PASS. 브라우저 JS 오류 없음.
- QA 최초 실패는 inventory 58개와 탭 참조 57개를 혼동한 기대값, 비동기 media 이벤트 및 이미지 교체 완료 대기 누락이었다. 정확한 공개 수와 대기 조건으로 수정한 최종 검사는 PASS다.

로그·화면: `artifacts/distribution127/preview` 및 `public` (Git 제외).

## 배포
현재 PC의 xrt-research portal/web만 `--no-deps`로 배포했다. 연구 API·PostgreSQL·모델 Registry·설치 릴리스·기존 Cloudflare tunnel은 유지했다.

```powershell
Set-Location D:\capstone\sic-xrt-analyzer
docker compose -p xrt-research -f deploy/docker-compose.yml -f deploy/portal.compose.yml up -d --build --no-deps portal web
```

로컬 사이트: http://127.0.0.1:18770. 임시 HTTPS 주소는 실행 중인 기존 tunnel을 사용한다. PC/Docker/tunnel이 중단되면 주소에 접속할 수 없다.

작업 branch: `feat/127-focused-public-portal`. 시작 HEAD `676eb65adeb5b1b2a8ed18cc5460006512baf32f`. 기존 stacked PR은 병합·rebase·retarget하지 않고 사용자 AGENTS.md 변경을 보존한다. 변경 범위는 웹/BFF 공개 가이드·검증·문서이며 desktop/native dialog/원본 좌표/ROI/모델 추론 경로는 수정하지 않았다.
