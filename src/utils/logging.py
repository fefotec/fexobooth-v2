"""Logging-Setup"""

import logging
import os
from pathlib import Path
from datetime import datetime

# Basis-Pfad
BASE_PATH = Path(__file__).parent.parent.parent
LOG_PATH = BASE_PATH / "logs"

_logger: logging.Logger = None


def setup_logging(level: int = logging.DEBUG) -> logging.Logger:
    """Initialisiert das Logging-System"""
    global _logger
    
    # Log-Verzeichnis erstellen
    LOG_PATH.mkdir(exist_ok=True)
    
    # Log-Datei mit Datum
    log_file = LOG_PATH / f"fexobooth_{datetime.now().strftime('%Y%m%d')}.log"
    
    # Logger konfigurieren
    logger = logging.getLogger("fexobooth")
    logger.setLevel(level)
    
    # Handler nur einmal hinzufügen
    if not logger.handlers:
        # File Handler
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_format = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
        
        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_format = logging.Formatter(
            "%(levelname)-8s | %(message)s"
        )
        console_handler.setFormatter(console_format)
        logger.addHandler(console_handler)
    
    _logger = logger
    return logger


def get_logger(name: str = None) -> logging.Logger:
    """Gibt einen Logger zurück"""
    global _logger
    if _logger is None:
        setup_logging()
    
    if name:
        return logging.getLogger(f"fexobooth.{name}")
    return _logger
