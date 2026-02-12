@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ============================================
echo    FexoBooth Update (GitHub Release)
echo ============================================
echo.

:: GitHub Repository - HIER ANPASSEN falls noetig!
set "GITHUB_REPO=fefotec/fexobooth-v2"
set "API_URL=https://api.github.com/repos/%GITHUB_REPO%/releases/latest"
set "ZIP_FILE=%TEMP%\fexobooth_update.zip"
set "EXTRACT_DIR=%TEMP%\fexobooth_update_extract"
set "SCRIPT_DIR=%~dp0"

echo Repository: %GITHUB_REPO%
echo.

:: Pruefe Internetverbindung
echo Pruefe Internetverbindung...
ping -n 1 github.com >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Keine Internetverbindung!
    echo Bitte mit dem Internet verbinden und erneut versuchen.
    pause
    exit /b 1
)
echo OK
echo.

:: Neuestes Release von GitHub API abfragen
echo Pruefe auf neuestes Release...
set "RELEASE_JSON=%TEMP%\fexobooth_release.json"

powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $r = Invoke-WebRequest -Uri '%API_URL%' -UseBasicParsing -Headers @{'User-Agent'='FexoBooth-Updater'}; $r.Content | Out-File -Encoding utf8 '%RELEASE_JSON%' } catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo.
    echo FEHLER: GitHub API nicht erreichbar!
    echo Moeglicherweise gibt es noch kein Release.
    echo.
    echo Stelle sicher dass ein Release mit ZIP-Asset
    echo auf GitHub existiert.
    echo.
    pause
    exit /b 1
)

:: Version und Download-URL aus JSON extrahieren
for /f "usebackq delims=" %%A in (`powershell -Command "$j = Get-Content '%RELEASE_JSON%' -Raw | ConvertFrom-Json; $j.tag_name"`) do set "RELEASE_TAG=%%A"
for /f "usebackq delims=" %%A in (`powershell -Command "$j = Get-Content '%RELEASE_JSON%' -Raw | ConvertFrom-Json; ($j.assets | Where-Object { $_.name -like '*fexobooth*.zip' }).browser_download_url"`) do set "DOWNLOAD_URL=%%A"

del "%RELEASE_JSON%" 2>nul

echo Neuestes Release: %RELEASE_TAG%

if "%DOWNLOAD_URL%"=="" (
    echo.
    echo FEHLER: Kein ZIP-Asset im Release gefunden!
    echo.
    echo Das Release muss eine Datei enthalten die
    echo 'fexobooth' im Namen hat und auf .zip endet.
    echo z.B.: fexobooth.zip
    echo.
    pause
    exit /b 1
)

echo Download-URL: %DOWNLOAD_URL%
echo.

:: Backup der config.json
if exist "%SCRIPT_DIR%config.json" (
    echo Sichere aktuelle config.json...
    copy "%SCRIPT_DIR%config.json" "%SCRIPT_DIR%config.json.backup" /Y >nul
    echo OK
    echo.
)

:: Download
echo Lade Update herunter...
echo (Dies kann je nach Internetgeschwindigkeit einige Minuten dauern)
echo.

powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%ZIP_FILE%' -UseBasicParsing } catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo.
    echo FEHLER: Download fehlgeschlagen!
    pause
    exit /b 1
)

echo Download abgeschlossen.
echo.

:: Entpacken
echo Entpacke Dateien...

if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%"
mkdir "%EXTRACT_DIR%"

powershell -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%EXTRACT_DIR%' -Force"

if errorlevel 1 (
    echo FEHLER: Entpacken fehlgeschlagen!
    pause
    exit /b 1
)

:: Quell-Verzeichnis finden (kann direkt oder in Unterordner sein)
set "SOURCE_DIR=%EXTRACT_DIR%"

