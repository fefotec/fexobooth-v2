"""Session-Screen mit Live-View im Template

Optimiert für Lenovo Miix 310 (1280x800)
- Live-View erscheint INNERHALB des Templates
- Countdown zentriert über dem Live-View
- Zeigt welcher Foto-Slot gerade aktiv ist
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
        # WICHTIG: fill="both" damit das Label den gesamten Container ausfüllt!
        self.preview_label = ctk.CTkLabel(
            self.preview_container,
            text="",
            fg_color="transparent"
        )
        self.preview_label.pack(expand=True, fill="both")
    
    def on_show(self):
        """Screen wird angezeigt"""
        
        # Prüfen ob wir nach Video fortsetzen (photos_taken nicht leer = Session läuft bereits)
        # WICHTIG: Der Screen wird bei show_screen() neu erstellt, daher können wir
        # uns NICHT auf lokale Flags verlassen - nur app.photos_taken ist persistent!
        resuming = len(self.app.photos_taken) > 0
        
        if resuming:
            logger.info(f"Session fortgesetzt nach Video: Index={self.app.current_photo_index}, photos_taken={len(self.app.photos_taken)}")
            # Nur Live-View neu starten, NICHT Session zurücksetzen
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
        live_res = cam_settings.get("live_view_resolution", 640)
        
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

        # Skalierungsfaktor berechnen (max 900px für Performance)
        max_preview_size = 900
        self._preview_scale = min(max_preview_size / orig_w, max_preview_size / orig_h, 1.0)

        # Overlay skalieren und cachen
        if self.app.overlay_image:
            new_w = int(orig_w * self._preview_scale)
            new_h = int(orig_h * self._preview_scale)
            self._scaled_overlay = self.app.overlay_image.resize(
                (new_w, new_h), Image.Resampling.LANCZOS
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
        """Baut das Template mit Live-View und bereits gemachten Fotos

        Nutzt das gecachte skalierte Overlay aus _prepare_preview_overlay().
        """
        # Gecachten Scale-Faktor verwenden
        scale = self._preview_scale

        # Canvas-Größe vom gecachten Overlay oder berechnen
        if self._scaled_overlay:
            canvas_w, canvas_h = self._scaled_overlay.size
        else:
            orig_w = self.config.get("canvas_width", 1800)
            orig_h = self.config.get("canvas_height", 1200)
            canvas_w = int(orig_w * scale)
            canvas_h = int(orig_h * scale)

        # Canvas erstellen (skalierte Größe)
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (20, 20, 30, 255))

        # Original-Boxen holen
        if self.app.overlay_image:
            orig_w, orig_h = self.app.overlay_image.size
        else:
            orig_w = self.config.get("canvas_width", 1800)
            orig_h = self.config.get("canvas_height", 1200)
        orig_boxes = self.app.template_boxes or [{"box": (0, 0, orig_w-1, orig_h-1), "angle": 0}]

        for i, box_info in enumerate(orig_boxes):
            # Box-Koordinaten skalieren
            ox1, oy1, ox2, oy2 = box_info["box"]
            x1 = int(ox1 * scale)
            y1 = int(oy1 * scale)
            x2 = int(ox2 * scale)
            y2 = int(oy2 * scale)
            box_w = x2 - x1 + 1
            box_h = y2 - y1 + 1

            if i < len(self.app.photos_taken):
                # Bereits gemachtes Foto anzeigen
                photo = self.app.photos_taken[i].copy()
                photo = self._fit_image_to_box(photo, box_w, box_h)
                canvas.paste(photo, (x1, y1))

            elif i == self.app.current_photo_index and live_frame is not None:
                # AKTUELLER SLOT: Live-View anzeigen
                # Optional: 180° Rotation (für kopfüber montierte Kameras)
                frame = live_frame
                if self.config.get("rotate_180", False):
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                # Frame spiegeln (Selfie-Modus)
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                live_img = Image.fromarray(rgb)
                live_img = self._fit_image_to_box(live_img, box_w, box_h)
                canvas.paste(live_img, (x1, y1))

                # Rahmen um aktiven Slot (Pink)
                draw = ImageDraw.Draw(canvas)
                draw.rectangle([x1, y1, x2, y2], outline=(224, 6, 117, 255), width=4)

            else:
                # Zukünftiger Slot: Grau mit Nummer
                draw = ImageDraw.Draw(canvas)
                draw.rectangle([x1, y1, x2, y2], fill=(40, 40, 50, 255), outline=(60, 60, 70, 255), width=2)

                # Nummer in der Mitte (Schriftgröße skaliert)
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

        # Gecachtes skaliertes Overlay anwenden (keine Skalierung mehr nötig!)
        if self._scaled_overlay:
            canvas = Image.alpha_composite(canvas, self._scaled_overlay)
        
        return canvas
    
    def _fit_image_to_box(self, img: Image.Image, box_w: int, box_h: int) -> Image.Image:
        """Passt ein Bild in eine Box ein (Cover-Modus)"""
        img_w, img_h = img.size
        
        # Aspect Ratios
        img_ratio = img_w / img_h
        box_ratio = box_w / box_h
        
        if img_ratio > box_ratio:
            # Bild ist breiter -> auf Höhe skalieren
            new_h = box_h
            new_w = int(new_h * img_ratio)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            # Horizontal croppen
            left = (new_w - box_w) // 2
            img = img.crop((left, 0, left + box_w, box_h))
        else:
            # Bild ist höher -> auf Breite skalieren
            new_w = box_w
            new_h = int(new_w / img_ratio)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            # Vertikal croppen
            top = (new_h - box_h) // 2
            img = img.crop((0, top, box_w, top + box_h))
        
        return img.convert("RGBA")
    
    def _update_live_view(self):
        """Aktualisiert die Live-Vorschau"""
        if not self.is_live:
            logger.debug("_update_live_view: is_live=False, stopping")
            return
        
        # Flash-Effekt?
        if self.show_flash:
            self._display_flash()
            self.after(100, self._update_live_view)
            return
        
        # Foto-Anzeige-Phase?
        if self.photo_display_until > 0:
            if time.time() < self.photo_display_until:
                # Foto anzeigen - Template MIT den bisherigen Fotos rendern!
                logger.debug(f"Display-Phase: Zeige Foto {self.app.current_photo_index}")
                preview = self._build_template_preview(None)  # Kein Live-Frame
                self._display_preview(preview)
                self.after(50, self._update_live_view)
                return
            else:
                # Foto-Anzeige vorbei -> weiter
                logger.debug("Display-Phase vorbei, starte nächstes Foto/Finish")
                self.photo_display_until = 0
                self._next_photo_or_finish()
                # WICHTIG: Update-Loop weiterlaufen lassen!
                if self.is_live:
                    self.after(50, self._update_live_view)
                return
        
        # Normaler Live-View mit Template
        frame = self.app.camera_manager.get_frame()
        
        # Template mit Live-View rendern
        preview = self._build_template_preview(frame)
        
        # Countdown-Overlay hinzufügen wenn aktiv
        if self.is_countdown_active and self.countdown_value > 0:
            preview = self._add_countdown_overlay(preview)
        
        # Auf Bildschirm-Größe skalieren
        self._display_preview(preview)
        
        # Nächstes Update
        if self.is_live:
            self.after(33, self._update_live_view)
    
    def _add_countdown_overlay(self, img: Image.Image) -> Image.Image:
        """Fügt ZENTRIERTEN Countdown zum Bild hinzu"""
        img = img.copy()
        draw = ImageDraw.Draw(img)
        
        # Große Schrift für Countdown
        font_size = min(img.width, img.height) // 3
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", font_size)
        except:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)
            except:
                font = ImageFont.load_default()
        
        text = str(self.countdown_value)
        
        # Text-Größe ermitteln
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        # ZENTRIERT positionieren
        x = (img.width - text_w) // 2
        y = (img.height - text_h) // 2
        
        # Schatten für bessere Lesbarkeit
        shadow_offset = 6
        draw.text((x + shadow_offset, y + shadow_offset), text, fill=(0, 0, 0, 200), font=font)
        
        # Countdown-Zahl in Pink
        draw.text((x, y), text, fill=(224, 6, 117, 255), font=font)
        
        return img
    
    def _display_preview(self, img: Image.Image):
        """Zeigt das Vorschau-Bild an.

        Das Bild kommt bereits in Vorschau-Größe (max 900px) aus _build_template_preview.
        Hier wird es nur noch auf die Bildschirm-Größe angepasst falls nötig.
        """
        # Einmalig loggen
        if not hasattr(self, '_logged_size'):
            logger.info(f"Preview-Bild: {img.width}x{img.height}")
            self._logged_size = True

        # CTkImage erstellen - Bild ist bereits in passender Größe
        # CTkImage mit der tatsächlichen Bildgröße verwenden
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
        self.preview_label.configure(image=ctk_img)
        self.preview_label.image = ctk_img
    
    def _display_flash(self):
        """Zeigt Flash-Screen - konfigurierbares Bild oder Standard-Smiley"""
        container_w = self.preview_container.winfo_width() - 10
        container_h = self.preview_container.winfo_height() - 10
        
        if container_w > 100 and container_h > 100:
            # Weißer Hintergrund
            flash = Image.new("RGB", (container_w, container_h), (255, 255, 255))
            
            # Option 1: Eigenes Bild aus Config
            flash_image_path = self.config.get("flash_image", "")
            custom_loaded = False
            
            if flash_image_path and os.path.exists(flash_image_path):
                try:
                    custom_img = Image.open(flash_image_path).convert("RGBA")
                    # Bild skalieren (max 60% der Fläche, Aspect Ratio beibehalten)
                    max_size = int(min(container_w, container_h) * 0.6)
                    custom_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                    # Zentriert einfügen
                    img_x = (container_w - custom_img.width) // 2
                    img_y = (container_h - custom_img.height) // 2
                    flash.paste(custom_img, (img_x, img_y), custom_img)
                    custom_loaded = True
                    logger.debug(f"Flash-Bild geladen: {flash_image_path}")
                except Exception as e:
                    logger.warning(f"Flash-Bild konnte nicht geladen werden: {e}")
            
            # Option 2: Standard-Smiley zeichnen (kein Font nötig!)
            if not custom_loaded:
                draw = ImageDraw.Draw(flash)
                
                # Smiley-Größe
                size = int(min(container_w, container_h) * 0.5)
                cx, cy = container_w // 2, container_h // 2
                radius = size // 2
                
                # Gelber Kreis (Gesicht)
                draw.ellipse(
                    [cx - radius, cy - radius, cx + radius, cy + radius],
                    fill=(255, 220, 50),
                    outline=(200, 170, 30),
                    width=max(3, size // 30)
                )
                
                # Augen
                eye_radius = size // 10
                eye_y = cy - size // 6
                eye_offset = size // 4
                # Linkes Auge
                draw.ellipse(
                    [cx - eye_offset - eye_radius, eye_y - eye_radius,
                     cx - eye_offset + eye_radius, eye_y + eye_radius],
                    fill=(50, 50, 50)
                )
                # Rechtes Auge
                draw.ellipse(
                    [cx + eye_offset - eye_radius, eye_y - eye_radius,
                     cx + eye_offset + eye_radius, eye_y + eye_radius],
                    fill=(50, 50, 50)
                )
                
                # Lächelnder Mund (Bogen)
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
        logger.info(f"Countdown gestartet: {self.countdown_value}, is_live={self.is_live}")
        self._countdown_tick()
    
    def _countdown_tick(self):
        """Ein Countdown-Tick"""
        logger.debug(f"Countdown-Tick: value={self.countdown_value}, active={self.is_countdown_active}, live={self.is_live}")
        
        if not self.is_countdown_active or not self.is_live:
            logger.warning(f"Countdown abgebrochen: active={self.is_countdown_active}, live={self.is_live}")
            return
        
        if self.countdown_value > 0:
            # Beep
            try:
                import winsound
                winsound.Beep(800, 100)
            except:
                pass
            
            self.countdown_value -= 1
            logger.debug(f"Countdown: {self.countdown_value + 1} -> {self.countdown_value}")
            self.after(1000, self._countdown_tick)
        else:
            # Countdown fertig -> Foto aufnehmen
            logger.info("Countdown bei 0 -> Foto aufnehmen")
            self.is_countdown_active = False
            self._take_photo()
    
    def _take_photo(self):
        """Nimmt ein Foto auf"""
        logger.info(f"Foto {self.app.current_photo_index + 1} aufnehmen")
        
        # Flash
        self.show_flash = True
        
        # Shutter-Sound
        try:
            import winsound
            winsound.Beep(1200, 200)
        except:
            pass
        
        # Flash-Dauer aus Config oder 300ms default
        flash_duration = self.config.get("flash_duration", 300)
        self.after(flash_duration, self._capture_photo)
    
    def _capture_photo(self):
        """Erfasst das Foto - Flash bleibt bis Foto da ist"""
        # Flash bleibt AN bis wir das Foto haben!
        
        photo = None
        
        # Canon DSLR: Nutze capture_photo() für volle Auflösung
        if hasattr(self.app.camera_manager, 'capture_photo'):
            logger.info("=== DSLR capture_photo() aufrufen ===")
            try:
                photo = self.app.camera_manager.capture_photo(timeout=10.0)
                if photo:
                    logger.info(f"DSLR Foto erhalten: {photo.size}")
                else:
                    logger.warning("DSLR capture_photo() gab None zurück, Fallback auf Live-View Frame")
            except Exception as e:
                logger.error(f"DSLR capture_photo() Exception: {e}")
                import traceback
                logger.error(traceback.format_exc())
            
            if photo is not None:
                # PIL Image zu numpy für Rotation/Flip
                frame = np.array(photo)
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                # Optional: 180° Rotation
                if self.config.get("rotate_180", False):
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                # Spiegeln (Selfie-Modus)
                frame = cv2.flip(frame, 1)
                
                # Zurück zu PIL Image
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                photo = Image.fromarray(rgb)
        
        # Webcam: Nutze get_frame() / get_high_res_frame()
        if photo is None:
            frame = self.app.camera_manager.get_frame(use_cache=False)
            
            # Optional: High-Res nur wenn Performance-Mode aus
            if not self.config.get("performance_mode", True):
                cam_settings = self.config.get("camera_settings", {})
                high_res = self.app.camera_manager.get_high_res_frame(
                    cam_settings.get("single_photo_width", 1920),
                    cam_settings.get("single_photo_height", 1080)
                )
                if high_res is not None:
                    frame = high_res
            
            if frame is not None:
                # Optional: 180° Rotation (für kopfüber montierte Kameras)
                if self.config.get("rotate_180", False):
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                # Spiegeln (Selfie-Modus) und konvertieren
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                photo = Image.fromarray(rgb)
        
        # Flash AUS - jetzt haben wir das Foto
        self.show_flash = False
        
        if photo is not None:
            # Speichern (async wäre besser, aber erstmal so)
            self.app.photos_taken.append(photo)
            
            # Statistik: Foto erfasst
            self.app.statistics.record_photo()
            
            # Speichern im Hintergrund starten
            self.after(10, lambda: self._save_photo_async(photo, self.app.current_photo_index + 1))
            
            logger.info(f"Foto aufgenommen: {photo.size}")
            
            # Foto kurz anzeigen
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
            logger.debug(f"Foto {index} gespeichert")
        except Exception as e:
            logger.error(f"Fehler beim Speichern: {e}")
    
    def _next_photo_or_finish(self):
        """Nächstes Foto oder zum Filter-Screen"""
        logger.info(f"=== Next: {self.app.current_photo_index}/{self.total_photos}, photos_taken={len(self.app.photos_taken)} ===")
        
        if self.app.current_photo_index < self.total_photos:
            # Prüfen ob Zwischen-Video abgespielt werden soll
            # video_after_1, video_after_2, video_after_3 je nach aktuellem Foto
            video_key = f"video_after_{self.app.current_photo_index}"
            video_path = self.config.get(video_key, "")
            
            if video_path and os.path.exists(video_path):
                # Video abspielen, dann zurück zur Session
                logger.info(f"Spiele Zwischen-Video: {video_key}")
                self.is_live = False
                self.app.play_video_and_return(video_path, self._continue_after_video)
            else:
                # Kein Video, direkt weiter
                logger.info(f"Kein Zwischen-Video für {video_key}, weiter zum nächsten Foto")
                self.after(300, self._start_countdown)
        else:
            # Alle Fotos gemacht!
            logger.info("=== Alle Fotos aufgenommen -> Filter-Screen ===")
            self.is_live = False
            self.app.show_screen("filter")
    
    def _continue_after_video(self):
        """Wird nach Zwischen-Video aufgerufen - setzt Session fort"""
        logger.info("Zwischen-Video fertig, setze Session fort")
        
        # Flag setzen damit on_show() die Session NICHT zurücksetzt
        self._resuming_after_video = True
        
        # Zurück zum Session-Screen wechseln (on_show wird aufgerufen)
        self.app.show_screen("session")
    
    def _on_cancel(self):
        """Abbrechen"""
        logger.info("Session abgebrochen")
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
