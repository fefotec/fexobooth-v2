#!/usr/bin/env python3
"""
Fexobooth - Haupteinstiegspunkt
"""

import sys
import os

# Pfad für relative Imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.config import load_config, get_config
from src.utils.logging import setup_logging
from src.app import PhotoboothApp


def main():
    """Hauptfunktion"""
    # Logging initialisieren
    logger = setup_logging()
    logger.info("Fexobooth startet...")
    
    # Config laden
    config = load_config()
    logger.info(f"Config geladen: {config.get('camera_type', 'webcam')} Kamera")
    
    # App starten
    app = PhotoboothApp(config)
    app.run()
    
    logger.info("Fexobooth beendet")


if __name__ == "__main__":
    main()
