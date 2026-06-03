#define AppName "BEAN & BREW Cafe Kiosk"
#define AppPublisher "이지우"
#ifndef AppVersion
#define AppVersion "1.1.5"
#endif
#define SourceRoot "..\.."

[Setup]
AppId={{A5D3ED81-DA59-4C51-9D16-5F3E58B32F6B}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\BEAN_BREW_Cafe_Kiosk
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#SourceRoot}\dist
OutputBaseFilename=CafeKiosk-Windows-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName}

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Files]
Source: "{#SourceRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\VERSION"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\requirements-windows.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\install_windows.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\run_windows.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\cafe_kiosk\*"; DestDir: "{app}\cafe_kiosk"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,.vs\*,.vscode\*,*.pyc,*.pyo,*.db,*.db-*,*.json,tts_cache\*"

[Icons]
Name: "{autodesktop}\BEAN & BREW Cafe Kiosk"; Filename: "{app}\run_windows.cmd"; WorkingDir: "{app}"
Name: "{group}\BEAN & BREW Cafe Kiosk"; Filename: "{app}\run_windows.cmd"; WorkingDir: "{app}"
Name: "{group}\설치/복구 실행"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\install_windows.ps1"""; WorkingDir: "{app}"

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\install_windows.ps1"" -NoShortcut"; WorkingDir: "{app}"; StatusMsg: "필수 Python 패키지를 설치하는 중입니다..."; Flags: runascurrentuser
