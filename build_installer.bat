@echo off
REM ============================================
REM FEXOBOOTH BUILD-SCRIPT
REM ============================================
REM
REM Erstellt eine ausfuehrbare Distribution mit
REM eingebettetem VLC fuer Hardware-Video-Decoding.
REM
REM Voraussetzungen:
REM   - Python 3.10+ installiert
REM   - pip install -r requirements.txt
REM   - .NET SDK 8 installiert (fuer die Nikon-Bridge)
REM   - VLC Media Player installiert
REM
REM Ergebnis: installer_output\fexobooth.zip
REM ============================================

REM Ins Verzeichnis des Scripts wechseln (wichtig bei Admin-Start)
cd /d "%~dp0"

echo.
echo ===================================================
echo       FEXOBOOTH BUILD
echo ===================================================
echo.

REM ─────────────────────────────────────────────
REM Schritt 1: Python pruefen
REM ─────────────────────────────────────────────

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo FEHLER: Python nicht gefunden!
    echo Bitte Python 3.10+ installieren und zum PATH hinzufuegen.
    pause
    exit /b 1
)

echo [OK] Python gefunden

REM .NET SDK frueh pruefen, bevor PyInstaller und andere teure Schritte laufen.
where dotnet >nul 2>&1
if %errorlevel% neq 0 (
    echo FEHLER: .NET SDK nicht gefunden - Nikon-Bridge kann nicht frisch gebaut werden.
    echo Ein alter Bridge-Build wird aus Sicherheitsgruenden NICHT verpackt.
    echo Bitte .NET SDK 8 installieren oder den GitHub-Actions-Build verwenden.
    pause
    exit /b 1
)

echo [OK] .NET SDK gefunden

REM ─────────────────────────────────────────────
REM Schritt 2: PyInstaller pruefen
REM ─────────────────────────────────────────────

pyinstaller --version >nul 2>&1
if %errorlevel% equ 0 goto :pyinstaller_ok

echo PyInstaller nicht gefunden, installiere...
pip install "pyinstaller>=6.0.0"
if %errorlevel% neq 0 (
    echo FEHLER: PyInstaller konnte nicht installiert werden!
    pause
    exit /b 1
)

:pyinstaller_ok
echo [OK] PyInstaller gefunden

REM ─────────────────────────────────────────────
REM Schritt 3: VLC suchen
REM ─────────────────────────────────────────────

set VLC_FOUND=0

REM Umgebungsvariable pruefen
if defined VLC_PATH (
    if exist "%VLC_PATH%\libvlc.dll" (
        echo [OK] VLC gefunden via VLC_PATH: %VLC_PATH%
        set VLC_FOUND=1
    )
)

REM Standard-Pfade pruefen
if %VLC_FOUND%==0 (
    if exist "C:\Program Files\VideoLAN\VLC\libvlc.dll" (
        set VLC_PATH=C:\Program Files\VideoLAN\VLC
        echo [OK] VLC gefunden: %VLC_PATH%
        set VLC_FOUND=1
    )
)

if %VLC_FOUND%==0 (
    if exist "C:\Program Files (x86)\VideoLAN\VLC\libvlc.dll" (
        set "VLC_PATH=C:\Program Files (x86)\VideoLAN\VLC"
        echo [OK] VLC gefunden: %VLC_PATH%
        set VLC_FOUND=1
    )
)

if %VLC_FOUND%==0 (
    echo.
    echo WARNUNG: VLC nicht gefunden!
    echo Video-Wiedergabe wird nur mit OpenCV-Fallback funktionieren.
    echo.
    echo Um VLC einzubinden:
    echo   1. VLC Media Player installieren
    echo   2. Oder: set VLC_PATH=C:\Pfad\zu\VLC
    echo.
    set /p CONTINUE="Trotzdem ohne VLC bauen? (J/N): "
    if /i not "%CONTINUE%"=="J" (
        exit /b 1
    )
)

REM ─────────────────────────────────────────────
REM Schritt 4: Alte Builds aufraumen
REM ─────────────────────────────────────────────

echo.
echo Raeume alte Builds auf...

