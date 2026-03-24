@echo off
chcp 65001 >nul

:: ─────────────────────────────────────────────
:: CRASH-SICHERER WRAPPER
:: cmd /k startet einen Subprozess der GARANTIERT offen bleibt,
:: selbst wenn das Script abstuerzt oder exit aufruft.
:: ─────────────────────────────────────────────
if not "%~1"=="--run" (
    cmd /k "%~f0" --run
    exit /b
)

setlocal EnableDelayedExpansion

echo.
echo ===================================================
echo    FexoBooth - USB-Stick komplett vorbereiten
echo ===================================================
echo.
echo Dieses Script macht ALLES automatisch:
echo   1. Laedt Clonezilla herunter (falls noetig)
echo   2. Partitioniert den USB-Stick (20 GB + Rest)
echo   3. Entpackt Clonezilla (bootfaehig)
echo   4. Erstellt Klon-Scripts und Bootmenue
echo   5. Kopiert FexoBooth Deployment-Dateien
echo.
echo ACHTUNG: ALLE DATEN AUF DEM STICK WERDEN GELOESCHT!
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: ─────────────────────────────────────────────
:: Admin-Check
:: ─────────────────────────────────────────────

net session >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Dieses Script muss als ADMINISTRATOR ausgefuehrt werden!
    echo.
    echo Rechtsklick auf die Datei ^> "Als Administrator ausfuehren"
    echo.
    exit /b 1
)

:: ─────────────────────────────────────────────
:: Schritt 1: Internet pruefen + Clonezilla herunterladen
:: ─────────────────────────────────────────────

echo [1/8] Suche Clonezilla...

set "CLONEZILLA_ZIP="
set "DOWNLOAD_DIR=%SCRIPT_DIR%downloads"

:: Suche in downloads/ Unterordner
for %%F in ("%DOWNLOAD_DIR%\clonezilla-live-*.zip") do (
    if exist "%%F" set "CLONEZILLA_ZIP=%%F"
)

:: Suche im aktuellen Ordner
if "!CLONEZILLA_ZIP!"=="" (
    for %%F in ("%SCRIPT_DIR%clonezilla-live-*.zip") do (
        if exist "%%F" set "CLONEZILLA_ZIP=%%F"
    )
)

:: Suche im Downloads-Ordner des Users
if "!CLONEZILLA_ZIP!"=="" (
    for %%F in ("%USERPROFILE%\Downloads\clonezilla-live-*.zip") do (
        if exist "%%F" set "CLONEZILLA_ZIP=%%F"
    )
)

if not "!CLONEZILLA_ZIP!"=="" goto :clonezilla_found

echo Clonezilla nicht gefunden - wird jetzt heruntergeladen...
echo.

:: Internet pruefen
echo Pruefe Internetverbindung...
ping -n 1 sourceforge.net >nul 2>&1
if not errorlevel 1 goto :inet_ok
ping -n 1 github.com >nul 2>&1
if not errorlevel 1 goto :inet_ok
echo.
echo FEHLER: Keine Internetverbindung!
echo Bitte manuell herunterladen: https://clonezilla.org/downloads.php
echo (stable, amd64, zip) - Speichere in: %DOWNLOAD_DIR%\
echo.
exit /b 1

:inet_ok
echo [OK] Internet verfuegbar
echo.

:: Download-Verzeichnis erstellen
if not exist "%DOWNLOAD_DIR%" mkdir "%DOWNLOAD_DIR%"

:: Clonezilla herunterladen (~500 MB)
set "CZ_VERSION=3.3.1-35"
set "CZ_FILE=clonezilla-live-!CZ_VERSION!-amd64.zip"
set "CZ_URL=https://sourceforge.net/projects/clonezilla/files/clonezilla_live_stable/!CZ_VERSION!/!CZ_FILE!/download"
set "CZ_URL_ALT=https://free.nchc.org.tw/clonezilla-live/stable/!CZ_FILE!"

echo Lade Clonezilla Live herunter (~500 MB)...
echo Version: !CZ_VERSION!
echo.
echo Bitte warten, das dauert je nach Internetgeschwindigkeit
echo 2-10 Minuten...
echo.

