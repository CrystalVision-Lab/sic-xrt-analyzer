# Analysis Pipeline Contract & Original Image Source

Issue #11 · 내부 계약 버전 **1.0** (`analysis.contracts.CONTRACT_VERSION`).
승인된 모델 파일·입출력 사양은 아직 없습니다. 이 문서는 원본 읽기와 실행 기반의 계약이며,
외부 ML 모델의 사양을 확정하거나 변경하지 않습니다.

## 역할과 데이터 흐름

```text
Original TIFF ── OriginalImageSource ── raw original ndarray
                         │                      │
                         │                 ModelAdapter
                         │             preprocessing / inference
                         │             inverse transform / output
                         │                      │
                         │               AnalysisPipeline
                         │           original coordinate conversion
                         │                      │
                         │                AnalysisResult
                         │
Original TIFF ── tiff_preview ── QImage ── Viewer (Pan / Zoom / FIT / ROI)
```

| 구성 요소 | 책임 |
|---|---|
| `imaging/original_source.py` | TIFF 헤더 메타데이터, 저비용 identity, 엄격한 원본 영역 읽기 |
| `imaging/tiff_preview.py` | 첫 페이지 샘플링과 표시용 8비트 정규화, 독립 QImage |
| `analysis/contracts.py` | 불변 요청·결과·ROI·geometry·error 계약 |
| `analysis/model_adapter.py` | 프레임워크와 UI가 분리된 어댑터 Protocol, 입력·출력 계약, cancellation token |
| `analysis/pipeline.py` | Qt worker, 원본 입력 선택, 상태·세대·취소·결과 수명 관리 |
| `ui/bridge.py` | 원본/preview 함께 로드, 상태를 QVariantMap으로 UI에 전달 |

분석 경로는 QImage나 viewer bitmap을 참조하지 않습니다. 원본 읽기는 정규화·반전·resize·채널 변환을
수행하지 않습니다. uint8/uint16/float32, 음수·NaN을 포함한 샘플 값과 dtype을 보존합니다.
MINISWHITE의 반전은 표시 경로에서만 수행합니다.

## OriginalImageSource와 원본 좌표

`OriginalImageSource(path, page_index=0)`는 픽셀을 디코딩하지 않고 헤더와 stat으로 스냅샷을 만듭니다.
경로와 페이지, `metadata` 및 `identity`는 불변입니다. 메타데이터는 width, height, dtype,
bit_depth, channels, file_size, mtime_ns, page_count, format을 포함합니다.
숫자형 2D MINISBLACK/MINISWHITE와 인터리브 RGB/RGBA만 지원합니다.
별도 채널 평면, 팔레트 등은 명확히 거절합니다. 데이터 변환 도구를 대신하지 않습니다.

```python
source = OriginalImageSource(path, page_index=0)
raw_roi = source.read_region(x=4000, y=1800, width=2200, height=1600)
raw_full = source.read_full()  # 명시적 호출이며 메모리 한도 적용
```

모든 영역은 좌상단 (0, 0), x 오른쪽, y 아래쪽인 **원본 TIFF 픽셀 좌표**입니다.
배열은 `[y:y+height, x:x+width]`, 채널은 마지막 축입니다.
ROI는 정수 좌표, width/height > 0, x/y >= 0, x+width <= 원본 너비,
y+height <= 원본 높이여야 합니다. bool·실수·빈 영역·범위 초과는 `INVALID_ROI`로 거절하며
자동 clamp하지 않습니다. 반환 배열은 독립 복사본이므로 원본 파일과 memory map을 수정하지 않습니다.
읽기가 끝나면 파일과 mmap을 닫습니다.

Viewer의 drag clamp는 유지합니다. 화면·정규화 좌표를 원본 정수 ROI로 바꾸는 작업은 UI 책임입니다.
원본 8000×6000은 현재 샘플링 간격 2로 preview 4000×3000이 됩니다.
Inspector는 원본 8000×6000과 표시 미리보기 4000×3000을 각각 표시합니다.
미리보기 크기는 축소 시에만 표시합니다. 100%는 원본 좌표 격자의 표시 배율이며
샘플링으로 사라진 세부 픽셀을 복원하지 않습니다. 향후 원본 region/tile viewer가 별도로 필요합니다.
스택 뷰어 TD에서 Gray 값 조회는 현재 표시 페이지의 제한된 raw 캐시에 연결했습니다.
OriginalImageSource의 `read_pixel()`은 별도 추가하지 않았으며 마우스 이동은 원본 디코딩을 호출하지 않습니다.

## Large TIFF 정책

