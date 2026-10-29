; Inno Setup script for the Kokoro TTS server (Windows).
;
; Compiled in CI (.github/workflows/release-installer.yml) on a Windows runner;
; pass the version with /DAppVersion=x.y.z. Produces a small per-user installer
; that copies the server sources, bootstraps uv + dependencies on install, runs
; the server from a system-tray app (no console window), and can auto-start on
; login. Heavy ML dependencies (torch, kokoro) and the model weights are NOT
; bundled — uv installs/downloads them at setup time, keeping the installer tiny.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{4B1D9E7A-3C2F-4A8B-9E6D-1A2B3C4D5E6F}
AppName=PageVoice Server
AppVersion={#AppVersion}
AppPublisher=davuses
DefaultDirName={localappdata}\KokoroTTSServer
DefaultGroupName=PageVoice Server
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=kokoro-tts-server-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Start PageVoice Server automatically when I sign in"; GroupDescription: "Startup:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\server.py";        DestDir: "{app}"; Flags: ignoreversion
Source: "..\app_logging.py";   DestDir: "{app}"; Flags: ignoreversion
Source: "..\kokoro_model.py";  DestDir: "{app}"; Flags: ignoreversion
Source: "..\engines.py";       DestDir: "{app}"; Flags: ignoreversion
Source: "..\tray.py";          DestDir: "{app}"; Flags: ignoreversion
Source: "..\pyproject.toml";   DestDir: "{app}"; Flags: ignoreversion
Source: "..\uv.lock";          DestDir: "{app}"; Flags: ignoreversion
Source: "..\dependency-version.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\.python-version";  DestDir: "{app}"; Flags: ignoreversion
Source: "..\setup.bat";        DestDir: "{app}"; Flags: ignoreversion
Source: "..\start-tray.vbs";   DestDir: "{app}"; Flags: ignoreversion
Source: "..\start-server.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md";        DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\PageVoice Server"; Filename: "wscript.exe"; Parameters: """{app}\start-tray.vbs"""; WorkingDir: "{app}"; Comment: "Start PageVoice Server in the background (tray icon)"
Name: "{group}\Uninstall PageVoice Server"; Filename: "{uninstallexe}"
Name: "{userdesktop}\PageVoice Server"; Filename: "wscript.exe"; Parameters: """{app}\start-tray.vbs"""; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\PageVoice Server"; Filename: "wscript.exe"; Parameters: """{app}\start-tray.vbs"""; WorkingDir: "{app}"; Tasks: autostart

[InstallDelete]
; Remove only the superseded shortcuts; preserve the install directory/AppId.
Type: files; Name: "{userprograms}\Kokoro TTS Server\Kokoro TTS Server.lnk"
Type: files; Name: "{userprograms}\Kokoro TTS Server\Uninstall Kokoro TTS Server.lnk"
Type: files; Name: "{userdesktop}\Kokoro TTS Server.lnk"
Type: files; Name: "{userstartup}\Kokoro TTS Server.lnk"

[Run]
; Do NOT run setup during install: the installer's process tree enforces a
; reparse-point mitigation that fails on redirected profiles ("untrusted mount
; point", os error 448). Instead, launch the app through Explorer so it runs in
; the user's shell context; start-tray.vbs builds the environment on first run
; (a few-minute, one-time download) and then starts the tray.
Filename: "{win}\explorer.exe"; Parameters: """{app}\start-tray.vbs"""; Description: "Set up and start PageVoice Server now (first run downloads dependencies)"; Flags: postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\.pytest_cache"
Type: files; Name: "{app}\gpu.flag"
Type: files; Name: "{app}\server.log"
Type: files; Name: "{app}\.environment-ready"
