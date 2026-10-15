# Windows 데스크톱 UI 라이브러리 검토 (#141)

조사일: 2026-10-15. 적용 범위: PySide6/QML 프로그램. 이번 배포에는 라이브러리를 추가하지 않았다.

## 현재 코드에서 확인한 점

- `__main__.py`는 `QQuickStyle.setStyle("Basic")`을 지정한다. 실제 환경은 PySide6 6.11.2다.
- `AppButton.qml`은 contentItem/background, `Theme.qml`은 색·크기·Segoe UI 글꼴을 직접 지정한다. 전역 스타일 변경만으로 이 컴포넌트들은 바뀌지 않는다.
- 이미지 렌더러·Qt Quick 3D·QML/파이썬 연결이 이미 있다. UI 현대화의 첫 단위는 공통 컨트롤과 화면 구성이다.
- 현재 가상 환경에 QtQuick/Controls/FluentWinUI3 모듈이 있다. 실제 설치 패키지 및 DPI·팝업 호환성 검증은 도입 시 별도 필요하다.

## 후보 비교

| 후보 | 현재 구조와의 관계 | 판단 |
| --- | --- | --- |
| Qt Quick Controls FluentWinUI3 | Qt 6.8부터 제공하는 공식 QML 스타일. Windows 11 계열 표현, 팔레트/라이트·다크 지원 | **우선 추천.** 기존 Qt 의존성 안에서 공통 컨트롤을 단계적으로 전환할 수 있다. 미지원 컨트롤은 Fusion으로 fallback하며 이미지 기반 일부 요소의 커스터마이징 제약이 있다. |
| FluentUI / PySide6-FluentUI-QML | QML용 Fluent 컴포넌트와 PySide6 구현. MIT 표기 | 후보. 내비게이션 등 풍부한 컴포넌트가 있지만 앱 프레임·테마·배포 수집을 함께 확인해야 한다. 기존 FluentUI 저장소는 새 Pro/FluentUI2를 안내하므로 서로 다른 제품의 라이선스와 Qt 호환성을 혼동하면 안 된다. |
| PySide6-Fluent-Widgets (QFluentWidgets) | PySide6 지원 Qt Widgets 컴포넌트. QML에 바로 import하는 라이브러리가 아님 | 신규 Widgets 앱에는 후보. 현재 앱에 적용하려면 창·화면 구성의 교체 또는 혼합 구조가 필요해 우선순위가 낮다. 저장소는 GPLv3 및 상용 라이선스를 안내한다. 도입 버전의 실제 LICENSE/조건 확인 필요. |
| KDE Kirigami | QML 기반 적응형 UI 프레임워크, Python 연동, LGPL-2.0-or-later 안내 | 크로스 플랫폼 중심 대안. 현재 Windows 전용 배포에는 KDE 모듈·테마 의존성과 패키징 비용을 먼저 검증해야 한다. |

위 판단 중 프로젝트 적용 비용은 현재 코드에 근거한 추정이다. 외부 라이브러리의 성능·설치 안정성을 실측했다는 뜻은 아니다.

## 권장 진행 순서

1. FluentWinUI3 시험 화면: 버튼·입력·콤보·모달·진행 상태·테이블만 대표 화면에서 비교한다. Native Dialog 안정화와 Viewer 엔진은 유지한다.
2. 공통 디자인 토큰을 정리한다. 본문 14px 전후, 컨트롤 32–36px 전후를 출발점으로 삼되 100/125/150/200% DPI에서 확인한다. 키보드 포커스·대비·비활성 상태를 통일한다.
3. 상단 도구·결과 요약·선택 결함 상세·신고 모달 순서로 교체한다. 핵심 작업 1개를 우선 노출하고 고급 기능은 필요 시 펼친다.
4. 고해상도 Pan/Zoom, ROI 원본 좌표, 3D, ImageJ/Fiji 창, 설치·업데이트를 회귀 검증한다. 라이브러리 이름 변경만으로 현대화 완료로 판단하지 않는다.

## 1차 자료

- [Qt FluentWinUI3 공식 문서](https://doc.qt.io/qt-6/qtquickcontrols-fluentwinui3.html): 제공 버전, 제한, 팔레트, Fusion fallback.
- [QML FluentUI](https://github.com/zhuzichu520/FluentUI): QML 컴포넌트, MIT 및 후속 제품 안내.
- [PySide6-FluentUI-QML](https://github.com/zhuzichu520/PySide6-FluentUI-QML): PySide6/QML 구현과 배포 예시.
- [QFluentWidgets 공식 저장소](https://github.com/zhiyiYo/PyQt-Fluent-Widgets): PySide6 브랜치, Widgets 기반, 라이선스 안내.
- [Kirigami 공식 문서](https://develop.kde.org/frameworks/kirigami/): QML/Python 지원과 라이선스.
