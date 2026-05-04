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
import ssl
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from src.utils.logging import get_logger

logger = get_logger(__name__)

# GitHub Repository
GITHUB_REPO = "fefotec/fexobooth-v2"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# Timeout für HTTP-Requests (Sekunden)
HTTP_TIMEOUT = 30


def _build_ssl_context() -> ssl.SSLContext:
    """Erstellt einen SSL-Context mit explizitem CA-Bundle.

    Hintergrund: Im PyInstaller-Build findet `urllib` kein CA-Bundle und liefert
    bei HTTPS-Calls "SSL: CERTIFICATE_VERIFY_FAILED — unable to get local issuer
    certificate". Im Dev-Modus klappt es weil Python die System-Zertifikate
    findet, im EXE-Build aber nicht. Lösung: certifi mitpacken und den
    Context-Parameter hier explizit setzen.
    """
    try:
        import certifi
        ca_path = certifi.where()
        if os.path.isfile(ca_path):
            return ssl.create_default_context(cafile=ca_path)
        logger.warning(f"certifi.where() liefert nicht-existenten Pfad: {ca_path} — fallback auf System-Default")
    except ImportError:
        logger.warning("certifi nicht installiert — verwende Python-Default-SSL-Context")

    # Fallback: System-Default. Funktioniert im Dev-Modus, im PyInstaller-Build
    # höchstwahrscheinlich nicht (siehe Doc-String).
    return ssl.create_default_context()


# Globaler SSL-Context für alle HTTPS-Calls in diesem Modul.
# Einmal beim Modul-Import gebaut, dann von check_for_update() und
# download_update() gemeinsam genutzt.
_SSL_CONTEXT = _build_ssl_context()


def _get_install_dir() -> Path:
    """Ermittelt das Installationsverzeichnis"""
    if getattr(sys, 'frozen', False):
        # PyInstaller-Build: Verzeichnis der EXE
        return Path(sys.executable).parent
    else:
        # Entwicklermodus: Projekt-Root
        return Path(__file__).parent.parent


