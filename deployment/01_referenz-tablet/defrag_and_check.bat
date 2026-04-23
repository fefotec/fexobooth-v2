@echo off
REM ============================================
REM FexoBooth Master-Tablet Defrag + Shrink-Check
REM ============================================
REM NACH prepare_master_for_capture.bat und Neustart
REM ausfuehren.
REM
REM Defragmentiert C, konsolidiert den freien Speicher,
REM und zeigt danach wie weit C geschrumpft werden kann.
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
echo   [3] Anzeige wie weit C geschrumpft werden kann
echo.
pause

set "LOG=%USERPROFILE%\Desktop\defrag_check_log.txt"
echo ==================================================== > "%LOG%"
echo  Defrag + Check %DATE% %TIME% >> "%LOG%"
echo ==================================================== >> "%LOG%"

REM ============================================
REM [1/3] Pruefung
REM ============================================
echo.
echo [1/3] Pruefe System-Dateien auf C:...
echo.
echo === [1/3] Pruefung === >> "%LOG%"

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
REM [2/3] Defragmentierung
REM ============================================
echo.
echo [2/3] Starte Defragmentierung und Konsolidierung...
echo.
echo Dies dauert ca. 10-20 Minuten. Bitte NICHT abbrechen!
echo.
echo === [2/3] Defrag === >> "%LOG%"

REM /X = Konsolidiert freien Speicher
REM /W = Komplett (alle Fragmente)
REM /V = Verbose (mehr Info)
defrag C: /X /W /V 2>&1 | tee -a "%LOG%" 2>nul

REM Falls tee nicht verfuegbar: normaler defrag
defrag C: /X /W /V >> "%LOG%" 2>&1

echo.
echo [OK] Defragmentierung abgeschlossen.

REM ============================================
REM [3/3] Shrink-Check
REM ============================================
echo.
echo [3/3] Pruefe wie weit C geschrumpft werden kann...
echo.
echo === [3/3] Shrink-Check === >> "%LOG%"

REM Hinweis: Der genaue max-shrink-Wert kann nur die
REM Datentraegerverwaltung anzeigen. Wir zeigen stattdessen
REM die aktuelle C-Groesse und freien Platz.

powershell -NoProfile -Command "$c = Get-Volume -DriveLetter C; $used = $c.Size - $c.SizeRemaining; Write-Host ''; Write-Host '=== AKTUELLE C-PARTITION ===' -ForegroundColor Cyan; Write-Host ('Gesamt: ' + [math]::Round($c.Size/1GB,2) + ' GB'); Write-Host ('Belegt: ' + [math]::Round($used/1GB,2) + ' GB'); Write-Host ('Frei:   ' + [math]::Round($c.SizeRemaining/1GB,2) + ' GB'); Write-Host ''; Write-Host '=== EMPFOHLENE ZIELGROESSE NACH SHRINK ===' -ForegroundColor Yellow; $target_gb = [math]::Max(22, [math]::Ceiling($used/1GB) + 3); Write-Host ('Ziel-Groesse:      ' + $target_gb + ' GB   (= ' + ($target_gb * 1024) + ' MB)'); $current_mb = [math]::Round($c.Size/1MB); $target_mb = $target_gb * 1024; $shrink_mb = $current_mb - $target_mb; Write-Host ('Zu verkleinern:    ' + $shrink_mb + ' MB'); Write-Host ''"

echo.
echo ====================================================
echo    WIE WEITER
echo ====================================================
echo.
echo 1. Rechtsklick auf Start-Menu - "Datentraegerverwaltung"
echo 2. Rechtsklick auf C: - "Volume verkleinern..."
echo 3. Bei "Zu verkleinernder Speicherplatz in MB" den Wert
echo    von oben eintragen ^(siehe "Zu verkleinern"^)
echo 4. Klick auf "Verkleinern"
echo.
echo Wenn Windows weniger erlaubt als der vorgeschlagene Wert:
echo   - Den maximal erlaubten Wert eintragen ^(geht auch^)
echo   - Solange C am Ende unter 25 GB ist, passt es auf
echo     32 GB Tablets
echo.
echo Log-Datei: %LOG%
echo.
pause
exit /b 0
