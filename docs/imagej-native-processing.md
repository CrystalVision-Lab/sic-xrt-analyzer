# ImageJ 분석 근거와 기본 처리 UI (Issue #158)

## 구현 범위

ImageJ 1.54p의 계산을 그대로 사용하며, 다음 9개 명령의 설정을 앱 내부
한국어 입력란으로 연결한다. 처리 메뉴와 명령 목록에서 해당 명령을 선택한다.

| 화면 | ImageJ 명령 | 입력 |
| --- | --- | --- |
| 가우시안 흐림 | Gaussian Blur... | sigma, 픽셀 단위 |
| 중앙값 필터 | Median... | radius |
| 평균 필터 | Mean... | radius |
| 최솟값 필터 | Minimum... | radius |
| 최댓값 필터 | Maximum... | radius |
| 분산 필터 | Variance... | radius |
| 선명하게 | Unsharp Mask... | radius, mask |
| 이상 픽셀 제거 | Remove Outliers... | radius, threshold, which |
| 배경 제거 | Subtract Background... | rolling, light, sliding, disable, separate |

현재 페이지의 작업 복사본을 만들며 원본 파일은 바꾸지 않는다. 면적 ROI가
선택되면 그 영역을 처리한다. 선·점·각도·텍스트 ROI는 필터 적용 전에 거부한다.
배경 제거는 ImageJ가 ROI를 무시하므로 선택 ROI를 해제한 경우에만 실행한다.
기존 TIFF 빠른 처리의 가우시안/배경 제거도 같은 검증과 실행 경로를 사용한다.
임계값/이진화 빠른 처리의 기존 동작은 이번 구현 대상이 아니다.

전체 스택은 기본 설정 UI에서 실행하지 않는다. 명시적인 현재 페이지 옵션과
새 페이지 복사본을 사용해 이전 고급 명령의 JVM 스택 상태가 섞이지 않게 한다.
이 기본 처리의 결과는 한 페이지이다. 입력 스택 전체를 수정하거나 보존한
새 다중 페이지 스택을 생성하는 기능으로 해석해서는 안 된다.

기본 설정에서 **고급 명령 입력**으로 전환하면 수정한 값이 매크로 옵션에
반영된다. 모든 옵션을 표현할 수 있는 명령만 기본 설정으로 표시한다.
예를 들어 `scaled`, `create`, `stack`, 구형 Gaussian `radius` 옵션은
자동으로 삭제하거나 바꾸지 않고 고급 입력에 그대로 남긴다.

## 실제 분석과 그 한계

분석 대상은 앱이 SHA256 검증 후 로드하는 `ij-1.54p.jar`이다.

```text
SHA256: 2e1a09961dfb41cee66ddc821b2577a41a072566ce45a49bae69267099741e20
REA: 6.4.0 / rea-artifact-graph provider 1
REA evidence: ev_22920cb3e2997b4e8ec014ce8d7c004c0e62ee24626d10125a59728db792a770
```

REA `inspect-artifact`는 내부 항목 517개와 그중 클래스 파일 469개를 관찰했다.
루트 JAR을 포함한 그래프 노드는 518개이다. 이 수치는 기능 수나 지원률이 아니다.
검사 범위는 ZIP 디렉터리 목록·포함 관계·내용 해시이며 메서드 의미 분석은 아니다.
REA Ghidra 어댑터는 JVM 바이트코드를 지원 대상 아키텍처로 받지 않는다.
REA의 Java 디컴파일 경로인 JEB는 별도 엔진/MCP 연결이 필요하며 이 환경에는 없다.
`doctor`의 Debian 12/미설정 공급자 경고와 패키지 검사 성공을 구분한다.

후속 심층 분석은 설치된 JDK 24의 `javap -c -p`로 **동일한 실제 JAR**의
메서드 명령과 분기를 읽고, 합성 영상으로 ImageJ를 실행해 확인했다.
이를 REA 심층 디컴파일 결과라고 부르지 않는다. 원시 REA JSON과 javap 출력은
Git에서 제외된 `artifacts/rea-imagej-20261016/`에 보존하며 제품에 넣지 않는다.

재현 예:

```powershell
docker exec rea-local-rea-1 node scripts/rea.mjs inspect-artifact /tmp/sic-xrt-ij-1.54p-20261016.jar --format json --full-output
& 'C:\Program Files\Java\jdk-24\bin\javap.exe' -classpath artifacts/imagej-runtime/ij-1.54p.jar -c -p ij.IJ ij.Macro ij.gui.GenericDialog ij.plugin.filter.PlugInFilterRunner ij.VirtualStack
& 'C:\Program Files\Java\jdk-24\bin\javap.exe' -classpath artifacts/imagej-runtime/ij-1.54p.jar -c -p ij.plugin.filter.GaussianBlur ij.plugin.filter.RankFilters ij.plugin.filter.BackgroundSubtracter ij.plugin.filter.UnsharpMask
```

Docker 내 JAR 경로는 검사 전에 제공한 복사본이다. 다른 환경에서는 실제 경로를
지정하고 원본 JAR SHA256과 일치하는지 확인한다. ImageJ 버전을 바꾸면 아래
관찰과 옵션 계약을 다시 검증한다.