:: Methode 1: BITS Transfer (nutzt Windows-Update-Netzwerkstack)
echo Methode 1: BITS Transfer (SourceForge)...
powershell -ExecutionPolicy Bypass -Command "try { Import-Module BitsTransfer -ErrorAction Stop; Start-BitsTransfer -Source '!CZ_URL!' -Destination '%DOWNLOAD_DIR%\!CZ_FILE!' -DisplayName 'Clonezilla' -ErrorAction Stop; exit 0 } catch { exit 1 }"
if not errorlevel 1 if exist "%DOWNLOAD_DIR%\!CZ_FILE!" goto :download_ok

:: Methode 2: curl SourceForge
echo Methode 2: curl (SourceForge)...
if exist "%DOWNLOAD_DIR%\!CZ_FILE!" del "%DOWNLOAD_DIR%\!CZ_FILE!" 2>nul
curl.exe -L -o "%DOWNLOAD_DIR%\!CZ_FILE!" -# --ssl-no-revoke --connect-timeout 30 --max-time 900 --retry 2 "!CZ_URL!"
if not errorlevel 1 if exist "%DOWNLOAD_DIR%\!CZ_FILE!" goto :download_ok

:: Methode 3: BITS Transfer alternativer Mirror (NCHC Taiwan)
echo Methode 3: BITS Transfer (alternativer Mirror)...
if exist "%DOWNLOAD_DIR%\!CZ_FILE!" del "%DOWNLOAD_DIR%\!CZ_FILE!" 2>nul
powershell -ExecutionPolicy Bypass -Command "try { Import-Module BitsTransfer -ErrorAction Stop; Start-BitsTransfer -Source '!CZ_URL_ALT!' -Destination '%DOWNLOAD_DIR%\!CZ_FILE!' -DisplayName 'Clonezilla' -ErrorAction Stop; exit 0 } catch { exit 1 }"
if not errorlevel 1 if exist "%DOWNLOAD_DIR%\!CZ_FILE!" goto :download_ok

:: Methode 4: curl alternativer Mirror
echo Methode 4: curl (alternativer Mirror)...
if exist "%DOWNLOAD_DIR%\!CZ_FILE!" del "%DOWNLOAD_DIR%\!CZ_FILE!" 2>nul
curl.exe -L -o "%DOWNLOAD_DIR%\!CZ_FILE!" -# --ssl-no-revoke --connect-timeout 30 --max-time 900 --retry 2 "!CZ_URL_ALT!"
if not errorlevel 1 if exist "%DOWNLOAD_DIR%\!CZ_FILE!" goto :download_ok

:: Alle Methoden fehlgeschlagen
echo.
echo ===================================================
echo  ALLE DOWNLOAD-METHODEN FEHLGESCHLAGEN
echo ===================================================
echo.
echo Dein Netzwerk blockiert die Downloads (Firewall/Antivirus).
echo.
echo Bitte manuell im Browser herunterladen:
echo   https://clonezilla.org/downloads.php
echo   (stable, amd64, zip Format)
echo.
echo ZIP-Datei speichern als:
echo   %DOWNLOAD_DIR%\!CZ_FILE!
echo.
echo Danach dieses Script erneut starten.
echo.
exit /b 1

:download_ok
echo.
echo [OK] Download abgeschlossen

set "CLONEZILLA_ZIP=%DOWNLOAD_DIR%\!CZ_FILE!"

:: Pruefe Dateigroesse (sollte >200 MB sein)
for %%A in ("!CLONEZILLA_ZIP!") do set CZ_SIZE=%%~zA
if !CZ_SIZE! LSS 200000000 (
    echo.
    echo WARNUNG: Datei ist nur !CZ_SIZE! Bytes - zu klein fuer Clonezilla.
    echo Moeglicherweise wurde eine Fehlerseite heruntergeladen.
    echo.
    echo Bitte manuell herunterladen: https://clonezilla.org/downloads.php
    del "!CLONEZILLA_ZIP!" 2>nul
    exit /b 1
)

:clonezilla_found

echo [OK] Clonezilla: !CLONEZILLA_ZIP!
echo.

:: ─────────────────────────────────────────────
:: Schritt 2: USB-Stick auswaehlen
:: ─────────────────────────────────────────────

echo [2/8] Verfuegbare USB-Laufwerke:
echo.

powershell -Command "Get-Disk | Where-Object { $_.BusType -eq 'USB' } | Format-Table -AutoSize @{L='Disk';E={$_.Number}}, @{L='Groesse (GB)';E={[math]::Round($_.Size/1GB,1)}}, @{L='Status';E={$_.OperationalStatus}}, @{L='Bezeichnung';E={$_.FriendlyName}}"

