"""Video-Screen für Session-Videos (OpenCV-basiert)

Spielt ein Video ab und wechselt dann zum nächsten Screen.
Verwendet OpenCV statt VLC - kein extra Install nötig!
"""

import customtkinter as ctk
import cv2
import os
from PIL import Image
from typing import TYPE_CHECKING, Optional, Callable

from src.ui.theme import COLORS, FONTS
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class VideoScreen(ctk.CTkFrame):
    """Spielt ein Video ab und wechselt dann zum Ziel-Screen
    
    Verwendet OpenCV für Video-Playback (kein VLC nötig).
    Unterstützt MP4, AVI, MKV (H.264 empfohlen).
    """
    
    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color="#000000")
        self.app = app
        
        self.video_path: Optional[str] = None
        self.next_screen: str = "start"
        self.on_complete: Optional[Callable] = None
        
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_playing = False
        self.fps = 30
        self.frame_delay = 33  # ms zwischen Frames
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Erstellt die UI"""
        # Video-Label (zeigt die Frames)
        self.video_label = ctk.CTkLabel(
            self,
            text="",
            fg_color="#000000"
        )
        self.video_label.pack(fill="both", expand=True)
        
        # Skip-Button (unten rechts, dezent)
        self.skip_btn = ctk.CTkButton(
            self,
            text="Überspringen →",
            font=FONTS["small"],
            width=120,
            height=35,
            fg_color=COLORS["bg_medium"],
            hover_color=COLORS["bg_light"],
            corner_radius=8,
            command=self._skip_video
        )
        self.skip_btn.place(relx=0.95, rely=0.95, anchor="se")
    
    def play(self, video_path: str, next_screen: str = "start", on_complete: Optional[Callable] = None):
        """Spielt ein Video ab
        
        Args:
            video_path: Pfad zum Video
            next_screen: Screen-Name nach Video-Ende
            on_complete: Callback nach Video-Ende (optional)
        """
        self.video_path = video_path
        self.next_screen = next_screen
        self.on_complete = on_complete
        
        if not video_path or not os.path.exists(video_path):
            logger.warning(f"🎬 Video nicht gefunden: {video_path}")
            self._on_video_end()
            return
        
        try:
            # Video öffnen
            self.cap = cv2.VideoCapture(video_path)
            
            if not self.cap.isOpened():
                logger.error(f"🎬 Video konnte nicht geöffnet werden: {video_path}")
                self._on_video_end()
                return
            
            # FPS ermitteln für korrektes Timing
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            if self.fps <= 0 or self.fps > 120:
                self.fps = 30
            self.frame_delay = int(1000 / self.fps)
            
            self.is_playing = True
            logger.info(f"🎬 Video gestartet: {video_path} ({self.fps:.1f} FPS)")
            
            # Ersten Frame anzeigen und Loop starten
            self._play_next_frame()
            
        except Exception as e:
            logger.error(f"🎬 Video-Fehler: {e}")
            self._on_video_end()
    
    def _play_next_frame(self):
        """Zeigt den nächsten Frame an"""
        if not self.is_playing or self.cap is None:
            return
        
        ret, frame = self.cap.read()
        
        if not ret:
            # Video zu Ende
            logger.info("🎬 Video zu Ende")
            self._on_video_end()
            return
        
        try:
            # Frame auf Bildschirmgröße skalieren
            screen_w = self.winfo_width()
            screen_h = self.winfo_height()
            
            if screen_w > 100 and screen_h > 100:
                # Aspect Ratio beibehalten
                frame_h, frame_w = frame.shape[:2]
                scale = min(screen_w / frame_w, screen_h / frame_h)
                new_w = int(frame_w * scale)
                new_h = int(frame_h * scale)
                
                frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            
            # BGR zu RGB konvertieren
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Zu PIL Image
            img = Image.fromarray(frame_rgb)
            
            # Zu CTkImage
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
            
            # Anzeigen
            self.video_label.configure(image=ctk_img)
            self.video_label.image = ctk_img  # Referenz halten!
            
        except Exception as e:
            logger.debug(f"Frame-Fehler: {e}")
        
        # Nächsten Frame planen
        if self.is_playing:
            self.after(self.frame_delay, self._play_next_frame)
    
    def _skip_video(self):
        """Video überspringen"""
        logger.info("🎬 Video übersprungen")
        self._on_video_end()
    
    def _on_video_end(self):
        """Video ist fertig"""
        if not self.is_playing and self.cap is None:
            return
        
        self.is_playing = False
        
        # OpenCV aufräumen
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None
        
        # Wenn Callback vorhanden: Callback aufrufen, NICHT Screen wechseln
        # (Callback übernimmt die Kontrolle, z.B. bei Zwischen-Videos)
        if self.on_complete:
            logger.info(f"🎬 Video fertig, rufe Callback auf")
            self.on_complete()
            return
        
        # Ohne Callback: Zum nächsten Screen wechseln
        logger.info(f"🎬 Video fertig, wechsle zu: {self.next_screen}")
        self.app.show_screen(self.next_screen)
    
    def on_hide(self):
        """Screen wird verlassen"""
        self.is_playing = False
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None
    
    def on_show(self):
        """Screen wird angezeigt"""
        pass  # Video wird über play() gestartet
