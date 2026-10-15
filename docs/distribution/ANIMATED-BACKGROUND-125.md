# 다운로드 배경 — Issue #125

## 디자인
[React Bits 시작 페이지](https://reactbits.dev/get-started/index), [Aurora](https://reactbits.dev/backgrounds/aurora), [Particles](https://reactbits.dev/backgrounds/particles)의 분위기를 참고한 자체 React/CSS 배경이다. 라이브러리 코드를 복사하거나 WebGL shader·새 dependency를 추가하지 않았다.

청록·파랑·약한 주황빛, 얇은 wafer 형태 등고선과 작은 입자를 다운로드 첫 영역에 배치했다. 아래 실제 데이터 가이드와 관리자 화면에는 배경을 넣지 않았다. 카드와 제목을 배경 위에 두고 pointer-events:none/aria-hidden으로 장식을 분리했다. 라이트·다크 팔레트와 모바일 레이아웃을 지원한다.

## 동작
- 배경 정지/재생 버튼. 별도 브라우저 저장소·데이터 요청 없음.
- OS prefers-reduced-motion이면 정적 배경으로 표시하고 사용자 버튼으로 강제로 켜지 않음.
- 화면 밖과 비활성 탭에서는 CSS animation-play-state를 paused로 전환.
- 프레임별 React state 갱신이나 JS animation loop 없음. 정해진 3개 glow, SVG 곡선 및 12개 particle의 transform/opacity만 움직임.
- 이벤트 listener와 IntersectionObserver는 unmount 시 정리.

## 검증
React 기존 6개 회귀 PASS, TypeScript/Vite build PASS. Chrome에서 실제 transform 변화, 수동 정지 시 transform 고정, visibility handler, 화면 밖 정지, 실시간 reduced-motion 전환을 확인했다. 라이트·다크 × 390/1100/1440 화면 6개에 가로 넘침 없음. 다운로드 링크는 기존 0.1.1을 유지하며 익명 화면에 실제 연구 이미지를 표시하지 않는다. 인증키를 사용하지 않았다. artifacts/distribution125에 QA 로그와 공개 화면 캡처를 보관한다. FPS/CPU 개선 수치는 측정하거나 주장하지 않았다.

## 변경 경계·배포
웹 화면과 이 문서만 변경한다. desktop/server/portal, 원본·모델·실제 가이드 PNG, 앱 릴리스와 설치 파일·서명·업데이트 계약을 변경하지 않는다. 사용자 AGENTS.md 변경은 보존한다. 기존 PC의 web 컨테이너만 --no-deps로 재빌드하여 기존 API/DB/터널을 유지한다.
