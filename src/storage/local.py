"""Lokale Speicherung mit automatischer USB-Kopie"""

import os
import sys
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
from PIL import Image

from src.utils.logging import get_logger

logger = get_logger(__name__)


def _resolve_images_base() -> Path:
    """Basis für BILDER/: IMMER neben der EXE, NIE in _internal.

    Bug 2026-08-07 („nach jedem Update sind alle Bilder weg"): Im
    PyInstaller-Build zeigt __file__ nach _internal → BILDER lag in
    C:\\FexoBooth\\_internal\\BILDER. Das Update-BAT ersetzt _internal aber
    ATOMISCH (move nach _internal_OLD, kopieren, _internal_OLD löschen) —
    sein „BILDER/ wird geschützt" galt nur für den Install-Root. Jedes
    OTA-Update löschte damit sämtliche Fotos. Fix wie in config.py:
    im Build neben der EXE (C:\\FexoBooth\\BILDER), im Dev-Mode Repo-Root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


# Basis-Pfade
BASE_PATH = _resolve_images_base()
IMAGES_PATH = BASE_PATH / "BILDER"
SINGLES_PATH = IMAGES_PATH / "Single"
PRINTS_PATH = IMAGES_PATH / "Prints"

# Alter (falscher) Speicherort im Build — Quelle für die Einmal-Migration
_LEGACY_INTERNAL_IMAGES = (
    Path(sys.executable).resolve().parent / "_internal" / "BILDER"
    if getattr(sys, "frozen", False) else None
)


def _migrate_legacy_internal_images() -> None:
    """Einmal-Migration: Bilder aus _internal\\BILDER in den sicheren Ort holen.

    Läuft beim ersten Start nach dem Update auf die gefixte Version. Verschiebt
    alles (Single/, Prints/, .thumbs/, …) per merge und entfernt danach den
    Legacy-Ordner. Best-effort: Ein Fehler darf den App-Start nicht verhindern.
    """
    legacy = _LEGACY_INTERNAL_IMAGES
    if legacy is None or not legacy.exists():
        return
    try:
        if legacy.resolve() == IMAGES_PATH.resolve():
            return  # Sicherheitsnetz — sollte im Build nie passieren
    except OSError:
        return

    moved = 0
    try:
        IMAGES_PATH.mkdir(parents=True, exist_ok=True)
        for root, _dirs, files in os.walk(legacy):
            rel = Path(root).relative_to(legacy)
            target_dir = IMAGES_PATH / rel
            target_dir.mkdir(parents=True, exist_ok=True)
            for name in files:
                src = Path(root) / name
                dst = target_dir / name
                try:
                    if not dst.exists():
                        shutil.move(str(src), str(dst))
                        moved += 1
                    else:
                        src.unlink()  # Duplikat — neuer Ort gewinnt
                except OSError as e:
                    logger.warning(f"BILDER-Migration: '{name}' nicht verschiebbar: {e}")
        shutil.rmtree(legacy, ignore_errors=True)
        logger.info(f"BILDER-Migration: {moved} Dateien aus _internal\\BILDER nach {IMAGES_PATH} verschoben")
    except Exception as e:
        logger.error(f"BILDER-Migration fehlgeschlagen (Bilder bleiben in _internal): {e}")

# Singleton USBManager - wird von allen geteilt
_shared_usb_manager = None

def get_shared_usb_manager():
    """Gibt den gemeinsamen USBManager zurück (Singleton)"""
    global _shared_usb_manager
    if _shared_usb_manager is None:
        from src.storage.usb import USBManager
        _shared_usb_manager = USBManager()
    return _shared_usb_manager


class LocalStorage:
    """Verwaltet lokale Bildspeicherung mit automatischer USB-Kopie"""
    
    def __init__(self):
        # Einmal-Migration von _internal\BILDER (siehe _resolve_images_base)
        _migrate_legacy_internal_images()

        # Verzeichnisse erstellen
        SINGLES_PATH.mkdir(parents=True, exist_ok=True)
        PRINTS_PATH.mkdir(parents=True, exist_ok=True)
        
        # Gemeinsamen USB-Manager verwenden
        self.usb_manager = get_shared_usb_manager()
        
        logger.info(f"Speicherpfade initialisiert: {IMAGES_PATH}")
    
    def save_single(self, image: Image.Image, suffix: str = "") -> Optional[Path]:
        """Speichert ein Einzelbild (lokal + USB)"""
        filename = self._generate_filename("single", suffix)
        path = SINGLES_PATH / filename
        
        try:
            # RGB konvertieren falls nötig
            if image.mode == "RGBA":
                image = image.convert("RGB")
            
            # Lokal speichern
            image.save(path, "JPEG", quality=95)
            logger.info(f"Einzelbild gespeichert: {path}")
            
            # Auf USB kopieren wenn verfügbar
            self.usb_manager.copy_to_usb(path, "Single")
            
            return path
            
        except Exception as e:
            logger.error(f"Fehler beim Speichern: {e}")
            return None
    
    def save_print(self, image: Image.Image, suffix: str = "") -> Optional[Path]:
        """Speichert ein Print-Bild (lokal + USB)"""
        filename = self._generate_filename("print", suffix)
        path = PRINTS_PATH / filename
        
        try:
            # RGB konvertieren falls nötig
            if image.mode == "RGBA":
                image = image.convert("RGB")
            
            # Lokal speichern
            image.save(path, "JPEG", quality=95)
            logger.info(f"Print gespeichert: {path}")
            
            # Auf USB kopieren wenn verfügbar
            self.usb_manager.copy_to_usb(path, "Prints")
            
            return path
            
        except Exception as e:
            logger.error(f"Fehler beim Speichern: {e}")
            return None
    
    def _generate_filename(self, prefix: str, suffix: str = "") -> str:
        """Generiert einen eindeutigen Dateinamen"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        
        if suffix:
            return f"{timestamp}_fexobox_{prefix}_{suffix}.jpg"
        return f"{timestamp}_fexobox_{prefix}.jpg"
    
    @staticmethod
    def get_images_path() -> Path:
        """Gibt den Bilder-Pfad zurück"""
        return IMAGES_PATH
    
    @staticmethod
    def get_recent_images(folder: str = "Single", count: int = 20) -> list:
        """Gibt die letzten Bilder aus einem Ordner zurück"""
        if folder == "Single":
            path = SINGLES_PATH
        elif folder == "Prints":
            path = PRINTS_PATH
        else:
            path = IMAGES_PATH / folder
        
        if not path.exists():
            return []
        
        images = list(path.glob("*.jpg"))
        images.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        return images[:count]
    
    @staticmethod
    def delete_all_images() -> int:
        """Löscht alle Bilder (mit Vorsicht verwenden!)"""
        count = 0

        for folder in [SINGLES_PATH, PRINTS_PATH]:
            if folder.exists():
                for file in folder.glob("*.jpg"):
                    try:
                        file.unlink()
                        count += 1
                    except Exception as e:
                        logger.warning(f"Konnte {file} nicht löschen: {e}")

        # Thumbnail-Cache der Galerie folgt dem Lebenszyklus der Bilder
        # (Plan Offline-Galerie Etappe 2): Event-Wechsel räumt ihn mit,
        # sonst lägen dort verwaiste Thumbs des alten Events.
        thumbs_cache = IMAGES_PATH / ".thumbs"
        if thumbs_cache.exists():
            try:
                shutil.rmtree(thumbs_cache)
                logger.info("Thumbnail-Cache (.thumbs) gelöscht")
            except Exception as e:
                logger.warning(f"Konnte Thumbnail-Cache nicht löschen: {e}")

        logger.info(f"{count} Bilder gelöscht")
        return count
