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
    online_gallery: bool = False  # Galerie-Feature aktiv
    dslr_camera: bool = False  # DSLR statt Webcam
    
    # Kundeninfo
    customer_name: str = ""
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
            online_gallery=features.get("online_gallery", False),
            dslr_camera=features.get("dslr_camera", False),
            customer_name=customer.get("name", ""),
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
                "online_gallery": self.online_gallery,
                "dslr_camera": self.dslr_camera,
            },
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
    
    def check_usb_for_new_booking(self, usb_root: Path) -> Optional[str]:
        """Prüft ob USB eine ANDERE Buchung enthält
        
        Returns:
            Neue booking_id wenn unterschiedlich, None wenn gleich oder keine settings.json
        """
        settings_path = usb_root / "settings.json"
        
        if not settings_path.exists():
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
        """Lädt settings.json vom USB-Stick
        
        Args:
            usb_root: Wurzelverzeichnis des USB-Sticks (z.B. E:\\)
            force: Erzwingt Laden auch wenn gleiche booking_id
            
        Returns:
            True wenn erfolgreich geladen
        """
        settings_path = usb_root / "settings.json"
        
        if not settings_path.exists():
            logger.debug(f"Keine settings.json gefunden: {settings_path}")
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
            
            logger.info(f"✅ Buchung geladen: {self._settings.booking_id}")
            logger.info(f"   Kunde: {self._settings.customer_name}")
            logger.info(f"   Einzeldruck: {'Ja' if self._settings.print_singles else 'Nein'}")
            logger.info(f"   Template: {self._settings.template_type}")
            
            # In Cache speichern
            self._save_to_cache()
            
            # Template cachen falls vorhanden
            self._cache_template_from_usb(usb_root)
            
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"settings.json ungültiges JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"Fehler beim Laden von settings.json: {e}")
            return False
    
    def _cache_template_from_usb(self, usb_root: Path):
        """Sucht und cached Template-ZIP vom USB"""
        # Mögliche Template-Pfade
        template_paths = [
            usb_root / "template.zip",
            usb_root / "Template.zip",
            usb_root / "TEMPLATE.zip",
        ]
        
        for path in template_paths:
            if path.exists():
                self._cache_template(path)
                return
        
        logger.debug("Kein Template-ZIP auf USB gefunden")
    
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
