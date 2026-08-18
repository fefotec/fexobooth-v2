"""Absturz-Protokoll — schreibt IMMER, auch ohne Developer-Mode (2.4.30)

Hintergrund (Werkstatt 18.08.2026): Zwei Boxen stürzten beim Hochfahren ab,
andere beim Anstecken des USB-Sticks — aber **nie im Developer-Mode**. Zurück
kamen nur Dev-Logs, die sauber bis „FEXOBOOTH BEENDET" durchliefen. Der Absturz
selbst war nirgends dokumentiert, weil die App im Normalbetrieb gar nichts
schreibt (`setup_logging` hängt dann einen NullHandler ein).

Zwei Dinge behebt dieses Modul:

1. **Absturz wird sichtbar.** Jeder unbehandelte Fehler landet in
   `C:\\FexoBooth\\logs\\absturz.log` — mit Zeitstempel, Version und komplettem
   Stacktrace. Dieselbe Stelle wie `netzwerk.log`, kommt also automatisch mit,
   wenn jemand den logs-Ordner kopiert.

2. **Der wahrscheinlichste Absturz-Grund selbst.** Tkinter meldet Fehler aus
   Callbacks (Button-Klick, `after()`-Ticks, USB-Prüfung) über
   `report_callback_exception` — und das schreibt standardmäßig nach
   `sys.stderr`. Im Fenster-Build (PyInstaller ohne Konsole) ist `sys.stderr`
   aber `None`. Der Fehler-Handler scheitert dann SELBST und reisst die ganze
   App mit. Genau deshalb knallt es nur im Normalbetrieb: Im Developer-Mode gibt
   es eine Konsole, dort wird der Fehler brav gedruckt und die App läuft weiter.
   Mit dem eigenen Handler unten überlebt die App den Fehler jetzt in beiden
   Fällen — und wir sehen im Protokoll, WAS schiefging.
"""

import sys
import time
import traceback
from typing import Optional

CRASH_LOG_NAME = "absturz.log"
CRASH_LOG_MAX_BYTES = 200 * 1024


def _crash_log_path():
    """Zielpfad (neben netzwerk.log), mit Fallback."""
    from pathlib import Path
    try:
        from src.utils.logging import LOG_PATH
        return Path(LOG_PATH) / CRASH_LOG_NAME
    except Exception:
        return Path(r"C:\ProgramData\FexoBox") / CRASH_LOG_NAME


def _version() -> str:
    try:
        from src import __version__
        return __version__
    except Exception:
        return "?"


def write_crash_report(context: str, exc_type=None, exc_value=None, exc_tb=None) -> bool:
    """Schreibt einen Absturz-Eintrag — unabhängig vom Developer-Mode.

    Args:
        context: Wo es passiert ist (z.B. "Tk-Callback", "Hauptthread")
        exc_type/exc_value/exc_tb: Exception-Infos; ohne Angabe wird die
                                   gerade behandelte Exception genommen.
    """
    from pathlib import Path

    if exc_type is None:
        exc_type, exc_value, exc_tb = sys.exc_info()

    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        zeilen = [
            f"----- {stamp} | Version {_version()} | {context} -----",
        ]
        if exc_type is not None:
            zeilen.extend(
                l.rstrip("\n")
                for l in traceback.format_exception(exc_type, exc_value, exc_tb)
            )
        else:
            zeilen.append("(keine Exception-Info verfügbar)")
        block = "\n".join(zeilen) + "\n\n"
    except Exception:
        return False

    for ziel in (_crash_log_path(), Path(r"C:\ProgramData\FexoBox") / CRASH_LOG_NAME):
        try:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            with open(ziel, "a", encoding="utf-8") as f:
                f.write(block)
            _trim(ziel)
            return True
        except Exception:
            continue
    return False


def _trim(path) -> None:
    """Datei klein halten (bei Überlänge die ältere Hälfte wegwerfen)."""
    try:
        if path.stat().st_size <= CRASH_LOG_MAX_BYTES:
            return
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        with open(path, "w", encoding="utf-8") as f:
            f.write("... (aeltere Eintraege gekuerzt) ...\n")
            f.writelines(lines[len(lines) // 2:])
    except Exception:
        pass


# ─────────────────────────────────────────────
# Native Abstuerze (Access Violation) mitschreiben
# ─────────────────────────────────────────────
# Werkstatt-Befund 18.08.2026, Windows-Ereignisprotokoll einer abgestuerzten Box:
#   Name des fehlerhaften Moduls: ntdll.dll
#   Ausnahmecode: 0xc0000005          (= Speicherzugriffsfehler)
# Das ist KEIN Python-Fehler. Der Prozess stirbt sofort, ohne dass noch
# Python-Code laeuft — `sys.excepthook`, der Tk-Handler und `write_crash_report`
# sehen davon NICHTS und die Datei bliebe leer.
#
# `faulthandler` ist genau dafuer gebaut: Es haengt sich unterhalb von Python in
# die Absturz-Signale und schreibt im Moment des Knalls noch den Python-Stack
# ALLER Threads raus. Damit sehen wir, welche Stelle gerade lief — Kamera, VLC,
# Drucker oder etwas anderes. Kostet zur Laufzeit praktisch nichts (nur ein paar
# installierte Signal-Handler), laeuft deshalb IMMER mit, auch ohne Dev-Mode.

_fault_file = None  # Referenz halten, sonst schliesst der GC die Datei


def install_faulthandler() -> bool:
    """Schreibt bei nativen Abstuerzen den Python-Stack nach absturz.log."""
    global _fault_file
    if _fault_file is not None:
        return True

    from pathlib import Path
    import faulthandler

    for ziel in (_crash_log_path(), Path(r"C:\ProgramData\FexoBox") / CRASH_LOG_NAME):
        try:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            f = open(ziel, "a", buffering=1, encoding="utf-8", errors="replace")
            f.write(
                f"----- {time.strftime('%Y-%m-%d %H:%M:%S')} | Version {_version()} | "
                f"Start (Absturz-Ueberwachung aktiv) -----\n"
            )
            faulthandler.enable(file=f, all_threads=True)
            _fault_file = f
            return True
        except Exception:
            continue
    return False


def install_tk_exception_handler(root, logger=None) -> bool:
    """Fängt Fehler aus Tkinter-Callbacks ab, statt die App sterben zu lassen.

    OHNE diesen Handler geht Tkinter den Standardweg über `sys.stderr` — der im
    Fenster-Build `None` ist. Ergebnis: Der Fehler-Handler wirft selbst einen
    AttributeError und die App ist weg, ohne jede Spur.

    Args:
        root: Das Tk-/CTk-Hauptfenster
        logger: optionaler Logger (greift nur im Developer-Mode)

    Returns:
        True wenn der Handler gesetzt werden konnte
    """
    def _handler(exc_type, exc_value, exc_tb):
        write_crash_report("Tk-Callback (abgefangen, App läuft weiter)",
                           exc_type, exc_value, exc_tb)
        if logger is not None:
            try:
                logger.error(
                    "Fehler in Tk-Callback abgefangen: "
                    f"{exc_type.__name__}: {exc_value}",
                    exc_info=(exc_type, exc_value, exc_tb),
                )
            except Exception:
                pass

    try:
        root.report_callback_exception = _handler
        return True
    except Exception:
        return False
