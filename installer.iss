; FexoBooth Inno Setup Script
; Erstellt einen professionellen Windows-Installer

#define MyAppName "FexoBooth"
#define MyAppVersion "2.0"
#define MyAppPublisher "FexoBox"
#define MyAppURL "https://github.com/fefotec/fexobooth-v2"
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
SetupIconFile=assets\fexobooth.ico
Compression=lzma2/normal
SolidCompression=yes

; Windows-Version
MinVersion=10.0
PrivilegesRequired=admin

; Installer-Design
WizardStyle=modern
WizardSizePercent=120

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "FexoBooth beim Windows-Start automatisch starten"; GroupDescription: "Autostart:"

[Files]
; Hauptanwendung (PyInstaller Output)
Source: "installer_output\fexobooth\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Icon separat kopieren (PyInstaller legt Assets in _internal/assets/ ab,
; aber Desktop-Shortcut braucht {app}\assets\fexobooth.ico)
Source: "assets\fexobooth.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

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
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\fexobooth.ico"
Name: "{group}\{#MyAppName} (Entwicklermodus)"; Filename: "{app}\start_dev.bat"; IconFilename: "{app}\assets\fexobooth.ico"
Name: "{group}\Von GitHub aktualisieren"; Filename: "{app}\update_from_github.bat"
Name: "{group}\Hotspot einrichten (Einmalig)"; Filename: "{app}\setup\einmalig_hotspot_einrichten.bat"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Desktop-Icon IMMER erstellen/überschreiben bei Installation (nicht nur bei Task-Auswahl)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\fexobooth.ico"; IconIndex: 0

; Autostart (für alle Benutzer, da Admin-Installation)
Name: "{commonstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart; IconFilename: "{app}\assets\fexobooth.ico"

[Run]
; Windows Icon-Cache per PowerShell löschen (erzwingt Rebuild beim nächsten Explorer-Start)
; ie4uinit.exe existiert nicht auf allen Geräten (z.B. Lenovo Miix 310), daher nur PowerShell
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Remove-Item -Path $env:LOCALAPPDATA\IconCache.db -Force -ErrorAction SilentlyContinue; Remove-Item -Path $env:LOCALAPPDATA\Microsoft\Windows\Explorer\iconcache_*.db -Force -ErrorAction SilentlyContinue"""; Flags: runhidden nowait; StatusMsg: "Aktualisiere Icon-Cache..."
; Nach Installation ausführen
Filename: "{app}\setup\einmalig_hotspot_einrichten.bat"; Description: "WLAN-Hotspot für Galerie einrichten (empfohlen)"; Flags: postinstall nowait skipifsilent runascurrentuser unchecked
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: postinstall nowait skipifsilent

[Code]
// Shell32 SHChangeNotify - benachrichtigt Explorer über Icon-Änderungen
procedure SHChangeNotify(wEventId, uFlags: Integer; dwItem1, dwItem2: Integer);
  external 'SHChangeNotify@shell32.dll stdcall';

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

// Nach Installation: Config erstellen + Shell über neue Icons benachrichtigen
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

    // Shell benachrichtigen: Icon-Cache neu laden (SHCNE_ASSOCCHANGED)
    SHChangeNotify($8000000, 0, 0, 0);
  end;
end;

[UninstallDelete]
; Lösche Log-Dateien bei Deinstallation
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\.booking_cache"
