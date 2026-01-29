"""Lokale Speicherung mit automatischer USB-Kopie"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from PIL import Image

from src.storage.usb import USBManager
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Basis-Pfade
BASE_PATH = Path(__file__).parent.parent.parent
IMAGES_PATH = BASE_PATH / "BILDER"
SINGLES_PATH = IMAGES_PATH / "Single"
PRINTS_PATH = IMAGES_PATH / "Prints"


class LocalStorage:
    """Verwaltet lokale Bildspeicherung mit automatischer USB-Kopie"""
    
    def __init__(self):
        # Verzeichnisse erstellen
        SINGLES_PATH.mkdir(parents=True, exist_ok=True)
        PRINTS_PATH.mkdir(parents=True, exist_ok=True)
        
        # USB-Manager für automatische Kopie
        self.usb_manager = USBManager()
        
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
        
        logger.info(f"{count} Bilder gelöscht")
        return count
