# XRT-UX-TD-05 — Result UX와 후보 검토

Issue #64. 기준: [TD-01 IA](XRT-UX-TD-01-IA.md), [TD-02 Toolbar](XRT-UX-TD-02-TOOLBAR.md), [TD-03 Context](XRT-UX-TD-03-CONTEXT.md), [TD-04 분석 Flow](XRT-UX-TD-04-ANALYSIS-FLOW.md), PR #63 / `refactor/62-analysis-flow` / `aa4899c0f2bde416b03b0c338e12029cf5419d95`. 작업: `refactor/64-result-ux`.

## 1. 기존 Result UX

ResultContext의 전체 ScrollView(최소 780px) 안에 ResultExplorer가 들어 있었다. 1100×700에서는 상세·목록·탐색·저장에 외부 스크롤이 필요했다. Header, lifecycle 문구, “후보 탐색” 제목과 빈 상세 카드가 결과 안내를 반복했다.

기존 순서: 제목·`필터 수 / 전체 수` → 경고 → 전체/Class 버튼 → 검색·낮은 점수 → 자동 ROI/크기/설명 → 266px 상세 카드 → 이전/다음 → 목록 → 목록 페이지·레이어 → 저장·실행 정보. 전체와 Class 버튼의 역할이 같아 보였다.

## 2. 정보 과잉과 실제 기존 기능

- `245 / 2946`와 선택 전 `0 / 245`의 의미가 불명확했다. 0개 결과에는 `0 / 0`이 나타났다.
- List에 번호·Class·좌표·raw score·낮은 점수·살펴봄이 동시에 노출됐다. 상세는 세 Class raw score를 같은 무게로 표시했다.
- Summary의 Class별 개수는 전체 결과이며, 기존 `filteredTotal`은 Class·검색·낮은 점수 조건을 모두 적용한 수다.
- 기존 Overlay는 이미 `filteredPoints`를 사용했다. 이번 TD가 필터 연결을 처음 추가한 것은 아니다. 일반 원이 불투명하고 색상이 ResultExplorer/Canvas에 중복돼 있었다.
- 검색, 낮은 점수 필터, 자동 ROI(128/256/512), 좌표·ID 복사, 원본 패치, 전체 보기, 실행 정보, 전체 결과 저장은 실제 기능이므로 유지했다. 정렬 기능과 후보 전용 단축키는 없으므로 추가하지 않았다. 기존 List의 키보드 조작과 Viewer 페이지 방향키는 유지한다.
- `visited`/살펴봄은 이번 실행에서 선택한 기록이다. 승인·확정·제외·영구 검수 상태가 아니며 새 검수 버튼을 만들지 않았다.

## 3. 변경 후 정보 위계

Context Header의 **결과** 제목은 한 번만 표시한다. Subtitle은 검토 목적을 안내하고, 결과가 없는 경우에만 lifecycle 안내를 본문에 표시한다.

1. **총 후보 N개**: 전체 결과 Summary, 천 단위 구분.
2. **전체 / ● BPD N / ● TED N / ● TSD N**: Class Filter와 Legend.
3. **BPD 후보 · N개**: 현재 적용된 조건과 결과 수. 검색/낮은 점수 적용 여부도 명시.
4. **이전 / 후보 N / M / 다음**: 현재 필터 기준 탐색.
5. **후보 #ID · Assigned Class / Confidence**: 원본 패치 미리보기, 보조 Class 점수와 좌표.
6. **후보 목록**: 목록만 독립 스크롤. 100개씩 페이지 이동.
7. 조용한 Secondary Action: 전체 결과 저장 / 탐색 설정 / 실행 정보.

기본 검토는 Modal 없이 가능하다. 연구용 raw score·ID를 확인할 때만 **상세…**, 검색·자동 ROI·레이어 설정은 **탐색 설정…**을 연다. Border로 새 카드를 쌓지 않고 spacing·divider·Accent 선택 배경을 사용한다.

## 4. Summary 구조

`research.total`과 `research.counts`를 그대로 표시한다. 총 후보는 큰 Text, 전체 필터는 **전체**라는 조용한 버튼이다. 전체 수를 같은 크기의 Class 버튼에 반복하지 않는다. Class 버튼 개수는 필터가 바뀌어도 전체 분포를 유지한다.

합성 검증: 총 **2,946개**, BPD **245**, TED **1,398**, TSD **1,303**. 합은 2,946이며 필터와 검색으로 원본 개수가 변하지 않는다. 실제 연구 데이터의 분석 결과를 새로 계산한 수치가 아니다.

## 5. Filter / Legend

