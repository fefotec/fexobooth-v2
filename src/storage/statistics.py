"""Statistik-Modul für Event-Tracking

Erfasst pro Buchung:
- Buchungsnummer
- Start-/Endzeit
- Anzahl geschossene Bilder
- Anzahl tatsächlich gedruckte Bilder
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Statistik-Datei
STATS_FILENAME = "fexobooth_statistics.json"


@dataclass
class EventStats:
    """Statistik für ein einzelnes Event/Buchung"""
    
    booking_id: str = ""
    start_time: Optional[str] = None  # ISO Format
    end_time: Optional[str] = None    # ISO Format (wird bei jedem Update aktualisiert)
    photos_taken: int = 0             # Geschossene Fotos
    prints_completed: int = 0         # Tatsächlich gedruckte Bilder
    prints_failed: int = 0            # Fehlgeschlagene Druckversuche
    sessions_count: int = 0           # Anzahl Foto-Sessions (Durchläufe)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventStats":
        return cls(**data)
    
    def get_summary(self) -> str:
        """Gibt eine lesbare Zusammenfassung zurück"""
        start = ""
        end = ""
        
        if self.start_time:
            try:
                dt = datetime.fromisoformat(self.start_time)
                start = dt.strftime("%d.%m.%Y %H:%M")
            except:
                start = self.start_time
        
        if self.end_time:
            try:
                dt = datetime.fromisoformat(self.end_time)
                end = dt.strftime("%H:%M")
            except:
                end = self.end_time
        
        time_range = f"{start} - {end}" if start and end else "Unbekannt"
        
        return (
            f"Buchung {self.booking_id or 'Unbekannt'} | "
            f"{time_range} | "
            f"{self.prints_completed} Prints | "
            f"{self.photos_taken} Fotos | "
            f"{self.sessions_count} Sessions"
        )


class StatisticsManager:
    """Verwaltet Event-Statistiken"""
    
    def __init__(self):
        self._current_stats: Optional[EventStats] = None
        self._stats_file_path: Optional[Path] = None
        self._all_stats: List[Dict[str, Any]] = []
    
    @property
    def current(self) -> Optional[EventStats]:
        """Aktuelle Event-Statistik"""
        return self._current_stats
    
    def start_event(self, booking_id: str = "", save_path: Optional[Path] = None):
        """Startet ein neues Event/Buchung
        
        Args:
            booking_id: Buchungsnummer (aus settings.json)
            save_path: IGNORIERT - Statistik wird IMMER lokal gespeichert!
        """
        # Vorheriges Event abschließen falls vorhanden
        if self._current_stats:
            self._finalize_current()
        
        # Neues Event starten
        self._current_stats = EventStats(
            booking_id=booking_id,
            start_time=datetime.now().isoformat()
        )
        
        # Speicherpfad: IMMER im Software-Ordner (nicht auf USB - geht Kunden nichts an!)
        self._stats_file_path = Path(__file__).parent.parent.parent / STATS_FILENAME
        
        # Existierende Statistiken laden
        self._load_existing_stats()
        
        logger.info(f"📊 Event gestartet: {booking_id or 'Ohne Buchungsnummer'}")
    
    def record_photo(self, count: int = 1):
        """Erfasst geschossene Fotos"""
        if self._current_stats:
            self._current_stats.photos_taken += count
            self._current_stats.end_time = datetime.now().isoformat()
            logger.debug(f"📷 Foto erfasst (Total: {self._current_stats.photos_taken})")
    
    def record_session(self):
        """Erfasst eine abgeschlossene Foto-Session (ein Durchlauf)"""
        if self._current_stats:
            self._current_stats.sessions_count += 1
            self._current_stats.end_time = datetime.now().isoformat()
            logger.debug(f"📸 Session erfasst (Total: {self._current_stats.sessions_count})")
    
    def record_print_success(self, count: int = 1):
        """Erfasst erfolgreich gedruckte Bilder
        
        WICHTIG: Nur aufrufen wenn Druck tatsächlich erfolgreich war!
        """
        if self._current_stats:
            self._current_stats.prints_completed += count
            self._current_stats.end_time = datetime.now().isoformat()
            self._save_stats()  # Sofort speichern bei Prints
            logger.info(f"🖨️ Print erfolgreich (Total: {self._current_stats.prints_completed})")
    
    def record_print_failed(self, count: int = 1):
        """Erfasst fehlgeschlagene Druckversuche"""
        if self._current_stats:
            self._current_stats.prints_failed += count
            self._current_stats.end_time = datetime.now().isoformat()
            self._save_stats()
            logger.warning(f"⚠️ Print fehlgeschlagen (Total failed: {self._current_stats.prints_failed})")
    
    def end_event(self):
        """Beendet das aktuelle Event"""
        if self._current_stats:
            self._finalize_current()
            logger.info(f"📊 Event beendet: {self._current_stats.get_summary()}")
            self._current_stats = None
    
    def _finalize_current(self):
        """Finalisiert und speichert das aktuelle Event"""
        if not self._current_stats:
            return
        
        self._current_stats.end_time = datetime.now().isoformat()
        
        # Zu Liste hinzufügen
        self._all_stats.append(self._current_stats.to_dict())
        
        # Speichern
        self._save_stats()
    
    def _load_existing_stats(self):
        """Lädt existierende Statistiken aus Datei"""
        self._all_stats = []
        
        if self._stats_file_path and self._stats_file_path.exists():
            try:
                with open(self._stats_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._all_stats = data.get("events", [])
                logger.debug(f"📊 {len(self._all_stats)} vorherige Events geladen")
            except Exception as e:
                logger.warning(f"Statistik-Datei lesen fehlgeschlagen: {e}")
    
    def _save_stats(self):
        """Speichert alle Statistiken in Datei"""
        if not self._stats_file_path:
            logger.warning("Kein Speicherpfad für Statistiken")
            return
        
        try:
            # Aktuelles Event aktualisieren in der Liste
            stats_to_save = self._all_stats.copy()
            if self._current_stats:
                # Aktuelles Event als letztes hinzufügen/aktualisieren
                current_dict = self._current_stats.to_dict()
                
                # Prüfen ob das Event schon in der Liste ist (Update)
                updated = False
                for i, event in enumerate(stats_to_save):
                    if (event.get("booking_id") == current_dict["booking_id"] and 
                        event.get("start_time") == current_dict["start_time"]):
                        stats_to_save[i] = current_dict
                        updated = True
                        break
                
                if not updated:
                    stats_to_save.append(current_dict)
            
            # JSON schreiben
            output = {
                "version": "1.0",
                "last_updated": datetime.now().isoformat(),
                "events": stats_to_save
            }
            
            with open(self._stats_file_path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"📊 Statistiken gespeichert: {self._stats_file_path}")
            
        except Exception as e:
            logger.error(f"Statistiken speichern fehlgeschlagen: {e}")
    
    def get_all_events(self) -> List[EventStats]:
        """Gibt alle erfassten Events zurück"""
        events = []
        for data in self._all_stats:
            events.append(EventStats.from_dict(data))
        return events
    
    def get_all_stats(self) -> List[Dict[str, Any]]:
        """Gibt alle Events als rohe Dictionaries zurück
        
        Lädt automatisch aus bekannten Speicherorten falls noch nicht geladen.
        """
        # Falls noch nichts geladen, versuche aus Standard-Pfaden zu laden
        if not self._all_stats and not self._current_stats:
            self._auto_load_stats()
        
        # Aktuelle Stats auch einbeziehen
        result = self._all_stats.copy()
        if self._current_stats:
            current_dict = self._current_stats.to_dict()
            # Prüfen ob schon enthalten
            already_in = False
            for event in result:
                if (event.get("booking_id") == current_dict["booking_id"] and 
                    event.get("start_time") == current_dict["start_time"]):
                    already_in = True
                    break
            if not already_in:
                result.append(current_dict)
        return result
    
    def _auto_load_stats(self):
        """Versucht Statistiken aus dem Software-Ordner zu laden"""
        # Mögliche Pfade durchsuchen (NUR lokal, nicht USB!)
        search_paths = [
            # Projekt-Root (Hauptspeicherort)
            Path(__file__).parent.parent.parent / STATS_FILENAME,
            # Aktuelles Verzeichnis
            Path.cwd() / STATS_FILENAME,
            # Windows Standard-Installation
            Path("C:/fexobooth/fexobooth-v2") / STATS_FILENAME,
        ]
        
        # Erste gefundene Datei laden
        for path in search_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._all_stats = data.get("events", [])
                        self._stats_file_path = path
                        logger.info(f"📊 Statistiken auto-geladen: {path} ({len(self._all_stats)} Events)")
                        return
                except Exception as e:
                    logger.warning(f"Statistik-Datei {path} lesen fehlgeschlagen: {e}")
    
    def get_current_summary(self) -> str:
        """Gibt Zusammenfassung des aktuellen Events zurück"""
        if self._current_stats:
            return self._current_stats.get_summary()
        return "Kein aktives Event"
    
    def reset_all(self):
        """Setzt alle Statistiken zurück"""
        self._all_stats = []
        self._current_stats = None
        
        # Datei löschen
        if self._stats_file_path and self._stats_file_path.exists():
            try:
                self._stats_file_path.unlink()
                logger.info(f"📊 Statistik-Datei gelöscht: {self._stats_file_path}")
            except Exception as e:
                logger.error(f"Statistik-Datei löschen fehlgeschlagen: {e}")
        
        logger.info("📊 Alle Statistiken zurückgesetzt")


# Singleton-Instanz
_stats_manager: Optional[StatisticsManager] = None


def get_statistics_manager() -> StatisticsManager:
    """Gibt die StatisticsManager-Instanz zurück (Singleton)"""
    global _stats_manager
    if _stats_manager is None:
        _stats_manager = StatisticsManager()
    return _stats_manager


# Öffentliche Instanz für einfachen Import
statistics_manager = get_statistics_manager()
