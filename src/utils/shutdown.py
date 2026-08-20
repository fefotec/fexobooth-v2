"""Geordnetes Beenden der FexoBooth-Software.

WARUM ES DIESE DATEI GIBT (Befund Christian, 19.08.2026)
--------------------------------------------------------
Beim Beenden ueber das Service-Menue (PIN 3198) ging das Fenster zwar zu, aber im
Task-Manager blieb ein Prozess stehen. Dahinter steckten zwei verschiedene Dinge,
die beide hier zentral geloest werden:

1. KINDPROZESSE. `main.py` beendet sich am Ende mit `os._exit(0)`. Das ist
   Absicht (siehe Kommentar dort), beendet aber NUR den Python-Prozess. Die
   unsichtbare `FexoNikonBridge.exe` ist ein eigenstaendiger Windows-Prozess und
   ueberlebt als Waise — sie haelt dann auch die Kamera belegt, sodass ein
   Neustart der App scheitern kann.

2. HAENGENDE HAUPTSCHLEIFE. Wenn `root.destroy()` aus irgendeinem Grund die
   Tk-Hauptschleife nicht beendet, wird die Zeile `os._exit(0)` in `main.py` nie
   erreicht. Das Fenster ist dann weg, der Prozess laeuft unsichtbar weiter —
   genau das beschriebene Symptom. Dagegen hilft nur ein Wachhund mit Zeitlimit.

Alle Funktionen hier sind absichtlich fehlertolerant: Beim Beenden darf NICHTS
mehr eine Ausnahme werfen, sonst bleibt der Prozess erst recht haengen.
"""

import os
import threading

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Windows: Prozess ohne aufblitzendes Konsolenfenster starten
_CREATE_NO_WINDOW = 0x08000000

# Nur EINMAL scharf machen — sonst legen mehrere Beenden-Klicks mehrere Wachhunde an
_wachhund_laeuft = False
_wachhund_lock = threading.Lock()


def beende_kindprozesse() -> None:
    """Beendet die Kindprozesse dieser App. MUSS schnell sein.

    Laeuft auf dem Beenden-Weg, also auch auf dem Oberflaechen-Thread — hier
    darf NICHTS blockieren, sonst friert die App beim Beenden sichtbar ein.
    Deshalb wird die Bridge ueber ihre bestehende Verbindung beendet
    (`quit`-Kommando, sonst `process.kill()` direkt auf das Prozess-Handle) und
    NICHT ueber `taskkill`. Ein `taskkill`-Aufruf ist ein eigener Prozessstart
    und kann mehrere Sekunden dauern — gemessen 5 s, siehe
    `raeume_verwaiste_prozesse_auf()`.
    """
    try:
        from src.camera.nikon import shutdown_bridge
        shutdown_bridge()
    except Exception as exc:
        logger.debug(f"Bridge-Stopp fehlgeschlagen: {exc}")


def raeume_verwaiste_prozesse_auf() -> None:
    """Raeumt Bridge-Prozesse frueherer Abstuerze weg. NUR beim App-Start.

    Stuerzt FexoBooth ab (oder wird es im Task-Manager abgeschossen), ueberlebt
    die `FexoNikonBridge.exe` als Waise und belegt weiter die Kamera — der
    naechste Start scheitert dann an der belegten Kamera. Solche Waisen kennt
    nur noch Windows, deshalb hier per Prozessname.

    Warum NICHT beim Beenden: `taskkill` ist ein externer Prozessstart und kann
    spuerbar dauern. Beim Start faellt das in einem Hintergrund-Thread nicht auf,
    beim Beenden waere es eine sichtbare Verzoegerung.

    Aufrufen mit `threading.Thread(..., daemon=True)` — nie blockierend.
    """
    try:
        import subprocess
        ergebnis = subprocess.run(
            ["taskkill", "/IM", "FexoNikonBridge.exe", "/F"],
            creationflags=_CREATE_NO_WINDOW,
            capture_output=True,
            timeout=20,
        )
        if ergebnis.returncode == 0:
            logger.info("Verwaiste FexoNikonBridge aus einem frueheren Lauf entfernt")
    except Exception as exc:
        logger.debug(f"Waisen-Aufraeumen: {exc}")


def harter_ausstieg(grund: str) -> None:
    """Beendet den Prozess sofort und endgueltig — inklusive Kindprozesse.

    Letzte Instanz. Wird vom Wachhund benutzt und kann auch direkt aufgerufen
    werden. Kehrt nie zurueck.
    """
    try:
        logger.warning(f"Harter Ausstieg: {grund}")
    except Exception:
        pass

    beende_kindprozesse()

    # logging.shutdown() MUSS abgefangen werden: Im Fenster-Build (ohne Konsole)
    # wirft colorama beim Stream-Flush AttributeError ('NoneType' hat kein
    # 'flush') — das zeigte sonst einen PyInstaller-Fehlerdialog beim Beenden.
    try:
        import logging as _logging
        _logging.shutdown()
    except Exception:
        pass

    os._exit(0)


def notausstieg_scharf_machen(sekunden: float = 8.0, grund: str = "Beenden") -> None:
    """Startet einen Wachhund, der den Prozess notfalls hart beendet.

    Wird beim Einleiten des Beendens aufgerufen. Im NORMALFALL feuert der
    Wachhund nie: `main.py` kommt nach dem Ende der Hauptschleife an seinem
    `os._exit(0)` an und der Prozess ist laengst weg, bevor die Zeit um ist.
    Er greift nur, wenn die Hauptschleife haengen bleibt — dann verschwindet die
    App trotzdem zuverlaessig aus dem Task-Manager.

    Args:
        sekunden: Zeit, die dem geordneten Beenden zugestanden wird
        grund: Klartext fuer das Log
    """
    global _wachhund_laeuft
    with _wachhund_lock:
        if _wachhund_laeuft:
            return
        _wachhund_laeuft = True

    def _wachen():
        # Daemon-Thread: haelt den Prozess nicht am Leben, falls doch alles klappt
        import time
        time.sleep(sekunden)
        harter_ausstieg(
            f"{grund} — Hauptschleife hat nach {sekunden:.0f} s nicht beendet"
        )

    threading.Thread(
        target=_wachen, daemon=True, name="beenden-wachhund"
    ).start()
    logger.info(
        f"Beenden eingeleitet ({grund}) — Notausstieg in {sekunden:.0f} s scharf"
    )
