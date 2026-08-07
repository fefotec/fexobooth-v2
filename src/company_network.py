"""Firmennetzwerk-Erkennung + Auto-Update-Trigger

Erkennt ob die FexoBooth im Firmen-WLAN (fexon) hängt und triggert
dort still einen Update-Check gegen GitHub sowie optional einen kurzen
Software-Monitoring-Heartbeat ans Dashboard. Beim Kunden ist nie Internet,
also passiert nichts.

Ablauf beim App-Start (Background-Thread):
1. Aktive WLAN-SSID via `netsh wlan show interfaces` auslesen
2. Gegen Whitelist aus config prüfen (company_wifi_ssids)
3. Wenn Firmen-WLAN: Monitoring-Heartbeat senden, sofern konfiguriert
4. Wenn Auto-Update aktiv: check_for_update() aufrufen
5. Bei verfügbarem Update: download + apply + Neustart
"""

import json
import re
import socket
import subprocess
import threading
import time
from typing import Any, Dict, Optional, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.utils.logging import get_logger

logger = get_logger(__name__)

MONITORING_HTTP_TIMEOUT = 3
DEFAULT_MONITORING_TOKEN = "fexobooth-v2-monitoring-X2KWF8ZS5Ab4s1hy2sevRlaxkkGti5glvSZhcSpWh5o"


def get_active_ssid() -> Optional[str]:
    """Gibt die aktuell verbundene WLAN-SSID zurück (Windows).

    Nutzt `netsh wlan show interfaces`. Gibt None zurück wenn nicht
    verbunden, kein WLAN-Adapter, oder Fehler.
    """
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            timeout=5,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug(f"netsh wlan show interfaces fehlgeschlagen: {e}")
        return None

    # netsh gibt je nach Windows-Locale unterschiedliche Encodings zurück.
    # Versuche UTF-8, dann cp850 (deutsche Konsole), dann latin-1 als Fallback.
    raw = result.stdout
    for encoding in ("utf-8", "cp850", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        logger.debug("netsh-Output konnte nicht dekodiert werden")
        return None

    # "SSID" (nicht "BSSID") suchen — deutsches und englisches Windows liefern
    # beides als "SSID" / "BSSID". Wir matchen nur die Zeile die mit SSID beginnt,
    # nicht BSSID.
    for line in text.splitlines():
        stripped = line.strip()
        # BSSID aussortieren
        if stripped.lower().startswith("bssid"):
            continue
        m = re.match(r"^SSID\s*:\s*(.+)$", stripped, re.IGNORECASE)
        if m:
            ssid = m.group(1).strip()
            if ssid:
                return ssid
            return None

    return None


def is_company_wifi(ssid: Optional[str], whitelist: List[str]) -> bool:
    """Prüft ob die SSID auf der Firmen-Whitelist steht (case-sensitive)."""
    if not ssid or not whitelist:
        return False
    return ssid in whitelist


def _get_booking_id(app=None) -> str:
    """Liest die aktive Buchungs-ID, ohne den Startfluss davon abhängig zu machen."""
    if app is None:
        return ""

    booking_manager = getattr(app, "booking_manager", None)
    if booking_manager is None:
        return ""

    booking_id = getattr(booking_manager, "booking_id", "")
    return str(booking_id or "").strip()


def _send_monitoring_heartbeat(config: Dict[str, Any], ssid: str, app=None) -> None:
    """Sendet einen kurzen Software-Heartbeat ans Dashboard.

    Läuft nur mit expliziter 3-stelliger box_id und Endpoint. Der Token ist als
    Fallback eingebaut, damit keine Box einzeln provisioniert werden muss.
    Fehler werden bewusst nicht in den UI-Fluss getragen, damit Kundenbetrieb
    und Startzeit nicht von Netzwerk oder Dashboard abhängen.
    """
    if not config.get("monitoring_enabled", True):
        logger.debug("Monitoring: Deaktiviert")
        return

    box_id = str(config.get("box_id", "")).strip()
    if not re.fullmatch(r"\d{3}", box_id):
        logger.debug("Monitoring: Keine gültige 3-stellige Box-ID gesetzt — übersprungen")
        return

    endpoint = str(config.get("monitoring_endpoint", "")).strip()
    if not endpoint:
        logger.debug("Monitoring: monitoring_endpoint fehlt — übersprungen")
        return
    token = str(config.get("monitoring_token", "")).strip() or DEFAULT_MONITORING_TOKEN

    try:
        from src.updater import _SSL_CONTEXT, get_current_version
        ssl_context = _SSL_CONTEXT
        version = get_current_version()
    except Exception as e:
        logger.debug(f"Monitoring: Version/SSL-Kontext nicht ladbar, nutze Fallback: {e}")
        ssl_context = None
        version = "0.0.0"

    payload = {
        "box_id": box_id,
        "version": version,
        "hostname": socket.gethostname(),
        "booking_id": _get_booking_id(app),
        "source": "fexobooth-v2",
        "ssid": ssid,
    }

    data = json.dumps(payload).encode("utf-8")
    request = Request(
        endpoint,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "FexoBooth-Monitoring/1.0",
        },
        method="POST",
    )

    try:
        if ssl_context is not None:
            response = urlopen(request, timeout=MONITORING_HTTP_TIMEOUT, context=ssl_context)
        else:
            response = urlopen(request, timeout=MONITORING_HTTP_TIMEOUT)
        with response:
            logger.info(f"Monitoring: Version {version} für Box-ID {box_id} gemeldet")
    except HTTPError as e:
        try:
            error_body = e.read().decode("utf-8", errors="replace").strip()
        except Exception:
            error_body = ""
        details = f": {error_body[:300]}" if error_body else ""
        logger.warning(f"Monitoring: Dashboard lehnt Meldung ab (HTTP {e.code}){details}")
    except (URLError, TimeoutError, OSError) as e:
        logger.debug(f"Monitoring: Dashboard nicht erreichbar — übersprungen ({e})")
    except Exception as e:
        logger.debug(f"Monitoring: Heartbeat fehlgeschlagen — übersprungen ({e})")