| 경로 | 정책 |
|---|---|
| 원본, mmap 가능한 페이지 | 읽기 전용 memory map에서 ROI만 복사. 전체 원본을 RAM 배열로 만들지 않음 |
| 원본, 압축·비매핑 페이지 | 페이지의 디코딩 크기가 기본 **64 MiB 이하**일 때만 전체 페이지 decode 후 ROI 복사 (`maxworkers=1`) |
| 원본, 반환 배열 | ROI/full 반환 크기가 기본 **128 MiB**를 초과하면 `READ_LIMIT_EXCEEDED` |
| 원본, 큰 비매핑 페이지 | ROI가 작아도 `UNSUPPORTED_LARGE_DECODE`, 영역 디코더가 필요함 |
| Preview, mmap 가능한 페이지 | 원본 map을 stride로 샘플링한 뒤 preview 배열만 복사·정규화 |
| Preview, 압축·비매핑 페이지 | 디코딩 크기 **64 MiB** 초과 시 열기 오류. 이전 이미지 유지 |

한도는 디코딩/반환 배열 크기를 제한하며 decoder와 NumPy의 모든 임시 메모리까지 총량을 보장하는
하드 RAM quota는 아닙니다. 원본 소스의 두 한도는 신뢰된 호출자가 명시적으로 조정할 수 있습니다.
20k×20k/30k×30k uint16의 mmap ROI는 전체 크기에 관계없이 요청 영역만 복사하며,
full read는 기본 반환 한도로 거절합니다. 타일·압축 TIFF의 완전한 region decoder는 이번 범위 밖입니다.

