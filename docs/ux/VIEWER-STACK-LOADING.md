# 공통 이미지 뷰어와 TIFF 준비 표시

Issue: [#94](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/94)

## 사용법

- 왼쪽 첫 작업 영역과 창 메뉴를 **이미지 뷰어**로 통일했다. JPG/JPEG와 TIFF 모두 여기서 탐색하며 **분석하기**는 기존 분석 준비 패널을 연다.
- 두 형식 모두 기본 우측 패널을 접어 Viewer를 넓게 사용한다. **패널 ▾ → 뷰어·스택**에서 페이지 이동·밝기/대비를 열고 **×**로 접는다. TIFF의 내부 Context는 viewer, JPG의 Context는 image로 유지한다.
- 파일을 여는 동안 기존 이미지 로딩 표시를 유지한다. TIFF 첫 페이지가 표시된 뒤에도 전체 탐색 준비가 진행 중이면 이미지 중앙에 **TIFF 스택 준비 중…**, 진행 막대, **준비 페이지 / 전체 페이지 · %**, **준비 취소·닫기**를 표시한다. 전체 준비 완료 시 자동으로 사라진다.
- 준비 중 현재 페이지의 Pan/Zoom/Fit와 기존 분석 계약은 그대로다. 새 상태 카드는 비모달이며 준비 시간을 늘리거나 추가 디코딩을 하지 않는다. 페이지 탐색·밝기/대비·ImageJ는 기존 전체 준비 조건을 유지한다.
- 준비 오류는 기존 Viewer 오류 안내의 **다시 준비 / 상세 정보…**로 복구한다. 취소는 기존 닫기 Action을 실행한다. 단일 TIFF/JPEG는 스택 진행률을 표시하지 않는다.

왼쪽 3D 뷰어로 이동하거나 frames를 공간 Z축으로 간주하지 않는다. 원본 픽셀,
bit depth, 좌표계/ROI, 분석 입력/ONNX 결과, ImageJ/Fiji, Export, Native Dialog,
원본 XRT와 sources/, 사용자 AGENTS.md를 변경하지 않았다.

## 검증 (2026-10-12)

- 로컬 관련 검사 29 PASS (29.96초), 추가 기존 UI·분석·ROI·결과 검사 74 PASS (162.45초), 총 103 PASS. Ruff/compileall/whitespace PASS. 새 검사 3개를 포함한다.
- 실제 reader의 준비 worker를 잠시 대기시키는 합성 uint16 TIFF로 첫 페이지 준비와 전체 스택 준비를 구분한다. 1100×700·1440×900에서 패널이 접혀도 진행률 4/8·50%와 회전 표시가 Viewer 중앙에 보이는지, 준비 완료·취소·오류·단일 파일 전환 후 숨겨지는지 검사한다.
- 기존 TIFF/JPEG 실제 포맷 판정, 수동 설정 접근, ROI/페이지/오류 처리 회귀를 유지한다. QML warnings를 수집하는 QTest fixture를 사용한다.
- 전체 CI 및 추가 UI 회귀 결과는 연결 PR에 기록한다. 원본 XRT의 로딩 시간이나 Windows Native Dialog 수동 Acceptance를 새로 측정한 작업은 아니다.
