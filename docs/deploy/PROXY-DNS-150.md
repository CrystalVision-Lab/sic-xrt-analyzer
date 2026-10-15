# 포털 재시작 후 502 장애와 수정

2026-10-15 배포 백업 과정에서 portal의 Docker IP가 바뀌었다. 웹 정적 파일은 200이지만 `/portal-api/releases`와 `/portal-api/guide/public`은 502였다. 기존 앱의 `SiC-XRT-App-Updater`도 동일한 502를 받았다.

Nginx 오류는 이전 upstream IP의 `Host is unreachable`이었다. `docker inspect portal` 및 `getent hosts portal` 결과는 다른 IP였다. 따라서 인증이나 DB 오류로 추측하지 않고, `nginx -t` 후 graceful reload로 먼저 서비스를 복구했다.

재발 방지를 위해 Docker DNS `127.0.0.11`과 `valid=5s`, shared zone을 가진 upstream `server ... resolve`를 적용했다. URI를 바꾸지 않는 proxy_pass로 기존 API 경로/쿼리/POST 계약을 유지한다. [Nginx 공식 resolve 설명](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#server).

`python tools/validate_proxy_dns.py`는 고유한 테스트 네트워크와 가짜 backend를 만든다. 이전 IP를 다른 테스트 컨테이너로 점유하고 같은 DNS 이름의 backend를 다른 IP로 교체한다. 실제 nginx.conf로 releases·guide·health와 POST reports를 검사한다. 운영 데이터·컨테이너에는 접근하지 않는다. Windows Docker 검사: IP 변경 후 4.797초에 정상 응답, proxy 재시작 0회, 경로·쿼리·POST 보존 PASS. 이 회귀 검사를 portal CI에 추가했다.

정적 HTML 200만으로 사이트 정상이라고 판단하지 않는다. 배포 후 공개 releases·guide API, 앱 업데이트 클라이언트, 인증된 신고 수신을 각각 확인해야 한다. 이 수정은 기존 연구 DB·릴리스·인증 계약을 변경하지 않는다.
