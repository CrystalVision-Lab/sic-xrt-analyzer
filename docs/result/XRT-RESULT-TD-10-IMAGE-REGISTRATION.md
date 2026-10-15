# XRT-RESULT-TD-10 — Before/After JPG 정합 및 비교

## Overall Status

**PARTIAL**. Engineering **ENGINEERING_VERIFIED**; 실제 연구 정합 품질 **REAL_REGISTRATION_PRELIMINARY**. 구현 및 정합 집중 검사 35개 PASS. 엔지니어링 동작과 실제 과학적 정합 정확도를 분리한다. 실제 원본 쌍은 자동 정합 실패이며, 실패를 정상 검출·보존했다. 원본 Crop/해시/저장/재열기/기존 과학 데이터 보존은 PASS.

- Engineering Status: **ENGINEERING_VERIFIED**. 최종 Windows 전체 652 PASS/5 SKIP, Linux 전체 653 PASS/4 SKIP, Native Plugin 및 PostgreSQL CI PASS. 기존 Windows native plugin DPR150%의 첫 실행 실패는 아래에 별도 기록하며 안정성 원인이 모두 해결됐다고 주장하지 않는다.
- Real Registration Quality: **REAL_REGISTRATION_PRELIMINARY**. 같은 Wafer/같은 관측 영역 여부와 전문가 정답 대응점은 미확인. REAL_REGISTRATION_VALIDATED가 아니다.
- Native Dialog 물리적 마우스 Acceptance: 기존 **PENDING** 유지.

## Git / 작업 기준

