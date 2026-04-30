"""Automatischer System-Test nach Event-Wechsel

Führt eine komplette Test-Session durch:
Kamera init → Foto pro Template-Slot → Template rendern → Testdruck
"""

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
ICON_ERROR = "❌"

# Pause zwischen Fotos (Sekunden) - Kamera braucht Zeit zum Nachregeln
PHOTO_DELAY = 2.0

# Maximale Gesamtdauer des Tests (Sekunden) - danach wird abgebrochen
GLOBAL_TIMEOUT = 90


class SystemTestDialog(ctk.CTkToplevel):
    """Automatischer System-Test nach Event-Wechsel.

    Fotografiert jeden Template-Slot einzeln und druckt das Ergebnis.
    Hat einen globalen Timeout und Abbrechen-Button für den Notfall.
    """

    def __init__(self, parent, app, on_complete: callable):
        super().__init__(parent)

        self.app = app
        self._on_complete = on_complete
        self._test_photos: List[Image.Image] = []
        self._test_result: Optional[Image.Image] = None
        self._test_file: Optional[Path] = None
        self._errors: List[str] = []
        self._destroyed = False
        self._cancelled = threading.Event()  # Thread-sicheres Abbruch-Signal

        # Anzahl Foto-Slots aus Template ermitteln
        self._num_photos = max(len(self.app.template_boxes), 1)

        # Schritte definieren (dynamisch je nach Template)
        foto_text = f"Fotos aufnehmen ({self._num_photos} Stück)"
        self.STEPS = [
            ("Kamera initialisieren", "Kamera wird initialisiert..."),
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
                if i < 2:
                    for j in range(i + 1, len(steps)):
                        self.after(0, lambda idx=j: self._update_step(idx, "error", "Übersprungen"))
                    break

        # Ergebnis anzeigen (nur wenn nicht bereits durch Cancel/Timeout geschehen)
        if not self._destroyed:
            self.after(0, lambda: self._update_status("Test abgeschlossen", 1.0))
            self.after(100, lambda: self._show_result())

    def _step_init_camera(self):
        """Schritt 1: Kamera initialisieren"""
        if self._cancelled.is_set():
            raise Exception("Abgebrochen")

        cam_index = self.app.config.get("camera_index", 0)
        cam_settings = self.app.config.get("camera_settings", {})
        width = cam_settings.get("single_photo_width", 640)
        height = cam_settings.get("single_photo_height", 480)

        success = self.app.camera_manager.initialize(cam_index, width, height)
        if not success:
            raise Exception("Kamera nicht erreichbar")

        # Kurz warten bis Kamera bereit
        time.sleep(1.0)

    def _capture_single_photo(self) -> Image.Image:
        """Nimmt ein Foto für den System-Test auf.

        Nutzt immer LiveView-Frames (kein echtes Auslösen der DSLR).
        Der System-Test prüft nur ob Kamera, Template und Drucker funktionieren -
        volle DSLR-Qualität ist dafür nicht nötig und spart SD-Karten-Abhängigkeit.
        """
        if self._cancelled.is_set():
            raise Exception("Abgebrochen")

        # LiveView-Frame holen (funktioniert mit DSLR und Webcam)
        frame = None

        # Bei Canon DSLR: LiveView starten falls nicht aktiv
        if hasattr(self.app.camera_manager, 'start_live_view'):
            if not self.app.camera_manager._live_view_active:
                self.app.camera_manager.start_live_view()

        # Mehrere Versuche (LiveView braucht nach Start ~1-2s für gültige Frames)
        for attempt in range(15):
            if self._cancelled.is_set():
                raise Exception("Abgebrochen")
            frame = self.app.camera_manager.get_frame(use_cache=False)
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
        """Schritt 2: Ein Foto pro Template-Slot aufnehmen"""
        total = self._num_photos
        self._test_photos = []

        for i in range(total):
            if self._cancelled.is_set():
                raise Exception("Abgebrochen")

            nr = i + 1

            # UI: "Foto 2 von 4 aufnehmen..."
            self.after(0, lambda n=nr, t=total:
                self._update_step_text(1, f"Foto {n} von {t} aufnehmen..."))
            self.after(0, lambda n=nr, t=total:
                self._update_status(
                    f"Foto {n} von {t} wird aufgenommen...",
                    (1 + n / t) / 5  # Schritt 2 von 5, anteilig
                ))

            # Zwischen Fotos kurz warten (nicht vor dem ersten)
            if i > 0:
                time.sleep(PHOTO_DELAY)

            photo = self._capture_single_photo()
            self._test_photos.append(photo)
            logger.info(f"System-Test: Foto {nr}/{total} aufgenommen ({photo.size})")

        # Finalen Step-Text setzen
        self.after(0, lambda t=total:
            self._update_step_text(1, f"Fotos aufnehmen ({t} Stück)"))

    def _step_apply_template(self):
        """Schritt 3: Template mit allen Fotos rendern"""
        if self._cancelled.is_set():
            raise Exception("Abgebrochen")

        if not self._test_photos:
            raise Exception("Keine Testfotos vorhanden")

        boxes = self.app.template_boxes
        overlay = self.app.overlay_image

        if not boxes:
            raise Exception("Keine Template-Boxen geladen")

        self._test_result = self.app.renderer.render(
            self._test_photos, boxes, overlay
        )
        logger.info(f"System-Test: Template angewendet ({self._test_result.size})")

    def _step_print(self):
        """Schritt 4: Testdruck ausführen"""
        if self._cancelled.is_set():
            raise Exception("Abgebrochen")

        if self._test_result is None:
            raise Exception("Kein Testbild zum Drucken")

        # Temporäre Datei speichern
        temp_dir = Path(tempfile.gettempdir())
        self._test_file = temp_dir / "fexobooth_systemtest.jpg"

        # RGBA → RGB konvertieren für JPEG
        img_rgb = self._test_result.convert("RGB")
        img_rgb.save(str(self._test_file), "JPEG", quality=95)
        logger.info(f"System-Test: Testbild gespeichert: {self._test_file}")

        # GDI-Druck
        self._print_via_gdi(self._test_file)

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
        """Schritt 5: Testdateien aufräumen"""
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

        if not self._errors:
            self.result_label.configure(
                text=f"Alles OK! Testdruck mit {self._num_photos} Fotos gesendet.",
                text_color=COLORS["success"]
            )
            logger.info("System-Test: ERFOLGREICH")
        else:
            error_text = "Test fehlgeschlagen:\n" + "\n".join(
                f"• {err}" for err in self._errors
            )
            self.result_label.configure(
                text=error_text,
                text_color=COLORS["error"]
            )
            logger.warning(f"System-Test: FEHLGESCHLAGEN - {self._errors}")

        self.result_label.pack(pady=(10, 5))
        self.ok_btn.pack(pady=(5, 20))

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
