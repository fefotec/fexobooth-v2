"""Hotspot-Waechter + QR-Adresse (2.4.65). Braucht KEINE Box.

Sichert die drei Befunde vom 01./04.09.2026 (Box 155) und den Kundenfall
NX-142048 ab:
  1. Der QR-Code enthaelt NIE eine Firmen-WLAN- oder Notfalladresse.
  2. Der Waechter greift erst nach zwei Fehlpruefungen ein, dann mit Ruhezeit.
  3. Installer, Boot-Aufgabe und App sind wirklich verdrahtet (statisch).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.gallery.hotspot_watchdog import (  # noqa: E402
    MISSES_BEFORE_REPAIR,
    REPAIR_COOLDOWN_S,
    HotspotWatchdog,
    decide,
    describe_windows_idle_shutdown,
)
from src.gallery.server import HOTSPOT_DEFAULT_IP, choose_gallery_ip  # noqa: E402

# ── 1. QR-Adresse ────────────────────────────────────────────────

# Werkstatt am 04.09.: Hotspot noch aus, nur Firmen-WLAN-Adresse vorhanden.
ip, grund = choose_gallery_ip(["192.168.2.159"])
assert ip == HOTSPOT_DEFAULT_IP, f"Firmen-WLAN-Adresse im QR: {ip}"
assert "fehlt noch" in grund

# 01.09.: Hotspot "an", aber nur Notfalladresse + Firmen-WLAN.
ip, _ = choose_gallery_ip(["192.168.2.149", "169.254.14.101"])
assert ip == HOTSPOT_DEFAULT_IP

# Normalfall: Hotspot-Adresse da → genau die.
ip, grund = choose_gallery_ip(["192.168.2.159", "192.168.137.1"])
assert ip == "192.168.137.1" and grund.startswith("Hotspot-Adresse erkannt")

# Kunde ohne jedes Netz.
ip, _ = choose_gallery_ip([])
assert ip == HOTSPOT_DEFAULT_IP

# ── 2. Entscheidungslogik ────────────────────────────────────────

assert decide(True, 0, None) == "ok"
assert decide(True, 5, 10.0) == "ok"                       # Adresse da → immer ok
assert decide(False, 1, None) == "wait"                    # erste Luecke: abwarten
assert decide(False, MISSES_BEFORE_REPAIR, None) == "repair"
assert decide(False, MISSES_BEFORE_REPAIR, 10.0) == "cooldown"   # gerade repariert
assert decide(False, MISSES_BEFORE_REPAIR, REPAIR_COOLDOWN_S + 1) == "repair"
assert decide(False, 99, REPAIR_COOLDOWN_S - 1) == "cooldown"

# Waechter-Objekt: check_once() ohne echte Box (IP-Liste gefaelscht,
# Reparatur abgefangen), damit Zaehler und Ablauf stimmen.
import src.gallery.hotspot_watchdog as wd  # noqa: E402
import src.utils.network_diag as nd  # noqa: E402

_ips = {"list": ["192.168.137.1"]}
nd_orig = nd.get_local_ipv4s
nd.get_local_ipv4s = lambda: list(_ips["list"])
repariert = {"n": 0}


class _TestWatchdog(HotspotWatchdog):
    def _repair(self, ips_before):  # keine PowerShell im Test
        repariert["n"] += 1
        self.repairs += 1
        self.last_repair_at = 10_000.0
        self.last_result = "test-repariert"


try:
    w = _TestWatchdog("fexobox-gallery", "fotobox123")
    assert w.check_once() == "ok" and w.consecutive_misses == 0
    _ips["list"] = ["192.168.2.159"]                # Hotspot weg
    assert w.check_once() == "wait" and repariert["n"] == 0
    assert w.check_once() == "repair" and repariert["n"] == 1
    _ips["list"] = ["192.168.2.159", "192.168.137.1"]   # wieder da
    assert w.check_once() == "ok" and w.consecutive_misses == 0
    assert w.checks == 4 and w.repairs == 1
    assert "1 Reparaturen" in w.status_line()
finally:
    nd.get_local_ipv4s = nd_orig

# Klartext der Registrierungs-Auswertung (App liest nur).
assert describe_windows_idle_shutdown({"PeerlessTimeoutEnabled": 0, "PublicConnectionTimeoutEnabled": 0}).startswith("AUS")
txt = describe_windows_idle_shutdown({"PeerlessTimeoutEnabled": None, "PublicConnectionTimeoutEnabled": 1})
assert txt.startswith("AKTIV") and "fehlt: PeerlessTimeoutEnabled" in txt and "aktiv: PublicConnectionTimeoutEnabled" in txt

# ── 3. Verdrahtung (statisch) ────────────────────────────────────

iss = (ROOT / "installer.iss").read_text(encoding="utf-8", errors="replace")
zeile = [z for z in iss.splitlines() if "hotspot_keepalive.ps1" in z and z.startswith("Filename:")]
assert zeile, "Installer ruft hotspot_keepalive.ps1 nicht auf"
assert "waituntilterminated" in zeile[0] and "postinstall" not in zeile[0], \
    "Keepalive muss Pflicht-Schritt sein (kein postinstall-Haekchen)"
assert "Tasks:" not in zeile[0], "Keepalive darf an keiner Checkbox haengen"

keepalive = (ROOT / "setup" / "hotspot_keepalive.ps1").read_text(encoding="utf-8", errors="replace")
for name in ("PeerlessTimeoutEnabled", "PublicConnectionTimeoutEnabled"):
    assert name in keepalive, f"{name} fehlt im Keepalive-Script"
assert "icssvc" in keepalive and "exit 0" in keepalive

lockdown = (ROOT / "setup" / "disable_windows_update.ps1").read_text(encoding="utf-8", errors="replace")
assert "hotspot_keepalive.ps1" in lockdown, "Boot-Aufgabe ruft Keepalive nicht auf"

app_py = (ROOT / "src" / "app.py").read_text(encoding="utf-8")
assert "start_hotspot_watchdog(" in app_py and "stop_hotspot_watchdog()" in app_py

hotspot_py = (ROOT / "src" / "gallery" / "hotspot.py").read_text(encoding="utf-8")
assert "_hotspot_lock" in hotspot_py and "with _hotspot_lock:" in hotspot_py

print("BESTANDEN: QR nur ueber Hotspot-Adresse; Waechter wartet, repariert, ruht; Installer + Boot-Aufgabe verdrahtet.")
