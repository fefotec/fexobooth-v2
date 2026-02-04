@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: Wechsle ins Verzeichnis des Scripts
cd /d "%~dp0"

echo ============================================
echo    FexoBooth Installer Build Script
echo ============================================
echo.
echo Arbeitsverzeichnis: %cd%
echo.

:: Prüfe ob wir im richtigen Verzeichnis sind
if not exist "src\main.py" (
    echo FEHLER: Bitte dieses Script im FexoBooth-Projektverzeichnis ausführen!
    pause
    exit /b 1
)

:: Prüfe ob PyInstaller installiert ist
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller nicht gefunden. Installiere...
    pip install pyinstaller
)

:: Prüfe ob Inno Setup installiert ist
set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if "!ISCC!"=="" (
    echo.
    echo WARNUNG: Inno Setup 6 nicht gefunden!
    echo Bitte installieren von: https://jrsoftware.org/isdl.php
    echo.
    echo Das Script wird trotzdem fortfahren und die EXE erstellen.
    echo Der Installer kann dann manuell mit Inno Setup kompiliert werden.
    echo.
)

:: Erstelle installer_files Verzeichnis
echo [1/5] Erstelle Verzeichnisse...
if not exist "installer_files" mkdir installer_files
if not exist "installer_output" mkdir installer_output

:: Erstelle BAT-Dateien für den installierten Modus
echo [2/5] Erstelle BAT-Dateien für Installation...

:: start_fexobooth.bat für installierten Modus
(
echo @echo off
echo cd /d "%%~dp0"
echo start "" "FexoBooth.exe"
) > installer_files\start_fexobooth.bat

:: start_dev.bat für installierten Modus
(
echo @echo off
echo cd /d "%%~dp0"
echo start "" "FexoBooth.exe" --dev
) > installer_files\start_dev.bat

:: update_from_github.bat
(
echo @echo off
echo chcp 65001 ^>nul
echo setlocal EnableDelayedExpansion
echo.
echo echo ============================================
echo echo    FexoBooth GitHub Update
echo echo ============================================
echo echo.
echo.
echo :: GitHub Repository URL
echo set "GITHUB_REPO=fexobox/fexobooth-v2"
echo set "BRANCH=main"
echo set "DOWNLOAD_URL=https://github.com/%%GITHUB_REPO%%/archive/refs/heads/%%BRANCH%%.zip"
echo set "ZIP_FILE=%%TEMP%%\fexobooth_update.zip"
echo set "EXTRACT_DIR=%%TEMP%%\fexobooth_extract"
echo.
echo echo Lade neueste Version von GitHub...
echo echo URL: %%DOWNLOAD_URL%%
echo echo.
echo.
echo :: Download mit PowerShell
echo powershell -Command "Invoke-WebRequest -Uri '%%DOWNLOAD_URL%%' -OutFile '%%ZIP_FILE%%'" 2^>nul
echo if errorlevel 1 ^(
echo     echo FEHLER: Download fehlgeschlagen!
echo     echo Bitte prüfen Sie die Internetverbindung.
echo     pause
echo     exit /b 1
echo ^)
echo.
echo echo Download abgeschlossen.
echo echo.
echo echo Entpacke Dateien...
echo.
echo :: Lösche altes Extract-Verzeichnis falls vorhanden
echo if exist "%%EXTRACT_DIR%%" rmdir /s /q "%%EXTRACT_DIR%%"
echo mkdir "%%EXTRACT_DIR%%"
echo.
echo :: Entpacke mit PowerShell
echo powershell -Command "Expand-Archive -Path '%%ZIP_FILE%%' -DestinationPath '%%EXTRACT_DIR%%' -Force"
echo.
echo :: Finde das entpackte Verzeichnis ^(enthält Branch-Name^)
echo for /d %%%%D in ^("%%EXTRACT_DIR%%\*"^) do set "SOURCE_DIR=%%%%D"
echo.
echo echo Kopiere Quelldateien...
echo echo.
echo.
echo :: Kopiere nur Source-Dateien ^(nicht die gebundelte EXE überschreiben^)
echo xcopy "%%SOURCE_DIR%%\src" "%%~dp0src" /E /I /Y ^>nul
echo xcopy "%%SOURCE_DIR%%\assets" "%%~dp0assets" /E /I /Y ^>nul
echo xcopy "%%SOURCE_DIR%%\setup" "%%~dp0setup" /E /I /Y ^>nul
echo copy "%%SOURCE_DIR%%\config.example.json" "%%~dp0" /Y ^>nul
echo copy "%%SOURCE_DIR%%\requirements.txt" "%%~dp0" /Y ^>nul
echo.
echo :: Aufräumen
echo del "%%ZIP_FILE%%" 2^>nul
echo rmdir /s /q "%%EXTRACT_DIR%%" 2^>nul
echo.
echo echo ============================================
echo echo    Update abgeschlossen!
echo echo ============================================
echo echo.
echo echo Die neuesten Quelldateien wurden heruntergeladen.
echo echo.
echo echo HINWEIS: Für ein vollständiges Update mit neuen
echo echo Dependencies muss der Installer neu gebaut werden.
echo echo.
echo pause
) > installer_files\update_from_github.bat

echo [3/5] Erstelle EXE mit PyInstaller...
echo.

:: Lösche alte Builds
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

:: Führe PyInstaller aus
python -m PyInstaller fexobooth.spec --noconfirm

if errorlevel 1 (
    echo.
    echo FEHLER: PyInstaller Build fehlgeschlagen!
    pause
    exit /b 1
)

echo.
echo [4/5] PyInstaller Build erfolgreich!
echo.

:: Kompiliere Installer falls Inno Setup verfügbar
if not "!ISCC!"=="" (
    echo [5/5] Erstelle Installer mit Inno Setup...
    "!ISCC!" installer.iss

    if errorlevel 1 (
        echo.
        echo FEHLER: Inno Setup Kompilierung fehlgeschlagen!
        pause
        exit /b 1
    )

    echo.
    echo ============================================
    echo    BUILD ERFOLGREICH ABGESCHLOSSEN!
    echo ============================================
    echo.
    echo Installer erstellt: installer_output\FexoBooth_Setup_2.0.exe
    echo.
) else (
    echo [5/5] Inno Setup nicht installiert - Installer übersprungen
    echo.
    echo ============================================
    echo    PYINSTALLER BUILD ABGESCHLOSSEN!
    echo ============================================
    echo.
    echo EXE erstellt in: dist\FexoBooth\
    echo.
    echo Um den Installer zu erstellen:
    echo 1. Installiere Inno Setup 6 von https://jrsoftware.org/isdl.php
    echo 2. Öffne installer.iss mit Inno Setup
    echo 3. Klicke auf Build -^> Compile
    echo.
)

echo Drücke eine Taste zum Beenden...
pause >nul
