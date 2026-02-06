"""Session-Screen mit Live-View im Template

Optimiert für Lenovo Miix 310 (1280x800)
- Live-View erscheint INNERHALB des Templates
- Countdown zentriert über dem Live-View
- Zeigt welcher Foto-Slot gerade aktiv ist
- Performance-optimiert für schwache Hardware
"""

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import TYPE_CHECKING, Optional
import time
import os

from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class SessionScreen(ctk.CTkFrame):
    """Session-Screen mit Template-basiertem Live-View"""

    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
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

        # Cache für skaliertes Overlay (Performance)
        self._scaled_overlay = None
        self._preview_scale = 1.0

        # Performance-Einstellungen
        self._low_perf = self.config.get("low_performance_mode", {})
        self._frame_counter = 0
        self._skip_frames = self._low_perf.get("skip_frames", 0) if self._low_perf.get("enabled", False) else 0

        # FPS aus Config (default 20 für schwache Hardware)
        cam_settings = self.config.get("camera_settings", {})
        self._target_fps = cam_settings.get("live_view_fps", 20)
        self._frame_delay_ms = max(33, int(1000 / self._target_fps))

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
        main_frame.pack(fill="both", expand=True, padx=15, pady=10)

        # Preview Container
        self.preview_container = ctk.CTkFrame(
            main_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=SIZES["corner_radius"]
        )
        self.preview_container.pack(expand=True, fill="both")

        # Preview Label (für das gerenderte Template mit Live-View)
        self.preview_label = ctk.CTkLabel(
            self.preview_container,
            text="",
            fg_color="transparent"
        )
        self.preview_label.pack(expand=True, fill="both")

    def on_show(self):
        """Screen wird angezeigt"""

        # Prüfen ob wir nach Video fortsetzen (photos_taken nicht leer = Session läuft bereits)
        resuming = len(self.app.photos_taken) > 0

        if resuming:
            logger.info(f"Session fortgesetzt nach Video: Index={self.app.current_photo_index}, photos_taken={len(self.app.photos_taken)}")
            self.total_photos = len(self.app.template_boxes) if self.app.template_boxes else 1
            self.photo_display_until = 0
            self._prepare_preview_overlay()
            self._update_progress()
            self.is_live = True
            self._update_live_view()
            self.after(500, self._start_countdown)
            return

        logger.info("Session gestartet (neu)")

        # Kamera initialisieren
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

        # Overlay für Preview skalieren und cachen
        self._prepare_preview_overlay()

        logger.info(f"Session: {self.total_photos} Fotos zu machen")
        self._update_progress()

        # Live-View starten
        self.is_live = True
        self._update_live_view()

        # Countdown nach kurzer Verzögerung starten
        self.after(500, self._start_countdown)

    def on_hide(self):
        """Screen wird verlassen"""
        self.is_live = False
        self.is_countdown_active = False
        # Cache leeren
        self._scaled_overlay = None

    def _prepare_preview_overlay(self):
        """Bereitet das skalierte Overlay für die LiveView-Vorschau vor (einmalig)"""
        if self.app.overlay_image:
            orig_w, orig_h = self.app.overlay_image.size
        else:
            orig_w = self.config.get("canvas_width", 1800)
            orig_h = self.config.get("canvas_height", 1200)

        # Preview-Größe aus Config (kleiner = schneller)
        low_perf = self.config.get("low_performance_mode", {})
        if low_perf.get("enabled", False):
            max_preview_size = low_perf.get("preview_max_size", 600)
        else:
            max_preview_size = 900

        # Skalierungsfaktor berechnen
        self._preview_scale = min(max_preview_size / orig_w, max_preview_size / orig_h, 1.0)

        # Resampling-Methode (NEAREST ist schneller, LANCZOS sieht besser aus)
        if low_perf.get("enabled", False) and low_perf.get("disable_antialiasing", False):
            resample = Image.Resampling.NEAREST
        else:
            resample = Image.Resampling.LANCZOS

        # Overlay skalieren und cachen
        if self.app.overlay_image:
            new_w = int(orig_w * self._preview_scale)
            new_h = int(orig_h * self._preview_scale)
            self._scaled_overlay = self.app.overlay_image.resize(
                (new_w, new_h), resample
            )
            logger.info(f"Overlay skaliert: {orig_w}x{orig_h} -> {new_w}x{new_h} (scale={self._preview_scale:.2f})")
        else:
            self._scaled_overlay = None

    def _update_progress(self):
        """Aktualisiert die Fortschrittsanzeige"""
        self.progress_label.configure(
            text=f"Foto {self.app.current_photo_index + 1} von {self.total_photos}"
        )

    def _build_template_preview(self, live_frame: Optional[np.ndarray] = None) -> Image.Image:
        """Baut das Template mit Live-View und bereits gemachten Fotos"""
        scale = self._preview_scale

        if self._scaled_overlay:
            canvas_w, canvas_h = self._scaled_overlay.size
        else:
            orig_w = self.config.get("canvas_width", 1800)
            orig_h = self.config.get("canvas_height", 1200)
            canvas_w = int(orig_w * scale)
            canvas_h = int(orig_h * scale)

        canvas = Image.new("RGBA", (canvas_w, canvas_h), (20, 20, 30, 255))

        if self.app.overlay_image:
            orig_w, orig_h = self.app.overlay_image.size
        else:
            orig_w = self.config.get("canvas_width", 1800)
            orig_h = self.config.get("canvas_height", 1200)
        orig_boxes = self.app.template_boxes or [{"box": (0, 0, orig_w-1, orig_h-1), "angle": 0}]

        for i, box_info in enumerate(orig_boxes):
            ox1, oy1, ox2, oy2 = box_info["box"]
            x1 = int(ox1 * scale)
            y1 = int(oy1 * scale)
            x2 = int(ox2 * scale)
            y2 = int(oy2 * scale)
            box_w = x2 - x1 + 1
            box_h = y2 - y1 + 1

            if i < len(self.app.photos_taken):
                photo = self.app.photos_taken[i].copy()
                photo = self._fit_image_to_box(photo, box_w, box_h)
                canvas.paste(photo, (x1, y1))

            elif i == self.app.current_photo_index and live_frame is not None:
                frame = live_frame
                if self.config.get("rotate_180", False):
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                live_img = Image.fromarray(rgb)
                live_img = self._fit_image_to_box(live_img, box_w, box_h)
                canvas.paste(live_img, (x1, y1))

                draw = ImageDraw.Draw(canvas)
                draw.rectangle([x1, y1, x2, y2], outline=(224, 6, 117, 255), width=4)

            else:
                draw = ImageDraw.Draw(canvas)
                draw.rectangle([x1, y1, x2, y2], fill=(40, 40, 50, 255), outline=(60, 60, 70, 255), width=2)

                font_size = max(20, int(60 * scale))
                try:
                    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", font_size)
                except:
                    font = ImageFont.load_default()

                text = str(i + 1)
                bbox = draw.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                tx = x1 + (box_w - tw) // 2
                ty = y1 + (box_h - th) // 2
                draw.text((tx, ty), text, fill=(80, 80, 90, 255), font=font)

        if self._scaled_overlay:
            canvas = Image.alpha_composite(canvas, self._scaled_overlay)

        return canvas

    def _fit_image_to_box(self, img: Image.Image, box_w: int, box_h: int) -> Image.Image:
        """Passt ein Bild in eine Box ein (Cover-Modus) - Performance-optimiert"""
        img_w, img_h = img.size

        # Resampling-Methode wählen
        low_perf = self.config.get("low_performance_mode", {})
        if low_perf.get("enabled", False) and low_perf.get("disable_antialiasing", False):
            resample = Image.Resampling.NEAREST
        else:
            resample = Image.Resampling.BILINEAR  # Schneller als LANCZOS

        img_ratio = img_w / img_h
        box_ratio = box_w / box_h

        if img_ratio > box_ratio:
            new_h = box_h
            new_w = int(new_h * img_ratio)
            img = img.resize((new_w, new_h), resample)
            left = (new_w - box_w) // 2
            img = img.crop((left, 0, left + box_w, box_h))
        else:
            new_w = box_w
            new_h = int(new_w / img_ratio)
            img = img.resize((new_w, new_h), resample)
            top = (new_h - box_h) // 2
            img = img.crop((0, top, box_w, top + box_h))

        return img.convert("RGBA")

    def _update_live_view(self):
        """Aktualisiert die Live-Vorschau (Performance-optimiert)"""
        if not self.is_live:
            return

        if self.show_flash:
            self._display_flash()
            self.after(100, self._update_live_view)
            return

        if self.photo_display_until > 0:
            if time.time() < self.photo_display_until:
                preview = self._build_template_preview(None)
                self._display_preview(preview)
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

        frame = self.app.camera_manager.get_frame()
        preview = self._build_template_preview(frame)

        if self.is_countdown_active and self.countdown_value > 0:
            preview = self._add_countdown_overlay(preview)

        self._display_preview(preview)

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
        """Zeigt das Vorschau-Bild an"""
        if not hasattr(self, '_logged_size'):
            logger.info(f"Preview-Bild: {img.width}x{img.height}")
            self._logged_size = True

        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
        self.preview_label.configure(image=ctk_img)
        self.preview_label.image = ctk_img

    def _display_flash(self):
        """Zeigt Flash-Screen"""
        container_w = self.preview_container.winfo_width() - 10
        container_h = self.preview_container.winfo_height() - 10

        if container_w > 100 and container_h > 100:
            flash = Image.new("RGB", (container_w, container_h), (255, 255, 255))

            flash_image_path = self.config.get("flash_image", "")
            custom_loaded = False

            if flash_image_path and os.path.exists(flash_image_path):
                try:
                    custom_img = Image.open(flash_image_path).convert("RGBA")
                    max_size = int(min(container_w, container_h) * 0.6)
                    custom_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                    img_x = (container_w - custom_img.width) // 2
                    img_y = (container_h - custom_img.height) // 2
                    flash.paste(custom_img, (img_x, img_y), custom_img)
                    custom_loaded = True
                except Exception as e:
                    logger.warning(f"Flash-Bild konnte nicht geladen werden: {e}")

            if not custom_loaded:
                draw = ImageDraw.Draw(flash)
                size = int(min(container_w, container_h) * 0.5)
                cx, cy = container_w // 2, container_h // 2
                radius = size // 2

                draw.ellipse(
                    [cx - radius, cy - radius, cx + radius, cy + radius],
                    fill=(255, 220, 50),
                    outline=(200, 170, 30),
                    width=max(3, size // 30)
                )

                eye_radius = size // 10
                eye_y = cy - size // 6
                eye_offset = size // 4
                draw.ellipse(
                    [cx - eye_offset - eye_radius, eye_y - eye_radius,
                     cx - eye_offset + eye_radius, eye_y + eye_radius],
                    fill=(50, 50, 50)
                )
                draw.ellipse(
                    [cx + eye_offset - eye_radius, eye_y - eye_radius,
                     cx + eye_offset + eye_radius, eye_y + eye_radius],
                    fill=(50, 50, 50)
                )

                mouth_width = size // 2
                mouth_height = size // 4
                mouth_y = cy + size // 10
                draw.arc(
                    [cx - mouth_width // 2, mouth_y - mouth_height // 2,
                     cx + mouth_width // 2, mouth_y + mouth_height],
                    start=0, end=180,
                    fill=(50, 50, 50),
                    width=max(4, size // 20)
                )

            ctk_img = ctk.CTkImage(light_image=flash, size=(container_w, container_h))
            self.preview_label.configure(image=ctk_img)
            self.preview_label.image = ctk_img

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
            try:
                import winsound
                winsound.Beep(800, 100)
            except:
                pass

            self.countdown_value -= 1
            self.after(1000, self._countdown_tick)
        else:
            self.is_countdown_active = False
            self._take_photo()

    def _take_photo(self):
        """Nimmt ein Foto auf"""
        logger.info(f"Foto {self.app.current_photo_index + 1} aufnehmen")

        self.show_flash = True

        try:
            import winsound
            winsound.Beep(1200, 200)
        except:
            pass

        flash_duration = self.config.get("flash_duration", 300)
        self.after(flash_duration, self._capture_photo)

    def _capture_photo(self):
        """Erfasst das Foto"""
        photo = None

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

            # Capture-Auflösung aus Config
            capture_w = cam_settings.get("capture_width", 1280)
            capture_h = cam_settings.get("capture_height", 720)

            # Noch höher wenn Performance-Mode aus
            if not self.config.get("performance_mode", True):
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

        self.show_flash = False

        if photo is not None:
            self.app.photos_taken.append(photo)
            self.app.statistics.record_photo()
            self.after(10, lambda: self._save_photo_async(photo, self.app.current_photo_index + 1))

            display_time = self.config.get("single_display_time", 2)
            self.photo_display_until = time.time() + display_time
            self.app.current_photo_index += 1
            self._update_progress()
        else:
            logger.error("Foto-Aufnahme fehlgeschlagen")
            self._next_photo_or_finish()

    def _save_photo_async(self, photo: Image.Image, index: int):
        """Speichert Foto im Hintergrund"""
        try:
            self.app.local_storage.save_single(photo, suffix=str(index))
        except Exception as e:
            logger.error(f"Fehler beim Speichern: {e}")

    def _next_photo_or_finish(self):
        """Nächstes Foto oder zum Filter-Screen"""
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
        self._resuming_after_video = True
        self.app.show_screen("session")

    def _on_cancel(self):
        """Abbrechen"""
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
