@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo.
echo ===================================================
echo    FexoBooth - Referenz-Tablet Pruefung
echo ===================================================
echo.
echo Prueft ob das Tablet korrekt fuer das Klonen
echo vorbereitet ist.
echo.

set ERRORS=0
set WARNINGS=0

:: ─────────────────────────────────────────────
:: FexoBooth Installation pruefen
:: ─────────────────────────────────────────────

if exist "C:\FexoBooth\FexoBooth.exe" (
    echo [OK] FexoBooth.exe gefunden
) else if exist "C:\FexoBooth\fexobooth.exe" (
    echo [OK] fexobooth.exe gefunden
) else (
    echo [FEHLER] FexoBooth.exe NICHT gefunden in C:\FexoBooth\!
    set /a ERRORS+=1
)

if exist "C:\FexoBooth\_internal" (
    echo [OK] _internal/ Ordner vorhanden
) else (
    echo [FEHLER] _internal/ Ordner NICHT gefunden!
    set /a ERRORS+=1
)

if exist "C:\FexoBooth\config.json" (
    echo [OK] config.json vorhanden
) else (
    echo [FEHLER] config.json NICHT gefunden!
    echo          Kopiere config.example.json nach config.json
    set /a ERRORS+=1
)

if exist "C:\FexoBooth\assets" (
    echo [OK] assets/ Ordner vorhanden
) else (
    echo [FEHLER] assets/ Ordner NICHT gefunden!
    set /a ERRORS+=1
)

:: ─────────────────────────────────────────────
:: Verzeichnisse pruefen
:: ─────────────────────────────────────────────

if exist "C:\FexoBooth\BILDER" (
    echo [OK] BILDER/ Ordner vorhanden
) else (
    echo [WARNUNG] BILDER/ Ordner nicht vorhanden - wird beim Start erstellt
    set /a WARNINGS+=1
)

if exist "C:\FexoBooth\logs" (
    echo [OK] logs/ Ordner vorhanden
) else (
    echo [WARNUNG] logs/ Ordner nicht vorhanden - wird beim Start erstellt
    set /a WARNINGS+=1
)

:: ─────────────────────────────────────────────
:: Hotspot pruefen
:: ─────────────────────────────────────────────

schtasks /query /TN "FexoboxHotspot" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Hotspot-Task "FexoboxHotspot" vorhanden
) else (
    echo [FEHLER] Hotspot-Task NICHT gefunden!
    echo          Fuehre setup\einmalig_hotspot_einrichten.bat als Admin aus
    set /a ERRORS+=1
)

:: ─────────────────────────────────────────────
:: Autostart pruefen
:: ─────────────────────────────────────────────

set AUTOSTART_FOUND=0
if exist "%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs\Startup\FexoBooth.lnk" set AUTOSTART_FOUND=1
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\FexoBooth.lnk" set AUTOSTART_FOUND=1

if %AUTOSTART_FOUND%==1 (
    echo [OK] Autostart-Verknuepfung vorhanden
) else (
    echo [WARNUNG] Autostart-Verknuepfung nicht gefunden
    echo           Wurde der Installer mit Autostart-Option ausgefuehrt?
    set /a WARNINGS+=1
)

:: ─────────────────────────────────────────────
:: Windows-Aktivierung pruefen
:: ─────────────────────────────────────────────

powershell -Command "$s = Get-CimInstance SoftwareLicensingProduct -Filter 'Name like \"Windows%%\"' -ErrorAction SilentlyContinue | Where-Object { $_.LicenseStatus -eq 1 }; if($s){ Write-Host '[OK] Windows ist aktiviert' } else { Write-Host '[WARNUNG] Windows ist NICHT aktiviert' }" 2>nul
if errorlevel 1 (
    echo [WARNUNG] Windows-Aktivierung konnte nicht geprueft werden
    set /a WARNINGS+=1
)

:: ─────────────────────────────────────────────
:: Festplattenbelegung pruefen
:: ─────────────────────────────────────────────

echo.
powershell -Command "$d = Get-PSDrive C -ErrorAction SilentlyContinue; if($d){ $usedGB = [math]::Round($d.Used/1GB,1); $freeGB = [math]::Round($d.Free/1GB,1); $totalGB = [math]::Round(($d.Used+$d.Free)/1GB,1); Write-Host \"Festplatte C: $usedGB GB belegt / $totalGB GB gesamt ($freeGB GB frei)\"; if($usedGB -gt 25){ Write-Host '[WARNUNG] Ueber 25 GB belegt - Image wird unnoetig gross!'; Write-Host '          Bitte Datentraegerbereinigung ausfuehren (cleanmgr)' } else { Write-Host '[OK] Festplattenbelegung ist in Ordnung' } }"

:: ─────────────────────────────────────────────
:: BILDER-Ordner pruefen (soll leer sein)
:: ─────────────────────────────────────────────

set FILE_COUNT=0
if exist "C:\FexoBooth\BILDER\Single" (
    for /f %%A in ('powershell -Command "(Get-ChildItem 'C:\FexoBooth\BILDER\Single' -File -ErrorAction SilentlyContinue).Count"') do set FILE_COUNT=%%A
)
if !FILE_COUNT! GTR 0 (
    echo [WARNUNG] !FILE_COUNT! Dateien in BILDER\Single\ - bitte loeschen!
    set /a WARNINGS+=1
) else (
    echo [OK] BILDER\Single\ ist leer
)

set FILE_COUNT=0
if exist "C:\FexoBooth\BILDER\Prints" (
    for /f %%A in ('powershell -Command "(Get-ChildItem 'C:\FexoBooth\BILDER\Prints' -File -ErrorAction SilentlyContinue).Count"') do set FILE_COUNT=%%A
)
if !FILE_COUNT! GTR 0 (
    echo [WARNUNG] !FILE_COUNT! Dateien in BILDER\Prints\ - bitte loeschen!
    set /a WARNINGS+=1
) else (
    echo [OK] BILDER\Prints\ ist leer
)

:: ─────────────────────────────────────────────
:: Zusammenfassung
:: ─────────────────────────────────────────────

echo.
echo ===================================================
if %ERRORS%==0 (
    if %WARNINGS%==0 (
        echo    ALLES OK - Tablet kann abgebildet werden!
    ) else (
        echo    %WARNINGS% Warnung(en) - Tablet kann abgebildet werden
        echo    (Warnungen sind nicht kritisch, aber pruefe sie)
    )
) else (
    echo    %ERRORS% FEHLER gefunden - bitte zuerst beheben!
    echo    Das Tablet sollte NICHT abgebildet werden.
)
echo ===================================================
echo.

pause
