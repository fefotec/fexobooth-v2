"""Logging-Setup mit Session-Rotation

- Jede Session erstellt eine neue Log-Datei
- Maximal 10 Log-Dateien werden behalten (älteste werden gelöscht)
- Im Developer Mode: DEBUG Level + Console Output
- Im Normal Mode: INFO Level in Datei (für Fehlersuche)
"""

import logging
import os
from pathlib import Path
from datetime import datetime

# Basis-Pfad
BASE_PATH = Path(__file__).parent.parent.parent
LOG_PATH = BASE_PATH / "logs"

# Maximale Anzahl Log-Dateien
MAX_LOG_FILES = 10

_logger: logging.Logger = None
_developer_mode: bool = False


def _cleanup_old_logs():
    """Löscht alte Log-Dateien, behält nur die neuesten MAX_LOG_FILES"""
    if not LOG_PATH.exists():
        return

    # Alle Log-Dateien finden
    log_files = list(LOG_PATH.glob("fexobooth_*.log"))

    if len(log_files) <= MAX_LOG_FILES:
        return

    # Nach Änderungsdatum sortieren (älteste zuerst)
    log_files.sort(key=lambda f: f.stat().st_mtime)

    # Älteste löschen bis nur noch MAX_LOG_FILES übrig sind
    files_to_delete = len(log_files) - MAX_LOG_FILES
    for i in range(files_to_delete):
        try:
            log_files[i].unlink()
            print(f"[LOG] Alte Log-Datei gelöscht: {log_files[i].name}")
        except Exception as e:
            print(f"[LOG] Konnte Log-Datei nicht löschen: {e}")


def setup_logging(developer_mode: bool = False) -> logging.Logger:
    """Initialisiert das Logging-System

    Erstellt für jede Session eine neue Log-Datei.
    Behält maximal 10 Log-Dateien (älteste werden gelöscht).

    Args:
        developer_mode: Wenn True, DEBUG Level + Console Output
                       Wenn False, INFO Level nur in Datei
    """
    global _logger, _developer_mode
    _developer_mode = developer_mode

    # Log-Verzeichnis erstellen
    LOG_PATH.mkdir(exist_ok=True)

    # Alte Log-Dateien aufräumen BEVOR neue erstellt wird
    _cleanup_old_logs()

    # Level je nach Modus
    # Developer: DEBUG (alles)
    # Normal: INFO (für Fehlersuche ausreichend)
    level = logging.DEBUG if developer_mode else logging.INFO

    # Session-basierte Log-Datei mit Datum UND Uhrzeit
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = LOG_PATH / f"fexobooth_{timestamp}.log"

    # Logger konfigurieren
    logger = logging.getLogger("fexobooth")
    logger.setLevel(level)

    # Alle vorhandenen Handler entfernen (für Neustart mit anderem Level)
    logger.handlers.clear()

    # File Handler - IMMER aktiv
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    # Console Handler - NUR im Developer Mode
    if developer_mode:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_format = logging.Formatter(
            "%(levelname)-8s | %(message)s"
        )
        console_handler.setFormatter(console_format)
        logger.addHandler(console_handler)
        logger.info("🛠️ Developer Mode aktiv - DEBUG Logging enabled")

    # Start-Nachricht immer loggen
    logger.info("=" * 60)
    logger.info("FexoBooth Session gestartet")
    logger.info(f"Log-Datei: {log_file.name}")
    logger.info(f"Log-Level: {'DEBUG' if developer_mode else 'INFO'}")
    logger.info("=" * 60)

    _logger = logger
    return logger


def is_developer_mode() -> bool:
    """Gibt zurück ob Developer Mode aktiv ist"""
    return _developer_mode


def get_logger(name: str = None) -> logging.Logger:
    """Gibt einen Logger zurück"""
    global _logger
    if _logger is None:
        setup_logging()

    if name:
        return logging.getLogger(f"fexobooth.{name}")
    return _logger


def get_current_log_file() -> Path:
    """Gibt den Pfad zur aktuellen Log-Datei zurück"""
    if _logger and _logger.handlers:
        for handler in _logger.handlers:
            if isinstance(handler, logging.FileHandler):
                return Path(handler.baseFilename)
    return None


def get_recent_logs(count: int = 5) -> list:
    """Gibt die neuesten Log-Dateien zurück

    Args:
        count: Anzahl der zurückzugebenden Dateien

    Returns:
        Liste von Path-Objekten (neueste zuerst)
    """
    if not LOG_PATH.exists():
        return []

    log_files = list(LOG_PATH.glob("fexobooth_*.log"))
    log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    return log_files[:count]
