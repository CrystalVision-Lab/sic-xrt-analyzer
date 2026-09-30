# sic-xrt-analyzer

SiC XRT 이미지의 데스크톱 분석 앱입니다. PySide6/QML UI, TIFF 로딩, 웨이퍼 맵, 이미지 정합, 3D 시각화, 승인된 ONNX 모델 추론을 이 저장소에서 다룹니다. 기능 구현은 각 GitHub Issue에서 범위를 먼저 정합니다.

## 시작

- Python 3.11 이상
- 개발 도구: `python -m pip install -e ".[dev]"`
- UI 실행: `python -m pip install -e ".[ui]"` 후 `python -m sic_xrt_analyzer`
- 검사: `ruff check .`, `pytest`

현재는 QML 진입점과 모듈 경계만 마련했습니다. TIFF·정합·3D·추론의 실제 동작은 별도 Issue와 기능별 PR로 구현합니다.

## 구조

`src/sic_xrt_analyzer/` 아래 `ui/`, `imaging/`, `wafer_map/`, `registration/`, `reconstruction/`, `inference/`를 분리합니다. 외부 모델은 버전·해시·입출력 규약을 확인한 산출물로만 받습니다.

작업 전 [AGENTS.md](AGENTS.md)와 [공통 handbook](https://github.com/CrystalVision-Lab/engineering-handbook)을 읽으세요. 이 저장소의 변경만 이 저장소 PR에 담습니다.
