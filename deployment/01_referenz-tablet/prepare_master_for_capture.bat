@echo off
REM ============================================
REM FexoBooth Master-Tablet Vorbereitung
REM ============================================
REM Bereitet das Master-Tablet darauf vor, dass C auf
REM 22 GB geschrumpft werden kann (damit das Image auch
REM auf 32 GB Tablets passt).
REM
REM Deaktiviert/loescht alle System-Dateien die das
REM Shrinken blockieren:
REM   - hiberfil.sys (Ruhezustand)
REM   - pagefile.sys (Auslagerungsdatei)
REM   - Wiederherstellungspunkte (Shadow Copies)
REM   - USN Journal
REM   - Windows Search Index (Windows.edb)
REM   - Defender Quarantaene
REM
REM WICHTIG: Rechtsklick auf diese Datei
REM          - "Als Administrator ausfuehren"
REM ============================================

chcp 65001 >nul

REM --- Admin-Check ---
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo ====================================================
    echo   FEHLER: Nicht als Administrator gestartet!
    echo ====================================================
    echo.
    echo   Rechtsklick auf diese Datei
    echo   - "Als Administrator ausfuehren"
    echo.
    pause
    exit /b 1
)

echo ====================================================
echo    FEXOBOOTH - MASTER-TABLET VORBEREITUNG
echo    fuer Image-Capture (C-Shrink)
echo ====================================================
echo.
echo Dieses Script bereitet das Master-Tablet darauf vor,
echo dass die C-Partition auf ca. 22 GB geschrumpft werden
echo kann. So passt das Image spaeter auch auf 32 GB Tablets.
echo.
echo Es werden folgende System-Dateien entfernt/deaktiviert:
echo   [1] Ruhezustand (hiberfil.sys)
echo   [2] Auslagerungsdatei (pagefile.sys)
echo   [3] Wiederherstellungspunkte
echo   [4] USN Journal
echo   [5] Windows Search Index
echo   [6] Defender Quarantaene
echo.
echo DANACH muss das Tablet NEU GESTARTET werden,
echo bevor der Defragmentierer ausgefuehrt wird.
echo.
choice /C JN /M "Jetzt starten? (J)a / (N)ein"
if errorlevel 2 exit /b 0

REM Log-Datei auf dem Desktop
set "LOG=%USERPROFILE%\Desktop\prepare_master_log.txt"
echo ==================================================== > "%LOG%"
echo  Master-Tablet Vorbereitung %DATE% %TIME% >> "%LOG%"
echo ==================================================== >> "%LOG%"

REM ============================================
REM [1/6] Hibernation aus
REM ============================================
echo.
echo [1/6] Deaktiviere Ruhezustand...
echo.
echo === [1/6] Hibernation === >> "%LOG%"
powercfg -h off >> "%LOG%" 2>&1
if errorlevel 1 (
    echo       WARNUNG: powercfg fehlgeschlagen ^(siehe Log^)
) else (
    echo       OK - hiberfil.sys wird geloescht
)

REM ============================================
REM [2/6] Pagefile deaktivieren
REM ============================================
echo.
echo [2/6] Deaktiviere Auslagerungsdatei...
echo.
echo === [2/6] Pagefile === >> "%LOG%"

REM Methode 1: WMIC (aelteres Windows)
wmic computersystem where name="%COMPUTERNAME%" set AutomaticManagedPagefile=False >> "%LOG%" 2>&1
wmic pagefileset where name="C:\\pagefile.sys" delete >> "%LOG%" 2>&1

REM Methode 2: PowerShell (neueres Windows / Fallback)
powershell -NoProfile -Command "try { $cs = Get-WmiObject Win32_ComputerSystem -EnableAllPrivileges; $cs.AutomaticManagedPagefile = $false; $cs.Put() | Out-Null; Get-WmiObject Win32_PageFileSetting | ForEach-Object { $_.Delete() }; Write-Host 'PowerShell-Pagefile: OK' } catch { Write-Host ('PowerShell-Pagefile: ' + $_.Exception.Message) }" >> "%LOG%" 2>&1

echo       OK - pagefile.sys wird nach Neustart geloescht

REM ============================================
REM [3/6] Shadow Copies / System Restore loeschen
REM ============================================
echo.
echo [3/6] Loesche Wiederherstellungspunkte...
echo.
echo === [3/6] Shadow Copies === >> "%LOG%"

REM Alle Shadow Copies loeschen
vssadmin delete shadows /for=C: /all /quiet >> "%LOG%" 2>&1
vssadmin delete shadows /all /quiet >> "%LOG%" 2>&1

