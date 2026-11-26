; Claude Krita Bridge installer (Inno Setup 6). Built by installer\build.ps1 - see docs/BUILDING.md.
; Installs per user (no admin): the MCP server + its own small Python, the Krita plugin (switched on), and
; optionally registers it with Claude Code. The optional AI tools are NOT installed (see ai_tools/README.md).
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#ifndef StageDir
  #define StageDir "build\stage-krita"
#endif
#define MyAppName "Claude Krita Bridge"
#define RepoUrl "https://github.com/xoxoFaith1993/claude-krita-bridge"

[Setup]
AppId={{4D7E1A90-6B2C-4F83-9E15-C2A8B73F0D46}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=claude-krita-bridge contributors
AppPublisherURL={#RepoUrl}
AppSupportURL={#RepoUrl}/issues
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Claude-Krita-Bridge-Setup-{#MyAppVersion}
LicenseFile={#StageDir}\LICENSE
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "plugin"; Description: "Install and switch on the Claude Bridge plugin in Krita (close Krita first)"; GroupDescription: "Krita:"
Name: "mcp"; Description: "Register the krita tools with Claude Code (claude mcp add)"; GroupDescription: "Claude Code:"

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#MyAppName}\Setup guide"; Filename: "{#RepoUrl}/blob/main/docs/SETUP.md"
Name: "{userprograms}\{#MyAppName}\Uninstall"; Filename: "{uninstallexe}"

[Dirs]
Name: "{userappdata}\claude-krita-bridge"; Flags: uninsneveruninstall

[Run]
Filename: "{app}\python\python.exe"; Parameters: """{app}\install_plugin.py"""; StatusMsg: "Installing the Krita plugin..."; Flags: runhidden; Tasks: plugin
Filename: "{app}\python\python.exe"; Parameters: """{app}\tools\connect_claude.py"""; StatusMsg: "Connecting to Claude Code..."; Flags: runhidden; Tasks: mcp
Filename: "{app}\CONNECT_CLAUDE.txt"; Description: "Show how to connect Claude Code (the claude command was not found)"; Flags: postinstall shellexec skipifsilent; Check: NeedsConnectNote
Filename: "{#RepoUrl}/blob/main/docs/SETUP.md"; Description: "Open the setup guide"; Flags: postinstall shellexec skipifsilent

[UninstallRun]
; only undo what this install set up (markers written after install)
Filename: "{app}\python\python.exe"; Parameters: """{app}\install_plugin.py"" --uninstall"; Flags: runhidden; RunOnceId: "RemovePlugin"; Check: TaskWasDone('plugin')
Filename: "{app}\python\python.exe"; Parameters: """{app}\tools\connect_claude.py"" --remove"; Flags: runhidden; RunOnceId: "DisconnectClaude"; Check: TaskWasDone('mcp')

[UninstallDelete]
Type: filesandordirs; Name: "{app}\server\__pycache__"
Type: filesandordirs; Name: "{app}\tools\__pycache__"
Type: filesandordirs; Name: "{app}\tests\__pycache__"
Type: files; Name: "{app}\CONNECT_CLAUDE.txt"
Type: files; Name: "{app}\task-*.done"

[Code]
{ remember which optional steps ran, so the uninstaller undoes only those }
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if WizardIsTaskSelected('plugin') then SaveStringToFile(ExpandConstant('{app}\task-plugin.done'), 'yes', False);
    if WizardIsTaskSelected('mcp') then SaveStringToFile(ExpandConstant('{app}\task-mcp.done'), 'yes', False);
  end;
end;

function TaskWasDone(Name: String): Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\task-' + Name + '.done'));
end;

function NeedsConnectNote: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\CONNECT_CLAUDE.txt'));
end;