압축 파일은 직접 mmap할 수 없으며 임시 파일로 전체 디코딩하는 방식도 자동으로 사용하지 않습니다.
이 정책은 [tifffile 공식 문서](https://www.cgohlke.com/docs/tifffile/)의 memory map 제약을 따릅니다.
기존 긴 변 4096px 이하 샘플링·1~99 백분위 정규화 알고리즘과 QML 표시 방식은 유지합니다.

## SourceIdentity와 불변 요청

Identity: canonical_path, file_size, mtime_ns, page_index, width, height.
전체 SHA256을 매 실행마다 계산하지 않습니다. 읽기 전·후, 결과 게시 전, GUI에서 1초 주기로
크기와 수정 시간을 확인합니다. 변경·삭제 시 결과와 작업을 무효화하고 다시 열도록 안내합니다.
동일 크기·동일 mtime으로 내용을 바꾼 경우는 탐지하지 못합니다. 이 identity는 콘텐츠 해시가 아닙니다.

`AnalysisRequest` 필수 계약:

| 필드 | 의미 |
|---|---|
| analysis_id, created_at | 고유 UUID 기본값, timezone 포함 생성 시각 |
| source, source_identity, page_index | OriginalImageSource와 생성 당시 identity/페이지 |
| scope, roi | 명시적 FULL_IMAGE 또는 ROI, ROI일 때 불변 Region 필수 |
| model_id, model_version | 실행할 어댑터 버전 |
| parameters | 문자열 키와 유한 JSON형 값, 중첩 mapping/list까지 복사·불변화 |

FULL_IMAGE에 ROI를 넣거나 ROI scope에 영역을 생략하면 생성에 실패합니다.
ROI가 존재한다는 이유로 분석 범위를 자동 선택하지 않습니다. UI 범위 선택의 초기값은 빈 값이며
모델 미연결 시 선택도 비활성화됩니다. 동일 analysis_id는 같은 controller에서 재실행할 수 없습니다.
ROI·파라미터를 나중에 바꾸어도 실행 중 request는 변하지 않습니다.

## ModelAdapter 입력·출력 계약

Protocol: model_id, model_name, model_version, available, device(미확정 시 None),
input_contract, output_contract, `analyze(image, request, cancellation_token) -> AdapterOutput`.
Production에는 구체 어댑터나 자동 로딩·설정 선택 경로가 없습니다. 향후 승인된 어댑터를
명시적으로 등록하며 실행 중 같은 인스턴스의 사양을 변경하거나 다른 스레드에서 교체하지 않습니다.

`ModelInputContract`는 supported_scopes, expected_channels, accepted_dtypes와
input_size_policy, normalization, color_space, bit_depth_policy를 필수로 선언합니다.
channels/dtypes는 전처리 전 **원본 입력** 기준이고 dtype 이름은 canonical NumPy 이름입니다.
크기·정규화·색 공간·비트 변환 정책은 어댑터가 문서화하고 검사·구현할 계약 설명입니다.
Pipeline은 scope/channel/dtype 호환성을 검사하며 모델별 크기 조건과 resize/normalize/channel
conversion/padding/tiling은 어댑터가 검사하고 실행합니다. 미확정 모델에 640×640, RGB, uint8,
0~1 정규화를 기본값으로 추측하지 않습니다. 승인 모델 추가 시 기계 판독 정책으로 확장할 수 있습니다.

`ModelOutputContract`는 허용 geometry 종류와 INPUT_LOCAL/ORIGINAL 좌표를 명시합니다.
어댑터는 tensor 좌표의 resize/padding/tiling 역변환을 먼저 수행해야 합니다.
INPUT_LOCAL은 **원본 input crop 픽셀**이며 모델 tensor나 preview 픽셀이 아닙니다.
`AdapterOutput`은 detections, summary, preprocessing(실제 수행 변환 기록)을 반환합니다.
Pipeline이 요청/원본 identity/모델 버전/시간을 권위 있게 붙여 최종 `AnalysisResult`를 만듭니다.
어댑터가 임의 traceability와 timing을 게시하는 방식은 사용하지 않습니다.

실제 모델의 클래스·confidence 의미·mask 형식·전처리 사양은 승인된 모델 계약에서 확정합니다.
다음 TD에서는 sic-xrt-ml의 승인 artifact 버전·설치 시 검증할 SHA256·입출력 schema·호환 버전을
별도로 기록해야 합니다. 현재 가짜 artifact hash나 외부 모델 계약은 생성하지 않습니다.
내부 1.x는 호환 필드 확장, 호환되지 않는 의미/좌표/필드 변경은 major 버전 변경 대상입니다.
현재 Python dataclass 계약이며 결과 export/JSON serializer는 아직 구현하지 않았습니다.

## Detection과 결과 좌표

Detection: id, class_id/class_name(없으면 None), confidence(없으면 None, 있으면 0~1),
geometry, 불변 metadata. ID는 결과 안에서 고유해야 합니다.

| Geometry | 데이터 |
|---|---|
| POINT | points에 (x,y) 하나, 픽셀 sample 좌표 |
| BOUNDING_BOX | bbox=(x,y,width,height), 양의 크기, 반열린 경계 |
| POLYGON | points에 최소 3개 꼭짓점, 픽셀 경계 좌표 |
| MASK | bbox 원점·범위 + mask_reference + mask_encoding, 원본 픽셀 격자에 대응하는 외부 mask 자원 |

Mask 리소스 내용과 encoding별 읽기/보관/크기 검증은 승인 어댑터와 다음 결과 UI TD의 책임입니다.
Raw tensor를 UI 계약에 노출하지 않습니다. 리소스 참조는 결과 수명 동안 유지되어야 합니다.
모든 숫자 좌표는 유한해야 하며, crop-local 결과는 입력 crop 안에 있어야 합니다.
Point는 마지막 픽셀까지, bbox/polygon의 경계는 width/height까지 허용합니다.
잘못된 geometry/미선언 종류/좌표계/중복 ID는 오류 처리하고 게시하지 않습니다.

ROI(1000,2000,400,400)의 local point(100,200)는 최종 original point(1100,2200)입니다.
Box/polygon/mask extent에도 같은 offset을 적용합니다. 이미 ORIGINAL인 결과는 offset을 다시
더하지 않습니다. **AnalysisResult에는 ORIGINAL geometry만 허용**합니다.
향후 Viewer overlay가 original → screen 변환을 담당합니다.

## AnalysisResult와 상태

Result는 불변 request 및 그에 대한 analysis_id, source_identity, model_id/version, scope, roi,
parameters 접근 속성, status, started_at, completed_at, duration(단조 시계의 실측 초), detections,
summary, preprocessing, error, contract_version을 제공합니다. 생성 시각은 request에 보존됩니다.
duration은 원본 읽기부터 어댑터와 출력 변환까지이며 thread queue 대기 시간은 포함하지 않습니다.
실패 결과에는 detections가 없습니다. UI에는 가짜 시간·GPU·confidence를 표시하지 않습니다.

| 상태 | 의미 |
|---|---|
| UNAVAILABLE | 승인 어댑터가 없음/available=False |
| READY | 사용 가능한 어댑터가 있음. 이미지 준비 여부는 별도 sourceReady |
| RUNNING | 현재 세대 작업이 제출됨/실행 중 |
| COMPLETED | 현재 원본에 대한 정상 결과 게시 |
| FAILED | 입력·읽기·모델·출력 오류, 또는 원본 변경 |
| CANCELED | 사용자 취소, 또는 어댑터가 협력 취소를 반환 |

READY와 이미지 준비는 별개입니다. Run은 원본 TIFF·사용 가능한 모델·명시적 지원 scope·유효 ROI가
필요합니다. 요청 사전 검사 오류는 바로 FAILED가 되며 실행 가능한 요청은 RUNNING에서 terminal
state로 갑니다. 모델이 없는 실행 시도는 UNAVAILABLE를 유지합니다. 새 이미지/새 요청은
이전 결과를 먼저 지우고 상태를 재설정합니다.

## Worker, 취소, stale 및 종료

Qt QThreadPool worker에서 원본 읽기와 analyze를 실행합니다. GUI는 요청과 결과를 연결하는
controller만 소유합니다. 모델 인스턴스 하나를 동시에 호출하지 않도록 worker 수는 1입니다.
취소에 협력하지 않는 기존 작업이 있으면 새 작업은 queue에서 기다리지만 GUI는 계속 반응합니다.

CancellationToken의 cancel_requested/check()를 어댑터가 단계마다 확인합니다.
사용자 Cancel은 즉시 CANCELED로 바꾸고 token을 설정하며 generation을 증가시킵니다.
늦게 반환된 결과는 무시합니다. 강제 thread/process kill은 없습니다. 사용자가 취소한 작업의
late worker result도 UI 결과로 보관하지 않습니다. 완료된 분석만 hasResult=True입니다.

다음 동작은 job cancel/invalidation과 result clear를 수행합니다:

- 새 TIFF 열기 요청 (실패해 이전 Viewer/OriginalSource가 유지되어도 이전 결과는 지움)
- 원본 source/페이지 변경, 이미지 닫기, 합성 데모 열기
- 파일 변경/삭제 감지
- 새 분석 요청 (유효하지 않은 새 요청도 이전 결과를 지움)

generation과 source_identity가 현재 값과 일치할 때만 완료를 게시합니다.
ROI만 바꾸면 기존 결과를 유지하고 `result_roi_mismatch`로 다른 ROI임을 추적합니다.
전체 분석 결과도 현재 ROI가 생기면 범위 차이를 표시합니다. 새 실행 시 교체합니다.
종료 시 token을 설정하고 worker가 끝날 때까지 기다립니다. 비협력 모델은 종료를 지연할 수 있습니다.
스택 뷰어 TD에서 다중 페이지 선택 UI를 연결했습니다. ImageJ single-IFD contiguous 파일도
논리 페이지별로 읽으며 source와 요청의 page_index는 해당 원본 2D 페이지를 식별합니다.
자세한 정책과 최신 검증은 [스택 뷰어 문서](tiff-stack-viewer.md)에 기록합니다.

## 오류와 UI 연결

AnalysisError: code, message, detail, recoverable. MODEL_NOT_AVAILABLE, MODEL_LOAD_FAILED,
INVALID_INPUT, UNSUPPORTED_SCOPE, SOURCE_READ_FAILED, INFERENCE_FAILED, CANCELED 등을 사용합니다.
원본 소스는 INVALID_ROI, SOURCE_CHANGED, UNSUPPORTED_FORMAT, READ_LIMIT_EXCEEDED,
UNSUPPORTED_LARGE_DECODE로 더 구체적인 원인도 전달합니다.
Python 로그는 analysis_id와 상세 원인/traceback을 기록합니다. Qt bridge는 code별 안전한 안내만
UI map에 제공하고 adapter message/detail/traceback을 그대로 렌더링하지 않습니다.
로그 파일 저장·사용자 진단 내보내기는 다음 범위입니다.

QML의 modelAvailable/analysisRunning/hasResult와 Run/Cancel/결과 메뉴는 실제 pipeline map에서
계산됩니다. Inspector는 model/version/device/inputSource/scope/status/error와 ROI 차이를 받습니다.
Production 기본은 UNAVAILABLE, 모델·버전·장치 `—`, Run/Cancel 비활성화입니다.
입력·출력 list/overlay/export UI는 미연결 상태로 유지합니다.

## 검증 및 다음 TD

기존 **9개** 테스트를 유지하고 **33개**를 추가했습니다. 합계 **42개**입니다.
uint8/uint16/float32, 압축·비압축, dtype/값/원본 metadata, ROI 경계·잘못된 입력,
RGB/페이지/MINISWHITE, 8000×6000 원본과 4000×3000 preview 분리, full-read/decode 한도,
모든 geometry 변환, state/오류 로그/snapshot/ROI 차이/새 source·페이지·요청/file mutation/
협력·비협력 취소, QML metadata/Run·Cancel 상태/worker 중 UI 반응을 검증합니다.
가짜 어댑터와 결과 생성은 `tests/` 안에만 있습니다.

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pytest -q
```

승인 모델, 실제 inference, Defect Overlay, 결함 목록, Export는 아직 미연결입니다.
다음 TD는 **승인 Model Adapter 구현 및 실제 Analysis Execution 연결**입니다.
