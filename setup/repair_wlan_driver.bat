@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo.
echo ===================================================
echo    FexoBooth - WLAN-Treiber Reparatur v4
echo ===================================================
echo.

:: Admin-Check
net session >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Bitte als Administrator ausfuehren!
    pause
    exit /b 1
)

set "LOG=%~dp0wlan_repair_log.txt"

echo ========================================== > "%LOG%"
echo  FexoBooth WLAN-Reparatur v4 >> "%LOG%"
echo  Datum: %DATE% %TIME% >> "%LOG%"
echo ========================================== >> "%LOG%"

:: ── Pruefen ob WLAN schon geht ──
netsh wlan show interfaces 2>nul | findstr /C:"Zustand" /C:"State" >nul 2>&1
if not errorlevel 1 (
    echo [OK] WLAN funktioniert bereits!
    echo WLAN ist bereits OK >> "%LOG%"
    pause
    exit /b 0
)

:: ── Schritt 1: Status vorher ──
echo [1/6] Analysiere Status...
echo. >> "%LOG%"
echo === Schritt 1: Status VOR Reparatur === >> "%LOG%"
echo -- PnpDevice SD -- >> "%LOG%"
powershell -NoProfile -Command "Get-PnpDevice -EA SilentlyContinue | Where-Object { $_.InstanceId -match 'SD\\VID_024C' } | Format-Table Status,FriendlyName,InstanceId -AutoSize -Wrap" >> "%LOG%" 2>&1
echo -- SDHost Controller -- >> "%LOG%"
powershell -NoProfile -Command "Get-PnpDevice -Class SDHost -EA SilentlyContinue | Format-Table Status,FriendlyName,InstanceId -AutoSize -Wrap" >> "%LOG%" 2>&1
echo -- netsh wlan -- >> "%LOG%"
netsh wlan show interfaces >> "%LOG%" 2>&1
echo -- Treiber im Store -- >> "%LOG%"
pnputil /enum-drivers 2>nul | findstr /A /C:"oem" /C:"netrtwlans" /C:"rtwlans" >> "%LOG%" 2>&1

:: ── Schritt 2: WlanSvc ──
echo [2/6] WlanSvc Dienst sicherstellen...
echo. >> "%LOG%"
echo === Schritt 2: WlanSvc === >> "%LOG%"
sc config WlanSvc start=auto >> "%LOG%" 2>&1
sc start WlanSvc >> "%LOG%" 2>&1

:: ── Schritt 3: Treiber neu registrieren ──
echo [3/6] Treiber im DriverStore sicherstellen...
echo. >> "%LOG%"
echo === Schritt 3: Treiber registrieren === >> "%LOG%"
set "FOUND_INF="
for %%I in (C:\Windows\INF\oem*.inf) do (
    findstr /C:"netrtwlans" "%%I" >nul 2>&1
    if not errorlevel 1 (
        findstr /C:"SD\\VID_024C" "%%I" >nul 2>&1
        if not errorlevel 1 (
            echo Gefunden: %%I >> "%LOG%"
            set "FOUND_INF=%%I"
        )
    )
)
if defined FOUND_INF (
    pnputil /add-driver "%FOUND_INF%" /install >> "%LOG%" 2>&1
    echo [OK] Treiber: %FOUND_INF%
) else (
    echo [!!] Keine Realtek WLAN INF gefunden >> "%LOG%"
    echo [!!] Keine Realtek WLAN INF - Treiber muss manuell installiert werden
)

:: ── Schritt 4: Fehlerhafte Eintraege bereinigen ──
echo [4/6] Fehlerhafte Geraeteeintraege bereinigen...
echo. >> "%LOG%"
echo === Schritt 4: Stale Device bereinigen === >> "%LOG%"
powershell -NoProfile -Command "$dev = Get-PnpDevice -EA SilentlyContinue | Where-Object { $_.InstanceId -match 'SD\\VID_024C&PID_B723' }; if ($dev -and $dev.Status -ne 'OK') { Write-Host \"Entferne: $($dev.InstanceId) Status: $($dev.Status)\"; pnputil /remove-device $dev.InstanceId 2>&1 } elseif ($dev) { Write-Host \"Status OK - nicht entfernen\" } else { Write-Host 'Kein Eintrag vorhanden' }" >> "%LOG%" 2>&1

