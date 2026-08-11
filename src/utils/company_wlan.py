"""Firmen-WLAN-Selbstheilung (2.4.22)

Hintergrund (Christian, 2026-08-11): 47 Flotten-Boxen melden sich nie im
Dashboard, weil sie sich nicht ins Firmen-WLAN einbuchen. Ein Mitarbeiter-Fix
(exportiertes Profil importieren) half nur teilweise — das exportierte
Passwort ist maschinengebunden verschlüsselt und passt nur auf Boxen mit
identischem Klon-Image. Dieses Modul erzeugt das Profil deshalb SELBST mit
Klartext-Schlüssel (funktioniert auf jeder Box) und den zwei entscheidenden
Einstellungen: automatisch verbinden = an, MAC-Randomisierung = aus.

Sicherer Auslöser der Automatik: NUR wenn das Firmen-WLAN im Funk SICHTBAR,
aber nicht verbunden ist (= Box steht in der Werkstatt und es klemmt).
Beim Kunden ist das Netz nie sichtbar → dort löst nie etwas aus.
"""

import os
import re
import subprocess
import tempfile
import time
from typing import List, Optional, Tuple

from src.utils.logging import get_logger

logger = get_logger(__name__)

COMPANY_WLAN_SSID = "fexon WLAN"
COMPANY_WLAN_PASSPHRASE = "68045370152863146883"

# Erkenntnis Mitarbeiter (2026-08-11): Boxen sollen sich nur mit EINEM
# Firmen-WLAN verbinden. Gespeicherte Profile fuer mehrere fexon-Netze mit
# Auto-Verbinden lassen Windows zwischen den Netzen springen bzw. am
# schwaecheren kleben. Diese Alt-Profile werden bei der Selbstheilung
# entfernt (NUR Verbindungs-Profile — die Erkennungs-Whitelist in der
# Config bleibt unberuehrt).
OTHER_COMPANY_SSIDS = [
    "fexon_Buero_WLAN2",
    "fexon_Buero_WLAN2_5GHZ",
    "fexon Gast-WLAN",
    "fexon_outdoor",
]

_CREATE_NO_WINDOW = 0x08000000

# Profil-Vorlage: WPA2-PSK/AES, Auto-Verbinden, MAC-Randomisierung AUS
# (zufällige MAC-Adressen bringen manche Router/DHCP durcheinander — das war
# sehr wahrscheinlich die Kernursache der Anmelde-Probleme).
_PROFILE_TEMPLATE = """<?xml version=\"1.0\"?>
<WLANProfile xmlns=\"http://www.microsoft.com/networking/WLAN/profile/v1\">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID>
            <hex>{ssid_hex}</hex>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{passphrase}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
    <MacRandomization xmlns=\"http://www.microsoft.com/networking/WLAN/profile/v3\">
        <enableRandomization>false</enableRandomization>
    </MacRandomization>
</WLANProfile>
"""


