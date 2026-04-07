@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo.
echo ===================================================
echo    FexoBooth - Tablet fuer Image vorbereiten
echo ===================================================
echo.
echo Dieses Script:
echo   1. Konfiguriert Windows auf Minimal-Einstellungen
echo   2. Deaktiviert unnoetige Dienste und Features
echo   3. Loescht alle Bilder, Logs und Caches
echo   4. Raeumt Temp-Dateien auf
echo.
echo ACHTUNG: Nur auf dem Referenz-Tablet ausfuehren,
echo          BEVOR das Clonezilla-Image erstellt wird!
echo.

:: Admin-Check
net session >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Dieses Script muss als Administrator ausgefuehrt werden!
    echo          Rechtsklick → "Als Administrator ausfuehren"
    echo.
    pause
    exit /b 1
)

echo Weiter mit beliebiger Taste...
pause >nul
echo.

:: ═══════════════════════════════════════════════
::  TEIL 1: WINDOWS DIENSTE DEAKTIVIEREN
:: ═══════════════════════════════════════════════

echo ---------------------------------------------------
echo  TEIL 1: Unnoetige Windows-Dienste deaktivieren
echo ---------------------------------------------------
echo.

:: Windows Update (komplett)
for %%S in (wuauserv WaaSMedicSvc UsoSvc DoSvc) do (
    sc stop %%S >nul 2>&1
    sc config %%S start=disabled >nul 2>&1
    echo [OK] %%S deaktiviert
)

:: Windows Search (braucht kein Mensch auf der Fotobox)
sc stop WSearch >nul 2>&1
sc config WSearch start=disabled >nul 2>&1
echo [OK] Windows Search (WSearch) deaktiviert

:: Superfetch / SysMain (RAM-Fresser auf schwacher Hardware)
sc stop SysMain >nul 2>&1
sc config SysMain start=disabled >nul 2>&1
echo [OK] SysMain/Superfetch deaktiviert

:: Windows Defender (offline Geraet, kein Risiko, frisst CPU)
sc stop WinDefend >nul 2>&1
sc config WinDefend start=disabled >nul 2>&1
echo [OK] Windows Defender Dienst deaktiviert

sc stop WdNisSvc >nul 2>&1
sc config WdNisSvc start=disabled >nul 2>&1
echo [OK] Defender Network Inspection deaktiviert

:: Diagnostics & Telemetrie
for %%S in (DiagTrack dmwappushservice diagnosticshub.standardcollector.service) do (
    sc stop %%S >nul 2>&1
    sc config %%S start=disabled >nul 2>&1
    echo [OK] %%S deaktiviert
)

:: Windows Error Reporting
sc stop WerSvc >nul 2>&1
sc config WerSvc start=disabled >nul 2>&1
echo [OK] Windows Error Reporting deaktiviert

:: Connected User Experiences (Telemetrie)
sc stop CDPUserSvc >nul 2>&1
sc config CDPUserSvc start=disabled >nul 2>&1
echo [OK] Connected User Experiences deaktiviert

:: Xbox Game Services (voellig unnoetig)
for %%S in (XblAuthManager XblGameSave XboxNetApiSvc XboxGipSvc) do (
    sc stop %%S >nul 2>&1
    sc config %%S start=disabled >nul 2>&1
)
echo [OK] Xbox-Dienste deaktiviert

:: Maps Broker
sc stop MapsBroker >nul 2>&1
sc config MapsBroker start=disabled >nul 2>&1
echo [OK] Maps Broker deaktiviert

:: Remote Registry
sc stop RemoteRegistry >nul 2>&1
sc config RemoteRegistry start=disabled >nul 2>&1
echo [OK] Remote Registry deaktiviert

:: Fax
sc stop Fax >nul 2>&1
sc config Fax start=disabled >nul 2>&1
echo [OK] Fax-Dienst deaktiviert

:: Bluetooth (Fotobox braucht kein BT)
for %%S in (bthserv BTAGService BthAvctpSvc) do (
    sc stop %%S >nul 2>&1
    sc config %%S start=disabled >nul 2>&1
)
echo [OK] Bluetooth-Dienste deaktiviert

:: Windows Biometric Service
sc stop WbioSrvc >nul 2>&1
sc config WbioSrvc start=disabled >nul 2>&1
echo [OK] Biometrie-Dienst deaktiviert

:: Retail Demo Service
sc stop RetailDemo >nul 2>&1
sc config RetailDemo start=disabled >nul 2>&1
echo [OK] Retail Demo deaktiviert

