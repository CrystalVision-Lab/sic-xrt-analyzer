# XRT-UX-TD-10 — Windows native file dialog 반복 종료 진단과 수명 관리

Issue [#74](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/74).
Base: `test/72-ux-integration-rc` / PR #73, exact SHA `62fa149c869a59efc76a06fd4df434c75615bdc8`.
Branch: `fix/74-windows-native-dialog-crash`.

**Status: PARTIAL / P0: MITIGATED / RC blocker: REMAINS.**
자동 재현과 데이터 callback을 검증한다. 실제 OS 선택창의 마우스 열기·취소·선택·확정은
**MANUAL NATIVE VALIDATION PENDING**이다. 자동 reject만으로 최종 PASS를 선언하지 않는다.
전체 회귀 및 CI 결과는 아래 검증 기록과 PR에서 확인한다.

## 1. TD-09 P0와 기존 구조

TD-09는 FAIL / NOT RC READY였다. Windows native Open, Save, QML 직접 open 반복에서
`0xC0000005`가 발생했다. 첫 도입 커밋은 UNKNOWN이며 TD-07/08 신규 회귀라고 단정하지 않는다.

- Open: Main `openImageDialog()` / Action → persistent `openDialog.open()` →
  accepted → `selectImagePath(selectedFile)` → FileBridge → 기존 image/stack loading.
- Save: `saveImageCopy()` → persistent `imageSaveDialog.open()` → accepted →
  `FileBridge.saveImageCopy(selectedFile)` → 기존 사본 저장.
- Result: persistent FolderDialog → accepted → 기존 JSON/CSV export.
- ROI import/export: 각각 persistent FileDialog → accepted → 기존 ROI loader/ZIP writer.
- ImageJ macro/plugin, stack measurement도 각 컴포넌트의 persistent 선택창을 사용한다.
- 총 12개 picker: Main 8, ImageJ 3, StackMeasurement 1. Open과 Save는 별도 객체이다.
- 기존 QtQuick FileDialog는 accepted/rejected 뒤 destroy하지 않는다. 생성은 QML 선언 시,
  파괴는 owner/component 및 engine 종료 시이다. 동적 파일창 재생성은 제품 동작이 아니었다.
- 일반 UI 호출은 GUI thread이다. worker가 파일창을 직접 여는 증거는 발견하지 않았다.
- Python의 일반 파일 경로 전달은 FileBridge loading API로 이어진다. QML 직접 open도 같은
  QtQuick helper를 사용한다. Action 우회에서도 crash가 발생했다.
- QML rejected는 기존 이미지·결과·ROI를 수정하지 않는다. accepted는 기존 callback을 실행한다.
- Main QQuickWindow와 QQmlApplicationEngine은 앱 수명 동안 유지된다. 반복 중 window recreate나
  engine reload는 관찰하지 않았다. signal handler에서 picker destroy/reopen하는 경로도 찾지 못했다.
- 기존 shutdown: app.aboutToQuit → FileBridge.waitForLoads → workers 정리 → engine 파괴.
  Windows native 완료 전에 논리적인 visible/rejected가 먼저 전달될 가능성은 별도 조사 대상이었다.

## 2. Baseline 및 최소 재현

원본 TD-09 소스를 ignored artifacts에 독립 보존해 비교했다. Qt/PySide6 6.11.2,
Windows/Python 3.13, 원래 QSG_RENDER_LOOP=basic 조건이다. cycle 간 대기를 늘리지 않았다.
아래는 일반 Windows 권한에서 독립 프로세스 3회씩 실행한 crash 발생 cycle이다.
실패 시각과 마지막 signal은 JSONL에 있으며, 고정 crash threshold로 해석하면 안 된다.

| Case | Run 1 | Run 2 | Run 3 | Exit / COM |
| --- | ---: | ---: | ---: | --- |
| Open/object | 7 | 7 | 9 | 12/12 C0000005, COM 0/12 |
| Save/object | 6 | 7 | 14 | 동일 |
| QML direct Open | 10 | 7 | 9 | 동일 |
| Mixed Open/Save | 5 | 4 | 10 | 동일 |

마지막 전체 완료 cycle은 Open 6/6/8, Save 5/6/13, QML 9/6/8, Mixed 4/3/9이다.

제한된 실행 환경에서는 각각 Open 8/7/9, Save 8/13/6, QML 9/11/10, Mixed 6/5/5 부근에서
AV가 관찰되었고 COM 진단은 11/12였다. 이 숫자는 마지막 reject 관찰값이며 Mixed 중간 단계가
포함될 수 있다. 일반 Windows 12-run 표가 권한 차이를 제거한 주된 비교이다.
`artifacts/td10-baseline-summary.json`, `td10-normal-baseline-summary.json`에 원시 결과를 남겼다.

`tools/dialog_lifecycle_probe.py`는 최소 Window/Button/Action/FileDialog 모드와 전체 앱 모드를
모두 지원한다. faulthandler, cpp pointer, destroyed, visible/rejected, OS thread, owner HWND,
COM apartment, process handles/USER/GDI/RSS를 기록한다. psutil은 검증 도구 의존성이며
production dependency에 추가하지 않았다. Windows API는 진단 정보를 읽기만 한다.

| 격리 실험 | 결과 | 해석 |
| --- | --- | --- |
| persistent native 최소 Open/Save/Action | 8/7/6 부근 AV | 분석·ROI·TIFF 및 Action wrapper 없이 재현 |
| original native, Qt QObject.thread getter 제거, 일반 Windows | cycle 9 AV | 계측 getter만으로 기존 P0를 설명할 수 없음 |
| persistent non-native 최소, 100회 | exit 0, AV/COM 0 | Windows native 경로에 국한될 강한 근거 |
| 매번 dynamic native, 100회, 제한 환경 | exit 0이나 USER 23→2600, GDI 15→1863 | crash 회피만으로 채택 불가 |
| dynamic non-native | 최초 조건 deadline 실패 | PASS에 포함하지 않음 |
| 별도 Qt 6.8.3 env / native | cycle 9 AV | 임의 버전 pin을 해결책으로 채택하지 않음 |
| Widgets modal native, 일반 Windows, 100회 | exit 0, 자원 warm-up 뒤 안정 | native 유지 대안의 근거 |

## 3. Thread, owner, signals, COM 및 crash evidence

확정된 사실:

- 원본 persistent QtQuick native 최소 재현과 원본 전체 앱이 `0xC0000005`로 종료된다.
- COM `0x80010108` 없이도 일반 Windows의 12개 원본 프로세스가 모두 AV로 종료됐다.
- 실제 GUI child process에 붙인 진단에서 qwindows.dll **+0x16fda**의 AV가 first/second chance로
  기록됐다. fault thread 33284, GUI thread 67512로 서로 달랐다. 프로세스 exit는
  `3221225477` (`0xC0000005`)이다. 해당 exception은 정상 처리한 것으로 숨기지 않았다.
- 기존 QML 객체, main window, engine는 마지막 open/reject 시점까지 유효했다.
- GUI thread의 CoGetApartmentType은 MAINSTA(3), HRESULT 0이었다. 직접 COM 초기화/해제를 추가하지 않았다.
- Application Error/WER 이벤트의 유효한 fault entry와 dump는 확보하지 못했다. 설치된 WinDbg/cdb도 없다.
  Python faulthandler만으로 C++ call stack을 확정할 수 없다.

강한 추정: QtQuick의 Windows async helper 완료와 논리적 close/rejected 사이의 수명 경계가
반복 reopen에 취약하다. Qt 소스는 non-modal helper에서 별도 STA thread를 사용하고,
logical close가 native helper hide 뒤 visible/rejected를 전달함을 보여준다.
다만 fault symbol/PDB가 없어 정확한 C++ 함수, 잘못된 ownership의 최초 지점, 최초 도입 커밋은
**UNKNOWN**이다. qwindows.dll offset만으로 use-after-free를 확정하지 않는다.
[Qt Windows helper source](https://raw.githubusercontent.com/qt/qtbase/v6.11.2/src/plugins/platforms/windows/qwindowsdialoghelpers.cpp),
[Qt Quick dialog source](https://raw.githubusercontent.com/qt/qtdeclarative/v6.11.2/src/quickdialogs/quickdialogs/qquickabstractdialog.cpp).

`0x80010108`은 RPC_E_DISCONNECTED이다. 제한 환경의 dynamic native처럼 진단 뒤 exit 0인 경우와
원본 crash-associated 경우를 구분한다. 기존 P0의 필요조건도 충분조건도 입증되지 않았다.
[Microsoft COM error codes](https://learn.microsoft.com/en-us/windows/win32/com/com-error-codes-3).

후보 구현 중 별도 Qt6Core.dll +0xea19f AV도 조사했다. owner 탐색에서 QQuickItem.window() 호출은
main Window Python wrapper를 invalid로 만들었고, QObject parent chain 탐색으로 제거했다.
빈 shutdown에서 QObject.thread getter를 쓰던 후보는 ROI 회귀에서 AV가 발생했다. 기존 source 및
변경된 bridge의 대조 실험 뒤 Python physical thread ID guard와 기존 단일 shutdown 경로로 수정했다.
이 후보 결함을 원래 qwindows.dll P0의 원인이라고 혼동하지 않는다. 정확한 binding 원인은 UNKNOWN.

## 4. 적용한 수정

- Windows 진입점만 QApplication을 사용한다. 다른 OS는 기존 QGuiApplication을 유지한다.
- SafeFileDialog/SafeFolderDialog는 기존 QML accepted/rejected/selection API를 보존한다.
  Windows native일 때 FileBridge 소유 NativeFileDialogs로 보내고, 다른 OS 및 명시적인
  DontUseNativeDialog는 기존 QtQuick fallback을 사용한다. 제품을 자동 non-native로 바꾸지 않는다.
- Windows는 **동일한 OS native picker를 QFileDialog.exec의 GUI STA modal 경로**로 실행한다.
  native exec 반환 후에만 visible=false와 QML accepted/rejected를 전달한다.
- request 하나만 허용하며 중복 open을 거절한다. QML stack을 벗어나는 queued dispatch(0ms)는
  완료 기다리기용 sleep이 아니다. native 호출 중 root/owner/widget reference를 보유한다.
- QObject parent chain의 QWindow를 native transient owner로 설정한다. HWND owner와 실제
  dialog 호출 OS thread를 로그에서 확인한다. worker 호출은 RuntimeError로 막는다.
- OpenFile/OpenFiles/SaveFile/Folder별 최대 4개 widget을 재사용한다. 종료 때 modal 반환 후
  deferred deletion을 완료한다. root/owner 파괴 또는 shutdown 중 reject하고 늦은 accept는 버린다.
- 기존 FileBridge.waitForLoads가 native shutdown을 먼저 처리한다. 추가 global quit connection은 없다.
- Main/ImageJ/StackMeasurement의 picker 선언만 교체한다. 기존 메뉴, 도구, callback, ROI,
  loading/cache, 저장 payload, 모델 계약은 변경하지 않는다.

Qt는 일반적으로 nested exec보다 open을 권장한다. 이번 Windows 경로는 원본 async native P0를
격리하기 위한 선택이며 owner/root 수명과 callback 시점을 명시적으로 관리한다.
Windows native modal에서 Qt timer dispatch가 중단될 수 있으므로 파일창이 열린 동안
새 UI timer update가 지연될 수 있다. 로딩 정책 자체는 바꾸지 않는다.
[QDialog exec](https://doc.qt.io/qt-6/qdialog.html#exec),
[QFileDialog Windows native caveat](https://doc.qt.io/qt-6/qfiledialog.html).

## 5. 채택하지 않은 대안

- sleep/timeout 증가: lifecycle 완료를 증명하지 못한다. 기존 100ms 관찰/10초 조건은 늘리지 않았다.
- 반복 횟수 감소, 경고 필터링, exception 무시, 기존 테스트 삭제: 결과를 왜곡하므로 하지 않았다.
- dynamic native 재생성: 제한 환경에서 resource runaway가 확인됐다.
- non-native 제품 전환: 일반 Windows native modal 경로를 먼저 검증했다. 제품 fallback 자동 전환 없음.
- Qt version pin: 격리한 6.8.3에서도 original native crash 재현. 기본 venv 버전은 그대로이다.
- CoInitialize/CoUninitialize 추가: Qt COM 소유권과 충돌 가능성, 근거 없음.
- UI/ROI/model/TIFF 변경: 이번 Issue 범위 밖이다.

## 6. 자동 stress 결과

첫 후보의 12개 독립 프로세스는 모두 100회 완료/exit 0였다(`td10-fixed-summary.json`).
최종 source 재검증(`td10-final-summary.json`)에서 Open/object 3회, Save/object 3회,
QML direct 3회는 100회/exit 0이다. Mixed Run 2도 100회/exit 0이나 Run 1/3은
native HWND 관찰 10초 deadline으로 exit 1이었다(완료 13/87 cycles).
이 실패를 PASS에 포함하지 않는다. AV/COM은 아니며 원시 로그를 보존하고 추가 진단한다.

최종 stress 및 전체 회귀 결과는 후속 검증 절에 갱신한다.

## 7. Resource stability

Open/object 최종 Run 1 예시. Windows Shell의 초기 로딩 증가 이후, cycle 50→100에서
handle/RSS가 감소했다. zero delta를 요구하거나 shutdown 후 모든 Shell cache 반환을 주장하지 않는다.

| 시점 | Process handles | USER | GDI | RSS MiB |
| --- | ---: | ---: | ---: | ---: |
| 0 | 1522 | 54 | 15 | 329.37 |
| 50 | 1948 | 75 | 82 | 367.60 |
| 100 | 1901 | 56 | 82 | 366.89 |
| 정리 후 | 1613 | 44 | 80 | 277.92 |

제한 sandbox에서는 Windows Shell error 창과 USER/GDI 누적이 발생했다. 일반 Windows 검사로
환경을 분리했다. 제한 환경의 값으로 resource PASS를 주장하지 않는다. 최종 각 case의
0/1/10/50/100/cleanup 수치는 ignored report.json에 남긴다.

## 8. 실제 native mouse 검증

| 항목 | 요구 | 결과 |
| --- | ---: | --- |
| Open → Cancel | 20 | PENDING |
| Save → Cancel | 20 | PENDING |
| Open → 실제 파일 선택 | 10 | PENDING |
| Save → 위치 선택/확정 | 10 | PENDING |
| Cancel/Accept 후 main focus, viewer/shortcut/toolbar 복귀 | 필수 확인 | PENDING |

사용 가능한 computer-use native runtime 초기화가 OS error 3으로 실패했다.
승인된 UI automation 경로로 실제 마우스를 조작하지 못했다. Qt reject는 실제 native HWND를
관찰한 후 GUI queued signal로 실행하며 human validation으로 부르지 않는다.
**MANUAL NATIVE VALIDATION PENDING.**

## 9. 실제 데이터 및 callback 회귀

`tools/validate_dialog_routes.py`의 report는 `artifacts/td10-data-routes-final/report.json`이다.
선택된 URL을 실제 QML picker accepted callback에 전달하는 검사이며 OS 마우스 선택의 대체 증거는 아니다.
원본 read-only SHA256 전후 일치. 사본/내보내기는 ignored artifacts만 사용했다.

| 파일 | 크기 / 페이지 | 확인 |
| --- | --- | --- |
| After annealing_1.jpg | 12349×12273 / 1 / uint8 | 열기, 사본 SHA256 일치 |
| generated single TIFF | 512×512 / 1 / uint16 | 열기, 사본 SHA256 일치 |
| No22_220_Section_stack_flipped.tif | 2944×2745 / 156 | 0, 78, 155 |
| N119_220_Section_stack_flipped.tif | 3072×3012 / 158 | 0, 79, 157 |
| No107_SectionTopo-beforeAnnealing.tif | 2922×2895 / 156 | 0, 78, 155 |
| No107_SectionTopo-afterAnnealing .tif | 2922×2895 / 156 | 0, 78, 155 |

- ROI import, ZIP export/reload의 좌표·페이지 일치: PASS.
- Result JSON/CSV: synthetic adapter 2946개 후보, 반복 export payload 일치: PASS.
  실제 모델 재추론 검증이라고 주장하지 않는다. TD-09의 실제 모델 결과는 별도 기존 증거이다.
- loaded/result/ROI 상태에서 Open/Save/ROI/Result 요청 취소: source/result/ROI/tool/context 유지 PASS.
  해당 rich-state 취소는 native exec 전에 취소한 protocol 검사이다.
- 잘못된 파일 오류 후 기존 이미지 유지, 정상 reopen 시 결과/ROI 정리: PASS.
- QML warnings: 0. 실제 파일 선택/저장 callback 뒤 shutdown: 0.012초, process exit 0.

## 10. 회귀 테스트와 검증 상태

`tests/test_native_file_dialog.py`에 7개 regression을 추가했다. 실제 QML facade를 사용하고
OS 호출만 fake modal picker로 대체해 중복/선행 cancel/root 파괴/accepted 순서/worker 호출/
late accept/owner 파괴/shutdown을 검증한다. 자동 OS stress는 별도 보존한다.

- native protocol 7 + 기존 ROI 전체 23: **30 passed**, 대기·deadline·기존 테스트 수정 없음.
- 앞선 전체 검사: **265 passed / 2 failed / 4 skipped**. 신규 테스트의 QJSValue/list
  반환 차이를 정규화해 수정했다. 나머지는 기존 ROI 화면 좌표 범위 검사이다.
- 후속 전체 검사: **267 passed / 1 failed / 4 skipped**, 기존 async Wand의 5초 deadline.
  당시 실제 대형 데이터와 native stress가 동시에 실행 중이었다. 원인 확정은 아니며 재검증한다.
- 최종 직렬 전체 pytest / Windows GUI plugin 4 / CI: 검증 후 아래에 기록한다.
- Linux X11 GUI plugin 4는 기존 CI에서 유지한다. macOS는 환경이 없어 미검증이다.

## 11. 실행 방법

PowerShell에서 기존 실행 명령을 그대로 사용한다.

```powershell
.\.venv\Scripts\python.exe -m sic_xrt_analyzer
```

실제 native stress(일반 Windows desktop 권한; 각 case를 별도 process 3회 실행):

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:QSG_RENDER_LOOP = 'basic'
.\.venv\Scripts\python.exe tools/dialog_lifecycle_probe.py --input artifacts/td09-prepared-smoke-input/generated.tif --output artifacts/native-open-run1 --case open --dispatch object --cycles 100 --managed-native
```

`--case save --dispatch object`, `--case open --dispatch qml`, `--case mixed --dispatch qml`을
각각 100회로 실행한다. optional `--minimal`, `--dynamic`, `--non-native`는 원인 격리용이다.
실제 데이터 callback 검사는 `validate_dialog_routes.py --help`에 따른다. 입력과 다른 artifact
폴더를 지정한다. 원본 이미지/모델 및 전체 private 경로를 Git에 올리지 않는다.

## 12. Known issues, RC 및 후속 TD

- P0 native mouse validation 미완료: RC blocker REMAINS. 자동 crash 재현만 완화한 MITIGATED 판정.
- Mixed native 관찰 deadline과 전체 ROI flaky 실패는 원시 로그를 유지하고 최종 결과에 포함한다.
- 정확한 C++ root cause / 최초 도입 커밋: UNKNOWN.
- P2 uint16 single-channel에서 RGB8 모델 입력 사전검사 부족: TD-11 Model Input Contract Preflight.
- P2 기존 ROI 좌표·async Wand deadline instability: 연관성 미확정, 이번 TD에서 변경하지 않았다.
- Windows modal native의 timer dispatch 제한: 파일창 동안 timer 기반 UI 갱신 지연 가능.
- 실제 stack preparing 중 mouse focus/shortcut 복귀 및 macOS는 미검증.
- TD-09 FAIL / NOT RC READY를 최종 RC READY로 올리지 않는다. 자동/수동 gate를 모두 확인한 후
  TD-11 preflight와 RC 재검증을 진행한다.

## 13. Git 및 증거

새 Issue #74와 exact TD-09 base 위의 새 브랜치로 진행한다. 새 draft PR은
`test/72-ux-integration-rc`를 base로 한다. 기존 #56~#73 stack을 merge/rebase/retarget하지 않는다.
사용자 변경 `AGENTS.md`의 whitespace는 보존하고 commit에서 제외한다.

진단 원시 JSONL/log/report는 ignored `artifacts/td10-*`에 남긴다. 개인정보/원본 데이터/모델을
커밋하지 않는다. debugger raw evidence는 `artifacts/td10-debugger/exceptions.json`이다.
GitHub CI URL과 최종 commit SHA는 PR 및 최종 보고에 기록한다.
