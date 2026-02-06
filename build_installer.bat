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
REM   - VLC Media Player installiert
REM
REM Ergebnis: dist\fexobooth\fexobooth.exe
REM ============================================

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

REM ─────────────────────────────────────────────
REM Schritt 2: PyInstaller pruefen
REM ─────────────────────────────────────────────

pyinstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo PyInstaller nicht gefunden, installiere...
    pip install pyinstaller>=6.0.0
    if %errorlevel% neq 0 (
        echo FEHLER: PyInstaller konnte nicht installiert werden!
        pause
        exit /b 1
    )
)

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
if exist "dist\fexobooth" (
    rmdir /s /q "dist\fexobooth"
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

pyinstaller fexobooth.spec --noconfirm

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
if not exist "dist\fexobooth\assets\videos" (
    mkdir "dist\fexobooth\assets\videos"
)

REM Falls lokale Videos vorhanden, kopieren
if exist "assets\videos\start.mp4" (
    copy "assets\videos\start.mp4" "dist\fexobooth\assets\videos\" >nul
    echo [OK] start.mp4 kopiert
)
if exist "assets\videos\end.mp4" (
    copy "assets\videos\end.mp4" "dist\fexobooth\assets\videos\" >nul
    echo [OK] end.mp4 kopiert
)

REM ─────────────────────────────────────────────
REM Schritt 7: Start-Script erstellen
REM ─────────────────────────────────────────────

echo Erstelle Start-Script...

(
echo @echo off
echo cd /d "%%~dp0"
echo start "" fexobooth.exe
) > "dist\fexobooth\START.bat"

echo [OK] START.bat erstellt

REM ─────────────────────────────────────────────
REM Ergebnis
REM ─────────────────────────────────────────────

echo.
echo ===================================================
echo  BUILD ERFOLGREICH!
echo ===================================================
echo.
echo  Ausgabe: dist\fexobooth\
echo  Starten: dist\fexobooth\fexobooth.exe
echo.

REM Ordnergroesse anzeigen
for /f "tokens=3" %%a in ('dir "dist\fexobooth" /s /-c ^| findstr "Datei(en)"') do (
    set SIZE=%%a
)
echo  Groesse: ca. %SIZE% Bytes
echo.

if %VLC_FOUND%==1 (
    echo  [OK] VLC eingebettet - Hardware-Video auf Miix 310 aktiv
) else (
    echo  [!!] VLC NICHT eingebettet - nur OpenCV-Fallback
)

echo.
echo Naechste Schritte:
echo   1. dist\fexobooth\ auf USB-Stick kopieren
echo   2. Auf Tablet nach C:\fexobooth\ kopieren
echo   3. fexobooth.exe starten oder START.bat nutzen
echo.
pause
