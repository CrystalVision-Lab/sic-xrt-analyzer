# XRT-UX-TD-04 — Single-Screen Analysis Flow

Issue #62. 시작 기준: [TD-03](XRT-UX-TD-03-CONTEXT.md), PR #61 / `refactor/60-context-panel-workflow` / `26bd62d628c9e232b56227ba3071b997f85c3809`. 작업 브랜치: `refactor/62-analysis-flow`.

## 1. 기존 Flow와 조사 결과

TD-03은 IMAGE → ANALYSIS → RESULT 전환과 고정 실행 영역을 이미 제공한다. 다만 설정 Scroll 안에서 모델 선택, 이름/버전/장치, 연결 상태, 후보 방식, CSV, 입력 원본, ROI 좌표, 범위 선택을 순서대로 읽어야 했다. 최소 창에서 범위가 Scroll 아래로 내려가고, 실행 영역에는 분석 가능 이유와 이미지/ROI/분석 상태가 반복되었다.

| 실제 구현 | 조사 결과 |
| --- | --- |
| 모델 | ResearchController가 환경 변수 `SIC_XRT_MODEL_BUNDLE` → 저장한 `researchModelBundle` → 로컬 bundle 순서로 찾는다. 성공한 폴더 선택은 QSettings에 저장한다. 매 분석마다 선택할 필요가 없다. |
| 로컬 bundle | 실행 위치의 `models/research`, `artifacts/models/research`에서 manifest.json을 찾는다. 모델 파일은 Git에 포함하지 않는다. |
| 범위 | 현재 연구 adapter는 FULL_IMAGE와 ROI(사각형)를 지원한다. UiState.analysisScope의 TD-03 초기값은 빈 문자열이므로 별도 선택이 필요했다. |
| 기본 입력 | Original TIFF/JPEG의 원본 픽셀. 현재 연구 모델 계약은 RGB uint8이며 표시용 밝기/배율과 독립적이다. |
| Run | Main.runAction.enabled는 UiState.canAnalyze. 실제 backend 입력 계약 검증은 기존 pipeline/adapter에 남는다. |
| Cancel | 기존 cancelAction은 즉시 CANCELED로 표시하고 generation을 변경하여 늦은 결과를 버린다. 별도 cancelling/progress API는 없다. |
| 영역 변경 | 기존 Viewer의 R 도구는 실행 중에도 이미 선택돼 있으면 드래그가 가능했다. 새 UI에서 분석용 사각형 변경만 잠근다. ImageJ 기록 편집과 데이터를 합치지 않는다. |

모델 이름/버전/hash/device는 실행에 필요한 사용자 선택 값이 아니다. 모델 상태와 변경 진입점을 기본 화면에 남기고 기술 정보는 기존 Model Info Dialog로 모았다. Python backend/model loading/inference 및 입력 계약은 변경하지 않았다.

## 2. 변경 후 Flow

```text
이미지 열기 → IMAGE
                └ 이 이미지 분석 → ANALYSIS (실행하지 않음)
                                      ├ 모델 상태 / 분석 범위 / 입력
                                      ├ 필요 시 지정 영역 → 기존 R Action → Viewer 드래그
                                      │                   └ ANALYSIS 유지
                                      └ 준비 상태 → Run
                                                   ├ RUNNING → Cancel → ANALYSIS
                                                   ├ FAILED → ANALYSIS → 다시 분석
                                                   └ COMPLETED → RESULT (후보 0개 포함)
```

Wizard·다음 버튼·실행 확인·완료 확인 Modal은 없다. 모델이 준비돼 있고 FULL_IMAGE가 지원되는 첫 기본 분석은 Analysis 진입 후 Run 한 번이다. ImageContext의 작은 연결 버튼은 준비 화면을 열 뿐 자동 실행하지 않는다. Toolbar와 Viewer에 분석 CTA를 추가하지 않았다.

## 3. 정보 위계와 화면 구조

| 위계 | 표시 |
| --- | --- |
| Primary | 모델 준비 여부와 연결/변경, 분석 범위, 지정 영역 없음/크기와 지정 Action, 준비/진행/오류 요약, Run/Cancel |
| Secondary | 모델 이름, Original TIFF/JPEG, 현재 원본 페이지 크기, 지정 영역 좌표·크기, 연구용 후보 주의 문구 |
| Advanced | 모델 version/hash/device/폴더와 안내는 모델 상세 Dialog; 파일 경로/dtype/페이지는 입력 상세 Dialog; 후보 방식·CSV는 고급 설정 한 곳 |