:: Windows Insider
sc stop wisvc >nul 2>&1
sc config wisvc start=disabled >nul 2>&1
echo [OK] Windows Insider deaktiviert

echo.

:: ═══════════════════════════════════════════════
::  TEIL 2: REGISTRY - PERFORMANCE & DATENSCHUTZ
:: ═══════════════════════════════════════════════

echo ---------------------------------------------------
echo  TEIL 2: Registry-Optimierungen
echo ---------------------------------------------------
echo.

:: --- Windows Update komplett blockieren ---
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v NoAutoUpdate /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate" /v DoNotConnectToWindowsUpdateInternetLocations /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v NoAutoRebootWithLoggedOnUsers /t REG_DWORD /d 1 /f >nul 2>&1
echo [OK] Windows Update per Registry blockiert

:: --- Telemetrie deaktivieren ---
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection" /v AllowTelemetry /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection" /v AllowTelemetry /t REG_DWORD /d 0 /f >nul 2>&1
echo [OK] Telemetrie deaktiviert

:: --- Cortana deaktivieren ---
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Search" /v AllowCortana /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Search" /v AllowSearchToUseLocation /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Search" /v ConnectedSearchUseWeb /t REG_DWORD /d 0 /f >nul 2>&1
echo [OK] Cortana deaktiviert

:: --- Visuelle Effekte auf Performance ---
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects" /v VisualFXSetting /t REG_DWORD /d 2 /f >nul 2>&1
:: Einzelne Animationen deaktivieren
reg add "HKCU\Control Panel\Desktop" /v UserPreferencesMask /t REG_BINARY /d 9012038010000000 /f >nul 2>&1
reg add "HKCU\Control Panel\Desktop\WindowMetrics" /v MinAnimate /t REG_SZ /d 0 /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" /v TaskbarAnimations /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\DWM" /v EnableAeroPeek /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\DWM" /v AlwaysHibernateThumbnails /t REG_DWORD /d 0 /f >nul 2>&1
echo [OK] Visuelle Effekte auf "Beste Performance" gesetzt

:: --- Transparenz deaktivieren (spart GPU) ---
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" /v EnableTransparency /t REG_DWORD /d 0 /f >nul 2>&1
echo [OK] Transparenz-Effekte deaktiviert

:: --- Benachrichtigungen deaktivieren ---
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\PushNotifications" /v ToastEnabled /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKCU\Software\Policies\Microsoft\Windows\Explorer" /v DisableNotificationCenter /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer" /v DisableNotificationCenter /t REG_DWORD /d 1 /f >nul 2>&1
echo [OK] Benachrichtigungscenter deaktiviert

:: --- Tips & Tricks deaktivieren ---
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\CloudContent" /v DisableSoftLanding /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\CloudContent" /v DisableWindowsConsumerFeatures /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager" /v SubscribedContent-338389Enabled /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager" /v SubscribedContent-310093Enabled /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager" /v SilentInstalledAppsEnabled /t REG_DWORD /d 0 /f >nul 2>&1
echo [OK] Tips, Tricks und vorgeschlagene Apps deaktiviert

:: --- Hintergrund-Apps deaktivieren ---
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications" /v GlobalUserDisabled /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy" /v LetAppsRunInBackground /t REG_DWORD /d 2 /f >nul 2>&1
echo [OK] Hintergrund-Apps deaktiviert

:: --- OneDrive deaktivieren ---
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\OneDrive" /v DisableFileSyncNGSC /t REG_DWORD /d 1 /f >nul 2>&1
echo [OK] OneDrive deaktiviert

:: --- Sperrbildschirm-Werbung deaktivieren ---
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager" /v RotatingLockScreenEnabled /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager" /v RotatingLockScreenOverlayEnabled /t REG_DWORD /d 0 /f >nul 2>&1
echo [OK] Sperrbildschirm-Werbung deaktiviert

:: --- Automatische Wartung deaktivieren ---
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Schedule\Maintenance" /v MaintenanceDisabled /t REG_DWORD /d 1 /f >nul 2>&1
echo [OK] Automatische Wartung deaktiviert

:: --- Storage Sense deaktivieren (soll nichts automatisch loeschen) ---
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy" /v 01 /t REG_DWORD /d 0 /f >nul 2>&1
echo [OK] Storage Sense deaktiviert

