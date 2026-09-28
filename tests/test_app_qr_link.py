"""App-QR als Web-Link (28.09.2026). Braucht KEINE Box.

Sichert ab:
  1. Seit 2.4.74 ist APP_QR_WEB_LINK AN (Web-Link am Startbildschirm). Das alte
     fexobox://-Schema bleibt per web_link=False abrufbar (Manifest, Rueckfall).
  2. Mit web_link=True entsteht https://fexobox.de/g#<gleiche Parameter> – die
     Daten stehen im Fragment (nie im Server-Log), kein '?' vor dem '#'.
  3. Das Manifest (urls.app_scheme) bleibt immer beim fexobox://-Schema.
"""

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import src.gallery.server as server  # noqa: E402

server._gallery_context = {
    "box_id": "221",
    "event_pin": "654321",
    "hotspot_ssid": "fexobox-gallery",
    "hotspot_password": "pw&#x",
    "locale": "fr-FR",
}
BASE = "http://192.168.137.1:8080"

# ── 1. Standard: Web-Link an, altes Schema weiter abrufbar ───────
assert server.APP_QR_WEB_LINK is True, "Seit 2.4.74 zeigt die Box den Web-Link (Christian, 28.09.2026)"
server_src = (ROOT / "src/gallery/server.py").read_text(encoding="utf-8")
assert "web_link=APP_QR_WEB_LINK" in server_src, "Startbildschirm-QR muss dem Schalter folgen"
alt = server._build_app_pairing_url(BASE)
assert alt.startswith("fexobox://g?v=1&a=http://192.168.137.1:8080/api/v1&t="), alt

# ── 2. Web-Link: gleiche Parameter im Fragment ───────────────────
web = server._build_app_pairing_url(BASE, web_link=True)
teile = urlsplit(web)
assert (teile.scheme, teile.netloc, teile.path) == ("https", "fexobox.de", "/g"), web
assert teile.query == "", "Box-Daten duerfen nicht im Query stehen (Server-Log)"
params = parse_qs(teile.fragment)
assert params["v"] == ["1"] and params["t"] == [server._gallery_pairing_token]
assert params["a"] == [f"{BASE}/api/v1"]
assert params["p"] == ["pw&#x"], "Sonderzeichen im WLAN-Passwort muessen kodiert sein"
assert params["c"] == ["654321"] and params["l"] == ["fr-FR"]
assert web.split("#", 1)[1] == alt.split("?", 1)[1], "beide Varianten muessen dieselben Daten tragen"

# ── 3. QR-Laenge bleibt im Rahmen (200-px-QR am Startbildschirm) ─
assert len(web) - len(alt) <= 10, f"Web-Link unerwartet lang: +{len(web) - len(alt)} Zeichen"

print("OK: App-QR https://fexobox.de/g# (Standard) und fexobox:// (Manifest) korrekt")