모델·범위·입력은 고정 기본 영역, 후보 방식·CSV는 펼칠 수 있는 Scroll 영역, 준비 이유와 Run/Cancel은 고정 하단이다. 전체 이미지에서는 ROI 네 좌표와 지정 버튼을 숨긴다. 지정 영역일 때만 현재 크기/좌표와 기존 R Action 버튼을 표시한다. 카드·탭·중첩 아코디언을 추가하지 않았다.

사용자 상태는 **분석 준비 필요 / 분석 준비 완료 / 분석 중 / 분석 완료 / 분석 취소됨 / 분석 실패**, 모델 상태는 **모델 준비 중 / 모델 준비됨 / 모델 연결 필요**로 구분한다. 실제 backend phase는 그대로 사용한다.

## 4. Ready 조건과 Source of Truth

AnalysisFlowState.ready는 `UiState.canAnalyze`를 직접 읽는다. 컴포넌트마다 새 Run 조건을 계산하지 않는다. 기존 canAnalyze 조건은 그대로다.

```text
hasLoadedImage
&& analysis.sourceReady
&& modelAvailable
&& !analysisRunning
&& !loading
&& !pageLoading
&& supportedScopes에 analysisScope 포함
&& (FULL_IMAGE || (ROI && hasRoi && roiWidth > 0 && roiHeight > 0))
```

AnalysisFlowState.blockers는 같은 조건에서 부족한 이유들을 표시한다: 원본 없음/미준비, 모델 연결/준비 중, 파일/페이지 준비 중, 범위 미선택/미지원, 지정 영역 없음/0크기. 실행 중에는 설정 잠금과 취소 가능 안내를 표시한다. disabled 버튼만으로 원인을 숨기지 않는다.

UiState의 초기 범위는 명시적인 `FULL_IMAGE`로 바꿨다. 화면 Combo에도 전체 이미지가 표시되고 Run은 해당 값을 기존 requestAnalysis에 전달한다. backend가 ROI 유무로 범위를 추측하게 만들지 않았다. Combo 선택은 adapter의 실제 supportedScopes로 구성하며, FULL_IMAGE 미지원 모델에서는 기존 Run 조건이 실행을 막고 이유를 표시한다. 사용자가 고른 ROI 범위는 취소·실패·새 파일에서도 자동으로 전체 이미지로 바꾸지 않는다.

표시 준비 상태는 기존 UI Run gate의 상태다. dtype/channel, 원본 파일 identity, CSV 유효성 등 backend 계약 검증을 대신하지 않는다. 특히 현재 연구 모델은 RGB uint8이며 16-bit 회색조에 암묵적 변환을 추가하지 않았다.

## 5. Run / Cancel / Error lifecycle

| 단계 | UI / Action / Context |
| --- | --- |
| Idle / Not Ready | ANALYSIS에서 부족 조건, 공유 Run 비활성 |
| Ready | 준비 완료, Run Primary. 전체 이미지에 ROI를 요구하지 않음 |
| Running | indeterminate BusyIndicator, Run 비활성, Cancel 표시. 모델·범위·후보 방식/CSV·분석 영역 변경 잠금 |
| Complete | TD-03 정책으로 RESULT. 0개 Empty State 유지. 중간 확인 창 없음 |
| Cancelled | ANALYSIS, 기존 scope/후보 방식/영역 유지, 조건 충족 시 공유 Run을 “다시 분석”으로 표시 |
| Error | ANALYSIS, 기존 bridge의 사용자용 errorMessage와 부족 조건, 조건 충족 시 “다시 분석” |

실행 중 이미 활성화된 R 드래그, R Action, 영역 초기화, 가져온 도형의 외접 사각형을 분석 영역으로 지정하는 버튼을 잠근다. 좌표 계산·도형 알고리즘·렌더링은 그대로다. UI 접근만 제한한다. 코드/외부 호출로 상태를 바꾸는 경우의 backend snapshot/generation 검증도 기존대로 유지한다.

Pan/Zoom/Fit와 다른 Context의 수동 탐색은 가능하다. 새 파일·닫기·스택 페이지 이동은 기존 source/generation 무효화 정책을 유지하며 이전 분석 응답을 새 입력에 적용하지 않는다. 입력은 요약/상세에서 읽기 전용으로 표시한다. ImageJ 기록은 분석 범위로 자동 선택하지 않고 외접 사각형 지정 명령에서만 기존 의미로 연결한다.

