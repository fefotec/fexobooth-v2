"""Filter-Auswahl Screen"""

import customtkinter as ctk
from PIL import Image
from typing import TYPE_CHECKING

from src.filters import FilterManager, AVAILABLE_FILTERS
from src.templates.renderer import TemplateRenderer
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class FilterScreen(ctk.CTkFrame):
    """Filter-Auswahl mit Vorschau"""
    
    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent)
        self.app = app
        self.config = app.config
        self.filter_manager = FilterManager()
        self.renderer = TemplateRenderer(
            canvas_width=self.config.get("canvas_width", 1800),
            canvas_height=self.config.get("canvas_height", 1200)
        )
        self.selected_filter = "none"
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Erstellt die UI"""
        # Titel
        title = ctk.CTkLabel(
            self,
            text=self.config["ui_texts"].get("choose_filter", "Wähle einen Filter"),
            font=ctk.CTkFont(size=28, weight="bold")
        )
        title.pack(pady=(20, 10))
        
        # Hauptbereich: Vorschau links, Filter rechts
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)
        main_frame.grid_columnconfigure(0, weight=3)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)
        
        # Vorschau-Bereich
        preview_frame = ctk.CTkFrame(main_frame)
        preview_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        self.preview_label = ctk.CTkLabel(preview_frame, text="")
        self.preview_label.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Filter-Liste
        filter_frame = ctk.CTkScrollableFrame(main_frame, width=200)
        filter_frame.grid(row=0, column=1, sticky="nsew")
        
        self.filter_buttons = {}
        for filter_key, filter_name in AVAILABLE_FILTERS.items():
            btn = ctk.CTkButton(
                filter_frame,
                text=filter_name,
                width=180,
                height=50,
                command=lambda k=filter_key: self._select_filter(k)
            )
            btn.pack(pady=5)
            self.filter_buttons[filter_key] = btn
        
        # Weiter-Button
        continue_btn = ctk.CTkButton(
            self,
            text="WEITER",
            font=ctk.CTkFont(size=20, weight="bold"),
            width=200,
            height=60,
            command=self._on_continue
        )
        continue_btn.pack(pady=20)
    
    def _select_filter(self, filter_key: str):
        """Wählt einen Filter aus"""
        self.selected_filter = filter_key
        self.app.current_filter = filter_key
        
        # Button-Styles aktualisieren
        for key, btn in self.filter_buttons.items():
            if key == filter_key:
                btn.configure(fg_color="#e00675")
            else:
                btn.configure(fg_color=["#3B8ED0", "#1F6AA5"])
        
        # Vorschau aktualisieren
        self._update_preview()
    
    def _update_preview(self):
        """Aktualisiert die Vorschau"""
        if not self.app.photos_taken:
            return
        
        # Filter auf alle Fotos anwenden
        filtered_photos = [
            self.filter_manager.apply(photo, self.selected_filter)
            for photo in self.app.photos_taken
        ]
        
        # Template rendern
        overlay = getattr(self.app, "overlay_image", None)
        boxes = self.app.template_boxes or [{"box": (0, 0, 1799, 1199), "angle": 0}]
        
        preview = self.renderer.render_preview(
            filtered_photos,
            boxes,
            overlay,
            max_size=600
        )
        
        # Anzeigen
        ctk_img = ctk.CTkImage(light_image=preview, size=preview.size)
        self.preview_label.configure(image=ctk_img)
        self.preview_label.image = ctk_img
    
    def _on_continue(self):
        """Weiter gedrückt"""
        logger.info(f"Filter ausgewählt: {self.selected_filter}")
        self.app.current_filter = self.selected_filter
        self.app.show_screen("final")
    
    def on_show(self):
        """Wird aufgerufen wenn Screen angezeigt wird"""
        self.selected_filter = "none"
        self._select_filter("none")
        self._update_preview()