:: --- Energiesparmodus: Bildschirm nie ausschalten ---
powershell -NoProfile -Command "powercfg /change monitor-timeout-ac 0; powercfg /change monitor-timeout-dc 0; powercfg /change standby-timeout-ac 0; powercfg /change standby-timeout-dc 0; powercfg /change hibernate-timeout-ac 0; powercfg /change hibernate-timeout-dc 0" >nul 2>&1
echo [OK] Energiesparmodus: Kein Standby, kein Bildschirm-Aus

:: --- Ruhezustand deaktivieren (spart ~3GB Disk) ---
powercfg /hibernate off >nul 2>&1
echo [OK] Ruhezustand deaktiviert (hiberfil.sys entfernt)

:: --- Schnellstart deaktivieren (verhindert Probleme beim Klonen) ---
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 0 /f >nul 2>&1
echo [OK] Schnellstart deaktiviert

:: --- Windows Defender deaktivieren (Registry + Policies) ---
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender" /v DisableAntiSpyware /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection" /v DisableRealtimeMonitoring /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection" /v DisableBehaviorMonitoring /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender\Spynet" /v SpynetReporting /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender\Spynet" /v SubmitSamplesConsent /t REG_DWORD /d 2 /f >nul 2>&1
echo [OK] Windows Defender per Registry deaktiviert

:: --- Geplante Tasks deaktivieren ---
schtasks /Change /TN "\Microsoft\Windows\WindowsUpdate\Scheduled Start" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\Defrag\ScheduledDefrag" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\DiskDiagnostic\Microsoft-Windows-DiskDiagnosticDataCollector" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\Maintenance\WinSAT" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\Application Experience\ProgramDataUpdater" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\Customer Experience Improvement Program\Consolidator" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip" /Disable >nul 2>&1
echo [OK] Geplante Tasks (Defrag, Diagnose, Telemetrie) deaktiviert

echo.

:: ═══════════════════════════════════════════════
::  TEIL 3: FEXOBOOTH DATEN BEREINIGEN
:: ═══════════════════════════════════════════════

echo ---------------------------------------------------
echo  TEIL 3: FexoBooth-Daten bereinigen
echo ---------------------------------------------------
echo.

set FEXO_DIR=C:\FexoBooth

if not exist "%FEXO_DIR%" (
    echo [INFO] FexoBooth nicht unter %FEXO_DIR% gefunden, ueberspringe...
    goto :cleanup_temp
)

:: Bilder loeschen
if exist "%FEXO_DIR%\BILDER\Single" (
    del /q "%FEXO_DIR%\BILDER\Single\*" >nul 2>&1
    echo [OK] BILDER\Single\ geleert
) else (
    mkdir "%FEXO_DIR%\BILDER\Single" >nul 2>&1
    echo [OK] BILDER\Single\ erstellt
)

if exist "%FEXO_DIR%\BILDER\Prints" (
    del /q "%FEXO_DIR%\BILDER\Prints\*" >nul 2>&1
    echo [OK] BILDER\Prints\ geleert
) else (
    mkdir "%FEXO_DIR%\BILDER\Prints" >nul 2>&1
    echo [OK] BILDER\Prints\ erstellt
)

:: Logs loeschen
if exist "%FEXO_DIR%\logs" (
    del /q "%FEXO_DIR%\logs\*" >nul 2>&1
    echo [OK] logs\ geleert
) else (
    mkdir "%FEXO_DIR%\logs" >nul 2>&1
    echo [OK] logs\ erstellt
)

:: Booking-Cache loeschen
if exist "%FEXO_DIR%\.booking_cache" (
    rd /s /q "%FEXO_DIR%\.booking_cache" >nul 2>&1
    mkdir "%FEXO_DIR%\.booking_cache" >nul 2>&1
    echo [OK] .booking_cache\ geleert
)

:: Statistik zuruecksetzen
if exist "%FEXO_DIR%\statistics.json" (
    del /q "%FEXO_DIR%\statistics.json" >nul 2>&1
    echo [OK] statistics.json geloescht
)

:: Drucker-Lifetime zuruecksetzen
if exist "%FEXO_DIR%\printer_lifetime.json" (
    del /q "%FEXO_DIR%\printer_lifetime.json" >nul 2>&1
    echo [OK] printer_lifetime.json geloescht
)

:: Gallery-Server Temp-Dateien
if exist "%FEXO_DIR%\gallery_cache" (
    rd /s /q "%FEXO_DIR%\gallery_cache" >nul 2>&1
    echo [OK] gallery_cache\ geloescht
)

