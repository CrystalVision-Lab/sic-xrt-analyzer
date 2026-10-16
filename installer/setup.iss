#ifndef AppVersion
 #define AppVersion "0.1.0"
#endif
#ifndef BundleDir
 #error BundleDir is required
#endif
#ifndef OutputPath
 #error OutputPath is required
#endif
#ifndef AppGuid
 #define AppGuid "81CAB3F6-F3BE-4B05-ACB8-E9F47113CC32"
#endif
#ifndef UpdateHelper
 #error UpdateHelper is required
#endif
#ifndef AppDisplayName
 #define AppDisplayName "SiC XRT Analyzer"
#endif
[Setup]
AppId={{{#AppGuid}}
AppName={#AppDisplayName}
AppVersion={#AppVersion}
AppPublisher=CrystalVision Lab
LicenseFile=..\LICENSE
AppPublisherURL=https://github.com/CrystalVision-Lab/sic-xrt-analyzer
DefaultDirName={localappdata}\Programs\CrystalVisionLab\SiCXrtAnalyzer
DefaultGroupName={#AppDisplayName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputPath}
OutputBaseFilename=SiCXrtAnalyzer-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
LZMANumBlockThreads=2
WizardStyle=modern
DisableProgramGroupPage=yes
ShowLanguageDialog=no
UninstallDisplayIcon={app}\SiCXrtAnalyzer.exe
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
SetupMutex=CrystalVisionLab_SicXrt_{#AppGuid}
UsePreviousAppDir=yes
[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "{#UpdateHelper}"; DestName: "XrtUpdateHandoff.exe"; Flags: dontcopy
Source: "{#BundleDir}\SiCXrtAnalyzer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BundleDir}\*"; DestDir: "{app}"; Excludes: "SiCXrtAnalyzer.exe"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "PYTHON-LICENSE.txt"; DestDir: "{app}\_internal"; Flags: ignoreversion
[InstallDelete]
; Only obsolete application-owned runtime payloads; never user images or settings.
Type: filesandordirs; Name: "{app}\_internal\runtimes\fiji\jars\linux64"
Type: filesandordirs; Name: "{app}\_internal\runtimes\fiji\jars\linux-arm64"
Type: filesandordirs; Name: "{app}\_internal\runtimes\fiji\jars\macos64"
Type: filesandordirs; Name: "{app}\_internal\runtimes\fiji\jars\macos-arm64"
Type: filesandordirs; Name: "{app}\_internal\runtimes\fiji\jars\macosx"
Type: filesandordirs; Name: "{app}\_internal\runtimes\openjdk\jmods"
Type: filesandordirs; Name: "{app}\_internal\PySide6\qml\QtWebEngine"
Type: filesandordirs; Name: "{app}\_internal\PySide6\qml\QtWebView"
Type: filesandordirs; Name: "{app}\_internal\PySide6\plugins\webview"
Type: files; Name: "{app}\_internal\runtimes\openjdk\lib\src.zip"
Type: files; Name: "{app}\_internal\PySide6\Qt6WebEngine*.dll"
Type: files; Name: "{app}\_internal\PySide6\Qt6WebView*.dll"
[Icons]
Name: "{group}\SiC XRT Analyzer"; Filename: "{app}\SiCXrtAnalyzer.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\SiC XRT Analyzer"; Filename: "{app}\SiCXrtAnalyzer.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\SiCXrtAnalyzer.exe"; WorkingDir: "{app}"; Flags: nowait skipifnotsilent; Check: ShouldLaunchUpdate
Filename: "{app}\SiCXrtAnalyzer.exe"; Description: "Launch SiC XRT Analyzer"; Flags: nowait postinstall skipifsilent; Check: RuntimeIsReady

[Code]
var RuntimeReady: Boolean;

function RuntimeIsReady(): Boolean;
begin
  Result := RuntimeReady;
end;

function GetCustomSetupExitCode(): Integer;
begin
  if RuntimeReady then Result := 0 else Result := 65;
end;

function IsXrtUpdate(): Boolean;
begin
  Result := ExpandConstant('{param:XRTUPDATE|0}') = '1';
end;

function ShouldLaunchUpdate(): Boolean;
begin
  Result := RuntimeReady and IsXrtUpdate() and (ExpandConstant('{param:XRTHANDOFF|0}') <> '1');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Code: Integer; Marker: String;
begin
  Marker := ExpandConstant('{app}\.xrt-install-incomplete');
  if CurStep = ssInstall then begin
    ForceDirectories(ExpandConstant('{app}'));
    if not SaveStringToFile(Marker, 'installation incomplete', False) then RaiseException('Cannot create installation marker');
  end;
  if CurStep = ssPostInstall then begin
    RuntimeReady := Exec(ExpandConstant('{app}\SiCXrtAnalyzer.exe'), '--verify-runtime', '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
    if RuntimeReady then RuntimeReady := DeleteFile(Marker);
    if not RuntimeReady then Log('Installed runtime integrity check failed; app launch disabled');
  end;
end;

function VerifiedLegacyUpdateCache(): Boolean;
var Name, Parent, Installed: String; I: Integer;
begin
  Result := False;
  Name := ExtractFileName(ExpandConstant('{srcexe}'));
  Parent := ExtractFileName(RemoveBackslashUnlessRoot(ExtractFileDir(ExpandConstant('{srcexe}'))));
  Log('Update cache check: ' + Name + ' / ' + Parent);
  if (Length(Name) <> 68) or (Lowercase(ExtractFileExt(Name)) <> '.exe') or (Lowercase(Parent) <> 'app-updates') then Exit;
  for I := 1 to 64 do
    if Pos(Lowercase(Name[I]), '0123456789abcdef') = 0 then Exit;
  if RegQueryStringValue(HKCU64, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#AppGuid}}_is1', 'InstallLocation', Installed) then
  begin
    Log('Existing installation: ' + Installed);
    Result := FileExists(AddBackslash(Installed) + 'SiCXrtAnalyzer.exe');
  end;
end;

function CurrentProcessId(): LongWord;
  external 'GetCurrentProcessId@kernel32.dll stdcall';

function InitializeSetup(): Boolean;
var ExitCode: Integer; Installed, Handoff, Params: String;
begin
  Result := True;
  { The old 0.2.0 caller provides only /NORESTART. A tiny sidecar waits for
    this setup to exit; setup must not execute itself during initialization. }
  if (ExpandConstant('{param:XRTHANDOFF|0}') <> '1') and VerifiedLegacyUpdateCache() then begin
    RegQueryStringValue(HKCU64, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#AppGuid}}_is1', 'InstallLocation', Installed);
    ExtractTemporaryFile('XrtUpdateHandoff.exe');
    Handoff := ChangeFileExt(ExpandConstant('{srcexe}'), '.handoff.exe');
    if FileCopy(ExpandConstant('{tmp}\XrtUpdateHandoff.exe'), Handoff, False) then begin
      Params := IntToStr(CurrentProcessId()) + ' "' + ExpandConstant('{srcexe}') + '" "' + RemoveBackslashUnlessRoot(Installed) + '"';
      if Exec(Handoff, Params, '', SW_HIDE, ewNoWait, ExitCode) then Result := False;
    end;
  end;
end;
