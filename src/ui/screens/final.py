"""Final-Screen - Fertiges Bild mit Druck-Option

Bild oben (expand), schwarze Button-Leiste unten (fest).
"""

import customtkinter as ctk
from PIL import Image
from typing import TYPE_CHECKING, Optional
from pathlib import Path
import threading
import time

from src.ui.theme import COLORS, FONTS, SIZES
from src.ui.error_images import load_printer_error_image
from src.utils.logging import get_logger
from src.i18n import t

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
        self._is_printing = False
        self._print_quantity_dialog: Optional[ctk.CTkToplevel] = None

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
                text=t(self.config, "common.print"),
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
                text=t(self.config, "common.finish"),
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
            text=t(self.config, "final.auto_return", seconds=int(remaining))
        )

        self.after(100, self._update_countdown)

    def _on_print(self):
        """Drucken gedrückt"""
        if self._is_printing:
            return

        remaining = self._get_remaining_prints()
        if remaining <= 0:
            self._update_print_button_state()
            return

        # Auto-Return Timer zurücksetzen sobald der Gast mit Drucken interagiert
        self.auto_return_time = time.time() + self.config.get("final_time", 30)

        if self._get_max_prints() > 1 and remaining > 1:
            self._show_print_quantity_dialog(remaining)
        else:
            self._start_prints(1)

    def _get_max_prints(self) -> int:
        """Gibt die maximal erlaubten Prints als sichere Zahl zurück."""
        try:
            return max(0, int(self.config.get("max_prints_per_session", 1)))
        except (TypeError, ValueError):
            return 1

    def _get_remaining_prints(self) -> int:
        """Gibt zurück, wie viele Prints in dieser Session noch erlaubt sind."""
        return max(0, self._get_max_prints() - self.prints_count)

    def _start_prints(self, quantity: int):
        """Startet einen oder mehrere Druckaufträge."""
        if self._is_printing:
            return

        remaining = self._get_remaining_prints()
        quantity = max(0, min(int(quantity), remaining))
        if quantity <= 0:
            self._update_print_button_state()
            return

        # Drucker-Status prüfen bevor gedruckt wird
        if self._check_printer_before_print():
            return  # Drucker nicht bereit, Meldung wird angezeigt

        logger.info(f"Drucke Bild ({quantity}x)...")
        self._is_printing = True
        self._set_printing_state(quantity)

        printed_count = 0
        had_error = False
        try:
            if not self.final_image:
                logger.warning("Kein finales Bild zum Drucken vorhanden")
                self.print_info.configure(
                    text=t(self.config, "final.no_image"),
                    text_color=COLORS["error"]
                )
                self._restore_print_button_after_error()
                return

            from src.storage.printer_lifetime import get_printer_lifetime
            lifetime_counter = get_printer_lifetime()

            for _ in range(quantity):
                print_number = self.prints_count + 1
                saved_path = self.app.local_storage.save_print(
                    self.final_image.convert("RGB"),
                    suffix=f"print_{print_number}"
                )

                if not saved_path:
                    had_error = True
                    self.print_info.configure(
                        text=t(self.config, "final.save_error"),
                        text_color=COLORS["error"]
                    )
                    break

                self.app.usb_manager.copy_to_usb(saved_path, "Prints")
                self._print_image(saved_path)

                self.prints_count += 1
                printed_count += 1
                self.app.prints_in_session = self.prints_count
                self.app.statistics.record_print_success()
                lifetime_counter.increment()

            if printed_count > 0 or not had_error:
                self._update_print_button_state(printed_count)
            else:
                self._restore_print_button_after_error()
        finally:
            self._is_printing = False
            # Auto-Return Timer zurücksetzen
            self.auto_return_time = time.time() + self.config.get("final_time", 30)

    def _set_printing_state(self, quantity: int):
        """Zeigt am Druck-Button, dass gerade gedruckt wird."""
        if self.print_btn:
            self.print_btn.configure(
                state="disabled",
                text=t(self.config, "final.printing"),
                fg_color=COLORS["success"]
            )

        if quantity > 1:
            info_text = t(self.config, "final.jobs_sending", quantity=quantity)
        else:
            info_text = t(self.config, "final.job_sending")
        self.print_info.configure(text=info_text, text_color=COLORS["success"])

    def _update_print_button_state(self, printed_count: int = 0):
        """Aktualisiert Button und Info ohne Limit-Hinweis für Gäste."""
        remaining = self._get_remaining_prints()
        button_text = t(self.config, "common.print")

        if remaining > 0:
            if printed_count > 0:
                if printed_count == 1:
                    info_text = t(self.config, "final.job_sent_remaining", remaining=remaining)
                else:
                    info_text = t(self.config, "final.jobs_sent_remaining", printed=printed_count, remaining=remaining)
            else:
                info_text = t(self.config, "final.prints_available", remaining=remaining)

            if self.print_btn:
                self.print_btn.configure(
                    state="normal",
                    text=button_text,
                    fg_color=COLORS["success"]
                )
            self.print_info.configure(text=info_text, text_color=COLORS["success"])
            return

        if printed_count > 1:
            info_text = t(self.config, "final.jobs_sent", printed=printed_count)
        elif printed_count == 1:
            info_text = t(self.config, "final.job_sent")
        else:
            info_text = t(self.config, "final.print_unavailable")

        if self.print_btn:
            self.print_btn.configure(
                state="disabled",
                text=t(self.config, "final.printing") if printed_count > 0 else button_text,
                fg_color=COLORS["success"] if printed_count > 0 else COLORS["bg_light"]
            )
        self.print_info.configure(
            text=info_text,
            text_color=COLORS["success"] if printed_count > 0 else COLORS["text_muted"]
        )

    def _restore_print_button_after_error(self):
        """Reaktiviert den Druck-Button nach lokalen Fehlern."""
        if not self.print_btn:
            return

        button_text = t(self.config, "common.print")
        if self._get_remaining_prints() > 0:
            self.print_btn.configure(
                state="normal",
                text=button_text,
                fg_color=COLORS["success"]
            )
        else:
            self.print_btn.configure(
                state="disabled",
                text=button_text,
                fg_color=COLORS["bg_light"]
            )

    def _show_print_quantity_dialog(self, max_quantity: int):
        """Zeigt eine Touch-Auswahl für die gewünschte Anzahl Prints."""
        if self._print_quantity_dialog and self._print_quantity_dialog.winfo_exists():
            self._print_quantity_dialog.lift()
            return

        parent = self.winfo_toplevel()
        dialog = ctk.CTkToplevel(parent)
        self._print_quantity_dialog = dialog

        dialog.overrideredirect(True)
        screen_w = dialog.winfo_screenwidth()
        screen_h = dialog.winfo_screenheight()
        dialog.geometry(f"{screen_w}x{screen_h}+0+0")
        dialog.configure(fg_color="#0a0a10")
        dialog.attributes("-topmost", True)
        dialog.transient(parent)
        dialog.grab_set()
        dialog.focus_force()

        def close_dialog():
            self._close_print_quantity_dialog(dialog)

        def choose_quantity(amount: int):
            close_dialog()
            self._start_prints(amount)

        def emergency_quit():
            close_dialog()
            if hasattr(self.app, "_emergency_quit"):
                self.app._emergency_quit()

        dialog.bind("<Escape>", lambda e: close_dialog())
        dialog.bind("<Control-Shift-Q>", lambda e: emergency_quit())
        dialog.bind("<Control-Shift-q>", lambda e: emergency_quit())

        bg_frame = ctk.CTkFrame(dialog, fg_color="#0a0a10", corner_radius=0)
        bg_frame.pack(fill="both", expand=True)

        card_w = min(620, int(screen_w * 0.86))
        card = ctk.CTkFrame(
            bg_frame,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["success"],
            border_width=3,
            corner_radius=20
        )
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.bind("<Button-1>", lambda e: "break")

        ctk.CTkLabel(
            card,
            text=t(self.config, "final.quantity_question"),
            font=FONTS["heading"],
            text_color=COLORS["text_primary"]
        ).pack(pady=(34, 6), padx=35)

        ctk.CTkLabel(
            card,
            text=t(self.config, "final.quantity_available", max_quantity=max_quantity),
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(pady=(0, 22))

        buttons_frame = ctk.CTkFrame(card, fg_color="transparent")
        buttons_frame.pack(padx=36, pady=(0, 24))

        columns = 3 if max_quantity > 4 else max_quantity
        button_size = max(76, min(108, int(screen_h * 0.12)))
        for amount in range(1, max_quantity + 1):
            row = (amount - 1) // columns
            column = (amount - 1) % columns
            ctk.CTkButton(
                buttons_frame,
                text=str(amount),
                font=("Segoe UI", 32, "bold"),
                width=button_size,
                height=button_size,
                fg_color=COLORS["success"],
                hover_color="#00e676",
                text_color=COLORS["text_primary"],
                corner_radius=16,
                command=lambda value=amount: choose_quantity(value)
            ).grid(row=row, column=column, padx=8, pady=8, sticky="nsew")

        ctk.CTkButton(
            card,
            text=t(self.config, "common.cancel"),
            font=FONTS["button"],
            width=min(260, int(card_w * 0.48)),
            height=48,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_secondary"],
            corner_radius=SIZES["corner_radius"],
            command=close_dialog
        ).pack(pady=(0, 32))

    def _close_print_quantity_dialog(self, dialog: Optional[ctk.CTkToplevel] = None):
        """Schließt den Print-Anzahl-Dialog, falls er offen ist."""
        active_dialog = dialog or self._print_quantity_dialog
        if not active_dialog:
            return

        if self._print_quantity_dialog is active_dialog:
            self._print_quantity_dialog = None

        try:
            active_dialog.grab_release()
        except Exception:
            pass

        try:
            if active_dialog.winfo_exists():
                active_dialog.destroy()
        except Exception:
            pass

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
                if "PAPIER" in error and "STAU" in error:
                    msg = t(self.config, "final.paper_jam")
                elif "PAPIER" in error:
                    msg = t(self.config, "final.no_paper")
                elif "KASSETTE" in error or "TINTE" in error:
                    msg = t(self.config, "final.cassette_empty")
                elif "KLAPPE" in error:
                    msg = t(self.config, "final.cover_open")
                elif (
                    "AUS" in error
                    or "FEHLT" in error
                    or "OFFLINE" in error
                    or "KEIN DRUCKER" in error
                ):
                    msg = t(self.config, "final.printer_off")
                else:
                    msg = t(self.config, "final.printer_reports", error=error)

                logger.warning(f"Drucken abgebrochen - Drucker nicht bereit: {error}")
                self._show_printer_warning(msg, error)
                return True

        except Exception as e:
            logger.debug(f"Drucker-Prüfung fehlgeschlagen: {e}")

        return False

    def _show_printer_warning(self, message: str, error_text: str = ""):
        """Zeigt Drucker-Warnung als Overlay über dem Final-Screen"""
        overlay = ctk.CTkFrame(
            self,
            fg_color=(
                "rgba(0,0,0,0.85)"
                if hasattr(ctk, 'TRANSPARENT')
                else "#1a1a1a"
            )
        )
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        compact = screen_w <= 1280 or screen_h <= 800
        image_size = 104 if compact else 124
        warning_image = load_printer_error_image(
            error_text or message,
            (image_size, image_size)
        )
        overlay._printer_warning_image = warning_image

        # Zentrierter Container
        container_w = min(500, max(360, screen_w - 90))
        container_h = 320 if warning_image else 280
        container = ctk.CTkFrame(
            overlay,
            fg_color=COLORS["bg_card"],
            corner_radius=20,
            width=container_w,
            height=container_h
        )
        container.place(relx=0.5, rely=0.5, anchor="center")
        container.pack_propagate(False)

        # Drucker-Bild oder Fallback-Icon
        if warning_image:
            image_frame = ctk.CTkFrame(
                container,
                width=image_size + 14,
                height=image_size + 14,
                fg_color="#ffffff",
                corner_radius=12
            )
            image_frame.pack(pady=(22, 10))
            image_frame.pack_propagate(False)
            ctk.CTkLabel(
                image_frame,
                text="",
                image=warning_image,
                fg_color="#ffffff"
            ).place(relx=0.5, rely=0.5, anchor="center")
        else:
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
            wraplength=container_w - 80,
            justify="center"
        ).pack(pady=(0, 16 if warning_image else 20), padx=35)

        def close_warning():
            overlay.destroy()

        # OK-Button
        ctk.CTkButton(
            container, text=t(self.config, "common.understood"),
            font=("Segoe UI", 16, "bold"),
            width=200, height=45,
            fg_color=COLORS["primary"],
            hover_color=(
                COLORS["primary_hover"]
                if "primary_hover" in COLORS
                else COLORS["primary"]
            ),
            corner_radius=12,
            command=close_warning
        ).pack(pady=(0, 18))

        # Auto-schließen nach 8 Sekunden
        overlay.after(8000, lambda: overlay.destroy() if overlay.winfo_exists() else None)

    def _print_image(self, image_path: Path):
        """Druckt ein Bild über GDI

        Verwendet feste Pixelwerte die zum 10x15cm Fotodrucker passen.
        Kein Dialog - vollautomatisch im Hintergrund.
        """
        # pywin32 separat pruefen — sonst wird ein Import-Fehler in
        # find_matching_printer (weiter unten) auch als "nur unter Windows"
        # gemeldet, was irrefuehrend waere.
        try:
            import win32print
            import win32ui
            from PIL import ImageWin
        except ImportError as e:
            logger.warning(f"pywin32-ImportError: {e} - Druck nur unter Windows")
            self.print_info.configure(
                text=t(self.config, "final.print_windows_only"),
                text_color=COLORS["warning"]
            )
            return

        try:

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
                        text=t(self.config, "final.printer_missing", printer=printer_name),
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
            # pywin32 wurde oben separat geprueft — dieser Pfad fängt jetzt
            # nur noch andere Imports (z.B. find_matching_printer) ab.
            logger.error(f"Print: ImportError (nicht pywin32): {e}", exc_info=True)
            self.print_info.configure(
                text=t(self.config, "final.module_missing", error=e),
                text_color=COLORS["error"]
            )
        except Exception as e:
            logger.error(f"Druckfehler: {e}")
            import traceback
            logger.error(traceback.format_exc())

            error_str = str(e)
            if "1801" in error_str or "unzulässig" in error_str.lower():
                msg = t(self.config, "final.printer_not_reachable")
            elif "offline" in error_str.lower():
                msg = t(self.config, "final.printer_offline")
            elif "paper" in error_str.lower() or "papier" in error_str.lower():
                msg = t(self.config, "final.no_paper_short")
            else:
                msg = t(self.config, "final.print_error")

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
        self.config = self.app.config
        self.is_active = True
        self._is_printing = False
        self.prints_count = 0
        self._close_print_quantity_dialog()

        if self.print_btn:
            self.print_btn.configure(text=t(self.config, "common.print"))
        if hasattr(self, "finish_btn"):
            self.finish_btn.configure(text=t(self.config, "common.finish"))

        # Rendern + Speichern laufen im Worker-Thread: der Screen erscheint
        # SOFORT mit Hinweis, statt den UI-Thread ~3s zu blockieren
        # (Messung Miix 310: 3.3s UI-HITCH beim Screenwechsel zu final).
        self.final_image = None
        self._show_rendering_placeholder()
        if self.print_btn:
            self.print_btn.configure(state="disabled")

        # Container-Größe VOR dem Thread ermitteln (Tk nur im UI-Thread nutzen)
        self.update_idletasks()
        container_w = self.image_frame.winfo_width()
        container_h = self.image_frame.winfo_height()
        if container_w < 100:
            container_w = 1000
        if container_h < 100:
            container_h = 500

        threading.Thread(
            target=self._render_final_worker,
            args=(container_w, container_h),
            daemon=True,
        ).start()

        # Auto-Return Timer starten
        self.auto_return_time = time.time() + self.config.get("final_time", 30)
        self.progress_bar.set(1.0)
        self._update_countdown()

    def _show_rendering_placeholder(self):
        """Zeigt 'Dein Bild wird erstellt…' und entfernt das Bild der Vorsession.

        Wichtig: Ohne das Leeren wäre bis zum Render-Ende noch das fertige Bild
        der VORHERIGEN Gäste sichtbar. CTkLabel löscht ein Bild nicht über
        image=None, daher ein 1x1-transparentes Platzhalterbild.
        """
        if not hasattr(self, "_blank_ctk"):
            blank = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
            self._blank_ctk = ctk.CTkImage(light_image=blank, dark_image=blank, size=(1, 1))
        self.preview_label.configure(
            image=self._blank_ctk,
            text=t(self.config, "final.rendering"),
            font=("Segoe UI", 26, "bold"),
            text_color=COLORS["text_primary"],
        )
        self.preview_label.image = self._blank_ctk

    def _render_final_worker(self, container_w: int, container_h: int):
        """Worker-Thread: finales Bild rendern, speichern, Vorschau vorbereiten."""
        started = time.perf_counter()
        final_image = None
        preview = None
        try:
            final_image = self._render_final_image()
        except Exception as e:
            logger.error(f"Final-Rendern fehlgeschlagen: {e}")

        if final_image is not None:
            self.final_image = final_image
            try:
                # IMMER speichern (reine PIL-/Datei-Arbeit — threadsicher,
                # gleiches Muster wie _save_photo_async in der Session)
                self._save_final_image()
            except Exception as e:
                logger.error(f"Final-Speichern fehlgeschlagen: {e}")

            preview = final_image.copy()
            preview.thumbnail((container_w, container_h), Image.Resampling.LANCZOS)

        logger.info(
            f"Final-Rendern (Hintergrund): {(time.perf_counter() - started) * 1000:.0f}ms, "
            f"{'ok' if final_image is not None else 'FEHLER'}"
        )
        self.after(0, lambda: self._on_final_ready(preview))

    def _on_final_ready(self, preview: Optional[Image.Image]):
        """UI-Thread: fertiges Bild anzeigen und Druck-Button freigeben."""
        if not self.is_active:
            return

        if preview is None or self.final_image is None:
            self.preview_label.configure(text=t(self.config, "final.no_image"))
            if self.print_btn:
                self.print_btn.configure(state="disabled")
            return

        # CTkImage size in logischen Pixeln (DPI-korrigiert)
        scaling = self._get_widget_scaling()
        logical_size = (int(preview.size[0] / scaling), int(preview.size[1] / scaling))
        ctk_img = ctk.CTkImage(light_image=preview, dark_image=preview, size=logical_size)
        self.preview_label.configure(image=ctk_img, text="")
        self.preview_label.image = ctk_img

        # Druck-Button freigeben
        if self.print_btn:
            self.print_btn.configure(state="normal")
            self._update_print_button_state()
        else:
            self.print_info.configure(
                text=t(self.config, "final.print_disabled"),
                text_color=COLORS["text_muted"]
            )

    def on_hide(self):
        """Screen wird verlassen"""
        self.is_active = False
        self._close_print_quantity_dialog()
