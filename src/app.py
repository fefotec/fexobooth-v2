"""
Fexobooth - Hauptanwendung
"""

import customtkinter as ctk
from typing import Dict, Any

from src.config.config import get_config, save_config
from src.ui.screens.start import StartScreen
from src.ui.screens.session import SessionScreen
from src.ui.screens.filter import FilterScreen
from src.ui.screens.final import FinalScreen
from src.ui.screens.admin import AdminDialog
from src.camera.webcam import WebcamManager
from src.storage.usb import USBManager
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PhotoboothApp:
    """Hauptanwendungsklasse"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # CustomTkinter Setup
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Hauptfenster
        self.root = ctk.CTk()
        self.root.title("Fexobooth")
        self.root.geometry("1280x800")
        
        # Fullscreen wenn konfiguriert
        if config.get("start_fullscreen", True):
            self.root.attributes("-fullscreen", True)
        
        # Manager initialisieren
        self.camera_manager = WebcamManager()
        self.usb_manager = USBManager()
        
        # Session-Status
        self.photos_taken = []
        self.current_filter = "none"
        self.template_path = None
        self.template_boxes = []
        
        # UI Setup
        self._setup_ui()
        
        logger.info("PhotoboothApp initialisiert")
    
    def _setup_ui(self):
        """Erstellt die UI-Struktur"""
        # Container für Screens
        self.container = ctk.CTkFrame(self.root)
        self.container.pack(fill="both", expand=True)
        
        # Screens erstellen (werden bei Bedarf angezeigt)
        self.screens = {}
        self.current_screen = None
        
        # Start-Screen als erstes anzeigen
        self.show_screen("start")
    
    def show_screen(self, screen_name: str, **kwargs):
        """Wechselt zu einem Screen"""
        # Alten Screen ausblenden
        if self.current_screen:
            self.current_screen.pack_forget()
        
        # Screen erstellen falls nicht vorhanden
        if screen_name not in self.screens:
            self.screens[screen_name] = self._create_screen(screen_name)
        
        # Screen anzeigen
        self.current_screen = self.screens[screen_name]
        self.current_screen.pack(fill="both", expand=True)
        
        # Screen aktualisieren
        if hasattr(self.current_screen, "on_show"):
            self.current_screen.on_show(**kwargs)
        
        logger.debug(f"Screen gewechselt: {screen_name}")
    
    def _create_screen(self, screen_name: str):
        """Erstellt einen Screen"""
        screen_classes = {
            "start": StartScreen,
            "session": SessionScreen,
            "filter": FilterScreen,
            "final": FinalScreen,
        }
        
        if screen_name in screen_classes:
            return screen_classes[screen_name](self.container, self)
        else:
            raise ValueError(f"Unbekannter Screen: {screen_name}")
    
    def show_admin_dialog(self):
        """Zeigt den Admin-Dialog"""
        dialog = AdminDialog(self.root, self.config)
        if dialog.result:
            self.config = dialog.result
            save_config(self.config)
            logger.info("Admin-Einstellungen gespeichert")
    
    def reset_session(self):
        """Setzt die Session zurück"""
        self.photos_taken = []
        self.current_filter = "none"
        self.template_path = None
        self.template_boxes = []
        self.camera_manager.release()
        logger.info("Session zurückgesetzt")
    
    def run(self):
        """Startet die Anwendung"""
        logger.info("Starte Hauptschleife")
        self.root.mainloop()
    
    def quit(self):
        """Beendet die Anwendung"""
        self.camera_manager.release()
        self.root.quit()
