"""Booking Settings Management - Lädt settings.json vom USB-Stick

Persistenz-Strategie:
- Buchungsdaten werden lokal gecached (last_booking.json)
- Template-ZIP wird lokal kopiert (cached_template.zip)
- Wechsel nur bei ANDERER booking_id oder manuellem Reset

Sicherheit (ab v2.4.0):
- settings.json kann mit HMAC-SHA256 signiert sein (Feld _signature)
- Soft-Mode: unsignierte JSONs werden mit Warning akzeptiert (Migration)
- Strict-Mode (geplant v2.5.0): nur signierte JSONs werden akzeptiert
- Manipulationsversuche (Signatur falsch) werden IMMER abgelehnt, auch im Soft-Mode
"""

import hashlib
import hmac
import json
import shutil
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict

from src.utils.logging import get_logger
from src.i18n import apply_locale_to_config, normalize_locale

logger = get_logger(__name__)

# Cache-Dateien im Projektverzeichnis
CACHE_DIR = Path(__file__).parent.parent.parent / ".booking_cache"
BOOKING_CACHE_FILE = CACHE_DIR / "last_booking.json"
TEMPLATE_CACHE_FILE = CACHE_DIR / "cached_template.zip"
# Marker fuer "per App-Upload empfangene Settings/Template noch uebernehmen".
# Wird vom Galerie-Server-Thread geschrieben und vom Main-Thread (UI) abgearbeitet.
UPLOAD_APPLY_MARKER = CACHE_DIR / ".apply_pending.json"
# Merkt, ob der aktuelle Cache zuletzt per App oder USB geschrieben wurde.
# Wichtig beim Neustart mit eingestecktem altem USB-Stick: App-Korrekturen
# duerfen nicht direkt wieder vom Stick ueberschrieben werden.
APP_UPLOAD_META_FILE = CACHE_DIR / ".app_upload_meta.json"

# HMAC-Geheimnis für settings.json-Signatur. Muss identisch im Laravel-Backend
# als ENV SETTINGS_HMAC_SECRET gesetzt sein, damit signierte JSONs akzeptiert werden.
# Bei Build-Zeit-Override via PyInstaller in eine .env oder direkte Patch-Konstante
# auslagern, sobald Laravel signiert.
_HMAC_SECRET = b"fexobox-settings-hmac-2026-CHANGE-ME-IN-PROD"
_SIGNATURE_PREFIX = "hmac_sha256:"
# Soft-Mode: True = unsignierte JSONs werden akzeptiert (Übergangsphase v2.4.x).
# False = Strict-Mode, alle JSONs müssen signiert sein (v2.5.0+).
_HMAC_SOFT_MODE = True


def _normalize_six_digit_code(value: Any) -> str:
    """Return a six digit event code, or an empty string if the value is unusable."""
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits if len(digits) == 6 else ""


