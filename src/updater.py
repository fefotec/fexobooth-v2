"""OTA-Update Modul für FexoBooth

Lädt neue Versionen von GitHub Releases herunter und aktualisiert
die Installation. Funktioniert sowohl im PyInstaller-Build als auch
im Entwicklermodus.

Ablauf:
1. GitHub API abfragen → neuestes Release finden
2. ZIP-Asset herunterladen (mit Fortschritts-Callback)
3. BAT-Script generieren, das nach App-Ende die Dateien ersetzt
4. App beendet sich → BAT übernimmt → Neustart

Geschützte Ordner (werden NICHT überschrieben):
- config.json (User-Einstellungen)
- BILDER/ (Fotos)
- logs/ (Protokolle)
- .booking_cache/ (Buchungsdaten)
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from src.utils.logging import get_logger

logger = get_logger(__name__)

# GitHub Repository
GITHUB_REPO = "fefotec/fexobooth-v2"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# Timeout für HTTP-Requests (Sekunden)
HTTP_TIMEOUT = 30


def _get_install_dir() -> Path:
    """Ermittelt das Installationsverzeichnis"""
    if getattr(sys, 'frozen', False):
        # PyInstaller-Build: Verzeichnis der EXE
        return Path(sys.executable).parent
    else:
        # Entwicklermodus: Projekt-Root
        return Path(__file__).parent.parent


def _parse_version(version_str: str) -> tuple:
    """Parst Version-String zu vergleichbarem Tuple

    Unterstützt: "2.0.0", "v2.1.0", "2.0.0-dev", "v2.0.1-beta"
    """
    # v-Prefix entfernen
    v = version_str.strip().lstrip("v")

    # Suffix entfernen (-dev, -beta, etc.)
    base = v.split("-")[0]

    # In Tuple umwandeln
    parts = []
    for p in base.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)

    # Auf 3 Stellen auffüllen
    while len(parts) < 3:
        parts.append(0)

    return tuple(parts[:3])


def get_current_version() -> str:
    """Gibt die aktuelle App-Version zurück"""
    try:
        from src import __version__
        return __version__
    except ImportError:
        return "0.0.0"


def check_for_update() -> Optional[dict]:
    """Prüft ob ein Update verfügbar ist

    Returns:
        dict mit Release-Info oder None wenn kein Update verfügbar.
        Keys: tag, version, download_url, size, description

    Raises:
        ConnectionError: Kein Internet / GitHub nicht erreichbar
        ValueError: API-Antwort ungültig
    """
    logger.info("Prüfe auf Updates...")

    current = get_current_version()
    current_tuple = _parse_version(current)
    logger.info(f"Aktuelle Version: {current} ({current_tuple})")

    # GitHub API abfragen
    req = Request(
        GITHUB_API_URL,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "FexoBooth-Updater"
        }
    )

    try:
        with urlopen(req, timeout=HTTP_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except URLError as e:
        raise ConnectionError(f"GitHub nicht erreichbar: {e}")
    except Exception as e:
        raise ValueError(f"API-Fehler: {e}")

    # Release-Tag parsen
    tag = data.get("tag_name", "")
    remote_tuple = _parse_version(tag)
    logger.info(f"Neuestes Release: {tag} ({remote_tuple})")

    # Version vergleichen
    if remote_tuple <= current_tuple:
        logger.info("Kein Update verfügbar - bereits aktuell.")
        return None

    # ZIP-Asset suchen
    download_url = None
    download_size = 0

    for asset in data.get("assets", []):
        name = asset.get("name", "").lower()
        if name.endswith(".zip") and "fexobooth" in name:
            download_url = asset.get("browser_download_url")
            download_size = asset.get("size", 0)
            break

    if not download_url:
        raise ValueError(
            f"Release {tag} hat kein ZIP-Asset. "
            "Bitte 'fexobooth.zip' als Release-Asset hochladen."
        )

    return {
        "tag": tag,
        "version": tag.lstrip("v"),
        "download_url": download_url,
        "size": download_size,
        "description": data.get("body", ""),
    }


def download_update(
    download_url: str,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Path:
    """Lädt das Update-ZIP herunter

    Args:
        download_url: URL zum ZIP-Asset
        progress_callback: Callback(fortschritt_0_bis_1, status_text)

    Returns:
        Pfad zur heruntergeladenen ZIP-Datei

    Raises:
        ConnectionError: Download fehlgeschlagen
    """
    zip_path = Path(tempfile.gettempdir()) / "fexobooth_update.zip"

    # Alte Datei löschen
    if zip_path.exists():
        zip_path.unlink()

    logger.info(f"Lade Update herunter: {download_url}")

    req = Request(
        download_url,
        headers={"User-Agent": "FexoBooth-Updater"}
    )

    try:
        with urlopen(req, timeout=120) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 64 * 1024  # 64 KB Chunks (schonend für schwache Hardware)

            with open(zip_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback and total_size > 0:
                        progress = downloaded / total_size
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        text = f"Lade herunter... {mb_done:.1f} / {mb_total:.1f} MB"
                        progress_callback(progress, text)

    except Exception as e:
        # Aufräumen bei Fehler
        if zip_path.exists():
            zip_path.unlink()
        raise ConnectionError(f"Download fehlgeschlagen: {e}")

    logger.info(f"Download abgeschlossen: {zip_path} ({downloaded} Bytes)")
    return zip_path


def create_update_script(zip_path: Path, install_dir: Path) -> Path:
    """Erstellt das BAT-Script das nach App-Ende die Dateien ersetzt

    Das Script:
    1. Wartet bis die App beendet ist
    2. Entpackt das ZIP
    3. Kopiert neue Dateien (schützt config.json, BILDER/, logs/)
    4. Räumt auf
    5. Startet die App neu

    Args:
        zip_path: Pfad zur heruntergeladenen ZIP-Datei
        install_dir: Installationsverzeichnis (z.B. C:\\FexoBooth)

    Returns:
        Pfad zum erstellten BAT-Script
    """
    script_path = Path(tempfile.gettempdir()) / "fexobooth_updater.bat"
    extract_dir = Path(tempfile.gettempdir()) / "fexobooth_update_extract"

    # EXE-Name ermitteln
    if getattr(sys, 'frozen', False):
        exe_name = Path(sys.executable).name
        process_name = exe_name
        start_cmd = f'start "" "{install_dir}\\{exe_name}"'
    else:
        exe_name = "python"
        process_name = "python.exe"
        start_cmd = f'start "" python "{install_dir}\\src\\main.py"'

    # BAT-Script Inhalt
    script = f'''@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ============================================
echo    FexoBooth Update wird installiert...
echo ============================================
echo.

set "INSTALL_DIR={install_dir}"
set "ZIP_FILE={zip_path}"
set "EXTRACT_DIR={extract_dir}"
set "PROCESS_NAME={process_name}"

:: Warte bis die App beendet ist (max 30 Sekunden)
echo Warte auf Beendigung von %PROCESS_NAME%...
set WAIT_COUNT=0
:wait_loop
tasklist /FI "IMAGENAME eq %PROCESS_NAME%" 2>NUL | find /I "%PROCESS_NAME%" >NUL
if not errorlevel 1 (
    set /a WAIT_COUNT+=1
    if !WAIT_COUNT! GEQ 30 (
        echo WARNUNG: App laeuft noch nach 30s - fahre trotzdem fort
        goto :do_update
    )
    timeout /t 1 /nobreak >nul
    goto :wait_loop
)
:: Kurz warten damit Dateien freigegeben werden
timeout /t 2 /nobreak >nul

:do_update
echo App beendet. Starte Update...
echo.

:: Altes Extract-Verzeichnis löschen
if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%"
mkdir "%EXTRACT_DIR%"

:: ZIP entpacken
echo Entpacke Update...
powershell -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%EXTRACT_DIR%' -Force"

if errorlevel 1 (
    echo FEHLER: Entpacken fehlgeschlagen!
    echo Die alte Version laeuft weiter.
    pause
    exit /b 1
)

:: Finde entpacktes Verzeichnis (kann direkt oder in Unterordner sein)
set "SOURCE_DIR=%EXTRACT_DIR%"

:: Prüfe ob es einen einzelnen Unterordner gibt
set SUBDIR_COUNT=0
for /d %%D in ("%EXTRACT_DIR%\\*") do (
    set "FIRST_SUBDIR=%%D"
    set /a SUBDIR_COUNT+=1
)
if !SUBDIR_COUNT! EQU 1 (
    :: Prüfe ob der Unterordner die App-Dateien enthält
    if exist "!FIRST_SUBDIR!\\fexobooth.exe" (
        set "SOURCE_DIR=!FIRST_SUBDIR!"
    )
    if exist "!FIRST_SUBDIR!\\_internal" (
        set "SOURCE_DIR=!FIRST_SUBDIR!"
    )
)

echo Quelle: %SOURCE_DIR%
echo Ziel: %INSTALL_DIR%
echo.

:: Dateien kopieren (SCHÜTZE config.json, BILDER/, logs/, .booking_cache/)
echo Kopiere neue Dateien...

:: EXE aktualisieren
if exist "%SOURCE_DIR%\\fexobooth.exe" (
    echo - fexobooth.exe
    copy /Y "%SOURCE_DIR%\\fexobooth.exe" "%INSTALL_DIR%\\" >nul 2>&1
)

:: _internal/ komplett ersetzen (Python-Runtime + Dependencies)
if exist "%SOURCE_DIR%\\_internal" (
    echo - _internal/ (Runtime + Dependencies)
    if exist "%INSTALL_DIR%\\_internal" rmdir /s /q "%INSTALL_DIR%\\_internal"
    xcopy "%SOURCE_DIR%\\_internal" "%INSTALL_DIR%\\_internal" /E /I /Y >nul 2>&1
)

:: Assets aktualisieren (Templates, Icons etc.)
if exist "%SOURCE_DIR%\\assets" (
    echo - assets/
    xcopy "%SOURCE_DIR%\\assets" "%INSTALL_DIR%\\assets" /E /I /Y >nul 2>&1
)

:: Setup-Scripts aktualisieren
if exist "%SOURCE_DIR%\\setup" (
    echo - setup/
    xcopy "%SOURCE_DIR%\\setup" "%INSTALL_DIR%\\setup" /E /I /Y >nul 2>&1
)

:: BAT-Dateien aktualisieren
for %%F in (START.bat start_fexobooth.bat start_dev.bat update_from_github.bat) do (
    if exist "%SOURCE_DIR%\\%%F" (
        echo - %%F
        copy /Y "%SOURCE_DIR%\\%%F" "%INSTALL_DIR%\\" >nul 2>&1
    )
)

:: config.example.json aktualisieren (nicht config.json!)
if exist "%SOURCE_DIR%\\config.example.json" (
    echo - config.example.json
    copy /Y "%SOURCE_DIR%\\config.example.json" "%INSTALL_DIR%\\" >nul 2>&1
)

echo.
echo Geschuetzte Dateien/Ordner (NICHT ueberschrieben):
echo - config.json (Einstellungen)
echo - BILDER/ (Fotos)
echo - logs/ (Protokolle)
echo - .booking_cache/ (Buchungsdaten)

:: Aufräumen
echo.
echo Raeume auf...
del "%ZIP_FILE%" 2>nul
rmdir /s /q "%EXTRACT_DIR%" 2>nul
echo OK

echo.
echo ============================================
echo    UPDATE ERFOLGREICH!
echo ============================================
echo.

:: App neu starten
echo Starte FexoBooth...
cd /d "%INSTALL_DIR%"
{start_cmd}

:: Dieses Script löschen
(goto) 2>nul & del "%~f0"
'''

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    logger.info(f"Update-Script erstellt: {script_path}")
    return script_path


def apply_update_and_restart(zip_path: Path) -> Path:
    """Startet den Update-Prozess: BAT-Script erstellen und starten

    ACHTUNG: Nach Aufruf dieser Funktion MUSS die App beendet werden!

    Args:
        zip_path: Pfad zur heruntergeladenen ZIP-Datei

    Returns:
        Pfad zum gestarteten BAT-Script
    """
    install_dir = _get_install_dir()
    script_path = create_update_script(zip_path, install_dir)

    logger.info(f"Starte Update-Script: {script_path}")
    logger.info(f"Install-Dir: {install_dir}")

    # BAT-Script starten (im eigenen Fenster, damit es weiterläuft nach App-Ende)
    os.startfile(str(script_path))

    return script_path
