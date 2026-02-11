"""Automatischer System-Test nach Event-Wechsel

Testet die komplette Kette: Kamera → Template → Druck
Zeigt Fortschritt und Ergebnis an.
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


class SystemTestDialog(ctk.CTkToplevel):
    """Automatischer System-Test nach Event-Wechsel"""

    STEPS = [
        ("Kamera initialisieren", "Kamera wird initialisiert..."),
        ("Testfoto aufnehmen", "Testfoto wird aufgenommen..."),
        ("Template anwenden", "Template wird angewendet..."),
        ("Testdruck starten", "Testdruck wird gesendet..."),
        ("Aufräumen", "Wird aufgeräumt..."),
    ]

    def __init__(self, parent, app, on_complete: callable):
        super().__init__(parent)

        self.app = app
        self._on_complete = on_complete
        self._test_photo: Optional[Image.Image] = None
        self._test_result: Optional[Image.Image] = None
        self._test_file: Optional[Path] = None
        self._errors: List[str] = []
        self._destroyed = False

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

        self._build_ui(screen_w, screen_h)

        # Test nach kurzem Delay starten
        self.after(500, self._start_test)
        logger.info("System-Test Dialog geöffnet")

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

        # OK-Button (zunächst unsichtbar)
        self.ok_btn = ctk.CTkButton(
            card,
            text="OK",
            font=FONTS["button_large"],
            width=160,
            height=50,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            corner_radius=SIZES["corner_radius"],
            command=self._close
        )
        # Wird erst nach Abschluss gepackt

    def _update_step(self, index: int, status: str, error_msg: str = ""):
        """Aktualisiert den Status eines Schritts (thread-safe Wrapper)"""
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

    def _update_status(self, text: str, progress: float):
        """Aktualisiert Status-Text und Fortschritt (thread-safe Wrapper)"""
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

    def _run_test(self):
        """Führt alle Test-Schritte durch"""
        steps = [
            self._step_init_camera,
            self._step_capture_photo,
            self._step_apply_template,
            self._step_print,
            self._step_cleanup,
        ]

        for i, step_func in enumerate(steps):
            step_name, status_text = self.STEPS[i]
            progress = i / len(steps)

            self.after(0, lambda idx=i: self._update_step(idx, "running"))
            self.after(0, lambda t=status_text, p=progress: self._update_status(t, p))

            # Kurze Pause damit UI-Update sichtbar ist
            time.sleep(0.3)

            try:
                step_func()
                self.after(0, lambda idx=i: self._update_step(idx, "success"))
            except Exception as e:
                error_msg = str(e)
                self._errors.append(f"{step_name}: {error_msg}")
                self.after(0, lambda idx=i, err=error_msg: self._update_step(idx, "error", err))
                logger.error(f"System-Test Schritt '{step_name}' fehlgeschlagen: {e}")

                # Bei Kamera- oder Foto-Fehler: restliche Schritte als übersprungen markieren
                if i < 2:
                    for j in range(i + 1, len(steps)):
                        self.after(0, lambda idx=j: self._update_step(idx, "error", "Übersprungen"))
                    break

        # Ergebnis anzeigen
        self.after(0, lambda: self._update_status("Test abgeschlossen", 1.0))
        self.after(100, lambda: self._show_result())

    def _step_init_camera(self):
        """Schritt 1: Kamera initialisieren"""
        cam_index = self.app.config.get("camera_index", 0)
        cam_settings = self.app.config.get("camera_settings", {})
        width = cam_settings.get("single_photo_width", 640)
        height = cam_settings.get("single_photo_height", 480)

        success = self.app.camera_manager.initialize(cam_index, width, height)
        if not success:
            raise Exception("Kamera nicht erreichbar")

        # Kurz warten bis Kamera bereit
        time.sleep(1.0)

    def _step_capture_photo(self):
        """Schritt 2: Testfoto aufnehmen"""
        photo = None

        # Canon DSLR
        if hasattr(self.app.camera_manager, 'capture_photo'):
            try:
                photo = self.app.camera_manager.capture_photo(timeout=10.0)
                if photo:
                    frame = np.array(photo)
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    if self.app.config.get("rotate_180", False):
                        frame = cv2.rotate(frame, cv2.ROTATE_180)
                    frame = cv2.flip(frame, 1)
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    photo = Image.fromarray(rgb)
            except Exception as e:
                logger.warning(f"DSLR Fehler bei Systemtest: {e}")

        # Webcam Fallback
        if photo is None:
            cam_settings = self.app.config.get("camera_settings", {})
            capture_w = cam_settings.get("single_photo_width", 1920)
            capture_h = cam_settings.get("single_photo_height", 1080)

            frame = None
            if hasattr(self.app.camera_manager, 'get_high_res_frame'):
                frame = self.app.camera_manager.get_high_res_frame(capture_w, capture_h)
            if frame is None and hasattr(self.app.camera_manager, 'get_frame'):
                frame = self.app.camera_manager.get_frame(use_cache=False)

            if frame is not None:
                if self.app.config.get("rotate_180", False):
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                photo = Image.fromarray(rgb)

        if photo is None:
            raise Exception("Foto konnte nicht aufgenommen werden")

        self._test_photo = photo
        logger.info(f"System-Test: Testfoto aufgenommen ({photo.size})")

    def _step_apply_template(self):
        """Schritt 3: Template auf Testfoto anwenden"""
        if self._test_photo is None:
            raise Exception("Kein Testfoto vorhanden")

        boxes = self.app.template_boxes
        overlay = self.app.overlay_image

        if not boxes:
            raise Exception("Keine Template-Boxen geladen")

        # Foto für alle Slots verwenden (Testbild)
        photos = [self._test_photo] * len(boxes)

        self._test_result = self.app.renderer.render(photos, boxes, overlay)
        logger.info(f"System-Test: Template angewendet ({self._test_result.size})")

    def _step_print(self):
        """Schritt 4: Testdruck ausführen"""
        if self._test_result is None:
            raise Exception("Kein Testbild zum Drucken")

        # Temporäre Datei speichern
        temp_dir = Path(tempfile.gettempdir())
        self._test_file = temp_dir / "fexobooth_systemtest.jpg"

        # RGBA → RGB konvertieren für JPEG
        img_rgb = self._test_result.convert("RGB")
        img_rgb.save(str(self._test_file), "JPEG", quality=95)
        logger.info(f"System-Test: Testbild gespeichert: {self._test_file}")

        # GDI-Druck (repliziert aus final.py)
        self._print_via_gdi(self._test_file)

    def _print_via_gdi(self, image_path: Path):
        """Druckt über Windows GDI (aus final.py repliziert)"""
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

        try:
            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(printer_name)
            hDC.StartDoc("Fexobooth Systemtest")
            hDC.StartPage()

            dib = ImageWin.Dib(img)
            dib.draw(
                hDC.GetHandleOutput(),
                (offset_x, offset_y, offset_x + base_width, offset_y + base_height)
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

        self._test_photo = None
        self._test_result = None

    def _show_result(self):
        """Zeigt das Testergebnis an"""
        if self._destroyed:
            return

        if not self._errors:
            self.result_label.configure(
                text="Test abgeschlossen - Alles OK!",
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
        success = len(self._errors) == 0
        callback = self._on_complete
        self.grab_release()
        self.destroy()
        if callback:
            callback(success, self._errors)

    def destroy(self):
        """Override destroy um Flag zu setzen"""
        self._destroyed = True
        super().destroy()
