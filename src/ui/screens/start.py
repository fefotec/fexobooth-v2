"""Start-Screen mit moderner Template-Auswahl

Optimiert für Lenovo Miix 310 (1280x800)
"""

import customtkinter as ctk
from typing import TYPE_CHECKING, Optional
from pathlib import Path
from PIL import Image
import os

from src.templates.loader import TemplateLoader
from src.templates.default import create_default_template
from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class TemplateCard(ctk.CTkFrame):
    """Template-Auswahl-Karte - kompakt für 1280x800"""
    
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
        
        # Preview-Bereich (kompakter)
        preview_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_medium"],
            corner_radius=SIZES["corner_radius_small"],
            height=130  # Kompakter für 800px Höhe
        )
        preview_frame.pack(fill="x", padx=10, pady=(10, 5))
        preview_frame.pack_propagate(False)
        preview_frame.bind("<Button-1>", self._on_click)
        
        # Preview-Bild oder Icon
        if preview_image:
            # Template-Vorschau skalieren
            preview_copy = preview_image.copy()
            preview_copy.thumbnail((200, 120), Image.Resampling.LANCZOS)
            self.preview_ctk = ctk.CTkImage(
                light_image=preview_copy,
                size=(preview_copy.width, preview_copy.height)
            )
            preview_label = ctk.CTkLabel(preview_frame, image=self.preview_ctk, text="")
            preview_label.image = self.preview_ctk  # Referenz halten!
        else:
            icon = "📷" if is_single else "🖼️"
            preview_label = ctk.CTkLabel(
                preview_frame,
                text=icon,
                font=("Segoe UI Emoji", 50)
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
        title_label.pack(pady=(5, 3))
        title_label.bind("<Button-1>", self._on_click)
        
        # Untertitel (kürzer)
        subtitle = "Einzelfoto" if is_single else "Layout"
        subtitle_label = ctk.CTkLabel(
            self,
            text=subtitle,
            font=FONTS["tiny"],
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
    """Start-Screen - optimiert für 1280x800"""
    
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
        
        # Titel (kompakter)
        title = ctk.CTkLabel(
            center_frame,
            text=self.config.get("ui_texts", {}).get("choose_mode", "Wähle dein Layout!"),
            font=FONTS["title"],
            text_color=COLORS["text_primary"]
        )
        title.pack(pady=(0, 5))
        
        # Untertitel
        subtitle = ctk.CTkLabel(
            center_frame,
            text="Tippe auf eine Option",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        )
        subtitle.pack(pady=(0, 20))
        
        # Karten-Container
        cards_frame = ctk.CTkFrame(center_frame, fg_color="transparent")
        cards_frame.pack(pady=10)
        
        # Template-Karten erstellen
        self._create_template_cards(cards_frame)
        
        # Start-Button (kompakter)
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
        self.start_btn.pack(pady=25)
    
    def _create_template_cards(self, parent):
        """Erstellt die Template-Karten"""
        has_custom_template = False
        
        logger.info("=== Erstelle Template-Karten ===")
        logger.debug(f"template1_enabled: {self.config.get('template1_enabled')}")
        logger.debug(f"template2_enabled: {self.config.get('template2_enabled')}")
        logger.debug(f"template_paths: {self.config.get('template_paths', {})}")
        
        # Template 1
        t1_enabled = self.config.get("template1_enabled", False)
        t1_path = self.config.get("template_paths", {}).get("template1", "")
        t1_resolved = self._resolve_template_path(t1_path) if t1_path else None
        logger.info(f"Template 1: enabled={t1_enabled}, path='{t1_path}', resolved='{t1_resolved}'")
        
        if t1_enabled:
            if t1_resolved:
                preview = self._load_template_preview(t1_resolved)
                card = TemplateCard(
                    parent,
                    title="Template 1",
                    preview_image=preview,
                    on_click=lambda c: self._select_card(c, "template1")
                )
                card.pack(side="left", padx=10)
                self.cards["template1"] = card
                has_custom_template = True
                logger.info(f"✅ Template 1 Karte erstellt: {t1_resolved}")
            else:
                logger.warning(f"Template 1 aktiviert aber Pfad nicht gefunden: '{t1_path}'")
        
        # Template 2
        t2_enabled = self.config.get("template2_enabled", False)
        t2_path = self.config.get("template_paths", {}).get("template2", "")
        t2_resolved = self._resolve_template_path(t2_path) if t2_path else None
        logger.info(f"Template 2: enabled={t2_enabled}, path='{t2_path}', resolved='{t2_resolved}'")
        
        if t2_enabled:
            if t2_resolved:
                preview = self._load_template_preview(t2_resolved)
                card = TemplateCard(
                    parent,
                    title="Template 2",
                    preview_image=preview,
                    on_click=lambda c: self._select_card(c, "template2")
                )
                card.pack(side="left", padx=10)
                self.cards["template2"] = card
                has_custom_template = True
                logger.info(f"✅ Template 2 Karte erstellt: {t2_resolved}")
            else:
                logger.warning(f"Template 2 aktiviert aber Pfad nicht gefunden: '{t2_path}'")
        
        # Standard 2x2 Template (wenn keine Custom-Templates aktiv)
        if not has_custom_template:
            logger.info("Keine Custom-Templates aktiv, zeige Standard 2x2")
            # Vorschau für Standard-Template generieren
            default_overlay, _ = create_default_template()
            
            card = TemplateCard(
                parent,
                title="Standard 2x2",
                preview_image=default_overlay,
                on_click=lambda c: self._select_card(c, "default_2x2")
            )
            card.pack(side="left", padx=10)
            self.cards["default_2x2"] = card
        
        # Single-Foto
        if self.config.get("allow_single_mode", True):
            card = TemplateCard(
                parent,
                title="Single-Foto",
                is_single=True,
                on_click=lambda c: self._select_card(c, "single")
            )
            card.pack(side="left", padx=10)
            self.cards["single"] = card
        
        logger.info(f"Erstellte Karten: {list(self.cards.keys())}")
    
    def _resolve_template_path(self, template_path: str) -> Optional[str]:
        """Löst Template-Pfad auf (relativ oder absolut)"""
        if not template_path:
            return None
        
        # Absoluter Pfad?
        if os.path.isabs(template_path) and os.path.exists(template_path):
            return template_path
        
        # Relativer Pfad - versuche verschiedene Basis-Verzeichnisse
        search_bases = [
            Path(__file__).parent.parent.parent.parent,  # Projekt-Root
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
        
        # Pfad wie angegeben versuchen
        if os.path.exists(template_path):
            return template_path
        
        return None
    
    def _load_template_preview(self, template_path: str) -> Optional[Image.Image]:
        """Lädt Template-Vorschau (ZIP oder PNG)"""
        resolved = self._resolve_template_path(template_path)
        if not resolved:
            logger.warning(f"Template-Pfad nicht gefunden: {template_path}")
            return None
        
        try:
            # Für PNG direkt laden (schneller für Preview)
            if resolved.lower().endswith(".png"):
                preview = Image.open(resolved).convert("RGBA")
                logger.debug(f"PNG-Vorschau geladen: {preview.size}")
                return preview
            
            # Für ZIP den Loader nutzen
            overlay, _ = TemplateLoader.load(resolved)
            return overlay
        except Exception as e:
            logger.warning(f"Template-Vorschau Fehler: {e}")
            return None
    
    def _select_card(self, card: TemplateCard, option: str):
        """Wählt eine Karte aus"""
        if self.selected_card:
            self.selected_card.set_selected(False)
        
        card.set_selected(True)
        self.selected_card = card
        self.selected_option = option
        
        self.start_btn.configure(state="normal")
        logger.debug(f"Option: {option}")
    
    def _on_start(self):
        """Start gedrückt"""
        if not self.selected_option:
            return
        
        logger.info(f"Start: {self.selected_option}")
        
        if self.selected_option == "single":
            # Single-Foto: Eine große Box
            self.app.template_path = None
            self.app.template_boxes = [{"box": (0, 0, 1799, 1199), "angle": 0}]
            self.app.overlay_image = None
            
        elif self.selected_option == "default_2x2":
            # Standard 2x2 Template
            overlay, boxes = create_default_template()
            self.app.template_path = None
            self.app.template_boxes = boxes
            self.app.overlay_image = overlay
            logger.info("Standard 2x2 Template geladen")
            
        else:
            # Custom Template laden
            if not self.app.load_template(self.selected_option):
                # Fallback auf Standard-Template
                overlay, boxes = create_default_template()
                self.app.template_boxes = boxes
                self.app.overlay_image = overlay
        
        # Video abspielen wenn konfiguriert, sonst direkt zur Session
        self.app.play_video("video_start", "session")
    
    def on_show(self):
        """Screen wird angezeigt"""
        if self.selected_card:
            self.selected_card.set_selected(False)
        self.selected_card = None
        self.selected_option = None
        self.start_btn.configure(state="disabled")
