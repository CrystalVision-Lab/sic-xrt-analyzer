# TD — Industrial UI/UX 통합 재설계

Issue #7 하나로 메뉴·툴바·Navigator·Viewer·Inspector·Settings·Status를 함께 정리한다. 기존 TIFF 및 메뉴 작업을 통합한다. 분석 알고리즘과 외부 모델 계약은 변경하지 않는다.

## 기존 구조와 결정

| 영역 | 기존 상태 | 구현 |
|---|---|---|
| Framework | PySide6 / Qt Quick Controls Basic | 유지 |
| Window | QML ApplicationWindow, 1440×900 / 최소 1100×700 | 유지, 전체 다크 팔레트·Windows 제목 표시줄 |
| Menu / Shortcut | 분산 명령과 공통 Action | 8개 메뉴, 공유 Action, Qt 키보드 동작 |
| Viewer | TIFF image provider와 합성 Canvas | 유지, 중복 도구 제거, 원본 좌표, 백그라운드 로딩 |
| Right Panel | 정보/설정/결과 책임 혼재 | IMAGE / ANALYSIS / RESULT Inspector |
| Settings | 패널 전환 | 독립 Modal, 임시 편집 상태와 적용 설정 분리 |
| Dialog | 별도 스타일 | AppDialog 기반 공통 다크 화면 |
| Metadata | 해상도·비트·페이지·미리보기 | 실제 정보만 표시 |
| Analysis / Result | 승인 모델과 백엔드 없음 | 실행 비활성, 미연결 이유와 결과 안내 |
| Theme | Viewer 중심의 다크 스타일 | 앱 전체 Gray Depth·밀도·테두리·공통 컨트롤 |

## 필수 완료 결과

1. **전체 Dark Gray**: Theme 토큰, 앱 팔레트, 공통 아이콘(16px/1.4px), 28px 컨트롤, 30px 메뉴, 44px Toolbar, 28px Status. 대형 흰색 팝업 없음.
2. **독립 Settings**: 10개 카테고리. 실제 연결된 값만 저장. Reset 확인 및 즉시 적용, Cancel 폐기, Apply 유지, OK 적용/닫기.
3. **Inspector 역할**: IMAGE 실제 메타데이터/ROI 표시, ANALYSIS 원본 ROI/모델 미연결/워크플로, RESULT 미실행 안내 및 비활성 결과 명령.
4. **명령 계층**: 메뉴는 전체 명령, Toolbar는 자주 쓰는 명령, Viewer는 이미지 조작, Status는 실제 상태. Viewer 안의 두 번째 도구 모음을 제거했다. ROI·확대 등은 메뉴+Toolbar 두 곳으로 제한한다.

## 상태와 데이터 정책

- 실제 상태: IDLE → LOADING → IMAGE READY → ROI SELECTED. 디코딩 실패 시 FILE ERROR와 오류 원문을 표시하며 이전 이미지와 ROI를 유지한다.
- 백그라운드 디코딩은 기존 TIFF 함수 호출 위치만 변경한다. TIFF 정규화와 다운샘플링 알고리즘은 보존한다.
- 성공한 파일만 최근 파일에 넣는다. 중복 제거, 최대 개수, 보관 해제, 복원 정책은 QSettings에서 검증한다.
- 배율 100%는 화면 맞춤. 실제 픽셀 100%는 준비 중이며, 기본 배율 설정은 다음 파일 열기에 적용한다.
- X/Y와 ROI는 원본 해상도 기반 픽셀 좌표다. Gray/물리 크기/보정/모델/Device 정보는 연결된 값이 없으므로 —로 표시한다.
- Analysis Ready / Processing / Completed / Failed: 현재 분석 백엔드가 없으므로 실제 검증 불가. 모델 연결 전 가짜 진행률·결함·성능을 넣지 않는다.
- 원본 파일/모델/외부 계약 변경 없음. 생성 테스트 TIFF는 임시 디렉터리에서만 만들고 Git에 넣지 않는다.

## 검증 기록

로컬 Windows: Python / PySide6 환경에서 ruff, compileall, pytest 및 native Qt 화면 캡처. 테스트 데이터는 생성 TIFF만 사용한다.

| 대상 | 결과 / 증거 |
|---|---|
| Main / IMAGE | industrial-main-image.png: TIFF 1024×768 / 16-bit / 첫 페이지, 실제 상태 |
| Empty | industrial-empty.png: TIFF 열기·드롭 안내 |
| Settings | General / Viewer / Model 준비 상태 / Reset 확인 화면, 10개 카테고리 |
| Settings 동작 | Cancel, Apply 후 추가 편집 취소, OK, Reset 취소/확인, 재실행 저장 검증 |
| ANALYSIS | industrial-analysis-roi.png: 마우스로 선택한 ROI 원본 픽셀 값, 모델 미연결 이유 |
| RESULT | industrial-result-empty.png: 분석 미실행 안내, 결과/Export 비활성 |
| Running / Complete | 검증 불가: 승인 모델·실행 파이프라인 없음 |
| Menu / Keyboard | 8개 순서, 설정 항목 1개, Alt/방향키/Escape, H/R, Ctrl+0, F11 |
| Viewer 회귀 | 16-bit TIFF, 해상도 비율, 확대/맞춤, 마우스 Pan/ROI, 좌표 및 복사, 이미지 닫기 |
| 최근 파일 / 오류 | 중복·최대 수·설정 저장·보관 해제, 손상/없는 파일 오류와 이전 이미지 유지 |
| 최소 화면 | industrial-demo-1100.png: 패널·핵심 Viewer·Toolbar 겹침 없음 |
| Dialog | industrial-about.png / settings-reset-confirm.png: 공통 다크 팝업 |
| 네이티브 파일 선택 | QML 연결 유지. OS 창의 마우스 수동 열기/취소는 미검증 |

로컬 검사: 8 tests passed, ruff 통과. 화면 캡처 스크립트: QML warnings 0. CI 결과는 PR에 기록한다.
