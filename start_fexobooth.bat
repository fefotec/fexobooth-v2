@echo off
REM ============================================
REM FEXOBOOTH STARTEN (Offline-Version)
REM ============================================

echo.
echo ===================================
echo       FEXOBOOTH STARTET...
echo ===================================
echo.

cd /d C:\fexobooth\fexobooth-v2
if %errorlevel% neq 0 (
    REM Fallback auf alten Pfad
    cd /d C:\fexobooth\fexobooth
    if %errorlevel% neq 0 (
        echo FEHLER: Projektverzeichnis nicht gefunden!
        pause
        exit /b 1
    )
)

echo Verzeichnis: %CD%
echo.

REM Starte Fexobooth
python src/main.py

REM Falls Fehler auftreten
if %errorlevel% neq 0 (
    echo.
    echo ===================================
    echo    FEHLER beim Starten!
    echo ===================================
    echo.
    pause
)
