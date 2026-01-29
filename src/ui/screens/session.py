"""Session-Screen mit Live-View und Countdown"""

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageTk
from typing import TYPE_CHECKING, Optional
import time

from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class SessionScreen(ctk.CTkFrame):
    """Session-Screen mit Kamera-Live-View und Countdown"""
    
    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent)
        self.app = app
        self.config = app.config
        
        # Status
        self.current_photo_index = 0
        self.countdown_value = 5
        self.is_countdown_active = False
        self.is_live = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Erstellt die UI"""
        # Vollbild-Vorschau
        self.preview_label = ctk.CTkLabel(self, text="")
        self.preview_label.pack(fill="both", expand=True)
        
        # Countdown-Overlay
        self.countdown_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=200, weight="bold"),
            text_color="#e00675"
        )
        
        # Abbrechen-Button
        self.cancel_btn = ctk.CTkButton(
            self,
            text=self.config["ui_texts"].get("cancel", "ABBRECHEN"),
            width=150,
            height=50,
            command=self._on_cancel
        )
        self.cancel_btn.place(relx=0.02, rely=0.98, anchor="sw")
    
    def on_show(self):
        """Wird aufgerufen wenn Screen angezeigt wird"""
        logger.info("Session-Screen angezeigt")
        
        # Kamera initialisieren
        cam_settings = self.config.get("camera_settings", {})
        width = cam_settings.get("live_view_resolution", 640)
        height = int(width * 0.75)  # 4:3 Aspect
        
        if not self.app.camera_manager.initialize(
            self.config.get("camera_index", 0),
            width,
            height
        ):
            logger.error("Kamera konnte nicht initialisiert werden")
            self.app.show_screen("start")
            return
        
        # Session starten
        self.app.photos_taken = []
        self.current_photo_index = 0
        self.countdown_value = self.config.get("countdown_time", 5)
        
        # Live-View starten
        self.is_live = True
        self._update_live_view()
        
        # Countdown starten
        self._start_countdown()
    
    def _update_live_view(self):
        """Aktualisiert die Live-Vorschau"""
        if not self.is_live:
            return
        
        frame = self.app.camera_manager.get_frame()
        if frame is not None:
            # Frame spiegeln (Selfie-Modus)
            frame = cv2.flip(frame, 1)
            
            # BGR zu RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Zu PIL konvertieren
            pil_img = Image.fromarray(rgb)
            
            # Skalieren auf Label-Größe
            label_width = self.preview_label.winfo_width() or 800
            label_height = self.preview_label.winfo_height() or 600
            
            # Aspect Ratio beibehalten
            img_ratio = pil_img.width / pil_img.height
            label_ratio = label_width / label_height
            
            if img_ratio > label_ratio:
                new_width = label_width
                new_height = int(label_width / img_ratio)
            else:
                new_height = label_height
                new_width = int(label_height * img_ratio)
            
            pil_img = pil_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Zu CTk-kompatiblem Format
            ctk_img = ctk.CTkImage(light_image=pil_img, size=(new_width, new_height))
            self.preview_label.configure(image=ctk_img)
            self.preview_label.image = ctk_img  # Referenz behalten
        
        # Nächstes Update planen
        if self.is_live:
            self.after(33, self._update_live_view)  # ~30 fps
    
    def _start_countdown(self):
        """Startet den Countdown"""
        self.is_countdown_active = True
        self.countdown_value = self.config.get("countdown_time", 5)
        
        # Countdown-Label anzeigen
        self.countdown_label.place(relx=0.5, rely=0.5, anchor="center")
        self._countdown_tick()
    
    def _countdown_tick(self):
        """Ein Countdown-Tick"""
        if not self.is_countdown_active:
            return
        
        if self.countdown_value > 0:
            self.countdown_label.configure(text=str(self.countdown_value))
            self.countdown_value -= 1
            self.after(1000, self._countdown_tick)
        else:
            # Countdown fertig → Foto aufnehmen
            self.countdown_label.place_forget()
            self._take_photo()
    
    def _take_photo(self):
        """Nimmt ein Foto auf"""
        logger.info(f"Foto aufnehmen: {self.current_photo_index + 1}")
        
        # High-Res Frame holen
        frame = self.app.camera_manager.get_high_res_frame()
        if frame is None:
            frame = self.app.camera_manager.get_frame(use_cache=False)
        
        if frame is not None:
            # Frame spiegeln und zu PIL konvertieren
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            photo = Image.fromarray(rgb)
            
            # Foto speichern
            self.app.photos_taken.append(photo)
            self.current_photo_index += 1
            
            logger.info(f"Foto gespeichert: {photo.size}")
        
        # Nächstes Foto oder weiter
        total_photos = len(self.app.template_boxes) if self.app.template_boxes else 1
        
        if self.current_photo_index < total_photos:
            # Nächstes Foto
            self.after(500, self._start_countdown)
        else:
            # Alle Fotos gemacht → Filter-Screen
            self.is_live = False
            self.app.show_screen("filter")
    
    def _on_cancel(self):
        """Abbrechen gedrückt"""
        logger.info("Session abgebrochen")
        self.is_live = False
        self.is_countdown_active = False
        self.app.reset_session()
        self.app.show_screen("start")
