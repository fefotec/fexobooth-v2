"""Final-Screen - Fertiges Bild mit Druck-Option

Sauberes Pack-Layout: Bild zentriert mit Rand, Buttons darunter.
Kein Overlay/place() - vermeidet Transparenz-Probleme in CustomTkinter.
"""

import customtkinter as ctk
from PIL import Image
from typing import TYPE_CHECKING, Optional
from pathlib import Path
import time

from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class FinalScreen(ctk.CTkFrame):
    """Final-Screen mit fertigem Bild und Aktionen"""

    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.app = app
        self.config = app.config

        self.final_image: Optional[Image.Image] = None
        self.prints_count = 0
        self.auto_return_time = 0
        self.is_active = False

        self._setup_ui()

    def _setup_ui(self):
        """Erstellt die UI - Pack-Layout ohne Overlays"""
        # Countdown/Status-Text oben
        self.subtitle_label = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self.subtitle_label.pack(pady=(8, 0))

        # Bild-Container mit großzügigem Rand
        self.image_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.image_frame.pack(fill="both", expand=True, padx=60, pady=(5, 5))

        self.preview_label = ctk.CTkLabel(self.image_frame, text="", fg_color="transparent")
        self.preview_label.pack(expand=True)

        # Druck-Info
        self.print_info = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["body_bold"] if "body_bold" in FONTS else FONTS["body"],
            text_color=COLORS["text_primary"],
        )
        self.print_info.pack(pady=(2, 0))

        # Button-Leiste
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(pady=(5, 0))

        # NOCHMAL Button
        self.redo_btn = ctk.CTkButton(
            button_frame,
            text=self.config.get("ui_texts", {}).get("redo", "NOCHMAL"),
            font=("Segoe UI", 16, "bold"),
            width=160,
            height=55,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            corner_radius=SIZES["corner_radius"],
            command=self._on_redo
        )
        self.redo_btn.pack(side="left", padx=10)

        # DRUCKEN Button
        self.print_btn = ctk.CTkButton(
            button_frame,
            text=f"DRUCKEN",
            font=("Segoe UI", 20, "bold"),
            width=220,
            height=65,
            fg_color=COLORS["success"],
            hover_color="#00e676",
            corner_radius=SIZES["corner_radius"],
            command=self._on_print
        )
        self.print_btn.pack(side="left", padx=10)

        # FERTIG Button
        if not self.config.get("hide_finish_button", False):
            self.finish_btn = ctk.CTkButton(
                button_frame,
                text=self.config.get("ui_texts", {}).get("finish", "FERTIG"),
                font=("Segoe UI", 16, "bold"),
                width=160,
                height=55,
                fg_color=COLORS["bg_light"],
                hover_color=COLORS["bg_card"],
                corner_radius=SIZES["corner_radius"],
                command=self._on_finish
            )
            self.finish_btn.pack(side="left", padx=10)

        # Progress-Bar
        self.progress_bar = ctk.CTkProgressBar(
            self,
            width=500,
            height=4,
            fg_color=COLORS["bg_light"],
            progress_color=COLORS["primary"],
            corner_radius=2
        )
        self.progress_bar.pack(pady=(8, 12))
        self.progress_bar.set(1.0)

    def _render_final_image(self) -> Image.Image:
        """Rendert das finale Bild"""
        filtered_photos = [
            self.app.filter_manager.apply(photo, self.app.current_filter)
            for photo in self.app.photos_taken
        ]

        return self.app.renderer.render(
            filtered_photos,
            self.app.template_boxes,
            self.app.overlay_image
        )

    def _update_countdown(self):
        """Aktualisiert den Auto-Return Countdown"""
        if not self.is_active:
            return

        remaining = self.auto_return_time - time.time()

        if remaining <= 0:
            self._on_finish()
            return

        # Progress-Bar aktualisieren
        total_time = self.config.get("final_time", 30)
        progress = remaining / total_time
        self.progress_bar.set(progress)

        # Untertitel aktualisieren
        self.subtitle_label.configure(
            text=f"Automatisch zurück in {int(remaining)} Sekunden..."
        )

        self.after(100, self._update_countdown)

    def _on_redo(self):
        """Nochmal gedrückt - neue Session"""
        logger.info("Redo - neue Session")
        self.is_active = False
        self.app.reset_session()
        self.app.play_video("video_end", "start")

    def _on_print(self):
        """Drucken gedrückt"""
        max_prints = self.config.get("max_prints_per_session", 1)

        if self.prints_count >= max_prints:
            self.print_info.configure(
                text="Maximale Anzahl Drucke erreicht!",
                text_color=COLORS["warning"]
            )
            return

        logger.info("Drucke Bild...")

        self.print_btn.configure(state="disabled", text="Wird gedruckt...")

        if self.final_image:
            saved_path = self.app.local_storage.save_print(
                self.final_image.convert("RGB"),
                suffix=f"print_{self.prints_count + 1}"
            )

            if saved_path:
                self.app.usb_manager.copy_to_usb(saved_path, "Prints")
                self._print_image(saved_path)

                self.prints_count += 1
                self.app.prints_in_session = self.prints_count
                self.app.statistics.record_print_success()

                remaining = max_prints - self.prints_count
                if remaining > 0:
                    self.print_info.configure(
                        text=f"Gedruckt! Noch {remaining} Druck(e) möglich",
                        text_color=COLORS["success"]
                    )
                    self.print_btn.configure(
                        state="normal",
                        text=f"{self.config.get('ui_texts', {}).get('print', 'DRUCKEN')}"
                    )
                else:
                    self.print_info.configure(
                        text="Gedruckt! Keine weiteren Drucke möglich",
                        text_color=COLORS["text_primary"]
                    )
                    self.print_btn.configure(
                        state="disabled",
                        text="Limit erreicht",
                        fg_color=COLORS["bg_light"]
                    )

        # Auto-Return Timer zurücksetzen
        self.auto_return_time = time.time() + self.config.get("final_time", 30)

    def _print_image(self, image_path: Path):
        """Druckt ein Bild über GDI

        Verwendet feste Pixelwerte die zum 10x15cm Fotodrucker passen.
        Kein Dialog - vollautomatisch im Hintergrund.
        """
        try:
            import win32print
            import win32ui
            from PIL import ImageWin

            printer_name = self.config.get("printer_name")
            if not printer_name:
                printer_name = win32print.GetDefaultPrinter()

            available_printers = [p[2] for p in win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )]

            if printer_name not in available_printers:
                logger.error(f"Drucker nicht gefunden: '{printer_name}'")
                logger.info(f"Verfügbare Drucker: {available_printers}")
                self.print_info.configure(
                    text=f"Drucker '{printer_name}' nicht gefunden!",
                    text_color=COLORS["error"]
                )
                return

            logger.info(f"Drucke auf: {printer_name}")
            logger.info(f"Bild: {image_path}")

            adjustment = self.config.get("print_adjustment", {})
            offset_x = adjustment.get("offset_x", 0)
            offset_y = adjustment.get("offset_y", 0)
            zoom = adjustment.get("zoom", 100) / 100

            img = Image.open(image_path)
            logger.info(f"Original-Bild: {img.size}")

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

            logger.info(f"Bild skaliert auf: {img.size} (Zoom: {int(zoom*100)}%)")

            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(printer_name)

            hDC.StartDoc("Fexobooth Print")
            hDC.StartPage()

            dib = ImageWin.Dib(img)
            dib.draw(
                hDC.GetHandleOutput(),
                (offset_x, offset_y, offset_x + base_width, offset_y + base_height)
            )

            hDC.EndPage()
            hDC.EndDoc()
            hDC.DeleteDC()

            logger.info(f"Gedruckt auf: {printer_name} "
                       f"(Größe: {base_width}x{base_height}, Offset: {offset_x},{offset_y})")

        except ImportError as e:
            logger.warning(f"Import-Fehler: {e} - Druck nur unter Windows")
            self.print_info.configure(
                text="Druck nur unter Windows verfügbar",
                text_color=COLORS["warning"]
            )
        except Exception as e:
            logger.error(f"Druckfehler: {e}")
            import traceback
            logger.error(traceback.format_exc())

            error_str = str(e)
            if "1801" in error_str or "unzulässig" in error_str.lower():
                msg = "Drucker nicht erreichbar!"
            elif "offline" in error_str.lower():
                msg = "Drucker ist offline!"
            elif "paper" in error_str.lower() or "papier" in error_str.lower():
                msg = "Kein Papier im Drucker!"
            else:
                msg = "Druckfehler"

            self.print_info.configure(
                text=msg,
                text_color=COLORS["error"]
            )

    def _save_final_image(self):
        """Speichert das finale Bild IMMER (nicht nur bei Druck)"""
        if self.final_image is None:
            logger.warning("Kein finales Bild zum Speichern")
            return

        try:
            saved_path = self.app.local_storage.save_print(
                self.final_image,
                suffix="final"
            )

            if saved_path:
                logger.info(f"Finales Bild gespeichert: {saved_path}")
                self.app.usb_manager.copy_to_usb(saved_path, "Prints")
            else:
                logger.warning("Finales Bild konnte nicht gespeichert werden")

        except Exception as e:
            logger.error(f"Fehler beim Speichern des finalen Bildes: {e}")

    def _on_finish(self):
        """Fertig gedrückt"""
        logger.info("Session beendet")
        self.is_active = False

        self.app.statistics.record_session()

        self.app.reset_session()
        self.app.play_video("video_end", "start")

    def on_show(self):
        """Screen wird angezeigt"""
        logger.info("Final-Screen angezeigt")
        self.is_active = True
        self.prints_count = 0

        # Finales Bild rendern
        self.final_image = self._render_final_image()

        # IMMER speichern
        self._save_final_image()

        # Vorschau anzeigen - Image-Frame Größe ermitteln
        self.update_idletasks()
        container_w = self.image_frame.winfo_width()
        container_h = self.image_frame.winfo_height()

        if container_w < 100:
            container_w = 900
        if container_h < 100:
            container_h = 500

        preview = self.final_image.copy()
        preview.thumbnail((container_w, container_h), Image.Resampling.LANCZOS)

        ctk_img = ctk.CTkImage(light_image=preview, dark_image=preview, size=preview.size)
        self.preview_label.configure(image=ctk_img)
        self.preview_label.image = ctk_img

        # Druck-Button zurücksetzen
        max_prints = self.config.get("max_prints_per_session", 1)
        self.print_btn.configure(
            state="normal",
            text=f"{self.config.get('ui_texts', {}).get('print', 'DRUCKEN')}",
            fg_color=COLORS["success"]
        )
        self.print_info.configure(
            text=f"{max_prints} Druck(e) verfügbar",
            text_color=COLORS["text_primary"]
        )

        # Auto-Return Timer starten
        self.auto_return_time = time.time() + self.config.get("final_time", 30)
        self.progress_bar.set(1.0)
        self._update_countdown()

    def on_hide(self):
        """Screen wird verlassen"""
        self.is_active = False
