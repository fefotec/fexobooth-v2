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
from src.utils.logging import get_logger

logger = get_logger(__name__)

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
_MISSING = object()

_PRODUCTION_PRINT_ADJUSTMENT = {
    "offset_x": 40,
    "offset_y": 30,
    "zoom": 103,
    "bleed_mm": 3,
}

_PRODUCTION_DEFAULT_OVERRIDES = {
    "countdown_time": 7,
    "single_display_time": 3,
    "final_time": 20,
    "flash_duration": 100,
    "max_prints_per_session": 1,
    "allow_single_mode": False,
    "performance_mode": True,
    "start_fullscreen": True,
    "hide_finish_button": True,
    "print_enabled": True,
    "template1_enabled": True,
    "template2_enabled": False,
    "template_paths": {
        "template1": "assets/templates/Fexobox Standard.zip",
        "template2": "",
    },
    "gallery_port": 8080,
    "gallery": {
        "hotspot_ssid": "fexobox-gallery",
        "hotspot_password": "fotobox123",
        "port": 8080,
    },
    "video_start": "assets/videos/Fexon - Fotobox Tutorial 1 By Videoboost.Undefined.mp4",
    "video_after_1": "assets/videos/Fexon - Fotobox Tutorial 3 By Videoboost.Undefined.mp4",
    "video_after_2": "assets/videos/Fexon - Fotobox Tutorial 4 By Videoboost.Undefined.mp4",
    "video_after_3": "assets/videos/Fexon - Fotobox Tutorial 5 By Videoboost.Undefined.mp4",
    "video_end": "assets/videos/Fexon - Fotobox Tutorial 7 By Videoboost.Undefined.mp4",
    "flash_image": "assets/icons/foto-screen.jpeg",
    # WICHTIG: print_adjustment bewusst NICHT hier eintragen!
    # Diese Overrides werden bei JEDEM Start ueber _apply_production_defaults()
    # erzwungen. Stuende print_adjustment hier, wuerde jeder Neustart die im
    # 2015er-Menue gespeicherten Druckwerte wieder auf Produktionswerte
    # zuruecksetzen (Bug, behoben 2026-06-19).
    # Der Start-Default kommt aus defaults.py (identische 40/30/103/3); der
    # gewollte Reset pro Eventwechsel laeuft ueber reset_event_defaults().
}

_BUILTIN_ASSET_KEYS = (
    ("video_start",),
    ("video_after_1",),
    ("video_after_2",),
    ("video_after_3",),
    ("video_end",),
    ("flash_image",),
    ("template_paths", "template1"),
    ("template_paths", "template2"),
)

_MACHINE_SETTINGS_KEYS = (
    ("box_id",),
    ("printer_name",),
    ("camera_type",),
    ("camera_index",),
    ("rotate_180",),
    ("liveview_template_overlay",),
    ("camera_settings", "single_photo_width"),
    ("camera_settings", "single_photo_height"),
    ("camera_settings", "live_view_resolution"),
)


def _programdata_base_path() -> Path:
    if os.name == "nt":
        base = os.environ.get("PROGRAMDATA") or os.environ.get("ALLUSERSPROFILE") or r"C:\ProgramData"
        return Path(base) / "FexoBox"
    return Path.home() / ".fexobooth"


def _persistent_store_path() -> Path:
    """Pfad zum update-sicheren Box-ID-Speicher AUSSERHALB des Installationsordners.

    Hintergrund: config.json liegt im Installationsordner (neben der EXE bzw. in
    alten Builds in _internal/). Beide können bei einem fehlerhaften OTA-Update
    verloren gehen — genau das passiert beim Update FROM einer Version mit altem
    BAT-Script, weil das ersetzende BAT immer von der ALTEN laufenden Version
    erzeugt wird (Selbst-Updater-Bootstrap-Problem).

    Deshalb spiegeln wir die Box-ID zusätzlich an einen Ort, den kein Update-BAT
    jemals anfasst:
    - Windows: %PROGRAMDATA%\\FexoBox\\box_id.json  (i.d.R. C:\\ProgramData\\FexoBox)
    - sonst (Dev/macOS/Linux): ~/.fexobooth/box_id.json
    """
    return _programdata_base_path() / "box_id.json"


def _machine_settings_path() -> Path:
    return _programdata_base_path() / "machine_settings.json"


def _read_persistent_identity() -> Dict[str, Any]:
    """Liest die im update-sicheren Speicher abgelegten Identity-Werte (Box-ID)."""
    path = _persistent_store_path()
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        print(f"Persistenter Box-ID-Speicher nicht lesbar ({path}): {e}")
    return {}


