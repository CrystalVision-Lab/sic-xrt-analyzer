# XRT-UX-TD-08 — Visual Density 및 전역 시각 위계

Issue #70. 기준 PR #69 / `refactor/68-tiff-loading-ux` / `c148d5d6fa84811d26ff73cd72c410a36607e0e0`.

## 1. 구현 전 Visual Inventory / 문제

제품 변경 전에 UI 64 QML과 동일 합성 데이터의 Qt 실제 화면을 조사한다. IA/Flow/원본 데이터/geometry/backend는 그대로 유지하고 시각 표현만 정리한다.

| 조사 대상 | 변경 전 조사 |
| --- | --- |
| AppShell / Menu | Segoe UI 12px, 메뉴 30px, 전역 palette. MenuBar 자체 border와 팝업 border 중복 |
| Toolbar / Dropdown / More | 7버튼 32px hit target, spacing 5/6px, 아이콘 16/20px, 일반/checked 버튼에 테두리. Popup row 30px |
| Navigation / Current / Recent | 184px 폭, 작업 34px·파일 25px, 현재/최근 11px, 하단 10px, passive 준비 원형 표식 |
| ViewerHeader / ImageViewer | 파일 12px, 메타데이터 11px, 기존 2줄 Header, empty 17/12px, 원본 렌더링·좌표·Overlay 별도 |
| Right Panel / ContextHeader | 일반 282px·Result 380px, 여백 12px, context button 32px, 부제 11px |
| ImageContext | 본문 12px, caption 11px, Section 11px DemiBold+letterSpacing+매번 divider |
| AnalysisContext | 모델 12px, 상태 13px DemiBold·accent, 모델 연결도 색 상태, 연구 주의 문구 warning, 버튼 28px |
| ResultContext / List / Detail | 총수 21px Bold·점수 25px Bold·Class 15px Bold 동시 강조, 필터 11px, 목록 12px, helper 10px, row 40px |
| RoiContext / Detail | 두 요약 모두 12px Bold, 원본 좌표·페이지 10px, helper 11px, list 36px, divider+Section divider 중복 |
| ViewerContext / Loading | 기존 단계 상태 유지, 페이지 12px·helper 11px, 대비 TextField 28px, 준비 count와 현재 page 별도 |
| StatusBar | 28px, 대부분 11px, 정상 완료 success+현재 도구 accent 등 중복 색. 기술 장치 placeholder |
| Dialog / Popup / Model·Candidate·ROI 상세 | Dialog 기본 Qt와 AppDialog 혼재, radius 3/4/5px, input 높이 28px와 Qt 기본 혼재, 기술 본문 11/12px |
| Empty / Error | 기존 간결한 메시지 및 error detail 접근. 새 카드나 오류 panel 전체 border 불필요 |

정적 Inventory: border.color 선언 **24곳 / 16개 파일**, 하드코딩 font 10px **14곳**, radius literal 2/3/4/5 혼재. 이는 실제 화면의 border 수가 아니라 소스 선언 수다. readonly 정보에 중첩 Card-in-card는 현재 주요 Context에 없으므로 새 카드도 만들지 않는다.

## 2. Typography system

`Theme.qml`의 공통 토큰을 적용한다. 값은 Qt 논리 픽셀이다.

| 역할 | 크기 / Weight | 용도 |
| --- | --- | --- |
| Title | 15 / Medium~DemiBold | Context·Dialog 제목 |
| Section | 13 / Medium | 기능 단위 제목, letterSpacing 없음 |
| Body | 13 / Regular | 주요 설명·입력·버튼 |
| Secondary | 12 / Regular·muted | 보조 설명·파일·페이지 |
| Caption | 11 / Regular·muted | 좌표·기술 ID·상태 |
| 예외 | Empty 17, Confidence 22 / Medium | 빈 화면 제목·현재 후보의 대표 점수 |

총 후보 수는 21 Bold → 15 Medium, Confidence는 25 Bold → 22 Medium으로 바꾼다. 기본 UI의 10px 글자는 없애고 최소 11px로 올린다. 기존 글꼴 Segoe UI / 기술 문자열 Consolas를 유지한다. Linux에서는 설치된 Qt 대체 글꼴을 사용한다.

## 3. Spacing

