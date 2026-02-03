"""Filter-Auswahl Screen - Cool & Modern

Optimiert für Touch mit großen Filter-Karten und Animationen
"""

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageEnhance
from typing import TYPE_CHECKING, Optional, Dict
import threading

from src.filters import FilterManager, AVAILABLE_FILTERS
from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)

# Filter-Emojis für visuelles Flair
FILTER_EMOJIS = {
    "none": "✨",
    "grayscale": "🖤",
    "sepia": "🟤",
    "vintage": "📷",
    "warm": "🔥",
    "cold": "❄️",
    "bright": "☀️",
    "contrast": "🎭",
    "soft": "🌸",
}


class FilterCard(ctk.CTkFrame):
    """Große, stylische Filter-Karte"""
    
    def __init__(self, parent, filter_key: str, filter_name: str,
                 preview_image: Optional[Image.Image] = None, on_click=None):
        super().__init__(
            parent,
            width=150,
            height=130,
            fg_color=COLORS["bg_card"],
            corner_radius=15,
            border_width=4,
            border_color=COLORS["border"]
        )
        self.pack_propagate(False)
        
        self.filter_key = filter_key
        self.filter_name = filter_name
        self.on_click = on_click
        self.is_selected = False
        
        # Container für Inhalt
        self.inner = ctk.CTkFrame(self, fg_color="transparent")
        self.inner.pack(expand=True, fill="both", padx=6, pady=6)
        
        # Vorschau-Bild
        self.preview_label = ctk.CTkLabel(
            self.inner, 
            text="", 
            fg_color=COLORS["bg_dark"],
            corner_radius=10
        )
        self.preview_label.pack(expand=True, fill="both")
        
        # Filter-Name mit Emoji
        emoji = FILTER_EMOJIS.get(filter_key, "🎨")
        self.name_label = ctk.CTkLabel(
            self.inner,
            text=f"{emoji} {filter_name}",
            font=("Segoe UI", 11, "bold"),
            text_color=COLORS["text_secondary"]
        )
        self.name_label.pack(pady=(4, 0))
        
        # Click-Bindings für alle Elemente
        for widget in [self, self.inner, self.preview_label, self.name_label]:
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

        if preview_image:
            self.set_preview(preview_image)
    
    def set_preview(self, image: Image.Image):
        """Setzt das Vorschaubild mit abgerundeten Ecken"""
        thumb = image.copy()
        thumb.thumbnail((130, 85), Image.Resampling.LANCZOS)
        
        # Abgerundete Ecken hinzufügen
        thumb = self._round_corners(thumb, 8)
        
        self.preview_ctk = ctk.CTkImage(light_image=thumb, size=thumb.size)
        self.preview_label.configure(image=self.preview_ctk)
    
    def _round_corners(self, img: Image.Image, radius: int) -> Image.Image:
        """Fügt abgerundete Ecken hinzu"""
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Maske erstellen
        mask = Image.new('L', img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([(0, 0), img.size], radius=radius, fill=255)
        
        # Maske anwenden
        img.putalpha(mask)
        return img
    
    def _on_enter(self, event):
        if not self.is_selected:
            self.configure(border_color=COLORS["primary"], border_width=4)
            self.name_label.configure(text_color=COLORS["primary"])
    
    def _on_leave(self, event):
        if not self.is_selected:
            self.configure(border_color=COLORS["border"], border_width=4)
            self.name_label.configure(text_color=COLORS["text_secondary"])
    
    def _on_click(self, event):
        if self.on_click:
            self.on_click(self)
    
    def set_selected(self, selected: bool):
        self.is_selected = selected
        if selected:
            self.configure(
                border_color=COLORS["primary"],
                border_width=5,
                fg_color=COLORS["bg_light"]
            )
            self.name_label.configure(
                text_color=COLORS["primary"],
                font=("Segoe UI", 12, "bold")
            )
        else:
            self.configure(
                border_color=COLORS["border"],
                border_width=4,
                fg_color=COLORS["bg_card"]
            )
            self.name_label.configure(
                text_color=COLORS["text_secondary"],
                font=("Segoe UI", 11, "bold")
            )


class FilterScreen(ctk.CTkFrame):
    """Moderner Filter-Auswahl Screen mit coolem Design"""
    
    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.app = app
        self.config = app.config
        
        self.selected_filter = "none"
        self.filter_buttons: Dict[str, FilterCard] = {}
        self.preview_cache: Dict[str, Image.Image] = {}
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Erstellt die UI - modern und ansprechend"""
        # Header mit Titel und Untertitel
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(15, 5))
        
        title = ctk.CTkLabel(
            header,
            text="🎨 Wähle deinen Style!",
            font=("Segoe UI", 26, "bold"),
            text_color=COLORS["primary"]
        )
        title.pack()
        
        subtitle = ctk.CTkLabel(
            header,
            text="Tippe auf einen Filter für die Vorschau",
            font=FONTS["body"],
            text_color=COLORS["text_muted"]
        )
        subtitle.pack(pady=(2, 0))
        
        # Hauptbereich
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)
        main_frame.grid_columnconfigure(0, weight=2)
        main_frame.grid_columnconfigure(1, weight=3)
        main_frame.grid_rowconfigure(0, weight=1)
        
        # Filter-Grid (links) - in eigenem Container
        filter_container = ctk.CTkFrame(
            main_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=15
        )
        filter_container.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        
        # Scrollbare Filter-Liste
        filter_scroll = ctk.CTkScrollableFrame(
            filter_container,
            fg_color="transparent",
            scrollbar_button_color=COLORS["primary"],
            scrollbar_button_hover_color=COLORS["primary_hover"]
        )
        filter_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Filter-Buttons in 2er-Reihen
        self._create_filter_grid(filter_scroll)
        
        # Vorschau-Bereich (rechts) - größer
        preview_container = ctk.CTkFrame(
            main_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=15
        )
        preview_container.grid(row=0, column=1, sticky="nsew")
        
        # Vorschau-Titel
        preview_title = ctk.CTkLabel(
            preview_container,
            text="📸 Vorschau",
            font=("Segoe UI", 16, "bold"),
            text_color=COLORS["text_primary"]
        )
        preview_title.pack(pady=(15, 5))
        
        # Aktueller Filter-Name
        self.current_filter_label = ctk.CTkLabel(
            preview_container,
            text="✨ Original",
            font=("Segoe UI", 14),
            text_color=COLORS["primary"]
        )
        self.current_filter_label.pack(pady=(0, 10))
        
        # Großes Vorschau-Bild
        self.preview_label = ctk.CTkLabel(
            preview_container, 
            text="",
            fg_color=COLORS["bg_dark"],
            corner_radius=10
        )
        self.preview_label.pack(expand=True, fill="both", padx=20, pady=(0, 20))
        
        # Button-Leiste unten
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(5, 15))
        
        # Zurück-Button (links)
        back_btn = ctk.CTkButton(
            button_frame,
            text="← Nochmal",
            font=FONTS["body"],
            width=130,
            height=50,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_primary"],
            corner_radius=12,
            command=self._on_back
        )
        back_btn.pack(side="left")
        
        # Weiter-Button (rechts) - prominent
        self.continue_btn = ctk.CTkButton(
            button_frame,
            text="Weiter →",
            font=("Segoe UI", 16, "bold"),
            width=180,
            height=55,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            corner_radius=12,
            command=self._on_continue
        )
        self.continue_btn.pack(side="right")
    
    def _create_filter_grid(self, parent):
        """Erstellt das Filter-Grid mit 2 Spalten"""
        filters = list(AVAILABLE_FILTERS.items())
        
        for i in range(0, len(filters), 2):
            row_frame = ctk.CTkFrame(parent, fg_color="transparent")
            row_frame.pack(fill="x", pady=8)
            
            # Zentrieren wenn nur ein Element in der Reihe
            if i + 1 >= len(filters):
                row_frame.pack_configure(anchor="center")
            
            for j in range(2):
                if i + j < len(filters):
                    key, name = filters[i + j]
                    card = FilterCard(
                        row_frame,
                        filter_key=key,
                        filter_name=name,
                        on_click=lambda b: self._select_filter(b)
                    )
                    card.pack(side="left", padx=8)
                    self.filter_buttons[key] = card
    
    def _select_filter(self, button: FilterCard):
        """Wählt einen Filter aus mit Animation"""
        # Alte Auswahl deselektieren
        if self.selected_filter in self.filter_buttons:
            self.filter_buttons[self.selected_filter].set_selected(False)
        
        # Neue Auswahl
        self.selected_filter = button.filter_key
        button.set_selected(True)
        self.app.current_filter = self.selected_filter
        
        # Filter-Label aktualisieren
        emoji = FILTER_EMOJIS.get(self.selected_filter, "🎨")
        self.current_filter_label.configure(
            text=f"{emoji} {button.filter_name}"
        )
        
        # Große Vorschau aktualisieren
        self._update_main_preview()
        
        logger.debug(f"Filter ausgewählt: {self.selected_filter}")
    
    def _update_main_preview(self):
        """Aktualisiert die große Vorschau"""
        if not self.app.photos_taken:
            return
        
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
                max_size=500
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
        
        # Sample-Bild für Previews
        sample = self.app.photos_taken[0].copy()
        sample.thumbnail((200, 150), Image.Resampling.LANCZOS)
        
        for key, card in self.filter_buttons.items():
            try:
                filtered = self.app.filter_manager.apply(sample, key)
                self.after(0, lambda c=card, img=filtered: c.set_preview(img))
            except Exception as e:
                logger.warning(f"Filter-Preview Fehler für {key}: {e}")
    
    def _on_back(self):
        """Zurück - neue Fotos machen"""
        self.app.photos_taken = []
        self.app.current_photo_index = 0
        self.app.show_screen("session")
    
    def _on_continue(self):
        """Weiter zum Final-Screen"""
        logger.info(f"Filter gewählt: {self.selected_filter}")
        self.app.current_filter = self.selected_filter
        self.app.show_screen("final")
    
    def on_show(self):
        """Screen wird angezeigt"""
        # Cache leeren
        self.preview_cache = {}
        
        # Standard-Filter auswählen
        self.selected_filter = "none"
        for key, card in self.filter_buttons.items():
            card.set_selected(key == "none")
        
        # Label zurücksetzen
        self.current_filter_label.configure(text="✨ Original")
        
        # Vorschau aktualisieren
        self._update_main_preview()
        
        # Filter-Previews im Hintergrund generieren
        threading.Thread(target=self._generate_filter_previews, daemon=True).start()
    
    def on_hide(self):
        """Screen wird verlassen"""
        self.preview_cache = {}
