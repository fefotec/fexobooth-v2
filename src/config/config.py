"""Konfigurationsmanagement"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from copy import deepcopy

from .defaults import DEFAULT_CONFIG

# Globale Config-Instanz
_config: Optional[Dict[str, Any]] = None

# Pfade
BASE_PATH = Path(__file__).parent.parent.parent
CONFIG_PATH = BASE_PATH / "config.json"


def load_config() -> Dict[str, Any]:
    """Lädt die Konfiguration"""
    global _config
    
    # Mit Defaults starten
    config = deepcopy(DEFAULT_CONFIG)
    
    # Lokale Config laden
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                local_config = json.load(f)
            _deep_merge(config, local_config)
        except Exception as e:
            print(f"Fehler beim Laden der Config: {e}")
    
    # USB-Config prüfen (überschreibt lokale)
    usb_config = _find_usb_config()
    if usb_config:
        _deep_merge(config, usb_config)
    
    _config = config
    return config


def save_config(config: Dict[str, Any]) -> bool:
    """Speichert die Konfiguration"""
    global _config
    
    try:
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


def _deep_merge(base: Dict, update: Dict) -> Dict:
    """Merged zwei Dicts rekursiv"""
    for key, value in update.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
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
