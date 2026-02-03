@echo off
REM ============================================
REM FEXOBOX HOTSPOT SETUP
REM Richtet Windows Mobile Hotspot ein und
REM konfiguriert Auto-Start beim Systemstart
REM ============================================
REM WICHTIG: Als Administrator ausfuehren!
REM ============================================

echo.
echo ========================================
echo    FEXOBOX HOTSPOT SETUP
echo ========================================
echo.

REM Admin-Check
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo FEHLER: Bitte als Administrator ausfuehren!
    echo Rechtsklick auf diese Datei ^> "Als Administrator ausfuehren"
    pause
    exit /b 1
)

echo [1/4] Konfiguriere Hotspot-Einstellungen...

REM Hotspot SSID und Passwort setzen via PowerShell
powershell -Command "& {
    $connectionProfile = [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]::GetInternetConnectionProfile()
    $tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]::CreateFromConnectionProfile($connectionProfile)
    
    # Aktuelle Konfiguration holen
    $config = $tetheringManager.GetCurrentAccessPointConfiguration()
    
    # Neue Einstellungen
    $config.Ssid = 'fexobox-gallery'
    $config.Passphrase = 'fotobox123'
    
    # Konfiguration anwenden
    $tetheringManager.ConfigureAccessPointAsync($config).AsTask().Wait()
    
    Write-Host 'Hotspot konfiguriert: SSID=fexobox-gallery, Passwort=fotobox123'
}"

if %errorlevel% neq 0 (
    echo WARNUNG: PowerShell-Konfiguration fehlgeschlagen.
    echo Bitte Hotspot manuell in den Windows-Einstellungen konfigurieren:
    echo   SSID: fexobox-gallery
    echo   Passwort: fotobox123
)

echo.
echo [2/4] Erstelle Auto-Start Script...

REM Script das den Hotspot aktiviert
echo @echo off > "%USERPROFILE%\start_hotspot.bat"
echo REM Startet den Windows Mobile Hotspot >> "%USERPROFILE%\start_hotspot.bat"
echo powershell -Command "^& {$connectionProfile = [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]::GetInternetConnectionProfile(); $tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]::CreateFromConnectionProfile($connectionProfile); $tetheringManager.StartTetheringAsync().AsTask().Wait(); Write-Host 'Hotspot gestartet'}" >> "%USERPROFILE%\start_hotspot.bat"

echo Auto-Start Script erstellt: %USERPROFILE%\start_hotspot.bat

echo.
echo [3/4] Erstelle Scheduled Task fuer Auto-Start...

REM Task Scheduler Eintrag erstellen
schtasks /create /tn "FexoboxHotspot" /tr "\"%USERPROFILE%\start_hotspot.bat\"" /sc onlogon /rl highest /f

if %errorlevel% equ 0 (
    echo Scheduled Task erstellt: FexoboxHotspot
) else (
    echo WARNUNG: Task konnte nicht erstellt werden.
)

echo.
echo [4/4] Starte Hotspot jetzt...

call "%USERPROFILE%\start_hotspot.bat"

echo.
echo ========================================
echo    SETUP ABGESCHLOSSEN!
echo ========================================
echo.
echo Hotspot-Daten:
echo   SSID:     fexobox-gallery
echo   Passwort: fotobox123
echo   IP:       192.168.137.1
echo.
echo Der Hotspot startet jetzt automatisch bei jedem Login.
echo.
echo NAECHSTE SCHRITTE:
echo 1. Tablet neustarten zum Testen
echo 2. Mit Handy verbinden und http://192.168.137.1:8080 oeffnen
echo.
pause
