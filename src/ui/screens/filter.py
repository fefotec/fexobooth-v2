"""Filter-Auswahl Screen — Redesign 2.4.70

8 große Foto-Kacheln im 4×2-Grid, jede zeigt das ERSTE Gast-Foto mit dem
jeweiligen Filter. Die frühere separate Groß-Vorschau entfällt (Handoff:
„Kacheln sind groß genug"). 2.4.71: Auch das nachträgliche Ersetzen durch
Collagen-Vorschauen ist raus (Christian, Box-Test 06.09.): das Nachladen
dauerte zu lange und die 8 Collagen-Renders (~10 s CPU) liefen genau dann,
wenn der Gast wählt. Jetzt: 8 schnelle Filter aufs erste Foto (<1 s gesamt),
fertig. Das finale Druckbild rendert weiterhin aus den Originalen (final.py).
"""

import customtkinter as ctk
from PIL import Image, ImageDraw
from typing import TYPE_CHECKING, Optional, Dict
import threading
import time

from src.filters import FilterManager, AVAILABLE_FILTERS
from src.ui.theme import (
    COLORS, FONTS_UI, RADII, SEMIBOLD, bind_pressed, style_primary,
    style_tertiary,
)
from src.utils.logging import get_logger
from src.i18n import t

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)

FILTER_INACTIVITY_SECONDS = 15.0

# Kachel-Maße (Handoff „Filter-Kachel"): 262×224, Thumb 238×158 r 12
TILE_W, TILE_H = 262, 224
THUMB_W, THUMB_H = 238, 158


