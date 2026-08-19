"""Netzwerk-Diagnose + DHCP-Reparatur (2.4.27)

Hintergrund (Feld-Log 18.08.2026, Box 200):
Die Box war laut `netsh wlan show interfaces` mit 'fexon WLAN' VERBUNDEN —
hatte aber keine brauchbare IP-Adresse. Vorhanden waren nur:

  - `169.254.183.239` → Windows-Notfalladresse (APIPA). Heisst im Klartext:
    "Ich bin auf Funk-Ebene verbunden, aber der Router hat mir keine
    IP-Adresse gegeben."
  - `192.168.137.1`   → der EIGENE Hotspot der Box (Windows Mobile Hotspot/ICS)

Folge: DNS scheitert (`getaddrinfo failed`), Dashboard-Meldung und Updates
kommen nie an. Nach aussen sieht das aus wie "die Box verbindet sich nicht
mit dem Firmen-WLAN" — obwohl der WLAN-Name stimmt.

Dieses Modul beantwortet deshalb die EHRLICHE Frage ("hat die Box wirklich
Netz?") statt der bisherigen ("steht der richtige WLAN-Name da?") und kann
eine fehlende DHCP-Adresse anstossen.

Wichtig: Alles hier ist reine Diagnose bzw. wird nur im Firmen-WLAN benutzt.
Im Kundenbetrieb laeuft davon nichts (siehe company_wlan.py / company_network.py).
"""

import re
import socket
import subprocess
import time
from typing import List, Optional, Tuple

from src.utils.logging import get_logger

logger = get_logger(__name__)

_CREATE_NO_WINDOW = 0x08000000

# Adressbereiche, die KEIN echtes Netzwerk bedeuten
LOOPBACK_PREFIX = "127."          # eigener Rechner
APIPA_PREFIX = "169.254."         # Windows-Notfalladresse = DHCP hat nichts geliefert
OWN_HOTSPOT_PREFIX = "192.168.137."  # eigener Hotspot (Windows Mobile Hotspot / ICS)


def get_local_ipv4s() -> List[str]:
    """Alle IPv4-Adressen dieses Rechners (ohne Loopback).

    Bewusst ohne Subprozess (schnell, keine Sprach-/Encoding-Fallen):
    Der eigene Hostname wird aufgeloest — das liefert unter Windows die
    Adressen aller aktiven Adapter.
    """
    ips: List[str] = []
    try:
        hostname = socket.gethostname()
        for entry in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = entry[4][0]
            if ip and not ip.startswith(LOOPBACK_PREFIX) and ip not in ips:
                ips.append(ip)
    except Exception as e:
        logger.debug(f"Netz-Diagnose: IP-Liste nicht ermittelbar ({e})")
    return ips


def is_usable_lan_ip(ip: str) -> bool:
    """Ist das eine Adresse, mit der man wirklich ins Netz kommt?

    Nein bei: Loopback, APIPA (kein DHCP) und der eigenen Hotspot-Adresse.
    """
    if not ip:
        return False
    return not (
        ip.startswith(LOOPBACK_PREFIX)
        or ip.startswith(APIPA_PREFIX)
        or ip.startswith(OWN_HOTSPOT_PREFIX)
    )


def get_usable_lan_ips(ips: Optional[List[str]] = None) -> List[str]:
    """Nur die Adressen, die ein echtes Netzwerk bedeuten."""
    if ips is None:
        ips = get_local_ipv4s()
    return [ip for ip in ips if is_usable_lan_ip(ip)]


def has_usable_lan_ip(ips: Optional[List[str]] = None) -> bool:
    """True, wenn die Box mindestens eine echte Netzwerk-Adresse hat."""
    return len(get_usable_lan_ips(ips)) > 0


