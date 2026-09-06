"""Start-Screen mit moderner Template-Auswahl

Responsive Design - passt sich automatisch an Bildschirmgröße an
"""

import customtkinter as ctk
from typing import TYPE_CHECKING, Optional
from pathlib import Path
from PIL import Image
import os
import shutil
import time

from src.templates.loader import TemplateLoader
from src.templates.default import create_default_template
from src.config.config import find_usb_template
from src.ui.theme import (
    COLORS, FONTS_UI, RADII, SEMIBOLD, bind_pressed, get_sizes, get_fonts,
    is_small_screen, style_primary,
)
from src.utils.logging import get_logger
from src.ui.screens.video import is_vlc_warm, warmup_vlc, _vlc_available
from src.i18n import t

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)

MIN_LOADING_SCREEN_SECONDS = 4.0

_UI_ASSETS = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "ui"


def _load_ui_image(name: str, size) -> Optional[ctk.CTkImage]:
    """Lädt ein Redesign-Asset einmalig als CTkImage (None wenn es fehlt)."""
    try:
        img = Image.open(_UI_ASSETS / name)
        return ctk.CTkImage(light_image=img, dark_image=img, size=size)
    except Exception as e:
        logger.debug(f"UI-Asset '{name}' nicht ladbar: {e}")
        return None


def _is_gallery_enabled(app: "PhotoboothApp") -> bool:
    """Prüft ob Galerie aktiviert ist (nur Config - Booking-Settings fließen via apply_settings_to_config ein)"""
    return app.config.get("gallery_enabled", False)


