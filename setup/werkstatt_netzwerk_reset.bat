@echo off
chcp 65001 >nul
REM ============================================
REM FEXOBOOTH - WERKSTATT NETZWERK-RESET (Radikal)
REM ============================================
REM Fuer harte Faelle, in denen sich eine Box trotz automatischer
REM WLAN-Selbstheilung (App) und "WLAN-Radikal-Reparatur" (3198-Menue)
REM nicht ins Firmen-WLAN einbucht.
REM
REM Macht:
REM   1. Optional: Box umbenennen
REM   2. Netzwerk-Werksreset (TCP/IP, Winsock, DNS)
REM   3. ALLE WLAN-Profile loeschen
REM   4. Firmen-WLAN-Profil frisch anlegen (maschinenunabhaengig,
REM      via company_wlan_setup.ps1 - funktioniert auf jedem Image!)
REM   5. Neustart
REM
REM Als Administrator ausfuehren!
REM ============================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [FEHLER] Bitte per Rechtsklick "Als Administrator ausfuehren"!
    pause
    exit /b 1
)

echo ===================================================
echo   FEXOBOOTH WERKSTATT NETZWERK-RESET
echo ===================================================
echo.
set /p "boxname=Neuer Box-Name (leer = Name behalten): "

if not "%boxname%"=="" (
    echo [1/5] Benenne Box um auf: %boxname% ...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Rename-Computer -NewName '%boxname%' -Force"
) else (
    echo [1/5] Box-Name bleibt unveraendert.
)

echo [2/5] Setze TCP/IP-Stack und Winsock zurueck...
netsh int ip reset >nul 2>&1
netsh winsock reset >nul 2>&1
ipconfig /flushdns >nul 2>&1

echo [3/5] Loesche alle WLAN-Profile...
netsh wlan delete profile name=* >nul 2>&1

echo [4/5] Lege Firmen-WLAN-Profil frisch an und verbinde...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0company_wlan_setup.ps1" -InstallDir "%~dp0.."

echo [5/5] Fertig - Box startet in 10 Sekunden neu...
echo        (Nach dem Neustart sollte die Box im fexon WLAN sein
echo         und sich im Dashboard melden.)
shutdown /r /f /t 10 /c "FexoBooth: Neustart nach Werkstatt-Netzwerk-Reset"
pause