XS=4, S=8, M=12, L=16, XL=24. Section 상단은 12, 제목 아래는 4, 일반 행은 8을 사용한다. 패널 좌우 12를 유지한다. 기존 3/5/6/10/14/18 간격을 공통 토큰으로 통일하고 이미지 좌표·Overlay·렌더링 크기는 바꾸지 않는다.

## 4. Control height

Compact=28, Default=32, Primary=36. Toolbar hit target=32, Menu row=32, 목록 row=40. TextField·SpinBox·ComboBox·Checkbox의 공통 기준은 32이며 Slider 입력 높이는 28, 손잡이는 12다. `AppTextField`, `AppSpinBox`를 추가하여 기존 validator·editable·signal 동작을 상속한다. 작은 ROI 제거 버튼만 compact 28을 사용한다.

## 5. Border 정책

일반 Panel·Navigation·MenuBar outer border, 기본 버튼 테두리, 매 Section의 divider를 제거한다. 배경과 여백으로 그룹을 구분한다. 입력은 1px, 키보드 focus는 2px, Dialog/Popup은 1px를 유지한다. 선택 후보·ROI는 배경과 strip/선택 상태로 표시하고 키보드 focus에만 테두리를 추가한다. destructive/warning 문구는 의미에 맞는 색을 유지한다.

SectionHeader에는 divider를 넣지 않는다. Result·ROI의 큰 작업 경계에는 `borderSubtle` 한 줄만 유지하고 고정 Action 영역의 경계는 유지한다. 주요 Context의 Card-in-card는 기존 0개 → 0개다.

## 6. Radius

Small=4, Control/Popup=6, Dialog=8. 작은 입력·아이콘 버튼은 4, 일반 버튼·메뉴는 6, Dialog는 8로 통일한다. StatusIndicator의 5px 상태 점 radius=2는 비조작 도형 예외다. Image/ROI geometry는 radius 정리 대상이 아니다.

## 7. Color hierarchy

Primary text `#e4e8eb`, Secondary/Technical `#929da6`, disabled `#87939d`. disabled는 기존 `#77828a`보다 밝게 하여 읽을 수 있게 한다. Accent `#45c3cf`는 선택·활성 도구·대표 실행에 사용한다. 정상 준비/모델 연결 상태의 중복 green/accent를 neutral로 줄인다. Warning `#d6ac64`는 실제 주의·낮은 점수·미저장 ROI, Error `#e68181`는 실제 실패에 사용한다. 원본 영상·Class Overlay 색은 유지한다.

surface `#272d33` 대비 자동 계산은 본문 ≥7:1, muted ≥4.5:1, disabled ≥3:1을 검사한다. 이는 제한된 색 조합의 기본 검사이며 모든 배경·플러그인 창에 대한 접근성 인증이 아니다.

## 8. Button hierarchy

Primary: Analysis의 실행 한 개만 filled Accent 36px. ROI의 기존 선택/편집 상태는 pale background로 식별한다. Secondary: 기본 neutral surface 32px. Tertiary: 상세·모델 변경·관리·저장 등 ghost/text. Result에는 filled Primary CTA가 없다. hover·pressed·checked 배경과 키보드 focus 2px, disabled 글자를 유지한다. 공통 AppButton의 `quiet`, `compact`, `labelSize`, `labelWeight`가 표현만 제어한다.

## 9. Context별 적용

Context whitelist·자동 전환·Navigation·메뉴 구조는 TD-01~07 그대로다. Context 제목은 15 Medium, 설명은 12 muted, body 13, technical caption 11이다. 이미지 정보의 중복 제목과 파일 로드 후 중복 부제를 줄인다. 경로·hash·원본 ID는 기존 상세 접근·복사 동작을 유지하고 elide/wrap/tooltip으로 패널 폭을 넘지 않게 한다. 긴 hash는 단어 경계 없이도 줄바꿈한다.

## 10. Toolbar

열기 / Pan / Zoom / Fit / ROI / 측정 / More 7개, 32px hit target, 기존 단축키 유지. 아이콘 20, 그룹 내부 간격 4, 제목 추가 없음. active는 pale Accent background와 텍스트로 표시하며 평상시 버튼 박스는 제거한다. ROI·측정·More 메뉴는 32px 행, 기존 check gutter와 submenu를 유지한다. 메뉴를 Escape로 닫으면 기존 호출 버튼 또는 Viewer의 포커스로 돌아간다.

## 11. Navigation