echo.

:: ═══════════════════════════════════════════════
::  TEIL 4: WINDOWS TEMP-DATEIEN BEREINIGEN
:: ═══════════════════════════════════════════════

:cleanup_temp
echo ---------------------------------------------------
echo  TEIL 4: Windows Temp-Dateien bereinigen
echo ---------------------------------------------------
echo.

:: Temp-Ordner leeren
del /q /f "%TEMP%\*" >nul 2>&1
rd /s /q "%TEMP%" >nul 2>&1
mkdir "%TEMP%" >nul 2>&1
echo [OK] User-Temp geleert

del /q /f "C:\Windows\Temp\*" >nul 2>&1
rd /s /q "C:\Windows\Temp" >nul 2>&1
mkdir "C:\Windows\Temp" >nul 2>&1
echo [OK] Windows-Temp geleert

:: Prefetch leeren
del /q /f "C:\Windows\Prefetch\*" >nul 2>&1
echo [OK] Prefetch geleert

:: Windows Update Cache leeren
rd /s /q "C:\Windows\SoftwareDistribution\Download" >nul 2>&1
mkdir "C:\Windows\SoftwareDistribution\Download" >nul 2>&1
echo [OK] Windows Update Cache geleert

:: Thumbnail Cache loeschen
del /q /f "%LOCALAPPDATA%\Microsoft\Windows\Explorer\thumbcache_*.db" >nul 2>&1
echo [OK] Thumbnail-Cache geloescht

:: Icon Cache loeschen
del /q /f "%LOCALAPPDATA%\IconCache.db" >nul 2>&1
del /q /f "%LOCALAPPDATA%\Microsoft\Windows\Explorer\iconcache_*.db" >nul 2>&1
echo [OK] Icon-Cache geloescht

:: Papierkorb leeren
rd /s /q "C:\$Recycle.Bin" >nul 2>&1
echo [OK] Papierkorb geleert

:: Delivery Optimization Cache
del /q /f "C:\Windows\ServiceProfiles\NetworkService\AppData\Local\Microsoft\Windows\DeliveryOptimization\Cache\*" >nul 2>&1
echo [OK] Delivery Optimization Cache geleert

:: Event Logs leeren
powershell -NoProfile -Command "Get-WinEvent -ListLog * -Force -ErrorAction SilentlyContinue | ForEach-Object { try { [System.Diagnostics.Eventing.Reader.EventLogSession]::GlobalSession.ClearLog($_.LogName) } catch {} }" >nul 2>&1
echo [OK] Windows Event-Logs geleert

:: Datentraegerbereinigung DEAKTIVIERT - cleanmgr haengt sich auf
:: Atom-Tablets wenn Defender deaktiviert ist (bleibt endlos bei
:: "Microsoft Defender Antivirus" stehen). Die manuellen Temp-Loeschungen
:: oben erledigen das Gleiche zuverlaessiger.
echo [INFO] Datentraegerbereinigung uebersprungen (haengt auf Atom-Tablets)

echo.

:: ═══════════════════════════════════════════════
::  TEIL 5: WLAN-ADAPTER FUER KLONEN VORBEREITEN
:: ═══════════════════════════════════════════════

echo ---------------------------------------------------
echo  TEIL 5: WLAN-Adapter fuer Klonen vorbereiten
echo ---------------------------------------------------
echo.

:: Problem: RTL8723BS haengt am SDIO-Bus mit Connected Standby.
:: Wenn der Chip beim Image-Erstellen im Schlafmodus ist, wacht
:: er auf manchen Tablets nach dem Klonen nicht mehr auf.
:: Loesung: Energieverwaltung deaktivieren und Adapter sauber neustarten.

:: WLAN Energieverwaltung deaktivieren (Adapter darf nicht schlafen)
powershell -NoProfile -Command "$k = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}'; Get-ChildItem $k -EA SilentlyContinue | ForEach-Object { if ((Get-ItemProperty $_.PSPath -EA SilentlyContinue).DriverDesc -match 'Wireless|WiFi|WLAN|802\.11') { Set-ItemProperty $_.PSPath -Name 'PnPCapabilities' -Value 24 -Type DWord -EA SilentlyContinue; Write-Host '[OK] Energieverwaltung fuer WLAN deaktiviert' } }"

