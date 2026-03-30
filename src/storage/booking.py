"""Booking Settings Management - Lädt settings.json vom USB-Stick

Persistenz-Strategie:
- Buchungsdaten werden lokal gecached (last_booking.json)
- Template-ZIP wird lokal kopiert (cached_template.zip)
- Wechsel nur bei ANDERER booking_id oder manuellem Reset
"""

import json
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field, asdict

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Cache-Dateien im Projektverzeichnis
CACHE_DIR = Path(__file__).parent.parent.parent / ".booking_cache"
BOOKING_CACHE_FILE = CACHE_DIR / "last_booking.json"
TEMPLATE_CACHE_FILE = CACHE_DIR / "cached_template.zip"


@dataclass
class BookingSettings:
    """Einstellungen aus settings.json"""
    
    # Buchungsidentifikation
    booking_id: str = ""
    source: str = "de"
    
    # Template-Infos
    template_type: str = ""  # preset, designer, selfmade, none
    template_code: str = ""
    template_text: str = ""
    template_date: str = ""
    
    # Feature-Flags
    print_singles: bool = True  # Einzelbilder drucken erlaubt
    print_enabled: bool = True  # Druckfunktion aktiviert (False = "Ohne Druck")
    max_prints: int = 0  # Max. Ausdrucke pro Session (0 = Config-Default verwenden)
    live_gallery: bool = False  # Live-Galerie-Feature aktiv
    dslr_camera: bool = False  # DSLR statt Webcam

    # Kundeninfo
    customer_name: str = ""
    shipping_first_name: str = ""  # Vorname für persönliche Begrüßung
    event_date: str = ""
    
    # Metadaten
    version: str = ""
    generated_at: str = ""
    
    # Raw data für Erweiterungen
    extensions: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BookingSettings":
        """Erstellt BookingSettings aus Dictionary (settings.json)"""
        template = data.get("template", {})
        features = data.get("features", {})
        customer = data.get("customer", {})
        
        return cls(
            booking_id=data.get("booking_id", ""),
            source=data.get("source", "de"),
            template_type=template.get("type", ""),
            template_code=template.get("code", ""),
            template_text=template.get("text", ""),
            template_date=template.get("date", ""),
            print_singles=features.get("print_singles", True),
            print_enabled=features.get("print_enabled", True),
            max_prints=features.get("max_prints", 0),
            live_gallery=features.get("live_gallery", False),
            dslr_camera=features.get("dslr_camera", False),
            customer_name=customer.get("name", ""),
            shipping_first_name=data.get("shipping_first_name", "") or customer.get("first_name", ""),
            event_date=customer.get("event_date", ""),
            version=data.get("_version", ""),
            generated_at=data.get("_generated_at", ""),
            extensions=data.get("extensions", {})
        )
    
    def is_loaded(self) -> bool:
        """Prüft ob gültige Buchungsdaten geladen sind"""
        return bool(self.booking_id)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für JSON-Speicherung"""
        return {
            "booking_id": self.booking_id,
            "source": self.source,
            "template": {
                "type": self.template_type,
                "code": self.template_code,
                "text": self.template_text,
                "date": self.template_date,
            },
            "features": {
                "print_singles": self.print_singles,
                "print_enabled": self.print_enabled,
                "max_prints": self.max_prints,
                "live_gallery": self.live_gallery,
                "dslr_camera": self.dslr_camera,
            },
            "shipping_first_name": self.shipping_first_name,
            "customer": {
                "name": self.customer_name,
                "event_date": self.event_date,
            },
            "_version": self.version,
            "_generated_at": self.generated_at,
            "extensions": self.extensions,
        }


class BookingManager:
    """Verwaltet Buchungseinstellungen vom USB-Stick
    
    Persistenz:
    - Buchungsdaten werden lokal gecached
    - Template wird lokal kopiert
    - Wechsel nur bei anderer booking_id
    """
    
    def __init__(self):
        self._settings: Optional[BookingSettings] = None
        self._settings_path: Optional[Path] = None
        self._last_check_path: Optional[Path] = None
        self._template_source_path: Optional[Path] = None
        
        # Cache-Verzeichnis erstellen
        CACHE_DIR.mkdir(exist_ok=True)
        
        # Beim Start: Cache laden falls vorhanden
        self._load_from_cache()
    
    @property
    def settings(self) -> Optional[BookingSettings]:
        """Aktuelle Buchungseinstellungen"""
        return self._settings
    
    @property
    def booking_id(self) -> str:
        """Aktuelle Buchungs-ID oder leer"""
        return self._settings.booking_id if self._settings else ""
    
    @property
    def is_loaded(self) -> bool:
        """Prüft ob Buchungsdaten geladen sind"""
        return self._settings is not None and self._settings.is_loaded()
    
    @property
    def cached_template_path(self) -> Optional[Path]:
        """Gibt den Pfad zum gecachten Template zurück (falls vorhanden)"""
        if TEMPLATE_CACHE_FILE.exists():
            return TEMPLATE_CACHE_FILE
        return None
    
    def _load_from_cache(self) -> bool:
        """Lädt letzte Buchung aus lokalem Cache"""
        if not BOOKING_CACHE_FILE.exists():
            logger.debug("Kein Booking-Cache vorhanden")
            return False
        
        try:
            with open(BOOKING_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._settings = BookingSettings.from_dict(data)
            logger.info(f"📂 Buchung aus Cache geladen: {self._settings.booking_id}")
            
            if TEMPLATE_CACHE_FILE.exists():
                logger.info(f"   Template-Cache vorhanden: {TEMPLATE_CACHE_FILE.name}")
            
            return True
            
        except Exception as e:
            logger.warning(f"Cache-Laden fehlgeschlagen: {e}")
            return False
    
    def _save_to_cache(self):
        """Speichert aktuelle Buchung in lokalen Cache"""
        if not self._settings:
            return
        
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            with open(BOOKING_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._settings.to_dict(), f, indent=2, ensure_ascii=False)
            logger.debug(f"Buchung gecached: {self._settings.booking_id}")
        except Exception as e:
            logger.warning(f"Cache-Speichern fehlgeschlagen: {e}")
    
    def _cache_template(self, template_path: Path) -> bool:
        """Kopiert Template-ZIP in lokalen Cache"""
        if not template_path.exists():
            return False
        
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            shutil.copy2(template_path, TEMPLATE_CACHE_FILE)
            logger.info(f"📦 Template gecached: {template_path.name}")
            return True
        except Exception as e:
            logger.warning(f"Template-Cache fehlgeschlagen: {e}")
            return False
    
    def _find_settings_file(self, usb_root: Path) -> Optional[Path]:
        """Findet die beste Settings-Datei auf dem USB-Stick
        
        Logik:
        1. Sucht alle .json Dateien im Root des USB-Sticks
        2. Prüft ob sie gültige Booking-Daten enthalten (booking_id)
        3. Gibt die NEUESTE (zuletzt geändert) zurück
        
        Returns:
            Pfad zur besten Settings-Datei oder None
        """
        try:
            # Alle JSON-Dateien im Root finden
            json_files = list(usb_root.glob("*.json"))
            
            if not json_files:
                return None
            
            # Gültige Settings-Dateien filtern (müssen booking_id enthalten)
            # KEIN Logging hier - wird sehr oft aufgerufen!
            valid_files = []
            for json_path in json_files:
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # Prüfen ob es eine gültige Settings-Datei ist
                    # Muss mindestens booking_id ODER customer_name enthalten
                    if data.get("booking_id") or data.get("customer_name"):
                        mtime = json_path.stat().st_mtime
                        valid_files.append((json_path, mtime))
                except (json.JSONDecodeError, KeyError, IOError):
                    continue
            
            if not valid_files:
                return None
            
            # Nach Änderungszeit sortieren (neueste zuerst)
            valid_files.sort(key=lambda x: x[1], reverse=True)
            
            newest = valid_files[0][0]
            # Nur loggen wenn mehrere Dateien (interessant)
            if len(valid_files) > 1:
                logger.info(f"📂 {len(valid_files)} Settings-Dateien gefunden, verwende neueste: {newest.name}")
            
            return newest
            
        except Exception as e:
            logger.error(f"Fehler beim Suchen von Settings-Dateien: {e}")
            return None
    
    def check_usb_for_new_booking(self, usb_root: Path) -> Optional[str]:
        """Prüft ob USB eine ANDERE Buchung enthält
        
        Sucht nach allen gültigen .json Dateien und nimmt die neueste.
        
        Returns:
            Neue booking_id wenn unterschiedlich, None wenn gleich oder keine gefunden
        """
        settings_path = self._find_settings_file(usb_root)
        
        if not settings_path:
            return None
        
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            new_booking_id = data.get("booking_id", "")
            
            # Vergleich mit aktuellem
            if new_booking_id and new_booking_id != self.booking_id:
                logger.info(f"🔄 Neue Buchung erkannt: {new_booking_id} (vorher: {self.booking_id or 'keine'})")
                return new_booking_id
            
            return None
            
        except Exception as e:
            logger.debug(f"USB-Check Fehler: {e}")
            return None
    
    def load_from_usb(self, usb_root: Path, force: bool = False) -> bool:
        """Lädt Settings vom USB-Stick
        
        Sucht nach allen gültigen .json Dateien und nimmt die neueste.
        Der Dateiname muss NICHT "settings.json" sein!
        
        Args:
            usb_root: Wurzelverzeichnis des USB-Sticks (z.B. E:\\)
            force: Erzwingt Laden auch wenn gleiche booking_id
            
        Returns:
            True wenn erfolgreich geladen
        """
        settings_path = self._find_settings_file(usb_root)
        
        if not settings_path:
            logger.debug(f"Keine gültige Settings-Datei auf USB: {usb_root}")
            return False
        
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            new_booking_id = data.get("booking_id", "")
            
            # Prüfen ob wirklich neue Buchung (außer force=True)
            if not force and new_booking_id == self.booking_id and self._settings:
                logger.debug(f"Gleiche Buchung, überspringe: {new_booking_id}")
                return True
            
            self._settings = BookingSettings.from_dict(data)
            self._settings_path = settings_path
            self._last_check_path = settings_path
            
            logger.info(f"✅ Buchung geladen aus: {settings_path.name}")
            logger.info(f"   Booking-ID: {self._settings.booking_id}")
            logger.info(f"   Kunde: {self._settings.customer_name}")
            logger.info(f"   Einzeldruck: {'Ja' if self._settings.print_singles else 'Nein'}")
            logger.info(f"   Template: {self._settings.template_type}")
            
            # In Cache speichern
            self._save_to_cache()
            
            # Template cachen falls vorhanden
            self._cache_template_from_usb(usb_root)
            
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"{settings_path.name} ungültiges JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"Fehler beim Laden von {settings_path.name}: {e}")
            return False
    
    def _cache_template_from_usb(self, usb_root: Path) -> bool:
        """Sucht und cached Template-ZIP vom USB.

        Sucht nach JEDER gültigen Template-ZIP im Root des USB-Sticks,
        nicht nur nach 'template.zip'. Verwendet die gleiche Validierung
        wie find_usb_template() in config.py.
        """
        try:
            zip_files = list(usb_root.glob("*.zip"))
            if not zip_files:
                logger.debug("Keine ZIP-Dateien auf USB gefunden")
                return False

            from src.config.config import _is_valid_template_zip

            for zip_path in zip_files:
                if _is_valid_template_zip(str(zip_path)):
                    return self._cache_template(zip_path)

            logger.debug("Keine gültige Template-ZIP auf USB gefunden")
            return False

        except Exception as e:
            logger.warning(f"Template-Suche auf USB fehlgeschlagen: {e}")
            return False
    
    def get_template_path_for_config(self) -> Optional[str]:
        """Gibt den Pfad zum Template zurück (Cache oder USB)
        
        Für Einbindung in config["template_paths"]["template1"]
        """
        # Gecachtes Template bevorzugen
        if TEMPLATE_CACHE_FILE.exists():
            logger.debug(f"Verwende gecachtes Template: {TEMPLATE_CACHE_FILE}")
            return str(TEMPLATE_CACHE_FILE)
        
        return None
    
    def apply_cached_template_to_config(self, config: Dict[str, Any]) -> bool:
        """Trägt das gecachte Template in die Config ein
        
        Args:
            config: Die App-Config (wird in-place modifiziert)
            
        Returns:
            True wenn Template angewendet wurde
        """
        template_path = self.get_template_path_for_config()
        
        if not template_path:
            return False
        
        # Template-Pfade sicherstellen
        if "template_paths" not in config:
            config["template_paths"] = {}
        
        # Als template1 eintragen (USB-Templates haben Priorität)
        config["template_paths"]["usb_template"] = template_path
        
        # Aktivieren
        config["usb_template_enabled"] = True
        
        logger.info(f"📦 Gecachtes Template in Config eingetragen: {template_path}")
        return True
    
    def apply_settings_to_config(self, config: Dict[str, Any]) -> bool:
        """Wendet BookingSettings auf die App-Config an
        
        Mapping:
        - print_singles → allow_single_mode
        - live_gallery → gallery_enabled
        - dslr_camera → camera_type
        
        Args:
            config: Die App-Config (wird in-place modifiziert)
            
        Returns:
            True wenn Settings angewendet wurden
        """
        if not self._settings:
            return False
        
        # Single-Foto Modus
        config["allow_single_mode"] = self._settings.print_singles
        logger.info(f"   📋 allow_single_mode = {self._settings.print_singles}")
        
        # Galerie (Fallback: False wenn nicht gesetzt)
        config["gallery_enabled"] = self._settings.live_gallery
        logger.info(f"   📋 gallery_enabled = {self._settings.live_gallery}")
        
        # Kamera-Typ
        if self._settings.dslr_camera:
            config["camera_type"] = "canon"
            logger.info(f"   📋 camera_type = canon (DSLR)")
        
        # Druckfunktion
        config["print_enabled"] = self._settings.print_enabled
        logger.info(f"   📋 print_enabled = {self._settings.print_enabled}")

        # Max. Ausdrucke pro Session (0 = Config-Default beibehalten)
        if self._settings.max_prints > 0:
            config["max_prints_per_session"] = self._settings.max_prints
            logger.info(f"   📋 max_prints_per_session = {self._settings.max_prints}")

        logger.info(f"✅ BookingSettings auf Config angewendet")
        return True
    
    def clear(self, clear_cache: bool = False):
        """Setzt Buchungsdaten zurück
        
        Args:
            clear_cache: Wenn True, wird auch der lokale Cache gelöscht
        """
        self._settings = None
        self._settings_path = None
        self._last_check_path = None
        logger.info("Buchungsdaten zurückgesetzt")
        
        if clear_cache:
            try:
                if BOOKING_CACHE_FILE.exists():
                    BOOKING_CACHE_FILE.unlink()
                if TEMPLATE_CACHE_FILE.exists():
                    TEMPLATE_CACHE_FILE.unlink()
                logger.info("Cache gelöscht")
            except Exception as e:
                logger.warning(f"Cache löschen fehlgeschlagen: {e}")
    
    def get_display_info(self) -> Dict[str, str]:
        """Gibt Infos für UI-Anzeige zurück"""
        if not self._settings:
            return {
                "booking_id": "---",
                "customer": "",
                "event_date": "",
                "status": "Keine Buchung"
            }
        
        return {
            "booking_id": self._settings.booking_id,
            "customer": self._settings.customer_name,
            "event_date": self._settings.event_date,
            "status": "Geladen"
        }


# Singleton-Instanz
_booking_manager: Optional[BookingManager] = None

def get_booking_manager() -> BookingManager:
    """Gibt die BookingManager-Instanz zurück (Singleton)"""
    global _booking_manager
    if _booking_manager is None:
        _booking_manager = BookingManager()
    return _booking_manager
