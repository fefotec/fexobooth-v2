@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ===================================================
echo    FexoBooth - Release erstellen
echo ===================================================
echo.
echo Dieses Script:
echo   1. Setzt die Versionsnummer
echo   2. Baut die Anwendung (PyInstaller + ZIP)
echo   3. Erstellt ein GitHub Release
echo   4. Laedt das ZIP als Asset hoch
echo.
echo Voraussetzungen:
echo   - Git konfiguriert (push-Rechte)
echo   - GitHub Token in GITHUB_TOKEN Umgebungsvariable
echo     ODER gh CLI installiert und eingeloggt
echo   - Python, PyInstaller, VLC (fuer Build)
echo.
echo ===================================================
echo.

cd /d "%~dp0"

:: ─────────────────────────────────────────────
:: Schritt 1: Version abfragen
:: ─────────────────────────────────────────────

:: Aktuelle Version auslesen
for /f "tokens=3 delims= " %%A in ('findstr /C:"__version__" src\__init__.py') do set "CURRENT_VERSION=%%~A"
echo Aktuelle Version: %CURRENT_VERSION%
echo.

set /p NEW_VERSION="Neue Version eingeben (z.B. 2.1.0): "

if "%NEW_VERSION%"=="" (
    echo Keine Version eingegeben. Abbruch.
    pause
    exit /b 1
)

:: Validierung: Muss X.Y.Z Format haben
echo %NEW_VERSION% | findstr /R "^[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*$" >nul
if errorlevel 1 (
    echo FEHLER: Version muss im Format X.Y.Z sein (z.B. 2.1.0)
    pause
    exit /b 1
)

echo.
echo Version wird gesetzt: %CURRENT_VERSION% -^> %NEW_VERSION%
echo.

:: ─────────────────────────────────────────────
:: Schritt 2: Version in Dateien setzen
:: ─────────────────────────────────────────────

echo [1/6] Setze Versionsnummer...

:: src/__init__.py
powershell -Command "(Get-Content 'src\__init__.py') -replace '__version__ = \".*\"', '__version__ = \"%NEW_VERSION%\"' | Set-Content 'src\__init__.py' -Encoding utf8"

:: installer.iss - nur Major.Minor fuer Installer
for /f "tokens=1,2 delims=." %%A in ("%NEW_VERSION%") do set "ISS_VERSION=%%A.%%B"
powershell -Command "(Get-Content 'installer.iss') -replace '#define MyAppVersion \".*\"', '#define MyAppVersion \"%ISS_VERSION%\"' | Set-Content 'installer.iss' -Encoding utf8"

:: Ausgabe-Dateiname im Installer anpassen
powershell -Command "(Get-Content 'installer.iss') -replace 'OutputBaseFilename=FexoBooth_Setup_.*', 'OutputBaseFilename=FexoBooth_Setup_%ISS_VERSION%' | Set-Content 'installer.iss' -Encoding utf8"

echo [OK] Version %NEW_VERSION% in src/__init__.py und installer.iss gesetzt
echo.

:: ─────────────────────────────────────────────
:: Schritt 3: Build ausfuehren
:: ─────────────────────────────────────────────

echo [2/6] Starte Build...
echo.
call build_installer.bat

if not exist "installer_output\fexobooth.zip" (
    echo.
    echo FEHLER: Build fehlgeschlagen - kein fexobooth.zip gefunden!
    echo Bitte Build-Fehler oben pruefen.
    pause
    exit /b 1
)

echo.
echo [OK] Build erfolgreich - fexobooth.zip vorhanden
echo.

:: ─────────────────────────────────────────────
:: Schritt 4: Git Commit + Tag
:: ─────────────────────────────────────────────

echo [3/6] Git Commit + Tag...

git add src\__init__.py installer.iss
git commit -m "release: v%NEW_VERSION%"

if errorlevel 1 (
    echo WARNUNG: Git Commit fehlgeschlagen (evtl. keine Aenderungen)
)

git tag -a "v%NEW_VERSION%" -m "Release v%NEW_VERSION%"

if errorlevel 1 (
    echo FEHLER: Tag v%NEW_VERSION% existiert bereits!
    echo Bitte anderen Versionsnamen waehlen.
    pause
    exit /b 1
)

echo [OK] Commit und Tag v%NEW_VERSION% erstellt
echo.