:: Pruefe ob ein einzelner Unterordner existiert
set SUBDIR_COUNT=0
for /d %%D in ("%EXTRACT_DIR%\*") do (
    set "FIRST_SUBDIR=%%D"
    set /a SUBDIR_COUNT+=1
)
if !SUBDIR_COUNT! EQU 1 (
    if exist "!FIRST_SUBDIR!\fexobooth.exe" set "SOURCE_DIR=!FIRST_SUBDIR!"
    if exist "!FIRST_SUBDIR!\_internal" set "SOURCE_DIR=!FIRST_SUBDIR!"
)

echo Quelle: %SOURCE_DIR%
echo.
echo Aktualisiere Dateien...
echo.

:: EXE aktualisieren
if exist "%SOURCE_DIR%\fexobooth.exe" (
    echo - fexobooth.exe
    copy /Y "%SOURCE_DIR%\fexobooth.exe" "%SCRIPT_DIR%" >nul 2>&1
)

:: _internal/ komplett ersetzen
if exist "%SOURCE_DIR%\_internal" (
    echo - _internal/ (Runtime + Dependencies)
    if exist "%SCRIPT_DIR%_internal" rmdir /s /q "%SCRIPT_DIR%_internal"
    xcopy "%SOURCE_DIR%\_internal" "%SCRIPT_DIR%_internal" /E /I /Y >nul 2>&1
)

:: Assets aktualisieren
if exist "%SOURCE_DIR%\assets" (
    echo - assets/
    xcopy "%SOURCE_DIR%\assets" "%SCRIPT_DIR%assets" /E /I /Y >nul 2>&1
)

:: Setup-Scripts
if exist "%SOURCE_DIR%\setup" (
    echo - setup/
    xcopy "%SOURCE_DIR%\setup" "%SCRIPT_DIR%setup" /E /I /Y >nul 2>&1
)

:: BAT-Dateien
for %%F in (START.bat start_fexobooth.bat start_dev.bat) do (
    if exist "%SOURCE_DIR%\%%F" (
        echo - %%F
        copy /Y "%SOURCE_DIR%\%%F" "%SCRIPT_DIR%" >nul 2>&1
    )
)

:: config.example.json (NICHT config.json!)
if exist "%SOURCE_DIR%\config.example.json" (
    echo - config.example.json
    copy /Y "%SOURCE_DIR%\config.example.json" "%SCRIPT_DIR%" >nul 2>&1
)

:: config.json wiederherstellen
if exist "%SCRIPT_DIR%config.json.backup" (
    echo.
    echo Stelle config.json wieder her...
    move /Y "%SCRIPT_DIR%config.json.backup" "%SCRIPT_DIR%config.json" >nul
    echo OK
)

:: Geschuetzte Ordner Info
echo.
echo Geschuetzte Dateien/Ordner (NICHT ueberschrieben):
echo - config.json (Einstellungen)
echo - BILDER/ (Fotos)
echo - logs/ (Protokolle)
echo - .booking_cache/ (Buchungsdaten)

:: Aufraeumen
echo.
echo Raeume auf...
del "%ZIP_FILE%" 2>nul
rmdir /s /q "%EXTRACT_DIR%" 2>nul
echo OK

echo.
echo ============================================
echo    UPDATE AUF %RELEASE_TAG% ERFOLGREICH!
echo ============================================
echo.

:: update_from_github.bat selbst aktualisieren (als letztes!)
if exist "%SOURCE_DIR%\update_from_github.bat" (
    copy /Y "%SOURCE_DIR%\update_from_github.bat" "%SCRIPT_DIR%" >nul 2>&1
)

echo Moechten Sie FexoBooth jetzt starten?
choice /C JN /M "(J)a/(N)ein"
if errorlevel 2 goto :end
if errorlevel 1 goto :start_app

:start_app
echo.
echo Starte FexoBooth...
if exist "%SCRIPT_DIR%fexobooth.exe" (
    start "" "%SCRIPT_DIR%fexobooth.exe"
) else if exist "%SCRIPT_DIR%START.bat" (
    start "" "%SCRIPT_DIR%START.bat"
) else (
    echo HINWEIS: Keine startbare Datei gefunden.
)

:end
echo.
echo Fertig!
timeout /t 3 >nul
