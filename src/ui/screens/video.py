"""Video-Screen für Start/End Videos

Spielt ein Video ab und wechselt dann zum nächsten Screen.
Nutzt Windows Media Foundation (MSMF) als primäres Backend für beste Kompatibilität.
Threading verhindert UI-Einfrieren auf schwacher Hardware.
"""

import customtkinter as ctk
import cv2
import os
import threading
import time
import queue
from PIL import Image
from typing import TYPE_CHECKING, Optional, Callable

from src.ui.theme import COLORS, FONTS
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class VideoScreen(ctk.CTkFrame):
    """Spielt ein Video ab und wechselt dann zum Ziel-Screen

    Nutzt Windows Media Foundation für Hardware-beschleunigtes Decoding.
    Fallback auf andere Backends wenn MSMF nicht funktioniert.
    """

    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.app = app

        self.video_path: Optional[str] = None
        self.next_screen: str = "start"
        self.on_complete: Optional[Callable] = None

        # Video-Zustand
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_playing = False
        self._stop_event = threading.Event()
        self._video_thread: Optional[threading.Thread] = None
        self._end_called = False

        # Frame-Queue für Thread-sichere Kommunikation
        self._frame_queue: queue.Queue = queue.Queue(maxsize=3)

        # FPS-Steuerung
        self.target_fps = 25
        self.frame_delay_ms = 40

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
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            fg_color="#000000"
        )
        self.video_label.pack(expand=True, fill="both")

        # Skip-Button (unten rechts)
        self.skip_btn = ctk.CTkButton(
            self,
            text="Überspringen →",
            font=FONTS["small"],
            width=140,
            height=40,
            fg_color=COLORS["bg_medium"],
            hover_color=COLORS["bg_light"],
            corner_radius=8,
            command=self._skip_video
        )
        self.skip_btn.place(relx=0.95, rely=0.95, anchor="se")

    def _try_open_video(self, video_path: str) -> Optional[cv2.VideoCapture]:
        """Versucht das Video mit verschiedenen Backends zu öffnen

        Reihenfolge:
        1. MSMF (Windows Media Foundation) - beste Kompatibilität auf Windows
        2. FFMPEG - falls vorhanden
        3. Default - OpenCV Standard
        """
        backends = [
            (cv2.CAP_MSMF, "MSMF"),
            (cv2.CAP_FFMPEG, "FFMPEG"),
            (cv2.CAP_ANY, "Default"),
        ]

        for backend_id, backend_name in backends:
            try:
                logger.info(f"Versuche {backend_name} Backend...")
                cap = cv2.VideoCapture(video_path, backend_id)

                if cap.isOpened():
                    # Test: Ersten Frame lesen
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.size > 0:
                        # Zurückspulen
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        logger.info(f"Video geöffnet mit {backend_name}")
                        return cap
                    else:
                        logger.warning(f"{backend_name}: Frame-Test fehlgeschlagen")
                        cap.release()
                else:
                    logger.debug(f"{backend_name}: Nicht verfügbar")

            except Exception as e:
                logger.debug(f"{backend_name} Fehler: {e}")

        return None

    def play(self, video_path: str, next_screen: str = "start", on_complete: Optional[Callable] = None):
        """Spielt ein Video ab"""
        self.video_path = video_path
        self.next_screen = next_screen
        self.on_complete = on_complete

        # Vorherige Wiedergabe stoppen
        self._stop_playback()

        # Reset
        self._stop_event.clear()
        self._end_called = False

        # Prüfen ob Video existiert
        if not video_path or not os.path.exists(video_path):
            logger.warning(f"Video nicht gefunden: {video_path}")
            self.after(100, self._on_video_end)
            return

        logger.info(f"Starte Video: {video_path}")

        # Status anzeigen
        self.video_label.configure(text="Video wird geladen...", image=None)
        self.update_idletasks()

        # Video öffnen (im Main-Thread, aber schnell)
        self.cap = self._try_open_video(video_path)

        if self.cap is None:
            logger.error(f"Konnte Video nicht öffnen: {video_path}")
            self.video_label.configure(text="Video konnte nicht geladen werden")
            self.after(2000, self._on_video_end)
            return

        # FPS aus Video lesen
        video_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if video_fps > 0 and video_fps < 120:
            self.target_fps = min(video_fps, 30)
        else:
            self.target_fps = 25

        self.frame_delay_ms = max(25, int(1000 / self.target_fps))

        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / self.target_fps if self.target_fps > 0 else 0
        logger.info(f"Video: {self.target_fps:.0f} FPS, {total_frames} Frames, {duration:.1f}s")

        self.is_playing = True

        # Video-Reader-Thread starten
        self._video_thread = threading.Thread(target=self._video_reader_thread, daemon=True)
        self._video_thread.start()

        # Frame-Display im Main-Thread starten
        self.after(10, self._display_next_frame)

    def _video_reader_thread(self):
        """Liest Frames in separatem Thread"""
        frame_time = 1.0 / self.target_fps
        frames_read = 0

        while not self._stop_event.is_set() and self.cap is not None:
            start_time = time.time()

            try:
                ret, frame = self.cap.read()

                if not ret or frame is None:
                    logger.info(f"Video Ende nach {frames_read} Frames")
                    break

                frames_read += 1

                # Frame in Queue (non-blocking)
                try:
                    self._frame_queue.put_nowait(frame)
                except queue.Full:
                    pass  # Queue voll, Frame überspringen

                # Timing
                elapsed = time.time() - start_time
                sleep_time = max(0.001, frame_time - elapsed)
                time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Reader-Fehler: {e}")
                break

        # Ende-Signal senden
        if not self._stop_event.is_set():
            try:
                self._frame_queue.put(None, timeout=0.5)
            except:
                pass

    def _display_next_frame(self):
        """Zeigt den nächsten Frame an (Main-Thread)"""
        if not self.is_playing or self._stop_event.is_set():
            return

        try:
            frame = self._frame_queue.get_nowait()

            if frame is None:
                # Video zu Ende
                self._cleanup_and_end()
                return

            self._show_frame(frame)

        except queue.Empty:
            pass  # Kein Frame, später erneut versuchen

        # Nächsten Frame planen
        if self.is_playing and not self._stop_event.is_set():
            self.after(self.frame_delay_ms, self._display_next_frame)

    def _show_frame(self, frame):
        """Zeigt einen Frame an"""
        try:
            container_w = self.video_frame.winfo_width()
            container_h = self.video_frame.winfo_height()

            if container_w < 50 or container_h < 50:
                return

            frame_h, frame_w = frame.shape[:2]

            # Skalierung berechnen
            scale = min(container_w / frame_w, container_h / frame_h)
            new_w = max(1, int(frame_w * scale))
            new_h = max(1, int(frame_h * scale))

            # Skalieren
            if new_w != frame_w or new_h != frame_h:
                interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
                frame = cv2.resize(frame, (new_w, new_h), interpolation=interp)

            # BGR -> RGB -> PIL -> CTkImage
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)
            ctk_image = ctk.CTkImage(
                light_image=pil_image,
                dark_image=pil_image,
                size=(new_w, new_h)
            )

            self.video_label.configure(image=ctk_image, text="")
            self.video_label.image = ctk_image

        except Exception as e:
            logger.debug(f"Frame-Anzeige-Fehler: {e}")

    def _skip_video(self):
        """Video überspringen"""
        logger.info("Video übersprungen")
        self._cleanup_and_end()

    def _stop_playback(self):
        """Stoppt die Wiedergabe"""
        self._stop_event.set()
        self.is_playing = False

        # Auf Thread warten
        if self._video_thread and self._video_thread.is_alive():
            self._video_thread.join(timeout=0.3)
        self._video_thread = None

        # Queue leeren
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except:
                break

        # Video schließen
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None

    def _cleanup_and_end(self):
        """Aufräumen und beenden"""
        self._stop_playback()

        try:
            self.video_label.configure(image=None, text="")
        except:
            pass

        self.after(50, self._on_video_end)

    def _on_video_end(self):
        """Video beendet"""
        if self._end_called:
            return
        self._end_called = True

        logger.info(f"Video beendet -> {self.next_screen}")

        if self.on_complete:
            try:
                self.on_complete()
            except Exception as e:
                logger.error(f"Callback-Fehler: {e}")

        self.app.show_screen(self.next_screen)

    def on_hide(self):
        """Screen wird verlassen"""
        self._stop_playback()

    def on_show(self):
        """Screen wird angezeigt"""
        self._end_called = False
        self._stop_event.clear()
