"""Filter-Auswahl Screen - Cool & Modern

Responsive Design - passt sich automatisch an Bildschirmgröße an
"""

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageEnhance
from typing import TYPE_CHECKING, Optional, Dict
import threading

from src.filters import FilterManager, AVAILABLE_FILTERS
from src.ui.theme import COLORS, FONTS, get_sizes, get_fonts, is_small_screen
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
    "instagram": "📸",
}


class FilterCard(ctk.CTkFrame):
    """Responsive Filter-Karte - passt sich an Bildschirmgröße an"""

    def __init__(self, parent, filter_key: str, filter_name: str,
                 preview_image: Optional[Image.Image] = None, on_click=None):
        # Responsive Größen laden
        sizes = get_sizes()
        self._card_width = sizes["filter_card_width"]
        self._card_height = sizes["filter_card_height"]
        self._thumb_width = sizes["filter_thumb_width"]
        self._thumb_height = sizes["filter_thumb_height"]
        self._is_small = is_small_screen()

        super().__init__(
            parent,
            width=self._card_width,
            height=self._card_height,
            fg_color=COLORS["bg_card"],
            corner_radius=12 if not self._is_small else 10,
            border_width=3 if not self._is_small else 2,
            border_color=COLORS["border"]
        )
        self.pack_propagate(False)

        self.filter_key = filter_key
        self.filter_name = filter_name
        self.on_click = on_click
        self.is_selected = False

        # Container für Inhalt
        self.inner = ctk.CTkFrame(self, fg_color="transparent")
        self.inner.pack(expand=True, fill="both", padx=4, pady=4)

        # Vorschau-Bild
        self.preview_label = ctk.CTkLabel(
            self.inner,
            text="",
            fg_color=COLORS["bg_dark"],
            corner_radius=8 if not self._is_small else 6
        )
        self.preview_label.pack(expand=True, fill="both")

        # Filter-Name mit Emoji - kürzerer Name bei kleinem Screen
        emoji = FILTER_EMOJIS.get(filter_key, "🎨")
        display_name = self._get_short_name(filter_name) if self._is_small else filter_name
        font_size = 10 if self._is_small else 11

        self.name_label = ctk.CTkLabel(
            self.inner,
            text=f"{emoji} {display_name}",
            font=("Segoe UI", font_size, "bold"),
            text_color=COLORS["text_secondary"]
        )
        self.name_label.pack(pady=(2, 0))

        # Click-Bindings für alle Elemente
        for widget in [self, self.inner, self.preview_label, self.name_label]:
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

        if preview_image:
            self.set_preview(preview_image)

    def _get_short_name(self, name: str) -> str:
        """Kürzt lange Filter-Namen für kleine Bildschirme"""
        short_names = {
            "Schwarz-Weiß": "S/W",
            "BW Kontrast": "BW Kontr.",
            "Cool Breeze": "Cool",
            "Warm Glow": "Warm",
            "Original": "Original",
        }
        return short_names.get(name, name[:8] if len(name) > 8 else name)

    def set_preview(self, image: Image.Image):
        """Setzt das Vorschaubild mit abgerundeten Ecken"""
        thumb = image.copy()
        thumb.thumbnail((self._thumb_width, self._thumb_height), Image.Resampling.LANCZOS)

        # Abgerundete Ecken hinzufügen
        thumb = self._round_corners(thumb, 6)

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
            self.configure(border_color=COLORS["primary"], border_width=3 if not self._is_small else 2)
            self.name_label.configure(text_color=COLORS["primary"])

    def _on_leave(self, event):
        if not self.is_selected:
            self.configure(border_color=COLORS["border"], border_width=3 if not self._is_small else 2)
            self.name_label.configure(text_color=COLORS["text_secondary"])

    def _on_click(self, event):
        if self.on_click:
            self.on_click(self)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        border_width = 4 if not self._is_small else 3
        font_size = 11 if not self._is_small else 10

        if selected:
            self.configure(
                border_color=COLORS["primary"],
                border_width=border_width,
                fg_color=COLORS["bg_light"]
            )
            self.name_label.configure(
                text_color=COLORS["primary"],
                font=("Segoe UI", font_size + 1, "bold")
            )
        else:
            self.configure(
                border_color=COLORS["border"],
                border_width=border_width - 1,
                fg_color=COLORS["bg_card"]
            )
            self.name_label.configure(
                text_color=COLORS["text_secondary"],
                font=("Segoe UI", font_size, "bold")
            )


