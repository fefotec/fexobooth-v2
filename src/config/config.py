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
        from ctypes import wintypes
        
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
