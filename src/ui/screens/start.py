"""Start-Screen mit Template-Auswahl"""

import customtkinter as ctk
from typing import TYPE_CHECKING
from pathlib import Path

from src.templates.loader import TemplateLoader
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class StartScreen(ctk.CTkFrame):
    """Start-Screen mit Template-Auswahl und Single-Foto Option"""
    
    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent)
        self.app = app
        self.config = app.config
        self.selected_option = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Erstellt die UI"""
        # Titel
        title = ctk.CTkLabel(
            self,
            text=self.config["ui_texts"].get("choose_mode", "Wähle dein Layout!"),
            font=ctk.CTkFont(size=36, weight="bold")
        )
        title.pack(pady=(40, 20))
        
        # Options-Container
        options_frame = ctk.CTkFrame(self)
        options_frame.pack(pady=20, padx=40, fill="x")
        
        # Template-Optionen laden
        self._create_options(options_frame)
        
        # Start-Button
        self.start_btn = ctk.CTkButton(
            self,
            text=self.config["ui_texts"].get("start", "START"),
            font=ctk.CTkFont(size=24, weight="bold"),
            width=250,
            height=70,
            state="disabled",
            command=self._on_start
        )
        self.start_btn.pack(pady=40)
        
        # Admin-Button (dezent)
        admin_btn = ctk.CTkButton(
            self,
            text=self.config["ui_texts"].get("admin", "ADMIN"),
            font=ctk.CTkFont(size=12),
            width=80,
            height=30,
            fg_color="transparent",
            text_color="gray",
            command=self.app.show_admin_dialog
        )
        admin_btn.place(relx=0.98, rely=0.02, anchor="ne")
    
    def _create_options(self, parent):
        """Erstellt die Template-Optionen"""
        # Grid für Optionen
        parent.grid_columnconfigure((0, 1, 2), weight=1)
        
        col = 0
        
        # Template 1
        if self.config.get("template1_enabled") and self.config["template_paths"].get("template1"):
            self._create_option_card(parent, "template1", "Template 1", col)
            col += 1
        
        # Template 2
        if self.config.get("template2_enabled") and self.config["template_paths"].get("template2"):
            self._create_option_card(parent, "template2", "Template 2", col)
            col += 1
        
        # Single-Foto
        if self.config.get("allow_single_mode", True):
            self._create_option_card(parent, "single", "Single-Foto", col, is_single=True)
    
    def _create_option_card(self, parent, option_id: str, label: str, column: int, is_single: bool = False):
        """Erstellt eine Options-Karte"""
        card = ctk.CTkFrame(parent, width=300, height=250, corner_radius=15)
        card.grid(row=0, column=column, padx=20, pady=20)
        card.grid_propagate(False)
        
        # Vorschau-Label (Platzhalter)
        preview = ctk.CTkLabel(
            card,
            text="📷" if is_single else "🖼️",
            font=ctk.CTkFont(size=80)
        )
        preview.pack(pady=(30, 10))
        
        # Text-Label
        text = ctk.CTkLabel(
            card,
            text=label,
            font=ctk.CTkFont(size=18, weight="bold")
        )
        text.pack(pady=10)
        
        # Klick-Handler
        card.bind("<Button-1>", lambda e, oid=option_id: self._select_option(oid))
        preview.bind("<Button-1>", lambda e, oid=option_id: self._select_option(oid))
        text.bind("<Button-1>", lambda e, oid=option_id: self._select_option(oid))
        
        # Referenz speichern
        setattr(self, f"card_{option_id}", card)
    
    def _select_option(self, option_id: str):
        """Wählt eine Option aus"""
        logger.info(f"Option ausgewählt: {option_id}")
        self.selected_option = option_id
        
        # Visuelle Auswahl aktualisieren
        for opt in ["template1", "template2", "single"]:
            card = getattr(self, f"card_{opt}", None)
            if card:
                if opt == option_id:
                    card.configure(border_width=3, border_color="#e00675")
                else:
                    card.configure(border_width=0)
        
        # Start-Button aktivieren
        self.start_btn.configure(state="normal")
    
    def _on_start(self):
        """Start-Button gedrückt"""
        if not self.selected_option:
            return
        
        logger.info(f"Session starten mit: {self.selected_option}")
        
        # Template laden
        if self.selected_option == "single":
            self.app.template_path = None
            self.app.template_boxes = []
        else:
            template_key = self.selected_option  # "template1" oder "template2"
            template_path = self.config["template_paths"].get(template_key, "")
            
            if template_path and Path(template_path).exists():
                overlay, boxes = TemplateLoader.load(template_path)
                self.app.template_path = template_path
                self.app.template_boxes = boxes
                self.app.overlay_image = overlay
        
        # Zu Session-Screen wechseln
        self.app.show_screen("session")
    
    def on_show(self):
        """Wird aufgerufen wenn Screen angezeigt wird"""
        # Auswahl zurücksetzen
        self.selected_option = None
        self.start_btn.configure(state="disabled")
        
        for opt in ["template1", "template2", "single"]:
            card = getattr(self, f"card_{opt}", None)
            if card:
                card.configure(border_width=0)