폭 184 유지. 작업 항목 34→40, 현재/최근 파일 25→32. 파일 11→12, footer 10→11. 파일명을 elide하고 기존 전체 경로 tooltip을 유지한다. 준비 중 작업의 수동 원형 표식을 없애고 기존 비활성/준비 안내를 유지한다. active 배경은 유지하고 read-only 파일 텍스트는 기본 색으로 한다.

## 12. Analysis

모델·범위·입력 → 준비 상태 → 실행 순서 그대로. 기본 화면에서 모델/범위/입력/Ready/Run을 모두 볼 수 있다. 모델 연결은 muted, 준비 상태는 13 Medium neutral, 실행은 유일한 filled Primary. 고급 설정의 기존 독립 스크롤과 하단 실행 영역을 유지한다. 연구용 설명은 그대로 두되 정상 준비 상태에서 과도한 warning 강조를 줄인다. 실제 분석 조건·알고리즘·model contract는 변경하지 않는다.

## 13. Result

총수 15 Medium → Class 필터 13 → 선택 Class 15 DemiBold·Confidence 22 Medium → 기술 caption 11 순서. 선택 Class의 글자는 neutral이며 Class 색은 필터 점·Overlay에 유지한다. 후보 row는 기존 40 유지, 간격 2→4. 선택 배경·strip·Accessible.selected와 방문 표시를 유지하고 각 행에 새 border box를 만들지 않는다. Raw score·ID·좌표·복사·patch·Export 내용은 그대로다. 합성 2,946개 / BPD 245·TED 1,398·TSD 1,303 상태를 검증한다.

## 14. ROI

분석 영역 / ImageJ ROI 두 Section은 기존 역할 그대로이며 요약 13 Medium, 좌표·페이지 11, 도움말 12로 구분한다. 큰 경계 한 줄만 유지한다. 기록 row 36→40, 간격 2→4, 선택은 배경·focus border로 식별한다. 생성·선택·편집·취소·이름·좌표·꼭짓점·ZIP 저장 동작과 원본 geometry를 유지한다. 세부 설정창은 공통 SurfaceDialog와 32px 입력을 사용한다.

## 15. Loading

TD-07의 opening / first frame / Stack preparing / ready / failed / canceled 조건을 바꾸지 않는다. 첫 정밀 frame 후 중앙 영상은 사용할 수 있고 전체 준비 count는 작은 상태/Viewer Context에 남는다. count와 현재 페이지는 별도다. 같은 합성 스택의 첫 frame 뒤 prepare를 Event로 잠근 상태를 Before/After에 캡처한다. ViewerHeader는 파일 13 Medium, 메타데이터 11 muted이며 mode indicator는 neutral이다. 원본 decode·cache·display pyramid·줌 품질은 이 TD에서 변경하지 않는다.

## 16. StatusBar

높이 28 유지. 기존 상태·배율·원본 좌표/값·해상도·장치 placeholder를 유지하며 정상 완료와 도구의 중복 강조색을 neutral로 줄인다. 데이터가 없는 경우 도구·모델 문자열을 숨긴다. 동작 조건은 바뀌지 않는다. StatusIndicator는 11 Regular, 보조 필드는 12이다.

## 17. Empty / Error

Empty는 기존 설명·열기 진입점, Error는 기존 짧은 문구·상세·재시도 진입점을 유지한다. 새 카드/상시 빨간 box를 만들지 않는다. 오류가 나면 기존 frame을 유지한다. SurfaceDialog는 title 15·body 13·radius 8·padding 12를 제공하고 기존 standardButtons/accept/reject 동작을 상속한다. Qt FileDialog/FolderDialog는 교체하지 않는다. Model/Candidate/ROI 상세창의 긴 문자열과 최소 창 내 배치를 확인했다.

## 18. Before / After

Windows Qt 실제 렌더링, DPR=1.0. 원본 파일은 합성 512×512 RGB JPEG/TIFF 8장이다. 분석은 테스트 어댑터이며 실제 모델 추론 결과가 아니다. Before는 TD-07 exact HEAD의 제품 코드, After는 TD-08 변경 코드로 동일 상태를 재현한다. 각 35장, 총 70장. 실제 XRT 이미지는 포함하지 않는다.

