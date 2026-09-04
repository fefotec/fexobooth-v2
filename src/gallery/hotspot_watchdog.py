"""Hotspot-Waechter (2.4.65) — haelt den Gaeste-Hotspot die ganze Feier durch.

WARUM (Feld-Befunde 01.09. und 04.09.2026, Box 155, plus Kundenfall NX-142048):

1. Der Windows-Hotspot geht von selbst aus. Box 155: 10:04 Uhr AN, 11:26 Uhr aus,
   ohne dass die Software ihn angefasst hat. Windows schaltet den mobilen
   Hotspot ab, wenn eine Weile kein Geraet verbunden ist. Genau das passiert
   auf einer Feier: Gaeste holen am Anfang Fotos, dann ist eine halbe Stunde
   Ruhe — danach kommt niemand mehr rein, "der QR-Code geht nicht".

2. Der Hotspot meldet "AN", hat aber keine Adresse. Box 155 am 01.09.: Windows
   sagte "Tethering On", die Box hatte aber nur eine Notfalladresse
   (169.254.x) und NICHT die Hotspot-Adresse 192.168.137.1. Handys kommen
   dann zwar ins WLAN, erreichen die Box aber nicht. `start_hotspot()` sah
   nur "war bereits aktiv" und hat nichts repariert.

Bisher wurde der Hotspot genau EINMAL beim App-Start angestossen und danach
nie wieder angeschaut. Dieser Waechter prueft ihn alle 45 Sekunden — ohne
PowerShell, nur ueber die IP-Liste (kostet nichts). Fehlt die Hotspot-Adresse
zweimal hintereinander, wird repariert: Hotspot stoppen (falls Windows ihn
fuer "an" haelt) und neu starten. Danach mindestens 3 Minuten Ruhe, damit
ein hartnaeckig kaputter Hotspot die Box nicht mit PowerShell-Aufrufen
zumuellt (Feld-Log 18.08.: parallele PowerShell-Aufrufe = Kamera-Timeouts).

In der Werkstatt (Firmen-WLAN) gilt weiterhin die Regel aus 2.4.27: Blockiert
der Hotspot auf dieser Box nachweislich das Firmen-WLAN, bleibt er dort aus —
der Waechter repariert dann NICHT.

Jede Reparatur landet zusaetzlich in netzwerk.log (wird auch ohne
Developer-Mode geschrieben), damit wir im Feld sehen, ob und wie oft der
Hotspot weggebrochen ist.
"""

import threading
import time
from typing import Callable, Dict, List, Optional

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Pruef-Takt. 45 s ist ein Kompromiss: schnell genug, dass ein Gast hoechstens
# ~1,5 Minuten vor einer verschlossenen Tuer steht, langsam genug fuer 0 Last.
CHECK_INTERVAL_S = 45

# Erst nach der zweiten fehlenden Adresse in Folge reparieren. Eine einzelne
# Luecke kann ein Neustart des Adapters sein — da waere Eingreifen schaedlich.
MISSES_BEFORE_REPAIR = 2

# Nach einer Reparatur mindestens so lange nicht wieder eingreifen.
REPAIR_COOLDOWN_S = 180

# Nach dem Neustart kurz warten, bis Windows die 192.168.137.1 vergeben hat.
SETTLE_AFTER_START_S = 6

# Registrierung: Hier steht, ob Windows den Hotspot bei Leerlauf abschaltet.
# Gesetzt wird das vom Installer bzw. der Boot-Aufgabe (setup/hotspot_keepalive.ps1)
# mit Admin-Rechten; die App liest nur (Kiosk-Konto).
_ICSSVC_SETTINGS = r"SYSTEM\CurrentControlSet\Services\icssvc\Settings"
_TIMEOUT_VALUES = ("PeerlessTimeoutEnabled", "PublicConnectionTimeoutEnabled")


