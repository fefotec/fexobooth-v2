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

# Bekannte Overlay-GUIDs für verständliches Logging
_OVERLAY_NAMES = {
    "ded574b5-45a0-4f42-8737-46345c09c238": "Beste Leistung",
    "3af9b8d9-7c97-431d-ad78-fd1e4ef7d80d": "Bessere Leistung",
    "961cc777-2547-4f9d-8174-7d86181b8a7a": "Bessere Akkulaufzeit",
    "00000000-0000-0000-0000-000000000000": "Ausbalanciert (kein Overlay)",
}

# Basis-Energiesparplan "Ausbalanciert" — NUR auf diesem Plan zeigt Windows
# den Leistungsregler an und wendet Overlays an
_SCHEME_BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, text: str) -> "_GUID":
        parts = text.split("-")
        return cls(
            int(parts[0], 16),
            int(parts[1], 16),
            int(parts[2], 16),
            (ctypes.c_ubyte * 8)(*bytes.fromhex(parts[3] + parts[4])),
        )

    def to_string(self) -> str:
        d4 = bytes(self.Data4)
        return (
            f"{self.Data1:08x}-{self.Data2:04x}-{self.Data3:04x}-"
            f"{d4[:2].hex()}-{d4[2:].hex()}"
        )


def boost_process_priority() -> None:
    """Hebt die Prozess-Priorität auf ABOVE_NORMAL (nur Windows).

    Die Kiosk-UI kommt damit bei CPU-Konkurrenz (Defender, Update, Indexer)
    zuerst dran. Bewusst NICHT HIGH: das könnte auf dem Miix Treiber/Audio
    aushungern.

    Über psutil statt ctypes: Der direkte SetPriorityClass-Aufruf mit dem
    GetCurrentProcess-Pseudo-Handle schlug im Feld fehl (Log 2026-08-07,
    SetPriorityClass=0 — ctypes übergibt den -1-Pseudo-Handle als 32-Bit-Wert).
    """
    if sys.platform != "win32":
        return
    try:
        import psutil
        psutil.Process().nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
        logger.info("Prozess-Priorität auf ABOVE_NORMAL gesetzt")
    except Exception as e:
        logger.warning(f"Prozess-Priorität konnte nicht gesetzt werden: {e}")


def set_best_performance_power_overlay() -> None:
    """Stellt den Windows-Leistungsregler auf "Beste Leistung" (nur Windows).

    Nutzt PowerSetActiveOverlayScheme aus powrprof.dll — exakt das, was der
    Schieberegler im Akku-Flyout tut. Windows merkt sich die Einstellung pro
    Stromquelle; da die Box am Netz läuft, bleibt "Beste Leistung" damit
    dauerhaft aktiv. Scheitert leise auf alten Windows-Builds ohne diese API.

    Seit 2.4.17 mit VERIFIKATION (Feld-Befund 2026-08-07: API meldete Erfolg,
    Regler stand aber nicht auf Maximum): Nach dem Setzen wird das tatsächlich
    aktive Overlay zurückgelesen und geloggt. Zusätzlich wird der Basis-
    Energiesparplan geprüft — Overlays wirken NUR auf "Ausbalanciert"; auf
    einem klassischen Plan (z.B. "Höchstleistung") gibt es den Regler nicht.
    """
    if sys.platform != "win32":
        return
    try:
        powrprof = ctypes.windll.powrprof
        set_overlay = getattr(powrprof, "PowerSetActiveOverlayScheme", None)
        if set_overlay is None:
            logger.info("Leistungsregler: API nicht verfügbar (altes Windows) — übersprungen")
            return

        # 1. Basis-Energiesparplan prüfen (Overlay wirkt nur auf "Ausbalanciert")
        active_scheme = "unbekannt"
        try:
            scheme_ptr = ctypes.POINTER(_GUID)()
            if powrprof.PowerGetActiveScheme(None, ctypes.byref(scheme_ptr)) == 0:
                active_scheme = scheme_ptr.contents.to_string().lower()
                ctypes.windll.kernel32.LocalFree(scheme_ptr)
        except Exception as e:
            logger.debug(f"Leistungsregler: Aktiver Plan nicht lesbar: {e}")

        if active_scheme not in ("unbekannt", _SCHEME_BALANCED):
            logger.warning(
                f"Leistungsregler: Aktiver Energiesparplan ist NICHT 'Ausbalanciert' "
                f"(GUID {active_scheme}) — der Regler existiert auf diesem Plan nicht. "
                f"Overlay wird trotzdem gesetzt, wirkt aber erst nach Wechsel auf 'Ausbalanciert'."
            )

        # 2. Overlay setzen
        guid = _GUID.from_string(_OVERLAY_SCHEME_MAX_PERFORMANCE)
        result = set_overlay(ctypes.byref(guid))
        if result != 0:
            logger.warning(f"Leistungsregler konnte nicht gestellt werden (Code {result})")
            return

        # 3. Verifizieren: Welches Overlay ist JETZT wirklich aktiv?
        effective = "nicht lesbar"
        get_effective = (getattr(powrprof, "PowerGetEffectiveOverlayScheme", None)
                         or getattr(powrprof, "PowerGetActualOverlayScheme", None))
        if get_effective is not None:
            out = _GUID()
            if get_effective(ctypes.byref(out)) == 0:
                eff_guid = out.to_string().lower()
                effective = _OVERLAY_NAMES.get(eff_guid, f"unbekannt ({eff_guid})")

        if effective == "Beste Leistung":
            logger.info("Leistungsregler auf 'Beste Leistung' gestellt und VERIFIZIERT")
        else:
            logger.warning(
                f"Leistungsregler: Setzen gemeldet OK, aber aktiv ist '{effective}' "
                f"(Basis-Plan {active_scheme})"
            )
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