| 상태 | 1100×700 | 1440×900 |
| --- | --- | --- |
| Empty | [Before](../screenshots/visual-td08/before/empty-1100.png) · [After](../screenshots/visual-td08/after/empty-1100.png) | [Before](../screenshots/visual-td08/before/empty-1440.png) · [After](../screenshots/visual-td08/after/empty-1440.png) |
| JPEG | [Before](../screenshots/visual-td08/before/jpeg-1100.png) · [After](../screenshots/visual-td08/after/jpeg-1100.png) | [Before](../screenshots/visual-td08/before/jpeg-1440.png) · [After](../screenshots/visual-td08/after/jpeg-1440.png) |
| Stack preparing | [Before](../screenshots/visual-td08/before/stack-preparing-1100.png) · [After](../screenshots/visual-td08/after/stack-preparing-1100.png) | [Before](../screenshots/visual-td08/before/stack-preparing-1440.png) · [After](../screenshots/visual-td08/after/stack-preparing-1440.png) |
| Viewer | [Before](../screenshots/visual-td08/before/viewer-1100.png) · [After](../screenshots/visual-td08/after/viewer-1100.png) | [Before](../screenshots/visual-td08/before/viewer-1440.png) · [After](../screenshots/visual-td08/after/viewer-1440.png) |
| Analysis ready | [Before](../screenshots/visual-td08/before/analysis-ready-1100.png) · [After](../screenshots/visual-td08/after/analysis-ready-1100.png) | [Before](../screenshots/visual-td08/before/analysis-ready-1440.png) · [After](../screenshots/visual-td08/after/analysis-ready-1440.png) |
| Model detail | [Before](../screenshots/visual-td08/before/model-detail-1100.png) · [After](../screenshots/visual-td08/after/model-detail-1100.png) | [Before](../screenshots/visual-td08/before/model-detail-1440.png) · [After](../screenshots/visual-td08/after/model-detail-1440.png) |
| Analysis running | [Before](../screenshots/visual-td08/before/analysis-running-1100.png) · [After](../screenshots/visual-td08/after/analysis-running-1100.png) | [Before](../screenshots/visual-td08/before/analysis-running-1440.png) · [After](../screenshots/visual-td08/after/analysis-running-1440.png) |
| Result all | [Before](../screenshots/visual-td08/before/result-all-1100.png) · [After](../screenshots/visual-td08/after/result-all-1100.png) | [Before](../screenshots/visual-td08/before/result-all-1440.png) · [After](../screenshots/visual-td08/after/result-all-1440.png) |
| BPD selected | [Before](../screenshots/visual-td08/before/result-bpd-1100.png) · [After](../screenshots/visual-td08/after/result-bpd-1100.png) | [Before](../screenshots/visual-td08/before/result-bpd-1440.png) · [After](../screenshots/visual-td08/after/result-bpd-1440.png) |
| Candidate detail | [Before](../screenshots/visual-td08/before/candidate-detail-1100.png) · [After](../screenshots/visual-td08/after/candidate-detail-1100.png) | [Before](../screenshots/visual-td08/before/candidate-detail-1440.png) · [After](../screenshots/visual-td08/after/candidate-detail-1440.png) |
| ROI none | [Before](../screenshots/visual-td08/before/roi-none-1100.png) · [After](../screenshots/visual-td08/after/roi-none-1100.png) | [Before](../screenshots/visual-td08/before/roi-none-1440.png) · [After](../screenshots/visual-td08/after/roi-none-1440.png) |
| ROI selected | [Before](../screenshots/visual-td08/before/roi-selected-1100.png) · [After](../screenshots/visual-td08/after/roi-selected-1100.png) | [Before](../screenshots/visual-td08/before/roi-selected-1440.png) · [After](../screenshots/visual-td08/after/roi-selected-1440.png) |
| ROI editing | [Before](../screenshots/visual-td08/before/roi-editing-1100.png) · [After](../screenshots/visual-td08/after/roi-editing-1100.png) | [Before](../screenshots/visual-td08/before/roi-editing-1440.png) · [After](../screenshots/visual-td08/after/roi-editing-1440.png) |
| ROI detail | [Before](../screenshots/visual-td08/before/roi-detail-1100.png) · [After](../screenshots/visual-td08/after/roi-detail-1100.png) | [Before](../screenshots/visual-td08/before/roi-detail-1440.png) · [After](../screenshots/visual-td08/after/roi-detail-1440.png) |
| ROI popup | [Before](../screenshots/visual-td08/before/popup-roi-1100.png) · [After](../screenshots/visual-td08/after/popup-roi-1100.png) | [Before](../screenshots/visual-td08/before/popup-roi-1440.png) · [After](../screenshots/visual-td08/after/popup-roi-1440.png) |
| More | [Before](../screenshots/visual-td08/before/more-menu-1100.png) · [After](../screenshots/visual-td08/after/more-menu-1100.png) | [Before](../screenshots/visual-td08/before/more-menu-1440.png) · [After](../screenshots/visual-td08/after/more-menu-1440.png) |
| Error | [Before](../screenshots/visual-td08/before/error-1100.png) · [After](../screenshots/visual-td08/after/error-1100.png) | [Before](../screenshots/visual-td08/before/error-1440.png) · [After](../screenshots/visual-td08/after/error-1440.png) |

