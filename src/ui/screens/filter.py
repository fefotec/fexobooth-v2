"""Filter-Auswahl Screen - Modern und Touch-optimiert

Optimiert für Lenovo Miix 310 (1280x800)
"""

import customtkinter as ctk
from PIL import Image
from typing import TYPE_CHECKING, Optional, Dict
import threading

from src.filters import FilterManager, AVAILABLE_FILTERS
from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class FilterButton(ctk.CTkFrame):
    """Filter-Button mit Vorschau - clean ohne Namen"""
    
    def __init__(self, parent, filter_key: str, filter_name: str,
                 preview_image: Optional[Image.Image] = None, on_click=None):
        # Größere Buttons ohne Namen = mehr Platz für Preview
        super().__init__(
            parent,
            width=95,
            height=75,
            fg_color=COLORS["bg_card"],
            corner_radius=SIZES["corner_radius_small"],
            border_width=3,
            border_color=COLORS["border"]
        )
        self.pack_propagate(False)
        
        self.filter_key = filter_key
        self.filter_name = filter_name
        self.on_click = on_click
        self.is_selected = False
        
        # Hover-Effekte
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        
        # Vorschau-Bild (füllt den ganzen Button)
        self.preview_label = ctk.CTkLabel(self, text="", fg_color="transparent")
        self.preview_label.pack(expand=True, fill="both", padx=4, pady=4)
        self.preview_label.bind("<Button-1>", self._on_click)

        if preview_image:
            self.set_preview(preview_image)
    
    def set_preview(self, image: Image.Image):
        """Setzt das Vorschaubild"""
        thumb = image.copy()
        thumb.thumbnail((85, 65), Image.Resampling.LANCZOS)  # Größer ohne Namen

        self.preview_ctk = ctk.CTkImage(light_image=thumb, size=thumb.size)
        self.preview_label.configure(image=self.preview_ctk)
    
    def _on_enter(self, event):
        if not self.is_selected:
            self.configure(border_color=COLORS["border_light"])
    
    def _on_leave(self, event):
        if not self.is_selected:
            self.configure(border_color=COLORS["border"])
    
    def _on_click(self, event):
        if self.on_click:
            self.on_click(self)
    
    def set_selected(self, selected: bool):
        self.is_selected = selected
        if selected:
            self.configure(
                border_color=COLORS["primary"],
                fg_color=COLORS["bg_light"]
            )
        else:
            self.configure(
                border_color=COLORS["border"],
                fg_color=COLORS["bg_card"]
            )