class FilterCard(ctk.CTkFrame):
    """Filter-Kachel — zeigt das Gast-Foto mit dem jeweiligen Filter."""

    _check_badge: Optional[ctk.CTkImage] = None

    def __init__(self, parent, filter_key: str, filter_name: str,
                 on_click=None, card_width: int = TILE_W, card_height: int = TILE_H,
                 compact: Optional[bool] = None):
        self._card_width = card_width
        self._card_height = card_height
        self._thumb_width = max(120, card_width - 24)
        self._thumb_height = max(80, card_height - 66)
        self._is_small = bool(compact)

        super().__init__(
            parent,
            width=card_width,
            height=card_height,
            fg_color=COLORS["bg_card"],
            corner_radius=RADII["tile"],
            border_width=2,
            border_color=COLORS["border"]
        )
        self.pack_propagate(False)

        self.filter_key = filter_key
        self.filter_name = filter_name
        self.on_click = on_click
        self.is_selected = False

        # Innen 12 (ausgewählt 11 — Außenmaß bleibt konstant)
        self.inner = ctk.CTkFrame(self, fg_color="transparent")
        self.inner.pack(expand=True, fill="both", padx=12, pady=12)

        # Vorschau-Fläche
        self.preview_label = ctk.CTkLabel(
            self.inner,
            text="",
            fg_color=COLORS["bg_dark"],
            corner_radius=RADII["thumb"]
        )
        self.preview_label.pack()

        # Filter-Name (18 semibold, ohne Emoji)
        self.name_label = ctk.CTkLabel(
            self.inner,
            text=filter_name,
            font=FONTS_UI["label"],
            text_color=COLORS["text_primary"]
        )
        self.name_label.pack(pady=(10, 0))

        # Auswahl-Badge oben rechts
        if FilterCard._check_badge is None:
            FilterCard._check_badge = _load_check_badge()
        self._badge_label = None
        if FilterCard._check_badge is not None:
            self._badge_label = ctk.CTkLabel(
                self, image=FilterCard._check_badge, text="",
                fg_color=COLORS["bg_card"], width=36, height=36
            )
            self._badge_label.bind("<Button-1>", self._on_click)

        # Klick-Bindings (kein Hover — Touch-Gerät)
        for widget in [self, self.inner, self.preview_label, self.name_label]:
            widget.bind("<Button-1>", self._on_click)

    def set_preview(self, image: Image.Image):
        """Setzt das Vorschaubild (auf Thumb-Maß gefittet, Ecken per PIL-Maske)."""
        thumb = image.copy()
        thumb.thumbnail((self._thumb_width, self._thumb_height), Image.Resampling.BILINEAR)
        thumb = self._round_corners(thumb, RADII["thumb"])

        self.preview_ctk = ctk.CTkImage(light_image=thumb, size=thumb.size)
        self.preview_label.configure(image=self.preview_ctk)

    def _round_corners(self, img: Image.Image, radius: int) -> Image.Image:
        """Fügt abgerundete Ecken hinzu"""
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        mask = Image.new('L', img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([(0, 0), img.size], radius=radius, fill=255)
        img.putalpha(mask)
        return img

    def _on_click(self, event):
        if self.on_click:
            self.on_click(self)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        if selected:
            self.configure(border_color=COLORS["primary"], border_width=3)
            self.inner.pack_configure(padx=11, pady=11)
            self.name_label.configure(text_color=COLORS["primary"])
            if self._badge_label is not None:
                self._badge_label.place(relx=1.0, x=-12, y=12, anchor="ne")
        else:
            self.configure(border_color=COLORS["border"], border_width=2)
            self.inner.pack_configure(padx=12, pady=12)
            self.name_label.configure(text_color=COLORS["text_primary"])
            if self._badge_label is not None:
                self._badge_label.place_forget()


def _load_check_badge() -> Optional[ctk.CTkImage]:
    try:
        from pathlib import Path
        asset = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "ui" / "icon_check_36.png"
        img = Image.open(asset)
        return ctk.CTkImage(light_image=img, dark_image=img, size=(36, 36))
    except Exception as e:
        logger.debug(f"Filter-Badge nicht ladbar: {e}")
        return None


class FilterScreen(ctk.CTkFrame):
    """Filter-Auswahl — 4×2-Kachel-Grid mit Live-Bild pro Filter"""

    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.app = app
        self.config = app.config

        self.selected_filter = "none"
        self.filter_buttons: Dict[str, FilterCard] = {}
        # Verkleinerte Arbeitskopien der Fotos für ALLE Vorschauen: Filter auf
        # den 6000x4000-Nikon-Originalen dauerten pro Klick viele Sekunden
        # (4x 24 MP); für die Vorschau reicht ~1000px. Das finale Druckbild
        # rendert weiterhin aus den Originalen (final.py).
        self._preview_photos = None
        self._preview_photos_lock = threading.Lock()
        self._auto_continue_job = None
        self._auto_continue_until = 0.0
        self._auto_continue_seconds = 0.0
        self._auto_last_label_seconds = -1
        self._activity_bindings = []

        self._setup_ui()

    def _setup_ui(self):
        """Erstellt die UI — Titel links, Kachel-Grid, Auto-Weiter-Zeile unten"""
        # Kopfzeile: Titel + Untertitel links, Tertiary „Fotos nochmal" rechts
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=40, pady=(18, 0))

        head_text = ctk.CTkFrame(header, fg_color="transparent")
        head_text.pack(side="left")

        self.title_label = ctk.CTkLabel(
            head_text,
            text=t(self.config, "filter.choose_style"),
            font=FONTS_UI["h1"],
            text_color=COLORS["text_primary"]
        )
        self.title_label.pack(anchor="w")

        self.subtitle_label = ctk.CTkLabel(
            head_text,
            text=t(self.config, "filter.hint"),
            font=FONTS_UI["label"],
            text_color=COLORS["text_secondary"]
        )
        self.subtitle_label.pack(anchor="w", pady=(4, 0))

        back_btn = ctk.CTkButton(
            header,
            text=t(self.config, "filter.back_redo"),
            command=self._on_back,
            **style_tertiary(width=220, height=56)
        )
        bind_pressed(back_btn, COLORS["bg_medium"], COLORS["bg_light"])
        back_btn.pack(side="right", pady=(6, 0))

        # Kachel-Grid 4×2 (zentriert, Zellen 262, Gap 24)
        grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        grid_frame.pack(pady=(16, 0))
        self._create_filter_grid(grid_frame)

        # Fußzeile: Auto-Weiter-Balken + Text links, WEITER rechts
        self.auto_progress = ctk.CTkProgressBar(
            self,
            height=6,
            fg_color=COLORS["bg_light"],
            progress_color=COLORS["primary"],
            corner_radius=3
        )
        self.auto_progress.pack(fill="x", padx=40, pady=(14, 0))
        self.auto_progress.set(1.0)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=40, pady=(10, 16))

        self.auto_label = ctk.CTkLabel(
            footer,
            text="",
            font=FONTS_UI["label"],
            text_color=COLORS["text_secondary"]
        )
        self.auto_label.pack(side="left")

        self.continue_btn = ctk.CTkButton(
            footer,
            text=t(self.config, "filter.continue"),
            command=self._on_continue,
            **style_primary(width=400, height=88)
        )
        bind_pressed(self.continue_btn, COLORS["primary"], COLORS["primary_pressed"])
        self.continue_btn.pack(side="right")

    def _create_filter_grid(self, parent):
        """Erstellt das 4×2-Kachel-Grid (feste Kachelgröße, kein Resize-Flackern)"""
        filters = list(AVAILABLE_FILTERS.items())
        num_cols = 4

        # Auf 1280×800 mit Kopf- und Fußzeile bleibt für 2 Reihen weniger als
        # 2×224 — die Kachelhöhe wird passend reduziert, Breite bleibt 262.
        tile_h = 200

        for idx, (key, name) in enumerate(filters):
            display_name = t(self.config, f"filter.{key}")
            row = idx // num_cols
            col = idx % num_cols
            card = FilterCard(
                parent,
                filter_key=key,
                filter_name=display_name if display_name != f"filter.{key}" else name,
                on_click=lambda b: self._select_filter(b),
                card_width=TILE_W,
                card_height=tile_h,
            )
            card.grid(row=row, column=col, padx=12, pady=12)
            self.filter_buttons[key] = card

    def _select_filter(self, button: FilterCard):
        """Wählt einen Filter aus"""
        if self.selected_filter in self.filter_buttons:
            self.filter_buttons[self.selected_filter].set_selected(False)

        self.selected_filter = button.filter_key
        button.set_selected(True)
        self.app.current_filter = self.selected_filter

        # Jede Interaktion gibt dem Gast wieder die volle Auswahlzeit.
        self._reset_auto_continue_timer()

        logger.debug(f"Filter ausgewählt: {self.selected_filter}")

    def _get_preview_photos(self):
        """Liefert die verkleinerten Arbeitskopien der Fotos (einmal erstellt).

        Läuft in Worker-Threads; der Lock verhindert doppelten Aufbau, wenn
        zwei Worker gleichzeitig starten.
        """
        with self._preview_photos_lock:
            if self._preview_photos is None:
                t0 = time.perf_counter()
                small = []
                for photo in self.app.photos_taken:
                    scale = min(1.0, 1000 / max(photo.width, photo.height))
                    if scale < 1.0:
                        small.append(photo.resize(
                            (max(1, int(photo.width * scale)), max(1, int(photo.height * scale))),
                            Image.Resampling.BILINEAR
                        ))
                    else:
                        small.append(photo)
                self._preview_photos = small
                logger.info(
                    f"Filter-Vorschau: {len(small)} Arbeitskopien erstellt "
                    f"({(time.perf_counter() - t0) * 1000:.0f}ms)"
                )
            return self._preview_photos

    def _generate_filter_previews(self):
        """Kachel-Thumbs: das erste Foto mit jedem Filter (Hintergrund, <1 s)."""
        if not self.app.photos_taken:
            return

        t0 = time.perf_counter()
        sample = self._get_preview_photos()[0].copy()
        sample.thumbnail((THUMB_W, THUMB_H), Image.Resampling.BILINEAR)

        for key, card in self.filter_buttons.items():
            try:
                filtered = self.app.filter_manager.apply(sample, key)
                self.after(0, lambda c=card, img=filtered: c.set_preview(img))
            except Exception as e:
                logger.warning(f"Filter-Preview Fehler für {key}: {e}")
        logger.info(
            f"Filter-Kacheln gerendert: {len(self.filter_buttons)} Thumbs in "
            f"{(time.perf_counter() - t0) * 1000:.0f}ms"
        )

    def _on_back(self):
        """Zurück - neue Fotos machen"""
        self._cancel_auto_continue_timer()
        logger.info(f"Filter-Screen: Zurück (Fotos verworfen, Filter war '{self.selected_filter}')")
        self.app.photos_taken = []
        self.app.current_photo_index = 0
        self.app.show_screen("session")

    def _on_continue(self, auto: bool = False):
        """Weiter zum Final-Screen"""
        self._cancel_auto_continue_timer()
        logger.info(f"Filter gewählt: {self.selected_filter}{' (Auto-Weiter)' if auto else ''}")
        self.app.current_filter = self.selected_filter
        self.app.show_screen("final")

    def _get_auto_continue_seconds(self) -> float:
        """Fester Inaktivitäts-Timeout für die Filter-Auswahl."""
        return FILTER_INACTIVITY_SECONDS

    def _on_user_activity(self, event=None):
        """Jede Touch-/Maus-Aktivität gibt wieder volle Auswahlzeit."""
        if getattr(self.app, "current_screen_name", None) != "filter":
            return
        self._reset_auto_continue_timer()

    def _bind_activity_events(self):
        """Bindet Touch-Aktivität nur während der Filter-Screen sichtbar ist."""
        self._unbind_activity_events()
        root = self.winfo_toplevel()
        for sequence in ("<ButtonPress-1>", "<ButtonRelease-1>", "<B1-Motion>"):
            try:
                bind_id = root.bind(sequence, self._on_user_activity, add="+")
                if bind_id:
                    self._activity_bindings.append((root, sequence, bind_id))
            except Exception as e:
                logger.debug(f"Filter-Aktivitätsbindung fehlgeschlagen ({sequence}): {e}")

    def _unbind_activity_events(self):
        for widget, sequence, bind_id in self._activity_bindings:
            try:
                widget.unbind(sequence, bind_id)
            except Exception:
                pass
        self._activity_bindings = []

    def _reset_auto_continue_timer(self):
        self._cancel_auto_continue_timer()
        seconds = self._get_auto_continue_seconds()
        if seconds <= 0:
            self.auto_progress.set(0.0)
            return

        self._auto_continue_seconds = seconds
        self._auto_continue_until = time.time() + seconds
        self._auto_last_label_seconds = -1
        self.auto_progress.set(1.0)
        self._auto_continue_job = self.after(100, self._tick_auto_continue)

    def _cancel_auto_continue_timer(self):
        job = self._auto_continue_job
        self._auto_continue_job = None
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass

    def _tick_auto_continue(self):
        self._auto_continue_job = None
        # Beim ERSTEN Anzeigen ist das CTkFrame evtl. noch nicht gemappt -> NICHT
        # abbrechen, sondern neu schedulen. Sonst startete der Auto-Ablauf erst
        # nach dem ersten manuellen Filter-Wechsel (Bug). on_hide() cancelt den
        # Job -> kein Zombie-Timer.
        if not self.winfo_ismapped():
            self._auto_continue_job = self.after(500, self._tick_auto_continue)
            return

        remaining = self._auto_continue_until - time.time()
        if remaining <= 0:
            self.auto_progress.set(0.0)
            self._on_continue(auto=True)
            return

        if self._auto_continue_seconds > 0:
            self.auto_progress.set(max(0.0, min(1.0, remaining / self._auto_continue_seconds)))

        # Sekunden-Text nur bei Wechsel aktualisieren (1 configure/s)
        secs = max(1, int(remaining + 0.999))
        if secs != self._auto_last_label_seconds:
            self._auto_last_label_seconds = secs
            self.auto_label.configure(
                text=t(self.config, "filter.auto_continue", seconds=secs)
            )

        # Redesign: Timer-Updates max. 2×/s (vorher 10×/s)
        self._auto_continue_job = self.after(500, self._tick_auto_continue)

    def on_show(self):
        """Screen wird angezeigt"""
        self.config = self.app.config

        # Texte in aktueller Sprache
        self.title_label.configure(text=t(self.config, "filter.choose_style"))
        self.subtitle_label.configure(text=t(self.config, "filter.hint"))
        self.continue_btn.configure(text=t(self.config, "filter.continue"))

        # Arbeitskopien leeren (neue Fotos)
        with self._preview_photos_lock:
            self._preview_photos = None

        # Standard-Filter auswählen
        self.selected_filter = "none"
        for key, card in self.filter_buttons.items():
            display_name = t(self.config, f"filter.{key}")
            if display_name != f"filter.{key}":
                card.filter_name = display_name
                card.name_label.configure(text=display_name)
            card.set_selected(key == "none")

        # Kachel-Thumbs im Hintergrund generieren (ein einziger kurzer Worker)
        threading.Thread(target=self._generate_filter_previews, daemon=True).start()

        # Ohne Eingabe automatisch nach fester Inaktivitätsdauer weiter.
        self._bind_activity_events()
        self._reset_auto_continue_timer()

    def on_hide(self):
        """Screen wird verlassen"""
        self._unbind_activity_events()
        self._cancel_auto_continue_timer()
        with self._preview_photos_lock:
            self._preview_photos = None