:: WLAN-Adapter deaktivieren und wieder aktivieren (sauberer Zustand)
powershell -NoProfile -Command "$dev = Get-PnpDevice -Class Net -EA SilentlyContinue | Where-Object { $_.FriendlyName -match 'Wireless|WiFi|WLAN|802\.11' }; if ($dev) { Disable-PnpDevice -InstanceId $dev.InstanceId -Confirm:$false -EA SilentlyContinue; Start-Sleep 2; Enable-PnpDevice -InstanceId $dev.InstanceId -Confirm:$false -EA SilentlyContinue; Start-Sleep 3; Write-Host \"[OK] WLAN-Adapter neugestartet (Status: $((Get-PnpDevice -InstanceId $dev.InstanceId).Status))\" } else { Write-Host '[INFO] Kein WLAN-Adapter gefunden' }"

:: Erstelle ein Startup-Script das nach dem Klonen den WLAN-Treiber repariert
:: Laeuft einmalig beim ersten Windows-Start nach dem Image-Aufspielen
:: WICHTIG: Niemals pnputil /remove-device verwenden! Das killt den SDIO-Adapter.
:: Stattdessen: SD-Hostcontroller neustarten + echtes Herunterfahren.
echo Erstelle WLAN-Reparatur fuer ersten Start nach Klonen...
set "STARTUP_SCRIPT=C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\fexobooth_wlan_repair.bat"

(
echo @echo off
echo :: FexoBooth WLAN Auto-Reparatur nach Klonen
echo :: Dieses Script loescht sich nach dem ersten Lauf selbst
echo chcp 65001 ^>nul
echo net session ^>nul 2^>^&1
echo if errorlevel 1 goto :cleanup
echo.
echo :: WlanSvc sicherstellen
echo sc config WlanSvc start=auto ^>nul 2^>^&1
echo sc start WlanSvc ^>nul 2^>^&1
echo timeout /t 3 ^>nul
echo.
echo :: Pruefen ob WLAN funktioniert
echo netsh wlan show interfaces 2^>nul ^| findstr /C:"Zustand" /C:"State" ^>nul 2^>^&1
echo if not errorlevel 1 goto :cleanup
echo.
echo :: WLAN funktioniert nicht - SD-Hostcontroller neustarten
echo pnputil /restart-device "ACPI\80860F14\1" ^>nul 2^>^&1
echo pnputil /restart-device "ACPI\80860F14\2" ^>nul 2^>^&1
echo pnputil /restart-device "ACPI\80860F14\3" ^>nul 2^>^&1
echo timeout /t 5 ^>nul
echo netsh interface set interface "WLAN" admin=enable ^>nul 2^>^&1
echo.
echo :: Nochmal pruefen - wenn immer noch kaputt: Herunterfahren erzwingen
echo netsh wlan show interfaces 2^>nul ^| findstr /C:"Zustand" /C:"State" ^>nul 2^>^&1
echo if errorlevel 1 shutdown /s /f /t 30 /c "WLAN-Reparatur: Herunterfahren noetig (SDIO). Bitte danach wieder einschalten."
echo.
echo :cleanup
echo :: Script loescht sich selbst nach einmaligem Lauf
echo del "%%~f0" ^>nul 2^>^&1
) > "%STARTUP_SCRIPT%"

echo [OK] WLAN Auto-Reparatur fuer ersten Start eingerichtet

echo.

:: ═══════════════════════════════════════════════
::  ZUSAMMENFASSUNG
:: ═══════════════════════════════════════════════

echo ===================================================
echo    FERTIG! Tablet ist bereit fuer Image-Erstellung
echo ===================================================
echo.
echo Was wurde gemacht:
echo   [1] 25+ unnoetige Windows-Dienste deaktiviert
echo   [2] Telemetrie, Cortana, OneDrive abgeschaltet
echo   [3] Visuelle Effekte auf Performance gesetzt
echo   [4] Energiesparmodus + Ruhezustand deaktiviert
echo   [5] FexoBooth Bilder/Logs/Caches geleert
echo   [6] Windows Temp-Dateien bereinigt
echo   [7] WLAN-Adapter fuer Klonen vorbereitet
echo.
echo NAECHSTE SCHRITTE:
echo   1. HERUNTERFAHREN (NICHT Neustart! SDIO braucht echten Power-Cycle)
echo   2. Wieder einschalten (Power-Button)
echo   3. post_install_check.bat ausfuehren
echo   4. Clonezilla-Image erstellen
echo.

pause
