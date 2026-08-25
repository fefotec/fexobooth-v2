"""Log-Versand ans Dashboard (2.4.46).

ANLASS (Christian, 21.08.2026): "hier in der firma haben die boxen doch wlan!
koennen wir nicht einen button einbauen der die logs an das laravel dashboard
schickt > dann kannst du sie direkt lesen und ich muss nicht immer mit dem
stick hin und her kopieren?"

Bisher lief jede Fehlersuche so: USB-Stick in die Box, Logs kopieren, Stick
zum PC tragen. Bei mehreren Testrunden am Tag ist das der groesste Zeitfresser
— und bei einer Box beim Kunden gar nicht moeglich.

WIE ES FUNKTIONIERT: Die Box packt ihre juengsten Logdateien und schickt sie an
denselben Dashboard-Kanal, ueber den sie ohnehin schon ihren Heartbeat meldet
(`monitoring_endpoint` / `monitoring_token`). Dadurch muss keine der ~280 Boxen
neu provisioniert werden.

BEWUSST OHNE FREMDE BIBLIOTHEKEN: `urllib` aus der Standardbibliothek, wie im
restlichen Netzwerk-Code der Box. Ein zusaetzliches Paket waere Ballast im
PyInstaller-Build.
"""

import base64
import gzip
import json
import os
import re
import socket
import ssl
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Grosszuegig, aber nicht endlos: ein Box-Log ist gepackt meist unter 200 KB.
MAX_GEPACKT_BYTES = 12 * 1024 * 1024
HTTP_TIMEOUT = 45


def _endpoint_fuer_logs(config: Dict[str, Any]) -> Optional[str]:
    """Leitet die Log-Adresse aus dem bekannten Heartbeat-Endpunkt ab.

    Aus  https://admin.fexobox.de/api/booth/heartbeat
    wird https://admin.fexobox.de/api/booth/logs

    So muss in der Konfiguration der Boxen NICHTS geaendert werden — die
    Heartbeat-Adresse steht dort seit Langem und ist erprobt.
    """
    roh = str(config.get("log_upload_endpoint", "")).strip()
    if roh:
        return roh

    heartbeat = str(config.get("monitoring_endpoint", "")).strip()
    if not heartbeat:
        return None

    if heartbeat.endswith("/heartbeat"):
        return heartbeat[: -len("/heartbeat")] + "/logs"

    return heartbeat.rstrip("/") + "/logs"


def _art_aus_dateiname(name: str) -> str:
    """Grobe Einordnung fuers Dashboard, damit man die Liste ueberfliegen kann."""
    klein = name.lower()
    if "absturz" in klein:
        return "absturz"
    if "netzwerk" in klein:
        return "netzwerk"
    if "update" in klein or "lockdown" in klein:
        return "update"
    if "company_wlan" in klein:
        return "wlan"
    return "app"


def sammle_logdateien(log_pfad: Path, max_dateien: int = 6) -> List[Path]:
    """Sucht die juengsten Logdateien der Box zusammen.

    Bewusst begrenzt: Es geht um die letzte Testrunde, nicht um ein Archiv.
    Die App-Logs sind die wichtigsten, deshalb stehen sie zuerst in der Liste.
    """
    if not log_pfad.exists():
        logger.warning(f"Log-Versand: Ordner existiert nicht: {log_pfad}")
        return []

    kandidaten: List[Path] = []
    for muster in ("fexobooth_*.log", "*.log", "*.txt"):
        for p in log_pfad.glob(muster):
            if p.is_file() and p not in kandidaten:
                kandidaten.append(p)

    # Juengste zuerst
    kandidaten.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return kandidaten[:max_dateien]


def _sende_eine_datei(
    datei: Path,
    endpoint: str,
    token: str,
    box_id: str,
    version: str,
    notiz: str,
    ssl_context: Optional[ssl.SSLContext],
) -> Tuple[bool, str]:
    """Packt eine Datei und schickt sie hoch. (Erfolg, Klartext-Meldung)"""
    try:
        roh = datei.read_bytes()
    except Exception as e:
        return False, f"{datei.name}: nicht lesbar ({e})"

    if not roh:
        return False, f"{datei.name}: leer, übersprungen"

    try:
        gepackt = gzip.compress(roh, compresslevel=6)
    except Exception as e:
        return False, f"{datei.name}: Packen fehlgeschlagen ({e})"

    if len(gepackt) > MAX_GEPACKT_BYTES:
        return False, f"{datei.name}: zu groß ({len(gepackt)//1024//1024} MB gepackt)"

    payload = {
        "box_id": box_id,
        "filename": datei.name,
        "content_gzip_b64": base64.b64encode(gepackt).decode("ascii"),
        "original_size": len(roh),
        "software_version": version,
        "hostname": socket.gethostname(),
        "kind": _art_aus_dateiname(datei.name),
        "note": notiz or None,
    }

    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "FexoBooth-LogUpload/1.0",
        },
        method="POST",
    )

    try:
        if ssl_context is not None:
            antwort = urlopen(request, timeout=HTTP_TIMEOUT, context=ssl_context)
        else:
            antwort = urlopen(request, timeout=HTTP_TIMEOUT)
        with antwort:
            pass
        kb_roh = len(roh) // 1024
        kb_gepackt = len(gepackt) // 1024
        logger.info(f"Log-Versand: {datei.name} gesendet ({kb_roh} KB -> {kb_gepackt} KB gepackt)")
        return True, f"{datei.name} ({kb_roh} KB)"
    except HTTPError as e:
        try:
            text = e.read().decode("utf-8", errors="replace").strip()[:200]
        except Exception:
            text = ""
        logger.error(f"Log-Versand: {datei.name} abgelehnt — HTTP {e.code} {text}")

        if e.code == 401:
            return False, f"{datei.name}: Dashboard lehnt den Zugang ab (Token)"
        if e.code == 404:
            return False, f"{datei.name}: Dashboard kennt die Adresse nicht (Update nötig?)"
        if e.code == 413:
            return False, f"{datei.name}: zu groß fürs Dashboard"
        return False, f"{datei.name}: Dashboard-Fehler {e.code}"
    except URLError as e:
        logger.error(f"Log-Versand: {datei.name} — kein Netz ({e.reason})")
        return False, f"{datei.name}: kein Netzzugang ({e.reason})"
    except Exception as e:
        logger.error(f"Log-Versand: {datei.name} — unerwarteter Fehler: {e}")
        return False, f"{datei.name}: Fehler ({e})"


