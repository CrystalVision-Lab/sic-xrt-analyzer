# XRT-RESULT-TD-12 Result

## Overall Status

**PARTIAL**. 제한된 원본 ROI를 사용하는 실제 내부 3D 작업공간과 페이지별 수동 관측 기록을 구현했다. 실제 촬영의 Z축 방향·간격과 동일 물리 결함의 연속성은 확인되지 않았다. 합성 형상 검증을 실제 결함 정확도로 일반화하지 않는다.

## Engineering Status

**INDEXED_STACK_3D_VERIFIED**. 실제 TIFF 4개, 합성 숫자·좌표·저장·취소·Source 전환과 native D3D11 장면을 확인했다. 최종 CI는 아래 및 Draft PR에 기록한다. Windows 물리 마우스·Native Dialog 수동 Acceptance는 기존 **PENDING**을 유지한다. GUI 입력은 Qt QTest 자동 입력이며 사용자의 입력 중지 확인은 받지 않았다.

## Physical 3D Status

**PHYSICAL_3D_NOT_READY**. 실제 TIFF 4개 모두 X/Y 원본 픽셀과 원본 페이지 인덱스 K를 사용한다. `frames`, `slices`, 파일명과 페이지 수는 물리 Z축의 근거가 아니다.

## Tracking Status

**DEFECT_TRACKING_PRELIMINARY**. 연구원은 페이지별 Point/Rectangle을 수동으로 기록한다. REVIEWED는 해당 수동 기록의 상태이며 동일 물리 결함 확인이나 학습 정답 승인 상태가 아니다. 자동 추적·BPD/TED/TSD 분류·결함 길이/부피 측정은 실행하지 않는다.

## Git