echo.
set /p DISK_NUM="Disk-Nummer des USB-Sticks eingeben (z.B. 1): "

if "%DISK_NUM%"=="" (
    echo Keine Auswahl. Abbruch.
    exit /b 1
)

:: Leerzeichen entfernen
set "DISK_NUM=%DISK_NUM: =%"

:: Sicherheitscheck: Disk 0 ist fast immer die System-Festplatte!
if "%DISK_NUM%"=="0" (
    echo.
    echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    echo  FEHLER: Disk 0 ist die SYSTEM-FESTPLATTE!
    echo  Das wuerde Windows zerstoeren!
    echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    echo.
    exit /b 1
)

:: Pruefe ob es ein USB-Laufwerk ist
powershell -ExecutionPolicy Bypass -Command "$d = Get-Disk -Number %DISK_NUM% -ErrorAction SilentlyContinue; if(-not $d){ exit 1 }; if($d.BusType -ne [string]'USB'){ exit 2 }; Write-Host ('Gewaehlt: ' + $d.FriendlyName + ' (' + [math]::Round($d.Size/1GB,1) + ' GB)'); exit 0"

if errorlevel 2 goto :disk_not_usb
if errorlevel 1 goto :disk_not_found
goto :disk_ok

:disk_not_usb
echo.
choice /C JN /M "WARNUNG: Kein USB-Laufwerk! Trotzdem fortfahren? (J)a/(N)ein"
if errorlevel 2 (
    echo Abbruch.
    exit /b 1
)
goto :disk_ok

:disk_not_found
echo FEHLER: Disk %DISK_NUM% existiert nicht!
exit /b 1

:disk_ok

:: ─────────────────────────────────────────────
:: Pruefen ob Stick bereits korrekt formatiert ist
:: ─────────────────────────────────────────────

echo.
echo Pruefe ob Stick bereits FEXOBOOT + FEXODATEN hat...

set "BOOT_DRIVE="
set "DATA_DRIVE="
call :scan_drives

if not "%BOOT_DRIVE%"=="" if not "%DATA_DRIVE%"=="" (
    echo.
    echo [OK] Stick ist bereits korrekt partitioniert!
    echo   FEXOBOOT  = %BOOT_DRIVE%:
    echo   FEXODATEN = %DATA_DRIVE%:
    echo.
    choice /C JN /M "Partitionen BEHALTEN und nur Daten kopieren? (J)a/(N)ein=neu formatieren"
    if not errorlevel 2 goto :partitions_ready
    echo.
    echo OK, Stick wird neu formatiert...
)

:: ─────────────────────────────────────────────
:: LETZTE WARNUNG
:: ─────────────────────────────────────────────

echo.
echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
echo  ACHTUNG: ALLE DATEN AUF DISK %DISK_NUM%
echo  WERDEN UNWIDERRUFLICH GELOESCHT!
echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
echo.
choice /C JN /M "Wirklich fortfahren? (J)a/(N)ein"
if errorlevel 2 (
    echo Abbruch.
    exit /b 0
)

echo.
choice /C JN /M "ENDGUELTIG bestaetigen? (J)a/(N)ein"
if errorlevel 2 (
    echo Abbruch.
    exit /b 0
)

:: ─────────────────────────────────────────────
:: Schritt 3: Partitionieren mit diskpart
:: ─────────────────────────────────────────────

echo.
echo [3/8] Partitioniere USB-Stick...
echo   Partition 1: 40 GB FAT32 (FEXOBOOT - Clonezilla + Image)
echo   Partition 2: Rest   NTFS (FEXODATEN - Deployment + Tools)
echo.

set "DISKPART_SCRIPT=%TEMP%\fexo_diskpart.txt"

(
echo select disk %DISK_NUM%
echo clean
echo create partition primary size=40960
echo format fs=fat32 label=FEXOBOOT quick
echo assign
echo active
echo create partition primary
echo format fs=ntfs label=FEXODATEN quick
echo assign
) > "%DISKPART_SCRIPT%"

diskpart /s "%DISKPART_SCRIPT%"

if errorlevel 1 (
    echo.
    echo FEHLER: Partitionierung fehlgeschlagen!
    del "%DISKPART_SCRIPT%" 2>nul
    exit /b 1
)

del "%DISKPART_SCRIPT%" 2>nul

echo.
echo [OK] Partitionierung abgeschlossen
echo Warte auf Laufwerkserkennung (10 Sek.)...
timeout /t 10 >nul

