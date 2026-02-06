"""Video-Screen für Start/End Videos

Spielt ein Video ab und wechselt dann zum nächsten Screen.
Primär: VLC für Hardware-beschleunigtes Decoding (funktioniert auf schwacher Hardware wie Miix 310).
Fallback: OpenCV wenn VLC nicht verfügbar.
"""

import customtkinter as ctk
import os
import sys
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

# VLC Plugin-Pfad setzen (für gebündelten Modus mit PyInstaller)
def _setup_vlc_path():
    """Setzt VLC_PLUGIN_PATH für gebündeltes VLC"""
    if os.environ.get("VLC_PLUGIN_PATH"):
        return  # Bereits gesetzt

    # PyInstaller: _MEIPASS ist das Temp-Verzeichnis bei --onefile
    # oder das exe-Verzeichnis bei --onedir
    base_path = getattr(sys, '_MEIPASS', None)
    if base_path is None:
        # Nicht gebündelt - normaler Python-Modus
        base_path = os.path.dirname(os.path.abspath(sys.argv[0]))

    # VLC Plugins im gleichen Verzeichnis wie die .exe suchen
    for candidate in [
        os.path.join(base_path, "vlc", "plugins"),
        os.path.join(base_path, "plugins"),
        os.path.join(os.path.dirname(base_path), "vlc", "plugins"),
    ]:
        if os.path.isdir(candidate):
            os.environ["VLC_PLUGIN_PATH"] = candidate
            logger.info(f"VLC Plugin-Pfad gesetzt: {candidate}")

            # Auch libvlc.dll Pfad zum PATH hinzufügen
            vlc_dir = os.path.dirname(candidate)
            if vlc_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = vlc_dir + os.pathsep + os.environ.get("PATH", "")
            return

_setup_vlc_path()

# VLC-Verfügbarkeit prüfen
_vlc_available = False
try:
    import vlc as _vlc
    _vlc_available = True
    logger.info("VLC-Bibliothek verfügbar - Hardware-beschleunigtes Video aktiv")
except ImportError:
    logger.warning("python-vlc nicht installiert - Fallback auf OpenCV")
except Exception as e:
    logger.warning(f"VLC konnte nicht geladen werden: {e} - Fallback auf OpenCV")