| 바이트코드 관찰 | 통합에 반영한 처리 |
| --- | --- |
| `IJ.setupDialog`는 composite 이미지에서 명시적 `slice`가 없으면 스택 처리를 선택할 수 있다 | 모든 기본 처리 옵션에 `slice` 포함 |
| `IJ.setupDialog`의 매크로 `stack` 분기는 대화형 virtual-stack 검사보다 먼저 반환한다 | 기본 처리에서 전체 스택 입력 거부 |
| `PlugInFilterRunner.processStack`는 `getPixels`를 수정하고, 기본 `VirtualStack.setPixels`는 no-op이다 | 가상 스택 편집이 보존된다고 가정하지 않음 |
| `PlugInFilterRunner.prepareProcessor`는 `Roi.isArea()`가 false이면 ROI를 제거한다 | 선·점 등 비면적 ROI 사전 거부 |
| `BackgroundSubtracter`는 전체 픽셀 배열을 처리하며 ROI masking을 제공하지 않는다 | ROI가 선택됐으면 배경 제거 거부 |
| Gaussian의 구형 `radius` 옵션은 sigma로 변환하며 2.5로 나눈다 | UI에서 `sigma`를 정확히 사용, 구형 옵션 자동 변환 안 함 |
| GenericDialog 숫자/선택값 생략 시 기억된 기본값이 사용될 수 있다 | 숫자·선택값을 매번 완전히 전달 |
| checkbox는 bare token, `disable`은 smoothing 끄기를 의미한다 | boolean을 명시적으로 검증하고 선택된 토큰만 전달 |
| 빈 macro options는 macro context를 제거할 수 있다 | 비어 있지 않은 옵션으로 `IJ.run` 호출 |

지원 숫자 범위는 UI의 자원 사용을 제한하기 위한 제품 정책도 포함한다.
Median/Outliers 반경은 ImageJ의 100 상한, 나머지 반경·sigma는 최대 1000,
Unsharp mask는 0–0.99, background 반경은 최소 0.001을 사용한다.
임의 매크로 문자열, 잘못된 boolean/choice, NaN/Infinity는 받지 않는다.

## 검증 방법

`tests/test_imagej_native_commands.py`는 기본 설정 실행과 독립적인 고정 옵션의
ImageJ 명령 실행을 서로 다른 작업 프로세스에서 비교한다. 9개 명령 ×
uint8/uint16/float32 영상, ROI 밖 픽셀, RGB checkbox 상태 전환,
이전 가상 스택 이후 현재 페이지 격리, 잘못된 파라미터/비면적 ROI 거부를 검사한다.
같은 ImageJ를 사용하므로 이 비교는 알고리즘 자체의 과학적 정확도 증명이 아니라
입력·출력과 옵션 연결의 동등성 검사이다.

실제 QML 창의 파라미터 입력, 기본/고급 전환, 실행 버튼, 작업 결과와 원본
보존을 함께 검사한다. 자동 QTest 검사를 실제 사람의 물리 마우스 검사로
보고하지 않는다. 기존 ImageJ/스택/TIFF 작업창 회귀도 실행한다.

Windows/JDK 24 로컬 검증에서 새 기본 처리 및 TIFF 검사는 45개,
기존 ImageJ/스택/Fiji ROI 검사는 21개 통과했다. 네이티브 GUI 검사 4개는
offscreen 환경에서 건너뛰었다. 기본/고급 옵션 재편집 후 왕복하는 QML 검사는
최종 수정 후 다시 통과했다. Ruff, Python 컴파일, wheel 빌드도 통과했다.

고급 경로에서 가상 스택에 `sigma=1 stack`을 적용한 뒤 저장하면 결과가
원본과 동일한 현상은 합성 uint16 3페이지 영상으로 별도 재현했다.
[Issue #159](https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues/159)에
기록했으며, 이번 기본 처리 경로는 이를 회피하지만 고급 경로의 결함은 남아 있다.

## 전체 통합의 남은 단계

- 복수 이미지 입력과 복수 결과 이미지 보존. 현재 마지막 결과를 대표로 고르는 경로 개선.
- ROI Manager 양방향 동기화와 결과표 행에서 페이지/ROI로 이동.
- 가상 스택에 대한 영속 작업 결과와 페이지 단위 메모리 예산을 갖춘 대용량 처리.
- 작업 이력·되돌리기·설정 저장·일괄 재실행.
- 기본 명령 전체의 입력/출력/ROI/페이지 동작 목록화 및 개별 네이티브 UI.
- Fiji/SciJava 특수 입력·표·그래프 출력, GUI 의존 플러그인별 호환성 검사.

위 항목과 모든 플러그인 호환은 이번 단계에서 완료되지 않았다. 기존 Java
설정창과 매크로 고급 경로를 유지한다. ImageJ 런타임 버전·JAR 해시, ROI 파일
형식, ML/DataTools/서버 계약, 승인 ONNX 추론 계약은 바뀌지 않는다.
새 `native`/`parameters` 요청은 앱 소유 작업 프로세스 내부 인터페이스이다.