def _run_netsh(args: List[str], timeout: int = 25) -> Tuple[int, str]:
    """Führt netsh aus (ohne Fenster) und liefert (Returncode, Ausgabe)."""
    try:
        result = subprocess.run(
            ["netsh"] + args,
            capture_output=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
        output = (result.stdout or b"").decode("utf-8", errors="replace")
        output += (result.stderr or b"").decode("utf-8", errors="replace")
        return result.returncode, output
    except Exception as e:
        return 1, str(e)


def get_connected_ssid() -> Optional[str]:
    """Aktuell verbundene SSID (sprachunabhängig: SSID-Zeile erscheint nur
    bei bestehender Verbindung in `netsh wlan show interfaces`)."""
    code, output = _run_netsh(["wlan", "show", "interfaces"])
    if code != 0:
        return None
    for line in output.splitlines():
        stripped = line.strip()
        if re.match(r"^SSID\s*:", stripped) and "BSSID" not in stripped:
            value = stripped.split(":", 1)[1].strip()
            if value:
                return value
    return None


def is_company_wlan_visible() -> bool:
    """Ist das Firmen-WLAN gerade im Funk sichtbar? (Scan-Ergebnis)"""
    code, output = _run_netsh(["wlan", "show", "networks"])
    if code != 0:
        return False
    for line in output.splitlines():
        stripped = line.strip()
        if re.match(r"^SSID\s+\d+\s*:", stripped):
            value = stripped.split(":", 1)[1].strip()
            if value == COMPANY_WLAN_SSID:
                return True
    return False


def ensure_company_wlan_profile() -> bool:
    """Legt das Firmen-WLAN-Profil frisch an (überschreibt Vorhandenes).

    Erst für alle Benutzer (braucht Adminrechte), sonst Fallback auf den
    aktuellen Benutzer — für den Kiosk-Betrieb reicht das.
    """
    xml = _PROFILE_TEMPLATE.format(
        ssid=COMPANY_WLAN_SSID,
        ssid_hex=COMPANY_WLAN_SSID.encode("utf-8").hex().upper(),
        passphrase=COMPANY_WLAN_PASSPHRASE,
    )

    profile_path = os.path.join(tempfile.gettempdir(), "fexobooth_company_wlan.xml")
    try:
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(xml)

        code, output = _run_netsh(
            ["wlan", "add", "profile", f"filename={profile_path}", "user=all"]
        )
        if code != 0:
            logger.debug(f"WLAN-Profil user=all fehlgeschlagen ({output.strip()[:120]}) — versuche user=current")
            code, output = _run_netsh(
                ["wlan", "add", "profile", f"filename={profile_path}", "user=current"]
            )

        if code == 0:
            logger.info(f"WLAN-Selbstheilung: Profil '{COMPANY_WLAN_SSID}' frisch angelegt (auto-connect an, MAC-Randomisierung aus)")
            return True

        logger.warning(f"WLAN-Selbstheilung: Profil konnte nicht angelegt werden: {output.strip()[:200]}")
        return False
    finally:
        try:
            os.remove(profile_path)  # Klartext-Passwort nicht liegen lassen
        except OSError:
            pass


def remove_other_company_profiles() -> int:
    """Löscht gespeicherte Profile der ANDEREN fexon-Netze (nur ein
    Verbindungs-Profil pro Box — Erkenntnis Mitarbeiter 2026-08-11)."""
    removed = 0
    for ssid in OTHER_COMPANY_SSIDS:
        code, _ = _run_netsh(["wlan", "delete", "profile", f"name={ssid}"])
        if code == 0:
            removed += 1
            logger.info(f"WLAN-Selbstheilung: Alt-Profil '{ssid}' entfernt (nur 'fexon WLAN' bleibt)")
    return removed


def connect_company_wlan() -> None:
    """Stößt die Verbindung mit dem Firmen-WLAN an (asynchron in Windows)."""
    _run_netsh(["wlan", "connect", f"name={COMPANY_WLAN_SSID}"])


def self_heal_company_wlan(wait_seconds: int = 20) -> str:
    """Kompletter Selbstheilungs-Ablauf. Rückgabe:

    - 'already_connected' — Firmen-WLAN steht bereits, nichts zu tun
    - 'not_visible'       — Firmen-WLAN nicht im Funk (Box beim Kunden) → no-op
    - 'connected'         — repariert und erfolgreich verbunden
    - 'failed'            — sichtbar, aber Verbindung kam trotz Reparatur nicht
    """
    connected = get_connected_ssid()
    if connected == COMPANY_WLAN_SSID:
        return "already_connected"

    if not is_company_wlan_visible():
        return "not_visible"

    logger.info(
        f"WLAN-Selbstheilung: '{COMPANY_WLAN_SSID}' ist sichtbar, aber nicht verbunden "
        f"(aktuell: {connected or 'kein WLAN'}) — repariere Profil und verbinde..."
    )

    remove_other_company_profiles()
    ensure_company_wlan_profile()
    connect_company_wlan()

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        time.sleep(2)
        if get_connected_ssid() == COMPANY_WLAN_SSID:
            logger.info("WLAN-Selbstheilung: Erfolgreich mit Firmen-WLAN verbunden ✓")
            return "connected"

    logger.warning(
        f"WLAN-Selbstheilung: Keine Verbindung nach {wait_seconds}s — "
        f"harter Fall (3198-Menü → WLAN-Radikal-Reparatur, oder Werkstatt-Skript)"
    )
    return "failed"


def radical_network_reset() -> List[str]:
    """Radikal-Reparatur für harte Fälle (3198-Menü, Werkstatt).

    Windows-Netzwerk auf Werkszustand: TCP/IP-Stack + Winsock zurücksetzen,
    DNS-Cache leeren, ALLE WLAN-Profile löschen und das Firmen-WLAN-Profil
    sofort frisch anlegen (wichtig: der Gäste-Hotspot braucht mindestens ein
    gespeichertes Profil!). Danach ist ein NEUSTART PFLICHT — macht der
    Aufrufer. Rückgabe: Ergebniszeilen pro Schritt fürs Log/UI.
    """
    results = []

    steps = [
        ("TCP/IP-Stack zurücksetzen", ["int", "ip", "reset"]),
        ("Winsock zurücksetzen", ["winsock", "reset"]),
    ]
    for name, args in steps:
        code, output = _run_netsh(args, timeout=40)
        ok = code == 0
        results.append(f"{name}: {'ok' if ok else 'FEHLER'}")
        logger.info(f"WLAN-Radikal-Reparatur: {name}: {'ok' if ok else 'FEHLER — ' + output.strip()[:150]}")

    try:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=15,
                       creationflags=_CREATE_NO_WINDOW)
        results.append("DNS-Cache leeren: ok")
        logger.info("WLAN-Radikal-Reparatur: DNS-Cache geleert")
    except Exception as e:
        results.append("DNS-Cache leeren: FEHLER")
        logger.warning(f"WLAN-Radikal-Reparatur: flushdns fehlgeschlagen: {e}")

    code, _ = _run_netsh(["wlan", "delete", "profile", "name=*"])
    results.append(f"Alle WLAN-Profile löschen: {'ok' if code == 0 else 'FEHLER'}")
    logger.info(f"WLAN-Radikal-Reparatur: Profile gelöscht ({'ok' if code == 0 else 'Fehler'})")

    # SOFORT wieder ein Profil anlegen — nie mit 0 Profilen zum Kunden
    # (Tethering-API/Hotspot braucht mindestens ein gespeichertes Profil)
    profile_ok = ensure_company_wlan_profile()
    results.append(f"Firmen-WLAN-Profil neu anlegen: {'ok' if profile_ok else 'FEHLER'}")

    connect_company_wlan()
    results.append("Neustart erforderlich!")
    logger.info("WLAN-Radikal-Reparatur: Abgeschlossen — Neustart erforderlich")
    return results
