@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ============================================
echo    FexoBooth GitHub Update (ohne Git)
echo ============================================
echo.

:: GitHub Repository URL - HIER ANPASSEN falls nötig!
set "GITHUB_REPO=fexobox/fexobooth-v2"
set "BRANCH=main"
set "DOWNLOAD_URL=https://github.com/%GITHUB_REPO%/archive/refs/heads/%BRANCH%.zip"
set "ZIP_FILE=%TEMP%\fexobooth_update.zip"
set "EXTRACT_DIR=%TEMP%\fexobooth_extract"
set "SCRIPT_DIR=%~dp0"

echo Repository: %GITHUB_REPO%
echo Branch: %BRANCH%
echo.

:: Prüfe Internetverbindung
echo Prüfe Internetverbindung...
ping -n 1 github.com >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Keine Internetverbindung!
    echo Bitte mit dem Internet verbinden und erneut versuchen.
    pause
    exit /b 1
)
echo OK
echo.

:: Backup der config.json falls vorhanden
if exist "%SCRIPT_DIR%config.json" (
    echo Sichere aktuelle config.json...
    copy "%SCRIPT_DIR%config.json" "%SCRIPT_DIR%config.json.backup" /Y >nul
    echo OK
    echo.
)

echo Lade neueste Version von GitHub...
echo URL: %DOWNLOAD_URL%
echo.

:: Download mit PowerShell (curl ist nicht auf allen Windows-Versionen verfügbar)
powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%ZIP_FILE%' -UseBasicParsing } catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo.
    echo FEHLER: Download fehlgeschlagen!
    echo Mögliche Ursachen:
    echo - Keine Internetverbindung
    echo - Repository nicht gefunden
    echo - Firewall blockiert die Verbindung
    echo.
    pause
    exit /b 1
)

echo Download abgeschlossen.
echo.
echo Entpacke Dateien...

:: Lösche altes Extract-Verzeichnis falls vorhanden
if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%"
mkdir "%EXTRACT_DIR%"

:: Entpacke mit PowerShell
powershell -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%EXTRACT_DIR%' -Force"

if errorlevel 1 (
    echo FEHLER: Entpacken fehlgeschlagen!
    pause
    exit /b 1
)

:: Finde das entpackte Verzeichnis (enthält Branch-Name)
for /d %%D in ("%EXTRACT_DIR%\*") do set "SOURCE_DIR=%%D"

echo Gefunden: %SOURCE_DIR%
echo.
echo Aktualisiere Dateien...
echo.

:: Kopiere alle wichtigen Dateien
echo - src/
xcopy "%SOURCE_DIR%\src" "%SCRIPT_DIR%src" /E /I /Y >nul 2>&1

echo - assets/
xcopy "%SOURCE_DIR%\assets" "%SCRIPT_DIR%assets" /E /I /Y >nul 2>&1

echo - setup/
xcopy "%SOURCE_DIR%\setup" "%SCRIPT_DIR%setup" /E /I /Y >nul 2>&1

echo - config.example.json
copy "%SOURCE_DIR%\config.example.json" "%SCRIPT_DIR%" /Y >nul 2>&1

echo - requirements.txt
copy "%SOURCE_DIR%\requirements.txt" "%SCRIPT_DIR%" /Y >nul 2>&1

echo - BAT-Dateien
copy "%SOURCE_DIR%\start_fexobooth.bat" "%SCRIPT_DIR%" /Y >nul 2>&1
copy "%SOURCE_DIR%\start_dev.bat" "%SCRIPT_DIR%" /Y >nul 2>&1
copy "%SOURCE_DIR%\update_and_start.bat" "%SCRIPT_DIR%" /Y >nul 2>&1

:: Stelle config.json wieder her falls gesichert
if exist "%SCRIPT_DIR%config.json.backup" (
    echo.
    echo Stelle config.json wieder her...
    move /Y "%SCRIPT_DIR%config.json.backup" "%SCRIPT_DIR%config.json" >nul
    echo OK
)

:: Aufräumen
echo.
echo Räume auf...
del "%ZIP_FILE%" 2>nul
rmdir /s /q "%EXTRACT_DIR%" 2>nul
echo OK

echo.
echo ============================================
echo    UPDATE ERFOLGREICH!
echo ============================================
echo.
echo Die neuesten Dateien wurden heruntergeladen.
echo.

:: Frage ob Dependencies aktualisiert werden sollen
echo Möchten Sie auch die Python-Dependencies aktualisieren?
echo (Empfohlen bei neuen Versionen)
echo.
choice /C JN /M "Dependencies aktualisieren (J)a/(N)ein"
if errorlevel 2 goto :skip_deps
if errorlevel 1 goto :install_deps

:install_deps
echo.
echo Installiere Python-Dependencies...
pip install -r "%SCRIPT_DIR%requirements.txt"
echo.
echo Dependencies aktualisiert.

:skip_deps
echo.
echo ============================================
echo Möchten Sie FexoBooth jetzt starten?
choice /C JN /M "(J)a/(N)ein"
if errorlevel 2 goto :end
if errorlevel 1 goto :start_app

:start_app
echo.
echo Starte FexoBooth...
start "" "%SCRIPT_DIR%start_fexobooth.bat"

:end
echo.
echo Fertig!
timeout /t 3 >nul
