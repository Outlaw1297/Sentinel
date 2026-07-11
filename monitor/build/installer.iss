; Inno Setup script for Sentinel monitor portable release.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define MyAppName "Sentinel"
#define MyAppVersion AppVersion
#define MyAppPublisher "Sentinel"
#define MyAppExeName "Sentinel.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Sentinel
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=GnBotsMonitor-Setup
SetupIconFile=sentinel.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\GnBotsMonitor-Release\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName} Setup"; Filename: "{app}\SentinelSetup.exe"
Name: "{group}\Open Dashboard"; Filename: "http://127.0.0.1:8787/"
Name: "{group}\Start Stack"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\SentinelSetup.exe"; Description: "Run setup wizard"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"

[Code]
function InitializeUninstall(): Boolean;
begin
  Result := True;
  if MsgBox('Preserve config.json and logs folder?', mbConfirmation, MB_YESNO) = IDYES then
  begin
    // User data kept by default — only remove program files via [Files] uninstall.
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigPath, ExamplePath: String;
begin
  if CurStep = ssPostInstall then
  begin
    ConfigPath := ExpandConstant('{app}\config.json');
    ExamplePath := ExpandConstant('{app}\config.example.json');
    if (not FileExists(ConfigPath)) and FileExists(ExamplePath) then
      FileCopy(ExamplePath, ConfigPath, False);
  end;
end;
