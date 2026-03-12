@echo off
chcp 65001 >nul
setlocal

echo.
echo ===================================================
echo    Windows Update DAUERHAFT deaktivieren
echo ===================================================
echo.
echo Fuer FexoBooth-Tablets die offline betrieben werden.
echo Updates sind unnoetig und koennen das Tablet lahmlegen!
echo.

:: Admin-Check
net session >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Dieses Script muss als Administrator ausgefuehrt werden!
    echo          Rechtsklick → "Als Administrator ausfuehren"
    echo.
    pause
    exit /b 1
)

echo Deaktiviere Windows Update...
echo.

:: ─────────────────────────────────────────────
:: 1. Windows Update Dienst stoppen und deaktivieren
:: ─────────────────────────────────────────────

sc stop wuauserv >nul 2>&1
sc config wuauserv start=disabled >nul 2>&1
if not errorlevel 1 (
    echo [OK] Windows Update Dienst (wuauserv) deaktiviert
) else (
    echo [FEHLER] Konnte wuauserv nicht deaktivieren
)

:: ─────────────────────────────────────────────
:: 2. Windows Update Medic Service deaktivieren
::    (Dieser Dienst reaktiviert Windows Update!)
:: ─────────────────────────────────────────────

sc stop WaaSMedicSvc >nul 2>&1
sc config WaaSMedicSvc start=disabled >nul 2>&1
if not errorlevel 1 (
    echo [OK] Update Medic Service (WaaSMedicSvc) deaktiviert
) else (
    echo [INFO] WaaSMedicSvc nicht vorhanden oder bereits deaktiviert
)

:: ─────────────────────────────────────────────
:: 3. Update Orchestrator Service deaktivieren
:: ─────────────────────────────────────────────

sc stop UsoSvc >nul 2>&1
sc config UsoSvc start=disabled >nul 2>&1
if not errorlevel 1 (
    echo [OK] Update Orchestrator (UsoSvc) deaktiviert
) else (
    echo [INFO] UsoSvc nicht vorhanden oder bereits deaktiviert
)

:: ─────────────────────────────────────────────
:: 4. Delivery Optimization deaktivieren
:: ─────────────────────────────────────────────

sc stop DoSvc >nul 2>&1
sc config DoSvc start=disabled >nul 2>&1
if not errorlevel 1 (
    echo [OK] Delivery Optimization (DoSvc) deaktiviert
) else (
    echo [INFO] DoSvc nicht vorhanden oder bereits deaktiviert
)

:: ─────────────────────────────────────────────
:: 5. Geplante Update-Tasks deaktivieren
:: ─────────────────────────────────────────────

schtasks /Change /TN "\Microsoft\Windows\WindowsUpdate\Scheduled Start" /Disable >nul 2>&1
echo [OK] Geplante Update-Tasks deaktiviert

:: ─────────────────────────────────────────────
:: 6. Registry: Updates per Gruppenrichtlinie blockieren
:: ─────────────────────────────────────────────

reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v NoAutoUpdate /t REG_DWORD /d 1 /f >nul 2>&1
if not errorlevel 1 (
    echo [OK] Registry: Automatische Updates deaktiviert
) else (
    echo [FEHLER] Konnte Registry nicht aendern
)

:: Kein Zugriff auf Windows Update Server
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate" /v DoNotConnectToWindowsUpdateInternetLocations /t REG_DWORD /d 1 /f >nul 2>&1
echo [OK] Registry: Verbindung zu Update-Servern blockiert

:: ─────────────────────────────────────────────
:: 7. Neustart-Erzwingung deaktivieren
:: ─────────────────────────────────────────────

reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v NoAutoRebootWithLoggedOnUsers /t REG_DWORD /d 1 /f >nul 2>&1
echo [OK] Registry: Automatischer Neustart blockiert

:: ─────────────────────────────────────────────
:: Zusammenfassung
:: ─────────────────────────────────────────────

echo.
echo ===================================================
echo    Windows Update ist jetzt DAUERHAFT deaktiviert!
echo ===================================================
echo.
echo Deaktivierte Dienste:
echo   - Windows Update (wuauserv)
echo   - Update Medic (WaaSMedicSvc)
echo   - Update Orchestrator (UsoSvc)
echo   - Delivery Optimization (DoSvc)
echo.
echo Ein Neustart ist empfohlen.
echo.

pause
