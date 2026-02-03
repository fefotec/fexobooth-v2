"""USB-Stick Management - Verbesserte Erkennung mit Auto-Sync"""

import os
import shutil
import time
import json
from pathlib import Path
from typing import Optional, List, Dict

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Pfad für Pending-Sync Liste (im Projekt-Root)
PENDING_SYNC_FILE = Path(__file__).parent.parent.parent / ".pending_usb_sync.json"


class USBManager:
    """Verwaltet USB-Stick Operationen mit verbesserter Erkennung"""
    
    # Verschiedene Label-Varianten (Case-insensitive)
    USB_LABELS = ["fexobox", "FEXOBOX", "Fexobox", "FexoBox"]
    
    def __init__(self):
        self._last_check_time: float = 0
        self._cached_drive: Optional[str] = None
        self._check_interval: float = 2.0
        self._was_available: bool = False  # Für Erkennung wenn USB wieder da
        self._pending_files: List[Dict] = []  # In-Memory Cache
        self._load_pending_files()
    
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
    
    def copy_to_usb(self, source: Path, subfolder: str = "", add_to_pending_on_fail: bool = True) -> bool:
        """Kopiert eine Datei auf den USB-Stick.

        Bei Fehler wird die Datei automatisch zur Pending-Liste hinzugefügt
        (sofern add_to_pending_on_fail=True), damit sie später synchronisiert wird.
        """
        usb_path = self.get_images_path()
        if not usb_path:
            logger.debug("USB nicht verfügbar für Kopie")
            if add_to_pending_on_fail:
                self.add_to_pending(source, subfolder)
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
            if add_to_pending_on_fail:
                self.add_to_pending(source, subfolder)
            return False
    
    def get_status_text(self) -> tuple:
        """Gibt Status-Text und Farbe zurück für UI"""
        if self.is_available():
            drive = self._cached_drive or "?"
            pending_count = len(self._pending_files)
            if pending_count > 0:
                return (f"✓ USB ({drive[0]}:) [{pending_count}]", "success")
            return (f"✓ USB ({drive[0]}:)", "success")
        else:
            return ("⚠️ KEIN USB-STICK!", "warning")

    # ============= USB-Sync Feature =============

    def _load_pending_files(self):
        """Lädt die Liste der ausstehenden Dateien"""
        self._pending_files = []
        if PENDING_SYNC_FILE.exists():
            try:
                with open(PENDING_SYNC_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Nur existierende Dateien behalten
                    for item in data:
                        if Path(item.get("source", "")).exists():
                            self._pending_files.append(item)
                if self._pending_files:
                    logger.info(f"Pending-Sync geladen: {len(self._pending_files)} Dateien")
            except Exception as e:
                logger.warning(f"Pending-Sync Laden fehlgeschlagen: {e}")

    def _save_pending_files(self):
        """Speichert die Liste der ausstehenden Dateien"""
        try:
            with open(PENDING_SYNC_FILE, "w", encoding="utf-8") as f:
                json.dump(self._pending_files, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Pending-Sync Speichern fehlgeschlagen: {e}")

    def add_to_pending(self, source: Path, subfolder: str = ""):
        """Fügt eine Datei zur Pending-Sync Liste hinzu"""
        entry = {
            "source": str(source),
            "subfolder": subfolder,
            "added": time.time()
        }
        # Duplikate vermeiden
        for item in self._pending_files:
            if item["source"] == entry["source"]:
                return
        self._pending_files.append(entry)
        self._save_pending_files()
        logger.info(f"Pending-Sync: +{source.name} (Total: {len(self._pending_files)})")

    def sync_pending(self) -> int:
        """Synchronisiert alle ausstehenden Dateien auf USB.

        Returns:
            Anzahl der erfolgreich synchronisierten Dateien
        """
        if not self.is_available():
            return 0

        if not self._pending_files:
            return 0

        logger.info(f"=== USB-Sync: {len(self._pending_files)} Dateien ===")
        synced = 0
        still_pending = []

        for item in self._pending_files:
            source = Path(item["source"])
            subfolder = item.get("subfolder", "")

            if not source.exists():
                logger.warning(f"Sync: Quelldatei nicht mehr vorhanden: {source}")
                continue

            usb_path = self.get_images_path()
            if not usb_path:
                still_pending.append(item)
                continue

            try:
                dest_folder = usb_path / subfolder if subfolder else usb_path
                dest_folder.mkdir(exist_ok=True)
                dest = dest_folder / source.name

                # Nur kopieren wenn nicht bereits vorhanden
                if not dest.exists():
                    shutil.copy2(source, dest)
                    logger.info(f"Sync OK: {source.name} -> {dest}")
                else:
                    logger.debug(f"Sync: Bereits vorhanden: {dest}")
                synced += 1
            except Exception as e:
                logger.warning(f"Sync fehlgeschlagen: {source.name} - {e}")
                still_pending.append(item)

        self._pending_files = still_pending
        self._save_pending_files()

        if synced > 0:
            logger.info(f"USB-Sync abgeschlossen: {synced} Dateien kopiert, {len(still_pending)} ausstehend")

        return synced

    def check_and_sync(self) -> int:
        """Prüft ob USB wieder verfügbar und synchronisiert automatisch.

        Returns:
            Anzahl der synchronisierten Dateien (0 wenn keine Änderung)
        """
        is_available = self.is_available()

        # USB wurde gerade eingesteckt
        if is_available and not self._was_available:
            self._was_available = True
            if self._pending_files:
                logger.info("USB wieder verfügbar - starte Auto-Sync...")
                return self.sync_pending()
        elif not is_available:
            self._was_available = False

        return 0

    def get_pending_count(self) -> int:
        """Gibt die Anzahl der ausstehenden Dateien zurück"""
        return len(self._pending_files)
