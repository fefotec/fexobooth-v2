"""Video-Screen für Session-Videos (OpenCV-basiert)

Spielt ein Video ab und wechselt dann zum nächsten Screen.
Verwendet OpenCV statt VLC - kein extra Install nötig!
Optimiert für Performance auf schwacher Hardware.
"""

import customtkinter as ctk
import cv2
import os
import time
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
        self.frame_time = 0.033  # Sekunden pro Frame
        self.last_frame_time = 0
        self.target_width = 0
        self.target_height = 0
        
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
            self.frame_time = 1.0 / self.fps
            
            # Zielgröße einmalig berechnen
            self.target_width = self.winfo_width()
            self.target_height = self.winfo_height()
            if self.target_width < 100:
                self.target_width = 1280
            if self.target_height < 100:
                self.target_height = 800
            
            self.is_playing = True
            self.last_frame_time = time.time()
            
            logger.info(f"🎬 Video gestartet: {video_path} ({self.fps:.1f} FPS)")
            
            # Playback Loop starten (schnell!)
            self._play_loop()
            
        except Exception as e:
            logger.error(f"🎬 Video-Fehler: {e}")
            self._on_video_end()
    
    def _play_loop(self):
        """Optimierter Playback-Loop"""
        if not self.is_playing or self.cap is None:
            return
        
        # Zeit seit letztem Frame
        now = time.time()
        elapsed = now - self.last_frame_time
        
        # Frames überspringen wenn wir hinterherhinken
        frames_to_skip = int(elapsed / self.frame_time) - 1
        if frames_to_skip > 0:
            for _ in range(min(frames_to_skip, 5)):  # Max 5 Frames überspringen
                self.cap.read()
        
        ret, frame = self.cap.read()
        
        if not ret:
            logger.info("🎬 Video zu Ende")
            self._on_video_end()
            return
        
        self.last_frame_time = now
        
        try:
            # Frame skalieren (INTER_NEAREST ist schneller!)
            frame_h, frame_w = frame.shape[:2]
            scale = min(self.target_width / frame_w, self.target_height / frame_h)
            new_w = int(frame_w * scale)
            new_h = int(frame_h * scale)
            
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
            
            # BGR zu RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Direkt zu CTkImage (ohne PIL Zwischenschritt)
            img = Image.fromarray(frame_rgb)
            ctk_img = ctk.CTkImage(light_image=img, size=(new_w, new_h))
            
            # Anzeigen
            self.video_label.configure(image=ctk_img)
            self.video_label.image = ctk_img
            
        except Exception as e:
            pass  # Frame überspringen bei Fehler
        
        # Nächsten Frame so schnell wie möglich (1ms delay für UI-Update)
        if self.is_playing:
            self.after(1, self._play_loop)
    
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
