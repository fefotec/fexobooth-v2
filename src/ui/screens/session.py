"""Session-Screen mit Live-View, Countdown und Foto-Aufnahme

Optimiert für Lenovo Miix 310 (1280x800)
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
    """Session-Screen mit Kamera-Live-View und Countdown"""
    
    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.app = app
        self.config = app.config
        
        # Status
        self.current_photo_index = 0
        self.total_photos = 1
        self.countdown_value = 0
        self.is_countdown_active = False
        self.is_live = False
        self.is_showing_photo = False
        self.show_flash = False
        self.photo_display_end_time = 0
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Erstellt die UI - kompakt für 800px Höhe"""
        # Info-Leiste oben (kompakter)
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
        
        # Abbrechen-Button (kompakter)
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
        
        # Hauptbereich mit Live-View (weniger Padding)
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Live-View Container mit Rahmen
        self.preview_container = ctk.CTkFrame(
            main_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=SIZES["corner_radius"],
            border_width=3,
            border_color=COLORS["border"]
        )
        self.preview_container.pack(expand=True, fill="both")
        
        # Preview Label
        self.preview_label = ctk.CTkLabel(
            self.preview_container,
            text="",
            fg_color="transparent"
        )
        self.preview_label.pack(expand=True, fill="both", padx=5, pady=5)
        
        # Countdown-Overlay (wird über dem Preview angezeigt)
        self.countdown_label = ctk.CTkLabel(
            self.preview_container,
            text="",
            font=FONTS["countdown"],
            text_color=COLORS["primary"]
        )
    
    def on_show(self):
        """Screen wird angezeigt"""
        logger.info("Session gestartet")
        
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
        
        # Session initialisieren
        self.app.photos_taken = []
        self.current_photo_index = 0
        self.total_photos = len(self.app.template_boxes) if self.app.template_boxes else 1
        
        # Fortschritt aktualisieren
        self._update_progress()
        
        # Live-View starten
        self.is_live = True
        self._update_live_view()
        
        # Countdown starten nach kurzer Verzögerung
        self.after(500, self._start_countdown)
    
    def on_hide(self):
        """Screen wird verlassen"""
        self.is_live = False
        self.is_countdown_active = False
    
    def _update_progress(self):
        """Aktualisiert die Fortschrittsanzeige"""
        self.progress_label.configure(
            text=f"Foto {self.current_photo_index + 1} von {self.total_photos}"
        )
    
    def _update_live_view(self):
        """Aktualisiert die Live-Vorschau"""
        if not self.is_live:
            return
        
        # Flash-Effekt?
        if self.show_flash:
            self._show_flash_effect()
            self.after(100, self._update_live_view)
            return
        
        # Foto-Anzeige?
        if self.is_showing_photo:
            if time.time() < self.photo_display_end_time:
                self.after(50, self._update_live_view)
                return
            else:
                self.is_showing_photo = False
                self._next_photo_or_finish()
                return
        
        # Normaler Live-View
        frame = self.app.camera_manager.get_frame()
        if frame is not None:
            # Frame spiegeln (Selfie-Modus)
            frame = cv2.flip(frame, 1)
            
            # BGR zu RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            
            # Countdown-Overlay hinzufügen wenn aktiv
            if self.is_countdown_active and self.countdown_value > 0:
                pil_img = self._add_countdown_overlay(pil_img)
            
            # Auf Container-Größe skalieren
            container_width = self.preview_container.winfo_width() - 10
            container_height = self.preview_container.winfo_height() - 10
            
            if container_width > 100 and container_height > 100:
                # Aspect Ratio beibehalten
                img_ratio = pil_img.width / pil_img.height
                container_ratio = container_width / container_height
                
                if img_ratio > container_ratio:
                    new_width = container_width
                    new_height = int(container_width / img_ratio)
                else:
                    new_height = container_height
                    new_width = int(container_height * img_ratio)
                
                pil_img = pil_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Anzeigen
                ctk_img = ctk.CTkImage(light_image=pil_img, size=(new_width, new_height))
                self.preview_label.configure(image=ctk_img)
                self.preview_label.image = ctk_img
        
        # Nächstes Update
        if self.is_live:
            self.after(33, self._update_live_view)  # ~30 fps
    
    def _add_countdown_overlay(self, img: Image.Image) -> Image.Image:
        """Fügt Countdown-Zahl zum Bild hinzu"""
        draw = ImageDraw.Draw(img)
        
        # Font laden
        try:
            # Windows Fonts
            font_paths = [
                "C:/Windows/Fonts/segoeui.ttf",
                "C:/Windows/Fonts/arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc"
            ]
            font = None
            for fp in font_paths:
                if os.path.exists(fp):
                    font = ImageFont.truetype(fp, min(img.width, img.height) // 2)
                    break
            if not font:
                font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()
        
        text = str(self.countdown_value)
        
        # Text-Größe ermitteln
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (img.width - text_width) // 2
        y = (img.height - text_height) // 2
        
        # Schatten
        shadow_offset = 4
        draw.text((x + shadow_offset, y + shadow_offset), text, fill=(0, 0, 0, 180), font=font)
        
        # Text in Pink
        draw.text((x, y), text, fill=(224, 6, 117, 255), font=font)
        
        return img
    
    def _start_countdown(self):
        """Startet den Countdown"""
        self.is_countdown_active = True
        self.countdown_value = self.config.get("countdown_time", 5)
        self._countdown_tick()
    
    def _countdown_tick(self):
        """Ein Countdown-Tick"""
        if not self.is_countdown_active or not self.is_live:
            return
        
        if self.countdown_value > 0:
            # Sound abspielen (Windows)
            try:
                import winsound
                winsound.Beep(800, 100)
            except:
                pass
            
            self.countdown_value -= 1
            self.after(1000, self._countdown_tick)
        else:
            # Countdown fertig → Foto aufnehmen
            self.is_countdown_active = False
            self._take_photo()
    
    def _take_photo(self):
        """Nimmt ein Foto auf"""
        logger.info(f"Foto {self.current_photo_index + 1} aufnehmen")
        
        # Flash-Effekt
        self.show_flash = True
        
        # Sound
        try:
            import winsound
            winsound.Beep(1200, 200)
        except:
            pass
        
        # Kurz warten für Flash
        self.after(150, self._capture_photo)
    
    def _capture_photo(self):
        """Erfasst das eigentliche Foto"""
        self.show_flash = False
        
        # High-Res Frame holen
        cam_settings = self.config.get("camera_settings", {})
        frame = self.app.camera_manager.get_high_res_frame(
            cam_settings.get("single_photo_width", 1920),
            cam_settings.get("single_photo_height", 1080)
        )
        
        if frame is None:
            frame = self.app.camera_manager.get_frame(use_cache=False)
        
        if frame is not None:
            # Frame spiegeln und zu PIL konvertieren
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            photo = Image.fromarray(rgb)
            
            # Foto speichern
            self.app.photos_taken.append(photo)
            
            # Einzelfoto auch lokal speichern
            self.app.local_storage.save_single(photo, suffix=str(self.current_photo_index + 1))
            
            # Auf USB kopieren wenn verfügbar
            # (wird in local_storage.save_single gehandhabt)
            
            logger.info(f"Foto gespeichert: {photo.size}")
            
            # Foto kurz anzeigen
            self._show_captured_photo(photo)
        else:
            logger.error("Konnte kein Foto aufnehmen")
            self._next_photo_or_finish()
    
    def _show_flash_effect(self):
        """Zeigt einen weißen Flash"""
        # Weißes Bild erstellen
        container_width = self.preview_container.winfo_width() - 10
        container_height = self.preview_container.winfo_height() - 10
        
        if container_width > 100 and container_height > 100:
            white_img = Image.new("RGB", (container_width, container_height), (255, 255, 255))
            ctk_img = ctk.CTkImage(light_image=white_img, size=(container_width, container_height))
            self.preview_label.configure(image=ctk_img)
            self.preview_label.image = ctk_img
    
    def _show_captured_photo(self, photo: Image.Image):
        """Zeigt das aufgenommene Foto kurz an"""
        self.is_showing_photo = True
        display_time = self.config.get("single_display_time", 2)
        self.photo_display_end_time = time.time() + display_time
        
        # Foto anzeigen
        container_width = self.preview_container.winfo_width() - 10
        container_height = self.preview_container.winfo_height() - 10
        
        if container_width > 100 and container_height > 100:
            display_photo = photo.copy()
            display_photo.thumbnail((container_width, container_height), Image.Resampling.LANCZOS)
            
            ctk_img = ctk.CTkImage(light_image=display_photo, size=display_photo.size)
            self.preview_label.configure(image=ctk_img)
            self.preview_label.image = ctk_img
        
        self.current_photo_index += 1
        self._update_progress()
    
    def _next_photo_or_finish(self):
        """Nächstes Foto oder zum Filter-Screen"""
        if self.current_photo_index < self.total_photos:
            # Nächstes Foto
            self.after(300, self._start_countdown)
        else:
            # Alle Fotos gemacht
            logger.info("Alle Fotos aufgenommen")
            self.is_live = False
            self.app.show_screen("filter")
    
    def _on_cancel(self):
        """Abbrechen gedrückt"""
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
