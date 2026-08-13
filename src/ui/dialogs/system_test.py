"""Automatischer System-Test nach Event-Wechsel

Führt eine komplette Test-Session durch und MISST dabei (seit 2.4.18):
Systemzustand → Kamera init → Foto pro Template-Slot → Template rendern → Testdruck

Jeder Schritt wird gestoppt und gegen Schwellwerte einer gesunden Box
verglichen. Auffälligkeiten (zu langsam, zu voll, Fremdlast) erscheinen als
⚠-Warnungen im Ergebnis und im Log — so fällt eine kranke Box VOR dem Event
auf, nicht erst beim Gast (Wunsch Christian 2026-08-07).
"""

import os
import threading
import time
import tempfile
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
from PIL import Image
import customtkinter as ctk

from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Status-Icons für die Schritt-Anzeige
ICON_PENDING = "⬜"
ICON_RUNNING = "⏳"
ICON_SUCCESS = "✅"
ICON_WARNING = "⚠️"
ICON_ERROR = "❌"

# Pause zwischen Fotos (Sekunden) - Kamera braucht Zeit zum Nachregeln
PHOTO_DELAY = 2.0

# Maximale Gesamtdauer des Tests (Sekunden) - danach wird abgebrochen
GLOBAL_TIMEOUT = 120

# Schwellwerte für "auffällig" — kalibriert an gesunden Miix-310-Logs (2026-08).
# Überschreitung ist KEIN Testabbruch, sondern eine sichtbare Warnung.
THRESHOLD_CAM_INIT_S = 5.0          # Kamera öffnen inkl. Codec-Verhandlung (gesund ~2s)
THRESHOLD_LIVEVIEW_FPS_WEBCAM = 12.0  # 1080p-MJPG liefert ~30 fps; YUY2-Fallback bricht auf ~5 ein
THRESHOLD_LIVEVIEW_FPS_DSLR = 5.0   # DSLR-LiveView (Bridge/EDSDK) ist prinzipbedingt langsamer
THRESHOLD_RENDER_S = 4.5            # Template-Rendern (Miix gesund ~2,3s)
THRESHOLD_PRINT_SUBMIT_S = 10.0     # Übergabe an den Windows-Spooler (nicht die Druckdauer!)
THRESHOLD_DISK_WRITE_MBS = 8.0      # eMMC gesund 40+ MB/s; <8 = sterbend oder randvoll
THRESHOLD_DISK_FREE_GB = 5.0        # Unter 5 GB wird Windows insgesamt zäh
THRESHOLD_CPU_BUSY_PCT = 70.0       # Fremdlast VOR dem Test (Defender/Update aktiv?)


