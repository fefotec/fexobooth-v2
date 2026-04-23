"""Final-Screen - Fertiges Bild mit Druck-Option

Bild oben (expand), schwarze Button-Leiste unten (fest).
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
        """Erstellt die UI - Bild oben, schwarze Button-Leiste unten.

        Pack-Reihenfolge: bottom-Elemente ZUERST, dann expand=True für Bild.
        """
        # === 1. Progress-Bar ganz unten (zuerst packen!) ===
        self.progress_bar = ctk.CTkProgressBar(
            self,
            height=4,
            fg_color=COLORS["bg_light"],
            progress_color=COLORS["primary"],
            corner_radius=2
        )
        self.progress_bar.pack(fill="x", side="bottom")
        self.progress_bar.set(1.0)

        # === 2. Schwarze Button-Leiste (vor dem Bild packen!) ===
        bottom_bar = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], corner_radius=0, height=90)
        bottom_bar.pack(fill="x", side="bottom")
        bottom_bar.pack_propagate(False)

        # Innerer Container für zentrierte Ausrichtung
        bar_inner = ctk.CTkFrame(bottom_bar, fg_color="transparent")
        bar_inner.pack(expand=True, fill="both", padx=15, pady=8)

        # Druck-Info (oben in der Leiste)
        self.print_info = ctk.CTkLabel(
            bar_inner,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            fg_color="transparent"
        )
        self.print_info.pack(side="top", pady=(0, 2))

        # Button-Container (unten in der Leiste)
        btn_frame = ctk.CTkFrame(bar_inner, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", pady=(0, 2))

        # DRUCKEN Button (mitte, prominent) - nur wenn Drucken aktiviert
        if self.config.get("print_enabled", True):
            self.print_btn = ctk.CTkButton(
                btn_frame,
                text="DRUCKEN",
                font=("Segoe UI", 22, "bold"),
                width=220,
                height=55,
                fg_color=COLORS["success"],
                hover_color="#00e676",
                corner_radius=14,
                command=self._on_print
            )
            self.print_btn.pack(side="left", expand=True)
        else:
            self.print_btn = None

        # FERTIG Button (rechts)
        if not self.config.get("hide_finish_button", False):
            self.finish_btn = ctk.CTkButton(
                btn_frame,
                text=self.config.get("ui_texts", {}).get("finish", "FERTIG"),
                font=("Segoe UI", 18, "bold"),
                width=160,
                height=50,
                fg_color=COLORS["bg_light"],
                hover_color=COLORS["bg_card"],
                text_color=COLORS["text_primary"],
                corner_radius=12,
                command=self._on_finish
            )
            self.finish_btn.pack(side="right", padx=(0, 10))

        # === 3. Countdown-Text oben ===
        self.subtitle_label = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["bg_dark"]
        )
        self.subtitle_label.pack(fill="x", side="top", pady=(2, 0))

        # === 4. Bild-Container (füllt den restlichen Raum) ===
        self.image_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"], corner_radius=0)
        self.image_frame.pack(fill="both", expand=True, padx=10, pady=(0, 0))

        self.preview_label = ctk.CTkLabel(self.image_frame, text="", fg_color="transparent")
        self.preview_label.pack(expand=True, fill="both")

    def _render_final_image(self) -> Image.Image:
        """Rendert das finale Bild"""
        logger.info(f"Rendere finales Bild: {len(self.app.photos_taken)} Fotos, "
                     f"Filter '{self.app.current_filter}'")
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

        total_time = self.config.get("final_time", 30)
        progress = remaining / total_time
        self.progress_bar.set(progress)

        self.subtitle_label.configure(
            text=f"Automatisch zurück in {int(remaining)} Sekunden..."
        )

        self.after(100, self._update_countdown)

    def _on_print(self):
        """Drucken gedrückt"""
        max_prints = self.config.get("max_prints_per_session", 1)

        if self.prints_count >= max_prints:
            self.print_info.configure(
                text="Maximale Anzahl Drucke erreicht!",
                text_color=COLORS["warning"]
            )
            return

        # Drucker-Status prüfen bevor gedruckt wird
        if self._check_printer_before_print():
            return  # Drucker nicht bereit, Meldung wird angezeigt

        logger.info("Drucke Bild...")

        if self.print_btn:
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

                # Lifetime-Drucker-Zähler hochzählen
                from src.storage.printer_lifetime import get_printer_lifetime
                get_printer_lifetime().increment()

                remaining = max_prints - self.prints_count
                if remaining > 0:
                    self.print_info.configure(
                        text=f"Gedruckt! Noch {remaining} Druck(e) möglich",
                        text_color=COLORS["success"]
                    )
                    if self.print_btn:
                        self.print_btn.configure(
                            state="normal",
                            text=f"{self.config.get('ui_texts', {}).get('print', 'DRUCKEN')}"
                        )
                else:
                    self.print_info.configure(
                        text="Gedruckt! Keine weiteren Drucke möglich",
                        text_color=COLORS["text_primary"]
                    )
                    if self.print_btn:
                        self.print_btn.configure(
                            state="disabled",
                            text="Limit erreicht",
                            fg_color=COLORS["bg_light"]
                        )

        # Auto-Return Timer zurücksetzen
        self.auto_return_time = time.time() + self.config.get("final_time", 30)

    def _check_printer_before_print(self) -> bool:
        """Prüft ob der Drucker bereit ist. Zeigt Meldung wenn nicht.
        Returns True wenn Drucker NICHT bereit (= abbrechen)."""
        try:
            from src.printer.controller import get_printer_controller
            controller = get_printer_controller()
            controller.update_printer_name(self.config.get("printer_name", ""))
            error = controller.get_error()

            if error:
                # Fehlermeldung je nach Problem
                if "AUS" in error or "FEHLT" in error or "KEIN" in error:
                    msg = "Drucker ist aus! Bitte einschalten und warten bis das Display leuchtet."
                elif "PAPIER" in error and "STAU" in error:
                    msg = "Papierstau! Bitte Drucker öffnen und Papier entfernen."
                elif "PAPIER" in error:
                    msg = "Kein Papier! Bitte Papier nachlegen."
                elif "KASSETTE" in error:
                    msg = "Farbkassette leer! Bitte wechseln."
                elif "KLAPPE" in error:
                    msg = "Druckerklappe offen! Bitte schließen."
                else:
                    msg = f"Drucker meldet: {error}"

                logger.warning(f"Drucken abgebrochen - Drucker nicht bereit: {error}")
                self._show_printer_warning(msg)
                return True

        except Exception as e:
            logger.debug(f"Drucker-Prüfung fehlgeschlagen: {e}")

        return False

    def _show_printer_warning(self, message: str):
        """Zeigt Drucker-Warnung als Overlay über dem Final-Screen"""
        overlay = ctk.CTkFrame(self, fg_color="rgba(0,0,0,0.85)" if hasattr(ctk, 'TRANSPARENT') else "#1a1a1a")
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Zentrierter Container
        container = ctk.CTkFrame(overlay, fg_color=COLORS["bg_card"], corner_radius=20, width=500, height=280)
        container.place(relx=0.5, rely=0.5, anchor="center")
        container.pack_propagate(False)

        # Drucker-Icon
        ctk.CTkLabel(
            container, text="🖨️", font=("Segoe UI", 48),
            fg_color="transparent"
        ).pack(pady=(30, 10))

        # Meldung
        ctk.CTkLabel(
            container, text=message,
            font=("Segoe UI", 16, "bold"),
            text_color=COLORS["warning"],
            fg_color="transparent",
            wraplength=400
        ).pack(pady=(0, 20))

        def close_warning():
            overlay.destroy()

        # OK-Button
        ctk.CTkButton(
            container, text="Verstanden",
            font=("Segoe UI", 16, "bold"),
            width=200, height=45,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"] if "primary_hover" in COLORS else COLORS["primary"],
            corner_radius=12,
            command=close_warning
        ).pack(pady=(0, 20))

        # Auto-schließen nach 8 Sekunden
        overlay.after(8000, lambda: overlay.destroy() if overlay.winfo_exists() else None)

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
                # Fuzzy-Match: Drucker-Kopien erkennen (anderer USB-Port)
                from src.printer import find_matching_printer
                matched = find_matching_printer(printer_name, available_printers)
                if matched:
                    printer_name = matched
                else:
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

            # Zoom zentriert: Offset so berechnen, dass sich das Bild
            # gleichmäßig nach allen Seiten ausdehnt statt nur nach rechts-unten
            center_offset_x = -int((1772 * (zoom - 1)) / 2)
            center_offset_y = -int((1181 * (zoom - 1)) / 2)
            draw_x = offset_x + center_offset_x
            draw_y = offset_y + center_offset_y

            logger.info(f"Bild skaliert auf: {img.size} (Zoom: {int(zoom*100)}%, "
                        f"Zentrierung: {center_offset_x},{center_offset_y})")

            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(printer_name)

            hDC.StartDoc("Fexobooth Print")
            hDC.StartPage()

            dib = ImageWin.Dib(img)
            dib.draw(
                hDC.GetHandleOutput(),
                (draw_x, draw_y, draw_x + base_width, draw_y + base_height)
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
            container_w = 1000
        if container_h < 100:
            container_h = 500

        # Bild auf Container-Größe skalieren (Seitenverhältnis beibehalten)
        preview = self.final_image.copy()
        preview.thumbnail((container_w, container_h), Image.Resampling.LANCZOS)

        # CTkImage size in logischen Pixeln (DPI-korrigiert)
        scaling = self._get_widget_scaling()
        logical_size = (int(preview.size[0] / scaling), int(preview.size[1] / scaling))
        ctk_img = ctk.CTkImage(light_image=preview, dark_image=preview, size=logical_size)
        self.preview_label.configure(image=ctk_img)
        self.preview_label.image = ctk_img

        # Druck-Button zurücksetzen
        max_prints = self.config.get("max_prints_per_session", 1)
        if self.print_btn:
            self.print_btn.configure(
                state="normal",
                text=f"{self.config.get('ui_texts', {}).get('print', 'DRUCKEN')}",
                fg_color=COLORS["success"]
            )
        self.print_info.configure(
            text=f"{max_prints} Druck(e) verfügbar" if self.print_btn else "Drucken deaktiviert",
            text_color=COLORS["text_primary"] if self.print_btn else COLORS["text_muted"]
        )

        # Auto-Return Timer starten
        self.auto_return_time = time.time() + self.config.get("final_time", 30)
        self.progress_bar.set(1.0)
        self._update_countdown()

    def on_hide(self):
        """Screen wird verlassen"""
        self.is_active = False