def _verify_signature(data: Dict[str, Any], log_unsigned: bool = True) -> Tuple[bool, str]:
    """Validiert die _signature der settings.json.

    Returns:
        (valid, reason):
        - (True, "unsigned"): keine Signatur, Soft-Mode akzeptiert
        - (True, "signed_valid"): Signatur korrekt
        - (False, "unsigned_strict"): keine Signatur, Strict-Mode lehnt ab
        - (False, "signed_invalid"): Signatur vorhanden aber falsch (Manipulation)
    """
    payload = dict(data)  # Kopie, damit das Original nicht modifiziert wird
    sig = payload.pop("_signature", None)

    if sig is None:
        if _HMAC_SOFT_MODE:
            if log_unsigned:
                logger.warning(
                    "⚠️  settings.json ohne Signatur — Soft-Mode akzeptiert "
                    "(in v2.5.0 wird das abgelehnt)"
                )
            return (True, "unsigned")
        return (False, "unsigned_strict")

    if not isinstance(sig, str) or not sig.startswith(_SIGNATURE_PREFIX):
        logger.error(f"settings.json _signature hat ungültiges Format: {sig!r:.40}")
        return (False, "signed_invalid")

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = hmac.new(
        _HMAC_SECRET, canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    expected_full = f"{_SIGNATURE_PREFIX}{expected}"

    if hmac.compare_digest(sig, expected_full):
        logger.info("✅ settings.json Signatur gültig")
        return (True, "signed_valid")

    logger.error(
        "🛑 settings.json Signatur UNGÜLTIG — JSON wurde manipuliert oder "
        "Geheimnis stimmt nicht überein. JSON wird ignoriert."
    )
    return (False, "signed_invalid")


@dataclass
class BookingSettings:
    """Einstellungen aus settings.json"""
    
    # Buchungsidentifikation
    booking_id: str = ""
    source: str = "de"
    locale: Optional[str] = None
    
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
    event_pin: str = ""  # 6-stelliger App/Event-Code, falls vom Dashboard geliefert
    
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
        event = data.get("event", {})
        gallery = data.get("gallery", {})
        extensions = data.get("extensions", {})
        
        raw_locale = data.get("locale", data.get("language"))
        event_pin = _normalize_six_digit_code(
            data.get("event_pin")
            or data.get("event_code")
            or data.get("pin")
            or event.get("event_pin")
            or event.get("pin")
            or event.get("code")
            or gallery.get("event_pin")
            or gallery.get("event_code")
            or gallery.get("pin")
            or extensions.get("event_pin")
            or extensions.get("event_code")
            or extensions.get("pin")
        )

        return cls(
            booking_id=data.get("booking_id", ""),
            source=data.get("source", "de"),
            locale=normalize_locale(raw_locale) if raw_locale else None,
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
            event_pin=event_pin,
            version=data.get("_version", ""),
            generated_at=data.get("_generated_at", ""),
            extensions=extensions
        )
    
    def is_loaded(self) -> bool:
        """Prüft ob gültige Buchungsdaten geladen sind"""
        return bool(self.booking_id)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für JSON-Speicherung"""
        result = {
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
        if self.event_pin:
            result["event_pin"] = self.event_pin
        if self.locale:
            result["locale"] = self.locale
        return result


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
            # Alle JSON-Dateien im Root finden.
            # WICHTIG: macOS legt auf FAT/exFAT-Sticks versteckte "._"-Begleit-
            # dateien an (AppleDouble, binär). Die MÜSSEN gefiltert werden – sonst
            # wirft das Einlesen einen UnicodeDecodeError, der früher die KOMPLETTE
            # Suche abbrach ("keine gültige settings.json", obwohl die echte da ist).
            json_files = [p for p in usb_root.glob("*.json") if not p.name.startswith("._")]

            if not json_files:
                return None

            # Gültige Settings-Dateien filtern (müssen booking_id enthalten)
            # KEIN Logging hier - wird sehr oft aufgerufen!
            valid_files = []
            for json_path in json_files:
                try:
                    # utf-8-sig: toleriert ein evtl. vorhandenes BOM (Windows-Editoren)
                    with open(json_path, "r", encoding="utf-8-sig") as f:
                        data = json.load(f)

                    # Prüfen ob es eine gültige Settings-Datei ist
                    # Muss mindestens booking_id ODER customer_name enthalten
                    if not (data.get("booking_id") or data.get("customer_name")):
                        continue

                    # Signatur prüfen — manipulierte/falsch signierte JSONs überspringen.
                    # Soft-Mode lässt unsignierte durch, hartes Reject nur bei
                    # falscher Signatur (echter Manipulationsversuch).
                    sig_valid, _ = _verify_signature(data, log_unsigned=False)
                    if not sig_valid:
                        continue

                    mtime = json_path.stat().st_mtime
                    valid_files.append((json_path, mtime))
                except Exception:
                    # EINE kaputte/fremde Datei darf die Suche NIE abbrechen
                    # (macOS "._"-Reste, Binärdateien, BOM, defektes JSON, …).
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
            with open(settings_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            # Signatur prüfen — manipulierte JSONs nicht als "neue Buchung" melden
            valid, reason = _verify_signature(data, log_unsigned=False)
            if not valid:
                logger.error(
                    f"❌ check_usb: {settings_path.name} abgelehnt ({reason})"
                )
                return None

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
            with open(settings_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            # Signatur prüfen (Soft-Mode: unsigniert wird akzeptiert, Manipulation nicht)
            valid, reason = _verify_signature(data)
            if not valid:
                logger.error(
                    f"❌ settings.json {settings_path.name} abgelehnt: {reason}"
                )
                return False

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
            template_cached = self._cache_template_from_usb(usb_root)
            self._record_cache_source(
                source="usb",
                booking_id=new_booking_id,
                settings=True,
                template=template_cached,
            )
            
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
            # macOS "._"-Begleitdateien ausfiltern (sind keine echten ZIPs)
            zip_files = [p for p in usb_root.glob("*.zip") if not p.name.startswith("._")]
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
        
        if self._settings.locale:
            config["locale"] = normalize_locale(self._settings.locale)
        else:
            config["locale"] = normalize_locale(config.get("locale", "de-DE"))
        apply_locale_to_config(config)
        logger.info(f"   📋 locale = {config['locale']}")

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

    def should_skip_usb_autoload_after_app_upload(self, usb_root: Path) -> bool:
        """Verhindert, dass ein alter USB-Stick eine App-Korrektur beim Neustart ueberschreibt.

        Gilt nur fuer die gleiche Buchung. Enthält der Stick eine andere booking_id,
        bleibt der normale Event-Wechsel/Aktualisierungsweg aktiv.
        """
        meta = self._load_cache_source()
        if meta.get("source") != "app":
            return False

        settings_path = self._find_settings_file(usb_root)
        if not settings_path:
            return False

        try:
            with open(settings_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            valid, reason = _verify_signature(data, log_unsigned=False)
            if not valid:
                logger.error(f"❌ USB-Autoload-Schutz: {settings_path.name} abgelehnt ({reason})")
                return False

            usb_booking_id = data.get("booking_id", "")
        except Exception as e:
            logger.debug(f"USB-Autoload-Schutz konnte Settings nicht lesen: {e}")
            return False

        current_booking_id = self.booking_id
        app_booking_id = str(meta.get("booking_id", "") or current_booking_id or "")
        if usb_booking_id and app_booking_id and usb_booking_id != app_booking_id:
            return False
        if usb_booking_id and current_booking_id and usb_booking_id != current_booking_id:
            return False

        logger.info(
            "📲 USB-Autoload übersprungen: App-Korrektur im Cache hat Vorrang "
            f"(booking_id={app_booking_id or usb_booking_id or '-'})"
        )
        return True

    # ------------------------------------------------------------------
    # App-Upload (settings.json / Template-ZIP ueber das Box-WLAN)
    # ------------------------------------------------------------------
    # Diese Methoden werden vom Galerie-Server-Thread aufgerufen. Sie mutieren
    # NICHT self._settings (das macht der Main-Thread via reload_from_cache),
    # sondern schreiben nur atomar in den Cache. So bleibt die Box-State im
    # Besitz des UI-Threads und es gibt keine Thread-Races.

    def ingest_uploaded_settings(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """Validiert eine per App hochgeladene settings.json und legt sie in den Cache.

        Gleiche Sicherheitsregeln wie beim USB-Import (HMAC-Signatur, Soft-Mode).

        Returns:
            (True, booking_id) bei Erfolg, sonst (False, Fehlergrund)
        """
        valid, reason = _verify_signature(data)
        if not valid:
            return False, reason

        if not (data.get("booking_id") or data.get("customer_name")):
            return False, "settings.json enthaelt weder booking_id noch customer_name"

        # Muss als BookingSettings parsebar sein, sonst lehnen wir ab.
        try:
            BookingSettings.from_dict(data)
        except Exception as e:  # pragma: no cover - defensiv
            return False, f"settings.json nicht verwertbar: {e}"

        try:
            CACHE_DIR.mkdir(exist_ok=True)
            tmp = BOOKING_CACHE_FILE.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp.replace(BOOKING_CACHE_FILE)
        except Exception as e:
            return False, f"Cache-Schreiben fehlgeschlagen: {e}"

        booking_id = data.get("booking_id", "") or ""
        self._record_cache_source(source="app", booking_id=booking_id, settings=True)
        logger.info(f"📲 Settings per App empfangen und gecached: {booking_id or '(ohne booking_id)'}")
        return True, booking_id

    def ingest_uploaded_template(self, src_path: Path) -> Tuple[bool, str]:
        """Validiert eine per App hochgeladene Template-ZIP und legt sie in den Cache.

        Nutzt dieselbe Validierung wie der USB-Import (_is_valid_template_zip):
        muss gueltige Bilder enthalten und darf keine Programmdateien (.exe/.dll)
        enthalten -> schuetzt davor, dass ueber "Template" Code eingeschleust wird.

        Returns:
            (True, "") bei Erfolg, sonst (False, Fehlergrund)
        """
        try:
            if not src_path.exists() or src_path.stat().st_size == 0:
                return False, "Leere oder fehlende Template-Datei"
            from src.config.config import _is_valid_template_zip
            if not _is_valid_template_zip(str(src_path)):
                return False, "Ungueltige Template-ZIP (keine gueltigen Bilder oder enthaelt Programmdateien)"
            CACHE_DIR.mkdir(exist_ok=True)
            tmp = TEMPLATE_CACHE_FILE.with_suffix(".tmp")
            shutil.copy2(src_path, tmp)
            tmp.replace(TEMPLATE_CACHE_FILE)
        except Exception as e:
            return False, f"Template-Cache fehlgeschlagen: {e}"

        self._record_cache_source(
            source="app",
            booking_id=self.booking_id,
            template=True,
            template_fingerprint=self.cached_template_fingerprint(),
        )
        logger.info("📲 Template per App empfangen und gecached")
        return True, ""

    def _load_cache_source(self) -> Dict[str, Any]:
        try:
            if APP_UPLOAD_META_FILE.exists():
                data = json.loads(APP_UPLOAD_META_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def _record_cache_source(
        self,
        source: str,
        booking_id: str = "",
        settings: bool = False,
        template: bool = False,
        template_fingerprint: str = "",
    ) -> None:
        try:
            existing = self._load_cache_source() if source == "app" else {}
            if booking_id:
                existing["booking_id"] = booking_id
            elif self.booking_id and "booking_id" not in existing:
                existing["booking_id"] = self.booking_id
            existing["source"] = source
            existing["updated_at"] = time.time()
            existing["settings"] = bool(existing.get("settings")) or settings
            existing["template"] = bool(existing.get("template")) or template
            if template_fingerprint:
                existing["template_fingerprint"] = template_fingerprint

            CACHE_DIR.mkdir(exist_ok=True)
            tmp = APP_UPLOAD_META_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(APP_UPLOAD_META_FILE)
        except Exception as e:
            logger.warning(f"Cache-Quelle konnte nicht gespeichert werden: {e}")

    def reload_from_cache(self) -> bool:
        """Laedt die (ggf. neu hochgeladene) Buchung aus dem Cache in den Speicher.

        Vom Main-Thread aufzurufen, nachdem ein App-Upload eingegangen ist.
        """
        return self._load_from_cache()

    def cached_template_fingerprint(self) -> str:
        """Fingerprint der gecachten Template-ZIP zur Verifikation durch die App."""
        try:
            if TEMPLATE_CACHE_FILE.exists():
                st = TEMPLATE_CACHE_FILE.stat()
                digest = hashlib.md5()
                with open(TEMPLATE_CACHE_FILE, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        digest.update(chunk)
                return f"{digest.hexdigest()}-{st.st_size}"
        except Exception:
            pass
        return ""

    def request_apply(self, settings: bool = False, template: bool = False) -> None:
        """Setzt/erweitert den Apply-Marker (vom Server-Thread aufgerufen)."""
        try:
            existing: Dict[str, Any] = {}
            if UPLOAD_APPLY_MARKER.exists():
                try:
                    existing = json.loads(UPLOAD_APPLY_MARKER.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}
            existing["settings"] = bool(existing.get("settings")) or settings
            existing["template"] = bool(existing.get("template")) or template
            CACHE_DIR.mkdir(exist_ok=True)
            tmp = UPLOAD_APPLY_MARKER.with_suffix(".tmp")
            tmp.write_text(json.dumps(existing), encoding="utf-8")
            tmp.replace(UPLOAD_APPLY_MARKER)
        except Exception as e:
            logger.warning(f"Apply-Marker schreiben fehlgeschlagen: {e}")

    def peek_apply_request(self) -> Optional[Dict[str, Any]]:
        """Liest den Apply-Marker (ohne ihn zu loeschen). Main-Thread."""
        try:
            if UPLOAD_APPLY_MARKER.exists():
                return json.loads(UPLOAD_APPLY_MARKER.read_text(encoding="utf-8"))
        except Exception:
            pass
        return None

    def clear_apply_request(self) -> None:
        """Loescht den Apply-Marker nach erfolgreicher Uebernahme. Main-Thread."""
        try:
            if UPLOAD_APPLY_MARKER.exists():
                UPLOAD_APPLY_MARKER.unlink()
        except Exception:
            pass


# Singleton-Instanz
_booking_manager: Optional[BookingManager] = None

def get_booking_manager() -> BookingManager:
    """Gibt die BookingManager-Instanz zurück (Singleton)"""
    global _booking_manager
    if _booking_manager is None:
        _booking_manager = BookingManager()
    return _booking_manager
