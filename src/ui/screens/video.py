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
            fg_color="#000000"
        )
        self.video_label.pack(expand=True, fill="both")

        # Status-Label für Fehlermeldungen
        self.status_label = ctk.CTkLabel(
            self.video_frame,
            text="",
            font=FONTS["normal"],
            text_color="#888888"
        )
        self.status_label.place(relx=0.5, rely=0.5, anchor="center")

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
        self.skip_btn.lower()  # Anfangs verstecken

    def _try_open_video(self, video_path: str) -> Optional[cv2.VideoCapture]:
        """Versucht Video mit verschiedenen Backends zu öffnen

        Reihenfolge:
        1. MSMF (Windows Media Foundation) - nutzt Windows-eigene H.264 Codecs
        2. FFMPEG - universeller Fallback
        3. Default - letzter Versuch
        """
        backends = [
            (cv2.CAP_MSMF, "MSMF (Windows Media Foundation)"),
            (cv2.CAP_FFMPEG, "FFMPEG"),
            (cv2.CAP_ANY, "Default"),
        ]

        for backend_id, backend_name in backends:
            try:
                logger.debug(f"Versuche Backend: {backend_name}")
                cap = cv2.VideoCapture(video_path, backend_id)

                if cap.isOpened():
                    # Testframe lesen um sicherzugehen dass es funktioniert
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.size > 0:
                        # Zurück zum Anfang
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        logger.info(f"Video geöffnet mit Backend: {backend_name}")
                        return cap
                    else:
                        logger.debug(f"Backend {backend_name}: Kann keine Frames lesen")
                        cap.release()
                else:
                    logger.debug(f"Backend {backend_name}: Konnte Video nicht öffnen")

            except Exception as e:
                logger.debug(f"Backend {backend_name} Fehler: {e}")

        return None

    def play(self, video_path: str, next_screen: str = "start", on_complete: Optional[Callable] = None):
        """Spielt ein Video ab

        Args:
            video_path: Pfad zum Video
            next_screen: Screen-Name nach Video-Ende
            on_complete: Callback nach Video-Ende (optional)
        """
        # Vorheriges Video stoppen falls noch aktiv
        self._stop_playback()

        self.video_path = video_path
        self.next_screen = next_screen
        self.on_complete = on_complete
        self._end_called = False
        self._stop_event.clear()

        # Status-Label verstecken
        self.status_label.configure(text="")

        # Prüfen ob Video existiert
        if not video_path or not os.path.exists(video_path):
            logger.info(f"Video nicht gefunden: {video_path}")
            self._on_video_end()
            return

        # Video öffnen mit Backend-Fallback
        self.cap = self._try_open_video(video_path)

        if self.cap is None:
            logger.error(f"Konnte Video nicht öffnen: {video_path}")
            self.status_label.configure(text="Video konnte nicht geladen werden")
            self.skip_btn.lift()  # Skip-Button zeigen
            # Nach 3 Sekunden automatisch weiter
            self.after(3000, self._on_video_end)
            return

        # FPS aus Video lesen
        video_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if video_fps > 0:
            self.target_fps = min(video_fps, 25)  # Max 25 FPS für schwache Hardware
        self.frame_delay_ms = int(1000.0 / self.target_fps)

        logger.info(f"Video gestartet: {video_path} ({self.target_fps:.1f} FPS)")

        self.is_playing = True
        self.skip_btn.lift()  # Skip-Button zeigen

        # Frame-Queue leeren
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break

        # Video-Thread starten für Frame-Lesen
        self._video_thread = threading.Thread(target=self._frame_reader_thread, daemon=True)
        self._video_thread.start()

        # Display-Loop starten
        self._display_next_frame()

    def _frame_reader_thread(self):
        """Liest Frames in separatem Thread (verhindert UI-Freeze)"""
        while not self._stop_event.is_set():
            if self.cap is None:
                break

            try:
                ret, frame = self.cap.read()

                if not ret or frame is None:
                    # Video zu Ende - None in Queue als Signal
                    try:
                        self._frame_queue.put(None, timeout=0.1)
                    except queue.Full:
                        pass
                    break

                # Frame in Queue (blockiert wenn voll - das ist gewollt für Sync)
                try:
                    self._frame_queue.put(frame, timeout=0.05)
                except queue.Full:
                    # Queue voll, Frame überspringen (passiert bei langsamer UI)
                    pass

            except Exception as e:
                logger.debug(f"Frame-Reader Fehler: {e}")
                break

        logger.debug("Frame-Reader Thread beendet")

    def _display_next_frame(self):
        """Zeigt den nächsten Frame aus der Queue an (läuft im Main-Thread)"""
        if not self.is_playing or self._stop_event.is_set():
            self._cleanup_and_end()
            return

        try:
            # Frame aus Queue holen (non-blocking)
            frame = self._frame_queue.get_nowait()

            if frame is None:
                # Video zu Ende
                logger.info("Video fertig (EOF)")
                self._cleanup_and_end()
                return

            self._render_frame(frame)

        except queue.Empty:
            # Kein Frame verfügbar, kurz warten
            pass

        # Nächsten Frame planen
        if self.is_playing and not self._stop_event.is_set():
            self.after(self.frame_delay_ms, self._display_next_frame)

    def _render_frame(self, frame):
        """Rendert einen Frame auf dem Video-Label"""
        try:
            # Container-Größe
            container_w = self.video_frame.winfo_width()
            container_h = self.video_frame.winfo_height()

            if container_w < 10 or container_h < 10:
                return

            # Video-Größe
            frame_h, frame_w = frame.shape[:2]

            # Aspect Ratio beibehalten (Letterbox)
            scale = min(container_w / frame_w, container_h / frame_h)
            new_w = int(frame_w * scale)
            new_h = int(frame_h * scale)

            # Skalieren wenn nötig
            if new_w != frame_w or new_h != frame_h:
                # INTER_AREA für Downscaling, INTER_LINEAR für Upscaling
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
            logger.debug(f"Render-Fehler (ignoriert): {e}")

    def _skip_video(self):
        """Video überspringen"""
        logger.info("Video übersprungen")
        self._stop_event.set()
        self._cleanup_and_end()

    def _stop_playback(self):
        """Stoppt aktive Wiedergabe"""
        self._stop_event.set()
        self.is_playing = False

        # Warten auf Thread-Ende (mit Timeout)
        if self._video_thread and self._video_thread.is_alive():
            self._video_thread.join(timeout=0.5)

        # Video-Capture freigeben
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None

    def _cleanup_and_end(self):
        """Räumt auf und beendet das Video"""
        self._stop_playback()

        # Video-Label leeren
        try:
            self.video_label.configure(image=None)
            self.video_label.image = None
        except:
            pass

        # Skip-Button verstecken
        try:
            self.skip_btn.lower()
        except:
            pass

        # Nur einmal _on_video_end aufrufen
        if not self._end_called:
            self.after(100, self._on_video_end)

    def _on_video_end(self):
        """Video ist fertig"""
        if self._end_called:
            return  # Schon aufgerufen

        self._end_called = True
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
        self._stop_playback()

    def on_show(self):
        """Screen wird angezeigt"""
        # Reset für neues Video
        self._end_called = False
        self._stop_event.clear()
