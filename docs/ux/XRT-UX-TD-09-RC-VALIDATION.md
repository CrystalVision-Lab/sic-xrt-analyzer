# XRT-UX-TD-09 — 최종 E2E 통합 검증과 RC 판정

Issue [#72](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/72). 시작점은 TD-08 PR #71의 `refactor/70-visual-density`, exact HEAD `b53dd26bd00f095e269adf07227973439543b4b0`. 작업 브랜치는 `test/72-ux-integration-rc`다. 검증 도구·테스트·문서만 추가한다. Production 코드, 외부 계약, 원본, 모델은 변경하지 않으며 기존 사용자 `AGENTS.md` 수정은 제외한다.

**Status: FAIL / RC Verdict: NOT RC READY.** Windows 파일 선택창 반복 열기·취소에서 프로세스 접근 위반 종료가 재현됐다. TD-09의 crash 등급 기준에 따라 P0 blocker이며 원인과 안전한 수정은 아직 확인되지 않았다.

## 1. 검증 환경

| 항목 | 환경 |
| --- | --- |
| OS | Windows 11 25H2, build 10.0.26200 |
| CPU | Intel Core i7-13700, 논리 CPU 24 |
| RAM | 34,088,583,168 bytes, 약 31.75 GiB |
| GPU / 추론 | ONNX CPU. GPU 장치 정보는 권한 제한으로 미확인 |
| Python / Qt | Python 3.13.7, PySide6/Qt 6.11.2 |
| Java | JDK 24.0.2 |
| Fiji | ImageJ2 2.18.0, imagej-common 2.1.1, imagej-legacy 3.0.0, SciJava-common 2.101.0 |
| Display / DPI | 1920×1080, logical DPI 96, DPR 1.0. Qt 창 크기 1100×700·1440×900·1920×1080 |
| Storage | OneDrive 아래 로컬에서 읽을 수 있는 원본. SSD/HDD는 권한 제한으로 미확인 |

Java 기본 heap 상한은 기존 설정 `-Xmx3g`다. 테스트용 `_JAVA_OPTIONS=-Xmx512m`을 실제 자료 검사에도 적용한 초기 시험은 Fiji OOM으로 중단되어 최종 근거에서 제외한다. 제한을 제거한 기본 설정으로 TIFF 4개 모두 통과했다. OS DPI를 바꾸지 않았으며 125/150%는 기존 TD-08 Qt DPR 회귀 검사를 유지한다. 논리 창 크기가 물리 모니터에 모두 들어간다는 의미는 아니다.

## 2. TD-01~08 통합 상태

시작 HEAD는 IA·Toolbar·Context·Analysis·Result·ROI·progressive TIFF loading·visual density를 포함한다. 초기 전체 검사 후 실제 자료 검사를 시작했다. 새 연속 세션 검사는 1100/1440에서 각 3회 Open→Analyze→Result→filter→export→ROI 분석→다른 파일 Open을 수행한다. 합성 어댑터를 실제 모델 검증으로 집계하지 않는다.

## 3. PR chain

| TD | PR | Base | Head | CI run | Mergeable | Review |
| --- | --- | --- | --- | --- | --- | --- |
| 01 | #56 | feat/52-candidate-roi | refactor/55-ui-information-architecture | 37448160374 | clean | PENDING |
| 02 | #59 | refactor/55-ui-information-architecture | refactor/58-toolbar-simplification | 37460753747 | clean | PENDING |
| 03 | #61 | refactor/58-toolbar-simplification | refactor/60-context-panel-workflow | 37466740073 | clean | PENDING |
| 04 | #63 | refactor/60-context-panel-workflow | refactor/62-analysis-flow | 37470961153 | clean | PENDING |
| 05 | #65 | refactor/62-analysis-flow | refactor/64-result-ux | 37475188402 | clean | PENDING |
| 06 | #67 | refactor/64-result-ux | refactor/66-roi-ux | 37481798962 | clean | PENDING |
| 07 | #69 | refactor/66-roi-ux | refactor/68-tiff-loading-ux | 37554175119 | clean | PENDING |
| 08 | #71 | refactor/68-tiff-loading-ux | refactor/70-visual-density | 37560097893 | clean | PENDING |

조사 당시 모두 open/draft, CI success, reviews/review threads 없음. Mergeable은 사람의 승인을 뜻하지 않는다. 선행 PR #53 (`feat/52-candidate-roi`, base `feat/50-result-explorer`)도 open/draft다. Merge/rebase/retarget 하지 않는다.

## 4. 자동 검사

시작 HEAD의 Ruff / compileall / wheel PASS. wheel에 QML 67개 포함, 실데이터·모델 없음.

| 검사 | 결과 | 근거/조건 |
| --- | --- | --- |
| 시작 HEAD 전체 최초 | 257 passed / 1 failed / 4 skipped, 206.04s | 디스크 여유 약250 MiB에서 대형 합성 TIFF 준비 실패 |
| 같은 HEAD, 생성 scratch만 정리 후 | 258 passed / 4 skipped, 203.45s | 원본/모델 삭제 없이 여유 약4.72 GiB 확보 |
| Windows native 최초, 전체 suite와 동시 실행 | 2 passed / 2 failed, 50.90s | host 이동 후 위치 기대50 / 실제30 |
| Windows native 직렬 재검사 | 4 passed, 54.75s | 대기 늘림·테스트 삭제·production 수정 없음 |
| 새 연속 세션 검사 | 3 passed, 35.56s | 합성 RGB 및 합성 어댑터 |

초기 실패를 숨기지 않는다. 디스크 부족은 환경 전제 문제, native 위치 검사의 부하 의존성은 원인 미확정이다. 신규 3개를 포함한 회귀 검사 수는 261개와 native 4개, 고유 검사 265개다. **최종 exact HEAD의 전체 suite·native 직렬 검사·CI 완료 결과와 소요 시간은 연결 PR의 최종 검증 기록으로 확인한다.** 문서에 자기 자신의 commit SHA를 내장하지 않는다.

## 5. 실제 XRT

원본은 읽기 전용. 개인 경로, 실이미지, 모델, 가공 결과, native dump는 ignored artifacts에만 보관한다.

| 파일 | bytes | 해상도 | 페이지 | dtype |
| --- | ---: | --- | ---: | --- |
| N119_220_Section_stack_flipped.tif | 2,923,950,451 | 3072×3012 | 158 | uint16, 단일 채널 |
| No107_SectionTopo-afterAnnealing .tif | 2,639,313,678 | 2922×2895 | 156 | uint16, 단일 채널 |
| No107_SectionTopo-beforeAnnealing.tif | 2,639,313,682 | 2922×2895 | 156 | uint16, 단일 채널 |
| No22_220_Section_stack_flipped.tif | 2,521,404,229 | 2944×2745 | 156 | uint16, 단일 채널 |

모두 첫·중간·마지막의 원본 픽셀/표시 범위/정밀 확대/Fiji ROI/재열기/캐시 정리 PASS. 전체 SHA-256 전후 동일:

| 파일 축약 | SHA-256 (검사 전 = 후) |
| --- | --- |
| N119 | `434b86d180d1e7238540cde1a81a099670e145dd40ef7a114e75bae7e9b387bb` |
| No107 after | `81d5c2a0f795f90a2db1ddee3debf3f570b0e2c8223ab76384d31f21bfcefeb7` |
| No107 before | `5d3aa50d204e118ca42ec7b54ff3444bde7406e9a548421042cd01e4272f47f4` |
| No22 | `e28cf99b4d482f24628cb87f9122b5ae505d73c9fdc5a8bd8b11380fc25542dd` |

## 6. 실제 모델

ID `spatial64-c4-24368b8f6613`, 계약 `frozen_xrt_patch_classifier` v1, ONNX SHA-256 `24368b8f6613cba5251c0bd8e63d7ddec726d6343a35ed878e823a0091369694`, CPU. 모델은 **uint8 RGB 3채널** 전용이다. uint16 단일 채널을 묵시적으로 변환하지 않았다.

실 RGB XRT `After annealing_1.jpg`: 106,125,836 bytes, 12349×12273, uint8 RGB. 전체 inference **8.232s**, 후보 **2946**, 지정 영역 **791**. RGB inference·취소·재실행 PASS. SHA-256 전후 및 복사본 동일: `c864ce2410e940ee0e5c11faf4bec2f38fa66cf1f8d5ecc4cc15bfa5b60f1c47`.

Ground truth가 없어 정확도·모델 승인·현장 유효성을 평가하지 않았다. 후보를 확정 결함으로 해석하지 않는다. Manifest의 개인 학습 경로는 공개하지 않는다.

## 7. E2E Flow

`tools/validate_rc_session.py`는 실제 Main.qml/FileBridge를 Windows Qt로 열고 QTest로 toolbar/context/result/ROI를 조작한다. Open/모델 선택은 native accepted와 같은 기존 slot 호출이다. OS picker에서 사람이 선택했다는 증거는 아니다.

| 단계 | 결과 / 근거 |
| --- | --- |
| Open | TIFF 4개·실제 JPG 로딩 PASS. native 실선택 미검증 |
| Viewer | Pan/Zoom/Fit·원본 픽셀·대비·Stack slider/next/previous PASS |
| Context | Image → Analysis → Result → ROI 전환 PASS |
| Analyze | RGB full/ROI PASS. uint16 계약 거절, 분석 완료 불가 |
| Result | filter·overlay·candidate 이동·JSON/CSV PASS |
| ROI | 4종 생성·Point 이동·ZIP 재읽기·페이지 태그 PASS, 정밀도 제약 §10 |
| Stack | 모든 페이지 앞/뒤 요청, 빠른 마지막 요청 우선 PASS |
| ImageJ/Fiji | 실제 TIFF 4개 ROI 계산·실제 현재 stack 페이지 macro PASS |
| Save | JPG 복사 SHA·결과 전체 내용·ROI 의미 비교 PASS. native Save 확인 미검증 |
| 새 파일 | 결과·ROI·고급 Stack 표시 초기화 PASS |
| 종료 | 실제 세션 OS 프로세스 exit 0, 새 engine 빈 상태 PASS |

최종 실제 세션은 전체 프로세스 97.926s, exit 0, QML warnings 0. Analysis Ready·Result 1100·ROI 1100 캡처를 직접 검토했다. Result 1440/1920도 캡처와 컨트롤 경계를 검사했으나 모든 화면의 사람 검토를 주장하지 않는다. 영상은 ignored artifacts에만 보관한다.

## 8. 분석

실 JPG 전체 PASS. 지정 영역 x=1003, y=1011, width=1495, height=1495; 모델 입력 `1495×1495×3`, ROI 후보 791. 결과 좌표가 원본 좌표의 지정 영역 안에 있는지 확인했다.

Cancel → CANCELED/no result → 재실행 COMPLETED PASS. 잘못된 모델 경로 → 정상 모델 로드 복구 PASS. 합성 회귀에서는 잘못된 파일 Open 후 결과 무효화와 정상 재개를 확인했다.

실제 No22 uint16 단일 채널에서 Run이 활성화되지만 `FAILED / INVALID_INPUT`으로 거절된다. 원본 불변과 입력 계약 검사는 작동한다. 16-bit 분석 flow는 미완료이며 준비 상태에서 계약을 미리 안내할 필요가 있다. 모델/입력 계약은 변경하지 않았다.

## 9. Result

Total **2946 / BPD 245 / TED 1398 / TSD 1303**. 각 filter count와 Overlay count 일치, 후보 next/next/previous·thumbnail 이동 PASS. backend result identity 유지. JSON 두 번 export의 전체 parse 내용 동일, CSV 2946행.

Filter 선택과 후보 클릭 3회를 포함하는 검증 cycle median **1229.192ms**, max **3375.335ms**. QTest 대기·thumbnail 포함이며 순수 filter latency/FPS가 아니다. 기존 후보 제한과 incomplete patch 제외 설정을 유지했다.

## 10. ROI

Analysis Area와 ImageJ ROI는 별도 상태다. 실제 TIFF에서 Rectangle/Polygon/Freehand/Point 생성, Point 10px 이동, ZIP export/import, 이름·종류·색상·페이지 유지 PASS. 태그는 모두 내부 page_index 0(표시 페이지 1). 미완료 Polygon은 Esc/Pan/page 전환 시 사라지고 확정 ROI 4개가 유지된다.

기존 ImageJ 직렬화 정밀도로 비교했다. 원본 float64 좌표의 bitwise round-trip을 주장하지 않는다.

| 도구 | 원본 좌표 대비 최대 차이 px | 저장 형식 |
| --- | ---: | --- |
| Rectangle | 0.668539325842687 | integer enclosing bounds, closing vertex/winding 차이 |
| Polygon | 0.0000137157653626 | float32 저장 값과 정확히 일치 |
| Freehand | 0.0000548630619051 | float32 저장 값과 정확히 일치 |
| Point | 0.0000274315307252 | float32 저장 값과 정확히 일치 |

Rectangle 재읽기 bounds가 저장 integer bounds와 같고 원본 대비 오차 <1px. 이번 TD에서 직렬화를 바꾸지 않았다.

## 11. TIFF / Stack

N119 첫/중간/마지막 1/80/158, 나머지 1/79/156. tifffile 원본 전체 페이지 배열 비교 PASS. 대비 조절 시 raw uint16 불변, PreparedView fit·100/200/400%·Pan 표시 값 일치 PASS. 모든 페이지 앞/뒤 요청을 검사했다.

첫 페이지가 먼저 보이고 Stack 준비 상태를 안내한다. 완료 뒤 연속 탐색, 빠른 요청의 마지막 페이지 우선, 파일 변경 후 이전 mapping/temp cache 해제 PASS. ImageJ frames는 공간 Z·촬영 방향·실제 간격으로 확정하지 않는다.

## 12. Native dialog

computer-use 초기화가 `failed to write kernel assets` (os error 3)로 실패했고 reset 뒤에도 같았다. native 파일 실선택/Save 확정/사람 mouse·keyboard focus는 **미검증**.

보조 도구는 실제 Windows Qt dialog를 열고 프로그램에서 reject한다. 실제 child process 종료 코드를 기록하며 stderr 문구만으로 실패를 판정하지 않는다.

| 진단 | 관측 | OS exit |
| --- | --- | --- |
| Open 1회 | reject·기존 이미지 유지, teardown COM 경고 | 0 |
| Save 1회 | reject·기존 이미지 유지 | 0 |
| Open 20회 요청, Python QObject 호출 | 16회 취소 후 17번째 Open 중 접근 위반 | 0xC0000005 |
| Save 20회 요청, Python QObject 호출 | 10회 취소 후 11번째 Open 중 접근 위반 | 0xC0000005 |
| Open 20회 요청, QML id 호출 | 7회 취소 후 8번째 Open 중 접근 위반 | 0xC0000005 |
| TD-06 QML id Open 20회 요청 | 10회 취소 후 11번째 Open 중 접근 위반 | 0xC0000005 |
| 최소 Qt 창, 프로젝트·이미지 없음 | COM 및 first-chance 접근 위반 경고, 20회 완료 | 0 |

실패 지점은 일정하지 않다. 마지막 행은 단회 비교다. Result 폴더 picker 반복/실선택과 native Save 확인은 미검증. 반복 충돌은 **P0 / unresolved / RC blocker**다.

## 13. COM 진단

`0x80010108`은 COM 객체가 클라이언트와 연결 해제된 `RPC_E_DISCONNECTED`([Microsoft COM error codes](https://learn.microsoft.com/en-us/windows/win32/com/com-error-codes-3)). Open/reject 반복과 engine teardown에서 재현됐다.

COM 경고 뒤 exit 0인 실행과 실제 `0xC0000005` 종료를 구분한다. faulthandler가 first-chance 예외에 “fatal”이라고 출력해도 프로세스가 계속될 수 있다. `0x80010012`도 일부 진단에 관측됐다.

원인 **미확인**, COM과 접근 위반의 인과관계 **미확인**, 수정 **없음**. Python wrapper 없이 QML dispatch에서도 충돌하고 최소 Qt 창에서도 COM 경고가 난다. ImageJ worker나 특정 wrapper만이 원인이라고 단정하지 않는다. Qt 버전 변경·로그 suppression·native dialog 우회를 검증된 수정으로 제시하지 않는다.

## 14. ImageJ / Fiji

실 TIFF 4개 첫/중간/마지막에서 Fiji MultiplyDataValuesBy를 32×32 ROI 작업 복사본에만 적용, 원본 기반 계산과 전체 배열 일치 PASS. 현재 stack 페이지 legacy print macro PASS.

기존 Windows native 4개는 합성 fixture로 실제 AWT/Swing/ImageJ 창 생성·호스팅·옵션 반영·닫기/중단 cleanup을 검사한다. 사용자 plugin 대화상자 입력·사람 focus 복귀·모든 plugin 완전 호환·native 창이 열린 상태 수동 종료는 미검증.

## 15. Save / Export / Data Integrity

TIFF 4개·실제 JPG 전후 전체 hash 동일. JPG 새 복사본 SHA도 일치. ROI ZIP 의미·float32/integer bounds precision 확인. Result JSON filter 전후 전체 내용 동일, CSV 행 수 일치.

QTest UI flow와 기존 저장 slot으로 export했다. native Save를 사람이 확정한 검사가 아니다. 원본 overwrite·삭제 없음. 데이터·모델·결과·사유 로그·캡처는 Git에서 제외한다.

## 16. 종료 / cleanup

상황별 별도 OS 프로세스. worker wait·engine DeferredDelete 수행.

| 상황 | 관측 / 종료 대기 | OS exit | 메인 Qt RSS 전 → 후 bytes |
| --- | --- | --- | --- |
| Idle | 0.001s | 0 | 283,000,832 → 228,229,120 |
| 실제 Stack 준비 중 | preparing 확인, temp cache 해제, 0.009s | 0 | 419,811,328 → 252,534,784 |
| 실제 모델 Running | RUNNING 확인, 취소 종료, 0.135s | 0 | 966,324,224 → 295,038,976 |
| 실제 E2E 끝 | worker 종료 대기 0.113s, 새 engine 빈 상태 | 0 | 장기 누수 추정 안 함 |

새 engine/분리된 QSettings의 빈 상태 검사다. 정상 entrypoint의 saved preference 로드와 사람 수동 재실행을 대신하지 않는다.

## 17. 성능

T0=Open 요청, T1=metadata, T2=source frame, T3=Main.qml first frame swap 및 initial overlay 없음, T4=full stack ready. T3는 scene 렌더링 근거이며 사용자 인지 시간은 아니다. 사전 SHA 계산이 OS cache를 데우므로 단회 참고값이다. 부하/측정 순서 차이가 있어 통계적 유의성을 주장하지 않는다.

| 실제 파일 | T1 s | T2 s | T3 First Viewable s | T4 Full Stack s | sampled peak RSS GiB | 요청 median/max ms |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| N119 | 0.009154 | 0.265358 | 0.304609 | 30.715239 | 4.35 | 4.422 / 18.229 |
| No107 after | 0.004308 | 0.180771 | 0.209663 | 16.378037 | 3.96 | 1.747 / 5.135 |
| No107 before | 0.006654 | 0.292401 | 0.310761 | 23.106634 | 3.96 | 4.273 / 15.106 |
| No22 | 0.008364 | 0.328757 | 0.354264 | 46.011865 | 3.76 | 5.517 / 31.137 |

준비 중 heartbeat 최대 간격 37.127~195.113ms. 페이지 요청 316/312/312/312회. 요청 시간은 상태 발행 CPU 시간이며 실제 FPS가 아니다. PreparedView.paint 샘플 최대 3.740/5.687/6.569/4.852ms. 재열기 36.352/19.224/19.937/40.560s.

TD-07 이전은 TD-06 exact SHA `a1d615356de8ce78842bf2a2703cc4ca042b8a87` archived src. 동일 Python 의존성·No107 before·측정 도구·warm hash 조건, Fiji worker 없는 benchmark-only 모드로 별도 프로세스에서 직렬 비교했다.

| 버전 | T3 s | T4 s | 10ms sampled peak RSS bytes | heartbeat max ms | exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| TD-06 | 13.077549 | 13.059279 | 4,306,407,424 | 34.884 | 0 |
| TD-08 기준 현재 | 0.166690 | 12.660995 | 4,306,309,120 | 31.269 | 0 |

단회 비교에서 full stack 완료 시간 증가가 관측되지 않았다. 이전에는 full gate 때문에 T3가 T4 뒤였다. 통계적 유의성·모든 파일의 회귀 없음은 주장하지 않는다. 4파일 세션 표와 단독 비교는 작업 순서·worker 부하·cache 상태가 달라 같은 실험이 아니다.

초기 실제 모델 harness의 QTest.qWait polling 중 353.168s 관측. 검증 도구의 같은 2ms 간격에서 time.sleep으로 GIL을 양보한 뒤 8~14s였다. 이를 product 회귀나 timeout 연장으로 기록하지 않는다.

## 18. 메모리

psutil 10ms timer RSS와 Windows OS lifetime process peak를 구분한다. RSS는 resident mmap 포함이며 heap 전용이 아니다. 같은 긴 세션 OS peak는 이전 파일도 포함하므로 파일 고유 peak로 해석하지 않는다. 별도 ImageJ worker Java heap은 메인 Qt RSS에 포함되지 않는다.

| 파일 | Open MiB | First MiB | Stack ready MiB | clear 후 MiB | browse/raw/display disk MiB |
| --- | ---: | ---: | ---: | ---: | --- |
| N119 | 268.92 | 359.30 | 4457.90 | 286.17 | 464.74 / 52.95 / 3703.47 |
| No107 after | 286.13 | 334.31 | 4047.88 | 282.59 | 419.79 / 48.40 / 826.36 |
| No107 before | 282.59 | 332.39 | 4047.46 | 285.34 | 419.79 / 48.40 / 826.36 |
| No22 | 285.34 | 330.12 | 3851.16 | 226.19 | 401.30 / 46.24 / 3194.03 |

메인 Qt OS lifetime peak 4,865,323,008 bytes(약4.53 GiB). Available RAM은 시작 전 약8 GiB에서 다른 앱/worker 부하에 따라 달랐다. 메모리 구조를 수정하지 않는다.

## 19. QML / Qt / Python / Java 로그

실제 E2E·TIFF·성공 종료 report QML warnings 0. raw stderr 보존. Cancel CANCELED와 gray16 INVALID_INPUT은 의도한 error-path 검사. COM/접근 위반 suppression 없음. Java client는 일반 stdout을 모두 수집하지 않으므로 전체 Java warning 0을 주장하지 않는다.

ignored artifacts 근거: `td09-real-default/report.json`, `td09-e2e-exit/report.json`, `td09-before-real/report.json`, `td09-after-real/report.json`, `td09-process-exits.json`, `td09-dialog-open20.log`, `td09-dialog-save20.log`, `td09-dialog-qml20.log`, `td09-dialog-before20.log`, `td09-minimal-dialog.log`. 잘못된 fixture 경로 등 harness 오류는 product 실패와 구분했다.

## 20. Regression / Known Issues / 실제 사용자 검증

Production source diff 없음. 계약·원본·결과 구조 회귀가 검사 범위에서 관측되지 않았다. native 반복 충돌은 TD-06에도 재현되어 TD-07/08에서 새로 생겼다는 근거가 없다. TD-01 이전·다른 Qt·다른 PC 비교는 하지 않아 최초 발생 시점과 원인은 미확인.

실제 자료로 Qt controls·일부 캡처를 검토했으나 사람의 native 마우스 전체 세션은 미수행. native 실선택/Save/focus/창 열린 상태 수동 종료, OS DPI 변경, 장기 사용·전체 plugin 호환·공간 축/간격은 미검증. uint16 분석은 현재 RGB8 모델과 계약이 달라 완료 불가. 디스크 부족 시 display cache 준비가 실패할 수 있다.

## 21. 발견 Issue / Severity

Issue #72에 기록한다. 새 기능이나 안전성이 검증되지 않은 수정은 추가하지 않았다.

| Severity | 내용 | Reproducible | Fixed | RC Blocker |
| --- | --- | --- | --- | --- |
| P0 | Windows native picker 반복 Open/reject 접근 위반 종료 | 현재·TD-06·QML dispatch 재현 | No | Yes |
| P2 | uint16에서 RGB8 Run 활성화 후 INVALID_INPUT | 실제 No22 | No, 기존 계약 | 16-bit 분석 범위 미완료 |
| P2 | native host 위치 assertion 동시 부하 실패 | 2개 실패, 직렬 4개 통과 | No, 원인 미확인 | 안정성 제약 |
| P3 | ROI ZIP integer/float32 정밀도 | 실제 4종 | No, 기존 형식 | No |
| 환경 | fixture 디스크 부족·잘못된 Java 512MB cap | 정상 조건 재검사 | 준비 조건 정정 | No |
| 검증 공백 | native 실선택/Save/focus·OS DPI 125/150% | 미수행 | No | PASS 판정 불가 조건 |

## 22. RC Verdict / 재현 방법

**FAIL / NOT RC READY.** unresolved P0 접근 위반 충돌로 병합·배포를 권고하지 않는다. 실제 자료·모델 통과와 자동 검사 성공을 RC 승인으로 해석하지 않는다.

검증 도구는 기존 앱 dependencies 외 **psutil** 설치가 필요하다. 앱 production dependency로 추가하지 않았다. 저장소 root에서 실행한다.

```powershell
.\.venv\Scripts\python.exe -m pip install psutil
$env:QT_QPA_PLATFORM = "windows"
$env:QSG_RENDER_LOOP = "basic"
# 실제 데이터와 로컬 bundle 경로를 직접 지정
.\.venv\Scripts\python.exe tools/validate_rc_session.py --folder "$XRT_DATA" --jpeg "$XRT_JPEG" --model "$XRT_MODEL" --fiji-home artifacts/fiji-runtime --output artifacts/td09-local
.\.venv\Scripts\python.exe tools/probe_rc_dialogs.py --input "$XRT_INPUT" --output artifacts/td09-dialog-local --dialog open --repeat 20 --qml-dispatch
```

원본 밖 ignored artifacts에 출력한다. 충돌 시 report JSON이 없을 수 있어 실제 종료 코드·raw log를 함께 보관한다. `--benchmark-only`, `--session-only`, `--shutdown-case idle|loading|analysis`로 검사 범위를 고른다. 전체 준비는 수 GiB RSS·임시 디스크 공간이 필요하다.

## 23. Merge 순서

현재 병합 권고 없음. native 반복 충돌 원인 규명·수정·재검증과 native 실선택/Save/focus 수동 확인이 우선이다. uint16 입력 계약 사전 안내와 모델 대응은 별도 작업으로 결정한다. 향후 blocker 해결/리뷰 후 선행 #53 이전 stack을 확인하고 #56→#59→#61→#63→#65→#67→#69→#71→TD09 의존 순서를 재확인한다. 일반 merge 뒤 ancestry를 확인하여 base를 main으로 retarget할 수 있고, squash/rebase merge 뒤 중복 ancestor commit 정리 rebase가 필요할 수 있다. 현재 clean은 미래 conflict 없음을 보장하지 않는다. 각 작업 뒤 CI/review/diff 재검사 필요.

## 24. Release Notes 초안

- 자주 쓰는 Viewer 조작을 7개 Toolbar로 정리.
- 이미지·분석·결과·ROI·표시 설정을 작업 Context에서 선택.
- 같은 화면에서 전체/지정 영역 분석, 취소, 후보 필터/이동, 결과 저장.
- ROI 작성·편집·관리와 분석 영역을 구분.
- TIFF 첫 페이지 조기 표시, 나머지 Stack 준비 상태 안내.
- 전역 글자·Control·focus·spacing 계층 통일.

정확도 보증이나 제조용 릴리스 승인을 뜻하지 않는다.

Git: Issue #72, 작업 branch `test/72-ux-integration-rc`. exact 최종 HEAD·commits·push·draft PR·최종 검사/CI는 연결 PR에 기록한다. 기존 사용자 AGENTS.md 수정은 보존하며 커밋하지 않는다.

## TD-10 후속 상태

Windows native 파일 선택창의 modal 경로와 수명 관리를 수정했습니다.
자동 반복 검증과 전체 회귀 결과는 [TD-10](XRT-UX-TD-10-NATIVE-DIALOG-CRASH.md)에 기록합니다.
수동 native 마우스 검증이 PENDING이므로 TD-09의 FAIL / NOT RC READY 판정과 RC blocker를 유지합니다.
