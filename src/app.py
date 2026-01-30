"""
Fexobooth - Hauptanwendung
Moderne Photobooth-Software für fexobox
"""

import customtkinter as ctk
from typing import Dict, Any, Optional, List
from PIL import Image
import os

from src.config.config import load_config, save_config
from src.camera.webcam import WebcamManager
from src.storage.usb import USBManager
from src.storage.local import LocalStorage
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
        
        # Bildschirmgröße
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"{screen_width}x{screen_height}")
        
        # Fullscreen wenn konfiguriert
        if config.get("start_fullscreen", True):
            self.root.attributes("-fullscreen", True)
        
        # Escape zum Beenden
        self.root.bind("<Escape>", lambda e: self._toggle_fullscreen())
        self.root.bind("<F11>", lambda e: self._toggle_fullscreen())
        
        # Manager initialisieren
        self.camera_manager = WebcamManager()
        self.usb_manager = USBManager()
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
        
        # UI Setup
        self._setup_ui()
        
        # Status-Timer starten
        self._start_status_checks()
        
        logger.info("PhotoboothApp initialisiert")
    
    def _toggle_fullscreen(self):
        """Toggle Fullscreen"""
        current = self.root.attributes("-fullscreen")
        self.root.attributes("-fullscreen", not current)
    
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
        
        # USB-Status
        self.usb_status = ctk.CTkLabel(
            status_frame,
            text="⚠️ USB",
            font=FONTS["small"],
            text_color=COLORS["warning"],
            fg_color=COLORS["bg_light"],
            corner_radius=8,
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
        
        # Admin-Button (sehr dezent)
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
        
        return bar
    
    def _start_status_checks(self):
        """Startet periodische Status-Checks"""
        self._check_usb_status()
        self._check_printer_status()
    
    def _check_usb_status(self):
        """Prüft USB-Status - BLINKEND wenn nicht vorhanden"""
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
            
            if self._usb_blink_state:
                self.usb_status.configure(
                    text="⚠️ KEIN USB-STICK!",
                    text_color="#ffffff",
                    fg_color="#ff0000"  # Knallrot
                )
            else:
                self.usb_status.configure(
                    text="⚠️ USB FEHLT!",
                    text_color="#000000",
                    fg_color="#ffcc00"  # Gelb
                )
        
        # Schnellerer Check für Blink-Effekt
        self.root.after(1000, self._check_usb_status)
    
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
        }
        
        # Screen erstellen falls nicht vorhanden oder neu erstellen für frischen State
        if screen_name in ["session", "filter", "final"]:
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
    
    def load_template(self, template_key: str) -> bool:
        """Lädt ein Template"""
        template_path = self.config.get("template_paths", {}).get(template_key, "")
        
        if not template_path or not os.path.exists(template_path):
            logger.warning(f"Template nicht gefunden: {template_path}")
            self.template_path = None
            self.template_boxes = []
            self.overlay_image = None
            return False
        
        overlay, boxes = TemplateLoader.load(template_path)
        
        if overlay and boxes:
            self.template_path = template_path
            self.template_boxes = boxes
            self.overlay_image = overlay
            logger.info(f"Template geladen: {len(boxes)} Foto-Slots")
            return True
        
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
