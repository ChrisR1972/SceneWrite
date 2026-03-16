; Inno Setup Script for SceneWrite
; Download Inno Setup from https://jrsoftware.org/isinfo.php
; Open this file in Inno Setup Compiler and click Build > Compile

#define MyAppName "SceneWrite"
#define MyAppVersion "1.0.0"
; Keep version in sync with main.py setApplicationVersion and help_dialogs.py
#define MyAppPublisher "SceneWrite"
#define MyAppExeName "SceneWrite.exe"

[Setup]
AppId={{A3F7B2C1-9D4E-4A6F-8E3B-1C5D7F9A2E4B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputBaseFilename=SceneWrite_Setup_{#MyAppVersion}
SetupIconFile=SceneWrite_Logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
OutputDir=installer_output
; In-place upgrade support: reuse previous install location, close the
; running app before overwriting, and show the version to the user.
UsePreviousAppDir=yes
CloseApplications=yes
RestartApplications=no
AppVerName={#MyAppName} {#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}";

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "SceneWrite_Logo.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\SceneWrite_Logo.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\SceneWrite_Logo.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