def decide(
    has_hotspot_ip: bool,
    consecutive_misses: int,
    seconds_since_repair: Optional[float],
    *,
    misses_needed: int = MISSES_BEFORE_REPAIR,
    cooldown_s: float = REPAIR_COOLDOWN_S,
) -> str:
    """Reine Entscheidung fuer EINEN Pruefdurchlauf (ohne Nebenwirkungen).

    Args:
        has_hotspot_ip: Hat die Box gerade eine 192.168.137.x-Adresse?
        consecutive_misses: Wie oft fehlte die Adresse jetzt IN FOLGE
            (diese Pruefung mitgezaehlt)?
        seconds_since_repair: Sekunden seit der letzten Reparatur, None = nie.

    Returns:
        "ok"       — Adresse da, nichts tun
        "wait"     — Adresse fehlt, aber noch nicht oft genug
        "cooldown" — Adresse fehlt, Reparatur war gerade erst
        "repair"   — jetzt reparieren
    """
    if has_hotspot_ip:
        return "ok"
    if consecutive_misses < misses_needed:
        return "wait"
    if seconds_since_repair is not None and seconds_since_repair < cooldown_s:
        return "cooldown"
    return "repair"


def read_windows_idle_shutdown() -> Dict[str, Optional[int]]:
    """Liest die zwei Leerlauf-Schalter des Windows-Hotspot-Dienstes.

    Returns:
        {"PeerlessTimeoutEnabled": 0|1|None, "PublicConnectionTimeoutEnabled": 0|1|None}
        None = Wert fehlt (Windows-Standard = abschalten AKTIV).
    """
    result: Dict[str, Optional[int]] = {name: None for name in _TIMEOUT_VALUES}
    try:
        import winreg  # nur Windows
    except ImportError:
        return result
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _ICSSVC_SETTINGS) as key:
            for name in _TIMEOUT_VALUES:
                try:
                    value, _ = winreg.QueryValueEx(key, name)
                    result[name] = int(value)
                except FileNotFoundError:
                    result[name] = None
    except OSError as e:
        logger.debug(f"Hotspot-Waechter: Registrierung nicht lesbar ({e})")
    return result


def describe_windows_idle_shutdown(values: Optional[Dict[str, Optional[int]]] = None) -> str:
    """Klartext fuer Logs und NETZ-BILANZ, z.B. 'AUS (beide Werte 0)'."""
    if values is None:
        values = read_windows_idle_shutdown()
    if all(v == 0 for v in values.values()):
        return "AUS (Installer-Schritt hat gegriffen)"
    fehlend = [n for n, v in values.items() if v is None]
    aktiv = [n for n, v in values.items() if v not in (None, 0)]
    teile = []
    if fehlend:
        teile.append("fehlt: " + ", ".join(fehlend))
    if aktiv:
        teile.append("aktiv: " + ", ".join(aktiv))
    return "AKTIV — Windows schaltet den Hotspot bei Leerlauf ab (" + "; ".join(teile) + ")"


