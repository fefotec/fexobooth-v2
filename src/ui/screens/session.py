"""Session-Screen mit Vollbild-LiveView

Optimiert für Lenovo Miix 310 (1280x800)
- Live-View Vollbild oder mit Template-Overlay (konfigurierbar)
- Countdown zentriert über dem Live-View
- Performance-optimiert für schwache Hardware
"""

import customtkinter as ctk
import tkinter as tk
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import TYPE_CHECKING, Optional
import time
import os
import random
import threading

from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger
from src.i18n import t

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class SessionScreen(ctk.CTkFrame):
    """Session-Screen mit Vollbild-LiveView"""

    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color="#FFFFFF")
        self.app = app
        self.config = app.config

        # Status (current_photo_index ist jetzt in self.app - bleibt bei Screen-Wechsel erhalten!)
        self.total_photos = 1
        self.countdown_value = 0
        self.is_countdown_active = False
        self.is_live = False
        self.photo_display_until = 0
        self._resuming_after_video = False  # Flag: Session nach Video fortsetzen
        self._redo_visible = False  # Redo-Button sichtbar?
        self._capture_in_progress = False  # Capture läuft im Hintergrund
        self._camera_restore_in_progress = False  # Preview-Auflösung wird im Hintergrund wiederhergestellt
        self._waiting_for_restore_countdown = False
        self._capture_visible_started_at = 0.0
        self._shutter_flash_overlay = None

        # Performance-Einstellungen
        self._low_perf = self.config.get("low_performance_mode", {})
        self._skip_frames = self._low_perf.get("skip_frames", 0) if self._low_perf.get("enabled", False) else 0

        # FPS aus Config (default 20 für schwache Hardware)
        cam_settings = self.config.get("camera_settings", {})
        self._target_fps = cam_settings.get("live_view_fps", 20)
        self._frame_delay_ms = max(33, int(1000 / self._target_fps))

        # Dev-Mode: LiveView-Performance messen (alle ~5s EINE Summenzeile,
        # kein Log pro Frame). Im Live-Betrieb komplett aus (0 Overhead).
        # Die Aufbereitungs-Messung loggt der LiveView-Worker selbst (lokale
        # Variablen im Thread); hier liegen nur die UI-Thread-Zähler.
        self._perf_enabled = bool(self.config.get("developer_mode"))
        self._perf_window_start = 0.0
        self._perf_photo_refreshes = 0
        self._perf_photo_ms = 0.0
        self._perf_display_frames = 0
        self._perf_display_ms = 0.0
        self._perf_display_max_ms = 0.0

        # LiveView-Worker (2.4.16): Die komplette Bildaufbereitung (Spiegeln,
        # Overlay, Skalieren auf Anzeigegröße) läuft in einem Hintergrund-
        # Thread. Der Tk-Thread zeigt nur noch fertige Frames an — vorher
        # blockierte die Aufbereitung den UI-Thread ~150ms pro Frame (Miix).
        self._lv_stop = threading.Event()
        self._lv_thread: Optional[threading.Thread] = None
        self._lv_latest = None  # (PIL-Bild in phys. Pixeln, (log_w, log_h), seq)
        self._lv_seq = 0
        self._lv_displayed_seq = -1
        self._lv_target = (0, 0, 1.0)  # (container_w, container_h, scaling) — vom UI-Thread gepflegt
        self._display_ms_ema = 0.0  # geglättete Anzeige-Kosten für adaptiven UI-Takt

        # Serialisiert LiveView-Reads gegen High-Res-Capture/Preview-Restore
        # (zusätzlich zu den Flags — die Kamera-Backends sind nicht alle gelockt)
        self._cam_access_lock = threading.Lock()

        # Countdown-Font einmal laden statt pro Frame
        self._countdown_font = None
        self._countdown_font_size = 0

        # Fotoanzeige-Cache: das statische "gerade aufgenommen"-Foto wird pro
        # Foto nur EINMAL auf Bildschirmgröße skaliert (Messung Miix 310:
        # vorher ~380ms pro 100ms-Tick = Dauer-UI-Blockade während der Anzeige).
        self._photo_display_key = None
        self._photo_display_ctk = None

        # Template-Overlay im LiveView (optional, konfigurierbar)
        self._template_overlay_enabled = self.config.get("liveview_template_overlay", False)
        self._cached_template_composite = None  # Vorbereitetes Template (skaliert)
        self._cached_template_boxes_scaled = []  # Skalierte Box-Koordinaten
        self._cached_template_scale = 1.0
        self._cached_template_display_size = (0, 0)
        self._cached_template_container_size = (0, 0)  # Container-Größe bei Cache-Erstellung

        # Basis-Canvas-Cache fürs Overlay: die bereits aufgenommenen Fotos
        # (6000x4000!) werden nur beim Foto-Wechsel in ihre Boxen skaliert,
        # NICHT bei jedem LiveView-Frame (Messung Miix 310: vorher +~160ms
        # pro Foto pro Frame → LiveView brach von 7.7 auf 1.8 fps ein).
        self._overlay_base_canvas = None
        self._overlay_base_photo_count = -1

        # P3 (2.4.16): Statisches Komposit (Basis + Overlay) und die Overlay-
        # Ausschnitte pro Box werden vorberechnet — pro Frame bleibt nur noch
        # die aktuelle Box: einsetzen + kleinen Ausschnitt compositen, statt
        # das ganze Overlay über die volle Fläche zu legen.
        self._overlay_static_composite = None
        self._overlay_static_photo_count = -1
        self._overlay_box_crops = {}

        logger.info(f"Session: FPS={self._target_fps}, delay={self._frame_delay_ms}ms, skip={self._skip_frames}")

        self._setup_ui()

    def _setup_ui(self):
        """Erstellt die UI"""
        # Info-Leiste oben
        info_bar = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], height=45)
        info_bar.pack(fill="x")
        info_bar.pack_propagate(False)

        # Foto-Fortschritt
        self.progress_label = ctk.CTkLabel(
            info_bar,
            text=t(self.config, "session.photo_progress", current=1, total=1),
            font=FONTS["body_bold"],
            text_color=COLORS["text_primary"]
        )
        self.progress_label.pack(side="left", padx=20, pady=10)

        # Abbrechen-Button
        cancel_btn = ctk.CTkButton(
            info_bar,
            text=t(self.config, "common.cancel"),
            font=FONTS["small"],
            width=120,
            height=32,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["error"],
            corner_radius=SIZES["corner_radius_small"],
            command=self._on_cancel
        )
        cancel_btn.pack(side="right", padx=20, pady=6)

        # Hauptbereich
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # Preview Container (volle Größe)
        self.preview_container = ctk.CTkFrame(
            main_frame,
            fg_color="#FFFFFF",
            corner_radius=0
        )
        self.preview_container.pack(expand=True, fill="both")

        # Preview Label
        self.preview_label = ctk.CTkLabel(
            self.preview_container,
            text="",
            fg_color="transparent"
        )
        self.preview_label.pack(expand=True, fill="both")

        # Button-Leiste: tkinter.Frame mit place() (CTkFrame place/lift unzuverlässig!)
        self._button_bar = tk.Frame(self, bg="#000000", height=80)
        # Versteckt - wird per place() eingeblendet

        self._redo_btn = ctk.CTkButton(
            self._button_bar,
            text=t(self.config, "session.redo"),
            font=("Segoe UI", 22, "bold"),
            width=220,
            height=55,
            fg_color=COLORS["error"],
            hover_color="#cc3344",
            text_color=COLORS["text_primary"],
            corner_radius=SIZES["corner_radius"],
            command=self._on_redo_photo
        )

        self._continue_btn = ctk.CTkButton(
            self._button_bar,
            text=t(self.config, "session.continue"),
            font=("Segoe UI", 22, "bold"),
            width=220,
            height=55,
            fg_color=COLORS["success"],
            hover_color="#00b85c",
            text_color=COLORS["text_primary"],
            corner_radius=SIZES["corner_radius"],
            command=self._on_continue_photo
        )

    def on_show(self):
        """Screen wird angezeigt"""
        self.config = self.app.config
        self._redo_btn.configure(text=t(self.config, "session.redo"))
        self._continue_btn.configure(text=t(self.config, "session.continue"))

        # Template-Overlay Einstellung bei jedem Show neu lesen (Admin kann es ändern)
        self._template_overlay_enabled = self.config.get("liveview_template_overlay", False)

        # Prüfen ob wir nach Video fortsetzen (photos_taken nicht leer = Session läuft bereits)
        resuming = len(self.app.photos_taken) > 0

        if resuming:
            logger.info(f"Session fortgesetzt nach Video: Index={self.app.current_photo_index}, photos_taken={len(self.app.photos_taken)}")
            self.total_photos = len(self.app.template_boxes) if self.app.template_boxes else 1
            self.photo_display_until = 0
            self._update_progress()
            # Template-Overlay Cache synchron aufbauen (vor LiveView!)
            if self._template_overlay_enabled and self._cached_template_composite is None:
                self._build_template_overlay_cache()
            self.is_live = True
            self._start_liveview_worker()
            self._update_live_view()
            # Kamera ist bereits warm - kürzerer Delay
            self.after(200, self._start_countdown)
            return

        logger.info("Session gestartet (neu)")

        # Kamera initialisieren (oder wiederverwenden wenn bereits initialisiert)
        if self.app.camera_manager.is_initialized:
            logger.info("Kamera bereits initialisiert - überspringe Neuinitialisierung")
        else:
            cam_settings = self.config.get("camera_settings", {})
            live_res = cam_settings.get("live_view_resolution", 480)  # Default 480 für Performance

            if not self.app.camera_manager.initialize(
                self.config.get("camera_index", 0),
                live_res,
                int(live_res * 0.75)
            ):
                logger.error("Kamera konnte nicht initialisiert werden")
                self._show_error(t(self.config, "session.camera_error"))
                return

        # Session initialisieren (NUR bei neuem Start!)
        self.app.photos_taken = []
        self.app.current_photo_index = 0
        self.total_photos = len(self.app.template_boxes) if self.app.template_boxes else 1
        self.photo_display_until = 0

        logger.info(f"Session: {self.total_photos} Fotos zu machen")
        self._update_progress()

        # Template-Overlay Cache SYNCHRON aufbauen (BEVOR LiveView startet,
        # sonst sieht man kurz Vollbild-Kamera bevor Template-Ansicht kommt)
        if self._template_overlay_enabled:
            self._build_template_overlay_cache()

        # Live-View starten
        self.is_live = True
        self._start_liveview_worker()
        self._update_live_view()

        # Countdown nach kurzer Verzögerung starten
        self.after(500, self._start_countdown)

    def on_hide(self):
        """Screen wird verlassen"""
        self.is_live = False
        self.is_countdown_active = False
        # LiveView-Worker beenden (der Screen wird beim nächsten Show neu erstellt)
        self._lv_stop.set()
        self._hide_redo_button()
        self._hide_shutter_flash()
        # Template-Overlay Cache freigeben (wird bei nächstem on_show neu gebaut)
        self._cached_template_composite = None
        self._cached_template_boxes_scaled = []

    def _update_progress(self, override_current: int = 0):
        """Aktualisiert die Fortschrittsanzeige"""
        if override_current > 0:
            current = override_current
        else:
            current = min(self.app.current_photo_index + 1, self.total_photos)
        self.progress_label.configure(
            text=t(self.config, "session.photo_progress", current=current, total=self.total_photos)
        )

    def _update_live_view(self):
        """Aktualisiert die Live-Vorschau (Vollbild, Performance-optimiert)"""
        if not self.is_live:
            return

        if self.photo_display_until > 0:
            if time.time() < self.photo_display_until:
                # Zuletzt aufgenommenes Foto anzeigen (gecacht — das Bild ist
                # statisch, es wird nur beim ersten Tick wirklich skaliert)
                if self.app.photos_taken:
                    if self._perf_enabled:
                        t0 = time.perf_counter()
                        self._display_photo_cached(self.app.photos_taken[-1])
                        self._perf_photo_refreshes += 1
                        self._perf_photo_ms += (time.perf_counter() - t0) * 1000
                        self._maybe_log_liveview_perf()
                    else:
                        self._display_photo_cached(self.app.photos_taken[-1])
                self.after(100, self._update_live_view)
                return
            else:
                self.photo_display_until = 0
                self._next_photo_or_finish()
                if self.is_live:
                    self.after(100, self._update_live_view)
                return

        # Ziel-Größe für den Worker aktualisieren (winfo_* nur im UI-Thread erlaubt!)
        container_w = self.preview_container.winfo_width()
        container_h = self.preview_container.winfo_height()
        if container_w < 100 or container_h < 100:
            container_w = self.winfo_screenwidth()
            container_h = self.winfo_screenheight()
        self._lv_target = (container_w, container_h, self._get_widget_scaling())

        # Overlay-Cache bei deutlicher Container-Größenänderung neu bauen (UI-Thread)
        if self._template_overlay_enabled and self._cached_template_composite is not None:
            old_size = self._cached_template_container_size
            if old_size:
                old_cw, old_ch = old_size
                if abs(container_w - old_cw) > 50 or abs(container_h - old_ch) > 50:
                    logger.info(f"Container-Resize erkannt: {old_cw}x{old_ch} → {container_w}x{container_h} → Cache rebuild")
                    self._build_template_overlay_cache()

        # Neuesten fertigen Frame vom Worker anzeigen (nur wenn wirklich neu).
        # Das Bild ist bereits EXAKT auf round(logisch*scaling) vorskaliert —
        # CTkImage trifft damit den PIL-Copy-Fastpath und skaliert nichts mehr.
        latest = self._lv_latest
        if latest is not None:
            img, logical_size, seq = latest
            if seq != self._lv_displayed_seq:
                t0 = time.perf_counter()
                try:
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=logical_size)
                    self.preview_label.configure(image=ctk_img)
                    self.preview_label.image = ctk_img
                except Exception as e:
                    logger.warning(f"LiveView-Anzeige fehlgeschlagen: {e}")
                self._lv_displayed_seq = seq
                display_ms = (time.perf_counter() - t0) * 1000
                self._display_ms_ema = (
                    display_ms if self._display_ms_ema <= 0
                    else self._display_ms_ema * 0.8 + display_ms * 0.2
                )
                if self._perf_enabled:
                    self._perf_display_frames += 1
                    self._perf_display_ms += display_ms
                    if display_ms > self._perf_display_max_ms:
                        self._perf_display_max_ms = display_ms
                    self._maybe_log_liveview_perf()

        if self.is_live:
            # Adaptiver UI-Takt: Die Vorschau darf höchstens ~1/3 der UI-Thread-
            # Zeit kosten, sonst leidet die Touch-Reaktion (Miix: 1 schwacher Kern
            # fürs UI). Ohne Messwert (Live-Betrieb) gilt der Config-Takt.
            delay = max(self._frame_delay_ms, int(self._display_ms_ema * 3))
            self.after(min(delay, 250), self._update_live_view)

    def _maybe_log_liveview_perf(self):
        """Dev-Mode: alle ~5s EINE Summenzeile für den UI-Thread-Anteil.

        Die Aufbereitungs-Summenzeile (Kamera/Overlay/Skalierung) loggt der
        LiveView-Worker selbst — hier steht nur, was der Tk-Thread noch
        wirklich kostet (Anzeige der fertigen Frames + Fotoanzeige-Refresh).
        """
        now = time.perf_counter()
        if self._perf_window_start <= 0:
            self._perf_window_start = now
            return
        elapsed = now - self._perf_window_start
        if elapsed < 5.0:
            return

        if self._perf_display_frames > 0:
            logger.info(
                "LIVEVIEW-PERF: Anzeige (UI-Thread): "
                f"{self._perf_display_frames}x in {elapsed:.1f}s, "
                f"avg={self._perf_display_ms / self._perf_display_frames:.0f}ms, "
                f"max={self._perf_display_max_ms:.0f}ms, "
                f"UI-Takt={max(self._frame_delay_ms, int(self._display_ms_ema * 3))}ms"
            )
        if self._perf_photo_refreshes > 0:
            logger.info(
                "LIVEVIEW-PERF: Fotoanzeige-Refresh: "
                f"{self._perf_photo_refreshes}x in {elapsed:.1f}s, "
                f"avg={self._perf_photo_ms / self._perf_photo_refreshes:.0f}ms pro Refresh"
            )

        self._perf_window_start = now
        self._perf_display_frames = 0
        self._perf_display_ms = 0.0
        self._perf_display_max_ms = 0.0
        self._perf_photo_refreshes = 0
        self._perf_photo_ms = 0.0

    def _start_liveview_worker(self):
        """Startet den Bildaufbereitungs-Thread (idempotent)."""
        if self._lv_thread is not None and self._lv_thread.is_alive():
            return
        self._lv_stop.clear()
        self._lv_thread = threading.Thread(
            target=self._liveview_worker, daemon=True, name="liveview-prep"
        )
        self._lv_thread.start()
        logger.info("LiveView-Worker gestartet (Bildaufbereitung im Hintergrund-Thread)")

    def _liveview_worker(self):
        """Hintergrund-Thread: Kamera lesen + Frame komplett aufbereiten.

        Legt das fertige, bereits auf Anzeigegröße skalierte Bild in
        self._lv_latest ab — nur der neueste Frame zählt, es gibt keinen
        Rückstau. KEINE Tk-Aufrufe hier! Die Anzeigegröße kommt über
        self._lv_target vom UI-Thread (winfo_* ist nicht thread-sicher).
        """
        base_interval = self._frame_delay_ms / 1000.0
        if self._skip_frames > 0:
            # low_performance_mode: Frame-Skipping wird zum längeren Takt
            base_interval *= (self._skip_frames + 1)
            logger.info(f"LiveView-Worker: skip_frames={self._skip_frames} → Takt {base_interval * 1000:.0f}ms")

        # Dev-Mode-Messfenster — bewusst lokale Variablen (kein UI-Thread-Zugriff)
        win_start = time.perf_counter()
        n = 0
        cam_ms = 0.0
        prep_ms = 0.0
        ov_ms_sum = 0.0
        max_ms = 0.0

        while not self._lv_stop.is_set():
            if (not self.is_live or self.photo_display_until > 0
                    or self._capture_in_progress or self._camera_restore_in_progress):
                self._lv_stop.wait(0.05)
                continue

            target_w, target_h, scaling = self._lv_target
            if target_w < 100 or target_h < 100:
                self._lv_stop.wait(0.05)
                continue

            t0 = time.perf_counter()
            frame = None
            try:
                with self._cam_access_lock:
                    # Flags nach Lock-Erwerb erneut prüfen (Capture könnte
                    # zwischenzeitlich gestartet sein)
                    if not self._capture_in_progress and not self._camera_restore_in_progress:
                        frame = self.app.camera_manager.get_frame()
            except Exception as e:
                logger.debug(f"LiveView-Worker: Kamera-Fehler: {e}")
            t_cam = time.perf_counter()

            if frame is None:
                self._lv_stop.wait(0.1)
                continue

            try:
                img, logical_size, overlay_ms = self._prepare_live_frame(
                    frame, target_w, target_h, scaling
                )
            except Exception as e:
                logger.warning(f"LiveView-Worker: Aufbereitung fehlgeschlagen: {e}")
                self._lv_stop.wait(0.1)
                continue
            t_end = time.perf_counter()

            self._lv_seq += 1
            self._lv_latest = (img, logical_size, self._lv_seq)

            elapsed = t_end - t0

            if self._perf_enabled:
                n += 1
                cam_ms += (t_cam - t0) * 1000
                prep_ms += (t_end - t_cam) * 1000
                ov_ms_sum += overlay_ms
                frame_ms = elapsed * 1000
                if frame_ms > max_ms:
                    max_ms = frame_ms
                w_elapsed = t_end - win_start
                if w_elapsed >= 5.0:
                    fps = n / w_elapsed
                    logger.info(
                        "LIVEVIEW-PERF: "
                        f"{n} Frames in {w_elapsed:.1f}s "
                        f"(~{fps:.1f} fps, Ziel {self._target_fps}), "
                        f"avg={(cam_ms + prep_ms) / n:.0f}ms/Frame "
                        f"(Kamera={cam_ms / n:.0f}ms, Aufbereitung={prep_ms / n:.0f}ms, "
                        f"davon Overlay={ov_ms_sum / n:.0f}ms), "
                        f"max={max_ms:.0f}ms [Worker-Thread]"
                    )
                    win_start = t_end
                    n = 0
                    cam_ms = prep_ms = ov_ms_sum = max_ms = 0.0

            # Adaptive Taktung: Ziel-FPS anstreben, aber die CPU nie mit
            # Aufbereitung sättigen — mindestens ~1/3 der Frame-Zeit Pause,
            # damit Capture-Worker, Galerie-Server & UI Luft behalten.
            sleep_s = max(base_interval - elapsed, elapsed * 0.35, 0.005)
            self._lv_stop.wait(sleep_s)

        logger.info("LiveView-Worker beendet")

    def _prepare_live_frame(self, frame, target_w: int, target_h: int, scaling: float):
        """Bereitet einen BGR-Kameraframe komplett zur Anzeige auf (Worker-Thread).

        Rückgabe: (PIL-Bild in physischen Pixeln, (logische Breite, Höhe), Overlay-ms).

        Das Bild wird hier EXAKT auf die Größe gebracht, die CTkImage intern
        anfordert (round(logisch * scaling)) — dadurch greift der PIL-
        Copy-Fastpath und der UI-Thread muss nichts mehr skalieren.
        """
        # Spiegelung NUR für LiveView (intuitiver Spiegel-Effekt für User).
        # Im _capture_worker (Webcam + DSLR) wird NICHT gespiegelt, damit Texte
        # auf Kleidung im gespeicherten/gedruckten Foto richtig herum sind.
        if self.config.get("rotate_180", False):
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        overlay_ms = 0.0
        img = None
        if self._template_overlay_enabled and self._cached_template_composite is not None:
            t0 = time.perf_counter()
            try:
                img = self._compose_overlay_frame(rgb)
            except Exception as e:
                logger.warning(f"Template-Overlay Fehler im LiveView: {e}")
                img = None
            overlay_ms = (time.perf_counter() - t0) * 1000

        if img is not None:
            src_w, src_h = img.size
        else:
            src_h, src_w = rgb.shape[:2]

        # Anzeigegröße: Seitenverhältnis in LOGISCHEN Pixeln einpassen
        # (winfo liefert Tk-Pixel; bei 125% DPI wäre das Bild sonst zu groß)
        logical_w = target_w / scaling
        logical_h = target_h / scaling
        img_ratio = src_w / src_h
        if img_ratio > logical_w / logical_h:
            disp_w = int(logical_w)
            disp_h = int(logical_w / img_ratio)
        else:
            disp_h = int(logical_h)
            disp_w = int(logical_h * img_ratio)
        phys_w = max(1, round(disp_w * scaling))
        phys_h = max(1, round(disp_h * scaling))

        if img is None:
            # Vollbild-LiveView: direkt per OpenCV auf Zielgröße (schneller als PIL)
            rgb = cv2.resize(rgb, (phys_w, phys_h), interpolation=cv2.INTER_LINEAR)
            img = Image.fromarray(rgb)
        elif img.size != (phys_w, phys_h):
            img = img.resize((phys_w, phys_h), Image.Resampling.BILINEAR)

        if img.mode != "RGB":
            img = img.convert("RGB")

        if self.is_countdown_active and self.countdown_value > 0:
            img = self._add_countdown_overlay(img)

        return img, (disp_w, disp_h), overlay_ms

    def _add_countdown_overlay(self, img: Image.Image) -> Image.Image:
        """Fügt ZENTRIERTEN Countdown zum Bild hinzu"""
        draw = ImageDraw.Draw(img)

        font_size = min(img.width, img.height) // 2
        font = self._get_countdown_font(font_size)

        text = str(self.countdown_value)

        bbox = draw.textbbox((0, 0), text, font=font, anchor="lt")
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        x = (img.width - text_w) // 2 - bbox[0]
        y = (img.height - text_h) // 3 - bbox[1]

        shadow_color = (0, 0, 0, 220)
        for dx, dy in [(-4, -4), (4, -4), (-4, 4), (4, 4), (0, 6), (6, 0), (-6, 0), (0, -6)]:
            draw.text((x + dx, y + dy), text, fill=shadow_color, font=font)

        draw.text((x, y), text, fill=(224, 6, 117, 255), font=font)

        return img

    def _get_countdown_font(self, size: int):
        """Countdown-Font einmal laden und cachen (truetype pro Frame ist teuer)."""
        if self._countdown_font is not None and self._countdown_font_size == size:
            return self._countdown_font
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", size)
        except Exception:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)
            except Exception:
                font = ImageFont.load_default()
        self._countdown_font = font
        self._countdown_font_size = size
        return font

    def _display_photo_cached(self, photo: Image.Image):
        """Zeigt ein STATISCHES Foto an — Skalierung + CTkImage nur einmal pro Foto.

        Das aufgenommene Nikon-Foto ist 6000x4000; es bei jedem 100ms-Tick neu
        auf Bildschirmgröße zu skalieren blockierte den UI-Thread dauerhaft
        (~380ms pro Tick auf dem Miix 310). Cache-Key = Foto-Objekt + Containergröße.
        """
        container_w = self.preview_container.winfo_width()
        container_h = self.preview_container.winfo_height()
        key = (id(photo), container_w, container_h)
        if key == self._photo_display_key and self._photo_display_ctk is not None:
            return  # Bild steht schon unverändert auf dem Label — nichts zu tun

        if container_w < 100 or container_h < 100:
            container_w = self.winfo_screenwidth()
            container_h = self.winfo_screenheight()

        scaling = self._get_widget_scaling()
        logical_w = container_w / scaling
        logical_h = container_h / scaling

        img_ratio = photo.width / photo.height
        container_ratio = logical_w / logical_h
        if img_ratio > container_ratio:
            display_w = int(logical_w)
            display_h = int(logical_w / img_ratio)
        else:
            display_h = int(logical_h)
            display_w = int(logical_h * img_ratio)

        # Einmalig auf Anzeigegröße (physische Pixel) verkleinern — danach hat
        # CTkImage intern nichts Großes mehr zu skalieren.
        phys_w = max(1, int(display_w * scaling))
        phys_h = max(1, int(display_h * scaling))
        small = photo.resize((phys_w, phys_h), Image.Resampling.BILINEAR)

        ctk_img = ctk.CTkImage(light_image=small, dark_image=small, size=(display_w, display_h))
        self.preview_label.configure(image=ctk_img)
        self.preview_label.image = ctk_img
        self._photo_display_key = key
        self._photo_display_ctk = ctk_img

    def _build_template_overlay_cache(self):
        """Erstellt den skalierten Template-Overlay-Cache für LiveView"""
        try:
            overlay = self.app.overlay_image
            boxes = self.app.template_boxes
            if not overlay or not boxes:
                self._cached_template_composite = None
                logger.info("Template-Overlay: Kein Overlay oder keine Boxen vorhanden")
                return

            # Layout sicherstellen bevor wir messen
            self.update_idletasks()

            container_w = self.preview_container.winfo_width()
            container_h = self.preview_container.winfo_height()
            if container_w < 100 or container_h < 100:
                # Fallback: Bildschirmgröße verwenden (nicht 900x500!)
                container_w = self.winfo_screenwidth()
                container_h = self.winfo_screenheight()
                logger.debug(f"Container noch nicht gerendert, verwende Bildschirmgröße: {container_w}x{container_h}")

            # Template auf Container-Größe skalieren (Seitenverhältnis beibehalten)
            overlay_w, overlay_h = overlay.size
            scale = min(container_w / overlay_w, container_h / overlay_h)
            display_w = int(overlay_w * scale)
            display_h = int(overlay_h * scale)

            # Overlay skalieren (BILINEAR statt LANCZOS für Performance)
            scaled_overlay = overlay.resize((display_w, display_h), Image.Resampling.BILINEAR)

            # Boxen skalieren
            scaled_boxes = []
            for box_info in boxes:
                x1, y1, x2, y2 = box_info["box"]
                scaled_boxes.append({
                    "box": (int(x1 * scale), int(y1 * scale), int(x2 * scale), int(y2 * scale)),
                    "angle": box_info.get("angle", 0.0)
                })

            self._cached_template_composite = scaled_overlay
            self._cached_template_boxes_scaled = scaled_boxes
            self._cached_template_scale = scale
            self._cached_template_display_size = (display_w, display_h)
            self._cached_template_container_size = (container_w, container_h)
            # Abgeleitete Caches müssen zur neuen Skalierung neu aufgebaut werden
            self._reset_overlay_derived_caches()
            logger.info(f"Template-Overlay Cache: {overlay_w}x{overlay_h} -> {display_w}x{display_h} (Container: {container_w}x{container_h}, scale={scale:.3f})")

        except Exception as e:
            logger.error(f"Template-Overlay Cache fehlgeschlagen: {e}")
            self._cached_template_composite = None
            self._reset_overlay_derived_caches()

    def _reset_overlay_derived_caches(self):
        """Verwirft Basis-Canvas, statisches Komposit und Box-Ausschnitte."""
        self._overlay_base_canvas = None
        self._overlay_base_photo_count = -1
        self._overlay_static_composite = None
        self._overlay_static_photo_count = -1
        self._overlay_box_crops = {}

    def _get_overlay_base_canvas(self) -> Image.Image:
        """Basis-Canvas (schwarz + bereits aufgenommene Fotos) — gecacht.

        Wird nur neu gebaut, wenn sich die Anzahl der Fotos ändert (Aufnahme/
        Redo) oder der Template-Cache neu skaliert wurde. Die teure Skalierung
        der 6000x4000-Fotos passiert damit einmal pro Foto statt pro Frame.
        """
        photo_count = len(self.app.photos_taken)
        if (self._overlay_base_canvas is not None
                and self._overlay_base_photo_count == photo_count):
            return self._overlay_base_canvas

        display_w, display_h = self._cached_template_display_size
        base = Image.new("RGBA", (display_w, display_h), (0, 0, 0, 255))

        for i, photo in enumerate(self.app.photos_taken):
            if i >= len(self._cached_template_boxes_scaled):
                break
            box_info = self._cached_template_boxes_scaled[i]
            x1, y1, x2, y2 = box_info["box"]
            bw, bh = x2 - x1 + 1, y2 - y1 + 1
            if bw > 0 and bh > 0:
                fitted = self._fit_to_box(photo, bw, bh)
                base.paste(fitted, (x1, y1))

        self._overlay_base_canvas = base
        self._overlay_base_photo_count = photo_count
        return base

    def _get_overlay_static_composite(self) -> Image.Image:
        """Basis-Canvas + Overlay als EIN vorberechnetes Bild (pro Foto-Anzahl).

        Das volle Alpha-Compositing über die ganze Fläche passiert damit nur
        noch beim Foto-Wechsel — pro LiveView-Frame bleibt nur die aktuelle Box.
        """
        photo_count = len(self.app.photos_taken)
        if (self._overlay_static_composite is not None
                and self._overlay_static_photo_count == photo_count):
            return self._overlay_static_composite

        base = self._get_overlay_base_canvas()
        composite = Image.alpha_composite(base, self._cached_template_composite)
        self._overlay_static_composite = composite
        self._overlay_static_photo_count = photo_count
        return composite

    def _get_overlay_box_crop(self, idx: int) -> Optional[Image.Image]:
        """Overlay-Ausschnitt der Box idx — einmal geschnitten, dann gecacht."""
        crop = self._overlay_box_crops.get(idx)
        if crop is not None:
            return crop
        overlay = self._cached_template_composite
        if overlay is None or idx >= len(self._cached_template_boxes_scaled):
            return None
        x1, y1, x2, y2 = self._cached_template_boxes_scaled[idx]["box"]
        crop = overlay.crop((x1, y1, x2 + 1, y2 + 1))
        self._overlay_box_crops[idx] = crop
        return crop

    def _compose_overlay_frame(self, rgb: np.ndarray) -> Image.Image:
        """Setzt den Kameraframe in die aktuelle Template-Box (Schnellpfad).

        Ergebnis ist identisch zum früheren Voll-Compositing: außerhalb der
        Box gilt das statische Komposit, innerhalb liegt der Overlay-
        Ausschnitt über dem (deckenden) LiveView-Bild.
        """
        idx = self.app.current_photo_index
        boxes = self._cached_template_boxes_scaled
        if idx >= len(boxes):
            return Image.fromarray(rgb)

        canvas = self._get_overlay_static_composite().copy()

        x1, y1, x2, y2 = boxes[idx]["box"]
        bw, bh = x2 - x1 + 1, y2 - y1 + 1
        if bw > 0 and bh > 0:
            fitted = self._fit_frame_to_box_np(rgb, bw, bh)
            live_rgba = Image.fromarray(fitted).convert("RGBA")
            crop = self._get_overlay_box_crop(idx)
            region = Image.alpha_composite(live_rgba, crop) if crop is not None else live_rgba
            canvas.paste(region, (x1, y1))
        return canvas

    def _fit_frame_to_box_np(self, rgb: np.ndarray, box_w: int, box_h: int) -> np.ndarray:
        """Cover-Fit eines Kameraframes per OpenCV (schneller als PIL auf dem Miix)."""
        h, w = rgb.shape[:2]
        img_aspect = w / h
        box_aspect = box_w / box_h

        # Rundung identisch zu _fit_to_box (int-Truncation), damit der
        # Bildausschnitt exakt dem bisherigen Verhalten entspricht
        if img_aspect > box_aspect:
            new_h = box_h
            new_w = max(box_w, int(new_h * img_aspect))
        else:
            new_w = box_w
            new_h = max(box_h, int(new_w / img_aspect))

        resized = cv2.resize(rgb, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        left = (new_w - box_w) // 2
        top = (new_h - box_h) // 2
        return resized[top:top + box_h, left:left + box_w]

    def _fit_to_box(self, img: Image.Image, box_w: int, box_h: int) -> Image.Image:
        """Passt ein Bild in eine Box ein (Cover-Modus, schnell)"""
        img_w, img_h = img.size
        box_aspect = box_w / box_h
        img_aspect = img_w / img_h

        if img_aspect > box_aspect:
            new_h = box_h
            new_w = int(new_h * img_aspect)
        else:
            new_w = box_w
            new_h = int(new_w / img_aspect)

        resized = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
        left = (new_w - box_w) // 2
        top = (new_h - box_h) // 2
        cropped = resized.crop((left, top, left + box_w, top + box_h))
        return cropped.convert("RGBA")

    def _start_countdown(self):
        """Startet den Countdown"""
        if self._camera_restore_in_progress:
            if not self._waiting_for_restore_countdown:
                logger.info("Countdown wartet auf Preview-Restore")
                self._waiting_for_restore_countdown = True
            self.after(100, self._start_countdown)
            return

        self._waiting_for_restore_countdown = False
        logger.info(f"=== Starte Countdown für Foto {self.app.current_photo_index + 1}/{self.total_photos} ===")
        self.is_countdown_active = True
        self.countdown_value = self.config.get("countdown_time", 5)
        self._countdown_tick()

    def _countdown_tick(self):
        """Ein Countdown-Tick"""
        if not self.is_countdown_active or not self.is_live:
            return

        if self.countdown_value > 0:
            self.countdown_value -= 1
            self.after(1000, self._countdown_tick)
        else:
            self.is_countdown_active = False
            self._take_photo()

    def _take_photo(self):
        """Nimmt ein Foto auf.

        Seit 2.4.17 ohne Auslöse-Bild-Screen und ohne "Foto wird
        aufgenommen"-Text (Wunsch Christian 2026-08-07): Der kurze weiße
        Auslöse-Blitz bleibt als Feedback, danach steht das letzte
        LiveView-Bild bis das Foto erscheint.
        """
        logger.info(f"Foto {self.app.current_photo_index + 1} aufnehmen")
        self._capture_photo()

    def _capture_photo(self):
        """Erfasst das Foto (non-blocking via Background-Thread)"""
        # Kamera-Zugriff für LiveView pausieren
        self._capture_in_progress = True
        self._capture_visible_started_at = time.perf_counter()

        # Kurzer echter Auslöse-Blitz: reines Tk-Overlay, keine Bildberechnung im LiveView.
        self._show_shutter_flash()

        # Capture in Background-Thread starten (blockiert nicht die UI)
        thread = threading.Thread(target=self._capture_photo_worker, daemon=True)
        thread.start()

    def _show_shutter_flash(self):
        """Zeigt beim eigentlichen Capture einen sehr leichten White-Flash."""
        try:
            if self._shutter_flash_overlay is None:
                self._shutter_flash_overlay = tk.Frame(
                    self.preview_container,
                    bg="#ffffff",
                    bd=0,
                    highlightthickness=0
                )

            self._shutter_flash_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._shutter_flash_overlay.tkraise()
            self.after(90, self._hide_shutter_flash)
        except Exception as e:
            logger.debug(f"Shutter-Flash konnte nicht angezeigt werden: {e}")

    def _hide_shutter_flash(self):
        try:
            if self._shutter_flash_overlay is not None:
                self._shutter_flash_overlay.place_forget()
        except Exception:
            pass

    def _capture_photo_worker(self):
        """Worker-Thread: Führt den blockierenden Kamera-Capture durch"""
        worker_started_at = time.perf_counter()
        photo = None

        # Exklusiver Kamera-Zugriff: der LiveView-Worker pausiert zwar über
        # _capture_in_progress, aber ein gerade laufender get_frame() muss
        # fertig sein, bevor die Auflösung umgeschaltet wird.
        try:
            with self._cam_access_lock:
                photo = self._capture_photo_camera_calls()
        except Exception as e:
            logger.error(f"Capture-Worker Fehler: {e}")

        worker_ms = (time.perf_counter() - worker_started_at) * 1000
        logger.info(
            "Capture-Worker Timing: "
            f"total={worker_ms:.0f}ms, photo={'ok' if photo is not None else 'failed'}"
        )

        # Ergebnis zurück auf UI-Thread geben
        self.after(0, lambda p=photo: self._on_capture_complete(p))

    def _capture_photo_camera_calls(self) -> Optional[Image.Image]:
        """Die eigentlichen Kamera-Aufrufe des Captures (läuft unter _cam_access_lock)."""
        photo = None

        try:
            # Canon DSLR
            if hasattr(self.app.camera_manager, 'capture_photo'):
                try:
                    photo = self.app.camera_manager.capture_photo(timeout=10.0)
                    if photo:
                        frame = np.array(photo)
                        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                        if self.config.get("rotate_180", False):
                            frame = cv2.rotate(frame, cv2.ROTATE_180)
                        # KEIN cv2.flip(frame, 1): LiveView ist gespiegelt (Spiegel-Effekt für
                        # intuitive Bewegung), aber das gespeicherte/gedruckte Foto darf nicht
                        # gespiegelt sein — sonst sind Texte auf Kleidung seitenverkehrt.
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        photo = Image.fromarray(rgb)
                except Exception as e:
                    logger.error(f"DSLR Fehler: {e}")

            # Webcam
            if photo is None:
                cam_settings = self.config.get("camera_settings", {})
                capture_w = cam_settings.get("single_photo_width", 1920)
                capture_h = cam_settings.get("single_photo_height", 1080)

                logger.info(f"Webcam Capture: {capture_w}x{capture_h}")

                if hasattr(self.app.camera_manager, 'get_high_res_frame'):
                    try:
                        frame = self.app.camera_manager.get_high_res_frame(
                            capture_w,
                            capture_h,
                            restore_preview=False
                        )
                    except TypeError:
                        # Kompatibilität mit Kamera-Managern ohne restore_preview-Parameter.
                        frame = self.app.camera_manager.get_high_res_frame(capture_w, capture_h)
                    if frame is not None:
                        logger.info(f"High-Res: {frame.shape[1]}x{frame.shape[0]}")
                    else:
                        frame = self.app.camera_manager.get_frame(use_cache=False)
                else:
                    frame = self.app.camera_manager.get_frame(use_cache=False)

                if frame is not None:
                    if self.config.get("rotate_180", False):
                        frame = cv2.rotate(frame, cv2.ROTATE_180)
                    # KEIN cv2.flip(frame, 1): siehe Kommentar im DSLR-Pfad oben.
                    # LiveView wird gespiegelt (Z. ~279), das Foto selbst nicht.
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    photo = Image.fromarray(rgb)

        except Exception as e:
            logger.error(f"Capture-Worker Fehler: {e}")

        return photo

    def _on_capture_complete(self, photo: Optional[Image.Image]):
        """Callback auf UI-Thread nach abgeschlossenem Capture"""
        self._capture_in_progress = False
        # Fotoanzeige-Cache invalidieren: gleich wird ein NEUES Foto angezeigt
        # (id()-Kollisionen über Sessions hinweg ausschließen)
        self._photo_display_key = None
        if self._capture_visible_started_at > 0:
            visible_ms = (time.perf_counter() - self._capture_visible_started_at) * 1000
            logger.info(f"Sichtbare Capture-Wartezeit bis Fotoanzeige: {visible_ms:.0f}ms")
            self._capture_visible_started_at = 0.0

        if photo is not None:
            self.app.photos_taken.append(photo)
            self.app.statistics.record_photo()
            self.after(10, lambda: self._save_photo_async(photo, self.app.current_photo_index + 1))

            display_time = self.config.get("single_display_time", 2)
            self.app.current_photo_index += 1
            # Fortschritt zeigt noch das gerade aufgenommene Foto (nicht das nächste)
            self._update_progress(override_current=self.app.current_photo_index)

            # Bei Collagen (>1 Foto): Button-Leiste zeigen (Nochmal + Weiter), 60s Timeout
            if self.total_photos > 1 and self.app.current_photo_index < self.total_photos:
                display_time = 60
                try:
                    self._show_redo_button()
                except Exception as e:
                    logger.error(f"Button-Leiste Fehler: {e}", exc_info=True)

            # WICHTIG: Timer immer setzen (auch wenn Button-Leiste fehlschlägt)
            self.photo_display_until = time.time() + display_time
            logger.info(f"Foto-Anzeige für {display_time}s (buttons={self._redo_visible})")

            # Webcam nach der sichtbaren Fotoaufnahme zurück auf Preview-Auflösung
            # schalten. Das passiert parallel während der Fotoanzeige.
            self._restore_preview_after_capture()
        else:
            logger.error("Foto-Aufnahme fehlgeschlagen")
            self._restore_preview_after_capture()
            self._next_photo_or_finish()

    def _restore_preview_after_capture(self):
        """Stellt die Preview-Auflösung nachgelagert im Hintergrund wieder her."""
        if not hasattr(self.app.camera_manager, 'restore_preview_resolution'):
            return
        if self._camera_restore_in_progress:
            return

        self._camera_restore_in_progress = True
        logger.info("Preview-Restore: Background-Task gestartet")

        def _restore():
            ok = False
            try:
                with self._cam_access_lock:
                    ok = self.app.camera_manager.restore_preview_resolution()
            except Exception as e:
                logger.error(f"Preview-Restore Fehler: {e}")
            finally:
                self.after(0, lambda success=ok: self._on_preview_restore_complete(success))

        threading.Thread(target=_restore, daemon=True).start()

    def _on_preview_restore_complete(self, success: bool):
        """UI-Thread Callback nach Preview-Restore."""
        self._camera_restore_in_progress = False
        logger.info(f"Preview-Restore abgeschlossen: {'ok' if success else 'nicht bestätigt'}")

    def _save_photo_async(self, photo: Image.Image, index: int):
        """Speichert Foto im Hintergrund"""
        try:
            self.app.local_storage.save_single(photo, suffix=str(index))
        except Exception as e:
            logger.error(f"Fehler beim Speichern: {e}")

    def _show_redo_button(self):
        """Zeigt die Button-Leiste (Nochmal + Weiter) am unteren Bildschirmrand"""
        logger.info(f"_show_redo_button aufgerufen - Foto {self.app.current_photo_index}/{self.total_photos}")
        self._redo_visible = True
        # tkinter place() auf self - funktioniert zuverlässig (kein CTk place-Bug)
        self._button_bar.place(x=0, rely=1.0, anchor="sw", relwidth=1.0, height=80)
        self._button_bar.tkraise()  # Über alle anderen Widgets heben
        # Buttons nebeneinander zentriert
        self._redo_btn.pack(side="left", padx=(0, 15), expand=True, anchor="e")
        self._continue_btn.pack(side="left", padx=(15, 0), expand=True, anchor="w")
        logger.info("Button-Leiste eingeblendet (Nochmal + Weiter)")

        # Stress-Test: 15% Redo, 85% Weiter
        if self.app.stress_test_active:
            if random.random() < 0.15:
                delay = random.randint(500, 1500)
                logger.info("Stress-Test: Redo einzelnes Foto")
                self.after(delay, self._on_redo_photo)
            else:
                delay = random.randint(500, 1500)
                logger.info("Stress-Test: Weiter zum nächsten Foto")
                self.after(delay, self._on_continue_photo)

    def _hide_redo_button(self):
        """Versteckt die Button-Leiste"""
        if self._redo_visible:
            self._redo_visible = False
            self._redo_btn.pack_forget()
            self._continue_btn.pack_forget()
            self._button_bar.place_forget()

    def _on_redo_photo(self):
        """Einzelnes Collage-Foto wiederholen"""
        if not self._redo_visible:
            return

        self._hide_redo_button()
        self.photo_display_until = 0  # Display-Timer stoppen

        # Letztes Foto entfernen und Index zurücksetzen
        if self.app.photos_taken:
            self.app.photos_taken.pop()
            self.app.current_photo_index -= 1
            self._update_progress()
            logger.info(f"Foto {self.app.current_photo_index + 1} wird wiederholt")

        # Countdown für das gleiche Foto neu starten
        self.after(300, self._start_countdown)

    def _on_continue_photo(self):
        """Weiter zum nächsten Foto (User hat auf Weiter gedrückt)"""
        if not self._redo_visible:
            return

        self._hide_redo_button()
        self.photo_display_until = 0  # Display-Timer stoppen
        logger.info("User hat Weiter gedrückt")
        self._next_photo_or_finish()

    def _next_photo_or_finish(self):
        """Nächstes Foto oder zum Filter-Screen"""
        self._hide_redo_button()
        logger.info(f"Next: {self.app.current_photo_index}/{self.total_photos}")

        if self.app.current_photo_index < self.total_photos:
            video_key = f"video_after_{self.app.current_photo_index}"
            video_path = self.config.get(video_key, "")

            if video_path and os.path.exists(video_path):
                logger.info(f"Spiele Zwischen-Video: {video_key}")
                self.is_live = False
                self.app.play_video_and_return(video_path, self._continue_after_video)
            else:
                self.after(300, self._start_countdown)
        else:
            logger.info("Alle Fotos -> Filter-Screen")
            self.is_live = False
            self.app.show_screen("filter")

    def _continue_after_video(self):
        """Wird nach Zwischen-Video aufgerufen"""
        self.app.show_screen("session")

    def _on_cancel(self):
        """Abbrechen"""
        logger.info(f"Session abgebrochen bei Foto {self.app.current_photo_index}/{self.total_photos}")
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
