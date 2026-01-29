"""Lokale Speicherung"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from PIL import Image

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Basis-Pfade
BASE_PATH = Path(__file__).parent.parent.parent
IMAGES_PATH = BASE_PATH / "BILDER"
SINGLES_PATH = IMAGES_PATH / "Single"
PRINTS_PATH = IMAGES_PATH / "Prints"


class LocalStorage:
    """Verwaltet lokale Bildspeicherung"""
    
    def __init__(self):
        # Verzeichnisse erstellen
        SINGLES_PATH.mkdir(parents=True, exist_ok=True)
        PRINTS_PATH.mkdir(parents=True, exist_ok=True)
        logger.info(f"Speicherpfade initialisiert: {IMAGES_PATH}")
    
    def save_single(self, image: Image.Image, suffix: str = "") -> Optional[Path]:
        """Speichert ein Einzelbild"""
        filename = self._generate_filename("single", suffix)
        path = SINGLES_PATH / filename
        
        try:
            image.save(path, "JPEG", quality=95)
            logger.info(f"Einzelbild gespeichert: {path}")
            return path
        except Exception as e:
            logger.error(f"Fehler beim Speichern: {e}")
            return None
    
    def save_print(self, image: Image.Image, suffix: str = "") -> Optional[Path]:
        """Speichert ein Print-Bild"""
        filename = self._generate_filename("print", suffix)
        path = PRINTS_PATH / filename
        
        try:
            image.save(path, "JPEG", quality=95)
            logger.info(f"Print gespeichert: {path}")
            return path
        except Exception as e:
            logger.error(f"Fehler beim Speichern: {e}")
            return None
    
    def _generate_filename(self, prefix: str, suffix: str = "") -> str:
        """Generiert einen eindeutigen Dateinamen"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if suffix:
            return f"{timestamp}_fexobox_{prefix}_{suffix}.jpg"
        return f"{timestamp}_fexobox_{prefix}.jpg"
    
    @staticmethod
    def get_recent_images(count: int = 20) -> list:
        """Gibt die letzten Bilder zurück"""
        images = []
        
        for folder in [SINGLES_PATH, PRINTS_PATH]:
            if folder.exists():
                for file in folder.glob("*.jpg"):
                    images.append(file)
        
        # Nach Datum sortieren (neueste zuerst)
        images.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        return images[:count]