`ResultPresentation.colorFor()`를 필터 dot와 Viewer Canvas가 함께 사용한다. 실제 기존 색 BPD `#ffad42`, TED `#50e0ee`, TSD `#ff78c4`를 유지한다. 이름·개수·checked 배경·Accessible.name을 함께 제공해 색만으로 구분하지 않는다.

| 선택 | 목록·탐색·Viewer에 사용하는 후보 | Summary |
| --- | --- | --- |
| 전체 | 모든 Class, 검색/낮은 점수 조건 적용 | 전체 분포 유지 |
| BPD | BPD 중 조건에 맞는 후보 | 전체 분포 유지 |
| TED | TED 중 조건에 맞는 후보 | 전체 분포 유지 |
| TSD | TSD 중 조건에 맞는 후보 | 전체 분포 유지 |

조건에 맞는 후보가 없으면 선택 전/빈 안내를 보여주며 0 기준 index를 만들지 않는다. 검색과 낮은 점수 조건은 Class 변경 시 유지하고 화면에 적용 여부를 표시한다.

## 6. Overlay 정책과 성능 판단

**현재 필터 밖의 후보는 완전히 숨긴다.** 기존 `filteredPoints` 배열과 hit-test를 그대로 쓰므로 비선택 Class를 추가로 그리는 비용이 없다. 일반 후보 선만 55% opacity로 낮춘다. 선택 후보는 기존 노란 ring/crosshair/번호·Class label을 100% opacity로 마지막에 그린다. Label은 기존처럼 선택 후보 한 개만 표시한다.

| 상태 | 표시 |
| --- | --- |
| 전체 | 모든 조건 일치 후보의 기존 원, 55% |
| BPD | BPD만 55%, TED/TSD 숨김 |
| TED | TED만 55%, BPD/TSD 숨김 |
| TSD | TSD만 55%, BPD/TED 숨김 |
| 선택 Candidate | 노란 원·십자·번호/Class label 100% |

기존 낮은 점수 원의 흰색 예외도 유지한다. 탐색 설정에서 그 의미를 설명한다. Label은 모든 원에 추가하지 않는다. 원 반경 5, 선택 반경 11, crosshair 길이, lineWidth, viewport culling, 원본 좌표·scale 변환·hit radius 12는 변경하지 않았다. `focusCandidate()`의 450ms 이동/기존 zoom·ROI 크기 정책도 그대로다. 매 선택에 기존 Focus가 수행되고, **전체 보기**로 fit으로 돌아간다.

이번 검증은 2,946개 합성 후보의 필터·탐색·렌더 확인이다. 프레임률 개선 수치를 측정하거나 GPU benchmark 통과로 보고하지 않는다. 전체 필터의 매우 밀집하거나 겹치는 후보는 여전히 복잡할 수 있다.

## 7. Candidate List

Row는 **#번호 / Class · 퍼센트 / 살펴봄 표시**만 표시한다. 좌표·모든 Class score·raw score·patch 설명을 Row에서 제거한다. 45px에서 40px로 정리하고 선택 Row는 AccentPale 배경·Accent 띠·굵은 번호·Accessible.selected로 표시한다. 선택 시 해당 Row를 목록 viewport 안에 놓는다. 페이지 경계의 다음 후보는 기존 controller가 해당 목록 페이지로 이동시킨다.

List는 “선택할 후보”, Detail은 “선택된 후보” 역할이다. Count·Header·Navigation을 스크롤하지 않고 List만 스크롤한다.

## 8. Candidate Detail

가장 먼저 **후보 #N · assigned class**, 다음으로 **assigned confidence**를 강조한다. 다른 두 Class 점수는 작은 퍼센트로, 위치는 그 아래 Secondary 정보로 표시한다. 가장 큰 score를 UI에서 다시 찾거나 Class를 재판정하지 않는다.

원본 128px 패치는 88px 미리보기로 보여주되 기존 원본 읽기·선택 중심 십자·thumbnail generation 검사를 유지한다. 패치 실패와 준비 상태도 표시한다. **위치로**는 같은 후보의 기존 Focus를 다시 수행한다. **상세…**에서 원시 픽셀 좌표, Candidate ID/Point ID, 원본 패치 크기와 raw score, 좌표·ID 복사를 제공한다. Patch는 원본 국소 영상으로 검토에 사용하며, “사람 검수 미확정”은 실제 검수 결과가 없음을 알린다.

## 9. Confidence 표현

모든 기본 점수는 공통 `ResultPresentation.confidence()`를 사용한다. 소수 퍼센트 한 자리로 표시하고 불필요한 `.0`은 생략한다. 부동소수점 경계의 `33.65` 표시를 위해 `Math.round(score * 1000) / 10`을 사용한다.

