# XRT-PERF-TD-03 Result

## Status

**PARTIAL** — 원본 좌표 기반 확대와 표시 무결성은 자동 검증 PASS.
125% DPI Windows D3D11 반복 성능도 PASS. 물리 마우스/OS DPI 설정을
직접 바꾸는 수동 acceptance는 PENDING이다. 자동 입력을 수동 PASS로 표시하지 않는다.

Issue: [#87](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/87).

## 1. 사용자 보고와 원인 확정 범위

28.5 → 35.6 → 44.6 → 55.7% 확대에서 이미지가 좌측/하단으로 치우친다는 보고를 조사했다.
스크린샷에 커서 위치가 없어 사진만으로 원인을 확정하지 않았다.
코드와 실제 입력 재현에서 다음 오류를 확인했다.

- 휠과 Zoom 도구 클릭이 커서 좌표 없이 `zoomIn/zoomOut`을 호출했다.
- 배율만 바꾸고 Pan의 논리 픽셀 이동량을 그대로 유지했다. 따라서 Pan 이후에는
  Viewer 중심 아래 원본 픽셀조차 바뀌었다.
- Pan 이벤트의 픽셀 검사 좌표가 Pan을 적용하기 전에 계산됐다.
  재현 시 표시 `(301,262)`와 실제 `(279,277)`이 달랐다.

Fit 자체의 중앙 정렬, DPR 중복 변환, 원본/preview 크기 혼동, 중복 wheel 처리,
정밀 화면의 비동기 위치 덮어쓰기는 이번 재현에서 원인으로 확인되지 않았다.
사용자 스크린샷의 모든 배치가 단일 원인으로 설명됐다고 주장하지 않는다.

## 2. 기존 Viewer 구조와 Source of Truth

| 상태/계층 | 기준 |
|---|---|
| 원본 크기 | `UiState.contentWidth/contentHeight` (실제 이미지 metadata) |
| 표시 크기 | 원본 크기 × `ImageViewer.displayScale` |
| Fit | `min((viewport.width-16)/원본W, (viewport.height-16)/원본H)` |
| 일반 배율 | `uiState.zoom / displayPixelRatio` |
| Image 원점 | `(viewport-표시크기)/2 + panX/panY` |
| Pan | viewport 논리 픽셀 이동량, Viewer 한 곳에서 관리 |
| 정밀 표시 | `PreparedView.viewTransform = [imageFrame.x,imageFrame.y,displayScale]` |
| Overlay | 같은 원점/배율로 원본 좌표를 화면에 투영 |

ImageViewer의 52px Header 아래 `viewerViewport`가 실제 이미지 영역이다.
그 안의 MouseArea, imageFrame, PreparedView, Overlay가 같은 local 좌표를 사용한다.
Flickable/Scroll offset, WheelHandler, PinchHandler나 별도의 Pan/Zoom 상태는 없다.
휠은 MouseArea 한 곳에서 처리하고 `accepted=true`로 종료한다.

## 3. 기존 Zoom과 수정 후 동작

| 입력 | 수정 후 기준점 | 유지한 정책 |
|---|---|---|
| 단일 이미지 wheel / Ctrl+wheel | 커서 | 한 이벤트당 1.25배 한 단계 |
| Stack 일반 wheel | 페이지 | 위/아래 페이지 이동, 확대하지 않음 |
| Zoom 도구 클릭 / Alt+클릭 | 클릭 위치 | 확대 / 축소 |
| Toolbar +/- / Ctrl++ / Ctrl+- | Viewer 중심 아래 원본 픽셀 | 1.25배 단계 |
| Fit / Ctrl+0 | 이미지 전체 중심 | 기존 Pan 제거, 전체 contain, 종횡비 유지 |
| 1:1 / Ctrl+1 / 기본 실제 크기 | 원본 이미지 중심 | 기존 명시적 Pan reset 정책 |

`zoomAt`은 기존 후보 Focus 애니메이션을 먼저 정지한다. 이전 Focus 애니메이션이
다음 사용자 입력의 Zoom/Pan을 덮어쓰지 못하게 한다. Viewer 크기 변경이나 페이지
변경을 임의의 자동 Fit으로 바꾸지 않았다.

## 4. Zoom Anchor Formula

viewport 논리 좌표의 커서 `c`, 원점 `t0`, 논리 배율 `s0`에 대해:

```text
source = (c - t0) / s0
s1 = clamp(physicalZoom, 0.01, 16) / DPR
t1 = c - source * s1
pan1 = t1 - (viewportExtent - originalExtent * s1) / 2
```

실제 코드는 X/Y에 각각 위 식을 적용한다. 배율/Fit 상태를 바꾸기 전에 source를
snapshot하고, 새 배율과 새 Pan을 함께 적용한다. 이는
`t1 = c - (c-t0)*(s1/s0)`와 동일하다. Zoom에서 Pan을 0으로 초기화하지 않는다.

기존 제품은 Pan/이미지 원점에 공간 clamp를 두지 않는다. 이를 유지했다.
화면보다 작은 이미지, 가로만 큰 이미지, 세로만 큰 이미지, 이미지 밖 커서에서도
동일한 affine 변환을 적용한다. 이미지 밖 pixel inspection은 기존처럼 `-1`이다.
원본/ROI 좌표 clamp와 확대율 한계(1–1600%)를 공간 Pan clamp와 혼동하지 않는다.
검사 허용 오차는 부동소수 계산 `1e-7` 원본 px로 설정했다(요구 목표 ≤1px보다 엄격).

## 5. Mouse Coordinate System와 DPI

Global screen → Window → viewport는 Qt `mapToScene/mapFromScene/mapToItem`으로 변환한다.
제품의 MouseArea wheel/click 좌표는 viewport 논리 픽셀이다. Sidebar/Header 크기를
빼는 상수를 추가하지 않았다. Image item 좌표는 viewport 좌표에서 imageFrame 원점을
빼며, 이를 displayScale로 나누면 원본 픽셀 좌표다. Preview 픽셀 좌표는 Zoom 계산에
사용하지 않는다. DPR은 물리 배율에서 논리 배율을 구할 때 한 번 적용한다.

Qt 6.11.2 `QTest.wheelEvent`에 논리 위치를 넣은 초기 시험에서는 125% DPI wheel
위치가 다르게 전달됐다. click은 정상이고 wheel에만 오차가 있었다. 검증 도구는
명시적인 논리 위치의 `QWheelEvent`를 Qt에 전달하도록 수정했다.
제품에 테스트 주입 오차를 보상하는 DPR/offset 수정을 넣지 않았다.
[Qt QWheelEvent 좌표 정의](https://doc.qt.io/qt-6/qwheelevent.html) 참조.
마우스 클릭/Pan/Shortcut은 QTest, wheel은 Qt 이벤트 주입이며 모두 자동 검증이다.

## 6. Preview / Original / 정밀 표시

실제 JPG는 12349×12273 RGB8, overview는 1765×1754이다.
Zoom %는 **물리 화면 픽셀 / 원본 픽셀**이다. 예를 들어 125% DPI의 100%는
논리 배율 0.8이고 원본 1px를 물리 1px로 표시한다.
28.5%에서의 물리 표시 너비는 약 3519.5px이며 preview 1765px 기준 배율이 아니다.
Fit에서는 기존처럼 % 대신 `FIT`을 표시한다.

PreparedView는 원본 크기와 같은 imageFrame 원점을 사용하여 필요한 원본 영역을
읽는다. 기존 pyramid, mmap, QImage cache(32MiB), DPR sampling 정책을 유지했다.
완료된 표시의 100% 이상은 native level/nearest이며 원본 픽셀 경계는 정상이다.
100% 미만의 축소 보간도 기존 정책이다. 비동기 detail 응답은 ImageFrame/Pan을
변경하지 않는다. 새로운 renderer/pyramid/cache 확장은 없다.

## 7. Fit / Pan / 배치 검증

- Fit 후 Pan 0, 가로·세로 독립 중앙 정렬, 전체 이미지 contain 확인.
- 320×240, 1920×240, 320×1920, 1920×1440 geometry ablation 검사.
  이 ablation은 좌표 검사이며 실물 화질 검사는 아래 실제 파일로 별도 수행했다.
- 0.285 시작 1.25배 3단계와 역순, 고배율 반복, Pan 이후 확대/축소, Toolbar 중심 확대 확인.
- Sidebar 축소/복원 및 Header가 있는 Window에서 Qt local mapping 확인.
- 빠른 입력 후 Focus가 정지되고 마지막 transform이 유지됨을 확인.
- 확대 중 파일 전환 후 새 파일의 기존 기본 View 정책과 이전 cache 정리 확인.

## 8. Before / After Zoom 테스트

수정 전 재현 테스트: **14 failed / 1 passed**. 테스트를 먼저 커밋한 후 제품을 수정했다.
125% software, 실제 JPG, 동일 원본 위치의 첫 1.25배 단계:

| Case | Anchor Before | 기존 Anchor After / Error(px) | 수정 Anchor After / Error(px) | PASS |
|---|---|---|---|---|
| Viewer 중심 | 6174.5,6136.5 | 동일 / <1e-12 | 동일 / 0 | PASS |
| 좌상단 | 5687,5761.5 | 5784.5,5836.5 / 123.009 | 동일 / 0 | PASS |
| 우하단 | 6662,6511.5 | 6564.5,6436.5 / 123.009 | 동일 / 0 | PASS |
| Pan 이후 | 5900.75,6354 | 5955.5,6310.5 / 69.927 | 동일 / 0 | PASS |
| Zoom 왕복 | 5930.75,6324 | 동일 / 0 | 동일 / <1e-12 | PASS |
| Fit 후 커서 Zoom | 3733.277,8025.940 | 4221.521,7648.052 / 617.400 | 동일 / <1e-12 | PASS |

기존 구현도 왕복 종료점과 Pan 없는 중심 확대는 통과한다. 중간 단계 및
커서가 중심 밖인 조건이 오류를 드러냈다. 수정 후 3 DPI, 실제 13개 페이지에서
**1209개 anchor 관찰**이 모두 허용 오차 이내였다.

## 9. DPI 결과

Windows 11의 별도 Qt 프로세스에서 `QT_SCALE_FACTOR`를 설정하고 실제 Window/UI DPR을 확인했다.
OS 디스플레이 설정을 수동으로 바꾼 검증과 구분한다.

| DPI | 자동 좌표/화질 backend | 최대 원본 좌표 오차(px) | 완료 표시 비교 |
|---|---|---|---|
| 100% | offscreen/software | 9.095e-13 | 52/52 exact |
| 125% | offscreen/software | 9.095e-13 | 52/52 exact |
| 150% | offscreen/software | 2.728e-12 | 52/52 exact |
| 125% | Windows/D3D11, 실제 JPG | 1.017e-12 | burst 후 4/4 exact |

20개 새 회귀와 기존 피드백 통합 2개도 125% DPI에서 22 passed였다.
초기 18개 좌표 회귀는 150%에서 18 passed였다.
100/150% native GPU 및 물리 마우스의 별도 acceptance는 이번 자동 DPI 행렬에 포함하지 않는다.

## 10. 실제 JPG / TIFF Stack

| 파일 | 크기 / 타입 | 검사한 1-based 페이지 |
|---|---|---|
| After annealing_1.jpg | 12349×12273 RGB8 | 1 |
| N119_220_Section_stack_flipped.tif | 3072×3012 uint16 | 1,80,158 |
| No107_SectionTopo-beforeAnnealing.tif | 2922×2895 uint16 | 1,79,156 |
| No107_SectionTopo-afterAnnealing .tif | 2922×2895 uint16 | 1,79,156 |
| No22_220_Section_stack_flipped.tif | 2944×2745 uint16 | 1,79,156 |

모든 페이지에서 커서 Zoom/Pan/Fit과 100/200/400/800% 원본 crop를 검사했다.
동일 크기의 페이지 전환은 기존 Zoom/Pan을 유지하고 ROI 선택을 해제한다.
크기가 달라지면 기존 defaultView를 적용한다. 마지막 요청 우선 처리도 확인했다.
페이지를 공간 Z로 해석하거나 TIFF/JPEG를 수정하지 않았다.

## 11. 화질 비교 / 원본 SHA

원본 독립 decode crop `(1003,1011,128,96)`와 source.read_region을 먼저 대조한다.
각 물리 Zoom의 Viewer 캡처를 동일 원본의 window/level 변환 및 nearest 반복 값과
비교한다. fractional-DPI clip 외곽 2px를 제외한 **124×92 물리 픽셀**이 모두 exact였다.
정식 페이지/DPI 행렬 156개 비교와 별도 burst 후 비교가 통과했다.
전체 화면/전체 파일의 모든 픽셀을 exhaustive 비교했다는 의미는 아니다.

모든 원본은 매 실행 전후 SHA256이 동일했다. 최종 150% 실행의 값:

| 파일 | SHA256 |
|---|---|
| JPG | c864ce2410e940ee0e5c11faf4bec2f38fa66cf1f8d5ecc4cc15bfa5b60f1c47 |
| N119 | 434b86d180d1e7238540cde1a81a099670e145dd40ef7a114e75bae7e9b387bb |
| No107 after | 81d5c2a0f795f90a2db1ddee3debf3f570b0e2c8223ab76384d31f21bfcefeb7 |
| No107 before | 5d3aa50d204e118ca42ec7b54ff3444bde7406e9a548421042cd01e4272f47f4 |
| No22 | e28cf99b4d482f24628cb87f9122b5ae505d73c9fdc5a8bd8b11380fc25542dd |

실제 crop/캡처/모델/원본 경로와 raw 보고서는 ignored artifacts에만 저장했다.

## 12. ROI / Overlay / 분석 보존

분석 ROI의 원본 X/Y/W/H가 Pan/Zoom 이후 동일함을 확인했다.
BPD/TED/TSD를 각각 선택한 후 Zoom하고 동일 후보를 화면에서 다시 hit-test했다.
Imported point/polygon ROI, 후보 Canvas, PreparedView가 동일 imageFrame 원점/배율을
사용함을 확인했다. Overlay on/off 및 Focus 후 마지막 화면도 검사했다.
기존 사각형/선/측정/ROI 편집·Export 계약의 회귀는 전체 테스트에서 확인한다.

실제 JPG의 `spatial64-c4-24368b8f6613` 모델 결과는 BPD245/TED1398/TSD1303,
총 2946개였다. TD-12 저장 결과와 ID, 원본 좌표, 분류, score, 전체 scores를 포함하여
정확히 동일했고 상호작용 후에도 동일했다. 이는 분석 정확도의 새 평가가 아니다.
uint16 grayscale 모델 호환성 제한은 유지했다.

## 13. 성능 비교

Windows 11 26200, Python3.13.7, Qt6.11.2, Direct3D11, RTX3050, basic render loop,
DPR1.25, Window1440×900, JPG400%, 후보2946/ALL. 다른 테스트 프로세스의 실행을
마친 뒤 Before → After를 순서대로 실행했다. 각 Pan/Zoom 30회, 반복과 별도 cold sample을 구분했다.

Before는 정확한 b7637be ImageViewer를 URL interceptor로 로드한다.
양쪽 모두 현재 main에서 통합한 동일 Main/Context/Feedback 기반 UI를 사용했다.
초기 Image Context viewport는 974×750이며 Result Context 전환 후 폭은 줄어든다
(anchor 행의 center local X438). Context 폭 변화는 양쪽에서 동일하게 유지했다.
이전 TD-02 15.35/15.24ms는 참조 값이며 직접 비교쌍은 아래 새 실행이다.

측정치는 명령부터 Qt `frameSwapped` **제출 완료**까지다. 물리 present/input-to-photon은 아니다.
Baseline 약15ms를 기준으로 중앙값 25ms 이내, p95 50ms 이내, 반복 중 재decode 0을
이번 퇴행 판정 기준으로 삼았다. 새로운 속도 향상을 목표로 한 TD가 아니다.

### Before Benchmark

| 배율 | Zoom median/p95 | Pan median/p95 | Pan frame interval median | RSS |
|---|---|---|---|---|
| 400% | 14.761/16.536ms | 14.582/18.910ms | 16.334ms | 1134.57MiB |

### After Benchmark

| 배율 | Zoom median/p95 | Pan median/p95 | Pan frame interval median | RSS |
|---|---|---|---|---|
| 400% | 15.517/18.224ms | 15.000/18.346ms | 16.407ms | 1125.66MiB |

추가 실제 wheel 이벤트 30회: Before median15.296/p95 29.347ms →
After median14.306/p95 15.869ms. 최대 anchor 오차 11.915px → 9.095e-13px.
단일 순차 비교쌍으로 통계적인 속도 개선을 주장하지 않는다. 퇴행 판정 기준은 PASS.

두 실행 모두 비교 루프에서 JPEG decode **0**, 원본 영역/cache refill 1회와 변환 1회,
Pan cache hit 30/30, Zoom cache hit 29/30이었다. QImage cache 한도는 32MiB이다.
GUI timer 최대 간격은 18.577 → 19.896ms, 50ms 초과는 0이었다.
1-core CPU 환산 81.88 → 78.07%이며 시스템 전체/GPU 사용률을 의미하지 않는다.
GPU upload 시간·바이트·VRAM·물리 dropped frames는 NOT MEASURED.

## 14. 최소 수정 및 대규모 개선 여부

제품 수정은 ImageViewer.qml뿐이다: source anchor 계산, wheel/click 기준점 전달,
Pan 이후 pixel inspection 갱신. 원본/분석/ROI geometry/ImageJ/Fiji/ONNX/Export 및
Native Dialog 구현은 현재 main과 동일하다. 기존 렌더러로 좌표 오류를 해결했다.
대규모 Tile/Pyramid Renderer TD를 새로 요구할 근거는 이번 문제에서 발견하지 못했다.
Fit 대량 Overlay 최적화는 기존 #84에서 별도 판단한다.

## 15. 전체 Regression

Windows/Python3.13.7/Qt6.11.2의 제품·테스트 HEAD
`bebf4c6b1290952b8412821eab136554aee43e69`에서 **334 passed / 4 skipped**,
481.78s, process exit0. 기존 302개를 유지하고 main의 12개 추가 검사 및 새 좌표 검사
20개를 포함한다. 이후 변경은 이 보고서뿐이며 최종 PR HEAD에서도 CI 전체 gate를
다시 실행한다. 최종 SHA/CI/Windows Native 재검사 결과는 PR 본문에 기록한다.

Ruff, compileall, wheel build PASS. Windows Native Plugin 기존 4개 검사는
4 passed / 5 deselected (49.78s), 첫 실행 exit0였다. 이전 TD-02의 간헐적인 geometry
실패 기록을 삭제하거나 해결됐다고 하지 않는다. Native Dialog 제품 코드는 변경하지 않았다.
새 20개 좌표 테스트 및 기존 Toolbar/Context/Analysis/Result/ROI/Model Preflight/
TIFF Loading/Viewer Render/Native Dialog/Export 검사를 유지했다.

## 16. 실제 마우스 / Known Issues

- 사용자가 Viewer를 앞에 유지하는 동안 자동 화면 계측은 완료했다.
- 자동 QTest/Qt wheel 이벤트와 물리 마우스 조작은 다르다. **물리 마우스 acceptance PENDING**.
- OS DPI 설정 자체를 바꾼 실사용 검증과 100/150% native GPU 재검증은 PENDING.
- Fit 대량 Overlay #84, Native Plugin geometry 간헐 실패 #84, Qt6.12 shutdown #83,
  Native Dialog 근본 원인 #74 / 수동 acceptance #80 및 모델 정확성 #49는 별개로 남는다.
- 화면/GPU의 미계측 항목을 FPS 향상이나 0 freeze 보장으로 바꾸지 않는다.

## 17. 검증 실행 방법 / 실패 로그

```powershell
$env:PYTHONPATH = "<checkout>\src"
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_SCALE_FACTOR = "1.25"
python tools/validate_cursor_zoom.py "<JPG>" "<TIFF>" --output artifacts/perf-td03/coordinates
```

화면 비교는 `QT_QPA_PLATFORM=windows`, `QSG_RHI_BACKEND=d3d11`,
`QSG_RENDER_LOOP=basic`와 `--benchmark --repeats 30 --model <bundle> --reference-result <result.json>`을 쓴다.
동일 기준 Viewer 재현은 `--baseline-ref b7637beb8127fc597f94caacbff2c1729eb4a86d`.
Opt-in 도구에는 개발 환경의 `psutil`도 필요하다. 테스트는 `python -m pytest tests/test_cursor_zoom.py -q`.

초기 테스트 준비/API 오류와 QTest DPI 주입 오류는 corrected 로그와 구분해서 보존했다.
첫 native benchmark는 오래된 Export reference에 number/scores가 없어 초기 equality
검사에서 중단됐다. 동일 원본/모델/설정의 TD-12 reference로 변경한 최종 두 실행은
완전한 rows equality로 통과했다. 허용 오차로 score/좌표 차이를 숨기지 않았다.
main 통합 전 예비 전체 검사는 통합 후 재검사를 위해 중단했으며 완료 gate로 집계하지 않는다.

Raw 결과: `artifacts/perf-td03/actual-software-{1,1.25,1.5}/report.json`,
`before-anchors`, `before-hardware-125-final`, `after-hardware-125-final`,
`native-plugin.xml`, `final-full-pytest.xml`. 실제 영상 캡처는 Git에 추가하지 않았다.

## 18. Git

- 시작 Branch: `perf/84-viewer-interaction-validation`
- 시작 HEAD: `b7637beb8127fc597f94caacbff2c1729eb4a86d`
- 작업 Branch: `fix/87-cursor-anchored-zoom`
- 제품/검증 도구 HEAD: `bebf4c6` (문서 commit 이전)
- 51f0c3c: 수정 전 재현 테스트
- 55a4e6a: 커서 및 중심 확대 계산
- a914dd4: Pan pixel inspection 및 DPI/Overlay 회귀
- 0e7baa1 / bebf4c6: 실제 데이터/화면 계측 도구
- 90d2591: 현재 main `1fe49b3` 통합, Feedback gesture guard와 픽셀 갱신 충돌 해결
- 최종 HEAD/Push/Draft PR/CI: PR 본문에 전체 SHA와 확정 gate 결과를 기록한다.

#85와 선행 PR은 이전 정리 작업에서 이미 병합됐다. 이번 TD에서 이들을
merge/rebase/retarget하지 않았다. 새 브랜치의 PR은 현재 main을 대상으로 한다.
원본 체크아웃의 사용자 AGENTS.md 변경은 보존하며 이 PR에 포함하지 않는다.
