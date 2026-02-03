@echo off
REM ============================================
REM FEXOBOX - EINMALIGES HOTSPOT SETUP
REM ============================================
REM WICHTIG: Rechtsklick > "Als Administrator ausfuehren"
REM ============================================

echo.
echo ================================================
echo    FEXOBOX HOTSPOT - EINMALIGES SETUP
echo ================================================
echo.
echo Dieses Script muss nur EINMAL ausgefuehrt werden!
echo Danach startet der Hotspot automatisch bei jedem Login.
echo.
echo WICHTIG: Als Administrator ausfuehren!
echo.
pause

REM Admin-Check
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ================================================
    echo    FEHLER: Keine Admin-Rechte!
    echo ================================================
    echo.
    echo Bitte Rechtsklick auf diese Datei und dann
    echo "Als Administrator ausfuehren" waehlen.
    echo.
    pause
    exit /b 1
)

echo.
echo Starte PowerShell Setup-Script...
echo.

REM PowerShell-Script ausfuehren
powershell -ExecutionPolicy Bypass -File "%~dp0setup_hotspot.ps1"

echo.
echo ================================================
echo    FERTIG!
echo ================================================
echo.
echo Hotspot-Daten zum Merken:
echo    WLAN-Name: fexobox-gallery
echo    Passwort:  fotobox123
echo.
echo Jetzt Tablet neustarten und testen!
echo.
pause