에러에는 traceback/내부 detail 대신 기존 bridge의 사용자용 메시지를 사용한다. 원래 Python 진단 로그는 유지한다. 모델/CSV의 기존 ResearchController 안내는 상세/고급 설정에서 접근한다. 가짜 진행률·ETA·새 상태 머신은 없다.

## 6. Context 이동과 클릭 수

측정 전제: 이미지가 이미 IMAGE에 열렸고 모델이 준비된 최초 분석, 마우스 사용, 고급 설정/상세 열기 제외. 드래그는 클릭과 별도 제스처로 센다. 반복 실행 시 기존 선택을 유지하므로 클릭 수는 달라질 수 있다.

| 흐름 | TD-03 Before | TD-04 After |
| --- | --- | --- |
| Context 이동 | IMAGE → ANALYSIS → RESULT, 2회 | 동일 2회. TD-03에서도 도구만으로 ROI Context를 강제하지 않았음 |
| 전체 이미지, IMAGE부터 | Context 메뉴/분석 2 + 범위 메뉴/전체 2 + Run 1 = **5 클릭** | 이 이미지 분석 1 + 기본 범위 확인 + Run 1 = **2 클릭** |
| 전체 이미지, ANALYSIS부터 | 범위 선택 2 + Run 1 = **3 클릭** | 기본 FULL_IMAGE → **Run 1 클릭** |
| 지정 영역, IMAGE부터 | Context 2 + 범위 2 + Toolbar ROI/R 2 + Run 1 = **7 클릭 + 드래그** | 진입 1 + 범위 2 + 영역 지정 1 + Run 1 = **5 클릭 + 드래그** |
| 지정 영역, ANALYSIS부터 | **5 클릭 + 드래그** | **4 클릭 + 드래그** |

R 단축키를 쓰면 도구 선택 클릭이 줄어든다. OS 파일/모델 폴더 선택은 위 준비된 상태의 클릭 수에 포함하지 않았다. 실제 사용자 3초 이해도 연구는 수행하지 않았으며, 기본 화면에 가능 여부·범위·Run을 동시에 표시하는 것으로 목표를 구현했다.

## 7. Responsive / Accessibility / Focus

일반 패널 282px/결과 380px, Toolbar 7버튼/40px, 최소 중앙 Viewer 536px를 유지한다. 1100×700과 1440×900에서 모델 상태·분석 범위·준비 요약·Run/Cancel은 기본 Scroll 없이 접근한다. 지정 영역과 CSV 고급 설정을 함께 열어도 하단은 유지하고 세부 CSV 컨트롤만 Scroll한다. 긴 모델 이름은 elide, path/hash는 상세 Dialog다.

주요 모델/범위/영역/실행/취소/고급/입력 컨트롤에 Accessible.name과 필요한 description을 제공한다. 상태는 색과 텍스트로 표시한다. 영역 지정은 공유 R Action과 Qt.callLater Viewer.focusView를 사용한다. H/R/Zoom/Stack 단축키 및 TD-03 메뉴 포커스 복구를 유지한다.

Windows 실창 QTest 캡처는 **합성 512×512 RGB 3페이지 TIFF와 테스트 adapter**다. 실제 XRT 데이터·모델 정확도 자료가 아니다.

| 화면 | 확인 |
| --- | --- |
| [이미지 없음](../screenshots/analysis-td04/no-image-1100.png) / [모델 연결 필요](../screenshots/analysis-td04/model-required-1100.png) | 부족 이유·비활성 Run |
| [준비 1100×700](../screenshots/analysis-td04/ready-1100.png) / [1440×900](../screenshots/analysis-td04/ready-1440.png) | 기본 전체 범위·Primary 접근 |
| [영역 없음](../screenshots/analysis-td04/area-required-1100.png) / [실제 드래그 후](../screenshots/analysis-td04/area-ready-1100.png) | 지정 Action·동일 Context·원본 영역 |
| [고급 설정](../screenshots/analysis-td04/advanced-1100.png) / [CSV](../screenshots/analysis-td04/csv-1100.png) | 하나의 펼침, 선택 방식 요약 유지 |
| [실행 중](../screenshots/analysis-td04/running-1100.png) | 설정 잠금·Cancel·실제 불확정 상태 |
| [취소](../screenshots/analysis-td04/cancelled-1100.png) / [오류](../screenshots/analysis-td04/error-1100.png) | 설정 유지·다시 분석 |
| [후보 0개](../screenshots/analysis-td04/zero-result-1100.png) | 기존 RESULT 연결 |

