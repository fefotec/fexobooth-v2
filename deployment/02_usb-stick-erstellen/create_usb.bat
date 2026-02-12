@echo off
chcp 65001 >nul
setlocal

echo.
echo ===================================================
echo    FexoBooth - USB-Stick Vorbereitung
echo ===================================================
echo.
echo Dieses Script laedt Clonezilla und Rufus herunter.
echo Danach erstellst du mit Rufus den bootfaehigen Stick.
echo.

cd /d "%~dp0"

set "DOWNLOAD_DIR=%~dp0downloads"
if not exist "%DOWNLOAD_DIR%" mkdir "%DOWNLOAD_DIR%"

:: ─────────────────────────────────────────────
:: Schritt 1: Clonezilla herunterladen
:: ─────────────────────────────────────────────

echo [1/3] Pruefe Clonezilla...

:: Pruefe ob bereits vorhanden
set CLONEZILLA_FOUND=0
for %%F in ("%DOWNLOAD_DIR%\clonezilla-live-*.zip") do (
    if exist "%%F" (
        echo [OK] Clonezilla bereits vorhanden: %%~nxF
        set CLONEZILLA_FOUND=1
    )
)

if %CLONEZILLA_FOUND%==0 (
    echo Lade Clonezilla Live herunter (~500 MB)...
    echo Dies kann einige Minuten dauern.
    echo.

    powershell -ExecutionPolicy Bypass -File "%~dp0..\tools\download_clonezilla.ps1" -OutputDir "%DOWNLOAD_DIR%"

    if errorlevel 1 (
        echo.
        echo FEHLER: Clonezilla Download fehlgeschlagen!
        echo.
        echo Bitte manuell herunterladen:
        echo   https://clonezilla.org/downloads.php
        echo   Waehle: stable, amd64, zip Format
        echo   Speichere in: %DOWNLOAD_DIR%\
        echo.
    ) else (
        echo [OK] Clonezilla heruntergeladen
    )
)
echo.

:: ─────────────────────────────────────────────
:: Schritt 2: Rufus herunterladen
:: ─────────────────────────────────────────────

echo [2/3] Pruefe Rufus...

if exist "%DOWNLOAD_DIR%\rufus.exe" (
    echo [OK] Rufus bereits vorhanden
) else (
    echo Lade Rufus Portable herunter...

    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -Uri 'https://github.com/pbatard/rufus/releases/download/v4.6/rufus-4.6p.exe' -OutFile '%DOWNLOAD_DIR%\rufus.exe' -UseBasicParsing; Write-Host '[OK] Rufus heruntergeladen' } catch { Write-Host \"FEHLER: $($_.Exception.Message)\"; Write-Host 'Bitte manuell von https://rufus.ie herunterladen'; exit 1 }"
)
echo.

:: ─────────────────────────────────────────────
:: Schritt 3: Anleitung anzeigen
:: ─────────────────────────────────────────────

echo [3/3] Downloads abgeschlossen!
echo.
echo ===================================================
echo  NAECHSTE SCHRITTE (manuell):
echo ===================================================
echo.
echo  1. USB-Stick einstecken (mind. 32 GB)
echo     ACHTUNG: Alle Daten auf dem Stick werden geloescht!
echo.
echo  2. Rufus starten:
echo     %DOWNLOAD_DIR%\rufus.exe
echo.
echo  3. In Rufus:
echo     - Laufwerk: Deinen USB-Stick waehlen
echo     - Startart: "Datentraeger- oder ISO-Image"
echo       Klick auf AUSWAEHLEN und dann die Clonezilla
echo       ZIP-Datei aus %DOWNLOAD_DIR%\ waehlen
echo     - Partitionsschema: MBR
echo     - Dateisystem: FAT32
echo     - Klick auf START
echo.
echo  4. Nach Rufus: custom-ocs/ Ordner auf den Stick kopieren!
echo     Quelle: %~dp0custom-ocs\
echo     Ziel:   USB-Stick:\live\custom-ocs\
echo.
echo  5. Bootmenue anpassen (grub_menu_patch.txt)
echo     Siehe ANLEITUNG_USB.md fuer Details.
echo.
echo ===================================================
echo.

:: Rufus oeffnen?
choice /C JN /M "Rufus jetzt oeffnen? (J)a/(N)ein"
if errorlevel 2 goto :end
if exist "%DOWNLOAD_DIR%\rufus.exe" (
    start "" "%DOWNLOAD_DIR%\rufus.exe"
) else (
    echo Rufus nicht gefunden. Bitte manuell starten.
)

:end
echo.
pause
