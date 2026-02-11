"""
Fexobooth - Hauptanwendung
Moderne Photobooth-Software für fexobox
"""

import customtkinter as ctk
from typing import Dict, Any, Optional, List
from pathlib import Path
from PIL import Image
import os
import time
import threading
import random

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

        # USB-Sync Dialog State
        self._sync_dialog_open: bool = False  # Verhindert mehrfache Dialoge

        # Event-Wechsel & FEXOSAFE Dialog State
        self._pending_event_change: Optional[str] = None   # Neue booking_id
        self._pending_fexosafe_drive: Optional[str] = None  # Laufwerksbuchstabe
        self._event_change_dialog_open: bool = False
        self._fexosafe_dialog_open: bool = False
        self._last_fexosafe_trigger: float = 0  # Cooldown nach Backup

        # Stress-Test Status (nur im Developer Mode)
        self.stress_test_active: bool = False
        self.stress_test_count: int = 0

        # Drucker initialisieren wenn nicht gesetzt
        self._init_default_printer()

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
        
        # Status-Timer starten
        self._start_status_checks()
        
        # Galerie-Server starten wenn aktiviert (NACH Settings-Anwendung!)
        self._init_gallery_server()
        
        # Developer Mode: Performance Overlay
        self._init_performance_overlay()
        
        # Statistik IMMER starten (auch ohne USB/Buchung)
        if not self.statistics.current:
            self._start_statistics_event()
            logger.info("📊 Statistik gestartet (ohne USB)")
        
        logger.info("PhotoboothApp initialisiert")

    def _load_settings_from_usb_immediately(self):
        """Lädt Settings vom USB-Stick SOFORT beim App-Start
        
        Wichtig: Nicht auf den Timer warten - Settings müssen sofort geladen werden,
        damit allow_single_mode, gallery_enabled etc. von Anfang an korrekt sind.
        """
        from pathlib import Path
        
        try:
            usb_drive = self.usb_manager.find_usb_stick()
            if not usb_drive:
                logger.debug("Kein USB beim Start gefunden - verwende Cache")
                return
            
            usb_root = Path(usb_drive)
            
            # Settings vom USB laden (sucht alle .json Dateien, nimmt neueste)
            logger.info(f"📂 USB gefunden beim Start: {usb_drive}")
            if self.booking_manager.load_from_usb(usb_root, force=True):
                logger.info(f"✅ Settings vom USB geladen: {self.booking_manager.booking_id}")
                
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
        """Aktiviert Vollbildmodus mit overrideredirect + WS_EX_APPWINDOW für Taskmanager"""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # overrideredirect(True) = deckt den gesamten Bildschirm ab (getestet auf Lenovo Miix 310)
        self.root.overrideredirect(True)
        self.root.geometry(f"{screen_width}x{screen_height}+0+0")

        # Kurz topmost setzen damit Fenster sicher im Vordergrund ist
        self.root.attributes("-topmost", True)
        self.root.after(100, lambda: self.root.attributes("-topmost", False))

        # Windows API: WS_EX_APPWINDOW setzen damit App als Vordergrund-Prozess im Taskmanager erscheint
        # (overrideredirect entfernt normalerweise den Taskbar-Eintrag)
        self._set_appwindow()

        self.root.focus_force()
        self._is_fullscreen = True
        logger.info(f"Vollbild aktiviert: {screen_width}x{screen_height}")

    def _exit_fullscreen(self):
        """Beendet Vollbildmodus"""
        self.root.overrideredirect(False)
        self.root.geometry("1024x768")
        self._is_fullscreen = False
        logger.info("Vollbild deaktiviert")
    
    def _set_appwindow(self):
        """Setzt WS_EX_APPWINDOW via Windows API damit die App im Taskmanager als Vordergrund-Prozess erscheint.

        overrideredirect(True) entfernt den Fensterrahmen UND den Taskbar-Eintrag.
        Mit WS_EX_APPWINDOW erzwingen wir den Taskbar-Eintrag zurück.
        """
        import sys
        if sys.platform != "win32":
            return

        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080

            # HWND des Tkinter-Fensters holen
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())

            # Aktuellen Extended Style lesen
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

            # TOOLWINDOW entfernen (versteckt aus Taskbar), APPWINDOW setzen (zeigt in Taskbar)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

            # Fenster kurz verstecken und wieder zeigen damit Windows den Style übernimmt
            self.root.withdraw()
            self.root.after(10, self.root.deiconify)

            logger.info("WS_EX_APPWINDOW gesetzt - App erscheint als Vordergrund-Prozess")
        except Exception as e:
            logger.warning(f"WS_EX_APPWINDOW konnte nicht gesetzt werden: {e}")

    def _toggle_fullscreen(self):
        """Toggle Fullscreen"""
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

        # Stress-Test Button (nur im Developer Mode)
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

        # USB-Status (feste Breite damit Position stabil bleibt)
        self.usb_status = ctk.CTkLabel(
            status_frame,
            text="⚠️ USB",
            font=FONTS["small"],
            text_color=COLORS["warning"],
            fg_color=COLORS["bg_light"],
            corner_radius=8,
            width=145,  # Feste Breite für stabiles Layout
            padx=8,
            pady=5
        )
        self.usb_status.pack(side="right", padx=4)

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
                self._was_usb_available = True
                # Nur bei gleichem Event synchronisieren (kein neues Event erkannt)
                if not new_booking:
                    self._offer_sync_dialog()
        elif not is_available:
            self._was_usb_available = False

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
        """Stellt Fullscreen automatisch wieder her wenn es deaktiviert wurde.

        Prüft alle 10 Sekunden ob start_fullscreen=True aber _is_fullscreen=False.
        z.B. nach Admin-Menü wenn der User das Fenster nur maximiert statt Fullscreen.
        """
        if self.config.get("start_fullscreen", True) and not self._is_fullscreen:
            # Prüfen ob ein Admin-Dialog offen ist (dann NICHT wiederherstellen)
            admin_open = False
            for child in self.root.winfo_children():
                if child.winfo_class() == "Toplevel":
                    admin_open = True
                    break
            if not admin_open:
                logger.info("Auto-Fullscreen: Stelle Vollbild wieder her")
                self._enter_fullscreen()

        self.root.after(10000, self._check_fullscreen_restore)

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
            return

        # Fehlende Bilder im Hintergrund zählen
        def check_missing():
            missing = self.usb_manager.count_missing(local_path)
            if missing > 0:
                self.root.after(0, lambda: self._show_sync_dialog(missing, local_path))
            else:
                logger.debug("USB-Sync: Alle Bilder bereits auf USB")

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

        dialog_w, dialog_h = 420, 250
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - dialog_w) // 2
        y = (screen_h - dialog_h) // 2
        dialog.geometry(f"{dialog_w}x{dialog_h}+{x}+{y}")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

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

                    # Abbrechen-Button durch OK ersetzen
                    for widget in btn_frame.winfo_children():
                        widget.destroy()
                    ctk.CTkButton(
                        btn_frame, text="OK",
                        font=FONTS["button"], width=120, height=45,
                        fg_color=COLORS["primary"], hover_color=COLORS["primary_hover"],
                        corner_radius=SIZES["corner_radius"], command=close_dialog
                    ).pack()

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

    def _check_printer_status(self):
        """Prüft Drucker-Status - BLINKEND wenn Drucker nicht bereit

        Prüft 3 Ebenen:
        1. Drucker-Spooler-Status (offline, error, paper_out, paper_jam)
        2. Druckjob-Queue (fehlgeschlagene Jobs = Kassette/Papier leer)
        3. Canon Status-Monitor Fenster in Vordergrund bringen
        """
        problem_text = None

        try:
            import win32print
            printer_name = self.config.get("printer_name") or win32print.GetDefaultPrinter()

            if not printer_name:
                problem_text = "KEIN DRUCKER!"
            else:
                hPrinter = win32print.OpenPrinter(printer_name)
                try:
                    info = win32print.GetPrinter(hPrinter, 2)

                    status = info.get("Status", 0)
                    attributes = info.get("Attributes", 0)

                    # 1. Spooler-Status-Flags prüfen
                    is_offline = bool(status & 0x80)          # PRINTER_STATUS_OFFLINE
                    is_work_offline = bool(attributes & 0x400) # PRINTER_ATTRIBUTE_WORK_OFFLINE
                    is_error = bool(status & 0x2)              # PRINTER_STATUS_ERROR
                    is_paper_jam = bool(status & 0x8)          # PRINTER_STATUS_PAPER_JAM
                    is_paper_out = bool(status & 0x10)         # PRINTER_STATUS_PAPER_OUT
                    is_not_available = bool(status & 0x1000)   # PRINTER_STATUS_NOT_AVAILABLE
                    is_door_open = bool(status & 0x400000)     # PRINTER_STATUS_DOOR_OPEN
                    is_no_toner = bool(status & 0x40000)       # PRINTER_STATUS_TONER_OUT
                    is_user_intervention = bool(status & 0x100000)  # PRINTER_STATUS_USER_INTERVENTION

                    if is_offline or is_work_offline or is_not_available:
                        problem_text = "DRUCKER AUS!"
                    elif is_paper_out:
                        problem_text = "PAPIER LEER!"
                    elif is_no_toner:
                        problem_text = "KASSETTE LEER!"
                    elif is_paper_jam:
                        problem_text = "PAPIERSTAU!"
                    elif is_door_open:
                        problem_text = "KLAPPE OFFEN!"
                    elif is_user_intervention:
                        problem_text = "DRUCKER PRÜFEN!"
                    elif is_error:
                        problem_text = "DRUCKER FEHLER!"

                    # 2. Druckjob-Queue prüfen (Canon meldet Fehler oft nur hier)
                    if not problem_text:
                        problem_text = self._check_print_jobs(hPrinter)

                finally:
                    win32print.ClosePrinter(hPrinter)

        except Exception:
            problem_text = "DRUCKER FEHLT!"

        # 3. Canon-Treiber-Fehlerfenster erkennen (zuverlässigste Methode!)
        if not problem_text:
            canon_error = self._detect_canon_error_window()
            if canon_error:
                problem_text = canon_error

        if problem_text:
            # Canon Status-Fenster in Vordergrund bringen
            self._bring_printer_dialog_to_front()

            # Blinkend anzeigen (wie USB-Warnung)
            self._printer_blink_state = not self._printer_blink_state

            if self._printer_blink_state:
                self.printer_status.configure(
                    text=f"⚠️ {problem_text}",
                    text_color="#ffffff",
                    fg_color="#ff0000"  # Knallrot
                )
            else:
                self.printer_status.configure(
                    text=f"⚠️ {problem_text}",
                    text_color="#000000",
                    fg_color="#ffcc00"  # Gelb
                )
            self.printer_status.pack(side="right", padx=5)
            # Bei Problem: schneller blinken (1s)
            self.root.after(1000, self._check_printer_status)
        else:
            # Alles OK -> Warnung verstecken
            self._printer_blink_state = False
            self.printer_status.pack_forget()
            # Kein Problem: seltener prüfen (5s)
            self.root.after(5000, self._check_printer_status)

    def _check_print_jobs(self, hPrinter) -> str:
        """Prüft Druckjobs auf Fehler (Canon meldet Kassette/Papier hier)

        Nutzt JOB_INFO Level 2 für das pStatus-Textfeld, das Canon-Treiber
        möglicherweise mit spezifischen Fehlertexten befüllen.

        Returns:
            Fehlertext oder None wenn alles OK
        """
        try:
            import win32print

            # Level 2 für pStatus-Textfeld (Level 1 hat kein pStatus!)
            jobs = win32print.EnumJobs(hPrinter, 0, 10, 2)
            if not jobs:
                return None

            for job in jobs:
                job_status = job.get("Status", 0)

                # Job-Status-Flags (aus winspool.h)
                JOB_STATUS_ERROR = 0x2
                JOB_STATUS_OFFLINE = 0x20
                JOB_STATUS_PAPEROUT = 0x40
                JOB_STATUS_BLOCKED = 0x200
                JOB_STATUS_USER_INTERVENTION = 0x400

                # pStatus: Freitext vom Drucker-Treiber (Canon-spezifisch)
                status_text = (job.get("pStatus") or "").strip()

                # Zuerst Freitext prüfen (spezifischer als Flags)
                if status_text:
                    lower = status_text.lower()
                    logger.info(f"Druckjob pStatus: '{status_text}' (flags=0x{job_status:X})")

                    # Canon Selphy Fehlertexte erkennen
                    if any(w in lower for w in ["ink", "tinte", "kassette", "cartridge", "cassette"]):
                        return "KASSETTE LEER!"
                    elif any(w in lower for w in ["paper", "papier"]):
                        return "PAPIER LEER!"
                    elif any(w in lower for w in ["mismatch", "incorrect", "stimmt nicht"]):
                        return "KASSETTE FALSCH!"
                    elif any(w in lower for w in ["jam", "stau"]):
                        return "PAPIERSTAU!"
                    elif any(w in lower for w in ["cover", "door", "klappe", "deckel"]):
                        return "KLAPPE OFFEN!"
                    else:
                        # Unbekannter Text -> trotzdem anzeigen (gekürzt)
                        short = status_text[:20]
                        return f"FEHLER: {short}"

                # Dann Flags prüfen
                if job_status & JOB_STATUS_PAPEROUT:
                    return "PAPIER/KASSETTE LEER!"
                elif job_status & JOB_STATUS_USER_INTERVENTION:
                    return "DRUCKER PRÜFEN!"
                elif job_status & JOB_STATUS_BLOCKED:
                    return "DRUCK BLOCKIERT!"
                elif job_status & JOB_STATUS_OFFLINE:
                    return "DRUCKER OFFLINE!"
                elif job_status & JOB_STATUS_ERROR:
                    return "DRUCK-FEHLER!"

        except Exception as e:
            logger.debug(f"Job-Check Fehler: {e}")

        return None

    def _detect_canon_error_window(self) -> str:
        """Erkennt Canon-Treiber-Fehlerfenster via Windows EnumWindows API

        Canon SELPHY zeigt bei Papier-/Kassettenfehlern ein eigenes
        Dialog-Fenster. Titel z.B.: 'Canon SELPHY CP1000 (Kopie 1)(USB002)'
        Inhalt z.B.: 'Kein Papier / Kassette falsch eingesetzt!'

        Returns: Kurztext für Status-Leiste oder None
        """
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32

            WNDENUMPROC = ctypes.WINFUNCTYPE(
                wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
            )

            found_text = [None]

            def _read_child_text(hwnd, lParam):
                """Liest Text aus Static-Label Child-Controls"""
                class_buf = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(hwnd, class_buf, 64)

                if class_buf.value.lower() == "static":
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 5:
                        text_buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, text_buf, length + 1)
                        text = text_buf.value.strip()
                        if text and len(text) > 5:
                            found_text[0] = text
                            return False  # Gefunden, Stop
                return True

            # Callback-Referenzen halten (ctypes GC-Schutz)
            child_proc = WNDENUMPROC(_read_child_text)

            def _find_canon_window(hwnd, lParam):
                if not user32.IsWindowVisible(hwnd):
                    return True

                title_buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title_buf, 256)
                title = title_buf.value.lower()

                if "canon selphy" in title:
                    # Child-Controls nach Fehlertext durchsuchen
                    user32.EnumChildWindows(hwnd, child_proc, 0)
                    if not found_text[0]:
                        found_text[0] = "DRUCKER PRÜFEN!"
                    return False  # Gefunden, Stop
                return True

            enum_proc = WNDENUMPROC(_find_canon_window)
            user32.EnumWindows(enum_proc, 0)

            if found_text[0]:
                error = found_text[0]
                error_lower = error.lower()
                logger.info(f"Canon-Fehlerfenster erkannt: '{error}'")
                # Bekannte Canon SELPHY Fehlermeldungen → Kurztext
                # WICHTIG: "tintenkassette" VOR "kassette" prüfen!
                if "tintenkassette" in error_lower or "druckerpatrone" in error_lower:
                    return "KEINE TINTENKASSETTE!"
                elif "kein papier" in error_lower:
                    return "KEIN PAPIER / KASSETTE!"
                elif "kassette" in error_lower:
                    return "KASSETTE PRÜFEN!"
                elif "tinte" in error_lower or "ink" in error_lower:
                    return "TINTE LEER!"
                elif error == "DRUCKER PRÜFEN!":
                    return error
                else:
                    # Unbekannter Fehler - kürzen für Leiste
                    upper = error.upper()
                    return upper[:25] + "..." if len(upper) > 25 else upper

        except Exception as e:
            logger.debug(f"Canon-Fenster-Erkennung: {e}")

        return None

    def _bring_printer_dialog_to_front(self):
        """Bringt Canon/Windows Drucker-Dialoge in den Vordergrund

        Sucht nach bekannten Drucker-Status-Fenstern und holt sie
        vor die Fullscreen-App (die durch overrideredirect oben liegt).
        """
        if not hasattr(self, '_last_printer_dialog_check'):
            self._last_printer_dialog_check = 0

        # Nur alle 5s prüfen (FindWindow ist günstig, aber nicht spammen)
        if time.time() - self._last_printer_dialog_check < 5:
            return
        self._last_printer_dialog_check = time.time()

        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            EnumWindows = user32.EnumWindows
            GetWindowTextW = user32.GetWindowTextW
            IsWindowVisible = user32.IsWindowVisible
            SetForegroundWindow = user32.SetForegroundWindow
            ShowWindow = user32.ShowWindow
            SetWindowPos = user32.SetWindowPos

            SW_SHOW = 5
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040

            # Bekannte Fenster-Titel von Drucker-Dialogen
            printer_keywords = [
                "canon", "selphy", "drucker", "printer",
                "druckerstatus", "printer status",
                "ink", "tinte", "papier", "paper",
                "kassette", "cartridge",
            ]

            WNDENUMPROC = ctypes.WINFUNCTYPE(
                wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
            )

            def enum_callback(hwnd, lParam):
                if not IsWindowVisible(hwnd):
                    return True

                title = ctypes.create_unicode_buffer(256)
                GetWindowTextW(hwnd, title, 256)
                window_title = title.value.lower()

                if not window_title:
                    return True

                for keyword in printer_keywords:
                    if keyword in window_title:
                        # Fenster in Vordergrund bringen
                        ShowWindow(hwnd, SW_SHOW)
                        SetWindowPos(
                            hwnd, HWND_TOPMOST,
                            0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
                        )
                        logger.info(f"Drucker-Dialog in Vordergrund: '{title.value}'")
                        return True

                return True

            EnumWindows(WNDENUMPROC(enum_callback), 0)

        except Exception as e:
            logger.debug(f"Drucker-Dialog Vordergrund fehlgeschlagen: {e}")

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
        """Zeigt den Admin-Dialog"""
        from src.ui.screens.admin import AdminDialog
        self._exit_fullscreen()
        dialog = AdminDialog(self.root, self.config)
        self.root.wait_window(dialog)

        # Service-Menü öffnen wenn über Service-PIN angefordert
        if getattr(dialog, '_open_service', False):
            from src.ui.screens.service import ServiceDialog
            service = ServiceDialog(self.root, self)
            self.root.wait_window(service)
            return

        if dialog.result:
            self.config = dialog.result
            save_config(self.config)
            logger.info("Admin-Einstellungen gespeichert")
            
            # Galerie/Hotspot starten oder stoppen je nach Einstellung
            if self.config.get("gallery_enabled", False):
                self._start_gallery_if_needed()
            else:
                # Galerie deaktiviert -> Hotspot stoppen
                self._stop_hotspot_if_running()

            # StartScreen aktualisieren wenn aktiv
            if self.current_screen_name == "start" and self.current_screen:
                logger.info("Aktualisiere StartScreen nach Admin-Änderung...")
                # Config im Screen aktualisieren
                self.current_screen.config = self.config
                # on_show aufrufen für Refresh
                if hasattr(self.current_screen, "on_show"):
                    self.current_screen.on_show()
    
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
        """Zeigt den Event-Wechsel Dialog"""
        if self._event_change_dialog_open:
            return

        self._event_change_dialog_open = True
        logger.info(f"Event-Wechsel Dialog: {new_booking_id}")

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
            on_reject=on_reject
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
            if overlay and boxes:
                self.cached_usb_template = {
                    "path": usb_template,
                    "name": os.path.basename(usb_template),
                    "overlay": overlay,
                    "boxes": boxes
                }
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
            # StartScreen refreshen nach Test
            if self.current_screen_name == "start" and self.current_screen:
                if hasattr(self.current_screen, "on_show"):
                    self.current_screen.on_show()

        SystemTestDialog(self.root, self, on_complete=on_complete)

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
        """Setzt die Session zurück"""
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
        self.camera_manager.release()
        self.filter_manager.clear_cache()
        logger.info("Session zurückgesetzt")
    
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
    
    def quit(self):
        """Beendet die Anwendung"""
        self.camera_manager.release()
        self.root.quit()
