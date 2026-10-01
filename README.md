# sic-xrt-analyzer

SiC XRT 이미지의 데스크톱 분석 앱입니다. PySide6/QML UI, TIFF 로딩, 웨이퍼 맵, 이미지 정합, 3D 시각화, 승인된 ONNX 모델 추론을 이 저장소에서 다룹니다. 기능 구현은 각 GitHub Issue에서 범위를 먼저 정합니다.

## 시작

- Python 3.11 이상
- 개발 도구: `python -m pip install -e ".[dev]"`
- UI 실행: `python -m pip install -e ".[ui]"` 후 `python -m sic_xrt_analyzer`
- 검사: `ruff check .`, `pytest` (`pytest`의 UI 스모크 검사는 PySide6가 필요합니다)

## 초기 UI

`python -m sic_xrt_analyzer`로 1440×900 기본 창을 엽니다. 창은 1100×700까지 줄일 수 있고 좌우 패널을 접어 이미지 영역을 넓힐 수 있습니다. 상단 **이미지 열기** 또는 `Ctrl+O`로 TIFF 파일 선택 창을 열 수 있습니다. 취소하면 현재 파일 선택은 유지됩니다.

- **이미지 분석**: 파일 선택 후 이름과 경로를 UI 상태에 보관합니다. 이미지 디코딩과 실제 TIFF 표시는 아직 연결되지 않았음을 뷰어에 표시합니다.
- **데모 보기**: 실제 SiC 데이터가 아닌 합성 샘플을 엽니다. 상단 확대·축소, `화면 맞춤`, 마우스 휠, 뷰어의 이동·영역 선택을 시험할 수 있습니다. 배율 100%는 화면 맞춤을 기준으로 합니다. `Ctrl+0`, `Ctrl++`, `Ctrl+-`도 사용할 수 있습니다.
- **Wafer Map·이미지 정합·3D 보기**: 탐색 항목과 준비 안내 화면만 제공합니다.
- **정보 및 설정**: 파일명 외의 이미지 크기·물리 스케일은 읽지 않았으므로 `—`로 표시합니다. 밝기·대비·결함 레이어는 비활성화되어 있습니다. 모델은 미연결이며 분석 실행도 비활성화되어 있습니다. 결과 화면은 분석 전 빈 상태를 보여줍니다.

UI는 `src/sic_xrt_analyzer/ui/`의 역할별 QML 컴포넌트와 공통 테마·상태 객체로 구성됩니다. 현재 Python 연결은 파일 선택 URL을 로컬 경로로 변환하는 작은 브리지만 제공합니다. 추후 TIFF 로더는 선택된 파일 경로와 이미지 뷰어를, 추론 기능은 승인된 모델 계약과 분석·결과 패널을 연결하면 됩니다. 결함 라벨과 분석 성능은 아직 정하지 않았습니다. TIFF·정합·3D·추론의 실제 동작은 별도 Issue와 기능별 PR로 구현합니다.

### 화면 캡처

아래 화면은 Qt 오프스크린 렌더링으로 캡처했습니다. 데모에는 합성 이미지 외의 검사 데이터가 포함되지 않습니다.

![초기 빈 화면](docs/screenshots/initial-empty.png)

![데모 이미지와 관심 영역 선택](docs/screenshots/initial-demo.png)

[1100×700 화면 보기](docs/screenshots/initial-demo-1100.png)

## 구조

`src/sic_xrt_analyzer/` 아래 `ui/`, `imaging/`, `wafer_map/`, `registration/`, `reconstruction/`, `inference/`를 분리합니다. 외부 모델은 버전·해시·입출력 규약을 확인한 산출물로만 받습니다.

작업 전 [AGENTS.md](AGENTS.md)와 [공통 handbook](https://github.com/CrystalVision-Lab/engineering-handbook)을 읽으세요. 이 저장소의 변경만 이 저장소 PR에 담습니다.
