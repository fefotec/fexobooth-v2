@echo off
REM ============================================
REM FexoBooth Master-Tablet Defrag + Auto-Shrink
REM ============================================
REM NACH prepare_master_for_capture.bat und Neustart
REM ausfuehren.
REM
REM Defragmentiert C, konsolidiert den freien Speicher,
REM und verkleinert C automatisch so, dass am Disk-Ende
REM 2 GB Reserve fuer robustes Klonen frei bleiben.
REM ============================================

chcp 65001 >nul

REM --- Admin-Check ---
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo FEHLER: Rechtsklick - "Als Administrator ausfuehren"
    echo.
    pause
    exit /b 1
)

echo ====================================================
echo    FEXOBOOTH - MASTER-TABLET DEFRAG + CHECK
echo ====================================================
echo.
echo Dieses Script macht nacheinander:
echo   [1] Pruefung ob System-Dateien geloescht sind
echo   [2] Defragmentierung und Konsolidierung ^(~10-20 Min^)
echo   [3] C: automatisch um Reserve verkleinern ^(2 GB Luft^)
echo   [4] Kontrolle der finalen Partitionsgroesse
echo.
pause

set "LOG=%USERPROFILE%\Desktop\defrag_check_log.txt"
echo ==================================================== > "%LOG%"
echo  Defrag + Check %DATE% %TIME% >> "%LOG%"
echo ==================================================== >> "%LOG%"

REM ============================================
REM [1/4] Pruefung
REM ============================================
echo.
echo [1/4] Pruefe System-Dateien auf C:...
echo.
echo === [1/4] Pruefung === >> "%LOG%"

set "BLOCKER_FOUND=0"

if exist "C:\pagefile.sys" (
    echo   [!!] pagefile.sys existiert noch - das wird das Shrinken blockieren!
    echo        pagefile.sys noch da >> "%LOG%"
    set "BLOCKER_FOUND=1"
) else (
    echo   [OK] pagefile.sys ist weg
)

if exist "C:\hiberfil.sys" (
    echo   [!!] hiberfil.sys existiert noch - das wird das Shrinken blockieren!
    echo        hiberfil.sys noch da >> "%LOG%"
    set "BLOCKER_FOUND=1"
) else (
    echo   [OK] hiberfil.sys ist weg
)

if "%BLOCKER_FOUND%"=="1" (
    echo.
    echo ====================================================
    echo   WARNUNG: System-Dateien sind noch da!
    echo ====================================================
    echo.
    echo Bitte nochmal ausfuehren:
    echo   1. prepare_master_for_capture.bat ^(als Admin^)
    echo   2. Tablet NEU STARTEN
    echo   3. Dann erst dieses Script
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] System-Dateien sind weg, weiter mit Defrag.
echo.

REM ============================================
REM [2/4] Defragmentierung
REM ============================================
echo.
echo [2/4] Starte Defragmentierung und Konsolidierung...
echo.
echo Dies dauert ca. 10-20 Minuten. Bitte NICHT abbrechen!
echo.
echo === [2/4] Defrag === >> "%LOG%"

REM /X = Konsolidiert freien Speicher
REM /W = Komplett (alle Fragmente)
REM /V = Verbose (mehr Info)
defrag C: /X /W /V >> "%LOG%" 2>&1

echo.
echo [OK] Defragmentierung abgeschlossen.

REM ============================================
REM [3/4] Automatischer Shrink
REM ============================================
echo.
echo [3/4] Verkleinere C: automatisch, damit 2 GB Reserve bleiben...
echo.
echo === [3/4] Auto-Shrink C === >> "%LOG%"