def sende_logs(
    config: Dict[str, Any],
    log_pfad: Path,
    notiz: str = "",
    fortschritt: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Schickt die juengsten Logs der Box ans Dashboard.

    Args:
        config: Box-Konfiguration (liefert box_id, Endpunkt und Token)
        log_pfad: Ordner mit den Logdateien
        notiz: Freitext, der im Dashboard neben dem Log steht
        fortschritt: wird pro Schritt mit einem kurzen Text aufgerufen (fuer die UI)

    Returns:
        {"ok": bool, "gesendet": int, "meldung": str, "details": [str, ...]}
    """
    def melde(text: str):
        logger.info(f"Log-Versand: {text}")
        if fortschritt:
            try:
                fortschritt(text)
            except Exception:
                pass

    box_id = str(config.get("box_id", "")).strip()
    if not re.fullmatch(r"\d{3}", box_id):
        return {
            "ok": False,
            "gesendet": 0,
            "meldung": "Diese Box hat keine gültige 3-stellige Box-Nummer.\n"
                       "Im Service-Menü unter „Box-ID\" eintragen, dann erneut versuchen.",
            "details": [],
        }

    endpoint = _endpoint_fuer_logs(config)
    if not endpoint:
        return {
            "ok": False,
            "gesendet": 0,
            "meldung": "Es ist keine Dashboard-Adresse hinterlegt.",
            "details": [],
        }

    token = str(config.get("monitoring_token", "")).strip()
    if not token:
        try:
            from src.company_network import DEFAULT_MONITORING_TOKEN
            token = DEFAULT_MONITORING_TOKEN
        except Exception:
            pass

    if not token:
        return {
            "ok": False,
            "gesendet": 0,
            "meldung": "Es ist kein Zugangsschlüssel fürs Dashboard hinterlegt.",
            "details": [],
        }

    try:
        from src.updater import _SSL_CONTEXT, get_current_version
        ssl_context = _SSL_CONTEXT
        version = get_current_version()
    except Exception:
        ssl_context = None
        version = "0.0.0"

    dateien = sammle_logdateien(log_pfad)
    if not dateien:
        return {
            "ok": False,
            "gesendet": 0,
            "meldung": f"Im Ordner {log_pfad} liegen keine Logdateien.",
            "details": [],
        }

    melde(f"{len(dateien)} Datei(en) gefunden, sende an das Dashboard …")

    gesendet = 0
    details: List[str] = []
    fehler: List[str] = []

    for i, datei in enumerate(dateien, start=1):
        melde(f"Sende {i}/{len(dateien)}: {datei.name} …")
        erfolg, text = _sende_eine_datei(
            datei, endpoint, token, box_id, version, notiz, ssl_context
        )
        if erfolg:
            gesendet += 1
            details.append("✓ " + text)
        else:
            fehler.append("✗ " + text)

            # Bei Zugangs- oder Adressproblemen bringt es nichts, die
            # restlichen Dateien auch noch durchzuprobieren.
            if "Token" in text or "Adresse" in text or "kein Netzzugang" in text:
                melde("Abbruch — das Grundproblem betrifft alle Dateien.")
                break

    if gesendet == 0:
        return {
            "ok": False,
            "gesendet": 0,
            "meldung": "Es konnte keine Datei gesendet werden.\n\n" + "\n".join(fehler[:5]),
            "details": fehler,
        }

    meldung = f"{gesendet} von {len(dateien)} Datei(en) ans Dashboard gesendet.\n\n"
    meldung += "\n".join(details[:8])
    if fehler:
        meldung += "\n\nNicht gesendet:\n" + "\n".join(fehler[:4])
    meldung += f"\n\nIm Dashboard zu finden unter „Box-Logs\" → Box {box_id}."

    return {
        "ok": True,
        "gesendet": gesendet,
        "meldung": meldung,
        "details": details + fehler,
    }
