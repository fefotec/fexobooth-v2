"""Logging-Setup mit Session-Rotation

- Jede Session erstellt eine neue Log-Datei
- Maximal 10 Log-Dateien werden behalten (älteste werden gelöscht)
- NUR im Developer Mode wird geloggt (Ressourcen-Schonung im Live-Betrieb!)
"""

import logging
import os
import sys
from pathlib import Path
from datetime import datetime


def _get_app_path() -> Path:
    """Ermittelt den Anwendungspfad (funktioniert auch bei PyInstaller)"""
    if getattr(sys, 'frozen', False):
        # PyInstaller-Build: exe-Verzeichnis
        return Path(sys.executable).parent
    else:
        # Normale Python-Ausführung
        return Path(__file__).parent.parent.parent


# Basis-Pfad (PyInstaller-kompatibel)
BASE_PATH = _get_app_path()
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

    NUR im Developer Mode wird geloggt (Ressourcen-Schonung im Live-Betrieb!)

    Args:
        developer_mode: Wenn True, DEBUG-Logging in Datei + Console
                       Wenn False, KEIN Logging (NullHandler)
    """
    global _logger, _developer_mode
    _developer_mode = developer_mode

    # Logger konfigurieren
    logger = logging.getLogger("fexobooth")

    # Alle vorhandenen Handler entfernen
    logger.handlers.clear()

    if not developer_mode:
        # KEIN Logging im Normal-Modus (Ressourcen-Schonung!)
        logger.setLevel(logging.CRITICAL + 1)  # Praktisch alles unterdrücken
        logger.addHandler(logging.NullHandler())
        _logger = logger
        return logger

    # === DEVELOPER MODE: Volles Logging ===

    logger.setLevel(logging.DEBUG)

    # Log-Verzeichnis erstellen
    log_path = LOG_PATH
    try:
        log_path.mkdir(exist_ok=True)
    except Exception as e:
        print(f"[LOGGING ERROR] Konnte Log-Verzeichnis nicht erstellen: {log_path} - {e}")
        log_path = Path.cwd() / "logs"
        log_path.mkdir(exist_ok=True)

    # Alte Log-Dateien aufräumen
    _cleanup_old_logs()

    # Session-basierte Log-Datei
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_path / f"fexobooth_{timestamp}.log"

    # File Handler - DEBUG Level
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S"
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    # Console Handler - DEBUG Level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_format = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # Start-Nachricht
    logger.info("🛠️ Developer Mode aktiv - DEBUG Logging enabled")
    logger.info("=" * 60)
    logger.info("FexoBooth Session gestartet")
    logger.info(f"Log-Datei: {log_file}")
    logger.info(f"Log-Pfad: {log_path}")
    logger.info(f"App-Pfad: {BASE_PATH}")
    logger.info(f"PyInstaller: {getattr(sys, 'frozen', False)}")
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
