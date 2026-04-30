"""Firmennetzwerk-Erkennung + Auto-Update-Trigger

Erkennt ob die FexoBooth im Firmen-WLAN (fexon) hängt und triggert
dort still einen Update-Check gegen GitHub. Beim Kunden ist nie Internet,
also passiert nichts.

Ablauf beim App-Start (Background-Thread):
1. Aktive WLAN-SSID via `netsh wlan show interfaces` auslesen
2. Gegen Whitelist aus config prüfen (company_wifi_ssids)
3. Wenn Firmen-WLAN: check_for_update() aufrufen (wirft ConnectionError ohne Internet)
4. Bei verfügbarem Update: download + apply + Neustart
"""

import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, List

from src.utils.logging import get_logger

logger = get_logger(__name__)


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


def check_and_auto_update(
    whitelist: List[str],
    delay_seconds: float = 15.0,
    app=None,
) -> None:
    """Startet einen Background-Thread der nach `delay_seconds` prüft:
    1. Firmen-WLAN aktiv?
    2. Internet + GitHub erreichbar?
    3. Update verfügbar? → UpdateProgressDialog auf UI-Thread öffnen.
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
    """
    if not whitelist:
        logger.debug("Auto-Update: Keine Firmen-SSIDs konfiguriert — übersprungen")
        return

    def worker():
        # Kurz warten damit die App fertig hochfährt und WLAN-Verbindung stabil ist
        time.sleep(delay_seconds)

        ssid = get_active_ssid()
        if ssid is None:
            logger.debug("Auto-Update: Kein WLAN aktiv — übersprungen")
            return

        if not is_company_wifi(ssid, whitelist):
            logger.debug(f"Auto-Update: SSID '{ssid}' nicht in Firmen-Whitelist — übersprungen")
            return

        logger.info(f"Auto-Update: Firmen-WLAN erkannt ('{ssid}') — prüfe auf Updates...")

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


def _silent_fallback(release: dict) -> None:
    """Stiller Update-Pfad ohne UI — Fallback wenn der Dialog nicht geöffnet werden kann."""
    try:
        from src.updater import download_update, apply_update_and_restart
        zip_path = download_update(release["download_url"])
        logger.info(f"Auto-Update (still): Download fertig ({zip_path}) — wende an")
        apply_update_and_restart(zip_path)
        logger.info("Auto-Update (still): Beende App per os._exit damit BAT übernehmen kann")
        import os
        os._exit(0)
    except Exception as e:
        logger.error(f"Auto-Update (still): Fehlgeschlagen: {e}", exc_info=True)
