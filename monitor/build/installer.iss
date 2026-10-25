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
; Selecting an existing Sentinel folder should repair that folder, not nest another \Sentinel.
AppendDefaultDirName=no
DirExistsWarning=no
UsePreviousAppDir=yes
OutputBaseFilename=Sentinel-Setup
SetupIconFile=sentinel.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
CloseApplicationsFilter=Sentinel.exe,gnbot-monitor.exe,SentinelTray.exe,SentinelSetup.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Repair installs replace program files only. config.json and logs stay on disk.
Source: "..\dist\GnBotsMonitor-Release\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "config.json,logs,logs\*,watcher.lock,watcher-status.json"

[Icons]
Name: "{group}\{#MyAppName} Setup"; Filename: "{app}\SentinelSetup.exe"
Name: "{group}\Open Dashboard"; Filename: "http://127.0.0.1:8787/"
Name: "{group}\Start Stack"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\SentinelSetup.exe"; Description: "Run setup wizard"; Flags: postinstall nowait skipifsilent; Check: ShouldRunSetupWizard

[Code]
var
  RepairInstall: Boolean;

function IsSentinelInstallDir(Dir: String): Boolean;
begin
  Dir := AddBackslash(RemoveBackslashUnlessRoot(Dir));
  Result :=
    FileExists(Dir + 'Sentinel.exe') or
    FileExists(Dir + 'gnbot-monitor.exe') or
    (FileExists(Dir + 'config.json') and FileExists(Dir + 'version.json'));
end;

function FirstExistingSentinelDir: String;
begin
  Result := '';
  if IsSentinelInstallDir(ExpandConstant('{autopf}\Sentinel')) then
    Result := ExpandConstant('{autopf}\Sentinel')
  else if IsSentinelInstallDir(ExpandConstant('{localappdata}\Programs\Sentinel')) then
    Result := ExpandConstant('{localappdata}\Programs\Sentinel')
  else if IsSentinelInstallDir(ExpandConstant('{localappdata}\Sentinel')) then
    Result := ExpandConstant('{localappdata}\Sentinel')
  else if IsSentinelInstallDir(ExpandConstant('{userdocs}\Sentinel')) then
    Result := ExpandConstant('{userdocs}\Sentinel');
end;

function ShouldRunSetupWizard: Boolean;
begin
  { Existing installs keep config.json. Do not run the wizard over those settings. }
  Result := not RepairInstall;
end;

procedure InitializeWizard;
var
  Current, Found: String;
begin
  Current := WizardForm.DirEdit.Text;
  if IsSentinelInstallDir(Current) then
  begin
    RepairInstall := True;
    Exit;
  end;
  Found := FirstExistingSentinelDir;
  if Found <> '' then
  begin
    WizardForm.DirEdit.Text := Found;
    RepairInstall := True;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Dir, Nested: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    Dir := RemoveBackslashUnlessRoot(WizardDirValue);
    Nested := AddBackslash(Dir) + 'Sentinel';
    if (not IsSentinelInstallDir(Dir)) and IsSentinelInstallDir(Nested) then
    begin
      WizardForm.DirEdit.Text := Nested;
      Dir := Nested;
    end;
    RepairInstall := IsSentinelInstallDir(Dir);
    if RepairInstall then
      MsgBox(
        'Sentinel is already installed in this folder.' + #13#10 +
        'Program files will be repaired. Your settings (config.json and logs) will be kept.',
        mbInformation, MB_OK);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  RepairInstall := IsSentinelInstallDir(ExpandConstant('{app}'));
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigPath, ExamplePath: String;
begin
  if CurStep = ssPostInstall then
  begin
    ForceDirectories(ExpandConstant('{app}\logs'));
    ConfigPath := ExpandConstant('{app}\config.json');
    ExamplePath := ExpandConstant('{app}\config.example.json');
    { Never replace an existing config — repair must keep GnBots paths and other settings. }
    if (not FileExists(ConfigPath)) and FileExists(ExamplePath) then
      FileCopy(ExamplePath, ConfigPath, True);
  end;
end;
