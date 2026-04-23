@echo off
REM ============================================
REM FEXOBOX HOTSPOT DIAGNOSE + AUTO-FIX
REM ============================================
REM Sammelt alle relevanten WLAN/Hotspot-Infos,
REM versucht die gaengigen Fixes und schreibt
REM ein lesbares Log auf den Desktop.
REM
REM WICHTIG: Als Administrator ausfuehren!
REM ============================================

chcp 65001 >nul

echo.
echo ================================================
echo    FEXOBOX HOTSPOT DIAGNOSE + AUTO-FIX
echo ================================================
echo.

REM Admin-Check
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo FEHLER: Bitte als Administrator ausfuehren!
    echo Rechtsklick auf diese Datei ^> "Als Administrator ausfuehren"
    pause
    exit /b 1
)

echo Starte PowerShell Diagnose-Script...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0diagnose_hotspot.ps1"
set "PS_EXIT=%errorlevel%"

echo.
if %PS_EXIT% equ 0 (
    echo ================================================
    echo    DIAGNOSE ABGESCHLOSSEN - HOTSPOT LAEUFT!
    echo ================================================
) else (
    echo ================================================
    echo    DIAGNOSE ABGESCHLOSSEN - HOTSPOT NICHT OK
    echo    Siehe Log auf dem Desktop:
    echo    hotspot_diagnose_YYYYMMDD_HHMMSS.log
    echo ================================================
)

echo.
pause
exit /b %PS_EXIT%
