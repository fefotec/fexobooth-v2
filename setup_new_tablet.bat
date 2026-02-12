@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ============================================
echo    FexoBooth - Neues Tablet Setup
echo ============================================
echo.
echo Dieses Script richtet FexoBooth auf einem
echo neuen Tablet ein (für Entwicklung/Testing).
echo.
echo Voraussetzungen:
echo - Windows 10/11
echo - Internetverbindung
echo - Administratorrechte (für Hotspot-Setup)
echo.
echo ============================================
echo.

:: Prüfe Administratorrechte
net session >nul 2>&1
if errorlevel 1 (
    echo HINWEIS: Für Hotspot-Setup werden Administratorrechte benötigt.
    echo Das Script läuft ohne Admin-Rechte, aber der Hotspot
    echo muss später manuell eingerichtet werden.
    echo.
)

set "INSTALL_DIR=C:\FexoBooth-Dev"
set "GITHUB_REPO=fefotec/fexobooth-v2"
set "BRANCH=main"

echo Installationsverzeichnis: %INSTALL_DIR%
echo.
echo Möchten Sie fortfahren?
choice /C JN /M "(J)a/(N)ein"
if errorlevel 2 exit /b 0

:: Prüfe ob Python installiert ist
echo.
echo [1/6] Prüfe Python-Installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python ist nicht installiert!
    echo.
    echo Bitte Python 3.10 oder höher installieren:
    echo https://www.python.org/downloads/
    echo.
    echo WICHTIG: Bei der Installation "Add Python to PATH" aktivieren!
    echo.
    echo Nach der Python-Installation dieses Script erneut ausführen.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Python gefunden: %PYTHON_VERSION%
echo.

:: Erstelle Installationsverzeichnis
echo [2/6] Erstelle Verzeichnis...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
cd /d "%INSTALL_DIR%"
echo OK - %INSTALL_DIR%
echo.

:: Download von GitHub
echo [3/6] Lade FexoBooth von GitHub...
set "DOWNLOAD_URL=https://github.com/%GITHUB_REPO%/archive/refs/heads/%BRANCH%.zip"
set "ZIP_FILE=%TEMP%\fexobooth_setup.zip"
set "EXTRACT_DIR=%TEMP%\fexobooth_setup_extract"

powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%ZIP_FILE%' -UseBasicParsing } catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo FEHLER: Download fehlgeschlagen!
    pause
    exit /b 1
)
echo Download abgeschlossen.
echo.

:: Entpacken
echo [4/6] Entpacke Dateien...
if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%"
powershell -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%EXTRACT_DIR%' -Force"

:: Kopiere Dateien
for /d %%D in ("%EXTRACT_DIR%\*") do (
    xcopy "%%D\*" "%INSTALL_DIR%\" /E /I /Y >nul
)

:: Aufräumen
del "%ZIP_FILE%" 2>nul
rmdir /s /q "%EXTRACT_DIR%" 2>nul
echo OK
echo.

:: Installiere Python-Dependencies
echo [5/6] Installiere Python-Abhängigkeiten...
echo Dies kann einige Minuten dauern...
echo.
pip install -r "%INSTALL_DIR%\requirements.txt"

if errorlevel 1 (
    echo.
    echo WARNUNG: Einige Dependencies konnten nicht installiert werden.
    echo Das Programm funktioniert möglicherweise trotzdem.
    echo.
)
echo.
echo Dependencies installiert.
echo.

:: Erstelle config.json
echo [6/6] Erstelle Konfiguration...
if not exist "%INSTALL_DIR%\config.json" (
    copy "%INSTALL_DIR%\config.example.json" "%INSTALL_DIR%\config.json" /Y >nul
)
echo OK
echo.

:: Erstelle Verzeichnisse
if not exist "%INSTALL_DIR%\BILDER" mkdir "%INSTALL_DIR%\BILDER"
if not exist "%INSTALL_DIR%\BILDER\Prints" mkdir "%INSTALL_DIR%\BILDER\Prints"
if not exist "%INSTALL_DIR%\BILDER\Single" mkdir "%INSTALL_DIR%\BILDER\Single"
if not exist "%INSTALL_DIR%\logs" mkdir "%INSTALL_DIR%\logs"

echo ============================================
echo    INSTALLATION ABGESCHLOSSEN!
echo ============================================
echo.
echo Installationsverzeichnis: %INSTALL_DIR%
echo.
echo Nächste Schritte:
echo.
echo 1. WLAN-Hotspot einrichten (optional, für Galerie):
echo    Führe als Administrator aus:
echo    %INSTALL_DIR%\setup\einmalig_hotspot_einrichten.bat
echo.
echo 2. FexoBooth starten:
echo    %INSTALL_DIR%\start_fexobooth.bat
echo.
echo 3. Entwicklermodus (mit Debug-Ausgabe):
echo    %INSTALL_DIR%\start_dev.bat
echo.
echo 4. Updates holen:
echo    %INSTALL_DIR%\update_from_github.bat
echo.

:: Frage ob Hotspot eingerichtet werden soll
echo Möchten Sie jetzt den WLAN-Hotspot einrichten?
echo (Erfordert Administratorrechte)
choice /C JN /M "(J)a/(N)ein"
if errorlevel 2 goto :skip_hotspot
if errorlevel 1 goto :setup_hotspot

:setup_hotspot
echo.
echo Starte Hotspot-Setup...
powershell -Command "Start-Process -FilePath '%INSTALL_DIR%\setup\einmalig_hotspot_einrichten.bat' -Verb RunAs -Wait"
goto :ask_start

:skip_hotspot

:ask_start
echo.
echo Möchten Sie FexoBooth jetzt starten?
choice /C JN /M "(J)a/(N)ein"
if errorlevel 2 goto :end
if errorlevel 1 goto :start_app

:start_app
echo.
echo Starte FexoBooth im Entwicklermodus...
start "" "%INSTALL_DIR%\start_dev.bat"

:end
echo.
echo Fertig!
pause
