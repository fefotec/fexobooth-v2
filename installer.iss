; FexoBooth Inno Setup Script
; Erstellt einen professionellen Windows-Installer

#define MyAppName "FexoBooth"
; MyAppVersion kann beim ISCC-Aufruf via /DMyAppVersion=2.4.4 ueberschrieben
; werden. build_installer.bat liest die echte App-Version aus src/__init__.py
; und uebergibt sie als Parameter — dann heisst die EXE z.B. FexoBooth_Setup_2.4.4.exe.
; Default fuer manuelle ISCC-Aufrufe ohne Parameter:
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
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
UsePreviousTasks=no
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
Name: "disableupdates"; Description: "Windows Update dauerhaft deaktivieren (empfohlen fuer Photobooth-Betrieb)"; GroupDescription: "Systemoptimierung:"

[Files]
; Hauptanwendung (PyInstaller Output)
Source: "installer_output\fexobooth\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Icon separat kopieren (PyInstaller legt Assets in _internal/assets/ ab,
; aber Desktop-Shortcut braucht {app}\assets\fexobooth.ico)
Source: "assets\fexobooth.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

; BAT-Dateien für verschiedene Modi
Source: "installer_files\start_fexobooth.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "installer_files\start_dev.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "update_from_github.bat"; DestDir: "{app}"; Flags: ignoreversion

; Setup-Skripte
Source: "setup\*"; DestDir: "{app}\setup"; Flags: ignoreversion recursesubdirs createallsubdirs

; Deployment-Tools (Image-Vorbereitung)
Source: "deployment\01_referenz-tablet\prepare_image.bat"; DestDir: "{app}\deployment"; Flags: ignoreversion
Source: "deployment\01_referenz-tablet\post_install_check.bat"; DestDir: "{app}\deployment"; Flags: ignoreversion

; Beispiel-Konfiguration
Source: "config.example.json"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Erstelle wichtige Verzeichnisse
Name: "{app}\BILDER"
Name: "{app}\BILDER\Prints"
Name: "{app}\BILDER\Single"
Name: "{app}\logs"
; .booking_cache wird NICHT vorab erstellt — entsteht erst im Produktionsbetrieb
; wenn ein USB-Stick mit Event-Daten eingesteckt wird

[Icons]
; Startmenü-Einträge
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\fexobooth.ico"
Name: "{group}\{#MyAppName} (Entwicklermodus)"; Filename: "{app}\start_dev.bat"; IconFilename: "{app}\assets\fexobooth.ico"
Name: "{group}\Von GitHub aktualisieren"; Filename: "{app}\update_from_github.bat"
Name: "{group}\Hotspot einrichten (Einmalig)"; Filename: "{app}\setup\einmalig_hotspot_einrichten.bat"
Name: "{group}\Image vorbereiten (Deployment)"; Filename: "{app}\deployment\prepare_image.bat"
Name: "{group}\Tablet-Pruefung (Deployment)"; Filename: "{app}\deployment\post_install_check.bat"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Desktop-Icon IMMER erstellen/überschreiben bei Installation (nicht nur bei Task-Auswahl)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\fexobooth.ico"; IconIndex: 0

; Autostart (für alle Benutzer, da Admin-Installation)
Name: "{commonstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart; IconFilename: "{app}\assets\fexobooth.ico"

[Run]
; Windows Update deaktivieren (wenn Checkbox ausgewaehlt)
; Laeuft synchron und legt zusaetzlich Boot/Login-Tasks an, die die Policy
; erneut setzen, falls Windows Update Medic/Orchestrator etwas reaktiviert.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup\disable_windows_update.ps1"" -InstallDir ""{app}"""; Tasks: disableupdates; Flags: runhidden waituntilterminated; StatusMsg: "Windows Update wird dauerhaft deaktiviert..."

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
  LegacyConfig: String;
begin
  if CurStep = ssPostInstall then
  begin
    ExampleConfig := ExpandConstant('{app}\config.example.json');
    ActualConfig := ExpandConstant('{app}\config.json');
    LegacyConfig := ExpandConstant('{app}\_internal\config.json');

    if not FileExists(ActualConfig) then
    begin
      if FileExists(LegacyConfig) then
      begin
        FileCopy(LegacyConfig, ActualConfig, False);
      end
      else
      begin
        FileCopy(ExampleConfig, ActualConfig, False);
      end;
    end;

    // Shell benachrichtigen: Icon-Cache neu laden (SHCNE_ASSOCCHANGED)
    SHChangeNotify($8000000, 0, 0, 0);
  end;
end;

[InstallDelete]
; Bei Neuinstallation: Statistiken und Druckerzähler zurücksetzen (sauberer Start)
Type: files; Name: "{app}\fexobooth_statistics.json"
Type: files; Name: "{app}\printer_lifetime.json"
Type: files; Name: "{app}\_internal\fexobooth_statistics.json"
Type: files; Name: "{app}\_internal\printer_lifetime.json"
; Booking-Cache an BEIDEN möglichen Pfaden löschen (App-Root UND PyInstaller _internal)
Type: filesandordirs; Name: "{app}\.booking_cache"
Type: filesandordirs; Name: "{app}\_internal\.booking_cache"

[UninstallDelete]
; Lösche Log-Dateien bei Deinstallation
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\.booking_cache"
Type: filesandordirs; Name: "{app}\_internal\.booking_cache"
Type: files; Name: "{app}\fexobooth_statistics.json"
Type: files; Name: "{app}\printer_lifetime.json"
Type: files; Name: "{app}\_internal\fexobooth_statistics.json"
Type: files; Name: "{app}\_internal\printer_lifetime.json"