1920×1080 Result: [Before](../screenshots/visual-td08/before/result-large-1920.png) · [After](../screenshots/visual-td08/after/result-large-1920.png). ROI none는 ImageJ 기록이 없는 상태이며 별도 분석 영역은 존재할 수 있다.

## 19. Responsive

1100×700·1440×900·1920×1080 논리 크기에서 Toolbar 7 targets, Context title, Analysis 선택/실행, Result 필터/상세/저장, ROI 선택/편집/상세의 창 내 접근을 검사한다. 1100/1440의 ROI·More popup은 keyboard Down/Escape 및 content bounds를 검사한다. 1100의 Model/Candidate/ROI 상세는 실제 렌더링을 확인했다. 긴 Unicode 파일명은 elide되어도 전체 text 및 원본 metadata를 유지한다.

| 창 크기 | 일반 Viewer 외곽 Before → After | Result Viewer 외곽 Before → After |
| --- | --- | --- |
| 1100×700 | 634×602 → 634×602 | 536×602 → 536×602 |
| 1440×900 | 974×802 → 974×802 | 876×802 → 876×802 |
| 1920×1080 | 1454×982 → 1454×982 (구조 검사) | 1356×982 → 1356×982 (캡처 비교) |

일반 우측 282·Result 380·Navigation 184, Header 52·Status 28 유지. 표는 Header 포함 ImageViewer item 크기이며 영상 자체의 원본 종횡비나 픽셀 해상도는 달라지지 않는다. 오류 안내는 입력 높이 증가로 내부 영상 높이에 약 4px 영향을 줄 수 있다.

## 20. DPI

Windows 캡처는 DPR 1.0(100%). 125/150%는 별도 Qt 프로세스에 `QT_SCALE_FACTOR=1.25/1.5`를 설정하여 실제 DPR와 세 창 크기의 논리 bounds/hit targets를 확인한다. 전체 suite 안의 두 DPI 테스트는 각각 세 shell 검사를 offscreen에서 실행한다. 별도 Windows Qt 플랫폼에서도 125% **3 passed**(3.93초), 150% **3 passed**(4.37초)다. 이는 같은 shell 검사의 반복으로 고유 262개에 중복 가산하지 않는다. OS 디스플레이 설정을 직접 변경한 사용자 세션·복수 모니터·물리 화면 밖의 전체 표시 여부는 검증하지 않는다. 큰 논리 창은 높은 DPR에서 모니터보다 클 수 있으므로 이를 실제 monitor fit으로 해석하지 않는다.

## 21. Visual metrics

정적 조사 기준은 UI 파일의 `border.color` 선언 수다. 전체 64→67 QML, border 선언 **24→16 (-33.3%)**, 이를 가진 파일 **16→13**. 공통 input/Dialog 3개 및 focus border 추가를 포함한 값이다. font 10px 선언 14→0, literal radius는 상태 점 2 하나 외에는 공통 4/6/8 토큰을 사용한다.

| 1100 대표 화면 | 주요 Control/Panel outline Before → After | Primary CTA Before → After |
| --- | --- | --- |
| Empty | 12 → 1 | 0 → 0 |
| JPEG | 7 → 1 | 0 → 0 |
| Analysis ready | 8 → 1 | 1 → 1 |
| Result all | 9 → 0 | 0 → 0 |
| BPD selected | 9 → 1 | 0 → 0 |
| ROI selected / editing | 8 / 7 → 1 / 1 | 0 → 0 |
| Viewer / Stack preparing | 9 / 9 → 0 / 0 | 0 → 0 |
| Error | 12 → 1 | 1 → 1 (기존 ROI 동작) |

