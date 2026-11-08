; WinTidy installer (Inno Setup 6). Build: ISCC.exe WinTidy.iss  (needs dist\WinTidy.exe first)
[Setup]
AppId={{7D1C3E52-4B8A-4F6E-9A21-0C5E8B7F1D33}
AppName=WinTidy
AppVersion=1.0
AppPublisher=WinTidy
DefaultDirName={autopf}\WinTidy
DefaultGroupName=WinTidy
PrivilegesRequired=admin
OutputDir=installer
OutputBaseFilename=WinTidy-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=WinTidy.ico
UninstallDisplayIcon={app}\WinTidy.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\WinTidy.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\WinTidy"; Filename: "{app}\WinTidy.exe"
Name: "{autodesktop}\WinTidy"; Filename: "{app}\WinTidy.exe"; Tasks: desktopicon