def cleanup_orphan_downloads(max_age_hours: float = 1.0) -> int:
    """Räumt nicht-abgeschlossene Update-Downloads aus %TEMP% auf.

    Wird beim App-Start aufgerufen. Wenn ein Update vorher abgebrochen wurde
    (Stromausfall, Prozess-Kill), bleiben ggf. eine ~150 MB ZIP-Datei und ein
    Extract-Verzeichnis in %TEMP% liegen. Windows räumt das nur bei manueller
    Datenträgerbereinigung auf → Tablets würden sich zumüllen.

    Wir löschen alles was älter als `max_age_hours` Stunden ist — damit ein
    gerade laufender Update-Download nicht versehentlich weggeputzt wird.

    Returns:
        Anzahl gelöschter Einträge (Dateien + Verzeichnisse)
    """
    import shutil
    import time

    temp_dir = Path(tempfile.gettempdir())
    now = time.time()
    max_age_sec = max_age_hours * 3600
    cleaned = 0

    # Targets: alle ZIPs/BATs/Extract-Dirs vom Updater (Glob-Patterns).
    # Seit v2.3.0 nutzen wir Timestamp+PID im Dateinamen, deshalb werden
    # Wildcards gebraucht. Alte Pfade ohne Suffix werden auch erfasst.
    patterns = [
        "fexobooth_update*.zip",
        "fexobooth_update_extract*",
        "fexobooth_updater*.bat",
    ]

    candidates = []
    for pattern in patterns:
        candidates.extend(temp_dir.glob(pattern))

    for path in candidates:
        if not path.exists():
            continue
        try:
            age = now - path.stat().st_mtime
            if age < max_age_sec:
                logger.debug(f"Orphan-Cleanup: {path.name} zu jung ({age/60:.0f} min) — übersprungen")
                continue

            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink()

            logger.info(f"Orphan-Cleanup: {path.name} entfernt (Alter: {age/3600:.1f} h)")
            cleaned += 1
        except Exception as e:
            logger.warning(f"Orphan-Cleanup: {path.name} konnte nicht entfernt werden: {e}")

    return cleaned


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
        with urlopen(req, timeout=HTTP_TIMEOUT, context=_SSL_CONTEXT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        # HTTP-Fehler (404, 403, 500…) — nicht einfach als "kein Internet" verkaufen.
        # 404 auf privaten Repos ohne Auth war historisch die Ursache für falsche
        # "Keine Internetverbindung"-Meldungen. Deshalb hier exakte Details loggen.
        logger.error(f"GitHub API HTTP {e.code}: {e.reason} (URL: {GITHUB_API_URL})", exc_info=True)
        raise ValueError(f"GitHub API HTTP {e.code}: {e.reason}")
    except URLError as e:
        # Echter Netzwerkfehler: kein DNS, kein Route, SSL-Fehler, Timeout
        logger.error(f"GitHub nicht erreichbar: {e}", exc_info=True)
        raise ConnectionError(f"GitHub nicht erreichbar: {e}")
    except Exception as e:
        logger.error(f"API-Fehler beim Update-Check: {e}", exc_info=True)
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
    # Eindeutiger Dateiname mit Timestamp + PID — vermeidet Lock-Konflikte mit
    # alten ZIPs die noch von Windows Defender gescannt werden, oder mit
    # einem laufenden BAT-Script vom letzten Update. Bug v2.2.9 trat auf wenn
    # %TEMP%\fexobooth_update.zip gerade gelocked war: unlink() warf eine
    # Exception → Update brach ab mit "Datei wird von anderem Prozess verwendet".
    import time
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    zip_path = Path(tempfile.gettempdir()) / f"fexobooth_update_{timestamp}_{os.getpid()}.zip"

    # Sicherheitshalber: Falls die Datei doch existiert (extrem unwahrscheinlich
    # wegen Timestamp+PID), versuche zu loeschen — bei Fehler ignorieren und
    # einen alternativen Namen verwenden.
    if zip_path.exists():
        try:
            zip_path.unlink()
        except OSError as e:
            logger.warning(f"Konnte {zip_path.name} nicht loeschen ({e}) — nutze Alternativnamen")
            zip_path = Path(tempfile.gettempdir()) / f"fexobooth_update_{timestamp}_{os.getpid()}_alt.zip"

    logger.info(f"Lade Update herunter: {download_url}")

    req = Request(
        download_url,
        headers={"User-Agent": "FexoBooth-Updater"}
    )

    try:
        with urlopen(req, timeout=120, context=_SSL_CONTEXT) as response:
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

                # Disk-Buffer hart flushen damit der Inhalt garantiert auf Disk
                # liegt bevor wir gleich validieren (und bevor BAT-Script + os._exit
                # die Datei aus der Hand nehmen).
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError as fsync_err:
                    logger.debug(f"fsync nicht möglich ({fsync_err}) — weiter")

    except Exception as e:
        # Aufräumen bei Fehler
        if zip_path.exists():
            try:
                zip_path.unlink()
            except OSError:
                pass
        raise ConnectionError(f"Download fehlgeschlagen: {e}")

    # Validierung 1: Content-Length muss übereinstimmen.
    # Wenn der Server die Verbindung früher schließt (WLAN-Drop, Server-Timeout)
    # haben wir eine truncated ZIP — PowerShell scheitert dann beim Expand-Archive
    # mit "Das Ende des Datensatzes im zentralen Verzeichnis wurde nicht gefunden".
    # Ohne diesen Check würde apply_update_and_restart() trotzdem starten,
    # die App würde sich beenden, das BAT-Script würde scheitern → Box hat
    # kein UI mehr (CMD-Fenster sichtbar). Genau der Bug aus 04.05.2026.
    if total_size > 0 and downloaded != total_size:
        try:
            zip_path.unlink()
        except OSError:
            pass
        raise ConnectionError(
            f"Download unvollständig: {downloaded} von {total_size} Bytes "
            f"empfangen ({downloaded / total_size * 100:.1f} %)"
        )

    # Validierung 2: ZIP-Integrität via zipfile.testzip() prüfen.
    # Stellt sicher dass die ZIP valide ist UND alle internen Checksummen passen.
    # Doppelt sicher — Content-Length kann theoretisch trotz Truncation matchen
    # wenn Server falschen Header sendet.
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                raise zipfile.BadZipFile(f"Datei {bad!r} im ZIP ist beschädigt")
    except (zipfile.BadZipFile, OSError) as e:
        try:
            zip_path.unlink()
        except OSError:
            pass
        raise ConnectionError(f"Heruntergeladenes ZIP ist beschädigt: {e}")

    logger.info(f"Download abgeschlossen + validiert: {zip_path} ({downloaded} Bytes)")
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
    # Eindeutige Namen pro Update-Lauf — vermeidet Konflikte mit Resten
    # vom letzten Update (Lock durch Windows Defender Scan, oder BAT-Script
    # das noch läuft).
    import time
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    script_path = Path(tempfile.gettempdir()) / f"fexobooth_updater_{timestamp}.bat"
    extract_dir = Path(tempfile.gettempdir()) / f"fexobooth_update_extract_{timestamp}"

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
    # WICHTIG: Bei jedem Fehlerpfad MUSS die App neu gestartet werden und das
    # Fenster sich automatisch schliessen. Sonst bleibt das CMD-Fenster offen
    # und blockiert das UI (Bug 04.05.2026: pause am Fehler-Ende → Fenster offen).
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
set "CONFIG_BACKUP=%TEMP%\\fexobooth_config_backup_%RANDOM%.json"

:: Warte bis die App beendet ist (max 15 Sekunden — sollte sofort wegen os._exit)
echo Warte auf Beendigung von %PROCESS_NAME%...
set WAIT_COUNT=0
:wait_loop
tasklist /FI "IMAGENAME eq %PROCESS_NAME%" 2>NUL | find /I "%PROCESS_NAME%" >NUL
if not errorlevel 1 (
    set /a WAIT_COUNT+=1
    if !WAIT_COUNT! GEQ 15 (
        echo App laeuft noch nach 15s - hartes Killen via taskkill
        taskkill /F /IM "%PROCESS_NAME%" >nul 2>&1
        timeout /t 3 /nobreak >nul
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

:: ============================================
:: SAFETY 1: config.json wegsichern
:: ============================================
:: Druck-Korrekturwerte (print_adjustment.offset_x/y/zoom), Drucker-Auswahl etc.
:: liegen in config.json. Falls beim Update etwas schiefgeht und die App
:: config.json mit Defaults neu erzeugt → Werte weg. Backup vor jedem Eingriff.
if exist "%INSTALL_DIR%\\config.json" (
    copy /Y "%INSTALL_DIR%\\config.json" "%CONFIG_BACKUP%" >nul 2>&1
    echo - config.json gesichert nach %CONFIG_BACKUP%
)

:: Altes Extract-Verzeichnis löschen
if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%"
mkdir "%EXTRACT_DIR%"

:: ZIP entpacken
echo Entpacke Update...
powershell -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%EXTRACT_DIR%' -Force" 2>&1

:: ============================================
:: SAFETY 2: Pre-Check NACH Entpacken, VOR jedem Anfassen von %INSTALL_DIR%
:: ============================================
:: PowerShell-Errors bei Expand-Archive setzen errorlevel NICHT zuverlaessig.
:: Bei truncated ZIPs liefert Expand-Archive teilweise Output, errorlevel
:: bleibt aber 0 → das alte Script ging trotzdem in den zerstoererischen
:: _internal-Move. Daher: explizit pruefen ob das Entpacken nutzbar war.
:: Wenn nicht → Abbruch BEVOR irgendwas am Install-Dir berührt wird.

:: Finde entpacktes Verzeichnis (kann direkt oder in Unterordner sein)
set "SOURCE_DIR=%EXTRACT_DIR%"
set SUBDIR_COUNT=0
for /d %%D in ("%EXTRACT_DIR%\\*") do (
    set "FIRST_SUBDIR=%%D"
    set /a SUBDIR_COUNT+=1
)
if !SUBDIR_COUNT! EQU 1 (
    if exist "!FIRST_SUBDIR!\\fexobooth.exe" set "SOURCE_DIR=!FIRST_SUBDIR!"
    if exist "!FIRST_SUBDIR!\\_internal" set "SOURCE_DIR=!FIRST_SUBDIR!"
)

:: Pre-Check 1: _internal/ muss existieren
if not exist "%SOURCE_DIR%\\_internal" (
    echo.
    echo ============================================
    echo  FEHLER: Update-Archiv unvollstaendig!
    echo  _internal/ fehlt im entpackten Inhalt.
    echo  Das Tablet wurde NICHT angefasst — alte Version laeuft weiter.
    echo ============================================
    goto :restart_old
)

:: Pre-Check 2: base_library.zip muss existieren (Pflicht-File jeder PyInstaller-Build)
if not exist "%SOURCE_DIR%\\_internal\\base_library.zip" (
    echo.
    echo ============================================
    echo  FEHLER: _internal/base_library.zip fehlt!
    echo  Das ZIP war beim Entpacken kaputt.
    echo  Das Tablet wurde NICHT angefasst — alte Version laeuft weiter.
    echo ============================================
    goto :restart_old
)

:: Pre-Check 3: pywin32-Module muessen drin sein (sonst geht der Druck nicht)
:: Bug 04.05.2026: halbherziges Update entfernte pywin32, "Druck nur unter
:: Windows verfuegbar" obwohl Box Windows war.
if not exist "%SOURCE_DIR%\\_internal\\win32" (
    if not exist "%SOURCE_DIR%\\_internal\\pywin32_system32" (
        echo.
        echo ============================================
        echo  FEHLER: pywin32-Module fehlen im Update-Archiv!
        echo  Druck-Funktionalitaet wuerde brechen.
        echo  Das Tablet wurde NICHT angefasst — alte Version laeuft weiter.
        echo ============================================
        goto :restart_old
    )
)

echo Pre-Check OK: Update-Archiv ist vollstaendig
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

:: _internal/ ATOMIC ersetzen mit Rollback bei Fehler.
echo - _internal/ (Runtime + Dependencies)
:: Aufraeumen aus vorherigem fehlgeschlagenen Update
if exist "%INSTALL_DIR%\\_internal_OLD" rmdir /s /q "%INSTALL_DIR%\\_internal_OLD" 2>nul
:: Alten Stand wegsichern (atomic move, scheitert wenn Files gelocked)
if exist "%INSTALL_DIR%\\_internal" (
    move "%INSTALL_DIR%\\_internal" "%INSTALL_DIR%\\_internal_OLD" >nul 2>&1
    if errorlevel 1 (
        echo FEHLER: _internal/ ist gelockt - Update abgebrochen
        goto :restart_old
    )
)
:: Neuen Stand kopieren
xcopy "%SOURCE_DIR%\\_internal" "%INSTALL_DIR%\\_internal" /E /I /Y /Q
if errorlevel 1 goto :rollback_internal

:: Post-Check: Wurde tatsaechlich was kopiert? xcopy kann errorlevel 0 setzen
:: auch wenn nur 0 Files kopiert wurden. Kritische Pflicht-Files pruefen.
if not exist "%INSTALL_DIR%\\_internal\\base_library.zip" goto :rollback_internal
if not exist "%INSTALL_DIR%\\_internal" goto :rollback_internal

:: Erfolg - alten Stand jetzt loeschen
if exist "%INSTALL_DIR%\\_internal_OLD" rmdir /s /q "%INSTALL_DIR%\\_internal_OLD" 2>nul
echo   _internal/ erfolgreich aktualisiert
goto :continue_assets

:rollback_internal
echo FEHLER: Kopieren fehlgeschlagen - Rollback auf alte Version...
if exist "%INSTALL_DIR%\\_internal" rmdir /s /q "%INSTALL_DIR%\\_internal" 2>nul
if exist "%INSTALL_DIR%\\_internal_OLD" (
    move "%INSTALL_DIR%\\_internal_OLD" "%INSTALL_DIR%\\_internal" >nul 2>&1
    echo Rollback abgeschlossen - alte Version laeuft.
)
goto :restart_old

:continue_assets

:: Assets aktualisieren — User-Custom-Files SCHUETZEN
:: Bug v2.2.8: xcopy /Y ueberschrieb assets/videos/start.mp4 etc. mit den
:: Defaults aus dem ZIP. User die ihre eigenen Videos eingerichtet hatten
:: verloren sie beim OTA-Update.
:: Fix: assets/videos/ vor dem xcopy in TEMP wegsichern, danach atomar
:: zurueckmoven (ueberschreibt die Defaults aus dem ZIP).
:: Auch das Auslose-Bild (flash_image, falls in assets/) wird via Backup
:: aller .png/.jpg/.jpeg im assets/-Root mitgesichert.
if exist "%SOURCE_DIR%\\assets" (
    echo - assets/ (User-Videos und Custom-Bilder werden geschuetzt)

    :: Backup-Verzeichnis vorbereiten
    set "ASSET_BACKUP=%TEMP%\\fexobooth_user_assets"
    if exist "%ASSET_BACKUP%" rmdir /s /q "%ASSET_BACKUP%" 2>nul
    mkdir "%ASSET_BACKUP%" 2>nul

    :: 1. assets/videos/ atomar wegsichern (User-Videos)
    if exist "%INSTALL_DIR%\\assets\\videos" (
        move "%INSTALL_DIR%\\assets\\videos" "%ASSET_BACKUP%\\videos" >nul 2>&1
    )

    :: 2. User-Bilder im assets/-Root sichern (z.B. custom flash_image)
    ::    Default-Files (fexobooth.ico) werden vom xcopy eh wieder hingelegt,
    ::    aber Custom-PNGs/JPGs die der User reingelegt hat sollen bleiben.
    mkdir "%ASSET_BACKUP%\\root_images" 2>nul
    for %%F in ("%INSTALL_DIR%\\assets\\*.png" "%INSTALL_DIR%\\assets\\*.jpg" "%INSTALL_DIR%\\assets\\*.jpeg") do (
        if exist "%%F" copy /Y "%%F" "%ASSET_BACKUP%\\root_images\\" >nul 2>&1
    )

    :: 3. Jetzt assets/ aus dem ZIP rueberkopieren
    xcopy "%SOURCE_DIR%\\assets" "%INSTALL_DIR%\\assets" /E /I /Y /Q

    :: 4. User-Videos zurueck (atomar move = ueberschreibt Default-Videos im ZIP)
    if exist "%ASSET_BACKUP%\\videos" (
        if exist "%INSTALL_DIR%\\assets\\videos" rmdir /s /q "%INSTALL_DIR%\\assets\\videos" 2>nul
        move "%ASSET_BACKUP%\\videos" "%INSTALL_DIR%\\assets\\videos" >nul 2>&1
        echo   User-Videos wiederhergestellt
    )

    :: 5. User-Bilder im assets/-Root zurueckkopieren
    if exist "%ASSET_BACKUP%\\root_images" (
        for %%F in ("%ASSET_BACKUP%\\root_images\\*.*") do (
            copy /Y "%%F" "%INSTALL_DIR%\\assets\\" >nul 2>&1
        )
    )

    :: 6. Backup aufraeumen
    if exist "%ASSET_BACKUP%" rmdir /s /q "%ASSET_BACKUP%" 2>nul
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
echo - assets/videos/ (User-Videos)
echo - assets/*.png/jpg (User-Bilder, z.B. Auslose-Bild)

:: ============================================
:: SAFETY: config.json-Restore wenn sie waehrend Update verloren ging
:: ============================================
:: Eigentlich wird config.json explizit nicht angefasst, aber als Sicherheitsnetz
:: stellen wir sie aus dem Backup wieder her, falls sie verloren ging oder
:: kleiner als das Backup wurde (Manipulation/Korruption durch teilweises Update).
if exist "%CONFIG_BACKUP%" (
    if not exist "%INSTALL_DIR%\\config.json" (
        echo - config.json fehlt - stelle aus Backup wieder her
        copy /Y "%CONFIG_BACKUP%" "%INSTALL_DIR%\\config.json" >nul 2>&1
    )
    del "%CONFIG_BACKUP%" 2>nul
)

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
exit /b 0

:: ============================================
:: FEHLER-PFAD: alte App neu starten + Fenster zu
:: ============================================
:: Wird von allen Pre-Checks und Rollback-Pfaden angesprungen. Stellt sicher
:: dass:
::   1. config.json aus dem Backup wiederhergestellt wird (falls sie verschwand)
::   2. die alte App automatisch neu gestartet wird
::   3. das CMD-Fenster sich nach 8 s automatisch schliesst
::   4. das BAT-Script sich selbst loescht
:: Verhindert den Bug 04.05.2026: pause am Ende blockierte das CMD-Fenster
:: ueber dem UI, Box wirkte tot.
:restart_old
echo.
echo === Update fehlgeschlagen — alte Version wird neu gestartet ===
:: config.json restoren falls weg
if exist "%CONFIG_BACKUP%" (
    if not exist "%INSTALL_DIR%\\config.json" (
        echo - config.json wird aus Backup wiederhergestellt
        copy /Y "%CONFIG_BACKUP%" "%INSTALL_DIR%\\config.json" >nul 2>&1
    )
    del "%CONFIG_BACKUP%" 2>nul
)
:: Aufraeumen Update-Reste
del "%ZIP_FILE%" 2>nul
rmdir /s /q "%EXTRACT_DIR%" 2>nul
:: Alte App starten
echo Starte FexoBooth...
cd /d "%INSTALL_DIR%"
{start_cmd}
:: Fenster schliesst sich automatisch — kein blockierendes pause mehr
echo.
echo Dieses Fenster schliesst sich in 8 Sekunden automatisch...
timeout /t 8 /nobreak >nul
:: Script selbst loeschen
(goto) 2>nul & del "%~f0"
exit /b 1
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
