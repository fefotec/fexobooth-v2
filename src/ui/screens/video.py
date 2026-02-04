"""Video-Screen für Start/End Videos

Spielt ein Video ab und wechselt dann zum nächsten Screen.
Nutzt OpenCV für die Wiedergabe - KEIN VLC erforderlich!
"""

import customtkinter as ctk
import cv2
import os
import threading
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

    Nutzt OpenCV statt VLC - leichtgewichtiger und keine Installation nötig!
    """

    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.app = app

        self.video_path: Optional[str] = None
        self.next_screen: str = "start"
        self.on_complete: Optional[Callable] = None

        # OpenCV Video
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_playing = False
        self._stop_requested = False

        # FPS-Steuerung
        self.target_fps = 30
        self.frame_delay = 1.0 / self.target_fps

        self._setup_ui()

    def _setup_ui(self):
        """Erstellt die UI"""
        # Video-Container (schwarz)
        self.video_frame = ctk.CTkFrame(
            self,
            fg_color="#000000",
            corner_radius=0
        )
        self.video_frame.pack(fill="both", expand=True)

        # Video-Label für Frames
        self.video_label = ctk.CTkLabel(
            self.video_frame,
            text="",
            fg_color="#000000"
        )
        self.video_label.pack(expand=True, fill="both")

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
        self._stop_requested = False

        # Prüfen ob Video existiert
        if not video_path or not os.path.exists(video_path):
            logger.info(f"Video nicht gefunden: {video_path}")
            self._on_video_end()
            return

        try:
            # Video mit OpenCV öffnen
            self.cap = cv2.VideoCapture(video_path)

            if not self.cap.isOpened():
                logger.error(f"Konnte Video nicht öffnen: {video_path}")
                self._on_video_end()
                return

            # FPS aus Video lesen
            video_fps = self.cap.get(cv2.CAP_PROP_FPS)
            if video_fps > 0:
                self.target_fps = min(video_fps, 30)  # Max 30 FPS für Performance
                self.frame_delay = 1.0 / self.target_fps

            logger.info(f"Video gestartet: {video_path} ({self.target_fps:.1f} FPS)")

            self.is_playing = True
            self._play_next_frame()

        except Exception as e:
            logger.error(f"Video-Fehler: {e}")
            self._on_video_end()

    def _play_next_frame(self):
        """Zeigt den nächsten Frame des Videos an"""
        if not self.is_playing or self._stop_requested:
            self._cleanup_and_end()
            return

        if self.cap is None:
            self._cleanup_and_end()
            return

        start_time = time.time()

        # Frame lesen
        ret, frame = self.cap.read()

        if not ret:
            # Video zu Ende
            logger.info("Video fertig (EOF)")
            self._cleanup_and_end()
            return

        try:
            # Frame skalieren auf Container-Größe
            container_w = self.video_frame.winfo_width()
            container_h = self.video_frame.winfo_height()

            if container_w > 10 and container_h > 10:
                # Video-Größe
                frame_h, frame_w = frame.shape[:2]

                # Aspect Ratio beibehalten (Letterbox)
                scale = min(container_w / frame_w, container_h / frame_h)
                new_w = int(frame_w * scale)
                new_h = int(frame_h * scale)

                # Nur skalieren wenn nötig (Performance!)
                if new_w != frame_w or new_h != frame_h:
                    # INTER_AREA für Downscaling (bessere Qualität)
                    # INTER_LINEAR für Upscaling (schneller)
                    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
                    frame = cv2.resize(frame, (new_w, new_h), interpolation=interp)

                # BGR zu RGB
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # PIL Image erstellen
                pil_image = Image.fromarray(rgb_frame)

                # CTkImage erstellen und anzeigen
                ctk_image = ctk.CTkImage(
                    light_image=pil_image,
                    dark_image=pil_image,
                    size=(new_w, new_h)
                )
                self.video_label.configure(image=ctk_image)
                self.video_label.image = ctk_image  # Referenz behalten!

        except Exception as e:
            logger.debug(f"Frame-Fehler (ignoriert): {e}")

        # Nächster Frame mit korrektem Timing
        elapsed = time.time() - start_time
        delay_ms = max(1, int((self.frame_delay - elapsed) * 1000))

        if self.is_playing and not self._stop_requested:
            self.after(delay_ms, self._play_next_frame)

    def _skip_video(self):
        """Video überspringen"""
        logger.info("Video übersprungen")
        self._stop_requested = True
        self._cleanup_and_end()

    def _cleanup_and_end(self):
        """Räumt auf und beendet das Video"""
        self.is_playing = False

        # Video-Capture freigeben
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None

        # Video-Label leeren
        try:
            self.video_label.configure(image=None)
            self.video_label.image = None
        except:
            pass

        # Nur einmal aufrufen
        self.after(100, self._on_video_end)

    def _on_video_end(self):
        """Video ist fertig"""
        if not hasattr(self, '_end_called'):
            self._end_called = True
        else:
            return  # Schon aufgerufen

        logger.info(f"Video fertig, wechsle zu: {self.next_screen}")

        # Callback ausführen
        if self.on_complete:
            try:
                self.on_complete()
            except Exception as e:
                logger.error(f"on_complete Fehler: {e}")

        # Zum nächsten Screen
        self.app.show_screen(self.next_screen)

    def on_hide(self):
        """Screen wird verlassen"""
        self._stop_requested = True
        self.is_playing = False

        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None

    def on_show(self):
        """Screen wird angezeigt"""
        # Reset für neues Video
        self._end_called = False
        self._stop_requested = False
