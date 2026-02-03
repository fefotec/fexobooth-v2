"""Booking Settings Management - Lädt settings.json vom USB-Stick"""

import json
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

from src.utils.logging import get_logger

logger = get_logger(__name__)


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


class BookingManager:
    """Verwaltet Buchungseinstellungen vom USB-Stick"""
    
    def __init__(self):
        self._settings: Optional[BookingSettings] = None
        self._settings_path: Optional[Path] = None
        self._last_check_path: Optional[Path] = None
    
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
    
    def load_from_usb(self, usb_root: Path) -> bool:
        """Lädt settings.json vom USB-Stick
        
        Args:
            usb_root: Wurzelverzeichnis des USB-Sticks (z.B. E:\\)
            
        Returns:
            True wenn erfolgreich geladen
        """
        settings_path = usb_root / "settings.json"
        
        # Schon geladen und unverändert?
        if settings_path == self._last_check_path and self._settings:
            return True
        
        if not settings_path.exists():
            logger.debug(f"Keine settings.json gefunden: {settings_path}")
            return False
        
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._settings = BookingSettings.from_dict(data)
            self._settings_path = settings_path
            self._last_check_path = settings_path
            
            logger.info(f"✅ Buchung geladen: {self._settings.booking_id}")
            logger.info(f"   Kunde: {self._settings.customer_name}")
            logger.info(f"   Einzeldruck: {'Ja' if self._settings.print_singles else 'Nein'}")
            logger.info(f"   Template: {self._settings.template_type}")
            
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"settings.json ungültiges JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"Fehler beim Laden von settings.json: {e}")
            return False
    
    def clear(self):
        """Setzt Buchungsdaten zurück"""
        self._settings = None
        self._settings_path = None
        logger.info("Buchungsdaten zurückgesetzt")
    
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
