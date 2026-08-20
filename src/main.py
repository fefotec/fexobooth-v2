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
import threading
import traceback

# Pfad für relative Imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.config import load_config
from src.utils.logging import setup_logging, get_logger
from src.app import PhotoboothApp


def _write_crash(context, exc_type=None, exc_value=None, exc_tb=None):
    """Absturz dauerhaft festhalten — arbeitet unabhaengig vom Logging."""
    try:
        from src.utils.crashlog import write_crash_report
        write_crash_report(context, exc_type, exc_value, exc_tb)
    except Exception:
        pass


def _setup_global_exception_handlers():
    """Installiert globale Exception-Handler für Crashes"""
    logger = get_logger("crash")

    def handle_exception(exc_type, exc_value, exc_traceback):
        """Handler für unbehandelte Exceptions im Hauptthread"""
        if issubclass(exc_type, KeyboardInterrupt):
            # Ctrl+C normal behandeln
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        # Taskleiste wiederherstellen bevor wir crashen
        _recover_taskbar()

        # 2.4.30: IMMER mitschreiben (auch ohne Developer-Mode) — sonst ist der
        # Absturz im Normalbetrieb komplett unsichtbar (Werkstatt 18.08.).
        _write_crash("Hauptthread", exc_type, exc_value, exc_traceback)

        # Vollständigen Stacktrace loggen
        logger.critical("=" * 60)
        logger.critical("UNBEHANDELTE EXCEPTION (Hauptthread)")
        logger.critical("=" * 60)
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        for line in tb_lines:
            for subline in line.rstrip().split('\n'):
                logger.critical(subline)
        logger.critical("=" * 60)

    def handle_thread_exception(args):
        """Handler für unbehandelte Exceptions in Threads"""
        _write_crash(f"Thread: {args.thread.name}",
                     args.exc_type, args.exc_value, args.exc_traceback)
        logger.critical("=" * 60)
        logger.critical(f"UNBEHANDELTE EXCEPTION (Thread: {args.thread.name})")
        logger.critical("=" * 60)
        tb_lines = traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        for line in tb_lines:
            for subline in line.rstrip().split('\n'):
                logger.critical(subline)
        logger.critical("=" * 60)

    # Handler installieren
    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception


def _hide_console_window():
    """Versteckt das Konsolenfenster (nur Windows).

    Wird nur im Produktionsmodus aufgerufen - im Developer Mode bleibt
    die Konsole für Debugging sichtbar.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def _recover_taskbar():
    """Stellt Taskleiste wieder her falls ein vorheriger Lauf abgestürzt ist.

    Muss VOR dem App-Start laufen, damit die Taskleiste nicht permanent
    versteckt bleibt wenn die App vorher per Stromausfall/Force-Kill beendet wurde.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        SW_SHOW = 5
        taskbar = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
        if taskbar:
            ctypes.windll.user32.ShowWindow(taskbar, SW_SHOW)
        start_btn = ctypes.windll.user32.FindWindowW("Button", "Start")
        if start_btn:
            ctypes.windll.user32.ShowWindow(start_btn, SW_SHOW)
    except Exception:
        pass


def _beende_kindprozesse():
    """Beendet Kindprozesse (FexoNikonBridge). Details: src/utils/shutdown.py."""
    try:
        from src.utils.shutdown import beende_kindprozesse
        beende_kindprozesse()
    except Exception:
        pass


def _kamera_fuer_messung():
    """Welche Kamera soll gemessen werden? Liefert (Index, Geraetename|None).

    WARUM NICHT EINFACH INDEX 0 (bis 2.4.34 stand hier eine harte 0):
    Auf dem Miix 310 ist Index 0 die INTERNE Tablet-Kamera. Die ist physisch
    abgeklebt — sie laesst sich zwar oeffnen, liefert aber nie ein Bild. Genau
    das ist der Fall, der die Messung endlos warten liess (Feld-Befund
    19.08.2026: "ich warte nun schon 5 min"). Die Fotobox selbst benutzt diese
    Kamera bewusst NICHT (`find_best_camera` filtert avstream & Co. weg und
    setzt sonst -1). Eine Messung, die eine andere Kamera misst als die App
    benutzt, ist wertlos — deshalb dieselbe Auswahl wie in app.py.
    """
    # 1. Ausdrueckliche Vorgabe auf der Kommandozeile schlaegt alles.
    if "--kamera-index" in sys.argv:
        try:
            return int(sys.argv[sys.argv.index("--kamera-index") + 1]), None
        except Exception:
            pass

    # 2. Wert aus der Config — denselben nimmt auch der Admin-Dialog.
    index = 0
    try:
        index = int(load_config().get("camera_index", 0))
    except Exception:
        index = 0
    if index > 0:
        return index, None

    # 3. Config sagt 0 oder -1: selbst suchen, wie die App es tut.
    #    NUR in diesem Fall, denn list_cameras() oeffnet selbst Kameras — das
    #    kostet auf dem Miix bis zu ~16 s und traegt ein eigenes Haenger-Risiko.
    #    Die Hardware-Sperre ist dabei Pflicht (2.4.31). Schlaegt es fehl,
    #    bleibt es bei 0 — also nie schlechter als bisher.
    try:
        from src.camera.webcam import WebcamManager, camera_hardware_lock
        with camera_hardware_lock():
            kameras = WebcamManager.list_cameras()
        bester = WebcamManager.find_best_camera(kameras)
        if bester >= 0:
            name = next((k.get("name") for k in kameras if k.get("index") == bester), None)
            return bester, name
    except Exception:
        pass

    return (index if index >= 0 else 0), None