REM System Protection deaktivieren
powershell -NoProfile -Command "try { Disable-ComputerRestore -Drive 'C:\' -ErrorAction Stop; Write-Host 'System-Restore deaktiviert' } catch { Write-Host ('System-Restore: ' + $_.Exception.Message) }" >> "%LOG%" 2>&1

echo       OK - Wiederherstellungspunkte geloescht

REM ============================================
REM [4/6] USN Journal loeschen
REM ============================================
echo.
echo [4/6] Loesche USN Journal...
echo.
echo === [4/6] USN Journal === >> "%LOG%"
fsutil usn deletejournal /d /n C: >> "%LOG%" 2>&1
if errorlevel 1 (
    echo       WARNUNG: USN Journal konnte nicht geloescht werden
) else (
    echo       OK
)

REM ============================================
REM [5/6] Windows Search Service + Index
REM ============================================
echo.
echo [5/6] Stoppe Windows Search und loesche Index...
echo.
echo === [5/6] Search Index === >> "%LOG%"
sc stop WSearch >> "%LOG%" 2>&1
timeout /t 2 >nul
sc config WSearch start= disabled >> "%LOG%" 2>&1
del /f /q "C:\ProgramData\Microsoft\Search\Data\Applications\Windows\Windows.edb" 2>> "%LOG%"
del /f /q "C:\ProgramData\Microsoft\Search\Data\Applications\Windows\*.log" 2>> "%LOG%"
echo       OK - Index geloescht

REM ============================================
REM [6/6] Defender Quarantaene + Caches bereinigen
REM ============================================
echo.
echo [6/6] Bereinige Defender-Quarantaene und temporaere Dateien...
echo.
echo === [6/6] Defender + Temp === >> "%LOG%"

REM Defender Quarantaene
powershell -NoProfile -Command "try { & 'C:\Program Files\Windows Defender\MpCmdRun.exe' -RemoveDefinitions -All; Write-Host 'Defender Quarantaene: OK' } catch { Write-Host ('Defender: ' + $_.Exception.Message) }" >> "%LOG%" 2>&1

REM Windows Update Cleanup
echo       - Windows Update-Cache bereinigen...
net stop wuauserv >nul 2>&1
net stop bits >nul 2>&1
rd /s /q "C:\Windows\SoftwareDistribution\Download" 2>> "%LOG%"
mkdir "C:\Windows\SoftwareDistribution\Download" 2>nul
net start wuauserv >nul 2>&1
net start bits >nul 2>&1

REM Temp-Ordner leeren
echo       - Temp-Dateien loeschen...
del /f /s /q "%TEMP%\*.*" 2>nul
del /f /s /q "C:\Windows\Temp\*.*" 2>nul

echo       OK

REM ============================================
REM Status-Check
REM ============================================
echo.
echo ====================================================
echo    STATUS NACH BEREINIGUNG
echo ====================================================
echo.
echo === STATUS === >> "%LOG%"

echo Pruefe ob pagefile/hiberfil noch existieren:
if exist "C:\pagefile.sys" (
    echo   [!] pagefile.sys existiert noch - wird nach Neustart geloescht
) else (
    echo   [OK] pagefile.sys bereits geloescht
)
if exist "C:\hiberfil.sys" (
    echo   [!] hiberfil.sys existiert noch - wird nach Neustart geloescht
) else (
    echo   [OK] hiberfil.sys bereits geloescht
)

echo.
echo Freier Speicher auf C: nach Bereinigung:
dir C:\ | findstr /C:"Bytes frei"

echo.
echo ====================================================
echo    FERTIG - TABLET JETZT NEU STARTEN!
echo ====================================================
echo.
echo WICHTIG:
echo   1. Tablet jetzt NEU STARTEN ^(Start - Ein/Aus - Neu starten^)
echo   2. Nach Neustart: defrag_and_check.bat ausfuehren
echo      ^(liegt im gleichen Ordner wie dieses Script^)
echo.
echo Log-Datei: %LOG%
echo.

choice /C JN /M "Jetzt automatisch neu starten? (J)a / (N)ein=Spaeter selbst"
if errorlevel 2 (
    echo.
    echo OK - bitte Tablet spaeter selbst neu starten.
    echo.
    pause
    exit /b 0
)

echo.
echo Tablet wird in 10 Sekunden neu gestartet...
shutdown /r /t 10 /c "FexoBooth Master-Tablet Vorbereitung - Neustart"
echo Abbrechen mit: shutdown /a
pause
exit /b 0
