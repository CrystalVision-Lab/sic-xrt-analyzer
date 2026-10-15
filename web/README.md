# SiC XRT 다운로드 · 관리자 포털

React + TypeScript + Tailwind. [운영/검증 보고서](../docs/deploy/XRT-DEPLOY-TD-01.md).

```powershell
Set-Location D:\capstone\sic-xrt-analyzer\web
npm ci
npm test
npm run build
npm run dev
```

개발 서버의 /portal-api와 /api/v1은 배포 loopback18770으로 proxy한다. npm run dev는 배포 서비스가 아니다. Docker 배포는 루트 tools/portal_ops.py start.

자체 Chromium QA는 설치된 Chrome을 사용한다. 로컬 관리자 QA만 private admin.json을 읽으며 인증값을 출력하지 않는다. 외부 검사는 XRT_QA_PUBLIC_ONLY=1 필수다. 캡처는 artifacts 아래에만 기록하고 실제 자료를 Git에 추가하지 않는다.

다운로드는 실제 PUBLISHED 버전만 제공한다. UI demo 값을 운영 데이터로 넣지 않는다. 모델 평가는 기존 산출물 조회이며 학습/재평가는 sic-xrt-ml 책임이다.