if exist "build\fexobooth" (
    rmdir /s /q "build\fexobooth"
)
if exist "installer_output" (
    rmdir /s /q "installer_output"
)

echo [OK] Aufgeraeumt

REM ─────────────────────────────────────────────
REM Schritt 5: PyInstaller Build
REM ─────────────────────────────────────────────

echo.
echo ===================================================
echo  PyInstaller Build starten...
echo ===================================================
echo.

pyinstaller fexobooth.spec --noconfirm --distpath installer_output

if %errorlevel% neq 0 (
    echo.
    echo FEHLER: PyInstaller Build fehlgeschlagen!
    echo Bitte Log-Ausgabe oben pruefen.
    pause
    exit /b 1
)

echo.
echo [OK] PyInstaller Build erfolgreich

REM ─────────────────────────────────────────────
REM Schritt 6: Videos-Ordner erstellen
REM ─────────────────────────────────────────────

echo Erstelle Videos-Ordner...
if not exist "installer_output\fexobooth\assets\videos" (
    mkdir "installer_output\fexobooth\assets\videos"
)

REM Falls lokale Videos vorhanden, kopieren
if exist "assets\videos\start.mp4" (
    copy "assets\videos\start.mp4" "installer_output\fexobooth\assets\videos\" >nul
    echo [OK] start.mp4 kopiert
)
if exist "assets\videos\end.mp4" (
    copy "assets\videos\end.mp4" "installer_output\fexobooth\assets\videos\" >nul
    echo [OK] end.mp4 kopiert
)

REM Absturz-Helfer neben die Setup-EXE legen (2.4.30), damit er beim
REM Kopieren auf den USB-Stick automatisch mitgeht.
if exist "setup\Absturz-Infos-sammeln.bat" (
    copy "setup\Absturz-Infos-sammeln.bat" "installer_output\" >nul
    echo [OK] Absturz-Infos-sammeln.bat neben die Setup-EXE gelegt
)
if exist "setup\Kamera-Messung-starten.bat" (
    copy "setup\Kamera-Messung-starten.bat" "installer_output\" >nul
    echo [OK] Kamera-Messung-starten.bat neben die Setup-EXE gelegt
)

REM ─────────────────────────────────────────────
REM Schritt 7: Start-Script erstellen
REM ─────────────────────────────────────────────

echo Erstelle Start-Script...

(
echo @echo off
echo cd /d "%%~dp0"
echo start "" fexobooth.exe
) > "installer_output\fexobooth\START.bat"

echo [OK] START.bat erstellt

REM ─────────────────────────────────────────────
REM Schritt 8: FexoNikonBridge frisch bauen und fuer Nikon beilegen
REM ─────────────────────────────────────────────

echo.
echo Baue FexoNikonBridge fuer Nikon frisch...

dotnet build "bridge\FexoNikonBridge\FexoNikonBridge.csproj" -c Release --nologo --no-incremental
if %errorlevel% neq 0 (
    echo FEHLER: FexoNikonBridge-Build fehlgeschlagen.
    echo Der Installer wird nicht mit einer alten oder fehlenden Nikon-Bridge erstellt.
    echo Falls Dateien gesperrt sind: FexoBooth und FexoNikonBridge vollstaendig schliessen.
    pause
    exit /b 1
)

python "tools\nikon_bridge_protocol_test.py"
if %errorlevel% neq 0 (
    echo FEHLER: FexoNikonBridge-Protokolltest fehlgeschlagen.
    pause
    exit /b 1
)

set "BRIDGE_BIN=bridge\FexoNikonBridge\bin\Release\net48"
if exist "%BRIDGE_BIN%\FexoNikonBridge.exe" (
    xcopy /E /I /Y "%BRIDGE_BIN%" "installer_output\fexobooth\bridge\" >nul
    echo [OK] Frische FexoNikonBridge wird mitinstalliert ^(unsichtbarer Nikon-Prozess^)
) else (
    echo FEHLER: Bridge-Build meldete Erfolg, aber FexoNikonBridge.exe fehlt.
    pause
    exit /b 1
)

REM ─────────────────────────────────────────────
REM Schritt 9: Windows-Installer erstellen
REM ─────────────────────────────────────────────