class VideoScreen(ctk.CTkFrame):
    """Spielt ein Video ab und wechselt dann zum Ziel-Screen

    Primär VLC (Hardware-Decoding), Fallback OpenCV.
    """

    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.app = app

        self.video_path: Optional[str] = None
        self.next_screen: str = "start"
        self.on_complete: Optional[Callable] = None

        # Video-Zustand
        self.is_playing = False
        self._end_called = False
        self._stop_event = threading.Event()

        # VLC-spezifisch
        self._vlc_instance = None
        self._vlc_player = None
        self._vlc_check_id = None

        # OpenCV-Fallback
        self.cap = None
        self._video_thread: Optional[threading.Thread] = None
        self._frame_queue: queue.Queue = queue.Queue(maxsize=3)
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

        # Video-Label für Frames (OpenCV-Modus) / Hintergrund (VLC-Modus)
        self.video_label = ctk.CTkLabel(
            self.video_frame,
            text="",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            fg_color="#000000"
        )
        self.video_label.pack(expand=True, fill="both")


    # ─────────────────────────────────────────────
    # Öffentliche API
    # ─────────────────────────────────────────────

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

        # Label leeren (schwarzer Screen während Video lädt)
        self.video_label.configure(text="", image=None)
        self.update_idletasks()

        # VLC bevorzugen, OpenCV als Fallback
        if _vlc_available and sys.platform == "win32":
            success = self._play_vlc(video_path)
            if success:
                return
            logger.warning("VLC-Wiedergabe fehlgeschlagen, Fallback auf OpenCV")

        self._play_opencv(video_path)

    def on_hide(self):
        """Screen wird verlassen"""
        self._stop_playback()

    def on_show(self):
        """Screen wird angezeigt"""
        self._end_called = False
        self._stop_event.clear()

    # ─────────────────────────────────────────────
    # VLC-Wiedergabe (Hardware-beschleunigt)
    # ─────────────────────────────────────────────

    def _play_vlc(self, video_path: str) -> bool:
        """Spielt Video mit VLC ab (Hardware-Decoding)

        Returns:
            True wenn erfolgreich gestartet, False bei Fehler
        """
        try:
            # Absoluten Pfad sicherstellen
            abs_path = os.path.abspath(video_path)
            logger.info(f"VLC: Öffne {abs_path}")

            # VLC-Instanz mit Hardware-Decoding
            args = [
                "--no-xlib",
                "--quiet",
                "--no-video-title-show",
                "--no-snapshot-preview",
                "--avcodec-hw=dxva2",  # DirectX Video Acceleration
            ]
            self._vlc_instance = _vlc.Instance(args)
            self._vlc_player = self._vlc_instance.media_player_new()

            # Media erstellen
            media = self._vlc_instance.media_new(abs_path)
            media.add_option("no-video-title-show")
            self._vlc_player.set_media(media)

            # Warten bis das Fenster sichtbar und bereit ist
            self.update_idletasks()
            self.after(50, lambda: self._vlc_embed_and_play(abs_path))

            return True

        except Exception as e:
            logger.error(f"VLC-Initialisierung fehlgeschlagen: {e}")
            self._cleanup_vlc()
            return False

    def _vlc_embed_and_play(self, video_path: str):
        """Bettet VLC in das Tkinter-Fenster ein und startet Wiedergabe"""
        try:
            if self._vlc_player is None:
                return

            # Window-Handle des video_frame holen
            hwnd = self.video_label.winfo_id()
            if not hwnd:
                logger.error("VLC: Kein Window-Handle verfügbar")
                self._cleanup_vlc()
                self._play_opencv(video_path)
                return

            logger.info(f"VLC: Einbetten in HWND {hwnd}")
            self._vlc_player.set_hwnd(hwnd)

            # Text ausblenden
            self.video_label.configure(text="")

            # Wiedergabe starten
            result = self._vlc_player.play()
            if result == -1:
                logger.error("VLC: play() fehlgeschlagen")
                self._cleanup_vlc()
                self._play_opencv(video_path)
                return

            self.is_playing = True
            logger.info("VLC: Wiedergabe gestartet")

            # Regelmäßig prüfen ob Video zu Ende
            self._vlc_check_id = self.after(200, self._vlc_check_status)

        except Exception as e:
            logger.error(f"VLC-Embed fehlgeschlagen: {e}")
            self._cleanup_vlc()
            self._play_opencv(video_path)

    def _vlc_check_status(self):
        """Prüft ob VLC-Wiedergabe noch läuft"""
        if not self.is_playing or self._stop_event.is_set():
            return

        if self._vlc_player is None:
            self._cleanup_and_end()
            return

        try:
            state = self._vlc_player.get_state()

            if state == _vlc.State.Ended:
                logger.info("VLC: Video zu Ende")
                self._cleanup_and_end()
                return
            elif state == _vlc.State.Error:
                logger.error("VLC: Wiedergabe-Fehler")
                self._cleanup_and_end()
                return
            elif state == _vlc.State.Stopped:
                logger.info("VLC: Wiedergabe gestoppt")
                self._cleanup_and_end()
                return

            # Weiter prüfen
            self._vlc_check_id = self.after(200, self._vlc_check_status)

        except Exception as e:
            logger.error(f"VLC Status-Check Fehler: {e}")
            self._cleanup_and_end()

    def _cleanup_vlc(self):
        """VLC-Ressourcen aufräumen"""
        if self._vlc_check_id is not None:
            try:
                self.after_cancel(self._vlc_check_id)
            except:
                pass
            self._vlc_check_id = None

        # VLC-Cleanup in Thread - stop()/release() können blockieren
        player = self._vlc_player
        instance = self._vlc_instance
        self._vlc_player = None
        self._vlc_instance = None

        if player or instance:
            def _release():
                if player is not None:
                    try:
                        # Nur stoppen wenn noch am Spielen
                        state = player.get_state()
                        if state in (_vlc.State.Playing, _vlc.State.Paused, _vlc.State.Opening):
                            player.stop()
                    except:
                        pass
                    try:
                        player.release()
                    except:
                        pass
                if instance is not None:
                    try:
                        instance.release()
                    except:
                        pass
                logger.debug("VLC-Ressourcen freigegeben")

            cleanup_thread = threading.Thread(target=_release, daemon=True)
            cleanup_thread.start()

            # Nur synchron warten wenn Callback existiert (= Zwischen-Video)
            # Dann muss VLC DXVA2 freigeben bevor Kamera startet
            # Bei Start/End-Videos (kein Callback) ist fire-and-forget OK
            if self.on_complete:
                cleanup_thread.join(timeout=1.0)
                if cleanup_thread.is_alive():
                    logger.warning("VLC-Cleanup dauert >1s - fahre fort")

    # ─────────────────────────────────────────────
    # OpenCV-Fallback
    # ─────────────────────────────────────────────

    def _play_opencv(self, video_path: str):
        """Spielt Video mit OpenCV ab (Software-Decoding, Fallback)"""
        import cv2

        self.cap = self._try_open_video(video_path)

        if self.cap is None:
            logger.error(f"OpenCV: Konnte Video nicht öffnen: {video_path}")
            self.video_label.configure(text="Video konnte nicht geladen werden")
            self.after(2000, self._on_video_end)
            return

        # FPS aus Video lesen
        video_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if 0 < video_fps < 120:
            self.target_fps = min(video_fps, 30)
        else:
            self.target_fps = 25

        self.frame_delay_ms = max(25, int(1000 / self.target_fps))

        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / self.target_fps if self.target_fps > 0 else 0
        logger.info(f"OpenCV: {self.target_fps:.0f} FPS, {total_frames} Frames, {duration:.1f}s")

        self.is_playing = True

        # Video-Reader-Thread starten
        self._video_thread = threading.Thread(target=self._video_reader_thread, daemon=True)
        self._video_thread.start()

        # Frame-Display im Main-Thread starten
        self.after(10, self._display_next_frame)

    def _try_open_video(self, video_path: str):
        """Versucht das Video mit verschiedenen Backends zu öffnen"""
        import cv2

        backends = [
            (cv2.CAP_MSMF, "MSMF"),
            (cv2.CAP_FFMPEG, "FFMPEG"),
            (cv2.CAP_ANY, "Default"),
        ]

        for backend_id, backend_name in backends:
            try:
                logger.info(f"OpenCV: Versuche {backend_name} Backend...")
                cap = cv2.VideoCapture(video_path, backend_id)

                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.size > 0:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        logger.info(f"OpenCV: Video geöffnet mit {backend_name}")
                        return cap
                    else:
                        logger.warning(f"OpenCV: {backend_name} Frame-Test fehlgeschlagen")
                        cap.release()
                else:
                    logger.debug(f"OpenCV: {backend_name} nicht verfügbar")

            except Exception as e:
                logger.debug(f"OpenCV: {backend_name} Fehler: {e}")

        return None

    def _video_reader_thread(self):
        """Liest Frames in separatem Thread (OpenCV)"""
        import cv2
        frame_time = 1.0 / self.target_fps
        frames_read = 0

        while not self._stop_event.is_set() and self.cap is not None:
            start_time = time.time()

            try:
                ret, frame = self.cap.read()

                if not ret or frame is None:
                    logger.info(f"OpenCV: Video Ende nach {frames_read} Frames")
                    break

                frames_read += 1

                try:
                    self._frame_queue.put_nowait(frame)
                except queue.Full:
                    pass

                elapsed = time.time() - start_time
                sleep_time = max(0.001, frame_time - elapsed)
                time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"OpenCV: Reader-Fehler: {e}")
                break

        if not self._stop_event.is_set():
            try:
                self._frame_queue.put(None, timeout=0.5)
            except:
                pass

    def _display_next_frame(self):
        """Zeigt den nächsten Frame an (Main-Thread, OpenCV)"""
        if not self.is_playing or self._stop_event.is_set():
            return

        try:
            frame = self._frame_queue.get_nowait()

            if frame is None:
                self._cleanup_and_end()
                return

            self._show_frame(frame)

        except queue.Empty:
            pass

        if self.is_playing and not self._stop_event.is_set():
            self.after(self.frame_delay_ms, self._display_next_frame)

    def _show_frame(self, frame):
        """Zeigt einen Frame an (OpenCV)"""
        import cv2
        try:
            container_w = self.video_frame.winfo_width()
            container_h = self.video_frame.winfo_height()

            if container_w < 50 or container_h < 50:
                return

            frame_h, frame_w = frame.shape[:2]

            scale = min(container_w / frame_w, container_h / frame_h)
            new_w = max(1, int(frame_w * scale))
            new_h = max(1, int(frame_h * scale))

            if new_w != frame_w or new_h != frame_h:
                interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
                frame = cv2.resize(frame, (new_w, new_h), interpolation=interp)

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
            logger.debug(f"OpenCV: Frame-Anzeige-Fehler: {e}")

    # ─────────────────────────────────────────────
    # Gemeinsame Methoden
    # ─────────────────────────────────────────────

    def _stop_playback(self):
        """Stoppt die Wiedergabe (VLC oder OpenCV)"""
        self._stop_event.set()
        self.is_playing = False

        # VLC aufräumen
        self._cleanup_vlc()

        # OpenCV aufräumen
        if self._video_thread and self._video_thread.is_alive():
            self._video_thread.join(timeout=0.3)
        self._video_thread = None

        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except:
                break

        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None

    def _cleanup_and_end(self):
        """Aufräumen und beenden"""
        if self._end_called:
            return

        self._stop_playback()

        try:
            self.video_label.configure(image=None, text="")
        except:
            pass

        # Direkt aufrufen statt self.after() - vermeidet Probleme mit zerstörten Widgets
        self._on_video_end()

    def _on_video_end(self):
        """Video beendet"""
        if self._end_called:
            return
        self._end_called = True

        logger.info(f"Video beendet -> {self.next_screen}")

        if self.on_complete:
            # Callback übernimmt Navigation (z.B. _continue_after_video -> show_screen)
            try:
                self.on_complete()
            except Exception as e:
                logger.error(f"Callback-Fehler: {e}")
                # Fallback bei Fehler: normaler Screen-Wechsel
                self.app.show_screen(self.next_screen)
        else:
            # Kein Callback -> normaler Screen-Wechsel (z.B. video_start -> session)
            self.app.show_screen(self.next_screen)
