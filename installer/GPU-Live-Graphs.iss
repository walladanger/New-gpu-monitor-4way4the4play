; Per-user installer. Source: https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm
#ifndef MyAppVersion
  #define MyAppVersion "0.5.0"
#endif
[Setup]
AppId={{C61F3A9C-E33F-4EEC-948F-ED08EAB114E8}
AppName=GPU Live Graphs
AppVersion={#MyAppVersion}
AppPublisher=walladanger
AppPublisherURL=https://github.com/walladanger/New-gpu-monitor-4way4the4play
DefaultDirName={localappdata}\Programs\GPU Live Graphs
DefaultGroupName=GPU Live Graphs
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=GPU-Live-Graphs-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\GPU-Live-Graphs.exe
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
[Files]
Source: "..\dist\GPU-Live-Graphs\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\GPU Live Graphs"; Filename: "{app}\GPU-Live-Graphs.exe"
Name: "{autodesktop}\GPU Live Graphs"; Filename: "{app}\GPU-Live-Graphs.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\GPU-Live-Graphs.exe"; Description: "Launch GPU Live Graphs"; Flags: nowait postinstall skipifsilent
; User history/preferences/exports are intentionally outside {app} and retained.
