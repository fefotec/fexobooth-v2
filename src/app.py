"""
Fexobooth - Hauptanwendung
Moderne Photobooth-Software für fexobox
"""

import customtkinter as ctk
from typing import Dict, Any, Optional, List
from pathlib import Path
from PIL import Image
import os
import sys
import time
import threading
import random
import atexit

from src import __version__
from src.config.config import (
    load_config,
    reset_event_defaults,
    save_config,
    vorschau_aufloesung,
)
from src.camera import get_camera_manager, CANON_AVAILABLE, NIKON_AVAILABLE
from src.storage.local import get_shared_usb_manager
from src.storage.local import LocalStorage
from src.storage.booking import get_booking_manager, BookingManager
from src.storage.statistics import get_statistics_manager, StatisticsManager
from src.filters import FilterManager
from src.templates.loader import TemplateLoader
from src.templates.renderer import TemplateRenderer
from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger
from src.i18n import apply_locale_to_config, t

logger = get_logger(__name__)

TOPBAR_PRINTER_ERROR_KEYS = {
    "KEIN DRUCKER!": "topbar.printer_no_printer",
    "DRUCKER AUS!": "topbar.printer_off",
    "PAPIER LEER!": "topbar.printer_no_paper",
    "KASSETTE LEER!": "topbar.printer_cassette_empty",
    "PAPIERSTAU!": "topbar.printer_paper_jam",
    "KLAPPE OFFEN!": "topbar.printer_cover_open",
    "DRUCKER PRÜFEN!": "topbar.printer_check",
    "DRUCKER FEHLER!": "topbar.printer_error",
    "DRUCKER FEHLT!": "topbar.printer_missing",
    "KASSETTE FALSCH!": "topbar.printer_cassette_wrong",
    "PAPIER/KASSETTE LEER!": "topbar.printer_paper_cassette_empty",
    "DRUCK BLOCKIERT!": "topbar.print_blocked",
    "DRUCKER OFFLINE!": "topbar.printer_offline",
    "DRUCK-FEHLER!": "topbar.print_error",
    "KEIN PAPIER / KASSETTE!": "topbar.printer_no_paper_cassette",
    "KEINE TINTENKASSETTE!": "topbar.printer_no_ink_cassette",
    "TINTE LEER!": "topbar.printer_ink_empty",
    "KASSETTE PRÜFEN!": "topbar.printer_check_cassette",
}


