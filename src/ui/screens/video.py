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
from src.ui.vlc_player import PersistentVlcPlayer
from src.utils.logging import get_logger, is_developer_mode

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


_VLC_ARGS = [
    "--no-xlib",
    "--quiet",
    "--no-video-title-show",
    "--no-snapshot-preview",
    "--avcodec-hw=dxva2",
]
_VLC_WARMUP_TIMEOUT_SECONDS = 120.0
_vlc_owner = (
    PersistentVlcPlayer(_vlc, logger, _VLC_ARGS, max_generations=2)
    if _vlc_available
    else None
)

# VLC Warmup (verhindert 57s Freeze beim ersten Video auf schwacher Hardware)
_vlc_warm = not _vlc_available  # Wenn VLC nicht verfügbar, ist "warm" irrelevant
_vlc_warmup_thread = None
_vlc_warmup_started_at = None
_vlc_warmup_timed_out = False
_vlc_metrics_process = None


def warmup_vlc():
    """Wärmt VLC vor (lädt Plugin-Cache im Hintergrund).

    Auf schwacher Hardware dauert die erste VLC-Instance-Erstellung ~57s.
    Durch Vorwärmen beim App-Start ist das erste Video sofort abspielbar.
    """
    global _vlc_warm, _vlc_warmup_thread, _vlc_warmup_started_at

    if not _vlc_available or _vlc_warm:
        return

    if _vlc_warmup_thread is not None and _vlc_warmup_thread.is_alive():
        return

    def _do_warmup():
        global _vlc_warm, _vlc_warmup_thread
        try:
            logger.info("VLC-Warmup: Lade Plugin-Cache...")
            start = time.time()
            ready = _vlc_owner.prepare()
            elapsed = time.time() - start
            if ready:
                logger.info(f"VLC-Warmup: Persistenter Player bereit in {elapsed:.1f}s")
            else:
                logger.warning(f"VLC-Warmup: Kein Player nach {elapsed:.1f}s - OpenCV bleibt verfügbar")
        except Exception as e:
            logger.warning(f"VLC-Warmup fehlgeschlagen: {e}")
        _vlc_warm = True
        _vlc_warmup_thread = None

    _vlc_warmup_started_at = time.monotonic()
    _vlc_warmup_thread = threading.Thread(target=_do_warmup, daemon=True, name="VLC-Warmup")
    _vlc_warmup_thread.start()
    logger.info("VLC-Warmup: Gestartet im Hintergrund")


def is_vlc_warm() -> bool:
    """Prüft ob VLC bereit ist oder nach endlicher Wartezeit ausweicht."""
    global _vlc_warm, _vlc_warmup_timed_out

    if (
        not _vlc_warm
        and _vlc_warmup_started_at is not None
        and time.monotonic() - _vlc_warmup_started_at >= _VLC_WARMUP_TIMEOUT_SECONDS
    ):
        _vlc_warmup_timed_out = True
        _vlc_warm = True
        if _vlc_owner is not None:
            _vlc_owner.disable("warmup_timeout")
        logger.error(
            "VLC-LIFECYCLE warmup_timeout seconds=%.0f fallback=opencv",
            _VLC_WARMUP_TIMEOUT_SECONDS,
        )
    return _vlc_warm


