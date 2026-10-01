# TD — Industrial UI Polish & Consistency

Issue #9. 기존 Industrial Dark Gray 구조와 패널 비율을 유지하고 배율 의미·한국어·ROI·상태·미연결 안내를 정리한다.

## 완료 결과

- **FIT ≠ 100%**: 화면 맞춤 모드는 FIT, 그 외에는 원본 픽셀 대비 실제 화면 배율을 소수 한 자리까지 표시한다. 보기 메뉴의 실제 크기 100%와 Ctrl+1을 추가했다.
- 화면 배율은 원본 픽셀에 대한 **화면 물리 픽셀** 비율이다. Qt 장치 픽셀 비율을 반영한다. FIT은 창/패널 크기에 자동 반응하며, 절대 배율은 창 크기가 바뀌어도 유지한다.
- 기본 보기: 화면 맞춤 / 100% (1:1) / 125% / 200%. QSettings의 기존 상대 defaultZoom은 화면 맞춤으로 마이그레이션하고 다른 설정은 보존한다. 저장 필드는 defaultView로 변경한다.
- 일반 UI는 한국어. 기술 용어 XRT/TIFF/ROI/Pan/AI/LUT/Wafer Map/3D는 유지한다. Inspector 탭은 이미지/분석/결과로 표시하며 책임과 구성은 유지한다.
- 향후 작업 영역은 작은 ○와 설명 Tooltip, 미연결 설정은 안내 한 번과 설명만 제공한다. 화면을 채우던 비활성 입력란·선택란·체크박스를 제거했다.
- ROI 선택 중 테두리 2px/채움 20÷255(7.8%), 완료 후 테두리 1px/채움 10÷255(3.9%). 원본 좌표 계산은 유지한다.
- Toolbar: 모델 미연결과 실행 버튼. Inspector: ROI·모델 상세 이유·작업 상태. Status: 실시간 도구·배율·X/Y·해상도·비트 깊이, 작은 모델 값. ROI 선택 상태를 Toolbar/Status에 중복 강조하지 않는다.
- 저장·분석·내보내기는 비활성 상태를 유지한다. 활성 기능과 혼동하지 않게 비활성 선택 버튼의 Accent 테두리를 정리했다.

## 범위와 한계

TIFF 디코딩·정규화·4096px 미리보기 정책·백그라운드 로딩·오류 시 이전 이미지 유지·최근 파일·원본 ROI·QSettings를 보존한다.

1:1은 **원본 좌표 격자의 표시 배율**이다. 큰 TIFF의 축소 미리보기를 다시 확대해 표시할 수 있으며 원본의 모든 미세 픽셀 정보를 복원하는 기능은 아니다. 원본 전체 해상도/타일 뷰어는 후속 기능이다. 합성 데모는 실제 검사 이미지가 아니다.

모델/분석/결함 Overlay/결함 목록/결과 Export/물리 보정/원본 Gray 조회는 미연결이다. 가짜 모델·결과·장비·성능값은 만들지 않는다. 학습·데이터 도구·외부 모델 계약에는 변경이 없다.

## 검증

기존 8개 테스트를 유지하고 1개 마이그레이션 테스트를 추가했다: **9 passed**.

| 검증 | 결과 |
| --- | --- |
| FIT / 실제 배율 | FIT 라벨, 확대/축소, Ctrl+0, 실제 크기, 125%/200%, 창 변경 시 FIT 유지 |
| 고해상도 화면 | 화면 픽셀 비율 2에서 원본 512px → Qt 논리 폭 256 확인 |
| 기본 보기 | 네 가지 선택, QSettings 저장, TIFF 재열기와 실제 표시 배율 일치 |
| 설정 | 10개 한국어 분류, 취소/적용/확인, 복원 취소/확인, 재실행 저장 |
| 기존 설정 | 상대 defaultZoom → FIT, 보간/최근 개수 보존 |
| TIFF / 오류 | 16-bit, 원본 메타데이터·비율, 비동기 로딩, 손상 파일에서 이전 이미지 유지 |
| Pan / ROI | 실제 마우스 이동/선택, 원본 좌표·클립보드, 선택/완료 테두리 및 Alpha |
| Status | 이미지 준비·ROI 선택 상태, 실시간 X/Y, FIT/실제 라벨 |
| Layout | 1100×700 Toolbar·탭·Status와 핵심 Viewer, 패널 숨김 시 확장 |
| 화면 | Windows 실제 Qt 렌더링, QML 경고 0 |

네이티브 OS 파일 선택 창의 마우스 수동 조작과 실제 분석 Running/Complete는 미검증이다. 분석 백엔드가 없어 후자는 실행할 수 없다.

## 새 화면

[이미지](screenshots/polish/01-main-image.png) · [ROI](screenshots/polish/02-main-roi.png) · [분석](screenshots/polish/03-analysis.png) · [결과 없음](screenshots/polish/04-result-empty.png) · [설정 일반](screenshots/polish/05-settings-general.png) · [설정 뷰어](screenshots/polish/06-settings-viewer.png) · [1100×700](screenshots/polish/07-minimum-1100x700.png)

생성한 테스트 TIFF만 사용했다. 원본 TIFF는 임시 디렉터리에서 생성·삭제하고 Git에 넣지 않는다.

## 이력 정리

기존 CI가 통과한 head를 확인하고 GitHub의 merge 방식으로 #4 → #6 → #8을 병합했다. #6/#8은 먼저 대상을 main으로 변경했다. squash/rebase/강제 push 없이 원본 커밋을 보존했다.

| PR | 병합 SHA |
| --- | --- |
| #4 | 1d4f6c5d5612337f65a1927449b7204af1225062 |
| #6 | 07582f2249cf0ad059da373299d1e56355844c07 |
| #8 | 0d3904795e89d70854b3b3f2c940c03fd4c19ae5 |

Polish PR과 최종 main SHA/CI는 PR 완료 보고에 기록한다. main에서 로컬 검사와 push CI를 다시 확인한다.

## 다음 연결 순서

승인 모델·입출력 계약 → 실제 분석 실행 상태 → 결과 Overlay → 결함 목록/좌표 → 결과 내보내기. UI 구조의 추가 전면 개편은 하지 않는다.