echo.

set "ISCC_PATH="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if not defined ISCC_PATH (
    if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
        set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
    )
)
if not defined ISCC_PATH (
    if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" (
        set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
    )
)

if not defined ISCC_PATH (
    echo WARNUNG: Inno Setup nicht gefunden!
    echo Nur ZIP wird erstellt, kein Installer.
    echo Installiere Inno Setup 6 fuer einen richtigen Windows-Installer.
    goto :skip_installer
)

echo ===================================================
echo  Windows-Installer erstellen...
echo ===================================================
echo.

REM App-Version aus src/__init__.py auslesen — damit der Installer-Dateiname
REM die echte App-Version traegt (FexoBooth_Setup_2.4.4.exe statt _2.1.exe).
set "APP_VERSION="
for /f "tokens=2 delims== " %%V in ('findstr /B "__version__" src\__init__.py') do (
    set "APP_VERSION=%%~V"
)
REM Anfuehrungszeichen entfernen falls vorhanden
set APP_VERSION=%APP_VERSION:"=%
if "%APP_VERSION%"=="" (
    echo FEHLER: App-Version konnte nicht aus src\__init__.py gelesen werden.
    echo Der Installer wird nicht mit einem falschen Versionsnamen erstellt.
    pause
    exit /b 1
)
echo App-Version: %APP_VERSION%

"%ISCC_PATH%" /DMyAppVersion=%APP_VERSION% installer.iss

if %errorlevel% neq 0 (
    echo WARNUNG: Installer-Erstellung fehlgeschlagen.
) else (
    echo [OK] Installer erstellt: installer_output\FexoBooth_Setup_%APP_VERSION%.exe
)

:skip_installer

REM ─────────────────────────────────────────────
REM Schritt 10: ZIP erstellen (fuer OTA-Updates via GitHub Releases)
REM ─────────────────────────────────────────────

echo.
echo Erstelle ZIP fuer OTA-Updates...
powershell -Command "Compress-Archive -Path 'installer_output\fexobooth\*' -DestinationPath 'installer_output\fexobooth.zip' -Force"
if %errorlevel% neq 0 (
    echo WARNUNG: ZIP konnte nicht erstellt werden.
) else (
    echo [OK] ZIP erstellt: installer_output\fexobooth.zip
    echo     (Dieses ZIP als Asset zum GitHub Release hochladen!)
)

REM ─────────────────────────────────────────────
REM Schritt 11: Build-Ordner aufraeumen
REM ─────────────────────────────────────────────

echo.
echo Raeume Build-Ordner auf...
if exist "installer_output\fexobooth" (
    rmdir /s /q "installer_output\fexobooth"
    echo [OK] Build-Ordner entfernt - nur Installer + ZIP bleiben
)

REM ─────────────────────────────────────────────
REM Ergebnis
REM ─────────────────────────────────────────────

echo.
echo ===================================================
echo  BUILD ERFOLGREICH!
echo ===================================================
echo.

if exist "installer_output\FexoBooth_Setup_%APP_VERSION%.exe" (
    echo  Installer: installer_output\FexoBooth_Setup_%APP_VERSION%.exe
)
if exist "installer_output\fexobooth.zip" (
    echo  ZIP:       installer_output\fexobooth.zip
)

echo.

if %VLC_FOUND%==1 (
    echo  [OK] VLC eingebettet - Hardware-Video auf Miix 310 aktiv
) else (
    echo  [!!] VLC NICHT eingebettet - nur OpenCV-Fallback
)

echo.
echo Naechste Schritte:
echo.
echo   ERSTINSTALLATION (neue Tablets):
echo   1. FexoBooth_Setup_%APP_VERSION%.exe auf USB-Stick kopieren
echo   2. Auf Tablet ausfuehren - installiert nach C:\FexoBooth\
echo.
echo   OTA-UPDATE (bestehende Tablets):
echo   1. GitHub Release erstellen mit Tag (z.B. v2.1.0)
echo   2. fexobooth.zip als Asset zum Release hochladen
echo   3. Tablets: Service-Menu -^> "Software aktualisieren"
echo      oder: update_from_github.bat ausfuehren
echo.
pause