:: ── Schritt 5: SD-Hostcontroller komplett durchstarten ──
echo [5/6] SD-Hostcontroller Reset (SDIO Bus neu starten)...
echo. >> "%LOG%"
echo === Schritt 5: SD-Hostcontroller Reset === >> "%LOG%"

:: Methode A: pnputil restart
echo -- Methode A: pnputil restart -- >> "%LOG%"
pnputil /restart-device "ACPI\80860F14\1" >> "%LOG%" 2>&1
pnputil /restart-device "ACPI\80860F14\2" >> "%LOG%" 2>&1
pnputil /restart-device "ACPI\80860F14\3" >> "%LOG%" 2>&1
timeout /t 3 >nul

:: Methode B: sdbus Dienst neu starten
echo -- Methode B: sdbus restart -- >> "%LOG%"
sc stop sdbus >> "%LOG%" 2>&1
timeout /t 2 >nul
sc start sdbus >> "%LOG%" 2>&1
timeout /t 3 >nul

:: Methode C: Disable/Enable SD-Hostcontroller
echo -- Methode C: Disable/Enable SDHost -- >> "%LOG%"
powershell -NoProfile -Command "$hosts = Get-PnpDevice -Class SDHost -Status OK -EA SilentlyContinue; foreach ($h in $hosts) { Write-Host \"Disable: $($h.InstanceId)\"; Disable-PnpDevice -InstanceId $h.InstanceId -Confirm:$false -EA SilentlyContinue }; Start-Sleep 3; foreach ($h in $hosts) { Write-Host \"Enable: $($h.InstanceId)\"; Enable-PnpDevice -InstanceId $h.InstanceId -Confirm:$false -EA SilentlyContinue }; Start-Sleep 5" >> "%LOG%" 2>&1

:: Hardware-Scan
pnputil /scan-devices >> "%LOG%" 2>&1
timeout /t 5 >nul

:: ── Schritt 6: Ergebnis pruefen ──
echo [6/6] Pruefe Ergebnis...
echo. >> "%LOG%"
echo === Schritt 6: Status NACH Reparatur === >> "%LOG%"
powershell -NoProfile -Command "Get-PnpDevice -EA SilentlyContinue | Where-Object { $_.InstanceId -match 'SD\\VID_024C' } | Format-Table Status,FriendlyName,InstanceId -AutoSize -Wrap" >> "%LOG%" 2>&1
netsh wlan show interfaces >> "%LOG%" 2>&1

:: Energieverwaltung deaktivieren falls Adapter da
powershell -NoProfile -Command "$k = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}'; Get-ChildItem $k -EA SilentlyContinue | ForEach-Object { if ((Get-ItemProperty $_.PSPath -EA SilentlyContinue).DriverDesc -match 'Wireless|WiFi|WLAN|802\.11') { Set-ItemProperty $_.PSPath -Name 'PnPCapabilities' -Value 24 -Type DWord -EA SilentlyContinue } }" >> "%LOG%" 2>&1

echo ========================================== >> "%LOG%"
echo  REPARATUR ENDE >> "%LOG%"
echo ========================================== >> "%LOG%"

:: ── Ergebnis anzeigen ──
echo.
netsh wlan show interfaces 2>nul | findstr /C:"Zustand" /C:"State" >nul 2>&1
if not errorlevel 1 (
    echo ===================================================
    echo  [OK] WLAN ist wieder aktiv!
    echo ===================================================
    echo.
    echo Log: %LOG%
    pause
    exit /b 0
)

echo ===================================================
echo  WLAN noch nicht verfuegbar.
echo.
echo  WICHTIG: "Neustart" reicht bei SDIO nicht!
echo  Windows Fast-Startup ueberspringt die SDIO-Erkennung.
echo.
echo  Das Tablet wird jetzt KOMPLETT HERUNTERGEFAHREN.
echo  Danach manuell wieder EINSCHALTEN (Power-Button).
echo.
echo  Log: %LOG%
echo ===================================================
echo.
echo Druecke eine Taste zum Herunterfahren...
pause
shutdown /s /f /t 3 /c "FexoBooth WLAN-Reparatur - Herunterfahren"