def check_and_auto_update(
    whitelist: List[str],
    delay_seconds: float = 15.0,
    app=None,
    config: Optional[Dict[str, Any]] = None,
    update_enabled: bool = True,
) -> None:
    """Startet einen Background-Thread der nach `delay_seconds` prüft:
    1. Firmen-WLAN aktiv?
    2. Optional Software-Monitoring ans Dashboard melden.
    3. Optional Internet + GitHub erreichbar?
    4. Update verfügbar? → UpdateProgressDialog auf UI-Thread öffnen.
       Der Dialog erledigt Download + Apply + os._exit selbst und ist
       sichtbar (Fullscreen, MB-Counter), damit der Mitarbeiter erkennt
       was passiert (vor v2.4.1 lief das komplett unsichtbar).

    Beim Kunden ohne Internet passiert einfach nichts (ConnectionError wird
    geschluckt).

    Args:
        whitelist: Liste der Firmen-SSIDs aus config.company_wifi_ssids
        delay_seconds: Wartezeit nach App-Start bevor geprüft wird
                       (damit die App erst sauber hochfährt)
        app: PhotoboothApp-Instanz für UI-Dialog-Anzeige. Wenn None,
             fällt es auf den alten stillen Pfad zurück (Headless-Tests).
        config: Vollständige App-Konfiguration für Monitoring.
        update_enabled: Wenn False, wird nur Monitoring geprüft.
    """
    config = config or {}
    monitoring_enabled = bool(config.get("monitoring_enabled", True))

    if not whitelist:
        logger.debug("Firmennetzwerk: Keine Firmen-SSIDs konfiguriert — übersprungen")
        return

    if not update_enabled and not monitoring_enabled:
        logger.debug("Firmennetzwerk: Auto-Update und Monitoring deaktiviert — übersprungen")
        return

    def worker():
        # Kurz warten damit die App fertig hochfährt und WLAN-Verbindung stabil ist
        time.sleep(delay_seconds)

        ssid = get_active_ssid()
        if ssid is None:
            logger.debug("Auto-Update: Kein WLAN aktiv — übersprungen")
            return

        if not is_company_wifi(ssid, whitelist):
            logger.debug(f"Firmennetzwerk: SSID '{ssid}' nicht in Firmen-Whitelist — übersprungen")
            return

        logger.info(f"Firmennetzwerk: Firmen-WLAN erkannt ('{ssid}')")

        _send_monitoring_heartbeat(config, ssid, app)

        if not update_enabled:
            logger.debug("Auto-Update: Deaktiviert — nur Monitoring geprüft")
            return

        logger.info("Auto-Update: Prüfe auf Updates...")

        # Update-Check (wirft ConnectionError ohne Internet — Kundenbetrieb)
        try:
            from src.updater import check_for_update
        except ImportError as e:
            logger.warning(f"Auto-Update: Updater-Modul nicht ladbar: {e}")
            return

        try:
            release = check_for_update()
        except ConnectionError as e:
            logger.info(f"Auto-Update: Kein Internet / GitHub nicht erreichbar — still ignoriert ({e})")
            return
        except Exception as e:
            logger.warning(f"Auto-Update: Update-Check fehlgeschlagen: {e}")
            return

        if release is None:
            logger.info("Auto-Update: Bereits aktuell — nichts zu tun")
            return

        logger.info(f"Auto-Update: Neue Version verfügbar: {release['tag']} — öffne UpdateProgressDialog")

        # Dialog auf UI-Thread öffnen, sofern App-Instanz da ist
        if app is not None and hasattr(app, "root"):
            def open_dialog():
                try:
                    from src.ui.dialogs.update_progress import UpdateProgressDialog
                    UpdateProgressDialog(app.root, app, release)
                except Exception as e:
                    logger.error(f"Auto-Update: Dialog konnte nicht geöffnet werden: {e}", exc_info=True)
                    _silent_fallback(release)

            try:
                app.root.after(0, open_dialog)
                return
            except Exception as e:
                logger.warning(f"Auto-Update: app.root.after fehlgeschlagen, Fallback auf still: {e}")

        # Fallback: alter stiller Pfad (App-Instanz fehlt oder UI nicht erreichbar)
        _silent_fallback(release)

    t = threading.Thread(target=worker, name="AutoUpdateCheck", daemon=True)
    t.start()