class TemplateCard(ctk.CTkFrame):
    """Template-Auswahl-Karte — Redesign 2.4.70 (Handoff „Layout-Karte")"""

    _check_badge: Optional[ctk.CTkImage] = None  # geteiltes Asset (einmal laden)

    def __init__(self, parent, title: str, preview_image: Optional[Image.Image] = None,
                 is_single: bool = False, on_click=None, card_width=None, card_height=None,
                 subtitle: Optional[str] = None):
        sizes = get_sizes()
        self._is_small = is_small_screen()

        card_width = card_width or sizes["card_width"]
        card_height = card_height or sizes["card_height"]

        super().__init__(
            parent,
            width=card_width,
            height=card_height,
            fg_color=COLORS["bg_card"],
            corner_radius=RADII["card"],
            border_width=2,
            border_color=COLORS["border"]
        )
        self.grid_propagate(False)
        self.pack_propagate(False)

        self.title = title
        self.is_selected = False
        self.on_click = on_click

        # Kein Hover (Touch-Gerät) — nur Klick
        self.bind("<Button-1>", self._on_click)

        # Innenabstand 22 (ausgewählt 21, Außenmaß bleibt konstant)
        pad = 22 if card_width >= 320 else 14
        self._pad_normal = pad
        self._pad_selected = pad - 1

        # Vorschaufläche (dunkel, r 16)
        preview_height = int(card_height * 0.60)
        preview_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_dark"],
            corner_radius=RADII["tile"],
            height=preview_height
        )
        self.preview_frame = preview_frame
        preview_frame.pack(fill="x", padx=pad, pady=(pad, 0))
        preview_frame.pack_propagate(False)
        preview_frame.bind("<Button-1>", self._on_click)

        # Einzelfoto-Karte bekommt die gebackene Bildträger-Grafik
        if preview_image is None and is_single:
            single_w = min(210, card_width - 2 * pad - 20)
            single_h = int(single_w * 140 / 210)
            single_img = _load_ui_image("card_single.png", (single_w, single_h))
            if single_img is not None:
                preview_label = ctk.CTkLabel(preview_frame, image=single_img, text="")
                preview_label.image = single_img
                preview_label.pack(expand=True)
                preview_label.bind("<Button-1>", self._on_click)
                preview_image_shown = True
            else:
                preview_image_shown = False
        else:
            preview_image_shown = False

        if preview_image:
            preview_copy = preview_image.copy()
            thumb_w = card_width - 2 * pad - 26
            thumb_h = preview_height - 24
            preview_copy.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            self.preview_ctk = ctk.CTkImage(
                light_image=preview_copy,
                size=(preview_copy.width, preview_copy.height)
            )
            preview_label = ctk.CTkLabel(preview_frame, image=self.preview_ctk, text="")
            preview_label.image = self.preview_ctk  # Referenz halten!
            preview_label.pack(expand=True)
            preview_label.bind("<Button-1>", self._on_click)
        elif not preview_image_shown:
            placeholder = ctk.CTkLabel(
                preview_frame,
                text="FOTO" if is_single else "LAYOUT",
                font=(SEMIBOLD, max(15, int(card_height * 0.08))),
                text_color=COLORS["text_muted"]
            )
            placeholder.place(relx=0.5, rely=0.5, anchor="center")
            placeholder.bind("<Button-1>", self._on_click)

        # Titel (h3 26 semibold; kleinere Karten: 22)
        title_font = FONTS_UI["h3"] if card_width >= 320 else (SEMIBOLD, 22)
        title_label = ctk.CTkLabel(
            self, text=title, font=title_font,
            text_color=COLORS["text_primary"]
        )
        self.title_label = title_label
        title_label.pack(pady=(16 if card_width >= 320 else 10, 0))
        title_label.bind("<Button-1>", self._on_click)

        # Untertitel 17 regular
        subtitle = subtitle or ("Einzelbild" if is_single else "Druck-Vorlage")
        subtitle_label = ctk.CTkLabel(
            self, text=subtitle, font=("Segoe UI", 17),
            text_color=COLORS["text_secondary"]
        )
        self.subtitle_label = subtitle_label
        subtitle_label.pack(pady=(2, 0))
        subtitle_label.bind("<Button-1>", self._on_click)

        # Auswahl-Badge oben rechts (Pink-Kreis mit Haken) — per place ein-/ausblenden
        if TemplateCard._check_badge is None:
            TemplateCard._check_badge = _load_ui_image("icon_check_40.png", (40, 40))
        self._badge_label = None
        if TemplateCard._check_badge is not None:
            self._badge_label = ctk.CTkLabel(
                self, image=TemplateCard._check_badge, text="",
                fg_color=COLORS["bg_card"], width=40, height=40
            )
            self._badge_label.bind("<Button-1>", self._on_click)

    def _on_click(self, event):
        if self.on_click:
            self.on_click(self)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        if selected:
            self.configure(border_color=COLORS["primary"], border_width=3)
            self.preview_frame.pack_configure(padx=self._pad_selected,
                                              pady=(self._pad_selected, 0))
            if self._badge_label is not None:
                self._badge_label.place(relx=1.0, x=-16, y=16, anchor="ne")
        else:
            self.configure(border_color=COLORS["border"], border_width=2)
            self.preview_frame.pack_configure(padx=self._pad_normal,
                                              pady=(self._pad_normal, 0))
            if self._badge_label is not None:
                self._badge_label.place_forget()


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
        self._is_small = is_small_screen()
        self._screen_w = self.winfo_screenwidth()
        self._screen_h = self.winfo_screenheight()
        self._is_compact = self._is_small or (self._screen_w <= 1280 and self._screen_h <= 800)

        self._setup_ui()

    def _setup_ui(self):
        """Erstellt die UI — Redesign 2.4.70 (Glow-Hintergrund, Eyebrow, Karten)"""
        self.qr_label: Optional[ctk.CTkLabel] = None

        # Glow-Hintergrund (statisches PNG, Verlauf eingebacken — 0 Laufzeitkosten).
        # ZUERST erzeugen, damit alles Weitere darüber liegt. Die Textzonen des
        # Assets sind bewusst rein #08080C, weil Tk-Labels ihre Fläche in der
        # Hintergrundfarbe malen (keine echte Transparenz).
        bg_img = _load_ui_image("bg_glow_start.png", (self._screen_w, self._screen_h))
        if bg_img is not None:
            bg_label = ctk.CTkLabel(self, image=bg_img, text="", fg_color=COLORS["bg_dark"])
            bg_label.image = bg_img
            bg_label.place(x=0, y=0)

        # (Das Marken-Logo sitzt in der App-Top-Bar, die auf dem Start-Screen
        #  immer sichtbar ist — kein zweites Logo auf dem Screen.)

        # Galerie-Banner wird bei Bedarf rechts eingeblendet.
        # Es reserviert keinen Layout-Platz, damit die Template-Auswahl frei bleibt.
        self.gallery_banner = ctk.CTkFrame(self, fg_color="transparent")
        self.gallery_banner.place_forget()

        # Start-Button DIREKT ueber Galerie-Banner packen (nicht im inner_frame!)
        # So kann er nicht vom zentrierten Inhalt verdeckt werden wenn die
        # Galerie aktiv ist und der inner_frame zu gross wird.
        self.start_btn = ctk.CTkButton(
            self,
            text=t(self.config, "common.start"),
            state="disabled",
            command=self._on_start,
            **style_primary(width=480, height=96, font_key="button_xl")
        )
        self._disable_start_button()
        bind_pressed(self.start_btn, COLORS["primary"], COLORS["primary_pressed"])
        self.start_btn.pack(side="bottom", pady=(8, 16))

        # Zentrierter Hauptcontainer (nimmt restlichen Platz zwischen Top und Button)
        self.center_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.center_frame.pack(expand=True, fill="both")

        # Innerer Container für vertikale Zentrierung
        self.inner_frame = ctk.CTkFrame(self.center_frame, fg_color="transparent")
        self._position_main_content()

        # Eyebrow „WILLKOMMEN" (Versalien, Pink)
        self.eyebrow_label = ctk.CTkLabel(
            self.inner_frame,
            text=t(self.config, "start.eyebrow").upper(),
            font=FONTS_UI["label"],
            text_color=COLORS["primary"]
        )
        self.eyebrow_label.pack(pady=(0, 8))

        # Titel (Display 44 bold)
        self.title_label = ctk.CTkLabel(
            self.inner_frame,
            text=t(self.config, "start.choose_mode").replace("!", ""),
            font=FONTS_UI["display"] if not self._is_compact else ("Segoe UI", 38, "bold"),
            text_color=COLORS["text_primary"]
        )
        self.title_label.pack(pady=(0, 8))

        # Untertitel (Body 20)
        self.subtitle_label = ctk.CTkLabel(
            self.inner_frame,
            text=t(self.config, "start.tap_option"),
            font=FONTS_UI["body"],
            text_color=COLORS["text_secondary"]
        )
        self.subtitle_label.pack(pady=(0, 24 if self._is_compact else 32))

        # Karten-Container
        self.cards_frame = ctk.CTkFrame(self.inner_frame, fg_color="transparent")
        self.cards_frame.pack()

        # Loading-Overlay (wird über allem angezeigt während VLC lädt)
        self._loading_overlay = None
        self._loading_progress = None
        self._loading_anim_after_id = None
        self._loading_visible = False
        self._loading_shown_at = 0.0
        self._vlc_warmup_after_id = None

        # Initiale Karten erstellen
        self._create_template_cards()

    def _position_main_content(self):
        """Positioniert die Auswahl so, dass rechts Platz fuer den QR-Code bleibt."""
        if not hasattr(self, "inner_frame"):
            return

        # Mit QR-Panel (288 px rechts) rückt die Auswahl in die Mitte der
        # verbleibenden Fläche (x 80–880), ohne QR in die Bildschirmmitte.
        qr_active = self._is_gallery_banner_enabled()
        relx = 0.37 if qr_active else 0.5
        self.inner_frame.place(relx=relx, rely=0.5, anchor="center")

    def _active_template_is_app_upload(self) -> bool:
        """App-Uploads sollen das alte USB-Template ersetzen, nicht daneben anzeigen."""
        try:
            if getattr(self.app, "_app_uploaded_template_active", False):
                return True
            manager = getattr(self.app, "booking_manager", None)
            if not manager:
                return False
            if hasattr(manager, "is_template_cache_from_app_upload"):
                return bool(manager.is_template_cache_from_app_upload())
            return bool(manager.is_cache_from_app_upload())
        except Exception as e:
            logger.debug(f"Cache-Quelle konnte nicht geprüft werden: {e}")
            return False

    def _ensure_app_template_active(self) -> bool:
        """Laedt das App-Template erneut aus dem lokalen Cache, falls USB es verdraengt hat."""
        if not self._active_template_is_app_upload():
            return False

        manager = getattr(self.app, "booking_manager", None)
        cached_path = getattr(manager, "cached_template_path", None) if manager else None
        if not cached_path:
            return False

        expected_path = str(cached_path)
        cached_card = self.app.cached_usb_template or {}
        current_path = cached_card.get("path")
        cache_fingerprint = manager.cached_template_fingerprint() if manager else ""
        loaded_fingerprint = cached_card.get("fingerprint", "")
        cache_changed = bool(cache_fingerprint and loaded_fingerprint != cache_fingerprint)
        if current_path != expected_path or cache_changed:
            reason = "Cache-Inhalt geändert" if cache_changed else "USB-Stick bleibt nur Referenz"
            logger.info(f"📲 App-Template erneut aktiviert; {reason}")
            TemplateLoader.clear_cache()
            self.app._restore_cached_template(force=True, use_cache=False)

        if self.app.cached_usb_template:
            self.app.cached_usb_template["source"] = "app"
            self.app.cached_usb_template["fingerprint"] = manager.cached_template_fingerprint()
            self.app._user_template_override = True
            self.app._app_uploaded_template_active = True
            self._usb_template_path = self.app.cached_usb_template.get("path")
            return True

        return False

    def _log_start_template_state(self, label: str):
        try:
            cached = self.app.cached_usb_template or {}
            usb = self.app._usb_stick_template or {}
            manager = getattr(self.app, "booking_manager", None)
            fp = manager.template_file_fingerprint if manager else (lambda path: "")
            logger.info(
                "📲 TEMPLATE DEBUG START %s | app_active=%s user_override=%s "
                "cached_card=%s path_fp=%s loaded_fp=%s source=%s | "
                "usb_ref=%s path_fp=%s loaded_fp=%s | cache_file=%s fp=%s",
                label,
                getattr(self.app, "_app_uploaded_template_active", False),
                getattr(self.app, "_user_template_override", False),
                cached.get("path", "-"),
                fp(cached.get("path", "")) if cached.get("path") else "",
                cached.get("fingerprint", ""),
                cached.get("source", "-"),
                usb.get("path", "-"),
                fp(usb.get("path", "")) if usb.get("path") else "",
                usb.get("fingerprint", ""),
                str(manager.cached_template_path) if manager and manager.cached_template_path else "-",
                manager.cached_template_fingerprint() if manager else "",
            )
        except Exception as e:
            logger.debug(f"Template-Debug StartScreen fehlgeschlagen: {e}")

    def _count_expected_cards(self):
        """Zählt die erwartete Anzahl Template-Karten für responsive Größenanpassung"""
        count = 0
        has_custom = False

        # Aktives Template (USB oder User-Override)
        if self.app.cached_usb_template:
            count += 1
            has_custom = True

        # USB-Stick Template als extra Karte nur bei manueller Auswahl, nicht bei App-Korrektur.
        usb_stick = self.app._usb_stick_template
        cached_path = self.app.cached_usb_template.get("path") if self.app.cached_usb_template else None
        if (self.app._user_template_override and not self._active_template_is_app_upload()
                and usb_stick and usb_stick.get("path") != cached_path):
            count += 1

        if not has_custom:
            count += 1  # default_2x2

        if self.config.get("allow_single_mode", True):
            count += 1

        return max(count, 1)

    def _create_template_cards(self):
        """Erstellt die Template-Karten im cards_frame"""
        has_custom_template = False
        logger.info("=== Erstelle Template-Karten ===")

        # Kartengrößen nach Anzahl (Redesign 2.4.70: Karte 380×330, Gap 40;
        # bei 3 Karten schmaler, damit die Reihe neben dem QR-Panel passt)
        card_count = self._count_expected_cards()
        qr_active = self._is_gallery_banner_enabled()

        # 2.4.71: etwas kompakter, damit links Luft bleibt und rechts nie
        # etwas unter das QR-Panel rutscht (Box-Test 06.09.: 380er Karten
        # klebten am Rand). Reihe bei 2 Karten: 2×360 + 80 Gap = 800 px,
        # zentriert im Bereich links vom Panel (x 0–944).
        if card_count <= 2:
            card_w, card_h = 360, 316
        else:
            card_w, card_h = (240, 226) if qr_active else (290, 264)

        # Karten-Gap 40 (padx wirkt je Seite)
        card_padx = 20 if card_count <= 2 else 12

        # Aktives Template (vom User gewählt oder USB auto-aktiviert)
        cached = self.app.cached_usb_template
        if cached:
            self._log_start_template_state("create-card")
            if cached.get("overlay"):
                preview = cached.get("overlay")
            else:
                preview = self._load_template_preview(cached.get("path", ""))

            # Titel: Immer "Wunsch-Template" anzeigen (nicht den Dateinamen)
            display_name = t(self.config, "start.wish_template")

            card = TemplateCard(
                self.cards_frame,
                title=display_name,
                preview_image=preview,
                on_click=lambda c: self._select_card(c, "usb_template"),
                card_width=card_w, card_height=card_h,
                subtitle=t(self.config, "start.print_template")
            )
            card.pack(side="left", padx=card_padx)
            self.cards["usb_template"] = card
            self._select_card(card, "usb_template")
            has_custom_template = True
            logger.info(f"✅ Aktives Template Karte: {display_name}")

        # USB-Stick Template als EXTRA Karte wenn User ein anderes gewählt hat
        usb_stick = self.app._usb_stick_template
        if (usb_stick and self.app._user_template_override
                and not self._active_template_is_app_upload()
                and usb_stick.get("path") != (cached.get("path") if cached else None)):
            usb_name = usb_stick.get("name", "USB").replace(".zip", "")
            if usb_stick.get("overlay"):
                usb_preview = usb_stick.get("overlay")
            else:
                usb_preview = self._load_template_preview(usb_stick.get("path", ""))

            card = TemplateCard(
                self.cards_frame,
                title=f"USB: {usb_name}" if len(usb_name) <= 12 else t(self.config, "start.usb_template"),
                preview_image=usb_preview,
                on_click=lambda c: self._select_card(c, "usb_stick_original"),
                card_width=card_w, card_height=card_h,
                subtitle=t(self.config, "start.print_template")
            )
            card.pack(side="left", padx=card_padx)
            self.cards["usb_stick_original"] = card
            has_custom_template = True
            logger.info(f"✅ USB-Stick Template Karte: {usb_name}")

        # Standard 2x2 (wenn keine Custom-Templates)
        if not has_custom_template:
            default_overlay, _ = create_default_template()
            card = TemplateCard(
                self.cards_frame,
                title=t(self.config, "start.standard_2x2"),
                preview_image=default_overlay,
                on_click=lambda c: self._select_card(c, "default_2x2"),
                card_width=card_w, card_height=card_h,
                subtitle=t(self.config, "start.print_template")
            )
            card.pack(side="left", padx=card_padx)
            self.cards["default_2x2"] = card

        # Single-Foto
        if self.config.get("allow_single_mode", True):
            card = TemplateCard(
                self.cards_frame,
                title=t(self.config, "start.single_photo"),
                is_single=True,
                on_click=lambda c: self._select_card(c, "single"),
                card_width=card_w, card_height=card_h,
                subtitle=t(self.config, "start.single_subtitle")
            )
            card.pack(side="left", padx=card_padx)
            self.cards["single"] = card

        # Fallback
        if not self.cards:
            card = TemplateCard(
                self.cards_frame,
                title=t(self.config, "start.one_photo"),
                is_single=True,
                on_click=lambda c: self._select_card(c, "single"),
                card_width=card_w, card_height=card_h,
                subtitle=t(self.config, "start.single_subtitle")
            )
            card.pack(side="left", padx=card_padx)
            self.cards["single"] = card

        # Auto-Select: Erste Karte vorauswählen wenn noch nichts gewählt
        # (USB-Template wird oben schon vorausgewählt)
        if not self.selected_card and self.cards:
            first_key = next(iter(self.cards))
            first_card = self.cards[first_key]
            self._select_card(first_card, first_key)
            logger.info(f"Auto-Select: '{first_key}' (keine USB-Vorlage)")

        # Header-Text anpassen wenn nur 1 Karte (nichts zu wählen)
        if len(self.cards) <= 1:
            self.title_label.configure(text=t(self.config, "start.print_format"))
            self.subtitle_label.configure(text=t(self.config, "start.tap_to_start"))
        else:
            default_title = t(self.config, "start.choose_mode").replace("!", "")
            self.title_label.configure(text=default_title)
            self.subtitle_label.configure(text=t(self.config, "start.tap_option"))

        logger.info(f"Erstellte Karten: {list(self.cards.keys())}")

    def _is_gallery_banner_enabled(self) -> bool:
        return _is_gallery_enabled(self.app) and self.config.get("gallery_show_qr", True)
    
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
            
            # Für ZIP: Erst preview.png suchen (schnelles Vorschaubild)
            import zipfile
            if resolved.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(resolved, "r") as zf:
                        for name in zf.namelist():
                            if name.lower().endswith("preview.png"):
                                import io
                                with zf.open(name) as f:
                                    preview = Image.open(io.BytesIO(f.read())).convert("RGBA")
                                    logger.debug(f"Preview aus ZIP geladen: {preview.size}")
                                    return preview
                except Exception:
                    pass

            # Fallback: Overlay aus Loader
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
        """Aktiviert den Start-Button (grau → Pink)"""
        self.start_btn.configure(
            state="normal",
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary"],
            text_color=COLORS["text_primary"]
        )

    def _disable_start_button(self):
        """Deaktiviert den Start-Button (Pink → grau)"""
        self.start_btn.configure(
            state="disabled",
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_light"],
            text_color=COLORS["text_muted"]
        )
    
    def _on_start(self):
        """Start gedrückt"""
        if not self.selected_option:
            return

        # VLC-Check: Wenn Video konfiguriert ist und VLC noch nicht warm, blockieren
        # Sonst friert das erste Video ~77s ein auf schwacher Hardware
        if not self.app.stress_test_active and _vlc_available and not is_vlc_warm():
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
            if cached and cached.get("boxes"):
                logger.info(f"Verwende gecachtes USB-Template: {cached.get('name')}")
                self.app.template_path = cached.get("path")
                self.app.template_boxes = cached.get("boxes")
                self.app.overlay_image = cached.get("overlay")  # kann None sein (kein Overlay-Frame)
                logger.info(f"USB-Template aus Cache: {len(cached.get('boxes'))} Foto-Slots, Overlay: {cached.get('overlay') is not None}")
            elif hasattr(self, '_usb_template_path') and self._usb_template_path:
                # Fallback: Direkt laden wenn Cache leer
                logger.info(f"Lade USB-Template direkt: {self._usb_template_path}")
                overlay, boxes = TemplateLoader.load(self._usb_template_path)
                if boxes:
                    self.app.template_path = self._usb_template_path
                    self.app.template_boxes = boxes
                    self.app.overlay_image = overlay
                    # Auch cachen für nächstes Mal
                    self.app.cached_usb_template = {
                        "path": self._usb_template_path,
                        "name": os.path.basename(self._usb_template_path),
                        "overlay": overlay,
                        "boxes": boxes,
                        "fingerprint": self.app.booking_manager.template_file_fingerprint(self._usb_template_path),
                        "source": "usb",
                    }
                    logger.info(f"USB-Template geladen und gecached: {len(boxes)} Foto-Slots")
                else:
                    logger.error("USB-Template konnte nicht geladen werden!")
                    return
            else:
                logger.error("Kein USB-Template verfügbar (weder Cache noch USB)!")
                return

        elif self.selected_option == "usb_stick_original":
            # User wählt zurück zum USB-Stick Template
            usb_stick = self.app._usb_stick_template
            if usb_stick and usb_stick.get("boxes"):
                self.app.template_path = usb_stick.get("path")
                self.app.template_boxes = usb_stick.get("boxes")
                self.app.overlay_image = usb_stick.get("overlay")
                # USB-Override zurücksetzen
                self.app.cached_usb_template = usb_stick
                self.app._user_template_override = False
                self.app._app_uploaded_template_active = False
                logger.info(f"Zurück zum USB-Stick Template: {usb_stick.get('name')}")
            else:
                logger.error("USB-Stick Template nicht verfügbar!")
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
        self._log_start_template_state("on_show-enter")

        # Config könnte sich geändert haben (Admin-Dialog)
        self.config = self.app.config

        # 2.4.31: Nach dem Schliessen des Admin-Dialogs kann on_show auf einem
        # bereits zerstoerten StartScreen landen. Frueher warf das
        #   _tkinter.TclError: invalid command name ".!ctkframe3.!startscreen...."
        # aus einem Tk-Callback heraus (nachgewiesen im absturz.log von Box 044,
        # 19.08. 08:43:54). Der Fehler-Handler faengt das inzwischen ab, aber der
        # sauberere Weg ist: gar nicht erst auf toten Widgets arbeiten.
        try:
            if not self.start_btn.winfo_exists():
                logger.debug("StartScreen.on_show: Screen bereits zerstoert - uebersprungen")
                return
        except Exception:
            return

        self.start_btn.configure(text=t(self.config, "common.start"))
        self._position_main_content()
        app_template_active = self._ensure_app_template_active()

        if _vlc_available and not is_vlc_warm():
            self._show_loading_overlay()
            self._schedule_vlc_warmup()

        # === USB-Stick Template erkennen (getrennt vom aktiven Template) ===
        real_usb = find_usb_template(include_cache=False)  # Nur echte USB-Sticks

        if real_usb:
            template_name = os.path.basename(real_usb)
            usb_cached = self.app._usb_stick_template

            if not usb_cached or usb_cached.get("name") != template_name:
                # Neues USB-Template — laden und separat speichern
                logger.info(f"=== USB-Stick Template gefunden: {real_usb} ===")
                try:
                    overlay, boxes = TemplateLoader.load(real_usb)
                    if boxes:
                        self.app._usb_stick_template = {
                            "path": real_usb,
                            "name": template_name,
                            "overlay": overlay,
                            "boxes": boxes,
                            "fingerprint": self.app.booking_manager.template_file_fingerprint(real_usb),
                            "source": "usb",
                        }
                        logger.info(f"USB-Stick Template geladen: {template_name} ({len(boxes)} Slots)")
                        if not app_template_active and not self.app._user_template_override:
                            self._persist_template_to_disk(real_usb)
                        else:
                            logger.info("USB-Template nicht in Cache kopiert: App-Template hat Vorrang")
                except Exception as e:
                    logger.error(f"USB-Template laden fehlgeschlagen: {e}")
            else:
                logger.info(f"USB-Stick Template unverändert: {template_name}")

            # Nur auto-aktivieren wenn User NICHT explizit ein anderes gewählt hat
            if not app_template_active and not self.app._user_template_override:
                self.app.cached_usb_template = self.app._usb_stick_template
                logger.info(f"USB-Template als aktives Template gesetzt (kein User-Override)")
            else:
                logger.info(f"User-Override aktiv — USB-Template nicht auto-aktiviert")
        else:
            # Kein USB-Stick — USB-Stick-Referenz behalten falls vorher geladen
            if not self.app._usb_stick_template:
                # Booking-Cache als Fallback für USB-Stick-Template
                cache_template = find_usb_template(include_cache=True)
                if cache_template:
                    try:
                        overlay, boxes = TemplateLoader.load(cache_template)
                        if boxes:
                            self.app._usb_stick_template = {
                                "path": cache_template,
                                "name": os.path.basename(cache_template),
                                "overlay": overlay,
                                "boxes": boxes,
                                "fingerprint": self.app.booking_manager.template_file_fingerprint(cache_template),
                                "source": "cache",
                            }
                    except Exception as e:
                        logger.error(f"Cache-Template laden fehlgeschlagen: {e}")

        # Aktives Template bestimmen
        self._ensure_app_template_active()
        self._log_start_template_state("after-usb-decision")

        if self.app.cached_usb_template:
            self._usb_template_path = self.app.cached_usb_template.get("path")
        elif self.app._usb_stick_template and not self.app._user_template_override:
            self.app.cached_usb_template = self.app._usb_stick_template
            self._usb_template_path = self.app._usb_stick_template.get("path")
        else:
            self._usb_template_path = None

        # Alte Karten entfernen und neu erstellen (setzt auch selected_card = None)
        self._refresh_template_cards()
        self._log_start_template_state("after-refresh")

        # Start-Button deaktivieren bis eine Auswahl getroffen wird
        # (wird in _create_template_cards aktiviert wenn USB-Template vorselektiert)
        if not self.selected_option:
            self._disable_start_button()
        else:
            self._enable_start_button()

        # QR-Code für Galerie anzeigen/ausblenden
        self._update_qr_code()

        # Loading-Overlay sichtbar halten/entfernen nachdem alle Karten aktualisiert sind.
        if _vlc_available and not is_vlc_warm():
            if self._loading_overlay is not None:
                self._loading_overlay.lift()
        else:
            self._hide_loading_overlay()

    def _show_loading_overlay(self):
        """Zeigt Loading-Overlay über dem StartScreen während VLC aufwärmt"""
        if self._loading_visible:
            return

        self._loading_visible = True
        self._loading_shown_at = time.monotonic()

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
            font=("Segoe UI", 38, "bold"),
            text_color=COLORS["primary"]
        ).pack(pady=(0, 20))

        # Persönliche Willkommensnachricht wenn Kundenname vorhanden
        first_name = ""
        if self.app.booking_manager and self.app.booking_manager.is_loaded:
            settings = self.app.booking_manager.settings
            first_name = (settings.shipping_first_name or "").strip()
            if not first_name and settings.customer_name:
                first_name = settings.customer_name.strip().split()[0]

        if first_name:
            ctk.CTkLabel(
                content,
                text=t(self.config, "start.greeting_named", name=first_name),
                font=("Segoe UI", 30, "bold"),
                text_color=COLORS["text_primary"]
            ).pack(pady=(0, 5))

            ctk.CTkLabel(
                content,
                text=t(self.config, "start.greeting_thanks"),
                font=("Segoe UI", 20),
                text_color=COLORS["text_primary"]
            ).pack(pady=(0, 15))

            ctk.CTkLabel(
                content,
                text=t(self.config, "start.greeting_warmup"),
                font=("Segoe UI", 18),
                text_color=COLORS["text_secondary"],
                justify="center"
            ).pack(pady=(0, 10))

            ctk.CTkLabel(
                content,
                text=t(self.config, "start.loading_wait"),
                font=("Segoe UI", 16),
                text_color=COLORS["text_secondary"],
                justify="center"
            ).pack(pady=(0, 25))
        else:
            # Lade-Text (ohne Kundenname)
            self._loading_label = ctk.CTkLabel(
                content,
                text=t(self.config, "start.loading_software"),
                font=("Segoe UI", 22),
                text_color=COLORS["text_primary"]
            )
            self._loading_label.pack(pady=(0, 5))

            ctk.CTkLabel(
                content,
                text=t(self.config, "start.loading_wait"),
                font=("Segoe UI", 16),
                text_color=COLORS["text_secondary"]
            ).pack(pady=(0, 20))

        # 5-Segment-Anzeige (Redesign 2.4.70): 1 Schritt pro Sekunde statt
        # 11-fps-Ping-Pong — signalisiert "die Box arbeitet" bei minimaler
        # Last (1 configure-Aufruf/s, harte Grenze: keine Animationen).
        segments_frame = ctk.CTkFrame(content, fg_color="transparent")
        segments_frame.pack(pady=(0, 10))
        self._loading_segments = []
        for _ in range(5):
            seg = ctk.CTkFrame(
                segments_frame, width=56, height=8,
                fg_color=COLORS["bg_light"], corner_radius=4
            )
            seg.pack(side="left", padx=4)
            self._loading_segments.append(seg)
        self._loading_progress = segments_frame  # Marker: Overlay hat Anzeige
        self._loading_segment_pos = 0
        self._loading_anim_after_id = None
        self._animate_loading_bar()

        # Start-Button blockieren
        self.start_btn.configure(state="disabled")

        # Polling: Prüfe alle 500ms ob VLC warm ist
        self._check_vlc_ready()

        try:
            self._loading_overlay.lift()
            self.update_idletasks()
        except Exception:
            pass

    def _animate_loading_bar(self):
        """Schaltet 1x pro Sekunde das nächste Segment auf Pink (Wanderlicht)."""
        if not self._loading_visible or self._loading_progress is None:
            return
        try:
            pos = self._loading_segment_pos % len(self._loading_segments)
            prev = (pos - 1) % len(self._loading_segments)
            self._loading_segments[prev].configure(fg_color=COLORS["bg_light"])
            self._loading_segments[pos].configure(fg_color=COLORS["primary"])
            self._loading_segment_pos += 1
        except Exception:
            return
        self._loading_anim_after_id = self.after(1000, self._animate_loading_bar)

    def _schedule_vlc_warmup(self):
        """Startet den VLC-Warmup erst nach dem ersten sichtbaren UI-Frame."""
        if self._vlc_warmup_after_id is not None:
            return

        self._vlc_warmup_after_id = self.after(250, self._start_vlc_warmup)

    def _start_vlc_warmup(self):
        self._vlc_warmup_after_id = None
        warmup_vlc()

    def _check_vlc_ready(self):
        """Prüft ob VLC warm ist und entfernt Loading-Overlay"""
        if not self._loading_visible:
            return

        if is_vlc_warm():
            elapsed = time.monotonic() - self._loading_shown_at
            if elapsed < MIN_LOADING_SCREEN_SECONDS:
                remaining_ms = int((MIN_LOADING_SCREEN_SECONDS - elapsed) * 1000)
                self.after(max(100, remaining_ms), self._check_vlc_ready)
                return

            logger.info("VLC-Warmup fertig - Ladebildschirm entfernen")
            self._hide_loading_overlay()
        else:
            self.after(500, self._check_vlc_ready)

    def _hide_loading_overlay(self):
        """Entfernt das Loading-Overlay"""
        # Eigene Balken-Animation stoppen
        self._loading_visible = False
        if getattr(self, "_loading_anim_after_id", None) is not None:
            try:
                self.after_cancel(self._loading_anim_after_id)
            except Exception:
                pass
            self._loading_anim_after_id = None
        self._loading_progress = None

        if self._loading_overlay:
            try:
                self._loading_overlay.destroy()
            except Exception:
                pass
            self._loading_overlay = None
        self._loading_shown_at = 0.0

        if self._vlc_warmup_after_id is not None:
            try:
                self.after_cancel(self._vlc_warmup_after_id)
            except Exception:
                pass
            self._vlc_warmup_after_id = None

        # Start-Button wieder freigeben (wenn Option gewählt)
        if self.selected_option:
            self._enable_start_button()


    def _hide_gallery_banner(self):
        """Versteckt das Galerie-Banner unabhaengig vom aktuellen Geometry-Manager."""
        try:
            self.gallery_banner.place_forget()
        except Exception:
            pass
        try:
            self.gallery_banner.pack_forget()
        except Exception:
            pass

    def _update_qr_code(self):
        """Zeigt das Galerie-Banner unten rechts."""
        # Alte Elemente entfernen
        if self.qr_label:
            self.qr_label.destroy()
            self.qr_label = None

        for widget in self.gallery_banner.winfo_children():
            widget.destroy()

        # Prüfen ob Galerie aktiv
        if not _is_gallery_enabled(self.app):
            logger.debug("Galerie nicht aktiv - Banner verstecken")
            self._hide_gallery_banner()
            return

        # Prüfen ob gallery_show_qr aktiv (default: True)
        if not self.config.get("gallery_show_qr", True):
            logger.debug("QR-Code Anzeige deaktiviert - Banner verstecken")
            self._hide_gallery_banner()
            return

        try:
            from src.gallery import (
                generate_qr_code,
                get_app_display_code,
                get_app_pairing_url,
                get_gallery_url,
                set_gallery_app_context,
            )

            # URL und WLAN-Daten holen
            gallery_config = self.config.get("gallery", {})
            port = gallery_config.get("port", self.config.get("gallery_port", 8080))
            if hasattr(self.app, "_get_gallery_app_context"):
                set_gallery_app_context(self.app._get_gallery_app_context())
            url = get_gallery_url(port)
            qr_payload = get_app_pairing_url(port)
            event_code = get_app_display_code()
            ssid = gallery_config.get("hotspot_ssid", "fexobox-gallery")
            password = gallery_config.get("hotspot_password", "fotobox123")

            # App-Pairing-QR generieren. Der Payload enthaelt API-URL, Box/Event
            # und Pairing-Token fuer die spaetere Smartphone-App.
            qr_size = 200
            qr_img = generate_qr_code(qr_payload, size=qr_size)
            if not qr_img:
                logger.warning("QR-Code konnte nicht generiert werden")
                self._hide_gallery_banner()
                return

            # QR-Panel (Redesign 2.4.70): 288 breit, dunkles Panel, weisser
            # QR-Träger, EVENT-CODE in Pink, WLAN-Zeilen unter Trennlinie.
            panel = ctk.CTkFrame(
                self.gallery_banner,
                width=288,
                fg_color=COLORS["bg_medium"],
                corner_radius=RADII["card"],
                border_width=1,
                border_color=COLORS["border"]
            )
            panel.pack()

            content = ctk.CTkFrame(panel, fg_color="transparent")
            content.pack(padx=24, pady=24)

            ctk.CTkLabel(
                content,
                text=t(self.config, "gallery.banner_title"),
                font=(SEMIBOLD, 22),
                text_color=COLORS["text_primary"]
            ).pack()

            ctk.CTkLabel(
                content,
                text=t(self.config, "gallery.banner_sub"),
                font=FONTS_UI["small"],
                text_color=COLORS["text_secondary"],
                wraplength=224,
                justify="center"
            ).pack(pady=(6, 0))

            # Weisser QR-Träger 224×224, r 16, QR 200×200
            qr_container = ctk.CTkFrame(
                content, width=224, height=224,
                fg_color=COLORS["white"], corner_radius=RADII["tile"]
            )
            qr_container.pack(pady=(18, 0))
            qr_container.pack_propagate(False)

            self.qr_ctk_image = ctk.CTkImage(light_image=qr_img, size=(qr_size, qr_size))
            self.qr_label = ctk.CTkLabel(
                qr_container,
                image=self.qr_ctk_image,
                text="",
                fg_color=COLORS["white"]
            )
            self.qr_label.place(relx=0.5, rely=0.5, anchor="center")

            if event_code:
                ctk.CTkLabel(
                    content,
                    text="EVENT-CODE",
                    font=(SEMIBOLD, 14),
                    text_color=COLORS["text_secondary"]
                ).pack(pady=(18, 0))
                ctk.CTkLabel(
                    content,
                    text=str(event_code),
                    font=("Segoe UI", 30, "bold"),
                    text_color=COLORS["primary"]
                ).pack()

            # Trennlinie
            ctk.CTkFrame(
                content, height=1, fg_color=COLORS["border"]
            ).pack(fill="x", pady=16)

            ctk.CTkLabel(
                content,
                text=t(self.config, "gallery.banner_wifi", ssid=ssid),
                font=FONTS_UI["small_semibold"],
                text_color=COLORS["text_primary"],
                wraplength=224,
                justify="center"
            ).pack()

            ctk.CTkLabel(
                content,
                text=t(self.config, "gallery.banner_password", password=password),
                font=FONTS_UI["small"],
                text_color=COLORS["text_secondary"],
                wraplength=224,
                justify="center"
            ).pack(pady=(4, 0))

            # Rechts, vertikal mittig im Bereich über dem Start-Button
            self.gallery_banner.place(relx=1.0, rely=0.44, x=-48, anchor="e")
            self.gallery_banner.lift()

            logger.info(f"✅ App-Galerie-QR angezeigt: {url}")

        except ImportError as e:
            logger.warning(f"Galerie-Modul nicht verfügbar: {e}")
        except Exception as e:
            logger.error(f"Galerie-Banner Fehler: {e}")
    
    def _persist_template_to_disk(self, usb_template_path: str):
        """Kopiert USB-Template lokal nach .booking_cache/ damit es auch ohne USB verfügbar bleibt"""
        try:
            from src.storage.booking import TEMPLATE_CACHE_FILE
            cache_path = TEMPLATE_CACHE_FILE
            cache_path.parent.mkdir(parents=True, exist_ok=True)

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