class HotspotWatchdog:
    """Hintergrund-Thread, der die Hotspot-Adresse ueberwacht und repariert."""

    def __init__(
        self,
        ssid: str = "",
        password: str = "",
        *,
        box_id_provider: Optional[Callable[[], str]] = None,
        company_ssids: Optional[List[str]] = None,
    ) -> None:
        self._ssid = ssid
        self._password = password
        self._box_id_provider = box_id_provider
        self._company_ssids = list(company_ssids or [])
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        # Zustand (fuer Log + Diagnose)
        self.checks = 0
        self.consecutive_misses = 0
        self.repairs = 0
        self.repairs_ok = 0
        self.last_repair_at: Optional[float] = None
        self.last_result = "noch keine Pruefung"
        self.last_ips: List[str] = []

    # ── Steuerung ──────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                logger.debug("Hotspot-Waechter laeuft bereits")
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, daemon=True, name="Hotspot-Waechter"
            )
            self._thread.start()
        logger.info(
            f"🛡️ Hotspot-Waechter gestartet (alle {CHECK_INTERVAL_S} s, Reparatur nach "
            f"{MISSES_BEFORE_REPAIR} Fehlpruefungen, Ruhe {REPAIR_COOLDOWN_S} s) — "
            f"Windows-Leerlauf-Abschaltung: {describe_windows_idle_shutdown()}"
        )

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> Dict[str, object]:
        """Kurzer Zustand fuer NETZ-BILANZ / Diagnose."""
        return {
            "checks": self.checks,
            "misses": self.consecutive_misses,
            "repairs": self.repairs,
            "repairs_ok": self.repairs_ok,
            "last_result": self.last_result,
        }

    def status_line(self) -> str:
        return (
            f"{self.checks} Pruefungen, {self.repairs} Reparaturen "
            f"({self.repairs_ok} erfolgreich), zuletzt: {self.last_result}"
        )

    # ── Schleife ───────────────────────────────────────────────

    def _run(self) -> None:
        # Kleine Anlaufpause: der App-Start hat den Hotspot gerade selbst
        # angestossen, dem geben wir Zeit, bevor die erste Pruefung zaehlt.
        if self._stop.wait(CHECK_INTERVAL_S):
            return
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception as e:
                logger.warning(f"Hotspot-Waechter: Pruefung fehlgeschlagen ({e})")
            if self._stop.wait(CHECK_INTERVAL_S):
                return

    def check_once(self) -> str:
        """Eine Pruefung inkl. Reparatur. Gibt die Entscheidung zurueck."""
        from src.utils.network_diag import get_local_ipv4s, has_own_hotspot_ip

        ips = get_local_ipv4s()
        self.last_ips = ips
        has_ip = has_own_hotspot_ip(ips)
        self.checks += 1

        if has_ip:
            if self.consecutive_misses > 0:
                logger.info(
                    f"Hotspot-Waechter: Hotspot-Adresse wieder da nach "
                    f"{self.consecutive_misses} Fehlpruefung(en) — IPs: {ips}"
                )
            self.consecutive_misses = 0
            self.last_result = "ok"
            return "ok"

        self.consecutive_misses += 1
        since_repair = (
            None if self.last_repair_at is None else time.monotonic() - self.last_repair_at
        )
        verdict = decide(has_ip, self.consecutive_misses, since_repair)
        logger.warning(
            f"Hotspot-Waechter: KEINE Hotspot-Adresse (192.168.137.x) — "
            f"Fehlpruefung {self.consecutive_misses} in Folge, IPs: {ips or '[keine]'}, "
            f"Entscheidung: {verdict}"
        )
        if verdict == "repair":
            self._repair(ips)
        else:
            self.last_result = f"{verdict} (Adresse fehlt)"
        return verdict

    # ── Reparatur ──────────────────────────────────────────────

    def _in_company_wlan_with_conflict(self) -> bool:
        """Werkstatt-Regel aus 2.4.27: Hotspot stoert das Firmen-WLAN → Finger weg."""
        try:
            from src.utils.company_wlan import (
                get_connected_ssid,
                hotspot_conflicts_with_company_wlan,
            )
            ssid = get_connected_ssid()
            if ssid and ssid in self._company_ssids and hotspot_conflicts_with_company_wlan():
                return True
        except Exception as e:
            logger.debug(f"Hotspot-Waechter: Firmen-WLAN-Pruefung uebersprungen ({e})")
        return False

    def _repair(self, ips_before: List[str]) -> None:
        from src.gallery.hotspot import is_hotspot_active, start_hotspot, stop_hotspot
        from src.utils.network_diag import get_local_ipv4s, has_own_hotspot_ip

        if self._in_company_wlan_with_conflict():
            self.last_result = "Reparatur uebersprungen (Firmen-WLAN, Hotspot-Konflikt)"
            logger.info(
                "Hotspot-Waechter: Reparatur uebersprungen — Hotspot blockiert auf dieser "
                "Box das Firmen-WLAN (gilt nur in der Werkstatt)"
            )
            return

        self.repairs += 1
        self.last_repair_at = time.monotonic()
        started = time.monotonic()
        logger.warning(
            f"Hotspot-Waechter: Reparatur #{self.repairs} startet — IPs vorher: {ips_before or '[keine]'}"
        )

        # Windows haelt den Hotspot fuer "an", vergibt aber keine Adresse
        # (Befund 01.09.): dann hilft nur aus und wieder an.
        windows_meint_an = False
        try:
            windows_meint_an = is_hotspot_active()
        except Exception as e:
            logger.debug(f"Hotspot-Waechter: Zustandsabfrage fehlgeschlagen ({e})")
        logger.info(
            f"Hotspot-Waechter: Windows meldet Hotspot "
            f"{'AN (aber ohne Adresse → stoppen + neu starten)' if windows_meint_an else 'aus (→ neu starten)'}"
        )
        if windows_meint_an:
            try:
                stop_hotspot()
            except Exception as e:
                logger.warning(f"Hotspot-Waechter: Stopp fehlgeschlagen ({e})")
            time.sleep(3)

        ok_start = False
        try:
            ok_start = start_hotspot(ssid=self._ssid, password=self._password)
        except Exception as e:
            logger.warning(f"Hotspot-Waechter: Start fehlgeschlagen ({e})")

        time.sleep(SETTLE_AFTER_START_S)
        ips_after = get_local_ipv4s()
        ok = has_own_hotspot_ip(ips_after)
        dauer = time.monotonic() - started
        if ok:
            self.repairs_ok += 1
            self.consecutive_misses = 0
            self.last_result = f"Reparatur #{self.repairs} erfolgreich ({dauer:.0f} s)"
            logger.info(
                f"Hotspot-Waechter: Reparatur #{self.repairs} ERFOLGREICH nach {dauer:.0f} s — "
                f"IPs jetzt: {ips_after}"
            )
        else:
            self.last_result = (
                f"Reparatur #{self.repairs} OHNE Erfolg (Start={'ok' if ok_start else 'fehlgeschlagen'})"
            )
            logger.error(
                f"Hotspot-Waechter: Reparatur #{self.repairs} OHNE Erfolg nach {dauer:.0f} s — "
                f"Start={'ok' if ok_start else 'fehlgeschlagen'}, IPs: {ips_after or '[keine]'}"
            )
        self._write_field_report(windows_meint_an, ok_start, ok, ips_before, ips_after, dauer)

    def _write_field_report(
        self,
        windows_meint_an: bool,
        ok_start: bool,
        ok: bool,
        ips_before: List[str],
        ips_after: List[str],
        dauer: float,
    ) -> None:
        """Kurzer Block in netzwerk.log — auch ohne Developer-Mode sichtbar."""
        try:
            from src.utils.network_diag import write_network_report
            try:
                from src import __version__ as version
            except Exception:
                version = ""
            box_id = ""
            if self._box_id_provider is not None:
                try:
                    box_id = self._box_id_provider() or ""
                except Exception:
                    box_id = ""
            lines = [
                "══════ HOTSPOT-WAECHTER: Reparatur ══════",
                f"  Grund         : Hotspot-Adresse 192.168.137.x fehlte {MISSES_BEFORE_REPAIR}x in Folge",
                f"  Windows sagte : Hotspot {'AN (ohne Adresse)' if windows_meint_an else 'aus'}",
                f"  IPs vorher    : {', '.join(ips_before) if ips_before else 'keine'}",
                f"  Neustart      : {'ok' if ok_start else 'FEHLGESCHLAGEN'}",
                f"  IPs danach    : {', '.join(ips_after) if ips_after else 'keine'}",
                f"  ERGEBNIS      : {'HOTSPOT WIEDER DA' if ok else 'HOTSPOT WEITER OHNE ADRESSE'} ({dauer:.0f} s)",
                f"  Bilanz        : {self.status_line()}",
                f"  Leerlauf-Aus  : {describe_windows_idle_shutdown()}",
                "══════════════════════════════════════════════",
            ]
            write_network_report(lines, version=version, box_id=box_id)
        except Exception as e:
            logger.debug(f"Hotspot-Waechter: netzwerk.log nicht geschrieben ({e})")


# ── Modul-Singleton (eine Box = ein Waechter) ─────────────────────
_watchdog: Optional[HotspotWatchdog] = None


def start_watchdog(
    ssid: str = "",
    password: str = "",
    *,
    box_id_provider: Optional[Callable[[], str]] = None,
    company_ssids: Optional[List[str]] = None,
) -> HotspotWatchdog:
    """Startet den Waechter (idempotent) und gibt ihn zurueck."""
    global _watchdog
    if _watchdog is None:
        _watchdog = HotspotWatchdog(
            ssid, password, box_id_provider=box_id_provider, company_ssids=company_ssids
        )
    _watchdog.start()
    return _watchdog


def stop_watchdog() -> None:
    if _watchdog is not None:
        _watchdog.stop()


def watchdog_status_line() -> str:
    """Fuer NETZ-BILANZ: 'nicht gestartet' oder die Bilanz des Waechters."""
    if _watchdog is None:
        return "nicht gestartet"
    return _watchdog.status_line()