이 runtime 수치는 AppButton 배경·AppComboBox 배경·AppCheckBox indicator 및 변경 전 명시적 Panel/MenuBar border만 대상으로 scene-visible 상태를 조사한 대표 outline 수다. 이미지 Overlay·Qt 기본 Form·Dialog/Popup 외곽·가려진 부분은 집계하지 않는다. 모든 화면 픽셀의 테두리 수 또는 접근성 완전 검증을 의미하지 않는다. 임의 Rectangle의 lazy pen을 만들며 집계하지 않는다. 주요 Context의 Card-in-card 0→0, Viewer 외곽과 panel width는 동일 scene 비교에서 같다.

Scroll 영향(1100): Analysis 기본 결정·Ready·Run은 여전히 스크롤 없이 보이고 Advanced의 독립 스크롤은 유지한다. Result all list viewport 211→208(-3), BPD 선택 149→142(-7). row 40 유지·gap 2→4로 100행 내용 높이 4198→4396(+4.7%). ROI selected 109→103(-6), editing 109→87(-22), ImageJ 기록 없음 132→110(-22). row 36→40·gap 2→4로 100행 내용 높이 3798→4396(+15.8%). 글자와 입력 높이를 확보하면서 목록 스크롤은 늘었으며 이를 감소했다고 주장하지 않는다. ROI 편집에서도 목록 ≥60과 주요 액션 접근을 검사한다. Right Panel 폭이나 Viewer 공간으로 보상하지 않았다.

## 22. Regression

전체 회귀 **258 passed / 4 skipped**(213.46초). 기존 237개에 `test_visual_density.py`의 21개를 추가했다. 4 skip은 offscreen에서 native 창을 직접 검증하지 못하는 항목이며 별도 Windows AWT/Swing/ImageJ 실행에서 **4 passed**(54.83초), 총 고유 검증 **262개**다. TD-07 loading 15개도 별도로 통과했다.

새 테스트는 세 창 크기에서 실제 QML geometry·Analysis 준비/실행·2,946개 Result와 원본 result identity·ROI 생성/편집/geometry identity·popup 키보드/focus·hover/pressed/checked/disabled·Unicode 파일명·제한된 contrast·DPR를 검사한다. 캡처의 QML warning은 Before/After 모두 0. Ruff·compileall·wheel build 및 wheel 내 QML 67개 포함 검사가 통과했다. 테스트용 캡처/측정 도구와 임시 TIFF·JPEG·Java 캐시는 ignored artifacts 아래에 두고 Git에 넣지 않는다.

Production Python/backend/계약은 변경하지 않는다. 변경 전 exact HEAD와 변경 후 source diff를 검사하여 메뉴 Action·단축키·Context policy·Flow·ROI geometry·TIFF/JPEG/cache·ImageJ/Fiji·Export·Score·모델 경계를 보존한다. 공통 Dialog는 Qt 의미를 상속하고 네이티브 FileDialog/FolderDialog는 유지한다. native 및 CI 최종 결과는 PR에 기록한다.

검증 재현(가상환경과 Java/Fiji 라이브러리 설치 후):

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q src
$env:QT_QPA_PLATFORM='offscreen'
$env:SIC_XRT_FIJI_HOME='artifacts/fiji-runtime'
.\.venv\Scripts\python.exe -m pytest -q
$env:QT_QPA_PLATFORM='windows'
$env:QSG_RENDER_LOOP='basic'
.\.venv\Scripts\python.exe -m pytest -q tests/test_stack_compatibility.py -k gui_plugin
$env:QT_SCALE_FACTOR='1.25' # 1.5에서도 같은 검사
.\.venv\Scripts\python.exe -m pytest -q tests/test_visual_density.py -k test_shell_geometry
Remove-Item Env:QT_SCALE_FACTOR
```

## 23. 남은 문제

Windows COM `0x80010108` native dialog/engine teardown 진단은 별도다. 이 TD의 synthetic GUI/native 검사 성공으로 해당 문제가 해결됐다고 주장하지 않는다. 실제 대형 XRT·실제 모델 재검증·실제 사용자 이해도/첫 행동 시간 측정은 미수행이다. native 파일 선택 창을 마우스로 직접 열기/취소한 검증, 모든 플러그인 창의 테마 통일, screen reader 전체 검증도 별도다. 실제 원본 데이터·모델·sources/·다른 저장소는 수정하지 않았다. 기존 AGENTS.md의 작업 전 whitespace 변경은 커밋에서 제외한다.
