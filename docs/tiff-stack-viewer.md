# 내부 XRT TIFF 스택 뷰어

Issue #13 · PR #12의 원본 소스/분석 계약 기반 위에 구현했습니다.
외부 ImageJ/Fiji를 실행하지 않습니다. 이번 범위는 **2D 페이지 탐색**입니다.

## 구조와 선택 근거

기존 프로젝트는 Python 3.11+, PySide6/Qt Quick QML, NumPy, tifffile/imagecodecs입니다.
Qt UI와 기존 Pan/Zoom/FIT/ROI를 유지하고 아래 구성 요소를 추가했습니다.

| 구성 요소 | 역할 |
|---|---|
| `imaging/tiff_pages.py` | 실제 TIFF IFD 및 ImageJ 단일 IFD의 논리 페이지 인덱스 |
| `imaging/original_source.py` | 읽기 전용 원본 페이지/영역, dtype/값 보존, 변경 탐지 |
| `imaging/tiff_stack.py` | raw/정밀 표시 LRU, 전체 BrowseCache, uint16 표시 변환, ImageJ 범위 |
| `ui/stack_controller.py` | 전체 페이지 준비, 진행률/재시도, 드래그 즉시 게시, 마지막 페이지 정밀 읽기 |
| `ui/StackControls.qml` | 오른쪽 뷰어 탭의 페이지 탐색, 표시 범위, 준비 상태 |
| `ui/InspectorPanel.qml` | 이미지/분석/결과/뷰어 탭과 세로 스크롤 |
| `tools/validate_tiff_stack.py` | 실제 파일 first/middle/last 원본·표시·한도 검증, 읽기 전용 |
| `tools/benchmark_tiff_scroll.py` | 생성 영상 또는 읽기 전용 실제 TIFF의 변환·캐시·게시 시간 측정 |