def shutdown_vlc():
    """Gibt das eine VLC-Paar beim App-Ende bestmoeglich und ohne Warten frei."""
    if _vlc_owner is not None:
        _vlc_owner.close()


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
        self._playback_generation = 0
        self._scheduled_ids = set()
        self._backend = None

        # VLC-spezifisch
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

        # Getrennte Ausgabeflaechen: Ein im nativen Abbau haengender VLC-
        # Ausgang darf den sichtbaren OpenCV-Fallback nicht ueberdecken.
        self.vlc_surface = ctk.CTkFrame(
            self.video_frame,
            fg_color="#000000",
            corner_radius=0,
        )

        # Video-Label für Frames (OpenCV-Modus)
        self.video_label = ctk.CTkLabel(
            self.video_frame,
            text="",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            fg_color="#000000"
        )
        self.video_label.pack_forget()


    # ─────────────────────────────────────────────
    # Öffentliche API
    # ─────────────────────────────────────────────

    def play(self, video_path: str, next_screen: str = "start", on_complete: Optional[Callable] = None):
        """Spielt ein Video ab"""
        self._stop_playback("new_play")

        self.video_path = video_path
        self.next_screen = next_screen
        self.on_complete = on_complete

        # Reset
        self._stop_event = threading.Event()
        self._frame_queue = queue.Queue(maxsize=3)
        self._end_called = False
        token = self._playback_generation

        # Prüfen ob Video existiert
        if not video_path or not os.path.exists(video_path):
            logger.warning(f"Video nicht gefunden: {video_path}")
            self._schedule(100, lambda: self._on_video_end(token), token)
            return

        logger.info(f"Starte Video: {video_path}")

        # Label leeren (schwarzer Screen während Video lädt)
        self._hide_video_surfaces()
        self.video_label.configure(text="", image=None)
        self.update_idletasks()

        # VLC bevorzugen, OpenCV als Fallback
        if _vlc_available and sys.platform == "win32":
            if not is_vlc_warm():
                # Warmup noch nicht fertig - warten mit Ladeanimation
                self._wait_for_vlc_warmup(video_path, token)
                return
            success = self._play_vlc(video_path, token)
            if success:
                return
            logger.warning("VLC-Wiedergabe fehlgeschlagen, Fallback auf OpenCV")

        self._play_opencv(video_path, token)

    def on_hide(self):
        """Screen wird verlassen"""
        self._stop_playback("screen_hidden")

    def on_show(self):
        """Screen wird angezeigt"""
        # Der komplette Wiedergabe-Reset passiert ausschliesslich in play().
        pass

    def _wait_for_vlc_warmup(self, video_path: str, token: int):
        """Wartet auf VLC-Warmup mit subtiler Ladeanimation"""
        warmup_vlc()
        self._warmup_counter = 0
        self._show_opencv_surface()
        logger.info("VLC-Warmup noch nicht fertig - warte...")

        def _check():
            if not self._is_current(token):
                return

            if is_vlc_warm():
                self.video_label.configure(text="")
                success = self._play_vlc(video_path, token)
                if success:
                    return
                logger.warning("VLC nach Warmup fehlgeschlagen, Fallback auf OpenCV")
                self._play_opencv(video_path, token)
            else:
                # Subtile Ladeanimation (pulsierende Punkte)
                self._warmup_counter += 1
                dots = "·" * ((self._warmup_counter % 3) + 1)
                self.video_label.configure(
                    text=dots,
                    font=("Segoe UI", 24),
                    text_color="#303040"
                )
                self._schedule(500, _check, token)

        _check()

    # ─────────────────────────────────────────────
    # VLC-Wiedergabe (Hardware-beschleunigt)
    # ─────────────────────────────────────────────

    def _play_vlc(self, video_path: str, token: int) -> bool:
        """Plant die Wiedergabe auf dem appweit persistenten VLC-Player."""
        try:
            if not self._is_current(token) or _vlc_owner is None:
                return False

            abs_path = os.path.abspath(video_path)
            logger.info(f"VLC: Öffne {abs_path}")

            status = _vlc_owner.snapshot()
            if not status["has_player"]:
                # Ein Wiederaufbau findet nie im Tk-Hauptfaden statt. Der
                # aktuelle Clip nutzt sofort OpenCV.
                _vlc_owner.prepare_async()
                self._log_vlc_lifecycle("fallback_no_player")
                return False

            self.update_idletasks()
            self._backend = "vlc"
            self._schedule(
                50,
                lambda: self._vlc_embed_and_play(abs_path, token),
                token,
            )
            return True

        except Exception as e:
            logger.error(f"VLC-Initialisierung fehlgeschlagen: {e}")
            if _vlc_owner is not None:
                _vlc_owner.retire_async("initialization_exception")
            return False

    def _vlc_embed_and_play(self, video_path: str, token: int):
        """Bettet VLC in die stabile VLC-Flaeche ein und startet Wiedergabe."""
        try:
            if not self._is_current(token) or _vlc_owner is None:
                return

            # VLC braucht unter Windows eine wirklich gemappte Flaeche mit der
            # aktuellen Groesse; ein nur erzeugtes, aber noch nie gepacktes
            # Tk-Widget liefert sonst haeufig nur ein 1x1-Ausgabefenster.
            self._show_vlc_surface()
            self.update_idletasks()
            hwnd = self.vlc_surface.winfo_id()
            if not hwnd:
                logger.error("VLC: Kein Window-Handle verfügbar")
                _vlc_owner.retire_async("missing_hwnd")
                self._play_opencv(video_path, token)
                return

            logger.info(f"VLC: Einbetten in HWND {hwnd}")
            if not _vlc_owner.start(video_path, hwnd):
                logger.error("VLC: Start fehlgeschlagen")
                self._play_opencv(video_path, token)
                return

            if not self._is_current(token):
                _vlc_owner.retire_async("stale_start")
                return

            self._show_vlc_surface()
            self.is_playing = True
            logger.info("VLC: Wiedergabe gestartet")
            self._log_vlc_lifecycle("started")

            self._vlc_check_id = self._schedule(
                200,
                lambda: self._vlc_check_status(token),
                token,
            )

        except Exception as e:
            logger.error(f"VLC-Embed fehlgeschlagen: {e}")
            if _vlc_owner is not None:
                _vlc_owner.retire_async("embed_exception")
            self._play_opencv(video_path, token)

    def _vlc_check_status(self, token: int):
        """Prüft ob VLC-Wiedergabe noch läuft."""
        if not self._is_current(token) or not self.is_playing:
            return

        if _vlc_owner is None:
            self._cleanup_and_end(token)
            return

        try:
            state = _vlc_owner.get_state()

            if state is None:
                logger.error("VLC: Player waehrend Wiedergabe nicht mehr verfuegbar")
                self._cleanup_and_end(token)
                return

            if state == _vlc.State.Ended:
                logger.info("VLC: Video zu Ende")
                _vlc_owner.mark_ended()
                self._cleanup_and_end(token)
                return
            if state == _vlc.State.Error:
                logger.error("VLC: Wiedergabe-Fehler")
                _vlc_owner.retire_async("runtime_error")
                # Wie bisher bei einem spaeten Laufzeitfehler nicht von vorn
                # wiederholen; der Fotoablauf geht direkt weiter.
                self._cleanup_and_end(token)
                return
            if state == _vlc.State.Stopped:
                logger.error("VLC: Unerwartet gestoppt")
                _vlc_owner.retire_async("unexpected_stopped")
                self._cleanup_and_end(token)
                return

            self._vlc_check_id = self._schedule(
                200,
                lambda: self._vlc_check_status(token),
                token,
            )

        except Exception as e:
            logger.error(f"VLC Status-Check Fehler: {e}")
            _vlc_owner.retire_async("status_exception")
            self._cleanup_and_end(token)

    # ─────────────────────────────────────────────
    # OpenCV-Fallback
    # ─────────────────────────────────────────────

    def _play_opencv(self, video_path: str, token: int):
        """Spielt Video mit OpenCV ab (Software-Decoding, Fallback)"""
        import cv2

        if not self._is_current(token):
            return

        self._show_opencv_surface()
        self._backend = "opencv"

        self.cap = self._try_open_video(video_path)

        if self.cap is None:
            logger.error(f"OpenCV: Konnte Video nicht öffnen: {video_path}")
            self.video_label.configure(text="Video konnte nicht geladen werden")
            self._schedule(2000, lambda: self._on_video_end(token), token)
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
        stop_event = self._stop_event
        frame_queue = self._frame_queue
        cap = self.cap
        target_fps = self.target_fps
        self._log_vlc_lifecycle("opencv")

        # Video-Reader-Thread starten
        self._video_thread = threading.Thread(
            target=self._video_reader_thread,
            args=(cap, stop_event, frame_queue, target_fps),
            daemon=True,
            name=f"Video-OpenCV-{token}",
        )
        self._video_thread.start()

        # Frame-Display im Main-Thread starten
        self._schedule(10, lambda: self._display_next_frame(token), token)

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

    def _video_reader_thread(self, cap, stop_event, frame_queue, target_fps):
        """Liest Frames in separatem Thread (OpenCV)"""
        frame_time = 1.0 / target_fps
        frames_read = 0

        while not stop_event.is_set():
            start_time = time.time()

            try:
                ret, frame = cap.read()

                if not ret or frame is None:
                    logger.info(f"OpenCV: Video Ende nach {frames_read} Frames")
                    break

                frames_read += 1

                try:
                    frame_queue.put_nowait(frame)
                except queue.Full:
                    pass

                elapsed = time.time() - start_time
                sleep_time = max(0.001, frame_time - elapsed)
                time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"OpenCV: Reader-Fehler: {e}")
                break

        if not stop_event.is_set():
            # Das Ende-Signal darf auf einem schwachen/kurz blockierten
            # UI-Faden nicht hinter drei alten Frames verloren gehen. Falls
            # die kleine Queue voll ist, ist der aelteste Frame entbehrlich;
            # der Abschluss des Fotoablaufs ist es nicht.
            while not stop_event.is_set():
                try:
                    frame_queue.put_nowait(None)
                    break
                except queue.Full:
                    try:
                        frame_queue.get_nowait()
                    except queue.Empty:
                        pass

    def _display_next_frame(self, token: int):
        """Zeigt den nächsten Frame an (Main-Thread, OpenCV)"""
        if not self._is_current(token) or not self.is_playing:
            return

        try:
            frame = self._frame_queue.get_nowait()

            if frame is None:
                self._cleanup_and_end(token)
                return

            self._show_frame(frame)

        except queue.Empty:
            pass

        if self._is_current(token) and self.is_playing:
            self._schedule(
                self.frame_delay_ms,
                lambda: self._display_next_frame(token),
                token,
            )

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

    def _schedule(self, delay_ms: int, callback: Callable, token: int):
        """Plant einen generationsgebundenen Tk-Rueckruf."""
        holder = {}

        def guarded():
            after_id = holder.get("id")
            if after_id is not None:
                self._scheduled_ids.discard(after_id)
            if self._is_current(token):
                callback()

        after_id = self.after(delay_ms, guarded)
        holder["id"] = after_id
        self._scheduled_ids.add(after_id)
        return after_id

    def _cancel_scheduled(self):
        for after_id in tuple(self._scheduled_ids):
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        self._scheduled_ids.clear()
        self._vlc_check_id = None

    def _is_current(self, token: int) -> bool:
        return (
            token == self._playback_generation
            and not self._end_called
            and not self._stop_event.is_set()
        )

    def _hide_video_surfaces(self):
        for widget in (self.vlc_surface, self.video_label):
            try:
                widget.pack_forget()
            except Exception:
                pass

    def _show_vlc_surface(self):
        self.video_label.pack_forget()
        self.vlc_surface.pack(fill="both", expand=True)

    def _show_opencv_surface(self):
        self.vlc_surface.pack_forget()
        self.video_label.pack(fill="both", expand=True)

    def _cleanup_opencv(self):
        """Stoppt nur die Ressourcen der aktuellen OpenCV-Wiedergabe."""
        if self._video_thread and self._video_thread.is_alive():
            self._video_thread.join(timeout=0.3)
        self._video_thread = None

        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except Exception:
                break

        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def _stop_playback(self, reason: str):
        """Entwertet den aktuellen Lauf; nur ein echter Abbruch mustert VLC aus."""
        was_active_vlc = self._backend == "vlc" and self.is_playing
        self._playback_generation += 1
        self._stop_event.set()
        self._cancel_scheduled()
        self.is_playing = False

        if was_active_vlc and _vlc_owner is not None:
            _vlc_owner.retire_async(f"aborted_{reason}")

        self._cleanup_opencv()
        self._backend = None
        self._hide_video_surfaces()
        self.on_complete = None
        self.video_path = None
        self.next_screen = "start"

    def _cleanup_and_end(self, token: int):
        """Beendet genau den aktuellen Clip ohne normales VLC-Teardown."""
        if not self._is_current(token):
            return

        self.is_playing = False
        self._cancel_scheduled()
        if self._backend == "vlc" and _vlc_owner is not None:
            _vlc_owner.mark_ended()
        elif self._backend == "opencv":
            self._cleanup_opencv()
        self._backend = None
        self._hide_video_surfaces()

        try:
            self.video_label.configure(image=None, text="")
        except Exception:
            pass

        self._log_vlc_lifecycle("ended")
        self._on_video_end(token)

    def _on_video_end(self, token: int):
        """Loest Referenzen vor dem einmaligen Abschluss-Rueckruf."""
        if not self._is_current(token):
            return
        self._end_called = True

        callback = self.on_complete
        next_screen = self.next_screen
        self.on_complete = None
        self.video_path = None
        self.next_screen = "start"

        logger.info(f"Video beendet -> {next_screen}")

        if callback:
            try:
                callback()
            except Exception as e:
                logger.error(f"Callback-Fehler: {e}")
                # Nur der weiterhin aktuelle Lauf darf nach einem Callback-
                # Fehler noch navigieren. Ein reentranter neuer Clip gewinnt.
                if token == self._playback_generation:
                    self.app.show_screen(next_screen)
        else:
            self.app.show_screen(next_screen)

    def _log_vlc_lifecycle(self, event: str):
        """Kompakte Ressourcenwerte nur im Developer Mode protokollieren."""
        global _vlc_metrics_process
        if not is_developer_mode():
            return

        status = _vlc_owner.snapshot() if _vlc_owner is not None else {
            "state": "unavailable",
            "generation": 0,
            "creations": 0,
            "videos": 0,
            "cleanup_pending": 0,
            "cleanup_result": "none",
            "preparing": 0,
        }
        rss_mb = -1.0
        system_ram = -1.0
        process_cpu = -1.0
        system_cpu = -1.0
        try:
            import psutil
            if _vlc_metrics_process is None:
                _vlc_metrics_process = psutil.Process(os.getpid())
            rss_mb = _vlc_metrics_process.memory_info().rss / (1024 * 1024)
            process_cpu = _vlc_metrics_process.cpu_percent(interval=None)
            system_ram = psutil.virtual_memory().percent
            system_cpu = psutil.cpu_percent(interval=None)
        except Exception:
            pass

        logger.info(
            "VLC-LIFECYCLE event=%s playback=%s backend=%s state=%s "
            "generation=%s creations=%s videos=%s cleanup_pending=%s "
            "cleanup_result=%s preparing=%s rss_mb=%.1f process_cpu_pct=%.1f "
            "system_ram_pct=%.1f system_cpu_pct=%.1f threads=%s",
            event,
            self._playback_generation,
            self._backend or "none",
            status["state"],
            status["generation"],
            status["creations"],
            status["videos"],
            status["cleanup_pending"],
            status["cleanup_result"],
            status["preparing"],
            rss_mb,
            process_cpu,
            system_ram,
            system_cpu,
            threading.active_count(),
        )

    def close_video(self):
        """Idempotenter UI-Close-Hook; wartet nicht auf native Freigaben."""
        self._stop_playback("app_shutdown")
