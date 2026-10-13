# Windows 연구용 설치 빌드

GPLv3 공개 배포·소스 제공은 [운영 보고서](../docs/deploy/XRT-DEPLOY-TD-01.md)를 먼저 읽는다. 게시자가 GPLv3+동일 버전 소스 배포를 승인했다. 초기 QA 빌드를 공개하지 않고 최종 GPL 설치와 소스를 새 경로에 빌드한다. 원본 TIFF/JPG, 사설 프로젝트, Credential, 모델은 패키지에 넣지 않는다.

빌드는 D의 Windows x64 `.venv`(Python3.13, PySide6 6.11.2), PyInstaller6.22.3/hooks2026.8, 공개 ImageJ/Fiji runtime, Eclipse Temurin21.0.12.1+1, Inno Setup7.1.0으로 검증했다. upstream 다운로드는 공식 HTTPS와 제공 SHA/Authenticode를 확인한다. 운영 머신의 Oracle JDK를 배포 입력으로 쓰지 않는다.

```powershell
Set-Location D:\capstone\sic-xrt-analyzer
.\.venv\Scripts\python.exe tools/setup_imagej.py
.\.venv\Scripts\python.exe tools/setup_fiji.py
# 소스·installer 입력을 커밋한 후 새 output 지정
.\.venv\Scripts\python.exe tools/build_windows_installer.py `
  --jdk artifacts/distribution120/openjdk/jdk-21.0.12.1+1 `
  --compiler artifacts/distribution120/inno/ISCC.exe `
  --output artifacts/distribution120/<new-build> `
  --source-directory artifacts/distribution120/corresponding-sources
```

GUI와 worker는 동일 onedir DLL/패키지를 사용한다. 스크립트는 source revision, 파일 SHA/size, component 목록과 배포보류 manifest를 출력한다. 앱이 import하는 서브프로세스 모듈은 runtime_process의 allowlist를 사용한다. PySide Addons/Essentials/shiboken metadata/license와 public Java legal 파일을 보존한다. 동일 revision의 소스 아카이브와 SHA 확인을 완료한 GPL 빌드만 APPROVED manifest로 만든다. 설치와 소스가 모두 있어야 서버 게시가 가능하다.

Smoke는 새 경로 JSON에 기록하며 temporary 합성 TIFF/JPG/설정만 사용한다:

```powershell
artifacts/distribution120/<new-build>/dist/SiCXrtAnalyzer/SiCXrtAnalyzer.exe --smoke-report artifacts/distribution120/<new-report>.json
```

실제 설치·제거는 별도의 새 QA 경로에서 검증한다. 기존 같은 AppId 설치가 있으면 QA 설치로 대체하지 않는다. 설치 밖 프로젝트의 SHA 보존도 대조한다. QA artifact는 Git/사이트에 게시하지 않는다.
