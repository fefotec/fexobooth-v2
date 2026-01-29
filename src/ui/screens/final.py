"""Final-Screen mit Druck-Option"""

import customtkinter as ctk
from PIL import Image
from typing import TYPE_CHECKING
from pathlib import Path

from src.filters import FilterManager
from src.templates.renderer import TemplateRenderer
from src.storage.local import LocalStorage
from src.storage.usb import USBManager
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class FinalScreen(ctk.CTkFrame):
    """Final-Screen mit fertigem Bild und Optionen"""
    
    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent)
        self.app = app
        self.config = app.config
        
        self.filter_manager = FilterManager()
        self.renderer = TemplateRenderer(
            canvas_width=self.config.get("canvas_width", 1800),
            canvas_height=self.config.get("canvas_height", 1200)
        )
        self.local_storage = LocalStorage()
        self.usb_manager = USBManager()
        
        self.prints_count = 0
        self.final_image = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Erstellt die UI"""
        # Vorschau
        self.preview_label = ctk.CTkLabel(self, text="")
        self.preview_label.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Button-Leiste
        button_frame = ctk.CTkFrame(self)
        button_frame.pack(pady=20)
        
        # Nochmal-Button
        self.redo_btn = ctk.CTkButton(
            button_frame,
            text=self.config["ui_texts"].get("redo", "NOCHMAL"),
            width=150,
            height=60,
            command=self._on_redo
        )
        self.redo_btn.pack(side="left", padx=10)
        
        # Drucken-Button
        self.print_btn = ctk.CTkButton(
            button_frame,
            text=self.config["ui_texts"].get("print", "DRUCKEN"),
            width=150,
            height=60,
            fg_color="#27ae60",
            command=self._on_print
        )
        self.print_btn.pack(side="left", padx=10)
        
        # Fertig-Button
        if not self.config.get("hide_finish_button", False):
            self.finish_btn = ctk.CTkButton(
                button_frame,
                text=self.config["ui_texts"].get("finish", "FERTIG"),
                width=150,
                height=60,
                command=self._on_finish
            )
            self.finish_btn.pack(side="left", padx=10)
    
    def _render_final_image(self) -> Image.Image:
        """Rendert das finale Bild"""
        # Filter auf alle Fotos anwenden
        filtered_photos = [
            self.filter_manager.apply(photo, self.app.current_filter)
            for photo in self.app.photos_taken
        ]
        
        # Template rendern
        overlay = getattr(self.app, "overlay_image", None)
        boxes = self.app.template_boxes or [{"box": (0, 0, 1799, 1199), "angle": 0}]
        
        return self.renderer.render(filtered_photos, boxes, overlay)
    
    def _on_redo(self):
        """Nochmal gedrückt"""
        logger.info("Redo - zurück zum Start")
        self.app.reset_session()
        self.app.show_screen("start")
    
    def _on_print(self):
        """Drucken gedrückt"""
        max_prints = self.config.get("max_prints_per_session", 1)
        
        if self.prints_count >= max_prints:
            logger.warning("Druck-Limit erreicht")
            return
        
        logger.info("Drucke Bild...")
        
        # Bild speichern
        if self.final_image:
            saved_path = self.local_storage.save_print(self.final_image.convert("RGB"))
            
            if saved_path:
                # Auf USB kopieren
                self.usb_manager.copy_to_usb(saved_path, "Prints")
                
                # Drucken (Windows)
                self._print_image(saved_path)
                
                self.prints_count += 1
                
                # Button deaktivieren wenn Limit erreicht
                if self.prints_count >= max_prints:
                    self.print_btn.configure(state="disabled", fg_color="gray")
    
    def _print_image(self, image_path: Path):
        """Druckt ein Bild (Windows)"""
        try:
            import win32print
            import win32ui
            from PIL import ImageWin
            
            printer_name = self.config.get("printer_name")
            if not printer_name:
                printer_name = win32print.GetDefaultPrinter()
            
            # Bild laden
            img = Image.open(image_path)
            
            # Druck-Einstellungen
            adjustment = self.config.get("print_adjustment", {})
            offset_x = adjustment.get("offset_x", 0)
            offset_y = adjustment.get("offset_y", 0)
            zoom = adjustment.get("zoom", 100) / 100
            
            # Größe berechnen
            base_width = int(1772 * zoom)
            base_height = int(1181 * zoom)
            img = img.resize((base_width, base_height), Image.Resampling.LANCZOS)
            
            # Drucken
            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(printer_name)
            hDC.StartDoc("Fexobooth Print")
            hDC.StartPage()
            
            dib = ImageWin.Dib(img)
            dib.draw(
                hDC.GetHandleOutput(),
                (offset_x, offset_y, offset_x + base_width, offset_y + base_height)
            )
            
            hDC.EndPage()
            hDC.EndDoc()
            hDC.DeleteDC()
            
            logger.info(f"Gedruckt auf: {printer_name}")
            
        except ImportError:
            logger.warning("win32print nicht verfügbar - Druck nur unter Windows")
        except Exception as e:
            logger.error(f"Druckfehler: {e}")
    
    def _on_finish(self):
        """Fertig gedrückt"""
        logger.info("Session beendet")
        self.app.reset_session()
        self.app.show_screen("start")
    
    def on_show(self):
        """Wird aufgerufen wenn Screen angezeigt wird"""
        self.prints_count = 0
        self.print_btn.configure(state="normal", fg_color="#27ae60")
        
        # Finales Bild rendern
        self.final_image = self._render_final_image()
        
        # Einzelfotos speichern
        for i, photo in enumerate(self.app.photos_taken):
            self.local_storage.save_single(photo.convert("RGB"), suffix=str(i+1))
        
        # Vorschau anzeigen
        preview = self.final_image.copy()
        preview.thumbnail((800, 600), Image.Resampling.LANCZOS)
        
        ctk_img = ctk.CTkImage(light_image=preview, size=preview.size)
        self.preview_label.configure(image=ctk_img)
        self.preview_label.image = ctk_img
