"""Logging-Setup

Im Developer Mode: DEBUG Level + Console Output
Im Normal Mode: WARNING Level nur in Datei (spart Ressourcen)
"""

import logging
import os
from pathlib import Path
from datetime import datetime

# Basis-Pfad
BASE_PATH = Path(__file__).parent.parent.parent
LOG_PATH = BASE_PATH / "logs"

_logger: logging.Logger = None
_developer_mode: bool = False


def setup_logging(developer_mode: bool = False) -> logging.Logger:
    """Initialisiert das Logging-System
    
    Args:
        developer_mode: Wenn True, DEBUG Level + Console Output
                       Wenn False, WARNING Level nur in Datei
    """
    global _logger, _developer_mode
    _developer_mode = developer_mode
    
    # Level je nach Modus
    level = logging.DEBUG if developer_mode else logging.WARNING
    
    # Log-Verzeichnis erstellen
    LOG_PATH.mkdir(exist_ok=True)
    
    # Log-Datei mit Datum
    log_file = LOG_PATH / f"fexobooth_{datetime.now().strftime('%Y%m%d')}.log"
    
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
