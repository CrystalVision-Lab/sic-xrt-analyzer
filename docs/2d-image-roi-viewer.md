# JPG·대형 2D TIFF·ImageJ ROI 뷰어

Issue #25. 기존 TIFF 스택과 PySide6/QML 화면에 단일 2D 이미지와 ImageJ ROI 표시를 연결했습니다. 외부 ImageJ/Fiji를 실행하지 않습니다. `sources/`와 사용자 원본을 수정하지 않습니다.

## 실행과 조작

Python 3.11 이상, Qt 그래픽 세션이 필요합니다. Windows 저장소 폴더에서:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[viewer]"
.\.venv\Scripts\python.exe -m sic_xrt_analyzer
```

Linux에서는 `.venv/bin/python`으로 동일하게 실행합니다. [Qt 시스템 의존성](tiff-stack-viewer.md#linux-데스크톱)을 참고하세요. 업데이트 후 실행 중인 프로그램을 다시 시작합니다.

1. `Ctrl+O` 또는 파일 드롭으로 TIFF/JPG/JPEG를 엽니다. 확장자 대신 파일 헤더를 확인합니다.
2. 기본 FIT, Pan(`H`), 휠 확대·축소, `Ctrl+0` 화면 맞춤, `Ctrl+1` 실제 크기를 사용합니다. 스택에서는 휠이 페이지 이동이고 `Ctrl+휠`이 확대입니다.
3. 오른쪽 **뷰어 탭**에서 표시 최소·최대와 자동/초기를 조절합니다. 표시 범위는 원본 배열에 적용되지 않습니다. TIFF ImageJ 저장 범위가 유효하면 초기값으로 사용합니다.
4. 이미지 위 마우스의 원본 X/Y와 값을 상태 표시줄에서 확인합니다. 정밀 값이 준비되기 전에는 `—`이며 축소 샘플값을 원본값으로 표시하지 않습니다.
5. **파일 → ImageJ ROI 가져오기** 또는 **ROI 탭 → 가져오기**에서 `.roi` 여러 개나 ROI ZIP을 선택합니다. 체크박스로 개별 표시를 바꾸고 이름으로 선택하며 `×`로 목록에서 제거합니다. 원본 파일은 삭제하지 않습니다.
6. **외접 사각형으로 선택**을 누르면 선택한 형상의 바깥 사각형을 기존 사각형 ROI에 반영합니다. Pan/Zoom/FIT에서도 형상은 원본 좌표에 정렬됩니다. 기존 드래그 사각형 ROI(`R`)도 유지합니다.

## 읽기·표시 구조

| 구성 요소 | 역할 |
|---|---|
| `imaging/image_stack.py` | TIFF/JPEG 헤더 구분, JPEG 원본 부분 읽기, 단일 이미지 샘플 표시 |
| `imaging/original_source.py` | TIFF 읽기 전용 mmap 샘플 및 정확한 영역 반환 |
| `ui/latest_reader.py` | 백그라운드 읽기, 최신 대기 요청 교체와 오래된 완료 폐기 |
| `ui/pixel_reader.py` | 원본 좌표의 정확한 작은 영역·픽셀 조회 |
| `ui/detail_reader.py` | 확대 시 보이는 원본 해상도 영역의 표시 범위 변환 |
| `imaging/imagej_roi.py`, `ui/roi_manager.py` | ROI/ZIP 파싱, 원본 경계·페이지 검증, 표시 목록 수명 |
| `ui/ImportedRoiOverlay.qml` | 화면 크기의 Canvas에 원본 좌표 변환으로 형상 표시 |

### JPG/JPEG

[Qt QImageReader](https://doc.qt.io/qt-6/qimagereader.html)의 JPEG 디코더에서 축소 읽기와 원본 clip 읽기를 사용합니다. Native ScaledSize/ClipRect 지원을 확인하며 전체 12k RGB 이미지를 NumPy 배열로 만들지 않습니다. 파일 크기·수정 시간 변경은 읽기 전후에 검사합니다.

JPEG는 **손실 압축의 디코딩된 RGB uint8/8-bit**입니다. 상태 표시줄 값은 밝기·대비 변환 전 디코딩 값이며 촬영 원시 16-bit 값이 아닙니다. EXIF 자동 회전은 끄고 인코딩된 원본 좌표를 유지합니다. ImageJ ROI와 좌표를 맞추기 위한 정책이며 EXIF 방향에 따른 회전은 지원하지 않습니다. 작은 JPEG는 원본 디코딩 샘플을 보관하고 큰 JPEG는 제한된 축소 샘플만 보관합니다.

### 대형 단일 TIFF

단일 페이지 원본 반환 크기가 기존 128 MiB 한도를 초과하면 `SampledImageStack`으로 전환합니다. 읽기 전용 tifffile memory map에서 stride로 샘플만 복사하고 map을 닫습니다. 원본 dtype/해상도와 TIFF 분석용 `OriginalImageSource`는 유지합니다. 실제 대상 9개 파일은 압축되지 않은 단일 RGB uint8 페이지이고 이 경로로 열립니다.

전체 페이지 배열을 복사하는 읽기나 임시 전체 디코딩 파일은 만들지 않습니다. **큰 압축·비매핑 TIFF는 아직 지원하지 않습니다.** 기존 원본 반환 128 MiB, 압축/비매핑 페이지 디코딩 64 MiB 제한을 올리지 않습니다. 다중 페이지 스택은 기존 전체 탐색 준비·캐시 정책을 유지합니다. ImageJ frames를 공간 Z축으로 해석하지 않습니다.

### 미리보기, 확대 정밀 영역, 원본값

- 단일 이미지 resident 원본 dtype 샘플은 **최대 32 MiB**, 긴 변 **2048px 이하**입니다. dtype/채널 수에 따라 더 줄입니다. 원본 TIFF 16-bit 배열은 수정하지 않으며 표시용 8-bit QImage만 변환합니다. uint8은 256개, uint16은 65,536개 LUT를 사용합니다.
- 샘플 화면을 확대하면 보이는 원본 영역을 백그라운드에서 읽어 같은 원본 좌표에 겹칩니다. 한 영역은 원본 가로·세로 각각 **2048px 이하**, 원본 작업 버퍼 추정량 **32 MiB 이하**로 제한합니다. 화면에 보이는 원본 영역이 이 한도를 넘으면 전체 축소 화면을 사용합니다.
- 이동/확대 입력 뒤 **70ms** 후 최신 정밀 영역을 요청합니다. 완료 전에는 미리보기를 표시하며 준비 중·실패 상태를 보여줍니다. 배율·원본·표시 범위가 바뀌면 오래된 영역을 지우고 구 완료 결과도 폐기합니다.
- 커서 조회는 **40ms** 후 원본 **128×128 이하 타일**을 비동기로 읽고 이 타일에서 값을 조회합니다. 전체 원본 페이지가 이미 캐시된 스택/작은 이미지에서는 기존 캐시값을 사용합니다.
- 동일 읽기 경로에서는 진행 중인 작업 1개와 최신 대기 1개만 유지합니다. 시작한 디코더를 강제 종료하지 않으므로 큰 JPEG 부분 디코딩과 느린 저장장치에서는 정밀 영역이 늦게 나타날 수 있습니다. 즉시 모든 원본 픽셀이 준비된다고 보장하지 않습니다.
- 캐시/작업 배열 한도는 Qt 디코더·OS 파일 캐시·GPU를 포함한 프로세스 전체 RAM 상한이 아닙니다. Qt 전역 이미지 allocation 제한도 해제하지 않습니다.
- 새 파일 요청 시 이전 비동기 결과를 무효화하고 새 파일 열기 성공/닫기 때 ROI와 커서·정밀 영역을 정리합니다. 열기 실패하면 이전 화면을 유지합니다. 종료 시 진행 중인 읽기가 끝날 때까지 기다립니다.

## ImageJ ROI 범위와 좌표

[roifile](https://github.com/cgohlke/roifile)을 사용합니다. Python 3.11 호환 버전을 유지하도록 `roifile>=2024.3.20,<2026`을 `viewer`/`ui` 의존성에 추가했습니다.

- 점·다중 점, 다각형/freehand/traced, 일반 사각형, 타원, line/polyline/freeline/angle과 지원 가능한 복합 경로를 표시합니다. 원본 stroke 색이 있으면 사용합니다. 점 표시와 선 굵기는 화면 픽셀 기준입니다.
- 타원은 표시용 다각 경로로 근사합니다. 텍스트·화살표·회전형 등 특수 subtype과 둥근 사각형은 명시적으로 지원하지 않습니다. 빈/잘못된 파일은 오류로 구분하며 ZIP 안의 정상 ROI는 유지합니다.
- ZIP은 멤버 바이트만 읽고 디스크에 압축을 풀지 않습니다. ROI 1개 4 MiB, 합계 32 MiB, 1024개, 합계 200,000개 점의 한도를 적용합니다.
- 좌상단 `(0,0)`, 오른쪽 x, 아래쪽 y의 **원본 이미지 좌표**를 사용합니다. 경계를 벗어난 ROI는 거절합니다. 파일명으로 대응 이미지를 추정하거나 비율을 바꾸지 않습니다. 대응 이미지 선택은 사용자의 책임이며 이미지 안에 들어간다는 사실만으로 같은 촬영 데이터임을 증명하지 않습니다.
- flat one-based page 위치가 있으면 해당 페이지에서 표시합니다. T/Z 위치는 파일의 frames/slices와 일치해 모호하지 않고 다른 채널·축 위치가 섞이지 않는 경우만 대응시킵니다. 지원하지 않는 혼합 C/Z/T는 오류입니다. 위치가 없는 ROI는 전체 페이지에서 표시합니다.
- ROI 가져오기는 **표시와 목록 관리**입니다. ROI 파일 편집·재저장·내보내기·다각형 mask 분석은 구현하지 않았습니다. 명시적 외접 사각형 선택만 기존 직사각형 분석 ROI로 전달합니다.

## 분석 계약과 저장소 경계

외부 계약 버전 **1.0**, `AnalysisRequest`/`AnalysisResult`/ModelAdapter 스키마·좌표·호환성은 변경하지 않습니다. TIFF 분석은 기존 `OriginalImageSource`의 원본 영역을 읽습니다. JPEG 원본 객체는 뷰어에서만 사용하고 분석 pipeline에는 전달하지 않습니다. 가져온 형상을 모델 결과로 표시하지 않습니다. 승인 모델은 아직 없어 분석 실행은 비활성화입니다.

사용자 TIFF/JPG/ROI/ZIP은 읽기 전용입니다. `sources/` 참조 파일과 다른 저장소는 수정하지 않습니다. 실제 데이터, 가공 영상, 픽셀값이 든 로컬 검증 보고서는 Git에 넣지 않습니다.

## 검증 결과 (2026-10-02, Windows)

사용자 `2D XRT` 폴더의 압축 해제된 파일을 읽기 전용으로 확인했습니다.

| 실제 파일 | 결과 |
|---|---|
| JPG/JPEG 347개 | 정상 346개: 열기·표시 범위 변경·원본 중앙 픽셀 부분 읽기 PASS |
| 대형 2D TIFF 9개 | 모두 PASS; 약 12k×12k 단일 RGB uint8, 원본 페이지 약 423–434 MiB |
| JPG 오류 1개 | `2 Area/After annealing_2_x100/1.jpg`: ZIP 원본부터 JPEG 헤더가 아님 |
| `.roi` 88개 | 유효 86개, 모두 POINT/multipoint, 총 23,709개 점 |
| ROI 오류 2개 | `Before an_9_3_TED(e).roi`, `Before an_9_1_TED(e).roi`: 0-byte 빈 파일 |
| `RoiSet.zip` 2개 | 정상 ROI 9개와 7개 읽기; 두 번째 ZIP의 빈 ROI 1개는 개별 오류 |
| 실제 QML 화면 | JPG 1개 + TIFF 9개 열기/확대 정밀 영역, ROI 15개 가져오기와 외접 사각형 좌표 일치; QML 경고 0 |
| 원본 보존 | 검사 전후 파일 크기와 mtime 미변경 |

배치 ROI 검증은 폴더 이미지들의 최대 경계를 사용한 **파싱·형상 검증**입니다. 전체 86개 ROI와 각각의 촬영 이미지를 자동 대응한 검증이 아닙니다. 실제 대응 TIFF를 연 QML 검사에서는 ROI 원본 좌표와 외접 사각형 전달을 별도로 확인했습니다. 배치 검증은 251.11초이며 UI 열기 지연이나 화면 FPS 측정은 아닙니다.

총 **95개 자동 테스트**가 통과합니다. 이번 15개 검사는 JPEG RGB값/EXIF 좌표·원본 변경, 큰 TIFF 전체 읽기 금지와 메모리 한도, 정확한 픽셀/확대 crop, ROI 6종·ZIP 오류·페이지 위치·한도, 최신 요청·파일 교체·ROI clear 시 구 결과 폐기, 실제 QML 표시 범위·외접 사각형 좌표·분석 원본 분리를 포함합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,viewer]"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
# 실제 파일은 읽기 전용, 보고서는 Git에서 제외되는 artifacts 아래 저장:
.\.venv\Scripts\python.exe tools/validate_2d_images.py "<2D XRT 폴더>" --output artifacts/2d-validation.json
# 아래 캡처는 임시 합성 데이터만 사용:
.\.venv\Scripts\python.exe tools/capture_2d_roi.py
```

![합성 JPG와 ROI, FIT](screenshots/2d-roi/jpeg-roi-fit.png)

[100% 원본 영역 표시](screenshots/2d-roi/jpeg-roi-100-detail.png) · [1100×700](screenshots/2d-roi/jpeg-roi-1100.png)

캡처는 Windows native Qt 렌더링이며 임시 생성 JPG/ROI만 포함합니다. 실제 XRT 이미지는 포함하지 않습니다. 네이티브 파일 선택 창의 수동 마우스 조작과 Linux 그래픽 세션 현장 검증은 별도입니다. 기존 Linux 경로의 3D XRT 4개 실파일 검증은 이 Windows 2D 검증으로 대체하지 않습니다. 3D 재구성은 촬영 순서·방향·실제 간격 확인 뒤 별도 단계입니다.