- Start Branch: `feat/112-tiff-imagej-workbench`
- Start HEAD: `926a747c5f4ab7eb05b95efce93a6a66e7fc427e` (TD-09 자동 검사 PASS)
- Work Branch: `feat/114-image-registration-workspace`
- Issue: [#114](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/114)
- Draft PR: [#115](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/pull/115), base는 TD-09 branch.
- 기존 stacked PR merge/rebase/retarget 없음. 사용자 `AGENTS.md` 변경은 제외.
- 검증한 앱 Source HEAD: `31491c552dd72a804918cac2096c6849e1a4d38e`. 이후 검증 도구·보고서·합성 캡처 커밋 포함 Final HEAD와 최종 CI는 Draft PR에 기록한다.

## 실행 및 사용 흐름

```powershell
Set-Location D:\capstone\sic-xrt-analyzer
.\.venv\Scripts\python.exe -m pip install -e ".[ui,research,imagej,sync]"
.\.venv\Scripts\python.exe -m sic_xrt_analyzer
```

1. 프로젝트를 열거나 생성한다. 필요한 JPG를 기존 이미지 뷰어로 열고 프로젝트에 원본 등록 후 저장한다. 기존 프로젝트의 JPG 두 장을 선택할 수 있다.
2. 왼쪽 **이미지 정합** → Before/After를 직접 지정 → **비교 영상 준비**. 파일 이름으로 역할을 자동 추론하지 않는다. 이 선택으로 정합 실행 시 BEFORE_ANNEALING/AFTER_ANNEALING 역할을 명시적으로 기록한다.
3. SHA 확인과 디스크 원본 캐시 준비 동안 로딩을 표시한다. 동일 파일/동일 SHA/TIFF/원본 불일치는 차단한다. 기존 뷰어에 TIFF가 열려 있어도 정합 Source 선택에는 JPG만 제공한다.
4. SIFT/ORB·Auto 변환으로 시작한다. Phase/ECC는 제한된 명암 방법이다. 실패 시 원인을 표시하고 이력을 보존한다. 나란히 보기에는 각 원본 좌표이며 정합 전 동일 물리 위치라고 가정하지 않는다.
5. 정합이 생기면 겹침/불투명도/분할/차이 모드를 사용한다. Fit/100%/400%, 마우스 휠 Zoom 및 드래그 Pan을 두 화면에 연동한다. After 기준으로 Before 좌표를 변환한다.
6. 수동 Landmark 선택 → 새 대응점 → Before 클릭 다음 After 클릭. 번호·각 원본 XY가 표시되고 좌표를 직접 수정하거나 점을 삭제할 수 있다. Translation 1쌍, Rigid/Similarity 2쌍, Affine 3쌍이 최소이며 중복·공선·원본 밖 좌표를 거부한다. 더 많은 점을 분산 선택하여 검토한다.
7. 번호별 잔차 선과 품질을 검토한다. 로컬 검수자 ID 입력 → **검토 승인·저장**. 실패/원본 누락 상태에서 승인하지 않는다. 자동 추정은 VERIFIED가 아니며 로컬 승인은 인증된 전문가의 공식 과학적 검증을 의미하지 않는다.
8. 프로젝트 재열기 시 마지막 정합의 쌍·행렬·상태·Landmark가 복원된다. 상단 정합 ID 목록으로 과거 시도를 선택할 수 있다. 누락 원본은 메타데이터·오류만 표시하고 실제 영상은 다시 SHA로 연결하기 전 차단한다.

## 기존 계약 및 보존

`AnalysisProject`, `ImageSourceRecord`, `ImageRole`, `ImageRelationship`, `VerificationStatus`, `ProjectStore`를 재사용한다. SpatialCalibration/WaferPlacement는 변경하지 않는다. 프로젝트 스키마 1.0/1.1과 기존 Export 계약은 그대로다.

새 자산 `xrt_registration/v1`에는 project/source/target ID, 원본 SHA·크기, `before_to_after`, algorithm/version, model/matrix, Landmark/inlier, quality/timings/refinement, 생성 시각, 승인자·부모 정합 ID를 기록한다.

`ImageRelationship.match_quality=None`: 오차·Inlier·상관은 정확도 퍼센트가 아니다. 정량 품질은 자산에 별도 기록한다. 추정/실패=UNVERIFIED, 명시적 승인=VERIFIED. 승인 시 기존 관계/자산을 수정하지 않고 새 ID로 추가한다. 승인 자산은 부모 추정 자산의 행렬·품질·원본·알고리즘 근거를 바꿀 수 없다.

기존 연구 배치 `registration/research.py`의 After→Before/Homography/결함 추적 코드는 바꾸거나 UI에 자동 연결하지 않았다. 이번 엔진은 Before→After affine 계열이다. 기존 Candidate/Raw Score/Prediction/Review/Geometry/Model/ROI 좌표·분석 입력·Export를 정합된 좌표로 덮어쓰지 않는다. µm/mm나 공간 Z를 추정하지 않는다. 중앙 서버 구조·ML 계약 변경 및 자동 업로드는 없다. 신규 정합 자산은 이번 단계에서 로컬 프로젝트 자산이며 서버 반출 프로토콜 확장으로 간주하지 않는다.

## Architecture / 좌표 및 알고리즘

- `registration/engine.py`: 재사용 가능한 validate/transform_points/inverse_transform/transform_bounds, 특징점·명암·Landmark·품질 평가·제한된 정밀 보정.
- `registration/comparison.py`: 기존 `JpegImageSource`와 `PreparedPixels` 재사용. Read-only disk native cache, preview, viewport warp·LRU·Overlay culling.
- `registration/assets.py`: 엄격한 JSON 검증, SHA 참조, 불변 자산·관계·승인.
- `ui/registration_controller.py`: 기존 LatestReader 기반 한 Worker, 취소 token/epoch/프로젝트 snapshot 검증, 최신 요청만 표시.
- `RegistrationWorkspace.qml`: 실제 Qt 비교 작업공간. 기존 다크 테마·탐색 구조 사용.

원본 픽셀 중심은 정수 XY, 이미지 외곽은 -0.5~width-0.5/height-0.5이다. Preview u/v 중심에서 원본은 `(u+.5)*original_width/preview_width-.5`와 각 Y 비율로 환산한다. X/Y 비율을 별도로 적용한다. EXIF 자동 회전은 적용하지 않는다.

원본 등록 행렬은 유한한 3×3, 마지막 행 [0,0,1], 양의 determinant, linear singular scale 0.1~10, condition≤4이며 모델 제약을 검사한다. Homography/반전/비선형 Warp는 지원하지 않는다. 화면 Fit 행렬은 과학 정합의 배율 제한과 별도로 검사한다. DPI는 표시 pixel viewport와 마우스 좌표 양쪽에 적용한다.

| 방법 | 구현 / 검사 | 한계 |
| --- | --- | --- |
| SIFT | 4,000 features, CLAHE, 쌍방 ratio<0.75, 중복 위치 제거, RANSAC | 반복 질감·구조 변화에서 실패 가능 |
| ORB | 같은 근거 검사, Hamming matcher | 대규모 배율·질감 차이에 취약 |
| Phase | 1024 이하 공통 명암 canvas, phase shift/response | 이동 중심, 해상도·비율 변화 모델 검사가 실패할 수 있음 |
| ECC | Phase 초기값, 최대 80 iterations, 이동/회전/Affine 보정 | 초기값·내용 변화·해상도 비율에 의존; 모든 모델의 대체가 아님 |
| Manual | 직접 원본 대응점, least squares 및 배치 검사 | 최소 점은 독립 정확도 근거가 아니며 잘못 지정하면 잘못 정합될 수 있음 |

Auto는 Translation→Rigid→Similarity→Affine 순으로 단순 모델을 우선한다. 최선 오차와 0.5 preview pixel 이내이며 Inlier 수가 90% 이상인 단순 후보를 선택한다. 자동 검사: 최소 12 Inlier, 비율≥0.4, 각 영상 support hull≥2%, 공통 After 면적≥5%. RANSAC 임계값은 3 preview pixel을 After 원본 단위로 환산한다. 낮은 근거/퇴화는 실패이며 Identity를 성공으로 반환하지 않는다.

정밀 보정은 near-translation에서 분산된 원본 128×128 Crop 최대 8개를 읽고 Phase 잔차를 확인한다. 3개 이상 일관된 작은 보정이고 기존 특징점 오차가 증가하지 않을 때만 translation을 조정한다. 큰 회전/배율/Affine에는 이 제한적 보정을 억지로 적용하지 않는다.

[OpenCV affine/RANSAC 문서](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html), [ECC 방향/Inverse Warp 문서](https://docs.opencv.org/4.13.0/dc/d6b/group__video__track.html)를 확인하고 합성 변환으로 방향을 검사했다. 이번 코드는 template=Before, input=After인 ECC의 Before→After 행렬을 사용한다.

## Quality / False Matching

- 후보·Inlier 수/비율: 독립 공간 위치를 사용. SIFT orientation 중복은 중복 근거로 세지 않는다.
- 중앙/P90 대응 오차: After 원본 pixel 유클리드 거리. Feature/Manual은 모든 제공 대응점 오차이며 outlier를 숨기지 않는다. 명암 방법은 독립 대응 오차가 없어 N/A이다.
- spatial support: Inlier convex hull / 각 원본 면적.
- overlap_target_fraction: 변환된 Before 외곽과 After 외곽의 교집합 / After 면적.
- linear_condition: 2×2 선형 부분 condition. NaN/Infinity/특이·반전·과도 변형 및 거의 일직선 Landmark 거부.
- 명암 response/ECC correlation은 별도 근거이며 정답 정확도가 아니다.
- NEEDS_REVIEW/REJECTED/ACCEPTED 상태, 이유와 불확실성을 표시한다. 자동 결함 생성·소멸·변환·어닐링 효과를 판정하지 않는다.

## Comparison Viewer / Large JPG

- 두 원본 native decode는 기존 libjpeg→disk memmap 경로를 사용하여 전체 RGB 배열 여러 장을 RAM에 복제하지 않는다. 크기/디스크 예산은 기존 PreparedPixels 정책(원본당 2GiB, 여유 공간 확인)을 따른다.
- Feature Preview: 각 축 최대 1600. SIFT descriptor 두 장 약 4MiB 이내; 최대 4000 특징 및 양방향 KNN으로 근거 수 제한. OpenCV 내부 matching workspace는 라이브러리 구현에 의존하여 실제 Peak RSS도 측정한다.
- 정밀 crop: 한 영상당 24MiB 범위, refinement 최대 8×128². 화면 warp는 최대 3840×2160; 범위 밖/너무 큰 crop은 Preview로 표시하며 `preview`/`original_crop` 표시를 제공한다.
- Fit는 Preview, 확대된 제한된 viewport는 원본 Crop. 100/200/400%에서 nearest neighbour로 원본 샘플을 유지한다. 작은 배율은 표시용 linear 보간. 원본에 없는 정보를 생성하지 않는다.
- Cached output: 최대 3 viewports 및 96MiB. 동일 view 재사용, stale 처리 무효화, 파일/프로젝트 전환 시 native 임시 캐시 수명 종료. OS mmap page cache 사용량과 Python heap은 같은 지표가 아니다.
- Alpha/Split은 QML texture opacity/clip 변경만 수행하여 재디코딩/재warp하지 않는다. Difference는 공통 mask 영역의 absolute RGB difference이며 밝기 변화와 결함 변화를 분리해 설명한다. ROI 기반 정밀 비교는 crop만 warp하며 원본 전체를 매 프레임 warp하지 않는다.
- Before/After 후보는 청록/주황, 해당 Source의 마지막 저장 Run 점과 보유 Geometry를 파생 표시한다. Landmark 잔차 선 포함. Graph는 실제 edge별로 그리며 존재하지 않는 연결선을 만들지 않는다. Viewport 선별·기하 준비는 Worker에서 수행한다. Geometry 이력도 포함되며 mask는 bounding extent만 표시한다. 4096점을 넘는 한 shape는 이 단계의 Canvas 레이어에서 제외한다. 결함 대응 매칭은 수행하지 않는다.

## Asset Integrity / Persistence

`assets/registrations/<SHA256>.json`에 bounded canonical JSON을 완전히 쓰고 검증한 뒤 manifest 관계를 추가한다. 기존 파일의 bytes가 다르면 덮어쓰기를 거부한다. 부정확한 경로/자산 해시/스키마/행렬/다른 Source·Project/원본 SHA/승인 부모 근거를 거부한다. 정합 자산 누락/변조는 안전하게 프로젝트 load/save를 실패시킨다. 원본 누락은 별개로 metadata 프로젝트를 열 수 있다.

ProjectStore OS writer lock, expected_revision, atomic replace, 다른 프로젝트/원본 덮어쓰기 방지, 과거 모든 image_relationships 불변 정책을 유지한다. Save As는 검증된 자산을 새 root에 먼저 복사한다. 저장 실패/충돌에서는 승인된 UI 상태를 적용하지 않는다. 작업 취소/파일·프로젝트 전환의 늦은 결과는 적용하지 않는다. native decoder/OpenCV 단일 호출은 중간 강제 중단할 수 없어 종료 후 token 검사하며 이때도 GUI는 Worker 밖에 있다. 승인 atomic commit은 최종 짧은 구간에서 완료될 수 있으므로 승인 저장 중 프로젝트 전환을 차단한다.

## Synthetic / Windows GUI

정합 집중 검사: **35 passed**, 41.44s (실제 TIFF 회귀와 CPU 자원이 겹친 실행; 초기 34개 독립 실행 6.73s). X/Y 이동, 회전, 배율, Affine, 다른 해상도, 밝기/대비/노이즈, 부분 공통 영역, 특징점 부족, 잘못된 대응, 공선/중복/가장자리, 반복 안정성, 비등방 Preview centre mapping, 원본 cache crop/1·2·4배, 그래프 culling/edge 보존, hash/history/revision/Save As/누락/변조 및 QML stale/TIFF gate/승인/재열기 검증. 합성 특성 변화 tests는 검사점 최대 2 원본 px 이내, 수동 알려진 변환 tests는 <1e-6 px 조건.

Windows Qt/QTest synthetic 실제 화면에서 4개 Landmark를 클릭해 번호/수동 계산/승인/복원을 확인했다. 1100×700, 1440×900, 1920×1080 × QT_SCALE_FACTOR 1/1.25/1.5 모두 버튼 bounds, 좌표 왕복 오차 <1e-12, QML warnings 0. 이 검사는 OS 모니터 DPI 전환이나 물리적 마우스 Acceptance를 대신하지 않는다.

## Performance

실제 Before JPG 12314×12272, After JPG 12349×12273, viewport1000×700. 준비에는 원본 SHA+native decode+Preview가 포함된다. 실제 기존 분석 프로젝트에 추가한 private 복사본 최종 단계 계측: 준비 **11,834ms**, 엔진 구간 Peak RSS **822.8MiB**, Pillow 원본 대조 포함 전체 **998.3MiB** (RSS는 20ms 간격 표본). native+scaled preview 최초 decode 합계 4회. 단회 값이며 반복 준비 성능으로 일반화하지 않는다.

실제 두 파일은 유효 정합이 없어 다음 렌더 benchmark는 정합 없는 각 원본 비교다. 이것은 Identity 정합을 승인했다는 의미가 아니다. 최종 실제 study 보고서에서 각 배율 5회의 wall/process CPU 시간을 별도로 기록한다. GPU 화면 지연과 동일하지 않다.

| 최종 실제 study 계측 배율 | Viewport render 5회 범위 | 사용 데이터 | 반복 동일 view |
| --- | --- | --- | --- |
| Fit≈6.5% | 13.28~15.55ms | Preview | Cache hit |
| 100% | 9.09~14.93ms | Original crop | Cache hit |
| 200% | 9.38~13.23ms | Original crop | Cache hit |
| 400% | 7.74~10.43ms | Original crop | Cache hit |

측정 환경: Windows 11 build 26200, Python 3.13, PySide6/Qt 6.11.2, Intel i7-13700 16 cores/24 threads, RAM 31.75GiB, Intel UHD770/NVIDIA RTX3050가 설치된 D 드라이브 환경. Qt backend는 Direct3D11이며 실제 adapter 선택/외부 화면 present latency를 계측한 결과는 아니다. OpenCV CPU 작업과 Qt 프레임 제출을 구분한다.

실제 JPG 단회 실패 시도 단계별 시간(각 두 영상/양방향 합계):

| 구간 | SIFT | ORB | Phase | ECC |
| --- | --- | --- | --- | --- |
| Feature extraction | 370.41ms | 299.62ms | N/A | N/A |
| Matching | 8.96ms | 25.55ms | N/A | N/A |
| Phase | N/A | N/A | 28.25ms | 22.32ms |
| ECC optimization | N/A | N/A | N/A | 63.78ms |
| 전체 추정 시도 | 389.08ms | 332.13ms | 92.17ms | 104.56ms |
| 유효 Transform / Refinement | N/A — 대응 부족 | N/A — 대응 부족 | N/A — 모델 거부 | N/A — 모델 거부 |

최초 native decode/cache Before 4807.07ms, After 4737.95ms; Preview 생성 Before 1154.37ms, After 916.02ms. 성공 Transform/refinement가 실행되지 않은 실제 실패를 0ms 성공으로 보고하지 않는다. 합성 1024² 알려진 이동 쌍 SIFT Auto 5회에서는 feature 단계 129.00~142.07ms, matching 5.49~7.08ms, transform 3.17~17.86ms, 원본 crop refinement 5.83~9.19ms. 첫 transform 17.86ms와 이후 3.17~3.59ms를 구분한다. 이 수치는 실제 연구 쌍의 정합 성공 성능이 아니다.

Windows Qt 6.11.2 / Direct3D11 / DPR100%, **synthetic 1024²**, 조작→frameSwapped 20회씩: Alpha 중앙 **16.31ms** / P95 **32.44ms**; Split 중앙 **16.56ms** / P95 **22.50ms**. native decoder 합계 4회 유지, Split 동안 viewport revision 변동 없음. CPU 렌더 시간과 실제 GPU 제출을 분리 기록하며 FPS 또는 실제 모든 XRT에서 동일 latency를 주장하지 않는다.

## Real JPG Validation

실험으로 명시적으로 선택한 `before annealing_1.jpg` 및 `After annealing_1.jpg`: 두 SHA 재확인, metadata identity, prepared native crop의 Pillow 직접 crop byte 대조, 캐시, 네 가지 자동 방법의 실패 이력 4건을 별도 private project에서 저장·재열기 PASS. SIFT/ORB는 독립 대응점 부족, Phase/ECC는 서로 다른 영상 비율에서 모델 검사 실패. 잘못된 성공/자동 VERIFIED/Identity fallback이 없다.

기존 프로젝트에 Source/정합 관계만 추가한 복사본에서 analysis_runs/observations/predictions/geometries/review_events/model_provenance/defect_instances 전부 동등하게 보존했다. 기존 manifest와 원본은 그대로다. 실제 원본의 전문가 Landmark·같은 영역 확인·실제 등록 성공 정확도는 **미검증**이다. 합성 QTest 수동 성공을 실제 연구 승인으로 사용하지 않는다.

실패 로그: 초기 real v1에서 Fit 화면 행렬에 과학 변환 배율 한도를 적용한 오류를 발견하여 수정했다. v2/v3 및 실제 study v1로 재검증 PASS. 초기에 Landmark QTest 레이아웃이 안정되기 전 클릭한 capture는 실패했고, layout/frame settle 후 실제 클릭 4쌍으로 재검사 PASS. 모두 artifacts 로그로 보존했다. 기존 tests 삭제/Skip 변경은 없다.

## TIFF / Existing Results / Regression

- Windows 최종 전체: **652 passed / 5 skipped, 912.77s** (앱 Source `31491c552dd72a804918cac2096c6849e1a4d38e`). 초기 전체 650 passed / 5 skipped, 908.66s도 보존했다. 기존 제외는 Windows symlink 권한 1개와 offscreen native GUI 4개이며 추가 Skip 변경 없음.
- Windows native plugin: DPR100% 4 PASS/23.09s, DPR125% 4 PASS/22.42s, DPR150% 재실행 4 PASS/22.61s. 처음 DPR150%는 ImageJ GenericDialog의 parent 위치 변경 후 100ms 검사에서 x=30 (예상50), 1 FAIL/3 PASS/20.88s였고 로그를 보존했다. 같은 코드·설정의 독립 재실행은 통과했지만 간헐적 GUI 위치 갱신 실패의 원인은 미확정이다. Native Plugin/Native Dialog 코드는 변경하지 않았다.
- 실제 saved JPG: Full2946(BPD245/TED1398/TSD1303), ROI791(3/779/9) × 각2 Run PASS. 정합 전 프로젝트와 TD09 baseline, 정합 추가 프로젝트의 4개 Run CSV/JSON byte 대조 모두 동일. Candidate/Raw Score/Model/Review/Geometry 동등성 및 original/model/project SHA 보존. new inference 0.
- TIFF4개 × first/middle/last (12 pages) Stack 및 ImageJ workbench 모두 PASS: 전체 uint16 oracle 비교, ROI Geometry 보존, Area1024 측정, Multiply1 복사본·뷰어, Source/SHA 보존, QML warning0. 자동 ML/BPD/sync0. TIFF에 새 정합을 자동 실행하지 않는다.
- Ruff/compileall/wheel: PASS. Server/Sync/Model update는 전체 회귀 및 별도 PostgreSQL CI로 검사한다. production DB/Model/원본/sources/Native Dialog 코드 수정 없음.
- CI: 최종 Source [run38274296744](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/actions/runs/38274296744) **PASS**. Ruff/import/compile/wheel/PR policy PASS, Linux 전체 **653 passed/4 skipped, 698.24s**, X11 native **4 passed/5 deselected, 25.18s**, 독립 PostgreSQL 서버 **79 passed/1 기존 httpx 경고, 18.98s**. 최종 보고서 HEAD의 CI 링크·판정은 Draft PR에 기록한다.

## GUI Screenshots

모든 아래 캡처는 실제 Windows Qt synthetic 입력이며 연구 원본 pixel을 Git에 넣지 않았다.

- [Before/After 선택](../screenshots/image-registration/01-selection.png), [준비 로딩](../screenshots/image-registration/02-loading.png), [정합 실행](../screenshots/image-registration/03-estimating.png)
- [나란히](../screenshots/image-registration/04-side.png), [겹쳐 보기](../screenshots/image-registration/05-overlay.png), [투명도](../screenshots/image-registration/06-opacity.png)
- [분할](../screenshots/image-registration/07-split.png), [차이](../screenshots/image-registration/08-difference.png), [수동 Landmark](../screenshots/image-registration/09-landmarks.png)
- [품질](../screenshots/image-registration/10-quality.png), [승인](../screenshots/image-registration/11-approved.png), [재열기](../screenshots/image-registration/12-reopened.png)
- [실패](../screenshots/image-registration/13-failed.png), [원본 누락](../screenshots/image-registration/14-missing-original.png)
- [1100×700](../screenshots/image-registration/layout-1100x700.png), [125%](../screenshots/image-registration/dpr125/layout-1100x700.png), [150%](../screenshots/image-registration/dpr150/layout-1100x700.png)

## Known Limitations / Next TD

실제 쌍의 동일 관측 영역 및 전문가 대응점 확보 후 REAL_REGISTRATION_VALIDATED를 별도 판정한다. 자동 정합 실패 시 수동 Landmark를 연구원이 지정해야 하며 이름이 같은 번호라는 이유로 같은 물리 구조를 가정하지 않는다.

비선형/투영/3D/TIFF 정합, 물리 Wafer 캘리브레이션, 결함 매칭·변화 확정 및 서버 정합 자산 반출은 범위 밖이다. Affine 과도한 변형/반전과 불명확한 axis는 거부한다. 대형 회전·배율의 정밀 refinement, mask pixel overlay, 4096점 초과 shape, 하드웨어별 실제 GUI latency 및 OS physical native-dialog Acceptance는 후속 검증 범위다. 외부 중앙 서버 및 ML 승인 데이터에 새 연구 정답이나 모델을 만들지 않았다.

### 검증 Artifact 위치 (Git 제외)

`artifacts/td114-real-study-timing/report.json`: 최종 단계별 CPU/Preview/decode·RSS·viewport 반복 측정, 실패 정합4건과 원본·과학 데이터 보존. `artifacts/td114-synthetic-timings.json`: 성공한 알려진 이동 쌍 SIFT Transform/refinement 5회. `artifacts/td114-real-study-v1/report.json`: 기존 연구 프로젝트에 JPG Source/실패 정합4건 추가, 과학 데이터 동등성, crop/hash/메모리·CPU 시간. `artifacts/td114-real-registration-v2/report.json`: 독립 실제 JPG viewport benchmark5회. `artifacts/td114-real-dataset-regression/report.json`: saved4Run 및 TIFF4개 보존. `artifacts/td114-real-tiff-workbench/report.json`: 실제12page/ImageJ/ROI/원본SHA. `artifacts/td114-registered-export-comparison-v2/report.json`: 정합 추가 후 baseline4Run CSV/JSON byte 동일. 초기 실패 로그와 Native150 재실행 로그, 전체 Windows 로그도 artifacts에 보존한다. 실제 연구 pixel·가공자료·모델·Credential은 Git에 넣지 않았다.

## 최종 판단

이번 변경은 원본 좌표 기반 JPG 정합·비교와 안전한 이력 저장을 제공한다. 합성·기존 실제 연구 데이터 회귀는 통과했다. 선택한 실제 JPG의 자동 정합은 실패했으며, 같은 관측 영역 확인과 전문가 Landmark를 확보해야 실제 연구 정확도를 검증할 수 있다. 따라서 전체 상태는 PARTIAL로 보고한다. 기존 Native Dialog 물리적 Acceptance도 PENDING이다. 후속 TD는 전문가가 지정한 실제 전후 대응점/공통 영역의 독립 검증과 Native Plugin 간헐적 위치 갱신 재현부터 진행한다.