- Start Branch: `feat/116-wafer-map-workspace`.
- Start HEAD: `84f9addc74549177f4b12b03b2406014b806b8a8` — TD-11 Draft PR #117.
- Work Branch: `feat/118-tiff-3d-viewer`.
- Issue: [#118](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/118).
- Draft PR: [#119](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/119), base는 TD-11 branch 유지.
- 기능 단위 커밋: `d5f0fa0` (Volume·계약), `4aaf125` (3D/직교/Track 작업공간), `d890eac` (진행률·프로젝트 변경 안정성), `975a25b` (navigation·계약 회귀), `5f97325` (작은 화면 상태 가시성). 최종 기능 Source HEAD: `5f97325eca4f1d9343ca28bdfe06001650489b53`. 추가 계측 도구·문서·합성 화면을 포함한 최종 HEAD/Push/CI는 PR에 기록한다.
- 기존 stacked PR 병합·rebase·retarget 없음. 사용자 수정 `AGENTS.md`, 원본·모델·개인 프로젝트·비밀값은 커밋하지 않았다.

## 실행과 사용

PowerShell:

```powershell
Set-Location D:\capstone\sic-xrt-analyzer
.\.venv\Scripts\python.exe -m sic_xrt_analyzer
```

1. TIFF 원본을 열거나 기존 프로젝트에 등록하고 **3D 뷰어**로 이동한다. JPG는 이 Volume 추출 대상이 아니다.
2. TIFF Source를 선택하고 원본 좌표 ROI `(x,y,width,height)`, 첫/마지막 페이지, 페이지 간격, XY 샘플 간격을 지정한다. UI 페이지는 1부터, 저장 계약은 0부터 시작한다.
3. **ROI / 범위 적용**의 `[K,Y,X]` 크기와 64 MiB 제한을 확인하고 **3D 생성**을 누른다. SHA·페이지 추출·표시 준비는 백그라운드에서 수행하며 취소할 수 있다.
4. **3D / XY / X–Page / Y–Page**로 탐색한다. 3D 왼쪽 드래그는 Orbit, 오른쪽 드래그는 Pan, 휠은 Zoom, **Fit / View Reset**은 초기 카메라다. 단면을 선택하면 같은 원본 위치가 강조된다.
5. 페이지 슬라이더·휠·방향키로 선택 페이지를 바꾸고 표시 Window를 조절한다. 마우스 위치의 원본 X/Y/Page/uint16 값을 확인한다.
6. **원본 2D 위치 열기**는 Source SHA를 확인한 뒤 정확한 원본 페이지와 X/Y 위치로 돌아간다.
7. 등록·저장된 프로젝트에서 연구원 ID와 이름으로 수동 Track을 만든다. 점 기록 또는 ROI 기록, 상태 변경, 제거, 중단/재개, Undo, 초안 취소를 제공한다. ROI 기록은 지정 사각 ROI이고 중심점을 영역으로 확대 해석하지 않는다.
8. **3D 세션 저장**으로 로컬 불변 Asset과 프로젝트 revision을 함께 저장한다. 재열기는 metadata만 복원하며 **3D 생성**으로 원본 ROI를 다시 읽는다. 원본이 없으면 기록 열람만 가능하다. 저장하지 않은 수동 기록은 다른 Source/프로젝트로 이동하기 전에 저장하거나 초안을 취소한다.

기존 개발 의존성 `.[dev,viewer,research,imagej,sync]`를 사용하며 별도 VTK/PyVista 패키지를 추가하지 않았다.

## Existing TIFF Architecture

기존 `OriginalImageSource`는 metadata·stat identity, 제한된 원본 region 읽기, 원본 좌표 ROI 검증을 제공한다. 2D Stack Viewer의 미리보기/정밀 표시·페이지 준비·ImageJ 작업 복사본은 그대로 유지한다. 3D는 기존 원본 Reader를 재사용하며 ImageJ 작업 복사본을 원본으로 간주하지 않는다. 기존 반환 128 MiB / decode 64 MiB 제한은 변경하지 않았다.

## Source Identity

Source ID, 경로, 크기·mtime·metadata·SHA를 확인한다. 추출·저장·원본 복귀 전에 SHA를 확인하며 파일 변경, relink, 프로젝트/Source 교체는 오래된 작업을 무효화한다. 관련 없는 같은 프로젝트 metadata 갱신은 정상 ROI 읽기를 취소하지 않는다. 완료 콜백은 최신 프로젝트의 Source 부가 metadata를 보존하며 hash만 갱신한다. 실제 JPEG/TIFF, 모델, baseline 프로젝트 해시는 별도 보존 검사 대상이다.

## Volume Extraction

`stack3d/volume.py`의 계획과 추출을 분리했다. ROI와 original page indices를 고정하고 `[K,Y,X]` native `uint16` 배열 한 개로 추출한다. endian 변환은 숫자 값을 보존한다. `OriginalImageSource.read_region`의 최대 128행 strip을 순서대로 읽고 최대 16 MiB scratch를 사용한다. 압축 strip의 디코딩은 Reader의 기존 decode 제한을 따른다. 여러 페이지를 한 번에 원본 크기로 펼치지 않는다.

## Axis Contract

`x = roi.x + ix * xy_step`, `y = roi.y + iy * xy_step`, `k = page_indices[ik]`. 다운샘플링은 명시적인 원본 픽셀 선택이며 원본 수정·보간·새 픽셀 생성이 아니다. XY/X–Page/Y–Page, Track, 원본 복귀가 같은 매핑을 사용한다. 장면의 Y는 아래 방향 원본 좌표를 Qt 3D 좌표에 맞춰 부호 변환한다. 표시용 정규화와 실제 좌표 계약은 분리한다.

## Memory Budget

- uint16 Volume: 기본/최대 **64 MiB**, 단일 resident Volume, 바꿀 때 이전 데이터 해제.
- Reader strip scratch: **16 MiB** 이내. 기존 Reader decode/return 제한 별도 유지.
- 페이지 수: 최대 4096, 명시 XY 샘플 간격 1–64. 초과는 추출 전에 거부.
- 표시 RGBA: 최대 edge 512, 총 **16 MiB** 이내, 최대 12개 표시 페이지 + 직교 단면 3개.
- Background Worker: 1개 실행 + 최신 대기 요청 1개. 오래된 요청 취소/epoch 무효화.
- 추출 timeout 120초, strip/page 사이 cooperative cancellation. SHA 읽기도 chunk 사이 취소 가능하며 추출 timeout과 별도다. 네이티브 decode 한 호출을 강제 종료하지는 않는다.
- Track 최대 100개/2048 events, Asset 8 MiB/세션 history 128 revisions·누적 32 MiB, Undo 32개. 표시 marker 1000개/line vertex 10000개 제한은 저장 기록의 삭제가 아니다.

이 수치는 프로세스 전체 RAM 상한이 아니다. 기존 2D Stack cache(원본 96 MiB/3 pages, 별도 표시·browse cache), Qt/RHI·framebuffer·driver 복사본·Python·JVM은 RSS에 별도로 포함된다.

## Indexed Stack Mode

원본 X/Y px와 original K page를 사용한다. 선택한 전체 ROI Volume과 3D 표시 planes를 구분한다. 장면은 최대 12개 대표 페이지와 현재 페이지를 보여주며 모든 선택 페이지의 원본 ROI는 직교 단면/페이지 탐색에 사용한다. 장면 페이지 간격의 단위 없는 정규화는 실제 깊이 측정이 아니다.

## Physical Calibration Gate

기존 Source calibration의 VERIFIED 상태, SPATIAL_Z/DEPTH, um/mm, 독립 근거 문자열, 명시 방향, 양의 XY/Z spacing, 전체 원본 페이지 순서 permutation이 모두 있어야 Physical 표시를 허용한다. UI는 자동 calibration을 만들지 않는다. 합성 forward/reverse/order 매핑만 검증했다. 현재 구현은 균일 Z 간격 계약을 소비하며 비균일 페이지별 깊이 입력 UI·실제 물리 측정은 후속이다.

## Rendering Technology

기존 Qt Quick/QML/PySide6 6.11.2의 **Qt Quick 3D View3D + PerspectiveCamera + Texture.sourceItem**을 사용한다. RHI 없는 software 모드에는 원본 기반 직교 단면과 명시적인 3D 미지원 상태를 제공한다.

[Qt Texture 문서](https://doc.qt.io/qt-6.11/qml-qtquick3d-texture.html)에 따라 `image://`는 Texture.source에 직접 지정할 수 없으므로 Image provider를 sourceItem으로 연결했다. 초기 PoC에서 실제 픽셀 texture가 호출되지 않은 실패를 수정했으며 `artifacts/td118-poc/report-source-item.json`에서 실제 N119 texture 3개를 확인했다. [Qt picking 예제](https://doc.qt.io/qt-6/qtquick3d-picking-example.html)의 localPosition을 원본 sample 좌표에 매핑한다.

## 3D Perspective

실제 픽셀 RGBA가 적용된 페이지 planes, 선택 페이지 강조, X/Y/Page 축 표시, Orbit/Pan/Zoom/reset을 제공한다. 선택 plane은 불투명, 대표 페이지는 투명이다. 투명 plane 겹침은 시각적 탐색이며 density volume/ray casting/isosurface가 아니다. 원본에 없는 선명도를 생성하지 않는다. 카메라 입력은 QML 장면을 갱신하며 매 입력마다 CPU Volume 변환을 다시 실행하지 않는다.

## Orthogonal Slices

XY = `V[k,:,:]`, X–Page = `V[:,y,:]`, Y–Page = `V[:,:,x]`. uint16 원본에서 표시 Window만 RGBA로 변환한다. nearest 표시/선택 grid와 crosshair를 제공한다. 고해상도 ROI의 표시 edge 축소는 표시용이며 픽셀 hover는 resident 원본 ROI 값을 읽는다.

## Page Navigation

선택 페이지/좌표는 세 뷰와 3D에서 공유된다. 원본 복귀는 Source/Page/X/Y를 전달한다. 파일 변경을 자동 clear하는 기존 2D 연결에는 한 번만 허용되는 navigation guard를 사용한다. 느린 원본 페이지를 기다릴 때 동일 pending 요청을 반복 제출하지 않는다. 기존 native 파일창 구현은 수정하지 않았다.

## Manual Structure Tracking

신규 Track 이름/creator/reviewer, 페이지별 Point/Rectangle, PROPOSED/REVIEWED/UNCERTAIN, UPSERT/REMOVE/PAUSE/RESUME 이벤트를 기록한다. 같은 페이지 수정은 새 이벤트다. 빠진 페이지는 관측 없음으로 남는다. Undo/초안 취소는 미저장 기록에만 적용하고 저장된 revision은 덮어쓰지 않는다. 자동 ROI/ML 추적이나 동일 결함 확정은 하지 않는다.

## Track Geometry

Point marker, Rectangle 네 변과 중심 marker, 관측 사이 수동 경로를 표시한다. 페이지 간 공백은 점선이다. 원본 ROI 밖 또는 표시에서 샘플링되지 않은 기록은 삭제하지 않고 표시 생략 수를 알려준다. 오버레이는 원본 X/Y/K 기록에서 파생한 bounded line geometry이며 실제 결함 길이/부피를 계산하지 않는다.

## Source / Page Coordinate Mapping

모든 Track은 source_id/source_sha256 + original page index + original X/Y를 저장한다. Scene 선택은 현재 Volume revision만 사용하며 오래된 pick을 거부한다. 원본 2D 복귀는 stat/SHA/페이지 준비 확인 후 정확한 X/Y focus를 전달한다. UI의 1-based page와 저장의 0-based page를 혼동하지 않는다.

## Project Persistence

`xrt_stack_3d_session/v1`, `xrt_stack_track/v1`을 별도 JSON Asset으로 저장하고 Source acquisition metadata의 `stack_3d_session_reference`로 연결한다. Project schema 1.0/1.1과 기존 lock/expected revision/atomic save/SaveAs를 재사용한다. metadata 재열기에는 전체 Volume을 읽지 않는다. Source 누락 시 metadata와 이력만 읽는다. 기존 과학 테이블·Wafer 배치·정합·calibration을 유지한다. 서버 projection/sync에는 이 로컬 Asset 계약을 추가하지 않았고 전송하지 않는다.

## Asset Integrity

`assets/stack-3d/<canonical-sha256>.json`, fsync와 배타 publish, 엄격한 UTF-8 JSON/중복 키/finite number/Source·SHA·범위/path 검사, 부모 revision chain 검증을 사용한다. 과거 Track 이벤트 prefix/identity는 변경할 수 없다. SaveAs는 chain/Track 의존 Asset을 해시 검사하며 복사한다. missing/corrupt/hash mismatch/history rewrite는 명시 오류이며 raw source 삭제·덮어쓰기는 없다.

## Real TIFF Validation

실제 4개 원본에서 중앙 256×256 ROI의 모든 원본 페이지를 추출하고 첫/중간/마지막 페이지를 독립 tifffile crop과 비교한다. 실제 pixel PNG와 프로젝트 복사본은 private artifacts에만 보관하며 Git에는 합성 화면만 포함한다. `artifacts/td118-real-3d-v7/report.json`: **PASS**. 선택 페이지 총 **626장**(158+156+156+156), 실제 3D texture/Track 저장/Source·K·X·Y 원본 복귀 4/4, 독립 원본 crop 12/12, 모든 원본 endian `>`/uint16 숫자 값 보존, metadata 재열기 성공. 8개 과학 테이블·원본/모델/baseline SHA 모두 보존, 신규 추론/자동 sync 0, QML 경고 0.

이전 실패 artifacts도 보존했다. v1은 3 GB byte 진행률의 Qt int overflow였다. v2–v4는 관련 없는 프로젝트 metadata 이벤트가 SHA 작업을 취소했다. v5 원본 복귀 timeout 후, v6에서 SHA 단계가 아직 읽는 중인 상태를 확인했다. SHA 진행률/검증 timeout과 동일 pending 페이지의 중복 요청 방지를 추가한 v7에서 4개 모두 성공했다. 실패를 물리적 Z나 데이터 정확도 검증 성공으로 대체하지 않았다.

## Synthetic Ground Truth

14개 합성 형상의 독립 TIFF 숫자 oracle, 원본 좌표/축 방향, 고값 uint16/endian, explicit sampling, 예산/잘못된 입력/cancel/timeout/파일 변경/decode 제한, known calibration forward/reverse/order, Track Rectangle/Point/gap, Source·Project 전환, 저장/SaveAs/missing/hash/history/기존 과학 계약을 검사한다. 이는 알려진 합성 구조에 대한 공학 검증이며 실제 동일 결함 검증이 아니다.

## Performance

추출 engine 시간, SHA+worker-ready 전체, display RGBA 준비, warm page 변경과 Qt frameSwapped를 분리한다. `frameSwapped`는 Qt 제출/스왑 신호이며 실제 화면 photon latency·GPU busy time·FPS 측정이 아니다. 사용자 입력 중지 확인 없이 QTest 자동 입력을 실행했으므로 수동 반응성 Acceptance는 별도다. 단회 실제 4개와 DPI별 반복 8회 합성 Orbit·4회 Zoom을 구분한다. Windows 11 / Intel Core i7-13700 / 32 GB RAM / Python 3.13.7 / PySide6·Qt 6.11.2 / Direct3D11 / basic render loop. 시스템에서 Intel UHD Graphics 770과 NVIDIA GeForce RTX 3050을 조회했으며 앱의 실제 backend는 Direct3D11이다. 어느 adapter가 활성화됐는지와 GPU 타이밍/VRAM은 직접 측정하지 않았다. 실제 원본은 OneDrive의 기존 로컬 파일이고 검증 사본·temp·logs는 D 프로젝트에 있다. SHA 전후와 소규모 회귀 실행이 일부 겹친 단회 실행이며 cold-cache 고정 벤치마크가 아니다. Worker-ready에는 Source SHA·추출·RGBA·Qt 콜백 대기가 포함된다. save에도 원본 SHA를 다시 읽는 시간이 포함된다. warm page 수치는 이미 resident Volume에서 4회 선택한 worker 준비 시간이며 실제 화면 표시 완료 시간은 아니다.

| 실제 파일 | 선택 pages | raw MiB | 추출 CPU s | worker-ready s | warm page 중앙값 ms (4회) | save+SHA s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| N119_220_Section_stack_flipped.tif | 158 | 19.75 | 48.90 | 111.29 | 298.3 | 65.05 |
| No107_SectionTopo-afterAnnealing .tif | 156 | 19.50 | 69.74 | 117.32 | 55.2 | 57.12 |
| No107_SectionTopo-beforeAnnealing.tif | 156 | 19.50 | 82.13 | 136.33 | 230.5 | 62.24 |
| No22_220_Section_stack_flipped.tif | 156 | 19.50 | 37.28 | 80.34 | 137.7 | 53.79 |

### 합성 native GUI 분리 계측

합성 768²×96 TIFF, 선택 ROI 256²×96 uint16 **12 MiB**, 보유 RGBA **3.4375 MiB**, Main.qml/Direct3D11/basic. DPI는 Windows 전역 설정을 바꾸지 않고 `QT_SCALE_FACTOR=1/1.25/1.5`로 지정했다. 3개 크기는 Qt logical window 크기이며 PNG 픽셀 크기는 해당 DPR을 곱한 값이다. 화면 앞 상태는 snapshot만 확인했고 수동 입력 정지는 확인되지 않았다. 아래 Qt 신호 시간은 실제 모니터 표시 완료나 GPU busy time을 뜻하지 않는다.

| Qt DPI | 첫 장면 submit 후 Qt frameSwapped ms (1회) | Orbit submit / Qt frame 중앙값 ms (8회) | Zoom submit / Qt frame 중앙값 ms (4회) | 직교 tab Qt frame 중앙값 ms (4회) | Track worker / RGBA 준비 ms (1회) | sampled RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 100% | 78.4 | 1.70 / 10.62 | 1.40 / 11.30 | 15.63 | 24.22 / 16.98 | 480.96 |
| 125% | 106.2 | 1.93 / 8.78 | 1.19 / 10.35 | 15.44 | 22.93 / 17.05 | 520.33 |
| 150% | 106.3 | 1.77 / 16.52 | 1.15 / 16.35 | 15.40 | 24.65 / 16.90 | 601.50 |

기록: `artifacts/td118-capture-final-{100,125,150}/report.json`. 첫 장면 측정은 controller scene publication 뒤 첫 Qt frameSwapped이며 화면 촬영과 같은 실행이다. Overlay 수치는 수동 기록 3개를 추가한 마지막 준비 호출이고 대량 Track 최대치의 성능 보장은 아니다. 실제 데이터의 FPS로 일반화하지 않는다.

일반적인 ROI 읽기에서도 strip decode와 원본 SHA로 수십 초가 걸릴 수 있다. UI는 그동안 progress/cancel을 제공하며 전체 파일을 미리 읽어 메모리에 넣지 않는다. 이 TD는 로딩 시간이 짧다고 주장하지 않는다.

## Peak RSS

프로세스 psutil RSS sample maximum을 기록한다. **실제 4 TIFF 통합 실행: 1635.99 MiB sampled peak RSS**. 64 MiB는 새 Volume만의 상한이며 이 실행에는 기존 2D 원본 복귀 Reader/cache·Qt 장면도 포함됐다. Python heap만의 peak나 RHI driver 전체 VRAM 측정값으로 해석하지 않는다. CPU extraction scratch/Volume/표시 texture budgets와 RSS 측정값을 구분한다.

## Renderer Resource Usage

원본 array의 nbytes와 보유 RGBA 이미지 bytes를 계산한다. Qt sourceItem/RHI upload/framebuffer/driver VRAM은 별도 복사본이므로 이 bytes를 실제 GPU 메모리로 주장하지 않는다. Source 전환/취소/종료에서 Volume/provider refs를 해제하고 GPU Loader를 비활성화한다. OS driver의 자원 반환 지연은 직접 계측하지 않았다.

## JPG Regression

`artifacts/td118-jpg-tiff-regression/report.json`: **PASS**. 기존 Full 2946 (BPD 245/TED 1398/TSD 1303), ROI 791 (3/779/9), 각 저장 Run 2개, 원본 scores/좌표/Export와 8개 과학 테이블·원본/모델/baseline SHA 보존. 신규 추론 0. TIFF 4개의 기존 원본 페이지 oracle도 PASS. 신규 구조 기록을 JPG 결과에 합치지 않았다.

## ImageJ/Fiji Regression

`artifacts/td118-tiff-workbench-regression/report.json`: **PASS**. TIFF 4개 × 첫/중간/마지막 12개 uint16/endian 비교, ImageJ selection/Area 1024/Multiply 1 작업 복사본/Viewer/ROI Geometry·SHA 보존, 신규 ML/BPD/sync 0, QML 경고 0. Windows native plugin **12/12 PASS**: DPI 100% `4 passed / 30.30초`, 125% `4 passed / 23.40초`, 150% `4 passed / 23.51초` (`artifacts/td118-native-plugin-{100,125,150}.log`). 기존 AWT/Swing/ImageJ 설정 창과 픽셀 반환을 실제 native platform에서 Qt 자동으로 검사했다. Linux X11 검사도 CI에 포함한다. OS 파일창 물리 마우스 검증은 이번 검사 범위가 아니다. 로컬 첫 wheel 시도는 `python -m build` 모듈 실행 패키지 미설치로 실패했고, CI와 동일한 `pip wheel --no-deps --no-build-isolation`은 PASS했다. wheel ZIP에 3D QML/Volume/Asset/geometry 포함도 검사했다. 로그 `td118-wheel.log`/`td118-pip-wheel.log`를 보존했다.

## Windows Tests

초기 전체 회귀: **728 passed / 5 기존 skipped**, 1008.51초, `artifacts/td118-full-windows.log`. 이는 초기 UI Source에서 실행했고 이후 진행률·metadata·원본 복귀 수정은 추가 회귀로 검사한다. 최종 Source의 focused **39 passed / 20.51초** (`td118-final-focused-v2.log`): 30 engine/계약 + 9 UI·navigation 검사. 별도 프로젝트/Wafer/정합 포함 실행은 **142 passed + 새 검사 코드 오류 1 failed / 182.16초**였고, 잘못된 존재하지 않는 Asset helper 호출을 수정한 뒤 해당 engine/계약/UI 전체를 위 39개로 재검사해 모두 성공했다. 기존 프로젝트/Wafer/정합 104개는 원래 실행에서 모두 PASS했다. 이 수치를 동일 HEAD의 새 전체 Windows 회귀로 바꿔 쓰지 않는다. 최종 기능 Source 전체 회귀는 별도 `artifacts/td118-final-full-windows.log`에 기록한다. 문서 커밋 뒤 완료되는 최종 전체 검사 수·최종 HEAD·CI 결과는 Draft PR 최신 검증 표가 최종 기록이다.

## GitHub CI

`d890eac`의 [CI 38355536207](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/38355536207): **success**, Linux 전체 **732 passed / 4 skipped**, 717.58초, 실제 X11 plugin windows **4 passed**, 독립 server-postgres·wheel·ruff·compile·PR policy 성공. 이후 최종 Source/문서 CI는 Draft PR 최신 검증 표에 기록한다. 서버 관련 코드는 이번 TD에서 수정하지 않았으며 server-postgres는 독립 서버 의존성 격리 검사로 실행한다.

## GUI Screenshots

실제 Qt Quick 3D Direct3D11과 QTest 입력을 사용한다. 18개 상태 × 1100×700/1440×900/1920×1080 × DPI 100/125/150을 합성 원본으로 촬영한다. 실제 XRT 캡처·원본 ROI를 Git에 넣지 않는다. 최종 **162 PNG = 18×3×3**, 모두 PASS/QML 경고 0/합성 원본 SHA 보존. `docs/screenshots/stack-3d/dpr{100,125,150}/{1100x700,1440x900,1920x1080}/`에 01–18 상태를 기록했다. 1100×700의 상단 오류·진행률, DPI 150의 Track 입력/Rectangle overlay와 작은 뷰를 직접 시각 검토했다. 왼쪽 세부 조작부는 세로 스크롤로 제공한다.

예: [3D Perspective](../screenshots/stack-3d/dpr100/1440x900/06-perspective.png), [직교 X–Page](../screenshots/stack-3d/dpr125/1440x900/08-x-page.png), [수동 Track](../screenshots/stack-3d/dpr150/1100x700/11-manual-track.png), [Rectangle·gap overlay](../screenshots/stack-3d/dpr150/1920x1080/12-track-3d-overlay.png), [메모리 제한](../screenshots/stack-3d/dpr100/1100x700/17-memory-limit.png).

## Scientific Limitations

- 실제 물리 Z축·방향·순서·간격·측정 근거 없음: PHYSICAL_3D_NOT_READY 유지.
- 실제 정답 Track 없음: 동일 물리 결함 연속성/추적 정확도 미검증, DEFECT_TRACKING_PRELIMINARY 유지.
- 대표 plane 렌더는 물리적 density reconstruction이 아니다. ray casting/isosurface는 이번 구현에 포함하지 않았다.
- Volume은 제한 ROI/명시 sample이며 원본 TIFF 전체의 GPU resident reconstruction이 아니다.
- 실제 VRAM/GPU 타이밍/물리 입력-to-display latency는 직접 계측하지 않았다.
- 비균일 실제 Z 간격 입력 UI, 자동 추적·길이/부피·모델 학습·서버 Track 전송은 별도 계약이 필요하다.

## Next TD

촬영 담당자가 독립적인 방향·순서·XY/Z 간격·unit·근거를 제공한 뒤 실제 physical calibration을 검증한다. 동일 구조의 전문가 정답 관측이 확보되면 Track 정확도를 별도 검증한다. 제한 ROI plane 탐색을 넘어선 volume ray casting/isosurface·GPU resource 계측은 요구와 baseline을 확인한 후 별도 TD로 분리한다.