:: ─────────────────────────────────────────────
:: Schritt 5: Push zu GitHub
:: ─────────────────────────────────────────────

echo [4/6] Push zu GitHub...

git push origin main
git push origin "v%NEW_VERSION%"

if errorlevel 1 (
    echo FEHLER: Push fehlgeschlagen!
    echo Bitte Internetverbindung und Git-Rechte pruefen.
    pause
    exit /b 1
)

echo [OK] Code und Tag gepusht
echo.

:: ─────────────────────────────────────────────
:: Schritt 6: GitHub Release erstellen + ZIP hochladen
:: ─────────────────────────────────────────────

echo [5/6] Erstelle GitHub Release...

:: Methode 1: gh CLI (bevorzugt)
where gh >nul 2>&1
if not errorlevel 1 (
    echo Verwende gh CLI...
    gh release create "v%NEW_VERSION%" "installer_output\fexobooth.zip" --title "v%NEW_VERSION%" --notes "FexoBooth Version %NEW_VERSION%"

    if errorlevel 1 (
        echo WARNUNG: gh release fehlgeschlagen.
        goto :manual_release
    )

    echo [OK] Release v%NEW_VERSION% mit ZIP erstellt!
    goto :done
)

:: Methode 2: GitHub API via PowerShell (braucht GITHUB_TOKEN)
if defined GITHUB_TOKEN (
    echo Verwende GitHub API mit Token...

    :: Release erstellen
    powershell -Command "$headers = @{ Authorization = 'token %GITHUB_TOKEN%'; 'Content-Type' = 'application/json' }; $body = @{ tag_name = 'v%NEW_VERSION%'; name = 'v%NEW_VERSION%'; body = 'FexoBooth Version %NEW_VERSION%'; draft = $false; prerelease = $false } | ConvertTo-Json; try { $r = Invoke-RestMethod -Uri 'https://api.github.com/repos/fefotec/fexobooth-v2/releases' -Method Post -Headers $headers -Body $body; $upload_url = $r.upload_url -replace '\{.*\}',''; Write-Host $upload_url | Out-File -Encoding ascii '%TEMP%\gh_upload_url.txt'; $upload_url = $r.upload_url -replace '\{\?.*\}',''; Invoke-RestMethod -Uri ($upload_url + '?name=fexobooth.zip') -Method Post -Headers @{ Authorization = 'token %GITHUB_TOKEN%'; 'Content-Type' = 'application/zip' } -InFile 'installer_output\fexobooth.zip'; Write-Host 'OK' } catch { Write-Host $_.Exception.Message; exit 1 }"

    if errorlevel 1 (
        echo WARNUNG: API-Upload fehlgeschlagen.
        goto :manual_release
    )

    echo [OK] Release v%NEW_VERSION% mit ZIP erstellt!
    goto :done
)

:: Methode 3: Manuell
:manual_release
echo.
echo ══════════════════════════════════════════════
echo  MANUELLER SCHRITT NOETIG
echo ══════════════════════════════════════════════
echo.
echo Der Code und Tag wurden gepusht, aber das
echo Release muss manuell auf GitHub erstellt werden:
echo.
echo 1. Oeffne: https://github.com/fefotec/fexobooth-v2/releases/new
echo 2. Tag: v%NEW_VERSION% (bereits vorhanden)
echo 3. Titel: v%NEW_VERSION%
echo 4. "Attach binaries" -^> installer_output\fexobooth.zip hochladen
echo 5. "Publish release" klicken
echo.
echo Oder installiere gh CLI und fuehre aus:
echo   gh auth login
echo   gh release create v%NEW_VERSION% installer_output\fexobooth.zip
echo.

:done
echo.
echo ===================================================
echo [6/6] RELEASE v%NEW_VERSION% ABGESCHLOSSEN!
echo ===================================================
echo.

if exist "installer_output\FexoBooth_Setup_%ISS_VERSION%.exe" (
    echo  Installer: installer_output\FexoBooth_Setup_%ISS_VERSION%.exe
)
echo  ZIP (OTA): installer_output\fexobooth.zip
echo  Git Tag:   v%NEW_VERSION%
echo.
echo Die 200 Tablets koennen jetzt updaten:
echo   Service-Menu -^> "Software aktualisieren"
echo.
pause
