"""USB-Stick Management - Verbesserte Erkennung"""

import os
import shutil
import time
from pathlib import Path
from typing import Optional

from src.utils.logging import get_logger

logger = get_logger(__name__)


class USBManager:
    """Verwaltet USB-Stick Operationen mit verbesserter Erkennung"""
    
    # Verschiedene Label-Varianten (Case-insensitive)
    USB_LABELS = ["fexobox", "FEXOBOX", "Fexobox", "FexoBox"]
    
    def __init__(self):
        self._last_check_time: float = 0
        self._cached_drive: Optional[str] = None
        self._check_interval: float = 2.0
    
    def find_usb_stick(self) -> Optional[str]:
        """Sucht USB-Stick mit Label 'fexobox' (Case-insensitive)"""
        current_time = time.time()
        
        # Cache nutzen (ohne Logging!)
        if current_time - self._last_check_time < self._check_interval:
            return self._cached_drive
        
        self._last_check_time = current_time
        previous_drive = self._cached_drive
        self._cached_drive = None
        
        # Nur Windows
        if os.name != "nt":
            return None
        
        try:
            import ctypes
            
            for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
                drive = f"{letter}:\\"
                
                # Prüfen ob Laufwerk existiert
                if not os.path.exists(drive):
                    continue
                
                # Laufwerkstyp prüfen (2 = Removable)
                try:
                    drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
                    # 2 = DRIVE_REMOVABLE, 3 = DRIVE_FIXED (für Tests)
                    if drive_type not in [2, 3]:
                        continue
                except:
                    pass
                
                # Volume-Label holen
                try:
                    volume_name = ctypes.create_unicode_buffer(261)
                    result = ctypes.windll.kernel32.GetVolumeInformationW(
                        drive, volume_name, 261,
                        None, None, None, None, 0
                    )
                    
                    if result:
                        label = volume_name.value
                        # Case-insensitive Vergleich
                        if label.lower() == "fexobox":
                            self._cached_drive = drive
                            # Nur loggen wenn NEU gefunden (nicht bei jedem Check)
                            if previous_drive != drive:
                                logger.info(f"USB-Stick gefunden: {drive} (Label: {label})")
                            return drive
                except Exception as e:
                    logger.debug(f"Volume-Info Fehler für {drive}: {e}")
                    
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
            try:
                path.mkdir(exist_ok=True)
                (path / "Single").mkdir(exist_ok=True)
                (path / "Prints").mkdir(exist_ok=True)
                return path
            except Exception as e:
                logger.error(f"Konnte USB-Ordner nicht erstellen: {e}")
        return None
    
    def copy_to_usb(self, source: Path, subfolder: str = "") -> bool:
        """Kopiert eine Datei auf den USB-Stick"""
        usb_path = self.get_images_path()
        if not usb_path:
            logger.debug("USB nicht verfügbar für Kopie")
            return False
        
        try:
            dest_folder = usb_path / subfolder if subfolder else usb_path
            dest_folder.mkdir(exist_ok=True)
            
            dest = dest_folder / source.name
            shutil.copy2(source, dest)
            logger.info(f"USB-Kopie: {dest}")
            return True
        except Exception as e:
            logger.error(f"USB-Kopie fehlgeschlagen: {e}")
            return False
    
    def get_status_text(self) -> tuple:
        """Gibt Status-Text und Farbe zurück für UI"""
        if self.is_available():
            drive = self._cached_drive or "?"
            return (f"✓ USB ({drive[0]}:)", "success")
        else:
            return ("⚠️ KEIN USB-STICK!", "warning")
