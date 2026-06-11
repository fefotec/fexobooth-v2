"""Konfigurationsmanagement"""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from copy import deepcopy

from .defaults import DEFAULT_CONFIG
from src.i18n import apply_locale_to_config

# Globale Config-Instanz
_config: Optional[Dict[str, Any]] = None

# Pfade
if getattr(sys, "frozen", False):
    # PyInstaller one-folder: config.json muss neben der EXE liegen, nicht in
    # _internal/. _internal wird bei OTA-Updates ersetzt.
    BASE_PATH = Path(sys.executable).resolve().parent
else:
    BASE_PATH = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_PATH / "config.json"
_LEGACY_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"
_IDENTITY_KEYS = ("box_id",)


def load_config() -> Dict[str, Any]:
    """Lädt die Konfiguration"""
    global _config
    
    # Mit Defaults starten
    config = deepcopy(DEFAULT_CONFIG)
    
    # Lokale Config laden. Bei alten Builds lag config.json unter _internal/.
    # Falls dort noch eine Box-ID steht, wird diese Legacy-Config bevorzugt und
    # in den neuen, update-sicheren Root-Pfad migriert.
    local_config = _load_local_config()
    if local_config:
        _deep_merge(config, local_config)
    
    # USB-Config prüfen (überschreibt lokale)
    usb_config = _find_usb_config()
    if usb_config:
        _deep_merge(config, usb_config, preserve_identity=True)

    apply_locale_to_config(config)
    
    _config = config
    return config


def save_config(config: Dict[str, Any]) -> bool:
    """Speichert die Konfiguration"""
    global _config
    
    try:
        apply_locale_to_config(config)
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        _config = config
        return True
    except Exception as e:
        print(f"Fehler beim Speichern der Config: {e}")
        return False


def get_config() -> Dict[str, Any]:
    """Gibt die aktuelle Konfiguration zurück"""
    global _config
    if _config is None:
        return load_config()
    return _config


def _load_local_config() -> Optional[Dict[str, Any]]:
    candidates = []
    seen = set()
    for path in (CONFIG_PATH, _LEGACY_CONFIG_PATH):
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.exists():
            candidates.append((path, _read_config_file(path)))

    valid = [(path, data) for path, data in candidates if isinstance(data, dict)]
    if not valid:
        return None

    selected_path, selected_config = valid[0]
    canonical_has_identity = _has_identity(selected_config)

    if selected_path == CONFIG_PATH and not canonical_has_identity:
        for path, data in valid[1:]:
            if _has_identity(data):
                selected_path, selected_config = path, data
                break

    if selected_path != CONFIG_PATH:
        _migrate_legacy_config(selected_path)

    return selected_config


def _read_config_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Fehler beim Laden der Config {path}: {e}")
        return None


def _has_identity(config: Dict[str, Any]) -> bool:
    return any(str(config.get(key, "") or "").strip() for key in _IDENTITY_KEYS)


def _migrate_legacy_config(source_path: Path) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, CONFIG_PATH)
        print(f"Legacy-Config migriert: {source_path} -> {CONFIG_PATH}")
    except Exception as e:
        print(f"Legacy-Config konnte nicht migriert werden: {e}")


def _deep_merge(base: Dict, update: Dict, preserve_identity: bool = False) -> Dict:
    """Merged zwei Dicts rekursiv"""
    for key, value in update.items():
        if (
            preserve_identity
            and key in _IDENTITY_KEYS
            and str(base.get(key, "") or "").strip()
            and not str(value or "").strip()
        ):
            continue
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value, preserve_identity=preserve_identity)
        else:
            base[key] = value
    return base


def _find_usb_config() -> Optional[Dict[str, Any]]:
    """Sucht config.json auf USB-Stick"""
    # Windows: Suche Laufwerke D-Z nach "fexobox" Volume
    if os.name == "nt":
        import ctypes

        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                # Volume-Label prüfen
                try:
                    volume_name = ctypes.create_unicode_buffer(261)
                    ctypes.windll.kernel32.GetVolumeInformationW(
                        drive, volume_name, 261,
                        None, None, None, None, 0
                    )
                    if volume_name.value.lower() == "fexobox":
                        config_path = Path(drive) / "config.json"
                        if config_path.exists():
                            with open(config_path, "r", encoding="utf-8") as f:
                                return json.load(f)
                except:
                    pass

    return None


def find_usb_template(include_cache: bool = True) -> Optional[str]:
    """Sucht ZIP-Templates auf USB-Sticks oder im Cache.

    Durchsucht alle Wechseldatenträger (USB-Sticks) nach ZIP-Dateien
    im Root-Verzeichnis. Falls kein USB gefunden wird und include_cache=True,
    wird das gecachte Template zurückgegeben (falls vorhanden).

    Args:
        include_cache: Wenn True, wird auch der Cache berücksichtigt
        
    Returns:
        Pfad zur ZIP-Datei oder None wenn nichts gefunden
    """
    # Erst auf USB suchen
    usb_template = _find_usb_template_on_drive()
    if usb_template:
        return usb_template
    
    # Fallback: Cache prüfen
    if include_cache:
        cache_path = Path(__file__).parent.parent.parent / ".booking_cache" / "cached_template.zip"
        if cache_path.exists():
            print(f"Gecachtes Template gefunden: {cache_path}")
            return str(cache_path)
    
    return None


def _find_usb_template_on_drive() -> Optional[str]:
    """Sucht ZIP-Templates nur auf USB-Sticks."""
    if os.name != "nt":
        return None

    import ctypes

    # DRIVE_REMOVABLE = 2 (USB-Sticks, SD-Karten, etc.)
    DRIVE_REMOVABLE = 2

    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        drive = f"{letter}:\\"

        # Prüfen ob Laufwerk existiert und Wechseldatenträger ist
        try:
            if not os.path.exists(drive):
                continue

            drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
            if drive_type != DRIVE_REMOVABLE:
                continue

            # ZIP-Dateien im Root suchen
            for item in os.listdir(drive):
                if item.lower().endswith(".zip"):
                    zip_path = os.path.join(drive, item)
                    # Prüfen ob es ein gültiges Template ist (enthält PNG)
                    if _is_valid_template_zip(zip_path):
                        print(f"USB-Template gefunden: {zip_path}")
                        return zip_path

        except (OSError, PermissionError):
            # Laufwerk nicht lesbar
            continue

    return None


def _is_valid_template_zip(zip_path: str) -> bool:
    """Prüft ob eine ZIP-Datei ein gültiges Template ist.

    Rejects:
    - ZIPs die .exe/.dll Dateien enthalten (Anwendungs-ZIPs)
    - ZIPs die _internal/ Verzeichnisse enthalten (PyInstaller builds)
    - ZIPs ohne PNG-Dateien
    """
    import zipfile

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            has_png = False
            for name in zf.namelist():
                lower = name.lower()
                # Anwendungs-ZIP erkennen (PyInstaller build, Installer etc.)
                if lower.endswith((".exe", ".dll")) or "_internal/" in lower:
                    return False
                if lower.endswith(".png"):
                    has_png = True
            return has_png
    except:
        pass

    return False
