"""Start-Screen mit moderner Template-Auswahl"""

import customtkinter as ctk
from typing import TYPE_CHECKING, Optional
from pathlib import Path
from PIL import Image
import os

from src.templates.loader import TemplateLoader
from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class TemplateCard(ctk.CTkFrame):
    """Moderne Template-Auswahl-Karte"""
    
    def __init__(self, parent, title: str, preview_image: Optional[Image.Image] = None,
                 is_single: bool = False, on_click=None):
        super().__init__(
            parent,
            width=SIZES["card_width"],
            height=SIZES["card_height"],
            fg_color=COLORS["bg_card"],
            corner_radius=SIZES["corner_radius"],
            border_width=3,
            border_color=COLORS["border"]
        )
        self.grid_propagate(False)
        self.pack_propagate(False)
        
        self.title = title
        self.is_selected = False
        self.on_click = on_click
        
        # Hover-Effekt
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        
        # Preview-Bereich
        preview_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_medium"],
            corner_radius=SIZES["corner_radius_small"],
            height=180
        )
        preview_frame.pack(fill="x", padx=15, pady=(15, 10))
        preview_frame.pack_propagate(False)
        preview_frame.bind("<Button-1>", self._on_click)
        
        # Preview-Bild oder Icon
        if preview_image:
            # Bild auf Größe skalieren
            preview_image.thumbnail((280, 160), Image.Resampling.LANCZOS)
            self.preview_ctk = ctk.CTkImage(
                light_image=preview_image,
                size=(preview_image.width, preview_image.height)
            )
            preview_label = ctk.CTkLabel(preview_frame, image=self.preview_ctk, text="")
        else:
            # Icon als Fallback
            icon = "📷" if is_single else "🖼️"
            preview_label = ctk.CTkLabel(
                preview_frame,
                text=icon,
                font=("Segoe UI Emoji", 70)
            )
        preview_label.pack(expand=True)
        preview_label.bind("<Button-1>", self._on_click)
        
        # Titel
        title_label = ctk.CTkLabel(
            self,
            text=title,
            font=FONTS["subheading"],
            text_color=COLORS["text_primary"]
        )
        title_label.pack(pady=(5, 10))
        title_label.bind("<Button-1>", self._on_click)
        
        # Untertitel
        subtitle = "Ein Foto, volle Auflösung" if is_single else "Mehrere Fotos im Layout"
        subtitle_label = ctk.CTkLabel(
            self,
            text=subtitle,
            font=FONTS["small"],
            text_color=COLORS["text_muted"]
        )
        subtitle_label.pack()
        subtitle_label.bind("<Button-1>", self._on_click)
    
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


class StartScreen(ctk.CTkFrame):
    """Moderner Start-Screen"""
    
    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.app = app
        self.config = app.config
        self.selected_card: Optional[TemplateCard] = None
        self.selected_option: Optional[str] = None
        self.cards = {}
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Erstellt die UI"""
        # Zentrierter Container
        center_frame = ctk.CTkFrame(self, fg_color="transparent")
        center_frame.place(relx=0.5, rely=0.5, anchor="center")
        
        # Titel
        title = ctk.CTkLabel(
            center_frame,
            text=self.config.get("ui_texts", {}).get("choose_mode", "Wähle dein Layout!"),
            font=FONTS["title"],
            text_color=COLORS["text_primary"]
        )
        title.pack(pady=(0, 10))
        
        # Untertitel
        subtitle = ctk.CTkLabel(
            center_frame,
            text="Tippe auf eine Option um zu starten",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        )
        subtitle.pack(pady=(0, 40))
        
        # Karten-Container
        cards_frame = ctk.CTkFrame(center_frame, fg_color="transparent")
        cards_frame.pack(pady=20)
        
        # Template-Karten erstellen
        self._create_template_cards(cards_frame)
        
        # Start-Button
        self.start_btn = ctk.CTkButton(
            center_frame,
            text=self.config.get("ui_texts", {}).get("start", "START"),
            font=FONTS["button_large"],
            width=SIZES["button_large_width"],
            height=SIZES["button_large_height"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            corner_radius=SIZES["corner_radius"],
            state="disabled",
            command=self._on_start
        )
        self.start_btn.pack(pady=40)
    
    def _create_template_cards(self, parent):
        """Erstellt die Template-Karten"""
        # Template 1
        if self.config.get("template1_enabled"):
            template_path = self.config.get("template_paths", {}).get("template1", "")
            preview = self._load_template_preview(template_path)
            
            card = TemplateCard(
                parent,
                title="Template 1",
                preview_image=preview,
                on_click=lambda c: self._select_card(c, "template1")
            )
            card.pack(side="left", padx=15)
            self.cards["template1"] = card
        
        # Template 2
        if self.config.get("template2_enabled"):
            template_path = self.config.get("template_paths", {}).get("template2", "")
            preview = self._load_template_preview(template_path)
            
            card = TemplateCard(
                parent,
                title="Template 2",
                preview_image=preview,
                on_click=lambda c: self._select_card(c, "template2")
            )
            card.pack(side="left", padx=15)
            self.cards["template2"] = card
        
        # Single-Foto
        if self.config.get("allow_single_mode", True):
            card = TemplateCard(
                parent,
                title="Single-Foto",
                is_single=True,
                on_click=lambda c: self._select_card(c, "single")
            )
            card.pack(side="left", padx=15)
            self.cards["single"] = card
    
    def _load_template_preview(self, template_path: str) -> Optional[Image.Image]:
        """Lädt Template-Vorschau"""
        if not template_path or not os.path.exists(template_path):
            return None
        
        try:
            overlay, _ = TemplateLoader.load(template_path)
            return overlay
        except Exception as e:
            logger.warning(f"Template-Vorschau konnte nicht geladen werden: {e}")
            return None
    
    def _select_card(self, card: TemplateCard, option: str):
        """Wählt eine Karte aus"""
        # Alte Auswahl deselektieren
        if self.selected_card:
            self.selected_card.set_selected(False)
        
        # Neue Auswahl
        card.set_selected(True)
        self.selected_card = card
        self.selected_option = option
        
        # Start-Button aktivieren
        self.start_btn.configure(state="normal")
        
        logger.debug(f"Option ausgewählt: {option}")
    
    def _on_start(self):
        """Start-Button gedrückt"""
        if not self.selected_option:
            return
        
        logger.info(f"Session starten: {self.selected_option}")
        
        # Template laden
        if self.selected_option == "single":
            self.app.template_path = None
            self.app.template_boxes = [{"box": (0, 0, 1799, 1199), "angle": 0}]
            self.app.overlay_image = None
        else:
            if not self.app.load_template(self.selected_option):
                # Fallback wenn Template nicht lädt
                self.app.template_boxes = [{"box": (0, 0, 1799, 1199), "angle": 0}]
        
        # Zu Session wechseln
        self.app.show_screen("session")
    
    def on_show(self):
        """Screen wird angezeigt"""
        # Auswahl zurücksetzen
        if self.selected_card:
            self.selected_card.set_selected(False)
        self.selected_card = None
        self.selected_option = None
        self.start_btn.configure(state="disabled")