def trigger_monitoring_heartbeat_now(app=None, config: Optional[Dict[str, Any]] = None) -> None:
    """Sendet einen Monitoring-Heartbeat sofort im Hintergrund.

    Wird z.B. nach dem Speichern der Box-ID genutzt. Prüft weiterhin Firmen-WLAN,
    Box-ID und Endpoint, damit im Kundenbetrieb nichts blockiert.
    """
    config = config or {}

    def worker():
        ssid = get_active_ssid()
        whitelist = config.get("company_wifi_ssids", [])
        if not is_company_wifi(ssid, whitelist):
            logger.debug("Monitoring-Sofortmeldung: Kein Firmen-WLAN — übersprungen")
            return

        logger.info("Monitoring-Sofortmeldung: Firmen-WLAN erkannt")
        _send_monitoring_heartbeat(config, ssid, app)

    t = threading.Thread(target=worker, name="MonitoringHeartbeatNow", daemon=True)
    t.start()


def _silent_fallback(release: dict) -> None:
    """Fallback ohne UI: Update wird NICHT mehr still installiert (seit 2.4.19).

    Updates brauchen eine Bestätigung am Screen (Bilder zurückkommender Boxen
    müssen vorher gesichert sein). Ohne UI gibt es keine Bestätigung — also
    nur loggen und beim nächsten Start mit UI erneut anbieten.
    """
    try:
        logger.warning(
            f"Auto-Update: Version {release.get('tag')} verfügbar, aber kein UI für die "
            f"Bestätigung erreichbar — Update wird NICHT automatisch installiert "
            f"(Bestätigungspflicht seit 2.4.19)"
        )
    except Exception as e:
        logger.error(f"Auto-Update (still): Fehlgeschlagen: {e}", exc_info=True)
