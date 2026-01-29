"""USB-Stick Management"""

import os
import shutil
import time
from pathlib import Path
from typing import Optional

from src.utils.logging import get_logger

logger = get_logger(__name__)


class USBManager:
    """Verwaltet USB-Stick Operationen"""
    
    USB_LABEL = "fexobox"
    
    def __init__(self):
        self._last_check_time: float = 0
        self._cached_drive: Optional[str] = None
        self._check_interval: float = 2.0  # Sekunden
    
    def find_usb_stick(self) -> Optional[str]:
        """Sucht USB-Stick mit Label 'fexobox'"""
        current_time = time.time()
        
        # Cache nutzen
        if current_time - self._last_check_time < self._check_interval:
            return self._cached_drive
        
        self._last_check_time = current_time
        self._cached_drive = None
        
        # Nur Windows unterstützt
        if os.name != "nt":
            return None
        
        try:
            import ctypes
            
            for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    volume_name = ctypes.create_unicode_buffer(261)
                    result = ctypes.windll.kernel32.GetVolumeInformationW(
                        drive, volume_name, 261,
                        None, None, None, None, 0
                    )
                    
                    if result and volume_name.value.lower() == self.USB_LABEL.lower():
                        self._cached_drive = drive
                        logger.debug(f"USB-Stick gefunden: {drive}")
                        return drive
        except Exception as e:
            logger.error(f"USB-Suche fehlgeschlagen: {e}")
        
        return None
    
    def is_available(self) -> bool:
        """Prüft ob USB-Stick verfügbar ist"""
        return self.find_usb_stick() is not None
    
    def get_images_path(self) -> Optional[Path]:
        """Gibt den Bilder-Pfad auf dem USB-Stick zurück"""
        usb = self.find_usb_stick()
        if usb:
            path = Path(usb) / "BILDER"
            path.mkdir(exist_ok=True)
            return path
        return None
    
    def copy_to_usb(self, source: Path, subfolder: str = "") -> bool:
        """Kopiert eine Datei auf den USB-Stick"""
        usb_path = self.get_images_path()
        if not usb_path:
            return False
        
        try:
            dest_folder = usb_path / subfolder if subfolder else usb_path
            dest_folder.mkdir(exist_ok=True)
            
            dest = dest_folder / source.name
            shutil.copy2(source, dest)
            logger.info(f"Kopiert auf USB: {dest}")
            return True
        except Exception as e:
            logger.error(f"USB-Kopie fehlgeschlagen: {e}")
            return False