def main():
    """Haupteinstiegspunkt"""
    # WICHTIG: Taskleiste wiederherstellen (Recovery von vorherigem Crash)
    _recover_taskbar()

    # Kamera-Messung (2.4.34): eigener Modus, startet KEINE Fotobox-Oberflaeche.
    # Beantwortet die Frage, ob die Kamera dauerhaft in 1080p laufen kann —
    # das laesst sich nur auf der echten Box messen, nicht am Entwickler-PC.
    if "--kamera-test" in sys.argv:
        # 2.4.35: faulthandler MUSS auch in diesem Zweig laufen. Die BAT
        # verspricht dem Bediener "in absturz.log steht dann, woran es lag" —
        # bis 2.4.34 wurde er aber erst weiter unten im Normalstart installiert,
        # im Messmodus also nie. Ein nativer Absturz war damit unsichtbar.
        try:
            from src.utils.crashlog import install_faulthandler
            install_faulthandler()
        except Exception:
            pass

        code = 1
        try:
            from src.tools.kamera_messung import messung_ausfuehren
            index, name = _kamera_fuer_messung()
            pfad = messung_ausfuehren(index, kamera_name=name)
            code = 0 if pfad else 1
        except Exception as e:
            # Ohne Konsole (Fenster-Build) darf hier nichts crashen — der Fehler
            # wandert ins Absturz-Protokoll, das immer geschrieben wird.
            try:
                from src.utils.crashlog import write_crash_report
                write_crash_report("Kamera-Messung")
            except Exception:
                pass
            try:
                print("Kamera-Messung fehlgeschlagen: " + str(e))
            except Exception:
                pass

        # HART beenden mit Exit-Code (0 = Bericht geschrieben), damit die BAT
        # nicht am Dateisystem raten muss. Hart, weil ein aufgegebener
        # Mess-Thread noch im C-Code von OpenCV stehen kann — ein normales
        # Prozessende wuerde daran haengenbleiben.
        _beende_kindprozesse()
        os._exit(code)

    # Developer Mode NUR via Kommandozeile (--dev oder -d)
    # Config-Wert wird IGNORIERT - nur CLI zählt!
    developer_mode = "--dev" in sys.argv or "-d" in sys.argv

    # Konsolenfenster verstecken (nur Produktion - im Dev Mode bleibt es sichtbar)
    if not developer_mode:
        _hide_console_window()

    # Config laden
    config = load_config()
    
    # Developer Mode in Config setzen (für App-Komponenten)
    # WICHTIG: Explizit auf False setzen wenn kein --dev!
    config["developer_mode"] = developer_mode
    
    # Logging initialisieren MIT Developer Mode Info
    logger = setup_logging(developer_mode=developer_mode)

    # Globale Exception-Handler für Crash-Logging
    _setup_global_exception_handlers()

    # 2.4.30: Native Abstürze (Access Violation in einer DLL) mitschreiben.
    # Werkstatt-Befund 18.08.: Ereignisprotokoll meldete ntdll.dll / 0xc0000005 —
    # da läuft KEIN Python-Code mehr, die normalen Handler sehen nichts.
    # faulthandler schreibt im Moment des Absturzes noch den Python-Stack aller
    # Threads nach C:\FexoBooth\logs\absturz.log.
    try:
        from src.utils.crashlog import install_faulthandler
        install_faulthandler()
    except Exception:
        pass

    # Waisen aus einem frueheren Absturz wegraeumen (belegen sonst die Kamera).
    # Im Hintergrund, weil taskkill mehrere Sekunden dauern kann — der Start
    # darf darauf nicht warten.
    try:
        from src.utils.shutdown import raeume_verwaiste_prozesse_auf
        threading.Thread(
            target=raeume_verwaiste_prozesse_auf,
            daemon=True,
            name="waisen-aufraeumen",
        ).start()
    except Exception:
        pass

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
        _write_crash("Start/Hauptschleife")
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
        
        _beende_kindprozesse()
        sys.exit(1)
    
    logger.info("FEXOBOOTH BEENDET")
    logger.info("=" * 50)

    # Prozess HART beenden: Galerie-Server-/Hotspot-/Kamera-Threads sind teils
    # non-daemon und hielten die EXE nach dem Menü-Beenden mit 0% CPU am Leben —
    # der Installer meldete dann "Anwendung läuft noch" (Befund Christian
    # 2026-08-07). Gleiches Muster wie beim App-OTA (_hard_exit_for_update).
    # logging.shutdown() MUSS abgefangen werden: Im Fenster-Build (ohne Konsole)
    # wirft colorama beim Stream-Flush AttributeError ('NoneType' hat kein
    # 'flush') — das zeigte sonst einen PyInstaller-Fehlerdialog beim Beenden.
    # Kindprozesse ZUERST (os._exit nimmt sie nicht mit, siehe Funktion oben)
    _beende_kindprozesse()

    import logging as _logging
    try:
        _logging.shutdown()
    except Exception:
        pass
    os._exit(0)


if __name__ == "__main__":
    main()