class FilterScreen(ctk.CTkFrame):
    """Moderner Filter-Auswahl Screen mit responsive Design"""

    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.app = app
        self.config = app.config

        self.selected_filter = "none"
        self.filter_buttons: Dict[str, FilterCard] = {}
        self.preview_cache: Dict[str, Image.Image] = {}

        # Responsive Einstellungen
        self._sizes = get_sizes()
        self._fonts = get_fonts()
        self._is_small = is_small_screen()

        self._setup_ui()

    def _setup_ui(self):
        """Erstellt die UI - responsive und modern"""
        # Header mit Titel und Untertitel
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(10 if self._is_small else 15, 5))

        title_size = 22 if self._is_small else 26
        title = ctk.CTkLabel(
            header,
            text="🎨 Wähle deinen Style!",
            font=("Segoe UI", title_size, "bold"),
            text_color=COLORS["primary"]
        )
        title.pack()

        subtitle = ctk.CTkLabel(
            header,
            text="Tippe auf einen Filter für die Vorschau",
            font=self._fonts["body"] if not self._is_small else self._fonts["small"],
            text_color=COLORS["text_muted"]
        )
        subtitle.pack(pady=(2, 0))

        # Hauptbereich
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=10 if self._is_small else 20, pady=8)
        main_frame.grid_columnconfigure(0, weight=2)
        main_frame.grid_columnconfigure(1, weight=3)
        main_frame.grid_rowconfigure(0, weight=1)

        # Filter-Grid (links) - in eigenem Container
        filter_container = ctk.CTkFrame(
            main_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=12 if not self._is_small else 10
        )
        filter_container.grid(row=0, column=0, sticky="nsew", padx=(0, 10 if self._is_small else 15))

        # Scrollbare Filter-Liste
        filter_scroll = ctk.CTkScrollableFrame(
            filter_container,
            fg_color="transparent",
            scrollbar_button_color=COLORS["primary"],
            scrollbar_button_hover_color=COLORS["primary_hover"]
        )
        filter_scroll.pack(fill="both", expand=True, padx=6 if self._is_small else 10, pady=6 if self._is_small else 10)

        # Filter-Buttons in 2er-Reihen
        self._create_filter_grid(filter_scroll)

        # Vorschau-Bereich (rechts) - größer
        preview_container = ctk.CTkFrame(
            main_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=12 if not self._is_small else 10
        )
        preview_container.grid(row=0, column=1, sticky="nsew")

        # Vorschau-Titel
        preview_title_size = 14 if self._is_small else 16
        preview_title = ctk.CTkLabel(
            preview_container,
            text="📸 Vorschau",
            font=("Segoe UI", preview_title_size, "bold"),
            text_color=COLORS["text_primary"]
        )
        preview_title.pack(pady=(10 if self._is_small else 15, 5))

        # Aktueller Filter-Name
        filter_label_size = 12 if self._is_small else 14
        self.current_filter_label = ctk.CTkLabel(
            preview_container,
            text="✨ Original",
            font=("Segoe UI", filter_label_size),
            text_color=COLORS["primary"]
        )
        self.current_filter_label.pack(pady=(0, 8))

        # Großes Vorschau-Bild
        self.preview_label = ctk.CTkLabel(
            preview_container,
            text="",
            fg_color=COLORS["bg_dark"],
            corner_radius=8
        )
        self.preview_label.pack(expand=True, fill="both", padx=12 if self._is_small else 20, pady=(0, 12 if self._is_small else 20))

        # Button-Leiste unten
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(fill="x", padx=10 if self._is_small else 20, pady=(5, 10 if self._is_small else 15))

        # Zurück-Button (links)
        back_btn_width = 100 if self._is_small else 130
        back_btn_height = 40 if self._is_small else 50
        back_btn = ctk.CTkButton(
            button_frame,
            text="← Nochmal",
            font=self._fonts["body"],
            width=back_btn_width,
            height=back_btn_height,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_primary"],
            corner_radius=10,
            command=self._on_back
        )
        back_btn.pack(side="left")

        # Weiter-Button (rechts) - prominent
        continue_btn_width = 140 if self._is_small else 180
        continue_btn_height = 45 if self._is_small else 55
        continue_font_size = 14 if self._is_small else 16
        self.continue_btn = ctk.CTkButton(
            button_frame,
            text="Weiter →",
            font=("Segoe UI", continue_font_size, "bold"),
            width=continue_btn_width,
            height=continue_btn_height,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            corner_radius=10,
            command=self._on_continue
        )
        self.continue_btn.pack(side="right")

    def _create_filter_grid(self, parent):
        """Erstellt das Filter-Grid mit 2 Spalten"""
        filters = list(AVAILABLE_FILTERS.items())
        card_spacing = 4 if self._is_small else 8

        for i in range(0, len(filters), 2):
            row_frame = ctk.CTkFrame(parent, fg_color="transparent")
            row_frame.pack(fill="x", pady=card_spacing)

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
                    card.pack(side="left", padx=card_spacing)
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

            # Kleinere Preview für kleine Bildschirme
            max_preview_size = 400 if self._is_small else 500
            preview = self.app.renderer.render_preview(
                filtered_photos,
                self.app.template_boxes,
                self.app.overlay_image,
                max_size=max_preview_size
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

        # Sample-Bild für Previews - kleiner für kleine Bildschirme
        sample = self.app.photos_taken[0].copy()
        thumb_size = (150, 100) if self._is_small else (200, 150)
        sample.thumbnail(thumb_size, Image.Resampling.LANCZOS)

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