class SystemTestDialog(ctk.CTkToplevel):
    """Automatischer System-Test nach Event-Wechsel.

    Fotografiert jeden Template-Slot einzeln und druckt das Ergebnis.
    Hat einen globalen Timeout und Abbrechen-Button für den Notfall.
    """

    def __init__(self, parent, app, on_complete: callable, on_adjust_print: callable = None):
        super().__init__(parent)

        self.app = app
        self._on_complete = on_complete
        self._on_adjust_print = on_adjust_print
        self._test_photos: List[Image.Image] = []
        self._test_result: Optional[Image.Image] = None
        self._test_file: Optional[Path] = None
        self._errors: List[str] = []
        self._warnings: List[str] = []   # Auffälligkeiten (Test läuft weiter)
        self._metrics = {}               # Messwerte für Log + Ergebnis
        self._destroyed = False
        self._cancelled = threading.Event()  # Thread-sicheres Abbruch-Signal

        # Anzahl Foto-Slots aus Template ermitteln
        self._num_photos = max(len(self.app.template_boxes), 1)

        # Schritte definieren (dynamisch je nach Template)
        foto_text = f"Fotos aufnehmen ({self._num_photos} Stück)"
        self.STEPS = [
            ("System prüfen", "Speicherplatz, Festplatte und Auslastung werden geprüft..."),
            ("Kamera prüfen", "Kamera wird initialisiert und gemessen..."),
            (foto_text, "Fotos werden aufgenommen..."),
            ("Template anwenden", "Template wird angewendet..."),
            ("Testdruck starten", "Testdruck wird gesendet..."),
            ("Aufräumen", "Wird aufgeräumt..."),
        ]

        # Fullscreen Overlay
        self.overrideredirect(True)
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        self.geometry(f"{screen_w}x{screen_h}+0+0")
        self.configure(fg_color="#0a0a10")
        self.attributes("-topmost", True)
        self.transient(parent)
        self.grab_set()
        self.focus_force()

        # Ctrl+Shift+Q auch im Dialog abfangen (grab_set blockiert Root-Bindings!)
        self.bind("<Control-Shift-Q>", lambda e: self._force_abort())
        self.bind("<Control-Shift-q>", lambda e: self._force_abort())

        self._build_ui(screen_w, screen_h)

        # Globaler Timeout-Timer
        self._timeout_id = self.after(GLOBAL_TIMEOUT * 1000, self._on_timeout)

        # Test nach kurzem Delay starten
        self.after(500, self._start_test)
        logger.info(f"System-Test Dialog geöffnet ({self._num_photos} Foto-Slots, Timeout: {GLOBAL_TIMEOUT}s)")

    def _build_ui(self, screen_w: int, screen_h: int):
        """Baut die Dialog-UI auf"""
        bg_frame = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
        bg_frame.pack(fill="both", expand=True)

        # Zentrierte Karte
        card_w = min(520, int(screen_w * 0.85))
        card = ctk.CTkFrame(
            bg_frame,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["info"],
            border_width=2,
            corner_radius=16
        )
        card.place(relx=0.5, rely=0.5, anchor="center")

        # Titel
        ctk.CTkLabel(
            card,
            text="System-Test",
            font=FONTS["heading"],
            text_color=COLORS["info"]
        ).pack(pady=(20, 15))

        # Schritte-Liste
        steps_frame = ctk.CTkFrame(card, fg_color="transparent")
        steps_frame.pack(padx=30, fill="x")

        self._step_labels = []
        for step_name, _ in self.STEPS:
            label = ctk.CTkLabel(
                steps_frame,
                text=f"{ICON_PENDING}  {step_name}",
                font=FONTS["body"],
                text_color=COLORS["text_muted"],
                anchor="w"
            )
            label.pack(fill="x", pady=2)
            self._step_labels.append(label)

        # Fortschrittsbalken
        self.progress_bar = ctk.CTkProgressBar(
            card,
            width=min(380, int(card_w * 0.8)),
            height=12,
            fg_color=COLORS["bg_dark"],
            progress_color=COLORS["info"],
            corner_radius=6
        )
        self.progress_bar.pack(pady=(15, 5))
        self.progress_bar.set(0)

        # Status-Text
        self.status_label = ctk.CTkLabel(
            card,
            text="Test wird vorbereitet...",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"]
        )
        self.status_label.pack(pady=(0, 5))

        # Ergebnis-Label (zunächst unsichtbar)
        self.result_label = ctk.CTkLabel(
            card,
            text="",
            font=FONTS["body_bold"],
            text_color=COLORS["success"],
            wraplength=min(400, int(card_w * 0.75))
        )
        # Wird erst nach Abschluss gepackt

        # Button-Container (immer sichtbar)
        self._btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._btn_frame.pack(pady=(10, 20))

        # Abbrechen-Button (immer sichtbar während Test läuft)
        self.cancel_btn = ctk.CTkButton(
            self._btn_frame,
            text="Abbrechen",
            font=FONTS["button_large"],
            width=160,
            height=50,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_primary"],
            corner_radius=SIZES["corner_radius"],
            command=self._on_cancel
        )
        self.cancel_btn.pack()

        # OK-Button (zunächst unsichtbar - wird nach Abschluss angezeigt)
        self.ok_btn = ctk.CTkButton(
            self._btn_frame,
            text="OK",
            font=FONTS["button_large"],
            width=160,
            height=50,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            corner_radius=SIZES["corner_radius"],
            command=self._close
        )

        self.adjust_print_btn = ctk.CTkButton(
            self._btn_frame,
            text="Druck korrigieren",
            font=FONTS["button_large"],
            width=220,
            height=50,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            corner_radius=SIZES["corner_radius"],
            command=self._open_print_adjustment
        )

        self.new_event_btn = ctk.CTkButton(
            self._btn_frame,
            text="Jetzt herunterfahren",
            font=FONTS["button_large"],
            width=260,
            height=50,
            fg_color=COLORS["warning"],
            hover_color="#ff6600",
            corner_radius=SIZES["corner_radius"],
            command=self._shutdown_for_new_event
        )

    def _update_step(self, index: int, status: str, error_msg: str = ""):
        """Aktualisiert den Status eines Schritts (thread-safe)"""
        if self._destroyed:
            return
        try:
            step_name = self.STEPS[index][0]
            if status == "running":
                icon = ICON_RUNNING
                color = COLORS["info"]
            elif status == "success":
                icon = ICON_SUCCESS
                color = COLORS["success"]
            else:
                icon = ICON_ERROR
                color = COLORS["error"]

            text = f"{icon}  {step_name}"
            if error_msg:
                text += f" - {error_msg}"

            self._step_labels[index].configure(text=text, text_color=color)
        except Exception:
            pass

    def _update_step_text(self, index: int, new_name: str):
        """Ändert den Text eines Schritts (für Foto-Fortschritt)"""
        if self._destroyed:
            return
        try:
            self.STEPS[index] = (new_name, self.STEPS[index][1])
            self._step_labels[index].configure(
                text=f"{ICON_RUNNING}  {new_name}",
                text_color=COLORS["info"]
            )
        except Exception:
            pass

    def _update_status(self, text: str, progress: float):
        """Aktualisiert Status-Text und Fortschritt (thread-safe)"""
        if self._destroyed:
            return
        try:
            self.status_label.configure(text=text)
            self.progress_bar.set(progress)
        except Exception:
            pass

    def _start_test(self):
        """Startet den Test in einem Background-Thread"""
        thread = threading.Thread(target=self._run_test, daemon=True)
        thread.start()

    def _on_cancel(self):
        """Abbrechen-Button gedrückt"""
        logger.warning("System-Test: Vom Benutzer abgebrochen")
        self._cancelled.set()
        self._errors.append("Vom Benutzer abgebrochen")
        # Kamera freigeben (falls aktiv)
        try:
            self.app.camera_manager.release()
        except Exception:
            pass
        self.after(500, self._show_result)

    def _on_timeout(self):
        """Globaler Timeout erreicht - Test abbrechen"""
        if self._destroyed or not self._cancelled.is_set():
            logger.error(f"System-Test: TIMEOUT nach {GLOBAL_TIMEOUT}s!")
            self._cancelled.set()
            self._errors.append(f"Timeout nach {GLOBAL_TIMEOUT}s")
            # Kamera freigeben (falls aktiv)
            try:
                self.app.camera_manager.release()
            except Exception:
                pass
            self.after(500, self._show_result)

    def _force_abort(self):
        """Ctrl+Shift+Q im Dialog - sofort schließen"""
        logger.warning("System-Test: Force-Abort via Ctrl+Shift+Q")
        self._cancelled.set()
        try:
            self.app.camera_manager.release()
        except Exception:
            pass
        self._destroyed = True
        self._errors.append("Force-Abort (Ctrl+Shift+Q)")
        self.grab_release()
        self.destroy()
        if self._on_complete:
            self._on_complete(False, self._errors)

    def _run_test(self):
        """Führt alle Test-Schritte durch"""
        steps = [
            self._step_system_check,
            self._step_init_camera,
            self._step_capture_photos,
            self._step_apply_template,
            self._step_print,
            self._step_cleanup,
        ]

        for i, step_func in enumerate(steps):
            # Abbruch prüfen
            if self._cancelled.is_set():
                for j in range(i, len(steps)):
                    self.after(0, lambda idx=j: self._update_step(idx, "error", "Abgebrochen"))
                break

            step_name, status_text = self.STEPS[i]
            progress = i / len(steps)

            self.after(0, lambda idx=i: self._update_step(idx, "running"))
            self.after(0, lambda t=status_text, p=progress: self._update_status(t, p))

            # Kurze Pause damit UI-Update sichtbar ist
            time.sleep(0.3)

            try:
                step_func()
                if not self._cancelled.is_set():
                    self.after(0, lambda idx=i: self._update_step(idx, "success"))
            except Exception as e:
                error_msg = str(e)
                self._errors.append(f"{step_name}: {error_msg}")
                self.after(0, lambda idx=i, err=error_msg: self._update_step(idx, "error", err))
                logger.error(f"System-Test Schritt '{step_name}' fehlgeschlagen: {e}")

                # Bei Kamera- oder Foto-Fehler: restliche Schritte überspringen
                # (Index 1 = Kamera, 2 = Fotos; der System-Check wirft nie)
                if i in (1, 2):
                    for j in range(i + 1, len(steps)):
                        self.after(0, lambda idx=j: self._update_step(idx, "error", "Übersprungen"))
                    break

        # Ergebnis anzeigen (nur wenn nicht bereits durch Cancel/Timeout geschehen)
        if not self._destroyed:
            self.after(0, lambda: self._update_status("Test abgeschlossen", 1.0))
            self.after(100, lambda: self._show_result())

    def _warn(self, text: str):
        """Auffälligkeit vermerken (Test läuft weiter) + loggen."""
        self._warnings.append(text)
        logger.warning(f"SYSTEMTEST-AUFFÄLLIG: {text}")

    def _step_system_check(self):
        """Schritt 1: Systemzustand messen — wirft nie, nur Warnungen.

        Deckt schleichende Probleme auf, BEVOR sie beim Event zuschlagen:
        volle/sterbende eMMC, zu wenig Speicherplatz, Windows-Hintergrundlast.
        """
        # Speicherplatz auf dem App-Laufwerk
        try:
            import shutil
            app_drive = os.path.splitdrive(os.path.abspath(__file__))[0] + os.sep
            usage = shutil.disk_usage(app_drive)
            free_gb = usage.free / (1024 ** 3)
            self._metrics["disk_frei_gb"] = round(free_gb, 1)
            if free_gb < THRESHOLD_DISK_FREE_GB:
                self._warn(f"Wenig Speicherplatz: nur {free_gb:.1f} GB frei (unter {THRESHOLD_DISK_FREE_GB:.0f} GB wird Windows zäh)")
        except Exception as e:
            logger.debug(f"System-Test: Speicherplatz-Check fehlgeschlagen: {e}")

        # Festplatten-Schreibtest: 8 MB mit echtem Sync auf die Platte
        try:
            test_file = Path(tempfile.gettempdir()) / "fexobooth_disktest.bin"
            payload = b"\0" * (8 * 1024 * 1024)
            t0 = time.perf_counter()
            with open(test_file, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            write_s = time.perf_counter() - t0
            try:
                test_file.unlink()
            except OSError:
                pass
            mbs = 8 / write_s if write_s > 0 else 999
            self._metrics["disk_schreiben_mbs"] = round(mbs, 1)
            if mbs < THRESHOLD_DISK_WRITE_MBS:
                self._warn(f"Festplatte sehr langsam: {mbs:.1f} MB/s schreiben (gesund: 40+; Speicher prüfen/aufräumen)")
        except Exception as e:
            logger.debug(f"System-Test: Schreibtest fehlgeschlagen: {e}")

        # Fremdlast: Läuft gerade etwas Schweres im Hintergrund?
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.8)
            ram = psutil.virtual_memory().percent
            self._metrics["cpu_prozent"] = round(cpu)
            self._metrics["ram_prozent"] = round(ram)
            if cpu > THRESHOLD_CPU_BUSY_PCT:
                self._warn(f"Hohe Hintergrund-Auslastung: CPU {cpu:.0f}% (Windows-Update/Defender? Details im Log)")
            # Detaillierte Störer-Analyse zusätzlich ins Log (blockiert ~1s)
            from src.utils.system_load import snapshot_system_load
            snapshot_system_load("System-Test")
        except Exception as e:
            logger.debug(f"System-Test: Lastmessung fehlgeschlagen: {e}")

    def _step_init_camera(self):
        """Schritt 2: Kamera initialisieren + Liefergeschwindigkeit messen.

        WICHTIG (2.4.26): Die Kamera wird in der PREVIEW-Auflösung geöffnet —
        exakt wie im echten Betrieb. Früher öffnete der Test direkt in voller
        Foto-Auflösung (1920x1080). Das ist NICHT der normale Ablauf (dort ist
        die Vorschau 640x480 und 1080p kommt nur kurz pro Foto) und war auf
        älteren C920-Webcams sehr langsam (~7,6s → Fehlalarm „Kamera langsam")
        und teils sogar hängend (Box friert beim Kalt-Öffnen in 1080p ein,
        Feld-Log 2026-08-13). Das eigentliche Foto nutzt weiter den High-Res-
        Pfad (get_high_res_frame) — genau wie eine echte Session.
        """
        if self._cancelled.is_set():
            raise Exception("Abgebrochen")

        cam_index = self.app.config.get("camera_index", 0)
        cam_settings = self.app.config.get("camera_settings", {})
        live_res = cam_settings.get("live_view_resolution", 480)  # wie Session/Pre-Init

        t0 = time.perf_counter()
        success = self.app.camera_manager.initialize(cam_index, live_res, int(live_res * 0.75))
        init_s = time.perf_counter() - t0
        if not success:
            raise Exception("Kamera nicht erreichbar")

        self._metrics["kamera_init_s"] = round(init_s, 1)
        if init_s > THRESHOLD_CAM_INIT_S:
            self._warn(f"Kamera-Start langsam: {init_s:.1f}s (gesund: ~2s; USB-Kabel/-Port prüfen)")

        # Kurz warten bis Kamera bereit
        time.sleep(1.0)

        # Liefergeschwindigkeit: 15 frische Frames am Stück lesen. Bei der
        # Webcam entlarvt das den YUY2-Fallback (MJPG abgelehnt → 1080p
        # bricht von ~30 auf ~5 fps ein), bei DSLR eine lahme Bridge.
        try:
            frames = 0
            t0 = time.perf_counter()
            for _ in range(15):
                if self._cancelled.is_set():
                    raise Exception("Abgebrochen")
                if self.app.camera_manager.get_frame(use_cache=False) is not None:
                    frames += 1
            elapsed = time.perf_counter() - t0
            fps = frames / elapsed if elapsed > 0 else 0
            self._metrics["kamera_fps"] = round(fps, 1)

            is_webcam = self.app.config.get("camera_type", "webcam") == "webcam"
            threshold = THRESHOLD_LIVEVIEW_FPS_WEBCAM if is_webcam else THRESHOLD_LIVEVIEW_FPS_DSLR
            if fps < threshold:
                self._warn(
                    f"Kamera liefert nur {fps:.1f} Bilder/s (erwartet: über {threshold:.0f}; "
                    f"{'Codec/USB prüfen' if is_webcam else 'Kamera/Bridge prüfen'})"
                )
        except Exception as e:
            if "Abgebrochen" in str(e):
                raise
            logger.debug(f"System-Test: fps-Messung fehlgeschlagen: {e}")

    def _capture_single_photo(self) -> Image.Image:
        """Nimmt ein Foto für den System-Test auf.

        Webcam (2.4.26): über den High-Res-Pfad `get_high_res_frame` — GENAU wie
        eine echte Session (kurz auf 1080p umschalten, Bild holen). Damit prüft
        der Test denselben Weg, den die Box im Betrieb nimmt, in voller Qualität.
        DSLR (Canon/Nikon): weiterhin nur LiveView-Frame (kein echtes Auslösen,
        spart SD-Karten-Abhängigkeit).
        """
        if self._cancelled.is_set():
            raise Exception("Abgebrochen")

        mgr = self.app.camera_manager
        frame = None

        # Webcam: echter High-Res-Aufnahmepfad (wie im Betrieb)
        is_webcam = self.app.config.get("camera_type", "webcam") == "webcam"
        if is_webcam and hasattr(mgr, "get_high_res_frame"):
            cam_settings = self.app.config.get("camera_settings", {})
            cap_w = cam_settings.get("single_photo_width", 1920)
            cap_h = cam_settings.get("single_photo_height", 1080)
            try:
                frame = mgr.get_high_res_frame(cap_w, cap_h, restore_preview=False)
            except TypeError:
                frame = mgr.get_high_res_frame(cap_w, cap_h)

        # DSLR bzw. Fallback: LiveView-Frame (mehrere Versuche, ~1-2s Anlauf)
        if frame is None:
            if hasattr(mgr, "start_live_view") and not getattr(mgr, "_live_view_active", True):
                mgr.start_live_view()
            for _attempt in range(15):
                if self._cancelled.is_set():
                    raise Exception("Abgebrochen")
                frame = mgr.get_frame(use_cache=False)
                if frame is not None:
                    break
                time.sleep(0.3)

        if frame is None:
            raise Exception("Kein Kamera-Frame verfügbar")

        # Rotation anwenden — KEIN cv2.flip(frame, 1):
        # Der Frame wird als Foto gespeichert/gedruckt. LiveView spiegelt nur
        # zur Darstellung (siehe session.py:282), Capture-Pfade dürfen nicht
        # spiegeln, sonst sind Texte auf Kleidung im Print seitenverkehrt.
        if self.app.config.get("rotate_180", False):
            frame = cv2.rotate(frame, cv2.ROTATE_180)

        # OpenCV BGR zu PIL RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    def _step_capture_photos(self):
        """Schritt 3: Ein Foto pro Template-Slot aufnehmen"""
        total = self._num_photos
        self._test_photos = []
        first_photo_s = None

        for i in range(total):
            if self._cancelled.is_set():
                raise Exception("Abgebrochen")

            nr = i + 1

            # UI: "Foto 2 von 4 aufnehmen..."
            self.after(0, lambda n=nr, t=total:
                self._update_step_text(2, f"Foto {n} von {t} aufnehmen..."))
            self.after(0, lambda n=nr, t=total:
                self._update_status(
                    f"Foto {n} von {t} wird aufgenommen...",
                    (2 + n / t) / 6  # Schritt 3 von 6, anteilig
                ))

            # Zwischen Fotos kurz warten (nicht vor dem ersten)
            if i > 0:
                time.sleep(PHOTO_DELAY)

            t0 = time.perf_counter()
            photo = self._capture_single_photo()
            if first_photo_s is None:
                first_photo_s = time.perf_counter() - t0
            self._test_photos.append(photo)
            logger.info(f"System-Test: Foto {nr}/{total} aufgenommen ({photo.size})")

        if first_photo_s is not None:
            self._metrics["erstes_foto_s"] = round(first_photo_s, 1)

        # Webcam nach dem High-Res-Capture zurück auf Vorschau-Auflösung,
        # damit die Kamera nicht auf 1080p stehen bleibt (sonst wäre die
        # erste echte Vorschau nach dem Test unnötig langsam).
        mgr = self.app.camera_manager
        if hasattr(mgr, "restore_preview_resolution"):
            try:
                mgr.restore_preview_resolution()
            except Exception as e:
                logger.debug(f"System-Test: Vorschau-Restore übersprungen: {e}")

        # Finalen Step-Text setzen
        self.after(0, lambda t=total:
            self._update_step_text(2, f"Fotos aufnehmen ({t} Stück)"))

    def _step_apply_template(self):
        """Schritt 4: Template mit allen Fotos rendern (mit Zeitmessung)"""
        if self._cancelled.is_set():
            raise Exception("Abgebrochen")

        if not self._test_photos:
            raise Exception("Keine Testfotos vorhanden")

        boxes = self.app.template_boxes
        overlay = self.app.overlay_image

        if not boxes:
            raise Exception("Keine Template-Boxen geladen")

        t0 = time.perf_counter()
        self._test_result = self.app.renderer.render(
            self._test_photos, boxes, overlay
        )
        render_s = time.perf_counter() - t0
        self._metrics["render_s"] = round(render_s, 1)
        if render_s > THRESHOLD_RENDER_S:
            self._warn(f"Bild-Erstellung langsam: {render_s:.1f}s (gesund: ~2s; Box wird bei Gästen träge wirken)")
        logger.info(f"System-Test: Template angewendet ({self._test_result.size}, {render_s:.1f}s)")

    def _step_print(self):
        """Schritt 5: Drucker-Status prüfen + Testdruck ausführen (mit Zeitmessung)"""
        if self._cancelled.is_set():
            raise Exception("Abgebrochen")

        if self._test_result is None:
            raise Exception("Kein Testbild zum Drucken")

        # Drucker-Status VOR dem Druck: meldet der SELPHY/Spooler ein Problem?
        try:
            from src.printer.controller import get_printer_controller
            printer_problem = get_printer_controller().get_error()
            if printer_problem:
                self._warn(f"Drucker meldet: '{printer_problem}' — Testdruck wird trotzdem versucht")
        except Exception as e:
            logger.debug(f"System-Test: Drucker-Status-Check fehlgeschlagen: {e}")

        # Temporäre Datei speichern
        temp_dir = Path(tempfile.gettempdir())
        self._test_file = temp_dir / "fexobooth_systemtest.jpg"

        # RGBA → RGB konvertieren für JPEG
        img_rgb = self._test_result.convert("RGB")
        img_rgb.save(str(self._test_file), "JPEG", quality=95)
        logger.info(f"System-Test: Testbild gespeichert: {self._test_file}")

        # GDI-Druck (gemessen wird die Übergabe an den Spooler, nicht der
        # physische Druck — der dauert beim SELPHY immer ~45s)
        t0 = time.perf_counter()
        self._print_via_gdi(self._test_file)
        submit_s = time.perf_counter() - t0
        self._metrics["druck_uebergabe_s"] = round(submit_s, 1)
        if submit_s > THRESHOLD_PRINT_SUBMIT_S:
            self._warn(f"Druck-Übergabe langsam: {submit_s:.1f}s (gesund: unter 5s; Spooler/USB prüfen)")

    def _print_via_gdi(self, image_path: Path):
        """Druckt über Windows GDI"""
        try:
            import win32print
            import win32ui
            from PIL import ImageWin
        except ImportError:
            raise Exception("Druck nur unter Windows verfügbar")

        printer_name = self.app.config.get("printer_name")
        if not printer_name:
            printer_name = win32print.GetDefaultPrinter()

        available = [p[2] for p in win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )]

        if printer_name not in available:
            # Fuzzy-Match: Drucker-Kopien erkennen (anderer USB-Port)
            from src.printer import find_matching_printer
            matched = find_matching_printer(printer_name, available)
            if matched:
                printer_name = matched
            else:
                raise Exception(f"Drucker '{printer_name}' nicht gefunden")

        adjustment = self.app.config.get("print_adjustment", {})
        offset_x = adjustment.get("offset_x", 0)
        offset_y = adjustment.get("offset_y", 0)
        zoom = adjustment.get("zoom", 100) / 100

        img = Image.open(image_path)

        # 10x15cm bei 300dpi
        base_width = int(1772 * zoom)
        base_height = int(1181 * zoom)

        img_ratio = img.width / img.height
        target_ratio = base_width / base_height

        if img_ratio > target_ratio:
            new_h = base_height
            new_w = int(new_h * img_ratio)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            left = (new_w - base_width) // 2
            img = img.crop((left, 0, left + base_width, base_height))
        else:
            new_w = base_width
            new_h = int(new_w / img_ratio)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            top = (new_h - base_height) // 2
            img = img.crop((0, top, base_width, top + base_height))

        # Zoom zentriert: Offset so berechnen, dass sich das Bild
        # gleichmäßig nach allen Seiten ausdehnt statt nur nach rechts-unten
        center_offset_x = -int((1772 * (zoom - 1)) / 2)
        center_offset_y = -int((1181 * (zoom - 1)) / 2)
        draw_x = offset_x + center_offset_x
        draw_y = offset_y + center_offset_y

        try:
            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(printer_name)
            hDC.StartDoc("Fexobooth Systemtest")
            hDC.StartPage()

            dib = ImageWin.Dib(img)
            dib.draw(
                hDC.GetHandleOutput(),
                (draw_x, draw_y, draw_x + base_width, draw_y + base_height)
            )

            hDC.EndPage()
            hDC.EndDoc()
            hDC.DeleteDC()
        except Exception as e:
            error_str = str(e)
            if "1801" in error_str or "unzulässig" in error_str.lower():
                raise Exception("Drucker nicht erreichbar")
            elif "offline" in error_str.lower():
                raise Exception("Drucker ist offline")
            elif "paper" in error_str.lower() or "papier" in error_str.lower():
                raise Exception("Kein Papier im Drucker")
            else:
                raise Exception(f"Druckfehler: {error_str}")

        logger.info(f"System-Test: Testdruck gesendet an '{printer_name}'")

        # Lifetime-Drucker-Zähler hochzählen (auch Testdrucke zählen!)
        from src.storage.printer_lifetime import get_printer_lifetime
        get_printer_lifetime().increment()

    def _step_cleanup(self):
        """Schritt 6: Testdateien aufräumen"""
        if self._test_file and self._test_file.exists():
            try:
                self._test_file.unlink()
                logger.info("System-Test: Testdatei gelöscht")
            except Exception as e:
                logger.warning(f"Testdatei löschen fehlgeschlagen: {e}")

        # Kamera freigeben
        try:
            self.app.camera_manager.release()
        except Exception:
            pass

        self._test_photos = []
        self._test_result = None

    def _show_result(self):
        """Zeigt das Testergebnis an"""
        if self._destroyed:
            return

        # Timeout-Timer abbrechen
        if hasattr(self, '_timeout_id') and self._timeout_id:
            try:
                self.after_cancel(self._timeout_id)
            except Exception:
                pass

        # Abbrechen-Button durch OK-Button ersetzen
        self.cancel_btn.pack_forget()

        # Alle Messwerte gesammelt ins Log (eine Zeile, gut vergleichbar)
        if self._metrics:
            metrics_text = ", ".join(f"{k}={v}" for k, v in self._metrics.items())
            logger.info(f"SYSTEMTEST-MESSWERTE: {metrics_text}")

        if not self._errors and not self._warnings:
            self.result_label.configure(
                text=f"Alles OK! Testdruck mit {self._num_photos} Fotos gesendet.\nAlle Messwerte im Normalbereich.",
                text_color=COLORS["success"]
            )
            logger.info("System-Test: ERFOLGREICH (keine Auffälligkeiten)")
        elif not self._errors:
            warn_text = (
                f"{ICON_WARNING} Test bestanden, aber mit Auffälligkeiten:\n"
                + "\n".join(f"• {w}" for w in self._warnings)
            )
            self.result_label.configure(
                text=warn_text,
                text_color=COLORS["warning"]
            )
            logger.warning(f"System-Test: BESTANDEN MIT {len(self._warnings)} AUFFÄLLIGKEIT(EN)")
        else:
            error_text = "Test fehlgeschlagen:\n" + "\n".join(
                f"• {err}" for err in self._errors
            )
            if self._warnings:
                error_text += "\n\nZusätzliche Auffälligkeiten:\n" + "\n".join(
                    f"• {w}" for w in self._warnings
                )
            self.result_label.configure(
                text=error_text,
                text_color=COLORS["error"]
            )
            logger.warning(f"System-Test: FEHLGESCHLAGEN - {self._errors}")

        self.result_label.pack(pady=(10, 5))
        if not self._errors:
            self.adjust_print_btn.pack(pady=(5, 0))
            self.new_event_btn.pack(pady=(5, 0))
        self.ok_btn.pack(pady=(5, 20))

    def _open_print_adjustment(self):
        """Schließt den Testdialog und öffnet die eingeschränkte Druckkorrektur."""
        self._destroyed = True
        self._cancelled.set()
        callback = self._on_adjust_print
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if callback:
            callback()

    def _shutdown_for_new_event(self):
        """Fährt Windows nach einem erfolgreichen Event-Test herunter."""
        import subprocess

        self.result_label.configure(
            text="Windows wird heruntergefahren...",
            text_color=COLORS["warning"]
        )
        self.adjust_print_btn.configure(state="disabled")
        self.new_event_btn.configure(state="disabled")
        self.ok_btn.configure(state="disabled")
        logger.info("System-Test: Herunterfahren bestätigt")
        subprocess.Popen(
            ["shutdown", "/s", "/f", "/t", "5", "/c", "FexoBooth: Neues Event bereit"],
            creationflags=0x08000000
        )

    def _close(self):
        """Dialog schließen"""
        self._destroyed = True
        self._cancelled.set()
        success = len(self._errors) == 0
        callback = self._on_complete
        self.grab_release()
        self.destroy()
        if callback:
            callback(success, self._errors)

    def destroy(self):
        """Override destroy um Flag zu setzen"""
        self._destroyed = True
        self._cancelled.set()
        super().destroy()