| 원본 | 기본 표시 |
| --- | --- |
| 0.6605 | 66.1% |
| 0.3365 | 33.7% |
| 0.003 | 0.3% |
| 1.0 | 100% |

모델 점수이며 정답 확률/사람 검수 결과가 아님을 유지한다. UI는 score에 값을 대입하거나 threshold를 변경하지 않는다.

## 10. Raw Score / Export 보존

Raw는 `String(score)`로 표시해 기존 `toFixed(4)`의 표시 반올림을 없앴다. 선택 상세에서 세 Class score와 assigned score를 확인한다. 표시만 달라졌으며 Python 결과/metadata/Export 스키마와 CSV writer는 수정하지 않았다.

완료한 **전체 결과 저장…**은 필터와 관계없이 모든 후보를 저장한다. 0개 결과도 기존처럼 저장할 수 있다. JSON의 full scores·원본 좌표·Class·confidence, CSV 원본 score를 UI 탐색/필터/표시 변경 전후 **파일별 바이트 비교**로 확인했다. 영상 Overlay opacity는 이미지 픽셀/원본/이미지 저장 경로에 영향을 주지 않는다.

## 11. Selection Source of Truth

기존 `ResearchController.selected_id`가 유일한 선택 원본이다. `research.selected`, `selectedIndex`, `displayRows`, thumbnail, Overlay와 automatic ROI는 같은 상태에서 파생된다. UI는 별도 선택 ID/index를 저장하지 않는다.

자동 첫 후보 선택은 기존에 없었다. 선택 전 “N개의 BPD 후보가 있습니다. 검토할 후보를 선택하세요.”를 표시한다. 첫 **다음** 또는 Row/영상 원을 누르면 선택한다. 후보가 새 필터에 포함되면 선택을 유지하며, 제외되면 **선택 없음(B)**으로 돌아가 썸네일과 추적 중 자동 ROI를 정리한다. 수동 ROI 처리 정책은 그대로다.

Class 버튼/검색/낮은 점수 변경 후 유지된 선택이 100개 목록의 뒤쪽 페이지에 있으면 그 선택의 목록 페이지를 표시한다. 이는 기존 `setResultPage()` 호출이며 선택/필터 상태를 새로 만들지 않는다.

## 12. Filter Source of Truth / 재분석

기존 `ResearchController.kind_filter`, `low_only`, `query`를 `setFilter()`로 변경한다. 목록·index·이전/다음·Overlay hit-test가 동일 `filtered` 배열을 사용한다. Summary는 전체, 현재 필터 안내는 filteredTotal로 역할을 구분한다.

기존 generation 정책 유지: 새 Run/원본 파일·페이지 변경은 이전 결과/선택/살펴봄/thumbnail을 무효화한다. RUNNING의 ResultContext에는 이번 결과가 없음을 안내하며 이전 Overlay를 숨긴다. 새 결과 ID가 오면 목록이 다시 생성된다. **Class·검색·낮은 점수 조건은 기존처럼 새 분석/파일에서도 유지**된다. 수동/분석용 작업 ROI의 보존은 기존 정책이다. backend stale validation에 변경이 없다.

## 13. Empty State

| 상태 | 안내 / 동작 |
| --- | --- |
| 분석 전 | 아직 분석 결과가 없습니다. / 목록·저장 숨김 |
| RUNNING | 분석 중입니다. 완료 후 결과가 표시됩니다. / 이전 목록·Overlay 숨김 |
| FAILED/CANCELED | 기존 실패/취소 문구 유지 / 결과 없음 |
| 완료, 총 후보 0 | 후보가 발견되지 않았습니다. + 총 후보 0개 / 탐색·목록 숨김, 저장 유지 |
| 결과 있음, 선택 전 | 필터 수와 후보 선택 안내, 첫 다음/Row 선택 가능 |
| 필터 일치 0 | 조건에 맞는 후보가 없습니다. 필터를 변경하세요. / 다음 비활성 |

`0 / 0`, `0 / 245`, `1 / 0`을 기본 화면에 표시하지 않는다. candidates available에서는 lifecycle 안내를 중복하지 않는다.

## 14. Responsive / 접근성

Result 패널 폭 **380px 유지**. 최소 창 1100×700의 중앙 Viewer 폭 **536px 유지**. 1440×900에서도 패널 폭을 늘리지 않고 목록에 남는 높이를 준다. Summary·Filter·index·선택 Class/confidence·저장/설정은 고정되고 List는 최소 80px로 스크롤한다. raw score/긴 ID/경로는 상세 Dialog 또는 elide로 처리한다.

