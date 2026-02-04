; FexoBooth Inno Setup Script
; Erstellt einen professionellen Windows-Installer

#define MyAppName "FexoBooth"
#define MyAppVersion "2.0"
#define MyAppPublisher "FexoBox"
#define MyAppURL "https://github.com/fexobox/fexobooth-v2"
#define MyAppExeName "FexoBooth.exe"

[Setup]
; Grundlegende Installer-Informationen
AppId={{F3X0B00TH-2024-0001-0001-000000000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installationspfad
DefaultDirName=C:\FexoBooth
UsePreviousAppDir=yes
DisableDirPage=no
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Update-Verhalten
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=yes

; Ausgabedatei
OutputDir=installer_output
OutputBaseFilename=FexoBooth_Setup_{#MyAppVersion}
SetupIconFile=assets\icons\camera.ico
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Windows-Version
MinVersion=10.0
PrivilegesRequired=admin

; Installer-Design
WizardStyle=modern
WizardSizePercent=120

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "FexoBooth beim Windows-Start automatisch starten"; GroupDescription: "Autostart:"

[Files]
; Hauptanwendung (PyInstaller Output)
Source: "dist\FexoBooth\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; BAT-Dateien für verschiedene Modi
Source: "installer_files\start_fexobooth.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "installer_files\start_dev.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "installer_files\update_from_github.bat"; DestDir: "{app}"; Flags: ignoreversion

; Setup-Skripte
Source: "setup\*"; DestDir: "{app}\setup"; Flags: ignoreversion recursesubdirs createallsubdirs

; Beispiel-Konfiguration
Source: "config.example.json"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Erstelle wichtige Verzeichnisse
Name: "{app}\BILDER"
Name: "{app}\BILDER\Prints"
Name: "{app}\BILDER\Single"
Name: "{app}\logs"
Name: "{app}\.booking_cache"

[Icons]
; Startmenü-Einträge
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} (Entwicklermodus)"; Filename: "{app}\start_dev.bat"; IconFilename: "{app}\assets\icons\camera.ico"
Name: "{group}\Von GitHub aktualisieren"; Filename: "{app}\update_from_github.bat"
Name: "{group}\Hotspot einrichten (Einmalig)"; Filename: "{app}\setup\einmalig_hotspot_einrichten.bat"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Desktop-Icon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; Autostart
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart

[Run]
; Nach Installation ausführen
Filename: "{app}\setup\einmalig_hotspot_einrichten.bat"; Description: "WLAN-Hotspot für Galerie einrichten (empfohlen)"; Flags: postinstall nowait skipifsilent runascurrentuser unchecked
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: postinstall nowait skipifsilent

[Code]
// Prüfe ob bereits eine Installation existiert
function InitializeSetup(): Boolean;
begin
  Result := True;
  if DirExists('C:\FexoBooth') then
  begin
    if MsgBox('FexoBooth ist bereits installiert. Möchten Sie die bestehende Installation aktualisieren?', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;

// Erstelle config.json aus config.example.json falls nicht vorhanden
procedure CurStepChanged(CurStep: TSetupStep);
var
  ExampleConfig: String;
  ActualConfig: String;
begin
  if CurStep = ssPostInstall then
  begin
    ExampleConfig := ExpandConstant('{app}\config.example.json');
    ActualConfig := ExpandConstant('{app}\config.json');

    if not FileExists(ActualConfig) then
    begin
      FileCopy(ExampleConfig, ActualConfig, False);
    end;
  end;
end;

[UninstallDelete]
; Lösche Log-Dateien bei Deinstallation
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\.booking_cache"
