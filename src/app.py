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

from src.config.config import load_config, save_config
from src.camera import get_camera_manager, CANON_AVAILABLE
from src.storage.local import get_shared_usb_manager
from src.storage.local import LocalStorage
from src.storage.booking import get_booking_manager, BookingManager
from src.storage.statistics import get_statistics_manager, StatisticsManager
from src.filters import FilterManager
from src.templates.loader import TemplateLoader
from src.templates.renderer import TemplateRenderer
from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PhotoboothApp:
    """Hauptanwendungsklasse"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # CustomTkinter Setup
        ctk.set_appearance_mode("dark")
        
        # Hauptfenster
        self.root = ctk.CTk()
        self.root.title("Fexobooth")
        self.root.configure(fg_color=COLORS["bg_dark"])

        # Fenster-Icon setzen
        self._set_window_icon()

        # App-Referenz am Root speichern (für Service-Menü Zugriff)
        self.root._photobooth_app = self
        
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
        
        # Manager initialisieren
        camera_type = config.get("camera_type", "webcam")
        self.camera_manager = get_camera_manager(camera_type)
        logger.info(f"Kamera-Typ: {camera_type} (Canon verfügbar: {CANON_AVAILABLE})")
        self.usb_manager = get_shared_usb_manager()
        self.booking_manager = get_booking_manager()
        self.statistics = get_statistics_manager()
        self.local_storage = LocalStorage()
        self.filter_manager = FilterManager()
        self.renderer = TemplateRenderer(
            canvas_width=config.get("canvas_width", 1800),
            canvas_height=config.get("canvas_height", 1200)
        )
        
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

        # USB-Sync Dialog State
        self._sync_dialog_open: bool = False  # Verhindert mehrfache Dialoge

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

        # WICHTIG: Settings ZUERST laden, BEVOR UI erstellt wird!
        # Sonst zeigt die UI falsche Optionen (z.B. Single-Foto obwohl deaktiviert)
        self._load_settings_from_usb_immediately()
        
        # Settings auf Config anwenden (VOR UI-Setup!)
        if self.booking_manager.is_loaded:
            logger.info(f"📂 Buchung aktiv: {self.booking_manager.booking_id}")
            
            # Template in Config eintragen
            if self.booking_manager.apply_cached_template_to_config(self.config):
                logger.info("📦 Template wird verwendet")
            
            # BookingSettings auf Config anwenden (allow_single_mode, gallery_enabled, etc.)
            self.booking_manager.apply_settings_to_config(self.config)
        
        # Log aktuelle Config nach Settings-Anwendung
        logger.info(f"📋 Config nach Settings-Load:")
        logger.info(f"   allow_single_mode = {self.config.get('allow_single_mode', True)}")
        logger.info(f"   gallery_enabled = {self.config.get('gallery_enabled', False)}")

        # UI Setup (NACH Settings, damit korrekte Optionen angezeigt werden!)
        self._setup_ui()

        # VLC vorwärmen (verhindert 57s Freeze beim ersten Video)
        try:
            from src.ui.screens.video import warmup_vlc
            warmup_vlc()
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

        # Galerie-Server starten wenn aktiviert (NACH Settings-Anwendung!)
        self._init_gallery_server()

        # Developer Mode: Performance Overlay
        self._init_performance_overlay()

        # Statistik IMMER starten (auch ohne USB/Buchung)
        if not self.statistics.current:
            self._start_statistics_event()
            logger.info("📊 Statistik gestartet (ohne USB)")

        logger.info("PhotoboothApp initialisiert")

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
            if self.booking_manager.load_from_usb(usb_root, force=True):
                new_booking_id = self.booking_manager.booking_id
                logger.info(f"✅ Settings vom USB geladen: {new_booking_id}")

                # Prüfen ob es eine ANDERE Buchung ist als im Cache
                if old_booking_id and new_booking_id and old_booking_id != new_booking_id:
                    logger.info(f"🔄 Neue Buchung beim Start erkannt: {old_booking_id} → {new_booking_id}")
                    self._startup_event_change = new_booking_id

                # Statistik-Event starten
                self._start_statistics_event(usb_root)

        except Exception as e:
            logger.warning(f"USB-Check beim Start fehlgeschlagen: {e}")

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
        """Startet den Galerie-Webserver und Hotspot wenn aktiviert"""
        if not self.config.get("gallery_enabled", False):
            logger.debug("Galerie-Server deaktiviert")
            # Hotspot stoppen wenn Galerie deaktiviert
            self._stop_hotspot_if_running()
            return

        try:
            from src.gallery import start_server, get_gallery_url, start_hotspot
            from pathlib import Path

            # Hotspot im Hintergrund starten (blockiert sonst ~6s)
            gallery_config = self.config.get("gallery", {})
            hs_ssid = gallery_config.get("hotspot_ssid", "")
            hs_password = gallery_config.get("hotspot_password", "")
            def _start_hs():
                try:
                    logger.info("📶 Starte Hotspot für Galerie...")
                    start_hotspot(ssid=hs_ssid, password=hs_password)
                except Exception as e:
                    logger.warning(f"Hotspot-Start fehlgeschlagen: {e}")
            threading.Thread(target=_start_hs, daemon=True, name="Hotspot-Start").start()

            # Galerie-Pfad = immer lokaler Speicher (damit Löschen sofort wirkt)
            gallery_path = self.local_storage.get_images_path()

            if gallery_path:
                port = self.config.get("gallery_port", 8080)
                start_server(gallery_path, port=port)

                # URL für QR-Code speichern
                self.gallery_url = get_gallery_url(port)
                logger.info(f"🌐 Galerie verfügbar: {self.gallery_url}")
            else:
                logger.warning("Kein Bilder-Pfad für Galerie verfügbar")

        except ImportError as e:
            logger.warning(f"Galerie-Modul nicht verfügbar: {e}")
        except Exception as e:
            logger.error(f"Galerie-Server Start fehlgeschlagen: {e}")

    def _stop_hotspot_if_running(self):
        """Stoppt den Hotspot wenn er läuft (Galerie deaktiviert) - im Hintergrund"""
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
        """Startet Galerie + Hotspot wenn noch nicht gestartet"""
        try:
            from src.gallery import is_running, start_server, get_gallery_url, start_hotspot

            # Hotspot starten (auch wenn Galerie schon läuft - Hotspot könnte aus sein)
            gallery_config = self.config.get("gallery", {})
            start_hotspot(
                ssid=gallery_config.get("hotspot_ssid", ""),
                password=gallery_config.get("hotspot_password", "")
            )

            if is_running():
                logger.debug("Galerie läuft bereits")
                return

            # Galerie-Pfad = immer lokal (damit Löschen sofort wirkt)
            gallery_path = self.local_storage.get_images_path()

            if gallery_path:
                port = self.config.get("gallery_port", 8080)
                start_server(gallery_path, port=port)
                self.gallery_url = get_gallery_url(port)
                logger.info(f"🌐 Galerie gestartet: {self.gallery_url}")
        except Exception as e:
            logger.error(f"Galerie-Start fehlgeschlagen: {e}")

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
        
        # Start-Screen anzeigen
        self.show_screen("start")
    
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
                logo_label.pack()
            except Exception as e:
                logger.warning(f"Logo konnte nicht geladen werden: {e}")
                ctk.CTkLabel(
                    logo_frame,
                    text="FEXOBOOTH",
                    font=FONTS["heading"],
                    text_color=COLORS["primary"]
                ).pack()
        else:
            ctk.CTkLabel(
                logo_frame,
                text="FEXOBOOTH",
                font=FONTS["heading"],
                text_color=COLORS["primary"]
            ).pack()

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
            text="Buchung: ---",
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
            text="⚠️ USB",
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
                    text=f"⚠️ KEIN USB!{pending_text}",
                    text_color="#ffffff",
                    fg_color="#ff0000"  # Knallrot
                )
            else:
                self.usb_status.configure(
                    text=f"⚠️ USB FEHLT!{pending_text}",
                    text_color="#000000",
                    fg_color="#ffcc00"  # Gelb
                )

        # Schnellerer Check für Blink-Effekt
        self.root.after(1000, self._check_usb_status)

    def _check_fullscreen_restore(self):
        """Sicherheitsnetz: Stellt Kiosk-Modus wieder her falls er verloren geht.

        Prüft alle 5 Sekunden:
        - Wenn Fullscreen verloren: wiederherstellen (falls kein Dialog offen)
        - Wenn Fullscreen aktiv: Taskleiste re-asserten (KEIN topmost - blockiert Dialoge!)
        """
        if self.config.get("start_fullscreen", True):
            if not self._is_fullscreen:
                # Fullscreen verloren - prüfen ob ein Dialog offen ist
                dialog_open = False
                for child in self.root.winfo_children():
                    if child.winfo_class() == "Toplevel":
                        dialog_open = True
                        break
                if not dialog_open:
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
                text="Buchung: ---",
                text_color=COLORS["text_muted"],
                fg_color=COLORS["bg_light"]
            )

    def _offer_sync_dialog(self):
        """Prüft fehlende Bilder und bietet Sync-Dialog an (gleiches Event)."""
        from src.storage.local import LocalStorage
        import threading

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
            content, text="USB-Stick erkannt",
            font=("Segoe UI", 20, "bold"), text_color=COLORS["primary"]
        ).pack(pady=(20, 5))

        # Info-Text (wird später zu Status-Text)
        status_label = ctk.CTkLabel(
            content,
            text=f"{missing_count} Bild(er) fehlen auf dem USB-Stick.\nJetzt kopieren?",
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
                btn_frame, text="Abbrechen",
                font=FONTS["button"], width=160, height=45,
                fg_color=COLORS["bg_light"], hover_color=COLORS["bg_card"],
                text_color=COLORS["text_primary"],
                corner_radius=SIZES["corner_radius"], command=on_cancel
            )
            cancel_btn.pack()

            # Fortschrittsbalken anzeigen
            progress_bar.set(0)
            progress_bar.pack(pady=(0, 10))

            status_label.configure(text="Kopiere...")

            def progress_callback(copied, total, filename):
                def update():
                    try:
                        progress_bar.set(copied / total)
                        status_label.configure(text=f"Kopiere... {copied}/{total}")
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
                            text=f"Abgebrochen. {copied} Bild(er) kopiert.",
                            text_color=COLORS["warning"]
                        )
                    elif result.get("errors", 0) > 0:
                        status_label.configure(
                            text=f"{copied} kopiert, {result['errors']} Fehler.",
                            text_color=COLORS["warning"]
                        )
                    else:
                        status_label.configure(
                            text=f"{copied} Bild(er) auf USB kopiert!",
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
            btn_frame, text="Kopieren",
            font=FONTS["button"], width=140, height=50,
            fg_color=COLORS["success"], hover_color="#00e676",
            corner_radius=SIZES["corner_radius"], command=on_copy
        ).pack(side="left", padx=10)

        # Abbrechen-Button
        ctk.CTkButton(
            btn_frame, text="Abbrechen",
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
            content, text="USB-Stick erkannt",
            font=("Segoe UI", 20, "bold"), text_color=COLORS["info"]
        ).pack(pady=(20, 5))

        # Laufwerk-Info
        drive_letter = target_drive[0]
        ctk.CTkLabel(
            content,
            text=f"Unbekannter Stick ({drive_letter}:) eingesteckt",
            font=FONTS["small"], text_color=COLORS["text_muted"]
        ).pack(pady=(0, 5))

        # Status-Text
        status_label = ctk.CTkLabel(
            content,
            text=f"{image_count} Bild(er) auf den Stick kopieren?",
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
                btn_frame, text="Abbrechen",
                font=FONTS["button"], width=160, height=45,
                fg_color=COLORS["bg_light"], hover_color=COLORS["bg_card"],
                text_color=COLORS["text_primary"],
                corner_radius=SIZES["corner_radius"], command=on_cancel
            )
            cancel_btn.pack()

            progress_bar.set(0)
            progress_bar.pack(pady=(0, 10))
            status_label.configure(text="Exportiere...")

            def progress_callback(copied, total):
                def update():
                    try:
                        progress_bar.set(copied / total)
                        status_label.configure(text=f"Exportiere... {copied}/{total}")
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
                            text=f"Abgebrochen. {copied} Bild(er) exportiert.",
                            text_color=COLORS["warning"]
                        )
                    elif result.get("errors", 0) > 0:
                        status_label.configure(
                            text=f"{copied} exportiert, {result['errors']} Fehler.",
                            text_color=COLORS["warning"]
                        )
                    else:
                        status_label.configure(
                            text=f"{copied} Bild(er) exportiert!",
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
            btn_frame, text="Exportieren",
            font=FONTS["button"], width=140, height=50,
            fg_color=COLORS["success"], hover_color="#00e676",
            corner_radius=SIZES["corner_radius"], command=on_export
        ).pack(side="left", padx=10)

        # Abbrechen-Button
        ctk.CTkButton(
            btn_frame, text="Abbrechen",
            font=FONTS["button"], width=140, height=50,
            fg_color=COLORS["bg_light"], hover_color=COLORS["bg_card"],
            text_color=COLORS["text_primary"],
            corner_radius=SIZES["corner_radius"], command=close_dialog
        ).pack(side="left", padx=10)

        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

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

        if problem_text:
            logger.info(f"Drucker-Fehler erkannt: '{problem_text}' → Overlay wird gezeigt")
            # Overlay zeigen (kümmert sich um Canon-Dialog + Bestätigung)
            self._show_printer_error_overlay(problem_text)

            # Blinkend in Top-Bar anzeigen
            self._printer_blink_state = not self._printer_blink_state

            if self._printer_blink_state:
                self.printer_status.configure(
                    text=f"⚠️ {problem_text}",
                    text_color="#ffffff",
                    fg_color="#ff0000"
                )
            else:
                self.printer_status.configure(
                    text=f"⚠️ {problem_text}",
                    text_color="#000000",
                    fg_color="#ffcc00"
                )
            self.printer_status.pack(side="right", padx=5)
            self.root.after(1000, self._check_printer_status)
        else:
            # Alles OK -> Warnung verstecken
            self._printer_blink_state = False
            self.printer_status.pack_forget()
            self.root.after(5000, self._check_printer_status)

    def _show_printer_error_overlay(self, error_text: str):
        """Zeigt blockierendes Drucker-Fehler-Overlay

        - Papierstau → automatischer Reset mit Animation
        - Verbrauchsmaterial → wartet bis Material gewechselt
        - other → nur Top-Bar (offline, etc.)
        """
        from src.ui.dialogs.printer_error import PrinterErrorOverlay, classify_error

        category = classify_error(error_text)

        # "other"-Fehler (offline, etc.) nur in Top-Bar anzeigen, kein Overlay
        if category == "other":
            logger.debug(f"Drucker-Fehler '{error_text}' → kein Overlay (other)")
            return

        logger.info(
            f">>> DRUCKER-OVERLAY WIRD ANGEZEIGT: '{error_text}' "
            f"(Kategorie: {category})"
        )
        self._printer_error_overlay = PrinterErrorOverlay(
            self.root, self, error_text, category
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
        """Prüft Kamera-Status - BLINKEND wenn keine Kamera erreichbar

        WICHTIG: EDSDK ist NICHT thread-safe (Windows COM STA)!
        Wenn die Kamera bereits initialisiert ist (z.B. System-Test oder Session),
        dürfen KEINE EDSDK-Aufrufe vom UI-Thread gemacht werden - sonst DEADLOCK!
        """
        problem_text = None

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
                    problem_text = "EDSDK FEHLT!"
                else:
                    # Kamera nicht aktiv → sicher EDSDK aufzurufen
                    from src.camera.canon import CanonCameraManager
                    from src.camera import edsdk as _edsdk
                    cameras = CanonCameraManager.list_cameras()
                    if not cameras:
                        problem_text = "KEINE KAMERA!"
                    # Kamera-Handles freigeben (sonst EDSDK Handle-Leak bei jedem Check!)
                    for cam in cameras:
                        ref = cam.get("ref")
                        if ref and _edsdk.EDSDK_DLL:
                            try:
                                _edsdk.EDSDK_DLL.EdsRelease(ref)
                            except Exception:
                                pass
            else:
                # Webcam: Prüfen ob Kamera erreichbar ist
                if self.camera_manager.is_initialized:
                    pass  # Kamera aktiv → OK
                else:
                    import cv2
                    cap = cv2.VideoCapture(
                        self.config.get("camera_index", 0), cv2.CAP_DSHOW
                    )
                    if cap.isOpened():
                        cap.release()
                    else:
                        problem_text = "KEINE KAMERA!"
        except Exception:
            problem_text = "KAMERA FEHLER!"

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
        """Prüft Stromversorgung - Grün=Netzbetrieb, Orange=Akku"""
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

            percent = status.BatteryLifePercent
            on_ac = status.ACLineStatus == 1

            if on_ac:
                self.power_status.configure(
                    text="⚡",
                    text_color=COLORS["success"],
                    fg_color=COLORS["bg_light"]
                )
            else:
                # Akku-Modus: Prozent anzeigen
                pct_text = f" {percent}%" if 0 <= percent <= 100 else ""
                self.power_status.configure(
                    text=f"⚡{pct_text}",
                    text_color="#ff8c00",  # Orange
                    fg_color=COLORS["bg_light"]
                )
        except Exception:
            pass  # Kein Akku-Info verfügbar (Desktop-PC etc.)

        # Alle 10 Sekunden prüfen (Stromstatus ändert sich selten)
        self.root.after(10000, self._check_power_status)

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

        # Service-Menü öffnen wenn über Service-PIN angefordert
        if getattr(dialog, '_open_service', False):
            from src.ui.screens.service import ServiceDialog
            service = ServiceDialog(self.root, self)
            self.root.wait_window(service)
        elif dialog.result:
            self.config = dialog.result
            save_config(self.config)
            logger.info("Admin-Einstellungen gespeichert")

            # Galerie/Hotspot starten oder stoppen je nach Einstellung
            if self.config.get("gallery_enabled", False):
                self._start_gallery_if_needed()
            else:
                # Galerie deaktiviert -> Hotspot stoppen
                self._stop_hotspot_if_running()

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
            image_count=image_count
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

        # 7. USB-Template laden (für Systemtest)
        from src.config.config import find_usb_template
        usb_template = find_usb_template(include_cache=False)
        if usb_template:
            overlay, boxes = TemplateLoader.load(usb_template, use_cache=False)
            if boxes:
                template_data = {
                    "path": usb_template,
                    "name": os.path.basename(usb_template),
                    "overlay": overlay,
                    "boxes": boxes
                }
                self.cached_usb_template = template_data
                self._usb_stick_template = template_data
                self.template_boxes = boxes
                self.overlay_image = overlay
                logger.info(f"Template geladen: {usb_template} ({len(boxes)} Slots)")

        # 8. Neues Statistik-Event
        self._start_statistics_event(usb_root)

        # 9. Galerie starten/stoppen je nach Settings
        if self.config.get("gallery_enabled", False):
            self._start_gallery_if_needed()
        else:
            self._stop_hotspot_if_running()

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
                # Buchungsmodus-Bestätigung anzeigen
                print_enabled = self.config.get("print_enabled", True)
                booking_id = ""
                if self.booking_manager and self.booking_manager._settings:
                    booking_id = self.booking_manager._settings.booking_id

                from src.ui.dialogs.print_mode_confirmation import PrintModeConfirmationDialog
                PrintModeConfirmationDialog(
                    parent=self.root,
                    print_enabled=print_enabled,
                    booking_id=booking_id,
                    on_confirm=lambda: self._after_print_mode_confirmed()
                )
            else:
                # Bei fehlgeschlagenem Test direkt weiter
                if self.current_screen_name == "start" and self.current_screen:
                    if hasattr(self.current_screen, "on_show"):
                        self.current_screen.on_show()

        SystemTestDialog(self.root, self, on_complete=on_complete)

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
        # Stress-Test: Videos überspringen für schnellere Zyklen
        if self.stress_test_active:
            self.show_screen(next_screen)
            return

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

        logger.info("🎥 Kamera-Vorinitialisierung während Video...")
        cam_settings = self.config.get("camera_settings", {})
        live_res = cam_settings.get("live_view_resolution", 480)
        if self.camera_manager.initialize(
            self.config.get("camera_index", 0),
            live_res,
            int(live_res * 0.75)
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
        # Stress-Test: Videos überspringen, Callback verzögert aufrufen
        if self.stress_test_active:
            self.root.after(50, callback)
            return

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

    def run(self):
        """Startet die Anwendung"""
        logger.info("Starte Hauptschleife")
        self.root.mainloop()
    
    def _emergency_quit(self):
        """Notfall-Beenden über Ctrl+Shift+Q - funktioniert IMMER, auch im Kiosk-Modus."""
        logger.warning("NOTFALL-BEENDEN: Ctrl+Shift+Q gedrückt")
        self._show_taskbar()
        self._suppress_notifications(False)
        try:
            self.camera_manager.release()
        except Exception:
            pass
        self.root.destroy()

    def quit(self):
        """Beendet die Anwendung - stellt Taskleiste und Benachrichtigungen wieder her."""
        self._show_taskbar()
        self._suppress_notifications(False)
        self.camera_manager.release()
        self.root.quit()
