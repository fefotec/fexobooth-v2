"""
Fexobooth - Hauptanwendung
Moderne Photobooth-Software für fexobox
"""

import customtkinter as ctk
from typing import Dict, Any, Optional, List
from pathlib import Path
from PIL import Image
import os

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
        self.current_filter: str = "none"
        self.template_path: Optional[str] = None
        self.template_boxes: List[Dict] = []
        self.overlay_image: Optional[Image.Image] = None
        self.prints_in_session: int = 0

        # USB-Template Cache (bleibt erhalten wenn USB abgezogen wird)
        self.cached_usb_template: Optional[Dict] = None  # {path, name, overlay, boxes}

        # USB-Sync Dialog State
        self._sync_dialog_open: bool = False  # Verhindert mehrfache Dialoge

        # Drucker initialisieren wenn nicht gesetzt
        self._init_default_printer()

        # UI Setup
        self._setup_ui()
        
        # Gecachte Buchung anzeigen (falls vorhanden)
        if self.booking_manager.is_loaded:
            self._update_booking_display()
            logger.info(f"📂 Letzte Buchung wiederhergestellt: {self.booking_manager.booking_id}")
            
            # Gecachtes Template in Config eintragen
            if self.booking_manager.apply_cached_template_to_config(self.config):
                logger.info("📦 Gecachtes Template wird verwendet")
        
        # Status-Timer starten
        self._start_status_checks()
        
        # Galerie-Server starten wenn aktiviert
        self._init_gallery_server()
        
        logger.info("PhotoboothApp initialisiert")

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
        """Startet den Galerie-Webserver wenn aktiviert"""
        if not self.config.get("gallery_enabled", False):
            logger.debug("Galerie-Server deaktiviert")
            return
        
        try:
            from src.gallery import start_server, get_gallery_url
            from pathlib import Path
            
            # Galerie-Pfad = USB BILDER Ordner oder lokaler Speicher
            gallery_path = None
            usb_path = self.usb_manager.get_images_path()
            if usb_path:
                gallery_path = usb_path
            else:
                # Fallback: Lokaler Bilder-Ordner
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

    def _start_statistics_event(self, usb_root: Path = None):
        """Startet Statistik-Erfassung für aktuelle Buchung"""
        booking_id = self.booking_manager.booking_id if self.booking_manager.is_loaded else ""
        
        # Speicherpfad: USB wenn verfügbar, sonst lokal
        save_path = usb_root if usb_root else self.local_storage.get_base_path()
        
        # Event starten (beendet vorheriges automatisch)
        self.statistics.start_event(booking_id=booking_id, save_path=save_path)

    def _start_gallery_if_needed(self):
        """Startet Galerie wenn noch nicht gestartet (für settings.json Aktivierung)"""
        try:
            from src.gallery import is_running, start_server, get_gallery_url
            
            if is_running():
                logger.debug("Galerie läuft bereits")
                return
            
            # Galerie-Pfad ermitteln
            gallery_path = self.usb_manager.get_images_path()
            if not gallery_path:
                gallery_path = self.local_storage.get_images_path()
            
            if gallery_path:
                port = self.config.get("gallery_port", 8080)
                start_server(gallery_path, port=port)
                self.gallery_url = get_gallery_url(port)
                logger.info(f"🌐 Galerie gestartet (via settings.json): {self.gallery_url}")
        except Exception as e:
            logger.error(f"Galerie-Start via settings.json fehlgeschlagen: {e}")

    def _enter_fullscreen(self):
        """Aktiviert echten Vollbildmodus"""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Window-Dekoration entfernen
        self.root.overrideredirect(True)
        
        # Fenster auf volle Bildschirmgröße setzen (Position 0,0)
        self.root.geometry(f"{screen_width}x{screen_height}+0+0")
        
        # Immer im Vordergrund
        self.root.attributes("-topmost", True)
        self.root.after(100, lambda: self.root.attributes("-topmost", False))
        
        # Focus setzen
        self.root.focus_force()
        
        self._is_fullscreen = True
        logger.info(f"Vollbild aktiviert: {screen_width}x{screen_height}")
    
    def _exit_fullscreen(self):
        """Beendet Vollbildmodus"""
        # Window-Dekoration wiederherstellen
        self.root.overrideredirect(False)
        
        # Normale Fenstergröße
        self.root.geometry("1024x768")
        
        self._is_fullscreen = False
        logger.info("Vollbild deaktiviert")
    
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
                
                self.logo_ctk = ctk.CTkImage(light_image=logo_img, size=(new_width, new_height))
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
        
        # Status-Bereich rechts
        status_frame = ctk.CTkFrame(bar, fg_color="transparent")
        status_frame.pack(side="right", padx=20, pady=10)

        # Admin-Button ZUERST (bleibt ganz rechts, wackelt nicht)
        admin_alpha = self.config.get("admin_button_alpha", 0.1)
        admin_btn = ctk.CTkButton(
            status_frame,
            text="⚙",
            width=40,
            height=40,
            font=("Segoe UI", 18),
            fg_color="transparent",
            hover_color=COLORS["bg_light"],
            text_color=COLORS["text_muted"],
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
            width=180,
            padx=12,
            pady=5
        )
        self.booking_label.pack(side="right", padx=10)

        # USB-Status (feste Breite damit Position stabil bleibt)
        self.usb_status = ctk.CTkLabel(
            status_frame,
            text="⚠️ USB",
            font=FONTS["small"],
            text_color=COLORS["warning"],
            fg_color=COLORS["bg_light"],
            corner_radius=8,
            width=160,  # Feste Breite für stabiles Layout
            padx=10,
            pady=5
        )
        self.usb_status.pack(side="right", padx=5)

        # Drucker-Status
        self.printer_status = ctk.CTkLabel(
            status_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["error"],
            fg_color=COLORS["bg_light"],
            corner_radius=8,
            padx=10,
            pady=5
        )
        self.printer_status.pack(side="right", padx=5)
        self.printer_status.pack_forget()  # Verstecken wenn OK
        
        return bar
    
    def _start_status_checks(self):
        """Startet periodische Status-Checks"""
        self._check_usb_status()
        self._check_printer_status()
    
    def _check_usb_status(self):
        """Prüft USB-Status - BLINKEND wenn nicht vorhanden, Dialog bei Pending-Files"""
        from pathlib import Path
        
        # Prüfen ob USB wieder verfügbar und Dateien pending sind
        is_available = self.usb_manager.is_available()
        pending_count = self.usb_manager.get_pending_count()

        # USB verfügbar -> prüfen ob NEUE Buchung
        if is_available:
            usb_drive = self.usb_manager.find_usb_stick()
            if usb_drive:
                usb_root = Path(usb_drive)
                
                # Prüfen ob es eine neue Buchung ist
                new_booking = self.booking_manager.check_usb_for_new_booking(usb_root)
                
                if new_booking:
                    # Neue Buchung gefunden -> laden
                    if self.booking_manager.load_from_usb(usb_root, force=True):
                        self._update_booking_display()
                        # allow_single_mode aus settings übernehmen
                        if self.booking_manager.settings:
                            self.config["allow_single_mode"] = self.booking_manager.settings.print_singles
                            
                            # Statistik-Event starten mit Buchungsnummer
                            self._start_statistics_event(usb_root)
                            
                            # Galerie starten wenn in settings.json aktiviert
                            if self.booking_manager.settings.online_gallery:
                                self._start_gallery_if_needed()
                elif not self.booking_manager.is_loaded:
                    # Noch keine Buchung geladen -> aus USB oder Cache laden
                    self.booking_manager.load_from_usb(usb_root)
                    self._update_booking_display()

        # USB wurde gerade eingesteckt und es gibt pending files -> Dialog zeigen
        if is_available and pending_count > 0 and not self._sync_dialog_open:
            if not hasattr(self, '_was_usb_available') or not self._was_usb_available:
                self._was_usb_available = True
                self._show_usb_sync_dialog(pending_count)
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

    def _show_usb_sync_dialog(self, pending_count: int):
        """Zeigt Dialog: Bilder auf USB kopieren? Ja/Nein"""
        if self._sync_dialog_open:
            return

        self._sync_dialog_open = True
        logger.info(f"USB-Sync Dialog: {pending_count} Dateien warten")

        # Dialog erstellen
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("USB-Stick erkannt")

        # Ohne Fensterrahmen für konsistentes Aussehen
        dialog.overrideredirect(True)

        # Dialog-Größe und Position (zentriert)
        dialog_width = 400
        dialog_height = 200
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - dialog_width) // 2
        y = (screen_h - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        # Styling
        dialog.configure(fg_color=COLORS["bg_medium"])

        # Immer im Vordergrund
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        # Content Frame mit Rahmen
        content = ctk.CTkFrame(
            dialog,
            fg_color=COLORS["bg_dark"],
            corner_radius=15,
            border_width=2,
            border_color=COLORS["primary"]
        )
        content.pack(fill="both", expand=True, padx=3, pady=3)

        # Icon und Titel
        title_label = ctk.CTkLabel(
            content,
            text="💾 USB-Stick erkannt",
            font=FONTS["heading"],
            text_color=COLORS["primary"]
        )
        title_label.pack(pady=(20, 10))

        # Frage
        question_label = ctk.CTkLabel(
            content,
            text=f"{pending_count} Bild(er) warten auf Kopie.\nJetzt auf USB-Stick kopieren?",
            font=FONTS["body"],
            text_color=COLORS["text_primary"]
        )
        question_label.pack(pady=(0, 20))

        # Button-Container
        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack(pady=(0, 20))

        def on_yes():
            logger.info("USB-Sync: Benutzer hat JA geklickt")
            dialog.destroy()
            self._sync_dialog_open = False
            # Sync durchführen
            synced = self.usb_manager.sync_pending()
            if synced > 0:
                self._show_sync_notification(synced)

        def on_no():
            logger.info("USB-Sync: Benutzer hat NEIN geklickt")
            dialog.destroy()
            self._sync_dialog_open = False

        # JA Button (grün, größer)
        yes_btn = ctk.CTkButton(
            btn_frame,
            text="JA",
            font=FONTS["button"],
            width=120,
            height=50,
            fg_color=COLORS["success"],
            hover_color="#00e676",
            corner_radius=SIZES["corner_radius"],
            command=on_yes
        )
        yes_btn.pack(side="left", padx=15)

        # NEIN Button (grau)
        no_btn = ctk.CTkButton(
            btn_frame,
            text="NEIN",
            font=FONTS["button"],
            width=120,
            height=50,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_primary"],
            corner_radius=SIZES["corner_radius"],
            command=on_no
        )
        no_btn.pack(side="left", padx=15)

        # Dialog-Close Handler (falls irgendwie geschlossen)
        def on_close():
            self._sync_dialog_open = False
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", on_close)

    def _show_sync_notification(self, count: int):
        """Zeigt Erfolgs-Dialog wenn Dateien synchronisiert wurden"""
        logger.info(f"USB-Sync erfolgreich: {count} Dateien kopiert")

        # Erfolgs-Dialog erstellen
        dialog = ctk.CTkToplevel(self.root)
        dialog.overrideredirect(True)

        # Größe und Position
        dialog_width = 350
        dialog_height = 150
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - dialog_width) // 2
        y = (screen_h - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        dialog.configure(fg_color=COLORS["bg_medium"])
        dialog.attributes("-topmost", True)

        # Content
        content = ctk.CTkFrame(
            dialog,
            fg_color=COLORS["success"],
            corner_radius=15
        )
        content.pack(fill="both", expand=True, padx=3, pady=3)

        # Erfolgs-Icon und Text
        ctk.CTkLabel(
            content,
            text="✅",
            font=("Segoe UI Emoji", 40),
            text_color="#ffffff"
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            content,
            text=f"{count} Bild(er) auf USB kopiert!",
            font=FONTS["body_bold"],
            text_color="#ffffff"
        ).pack(pady=(0, 20))

        # Dialog nach 2 Sekunden automatisch schließen
        def close_dialog():
            try:
                dialog.destroy()
            except:
                pass

        dialog.after(2000, close_dialog)

        # USB-Status auch aktualisieren
        self.usb_status.configure(
            text=f"✅ {count} sync!",
            text_color="#ffffff",
            fg_color="#00d26a"
        )
        # Nach 3 Sekunden wieder normalen Status anzeigen
        self.root.after(3000, self._reset_usb_status_after_sync)

    def _reset_usb_status_after_sync(self):
        """Setzt USB-Status nach Sync-Benachrichtigung zurück"""
        text, status = self.usb_manager.get_status_text()
        if status == "success":
            self.usb_status.configure(
                text=text,
                text_color=COLORS["success"],
                fg_color=COLORS["bg_light"]
            )
    
    def _check_printer_status(self):
        """Prüft Drucker-Status"""
        try:
            import win32print
            printer_name = self.config.get("printer_name") or win32print.GetDefaultPrinter()
            
            hPrinter = win32print.OpenPrinter(printer_name)
            info = win32print.GetPrinter(hPrinter, 2)
            win32print.ClosePrinter(hPrinter)
            
            status = info.get("Status", 0)
            
            if status & 0x8:  # Papier leer
                self.printer_status.configure(text="⚠️ Papier leer!")
                self.printer_status.pack(side="right", padx=5)
            elif status & 0x80:  # Offline
                self.printer_status.configure(text="⚠️ Drucker offline")
                self.printer_status.pack(side="right", padx=5)
            else:
                self.printer_status.pack_forget()
                
        except Exception:
            pass  # Unter macOS/Linux ignorieren
        
        # Nächster Check in 5 Sekunden
        self.root.after(5000, self._check_printer_status)
    
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
        
        # Screen aktualisieren
        if hasattr(self.current_screen, "on_show"):
            self.current_screen.on_show(**kwargs)
        
        logger.debug(f"Screen gewechselt: {screen_name}")
    
    def show_admin_dialog(self):
        """Zeigt den Admin-Dialog"""
        from src.ui.screens.admin import AdminDialog
        dialog = AdminDialog(self.root, self.config)
        self.root.wait_window(dialog)
        
        if dialog.result:
            self.config = dialog.result
            save_config(self.config)
            logger.info("Admin-Einstellungen gespeichert")
            
            # StartScreen aktualisieren wenn aktiv
            if self.current_screen_name == "start" and self.current_screen:
                logger.info("Aktualisiere StartScreen nach Admin-Änderung...")
                # Config im Screen aktualisieren
                self.current_screen.config = self.config
                # on_show aufrufen für Refresh
                if hasattr(self.current_screen, "on_show"):
                    self.current_screen.on_show()
    
    def play_video(self, video_key: str, next_screen: str):
        """Spielt ein Video ab und wechselt dann zum nächsten Screen
        
        Args:
            video_key: Config-Key für Video (z.B. "video_start", "video_end")
            next_screen: Screen nach Video-Ende
        """
        video_path = self.config.get(video_key, "")
        
        if not video_path or not os.path.exists(video_path):
            logger.debug(f"Video nicht konfiguriert/gefunden: {video_key}")
            self.show_screen(next_screen)
            return
        
        # Video-Screen anzeigen und abspielen
        self.show_screen("video")
        self.current_screen.play(video_path, next_screen)
    
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
            logger.info(f"✅ Template geladen: {len(boxes)} Foto-Slots, Overlay {overlay.size}")
            for i, box in enumerate(boxes):
                logger.debug(f"  Slot {i+1}: {box}")
            return True
        
        logger.error(f"Template-Loader gab None zurück für: {resolved_path}")
        return False
    
    def reset_session(self):
        """Setzt die Session zurück"""
        self.photos_taken = []
        self.current_filter = "none"
        self.template_path = None
        self.template_boxes = []
        self.overlay_image = None
        self.prints_in_session = 0
        self.camera_manager.release()
        self.filter_manager.clear_cache()
        logger.info("Session zurückgesetzt")
    
    def run(self):
        """Startet die Anwendung"""
        logger.info("Starte Hauptschleife")
        self.root.mainloop()
    
    def quit(self):
        """Beendet die Anwendung"""
        self.camera_manager.release()
        self.root.quit()