def _write_persistent_identity(config: Dict[str, Any]) -> None:
    """Spiegelt eine gültige Box-ID in den update-sicheren Speicher.

    Wird bei jedem Speichern und beim Start aufgerufen. Schreibt NUR, wenn eine
    nicht-leere Box-ID vorhanden ist — eine leere ID darf den vorhandenen
    Speicher niemals überschreiben (sonst ginge der Schutz verloren).
    """
    identity = {
        key: config.get(key)
        for key in _IDENTITY_KEYS
        if str(config.get(key, "") or "").strip()
    }
    if not identity:
        return
    path = _persistent_store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(identity, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Persistenter Box-ID-Speicher nicht schreibbar ({path}): {e}")


def _read_machine_settings() -> Dict[str, Any]:
    """Liest update-sichere Maschinenwerte aus ProgramData.

    Diese Datei enthaelt nur box-spezifische Werte, keine Event-/Kundenwerte.
    """
    path = _machine_settings_path()
    data: Dict[str, Any] = {}
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data.update(loaded)
    except Exception as e:
        print(f"Machine-Settings nicht lesbar ({path}): {e}")

    # Migration/Kompatibilitaet: v2.4.6 speicherte nur box_id.json.
    identity = _read_persistent_identity()
    for key in _IDENTITY_KEYS:
        if not str(data.get(key, "") or "").strip() and str(identity.get(key, "") or "").strip():
            data[key] = identity[key]

    return data


def _write_machine_settings(config: Dict[str, Any]) -> None:
    """Spiegelt stabile Maschinenwerte in ProgramData.

    Leere Strings ueberschreiben vorhandene Werte nicht. So kann eine durch ein
    Update geleerte config.json keine Maschinenwerte loeschen.
    """
    path = _machine_settings_path()
    existing_data = _read_machine_settings()
    data: Dict[str, Any] = {}

    for key_path in _MACHINE_SETTINGS_KEYS:
        value = _get_nested(config, key_path)
        if value is _MISSING or (isinstance(value, str) and not value.strip()):
            value = _get_nested(existing_data, key_path)
            if value is _MISSING:
                continue
            if isinstance(value, str) and not value.strip():
                continue
        _set_nested(data, key_path, value)

    if not data:
        return

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Machine-Settings nicht schreibbar ({path}): {e}")


def _recover_machine_settings(config: Dict[str, Any]) -> bool:
    """Wendet gespeicherte ProgramData-Maschinenwerte auf die Config an."""
    data = _read_machine_settings()
    changed = False

    for key_path in _MACHINE_SETTINGS_KEYS:
        value = _get_nested(data, key_path)
        if value is _MISSING:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        changed |= _assign_if_changed(config, key_path, value)

    return changed


def _recover_identity_from_store(config: Dict[str, Any]) -> bool:
    """Holt fehlende Identity-Werte (Box-ID) aus dem update-sicheren Speicher.

    Greift nur, wenn die geladene Config KEINE Box-ID hat — typischerweise nach
    einem Update, das config.json im Installationsordner verloren hat.

    Returns:
        True, wenn eine Box-ID wiederhergestellt wurde.
    """
    if _has_identity(config):
        return False

    stored = _read_persistent_identity()
    recovered = False
    for key in _IDENTITY_KEYS:
        value = str(stored.get(key, "") or "").strip()
        if value:
            config[key] = value
            recovered = True

    if recovered:
        print(f"Box-ID aus update-sicherem Speicher wiederhergestellt: {config.get('box_id')!r}")
    return recovered


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

    changed = False

    # Produktions-Defaults aus v2.4.7 wiederherstellen. Diese Werte wurden bei
    # manchen OTA-Updates durch eine neu erzeugte config.json verloren.
    changed |= _apply_production_defaults(config)

    # Box-spezifische Maschinenwerte aus ProgramData zurueckholen.
    changed |= _recover_machine_settings(config)

    # Update-sicherer Box-ID-Speicher (ProgramData): Wenn weder lokale noch
    # USB-Config eine Box-ID liefern, aber im update-sicheren Speicher eine steht,
    # diese zurückholen. Schützt vor Box-ID-Verlust durch fehlerhafte Updates.
    changed |= _recover_identity_from_store(config)

    apply_locale_to_config(config)

    _config = config

    # Welcher print_adjustment-Wert wurde wirklich geladen? (Feld-Bug-Diagnose:
    # zeigt, ob die im 2015er-Menue gespeicherten Druckwerte erhalten bleiben.)
    logger.info(f"Config geladen - print_adjustment={config.get('print_adjustment')}")

    if changed:
        # Wiederhergestellte Werte dauerhaft zurück in config.json schreiben,
        # damit der Rest der App und kuenftige Update-Backups sie wieder sehen.
        save_config(config)
    else:
        # Gültige Box-ID in den update-sicheren Speicher spiegeln (z.B. beim ersten
        # Start einer Version mit diesem Schutz, oder nach manuellem Setzen).
        _write_persistent_identity(config)
        _write_machine_settings(config)

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
        # Box-ID zusätzlich in den update-sicheren Speicher spiegeln, damit sie
        # jedes Update überlebt — egal welche Version das ersetzende BAT erzeugt.
        _write_persistent_identity(config)
        _write_machine_settings(config)
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


def reset_event_defaults(config: Dict[str, Any]) -> bool:
    """Setzt Werte zurueck, die bei jedem Event neu auf Produktionsstandard sollen."""
    return _assign_if_changed(config, ("print_adjustment",), _PRODUCTION_PRINT_ADJUSTMENT)


def _apply_production_defaults(config: Dict[str, Any]) -> bool:
    """Erzwingt Produktions-Defaults, die durch Updates nicht verloren gehen duerfen."""
    changed = False
    for key, value in _PRODUCTION_DEFAULT_OVERRIDES.items():
        changed |= _assign_if_changed(config, (key,), _production_default_value(key, value))

    # Top-Level-Port und Admin-Galerie-Port synchron halten.
    gallery_port = _get_nested(config, ("gallery", "port"))
    if gallery_port is not _MISSING:
        changed |= _assign_if_changed(config, ("gallery_port",), gallery_port)

    changed |= _resolve_builtin_asset_paths(config)
    return changed


def _production_default_value(key: str, value):
    expected = deepcopy(value)
    if key in {"video_start", "video_after_1", "video_after_2", "video_after_3", "video_end", "flash_image"}:
        return _resolve_builtin_asset_path(str(expected))

    if key == "template_paths" and isinstance(expected, dict):
        for template_key, template_value in expected.items():
            if template_value:
                expected[template_key] = _resolve_builtin_asset_path(str(template_value))

    return expected


def _resolve_builtin_asset_paths(config: Dict[str, Any]) -> bool:
    changed = False
    for key_path in _BUILTIN_ASSET_KEYS:
        value = _get_nested(config, key_path)
        if not value:
            continue
        resolved = _resolve_builtin_asset_path(str(value))
        if resolved != value:
            changed |= _assign_if_changed(config, key_path, resolved)
    return changed


def _resolve_builtin_asset_path(value: str) -> str:
    """Mappt assets/... auf den echten Pfad im Dev- oder PyInstaller-Build."""
    raw = str(value).strip()
    if not raw:
        return raw

    path = Path(raw)
    if path.is_absolute() and path.exists():
        return raw

    suffix = _extract_asset_suffix(raw)
    if not suffix:
        return raw

    for base in _asset_base_candidates():
        candidate = base / Path(*suffix.split("/"))
        if candidate.exists():
            return str(candidate)

    return raw


def _extract_asset_suffix(value: str) -> Optional[str]:
    normalized = value.replace("\\", "/")
    idx = normalized.lower().find("assets/")
    if idx < 0:
        return None
    return normalized[idx:]


def _asset_base_candidates():
    candidates = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass))

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir / "_internal", exe_dir])

    candidates.extend([
        BASE_PATH,
        Path(__file__).resolve().parents[2],
        Path.cwd(),
    ])

    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        yield candidate


def _get_nested(data: Dict[str, Any], key_path):
    current = data
    for key in key_path:
        if not isinstance(current, dict) or key not in current:
            return _MISSING
        current = current[key]
    return current


def _set_nested(data: Dict[str, Any], key_path, value) -> None:
    current = data
    for key in key_path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[key_path[-1]] = deepcopy(value)


def _assign_if_changed(data: Dict[str, Any], key_path, value) -> bool:
    current = _get_nested(data, key_path)
    if current == value:
        return False
    _set_nested(data, key_path, value)
    return True


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
        from src.storage.paths import persistent_data_path
        cache_dir = persistent_data_path(".booking_cache")
        meta_path = cache_dir / ".app_upload_meta.json"
        try:
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if (
                    isinstance(meta, dict)
                    and meta.get("source") == "app"
                    and meta.get("template")
                    and meta.get("template_path")
                ):
                    app_template = Path(str(meta.get("template_path")))
                    if app_template.exists():
                        print(f"Gecachtes App-Template gefunden: {app_template}")
                        return str(app_template)
        except Exception:
            pass

        cache_path = cache_dir / "cached_template.zip"
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
