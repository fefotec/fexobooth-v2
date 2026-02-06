@echo off
REM ============================================
REM FEXOBOX HOTSPOT SETUP
REM Richtet Windows Mobile Hotspot ein und
REM konfiguriert Auto-Start beim Systemstart
REM ============================================
REM WICHTIG: Als Administrator ausfuehren!
REM ============================================

echo.
echo ========================================
echo    FEXOBOX HOTSPOT SETUP
echo ========================================
echo.

REM Admin-Check
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo FEHLER: Bitte als Administrator ausfuehren!
    echo Rechtsklick auf diese Datei ^> "Als Administrator ausfuehren"
    pause
    exit /b 1
)

echo Starte PowerShell Setup-Script...
echo.

REM PowerShell-Script ausfuehren (im gleichen Verzeichnis)
powershell -ExecutionPolicy Bypass -File "%~dp0setup_hotspot.ps1"

if %errorlevel% neq 0 (
    echo.
    echo WARNUNG: PowerShell-Script fehlgeschlagen.
    echo Bitte versuchen Sie es erneut oder konfigurieren Sie den Hotspot manuell.
    echo.
)

pause