class FilterScreen(ctk.CTkFrame):
    """Moderner Filter-Auswahl Screen"""
    
    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.app = app
        self.config = app.config
        
        self.selected_filter = "none"
        self.filter_buttons: Dict[str, FilterButton] = {}
        self.preview_cache: Dict[str, Image.Image] = {}
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Erstellt die UI - kompakt für 800px Höhe"""
        # Titel (kompakter)
        title = ctk.CTkLabel(
            self,
            text=self.config.get("ui_texts", {}).get("choose_filter", "Wähle einen Filter"),
            font=FONTS["subheading"],
            text_color=COLORS["text_primary"]
        )
        title.pack(pady=(10, 5))
        
        # Hauptbereich (weniger Padding)
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=15, pady=5)
        main_frame.grid_columnconfigure(0, weight=3)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)
        
        # Vorschau-Bereich (links)
        preview_frame = ctk.CTkFrame(
            main_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=SIZES["corner_radius"]
        )
        preview_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        
        self.preview_label = ctk.CTkLabel(preview_frame, text="", fg_color="transparent")
        self.preview_label.pack(expand=True, padx=20, pady=20)
        
        # Filter-Bereich (rechts)
        filter_frame = ctk.CTkFrame(
            main_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=SIZES["corner_radius"]
        )
        filter_frame.grid(row=0, column=1, sticky="nsew")
        
        # Filter-Label
        filter_label = ctk.CTkLabel(
            filter_frame,
            text="Filter",
            font=FONTS["subheading"],
            text_color=COLORS["text_primary"]
        )
        filter_label.pack(pady=(15, 10))
        
        # Scrollbarer Filter-Container
        filter_scroll = ctk.CTkScrollableFrame(
            filter_frame,
            fg_color="transparent",
            scrollbar_button_color=COLORS["bg_light"]
        )
        filter_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Filter-Buttons erstellen (2 pro Reihe)
        self._create_filter_buttons(filter_scroll)
        
        # Button-Leiste unten (kompakter)
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(fill="x", padx=15, pady=10)
        
        # Zurück
        back_btn = ctk.CTkButton(
            button_frame,
            text="← Zurück",
            font=FONTS["small"],
            width=SIZES["button_width"],
            height=SIZES["button_height"],
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            corner_radius=SIZES["corner_radius"],
            command=self._on_back
        )
        back_btn.pack(side="left")
        
        # Weiter
        self.continue_btn = ctk.CTkButton(
            button_frame,
            text="Weiter →",
            font=FONTS["button"],
            width=SIZES["button_large_width"],
            height=SIZES["button_height"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            corner_radius=SIZES["corner_radius"],
            command=self._on_continue
        )
        self.continue_btn.pack(side="right")
    
    def _create_filter_buttons(self, parent):
        """Erstellt die Filter-Buttons - 3 pro Reihe, clean ohne Namen"""
        row_frame = None
        col = 0

        for i, (key, name) in enumerate(AVAILABLE_FILTERS.items()):
            if col == 0:
                row_frame = ctk.CTkFrame(parent, fg_color="transparent")
                row_frame.pack(fill="x", pady=5)

            btn = FilterButton(
                row_frame,
                filter_key=key,
                filter_name=name,
                on_click=lambda b: self._select_filter(b)
            )
            btn.pack(side="left", padx=5)
            self.filter_buttons[key] = btn

            col = (col + 1) % 3
    
    def _select_filter(self, button: FilterButton):
        """Wählt einen Filter aus"""
        # Alte Auswahl deselektieren
        if self.selected_filter in self.filter_buttons:
            self.filter_buttons[self.selected_filter].set_selected(False)
        
        # Neue Auswahl
        self.selected_filter = button.filter_key
        button.set_selected(True)
        self.app.current_filter = self.selected_filter
        
        # Große Vorschau aktualisieren
        self._update_main_preview()
        
        logger.debug(f"Filter ausgewählt: {self.selected_filter}")
    
    def _update_main_preview(self):
        """Aktualisiert die große Vorschau"""
        if not self.app.photos_taken:
            return
        
        # Gecachte oder neue Vorschau
        cache_key = self.selected_filter
        
        if cache_key not in self.preview_cache:
            # Vorschau rendern
            filtered_photos = [
                self.app.filter_manager.apply(photo, self.selected_filter)
                for photo in self.app.photos_taken
            ]
            
            preview = self.app.renderer.render_preview(
                filtered_photos,
                self.app.template_boxes,
                self.app.overlay_image,
                max_size=550  # Kleiner für 1280x800
            )
            self.preview_cache[cache_key] = preview
        else:
            preview = self.preview_cache[cache_key]
        
        # Anzeigen
        ctk_img = ctk.CTkImage(light_image=preview, size=preview.size)
        self.preview_label.configure(image=ctk_img)
        self.preview_label.image = ctk_img
    
    def _generate_filter_previews(self):
        """Generiert Mini-Vorschauen für alle Filter (im Hintergrund)"""
        if not self.app.photos_taken:
            return
        
        # Sample-Bild für Previews (erstes Foto, klein)
        sample = self.app.photos_taken[0].copy()
        sample.thumbnail((200, 150), Image.Resampling.LANCZOS)
        
        for key, btn in self.filter_buttons.items():
            try:
                filtered = self.app.filter_manager.apply(sample, key)
                self.after(0, lambda b=btn, img=filtered: b.set_preview(img))
            except Exception as e:
                logger.warning(f"Filter-Preview Fehler für {key}: {e}")
    
    def _on_back(self):
        """Zurück gedrückt"""
        # Zurück zur Session (Photos neu machen)
        self.app.photos_taken = []
        self.app.show_screen("session")
    
    def _on_continue(self):
        """Weiter gedrückt"""
        logger.info(f"Filter gewählt: {self.selected_filter}")
        self.app.current_filter = self.selected_filter
        self.app.show_screen("final")
    
    def on_show(self):
        """Screen wird angezeigt"""
        # Cache leeren
        self.preview_cache = {}
        
        # Standard-Filter auswählen
        self.selected_filter = "none"
        for key, btn in self.filter_buttons.items():
            btn.set_selected(key == "none")
        
        # Vorschau aktualisieren
        self._update_main_preview()
        
        # Filter-Previews im Hintergrund generieren
        threading.Thread(target=self._generate_filter_previews, daemon=True).start()
    
    def on_hide(self):
        """Screen wird verlassen"""
        self.preview_cache = {}
