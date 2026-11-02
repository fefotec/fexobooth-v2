"""Abschalt-Verlauf ins absturz.log – Diagnose fuer Bug #80 (02.11.2026)

Meldung FX-80 (06.10.2026): „Herunterfahren dauert ewig, dann steht da ‚Box
wird neu gestartet‘". Die Box-Software selbst ruft beim Ausschalten nur
`shutdown /s /f /t 5` auf – ein Neustart kommt von dort nicht. Verdacht:
Windows spielt beim Ausschalten noch Updates ein (Box 018: der Lockdown meldet
gelegentlich `wuauserv.Start=3`, Windows setzt den Dienst also zurueck).

Beweisen laesst sich das nur mit dem Windows-Ereignisprotokoll. Deshalb liest
die Box EINMAL pro Start – 60 s verzoegert, im Hintergrund, ohne Fenster – die
letzten Abschalt-/Neustart-Ereignisse und ausstehende Neustart-Merker aus und
haengt sie an absturz.log (kommt mit dem Log-Upload im Service-Menue mit).
Geschrieben wird nur, wenn sich seit dem letzten Mal etwas geaendert hat,
damit die Datei nicht bei jedem Start waechst.

Ereignisse (Log „System"):
  1074  Wer hat Abschalten/Neustart ausgeloest (Prozess + Grund)
  6006  Ereignisprotokoll sauber beendet (= normales Herunterfahren)
  6008  Unerwartetes Herunterfahren
    41  Kernel-Power: Neustart ohne sauberes Herunterfahren (Strom weg)
19/20/43 WindowsUpdateClient: Update installiert / fehlgeschlagen / gestartet
"""

import hashlib
import subprocess
import threading
import time
from typing import List

from src.utils.logging import get_logger

logger = get_logger(__name__)

START_DELAY_S = 60
MAX_EVENTS = 20
MAX_DESC_CHARS = 220
CREATE_NO_WINDOW = 0x08000000

EVENT_QUERY = (
    "*[System[(EventID=1074 or EventID=6006 or EventID=6008 or EventID=41 "
    "or EventID=19 or EventID=20 or EventID=43) "
    "and TimeCreated[timediff(@SystemTime) <= 1209600000]]]"  # 14 Tage
)

# Registry-Merker fuer „Neustart steht aus" (Windows Update / Komponenten).
PENDING_KEYS = [
    (r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired", None),
    (r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending", None),
    (r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager", "PendingFileRenameOperations"),
    (r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power", "HiberbootEnabled"),
    (r"HKLM\SYSTEM\CurrentControlSet\Services\wuauserv", "Start"),
]


def _run(args: List[str], timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            args, capture_output=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        # wevtutil/reg geben in der ANSI-Codepage aus (deutsches Windows:
        # cp1252) – am PC geprueft, cp850 machte aus „für" ein „f³r".
        return result.stdout.decode("mbcs", errors="replace")
    except Exception as e:
        return f"(Fehler: {type(e).__name__}: {e})"


def _events() -> List[str]:
    # Doppelt so viele holen wie gezeigt: 19/20/43 gibt es auch von anderen
    # Quellen (Wininit, Kernel-General) – die fliegen unten raus.
    raw = _run(["wevtutil", "qe", "System", f"/q:{EVENT_QUERY}",
                f"/c:{MAX_EVENTS * 2}", "/rd:true", "/f:text"])
    zeilen: List[str] = []
    datum = ereignis = quelle = ""
    beschreibung: List[str] = []
    in_beschreibung = False

    def flush():
        relevant = ereignis not in ("19", "20", "43") or quelle.startswith(
            ("WindowsUpdateClient", "Kernel-Boot"))
        if ereignis and relevant and len(zeilen) < MAX_EVENTS:
            text = " ".join(" ".join(beschreibung).split())[:MAX_DESC_CHARS]
            zeilen.append(f"  {datum[:19]} | {ereignis:>4} | {quelle[:28]} | {text}")

    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("Event["):
            flush()
            datum = ereignis = quelle = ""
            beschreibung = []
            in_beschreibung = False
            continue
        key, _, value = s.partition(":")
        key = key.strip().lower()
        if in_beschreibung:
            if s:
                beschreibung.append(s)
        elif key in ("date", "datum"):
            datum = value.strip()
        elif key in ("event id", "ereignis-id", "ereignis id"):
            ereignis = value.strip()
        elif key in ("source", "quelle"):
            quelle = value.strip().replace("Microsoft-Windows-", "")
        elif key in ("description", "beschreibung"):
            in_beschreibung = True
            if value.strip():
                beschreibung.append(value.strip())
    flush()
    if not zeilen and raw.strip().startswith("(Fehler"):
        zeilen.append(f"  {raw.strip()[:200]}")
    return zeilen or ["  (keine passenden Ereignisse in den letzten 14 Tagen)"]


def _pending_flags() -> List[str]:
    zeilen: List[str] = []
    for key, value in PENDING_KEYS:
        args = ["reg", "query", key] + (["/v", value] if value else [])
        out = _run(args, timeout=10)
        name = value or key.rsplit("\\", 1)[-1]
        vorhanden = "ERROR" not in out.upper() and "FEHLER" not in out.upper() and out.strip() != ""
        if value and vorhanden:
            # Letzte Spalte der Treffer-Zeile = Wert (bei Mehrfachwerten gekuerzt)
            wert = ""
            for line in out.splitlines():
                if value.lower() in line.lower():
                    wert = line.split(None, 2)[-1].strip()[:80]
            zeilen.append(f"  {name} = {wert or '(vorhanden)'}")
        else:
            zeilen.append(f"  {name}: {'JA' if vorhanden else 'nein'}")
    return zeilen


def _write_if_changed(block_lines: List[str]) -> bool:
    from src.utils.crashlog import write_info_block, _crash_log_path

    marker = _crash_log_path().with_name(".abschalt_verlauf.hash")
    digest = hashlib.sha1("\n".join(block_lines).encode("utf-8")).hexdigest()
    try:
        if marker.exists() and marker.read_text(encoding="utf-8").strip() == digest:
            logger.debug("Abschalt-Verlauf unveraendert -> nicht erneut geschrieben")
            return False
    except Exception:
        pass
    ok = write_info_block("Abschalt-Verlauf (Diagnose Bug #80)", block_lines)
    if ok:
        try:
            marker.write_text(digest, encoding="utf-8")
        except Exception:
            pass
    return ok


def collect_and_write() -> None:
    """Sammelt Ereignisse + Merker und schreibt sie bei Aenderung ins absturz.log."""
    started = time.monotonic()
    lines = ["Letzte Abschalt-/Neustart-/Update-Ereignisse (neueste zuerst):"]
    lines += _events()
    lines.append("Neustart-Merker / Einstellungen:")
    lines += _pending_flags()
    written = _write_if_changed(lines)
    logger.info(
        f"Abschalt-Verlauf gesammelt ({len(lines)} Zeilen, "
        f"{'geschrieben' if written else 'unveraendert'}, "
        f"{time.monotonic() - started:.1f} s)"
    )


def start_power_history_async(delay_s: int = START_DELAY_S) -> None:
    """Startet die einmalige Sammlung verzoegert im Hintergrund (nie blockierend)."""
    def _worker():
        time.sleep(delay_s)
        try:
            collect_and_write()
        except Exception as e:
            logger.warning(f"Abschalt-Verlauf fehlgeschlagen: {type(e).__name__}: {e}")

    threading.Thread(target=_worker, name="abschalt-verlauf", daemon=True).start()
