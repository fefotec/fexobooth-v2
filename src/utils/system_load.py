"""Systemlast-Diagnose und Windows-Leistungseinstellungen

Zwei Aufgaben:
1. snapshot_system_load(): beantwortet bei UI-Hängern die Frage "WER frisst
   gerade die CPU des Miix?" — bekannte Windows-Hintergrundprozesse
   (Defender-Scan, Update-Worker, Such-Indexer) werden im Log benannt.
2. boost_process_priority() / set_best_performance_power_overlay(): heben
   beim App-Start die Prozess-Priorität an und stellen den Windows-
   Leistungsregler auf "Beste Leistung" (im Standard-Modus drosselt der
   Miix spürbar).
"""

import sys
import ctypes

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Prozessname (lowercase) → verständlicher Name der Lastquelle
KNOWN_BACKGROUND_HOGS = {
    "msmpeng.exe": "Windows-Defender-Scan",
    "tiworker.exe": "Windows-Update-Installer",
    "usoclient.exe": "Windows-Update-Planer",
    "wuauclt.exe": "Windows-Update",
    "searchindexer.exe": "Windows-Such-Indexer",
    "compattelrunner.exe": "Windows-Telemetrie",
    "mscorsvw.exe": ".NET-Optimierung nach Update",
    "dism.exe": "Windows-Wartung (DISM)",
    "cleanmgr.exe": "Datenträgerbereinigung",
    "defrag.exe": "Laufwerksoptimierung",
}

# Windows Power-Overlay "Beste Leistung" (derselbe Mechanismus wie der
# Schieberegler im Akku-Flyout; kein Admin nötig, ab Windows 10 1709)
_OVERLAY_SCHEME_MAX_PERFORMANCE = "ded574b5-45a0-4f42-8737-46345c09c238"


def boost_process_priority() -> None:
    """Hebt die Prozess-Priorität auf ABOVE_NORMAL (nur Windows).

    Die Kiosk-UI kommt damit bei CPU-Konkurrenz (Defender, Update, Indexer)
    zuerst dran. Bewusst NICHT HIGH: das könnte auf dem Miix Treiber/Audio
    aushungern.
    """
    if sys.platform != "win32":
        return
    try:
        above_normal_priority_class = 0x00008000
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.kernel32.SetPriorityClass(handle, above_normal_priority_class)
        if ok:
            logger.info("Prozess-Priorität auf ABOVE_NORMAL gesetzt")
        else:
            logger.warning("Prozess-Priorität konnte nicht gesetzt werden (SetPriorityClass=0)")
    except Exception as e:
        logger.warning(f"Prozess-Priorität konnte nicht gesetzt werden: {e}")


def set_best_performance_power_overlay() -> None:
    """Stellt den Windows-Leistungsregler auf "Beste Leistung" (nur Windows).

    Nutzt PowerSetActiveOverlayScheme aus powrprof.dll — exakt das, was der
    Schieberegler im Akku-Flyout tut. Windows merkt sich die Einstellung pro
    Stromquelle; da die Box am Netz läuft, bleibt "Beste Leistung" damit
    dauerhaft aktiv. Scheitert leise auf alten Windows-Builds ohne diese API.
    """
    if sys.platform != "win32":
        return
    try:
        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        parts = _OVERLAY_SCHEME_MAX_PERFORMANCE.split("-")
        guid = _GUID(
            int(parts[0], 16),
            int(parts[1], 16),
            int(parts[2], 16),
            (ctypes.c_ubyte * 8)(*bytes.fromhex(parts[3] + parts[4])),
        )

        powrprof = ctypes.windll.powrprof
        set_overlay = getattr(powrprof, "PowerSetActiveOverlayScheme", None)
        if set_overlay is None:
            logger.info("Leistungsregler: API nicht verfügbar (altes Windows) — übersprungen")
            return

        result = set_overlay(ctypes.byref(guid))
        if result == 0:
            logger.info("Leistungsregler auf 'Beste Leistung' gestellt")
        else:
            logger.warning(f"Leistungsregler konnte nicht gestellt werden (Code {result})")
    except Exception as e:
        logger.warning(f"Leistungsregler-Einstellung fehlgeschlagen: {e}")


def snapshot_system_load(reason: str = "") -> None:
    """Loggt CPU gesamt, Top-3-Prozesse und erkannte Hintergrund-Störer.

    Blockiert ~1s (CPU-Messfenster) — IMMER aus einem Hintergrund-Thread
    aufrufen, nie vom UI-Thread.
    """
    try:
        import psutil
    except ImportError:
        logger.debug("SYSTEM-LAST: psutil nicht verfügbar")
        return

    procs = []
    for proc in psutil.process_iter(["name"]):
        try:
            proc.cpu_percent(None)  # Messfenster für diesen Prozess starten
            procs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    total = psutil.cpu_percent(interval=1.0)
    cores = psutil.cpu_count() or 1

    loads = []
    for proc in procs:
        try:
            cpu = proc.cpu_percent(None) / cores  # Anteil an der GESAMT-CPU
            if cpu >= 1.0:
                loads.append((cpu, proc.info.get("name") or "?"))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    loads.sort(key=lambda item: item[0], reverse=True)

    top = ", ".join(f"{name} {cpu:.0f}%" for cpu, name in loads[:3]) or "keine nennenswerte Last"
    hogs = [
        f"{KNOWN_BACKGROUND_HOGS[name.lower()]} ({name} {cpu:.0f}%)"
        for cpu, name in loads
        if name.lower() in KNOWN_BACKGROUND_HOGS
    ]

    mem = psutil.virtual_memory()
    prefix = f" ({reason})" if reason else ""
    suffix = f" | Störer erkannt: {'; '.join(hogs)}" if hogs else ""
    logger.info(
        f"SYSTEM-LAST{prefix}: CPU gesamt={total:.0f}%, RAM={mem.percent:.0f}%, "
        f"Top: {top}{suffix}"
    )
