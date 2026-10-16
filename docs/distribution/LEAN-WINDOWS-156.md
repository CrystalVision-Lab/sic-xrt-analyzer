# Windows 0.6.2 경량화와 UI 배포 (#156)

새 다크 민트 UI/분포·영역·비교 검토(#155)를 Windows 설치판에 제공한다. 패키지/앱 버전은 0.6.2이며 기존 BETA 채널 및 GPLv3 대응 소스 제공 계약을 유지한다.

## 경량화 경계

일반 JavaScript의 트리 셰이킹을 Python/Qt/Java 동적 로더에 적용하지 않는다. 검증된 PyInstaller TOC에서 다음 배포 파일만 제외한다.

- Fiji jars/linux64, linux-arm64, macos64, macos-arm64, macosx: Windows x64에서 사용하지 않는 다른 플랫폼 네이티브 JAR.
- OpenJDK jmods 및 lib/src.zip: 링크 입력/개발 소스. lib/modules 전체, javac, JVM, JavaFX Windows 라이브러리, 모든 법적 고지는 보존한다. Java 전체 소스는 동일 버전 대응 소스 아카이브에 계속 제공한다.
- 사용하지 않는 QtWebEngine/QtWebView QML 플러그인 및 실행 DLL. QtQuick3D, FluentWinUI3, 이미지 코덱은 보존한다.

기존 qml_exclude_plugins 설정은 설치된 PyInstaller 6.22.3에서 구현되지 않은 옵션이었다. 실제 수집 목록을 필터링하고 남은 PE 바이너리의 일반/지연 import가 제외 DLL을 참조하면 빌드를 실패시킨다. bundle-selection.json에 경로/이유/실제 제외 바이트를 기록한다. 기존 설치 갱신 시 InstallDelete는 앱 전용 _internal 아래 해당 폐기 경로만 정리한다. 원본·사용자 설정·프로젝트·모델 경로는 대상이 아니다.

기존 0.6.1 설치 EXE: 1,283,259,911 bytes. 이전 bundle 대상 예비 검사에서 제외 대상 147개, 753,980,312 bytes(압축 전)를 확인했다. 설치 EXE 절감률은 새 빌드 완료 후 별도로 측정한다.

## 검증 및 호환성

정책/빌드 환경 단위 검사 22 PASS. 기존 bundle에 대해 보존 DLL의 제외 DLL 의존성 없음 확인. 새로운 frozen runtime, 설치/갱신/제거, 업데이트 전달 검사는 게시 전 수행한다. 테스트 결과는 배포 완료 기록에 추가한다.

연구 서버/API/DB/모델/프로젝트 스키마 변경 없음. Fiji 공통/Windows 플러그인과 Java 모듈을 유지하나 임의의 외부 플러그인 전체 호환성을 주장하지 않는다. 앱 코드 서명 상태는 기존처럼 UNSIGNED이며 다운로드 SHA와 설치 runtime manifest 검증은 유지한다.
