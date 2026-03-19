"""Session-Screen mit Vollbild-LiveView

Optimiert für Lenovo Miix 310 (1280x800)
- Live-View Vollbild oder mit Template-Overlay (konfigurierbar)
- Countdown zentriert über dem Live-View
- Performance-optimiert für schwache Hardware
"""

import customtkinter as ctk
import tkinter as tk
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import TYPE_CHECKING, Optional
import time
import os
import random
import threading

from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class SessionScreen(ctk.CTkFrame):
    """Session-Screen mit Vollbild-LiveView"""

    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color="#FFFFFF")
        self.app = app
        self.config = app.config

        # Status (current_photo_index ist jetzt in self.app - bleibt bei Screen-Wechsel erhalten!)
        self.total_photos = 1
        self.countdown_value = 0
        self.is_countdown_active = False
        self.is_live = False
        self.show_flash = False
        self.photo_display_until = 0
        self._resuming_after_video = False  # Flag: Session nach Video fortsetzen
        self._redo_visible = False  # Redo-Button sichtbar?
        self._capture_in_progress = False  # Capture läuft im Hintergrund

        # Performance-Einstellungen
        self._low_perf = self.config.get("low_performance_mode", {})
        self._frame_counter = 0
        self._skip_frames = self._low_perf.get("skip_frames", 0) if self._low_perf.get("enabled", False) else 0

        # FPS aus Config (default 20 für schwache Hardware)
        cam_settings = self.config.get("camera_settings", {})
        self._target_fps = cam_settings.get("live_view_fps", 20)
        self._frame_delay_ms = max(33, int(1000 / self._target_fps))

        # Gecachtes Flash-Bild (wird in on_show erstellt, nicht bei jedem Foto neu)
        self._cached_flash_ctk = None
        self._cached_flash_size = (0, 0)

        # Template-Overlay im LiveView (optional, konfigurierbar)
        self._template_overlay_enabled = self.config.get("liveview_template_overlay", False)
        self._cached_template_composite = None  # Vorbereitetes Template (skaliert)
        self._cached_template_boxes_scaled = []  # Skalierte Box-Koordinaten
        self._cached_template_scale = 1.0
        self._cached_template_display_size = (0, 0)
        self._cached_template_container_size = (0, 0)  # Container-Größe bei Cache-Erstellung

        logger.info(f"Session: FPS={self._target_fps}, delay={self._frame_delay_ms}ms, skip={self._skip_frames}")

        self._setup_ui()

    def _setup_ui(self):
        """Erstellt die UI"""
        # Info-Leiste oben
        info_bar = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], height=45)
        info_bar.pack(fill="x")
        info_bar.pack_propagate(False)

        # Foto-Fortschritt
        self.progress_label = ctk.CTkLabel(
            info_bar,
            text="Foto 1 von 1",
            font=FONTS["body_bold"],
            text_color=COLORS["text_primary"]
        )
        self.progress_label.pack(side="left", padx=20, pady=10)

        # Abbrechen-Button
        cancel_btn = ctk.CTkButton(
            info_bar,
            text=self.config.get("ui_texts", {}).get("cancel", "ABBRECHEN"),
            font=FONTS["small"],
            width=120,
            height=32,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["error"],
            corner_radius=SIZES["corner_radius_small"],
            command=self._on_cancel
        )
        cancel_btn.pack(side="right", padx=20, pady=6)

        # Hauptbereich
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # Preview Container (volle Größe)
        self.preview_container = ctk.CTkFrame(
            main_frame,
            fg_color="#FFFFFF",
            corner_radius=0
        )
        self.preview_container.pack(expand=True, fill="both")

        # Preview Label
        self.preview_label = ctk.CTkLabel(
            self.preview_container,
            text="",
            fg_color="transparent"
        )
        self.preview_label.pack(expand=True, fill="both")

        # Button-Leiste: tkinter.Frame mit place() (CTkFrame place/lift unzuverlässig!)
        self._button_bar = tk.Frame(self, bg="#000000", height=80)
        # Versteckt - wird per place() eingeblendet

        self._redo_btn = ctk.CTkButton(
            self._button_bar,
            text="↻ NOCHMAL",
            font=("Segoe UI", 22, "bold"),
            width=220,
            height=55,
            fg_color=COLORS["error"],
            hover_color="#cc3344",
            text_color=COLORS["text_primary"],
            corner_radius=SIZES["corner_radius"],
            command=self._on_redo_photo
        )

        self._continue_btn = ctk.CTkButton(
            self._button_bar,
            text="WEITER →",
            font=("Segoe UI", 22, "bold"),
            width=220,
            height=55,
            fg_color=COLORS["success"],
            hover_color="#00b85c",
            text_color=COLORS["text_primary"],
            corner_radius=SIZES["corner_radius"],
            command=self._on_continue_photo
        )

    def on_show(self):
        """Screen wird angezeigt"""

        # Template-Overlay Einstellung bei jedem Show neu lesen (Admin kann es ändern)
        self._template_overlay_enabled = self.config.get("liveview_template_overlay", False)

        # Prüfen ob wir nach Video fortsetzen (photos_taken nicht leer = Session läuft bereits)
        resuming = len(self.app.photos_taken) > 0

        if resuming:
            logger.info(f"Session fortgesetzt nach Video: Index={self.app.current_photo_index}, photos_taken={len(self.app.photos_taken)}")
            self.total_photos = len(self.app.template_boxes) if self.app.template_boxes else 1
            self.photo_display_until = 0
            self._update_progress()
            # Template-Overlay Cache synchron aufbauen (vor LiveView!)
            if self._template_overlay_enabled and self._cached_template_composite is None:
                self._build_template_overlay_cache()
            self.is_live = True
            self._update_live_view()
            # Flash-Cache erstellen falls noch nicht vorhanden
            if self._cached_flash_ctk is None:
                self.after(100, self._build_flash_cache)
            # Kamera ist bereits warm - kürzerer Delay
            self.after(200, self._start_countdown)
            return

        logger.info("Session gestartet (neu)")

        # Kamera initialisieren (oder wiederverwenden wenn bereits initialisiert)
        if self.app.camera_manager.is_initialized:
            logger.info("Kamera bereits initialisiert - überspringe Neuinitialisierung")
        else:
            cam_settings = self.config.get("camera_settings", {})
            live_res = cam_settings.get("live_view_resolution", 480)  # Default 480 für Performance

            if not self.app.camera_manager.initialize(
                self.config.get("camera_index", 0),
                live_res,
                int(live_res * 0.75)
            ):
                logger.error("Kamera konnte nicht initialisiert werden")
                self._show_error("Kamera konnte nicht geöffnet werden!")
                return

        # Session initialisieren (NUR bei neuem Start!)
        self.app.photos_taken = []
        self.app.current_photo_index = 0
        self.total_photos = len(self.app.template_boxes) if self.app.template_boxes else 1
        self.photo_display_until = 0

        logger.info(f"Session: {self.total_photos} Fotos zu machen")
        self._update_progress()

        # Template-Overlay Cache SYNCHRON aufbauen (BEVOR LiveView startet,
        # sonst sieht man kurz Vollbild-Kamera bevor Template-Ansicht kommt)
        if self._template_overlay_enabled:
            self._build_template_overlay_cache()

        # Live-View starten
        self.is_live = True
        self._update_live_view()

        # Flash-Bild im Voraus erstellen (nicht bei jedem Foto neu laden!)
        self.after(300, self._build_flash_cache)

        # Countdown nach kurzer Verzögerung starten
        self.after(500, self._start_countdown)

    def on_hide(self):
        """Screen wird verlassen"""
        self.is_live = False
        self.is_countdown_active = False
        self._hide_redo_button()
        # Template-Overlay Cache freigeben (wird bei nächstem on_show neu gebaut)
        self._cached_template_composite = None
        self._cached_template_boxes_scaled = []

    def _update_progress(self, override_current: int = 0):
        """Aktualisiert die Fortschrittsanzeige"""
        if override_current > 0:
            current = override_current
        else:
            current = min(self.app.current_photo_index + 1, self.total_photos)
        self.progress_label.configure(
            text=f"Foto {current} von {self.total_photos}"
        )

    def _update_live_view(self):
        """Aktualisiert die Live-Vorschau (Vollbild, Performance-optimiert)"""
        if not self.is_live:
            return

        if self.show_flash:
            self._display_flash()
            self.after(100, self._update_live_view)
            return

        if self.photo_display_until > 0:
            if time.time() < self.photo_display_until:
                # Zuletzt aufgenommenes Foto anzeigen
                if self.app.photos_taken:
                    self._display_preview(self.app.photos_taken[-1])
                self.after(100, self._update_live_view)
                return
            else:
                self.photo_display_until = 0
                self._next_photo_or_finish()
                if self.is_live:
                    self.after(100, self._update_live_view)
                return

        # Frame-Skipping für schwache Hardware
        self._frame_counter += 1
        if self._skip_frames > 0 and (self._frame_counter % (self._skip_frames + 1)) != 0:
            if self.is_live:
                self.after(self._frame_delay_ms, self._update_live_view)
            return

        # Kein Kamera-Zugriff während Capture im Hintergrund (Race Condition vermeiden)
        if not self._capture_in_progress:
            frame = self.app.camera_manager.get_frame()
            if frame is not None:
                # Kamera-Frame aufbereiten (spiegeln, rotieren)
                if self.config.get("rotate_180", False):
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                live_img = Image.fromarray(rgb)

                # Template-Overlay anwenden (wenn aktiviert)
                if self._template_overlay_enabled and self._cached_template_composite is not None:
                    # Cache-Rebuild wenn Container-Größe sich deutlich geändert hat
                    try:
                        cw = self.preview_container.winfo_width()
                        ch = self.preview_container.winfo_height()
                        old_size = getattr(self, '_cached_template_container_size', None)
                        if old_size and cw > 100 and ch > 100:
                            old_cw, old_ch = old_size
                            if abs(cw - old_cw) > 50 or abs(ch - old_ch) > 50:
                                logger.info(f"Container-Resize erkannt: {old_cw}x{old_ch} → {cw}x{ch} → Cache rebuild")
                                self._build_template_overlay_cache()
                        live_img = self._apply_template_overlay(live_img)
                    except Exception as e:
                        logger.warning(f"Template-Overlay Fehler im LiveView: {e}")
                        self._cached_template_composite = None

                if self.is_countdown_active and self.countdown_value > 0:
                    live_img = self._add_countdown_overlay(live_img)

                self._display_preview(live_img)

        if self.is_live:
            self.after(self._frame_delay_ms, self._update_live_view)

    def _add_countdown_overlay(self, img: Image.Image) -> Image.Image:
        """Fügt ZENTRIERTEN Countdown zum Bild hinzu"""
        img = img.copy()
        draw = ImageDraw.Draw(img)

        font_size = min(img.width, img.height) // 2
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", font_size)
        except:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)
            except:
                font = ImageFont.load_default()

        text = str(self.countdown_value)

        bbox = draw.textbbox((0, 0), text, font=font, anchor="lt")
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        x = (img.width - text_w) // 2 - bbox[0]
        y = (img.height - text_h) // 3 - bbox[1]

        shadow_color = (0, 0, 0, 220)
        for dx, dy in [(-4, -4), (4, -4), (-4, 4), (4, 4), (0, 6), (6, 0), (-6, 0), (0, -6)]:
            draw.text((x + dx, y + dy), text, fill=shadow_color, font=font)

        draw.text((x, y), text, fill=(224, 6, 117, 255), font=font)

        return img

    def _display_preview(self, img: Image.Image):
        """Zeigt das Vorschau-Bild bildschirmfüllend an.

        WICHTIG: winfo_width()/winfo_height() geben Tk-Pixel zurück,
        CTkImage.size erwartet aber DPI-unabhängige (logische) Pixel.
        Bei 125% DPI-Skalierung (Lenovo Miix 310): Tk=1280, Logisch=1024.
        Ohne Korrektur wird das Bild zu groß und abgeschnitten.
        """
        container_w = self.preview_container.winfo_width()
        container_h = self.preview_container.winfo_height()

        if container_w < 100 or container_h < 100:
            container_w = self.winfo_screenwidth()
            container_h = self.winfo_screenheight()

        # Tk-Pixel → logische Pixel umrechnen (DPI-Skalierung berücksichtigen)
        scaling = self._get_widget_scaling()
        logical_w = container_w / scaling
        logical_h = container_h / scaling

        # Seitenverhältnis beibehalten, Container füllen (in logischen Pixeln)
        img_ratio = img.width / img.height
        container_ratio = logical_w / logical_h

        if img_ratio > container_ratio:
            display_w = int(logical_w)
            display_h = int(logical_w / img_ratio)
        else:
            display_h = int(logical_h)
            display_w = int(logical_h * img_ratio)

        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(display_w, display_h))
        self.preview_label.configure(image=ctk_img)
        self.preview_label.image = ctk_img

    def _build_flash_cache(self):
        """Erstellt und cached das Flash-Bild einmalig (statt bei jedem Foto neu)"""
        try:
            container_w = self.preview_container.winfo_width() - 10
            container_h = self.preview_container.winfo_height() - 10

            if container_w < 100 or container_h < 100:
                screen_w = self.winfo_screenwidth()
                screen_h = self.winfo_screenheight()
                container_w = max(screen_w - 20, 800)
                container_h = max(screen_h - 80, 500)

            if container_w <= 100 or container_h <= 100:
                return

            flash = Image.new("RGB", (container_w, container_h), (255, 255, 255))

            flash_image_path = self.config.get("flash_image", "")
            custom_loaded = False

            if flash_image_path and os.path.exists(flash_image_path):
                try:
                    custom_img = Image.open(flash_image_path)
                    custom_img.load()
                    logger.info(f"Flash-Cache: Bild geladen: {flash_image_path} ({custom_img.size})")

                    # Bild auf 80% der Container-Größe skalieren (gut sichtbar)
                    max_size = int(min(container_w, container_h) * 0.8)
                    custom_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                    img_x = (container_w - custom_img.width) // 2
                    img_y = (container_h - custom_img.height) // 2

                    if custom_img.mode == "RGBA":
                        flash.paste(custom_img, (img_x, img_y), custom_img)
                    else:
                        flash.paste(custom_img.convert("RGB"), (img_x, img_y))

                    custom_loaded = True
                except Exception as e:
                    logger.error(f"Flash-Bild Fehler: {e}")
            elif flash_image_path:
                logger.warning(f"Flash-Bild nicht gefunden: {flash_image_path}")

            if not custom_loaded:
                draw = ImageDraw.Draw(flash)
                size = int(min(container_w, container_h) * 0.5)
                cx, cy = container_w // 2, container_h // 2
                radius = size // 2
                draw.ellipse(
                    [cx - radius, cy - radius, cx + radius, cy + radius],
                    fill=(255, 220, 50), outline=(200, 170, 30),
                    width=max(3, size // 30)
                )
                eye_radius = size // 10
                eye_y = cy - size // 6
                eye_offset = size // 4
                draw.ellipse([cx - eye_offset - eye_radius, eye_y - eye_radius,
                              cx - eye_offset + eye_radius, eye_y + eye_radius], fill=(50, 50, 50))
                draw.ellipse([cx + eye_offset - eye_radius, eye_y - eye_radius,
                              cx + eye_offset + eye_radius, eye_y + eye_radius], fill=(50, 50, 50))
                mouth_width = size // 2
                mouth_height = size // 4
                mouth_y = cy + size // 10
                draw.arc([cx - mouth_width // 2, mouth_y - mouth_height // 2,
                          cx + mouth_width // 2, mouth_y + mouth_height],
                         start=0, end=180, fill=(50, 50, 50), width=max(4, size // 20))

            # CTkImage size in logischen Pixeln (DPI-korrigiert)
            scaling = self._get_widget_scaling()
            logical_w = int(container_w / scaling)
            logical_h = int(container_h / scaling)
            self._cached_flash_ctk = ctk.CTkImage(light_image=flash, dark_image=flash, size=(logical_w, logical_h))
            self._cached_flash_size = (container_w, container_h)
            logger.info(f"Flash-Cache erstellt: {container_w}x{container_h}")

        except Exception as e:
            logger.error(f"Flash-Cache Erstellung fehlgeschlagen: {e}")

    def _build_template_overlay_cache(self):
        """Erstellt den skalierten Template-Overlay-Cache für LiveView"""
        try:
            overlay = self.app.overlay_image
            boxes = self.app.template_boxes
            if not overlay or not boxes:
                self._cached_template_composite = None
                logger.info("Template-Overlay: Kein Overlay oder keine Boxen vorhanden")
                return

            # Layout sicherstellen bevor wir messen
            self.update_idletasks()

            container_w = self.preview_container.winfo_width()
            container_h = self.preview_container.winfo_height()
            if container_w < 100 or container_h < 100:
                # Fallback: Bildschirmgröße verwenden (nicht 900x500!)
                container_w = self.winfo_screenwidth()
                container_h = self.winfo_screenheight()
                logger.debug(f"Container noch nicht gerendert, verwende Bildschirmgröße: {container_w}x{container_h}")

            # Template auf Container-Größe skalieren (Seitenverhältnis beibehalten)
            overlay_w, overlay_h = overlay.size
            scale = min(container_w / overlay_w, container_h / overlay_h)
            display_w = int(overlay_w * scale)
            display_h = int(overlay_h * scale)

            # Overlay skalieren (BILINEAR statt LANCZOS für Performance)
            scaled_overlay = overlay.resize((display_w, display_h), Image.Resampling.BILINEAR)

            # Boxen skalieren
            scaled_boxes = []
            for box_info in boxes:
                x1, y1, x2, y2 = box_info["box"]
                scaled_boxes.append({
                    "box": (int(x1 * scale), int(y1 * scale), int(x2 * scale), int(y2 * scale)),
                    "angle": box_info.get("angle", 0.0)
                })

            self._cached_template_composite = scaled_overlay
            self._cached_template_boxes_scaled = scaled_boxes
            self._cached_template_scale = scale
            self._cached_template_display_size = (display_w, display_h)
            self._cached_template_container_size = (container_w, container_h)
            logger.info(f"Template-Overlay Cache: {overlay_w}x{overlay_h} -> {display_w}x{display_h} (Container: {container_w}x{container_h}, scale={scale:.3f})")

        except Exception as e:
            logger.error(f"Template-Overlay Cache fehlgeschlagen: {e}")
            self._cached_template_composite = None

    def _apply_template_overlay(self, live_img: Image.Image) -> Image.Image:
        """Setzt den Kamera-Frame in die aktuelle Template-Box ein und legt das Overlay darüber"""
        if self._cached_template_composite is None:
            return live_img

        idx = self.app.current_photo_index
        if idx >= len(self._cached_template_boxes_scaled):
            return live_img

        display_w, display_h = self._cached_template_display_size

        # Canvas mit schwarzem Hintergrund erstellen
        canvas = Image.new("RGBA", (display_w, display_h), (0, 0, 0, 255))

        # Bereits aufgenommene Fotos in ihre Boxen einfügen (verkleinert)
        for i, photo in enumerate(self.app.photos_taken):
            if i >= len(self._cached_template_boxes_scaled):
                break
            box_info = self._cached_template_boxes_scaled[i]
            x1, y1, x2, y2 = box_info["box"]
            bw, bh = x2 - x1 + 1, y2 - y1 + 1
            if bw > 0 and bh > 0:
                fitted = self._fit_to_box(photo, bw, bh)
                canvas.paste(fitted, (x1, y1))

        # LiveView in aktuelle Box einsetzen
        current_box = self._cached_template_boxes_scaled[idx]
        x1, y1, x2, y2 = current_box["box"]
        bw, bh = x2 - x1 + 1, y2 - y1 + 1
        if bw > 0 and bh > 0:
            fitted_live = self._fit_to_box(live_img, bw, bh)
            canvas.paste(fitted_live, (x1, y1))

        # Template-Overlay darüber legen
        canvas = Image.alpha_composite(canvas, self._cached_template_composite)

        return canvas.convert("RGB")

    def _fit_to_box(self, img: Image.Image, box_w: int, box_h: int) -> Image.Image:
        """Passt ein Bild in eine Box ein (Cover-Modus, schnell)"""
        img_w, img_h = img.size
        box_aspect = box_w / box_h
        img_aspect = img_w / img_h

        if img_aspect > box_aspect:
            new_h = box_h
            new_w = int(new_h * img_aspect)
        else:
            new_w = box_w
            new_h = int(new_w / img_aspect)

        resized = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
        left = (new_w - box_w) // 2
        top = (new_h - box_h) // 2
        cropped = resized.crop((left, top, left + box_w, top + box_h))
        return cropped.convert("RGBA")

    def _display_flash(self):
        """Zeigt das gecachte Flash-Bild (sofort, ohne Neuberechnung)"""
        try:
            # Cache erstellen falls noch nicht vorhanden
            if self._cached_flash_ctk is None:
                self._build_flash_cache()

            if self._cached_flash_ctk is not None:
                self.preview_label.configure(image=self._cached_flash_ctk)
                self.preview_label.image = self._cached_flash_ctk
        except Exception as e:
            logger.error(f"Flash-Anzeige fehlgeschlagen: {e}")

    def _start_countdown(self):
        """Startet den Countdown"""
        logger.info(f"=== Starte Countdown für Foto {self.app.current_photo_index + 1}/{self.total_photos} ===")
        self.is_countdown_active = True
        self.countdown_value = self.config.get("countdown_time", 5)
        self._countdown_tick()

    def _countdown_tick(self):
        """Ein Countdown-Tick"""
        if not self.is_countdown_active or not self.is_live:
            return

        if self.countdown_value > 0:
            self.countdown_value -= 1
            self.after(1000, self._countdown_tick)
        else:
            self.is_countdown_active = False
            self._take_photo()

    def _take_photo(self):
        """Nimmt ein Foto auf"""
        logger.info(f"Foto {self.app.current_photo_index + 1} aufnehmen")

        self.show_flash = True
        self._display_flash()  # Sofort anzeigen, nicht auf nächsten Loop-Tick warten
        # GUI-Redraw erzwingen damit Flash SICHER auf dem Bildschirm gemalt wird
        # bevor die blocking Kamera-Aufnahme startet
        self.update_idletasks()

        flash_duration = self.config.get("flash_duration", 300)
        self.after(flash_duration, self._capture_photo)

    def _capture_photo(self):
        """Erfasst das Foto (non-blocking via Background-Thread)"""
        # Flash ausschalten, Kamera-Zugriff für LiveView pausieren
        self.show_flash = False
        self._capture_in_progress = True

        # Lade-Anzeige während Capture im Hintergrund läuft
        self._capture_dots = 0
        self._show_capture_loading()

        # Capture in Background-Thread starten (blockiert nicht die UI)
        thread = threading.Thread(target=self._capture_photo_worker, daemon=True)
        thread.start()

    def _show_capture_loading(self):
        """Animierte Lade-Anzeige während Webcam-Capture"""
        if not self._capture_in_progress:
            # Lade-Label verstecken
            if hasattr(self, '_loading_label'):
                self._loading_label.place_forget()
            return
        self._capture_dots = (self._capture_dots + 1) % 4
        dots = "." * self._capture_dots
        # Separates Label ganz unten auf dem Screen (über preview, nicht IN preview)
        if not hasattr(self, '_loading_label'):
            self._loading_label = tk.Label(
                self,
                text="",
                font=("Segoe UI", 36, "bold"),
                fg="#e00675",
                bg="#ffffff",
                padx=20,
                pady=10
            )
        self._loading_label.configure(text=f"  Foto wird aufgenommen{dots}  ")
        self._loading_label.place(relx=0.5, rely=0.95, anchor="center")
        self._loading_label.tkraise()
        self.after(400, self._show_capture_loading)

    def _capture_photo_worker(self):
        """Worker-Thread: Führt den blockierenden Kamera-Capture durch"""
        photo = None

        try:
            # Canon DSLR
            if hasattr(self.app.camera_manager, 'capture_photo'):
                try:
                    photo = self.app.camera_manager.capture_photo(timeout=10.0)
                    if photo:
                        frame = np.array(photo)
                        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                        if self.config.get("rotate_180", False):
                            frame = cv2.rotate(frame, cv2.ROTATE_180)
                        frame = cv2.flip(frame, 1)
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        photo = Image.fromarray(rgb)
                except Exception as e:
                    logger.error(f"DSLR Fehler: {e}")

            # Webcam
            if photo is None:
                cam_settings = self.config.get("camera_settings", {})
                capture_w = cam_settings.get("single_photo_width", 1920)
                capture_h = cam_settings.get("single_photo_height", 1080)

                logger.info(f"Webcam Capture: {capture_w}x{capture_h}")

                if hasattr(self.app.camera_manager, 'get_high_res_frame'):
                    frame = self.app.camera_manager.get_high_res_frame(capture_w, capture_h)
                    if frame is not None:
                        logger.info(f"High-Res: {frame.shape[1]}x{frame.shape[0]}")
                    else:
                        frame = self.app.camera_manager.get_frame(use_cache=False)
                else:
                    frame = self.app.camera_manager.get_frame(use_cache=False)

                if frame is not None:
                    if self.config.get("rotate_180", False):
                        frame = cv2.rotate(frame, cv2.ROTATE_180)
                    frame = cv2.flip(frame, 1)
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    photo = Image.fromarray(rgb)

        except Exception as e:
            logger.error(f"Capture-Worker Fehler: {e}")

        # Ergebnis zurück auf UI-Thread geben
        self.after(0, lambda p=photo: self._on_capture_complete(p))

    def _on_capture_complete(self, photo: Optional[Image.Image]):
        """Callback auf UI-Thread nach abgeschlossenem Capture"""
        self._capture_in_progress = False
        # Lade-Anzeige aufräumen
        self.preview_label.configure(text="", font=("Segoe UI", 1))
        if hasattr(self, '_loading_label'):
            self._loading_label.place_forget()

        if photo is not None:
            self.app.photos_taken.append(photo)
            self.app.statistics.record_photo()
            self.after(10, lambda: self._save_photo_async(photo, self.app.current_photo_index + 1))

            display_time = self.config.get("single_display_time", 2)
            self.app.current_photo_index += 1
            # Fortschritt zeigt noch das gerade aufgenommene Foto (nicht das nächste)
            self._update_progress(override_current=self.app.current_photo_index)

            # Bei Collagen (>1 Foto): Button-Leiste zeigen (Nochmal + Weiter), 60s Timeout
            if self.total_photos > 1 and self.app.current_photo_index < self.total_photos:
                display_time = 60
                try:
                    self._show_redo_button()
                except Exception as e:
                    logger.error(f"Button-Leiste Fehler: {e}", exc_info=True)

            # WICHTIG: Timer immer setzen (auch wenn Button-Leiste fehlschlägt)
            self.photo_display_until = time.time() + display_time
            logger.info(f"Foto-Anzeige für {display_time}s (buttons={self._redo_visible})")
        else:
            logger.error("Foto-Aufnahme fehlgeschlagen")
            self._next_photo_or_finish()

    def _save_photo_async(self, photo: Image.Image, index: int):
        """Speichert Foto im Hintergrund"""
        try:
            self.app.local_storage.save_single(photo, suffix=str(index))
        except Exception as e:
            logger.error(f"Fehler beim Speichern: {e}")

    def _show_redo_button(self):
        """Zeigt die Button-Leiste (Nochmal + Weiter) am unteren Bildschirmrand"""
        logger.info(f"_show_redo_button aufgerufen - Foto {self.app.current_photo_index}/{self.total_photos}")
        self._redo_visible = True
        # tkinter place() auf self - funktioniert zuverlässig (kein CTk place-Bug)
        self._button_bar.place(x=0, rely=1.0, anchor="sw", relwidth=1.0, height=80)
        self._button_bar.tkraise()  # Über alle anderen Widgets heben
        # Buttons nebeneinander zentriert
        self._redo_btn.pack(side="left", padx=(0, 15), expand=True, anchor="e")
        self._continue_btn.pack(side="left", padx=(15, 0), expand=True, anchor="w")
        logger.info("Button-Leiste eingeblendet (Nochmal + Weiter)")

        # Stress-Test: 15% Redo, 85% Weiter
        if self.app.stress_test_active:
            if random.random() < 0.15:
                delay = random.randint(500, 1500)
                logger.info("Stress-Test: Redo einzelnes Foto")
                self.after(delay, self._on_redo_photo)
            else:
                delay = random.randint(500, 1500)
                logger.info("Stress-Test: Weiter zum nächsten Foto")
                self.after(delay, self._on_continue_photo)

    def _hide_redo_button(self):
        """Versteckt die Button-Leiste"""
        if self._redo_visible:
            self._redo_visible = False
            self._redo_btn.pack_forget()
            self._continue_btn.pack_forget()
            self._button_bar.place_forget()

    def _on_redo_photo(self):
        """Einzelnes Collage-Foto wiederholen"""
        if not self._redo_visible:
            return

        self._hide_redo_button()
        self.photo_display_until = 0  # Display-Timer stoppen

        # Letztes Foto entfernen und Index zurücksetzen
        if self.app.photos_taken:
            self.app.photos_taken.pop()
            self.app.current_photo_index -= 1
            self._update_progress()
            logger.info(f"Foto {self.app.current_photo_index + 1} wird wiederholt")

        # Countdown für das gleiche Foto neu starten
        self.after(300, self._start_countdown)

    def _on_continue_photo(self):
        """Weiter zum nächsten Foto (User hat auf Weiter gedrückt)"""
        if not self._redo_visible:
            return

        self._hide_redo_button()
        self.photo_display_until = 0  # Display-Timer stoppen
        logger.info("User hat Weiter gedrückt")
        self._next_photo_or_finish()

    def _next_photo_or_finish(self):
        """Nächstes Foto oder zum Filter-Screen"""
        self._hide_redo_button()
        logger.info(f"Next: {self.app.current_photo_index}/{self.total_photos}")

        if self.app.current_photo_index < self.total_photos:
            video_key = f"video_after_{self.app.current_photo_index}"
            video_path = self.config.get(video_key, "")

            if video_path and os.path.exists(video_path):
                logger.info(f"Spiele Zwischen-Video: {video_key}")
                self.is_live = False
                self.app.play_video_and_return(video_path, self._continue_after_video)
            else:
                self.after(300, self._start_countdown)
        else:
            logger.info("Alle Fotos -> Filter-Screen")
            self.is_live = False
            self.app.show_screen("filter")

    def _continue_after_video(self):
        """Wird nach Zwischen-Video aufgerufen"""
        self.app.show_screen("session")

    def _on_cancel(self):
        """Abbrechen"""
        logger.info(f"Session abgebrochen bei Foto {self.app.current_photo_index}/{self.total_photos}")
        self.is_live = False
        self.is_countdown_active = False
        self.app.reset_session()
        self.app.show_screen("start")

    def _show_error(self, message: str):
        """Zeigt Fehlermeldung"""
        self.preview_label.configure(
            text=f"❌ {message}",
            font=FONTS["heading"],
            text_color=COLORS["error"]
        )
        self.after(3000, lambda: self.app.show_screen("start"))