[tifffile 공식 문서](https://www.cgohlke.com/docs/tifffile/)에서 multi-page/ImageJ TIFF,
페이지 단위 `asarray`와 읽기 전용 memory map을 제공하므로 기존 라이브러리를 유지했습니다.
표시는 QML Image에 QImage를 전달하고 원본 uint16 배열은 별도로 보관합니다.
전체 stack `asarray()`는 호출하지 않습니다. ModelAdapter/분석 입력은 계속 OriginalImageSource를
사용하며 표시 범위 변경으로 분석 원본을 바꾸지 않습니다. 외부 모델 계약은 변경하지 않습니다.

## 실행

### Linux 데스크톱

Python 3.11 이상과 그래픽 로그인 세션이 필요합니다. 저장소 디렉터리에서:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[viewer]'
.venv/bin/python -m sic_xrt_analyzer
```

Ubuntu/Debian의 최소 환경에서 Qt 플랫폼 라이브러리가 없다면:

```bash
sudo apt-get install python3-venv libegl1 libopengl0 libxcb-cursor0
```

Qt Python wheel에는 Qt 바이너리가 포함됩니다. 별도의 Qt 개발 도구나 ImageJ 설치는 필요하지
않습니다. 설치 환경은 [Qt for Python 공식 안내](https://doc.qt.io/qtforpython-6/gettingstarted.html)를
따릅니다. 배포판·X11/Wayland에 따라 추가 시스템 라이브러리가 필요할 수 있습니다.

### Windows PowerShell

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[viewer]"
.\.venv\Scripts\python.exe -m sic_xrt_analyzer
```

`viewer` extra는 PySide6/NumPy/tifffile/imagecodecs만 설치합니다. 학습·추론 프레임워크는
스택 보기의 설치 요구 사항이 아닙니다. 기존 `ui` extra도 계속 사용할 수 있습니다.

## 조작

- 파일 → 이미지 열기 (`Ctrl+O`)에서 TIFF를 선택하거나 Viewer에 drop합니다. 처음에는 페이지 1을 표시합니다.
- TIFF 열기 성공 시 오른쪽 **뷰어 탭**을 자동으로 엽니다. 이 탭에 페이지 탐색,
  밝기·대비, 전체 준비 상태와 조작 안내를 모았습니다. 이미지/분석/결과 탭도 유지합니다.
- 뷰어 탭의 페이지 슬라이더·‹/› 버튼, 이미지 위 휠, 방향키/PageUp/Down, Home/End로 이동합니다.
  방향키는 Viewer 또는 페이지 슬라이더에 포커스가 있을 때 사용합니다.
- 파일을 열면 **모든 페이지를 준비할 때까지 중앙 로딩 화면을 유지**합니다. 첫 페이지가
  읽혀도 로딩을 해제하지 않습니다. `전체 페이지 불러오는 중 N / 전체` 진행률을 표시하고
  스크롤·슬라이더·방향키·확대·표시 범위 변경을 차단합니다. Python 요청도 이 기간에 거절합니다.
  100% 완료 후 로딩 화면을 닫고 탐색을 활성화합니다. 준비된 일부 페이지를 먼저 탐색하지 않습니다.
- 준비 실패 시 로딩 잠금을 유지하며 원인과 `다시 준비`/`취소`를 제공합니다. 창과 파일 열기,
  취소/닫기는 계속 반응합니다. `Ctrl+W`도 로딩 취소에 사용할 수 있습니다.
- 드래그 중에는 탐색용 화면, 손을 놓으면 선택한 페이지의 정밀 화면을 표시합니다.
  휠/키 이동도 준비된 화면을 먼저 표시하고 마지막 입력 후 80ms부터 정밀 읽기를 요청합니다.
- 스택에서 기본 휠은 페이지, **Ctrl+휠은 확대·축소**입니다. 단일 이미지는 기존 휠 확대를 유지합니다.
- Pan으로 이동하고 도구 모음 확대·축소·FIT, `Ctrl+0`, `Ctrl+1`을 사용합니다.
- 하단 조작 패널을 제거하여 이미지 영역을 확장했습니다. 기본 FIT는 종횡비와 이미지
  전체를 유지하는 최대 배율이며 가장자리 여백은 8px입니다. 긴 이미지나 넓은 이미지의
  남는 공간은 원본 종횡비에 따라 달라집니다. 설정에서 명시한 기본 배율은 계속 적용합니다.
  탭을 전환해도 페이지·표시 범위·배율은 유지됩니다.
- `표시 최소/최대` 슬라이더나 숫자 입력으로 밝기·대비 범위를 정합니다. 최소값은 최대값보다 작아야 합니다.
- 초기 범위는 유효한 ImageJ `min/max`, 또는 단일 채널 `Ranges`를 사용합니다.
  저장 범위가 없거나 잘못되면 첫 페이지의 샘플 1~99 백분위(8-bit는 0~255)를 사용합니다.
  이 범위를 페이지 이동에도 유지합니다. `자동`은 현재 요청 페이지의 범위, `초기`는 파일 초기 범위입니다.
- 아래 상태 표시줄은 원본 이미지 X/Y 좌표와 **캐시된 현재 페이지의 원본 픽셀값**을 표시합니다.
  축소된 preview 값이나 표시용 8-bit 값을 보여주지 않습니다. 마우스 이동은 TIFF를 읽지 않습니다.
  탐색용 화면에서 원본이 준비되기 전에는 값이 `—`입니다. 다른 페이지의 값이나 축소 샘플을
  원본 픽셀값으로 표시하지 않습니다. 선택 페이지 원본이 로드되면 원본 값이 다시 나타납니다.
- Viewer 헤더/Inspector에 현재 표시 페이지/전체 페이지, 해상도, dtype이 나타납니다.
  로딩 중 슬라이더 위치는 요청 페이지이고, 페이지 번호는 **현재 실제 표시 페이지**입니다.

ImageJ `frames`/`slices`는 파일의 저장 라벨로만 보존합니다. frames를 공간상의 Z라고
해석하지 않으며 거리·방향·공간 간격을 추측하지 않습니다. 3D 작업 영역은 아직 미연결입니다.

## 메모리·스케줄링·파일 수명

- 읽는 단위는 원본 페이지 하나입니다. 대상 페이지 약 16~19 MiB가 읽기 한도 안에 들어가면
  전체 TIFF가 2.5~2.9 GB여도 해당 페이지를 열 수 있습니다.
- mmap 가능 페이지는 읽기 전용 map에서 페이지만 복사합니다. ImageJ single-IFD contiguous
  stack은 읽기 전용 가상 map을 페이지 view로 잘라 복사합니다. 가상 map이 전체 파일을
  주소 공간에 연결하더라도 전체 stack을 RAM 배열로 만들지는 않습니다.
- 압축 페이지는 해당 페이지만 decode하며 기본 **64 MiB/page** 제한을 적용합니다.
  원본 반환 배열은 **128 MiB/page** 제한입니다. 한도를 넘는 페이지에는 영역 decoder가 필요합니다.
- LRU는 최대 **3페이지 및 96 MiB**의 raw 배열을 보관하며 둘 중 먼저 도달하는 한도를 지킵니다.
  한 페이지가 cache byte 한도보다 크면 보관하지 않습니다. 원본 배열은 non-writable입니다.
- 별도의 표시 캐시는 **최대 32 MiB**이며 raw 캐시에 남은 페이지만 보관합니다. 페이지당 표시
  범위 하나만 저장하고 raw eviction 시 해당 표시도 제거합니다. 이전 밝기·대비 화면을 잘못
  게시하지 않도록 페이지와 표시 범위를 함께 검사합니다. uint16은 65,536단계 lookup table로
  변환하여 전체 영상의 float64 임시 배열 생성을 피합니다. 원본 값은 바뀌지 않습니다.
- **전체 탐색 캐시**는 별도로 최대 **512 MiB**의 배열/QImage 버퍼를 보관합니다. 기본 긴 변은
  1024픽셀 이하이며 모든 페이지의 원본 dtype 샘플과 표시용 8비트 화면을 보관합니다.
  예상 총량이 한도를 넘으면 샘플 간격을 늘립니다. 원본 크기의 배열 전체를 보관하지 않습니다.
  이 캐시는 raw LRU eviction과 무관하게 유지되므로 준비 완료 뒤 임의/역방향 드래그에도
  원본 재읽기/디코딩이 없습니다. 표시 범위 변경은 저장된 원본 dtype 샘플에 적용하며 페이지를
  버리거나 파일 전체를 다시 읽지 않습니다. 재변환은 해당 페이지를 탐색할 때 수행합니다.
- 캐시 외 현재 표시 페이지와 작업 중 페이지/표시 변환 임시 배열/QImage가 추가로 존재합니다.
  96 MiB는 프로세스 전체 RAM quota가 아닙니다. 이미지 크기에 따른 메모리는 있지만
  전체 탐색 버퍼도 설정한 한도 안에서만 쌓고 원본 스택 전체 배열은 만들지 않습니다.
- 원본 읽기와 정밀 표시 변환은 worker에서 실행합니다. 탐색 화면은 GUI 이벤트에서 바로
  게시합니다. 표시 범위가 달라진 탐색 화면은 제한된 크기의 resident 샘플만 GUI에서 변환합니다.
  드래그 중에는 TIFF 픽셀 읽기 및 metadata 재조회가 없으며, 손을 놓은 정밀 읽기에서 파일
  identity를 검증합니다. 정밀 화면 준비 전까지 원본 픽셀값은 표시하지 않습니다.
  짧은 lock으로 캐시 조회/교체를 보호하고 디스크 읽기·렌더링 중에는 lock을 잡지 않습니다.
- 읽기 1개가 진행 중이면 pending 요청은 **최신 1개로 교체**합니다. 이미 시작한 decode는
  강제 중단하지 않지만 완료 후 구 요청은 게시하지 않고 최신 요청을 처리합니다.
- 첫 페이지 게시 후 worker가 전체 페이지를 순차 준비합니다. `initialLoading` 상태가 전체 완료
  전까지 유지되고 UI의 파일 열기 상태와 함께 탐색을 잠급니다. GUI에서 진행률을 알리고 준비
  실패 시 원인과 `다시 준비`를 표시합니다. 슬라이더는 `live`이며 pressed 상태에서도 게시합니다.
  이미 준비된 화면을 드래그하는 동안 백그라운드 사전 읽기는 계속됩니다. 손을 놓은 정밀 읽기는
  사전 읽기를 취소하고 우선 처리합니다. 새 드래그는 이전 정밀 읽기 결과를 무효화합니다.
  초기 준비가 끝나기 전에는 아직 준비되지 않은 페이지의 요청도 허용하지 않습니다.
- 새 파일은 이전 작업 결과를 무효화하며 이전 worker가 읽기를 끝낸 뒤 이전 cache를 비웁니다.
  TIFF/mmap handle은 페이지 읽기 후 닫습니다. 성공한 새 페이지로 현재 표시 raw도 교체합니다.
  전체 탐색 캐시도 함께 정리하고 다른 파일의 샘플/화면/진행률을 섞지 않습니다.
- 새 파일/페이지 읽기 실패 시 이전 화면과 그 raw pixel snapshot을 유지하고 오류를 표시합니다.
  파일 size/mtime 변경을 검사하고 다시 열도록 안내합니다. 열기 시도에는 이전 분석 결과를 지웁니다.
- 페이지 변경은 분석 source identity를 바꿔 이전 결과를 무효화합니다. 표시 범위 변경만으로
  같은 페이지의 분석 요청/결과를 무효화하지 않습니다. 새 페이지에서 ROI는 초기화합니다.
- 닫기·종료 시 pending을 정리하고 active 읽기가 끝난 뒤 cache/raw를 해제합니다.
  느린 디스크/decoder는 마지막 읽기 및 종료를 지연할 수 있습니다.

Production 경로에는 TIFF 쓰기·덮어쓰기·삭제 호출이 없습니다. 생성 TIFF 쓰기는 테스트와
synthetic capture 도구에만 있으며 임시 폴더를 사용합니다. `sources/` 참조 파일은 수정하지 않았습니다.

## 검증 결과

### 구현 검증: PASS

기존 **42개 유지 + 스택 17개 + 탐색 성능 회귀 8개 + 전체 탐색 10개 + 초기 로딩 3개 = 80개** 자동 테스트가 통과했습니다.

- uint16 BigTIFF/압축 multi-page, ImageJ TYX frames, ImageJ single-IFD truncated stack
- 첫·중간·마지막 페이지, 원본 배열/ROI/dtype 동일, source bytes/mtime 보존
- ImageJ min/max/Ranges, 잘못된 range fallback, 표시 범위만 바뀌고 raw·decode 횟수 유지
- LRU page/byte 한도, cache eviction, 파일 교체·닫기 시 정리
- 읽기 block 중 1→2→3→4→5→6 요청: 실제 읽기 1과 마지막 6만 수행, 중간 결과 게시 방지
- 이전 파일 읽기 중 새 파일 요청: 이전 파일 결과 무시
- QML slider/방향키/Home/End/휠/Ctrl+휠/FIT, contrast sliders, 원본 cursor 값, 1100×700
- 읽기/범위 오류, 이전 화면 유지, source 변경 탐지
- uint16 전체 65,536값의 lookup 표시와 기존 float 변환 일치, MINISWHITE·소수 표시 범위
- 표시 캐시 범위/파일 identity/eviction/byte 제한, 종료 시 raw·표시 캐시 해제
- prefetch 중 캐시 페이지 즉시 게시·역방향 이동, 마지막 요청 우선, 범위 변경 후 새 표시 사용
- prefetch 중 파일 교체 정리, QML 휠 이벤트에서 준비된 페이지 즉시 반영, benchmark CLI
- 전체 캐시 byte 한도에 맞춘 샘플 크기 축소, 원본 dtype 샘플 불변, 전 페이지/역방향 무읽기 탐색
- 실제 QML 마우스 press→여러 위치 move→release: 누른 상태에서 페이지 변경, release 때 최종 1개 읽기
- 드래그 전환으로 이전 정밀 읽기 취소, 파일 변경 시 오래된 원본값 방지, 전체 사전 읽기 실패/재시도
- 전체 사전 읽기 중 파일 교체/닫기 및 buffer 해제, 전체 탐색 benchmark CLI
- 첫 페이지 이후에도 중앙 로딩/입력 잠금 유지, 캐시된 페이지 요청 거절, 100% 후 wheel 즉시 탐색
- 초기 준비 오류 시 잠금 유지/재시도 및 로딩 화면의 취소 버튼/자원 정리 (실제 QML)
- 사이드바의 실제 표시 최대 슬라이더 드래그, 원본값 보존, 네 탭 마우스 클릭 후
  페이지/범위/FIT 유지, 두 창 크기에서 컨트롤이 사이드바 내부에 있고 이미지가 전체 높이를 사용

Ruff/compileall/pytest와 GitHub Actions Ubuntu offscreen에서 검증합니다.
Windows native Qt 렌더링 screenshot은 **생성 테스트 스택**이며 실제 XRT 데이터가 아닙니다.
Linux 그래픽 세션에서의 직접 화면 조작과 네이티브 파일 dialog 수동 클릭은 별도 현장 검증입니다.

![내부 스택 탐색](screenshots/stack/middle-page.png)

[첫 페이지](screenshots/stack/first-page.png) · [마지막](screenshots/stack/last-page.png) ·
[표시 범위와 원본 픽셀값](screenshots/stack/contrast-and-raw-pixel.png) ·
[1100×700](screenshots/stack/minimum-1100x700.png)

### 사이드바 뷰어 탭과 넓어진 이미지 영역 (Issue #23)

파일을 열면 오른쪽 뷰어 탭에서 바로 페이지와 표시 범위를 조절합니다. 하단의 156px
스택 조작 영역을 없애고 FIT 여백을 기존 24px에서 8px로 줄였습니다. 이미지의 실제 표시
크기는 창 크기와 원본 종횡비에 따라 결정됩니다. 단일 이미지에서도 표시 범위는 같은
탭에 있고 페이지 조작은 숨깁니다. 작은 창이나 긴 오류 메시지에서는 사이드바를 스크롤합니다.

![기본 뷰어 탭](screenshots/stack/first-page.png)

[이미지 정보 탭](screenshots/stack/image-info.png)으로 전환해도 뷰어의 배율은 유지됩니다.
위 화면은 Windows 실제 Qt 렌더링이며 합성 9페이지 스택으로 확인했습니다. 기존 80개
테스트를 통과했고, Linux 실데이터 검증 범위는 아래와 같습니다.

### 전체 로딩 후 탐색 활성화 (Issue #19)

![전체 사전 로딩 중 입력 잠금](screenshots/stack/initial-loading.png)

생성 TIFF의 읽기를 테스트 도구에서 잠시 멈춰 실제 초기 로딩 화면을 캡처했습니다.
화면의 진행률은 준비된 캐시 수이며 임의로 만든 값이 아닙니다. 준비를 끝내기 전에는
탐색을 허용하지 않습니다. 실패해도 잠금을 유지하고 재시도/취소할 수 있습니다.

### 전체 준비 후 연속 드래그 (Issue #17)

![슬라이더를 누른 상태의 연속 탐색](screenshots/stack/scrubbing.png)

Windows 개발 환경에서 **3000×3000 uint16, 158장, 약 2.84GB 생성 TIFF**로 검증했습니다.
디스크 최초 접근 성능을 측정하는 실험은 아니며 OS 파일 캐시가 존재할 수 있습니다.

| 측정 | 결과 |
|---|---:|
| 첫 페이지부터 158장 전체 준비 | 5.103초 |
| 전체 앞뒤 이동 632회, GUI/Qt 신호 게시 중앙값 | 0.021ms |
| 같은 게시 측정의 최대값 | 2.920ms |
| 드래그 중 추가 TIFF 디코딩 | 0회 |
| 전체 탐색 버퍼 (1000×1000 샘플 + 표시 / 158장) | 474,000,000 bytes (약 452 MiB) |
| raw LRU 버퍼 | 54,000,000 bytes (3페이지) |
| 손을 놓은 마지막 페이지 원본 복원 / 파일 size·mtime 미변경 | PASS |

게시 시간은 **GPU 텍스처 업로드·모니터 프레임 시간 제외**입니다. 실제 화면의 FPS를 의미하지
않습니다. Qt native 생성 영상 캡처 및 실제 QML pressed 드래그 테스트로 누른 상태의 화면/페이지
변경을 별도로 검증했습니다. 실제 XRT 4개 파일의 초기 준비 시간/연속 탐색 FPS는 미측정입니다.

```powershell
.\.venv\Scripts\python.exe tools/benchmark_tiff_scroll.py --all-pages --pages 158 --repeats 2
# 실제 파일은 읽기 전용:
.\.venv\Scripts\python.exe tools/benchmark_tiff_scroll.py --all-pages --path "실제 TIFF 경로"
```

Linux에서는 `.venv/bin/python tools/benchmark_tiff_scroll.py --all-pages --path '실제 TIFF 경로'`를
사용합니다. default synthetic 모드는 임시 폴더에 생성하고 종료 시 정리합니다. 보고서에는 원본
픽셀 샘플이나 가공 영상이 포함되지 않습니다. 큰 생성 스택을 측정할 때는 해당 크기의 임시
디스크 공간이 필요합니다. 512 MiB는 전체 탐색 버퍼 한도이며 Qt/정밀 캐시/worker/임시 배열을
포함하는 프로세스 전체 RAM 상한은 아닙니다.

### 이전 인접 페이지 탐색 성능 (Issue #15)

Windows 개발 환경에서 3000×3000 uint16, 5페이지 생성 TIFF로 측정했습니다.
개선 전 같은 raw 캐시 페이지도 재변환하며 5회 중앙값 **50.32ms**가 걸렸습니다.
개선 후에는 다음과 같습니다. OS 파일 캐시가 존재할 수 있는 생성 파일이며 실제 USB 파일
성능이나 디스크 최초 접근 시간으로 해석하지 않습니다.

| 측정 | 시간 |
|---|---:|
| 페이지 캐시가 없을 때 읽기 + 표시 변환 1회 | 39.984ms |
| uint16 표시 변환만, 5회 중앙값 | 18.496ms |
| 준비된 StackFrame 조회, 5회 중앙값 | 0.030ms |
| 준비된 페이지 전환 및 Qt 신호 게시, 5회 중앙값 | 0.039ms |

게시 시간에는 QML 텍스처 업로드·모니터 프레임 표시 시간이 포함되지 않습니다. 캐시된
페이지는 입력 이벤트에서 게시하지만, 초기 준비 중 캐시 미적중/느린 디스크/압축 디코딩은
대기가 생길 수 있습니다. 실제 XRT 4개 파일의 시간은 이 환경에서 측정하지 못했습니다.

```powershell
.\.venv\Scripts\python.exe tools/benchmark_tiff_scroll.py
# 실제 TIFF를 읽기 전용으로 측정할 경우:
.\.venv\Scripts\python.exe tools/benchmark_tiff_scroll.py --path "D:\3D XRT\your-stack.tif"
```

Linux에서는 `.venv/bin/python tools/benchmark_tiff_scroll.py --path '실제 TIFF 경로'`로
실행합니다. 기본 모드는 임시 폴더에 생성 영상만 만들고 종료 시 정리합니다. 페이지 두 개가
캐시 한도 안에 들어가는 uint16 단일 채널 스택이 필요합니다. 시간 값 자체는 CI 통과 기준으로
사용하지 않으며 동기 게시·픽셀 정확성·캐시 한도·작업 우선순위를 자동 검사합니다.

### 요청한 실제 파일 검증: NOT RUN

현재 에이전트 환경은 Windows입니다. 아래 Linux mount 경로에 접근되지 않으며
Windows D:/E:의 `3D XRT` 폴더에서도 확인되지 않았습니다. WSL에는 docker-desktop만 있습니다.
Windows 경로를 요청했고, 파일을 확보하기 전에는 **실제 파일 검증 PASS를 주장하지 않습니다**.

| 파일 | 사용자 제공 해상도/페이지 수 | 실제 first/middle/last 및 contrast 검증 |
|---|---|---|
| `No22_220_Section_stack_flipped.tif` | 2944×2745 / 156 | NOT RUN |
| `N119_220_Section_stack_flipped.tif` | 3072×3012 / 158 | NOT RUN |
| `No107_SectionTopo-beforeAnnealing.tif` | 2922×2895 / 156 | NOT RUN |
| `No107_SectionTopo-afterAnnealing .tif` | 2922×2895 / 156 | NOT RUN |

실제 폴더가 있는 Linux에서 실행:

```bash
.venv/bin/python tools/validate_tiff_stack.py \
  --folder '/run/media/didgmltmd/6E25-3446/3D XRT'
```

출력은 파일별 JSON 보고서입니다. 사용자 제공 크기/페이지 수, uint16 단일 채널, 첫·중간·마지막
페이지를 별도 tifffile 페이지 읽기와 비교하고 contrast 변화, 원본 유지, cache 한도, 파일 stat
미변경을 검증합니다. TIFF와 screenshot을 쓰지 않습니다. missing은 NOT_RUN, 읽기/검사 실패는
FAIL이며 모두 PASS일 때만 exit code 0입니다. 파일명 중 `afterAnnealing .tif`의 공백도 그대로 사용합니다.
보고서를 저장한다면 실제 데이터의 픽셀 샘플이 포함되므로 사용자 데이터 폴더에 보관하고 Git에 넣지 마세요.
이 CLI는 읽기/표시 경로 검증이며 실제 파일에서의 UI 조작까지 대체하지 않습니다.

## 개발 검사 재현

```bash
.venv/bin/python -m pip install -e '.[dev,viewer]'
.venv/bin/python -m ruff check .
.venv/bin/python -m compileall -q src tests tools
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
# 그래픽 세션에서 생성 데이터의 native UI 캡처:
.venv/bin/python tools/capture_tiff_stack.py
```

## 남은 제약

실제 4개 파일과 Linux 그래픽 세션의 현장 검증이 남아 있어 전체 요청 상태는 **PARTIAL**입니다.
대형 단일 페이지의 tile streaming, 비표준 multi-series/복합 channel hyperstack UI, 촬영 방향·간격
교정, 물리 좌표, 3D 재구성, 실제 모델 분석/overlay/export는 이번 범위 밖입니다.
3D는 슬라이스 순서·촬영 방향·실제 간격이 확인된 뒤 별도 단계로 진행합니다.
