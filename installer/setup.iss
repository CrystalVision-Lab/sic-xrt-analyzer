#ifndef AppVersion
 #define AppVersion "0.1.0"
#endif
#ifndef BundleDir
 #error BundleDir is required
#endif
#ifndef OutputPath
 #error OutputPath is required
#endif
[Setup]
AppId={{81CAB3F6-F3BE-4B05-ACB8-E9F47113CC32}
AppName=SiC XRT Analyzer
AppVersion={#AppVersion}
AppPublisher=CrystalVision Lab
LicenseFile=..\LICENSE
AppPublisherURL=https://github.com/CrystalVision-Lab/sic-xrt-analyzer
DefaultDirName={localappdata}\Programs\CrystalVisionLab\SiCXrtAnalyzer
DefaultGroupName=SiC XRT Analyzer
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
UninstallDisplayIcon={app}\SiCXrtAnalyzer.exe
CloseApplications=yes
[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "PYTHON-LICENSE.txt"; DestDir: "{app}\_internal"; Flags: ignoreversion
[Icons]
Name: "{group}\SiC XRT Analyzer"; Filename: "{app}\SiCXrtAnalyzer.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\SiC XRT Analyzer"; Filename: "{app}\SiCXrtAnalyzer.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\SiCXrtAnalyzer.exe"; Description: "Launch SiC XRT Analyzer"; Flags: nowait postinstall skipifsilent
