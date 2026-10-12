# XRT-RESULT-TD-08 Result

## 현재 검증 진행 상태

Engineering: 최종 전체 회귀·CI·격리 ML E2E 확인 중. Scientific: **SCIENTIFIC_MODEL_NOT_READY**. 실제 승인 Ground Truth0건, 실제 신규 학습/독립 정확도 개선/연구원 STABLE 배포 없음. 엔지니어링 검증과 실제 연구 Release를 별도로 판정한다.

## Git·경계

Analyzer 시작 feat/108-verified-dataset-export @ ab50c9a5a5c34050f8276eab65004f5cd10afeb2. Issue #110, 작업 feat/110-model-registry-updater, base feat/108-verified-dataset-export. TD07 Draft #109 및 ML Draft #46의 의존 관계를 유지한다. ML TD07 @7dfc15cdad40e2933ec4a3585baea5fa0bcc785a의 실제 Candidate 계약을 그대로 소비한다. ML 소스 복사/수정 없음. 사용자 AGENTS.md, sources/, 원본/기존 ONNX·프로젝트를 Git에 추가하거나 변경하지 않는다.

## 구성

Registry 0003 불변3테이블, CAS 별도 Volume, Dataset/Evaluation Gate, 승인 Event, offline Ed25519 서명, 인증 stream API, AppData ModelStore 및 QML 관리 UI를 구현했다. [Registry 운영](../server/MODEL-REGISTRY.md), [보안 계약](../server/MODEL-RELEASE-SECURITY.md), [Desktop 사용](../desktop/MODEL-UPDATES.md).

Current SHA: 24368b8f6613cba5251c0bd8e63d7ddec726d6343a35ed878e823a0091369694. 기존 RGB128/v1/uncalibrated BPD,TED,TSD/내부 contrast 입력·출력을 유지한다. ML 새 Manifest에 bundle_id가 없으면 architecture+SHA의 실제 식별자를 사용하고 기존 bundle_id는 유지한다.

## 진행된 검사

- Ruff/compileall/Desktop·Server Wheel 성공.
- 업데이트·기존 모델 탐색36 PASS: 서명 변조/키 교체/폐기/replay/expiry, network/부분/취소/디스크/권한/동시 설치, 상태 atomic 실패, 실제 ORT, 현재/이전/offline 복구, 미저장/실행/Geometry 보호, stale context, QML 버튼 전체 흐름.
- PostgreSQL17 서버78 PASS: 기존58+신규20, migration/append-only/동시 승인/권한/Synthetic STABLE·BETA 차단/손상/출처/CPU·metric 부족/실제 HTTP adapter stream/철회/DB 복원. 기존 Starlette httpx TestClient deprecation warning1건.
- 기존 분석 Flow와 새 관리 UI48 PASS. 초반 전체 회귀에서 모델 상세창 대체로2건 실패해 기존 상세창을 복원하고 새 메뉴를 분리했다.
- 운영의 마이그레이션 전 private backup을 별도 xrt-restore-td110-before 빈 DB로 복원했다. 복원본과 운영의 audit/alembic 제외22테이블(이전19+신규3) count 및 모든 행 canonical SHA 일치. 신규 Registry Candidate/Event/Release 모두0개.

최종 Windows/CI/실제 JPG·TIFF 및 격리 ML E2E 결과는 완료 시 아래에 기록한다. 단위 QA의 전문가 Metadata 모의 조건은 운영 승인으로 취급하지 않는다.

## 보존·제약

Private signing key 없음(운영), packaged trust origins 비어 있음. 실제 승인 Release가 준비되면 별도 신뢰 키 배포와 전문가 지표·연구원 실사용 acceptance가 필요하다. ONNX subprocess 제한은 완전한 OS sandbox가 아니다. 서버를 못 만나는 동안 새로운 철회를 확인할 수 없다. 원격 byte-range resume 없음, 최신 승인100개/최대64MiB/Volume1GiB 정책. 대규모 관리자 Dashboard·앱 Installer/Tunnel/실제 재학습은 범위 밖이다.
