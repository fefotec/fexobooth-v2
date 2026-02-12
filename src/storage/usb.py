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
        # FEXOSAFE Sicherungs-Stick
        self._cached_fexosafe_drive: Optional[str] = None
        self._last_fexosafe_check_time: float = 0
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

    def find_fexosafe_stick(self) -> Optional[str]:
        """Sucht FEXOSAFE Sicherungs-USB-Stick (Label 'FEXOSAFE', Case-insensitive)"""
        current_time = time.time()

        # Cache nutzen
        if current_time - self._last_fexosafe_check_time < self._check_interval:
            return self._cached_fexosafe_drive

        self._last_fexosafe_check_time = current_time
        previous_drive = self._cached_fexosafe_drive
        self._cached_fexosafe_drive = None

        if os.name != "nt":
            return None

        try:
            import ctypes

            for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
                drive = f"{letter}:\\"

                if not os.path.exists(drive):
                    continue

                try:
                    drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
                    if drive_type not in [2, 3]:
                        continue
                except:
                    pass

                try:
                    volume_name = ctypes.create_unicode_buffer(261)
                    result = ctypes.windll.kernel32.GetVolumeInformationW(
                        drive, volume_name, 261,
                        None, None, None, None, 0
                    )

                    if result:
                        label = volume_name.value
                        if label.lower() == "fexosafe":
                            self._cached_fexosafe_drive = drive
                            if previous_drive != drive:
                                logger.info(f"FEXOSAFE-Stick gefunden: {drive}")
                            return drive
                except Exception as e:
                    logger.debug(f"Volume-Info Fehler für {drive}: {e}")

        except Exception as e:
            logger.error(f"FEXOSAFE-Suche fehlgeschlagen: {e}")

        return None

    def find_unknown_stick(self) -> Optional[str]:
        """Sucht einen Wechseldatenträger der weder 'fexobox' noch 'FEXOSAFE' ist.

        Für Notfall-Export wenn der Kunden-Stick kaputt geht und ein
        eigener USB-Stick eingesteckt wird.
        """
        if os.name != "nt":
            return None

        try:
            import ctypes

            known_labels = {"fexobox", "fexosafe"}

            for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
                drive = f"{letter}:\\"

                if not os.path.exists(drive):
                    continue

                try:
                    drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
                    if drive_type != 2:  # Nur DRIVE_REMOVABLE
                        continue
                except:
                    continue

                try:
                    volume_name = ctypes.create_unicode_buffer(261)
                    result = ctypes.windll.kernel32.GetVolumeInformationW(
                        drive, volume_name, 261,
                        None, None, None, None, 0
                    )

                    if result:
                        label = volume_name.value.lower()
                        if label not in known_labels:
                            return drive
                except Exception:
                    # Stick ohne Label → auch unbekannt
                    return drive

        except Exception as e:
            logger.error(f"Unbekannter-Stick-Suche fehlgeschlagen: {e}")

        return None

    def export_to_stick(self, target_drive: str, local_base_path: Path,
                        progress_callback=None, cancel_event=None) -> Dict[str, int]:
        """Exportiert alle lokalen Bilder auf einen beliebigen USB-Stick.

        Args:
            target_drive: Laufwerk z.B. "E:\\"
            local_base_path: Lokaler BILDER-Pfad
            progress_callback: Callback(copied, total) für Fortschritt
            cancel_event: threading.Event zum Abbrechen

        Returns:
            {"copied": int, "errors": int, "cancelled": bool}
        """
        result = {"copied": 0, "errors": 0, "cancelled": False}
        target_base = Path(target_drive) / "BILDER"

        # Alle lokalen Dateien sammeln
        files = []
        for subfolder in ["Single", "Prints"]:
            local_folder = local_base_path / subfolder
            if local_folder.exists():
                for f in local_folder.glob("*.jpg"):
                    files.append((f, subfolder))

        if not files:
            return result

        for i, (source, subfolder) in enumerate(files):
            if cancel_event and cancel_event.is_set():
                result["cancelled"] = True
                break

            try:
                dest_folder = target_base / subfolder
                dest_folder.mkdir(parents=True, exist_ok=True)
                dest = dest_folder / source.name
                if not dest.exists():
                    shutil.copy2(source, dest)
                    result["copied"] += 1
                    logger.debug(f"Export: {source.name} → {dest}")
            except Exception as e:
                result["errors"] += 1
                logger.error(f"Export fehlgeschlagen: {source.name}: {e}")

            if progress_callback:
                progress_callback(i + 1, len(files))

        logger.info(f"Export abgeschlossen: {result}")
        return result

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

    def check_and_sync(self, local_base_path: Optional[Path] = None) -> int:
        """Prüft ob USB wieder verfügbar und synchronisiert automatisch.

        Bei USB-Wiedereinstecken wird eine vollständige Synchronisation
        aller fehlenden Bilder durchgeführt.

        Args:
            local_base_path: Basis-Pfad für lokale Bilder (optional).
                             Wenn nicht angegeben, wird nur Pending-Sync durchgeführt.

        Returns:
            Anzahl der synchronisierten Dateien (0 wenn keine Änderung)
        """
        is_available = self.is_available()

        # USB wurde gerade eingesteckt
        if is_available and not self._was_available:
            self._was_available = True
            logger.info("USB wieder verfügbar - starte Auto-Sync...")

            # Vollständige Synchronisation wenn local_base_path angegeben
            if local_base_path and local_base_path.exists():
                result = self.sync_all_missing(local_base_path)
                return result["copied"]
            elif self._pending_files:
                # Fallback: Nur Pending-Sync
                return self.sync_pending()
        elif not is_available:
            self._was_available = False

        return 0

    def get_pending_count(self) -> int:
        """Gibt die Anzahl der ausstehenden Dateien zurück"""
        return len(self._pending_files)

    def count_missing(self, local_base_path: Path) -> int:
        """Zählt fehlende Bilder auf dem USB-Stick (schneller Check ohne Kopieren)."""
        if not self.is_available():
            return 0

        usb_path = self.get_images_path()
        if not usb_path:
            return 0

        count = 0
        for subfolder in ["Single", "Prints"]:
            local_folder = local_base_path / subfolder
            usb_folder = usb_path / subfolder
            if not local_folder.exists():
                continue
            local_files = set(f.name for f in local_folder.glob("*.jpg"))
            usb_files = set(f.name for f in usb_folder.glob("*.jpg")) if usb_folder.exists() else set()
            count += len(local_files - usb_files)
        return count

    def sync_all_missing(self, local_base_path: Path, progress_callback=None, cancel_event=None) -> Dict[str, int]:
        """Synchronisiert ALLE fehlenden lokalen Bilder auf den USB-Stick.

        Args:
            local_base_path: Basis-Pfad für lokale Bilder (z.B. BILDER/)
            progress_callback: Optional callback(copied, total, filename) für Fortschritt
            cancel_event: Optional threading.Event - wenn gesetzt, wird abgebrochen

        Returns:
            Dict mit {"copied": n, "skipped": n, "errors": n, "cancelled": bool}
        """
        result = {"copied": 0, "skipped": 0, "errors": 0, "cancelled": False}

        if not self.is_available():
            logger.warning("sync_all_missing: USB nicht verfügbar")
            return result

        usb_path = self.get_images_path()
        if not usb_path:
            return result

        logger.info(f"=== Vollständige USB-Synchronisation gestartet ===")
        logger.info(f"Lokal: {local_base_path}")
        logger.info(f"USB:   {usb_path}")

        # Erst alle fehlenden Dateien sammeln
        missing_files = []  # (source, dest) Tupel
        for subfolder in ["Single", "Prints"]:
            local_folder = local_base_path / subfolder
            usb_folder = usb_path / subfolder

            if not local_folder.exists():
                continue

            usb_folder.mkdir(exist_ok=True)
            local_files = set(f.name for f in local_folder.glob("*.jpg"))
            usb_files = set(f.name for f in usb_folder.glob("*.jpg"))
            missing = local_files - usb_files
            result["skipped"] += len(local_files) - len(missing)

            for filename in missing:
                missing_files.append((local_folder / filename, usb_folder / filename))

        total = len(missing_files)
        if total > 0:
            logger.info(f"{total} fehlende Dateien gefunden")

        for i, (source, dest) in enumerate(missing_files):
            # Abbruch prüfen
            if cancel_event and cancel_event.is_set():
                result["cancelled"] = True
                logger.info(f"USB-Sync abgebrochen nach {result['copied']}/{total}")
                break

            try:
                shutil.copy2(source, dest)
                result["copied"] += 1
            except Exception as e:
                logger.warning(f"Kopie fehlgeschlagen: {source.name} - {e}")
                result["errors"] += 1

            # Fortschritt melden
            if progress_callback:
                progress_callback(result["copied"], total, source.name)

        # Pending-Liste leeren wenn alles synchronisiert (nicht bei Abbruch)
        if not result["cancelled"] and (result["copied"] > 0 or result["errors"] == 0):
            self._pending_files = []
            self._save_pending_files()

        logger.info(f"=== USB-Sync abgeschlossen: {result['copied']} kopiert, {result['skipped']} übersprungen, {result['errors']} Fehler ===")
        return result