:: ─────────────────────────────────────────────
:: Schritt 4: Laufwerksbuchstaben finden
:: ─────────────────────────────────────────────

echo [4/8] Suche Laufwerksbuchstaben...

set "BOOT_DRIVE="
set "DATA_DRIVE="
set "RETRY_COUNT=0"

:find_drives
call :scan_drives

if not "%BOOT_DRIVE%"=="" if not "%DATA_DRIVE%"=="" goto :drives_found

set /a RETRY_COUNT+=1
if !RETRY_COUNT! GEQ 6 goto :drives_not_found
echo   Warte auf Laufwerke... (Versuch !RETRY_COUNT!/5)
timeout /t 5 >nul
goto :find_drives

:drives_not_found
if "%BOOT_DRIVE%"=="" echo FEHLER: FEXOBOOT nicht gefunden!
if "%DATA_DRIVE%"=="" echo FEHLER: FEXODATEN nicht gefunden!
echo Oeffne Datentraegerverwaltung zum Pruefen...
start diskmgmt.msc
exit /b 1

:drives_found
:partitions_ready
echo [OK] FEXOBOOT  = %BOOT_DRIVE%:
echo [OK] FEXODATEN = %DATA_DRIVE%:
echo.

:: ─────────────────────────────────────────────
:: Schritt 5: Clonezilla entpacken
:: ─────────────────────────────────────────────

echo [5/8] Entpacke Clonezilla auf %BOOT_DRIVE%: ...
echo   (Dies dauert 1-3 Minuten)
echo.

powershell -ExecutionPolicy Bypass -Command "try { Expand-Archive -Path '!CLONEZILLA_ZIP!' -DestinationPath '%BOOT_DRIVE%:\' -Force; Write-Host '[OK] Entpackt'; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo FEHLER: Entpacken fehlgeschlagen!
    exit /b 1
)

:: Pruefen ob Clonezilla in einem Unterordner gelandet ist
if not exist "%BOOT_DRIVE%:\live\vmlinuz" (
    echo Dateien nicht im Root - pruefe auf Unterordner...
    for /d %%D in ("%BOOT_DRIVE%:\clonezilla-live-*") do (
        if exist "%%D\live\vmlinuz" (
            echo Verschiebe Dateien aus %%D nach %BOOT_DRIVE%:\...
            xcopy "%%D\*" "%BOOT_DRIVE%:\" /E /Y >nul 2>&1
            rmdir /S /Q "%%D" 2>nul
        )
    )
)

if not exist "%BOOT_DRIVE%:\live\vmlinuz" (
    echo FEHLER: Clonezilla-Dateien nicht korrekt entpackt!
    echo   vmlinuz nicht gefunden in %BOOT_DRIVE%:\live\
    echo.
    echo Inhalt von %BOOT_DRIVE%:\
    dir "%BOOT_DRIVE%:\" /B
    exit /b 1
)

echo [OK] Clonezilla entpackt
echo.

:: ─────────────────────────────────────────────
:: Schritt 6: Klon-Scripts direkt erstellen
:: ─────────────────────────────────────────────

echo [6/8] Erstelle FexoBooth Klon-Scripts...

:: custom-ocs Verzeichnis
if not exist "%BOOT_DRIVE%:\live\custom-ocs" mkdir "%BOOT_DRIVE%:\live\custom-ocs"

:: ── custom-ocs-capture ──
:: WICHTIG: goto statt if/else, weil inline-PowerShell Klammern enthaelt
:: die den Batch-Parser in if/else-Bloecken zum Absturz bringen
if exist "%SCRIPT_DIR%custom-ocs\custom-ocs-capture" goto :capture_from_file
goto :capture_inline

:capture_from_file
copy /Y "%SCRIPT_DIR%custom-ocs\custom-ocs-capture" "%BOOT_DRIVE%:\live\custom-ocs\" >nul
:: CRLF zu LF konvertieren (Linux-Scripts muessen LF haben)
powershell -Command "$f='%BOOT_DRIVE%:\live\custom-ocs\custom-ocs-capture'; [System.IO.File]::WriteAllText($f, ([System.IO.File]::ReadAllText($f) -replace \"`r`n\", \"`n\"))"
echo [OK] custom-ocs-capture kopiert (LF)
goto :capture_done

:capture_inline
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%_write_capture.ps1" "%BOOT_DRIVE%:\live\custom-ocs\custom-ocs-capture"
echo [OK] custom-ocs-capture erstellt (inline)
goto :capture_done