def has_own_hotspot_ip(ips: Optional[List[str]] = None) -> bool:
    """Laeuft der eigene Hotspot? — erkannt an der Adresse 192.168.137.x.

    Bewusst ohne PowerShell-Abfrage: Die Adresse steht ohnehin in der IP-Liste,
    die Erkennung kostet damit NICHTS. Wichtig fuer die Reparatur, weil dort
    jede Sekunde zaehlt (Feld-Log 18.08.: die Box wurde nach ~2 Minuten
    ausgeschaltet, bevor die langsamen Schritte durch waren).
    """
    if ips is None:
        ips = get_local_ipv4s()
    return any(ip.startswith(OWN_HOTSPOT_PREFIX) for ip in ips)


def describe_ips(ips: Optional[List[str]] = None) -> str:
    """Eine gut lesbare Log-Zeile ueber den IP-Zustand.

    Beispiel-Ausgabe:
      "169.254.183.239 (KEINE DHCP-Adresse/APIPA), 192.168.137.1 (eigener Hotspot)
       → KEINE brauchbare Netzwerk-Adresse"
    """
    if ips is None:
        ips = get_local_ipv4s()

    if not ips:
        return "keine IPv4-Adresse gefunden → KEINE brauchbare Netzwerk-Adresse"

    parts = []
    for ip in ips:
        if ip.startswith(APIPA_PREFIX):
            parts.append(f"{ip} (KEINE DHCP-Adresse/APIPA)")
        elif ip.startswith(OWN_HOTSPOT_PREFIX):
            parts.append(f"{ip} (eigener Hotspot)")
        else:
            parts.append(f"{ip} (ok)")

    usable = get_usable_lan_ips(ips)
    verdict = f"→ brauchbar: {', '.join(usable)}" if usable else "→ KEINE brauchbare Netzwerk-Adresse"
    return f"{', '.join(parts)} {verdict}"


def log_network_snapshot(context: str, ssid: Optional[str] = None) -> bool:
    """Schreibt den aktuellen Netz-Zustand ins Log und sagt, ob er ok ist.

    Genau diese eine Zeile hat im Feld-Log vom 18.08. gefehlt — sie macht aus
    "Dashboard nicht erreichbar" sofort eine Diagnose.

    Args:
        context: Wo im Ablauf wir stehen (erscheint im Log)
        ssid:    Aktuelle WLAN-SSID, falls schon bekannt (spart einen netsh-Aufruf)

    Returns:
        True wenn eine brauchbare Netzwerk-Adresse da ist
    """
    ips = get_local_ipv4s()
    ok = has_usable_lan_ip(ips)
    wlan = f"WLAN='{ssid}' | " if ssid else ""
    level = logger.info if ok else logger.warning
    level(f"Netz-Check [{context}]: {wlan}{describe_ips(ips)}")
    return ok


