# AI 모델 관리

## 실행·설정

```powershell
Set-Location D:\capstone\sic-xrt-analyzer
.\.venv\Scripts\python.exe -m pip install -e ".[research,sync]"
.\.venv\Scripts\python.exe -m sic_xrt_analyzer
```

중앙 서버 연결은 기존 프로젝트 영역의 중앙 서버 설정(origin/client ID/Credential)을 사용한다. 별도 토큰을 모델 설정에 저장하지 않는다. **분석 메뉴 → AI 모델 관리…**에서 현재 모델·출처·업데이트·설치 모델을 확인한다. 기존 ‘모델 상세 정보’는 그대로 제공한다.

현재 실제 승인 모델은 없다. 업데이트 확인은 ‘최신 승인 모델이 없습니다. 현재 모델을 유지합니다.’를 표시한다. 서버가 중지돼도 JPG 분석·저장된 결과·검수·프로젝트 저장은 계속할 수 있다. TIFF는 스택/향후3D 데이터이며 모델 분석이나 학습 Crop을 자동 실행하지 않는다.

## 설치와 적용

1. 업데이트 확인: 인증된 목록의 Signature/Trust/앱 호환/channel/sequence를 검증한다. 키 교체 후 과거 폐기 키로 서명된 항목은 건너뛰고 최신 정상 신뢰 모델을 선택한다. 모든 항목이 검증에 실패하면 경고하며 현재 모델을 유지한다.
2. 다운로드·설치: 새 staging으로 수신, SHA·Manifest·CPU 로딩·현재 서버 상태를 확인한 뒤 게시한다. 설치만으로 모델은 변경되지 않는다.
3. **다음 분석에 적용**: 사용자가 직접 선택한다. 새 Adapter가 정상 준비되고 포인터가 저장된 뒤 전환한다.
4. 이전 모델 복원: 직전 정상 모델만 확인하고 로딩한다. 오프라인에서도 가능하다.

다운로드 진행·취소를 제공한다. 연결 끊김·Timeout·잘못된 서명/Hash·ONNX·디스크 부족·권한·취소·부분 다운로드는 기존 모델을 유지한다. 불완전 staging은 정리하고 재시도는 처음부터 받는다. 같은 설치는 Hash를 검사해 재사용한다. 파일 경로/프로젝트/설정 변경 후 늦게 도착한 응답은 폐기한다.

분석 실행·Model Loader·프로젝트 작업·미저장 결과/검수·Geometry draft·ROI 미저장 편집 중에는 적용을 막는다. 작업을 마치고 프로젝트를 저장한다. 적용 대기 중 작업 상태가 바뀌면 다시 차단한다. 기존 AnalysisRun·Candidate IDs/좌표·점수·ReviewEvent·Geometry·Export를 다시 쓰지 않는다. 새 분석은 기존 새 Run 생성 흐름을 따른다.

## 경로와 우선순위

기본 Qt `AppLocalDataLocation/models`, 선택 override `SIC_XRT_MODEL_DIR`. 프로젝트 개발 경로에 설치하지 않아 설치 폴더 권한이 필요하지 않다. 테스트 INI 설정은 해당 INI 옆의 독립 models를 사용한다. Windows 예:

```powershell
$env:SIC_XRT_MODEL_DIR = 'D:\capstone\private-models'
$env:SIC_XRT_MODEL_TRUST_FILE = '<별도로 검증·배포받은 공개 Trust JSON>'
```

저장된 모델의 우선순위:

1. `SIC_XRT_MODEL_BUNDLE` 개발용 override.
2. 사용자가 직접 선택한 `researchModelBundle`.
3. 서명 검증된 설치 모델의 active pointer.
4. 기존 models/research 또는 artifacts/models/research Bundle.

개발 override가 있으면 관리 활성화는 차단하고 UI에 표시한다. 승인 다운로드를 명시적으로 적용하면 직접 선택 설정을 해제한다. startup 자동 복원은 직접 선택 설정을 새로 만들지 않는다. 새 모델 로딩/Hash/상태가 손상되면 검증된 이전 모델, 기존 Bundle 순으로 복구한다. 직접 선택한 파일도 변경 전 정상 Adapter를 준비하며 완료된 과거 결과를 유지한다.

`<release-id>/model.onnx`, manifest.json, release.json은 설치 후 불변, `state.json`은 current/previous/sequence/known-unavailable 상태만 저장한다. release.json에 서명과 전체 Metadata를 함께 보관한다. Credential/Private Key는 포함하지 않는다.

## 제한

자동 업데이트·자동 변경은 제공하지 않는다. BETA는 체크박스 선택과 별도 ADMIN grant가 모두 필요하다. INTERNAL_TEST는 연구원 UI에 노출하지 않으며 테스트 ADMIN 환경에서만 검증한다. 공개키는 서버에서 자동 신뢰하지 않는다. 유효한 실제 STABLE 모델과 운영 서명키는 아직 없다.

업데이트 확인 시 현재 설치 모델의 파일·Trust·알려진 철회도 다시 확인하고 문제가 있으면 경고한다. 실행 중 Adapter를 즉시 제거하지는 않으며 저장 후 이전 모델 복원 또는 재시작을 수행한다.

새 모델 적용으로 정확도가 향상됐다는 보장은 없다. 업데이트 도구는 연구 성능을 검증하지 않는다. 알고리즘/ONNX 입력 계약 변경, 앱 EXE 설치·업데이트, 외부 HTTPS/Tunnel 배포는 별도 작업이다.