:capture_done

:: ── custom-ocs-deploy ──
if exist "%SCRIPT_DIR%custom-ocs\custom-ocs-deploy" goto :deploy_from_file
goto :deploy_inline

:deploy_from_file
copy /Y "%SCRIPT_DIR%custom-ocs\custom-ocs-deploy" "%BOOT_DRIVE%:\live\custom-ocs\" >nul
:: CRLF zu LF konvertieren (Linux-Scripts muessen LF haben)
powershell -Command "$f='%BOOT_DRIVE%:\live\custom-ocs\custom-ocs-deploy'; [System.IO.File]::WriteAllText($f, ([System.IO.File]::ReadAllText($f) -replace \"`r`n\", \"`n\"))"
echo [OK] custom-ocs-deploy kopiert (LF)
goto :deploy_done

:deploy_inline
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%_write_deploy.ps1" "%BOOT_DRIVE%:\live\custom-ocs\custom-ocs-deploy"
echo [OK] custom-ocs-deploy erstellt (inline)
goto :deploy_done

:deploy_done

:: ─────────────────────────────────────────────
:: Schritt 7: GRUB Bootmenue patchen
:: ─────────────────────────────────────────────

echo.
echo [7/8] Richte Bootmenue ein...

:: GRUB config suchen - verschiedene moegliche Pfade
set "GRUB_CFG="
if exist "%BOOT_DRIVE%:\EFI\boot\grub.cfg" set "GRUB_CFG=%BOOT_DRIVE%:\EFI\boot\grub.cfg"
if "%GRUB_CFG%"=="" if exist "%BOOT_DRIVE%:\boot\grub\grub.cfg" set "GRUB_CFG=%BOOT_DRIVE%:\boot\grub\grub.cfg"

:: Falls nicht gefunden: Clonezilla-Unterordner durchsuchen
if "%GRUB_CFG%"=="" (
    for /d %%D in ("%BOOT_DRIVE%:\clonezilla-live-*") do (
        if exist "%%D\EFI\boot\grub.cfg" set "GRUB_CFG=%%D\EFI\boot\grub.cfg"
    )
)

if "%GRUB_CFG%"=="" goto :grub_skip

echo   Gefunden: %GRUB_CFG%

:: Original sichern
copy /Y "%GRUB_CFG%" "%GRUB_CFG%.original" >nul

:: GRUB-Patch: Aus externer Datei oder inline per PS1
if exist "%SCRIPT_DIR%..\tools\grub_menu_patch.txt" goto :grub_from_file
goto :grub_inline

:grub_from_file
powershell -Command "$patch = Get-Content '%SCRIPT_DIR%..\tools\grub_menu_patch.txt' -Raw; $orig = Get-Content '%GRUB_CFG%.original' -Raw; [System.IO.File]::WriteAllText('%GRUB_CFG%', ($patch + \"`n`n\" + $orig))"
echo [OK] GRUB-Bootmenue: Deutsche FexoBooth-Eintraege hinzugefuegt
goto :grub_done

:grub_inline
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%_write_grub_patch.ps1" "%GRUB_CFG%" "%GRUB_CFG%.original"
echo [OK] GRUB-Bootmenue: Deutsche FexoBooth-Eintraege hinzugefuegt
goto :grub_done

:grub_skip
echo [WARNUNG] grub.cfg nicht gefunden - suche auf %BOOT_DRIVE%: ...
dir "%BOOT_DRIVE%:\EFI" /S /B 2>nul
if not exist "%BOOT_DRIVE%:\EFI" echo   EFI-Ordner existiert nicht auf %BOOT_DRIVE%:

:grub_done

:: Syslinux wird NICHT installiert:
:: - Miix 310 Tablets sind reine UEFI-Geraete
:: - makeboot64.bat erwartet interaktive Eingaben und haengt sonst
echo [INFO] Syslinux uebersprungen - Miix 310 bootet nur per UEFI

:: Image-Verzeichnis erstellen
if not exist "%BOOT_DRIVE%:\home\partimag" mkdir "%BOOT_DRIVE%:\home\partimag"
echo [OK] Image-Verzeichnis erstellt

echo.

:: ─────────────────────────────────────────────
:: Schritt 8: Deployment-Dateien auf Daten-Partition
:: ─────────────────────────────────────────────

echo [8/8] Kopiere Deployment-Dateien auf %DATA_DRIVE%: ...

