"""Lifetime-Drucker-Zähler

Zählt die Gesamtanzahl erfolgreicher Drucke über die gesamte Lebensdauer
des Druckers. Wird NICHT durch Event-Wechsel oder Statistik-Reset zurückgesetzt.

Reset nur über Service-PIN (6588) im Admin-Menü möglich.

Speicherort: printer_lifetime.json (im Software-Ordner, neben fexobooth_statistics.json)
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from src.utils.logging import get_logger

logger = get_logger(__name__)

LIFETIME_FILENAME = "printer_lifetime.json"


class PrinterLifetimeCounter:
    """Persistenter Lifetime-Zähler für Drucke"""

    def __init__(self):
        self._file_path = Path(__file__).parent.parent.parent / LIFETIME_FILENAME
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        """Lädt den Zählerstand aus der Datei"""
        if self._file_path.exists():
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.debug(f"Drucker-Lifetime geladen: {data.get('total_prints', 0)} Prints")
                    return data
            except Exception as e:
                logger.warning(f"Drucker-Lifetime laden fehlgeschlagen: {e}")

        return {
            "total_prints": 0,
            "last_reset": None,
            "last_print": None,
        }

    def _save(self):
        """Speichert den Zählerstand"""
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Drucker-Lifetime speichern fehlgeschlagen: {e}")

    @property
    def total_prints(self) -> int:
        """Gesamtanzahl Drucke seit letztem Reset"""
        return self._data.get("total_prints", 0)

    @property
    def last_reset(self) -> Optional[str]:
        """Zeitpunkt des letzten Resets (ISO Format)"""
        return self._data.get("last_reset")

    def increment(self, count: int = 1):
        """Zählt erfolgreiche Drucke hoch"""
        self._data["total_prints"] = self._data.get("total_prints", 0) + count
        self._data["last_print"] = datetime.now().isoformat()
        self._save()
        logger.info(f"Drucker-Lifetime: {self._data['total_prints']} Prints gesamt")

    def reset(self):
        """Setzt den Zähler zurück (nur über Service-PIN!)"""
        old_count = self._data.get("total_prints", 0)
        self._data = {
            "total_prints": 0,
            "last_reset": datetime.now().isoformat(),
            "last_print": None,
        }
        self._save()
        logger.info(f"Drucker-Lifetime zurückgesetzt (war: {old_count} Prints)")


# Singleton
_instance: Optional[PrinterLifetimeCounter] = None


def get_printer_lifetime() -> PrinterLifetimeCounter:
    """Gibt die PrinterLifetimeCounter-Instanz zurück (Singleton)"""
    global _instance
    if _instance is None:
        _instance = PrinterLifetimeCounter()
    return _instance