set "SHRINK_SCRIPT=%~dp0auto_shrink_c.ps1"
if not exist "%SHRINK_SCRIPT%" (
    echo.
    echo FEHLER: auto_shrink_c.ps1 wurde nicht gefunden!
    echo Erwartet: %SHRINK_SCRIPT%
    echo.
    echo FEHLER: auto_shrink_c.ps1 fehlt >> "%LOG%"
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SHRINK_SCRIPT%" -ReserveBytes 2147483648
set "SHRINK_EXIT=%ERRORLEVEL%"
echo Auto-Shrink Exit-Code: %SHRINK_EXIT% >> "%LOG%"

if not "%SHRINK_EXIT%"=="0" (
    if "%SHRINK_EXIT%"=="5" goto :chkdsk_required
    echo.
    echo ====================================================
    echo   FEHLER: C: konnte nicht automatisch vorbereitet werden
    echo ====================================================
    echo.
    echo Das Image darf jetzt NICHT erstellt werden.
    echo.
    echo Bitte:
    echo   1. prepare_master_for_capture.bat erneut als Admin ausfuehren
    echo   2. Tablet neu starten
    echo   3. defrag_and_check.bat erneut als Admin ausfuehren
    echo.
    echo Details: %USERPROFILE%\Desktop\auto_shrink_c_log.txt
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] C: hat jetzt 2 GB Sicherheitsreserve.

REM ============================================
REM [4/4] Status
REM ============================================
echo.
echo [4/4] Finale Kontrolle...
echo.
echo === [4/4] Finale Kontrolle === >> "%LOG%"

powershell -NoProfile -Command "$p = Get-Partition -DriveLetter C; $d = Get-Disk -Number $p.DiskNumber; $parts = @(Get-Partition -DiskNumber $p.DiskNumber | Sort-Object Offset); $last = $parts[$parts.Count - 1]; $tail = $d.Size - ($last.Offset + $last.Size); $v = Get-Volume -DriveLetter C; $used = $v.Size - $v.SizeRemaining; Write-Host ''; Write-Host '=== FINALE C-PARTITION ===' -ForegroundColor Cyan; Write-Host ('C Gesamt:     ' + [math]::Round($v.Size/1GB,2) + ' GB'); Write-Host ('C Belegt:     ' + [math]::Round($used/1GB,2) + ' GB'); Write-Host ('C Frei:       ' + [math]::Round($v.SizeRemaining/1GB,2) + ' GB'); Write-Host ('Letzte Part.: ' + $last.PartitionNumber + ' / Drive ' + $last.DriveLetter); Write-Host ('Reserve Ende: ' + [math]::Round($tail/1GB,2) + ' GB'); if($last.DriveLetter -ne 'C'){ exit 2 }; if($tail -lt 2GB){ exit 1 }"

if errorlevel 1 (
    echo.
    echo FEHLER: Finale Kontrolle meldet weniger als 2 GB Reserve.
    echo Image-Erstellung bitte nicht starten.
    echo.
    pause
    exit /b 1
)

echo.
echo ====================================================
echo    FERTIG - BEREIT FUER IMAGE-CAPTURE
echo ====================================================
echo.
echo C: wurde automatisch so vorbereitet, dass am Ende
echo der Festplatte 2 GB Reserve frei sind.
echo.
echo Jetzt:
echo   1. Tablet komplett herunterfahren
echo   2. Vom Clonezilla-Stick starten
echo   3. "FexoBooth IMAGE ERSTELLEN" waehlen
echo.
echo Log-Datei: %LOG%
echo Auto-Shrink-Log: %USERPROFILE%\Desktop\auto_shrink_c_log.txt
echo.
pause
exit /b 0

:chkdsk_required
echo.
echo ====================================================
echo   C: muss zuerst von Windows repariert werden
echo ====================================================
echo.
echo Windows hat Dateisystemfehler auf C: gemeldet.
echo Das ist der Grund, warum C: nicht verkleinert werden kann.
echo.
echo chkdsk C: /F wurde fuer den naechsten Neustart eingeplant.
echo.
echo Jetzt bitte:
echo   1. Tablet neu starten
echo   2. Windows-Reparatur komplett durchlaufen lassen
echo   3. Wieder anmelden
echo   4. defrag_and_check.bat erneut als Administrator starten
echo.
echo Details: %USERPROFILE%\Desktop\auto_shrink_c_log.txt
echo.
choice /C JN /M "Tablet jetzt neu starten? (J)a/(N)ein"
if errorlevel 2 (
    echo.
    echo OK - bitte manuell neu starten, bevor du weitermachst.
    echo.
    pause
    exit /b 1
)

shutdown /r /t 10 /c "FexoBooth: C wird beim Neustart repariert"
echo.
echo Neustart in 10 Sekunden. Abbrechen mit: shutdown /a
echo.
pause
exit /b 1