def get_wlan_interface_name() -> Optional[str]:
    """Name des WLAN-Adapters (dt. 'WLAN', engl. 'Wi-Fi').

    Wird fuer `ipconfig /renew "<Name>"` gebraucht. Die Zeile heisst in beiden
    Windows-Sprachen 'Name', deshalb ist das sprachunabhaengig.
    """
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception as e:
        logger.debug(f"Netz-Diagnose: netsh wlan show interfaces fehlgeschlagen ({e})")
        return None

    raw = result.stdout or b""
    text = ""
    for encoding in ("utf-8", "cp850", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    for line in text.splitlines():
        stripped = line.strip()
        m = re.match(r"^Name\s*:\s*(.+)$", stripped)
        if m:
            name = m.group(1).strip()
            if name:
                return name
    return None


def _run(cmd: List[str], timeout: int = 60) -> Tuple[int, str]:
    """Hilfsprogramm ohne Fenster ausfuehren."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
        out = (result.stdout or b"").decode("utf-8", errors="replace")
        out += (result.stderr or b"").decode("utf-8", errors="replace")
        return result.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"
    except Exception as e:
        return 1, str(e)


def flush_dns() -> None:
    """DNS-Zwischenspeicher leeren (harmlos, braucht keine Adminrechte)."""
    code, _ = _run(["ipconfig", "/flushdns"], timeout=15)
    logger.debug(f"Netz-Reparatur: DNS-Cache geleert (Code {code})")


def renew_dhcp_lease(interface_name: Optional[str] = None, wait_seconds: int = 10,
                     renew_timeout: int = 20) -> bool:
    """Fordert eine neue IP-Adresse vom Router an (release + renew).

    ACHTUNG: `ipconfig /release` und `/renew` brauchen unter Windows in der
    Regel Administratorrechte. Die App laeuft als Kiosk-Benutzer, deshalb kann
    das fehlschlagen — das ist kein Drama, der Aufrufer hat dann noch den
    Weg "WLAN trennen und neu verbinden" (braucht keine Adminrechte).

    Returns:
        True wenn danach eine brauchbare Adresse da ist
    """
    target = interface_name or get_wlan_interface_name()
    args_release = ["ipconfig", "/release"]
    args_renew = ["ipconfig", "/renew"]
    if target:
        args_release.append(target)
        args_renew.append(target)

    logger.info(f"Netz-Reparatur: Neue IP-Adresse anfordern (Adapter: {target or 'alle'})...")

    code_rel, out_rel = _run(args_release, timeout=30)
    if code_rel != 0:
        logger.debug(f"Netz-Reparatur: release meldete Code {code_rel} ({out_rel.strip()[:150]})")
    if "erforderlich" in out_rel.lower() or "elevation" in out_rel.lower() or "denied" in out_rel.lower():
        logger.warning(
            "Netz-Reparatur: ipconfig braucht Administratorrechte — nicht moeglich als Kiosk-Benutzer "
            "(es bleibt der Weg: WLAN trennen und neu verbinden)"
        )
        return False

    # Timeout bewusst kurz (Feld-Log 18.08., Box 056): `ipconfig /renew` hing
    # dort volle 60 s und lieferte dann TIMEOUT — in der Zeit war die Box laengst
    # wieder aus. Antwortet der Router in 20 s nicht, antwortet er auch spaeter
    # nicht; dann sind die naechsten Stufen wichtiger als das Warten.
    code_ren, out_ren = _run(args_renew, timeout=renew_timeout)
    logger.debug(f"Netz-Reparatur: renew Code {code_ren} ({out_ren.strip()[:150]})")

    return wait_for_usable_ip(wait_seconds)


def wait_for_usable_ip(timeout_seconds: int = 20) -> bool:
    """Wartet, bis eine echte Netzwerk-Adresse da ist (oder die Zeit um ist)."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        if has_usable_lan_ip():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(2)


# ─────────────────────────────────────────────
# Einzelpruefungen: Wo genau haengt es?
# ─────────────────────────────────────────────
# Damit im Log unterscheidbar ist:
#   keine IP  ≠  IP aber kein DNS  ≠  DNS ok aber Server nicht erreichbar
# Genau diese Unterscheidung hat beim Feld-Log 18.08. gefehlt.

def probe_gateway() -> Tuple[bool, str]:
    """Antwortet das Standard-Gateway (der Router)? Ein Ping genuegt."""
    gateway = get_default_gateway()
    if not gateway:
        return False, "kein Standard-Gateway gesetzt"
    code, _ = _run(["ping", "-n", "1", "-w", "1500", gateway], timeout=15)
    if code == 0:
        return True, f"Router {gateway} antwortet"
    return False, f"Router {gateway} antwortet NICHT"


def get_default_gateway() -> Optional[str]:
    """Adresse des Routers (sprachunabhaengig ueber die Routing-Tabelle)."""
    code, out = _run(["route", "print", "-4", "0.0.0.0"], timeout=15)
    if code != 0:
        return None
    # Zeile: "  0.0.0.0    0.0.0.0   192.168.178.1   192.168.178.42   35"
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
            candidate = parts[2]
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", candidate) and candidate != "0.0.0.0":
                return candidate
    return None


def probe_dns(hostname: str = "admin.fexobox.de") -> Tuple[bool, str]:
    """Laesst sich ein Name aufloesen? (Das ist im Feld-Log gescheitert.)"""
    try:
        started = time.monotonic()
        ip = socket.gethostbyname(hostname)
        dauer = (time.monotonic() - started) * 1000
        return True, f"{hostname} → {ip} ({dauer:.0f} ms)"
    except Exception as e:
        return False, f"{hostname} nicht aufloesbar ({e})"


def probe_tcp(host: str = "admin.fexobox.de", port: int = 443, timeout: float = 3.0) -> Tuple[bool, str]:
    """Kommt eine echte Verbindung zum Dashboard zustande?"""
    sock = None
    try:
        started = time.monotonic()
        sock = socket.create_connection((host, port), timeout=timeout)
        dauer = (time.monotonic() - started) * 1000
        return True, f"{host}:{port} erreichbar ({dauer:.0f} ms)"
    except Exception as e:
        return False, f"{host}:{port} NICHT erreichbar ({e})"
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


# ─────────────────────────────────────────────
# Dauer-Protokoll: netzwerk.log (2.4.27)
# ─────────────────────────────────────────────
# WARUM EIGENE DATEI:
# Das normale App-Log gibt es NUR im Developer-Mode (`setup_logging` haengt sonst
# einen NullHandler ein). In der Werkstatt startet die Box aber ganz normal —
# deshalb kam beim Test am 18.08. von drei Boxen (073/116/016) kein einziges
# App-Log zurueck, nur die Installer-Logs. Damit war nicht feststellbar, WORAN
# es lag.
#
# Diese Datei wird deshalb IMMER geschrieben — aber sehr sparsam:
#   - nur im Firmen-WLAN (beim Kunden passiert nie etwas)
#   - nur ein kurzer Block pro Start bzw. pro fehlgeschlagener Wiederholmeldung
#   - Datei wird bei Ueberlaenge vorne gekuerzt
# Sie liegt neben den Installer-Logs (C:\FexoBooth\logs) und landet damit
# automatisch mit, wenn ein Mitarbeiter den logs-Ordner kopiert.

NETWORK_LOG_NAME = "netzwerk.log"
NETWORK_LOG_MAX_BYTES = 200 * 1024   # ~200 KB, dann wird vorne gekuerzt


def _network_log_path():
    """Zielpfad fuer netzwerk.log (mit Fallback, falls nicht schreibbar)."""
    from pathlib import Path
    try:
        from src.utils.logging import LOG_PATH
        return Path(LOG_PATH) / NETWORK_LOG_NAME
    except Exception:
        return Path(r"C:\ProgramData\FexoBox") / NETWORK_LOG_NAME


def _trim_network_log(path) -> None:
    """Haelt die Datei klein: bei Ueberlaenge die aeltere Haelfte wegwerfen."""
    try:
        if path.stat().st_size <= NETWORK_LOG_MAX_BYTES:
            return
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        keep = lines[len(lines) // 2:]
        with open(path, "w", encoding="utf-8") as f:
            f.write("... (aeltere Eintraege gekuerzt) ...\n")
            f.writelines(keep)
    except Exception:
        pass


def write_network_report(lines: List[str], version: str = "", box_id: str = "") -> bool:
    """Schreibt einen Block in netzwerk.log — unabhaengig vom Developer-Mode.

    Returns:
        True wenn geschrieben werden konnte
    """
    from pathlib import Path

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    kopf = f"----- {stamp}"
    if box_id:
        kopf += f" | Box {box_id}"
    if version:
        kopf += f" | Version {version}"
    kopf += " -----"

    block = kopf + "\n" + "\n".join(lines) + "\n\n"

    for ziel in (_network_log_path(), Path(r"C:\ProgramData\FexoBox") / NETWORK_LOG_NAME):
        try:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            with open(ziel, "a", encoding="utf-8") as f:
                f.write(block)
            _trim_network_log(ziel)
            return True
        except Exception:
            continue

    logger.debug("Netz-Bilanz konnte nicht dauerhaft gespeichert werden")
    return False


def log_network_verdict(context: str, ssid: Optional[str] = None,
                        hostname: str = "admin.fexobox.de",
                        extra: Optional[dict] = None,
                        persist: bool = False,
                        version: str = "", box_id: str = "") -> dict:
    """Kompakte NETZ-BILANZ ins Log — die Antwort auf "hat es geholfen?".

    Schreibt einen klar erkennbaren Block, an dem sofort ablesbar ist, wo es
    haengt. Wenn ein Fix nicht wirkt, steht die Ursache damit im naechsten Log,
    ohne dass jemand an die Box muss.

    Returns:
        Die Einzelergebnisse als dict (fuer Auswerter/Tests)
    """
    ips = get_local_ipv4s()
    ip_ok = has_usable_lan_ip(ips)
    gw_ok, gw_text = probe_gateway()
    dns_ok, dns_text = probe_dns(hostname)
    tcp_ok, tcp_text = (False, "uebersprungen (kein DNS)")
    if dns_ok:
        tcp_ok, tcp_text = probe_tcp(hostname)

    def mark(ok: bool) -> str:
        return "OK  " if ok else "FEHLT"

    lines = [
        f"══════ NETZ-BILANZ [{context}] ══════",
        f"  WLAN-Name     : {ssid or 'unbekannt'}",
        f"  IP-Adressen   : {mark(ip_ok)} | {describe_ips(ips)}",
        f"  Router-Ping   : {mark(gw_ok)} | {gw_text}",
        f"  Namensauflös. : {mark(dns_ok)} | {dns_text}",
        f"  Dashboard     : {mark(tcp_ok)} | {tcp_text}",
    ]

    if extra:
        for key, value in extra.items():
            lines.append(f"  {key:<14}: {value}")

    # Klartext-Urteil: Wo genau haengt es?
    if not ip_ok:
        # 2.4.33: Sauber trennen. Laeuft der eigene Hotspot NICHT, ist er auch
        # nicht schuld — dann zeigt alles auf den Router. Feld-Befund 19.08.
        # (Boxen 019 und 038): Hotspot aus, Reparatur erfolglos, trotzdem nur
        # 169.254.x.x. Der alte Text nannte weiter den Hotspot als Verdacht und
        # hat damit in die falsche Richtung gezeigt.
        if has_own_hotspot_ip(ips):
            urteil = ("KEINE IP-ADRESSE, und der eigene Hotspot laeuft → wahrscheinlich "
                      "belegt er die WLAN-Karte (die Reparatur schaltet ihn ab und prueft das)")
        else:
            urteil = ("KEINE IP-ADRESSE, eigener Hotspot ist AUS → die Box ist entlastet, "
                      "der ROUTER vergibt ihr keine Adresse. Zu pruefen: DHCP-Bereich voll "
                      "(zu wenige Adressen fuer die Flotte), MAC-Sperre/Zugangsliste, "
                      "oder Client-Limit des Routers erreicht")
    elif not gw_ok:
        urteil = ("IP da, aber Router antwortet nicht → Funkverbindung steht nur "
                  "auf dem Papier (Verdacht: WLAN-Karte im Hotspot-Betrieb)")
    elif not dns_ok:
        urteil = ("Router erreichbar, aber keine Namensauflösung → DNS-Server "
                  "fehlt/blockiert (Verdacht: falsche DNS-Einträge durch den Hotspot/ICS)")
    elif not tcp_ok:
        urteil = ("DNS ok, aber Dashboard nicht erreichbar → Internet/Firewall prüfen "
                  "(nicht die WLAN-Anmeldung)")
    else:
        urteil = "ALLES GRÜN — Box hat vollen Netzzugang"

    lines.append(f"  URTEIL        : {urteil}")
    lines.append("═" * 46)

    level = logger.info if (ip_ok and dns_ok and tcp_ok) else logger.warning
    for line in lines:
        level(line)

    # Dauerhaft mitschreiben — das ist der Teil, der in der Werkstatt zaehlt
    # (dort laeuft die App ohne Developer-Mode und schreibt sonst NICHTS).
    if persist:
        write_network_report(lines, version=version, box_id=box_id)

    return {
        "ssid": ssid,
        "ips": ips,
        "ip_ok": ip_ok,
        "gateway_ok": gw_ok,
        "dns_ok": dns_ok,
        "dashboard_ok": tcp_ok,
        "urteil": urteil,
    }
