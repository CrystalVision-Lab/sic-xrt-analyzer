# 고정 배포 주소 전환 — #133

- 공식 배포·업데이트 origin: `https://pc1.tail23f008.ts.net`
- Funnel 루트 443 → `http://127.0.0.1:18770`, background 영속 설정. Tailscale 서비스 Automatic.
- 기존 루트의 다른 사이트 연결을 XRT로 바꾸는 것은 사용자에게 확인하여 승인받았다. 다른 사이트의 소스·컨테이너·DB는 변경하지 않는다. 이전 Funnel 설정은 ignored 작업 artifact에 보관했다.
- 0.3.1 기본 origin과 저장된 유효 Quick Tunnel URL을 고정 주소로 이관한다. 별도 HTTPS 사용자 서버는 보존하며 HTTP·userinfo·path·query·임의 port 허용 범위를 넓히지 않는다.
- 현재 PC의 기존 설치 설정도 applicationUpdates/origin 한 값만 복구한다. 이미 실행 중인 앱의 메모리 설정은 재시작 또는 대화상자 저장이 필요하다. 다른 PC의 구 버전은 최초 한 번 고정 주소를 입력하거나 0.3.1을 직접 설치한다.
- 업데이트 manifest·SHA·배포 상태·GPL 대응 소스·저장 확인·무인 설치 계약은 유지한다. 원본·ONNX·Native Dialog·연구 서버 자료를 변경하지 않는다.

## 복구

기존 root proxy는 `http://127.0.0.1:8080`이었다. 롤백은 이 대상의 Funnel 설정만 되돌리고 XRT 기본 origin을 별도 검토한다. `funnel reset`으로 다른 서비스 설정까지 지우지 않는다. 임시 Cloudflare 경로를 기본값으로 복원하지 않는다.
