"""Start-Screen mit moderner Template-Auswahl

Responsive Design - passt sich automatisch an Bildschirmgröße an
"""

import customtkinter as ctk
from typing import TYPE_CHECKING, Optional
from pathlib import Path
from PIL import Image
import os
import shutil

from src.templates.loader import TemplateLoader
from src.templates.default import create_default_template
from src.config.config import find_usb_template
from src.ui.theme import COLORS, FONTS, SIZES, get_sizes, get_fonts, is_small_screen
from src.utils.logging import get_logger
from src.ui.screens.video import is_vlc_warm, _vlc_available

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
    """Template-Auswahl-Karte - responsive Design"""

    def __init__(self, parent, title: str, preview_image: Optional[Image.Image] = None,
                 is_single: bool = False, on_click=None):
        # Responsive Größen laden
        sizes = get_sizes()
        fonts = get_fonts()
        self._is_small = is_small_screen()

        card_width = sizes["card_width"]
        card_height = sizes["card_height"]
        corner_radius = sizes["corner_radius"]

        super().__init__(
            parent,
            width=card_width,
            height=card_height,
            fg_color=COLORS["bg_card"],
            corner_radius=corner_radius,
            border_width=2 if self._is_small else 3,
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

        # Preview-Bereich - responsive Höhe
        preview_height = 125 if self._is_small else 165
        preview_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_medium"],
            corner_radius=sizes["corner_radius_small"],
            height=preview_height
        )
        preview_frame.pack(fill="x", padx=8 if self._is_small else 10, pady=(8 if self._is_small else 10, 5))
        preview_frame.pack_propagate(False)
        preview_frame.bind("<Button-1>", self._on_click)

        # Preview-Bild oder Icon
        if preview_image:
            # Template-Vorschau skalieren - responsive
            preview_copy = preview_image.copy()
            thumb_size = (190, 115) if self._is_small else (250, 155)
            preview_copy.thumbnail(thumb_size, Image.Resampling.LANCZOS)
            self.preview_ctk = ctk.CTkImage(
                light_image=preview_copy,
                size=(preview_copy.width, preview_copy.height)
            )
            preview_label = ctk.CTkLabel(preview_frame, image=self.preview_ctk, text="")
            preview_label.image = self.preview_ctk  # Referenz halten!
        else:
            icon = "📷" if is_single else "🖼️"
            icon_size = 45 if self._is_small else 60
            preview_label = ctk.CTkLabel(
                preview_frame,
                text=icon,
                font=("Segoe UI Emoji", icon_size)
            )
        preview_label.pack(expand=True)
        preview_label.bind("<Button-1>", self._on_click)

        # Titel - responsive Font
        title_font = fonts["subheading"] if not self._is_small else fonts["body_bold"]
        title_label = ctk.CTkLabel(
            self,
            text=title,
            font=title_font,
            text_color=COLORS["text_primary"]
        )
        title_label.pack(pady=(4 if self._is_small else 5, 2 if self._is_small else 3))
        title_label.bind("<Button-1>", self._on_click)

        # Untertitel (kürzer) - responsive Font
        subtitle = "Einzelbild" if is_single else "Druck-Vorlage"
        subtitle_font = fonts["tiny"] if not self._is_small else ("Segoe UI", 9)
        subtitle_label = ctk.CTkLabel(
            self,
            text=subtitle,
            font=subtitle_font,
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
        border_width = 3 if self._is_small else 4
        if selected:
            self.configure(
                border_color=COLORS["primary"],
                border_width=border_width,
                fg_color=COLORS["bg_light"]
            )
        else:
            self.configure(
                border_color=COLORS["border"],
                border_width=border_width - 1,
                fg_color=COLORS["bg_card"]
            )


class StartScreen(ctk.CTkFrame):
    """Start-Screen - responsive Design"""

    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.app = app
        self.config = app.config
        self.selected_card: Optional[TemplateCard] = None
        self.selected_option: Optional[str] = None
        self.cards = {}
        self.cards_frame: Optional[ctk.CTkFrame] = None
        self._usb_template_path: Optional[str] = None

        # Responsive Einstellungen
        self._sizes = get_sizes()
        self._fonts = get_fonts()
        self._is_small = is_small_screen()

        self._setup_ui()

    def _setup_ui(self):
        """Erstellt die UI mit pack()-Layout - responsive Design"""
        self.qr_label: Optional[ctk.CTkLabel] = None

        # Galerie-Banner ZUERST (unten) - damit es Platz reserviert
        banner_pady = (0, 5) if self._is_small else (0, 8)
        self.gallery_banner = ctk.CTkFrame(self, fg_color="transparent")
        self.gallery_banner.pack(side="bottom", fill="x", pady=banner_pady)

        # Zentrierter Hauptcontainer (nimmt restlichen Platz)
        center_frame = ctk.CTkFrame(self, fg_color="transparent")
        center_frame.pack(expand=True, fill="both")

        # Innerer Container für vertikale Zentrierung
        inner_frame = ctk.CTkFrame(center_frame, fg_color="transparent")
        inner_frame.place(relx=0.5, rely=0.5, anchor="center")

        # Titel - responsive Font
        title_text = self.config.get("ui_texts", {}).get("choose_mode", "Wähle dein Layout!")
        title_font = self._fonts["title"] if not self._is_small else self._fonts["heading"]
        self.title_label = ctk.CTkLabel(
            inner_frame,
            text=title_text,
            font=title_font,
            text_color=COLORS["text_primary"]
        )
        self.title_label.pack(pady=(0, 3 if self._is_small else 5))

        # Untertitel - responsive Font
        self.subtitle_label = ctk.CTkLabel(
            inner_frame,
            text="Tippe auf eine Option",
            font=self._fonts["body"] if not self._is_small else self._fonts["small"],
            text_color=COLORS["text_secondary"]
        )
        self.subtitle_label.pack(pady=(0, 10 if self._is_small else 15))

        # Karten-Container
        self.cards_frame = ctk.CTkFrame(inner_frame, fg_color="transparent")
        self.cards_frame.pack()

        # Start-Button (groß und auffällig, unter den Karten) - responsive
        btn_font_size = 18 if self._is_small else 24
        btn_width = 220 if self._is_small else 280
        btn_height = 55 if self._is_small else 70
        btn_corner = 28 if self._is_small else 35
        self.start_btn = ctk.CTkButton(
            inner_frame,
            text=f"▶  {self.config.get('ui_texts', {}).get('start', 'START')}",
            font=("Segoe UI", btn_font_size, "bold"),
            width=btn_width,
            height=btn_height,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_muted"],
            corner_radius=btn_corner,
            border_width=2 if self._is_small else 3,
            border_color=COLORS["border"],
            state="disabled",
            command=self._on_start
        )
        self.start_btn.pack(pady=(15 if self._is_small else 25, 0))

        # Loading-Overlay (wird über allem angezeigt während VLC lädt)
        self._loading_overlay = None
        self._loading_visible = False

        # Initiale Karten erstellen
        self._create_template_cards()

    def _create_template_cards(self):
        """Erstellt die Template-Karten im cards_frame"""
        has_custom_template = False
        logger.info("=== Erstelle Template-Karten ===")

        # Responsive Abstand zwischen Karten
        card_padx = 6 if self._is_small else 10

        # USB-Template hat höchste Priorität
        cached = self.app.cached_usb_template
        if cached or (hasattr(self, '_usb_template_path') and self._usb_template_path):
            if cached and cached.get("overlay"):
                preview = cached.get("overlay")
            else:
                preview = self._load_template_preview(self._usb_template_path)

            card = TemplateCard(
                self.cards_frame,
                title="Druckvorlage",
                preview_image=preview,
                on_click=lambda c: self._select_card(c, "usb_template")
            )
            card.pack(side="left", padx=card_padx)
            self.cards["usb_template"] = card
            self._select_card(card, "usb_template")
            has_custom_template = True
            logger.info("✅ USB-Template Karte erstellt")

        usb_active = self.app.cached_usb_template or (hasattr(self, '_usb_template_path') and self._usb_template_path)

        # Template 1
        t1_enabled = self.config.get("template1_enabled", False) and not usb_active
        t1_path = self.config.get("template_paths", {}).get("template1", "")
        t1_resolved = self._resolve_template_path(t1_path) if t1_path else None

        if t1_enabled and t1_resolved:
            preview = self._load_template_preview(t1_resolved)
            card = TemplateCard(
                self.cards_frame,
                title="Template 1",
                preview_image=preview,
                on_click=lambda c: self._select_card(c, "template1")
            )
            card.pack(side="left", padx=card_padx)
            self.cards["template1"] = card
            has_custom_template = True

        # Template 2
        t2_enabled = self.config.get("template2_enabled", False) and not usb_active
        t2_path = self.config.get("template_paths", {}).get("template2", "")
        t2_resolved = self._resolve_template_path(t2_path) if t2_path else None

        if t2_enabled and t2_resolved:
            preview = self._load_template_preview(t2_resolved)
            card = TemplateCard(
                self.cards_frame,
                title="Template 2",
                preview_image=preview,
                on_click=lambda c: self._select_card(c, "template2")
            )
            card.pack(side="left", padx=card_padx)
            self.cards["template2"] = card
            has_custom_template = True

        # Standard 2x2 (wenn keine Custom-Templates)
        if not has_custom_template:
            default_overlay, _ = create_default_template()
            card = TemplateCard(
                self.cards_frame,
                title="Standard 2x2",
                preview_image=default_overlay,
                on_click=lambda c: self._select_card(c, "default_2x2")
            )
            card.pack(side="left", padx=card_padx)
            self.cards["default_2x2"] = card

        # Single-Foto
        if self.config.get("allow_single_mode", True):
            card = TemplateCard(
                self.cards_frame,
                title="Single-Foto",
                is_single=True,
                on_click=lambda c: self._select_card(c, "single")
            )
            card.pack(side="left", padx=card_padx)
            self.cards["single"] = card

        # Fallback
        if not self.cards:
            card = TemplateCard(
                self.cards_frame,
                title="Einzelfoto",
                is_single=True,
                on_click=lambda c: self._select_card(c, "single")
            )
            card.pack(side="left", padx=card_padx)
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

        # VLC-Check: Wenn Video konfiguriert ist und VLC noch nicht warm, blockieren
        if _vlc_available and not is_vlc_warm():
            video_start = self.config.get("video_start", "")
            if video_start and os.path.exists(video_start):
                logger.warning("Start blockiert - VLC noch nicht bereit")
                self._show_loading_overlay()
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

                        # Lokal auf Disk kopieren (überlebt USB-Abzug und Neustart)
                        self._persist_template_to_disk(current_usb_template)
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

        # Loading-Overlay wenn VLC noch nicht warm ist
        if _vlc_available and not is_vlc_warm():
            self._show_loading_overlay()
        else:
            self._hide_loading_overlay()

    def _show_loading_overlay(self):
        """Zeigt Loading-Overlay über dem StartScreen während VLC aufwärmt"""
        if self._loading_visible:
            return

        self._loading_visible = True

        # Overlay-Frame über allem
        self._loading_overlay = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"])
        self._loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Zentrierter Inhalt
        content = ctk.CTkFrame(self._loading_overlay, fg_color="transparent")
        content.place(relx=0.5, rely=0.45, anchor="center")

        # Icon
        ctk.CTkLabel(
            content,
            text="FEXOBOOTH",
            font=("Segoe UI", 28, "bold"),
            text_color=COLORS["primary"]
        ).pack(pady=(0, 20))

        # Lade-Text
        self._loading_label = ctk.CTkLabel(
            content,
            text="Software wird geladen...",
            font=("Segoe UI", 16),
            text_color=COLORS["text_secondary"]
        )
        self._loading_label.pack(pady=(0, 20))

        # Progress-Bar
        self._loading_progress = ctk.CTkProgressBar(
            content,
            width=300,
            height=6,
            fg_color=COLORS["bg_light"],
            progress_color=COLORS["primary"],
            corner_radius=3,
            mode="indeterminate"
        )
        self._loading_progress.pack(pady=(0, 10))
        self._loading_progress.start()

        # Start-Button blockieren
        self.start_btn.configure(state="disabled")

        # Polling: Prüfe alle 500ms ob VLC warm ist
        self._check_vlc_ready()

    def _check_vlc_ready(self):
        """Prüft ob VLC warm ist und entfernt Loading-Overlay"""
        if not self._loading_visible:
            return

        if is_vlc_warm():
            logger.info("VLC-Warmup fertig - Ladebildschirm entfernen")
            self._hide_loading_overlay()
        else:
            self.after(500, self._check_vlc_ready)

    def _hide_loading_overlay(self):
        """Entfernt das Loading-Overlay"""
        if self._loading_overlay:
            try:
                self._loading_overlay.destroy()
            except Exception:
                pass
            self._loading_overlay = None
        self._loading_visible = False

        # Start-Button wieder freigeben (wenn Option gewählt)
        if self.selected_option:
            self._enable_start_button()


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
            logger.debug("Galerie nicht aktiv - Banner verstecken")
            # WICHTIG: Banner komplett verstecken wenn nicht aktiv!
            self.gallery_banner.pack_forget()
            return

        # Prüfen ob gallery_show_qr aktiv (default: True)
        if not self.config.get("gallery_show_qr", True):
            logger.debug("QR-Code Anzeige deaktiviert - Banner verstecken")
            self.gallery_banner.pack_forget()
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
                self.gallery_banner.pack_forget()
                return

            # Banner wieder anzeigen falls es versteckt war
            banner_pady = (0, 5) if self._is_small else (0, 8)
            self.gallery_banner.pack(side="bottom", fill="x", pady=banner_pady)

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
    
    def _persist_template_to_disk(self, usb_template_path: str):
        """Kopiert USB-Template lokal nach .booking_cache/ damit es auch ohne USB verfügbar bleibt"""
        try:
            cache_dir = Path(__file__).parent.parent.parent.parent / ".booking_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / "cached_template.zip"

            shutil.copy2(usb_template_path, cache_path)
            logger.info(f"Template lokal gespeichert: {cache_path}")
        except Exception as e:
            logger.warning(f"Template konnte nicht lokal gecached werden: {e}")

    def _refresh_template_cards(self):
        """Erstellt Template-Karten neu (nach Config-Änderung)"""
        logger.info("=== Refresh Template-Karten ===")

        # Auswahl zurücksetzen
        self.selected_card = None
        self.selected_option = None

        # Alle alten Karten zerstören
        for key, card in self.cards.items():
            try:
                card.destroy()
            except:
                pass
        self.cards = {}

        # Neue Karten erstellen
        self._create_template_cards()

    def on_hide(self):
        """Screen wird verlassen"""
        pass  # Placeholder für eventuelle Cleanup-Aufgaben