## 8. 검증

- 전체 회귀: **185 passed, 4 skipped, 151.16초**. skip은 별도 native 4개다.
- 신규 분석 Flow **17개**: 실제 QML/Action/마우스 드래그와 테스트 adapter로 검증.
- Ruff / compileall / wheel build PASS. wheel에 QML **61개** 포함, sources/·실제 원본·모델·artifacts 제외 확인.
- Windows 실창 캡처 **12장** 검토, QML 경고 0개. 지정 영역 + CSV + RUNNING 최소 창에서 Primary와 Run/Cancel 경계 확인.
- Windows AWT/Swing 별도 **4 passed, 55.74초**. 전체 검사와 합쳐 **189개**다. 테스트 전용 JVM `-Xms32m -Xmx512m`을 사용했으며 제품 설정은 그대로다.
- 마지막 화면 조정 후 신규 Flow/TD-03 Context/Smoke **29 passed, 26.66초**, Ruff·compileall 재확인. wheel의 QML 61개 포함도 확인했다.

| 요구 Case | 검사 |
| --- | --- |
| 1 이미지 없음 | 분석 화면 접근, 이미지/모델 복수 부족 이유·Run 비활성 |
| 2 이미지+모델 | IMAGE 연결 버튼은 준비 진입만, 기본 범위 Run 1회 |
| 3 모델 없음 | 모델 연결 버튼과 폴더 선택 진입/취소, Run 비활성 |
| 4 전체 이미지 | ROI 없음에도 FULL_IMAGE request, 확인 Modal 없음 |
| 5 영역 없음 | ROI 선택 후 부족 이유·공유 R Action |
| 6 영역 생성 | 실제 Viewer 드래그, 동일 ANALYSIS, 표시 좌표와 request ROI 일치 |
| 7 ImageJ 기록 | 기록이 있어도 분석 영역 미지정이면 Run 비활성 |
| 8 Running | 중복 Run 방지, 모델/범위/방식/영역 잠금, Pan/Zoom/Fit 가능 |
| 9 Cancel | scope/방식/영역 유지, ANALYSIS, 공유 Run 재실행 |
| 10 Error | 사용자용 메시지·내부 detail 비노출, ANALYSIS, 재실행 |
| 11 후보 있음 | RESULT/list, 기존 후보 처리 |
| 12 후보 0개 | RESULT/zero |
| 13 새 이미지 | IMAGE, 결과/선택/영역 혼입 없음, 기존 ROI 범위면 재지정 안내 |
| 14 최소 창 | 핵심 설정과 Run 경계, 실제 native CSV+RUNNING 캡처 |

기존 desktop/model input UI 검사 두 곳은 FULL_IMAGE 기본 선택 및 “모델 준비됨” 문구 기대만 갱신했다. 입력 원본·좌표·결과 mismatch·Export 검사 내용은 유지했다. 정적 타입 검사 도구는 별도 구성되어 있지 않다.

## 9. 보존과 후속 작업

Python backend/model loading/모델·threshold·preprocessing·inference·BPD/TED/TSD/Score/후보·좌표/ROI 계산/디코딩·스택·TIFF cache·렌더링/저장·Export/ImageJ·Fiji/Macro·Plugin 및 외부 계약/스키마/모델 해시는 변경하지 않았다. sources/와 실제 원본은 수정하지 않았다. 사용자 AGENTS.md 변경은 커밋에서 제외한다.

이번 단계는 합성 입력과 기존 회귀 검사 중심이다. 실제 대형 XRT 4개·실제 모델 재추론 정확도·사람이 OS 파일 선택 창을 조작하는 검증은 재수행하지 않았다. 기존 native 검사에는 고정 대기 시간 민감성이 있으며 테스트 JVM 한도를 제품에 반영하지 않는다. CSV 고급 설정은 작은 창에서 Scroll이 필요하고 실제 progress API는 없다.

| 후속 TD | 범위 |
| --- | --- |
| TD-05 | Result 후보 검토·카드·Legend·필터 |
| TD-06 | ROI 생성·완료·취소·편집 UX |
| TD-07 | TIFF loading UX |
| TD-08 | 전체 Visual Density |