class PhotoboothApp:
    """Hauptanwendungsklasse"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        apply_locale_to_config(self.config)

        # Windows-Leistung sicherstellen (2.4.16): Prozess-Priorität anheben
        # und den Leistungsregler auf "Beste Leistung" stellen. Der Miix
        # drosselt im Standard-Modus spürbar; Hintergrundlast (Defender/
        # Update) darf die Kiosk-UI nicht aushungern.
        try:
            from src.utils.system_load import boost_process_priority, set_best_performance_power_overlay
            boost_process_priority()
            set_best_performance_power_overlay()
        except Exception as e:
            logger.debug(f"Windows-Leistungseinstellungen fehlgeschlagen: {e}")


        # CustomTkinter Setup
        ctk.set_appearance_mode("dark")
        
        # Hauptfenster
        self.root = ctk.CTk()
        self.root.title("Fexobooth")
        self.root.configure(fg_color=COLORS["bg_dark"])

        # 2.4.30: Fehler aus Tk-Callbacks abfangen, BEVOR irgendein Screen läuft.
        # Ohne das geht Tkinter über sys.stderr — im Fenster-Build ist der aber
        # None, der Fehler-Handler stirbt selbst und reisst die App mit. Genau
        # das erklärt die Abstürze, die sich im Developer-Mode nie zeigen
        # (dort gibt es eine Konsole). Siehe src/utils/crashlog.py.
        try:
            from src.utils.crashlog import install_tk_exception_handler
            if install_tk_exception_handler(self.root, logger):
                logger.debug("Tk-Fehler-Handler aktiv (Absturz-Schutz)")
        except Exception as e:
            logger.debug(f"Tk-Fehler-Handler nicht gesetzt: {e}")

        # Fenster-Icon setzen
        self._set_window_icon()

        # App-Referenz am Root speichern (für Service-Menü Zugriff)
        self.root._photobooth_app = self
        self._mainloop_started = False
        
        # Bildschirmgröße ermitteln
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        logger.info(f"Bildschirm: {screen_width}x{screen_height}")
        
        # Sicherheitsnetz: Bei JEDEM App-Ende Taskleiste wiederherstellen
        # atexit wird auch bei unbehandelten Exceptions aufgerufen (nicht bei SIGKILL/Stromausfall)
        atexit.register(self._restore_taskbar_safe)

        # Fullscreen wenn konfiguriert
        self._is_fullscreen = False
        if config.get("start_fullscreen", True):
            self._enter_fullscreen()
        else:
            # Fenster zentriert anzeigen
            self.root.geometry(f"{screen_width}x{screen_height}+0+0")
        
        # Escape zum Beenden / F11 zum Toggle
        self.root.bind("<Escape>", lambda e: self._toggle_fullscreen())
        self.root.bind("<F11>", lambda e: self._toggle_fullscreen())

        # Maximize-Klick abfangen → direkt in Kiosk-Vollbild wechseln
        self.root.bind("<Configure>", self._on_window_configure)

        # Notfall-Shortcut: Ctrl+Shift+Q beendet die App sofort (auch im Kiosk-Modus)
        self.root.bind("<Control-Shift-Q>", lambda e: self._emergency_quit())
        self.root.bind("<Control-Shift-q>", lambda e: self._emergency_quit())

        self.booking_manager = get_booking_manager()
        self._startup_loading_frame = None
        self._startup_loading_name_label = None
        self._startup_loading_status_label = None
        self._show_startup_loading_screen()

        # Manager initialisieren
        camera_type = config.get("camera_type", "webcam")
        self._camera_type = camera_type
        # Zuletzt angewandter Stand des HD-Dauerbetrieb-Schalters (2.4.43).
        # Wird gebraucht, um nach dem Admin-Speichern zu erkennen, dass die
        # Kamera in einer ANDEREN Aufloesung neu geoeffnet werden muss.
        self._camera_dauerbetrieb_hd = True  # 2.4.45: fest, kein Schalter mehr
        self.camera_manager = get_camera_manager(camera_type, config=self.config)
        logger.info(
            f"Kamera-Typ: {camera_type} "
            f"(Canon verfügbar: {CANON_AVAILABLE}, Nikon verfügbar: {NIKON_AVAILABLE})"
        )
        self._pump_startup_loading_screen()

        # Webcam: Automatisch beste EXTERNE Kamera wählen — im HINTERGRUND
        # (2.4.23). Die Suche lief früher über eine PowerShell-Geräte-
        # Enumeration, die auf dem Miix beim Kaltstart unter Last bis ~16s
        # brauchte/timeoutete; früher blockierte das den Startup-Thread
        # komplett (Ladebalken fror ein, Box startete zunächst „ohne Kamera").
        # Jetzt läuft es nebenher; der laufende Kamera-Wächter
        # (_check_camera_status) korrigiert den Index, sobald die Kamera
        # gefunden ist. Seit 2.4.40 läuft die Namensabfrage in-process
        # (ctypes, wenige Millisekunden statt Sekunden).
        # Wurde der aktuelle camera_index in DIESEM Lauf per Gerätename als
        # externe Kamera bestätigt? Muss VOR dem Start des Suchthreads stehen
        # (sonst überschreibt die spätere Initialisierung das Ergebnis wieder).
        # Solange das False ist, gilt ein camera_index nur dann als brauchbar,
        # wenn es einen echten Beweis dafür gibt — der Grundwert 0 aus
        # defaults.py ist auf dem Miix die abgeklebte interne Kamera.
        self._camera_index_bestaetigt = False
        if camera_type == "webcam":
            def _auto_select_webcam():
                try:
                    from src.camera.webcam import WebcamManager
                    available = WebcamManager.list_cameras()
                    befund = WebcamManager.erkenne_kamera(available)
                    best_idx = befund["index"]
                    zustand = befund["zustand"]
                    current_idx = config.get("camera_index", 0)
                    manuell = bool(config.get("camera_index_manuell", False))

                    if best_idx >= 0:
                        if best_idx != current_idx:
                            best_name = next(
                                (c["name"] for c in available if c["index"] == best_idx), "?")
                            logger.info(
                                f"Kamera Auto-Auswahl: [{best_idx}] {best_name} "
                                f"(statt [{current_idx}]) — {befund['begruendung']}"
                            )
                            config["camera_index"] = best_idx
                            # Der Index kommt jetzt von der Erkennung, nicht
                            # mehr von Hand -> Handmerker fällt weg.
                            config["camera_index_manuell"] = False
                        self._camera_index_bestaetigt = True
                        return

                    # KEIN Treffer. Ab 2.4.40 wird camera_index NICHT mehr aus
                    # blossem Unwissen auf -1 gesetzt (bis 2.4.39 überschrieb
                    # ein einziger PowerShell-Aussetzer eine funktionierende
                    # Einstellung). Umgekehrt gilt aber genauso: Ein Index, der
                    # einfach nur in der Config steht, ist KEIN Beweis für eine
                    # externe Kamera. Stehen bleiben darf er nur mit Beweis.
                    sicher = befund.get("bestaetigter_index", -1)

                    if zustand == "intern":
                        # Positiver Befund: alle sichtbaren Geräte sind
                        # nachweislich intern. Hier hilft auch keine
                        # Handauswahl mehr — abschalten.
                        logger.warning(
                            f"⚠️ Keine externe Kamera verwendbar ({zustand}): "
                            f"{befund['begruendung']} — interne Kamera wird NICHT verwendet."
                        )
                        config["camera_index"] = -1
                    elif sicher >= 0 and sicher != current_idx:
                        # Das zuletzt per Name UND DevicePath bestätigte Gerät
                        # hängt laut Registry wieder am Bus — aber unter einem
                        # anderen Index als dem eingestellten.
                        logger.warning(
                            f"Kamera-Erkennung unbestimmt ({zustand}): "
                            f"{befund['begruendung']} — bestätigte externe Kamera "
                            f"ist [{sicher}], camera_index wird von "
                            f"[{current_idx}] darauf gesetzt."
                        )
                        config["camera_index"] = sicher
                        config["camera_index_manuell"] = False
                        self._camera_index_bestaetigt = True
                    elif sicher >= 0:
                        logger.warning(
                            f"Kamera-Erkennung unbestimmt ({zustand}): "
                            f"{befund['begruendung']} — camera_index "
                            f"[{current_idx}] bleibt: als externe Kamera bestätigt "
                            f"(Gedächtnis + Registry)."
                        )
                        self._camera_index_bestaetigt = True
                    elif manuell and current_idx >= 0:
                        # Handauswahl aus dem Admin-Menü. Dort werden als
                        # intern erkannte Geräte gar nicht erst angeboten, die
                        # Auswahl war also eine sichtbare Personenentscheidung.
                        # Die darf ein misslungener Suchlauf nicht kippen.
                        logger.warning(
                            f"Kamera-Erkennung unbestimmt ({zustand}): "
                            f"{befund['begruendung']} — camera_index "
                            f"[{current_idx}] bleibt: im Admin-Menü von Hand gewählt."
                        )
                    else:
                        logger.warning(
                            f"⚠️ Kamera-Erkennung unbestimmt ({zustand}): "
                            f"{befund['begruendung']} — camera_index "
                            f"[{current_idx}] ist NICHT als extern bestätigt und "
                            f"wird abgeschaltet. Lieber blinkende Warnung als "
                            f"schwarze Fotos aus der abgeklebten Kamera."
                        )
                        config["camera_index"] = -1
                except Exception as e:
                    logger.debug(f"Kamera Auto-Auswahl fehlgeschlagen: {e}")

            threading.Thread(target=_auto_select_webcam, daemon=True, name="cam-autoselect").start()
        self._pump_startup_loading_screen()

        self.usb_manager = get_shared_usb_manager()
        self.statistics = get_statistics_manager()
        self.local_storage = LocalStorage()
        self.filter_manager = FilterManager()
        self.renderer = TemplateRenderer(
            canvas_width=config.get("canvas_width", 1800),
            canvas_height=config.get("canvas_height", 1200)
        )
        self._pump_startup_loading_screen()
        
        # Session-Status
        self.photos_taken: List[Image.Image] = []
        self.current_photo_index: int = 0  # Aktueller Foto-Index (bleibt bei Screen-Wechsel erhalten!)
        self.current_filter: str = "none"
        self.template_path: Optional[str] = None
        self.template_boxes: List[Dict] = []
        self.overlay_image: Optional[Image.Image] = None
        self.prints_in_session: int = 0

        # Skaliertes Overlay-Cache (überlebt Screen-Wechsel, vermeidet wiederholtes LANCZOS-Resize)
        self._cached_scaled_overlay: Optional[Image.Image] = None
        self._cached_overlay_scale: float = 0.0
        self._cached_overlay_source_size: Optional[tuple] = None

        # USB-Template Cache (bleibt erhalten wenn USB abgezogen wird)
        self.cached_usb_template: Optional[Dict] = None  # {path, name, overlay, boxes}
        # USB-Stick Template (Original vom Stick, wird nie überschrieben)
        self._usb_stick_template: Optional[Dict] = None  # {path, name, overlay, boxes}
        # Flag: User hat explizit ein Template über 2015-Menü gewählt
        self._user_template_override: bool = False
        # Flag: Aktives Template kam per App-Upload und darf vom USB-Stick nicht
        # wieder ersetzt werden, solange keine neue USB-Buchung geladen wird.
        self._app_uploaded_template_active: bool = False

        # USB-Sync Dialog State
        self._sync_dialog_open: bool = False  # Verhindert mehrfache Dialoge
        self._sync_offer_deferred: bool = False

        # Event-Wechsel & FEXOSAFE Dialog State
        self._pending_event_change: Optional[str] = None   # Neue booking_id
        self._pending_fexosafe_drive: Optional[str] = None  # Laufwerksbuchstabe
        self._event_change_dialog_open: bool = False
        self._fexosafe_dialog_open: bool = False
        self._last_fexosafe_trigger: float = 0  # Cooldown nach Backup
        self._export_dialog_open: bool = False
        self._last_unknown_stick_drive: Optional[str] = None  # Doppel-Dialog verhindern
        self._boot_drives: set = set()  # Laufwerke die beim Start schon da waren
        self._boot_grace_period: float = 0  # Zeitpunkt nach dem unknown-stick-check aktiv wird

        # Stress-Test Status (nur im Developer Mode)
        self.stress_test_active: bool = False
        self.stress_test_count: int = 0

        # Drucker initialisieren wenn nicht gesetzt
        self._init_default_printer()

        # PrinterController mit Druckername initialisieren
        from src.printer.controller import get_printer_controller
        printer_ctrl = get_printer_controller()
        printer_ctrl.update_printer_name(self.config.get("printer_name", ""))

        # Overlay-Referenz
        self._printer_error_overlay = None
        # Letzter geloggter Drucker-Status (nur bei Wechsel loggen → keine Log-Flut)
        self._last_printer_problem = None
        # Bug #49: Nach Service-Ausstieg (PIN im Fehler-Overlay) das automatische
        # Wieder-Öffnen pausieren – sonst holt der Sekunden-Poll das Overlay
        # sofort zurück. Top-Bar-Warnung läuft trotzdem weiter.
        self._printer_overlay_snooze_until = 0.0

        # WICHTIG: Settings ZUERST laden, BEVOR UI erstellt wird!
        # Sonst zeigt die UI falsche Optionen (z.B. Single-Foto obwohl deaktiviert)
        self._load_settings_from_usb_immediately()
        self._pump_startup_loading_screen()

        # Settings auf Config anwenden (VOR UI-Setup!)
        if self.booking_manager.is_loaded:
            logger.info(f"📂 Buchung aktiv: {self.booking_manager.booking_id}")

            # Template in Config eintragen
            if self.booking_manager.apply_cached_template_to_config(self.config):
                logger.info("📦 Template wird verwendet")

            # BookingSettings auf Config anwenden (allow_single_mode, gallery_enabled, etc.)
            self.booking_manager.apply_settings_to_config(self.config)
            # Buchung kann camera_type überschrieben haben (DSLR) → Manager angleichen.
            self._sync_camera_manager_with_config()

        self._refresh_startup_loading_screen()
        self._pump_startup_loading_screen()

        # Gecachtes Template VOR UI-Erstellung laden, damit StartScreen sofort
        # das richtige Template anzeigt (nicht kurz "Standard 2x2" flashen)
        self._restore_cached_template()
        self._pump_startup_loading_screen()

        # Log aktuelle Config nach Settings-Anwendung
        logger.info(f"📋 Config nach Settings-Load:")
        logger.info(f"   allow_single_mode = {self.config.get('allow_single_mode', True)}")
        logger.info(f"   gallery_enabled = {self.config.get('gallery_enabled', False)}")
        logger.info(f"   locale = {self.config.get('locale', 'de-DE')}")

        # Der QR-Code kann schon beim ersten StartScreen-Render entstehen.
        # Deshalb Kontext fuer die spaetere Smartphone-App vor dem UI-Aufbau setzen.
        self._prepare_gallery_app_context()

        # UI Setup (NACH Settings, damit korrekte Optionen angezeigt werden!)
        self._setup_ui()
        self._hide_startup_loading_screen()

        # VLC erst nach dem ersten UI-Frame vorwärmen, damit der Kunden-
        # Begrüßungsscreen sichtbar bleibt während VLC seine Plugins lädt.
        try:
            from src.ui.screens.video import warmup_vlc
            self.root.after(500, warmup_vlc)
        except Exception as e:
            logger.debug(f"VLC-Warmup übersprungen: {e}")

        # Buchungsanzeige aktualisieren
        if self.booking_manager.is_loaded:
            self._update_booking_display()
        
        # Boot-Drives ZUERST erfassen (VOR Status-Checks, damit Export-Dialog sie ignoriert)
        self._record_boot_drives()

        # Status-Timer starten
        self._start_status_checks()

        # Event-Wechsel Dialog beim Start (USB hatte andere Buchung als Cache)
        if self._startup_event_change:
            logger.info(f"🔄 Event-Wechsel-Dialog wird nach Start angezeigt: {self._startup_event_change}")
            booking_id = self._startup_event_change
            self._startup_event_change = None
            # Verzögert anzeigen damit UI vollständig geladen ist
            self.root.after(500, lambda: self._show_event_change_dialog(booking_id))

        # Galerie-Server starten wenn aktiviert (NACH Settings-Anwendung!).
        # BEWUSST verzoegert (2.4.24: 4s -> 7s): Der Flask-Server-Start blockiert
        # den Main-Thread ~1,5s. Bei 4s landete das MITTEN im Willkommens-/Lade-
        # screen -> der Ladebalken fror dort ein ("bewegt sich erst spaet").
        # 7s spaeter ist der Ladescreen (VLC-Warmup) typisch schon weg und der
        # Balken konnte frei durchlaufen; der Server-Start blockiert dann nur den
        # statischen Startbildschirm (unsichtbar). Hotspot/Server sind in den
        # ersten Sekunden ohnehin nicht noetig (kein Gast koppelt so schnell).
        self.root.after(7000, self._init_gallery_server)

        # Developer Mode: Performance Overlay
        self._init_performance_overlay()

        # Statistik IMMER starten (auch ohne USB/Buchung)
        if not self.statistics.current:
            self._start_statistics_event()
            logger.info("📊 Statistik gestartet (ohne USB)")

        # Orphan-Cleanup: Reste von abgebrochenen Updates aus %TEMP% löschen.
        # Verhindert dass Tablets sich mit ~150 MB ZIP-Dateien zumüllen.
        try:
            from src.updater import cleanup_orphan_downloads
            cleaned = cleanup_orphan_downloads(max_age_hours=1.0)
            if cleaned > 0:
                logger.info(f"Update-Orphan-Cleanup: {cleaned} Reste entfernt")
        except Exception as e:
            logger.debug(f"Orphan-Cleanup fehlgeschlagen: {e}")

        # Firmen-WLAN-Aktionen: Auto-Update und Software-Monitoring.
        # Läuft als Background-Thread mit 15s Verzögerung, damit App erst sauber hochfährt.
        auto_update_enabled = self.config.get("auto_update_enabled", True)
        monitoring_enabled = self.config.get("monitoring_enabled", True)
        if auto_update_enabled or monitoring_enabled:
            try:
                from src.company_network import check_and_auto_update
                check_and_auto_update(
                    whitelist=self.config.get("company_wifi_ssids", []),
                    delay_seconds=15.0,
                    app=self,
                    config=self.config,
                    update_enabled=auto_update_enabled,
                )
            except Exception as e:
                logger.debug(f"Firmennetzwerk-Trigger fehlgeschlagen: {e}")

        logger.info("PhotoboothApp initialisiert")

        # Dev-Mode: UI-Hänger-Monitor (loggt, wenn der Tk-Hauptthread blockiert war)
        self._start_ui_hitch_monitor()

        # FexoNikonBridge automatisch vorstarten (nur Nikon) – unsichtbarer
        # Hintergrundprozess ohne Fenster. Blockiert den Startup nicht und
        # entschärft den Kaltstart beim ersten Capture.
        self._warmup_nikon_async()

    def _start_ui_hitch_monitor(self):
        """Dev-Mode: loggt, wenn der Tk-UI-Thread spürbar blockiert war.

        Ein after(200ms)-Herzschlag misst seine eigene Verspätung. Kommt er
        deutlich zu spät, hat IRGENDWAS den UI-Thread so lange blockiert
        (Sekunden-Polls, Screen-Wechsel, versehentlich synchrone Arbeit) —
        die Log-Zeitmarke zeigt dann, welche Aktion unmittelbar davor lief.
        Im Live-Betrieb komplett deaktiviert (0 Overhead).
        """
        if not self.config.get("developer_mode"):
            return

        interval_seconds = 0.2
        self._last_load_snapshot = 0.0

        def _tick():
            now = time.perf_counter()
            late_ms = (now - self._ui_hitch_expected_at) * 1000
            if late_ms > 200:
                logger.info(f"UI-HITCH: Tk-Hauptschleife war ~{late_ms:.0f}ms blockiert")
                if late_ms > 1000:
                    # Bei großen Hängern: Wer frisst gerade die CPU?
                    self._log_system_load_async(f"UI-Hitch {late_ms:.0f}ms")
            self._ui_hitch_expected_at = time.perf_counter() + interval_seconds
            self.root.after(int(interval_seconds * 1000), _tick)

        self._ui_hitch_expected_at = time.perf_counter() + interval_seconds
        self.root.after(int(interval_seconds * 1000), _tick)

        # Einmaliger Start-Schnappschuss: zeigt, ob die Box schon beim
        # Hochfahren unter Windows-Hintergrundlast steht
        self._log_system_load_async("App-Start")

    def _log_system_load_async(self, reason: str):
        """Dev-Mode: Systemlast-Schnappschuss im Hintergrund loggen (max. 1x/Minute).

        Zeigt bei großen UI-Hängern, ob Windows-Hintergrundlast (Defender-Scan,
        Update-Worker, Such-Indexer) die CPU wegnimmt — die häufigste Ursache
        für 'Box hängt' auf den Miix-Tablets.
        """
        now = time.monotonic()
        if now - getattr(self, "_last_load_snapshot", 0.0) < 60.0:
            return
        self._last_load_snapshot = now

        def _worker():
            try:
                from src.utils.system_load import snapshot_system_load
                snapshot_system_load(reason)
            except Exception as e:
                logger.debug(f"Systemlast-Schnappschuss fehlgeschlagen: {e}")

        threading.Thread(target=_worker, daemon=True, name="load-snapshot").start()

    def _warmup_nikon_async(self):
        """Startet die FexoNikonBridge im Hintergrund vor (nur wenn camera_type == 'nikon').

        Die Bridge ist ein unsichtbarer Hintergrundprozess (kein Fenster, kein
        Webserver). Der Warmup verhindert, dass initialize() beim ersten
        Session-Start den Bridge-Kaltstart auf dem UI-Thread durchläuft.
        Komplett im Daemon-Thread – kein Block des UI-/Startup-Threads.
        Idempotent (no-op, wenn die Bridge schon läuft oder kein Nikon-Manager
        aktiv ist).
        """
        if self.config.get("camera_type") != "nikon":
            return
        manager = self.camera_manager
        if not hasattr(manager, "ensure_bridge_running"):
            return

        def _warmup():
            try:
                ok = manager.ensure_bridge_running()
                logger.info(f"Nikon-Bridge-Warmup: {'bereit' if ok else 'nicht verfügbar'}")
            except Exception as e:
                logger.warning(f"Nikon-Bridge-Warmup fehlgeschlagen: {e}")

        threading.Thread(target=_warmup, daemon=True, name="nikon-warmup").start()

    def _sync_camera_manager_with_config(self):
        """Baut den Kamera-Manager neu, wenn sich camera_type geändert hat.

        Nötig, weil Buchungs-/Event-Reloads und das Admin-Speichern den
        camera_type ändern können (z.B. webcam→nikon). Bleibt der Typ gleich,
        wird nur die Config in den Manager durchgereicht (Nikon braucht sie für
        die Bridge-Pfade) – kein teurer Re-Init.
        """
        camera_type = self.config.get("camera_type", "webcam")

        if getattr(self, "_camera_type", None) == camera_type:
            if hasattr(self.camera_manager, "update_config"):
                self.camera_manager.update_config(self.config)
            self._sync_dauerbetrieb_hd()
            return

        logger.info(f"Kamera-Typ geändert: {self._camera_type} -> {camera_type}")
        try:
            if self.camera_manager and self.camera_manager.is_initialized:
                self.camera_manager.release()
        except Exception as e:
            logger.warning(f"Alte Kamera konnte nicht freigegeben werden: {e}")

        self._camera_type = camera_type
        self._camera_dauerbetrieb_hd = True  # 2.4.45: fest, kein Schalter mehr
        self.camera_manager = get_camera_manager(camera_type, config=self.config)

        # Bei Wechsel auf Nikon die FexoNikonBridge im Hintergrund vorstarten.
        if camera_type == "nikon":
            self._warmup_nikon_async()

        # 2.4.46: Wechselt eine Buchung zur Laufzeit auf Canon-DSLR, muss der
        # Ereignis-Takt nachgezogen werden — sonst kommen die Fotos nicht an.
        # (Beim Programmstart erledigt das run().) Nur bei laufender
        # Hauptschleife, sonst legt run() den Takt gleich selbst an.
        if camera_type == "canon" and getattr(self, "_mainloop_started", False):
            self._starte_canon_event_takt()

    def _sync_dauerbetrieb_hd(self):
        """Gibt die Kamera frei, wenn der HD-Dauerbetrieb umgelegt wurde (2.4.43).

        WARUM FREIGEBEN UND NICHT EINFACH NEU INITIALISIEREN:
        `WebcamManager.initialize()` steigt sofort aus, wenn die Kamera bereits
        offen ist und der Index gleich blieb — width/height werden dabei
        komplett IGNORIERT. Ohne `release()` bliebe die Kamera also stur in der
        alten Aufloesung, der Schalter waere scheinbar wirkungslos, und wir
        wuerden einen Fehler suchen, der keiner ist.

        BEWUSST NUR FREIGEBEN, NICHT NEU OEFFNEN: Das Oeffnen laeuft auf dem
        Tk-Thread und wuerde die Oberflaeche direkt nach dem Schliessen des
        Admin-Menues fuer ein bis zwei Sekunden einfrieren. Das naechste
        `_pre_init_camera` (waehrend des Intro-Videos) bzw. `session.on_show`
        holt das Oeffnen nach — dort stoert es niemanden.
        """
        gewuenscht = True  # 2.4.45: Dauerbetrieb ist der einzige Weg
        zuletzt = getattr(self, "_camera_dauerbetrieb_hd", None)

        if zuletzt is None:
            self._camera_dauerbetrieb_hd = gewuenscht
            return
        if zuletzt == gewuenscht:
            return

        self._camera_dauerbetrieb_hd = gewuenscht
        logger.info(
            f"Kamera-Dauerbetrieb HD geändert: {zuletzt} -> {gewuenscht} "
            f"— Kamera wird freigegeben und beim nächsten Start neu geöffnet"
        )
        try:
            if self.camera_manager and self.camera_manager.is_initialized:
                self.camera_manager.release()
        except Exception as e:
            logger.warning(f"Kamera konnte für den Betriebsart-Wechsel nicht freigegeben werden: {e}")

    def _show_startup_loading_screen(self):
        """Zeigt sehr früh einen einfachen Ladescreen im Kiosk-Fenster."""
        if self._startup_loading_frame is not None:
            return

        frame = ctk.CTkFrame(self.root, fg_color=COLORS["bg_dark"], corner_radius=0)
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.place(relx=0.5, rely=0.45, anchor="center")

        ctk.CTkLabel(
            content,
            text="FEXOBOOTH",
            font=("Segoe UI", 38, "bold"),
            text_color=COLORS["primary"],
        ).pack(pady=(0, 20))

        self._startup_loading_name_label = ctk.CTkLabel(
            content,
            text="",
            font=("Segoe UI", 30, "bold"),
            text_color=COLORS["text_primary"],
        )
        self._startup_loading_name_label.pack(pady=(0, 5))

        self._startup_loading_status_label = ctk.CTkLabel(
            content,
            text="",
            font=("Segoe UI", 18),
            text_color=COLORS["text_secondary"],
            justify="center",
        )
        self._startup_loading_status_label.pack(pady=(0, 25))

        # Determinate Bar, die wir SELBST bei jedem Startschritt weiterschieben
        # (2.4.23). Der eingebaute "indeterminate"-Modus von CTk animiert nur
        # bei laufender, freier Tk-Mainloop — die gibt es beim Start aber noch
        # nicht (nur manuelle update()-Pumps). Deshalb fror der Balken ein und
        # zuckte erst kurz vor dem Verschwinden. Manuelles Ping-Pong wirkt
        # zuverlässig "die Box arbeitet" und kostet fast nichts.
        progress = ctk.CTkProgressBar(
            content,
            width=300,
            height=6,
            fg_color=COLORS["bg_light"],
            progress_color=COLORS["primary"],
            corner_radius=3,
            mode="determinate",
        )
        progress.pack(pady=(0, 10))
        progress.set(0.0)
        self._startup_loading_progress = progress
        self._startup_loading_pos = 0.0
        self._startup_loading_dir = 1

        self._startup_loading_frame = frame
        self._refresh_startup_loading_screen()

        try:
            self.root.update_idletasks()
            self.root.update()
        except Exception:
            pass

    def _refresh_startup_loading_screen(self):
        if self._startup_loading_frame is None:
            return

        first_name = self._get_startup_first_name()
        if first_name:
            self._startup_loading_name_label.configure(
                text=t(self.config, "start.greeting_named", name=first_name)
            )
            self._startup_loading_status_label.configure(
                text=(
                    f"{t(self.config, 'start.greeting_thanks')}\n\n"
                    f"{t(self.config, 'start.greeting_warmup')}\n"
                    f"{t(self.config, 'start.loading_wait')}"
                )
            )
        else:
            self._startup_loading_name_label.configure(
                text=t(self.config, "start.loading_software")
            )
            self._startup_loading_status_label.configure(text=t(self.config, "start.loading_wait"))

        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def _pump_startup_loading_screen(self):
        if self._startup_loading_frame is None:
            return
        # Ladebalken bei jedem Startschritt monoton nach vorn schieben — das
        # liest sich klar als „Fortschritt beim Booten" (0 → ~92%; den Rest
        # füllt der Übergang zum StartScreen). Bewusst monoton statt Ping-Pong,
        # damit sich der Balken von Anfang an sichtbar vorwärts bewegt.
        try:
            bar = getattr(self, "_startup_loading_progress", None)
            if bar is not None:
                self._startup_loading_pos = min(0.92, self._startup_loading_pos + 0.08)
                bar.set(self._startup_loading_pos)
        except Exception:
            pass
        try:
            self.root.update_idletasks()
            self.root.update()
        except Exception:
            pass

    def _hide_startup_loading_screen(self):
        if self._startup_loading_frame is None:
            return

        try:
            self._startup_loading_frame.destroy()
        except Exception:
            pass

        self._startup_loading_frame = None
        self._startup_loading_name_label = None
        self._startup_loading_status_label = None

    def _get_startup_first_name(self) -> str:
        if not self.booking_manager or not self.booking_manager.is_loaded:
            return ""
        settings = self.booking_manager.settings
        if not settings:
            return ""
        first_name = (settings.shipping_first_name or "").strip()
        if not first_name and settings.customer_name:
            first_name = settings.customer_name.strip().split()[0]
        return first_name

    def _record_boot_drives(self):
        """Merkt sich alle Wechseldatenträger die beim Boot schon da sind.
        Diese werden nicht als 'unbekannter Stick' für den Export-Dialog behandelt.
        Grace period: 15s nach Boot keine Unknown-Stick-Checks.
        """
        import ctypes
        self._boot_drives = set()
        try:
            for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
                drive = f"{letter}:\\"
                if not os.path.exists(drive):
                    continue
                try:
                    drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
                    if drive_type == 2:  # DRIVE_REMOVABLE
                        self._boot_drives.add(drive)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Boot-Drive-Erkennung fehlgeschlagen: {e}")

        self._boot_grace_period = time.time() + 15  # 15s Grace Period nach Boot
        if self._boot_drives:
            logger.info(f"Boot-Drives (ignoriert für Export): {self._boot_drives}")

    def _load_settings_from_usb_immediately(self):
        """Lädt Settings vom USB-Stick SOFORT beim App-Start

        Wichtig: Nicht auf den Timer warten - Settings müssen sofort geladen werden,
        damit allow_single_mode, gallery_enabled etc. von Anfang an korrekt sind.

        Wenn eine ANDERE Buchung als im Cache erkannt wird, wird ein Flag gesetzt
        damit nach dem UI-Setup der Event-Wechsel-Dialog angezeigt wird.
        """
        from pathlib import Path

        self._startup_event_change = None  # Flag für Event-Wechsel beim Start

        try:
            usb_drive = self.usb_manager.find_usb_stick()
            if not usb_drive:
                logger.debug("Kein USB beim Start gefunden - verwende Cache")
                return

            usb_root = Path(usb_drive)

            # Alte Booking-ID merken (aus Cache) BEVOR neue geladen wird
            old_booking_id = self.booking_manager.booking_id

            # Settings vom USB laden (sucht alle .json Dateien, nimmt neueste)
            logger.info(f"📂 USB gefunden beim Start: {usb_drive}")
            if self.booking_manager.should_skip_usb_autoload_after_app_upload(usb_root):
                return

            if self.booking_manager.load_from_usb(usb_root, force=True):
                self._app_uploaded_template_active = False
                self._user_template_override = False
                new_booking_id = self.booking_manager.booking_id
                logger.info(f"✅ Settings vom USB geladen: {new_booking_id}")

                # USB-Template SOFORT in Memory laden + auf Disk persistieren
                from src.config.config import find_usb_template
                usb_template = find_usb_template(include_cache=False)
                if usb_template:
                    try:
                        overlay, boxes = TemplateLoader.load(usb_template, use_cache=True)
                        if overlay and boxes:
                            self.cached_usb_template = {
                                "path": usb_template,
                                "name": os.path.basename(usb_template),
                                "overlay": overlay,
                                "boxes": boxes,
                                "fingerprint": self.booking_manager.template_file_fingerprint(usb_template),
                                "source": "usb",
                            }
                            self._usb_stick_template = self.cached_usb_template
                            self._persist_template_to_cache(usb_template)
                            logger.info(f"📦 USB-Template beim Start geladen: {os.path.basename(usb_template)}")
                    except Exception as e:
                        logger.warning(f"USB-Template laden beim Start fehlgeschlagen: {e}")

                # Prüfen ob es eine ANDERE Buchung ist als im Cache
                if old_booking_id and new_booking_id and old_booking_id != new_booking_id:
                    logger.info(f"🔄 Neue Buchung beim Start erkannt: {old_booking_id} → {new_booking_id}")
                    self._startup_event_change = new_booking_id

                # Statistik-Event starten
                self._start_statistics_event(usb_root)

        except Exception as e:
            logger.warning(f"USB-Check beim Start fehlgeschlagen: {e}")

    def _restore_cached_template(self, force: bool = False, use_cache: bool = True):
        """Stellt gecachtes Template beim App-Start wieder her.

        Lädt cached_template.zip in self.cached_usb_template, damit der StartScreen
        sofort das richtige Template anzeigt — ohne den Umweg über on_show().
        Wird nur aktiv wenn eine Buchung aus dem Cache geladen wurde UND kein
        USB-Stick eingesteckt ist (sonst kommt das Template direkt vom Stick).

        WICHTIG: Sucht NUR im lokalen Cache, nicht auf USB-Sticks!
        USB-Templates werden separat über _load_settings_from_usb_immediately geladen.
        """
        # Schon geladen (z.B. vom USB beim Start)
        if self.cached_usb_template and not force:
            return

        # Keine Buchung → kein gecachtes Template nötig
        if not self.booking_manager.is_loaded and not force:
            return

        # NUR lokalen Cache prüfen (nicht USB durchsuchen!)
        cached_path = self.booking_manager.cached_template_path
        if not cached_path:
            logger.debug("Kein gecachtes Template zum Wiederherstellen gefunden")
            return

        try:
            overlay, boxes = TemplateLoader.load(str(cached_path), use_cache=use_cache)
            if boxes:
                app_template = self.booking_manager.is_template_cache_from_app_upload()
                fingerprint = self.booking_manager.template_file_fingerprint(cached_path)
                self.cached_usb_template = {
                    "path": str(cached_path),
                    "name": cached_path.name,
                    "overlay": overlay,
                    "boxes": boxes,
                    "source": "app" if app_template else "cache",
                    "fingerprint": fingerprint,
                }
                if not app_template:
                    self._usb_stick_template = self.cached_usb_template
                self.template_path = str(cached_path)
                self.template_boxes = boxes
                self.overlay_image = overlay
                if app_template:
                    self._user_template_override = True
                    self._app_uploaded_template_active = True
                    logger.info("📲 App-Template bleibt aktiv; USB-Autoload darf es nicht ersetzen")
                logger.info(f"📦 Gecachtes Template wiederhergestellt: {cached_path.name} ({len(boxes)} Slots)")
            else:
                logger.warning(f"Gecachtes Template konnte nicht geladen werden: {cached_path}")
        except Exception as e:
            logger.warning(f"Fehler beim Wiederherstellen des gecachten Templates: {e}")

    def _reload_template_from_usb(self, usb_root: Path):
        """Lädt Template vom USB-Stick wenn cached_usb_template leer ist.

        Wird aufgerufen wenn der gleiche Stick wieder eingesteckt wird und
        das Template aus dem Memory verloren ging (z.B. nach Neustart).
        """
        from src.config.config import find_usb_template

        usb_template = find_usb_template(include_cache=False)
        if not usb_template:
            # Fallback: aus Cache laden
            cached_path = self.booking_manager.cached_template_path
            if cached_path:
                usb_template = str(cached_path)
            else:
                return

        try:
            overlay, boxes = TemplateLoader.load(usb_template, use_cache=True)
            if overlay and boxes:
                self._app_uploaded_template_active = False
                self.cached_usb_template = {
                    "path": usb_template,
                    "name": os.path.basename(usb_template),
                    "overlay": overlay,
                    "boxes": boxes,
                    "fingerprint": self.booking_manager.template_file_fingerprint(usb_template),
                    "source": "usb",
                }
                self._usb_stick_template = self.cached_usb_template
                self._persist_template_to_cache(usb_template)
                logger.info(f"📦 Template bei Stick-Wiedereinstecken geladen: {os.path.basename(usb_template)}")

                # StartScreen aktualisieren wenn sichtbar
                if self.current_screen_name == "start" and hasattr(self.current_screen, "on_show"):
                    self.current_screen.on_show()
        except Exception as e:
            logger.warning(f"Template-Reload bei Stick-Wiedereinstecken fehlgeschlagen: {e}")

    def _persist_template_to_cache(self, template_path: str):
        """Kopiert eine Template-ZIP in den lokalen Cache (.booking_cache/).

        Wird aufgerufen von: _execute_event_change, _load_settings_from_usb_immediately,
        und on_show im StartScreen. Stellt sicher dass cached_template.zip IMMER
        existiert wenn ein Template vom USB geladen wurde.
        """
        import shutil
        try:
            from src.storage.booking import CACHE_DIR, TEMPLATE_CACHE_FILE
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(template_path, TEMPLATE_CACHE_FILE)
            logger.info(f"📦 Template auf Disk gespeichert: {TEMPLATE_CACHE_FILE}")
        except Exception as e:
            logger.warning(f"Template konnte nicht auf Disk gecached werden: {e}")

    def _init_default_printer(self):
        """Setzt den Standard-Drucker falls keiner konfiguriert ist"""
        if not self.config.get("printer_name"):
            try:
                import win32print
                default_printer = win32print.GetDefaultPrinter()
                if default_printer:
                    self.config["printer_name"] = default_printer
                    save_config(self.config)
                    logger.info(f"Standard-Drucker gesetzt: {default_printer}")
            except Exception as e:
                logger.debug(f"Drucker-Init übersprungen: {e}")

    def _init_gallery_server(self):
        """Startet den permanenten lokalen Service-Kanal (Hotspot + Flask-API).

        APP-PLATTFORM-FUNDAMENT: Hotspot + Server laufen ab jetzt IMMER (Support,
        Settings-/Template-Korrektur, Software-OTA) — entkoppelt von der gebuchten
        Galerie. Das ZAHLENDE Foto-Feature bleibt serverseitig an `gallery_enabled`
        gekoppelt (`set_gallery_feature_enabled`). Am Box-SCREEN aendert sich fuer
        Nicht-Galerie-Kunden NICHTS (QR/Banner bleiben strikt an `gallery_enabled`,
        siehe start.py). Start weiterhin 4 s verzoegert (Boot-Ruckler).
        """
        gallery_enabled = self.config.get("gallery_enabled", False)
        logger.info(
            f"🔌 Lokaler Service-Kanal startet (Foto-Feature={'an' if gallery_enabled else 'aus'})"
        )
        try:
            from src.gallery import (
                start_server,
                get_gallery_url,
                start_hotspot,
                set_gallery_feature_enabled,
            )
            from pathlib import Path

            # Hotspot im Hintergrund starten (blockiert sonst ~6s)
            gallery_config = self.config.get("gallery", {})
            hs_ssid = gallery_config.get("hotspot_ssid", "")
            hs_password = gallery_config.get("hotspot_password", "")
            def _start_hs():
                try:
                    # 2.4.27 — Reihenfolge im Firmen-WLAN:
                    # Der eigene Hotspot teilt sich die WLAN-Karte mit der
                    # Firmen-Verbindung und kann sie stoeren. Steht die Box in
                    # der Werkstatt, laeuft deshalb ZUERST die Netz-Arbeit
                    # (Dashboard-Meldung + Update-Check) und erst danach der
                    # Hotspot. Beim Kunden aendert sich nichts: dort ist keine
                    # Firmen-SSID verbunden -> es wird nicht gewartet.
                    try:
                        from src.utils.company_wlan import get_connected_ssid
                        from src.company_network import wait_for_startup_network_window

                        aktuelle_ssid = get_connected_ssid()
                        if aktuelle_ssid in self.config.get("company_wifi_ssids", []):
                            logger.info(
                                f"📶 Hotspot wartet: Firmen-WLAN '{aktuelle_ssid}' erkannt — "
                                f"erst Dashboard-Meldung/Update, dann Hotspot"
                            )
                            wait_for_startup_network_window(timeout=120.0)
                    except Exception as e:
                        logger.debug(f"Hotspot-Reihenfolge: Prüfung übersprungen ({e})")

                    logger.info("📶 Starte Hotspot (Service-Kanal)...")
                    start_hotspot(ssid=hs_ssid, password=hs_password)
                except Exception as e:
                    logger.warning(f"Hotspot-Start fehlgeschlagen: {e}")
            threading.Thread(target=_start_hs, daemon=True, name="Hotspot-Start").start()

            # Galerie-Pfad = immer lokaler Speicher (damit Löschen sofort wirkt)
            gallery_path = self.local_storage.get_images_path()

            if gallery_path:
                port = int(gallery_config.get("port") or self.config.get("gallery_port", 8080))
                start_server(
                    gallery_path,
                    port=port,
                    locale=self.config.get("locale", "de-DE"),
                    app_context=self._get_gallery_app_context()
                )
                # Foto-Feature serverseitig gaten (zahlendes Feature, an gallery_enabled).
                set_gallery_feature_enabled(gallery_enabled)

                # URL für QR-Code speichern
                self.gallery_url = get_gallery_url(port)
                logger.info(
                    f"🌐 Service-Kanal verfügbar: {self.gallery_url} "
                    f"(Foto-Feature={'an' if gallery_enabled else 'aus'})"
                )
            else:
                logger.warning("Kein Bilder-Pfad für Service-Kanal verfügbar")

        except ImportError as e:
            logger.warning(f"Galerie-Modul nicht verfügbar: {e}")
        except Exception as e:
            logger.error(f"Service-Kanal Start fehlgeschlagen: {e}")

    def _get_gallery_app_context(self) -> Dict[str, Any]:
        """Kontext fuer Pairing-QR und Smartphone-App API."""
        gallery_config = self.config.get("gallery", {})
        booking_id = self.booking_manager.booking_id if self.booking_manager.is_loaded else ""
        event_pin = ""
        if self.booking_manager.is_loaded and self.booking_manager.settings:
            event_pin = getattr(self.booking_manager.settings, "event_pin", "") or ""
        try:
            from src import __version__ as software_version
        except Exception:
            software_version = ""

        active_template_path = ""
        active_template_source = ""
        active_template_fingerprint = ""
        if self.cached_usb_template:
            active_template_path = self.cached_usb_template.get("path", "") or ""
            active_template_source = self.cached_usb_template.get("source", "") or ""
            active_template_fingerprint = self.cached_usb_template.get("fingerprint", "") or ""
        elif self.template_path:
            active_template_path = self.template_path
            active_template_source = "session"
        if active_template_path and not active_template_fingerprint:
            active_template_fingerprint = self.booking_manager.template_file_fingerprint(active_template_path)

        return {
            "box_id": self.config.get("box_id", ""),
            "booking_id": booking_id,
            "event_pin": event_pin,
            "locale": self.config.get("locale", "de-DE"),
            "software_version": software_version,
            "hotspot_ssid": gallery_config.get("hotspot_ssid", ""),
            "hotspot_password": gallery_config.get("hotspot_password", ""),
            "active_template_path": active_template_path,
            "active_template_source": active_template_source,
            "active_template_fingerprint": active_template_fingerprint,
            "cached_template_path": str(self.booking_manager.cached_template_path or ""),
            "cached_template_fingerprint": self.booking_manager.cached_template_fingerprint(),
            "app_template_active": self._app_uploaded_template_active,
            "user_template_override": self._user_template_override,
        }

    def _prepare_gallery_app_context(self) -> None:
        """Setzt App-Metadaten auch dann, wenn der Server noch nicht laeuft.

        Plattform-Fundament: laeuft unabhaengig von `gallery_enabled`, damit
        `/api/v1/status` schon vor dem (4 s verzoegerten) Server-Start die
        software_version/box_id melden kann.
        """
        try:
            from src.gallery import set_gallery_app_context, set_gallery_locale
            set_gallery_locale(self.config.get("locale", "de-DE"))
            set_gallery_app_context(self._get_gallery_app_context())
        except Exception as e:
            logger.debug(f"Galerie-App-Kontext konnte nicht vorbereitet werden: {e}")

    def _stop_hotspot_if_running(self):
        """Stoppt den Hotspot im Hintergrund, falls er laeuft.

        ⚠️ NICHT MEHR im "Galerie deaktiviert"-Pfad aufrufen! Seit dem
        App-Plattform-Fundament laeuft der lokale Service-Kanal (Hotspot + Flask)
        DAUERHAFT, entkoppelt von `gallery_enabled` (siehe `_init_gallery_server`).
        Den Hotspot abzuwuergen, nur weil keine Galerie gebucht ist, wuerde die
        Template-/Settings-Korrektur und die App-OTA fuer Nicht-Galerie-Kunden
        kaputtmachen. Diese Methode bleibt nur fuer einen echten, bewussten
        Shutdown erhalten und wird aktuell nicht aufgerufen.
        """
        def _do_stop():
            try:
                from src.gallery import is_hotspot_active, stop_hotspot
                if is_hotspot_active():
                    logger.info("📶 Stoppe Hotspot (Galerie deaktiviert)...")
                    stop_hotspot()
            except ImportError:
                pass
            except Exception as e:
                logger.debug(f"Hotspot-Stop übersprungen: {e}")

        threading.Thread(target=_do_stop, daemon=True, name="Hotspot-Stop").start()

    def _init_performance_overlay(self):
        """Initialisiert Performance Overlay im Developer Mode"""
        if not self.config.get("developer_mode", False):
            self.performance_overlay = None
            return
        
        try:
            from src.ui.performance_overlay import PerformanceOverlay
            self.performance_overlay = PerformanceOverlay(self)
            logger.info("🛠️ Developer Mode: Performance Overlay aktiviert")
        except Exception as e:
            logger.warning(f"Performance Overlay konnte nicht geladen werden: {e}")
            self.performance_overlay = None

    def _start_statistics_event(self, usb_root: Path = None):
        """Startet Statistik-Erfassung für aktuelle Buchung"""
        booking_id = self.booking_manager.booking_id if self.booking_manager.is_loaded else ""
        
        # Speicherpfad: Wird ignoriert - Statistik speichert immer lokal
        save_path = usb_root  # Parameter wird in start_event() ignoriert
        
        # Event starten (beendet vorheriges automatisch)
        self.statistics.start_event(booking_id=booking_id, save_path=save_path)

    def _start_gallery_if_needed(self):
        """Stellt sicher, dass der lokale Service-Kanal (Hotspot + Server) laeuft.

        Laeuft ab jetzt unabhaengig von `gallery_enabled` (Plattform-Fundament).
        Das ZAHLENDE Foto-Feature wird separat ueber `set_gallery_feature_enabled`
        an `gallery_enabled` gekoppelt — Server an, Fotos aber nur wenn gebucht.
        """
        try:
            from src.gallery import (
                is_running,
                set_gallery_app_context,
                start_server,
                get_gallery_url,
                start_hotspot,
                set_gallery_feature_enabled,
            )

            # Hotspot starten (auch wenn Server schon läuft - Hotspot könnte aus sein)
            # 2.4.27: NICHT mehr direkt hier — der Aufruf geht über PowerShell und
            # dauert auf der Box ~8 s. Da diese Methode auch aus dem Admin-Menü
            # heraus läuft, fror der Bildschirm dabei ein (Feld-Log 18.08.:
            # "UI-HITCH: Tk-Hauptschleife war ~9207ms blockiert" nach dem
            # Speichern). Jetzt im Hintergrund-Thread wie beim App-Start.
            gallery_config = self.config.get("gallery", {})
            hs_ssid = gallery_config.get("hotspot_ssid", "")
            hs_password = gallery_config.get("hotspot_password", "")

            def _ensure_hs():
                try:
                    start_hotspot(ssid=hs_ssid, password=hs_password)
                except Exception as e:
                    logger.warning(f"Hotspot-Start fehlgeschlagen: {e}")

            threading.Thread(target=_ensure_hs, daemon=True, name="Hotspot-Ensure").start()

            gallery_enabled = self.config.get("gallery_enabled", False)

            if is_running():
                set_gallery_app_context(self._get_gallery_app_context())
                set_gallery_feature_enabled(gallery_enabled)
                logger.debug(f"Service-Kanal läuft bereits (Foto-Feature={gallery_enabled})")
                return

            # Galerie-Pfad = immer lokal (damit Löschen sofort wirkt)
            gallery_path = self.local_storage.get_images_path()

            if gallery_path:
                port = int(gallery_config.get("port") or self.config.get("gallery_port", 8080))
                start_server(
                    gallery_path,
                    port=port,
                    locale=self.config.get("locale", "de-DE"),
                    app_context=self._get_gallery_app_context()
                )
                set_gallery_feature_enabled(gallery_enabled)
                self.gallery_url = get_gallery_url(port)
                logger.info(
                    f"🌐 Service-Kanal gestartet: {self.gallery_url} "
                    f"(Foto-Feature={gallery_enabled})"
                )
        except Exception as e:
            logger.error(f"Service-Kanal Start fehlgeschlagen: {e}")

    def _push_gallery_feature_flag(self):
        """Meldet den aktuellen `gallery_enabled`-Wert an den Server (Foto-Feature-Gate).

        Leichtgewichtig: aendert nur das serverseitige Flag, ohne den Server neu
        zu starten. Wird bei jeder moeglichen Aenderung von `gallery_enabled`
        aufgerufen (Event-Wechsel, Admin-Speichern, App-Settings-Apply).
        """
        try:
            from src.gallery import set_gallery_feature_enabled
            enabled = self.config.get("gallery_enabled", False)
            set_gallery_feature_enabled(enabled)
            logger.debug(f"Foto-Feature-Flag an Server gemeldet: {enabled}")
        except Exception as e:
            logger.debug(f"Foto-Feature-Flag konnte nicht gemeldet werden: {e}")

    def _set_window_icon(self):
        """Setzt das Fenster-Icon (Taskbar + Titelleiste)"""
        try:
            # ICO für Windows-Taskbar
            ico_path = Path(__file__).parent.parent / "assets" / "fexobooth.ico"
            if ico_path.exists():
                self.root.iconbitmap(str(ico_path))
            else:
                # Fallback: Im PyInstaller-Bundle
                import sys
                if getattr(sys, 'frozen', False):
                    ico_path = Path(sys._MEIPASS) / "assets" / "fexobooth.ico"
                    if ico_path.exists():
                        self.root.iconbitmap(str(ico_path))
        except Exception as e:
            logger.debug(f"Icon konnte nicht gesetzt werden: {e}")

    def _enter_fullscreen(self):
        """Aktiviert Kiosk-Vollbildmodus.

        - overrideredirect(True) entfernt Fensterrahmen und deckt den gesamten Bildschirm ab
        - topmost wird KURZ gesetzt um Fenster in den Vordergrund zu bringen, dann wieder entfernt
        - Taskleiste wird via Windows API versteckt
        - Windows-Benachrichtigungen werden über Focus Assist unterdrückt
        - Kein permanentes topmost - das blockiert eigene App-Dialoge!
        """
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        self.root.overrideredirect(True)
        self.root.geometry(f"{screen_width}x{screen_height}+0+0")

        # topmost KURZ setzen um Fenster in den Vordergrund zu bringen
        self.root.attributes("-topmost", True)

        # Taskleiste verstecken für echten Kiosk-Modus
        self._hide_taskbar()

        # Windows-Benachrichtigungen unterdrücken (Focus Assist)
        self._suppress_notifications(True)

        # Fenster in den Vordergrund zwingen
        self.root.lift()
        self.root.focus_force()
        self.root.update_idletasks()

        # topmost nach kurzem Moment wieder entfernen - sonst blockiert es eigene Dialoge
        self.root.after(500, lambda: self.root.attributes("-topmost", False))

        self._is_fullscreen = True
        logger.info(f"Kiosk-Vollbild aktiviert: {screen_width}x{screen_height}")

    def _exit_fullscreen(self):
        """Beendet Vollbildmodus - zeigt Taskleiste und Fensterrahmen wieder an."""
        self.root.attributes("-topmost", False)
        self.root.overrideredirect(False)
        self.root.geometry("1024x768")
        self._show_taskbar()
        self._suppress_notifications(False)
        self._is_fullscreen = False
        logger.info("Vollbild deaktiviert")
    
    def _hide_taskbar(self):
        """Versteckt die Windows-Taskleiste für echten Kiosk-Modus.

        Nutzt FindWindowW um Shell_TrayWnd (Taskleiste) und Button (Start-Button)
        zu finden und via ShowWindow zu verstecken.
        """
        import sys
        if sys.platform != "win32":
            return

        try:
            import ctypes
            SW_HIDE = 0

            # Taskleiste verstecken
            taskbar = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
            if taskbar:
                ctypes.windll.user32.ShowWindow(taskbar, SW_HIDE)

            # Start-Button verstecken (Windows 10/11)
            start_btn = ctypes.windll.user32.FindWindowW("Button", "Start")
            if start_btn:
                ctypes.windll.user32.ShowWindow(start_btn, SW_HIDE)

            logger.debug("Taskleiste versteckt")
        except Exception as e:
            logger.debug(f"Taskleiste verstecken fehlgeschlagen: {e}")

    def _show_taskbar(self):
        """Zeigt die Windows-Taskleiste wieder an."""
        import sys
        if sys.platform != "win32":
            return

        try:
            import ctypes
            SW_SHOW = 5

            taskbar = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
            if taskbar:
                ctypes.windll.user32.ShowWindow(taskbar, SW_SHOW)

            start_btn = ctypes.windll.user32.FindWindowW("Button", "Start")
            if start_btn:
                ctypes.windll.user32.ShowWindow(start_btn, SW_SHOW)

            logger.debug("Taskleiste wiederhergestellt")
        except Exception as e:
            logger.debug(f"Taskleiste anzeigen fehlgeschlagen: {e}")

    def _restore_taskbar_safe(self):
        """atexit-Handler: Stellt Taskleiste wieder her, fängt ALLE Fehler ab.

        Wird bei App-Beendigung aufgerufen (auch bei Exceptions).
        Muss komplett eigenständig funktionieren (App-State evtl. kaputt).
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes
            SW_SHOW = 5
            taskbar = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
            if taskbar:
                ctypes.windll.user32.ShowWindow(taskbar, SW_SHOW)
            start_btn = ctypes.windll.user32.FindWindowW("Button", "Start")
            if start_btn:
                ctypes.windll.user32.ShowWindow(start_btn, SW_SHOW)
        except Exception:
            pass  # Absolut nichts werfen im atexit-Handler

    def _suppress_notifications(self, suppress: bool):
        """Aktiviert/deaktiviert Windows Focus Assist (Benachrichtigungen unterdrücken).

        Setzt Registry-Key für Focus Assist:
        - suppress=True: Priority Only (nur wichtige Benachrichtigungen)
        - suppress=False: Alles erlaubt (normal)

        Zusätzlich wird das Action Center (Benachrichtigungszentrum) versteckt/gezeigt.
        """
        import sys
        if sys.platform != "win32":
            return

        try:
            import winreg

            # Focus Assist / Quiet Hours: 0=Aus, 1=Priority Only, 2=Alarms Only
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Notifications\Settings"
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, key_path,
                    0, winreg.KEY_SET_VALUE
                )
                winreg.SetValueEx(
                    key, "NOC_GLOBAL_SETTING_TOASTS_ENABLED",
                    0, winreg.REG_DWORD,
                    0 if suppress else 1
                )
                winreg.CloseKey(key)
                logger.debug(f"Windows-Benachrichtigungen: {'unterdrückt' if suppress else 'erlaubt'}")
            except Exception as e:
                logger.debug(f"Focus Assist Registry fehlgeschlagen: {e}")

        except Exception as e:
            logger.debug(f"Benachrichtigungen unterdrücken fehlgeschlagen: {e}")

    def _on_window_configure(self, event):
        """Fängt Maximize-Klick ab und wechselt in echten Kiosk-Vollbild"""
        if self._is_fullscreen:
            return
        # Nur auf Root-Window Events reagieren (nicht auf Child-Widgets)
        if event.widget != self.root:
            return
        if self.root.state() == "zoomed":
            # Maximize rückgängig machen und stattdessen echten Kiosk-Vollbild
            self.root.state("normal")
            self.root.after(50, self._enter_fullscreen)

    def _toggle_fullscreen(self):
        """Toggle Fullscreen - nur im Fenstermodus erlaubt.

        Im Kiosk-Modus (start_fullscreen=True) wird Escape/F11 ignoriert.
        Vollbild kann dann nur über den Admin-PIN verlassen werden.
        """
        if self.config.get("start_fullscreen", True):
            # Kiosk-Modus: Escape/F11 blockiert - kein Zugriff auf Windows ohne PIN
            return

        if self._is_fullscreen:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _setup_ui(self):
        """Erstellt die UI-Struktur"""
        # Top-Bar
        self.top_bar = self._create_top_bar()
        self.top_bar.pack(fill="x")
        
        # Container für Screens
        self.container = ctk.CTkFrame(self.root, fg_color=COLORS["bg_dark"])
        self.container.pack(fill="both", expand=True)
        
        # Screens
        self.screens = {}
        self.current_screen = None
        self.current_screen_name = None

        # Ladebalken auch während des (schwereren) StartScreen-Aufbaus bewegen
        self._pump_startup_loading_screen()

        # Start-Screen anzeigen
        self.show_screen("start")
        self._pump_startup_loading_screen()
    
    def _create_top_bar(self) -> ctk.CTkFrame:
        """Erstellt die Top-Bar mit Logo und Status"""
        bar = ctk.CTkFrame(
            self.root,
            height=SIZES["topbar_height"],
            fg_color=COLORS["bg_medium"],
            corner_radius=0
        )
        
        # Logo-Bereich links
        logo_frame = ctk.CTkFrame(bar, fg_color="transparent")
        logo_frame.pack(side="left", padx=20, pady=10)
        
        # Logo laden wenn vorhanden
        logo_path = self.config.get("logo_path", "")
        if logo_path and os.path.exists(logo_path):
            try:
                logo_img = Image.open(logo_path)
                scale = self.config.get("logo_scale", 80) / 100
                new_height = int(50 * scale)
                ratio = logo_img.width / logo_img.height
                new_width = int(new_height * ratio)
                logo_img = logo_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                self.logo_ctk = ctk.CTkImage(
                    light_image=logo_img,
                    dark_image=logo_img,
                    size=(new_width, new_height)
                )
                logo_label = ctk.CTkLabel(logo_frame, image=self.logo_ctk, text="")
                logo_label.pack(side="left")
            except Exception as e:
                logger.warning(f"Logo konnte nicht geladen werden: {e}")
                ctk.CTkLabel(
                    logo_frame,
                    text="FEXOBOOTH",
                    font=FONTS["heading"],
                    text_color=COLORS["primary"]
                ).pack(side="left")
        else:
            ctk.CTkLabel(
                logo_frame,
                text="FEXOBOOTH",
                font=FONTS["heading"],
                text_color=COLORS["primary"]
            ).pack(side="left")

        ctk.CTkLabel(
            logo_frame,
            text=f"v{__version__}",
            font=FONTS["tiny"],
            text_color=COLORS["text_secondary"]
        ).pack(side="left", padx=(8, 0), pady=(8, 0))

        # Dev-Mode Buttons (nur im Developer Mode)
        if self.config.get("developer_mode", False):
            self.stress_test_btn = ctk.CTkButton(
                bar,
                text="STRESS TEST",
                width=150,
                height=35,
                font=("Segoe UI", 12, "bold"),
                fg_color=COLORS["bg_light"],
                hover_color=COLORS["warning"],
                text_color=COLORS["text_primary"],
                corner_radius=8,
                command=self._toggle_stress_test
            )
            self.stress_test_btn.pack(side="left", padx=10, pady=10)

            # Drucker-Reset Button (Dev Mode)
            printer_reset_btn = ctk.CTkButton(
                bar,
                text="DRUCKER RESET",
                width=160,
                height=35,
                font=("Segoe UI", 12, "bold"),
                fg_color=COLORS["bg_light"],
                hover_color=COLORS["error"],
                text_color=COLORS["text_primary"],
                corner_radius=8,
                command=self.trigger_printer_reset
            )
            printer_reset_btn.pack(side="left", padx=5, pady=10)

        # Status-Bereich rechts
        status_frame = ctk.CTkFrame(bar, fg_color="transparent")
        status_frame.pack(side="right", padx=20, pady=10)

        # Admin-Button - im Normal Mode unsichtbar aber klickbar (für Support)
        is_dev_mode = self.config.get("developer_mode", False)
        admin_btn = ctk.CTkButton(
            status_frame,
            text="⚙" if is_dev_mode else "",  # Kein Text im Normal Mode
            width=40,
            height=40,
            font=("Segoe UI", 18),
            fg_color="transparent",
            hover_color=COLORS["bg_light"] if is_dev_mode else COLORS["bg_medium"],
            text_color=COLORS["text_muted"] if is_dev_mode else COLORS["bg_medium"],
            command=self.show_admin_dialog
        )
        admin_btn.pack(side="right", padx=5)

        # Buchungsnummer-Anzeige (prominent, für Support-Anrufe)
        self.booking_label = ctk.CTkLabel(
            status_frame,
            text=t(self.config, "topbar.booking_empty"),
            font=FONTS["body_bold"] if "body_bold" in FONTS else FONTS["body"],
            text_color=COLORS["primary"],
            fg_color=COLORS["bg_light"],
            corner_radius=8,
            width=160,
            padx=10,
            pady=5
        )
        self.booking_label.pack(side="right", padx=8)

        # USB-Status in festem Container (verhindert Größenänderung bei wechselndem Text)
        usb_container = ctk.CTkFrame(status_frame, fg_color="transparent", width=160, height=28)
        usb_container.pack(side="right", padx=4)
        usb_container.pack_propagate(False)  # Container-Größe fixieren

        self.usb_status = ctk.CTkLabel(
            usb_container,
            text=f"⚠️ {t(self.config, 'topbar.usb_label')}",
            font=FONTS["small"],
            text_color=COLORS["warning"],
            fg_color=COLORS["bg_light"],
            corner_radius=8,
            padx=8,
            pady=5,
            anchor="center"
        )
        self.usb_status.pack(fill="both", expand=True)

        # Drucker-Status (feste Breite wie USB-Status)
        self.printer_status = ctk.CTkLabel(
            status_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["error"],
            fg_color=COLORS["bg_light"],
            corner_radius=8,
            width=155,  # Feste Breite für stabiles Layout
            padx=8,
            pady=5
        )
        self.printer_status.pack(side="right", padx=5)
        self.printer_status.pack_forget()  # Verstecken wenn OK
        self._printer_blink_state = False

        # Kamera-Status (feste Breite wie USB/Drucker-Status)
        self.camera_status = ctk.CTkLabel(
            status_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["error"],
            fg_color=COLORS["bg_light"],
            corner_radius=8,
            width=165,
            padx=8,
            pady=5
        )
        self.camera_status.pack(side="right", padx=4)
        self.camera_status.pack_forget()  # Verstecken wenn OK
        self._camera_blink_state = False
        self._camera_check_running = False  # Hintergrund-Prüfung aktiv?
        # Wann lief zuletzt eine VOLLE Kamerasuche (list_cameras)? 2.4.40:
        # Blinken und Suchen sind getrennt. Die Warnung blinkt weiter alle 2 s
        # (reine Anzeige), die teure Suche läuft im Problemfall höchstens alle
        # 20 s. Vorher plante der Wächter im -1-Zustand alle 2 s eine neue
        # Suche, obwohl ein Durchlauf über 10 s dauerte — die Box war damit
        # praktisch dauerhaft mit Kamerasuche beschäftigt. Genau dieser Zustand
        # hat die größte Kollisionsfläche für den Heap-Absturz 0xc0000374
        # (Box 044). Preis: eine im Betrieb neu angesteckte Kamera wird
        # schlimmstenfalls 20 statt 2 Sekunden später erkannt.
        self._letzte_kamerasuche = 0.0
        # Wann lief zuletzt die VOLLE Gegenprüfung eines bereits gesetzten
        # camera_index (2.4.40, Nachbesserung)? Der reine „lässt sich öffnen"-
        # Test kann eine interne Kamera nicht von einer externen unterscheiden;
        # deshalb wird höchstens jede Minute neu erkannt statt nur angetippt.
        self._letzte_vollpruefung = 0.0
        # Seit wann läuft die Hintergrund-Prüfung? Gegen ein für immer
        # gesetztes _camera_check_running (siehe _check_camera_status).
        self._camera_check_start = 0.0
        # Läuft gerade die Kamera-Messung als eigener Prozess? Dann fasst der
        # Wächter die Kamera NICHT an (siehe _check_camera_status). Gesetzt und
        # zurückgesetzt wird das ausschließlich von
        # src/ui/dialogs/kamera_messung.py.
        self._kamera_messung_laeuft = False

        # Strom-Status (kompakt, immer sichtbar)
        self.power_status = ctk.CTkLabel(
            status_frame,
            text="⚡",
            font=FONTS["small"],
            text_color=COLORS["success"],
            fg_color=COLORS["bg_light"],
            corner_radius=8,
            width=55,
            padx=4,
            pady=5
        )
        self.power_status.pack(side="right", padx=3)
        self._power_blink_state = False

        return bar
    
    def _start_status_checks(self):
        """Startet periodische Status-Checks"""
        self._check_usb_status()
        self._check_printer_status()
        self._check_camera_status()
        self._check_power_status()
        self._check_fullscreen_restore()
    
    def _check_usb_status(self):
        """Prüft USB-Status - BLINKEND wenn nicht vorhanden, Dialog bei Pending-Files"""
        from pathlib import Path

        # App-Upload (korrigierte Settings/Template über das Box-WLAN) übernehmen,
        # sobald die Box idle ist. Foto-sicher, läuft hier im Main-Thread.
        self._check_pending_upload_apply()

        # Prüfen ob USB wieder verfügbar und Dateien pending sind
        is_available = self.usb_manager.is_available()
        pending_count = self.usb_manager.get_pending_count()
        new_booking = None

        # USB verfügbar -> prüfen ob NEUE Buchung
        if is_available:
            usb_drive = self.usb_manager.find_usb_stick()
            if usb_drive:
                usb_root = Path(usb_drive)

                # Prüfen ob es eine neue Buchung ist
                new_booking = self.booking_manager.check_usb_for_new_booking(usb_root)

                if new_booking and not self._event_change_dialog_open:
                    # Neue Buchung erkannt -> Event-Wechsel-Dialog
                    if self.current_screen_name == "start":
                        self._show_event_change_dialog(new_booking)
                    elif not self._pending_event_change:
                        self._pending_event_change = new_booking
                        logger.info(f"Event-Wechsel pending: {new_booking} (warte auf StartScreen)")

                elif not self.booking_manager.is_loaded:
                    # Noch keine Buchung geladen -> aus USB oder Cache laden
                    self.booking_manager.load_from_usb(usb_root)
                    self._update_booking_display()

        # FEXOSAFE Sicherungs-Stick prüfen
        fexosafe_drive = self.usb_manager.find_fexosafe_stick()
        if fexosafe_drive and not self._fexosafe_dialog_open:
            if time.time() - self._last_fexosafe_trigger > 30:
                if self.current_screen_name == "start":
                    self._show_fexosafe_dialog(fexosafe_drive)
                elif not self._pending_fexosafe_drive:
                    self._pending_fexosafe_drive = fexosafe_drive
                    logger.info("FEXOSAFE pending (warte auf StartScreen)")

        # USB wurde gerade (wieder) eingesteckt -> Sync anbieten wenn gleiches Event
        if is_available and not self._sync_dialog_open:
            if not hasattr(self, '_was_usb_available') or not self._was_usb_available:
                logger.info(f"USB-Transition: nicht da → da (new_booking={new_booking}, pending={pending_count})")
                self._was_usb_available = True
                # Nur bei gleichem Event synchronisieren (kein neues Event erkannt)
                if not new_booking:
                    # Template wiederherstellen wenn es aus dem Memory verloren ging
                    # (z.B. nach Neustart ohne USB, dann Stick wieder eingesteckt)
                    if not self.cached_usb_template and self.booking_manager.is_loaded:
                        self._reload_template_from_usb(usb_root)
                    self._offer_sync_dialog()
        elif not is_available:
            if hasattr(self, '_was_usb_available') and self._was_usb_available:
                logger.info("USB-Transition: da → nicht da")
            self._was_usb_available = False

        # Unbekannter USB-Stick → Bilder-Export anbieten (Notfall-Fallback)
        # Ignoriert Drives die beim Boot schon da waren (z.B. SD-Karten-Slot)
        if not is_available and not fexosafe_drive and not self._export_dialog_open:
            if time.time() > self._boot_grace_period:  # Grace Period nach Boot
                unknown_drive = self.usb_manager.find_unknown_stick()
                if unknown_drive and unknown_drive not in self._boot_drives:
                    if unknown_drive != self._last_unknown_stick_drive:
                        self._last_unknown_stick_drive = unknown_drive
                        if self.current_screen_name == "start":
                            self._show_export_dialog(unknown_drive)
        elif is_available or fexosafe_drive:
            # Bekannter Stick da → Unknown-Tracking zurücksetzen
            self._last_unknown_stick_drive = None
        elif not self.usb_manager.find_unknown_stick():
            # Gar kein Stick mehr da → Unknown-Tracking zurücksetzen
            self._last_unknown_stick_drive = None
            # Boot-Drives die abgezogen wurden aus der Ignorier-Liste entfernen
            # Damit sie beim erneuten Einstecken als Export-Ziel angeboten werden
            if self._boot_drives:
                import ctypes as _ctypes
                still_present = set()
                for bd in self._boot_drives:
                    if os.path.exists(bd):
                        try:
                            if _ctypes.windll.kernel32.GetDriveTypeW(bd) == 2:
                                still_present.add(bd)
                        except Exception:
                            pass
                removed = self._boot_drives - still_present
                if removed:
                    self._boot_drives = still_present
                    logger.info(f"Boot-Drives abgezogen (jetzt Export-fähig): {removed}")

        text, status = self.usb_manager.get_status_text()

        if status == "success":
            self.usb_status.configure(
                text=text,
                text_color=COLORS["success"],
                fg_color=COLORS["bg_light"]
            )
            self._usb_blink_state = False
        else:
            # BLINKEND: Rot/Orange wechselnd
            if not hasattr(self, '_usb_blink_state'):
                self._usb_blink_state = False

            self._usb_blink_state = not self._usb_blink_state

            pending = self.usb_manager.get_pending_count()
            pending_text = f" [{pending}]" if pending > 0 else ""

            if self._usb_blink_state:
                self.usb_status.configure(
                    text=f"⚠️ {t(self.config, 'topbar.usb_none')}{pending_text}",
                    text_color="#ffffff",
                    fg_color="#ff0000"  # Knallrot
                )
            else:
                self.usb_status.configure(
                    text=f"⚠️ {t(self.config, 'topbar.usb_missing')}{pending_text}",
                    text_color="#000000",
                    fg_color="#ffcc00"  # Gelb
                )

        # Schnellerer Check für Blink-Effekt
        self.root.after(1000, self._check_usb_status)

    def _check_pending_upload_apply(self):
        """Übernimmt per App hochgeladene Settings/Template – nur wenn die Box idle ist.

        Läuft im Main-Thread (aus _check_usb_status). Foto-SICHER: löscht KEINE
        Bilder und setzt KEINE Session zurück. Ist die Box gerade nicht im
        Startbildschirm, bleibt der Marker liegen und wir versuchen es später.
        """
        # Laeuft bereits ein OTA (App wird gleich hart beendet)? Dann nichts mehr
        # anwenden — sonst koennte in den ~1,2 s bis zum Exit noch ein Settings-/
        # Template-Apply config.json mitten im Schreiben abschneiden (torn write).
        if getattr(self, "_software_update_in_progress", False):
            return

        req = self.booking_manager.peek_apply_request()
        if not req:
            return

        # Nur im Startbildschirm übernehmen (kein Eingriff in laufende Session).
        if self.current_screen_name != "start":
            return

        # Software-OTA zuerst: ersetzt die GANZE App -> Neustart. Settings/Template
        # bleiben als Marker liegen und greifen automatisch nach dem Neustart.
        if bool(req.get("software")):
            self._apply_pending_software_update()
            return

        applied = []
        process_settings = bool(req.get("settings"))
        process_template = bool(req.get("template"))
        try:
            self._log_template_debug_state("before-apply")
            if process_settings:
                if self.booking_manager.reload_from_cache():
                    self.booking_manager.apply_settings_to_config(self.config)
                    self._sync_camera_manager_with_config()
                    self._update_booking_display()
                    applied.append("Einstellungen")

            if process_template:
                # Caches leeren, damit die NEUE cached_template.zip frisch geladen
                # wird (sonst greift der mtime-Cache / die alte Vorschau).
                TemplateLoader.clear_cache()
                self.cached_usb_template = None
                self._usb_stick_template = None
                self._cached_scaled_overlay = None
                self._cached_overlay_scale = 0.0
                self._cached_overlay_source_size = None
                self.booking_manager.apply_cached_template_to_config(self.config)
                # WICHTIG: cached_usb_template NEU fuellen – DARAUS rendert der
                # StartScreen die Template-Vorschau. Vorher wurde nur overlay_image
                # gesetzt (load_template), die Vorschau blieb auf dem alten Template
                # haengen -> Template wechselte beim 2. Upload nicht.
                self._restore_cached_template(force=True, use_cache=False)
                if self.cached_usb_template:
                    self.booking_manager.mark_template_cache_from_app_upload()
                    # Dieser Apply-Pfad kommt nur von POST /upload/template.
                    # Deshalb das App-Template hier explizit als aktive Vorlage
                    # festhalten, selbst wenn kurz vorher Settings neu geladen
                    # wurden oder ein USB-Stick steckt.
                    self.cached_usb_template["source"] = "app"
                    self.cached_usb_template["fingerprint"] = self.booking_manager.cached_template_fingerprint()
                    self._user_template_override = True
                    self._app_uploaded_template_active = True
                    self.template_path = self.cached_usb_template["path"]
                    self.overlay_image = self.cached_usb_template["overlay"]
                    self.template_boxes = self.cached_usb_template["boxes"]
                    applied.append("Template")

            if applied:
                self._log_template_debug_state("after-apply-before-status")
                save_config(self.config)
                # Galerie-App-Kontext aktualisieren, damit /status die neue
                # booking_id und den neuen Template-Fingerprint meldet.
                try:
                    from src.gallery import set_gallery_app_context
                    set_gallery_app_context(self._get_gallery_app_context())
                except Exception:
                    pass
                # Startbildschirm neu rendern (zeigt neues Template/Settings)
                if self.current_screen and hasattr(self.current_screen, "on_show"):
                    self.current_screen.config = self.config
                    self.current_screen.on_show()
                self._log_template_debug_state("after-startscreen-on-show")
                logger.info(f"📲 App-Upload übernommen: {', '.join(applied)}")
            else:
                logger.warning("📲 App-Upload-Marker vorhanden, aber nichts angewendet")

            # Nur die Marker-Teile bestaetigen, die dieser Lauf gesehen hat.
            # Kommt das Template waehrend eines Settings-Applys nach, bleibt es
            # fuer den naechsten Tick liegen und wird nicht versehentlich geloescht.
            if process_settings or process_template:
                self.booking_manager.clear_apply_request(
                    settings=process_settings,
                    template=process_template,
                )
            else:
                self.booking_manager.clear_apply_request(settings=True, template=True)
        except Exception as e:
            logger.error(f"App-Upload-Apply fehlgeschlagen: {e}")
            if process_settings or process_template:
                self.booking_manager.clear_apply_request(
                    settings=process_settings,
                    template=process_template,
                )
            else:
                self.booking_manager.clear_apply_request(settings=True, template=True)

    def _apply_pending_software_update(self):
        """Wendet ein per App hochgeladenes + SHA256-verifiziertes Software-Update an.

        Nur im Idle (Aufrufer hat current_screen_name == "start" bereits geprueft).
        SHA256 wurde beim Empfang verifiziert (booking.stage_software_update). Hier
        nutzen wir den BESTEHENDEN Updater (Backup + Rollback + Neustart) — wir
        erfinden den Apply-Mechanismus nicht neu. Danach wird die App HART beendet,
        damit das BAT-Script das _internal-Paket tauschen kann (gelockte DLLs sonst).
        """
        meta = self.booking_manager.peek_software_update()
        if not meta:
            logger.warning("📲 Software-Apply angefordert, aber kein verifiziertes Paket vorhanden")
            self.booking_manager.clear_apply_request(software=True)
            return

        zip_path = Path(meta.get("path", ""))
        if not zip_path.exists():
            logger.error(f"📲 Software-ZIP nicht gefunden: {zip_path}")
            self.booking_manager.clear_software_update()
            self.booking_manager.clear_apply_request(software=True)
            return

        try:
            logger.info(
                f"📲 Wende Software-Update an (Idle): {zip_path.name} "
                f"sha256={str(meta.get('sha256', ''))[:12]}…"
            )
            from src import updater

            # Ab hier laeuft der OTA: weitere Apply-Ticks (Settings/Template) sperren,
            # damit kurz vor dem Hard-Exit kein torn write von config.json passiert.
            self._software_update_in_progress = True

            # Marker VOR dem Neustart bestaetigen, damit nach dem Reboot kein
            # Re-Apply-Loop entsteht (das neue Paket ist dann ja schon installiert).
            # Das ZIP NICHT loeschen — das BAT-Script braucht es noch zum Entpacken.
            self.booking_manager.clear_apply_request(software=True)

            updater.apply_update_and_restart(zip_path)
            logger.info("📲 Update-Script gestartet — App wird fuer den Tausch HART beendet…")
            # Kurz warten, damit das letzte Log + die HTTP-Antwort flushen, dann
            # hart beenden (wie UpdateProgressDialog._quit_for_update): os._exit(0),
            # sonst halten Kamera-/Flask-/USB-Threads den Prozess am Leben und das
            # BAT-Script kollidiert mit gelockten DLLs.
            self.root.after(1200, self._hard_exit_for_update)
        except Exception as e:
            logger.error(f"📲 Software-Update fehlgeschlagen: {e}", exc_info=True)
            # Fehlgeschlagen -> Sperre wieder loesen, damit Settings/Template-Applies
            # (und ein erneuter Versuch) wieder moeglich sind.
            self._software_update_in_progress = False
            # Bei Fehler Paket + Marker entfernen, damit es nicht endlos retryt.
            self.booking_manager.clear_software_update()
            self.booking_manager.clear_apply_request(software=True)

    def _hard_exit_for_update(self):
        """Beendet den Prozess SOFORT (os._exit), damit das Update-BAT uebernehmen kann."""
        logger.info("App wird HART beendet (os._exit) fuer App-OTA…")
        import logging as _logging
        try:
            _logging.shutdown()
        except Exception:
            pass
        os._exit(0)

    def _log_template_debug_state(self, label: str):
        try:
            cached = self.cached_usb_template or {}
            usb = self._usb_stick_template or {}
            cache_path = self.booking_manager.cached_template_path
            logger.info(
                "📲 TEMPLATE DEBUG APP %s | app_active=%s user_override=%s "
                "template_path=%s fp=%s | cached_card=%s path_fp=%s loaded_fp=%s source=%s | "
                "usb_ref=%s path_fp=%s loaded_fp=%s | cache_file=%s fp=%s",
                label,
                self._app_uploaded_template_active,
                self._user_template_override,
                self.template_path or "-",
                self.booking_manager.template_file_fingerprint(self.template_path) if self.template_path else "",
                cached.get("path", "-"),
                self.booking_manager.template_file_fingerprint(cached.get("path", "")) if cached.get("path") else "",
                cached.get("fingerprint", ""),
                cached.get("source", "-"),
                usb.get("path", "-"),
                self.booking_manager.template_file_fingerprint(usb.get("path", "")) if usb.get("path") else "",
                usb.get("fingerprint", ""),
                str(cache_path) if cache_path else "-",
                self.booking_manager.cached_template_fingerprint(),
            )
        except Exception as e:
            logger.debug(f"Template-Debug App fehlgeschlagen: {e}")

    def _check_fullscreen_restore(self):
        """Sicherheitsnetz: Stellt Kiosk-Modus wieder her falls er verloren geht.

        Prüft alle 5 Sekunden:
        - Wenn Fullscreen verloren: wiederherstellen (falls kein Dialog offen)
        - Wenn Fullscreen aktiv: Taskleiste re-asserten (KEIN topmost - blockiert Dialoge!)

        WICHTIG: Wenn ein Dialog (Admin, Service, USB-Sync, ...) offen ist,
        machen wir GAR NICHTS — auch kein _hide_taskbar(). Win32-ShowWindow-Calls
        können den Z-Order stören und den Dialog im Hintergrund verschwinden
        lassen. Bug-Bericht v2.2.9: Admin-Dialog (PIN 3198) schloss sich
        nach wenigen Sekunden, ADMIN-Button reagierte danach nicht mehr.
        """
        # Toplevel-Dialoge erkennen — auch CTkToplevel mit overrideredirect.
        # Wir prüfen sowohl winfo_class() als auch isinstance(child, ctk.CTkToplevel)
        # damit nichts übersehen wird.
        try:
            import customtkinter as _ctk
            ctk_toplevel_cls = _ctk.CTkToplevel
        except Exception:
            ctk_toplevel_cls = None

        any_toplevel_open = False
        for child in self.root.winfo_children():
            try:
                if child.winfo_class() == "Toplevel":
                    any_toplevel_open = True
                    break
                if ctk_toplevel_cls is not None and isinstance(child, ctk_toplevel_cls):
                    any_toplevel_open = True
                    break
            except Exception:
                continue

        # Wenn ein Dialog offen ist: NICHTS tun. Periodische Win32-Operationen
        # könnten den Z-Order stören → Dialog verschwindet im Hintergrund.
        if any_toplevel_open:
            self.root.after(5000, self._check_fullscreen_restore)
            return

        if self.config.get("start_fullscreen", True):
            if not self._is_fullscreen:
                logger.info("Kiosk-Sicherheit: Stelle Vollbild wieder her")
                self._enter_fullscreen()
            else:
                # Fullscreen aktiv - nur Taskleiste sicherstellen (kein topmost!)
                self._hide_taskbar()

        self.root.after(5000, self._check_fullscreen_restore)

    def _update_booking_display(self):
        """Aktualisiert die Buchungsanzeige in der Top-Bar"""
        if self.booking_manager.is_loaded:
            booking_id = self.booking_manager.booking_id
            self.booking_label.configure(
                text=f"📋 {booking_id}",
                text_color=COLORS["success"],
                fg_color=COLORS["bg_light"]
            )
            logger.info(f"Buchungsanzeige aktualisiert: {booking_id}")
        else:
            self.booking_label.configure(
                text=t(self.config, "topbar.booking_empty"),
                text_color=COLORS["text_muted"],
                fg_color=COLORS["bg_light"]
            )

    def _offer_sync_dialog(self):
        """Prüft fehlende Bilder und bietet Sync-Dialog an (gleiches Event)."""
        from src.storage.local import LocalStorage
        import threading

        if not getattr(self, "_mainloop_started", False):
            if not self._sync_offer_deferred:
                self._sync_offer_deferred = True
                logger.debug("USB-Sync: Warte bis Hauptschleife laeuft")
                self.root.after(1000, self._run_deferred_sync_offer)
            return

        local_path = LocalStorage.get_images_path()
        if not local_path.exists():
            logger.warning(f"USB-Sync: local_path existiert nicht: {local_path}")
            return

        pending_count = self.usb_manager.get_pending_count()
        logger.info(f"USB-Sync: Prüfe fehlende Bilder (local={local_path}, pending={pending_count})")

        # Fehlende Bilder im Hintergrund zählen
        def check_missing():
            try:
                missing = self.usb_manager.count_missing(local_path)
                logger.info(f"USB-Sync: count_missing={missing}, pending={pending_count}")

                # count_missing ODER pending_count — das höhere zählt
                effective_count = max(missing, pending_count)

                if effective_count > 0:
                    self.root.after(0, lambda: self._show_sync_dialog(effective_count, local_path))
                else:
                    logger.debug("USB-Sync: Alle Bilder bereits auf USB")
            except Exception as e:
                logger.error(f"USB-Sync: Fehler beim Zählen: {e}")
                # Fallback: Wenn pending_count > 0, trotzdem Dialog anbieten
                if pending_count > 0:
                    self.root.after(0, lambda: self._show_sync_dialog(pending_count, local_path))

        threading.Thread(target=check_missing, daemon=True).start()

    def _run_deferred_sync_offer(self):
        self._sync_offer_deferred = False
        self._offer_sync_dialog()

    def _show_sync_dialog(self, missing_count: int, local_path):
        """Zeigt Dialog: X Bilder auf USB kopieren? Mit Fortschritt und Abbrechen."""
        import threading

        if self._sync_dialog_open:
            return

        self._sync_dialog_open = True
        logger.info(f"USB-Sync Dialog: {missing_count} fehlende Bilder")

        dialog = ctk.CTkToplevel(self.root)
        dialog.overrideredirect(True)
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.transient(self.root)

        dialog_w, dialog_h = 420, 250
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - dialog_w) // 2
        y = (screen_h - dialog_h) // 2
        dialog.geometry(f"{dialog_w}x{dialog_h}+{x}+{y}")
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        dialog.bind("<Control-Shift-Q>", lambda e: self._emergency_quit())
        dialog.bind("<Control-Shift-q>", lambda e: self._emergency_quit())

        content = ctk.CTkFrame(
            dialog, fg_color=COLORS["bg_medium"],
            border_color=COLORS["primary"], border_width=2, corner_radius=16
        )
        content.pack(fill="both", expand=True, padx=2, pady=2)

        # Titel
        ctk.CTkLabel(
            content, text=t(self.config, "usb.detected"),
            font=("Segoe UI", 20, "bold"), text_color=COLORS["primary"]
        ).pack(pady=(20, 5))

        # Info-Text (wird später zu Status-Text)
        status_label = ctk.CTkLabel(
            content,
            text=t(self.config, "usb.sync_missing", count=missing_count),
            font=FONTS["body"], text_color=COLORS["text_primary"], justify="center"
        )
        status_label.pack(pady=(5, 15))

        # Fortschrittsbalken (zunächst versteckt)
        progress_bar = ctk.CTkProgressBar(
            content, width=340, height=14,
            fg_color=COLORS["bg_dark"], progress_color=COLORS["primary"], corner_radius=7
        )

        # Button-Container
        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack(pady=(0, 20))

        cancel_event = threading.Event()

        def close_dialog():
            self._sync_dialog_open = False
            try:
                dialog.destroy()
            except Exception:
                pass

        def on_cancel():
            cancel_event.set()
            logger.info("USB-Sync: Abgebrochen")
            close_dialog()

        def on_copy():
            # Buttons durch Abbrechen-Button ersetzen
            for widget in btn_frame.winfo_children():
                widget.destroy()

            cancel_btn = ctk.CTkButton(
                btn_frame, text=t(self.config, "common.cancel"),
                font=FONTS["button"], width=160, height=45,
                fg_color=COLORS["bg_light"], hover_color=COLORS["bg_card"],
                text_color=COLORS["text_primary"],
                corner_radius=SIZES["corner_radius"], command=on_cancel
            )
            cancel_btn.pack()

            # Fortschrittsbalken anzeigen
            progress_bar.set(0)
            progress_bar.pack(pady=(0, 10))

            status_label.configure(text=t(self.config, "usb.copying"))

            def progress_callback(copied, total, filename):
                def update():
                    try:
                        progress_bar.set(copied / total)
                        status_label.configure(
                            text=t(self.config, "usb.copying_progress", copied=copied, total=total)
                        )
                    except Exception:
                        pass
                dialog.after(0, update)

            def do_sync():
                result = self.usb_manager.sync_all_missing(
                    local_path, progress_callback=progress_callback, cancel_event=cancel_event
                )
                copied = result.get("copied", 0)
                cancelled = result.get("cancelled", False)

                def show_result():
                    if cancelled:
                        status_label.configure(
                            text=t(self.config, "usb.copy_cancelled", copied=copied),
                            text_color=COLORS["warning"]
                        )
                    elif result.get("errors", 0) > 0:
                        status_label.configure(
                            text=t(self.config, "usb.copy_errors", copied=copied, errors=result["errors"]),
                            text_color=COLORS["warning"]
                        )
                    else:
                        status_label.configure(
                            text=t(self.config, "usb.copy_success", copied=copied),
                            text_color=COLORS["success"]
                        )
                        progress_bar.set(1.0)
                        progress_bar.configure(progress_color=COLORS["success"])

                    # Buttons entfernen
                    for widget in btn_frame.winfo_children():
                        widget.destroy()

                    # Auto-Close nach 3 Sekunden (Erfolg) oder 4 Sekunden (Fehler/Abbruch)
                    auto_close_ms = 3000 if not cancelled and result.get("errors", 0) == 0 else 4000
                    dialog.after(auto_close_ms, close_dialog)

                dialog.after(0, show_result)

            threading.Thread(target=do_sync, daemon=True).start()

        # Kopieren-Button
        ctk.CTkButton(
            btn_frame, text=t(self.config, "usb.copy"),
            font=FONTS["button"], width=140, height=50,
            fg_color=COLORS["success"], hover_color="#00e676",
            corner_radius=SIZES["corner_radius"], command=on_copy
        ).pack(side="left", padx=10)

        # Abbrechen-Button
        ctk.CTkButton(
            btn_frame, text=t(self.config, "common.cancel"),
            font=FONTS["button"], width=140, height=50,
            fg_color=COLORS["bg_light"], hover_color=COLORS["bg_card"],
            text_color=COLORS["text_primary"],
            corner_radius=SIZES["corner_radius"], command=close_dialog
        ).pack(side="left", padx=10)

        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

    def _show_export_dialog(self, target_drive: str):
        """Zeigt Dialog: Bilder auf unbekannten USB-Stick exportieren?"""
        import threading
        from src.storage.local import LocalStorage, SINGLES_PATH, PRINTS_PATH

        if self._export_dialog_open:
            return

        # Lokale Bilder zählen
        image_count = 0
        if SINGLES_PATH.exists():
            image_count += len(list(SINGLES_PATH.glob("*.jpg")))
        if PRINTS_PATH.exists():
            image_count += len(list(PRINTS_PATH.glob("*.jpg")))

        if image_count == 0:
            logger.debug("Export-Dialog: Keine lokalen Bilder vorhanden")
            return

        self._export_dialog_open = True
        local_path = LocalStorage.get_images_path()
        logger.info(f"Export-Dialog: {target_drive} ({image_count} Bilder)")

        dialog = ctk.CTkToplevel(self.root)
        dialog.overrideredirect(True)
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.transient(self.root)

        dialog_w, dialog_h = 420, 260
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - dialog_w) // 2
        y = (screen_h - dialog_h) // 2
        dialog.geometry(f"{dialog_w}x{dialog_h}+{x}+{y}")
        dialog.attributes("-topmost", True)
        # Kein grab_set() - Dialog soll die App NICHT blockieren!
        # User kann weiterhin den Start-Button oder Einstellungen nutzen
        dialog.lift()
        dialog.focus_force()
        dialog.bind("<Control-Shift-Q>", lambda e: self._emergency_quit())
        dialog.bind("<Control-Shift-q>", lambda e: self._emergency_quit())

        content = ctk.CTkFrame(
            dialog, fg_color=COLORS["bg_medium"],
            border_color=COLORS["info"], border_width=2, corner_radius=16
        )
        content.pack(fill="both", expand=True, padx=2, pady=2)

        # Titel
        ctk.CTkLabel(
            content, text=t(self.config, "usb.detected"),
            font=("Segoe UI", 20, "bold"), text_color=COLORS["info"]
        ).pack(pady=(20, 5))

        # Laufwerk-Info
        drive_letter = target_drive[0]
        ctk.CTkLabel(
            content,
            text=t(self.config, "usb.unknown_drive", drive=drive_letter),
            font=FONTS["small"], text_color=COLORS["text_muted"]
        ).pack(pady=(0, 5))

        # Status-Text
        status_label = ctk.CTkLabel(
            content,
            text=t(self.config, "usb.export_question", count=image_count),
            font=FONTS["body"], text_color=COLORS["text_primary"], justify="center"
        )
        status_label.pack(pady=(5, 15))

        # Fortschrittsbalken (zunächst versteckt)
        progress_bar = ctk.CTkProgressBar(
            content, width=340, height=14,
            fg_color=COLORS["bg_dark"], progress_color=COLORS["info"], corner_radius=7
        )

        # Button-Container
        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack(pady=(0, 20))

        cancel_event = threading.Event()

        def close_dialog():
            self._export_dialog_open = False
            try:
                dialog.destroy()
            except Exception:
                pass

        def on_cancel():
            cancel_event.set()
            logger.info("Bilder-Export: Abgebrochen")
            close_dialog()

        def on_export():
            # Buttons durch Abbrechen-Button ersetzen
            for widget in btn_frame.winfo_children():
                widget.destroy()

            cancel_btn = ctk.CTkButton(
                btn_frame, text=t(self.config, "common.cancel"),
                font=FONTS["button"], width=160, height=45,
                fg_color=COLORS["bg_light"], hover_color=COLORS["bg_card"],
                text_color=COLORS["text_primary"],
                corner_radius=SIZES["corner_radius"], command=on_cancel
            )
            cancel_btn.pack()

            progress_bar.set(0)
            progress_bar.pack(pady=(0, 10))
            status_label.configure(text=t(self.config, "usb.exporting"))

            def progress_callback(copied, total):
                def update():
                    try:
                        progress_bar.set(copied / total)
                        status_label.configure(
                            text=t(self.config, "usb.exporting_progress", copied=copied, total=total)
                        )
                    except Exception:
                        pass
                dialog.after(0, update)

            def do_export():
                result = self.usb_manager.export_to_stick(
                    target_drive, local_path,
                    progress_callback=progress_callback,
                    cancel_event=cancel_event
                )
                copied = result.get("copied", 0)
                cancelled = result.get("cancelled", False)

                def show_result():
                    if cancelled:
                        status_label.configure(
                            text=t(self.config, "usb.export_cancelled", copied=copied),
                            text_color=COLORS["warning"]
                        )
                    elif result.get("errors", 0) > 0:
                        status_label.configure(
                            text=t(self.config, "usb.export_errors", copied=copied, errors=result["errors"]),
                            text_color=COLORS["warning"]
                        )
                    else:
                        status_label.configure(
                            text=t(self.config, "usb.export_success", copied=copied),
                            text_color=COLORS["success"]
                        )
                        progress_bar.set(1.0)
                        progress_bar.configure(progress_color=COLORS["success"])

                    # Buttons entfernen
                    for widget in btn_frame.winfo_children():
                        widget.destroy()

                    # Auto-Close nach 3 Sekunden (Erfolg) oder 4 Sekunden (Fehler/Abbruch)
                    auto_close_ms = 3000 if not cancelled and result.get("errors", 0) == 0 else 4000
                    dialog.after(auto_close_ms, close_dialog)

                dialog.after(0, show_result)

            threading.Thread(target=do_export, daemon=True).start()

        # Exportieren-Button
        ctk.CTkButton(
            btn_frame, text=t(self.config, "usb.export"),
            font=FONTS["button"], width=140, height=50,
            fg_color=COLORS["success"], hover_color="#00e676",
            corner_radius=SIZES["corner_radius"], command=on_export
        ).pack(side="left", padx=10)

        # Abbrechen-Button
        ctk.CTkButton(
            btn_frame, text=t(self.config, "common.cancel"),
            font=FONTS["button"], width=140, height=50,
            fg_color=COLORS["bg_light"], hover_color=COLORS["bg_card"],
            text_color=COLORS["text_primary"],
            corner_radius=SIZES["corner_radius"], command=close_dialog
        ).pack(side="left", padx=10)

        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

    def _translate_topbar_printer_problem(self, problem_text: str) -> str:
        """Übersetzt bekannte Drucker-Fehler nur für die Top-Bar-Anzeige."""
        raw_text = str(problem_text or "").strip()
        normalized = raw_text.upper()

        key = TOPBAR_PRINTER_ERROR_KEYS.get(normalized)
        if key:
            return t(self.config, key)

        if normalized.startswith("FEHLER:"):
            details = raw_text.split(":", 1)[1].strip()
            return t(self.config, "topbar.printer_error_detail", details=details)

        if "STAU" in normalized:
            return t(self.config, "topbar.printer_paper_jam")
        if "PAPIER" in normalized and "KASSETTE" in normalized:
            return t(self.config, "topbar.printer_no_paper_cassette")
        if "PAPIER" in normalized:
            return t(self.config, "topbar.printer_no_paper")
        if "TINTENKASSETTE" in normalized:
            return t(self.config, "topbar.printer_no_ink_cassette")
        if "TINTE" in normalized:
            return t(self.config, "topbar.printer_ink_empty")
        if "KASSETTE" in normalized:
            return t(self.config, "topbar.printer_check_cassette")
        if "KLAPPE" in normalized:
            return t(self.config, "topbar.printer_cover_open")
        if "OFFLINE" in normalized:
            return t(self.config, "topbar.printer_offline")
        if "FEHLT" in normalized or "KEIN DRUCKER" in normalized:
            return t(self.config, "topbar.printer_missing")
        if "BLOCKIERT" in normalized:
            return t(self.config, "topbar.print_blocked")
        if "FEHLER" in normalized or "DRUCK" in normalized:
            return t(self.config, "topbar.printer_error")

        return raw_text

    def _check_printer_status(self):
        """Prüft Drucker-Status via PrinterController

        Bei erkanntem Fehler:
        - Blockierendes Overlay anzeigen (nur einmal!)
        - Canon-Dialog wird vom Overlay per SW_HIDE versteckt
        - Blinkende Warnung in Top-Bar
        - KEIN close_canon_dialogs() hier! Das macht das Overlay selbst.
        """
        from src.printer.controller import get_printer_controller
        controller = get_printer_controller()
        controller.update_printer_name(self.config.get("printer_name", ""))

        # Nicht prüfen wenn Overlay aktiv (Overlay kümmert sich selbst)
        overlay_active = (
            hasattr(self, '_printer_error_overlay') and
            self._printer_error_overlay is not None and
            self._printer_error_overlay.is_open
        )
        if overlay_active:
            self.root.after(2000, self._check_printer_status)
            return

        problem_text = controller.get_error()
        # Nur beim Statuswechsel loggen (sonst flutet ein dauerhafter Zustand,
        # z.B. "DRUCKER AUS!", das Log jede Sekunde zu). Overlay + Top-Bar laufen
        # unverändert jeden Poll weiter.
        status_changed = problem_text != self._last_printer_problem

        if problem_text:
            if status_changed:
                logger.info(f"Drucker-Fehler erkannt: '{problem_text}'")
            # Overlay zeigen (kümmert sich um Canon-Dialog + Bestätigung).
            # Wird weiterhin jeden Poll aufgerufen (re-zeigt bei anhaltendem
            # Stau/Verbrauch), aber nur beim Wechsel geloggt.
            self._show_printer_error_overlay(problem_text, log=status_changed)

            # Blinkend in Top-Bar anzeigen
            self._printer_blink_state = not self._printer_blink_state
            display_text = self._translate_topbar_printer_problem(problem_text)

            if self._printer_blink_state:
                self.printer_status.configure(
                    text=f"⚠️ {display_text}",
                    text_color="#ffffff",
                    fg_color="#ff0000"
                )
            else:
                self.printer_status.configure(
                    text=f"⚠️ {display_text}",
                    text_color="#000000",
                    fg_color="#ffcc00"
                )
            self.printer_status.pack(side="right", padx=5)
            self._last_printer_problem = problem_text
            self.root.after(1000, self._check_printer_status)
        else:
            # Alles OK -> Warnung verstecken
            if status_changed and self._last_printer_problem is not None:
                logger.info("Drucker-Status wieder OK")
            self._printer_blink_state = False
            self.printer_status.pack_forget()
            self._last_printer_problem = None
            self.root.after(5000, self._check_printer_status)

    def _show_printer_error_overlay(self, error_text: str, log: bool = True):
        """Zeigt blockierendes Drucker-Fehler-Overlay

        - Papierstau → automatischer Reset mit Animation
        - Verbrauchsmaterial → wartet bis Material gewechselt
        - other → nur Top-Bar (offline, etc.)

        log=False unterdrückt die Log-Ausgaben (bei unverändertem Status), damit
        ein Dauerzustand das Log nicht jede Sekunde flutet. Das Verhalten
        (Overlay zeigen/nicht zeigen) bleibt davon unberührt.
        """
        from src.ui.dialogs.printer_error import PrinterErrorOverlay, classify_error

        # Bug #49: Service hat das Overlay per PIN geschlossen → für die
        # Snooze-Dauer nicht automatisch wieder öffnen (Top-Bar warnt weiter).
        if time.time() < self._printer_overlay_snooze_until:
            if log:
                logger.info(
                    f"Drucker-Fehler '{error_text}' → Overlay pausiert bis "
                    f"{time.strftime('%H:%M:%S', time.localtime(self._printer_overlay_snooze_until))}"
                )
            return

        category = classify_error(error_text, log=log)

        # "other"-Fehler (offline, etc.) nur in Top-Bar anzeigen, kein Overlay
        if category == "other":
            if log:
                logger.debug(f"Drucker-Fehler '{error_text}' → kein Overlay (other)")
            return

        if log:
            logger.info(
                f">>> DRUCKER-OVERLAY WIRD ANGEZEIGT: '{error_text}' "
                f"(Kategorie: {category})"
            )
        self._printer_error_overlay = PrinterErrorOverlay(
            self.root, self, error_text, category
        )

    def snooze_printer_overlay(self, seconds: int):
        """Bug #49: Pausiert das automatische Drucker-Fehler-Overlay.

        Wird vom Service-Ausstieg im PrinterErrorOverlay aufgerufen, nachdem
        das Overlay per PIN erzwungen geschlossen wurde.
        """
        self._printer_overlay_snooze_until = time.time() + max(0, int(seconds))
        logger.warning(
            f"Drucker-Overlay pausiert für {seconds}s (Service-Ausstieg per PIN)"
        )

    def trigger_printer_reset(self):
        """Manueller Drucker-Reset (für Dev-Mode Button)"""
        from src.ui.dialogs.printer_error import PrinterErrorOverlay
        logger.info("Manueller Drucker-Reset ausgelöst")
        self._printer_error_overlay = PrinterErrorOverlay(
            self.root, self, "MANUELLER RESET", "jam"
        )

    # _check_print_jobs, _detect_canon_error_window, _bring_printer_dialog_to_front
    # → Ausgelagert nach src/printer/controller.py (PrinterController)

    def _check_camera_status(self):
        """Prüft Kamera-Status - BLINKEND wenn keine Kamera erreichbar.

        Seit 2.4.17 läuft die eigentliche Prüfung im Hintergrund-Thread:
        Das Webcam-Probing (PowerShell-Geräte-Enumeration bis 15s Timeout,
        cv2-Testöffnung ~500ms) blockierte vorher den UI-Thread — Miix-Log
        2026-08-07: UI-Hitches bis 16,5s beim Start und ~500ms alle 15s im
        Leerlauf. Der UI-Thread macht nur noch Anzeige + Terminplanung.

        Schutzregeln:
        - Immer nur EINE Prüfung gleichzeitig (_camera_check_running).
        - Geprüft wird nur auf dem Start-Screen und solange die Kamera nicht
          initialisiert ist — so kollidiert der Probe-Thread nicht mit
          Session-/Vorinitialisierung (EDSDK ist NICHT thread-safe, und eine
          DirectShow-Webcam verträgt keine zwei gleichzeitigen Öffner).
        """
        # Erst prüfen, wenn die Tk-Hauptschleife wirklich läuft. Sonst kann der
        # Probe-Thread `root.after()` aufrufen, bevor die Mainloop aktiv ist →
        # RuntimeError "main thread is not in main loop", der Thread stirbt und
        # damit die gesamte automatische Kamera-Wiederherstellung (Feld-Crash
        # 2026-08-11). Bis dahin nur neu terminieren (Main-Thread, sicher).
        if not getattr(self, "_mainloop_started", False):
            self.root.after(1000, self._check_camera_status)
            return

        if getattr(self, "_camera_check_running", False):
            # 2.4.40, Nachbesserung: Notausgang gegen einen hängenden
            # Prüf-Thread. `_camera_check_running` wird sonst NUR in
            # `_on_camera_status_result` zurückgesetzt — kommt der Thread nie
            # zurück (hängender Kameratreiber), wäre die gesamte
            # Kameraerkennung bis zum Neustart still tot: der Wächter plant
            # sich alle 2 s neu und steigt hier jedes Mal sofort wieder aus.
            # Nach 90 s wird das Flag deshalb freigegeben. Gefahrlos, weil
            # jeder Hardwarezugriff ohnehin unter der gemeinsamen Kamera-Sperre
            # läuft (ein zweiter Thread wartet dort, statt zu kollidieren).
            laeuft_seit = time.time() - getattr(self, "_camera_check_start", 0.0)
            if laeuft_seit > 90.0:
                logger.warning(
                    f"Kamera-Prüfung hängt seit {laeuft_seit:.0f} s — Sperre wird "
                    f"freigegeben, damit die Kameraerkennung weiterläuft."
                )
                self._camera_check_running = False
            else:
                self.root.after(2000, self._check_camera_status)
                return

        # 2.4.37: Waehrend der Kamera-Messung NICHTS anfassen.
        # Die Messung laeuft als eigener Prozess (src/ui/dialogs/kamera_messung.py)
        # und streamt dieselbe USB-Kamera. `camera_hardware_lock()` hilft dagegen
        # NICHT — die Sperre wirkt nur innerhalb eines Prozesses. Ohne diesen
        # Riegel oeffnet der Waechter alle 2-15 s dieselbe DirectShow-Kamera und
        # kann damit einen Messschritt scheitern lassen (im Bericht sieht das
        # aus wie "1080p geht auf dieser Box nicht" — ein reines Messartefakt)
        # oder im schlimmsten Fall selbst im Oeffnen haengen bleiben.
        if getattr(self, "_kamera_messung_laeuft", False):
            # Bewusst seltener nachsehen als sonst: Waehrend der Messung zaehlt
            # jede CPU-Scheibe auf dem Atom-Tablet, und die Messwerte sollen
            # nicht durch die eigene Oberflaeche verfaelscht werden.
            self.root.after(5000, self._check_camera_status)
            return

        # Außerhalb des Start-Screens oder bei aktiver Kamera: nichts prüfen
        # (Session läuft bzw. steht bevor) — nur Terminschleife weiterführen
        if (self.current_screen_name != "start"
                or self.camera_manager.is_initialized):
            if self.camera_manager.is_initialized:
                self._camera_blink_state = False
                self.camera_status.pack_forget()
            self.root.after(15000, self._check_camera_status)
            return

        self._camera_check_running = True
        self._camera_check_start = time.time()
        threading.Thread(
            target=self._camera_status_probe, daemon=True, name="camera-check"
        ).start()

    def _camera_status_probe(self):
        """Hintergrund-Thread: eigentliche Kamera-Erreichbarkeits-Prüfung.

        WICHTIG: EDSDK ist NICHT thread-safe (Windows COM STA)!
        Wenn die Kamera bereits initialisiert ist (z.B. System-Test oder Session),
        dürfen KEINE EDSDK-Aufrufe gemacht werden - sonst DEADLOCK!
        (Der Aufrufer prüft das bereits; die Guards hier bleiben als zweite Ebene.)
        """
        problem_text = None
        found_webcam_index = None

        try:
            camera_type = self.config.get("camera_type", "webcam")

            if camera_type == "canon":
                if self.camera_manager.is_initialized:
                    # Kamera ist aktiv (Session offen) → alles OK
                    # KEINE weiteren EDSDK-Aufrufe! (Deadlock-Gefahr!)
                    pass
                elif hasattr(self.camera_manager, '_initializing') and self.camera_manager._initializing:
                    # Initialisierung läuft gerade → KEINE EDSDK-Aufrufe!
                    # Sonst DEADLOCK: UI-Thread + Session-Thread rufen gleichzeitig EDSDK auf
                    pass
                elif not CANON_AVAILABLE:
                    problem_text = t(self.config, "topbar.camera_edsdk_missing")
                else:
                    # Kamera nicht aktiv → sicher EDSDK aufzurufen
                    from src.camera.canon import CanonCameraManager
                    from src.camera import edsdk as _edsdk
                    cameras = CanonCameraManager.list_cameras()
                    if not cameras:
                        problem_text = t(self.config, "topbar.camera_missing")
                    # Kamera-Handles freigeben (sonst EDSDK Handle-Leak bei jedem Check!)
                    for cam in cameras:
                        ref = cam.get("ref")
                        if ref:
                            try:
                                _edsdk.release(ref)
                            except Exception:
                                pass
            elif camera_type == "nikon":
                # Nikon läuft über die FexoNikonBridge (stdio, unsichtbar).
                # Wenn die Kamera bereits aktiv ist, KEINE weiteren Anfragen
                # (kein Eingriff in Session). list_cameras() fragt nur eine
                # BEREITS laufende Bridge (startet nichts auf dem UI-Thread).
                if self.camera_manager.is_initialized:
                    pass
                else:
                    from src.camera.nikon import NikonCameraManager
                    if not NikonCameraManager.is_available(self.config):
                        problem_text = t(self.config, "topbar.camera_bridge_missing")
                    elif not NikonCameraManager.list_cameras(self.config):
                        problem_text = t(self.config, "topbar.camera_nikon_missing")
            else:
                # Webcam: Prüfen ob Kamera erreichbar ist
                cam_idx = self.config.get("camera_index", 0)
                if cam_idx < 0:
                    # Keine externe Kamera konfiguriert → nochmal suchen
                    # (Kamera könnte im laufenden Betrieb angesteckt worden sein)
                    #
                    # 2.4.40: NICHT bei jedem Blinken. Die volle Suche öffnet
                    # echte DirectShow-Geräte und ist auf dem Atom der teuerste
                    # Posten im Leerlauf; alle 2 s war das ein Dauerlauf.
                    seit = time.time() - getattr(self, "_letzte_kamerasuche", 0.0)
                    if seit < 20.0:
                        # Nur blinken lassen, nichts anfassen.
                        problem_text = t(self.config, "topbar.camera_missing")
                    else:
                        self._letzte_kamerasuche = time.time()
                        from src.camera.webcam import WebcamManager
                        available = WebcamManager.list_cameras()
                        befund = WebcamManager.erkenne_kamera(available)
                        best_idx = befund["index"]
                        if best_idx >= 0:
                            best_name = next(
                                (c["name"] for c in available if c["index"] == best_idx), "?")
                            logger.info(
                                f"📷 Externe Kamera gefunden: [{best_idx}] {best_name} "
                                f"— {befund['begruendung']}"
                            )
                            found_webcam_index = best_idx
                            # Kein problem_text → Warnung verschwindet
                        else:
                            # Bei "unbestimmt" wird der Index NICHT laufend neu
                            # überschrieben — nur die Warnung bleibt stehen.
                            logger.debug(
                                f"Kamera-Wächter: weiterhin keine Kamera "
                                f"({befund['zustand']}) — {befund['begruendung']}"
                            )
                            problem_text = t(self.config, "topbar.camera_missing")
                elif self.camera_manager.is_initialized:
                    pass  # Kamera aktiv → OK
                elif (time.time() - getattr(self, "_letzte_vollpruefung", 0.0)) >= 60.0:
                    # ── VOLLE GEGENPRÜFUNG, höchstens jede Minute ──────────
                    # 2.4.40, Nachbesserung: Bisher wurde bei gesetztem Index
                    # NUR gefragt „lässt sich Index N öffnen?". Die abgeklebte
                    # interne Kamera lässt sich anstandslos öffnen — die
                    # Warnung verschwand also auch dann, wenn N längst auf sie
                    # zeigt (z.B. weil das USB-Kabel der C922 im laufenden
                    # Betrieb rausgerutscht ist und die Indizes nachrutschen).
                    # Deshalb wird der Index regelmäßig neu belegt statt nur
                    # angetippt. Kosten: eine Geräteaufzählung (wenige ms) plus
                    # so viele cv2-Öffnungen, wie DirectShow Geräte meldet.
                    self._letzte_vollpruefung = time.time()
                    from src.camera.webcam import WebcamManager
                    available = WebcamManager.list_cameras()
                    befund = WebcamManager.erkenne_kamera(available)
                    best_idx = befund["index"]
                    aktuelle = next(
                        (c for c in befund.get("kameras", []) if c.get("index") == cam_idx),
                        None)

                    if best_idx >= 0 and best_idx != cam_idx:
                        best_name = next(
                            (c["name"] for c in available if c["index"] == best_idx), "?")
                        logger.warning(
                            f"📷 Kamera-Index korrigiert: [{cam_idx}] → [{best_idx}] "
                            f"{best_name} — {befund['begruendung']}"
                        )
                        found_webcam_index = best_idx
                    elif best_idx >= 0:
                        found_webcam_index = best_idx   # bestätigt, Warnung weg
                    elif aktuelle is not None and aktuelle.get("einordnung") == "intern":
                        # Der eingestellte Index zeigt nachweislich auf eine
                        # interne Kamera. Sofort abschalten — das ist genau der
                        # Fall, den die Sperre verhindern soll.
                        logger.warning(
                            f"⚠️ Eingestellte Kamera [{cam_idx}] ist eine INTERNE "
                            f"Kamera ({aktuelle.get('einordnung_grund', '')}) — "
                            f"wird abgeschaltet."
                        )
                        found_webcam_index = -1
                        problem_text = t(self.config, "topbar.camera_missing")
                    elif befund["zustand"] == "intern":
                        logger.warning(
                            f"⚠️ Nur noch interne Kameras sichtbar — "
                            f"{befund['begruendung']}. Kamera wird abgeschaltet."
                        )
                        found_webcam_index = -1
                        problem_text = t(self.config, "topbar.camera_missing")
                    elif (getattr(self, "_camera_index_bestaetigt", False)
                          or befund.get("bestaetigter_index", -1) == cam_idx
                          or self.config.get("camera_index_manuell", False)):
                        # Unbestimmter Befund, aber für DIESEN Index gibt es
                        # einen Beweis (in diesem Lauf bestätigt, im Gedächtnis
                        # bestätigt oder im Admin-Menü von Hand gewählt). Ein
                        # misslungener Suchlauf kippt das NICHT — genau daran ist
                        # 2.4.39 gescheitert. Trotzdem prüfen, ob er noch aufgeht.
                        logger.debug(
                            f"Kamera-Wächter: Befund unbestimmt "
                            f"({befund['zustand']}), bestätigter camera_index "
                            f"[{cam_idx}] bleibt — {befund['begruendung']}"
                        )
                        if not any(c.get("index") == cam_idx for c in available):
                            problem_text = t(self.config, "topbar.camera_missing")
                    else:
                        logger.warning(
                            f"⚠️ Kamera-Wächter: camera_index [{cam_idx}] ist nicht "
                            f"als externe Kamera belegt ({befund['zustand']}: "
                            f"{befund['begruendung']}) — wird abgeschaltet."
                        )
                        found_webcam_index = -1
                        problem_text = t(self.config, "topbar.camera_missing")
                else:
                    # 2.4.31: NUR unter der gemeinsamen Kamera-Sperre anfassen.
                    # Genau diese Zeile stand im Absturz-Protokoll von Box 044
                    # (19.08.), waehrend ein zweiter Thread parallel in
                    # WebcamManager.list_cameras() dieselbe DirectShow-Kamera
                    # oeffnete -> Heap-Zerstoerung (0xc0000374) und die App war weg.
                    #
                    # 2.4.37: Die Sperre wird nur noch MIT Zeitgrenze genommen.
                    # `with camera_hardware_lock():` wartet sonst unbegrenzt.
                    # Haengt irgendwo ein Kamera-Aufruf und haelt die Sperre,
                    # blockiert dieser Waechter-Thread fuer immer — und mit ihm
                    # jeder spaetere Kamerazugriff, inklusive Session-Start.
                    # Bekommen wir die Sperre nicht, wird NICHT geprueft und
                    # auch KEINE Warnung gemeldet: "gerade belegt" ist kein
                    # Beweis fuer "Kamera fehlt".
                    import cv2
                    from src.camera.webcam import camera_hardware_lock
                    sperre = camera_hardware_lock()
                    if sperre.acquire(timeout=5.0):
                        try:
                            cap = cv2.VideoCapture(cam_idx, cv2.CAP_DSHOW)
                            if cap.isOpened():
                                cap.release()
                            else:
                                problem_text = t(self.config, "topbar.camera_missing")
                        finally:
                            sperre.release()
                    else:
                        logger.debug(
                            "Kamera-Pruefung uebersprungen: Hardware-Sperre belegt"
                        )
        except Exception:
            problem_text = t(self.config, "topbar.camera_error")

        # Ergebnis zurück auf den UI-Thread (Config-Änderung + Label-Update).
        # Crash-sicher: Läuft die Mainloop (noch) nicht, würde root.after() aus
        # diesem Thread eine RuntimeError werfen und die Kamera-Prüfung dauerhaft
        # beenden. Deshalb bei Bedarf kurz warten und erneut versuchen.
        for _attempt in range(30):
            try:
                self.root.after(
                    0, lambda p=problem_text, idx=found_webcam_index: self._on_camera_status_result(p, idx)
                )
                return
            except RuntimeError:
                time.sleep(0.2)
        # Konnte nicht zustellen → Flag zurücksetzen, damit die Prüfung
        # (vom Main-Thread neu geplant) nicht dauerhaft blockiert bleibt.
        self._camera_check_running = False

    def _on_camera_status_result(self, problem_text, found_webcam_index):
        """UI-Thread: Ergebnis der Hintergrund-Prüfung anzeigen + neu planen."""
        self._camera_check_running = False

        if found_webcam_index is not None:
            self.config["camera_index"] = found_webcam_index
            # Merken, ob dieser Index in DIESEM Lauf per Erkennung als extern
            # belegt wurde. Nur ein so belegter (oder von Hand gewählter)
            # Index überlebt später einen misslungenen Suchlauf.
            self._camera_index_bestaetigt = found_webcam_index >= 0
            if found_webcam_index >= 0:
                self.config["camera_index_manuell"] = False

        if problem_text:
            # Blinkend anzeigen (wie USB/Drucker-Warnung)
            self._camera_blink_state = not self._camera_blink_state

            if self._camera_blink_state:
                self.camera_status.configure(
                    text=f"📷 {problem_text}",
                    text_color="#ffffff",
                    fg_color="#ff0000"
                )
            else:
                self.camera_status.configure(
                    text=f"📷 {problem_text}",
                    text_color="#000000",
                    fg_color="#ffcc00"
                )
            self.camera_status.pack(side="right", padx=4)
            # Bei Problem: schneller blinken (2s statt 1.5s - weniger EDSDK-Last)
            self.root.after(2000, self._check_camera_status)
        else:
            # Alles OK -> Warnung verstecken
            self._camera_blink_state = False
            self.camera_status.pack_forget()
            # Kein Problem: seltener prüfen (15s)
            self.root.after(15000, self._check_camera_status)

    def _check_power_status(self):
        """Prüft Stromversorgung - Grün=Netzbetrieb, BLINKEND=kein Strom"""
        try:
            import ctypes

            class SYSTEM_POWER_STATUS(ctypes.Structure):
                _fields_ = [
                    ('ACLineStatus', ctypes.c_byte),
                    ('BatteryFlag', ctypes.c_byte),
                    ('BatteryLifePercent', ctypes.c_byte),
                    ('SystemStatusFlag', ctypes.c_byte),
                    ('BatteryLifeTime', ctypes.c_ulong),
                    ('BatteryFullLifeTime', ctypes.c_ulong),
                ]

            status = SYSTEM_POWER_STATUS()
            ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))

            on_ac = status.ACLineStatus == 1

            if on_ac:
                self._power_blink_state = False
                self.power_status.configure(
                    text="⚡",
                    text_color=COLORS["success"],
                    fg_color=COLORS["bg_light"]
                )
                self.root.after(10000, self._check_power_status)
            else:
                # Kein Strom: Blinkend rot/gelb
                self._power_blink_state = not self._power_blink_state
                if self._power_blink_state:
                    self.power_status.configure(
                        text="⚡",
                        text_color="#ffffff",
                        fg_color="#ff0000"
                    )
                else:
                    self.power_status.configure(
                        text="⚡",
                        text_color="#000000",
                        fg_color="#ffcc00"
                    )
                self.root.after(1500, self._check_power_status)

        except Exception:
            self.root.after(30000, self._check_power_status)

    def show_screen(self, screen_name: str, **kwargs):
        """Wechselt zu einem Screen"""
        from src.ui.screens.start import StartScreen
        from src.ui.screens.session import SessionScreen
        from src.ui.screens.filter import FilterScreen
        from src.ui.screens.final import FinalScreen
        from src.ui.screens.video import VideoScreen
        
        # Alten Screen ausblenden
        if self.current_screen:
            if hasattr(self.current_screen, "on_hide"):
                self.current_screen.on_hide()
            self.current_screen.pack_forget()
        
        # Screen-Klassen
        screen_classes = {
            "start": StartScreen,
            "session": SessionScreen,
            "filter": FilterScreen,
            "final": FinalScreen,
            "video": VideoScreen,
        }
        
        # Screen erstellen falls nicht vorhanden oder neu erstellen für frischen State
        if screen_name in ["session", "filter", "final", "video"]:
            # Diese Screens immer neu erstellen
            if screen_name in self.screens:
                self.screens[screen_name].destroy()
            self.screens[screen_name] = screen_classes[screen_name](self.container, self)
        elif screen_name not in self.screens:
            self.screens[screen_name] = screen_classes[screen_name](self.container, self)
        
        # Screen anzeigen
        self.current_screen = self.screens[screen_name]
        self.current_screen_name = screen_name
        self.current_screen.pack(fill="both", expand=True)

        # Top-Bar Sichtbarkeit: Nur im Start-Screen oder im DEV Mode
        is_dev_mode = self.config.get("developer_mode", False)
        show_topbar = (screen_name == "start") or is_dev_mode

        if show_topbar:
            self.top_bar.pack(fill="x", before=self.container)
        else:
            self.top_bar.pack_forget()

        # Screen aktualisieren
        if hasattr(self.current_screen, "on_show"):
            self.current_screen.on_show(**kwargs)

        logger.info(f"Screen gewechselt: {screen_name}")

        # Pending-Dialoge prüfen wenn StartScreen angezeigt wird
        if screen_name == "start":
            self.root.after(500, self._check_pending_dialogs)

        # Stress-Test: Automatisch weitermachen
        if self.stress_test_active:
            self._stress_test_auto_proceed(screen_name)

    def show_admin_dialog(self):
        """Zeigt den Admin-Dialog.

        Im Kiosk-Modus: Dialog als Fullscreen-Overlay (kein Fenstermodus-Wechsel).
        Im Fenstermodus: Dialog als normales Fenster.
        """
        from src.ui.screens.admin import AdminDialog
        is_kiosk = self.config.get("start_fullscreen", True) and self._is_fullscreen
        if not is_kiosk:
            self._exit_fullscreen()
        dialog = AdminDialog(self.root, self.config, kiosk_mode=is_kiosk)
        self.root.wait_window(dialog)

        # Wurde die App aus dem Dialog heraus beendet? Dann ist das Hauptfenster
        # weg und ab hier darf nichts mehr angefasst werden.
        if not self._root_lebt():
            logger.info("Admin-Dialog: App wurde beendet — kein Nacharbeiten mehr")
            return

        # Service-Menü öffnen wenn über Service-PIN angefordert
        if getattr(dialog, '_open_service', False):
            from src.ui.screens.service import ServiceDialog
            service = ServiceDialog(self.root, self)
            self.root.wait_window(service)
            if not self._root_lebt():
                logger.info("Service-Menü: App wurde beendet — kein Nacharbeiten mehr")
                return
        elif dialog.result:
            self.config = dialog.result
            apply_locale_to_config(self.config)
            save_config(self.config)
            self._sync_camera_manager_with_config()
            logger.info("Admin-Einstellungen gespeichert")

            try:
                from src.gallery import set_gallery_app_context, set_gallery_locale
                set_gallery_locale(self.config.get("locale", "de-DE"))
                set_gallery_app_context(self._get_gallery_app_context())
            except Exception:
                pass

            self._update_booking_display()

            try:
                from src.company_network import trigger_monitoring_heartbeat_now
                trigger_monitoring_heartbeat_now(app=self, config=self.config)
            except Exception as e:
                logger.debug(f"Monitoring-Sofortmeldung nach Admin-Speichern fehlgeschlagen: {e}")

            # Service-Kanal laeuft IMMER (Plattform-Fundament) — Hotspot bleibt an,
            # auch ohne gebuchte Galerie. Nur das Foto-Feature folgt gallery_enabled.
            self._start_gallery_if_needed()
            self._push_gallery_feature_flag()

        # StartScreen IMMER aktualisieren nach Dialog-Schließung
        # (auch nach Kunden-Menü 2015 Template-Wechsel, nicht nur nach Admin-Settings)
        if self.current_screen_name == "start" and self.current_screen:
            logger.info("Aktualisiere StartScreen nach Admin-Dialog...")
            self.current_screen.config = self.config
            if hasattr(self.current_screen, "on_show"):
                self.current_screen.on_show()

        # Kiosk-Modus wiederherstellen (nur wenn vorher deaktiviert)
        if not is_kiosk and self.config.get("start_fullscreen", True):
            self.root.after(200, self._enter_fullscreen)
    
    # ========================================
    # Event-Wechsel & FEXOSAFE
    # ========================================

    def _check_pending_dialogs(self):
        """Prüft und zeigt anstehende Dialoge auf dem StartScreen"""
        if self.current_screen_name != "start":
            return

        # Event-Wechsel hat Priorität
        if self._pending_event_change and not self._event_change_dialog_open:
            new_booking = self._pending_event_change
            self._pending_event_change = None
            self._show_event_change_dialog(new_booking)
            return  # Nur ein Dialog gleichzeitig

        # FEXOSAFE Backup
        if self._pending_fexosafe_drive and not self._fexosafe_dialog_open:
            drive = self._pending_fexosafe_drive
            self._pending_fexosafe_drive = None
            self._show_fexosafe_dialog(drive)

    def _show_event_change_dialog(self, new_booking_id: str):
        """Zeigt den Event-Wechsel Dialog mit Lösch-Bestätigung"""
        if self._event_change_dialog_open:
            return

        self._event_change_dialog_open = True
        logger.info(f"Event-Wechsel Dialog: {new_booking_id}")

        # Lokale Bilder zählen für Lösch-Warnung
        image_count = 0
        from src.storage.local import LocalStorage, SINGLES_PATH, PRINTS_PATH
        if SINGLES_PATH.exists():
            image_count += len(list(SINGLES_PATH.glob("*.jpg")))
        if PRINTS_PATH.exists():
            image_count += len(list(PRINTS_PATH.glob("*.jpg")))

        from src.ui.dialogs.event_change import EventChangeDialog

        def on_accept():
            self._event_change_dialog_open = False
            self._execute_event_change(new_booking_id)

        def on_reject():
            self._event_change_dialog_open = False
            logger.info(f"Event-Wechsel abgelehnt: {new_booking_id}")

        EventChangeDialog(
            self.root, new_booking_id,
            on_accept=on_accept,
            on_reject=on_reject,
            image_count=image_count,
            config=self.config
        )

    def _execute_event_change(self, new_booking_id: str):
        """Führt den Event-Wechsel durch"""
        logger.info(f"=== EVENT-WECHSEL: {new_booking_id} ===")

        usb_drive = self.usb_manager.find_usb_stick()
        if not usb_drive:
            logger.error("USB-Stick nicht mehr verfügbar für Event-Wechsel!")
            return

        usb_root = Path(usb_drive)

        # 1. Neue Buchung + Template vom USB laden
        if self.booking_manager.load_from_usb(usb_root, force=True):
            self._update_booking_display()
            self.booking_manager.apply_settings_to_config(self.config)
            reset_event_defaults(self.config)
            self._sync_camera_manager_with_config()
            self._app_uploaded_template_active = False
            self._user_template_override = False
            logger.info(f"Neue Buchung geladen: {new_booking_id}")

        # 2. Alle Bilder auf Tablet löschen
        deleted = self.local_storage.delete_all_images()
        logger.info(f"Event-Wechsel: {deleted} Bilder gelöscht")

        # 3. Galerie: Bilder sind gelöscht, Server zeigt auto leere Galerie

        # 4. Session zurücksetzen (VOR Template-Laden, sonst werden Boxes gelöscht)
        self.reset_session()

        # 5. Alle Caches leeren
        TemplateLoader.clear_cache()
        self.filter_manager.clear_cache()
        self._cached_scaled_overlay = None
        self._cached_overlay_scale = 0.0
        self._cached_overlay_source_size = None
        self.cached_usb_template = None

        # 6. Template in Config eintragen
        self.booking_manager.apply_cached_template_to_config(self.config)

        # 7. USB-Template laden und SOFORT auf Disk persistieren
        from src.config.config import find_usb_template
        usb_template = find_usb_template(include_cache=False)
        if usb_template:
            overlay, boxes = TemplateLoader.load(usb_template, use_cache=False)
            if boxes:
                template_data = {
                    "path": usb_template,
                    "name": os.path.basename(usb_template),
                    "overlay": overlay,
                    "boxes": boxes,
                    "fingerprint": self.booking_manager.template_file_fingerprint(usb_template),
                    "source": "usb",
                }
                self.cached_usb_template = template_data
                self._usb_stick_template = template_data
                self.template_boxes = boxes
                self.overlay_image = overlay
                logger.info(f"Template geladen: {usb_template} ({len(boxes)} Slots)")

                # Template sofort auf Disk cachen (nicht erst bei on_show warten!)
                self._persist_template_to_cache(usb_template)

        # 8. Neues Statistik-Event
        self._start_statistics_event(usb_root)

        # 9. Service-Kanal sicherstellen (laeuft IMMER) + Foto-Feature an gallery_enabled
        self._start_gallery_if_needed()
        self._push_gallery_feature_flag()

        # 10. Config speichern
        save_config(self.config)

        # 11. StartScreen aktualisieren
        if self.current_screen_name == "start" and self.current_screen:
            self.current_screen.config = self.config
            if hasattr(self.current_screen, "on_show"):
                self.current_screen.on_show()

        # 12. System-Test starten
        self._run_system_test()

    def _run_system_test(self):
        """Startet den automatischen System-Test nach Event-Wechsel"""
        from src.ui.dialogs.system_test import SystemTestDialog

        def on_complete(success: bool, errors: list):
            logger.info(f"System-Test abgeschlossen: success={success}, errors={errors}")

            if success:
                self._show_print_mode_confirmation()
            else:
                # Bei fehlgeschlagenem Test direkt weiter
                if self.current_screen_name == "start" and self.current_screen:
                    if hasattr(self.current_screen, "on_show"):
                        self.current_screen.on_show()

        def on_adjust_print():
            logger.info("System-Test: Öffne Druckkorrektur nach Testdruck")
            self._adjust_print_then_show_confirmation()

        SystemTestDialog(
            self.root,
            self,
            on_complete=on_complete,
            on_adjust_print=on_adjust_print
        )

    def _show_print_mode_confirmation(self):
        """Zeigt nach erfolgreichem Event-Test die Druckmodus-Bestätigung."""
        print_enabled = self.config.get("print_enabled", True)
        booking_id = ""
        if self.booking_manager and self.booking_manager._settings:
            booking_id = self.booking_manager._settings.booking_id

        from src.ui.dialogs.print_mode_confirmation import PrintModeConfirmationDialog
        PrintModeConfirmationDialog(
            parent=self.root,
            print_enabled=print_enabled,
            booking_id=booking_id,
            on_confirm=lambda: self._after_print_mode_confirmed(),
            on_adjust_print=lambda: self._adjust_print_then_show_confirmation(),
            on_shutdown=lambda: self._shutdown_for_new_event()
        )

    def _adjust_print_then_show_confirmation(self):
        """Öffnet die Druckkorrektur und danach wieder die Abschlussaktionen."""
        self._show_customer_print_adjustment_dialog()
        self._show_print_mode_confirmation()

    def _shutdown_for_new_event(self):
        """Fährt Windows nach abgeschlossenem Event-Test herunter."""
        import subprocess

        logger.info("Event-Test abgeschlossen: Windows wird heruntergefahren")
        subprocess.Popen(
            ["shutdown", "/s", "/f", "/t", "5", "/c", "FexoBooth: Neues Event bereit"],
            creationflags=0x08000000
        )

    def _show_customer_print_adjustment_dialog(self):
        """Öffnet nur die Druckkorrektur für Kunden/Mitarbeiter, ohne Admin-Settings."""
        from src.ui.screens.admin import AdminDialog

        is_kiosk = self.config.get("start_fullscreen", True) and self._is_fullscreen
        if not is_kiosk:
            self._exit_fullscreen()

        dialog = AdminDialog(
            self.root,
            self.config,
            kiosk_mode=is_kiosk,
            initial_customer_screen="print_adjustment"
        )
        self.root.wait_window(dialog)

        # Auch hier: Wurde die App aus dem Dialog heraus beendet?
        if not self._root_lebt():
            logger.info("Druckkorrektur-Dialog: App wurde beendet")
            return

        if dialog.result:
            self.config = dialog.result
            save_config(self.config)
            logger.info("Druckkorrektur gespeichert")

        if self.current_screen_name == "start" and self.current_screen:
            self.current_screen.config = self.config
            if hasattr(self.current_screen, "on_show"):
                self.current_screen.on_show()

        if not is_kiosk and self.config.get("start_fullscreen", True):
            self.root.after(200, self._enter_fullscreen)

    def _after_print_mode_confirmed(self):
        """Wird aufgerufen nachdem der Druck-Modus bestätigt wurde."""
        if self.current_screen_name == "start" and self.current_screen:
            if hasattr(self.current_screen, "on_show"):
                self.current_screen.on_show()

    def _show_fexosafe_dialog(self, drive: str):
        """Zeigt den FEXOSAFE Backup Dialog"""
        if self._fexosafe_dialog_open:
            return

        self._fexosafe_dialog_open = True
        logger.info(f"FEXOSAFE Dialog: {drive}")

        from src.ui.dialogs.backup import FexosafeBackupDialog

        def on_complete():
            self._fexosafe_dialog_open = False
            self._last_fexosafe_trigger = time.time()
            logger.info("FEXOSAFE Backup abgeschlossen")

        FexosafeBackupDialog(self.root, self, drive, on_complete=on_complete)

    def play_video(self, video_key: str, next_screen: str):
        """Spielt ein Video ab und wechselt dann zum nächsten Screen

        Args:
            video_key: Config-Key für Video (z.B. "video_start", "video_end")
            next_screen: Screen nach Video-Ende
        """
        # 2.4.42: Der Stress-Test ueberspringt Videos NICHT mehr.
        # Frueher stand hier "Videos ueberspringen fuer schnellere Zyklen".
        # Das hat einen ganzen Teilbereich vom Test ausgenommen: VLC starten,
        # ins Fenster einbetten und wieder abbauen, Bildschirmwechsel
        # Session -> Video -> Session, Kamera freigeben und neu holen,
        # LiveView-Worker beenden und neu starten.
        # Genau dort trat am 20.08.2026 auf Box 101 ein 15-Sekunden-Freeze auf
        # (ein 2-Sekunden-Video lief 17,5 s, UI-Thread 16,7 s blockiert bei
        # 22 % CPU). Der Stress-Test haette ihn nie gefunden, egal wie lange er
        # laeuft. Christians Entscheidung: "die videos muessen immer laufen,
        # sonst ist es nicht realistisch". Weniger Zyklen pro Stunde ist der
        # Preis dafuer, dass der Test abbildet, was im Betrieb wirklich passiert.

        video_path = self.config.get(video_key, "")
        
        logger.info(f"🎬 play_video aufgerufen: key={video_key}, path='{video_path}'")
        
        if not video_path:
            logger.info(f"🎬 Video '{video_key}' nicht konfiguriert - überspringe")
            self.show_screen(next_screen)
            return
        
        if not os.path.exists(video_path):
            logger.warning(f"🎬 Video-Datei nicht gefunden: {video_path}")
            self.show_screen(next_screen)
            return
        
        # Video-Screen anzeigen und abspielen
        logger.info(f"🎬 Starte Video: {video_path}")
        self.show_screen("video")
        self.current_screen.play(video_path, next_screen)

        # Kamera vorinitialisieren während Video läuft (für schnellen Session-Start)
        # VLC spielt in eigenem Thread weiter, kurze Tkinter-Blockade (~1s) ist okay
        if next_screen == "session" and not self.camera_manager.is_initialized:
            self.root.after(200, self._pre_init_camera)
    
    def _pre_init_camera(self):
        """Kamera vorinitialisieren während Video läuft (Background-Warmup)"""
        if self.camera_manager.is_initialized:
            return  # Bereits initialisiert (z.B. durch schnelle Wiedergabe)

        # Aufloesung zentral bestimmen (2.4.43). Vorher stand die Rechnung
        # `int(live_res * 0.75)` hier, in session.on_show und im System-Test
        # dreimal getrennt — eine Box haette je nach Weg in unterschiedlichen
        # Aufloesungen laufen koennen.
        breite, hoehe = vorschau_aufloesung(self.config)
        betriebsart = ("Dauerbetrieb" if True
                       else "klassisch")
        logger.info(
            f"🎥 Kamera-Vorinitialisierung während Video: {breite}x{hoehe} ({betriebsart})"
        )
        # Betriebsart VOR dem Oeffnen anmelden (2.4.44): Der Dauerbetrieb haengt
        # damit am Schalter und nicht an der zufaellig angeforderten Aufloesung.
        setzer = getattr(self.camera_manager, "set_dauerbetrieb_hd", None)
        if setzer is not None:
            setzer(True)  # 2.4.45: kein Schalter mehr, Dauerbetrieb ist der Weg

        if self.camera_manager.initialize(
            self.config.get("camera_index", 0),
            breite,
            hoehe
        ):
            logger.info("🎥 Kamera vorinitialisiert - Session-Start wird schneller!")
        else:
            logger.warning("🎥 Kamera-Vorinitialisierung fehlgeschlagen (wird bei Session-Start erneut versucht)")

    def play_video_and_return(self, video_path: str, callback):
        """Spielt ein Video ab und ruft dann Callback auf (für Zwischen-Videos)

        Args:
            video_path: Direkter Pfad zum Video
            callback: Funktion die nach Video-Ende aufgerufen wird
        """
        # 2.4.42: Auch die Zwischen-Videos laufen im Stress-Test mit.
        # Begruendung siehe play_video() weiter oben.

        logger.info(f"🎬 play_video_and_return aufgerufen: path='{video_path}'")
        
        if not video_path:
            logger.info(f"🎬 Zwischen-Video nicht konfiguriert - überspringe")
            callback()
            return
        
        if not os.path.exists(video_path):
            logger.warning(f"🎬 Zwischen-Video nicht gefunden: {video_path}")
            callback()
            return
        
        # Video-Screen anzeigen
        logger.info(f"🎬 Starte Zwischen-Video: {video_path}")
        self.show_screen("video")
        # Abspielen mit Callback statt Screen-Wechsel
        self.current_screen.play(video_path, "session", on_complete=callback)
    
    def _resolve_template_path(self, template_path: str) -> str:
        """Löst Template-Pfad auf (relativ oder absolut)"""
        from pathlib import Path
        
        if not template_path:
            return ""
        
        # Absoluter Pfad?
        if os.path.isabs(template_path) and os.path.exists(template_path):
            return template_path
        
        # Relativer Pfad - versuche verschiedene Basis-Verzeichnisse
        search_bases = [
            Path(__file__).parent.parent,  # src/..
            Path.cwd(),  # Aktuelles Verzeichnis
            Path("C:/fexobooth/fexobooth-v2") if os.name == "nt" else None,  # Windows Install
        ]
        
        for base in search_bases:
            if base is None:
                continue
            full_path = base / template_path
            if full_path.exists():
                logger.debug(f"Template-Pfad aufgelöst: {template_path} -> {full_path}")
                return str(full_path)
        
        # Pfad wie angegeben zurückgeben
        return template_path
    
    def load_template(self, template_key: str) -> bool:
        """Lädt ein Template
        
        Args:
            template_key: Key wie "template1", "template2"
        """
        logger.info(f"=== Template laden: {template_key} ===")
        
        # Debug: Alle Template-Pfade ausgeben
        template_paths = self.config.get("template_paths", {})
        logger.debug(f"Konfigurierte Template-Pfade: {template_paths}")
        
        template_path = template_paths.get(template_key, "")
        logger.info(f"Template-Pfad für '{template_key}': {template_path}")
        
        if not template_path:
            logger.warning(f"Kein Pfad für Template '{template_key}' konfiguriert!")
            logger.debug(f"Verfügbare Keys: {list(template_paths.keys())}")
            self.template_path = None
            self.template_boxes = []
            self.overlay_image = None
            return False
        
        # Pfad auflösen (relativ -> absolut)
        resolved_path = self._resolve_template_path(template_path)
        logger.info(f"Aufgelöster Pfad: {resolved_path}")
        
        if not os.path.exists(resolved_path):
            logger.error(f"Template-Datei existiert nicht: {resolved_path}")
            self.template_path = None
            self.template_boxes = []
            self.overlay_image = None
            return False
        
        logger.info(f"Lade Template von: {resolved_path}")
        overlay, boxes = TemplateLoader.load(resolved_path)
        
        if overlay and boxes:
            self.template_path = resolved_path
            self.template_boxes = boxes
            self.overlay_image = overlay
            # Overlay-Cache invalidieren (neues Template = neues Overlay)
            self._cached_scaled_overlay = None
            self._cached_overlay_scale = 0.0
            self._cached_overlay_source_size = None
            logger.info(f"✅ Template geladen: {len(boxes)} Foto-Slots, Overlay {overlay.size}")
            for i, box in enumerate(boxes):
                logger.debug(f"  Slot {i+1}: {box}")
            return True
        
        logger.error(f"Template-Loader gab None zurück für: {resolved_path}")
        return False
    
    def reset_session(self):
        """Setzt die Session zurück (Kamera bleibt initialisiert für schnellen Neustart)"""
        self.photos_taken = []
        self.current_photo_index = 0
        self.current_filter = "none"
        self.template_path = None
        self.template_boxes = []
        self.overlay_image = None
        self.prints_in_session = 0
        # Overlay-Cache invalidieren
        self._cached_scaled_overlay = None
        self._cached_overlay_scale = 0.0
        self._cached_overlay_source_size = None
        # Kamera NICHT freigeben - bleibt initialisiert für schnellen Session-Start
        # (Neuinitialisierung dauert ~5s, LiveView-Restart nur ~1s)
        # LiveView stoppen falls aktiv (wird bei nächster Session neu gestartet)
        if self.camera_manager.is_initialized and hasattr(self.camera_manager, 'stop_live_view'):
            self.camera_manager.stop_live_view()
        self.filter_manager.clear_cache()
        logger.info("Session zurückgesetzt (Kamera bleibt initialisiert)")
    
    # ========================================
    # Stress-Test (Developer Mode)
    # ========================================

    def _toggle_stress_test(self):
        """Belastungstest ein-/ausschalten"""
        if self.stress_test_active:
            self._stop_stress_test()
        else:
            self._start_stress_test()

    def _start_stress_test(self):
        """Startet den Belastungstest - simuliert realistisches Nutzerverhalten"""
        self.stress_test_active = True
        self.stress_test_count = 0
        self.stress_test_redos = 0
        self.stress_test_btn.configure(
            text="STOP (0)",
            fg_color=COLORS["error"],
            hover_color="#ff4444"
        )
        logger.info("=" * 60)
        logger.info("BELASTUNGSTEST GESTARTET - Realistische Simulation")
        logger.info("=" * 60)

        # Wenn auf dem Start-Screen, sofort loslegen
        if self.current_screen_name == "start":
            delay = random.randint(500, 1500)
            self.root.after(delay, self._stress_test_auto_start)

    def _stop_stress_test(self):
        """Stoppt den Belastungstest"""
        self.stress_test_active = False
        self.stress_test_btn.configure(
            text=f"STRESS TEST ({self.stress_test_count})",
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["warning"]
        )
        logger.info("=" * 60)
        logger.info(f"BELASTUNGSTEST GESTOPPT: {self.stress_test_count} Sessions, "
                     f"{self.stress_test_redos} Redos")
        logger.info("=" * 60)

    def _stress_test_auto_proceed(self, screen_name: str):
        """Stress-Test: Automatisch zum nächsten Schritt mit zufälligem Delay"""
        if not self.stress_test_active:
            return

        if screen_name == "start":
            delay = random.randint(800, 2000)
            self.root.after(delay, self._stress_test_auto_start)
        elif screen_name == "filter":
            # User schaut sich Filter an, klickt durch
            delay = random.randint(500, 1500)
            self.root.after(delay, self._stress_test_auto_filter)
        elif screen_name == "final":
            # User betrachtet Ergebnis
            delay = random.randint(1500, 4000)
            self.root.after(delay, self._stress_test_auto_finish)

    def _stress_test_auto_start(self):
        """Stress-Test: Template auswählen und starten (kein Single-Modus)"""
        if not self.stress_test_active:
            return

        start_screen = self.screens.get("start")
        if not start_screen or not start_screen.cards:
            return

        # Template-Karten bevorzugen (kein "single" - Stresstest soll Template feuern)
        template_cards = [(k, c) for k, c in start_screen.cards.items() if k != "single"]
        if template_cards:
            key, card = random.choice(template_cards)
        else:
            # Fallback: Nur Single verfügbar
            key, card = list(start_screen.cards.items())[0]
        start_screen._select_card(card, key)
        logger.info(f"Stress-Test: Template '{key}' gewählt")

        if start_screen.selected_option:
            # Kurze Pause wie ein echter User der auf Start tippt
            delay = random.randint(300, 800)
            self.root.after(delay, lambda: (
                start_screen._on_start() if self.stress_test_active else None
            ))

    def _stress_test_auto_filter(self):
        """Stress-Test: Zufälligen Filter auswählen, evtl. mehrere durchprobieren"""
        if not self.stress_test_active:
            return

        screen = self.current_screen
        if not hasattr(screen, 'filter_buttons') or not screen.filter_buttons:
            # Fallback: einfach weiter
            if hasattr(screen, '_on_continue'):
                screen._on_continue()
            return

        buttons = list(screen.filter_buttons.values())

        # 40% Chance: User probiert mehrere Filter durch bevor er sich entscheidet
        if random.random() < 0.4:
            self._stress_test_browse_filters(buttons, browse_count=random.randint(2, 4))
        else:
            # Direkt einen zufälligen Filter wählen
            btn = random.choice(buttons)
            screen._select_filter(btn)
            logger.info(f"Stress-Test: Filter '{btn.filter_key}' gewählt")
            delay = random.randint(400, 1200)
            self.root.after(delay, self._stress_test_click_continue)

    def _stress_test_browse_filters(self, buttons, browse_count, current=0):
        """Stress-Test: Durch mehrere Filter klicken (realistisches Stöbern)"""
        if not self.stress_test_active or current >= browse_count:
            # Fertig mit Stöbern -> Weiter
            delay = random.randint(300, 800)
            self.root.after(delay, self._stress_test_click_continue)
            return

        screen = self.current_screen
        if not hasattr(screen, '_select_filter'):
            return

        btn = random.choice(buttons)
        screen._select_filter(btn)
        logger.info(f"Stress-Test: Filter durchstöbern ({current+1}/{browse_count}): "
                     f"'{btn.filter_key}'")

        # Nächsten Filter nach kurzem Delay
        delay = random.randint(400, 1000)
        self.root.after(delay, lambda: self._stress_test_browse_filters(
            buttons, browse_count, current + 1
        ))

    def _stress_test_click_continue(self):
        """Stress-Test: Weiter-Button auf Filter-Screen drücken"""
        if not self.stress_test_active:
            return
        if hasattr(self.current_screen, '_on_continue'):
            self.current_screen._on_continue()

    def _stress_test_auto_finish(self):
        """Stress-Test: Final-Screen - zufällig Nochmal oder Fertig"""
        if not self.stress_test_active:
            return

        self.stress_test_count += 1
        self.stress_test_btn.configure(text=f"STOP ({self.stress_test_count})")

        # Zufällige Aktion wie ein echter Benutzer
        # 25% Redo (nochmal fotografieren), 75% Fertig
        do_redo = random.random() < 0.25

        if do_redo and hasattr(self.current_screen, '_on_redo'):
            self.stress_test_redos += 1
            logger.info(f"Stress-Test Session #{self.stress_test_count}: "
                         f"REDO (Redos gesamt: {self.stress_test_redos})")
            self.current_screen._on_redo()
        else:
            logger.info(f"Stress-Test Session #{self.stress_test_count}: FERTIG")
            if hasattr(self.current_screen, '_on_finish'):
                self.current_screen._on_finish()

    def _starte_canon_event_takt(self):
        """Holt regelmäßig die Kamera-Ereignisse ab — NUR bei Canon-DSLR.

        2.4.46 — Das war die Ursache dafür, dass die Spiegelreflexkameras auf
        den Box-Tests am 21.08.2026 KEIN EINZIGES Foto lieferten (Box 245:
        0 von 133, Box 248: 0 von 79 — alles nur Notlösungen).

        Warum: Canons Kamera-Bibliothek meldet "Bild ist fertig" über die
        Windows-Nachrichtenschlange, und zwar an den Programmfaden, der die
        Kamera geöffnet hat — das ist der Haupt-Faden mit der Bedienoberfläche.
        Abgeholt wurde die Meldung aber nur in der Warteschleife der Aufnahme,
        und die läuft seit dem Umbau auf Hintergrund-Aufnahme in einem NEBEN-
        Faden. Die Meldungen blieben also ungelesen liegen. Im Box-Log stand
        deshalb kein einziges `>>> OBJECT EVENT`.

        SICHERHEIT FÜR DIE FLOTTE: Dieser Takt startet ausschließlich, wenn der
        Kameratyp 'canon' ist. Bei Webcam-Boxen — also der kompletten laufenden
        Flotte — passiert hier gar nichts, es wird kein Timer angelegt.

        Kosten: ein sehr kurzer Aufruf alle 50 ms. Auf den schwachen Tablets
        gemessen unkritisch, weil EdsGetEvent() ohne wartende Ereignisse sofort
        zurückkehrt.
        """
        if self.config.get("camera_type") != "canon":
            return

        # Nur EIN Takt gleichzeitig. Ohne die Sperre legt jeder Kameratyp-Wechsel
        # einen weiteren Timer an und die Box pumpt am Ende vielfach parallel.
        if getattr(self, "_canon_takt_laeuft", False):
            logger.debug("Canon-Event-Takt läuft bereits")
            return
        self._canon_takt_laeuft = True

        intervall_ms = 50

        def _takt():
            # Typ kann sich zur Laufzeit ändern (Buchung stellt auf Webcam um)
            if self.config.get("camera_type") != "canon":
                self._canon_takt_laeuft = False
                logger.info("Canon-Event-Takt beendet (Kameratyp gewechselt)")
                return

            try:
                pumpe = getattr(self.camera_manager, "pump_events", None)
                if pumpe is not None:
                    pumpe()
            except Exception as e:
                logger.debug(f"Canon-Event-Takt: {e}")

            try:
                self.root.after(intervall_ms, _takt)
            except Exception:
                self._canon_takt_laeuft = False  # Fenster ist weg (App beendet sich)

        logger.info(
            f"Canon-Event-Takt gestartet (alle {intervall_ms}ms im Haupt-Faden) — "
            f"ohne den kommen die aufgenommenen Fotos nicht bei der App an"
        )
        self.root.after(intervall_ms, _takt)

    def run(self):
        """Startet die Anwendung"""
        logger.info("Starte Hauptschleife")
        self._mainloop_started = True
        self._starte_canon_event_takt()
        try:
            self.root.mainloop()
        finally:
            self._mainloop_started = False
    
    def _root_lebt(self) -> bool:
        """Existiert das Hauptfenster noch?

        Wird nach jedem `wait_window(...)` geprueft: Wenn die App aus einem
        Dialog heraus beendet wurde (Beenden-Button im Service-Menue oder
        Ctrl+Shift+Q), ist das Hauptfenster danach zerstoert. Der Code hinter
        dem Warten wuerde dann auf toten Widgets weiterarbeiten und eine
        TclError werfen — mitten im Beenden.
        """
        try:
            return bool(self.root.winfo_exists())
        except Exception:
            return False

    def shutdown(self, grund: str = "unbekannt"):
        """Einziger geordneter Weg, die App zu beenden.

        BEFUND CHRISTIAN 19.08.2026: Der Beenden-Button im Service-Menue (3198)
        schloss zwar das Fenster, liess aber einen Prozess im Task-Manager
        stehen. Ursache: Es gab ZWEI verschiedene Beenden-Wege mit eigenem Code —
        der erprobte Notausstieg (Ctrl+Shift+Q) gab die Kamera frei, der
        Button-Weg nicht. Ausserdem hatte keiner der beiden ein Netz, falls
        `root.destroy()` die Hauptschleife nicht beendet: Dann wird das
        abschliessende `os._exit(0)` in main.py nie erreicht und der Prozess
        laeuft unsichtbar weiter.

        Deshalb laufen jetzt BEIDE Wege hier durch, und der Notausstieg wird
        vorher scharf gemacht. Jeder Aufraeum-Schritt ist einzeln abgesichert —
        beim Beenden darf ein Fehler in Schritt 2 nicht Schritt 3 verhindern.

        Args:
            grund: Klartext fuer das Log (wer hat das Beenden ausgeloest)
        """
        logger.warning(f"App wird beendet (Grund: {grund})")

        # Netz zuerst spannen: Ab hier verschwindet der Prozess garantiert,
        # egal was in den folgenden Schritten oder in Tk noch schiefgeht.
        try:
            from src.utils.shutdown import notausstieg_scharf_machen
            notausstieg_scharf_machen(sekunden=8.0, grund=grund)
        except Exception:
            pass

        for schritt, aktion in (
            ("Taskleiste einblenden", self._show_taskbar),
            ("Benachrichtigungen freigeben", lambda: self._suppress_notifications(False)),
            ("Kamera freigeben", self.camera_manager.release),
        ):
            try:
                aktion()
            except Exception as e:
                logger.warning(f"Beenden — '{schritt}' fehlgeschlagen: {e}")

        # Kindprozesse (FexoNikonBridge) beenden, solange die Verbindung noch
        # steht — os._exit(0) in main.py nimmt sie sonst NICHT mit.
        try:
            from src.utils.shutdown import beende_kindprozesse
            beende_kindprozesse()
        except Exception as e:
            logger.warning(f"Beenden — Kindprozesse: {e}")

        try:
            self.root.destroy()
        except Exception as e:
            # Hauptschleife laesst sich nicht beenden -> Wachhund erledigt es
            logger.warning(f"Beenden — root.destroy() fehlgeschlagen: {e}")

    def _emergency_quit(self):
        """Notfall-Beenden über Ctrl+Shift+Q - funktioniert IMMER, auch im Kiosk-Modus."""
        self.shutdown("Notausstieg Ctrl+Shift+Q")

    def quit(self):
        """Beendet die Anwendung (Altbestand — geht ueber den gemeinsamen Weg)."""
        self.shutdown("quit()")
