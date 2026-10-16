# 관리자 아이디·비밀번호 로그인 (#162)

관리자 `/admin` 화면에서 아이디와 비밀번호를 입력한다. 포털이 비밀번호를
검증하고 연결된 연구 API 인증키의 현재 관리자 권한을 확인한 뒤 기존 2시간
HttpOnly/SameSite=Strict 세션을 발급한다. 외부 HTTPS에서는 Secure 쿠키를 쓴다.
비밀번호와 인증키는 응답·브라우저 저장소·감사 로그에 넣지 않는다.

## 운영 계정 설정·변경

운영 checkout에서 새 포털 이미지를 배포한 뒤 실행한다.

```powershell
.\.venv\Scripts\python.exe tools/portal_ops.py set-admin-login --username operator-id
```

비밀번호는 숨김 프롬프트에서 입력한다. 명령 인수·환경 변수에 넣지 않는다.
이 명령은 기존 private `artifacts/sync106-private/admin.json`을 일회성 운영
컨테이너에 읽기 전용으로 연결하고 실제 관리자 권한과 기기 ID를 검증한다.
상시 포털에는 이 파일을 마운트하지 않는다. 같은 아이디를 다시 설정하면
비밀번호와 연결 인증을 교체하고 해당 아이디의 기존 비밀번호 로그인 세션을
무효화한다. 다른 아이디의 세션은 유지한다.

자동화는 `python -m xrt_portal.admin_login --username operator-id
--credential /operation/admin.json --password-stdin`의 표준입력을 사용한다.
터미널 echo, shell history, 프로세스 인수, CI 로그에 실제 비밀번호를 넣지 않는다.
설정 실패 시 기존 계정을 유지하고 비밀값이 없는 오류만 출력한다.

아이디는 영문·숫자·`_.-` 3–64자이며 대소문자를 구분하지 않는다. 설정 가능한
비밀번호는 10–256자이고 공백·대소문자를 그대로 구분한다. 하드코딩한 초기
계정이나 기본 비밀번호는 없다.

## 저장·권한·호환성

- 독립 SQLite `admin_logins` 테이블을 추가한다. 계정마다 16바이트 salt와
  `scrypt-v1` 해시(N=2^17, r=8, p=1, 32바이트 결과)를 저장한다.
  [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)의
  scrypt 권고 매개변수를 사용한다. 포털 전체 동시 해시 계산은 2개로 제한한다.
- 연구 API 인증키·사용자 식별은 기존 portal key로 Fernet 암호화한다.
  연구 API의 ADMIN 권한·사용자 비활성화·인증키 취소를 계속 재검증한다.
  로컬 계정 생성은 연구 API 권한을 새로 부여하지 않는다.
- 아이디별 8회/10분, 비밀번호 로그인 전체 60회/10분 시도 제한이다.
  알 수 없는 아이디에도 동일한 해시 계산과 일반적인 인증 실패 응답을 쓴다.
  현재 단일 포털 프로세스의 메모리 제한이며 재시작 시 초기화된다.
- `/portal-api/login`에 `{username,password}` 입력을 추가한다. 기존 운영 도구의
  `{client_id,credential}` 입력과 연구원 guide 로그인은 유지한다. 비밀번호를
  바꿔도 별도 API 인증키나 인증키로 만든 세션 자체를 취소하지는 않는다.
- 세션 암호문에 계정 revision을 포함한다. 예전 세션 암호문도 읽을 수 있으며,
  비밀번호 변경과 로그인 완료가 경합해도 예전 revision 세션은 거부한다.
- 연구 PostgreSQL/Alembic, Desktop Bearer, 모델·데이터셋·ONNX 계약은 변경 없다.
  새 테이블만 추가하므로 기존 이미지로 롤백해도 릴리스 원장은 그대로 읽는다.

배포 전 포털 SQLite를 online backup하고 이전 컨테이너 이미지 ID를 보관한다.
프로그램 릴리스 파일·연구 DB 볼륨은 변경하지 않는다. 비밀번호 계정이 포함된
백업도 private 자료이며 portal key는 별도로 보관한다. 기존 backup 명령은
브라우저 세션을 제거하지만 계정 해시와 암호화된 연결 정보는 보존한다.

브라우저 QA는 localhost에서만 인증한다. `web/qa.mjs`의 `XRT_QA_LOGIN_FILE`은
private `{username,password}` JSON 경로이며 저장소에 넣지 않는다. 공개 HTTPS
QA는 `XRT_QA_PUBLIC_ONLY=1`로 익명 경로만 확인한다.

## 검증 범위

합성 계정으로 성공·실패·unknown user·시도 제한·same-origin·CSRF·쿠키·원본
인증키 취소·기기 불일치·비밀번호 교체·다른 계정 세션 유지·비밀값 평문 저장
방지를 검사한다. React 입력 테스트는 username/password 전송, 비밀번호 입력
마스킹·성공 후 비우기·실패 안내를 확인한다. 운영 설정은 Git에 기록하지 않는다.