:: Deployment-Ordner (ganzer deployment/ Ordner)
set "DEPLOY_ROOT=%SCRIPT_DIR%..\"
if exist "%DEPLOY_ROOT%README_DEPLOYMENT.md" (
    xcopy "%DEPLOY_ROOT%*" "%DATA_DRIVE%:\deployment\" /E /I /Y >nul 2>&1
    echo [OK] deployment/ Ordner kopiert
) else (
    echo [INFO] deployment/ Quellordner nicht am erwarteten Ort
)

:: FexoBooth Installer
set "INSTALLER_PATH=%SCRIPT_DIR%..\..\installer_output\FexoBooth_Setup_2.0.exe"
if exist "%INSTALLER_PATH%" (
    echo Kopiere FexoBooth Installer ~85 MB...
    copy /Y "%INSTALLER_PATH%" "%DATA_DRIVE%:\" >nul
    echo [OK] FexoBooth_Setup_2.0.exe kopiert
) else (
    echo [INFO] Kein Installer in installer_output/ - spaeter manuell kopieren
)

:: FexoBooth ZIP (OTA-Updates)
set "ZIP_PATH=%SCRIPT_DIR%..\..\installer_output\fexobooth.zip"
if exist "%ZIP_PATH%" (
    echo Kopiere fexobooth.zip ~140 MB...
    copy /Y "%ZIP_PATH%" "%DATA_DRIVE%:\" >nul
    echo [OK] fexobooth.zip kopiert
)

:: update_from_github.bat
set "UPDATE_BAT=%SCRIPT_DIR%..\..\update_from_github.bat"
if exist "%UPDATE_BAT%" (
    copy /Y "%UPDATE_BAT%" "%DATA_DRIVE%:\" >nul
    echo [OK] update_from_github.bat kopiert
)

:: Post-Install Check Script extra nochmal auf Daten-Partition
set "CHECK_BAT=%SCRIPT_DIR%..\01_referenz-tablet\post_install_check.bat"
if exist "%CHECK_BAT%" (
    copy /Y "%CHECK_BAT%" "%DATA_DRIVE%:\" >nul
    echo [OK] post_install_check.bat kopiert
)

:: ─────────────────────────────────────────────
:: Zusammenfassung
:: ─────────────────────────────────────────────

echo.
echo ===================================================
echo    USB-STICK FERTIG!
echo ===================================================
echo.
echo  %BOOT_DRIVE%:  FEXOBOOT (20 GB, FAT32)
echo     Clonezilla Live (bootfaehig)
echo     FexoBooth Klon-Scripts
echo     Image-Speicher (fuer ~8-12 GB)
echo.
echo  %DATA_DRIVE%:  FEXODATEN (NTFS)
echo     Deployment-Anleitungen
echo     FexoBooth Installer + Update-Tools
echo.
echo ───────────────────────────────────────────
echo  SO GEHT ES WEITER:
echo ───────────────────────────────────────────
echo.
echo  1. Referenz-Tablet einrichten:
echo     FexoBooth_Setup_2.0.exe von %DATA_DRIVE%: installieren
echo     Hotspot einrichten, testen, aufraeumen
echo     post_install_check.bat ausfuehren
echo.
echo  2. Image erstellen:
echo     USB-Stick ans Tablet (mit OTG-Hub)
echo     Novo-Button druecken (Bueroklammer)
echo     "FexoBooth IMAGE ERSTELLEN" waehlen
echo.
echo  3. Andere Tablets klonen:
echo     USB-Stick einstecken, Novo-Button
echo     "FexoBooth IMAGE AUFSPIELEN" waehlen
echo     ~15-20 Min warten, fertig!
echo.
echo ===================================================
echo.
exit /b 0

:: ─────────────────────────────────────────────
:: Subroutine: Laufwerksbuchstaben per vol-Befehl suchen
:: Kein PowerShell noetig - reines Batch, schnell und zuverlaessig
:: ─────────────────────────────────────────────
:scan_drives
for %%L in (D E F G H I J K L M N O P Q R S T U V W X Y Z) do (
    if exist "%%L:\" (
        vol %%L: 2>nul | findstr /C:"FEXOBOOT" >nul 2>&1 && set "BOOT_DRIVE=%%L"
        vol %%L: 2>nul | findstr /C:"FEXODATEN" >nul 2>&1 && set "DATA_DRIVE=%%L"
    )
)
goto :eof
