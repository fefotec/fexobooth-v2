"""Video-Screen für Start/End Videos

Spielt ein Video ab und wechselt dann zum nächsten Screen.
Nutzt Canvas + PhotoImage für maximale Kompatibilität (auch auf altem Windows 10).
"""

import customtkinter as ctk
import cv2
import os
import time
import tkinter as tk
from PIL import Image, ImageTk
from typing import TYPE_CHECKING, Optional, Callable

from src.ui.theme import COLORS, FONTS
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class VideoScreen(ctk.CTkFrame):
    """Spielt ein Video ab und wechselt dann zum Ziel-Screen

    Verwendet Canvas + PhotoImage für beste Kompatibilität.
    """

    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color="#000000")
        self.app = app

        self.video_path: Optional[str] = None
        self.next_screen: str = "start"
        self.on_complete: Optional[Callable] = None

        # OpenCV Video
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_playing = False
        self._stop_requested = False
        self._end_called = False

        # FPS-Steuerung
        self.target_fps = 25
        self.frame_delay_ms = 40

        # Für PhotoImage Referenz
        self._photo_image = None
        self._frame_count = 0

        self._setup_ui()

    def _setup_ui(self):
        """Erstellt die UI mit Canvas für Video"""
        # Canvas für Video (Tkinter Canvas, nicht CTk!)
        self.canvas = tk.Canvas(
            self,
            bg="#000000",
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        # Status-Text auf Canvas (für Fehlermeldungen)
        self.status_text_id = None

    def _try_open_video(self, video_path: str) -> Optional[cv2.VideoCapture]:
        """Versucht Video mit verschiedenen Backends zu öffnen"""
        import platform
        logger.debug(f"=== VIDEO OPEN DEBUG ===")
        logger.debug(f"Video-Pfad: {video_path}")
        logger.debug(f"Datei existiert: {os.path.exists(video_path)}")
        logger.debug(f"Dateigröße: {os.path.getsize(video_path) if os.path.exists(video_path) else 'N/A'} bytes")
        logger.debug(f"OpenCV Version: {cv2.__version__}")
        logger.debug(f"Windows: {platform.platform()}")

        backends = [
            (cv2.CAP_MSMF, "MSMF"),
            (cv2.CAP_FFMPEG, "FFMPEG"),
            (cv2.CAP_ANY, "Default"),
        ]

        for backend_id, backend_name in backends:
            try:
                logger.debug(f"Versuche Backend: {backend_name}")
                cap = cv2.VideoCapture(video_path, backend_id)

                if cap.isOpened():
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

                    logger.info(f"Video geöffnet: {backend_name}, {width}x{height}, {fps:.1f}fps, {frames} frames")
                    return cap
            except Exception as e:
                logger.debug(f"Backend {backend_name} Fehler: {e}")

        logger.error("KEIN Backend konnte das Video öffnen!")
        return None

    def play(self, video_path: str, next_screen: str = "start", on_complete: Optional[Callable] = None):
        """Spielt ein Video ab"""
        self.video_path = video_path
        self.next_screen = next_screen
        self.on_complete = on_complete
        self._stop_requested = False
        self._end_called = False
        self._frame_count = 0

        # Status-Text löschen
        if self.status_text_id:
            self.canvas.delete(self.status_text_id)
            self.status_text_id = None

        # Prüfen ob Video existiert
        if not video_path or not os.path.exists(video_path):
            logger.info(f"Video nicht gefunden: {video_path}")
            self._on_video_end()
            return

        try:
            self.cap = self._try_open_video(video_path)

            if self.cap is None:
                logger.error(f"Konnte Video nicht öffnen: {video_path}")
                self._show_error("Video konnte nicht geladen werden")
                self.after(2000, self._on_video_end)
                return

            # FPS
            video_fps = self.cap.get(cv2.CAP_PROP_FPS)
            if video_fps > 0:
                self.target_fps = min(video_fps, 25)
            self.frame_delay_ms = int(1000.0 / self.target_fps)

            logger.info(f"Video startet: {self.target_fps:.1f} FPS, delay={self.frame_delay_ms}ms")

            # WICHTIG: Layout erzwingen
            self.update_idletasks()
            self.update()

            # Canvas-Größe prüfen
            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            logger.debug(f"Canvas-Größe: {canvas_w}x{canvas_h}")

            if canvas_w < 10:
                canvas_w = self.winfo_screenwidth()
                canvas_h = self.winfo_screenheight()
                logger.warning(f"Canvas zu klein, verwende Bildschirm: {canvas_w}x{canvas_h}")

            self.is_playing = True
            self._play_frame()

        except Exception as e:
            logger.error(f"Video-Fehler: {e}", exc_info=True)
            self._on_video_end()

    def _show_error(self, text: str):
        """Zeigt Fehlermeldung auf Canvas"""
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 10:
            canvas_w = 800
            canvas_h = 600
        self.status_text_id = self.canvas.create_text(
            canvas_w // 2, canvas_h // 2,
            text=text,
            fill="#888888",
            font=("Segoe UI", 14)
        )

    def _play_frame(self):
        """Spielt einen Frame ab"""
        if not self.is_playing or self._stop_requested:
            self._cleanup_and_end()
            return

        if self.cap is None:
            self._cleanup_and_end()
            return

        start_time = time.time()

        # Frame lesen
        ret, frame = self.cap.read()

        if not ret or frame is None:
            logger.info(f"Video fertig nach {self._frame_count} Frames")
            self._cleanup_and_end()
            return

        self._frame_count += 1

        try:
            # Canvas-Größe
            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()

            if canvas_w < 10 or canvas_h < 10:
                canvas_w = self.winfo_screenwidth()
                canvas_h = self.winfo_screenheight()

            # Frame-Größe
            frame_h, frame_w = frame.shape[:2]

            # Skalieren (Aspect Ratio beibehalten)
            scale = min(canvas_w / frame_w, canvas_h / frame_h)
            new_w = int(frame_w * scale)
            new_h = int(frame_h * scale)

            if self._frame_count == 1:
                logger.debug(f"Frame 1: {frame_w}x{frame_h} -> {new_w}x{new_h}, Canvas: {canvas_w}x{canvas_h}")

            # Skalieren
            if scale != 1.0:
                frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

            # BGR -> RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # PIL Image
            pil_image = Image.fromarray(frame_rgb)

            # PhotoImage (WICHTIG: Referenz behalten!)
            self._photo_image = ImageTk.PhotoImage(pil_image)

            # Position (zentriert)
            x = (canvas_w - new_w) // 2
            y = (canvas_h - new_h) // 2

            # Canvas leeren und Bild zeichnen
            self.canvas.delete("video_frame")
            self.canvas.create_image(x, y, anchor="nw", image=self._photo_image, tags="video_frame")

            if self._frame_count == 1:
                logger.debug(f"Erster Frame gezeichnet bei ({x}, {y})")

            # Canvas aktualisieren
            self.canvas.update_idletasks()

        except Exception as e:
            if self._frame_count == 1:
                logger.error(f"Frame-Fehler: {e}", exc_info=True)

        # Timing
        elapsed = time.time() - start_time
        delay = max(1, self.frame_delay_ms - int(elapsed * 1000))

        if self.is_playing and not self._stop_requested:
            self.after(delay, self._play_frame)

    def _cleanup_and_end(self):
        """Aufräumen und beenden"""
        logger.debug(f"Cleanup: {self._frame_count} Frames abgespielt")
        self.is_playing = False

        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None

        # Canvas leeren
        self.canvas.delete("video_frame")
        self._photo_image = None

        if not self._end_called:
            self.after(100, self._on_video_end)

    def _on_video_end(self):
        """Video ist fertig"""
        if self._end_called:
            return
        self._end_called = True

        logger.info(f"Video fertig -> {self.next_screen}")

        if self.on_complete:
            try:
                self.on_complete()
            except Exception as e:
                logger.error(f"Callback-Fehler: {e}")

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
        self._end_called = False
        self._stop_requested = False
