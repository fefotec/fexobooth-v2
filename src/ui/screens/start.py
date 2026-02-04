"""Start-Screen mit moderner Template-Auswahl

Optimiert für Lenovo Miix 310 (1280x800)
"""

import customtkinter as ctk
import tkinter as tk
from typing import TYPE_CHECKING, Optional
from pathlib import Path
from PIL import Image, ImageTk
import os

from src.templates.loader import TemplateLoader
from src.templates.default import create_default_template
from src.config.config import find_usb_template
from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


def _is_gallery_enabled(app: "PhotoboothApp") -> bool:
    """Prüft ob Galerie aktiviert ist (Config oder settings.json)"""
    # Erst settings.json prüfen (hat Priorität)
    if app.booking_manager and app.booking_manager.is_loaded:
        if app.booking_manager.settings.online_gallery:
            return True
    # Dann Config prüfen
    return app.config.get("gallery_enabled", False)


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
        
        # Preview-Bereich (größer für bessere Erkennbarkeit)
        preview_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_medium"],
            corner_radius=SIZES["corner_radius_small"],
            height=165  # Größer für bessere Vorschau
        )
        preview_frame.pack(fill="x", padx=10, pady=(10, 5))
        preview_frame.pack_propagate(False)
        preview_frame.bind("<Button-1>", self._on_click)

        # Preview-Bild oder Icon
        if preview_image:
            # Template-Vorschau skalieren (größer)
            preview_copy = preview_image.copy()
            preview_copy.thumbnail((250, 155), Image.Resampling.LANCZOS)
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
                font=("Segoe UI Emoji", 60)  # Größeres Icon
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
        subtitle = "Einzelbild" if is_single else "Druck-Vorlage"
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
    """Start-Screen - optimiert für 1280x800

    Verwendet ein Tkinter Canvas für das Hintergrundbild,
    da CustomTkinter's Stacking-Order nicht zuverlässig funktioniert.
    """

    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.app = app
        self.config = app.config
        self.selected_card: Optional[TemplateCard] = None
        self.selected_option: Optional[str] = None
        self.cards = {}
        self.cards_frame: Optional[ctk.CTkFrame] = None
        self._usb_template_path: Optional[str] = None

        # Hintergrundbild-Referenzen
        self._bg_photo: Optional[ImageTk.PhotoImage] = None  # Tkinter PhotoImage
        self._bg_canvas_id: Optional[int] = None  # Canvas Item ID

        self._setup_ui()

    def _setup_ui(self):
        """Erstellt die UI mit Canvas-basiertem Hintergrundbild"""
        self.qr_label: Optional[ctk.CTkLabel] = None

        # Canvas für Hintergrundbild (füllt gesamten Screen)
        self.bg_canvas = tk.Canvas(
            self,
            highlightthickness=0,
            bg=COLORS["bg_dark"]
        )
        self.bg_canvas.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        # Titel (direkt auf dem Frame, über dem Canvas)
        self.title_label = ctk.CTkLabel(
            self,
            text=self.config.get("ui_texts", {}).get("choose_mode", "Wähle dein Layout!"),
            font=FONTS["title"],
            text_color=COLORS["text_primary"],
            fg_color="transparent"
        )
        self.title_label.place(relx=0.5, rely=0.18, anchor="center")

        # Untertitel
        self.subtitle_label = ctk.CTkLabel(
            self,
            text="Tippe auf eine Option",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            fg_color="transparent"
        )
        self.subtitle_label.place(relx=0.5, rely=0.24, anchor="center")

        # Karten-Container (transparent)
        self.cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.cards_frame.place(relx=0.5, rely=0.50, anchor="center")

        # Template-Karten erstellen
        self._create_template_cards(self.cards_frame)

        # Start-Button
        self.start_btn = ctk.CTkButton(
            self,
            text=f"▶  {self.config.get('ui_texts', {}).get('start', 'START')}",
            font=("Segoe UI", 24, "bold"),
            width=280,
            height=70,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_muted"],
            corner_radius=35,
            border_width=3,
            border_color=COLORS["border"],
            state="disabled",
            command=self._on_start
        )
        self.start_btn.place(relx=0.5, rely=0.75, anchor="center")

        # Galerie-Banner (unten)
        self.gallery_banner = ctk.CTkFrame(self, fg_color="transparent")
        self.gallery_banner.place(relx=0.5, rely=0.92, anchor="center")

    def _setup_background(self):
        """Lädt und zeigt optionales Hintergrundbild auf dem Canvas"""
        # Altes Bild vom Canvas entfernen
        if self._bg_canvas_id is not None:
            self.bg_canvas.delete(self._bg_canvas_id)
            self._bg_canvas_id = None
        self._bg_photo = None

        bg_path = self.config.get("startscreen_background", "")
        if not bg_path or not os.path.exists(bg_path):
            logger.debug("Kein Hintergrundbild konfiguriert")
            self.bg_canvas.configure(bg=COLORS["bg_dark"])
            return

        try:
            # Bild laden
            bg_img = Image.open(bg_path)
            logger.debug(f"Hintergrundbild geladen: {bg_img.size} ({bg_img.mode})")

            # Zielgröße
            target_w = 1280
            target_h = 800

            # Cover-Modus: Bild füllt gesamten Bereich
            img_ratio = bg_img.width / bg_img.height
            target_ratio = target_w / target_h

            if img_ratio > target_ratio:
                new_h = target_h
                new_w = int(new_h * img_ratio)
            else:
                new_w = target_w
                new_h = int(new_w / img_ratio)

            bg_img = bg_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Zentrieren und beschneiden
            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            bg_img = bg_img.crop((left, top, left + target_w, top + target_h))

            # Als Tkinter PhotoImage (NICHT CTkImage!)
            self._bg_photo = ImageTk.PhotoImage(bg_img)

            # Auf Canvas zeichnen (Position: Mitte des Canvas)
            self._bg_canvas_id = self.bg_canvas.create_image(
                target_w // 2, target_h // 2,
                image=self._bg_photo,
                anchor="center"
            )

            logger.info(f"✅ Hintergrundbild auf Canvas: {bg_path}")

        except Exception as e:
            logger.warning(f"Hintergrundbild konnte nicht geladen werden: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    def _create_template_cards(self, parent):
        """Erstellt die Template-Karten"""
        has_custom_template = False

        logger.info("=== Erstelle Template-Karten ===")

        # USB-Template hat höchste Priorität (aus Cache oder USB)
        cached = self.app.cached_usb_template
        if cached or (hasattr(self, '_usb_template_path') and self._usb_template_path):
            # Preview aus Cache oder vom USB laden
            if cached and cached.get("overlay"):
                logger.info(f"USB-Template aus Cache: {cached.get('name')}")
                preview = cached.get("overlay")
                usb_filename = cached.get("name", "USB-Template")
            else:
                logger.info(f"USB-Template vom Stick: {self._usb_template_path}")
                preview = self._load_template_preview(self._usb_template_path)
                usb_filename = os.path.basename(self._usb_template_path)

            card = TemplateCard(
                parent,
                title="Druckvorlage",
                preview_image=preview,
                on_click=lambda c: self._select_card(c, "usb_template")
            )
            card.pack(side="left", padx=10)
            self.cards["usb_template"] = card

            # Automatisch vorselektieren!
            self._select_card(card, "usb_template")
            # Button wird in _select_card aktiviert

            logger.info(f"✅ USB-Template Karte erstellt und vorselektiert: {self._usb_template_path}")
            # WICHTIG: Kein return hier! Single-Foto Karte soll auch erstellt werden
            has_custom_template = True  # USB-Template zählt als Custom

        # Bei USB-Template (Cache oder aktuell): Nur USB + Single anzeigen, keine Config-Templates
        usb_active = self.app.cached_usb_template or (hasattr(self, '_usb_template_path') and self._usb_template_path)

        if not usb_active:
            logger.debug(f"template1_enabled: {self.config.get('template1_enabled')}")
            logger.debug(f"template2_enabled: {self.config.get('template2_enabled')}")
            logger.debug(f"template_paths: {self.config.get('template_paths', {})}")

        # Template 1 (nur wenn kein USB-Template)
        t1_enabled = self.config.get("template1_enabled", False) and not usb_active
        t1_path = self.config.get("template_paths", {}).get("template1", "")
        t1_resolved = self._resolve_template_path(t1_path) if t1_path else None
        if not usb_active:
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
        
        # Template 2 (nur wenn kein USB-Template)
        t2_enabled = self.config.get("template2_enabled", False) and not usb_active
        t2_path = self.config.get("template_paths", {}).get("template2", "")
        t2_resolved = self._resolve_template_path(t2_path) if t2_path else None
        if not usb_active:
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
        allow_single = self.config.get("allow_single_mode", True)
        logger.info(f"Single-Foto Modus: {'aktiviert' if allow_single else 'DEAKTIVIERT (im Admin aktivieren!)'}")
        
        if allow_single:
            card = TemplateCard(
                parent,
                title="Single-Foto",
                is_single=True,
                on_click=lambda c: self._select_card(c, "single")
            )
            card.pack(side="left", padx=10)
            self.cards["single"] = card
        
        # Fallback: Wenn keine Karten erstellt wurden, zeige Warnung und Standard
        if not self.cards:
            logger.error("KEINE KARTEN ERSTELLT! Zeige Notfall-Single-Karte")
            card = TemplateCard(
                parent,
                title="Einzelfoto",
                is_single=True,
                on_click=lambda c: self._select_card(c, "single")
            )
            card.pack(side="left", padx=10)
            self.cards["single"] = card
        
        logger.info(f"Erstellte Karten: {list(self.cards.keys())}")
    
    def _resolve_template_path(self, template_path: str) -> Optional[str]:
        """Löst Template-Pfad auf (relativ oder absolut)"""
        if not template_path:
            logger.debug("Template-Pfad leer")
            return None
        
        logger.debug(f"Prüfe Template-Pfad: '{template_path}'")
        
        # Direkt prüfen ob Pfad existiert (absolut oder relativ)
        if os.path.exists(template_path):
            logger.debug(f"Pfad existiert direkt: {template_path}")
            return template_path
        
        # Windows: Laufwerksbuchstaben wie D:/ sind absolut
        if os.name == "nt" and len(template_path) >= 2 and template_path[1] == ':':
            logger.warning(f"Windows-Pfad existiert nicht: {template_path}")
            return None
        
        # Absoluter Pfad der nicht existiert
        if os.path.isabs(template_path):
            logger.warning(f"Absoluter Pfad existiert nicht: {template_path}")
            return None
        
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
            logger.debug(f"Versuche: {full_path}")
            if full_path.exists():
                logger.info(f"Template-Pfad aufgelöst: {template_path} -> {full_path}")
                return str(full_path)
        
        logger.warning(f"Template-Pfad nicht gefunden: {template_path}")
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
        logger.debug(f"Karte ausgewählt: {option}")

        # Alte Auswahl zurücksetzen (mit Fehlerbehandlung für zerstörte Widgets)
        if self.selected_card:
            try:
                self.selected_card.set_selected(False)
            except Exception as e:
                logger.debug(f"Alte Karte bereits zerstört: {e}")

        # Neue Auswahl setzen
        try:
            card.set_selected(True)
            self.selected_card = card
            self.selected_option = option

            # Start-Button aktivieren und animieren
            self._enable_start_button()

            logger.info(f"Ausgewählt: {option}")
        except Exception as e:
            logger.error(f"Fehler beim Auswählen der Karte: {e}")
            self.selected_card = None
            self.selected_option = None

    def _enable_start_button(self):
        """Aktiviert den Start-Button (grau → farbig)"""
        self.start_btn.configure(
            state="normal",
            fg_color=COLORS["primary"],
            text_color=COLORS["text_primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["primary"]
        )

    def _disable_start_button(self):
        """Deaktiviert den Start-Button (farbig → grau)"""
        self.start_btn.configure(
            state="disabled",
            fg_color=COLORS["bg_light"],
            text_color=COLORS["text_muted"],
            hover_color=COLORS["bg_card"],
            border_color=COLORS["border"]
        )
    
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

        elif self.selected_option == "usb_template":
            # USB-Template aus Cache verwenden (falls vorhanden)
            cached = self.app.cached_usb_template
            if cached and cached.get("overlay") and cached.get("boxes"):
                logger.info(f"Verwende gecachtes USB-Template: {cached.get('name')}")
                self.app.template_path = cached.get("path")
                self.app.template_boxes = cached.get("boxes")
                self.app.overlay_image = cached.get("overlay")
                logger.info(f"USB-Template aus Cache: {len(cached.get('boxes'))} Foto-Slots")
            elif hasattr(self, '_usb_template_path') and self._usb_template_path:
                # Fallback: Direkt laden wenn Cache leer
                logger.info(f"Lade USB-Template direkt: {self._usb_template_path}")
                overlay, boxes = TemplateLoader.load(self._usb_template_path)
                if overlay and boxes:
                    self.app.template_path = self._usb_template_path
                    self.app.template_boxes = boxes
                    self.app.overlay_image = overlay
                    # Auch cachen für nächstes Mal
                    self.app.cached_usb_template = {
                        "path": self._usb_template_path,
                        "name": os.path.basename(self._usb_template_path),
                        "overlay": overlay,
                        "boxes": boxes
                    }
                    logger.info(f"USB-Template geladen und gecached: {len(boxes)} Foto-Slots")
                else:
                    logger.error("USB-Template konnte nicht geladen werden!")
                    return
            else:
                logger.error("Kein USB-Template verfügbar (weder Cache noch USB)!")
                return

        else:
            # Custom Template laden (template1, template2)
            if not self.app.load_template(self.selected_option):
                # Fallback auf Standard-Template
                overlay, boxes = create_default_template()
                self.app.template_boxes = boxes
                self.app.overlay_image = overlay

        # Video abspielen wenn konfiguriert, sonst direkt zur Session
        self.app.play_video("video_start", "session")

    def on_show(self):
        """Screen wird angezeigt - Template-Karten neu laden falls Config geändert"""
        logger.info("=== StartScreen on_show ===")

        # Config könnte sich geändert haben (Admin-Dialog)
        self.config = self.app.config

        # USB-Template prüfen mit Caching-Logik
        current_usb_template = find_usb_template()

        if current_usb_template:
            # USB eingesteckt mit Template
            template_name = os.path.basename(current_usb_template)

            # Prüfen ob es ein NEUES Template ist (anderer Name)
            cached = self.app.cached_usb_template
            if cached and cached.get("name") == template_name:
                # Gleiches Template - Cache verwenden
                logger.info(f"USB-Template unverändert: {template_name} (verwende Cache)")
                self._usb_template_path = current_usb_template
            else:
                # Neues Template - laden und cachen
                logger.info(f"=== NEUES USB-Template gefunden: {current_usb_template} ===")
                self._usb_template_path = current_usb_template

                # Template vorladen und cachen
                try:
                    overlay, boxes = TemplateLoader.load(current_usb_template)
                    if overlay and boxes:
                        self.app.cached_usb_template = {
                            "path": current_usb_template,
                            "name": template_name,
                            "overlay": overlay,
                            "boxes": boxes
                        }
                        logger.info(f"USB-Template gecached: {template_name} ({len(boxes)} Slots)")
                except Exception as e:
                    logger.error(f"USB-Template laden fehlgeschlagen: {e}")
        else:
            # Kein USB eingesteckt - prüfen ob Cache vorhanden
            if self.app.cached_usb_template:
                logger.info(f"USB nicht eingesteckt - verwende gecachtes Template: {self.app.cached_usb_template.get('name')}")
                self._usb_template_path = self.app.cached_usb_template.get("path")
            else:
                self._usb_template_path = None

        # Alte Karten entfernen und neu erstellen (setzt auch selected_card = None)
        self._refresh_template_cards()

        # Start-Button deaktivieren bis eine Auswahl getroffen wird
        # (wird in _create_template_cards aktiviert wenn USB-Template vorselektiert)
        if not self.selected_option:
            self._disable_start_button()
        else:
            self._enable_start_button()

        # QR-Code für Galerie anzeigen/ausblenden
        self._update_qr_code()

        # Hintergrundbild aktualisieren (Canvas-basiert)
        self._setup_background()
    
    def _update_qr_code(self):
        """Zeigt horizontales Galerie-Banner am unteren Rand"""
        # Alte Elemente entfernen
        if self.qr_label:
            self.qr_label.destroy()
            self.qr_label = None

        for widget in self.gallery_banner.winfo_children():
            widget.destroy()

        # Prüfen ob Galerie aktiv
        if not _is_gallery_enabled(self.app):
            logger.debug("Galerie nicht aktiv - kein Banner")
            return

        # Prüfen ob gallery_show_qr aktiv (default: True)
        if not self.config.get("gallery_show_qr", True):
            logger.debug("QR-Code Anzeige deaktiviert")
            return

        try:
            from src.gallery import get_gallery_url, generate_qr_code

            # URL und WLAN-Daten holen
            gallery_config = self.config.get("gallery", {})
            port = gallery_config.get("port", self.config.get("gallery_port", 8080))
            url = get_gallery_url(port)
            ssid = gallery_config.get("hotspot_ssid", "fexobox-gallery")
            password = gallery_config.get("hotspot_password", "fotobox123")

            # QR-Code generieren (größer für bessere Scanbarkeit)
            qr_img = generate_qr_code(url, size=90)
            if not qr_img:
                logger.warning("QR-Code konnte nicht generiert werden")
                return

            # Horizontales Banner mit Pink-Rahmen
            outer_banner = ctk.CTkFrame(
                self.gallery_banner,
                fg_color=COLORS["primary"],
                corner_radius=12
            )
            outer_banner.pack(padx=20, pady=5)

            # Innerer Banner-Container
            banner = ctk.CTkFrame(
                outer_banner,
                fg_color=COLORS["bg_medium"],
                corner_radius=10
            )
            banner.pack(padx=2, pady=2)

            # Horizontales Layout: QR links, Info rechts
            content = ctk.CTkFrame(banner, fg_color="transparent")
            content.pack(padx=15, pady=10)

            # QR-Code links (weißer Hintergrund)
            qr_container = ctk.CTkFrame(content, fg_color="#ffffff", corner_radius=8)
            qr_container.pack(side="left", padx=(0, 20))

            self.qr_ctk_image = ctk.CTkImage(light_image=qr_img, size=(90, 90))
            self.qr_label = ctk.CTkLabel(
                qr_container,
                image=self.qr_ctk_image,
                text="",
                fg_color="#ffffff"
            )
            self.qr_label.pack(padx=6, pady=6)

            # Info-Bereich rechts
            info_frame = ctk.CTkFrame(content, fg_color="transparent")
            info_frame.pack(side="left", fill="y")

            # Titel
            ctk.CTkLabel(
                info_frame,
                text="📸 FOTO-GALERIE",
                font=("Segoe UI", 16, "bold"),
                text_color=COLORS["primary"]
            ).pack(anchor="w")

            # WLAN-Info (größer und lesbarer)
            wifi_info = ctk.CTkFrame(info_frame, fg_color="transparent")
            wifi_info.pack(anchor="w", pady=(8, 0))

            ctk.CTkLabel(
                wifi_info,
                text=f"📶 WLAN:  {ssid}",
                font=("Segoe UI", 14, "bold"),
                text_color=COLORS["text_primary"]
            ).pack(anchor="w")

            ctk.CTkLabel(
                wifi_info,
                text=f"🔑 Passwort:  {password}",
                font=("Segoe UI", 14),
                text_color=COLORS["text_secondary"]
            ).pack(anchor="w", pady=(2, 0))

            # Anleitung
            ctk.CTkLabel(
                info_frame,
                text="1. Mit WLAN verbinden  →  2. QR-Code scannen  →  3. Fotos ansehen!",
                font=("Segoe UI", 12),
                text_color=COLORS["text_muted"]
            ).pack(anchor="w", pady=(10, 0))

            logger.info(f"✅ Galerie-Banner angezeigt: {url}")

        except ImportError as e:
            logger.warning(f"Galerie-Modul nicht verfügbar: {e}")
        except Exception as e:
            logger.error(f"Galerie-Banner Fehler: {e}")
    
    def _refresh_template_cards(self):
        """Erstellt Template-Karten neu (nach Config-Änderung)"""
        logger.info("=== Refresh Template-Karten ===")
        
        # WICHTIG: Auswahl zurücksetzen BEVOR Karten zerstört werden!
        self.selected_card = None
        self.selected_option = None
        
        # Alle alten Karten entfernen
        for key, card in self.cards.items():
            logger.debug(f"Entferne alte Karte: {key}")
            try:
                card.destroy()
            except Exception as e:
                logger.debug(f"Karte {key} bereits zerstört: {e}")
        self.cards = {}
        
        # Neue Karten im gespeicherten Container erstellen
        if self.cards_frame is not None:
            self._create_template_cards(self.cards_frame)
        else:
            logger.error("cards_frame ist None - kann keine Karten erstellen!")

    def on_hide(self):
        """Screen wird verlassen"""
        pass  # Placeholder für eventuelle Cleanup-Aufgaben
