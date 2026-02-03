#!/usr/bin/env python3
"""
Fexobooth - Photobooth Software für fexobox
==========================================

Moderne, leichtgewichtige Photobooth-Software optimiert für
Lenovo Miix 310 Tablets (4GB RAM).

Features:
- ZIP-Templates (DSLR-Booth kompatibel)
- 9 Bildfilter
- USB-Stick Auto-Sync
- Windows-Druck
- Touch-optimierte UI

Usage:
    python src/main.py
    
(c) 2026 fexon e.K.
"""

import sys
import os

# Pfad für relative Imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.config import load_config
from src.utils.logging import setup_logging, get_logger
from src.app import PhotoboothApp


def main():
    """Haupteinstiegspunkt"""
    # Developer Mode NUR via Kommandozeile (--dev oder -d)
    # Config-Wert wird IGNORIERT - nur CLI zählt!
    developer_mode = "--dev" in sys.argv or "-d" in sys.argv
    
    # Config laden
    config = load_config()
    
    # Developer Mode in Config setzen (für App-Komponenten)
    # WICHTIG: Explizit auf False setzen wenn kein --dev!
    config["developer_mode"] = developer_mode
    
    # Logging initialisieren MIT Developer Mode Info
    logger = setup_logging(developer_mode=developer_mode)
    logger.info("=" * 50)
    logger.info("FEXOBOOTH STARTET")
    if developer_mode:
        logger.info("🛠️  DEVELOPER MODE AKTIV")
    logger.info("=" * 50)
    
    try:
        logger.info(f"Config geladen")
        logger.info(f"  - Kamera: {config.get('camera_index', 0)}")
        logger.info(f"  - Countdown: {config.get('countdown_time', 5)}s")
        logger.info(f"  - Max Prints: {config.get('max_prints_per_session', 1)}")
        
        # Template-Status
        t1_enabled = config.get("template1_enabled", False)
        t2_enabled = config.get("template2_enabled", False)
        single_enabled = config.get("allow_single_mode", True)
        logger.info(f"  - Templates: T1={t1_enabled}, T2={t2_enabled}, Single={single_enabled}")
        
        # App starten
        logger.info("Starte UI...")
        app = PhotoboothApp(config)
        app.run()
        
    except KeyboardInterrupt:
        logger.info("Beendet durch Benutzer (Ctrl+C)")
    except Exception as e:
        logger.exception(f"Kritischer Fehler: {e}")
        
        # Fehler-Dialog wenn möglich
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Fexobooth Fehler",
                f"Ein kritischer Fehler ist aufgetreten:\n\n{e}\n\nBitte Log-Datei prüfen."
            )
        except:
            print(f"\n\nKRITISCHER FEHLER: {e}\n")
        
        sys.exit(1)
    
    logger.info("FEXOBOOTH BEENDET")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