Class Accessible.name: “BPD 후보 245개”. Row Accessible.name: “후보 816, BPD, 신뢰도 66.1%”. 이름·선택 배경·띠를 함께 제공한다. 기존 Context 메뉴의 Viewer 포커스 복귀, 도구 단축키와 페이지 방향키, 선택 Focus 정책을 유지한다. 후보 전용 단축키 시스템은 추가하지 않았다.

## 15. 테스트와 실제 화면

2026-10-06, Windows / Python 3.13 / Qt 6.11.2 / Java 24. 실제 XRT나 모델 대신 생성 RGB 스택과 테스트 adapter 사용. 모든 캡처는 합성 데이터다.

- 전체: **199 passed, 4 skipped, 155.64초**. skip 4개는 offscreen에서 실행할 수 없는 native plugin 창 검사이며 Windows에서 별도 **4 passed, 56.08초**. 총 203개 시나리오.
- 신규 `test_result_ux.py`: 14개. 다중 Class Summary/전체·BPD·TED·TSD 필터, Overlay와 selection/index, 포함/제외 정책, 뒤쪽 목록 페이지, 퍼센트/원본 값, raw/copy/검색/낮은 점수/ROI 설정/레이어/실행 정보/저장 진입, Export 바이트 보존, 두 창 크기, 이전/다음 페이지 경계, 새 Run·새 파일·zero, assigned class 재계산 방지.
- Ruff, import, compileall, wheel 패키징 PASS. 62개 QML 포함, sources/artifacts/실제 데이터·모델 제외.
- Windows 실제 창 합성 캡처 **10장**, 고정 정보·목록·저장 화면 경계 및 QML 경고 **0개** 확인.
- 추가 Windows Result 14개: **14 passed, 28.65초**, exit code 0. 저장 폴더 대화상자를 열고 취소하는 테스트의 engine teardown에서 Windows COM `0x80010108` 진단이 출력됐다. 해당 assert와 실제 창 캡처는 통과했으며, 이 추가 실행의 native 폴더 정리를 경고 없는 검증으로 보고하지 않는다. 별도 저장 진입 재검사도 1 passed / exit 0과 같은 진단을 남겼다.
- 기존 후보 Viewer hit-test·Focus·자동 ROI·필터·Export 회귀는 `test_result_explorer.py`, Toolbar/Context/Analysis Flow 및 원본 좌표/identity 검사를 유지했다.

| 화면 | 캡처 |
| --- | --- |
| 분석 전 | [1100×700](../screenshots/result-td05/before-analysis-1100.png) |
| 전체·선택 전 | [1100×700](../screenshots/result-td05/all-unselected-1100.png) |
| 전체·선택 상세 | [1100×700](../screenshots/result-td05/all-selected-1100.png) · [1440×900](../screenshots/result-td05/all-selected-1440.png) |
| BPD / TED / TSD | [BPD](../screenshots/result-td05/bpd-selected-1100.png) · [TED](../screenshots/result-td05/ted-selected-1100.png) · [TSD](../screenshots/result-td05/tsd-selected-1100.png) |
| raw / 탐색 설정 | [상세](../screenshots/result-td05/raw-detail-1100.png) · [설정](../screenshots/result-td05/options-1100.png) |
| 0개 결과 | [1100×700](../screenshots/result-td05/zero-result-1100.png) |

## 16. 보존·제약·후속 TD

분석 알고리즘/threshold/Class 판정/score/후보 개수·좌표/Overlay geometry/Export 데이터/backend/원본 TIFF/sources는 변경하지 않았다. 계약 버전·스키마·해시·모델 호환성 영향 없음. Toolbar·Context 전환 규칙·TD-04 실행 조건도 유지한다.

실제 사용자의 “3초 내 이해” 시간은 사용자 실험으로 측정하지 않았다. 합성 UI·integration·native 검증이며 이번 TD에서 실제 모델 inference/대형 TIFF 성능/물리적 Z 검증을 새로 수행하지 않았다. 전체 필터의 겹침, 기존 선택 시 zoom, 88px 패치 미리보기 크기, 기존 필터 유지 정책은 후속 사용자 피드백 대상이다. 사람 검수/annotation persistence나 새 검색·정렬은 구현 범위에 없다.

Windows native 저장 폴더 취소 후 테스트 engine 해제 시 COM 진단의 원인은 이번 UI 범위에서 확정하지 않았다. 기존 저장 대화상자/Export backend는 수정하지 않았으며, 지속 실행 앱에서의 창 닫기·반복 저장 확인은 별도 과제로 남긴다.

- TD-06: ROI 생성·편집·관리와 분석 영역 역할.
- TD-07: TIFF 초기 loading·progress·취소·메모리.
- TD-08: 전체 Visual Density·typography·border.
