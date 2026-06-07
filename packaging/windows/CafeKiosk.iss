#define AppName "BEAN & BREW Cafe Kiosk"
#define AppPublisher "이지우"
#ifndef AppVersion
#define AppVersion "1.2.6"
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
Source: "{#SourceRoot}\uninstall_windows.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\run_windows.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\launch_windows.pyw"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\cafe_kiosk\*"; DestDir: "{app}\cafe_kiosk"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,.vs\*,.vscode\*,*.pyc,*.pyo,*.db,*.db-*,*.json,tts_cache\*"

[Icons]
Name: "{autodesktop}\BEAN & BREW Cafe Kiosk"; Filename: "{app}\run_windows.cmd"; WorkingDir: "{app}"
Name: "{group}\BEAN & BREW Cafe Kiosk"; Filename: "{app}\run_windows.cmd"; WorkingDir: "{app}"
Name: "{group}\설치/복구 실행"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\install_windows.ps1"""; WorkingDir: "{app}"

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\install_windows.ps1"" -NoShortcut"; WorkingDir: "{app}"; StatusMsg: "필수 Python 패키지를 설치하는 중입니다..."; Flags: runascurrentuser

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall_windows.ps1"""; WorkingDir: "{app}"; Flags: runhidden; RunOnceId: "CafeKioskCleanup"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv-windows"
Type: filesandordirs; Name: "{app}\install_logs"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\cafe_kiosk\tts_cache"
Type: filesandordirs; Name: "{app}\cafe_kiosk\__pycache__"
Type: files; Name: "{app}\cafe_kiosk\*.json"
Type: files; Name: "{app}\cafe_kiosk\*.db"
Type: files; Name: "{app}\cafe_kiosk\*.db-*"
Type: files; Name: "{app}\cafe_kiosk\*.log"
Type: files; Name: "{app}\cafe_kiosk\*.tmp"
Type: files; Name: "{app}\cafe_kiosk\*.pyc"
Type: files; Name: "{app}\cafe_kiosk\*.pyo"
Type: dirifempty; Name: "{app}\cafe_kiosk"
Type: filesandordirs; Name: "{userappdata}\BEAN_BREW_Cafe_Kiosk"
Type: filesandordirs; Name: "{%TEMP}\bean_brew_cafe_kiosk_updates"
Type: filesandordirs; Name: "{%TEMP}\bean_brew_cafe_kiosk_restore_extract"
Type: filesandordirs; Name: "{%TEMP}\bean_brew_portable_update_extract"
Type: filesandordirs; Name: "{%TEMP}\bean_brew_portable_update_restore"
Type: files; Name: "{%TEMP}\bean_brew_portable_update.ps1"
Type: dirifempty; Name: "{app}"
