"""Final-Screen - Fertiges Bild mit Druck-Option

Bild oben (expand), schwarze Button-Leiste unten (fest).
"""

import customtkinter as ctk
from PIL import Image
from typing import TYPE_CHECKING, Optional
from pathlib import Path
import threading
import time

from src.ui.theme import (
    COLORS, FONTS, FONTS_UI, RADII, SEMIBOLD, SIZES, bind_pressed,
    style_primary, style_secondary,
)
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
        """Erstellt die UI — Redesign 2.4.70: Bild links, Aktionen rechts.

        Pack-Reihenfolge: Fußzeile ZUERST (bottom), dann Kopfzeile, dann
        Inhalt mit expand — bleibt so auch im Dev-Mode (weniger Höhe) stabil.
        """
        # === Fußzeile: Auto-Rückkehr-Balken + Text (zuerst packen!) ===
        self.progress_bar = ctk.CTkProgressBar(
            self,
            height=6,
            fg_color=COLORS["bg_light"],
            progress_color=COLORS["primary"],
            corner_radius=3
        )
        self.progress_bar.pack(fill="x", side="bottom", padx=40, pady=(0, 14))
        self.progress_bar.set(1.0)

        self.subtitle_label = ctk.CTkLabel(
            self,
            text="",
            font=FONTS_UI["caption"],
            text_color=COLORS["text_secondary"],
            anchor="w"
        )
        self.subtitle_label.pack(fill="x", side="bottom", padx=40, pady=(0, 6))

        # === Kopfzeile: Titel + Untertitel links ===
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=40, pady=(18, 0))

        self.title_label = ctk.CTkLabel(
            header,
            text=t(self.config, "final.title_ready"),
            font=FONTS_UI["h1"],
            text_color=COLORS["text_primary"]
        )
        self.title_label.pack(anchor="w")

        self.sub_label = ctk.CTkLabel(
            header,
            text=t(self.config, "final.sub_ready"),
            font=FONTS_UI["label"],
            text_color=COLORS["text_secondary"]
        )
        self.sub_label.pack(anchor="w", pady=(4, 0))

        # === Inhalt: Bild links (780×520), Aktions-Spalte rechts (280) ===
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=40, pady=(14, 8))

        self.image_frame = ctk.CTkFrame(
            content, width=780, height=520,
            fg_color=COLORS["bg_dark"], corner_radius=0
        )
        self.image_frame.pack(side="left", anchor="n")
        self.image_frame.pack_propagate(False)

        self.preview_label = ctk.CTkLabel(self.image_frame, text="", fg_color="transparent")
        self.preview_label.pack(expand=True, fill="both")

        # Render-Panel („Dein Bild wird erstellt …") — überdeckt die Bildfläche,
        # solange der Hintergrund-Renderer arbeitet.
        self._render_panel = ctk.CTkFrame(
            self.image_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=RADII["card"],
            border_width=1,
            border_color=COLORS["border"]
        )
        panel_inner = ctk.CTkFrame(self._render_panel, fg_color="transparent")
        panel_inner.place(relx=0.5, rely=0.5, anchor="center")

        self._render_illu = None
        try:
            illu_path = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "ui" / "illu_rendering_160.png"
            illu_img = Image.open(illu_path)
            self._render_illu = ctk.CTkImage(light_image=illu_img, dark_image=illu_img, size=(160, 160))
            ctk.CTkLabel(panel_inner, image=self._render_illu, text="").pack()
        except Exception as e:
            logger.debug(f"Render-Illustration nicht ladbar: {e}")

        self._render_title = ctk.CTkLabel(
            panel_inner,
            text=t(self.config, "final.rendering"),
            font=FONTS_UI["h2"],
            text_color=COLORS["text_primary"]
        )
        self._render_title.pack(pady=(28, 0))

        self._render_sub = ctk.CTkLabel(
            panel_inner,
            text=t(self.config, "final.rendering_sub"),
            font=FONTS_UI["label"],
            text_color=COLORS["text_secondary"]
        )
        self._render_sub.pack(pady=(6, 0))

        # 5-Segment-Fortschritt (1 Schritt/s, kein indeterminate)
        segments = ctk.CTkFrame(panel_inner, fg_color="transparent")
        segments.pack(pady=(28, 0))
        self._render_segments = []
        for _ in range(5):
            seg = ctk.CTkFrame(
                segments, width=56, height=8,
                fg_color=COLORS["bg_light"], corner_radius=4
            )
            seg.pack(side="left", padx=4)
            self._render_segments.append(seg)
        self._render_segment_pos = 0
        self._render_anim_job = None

        # Rechte Aktions-Spalte
        side = ctk.CTkFrame(content, fg_color="transparent", width=280)
        side.pack(side="right", anchor="n", padx=(0, 0))
        side.pack_propagate(False)
        side.configure(height=520)

        # DRUCKEN (Primary 280×96) - nur wenn Drucken aktiviert
        if self.config.get("print_enabled", True):
            self.print_btn = ctk.CTkButton(
                side,
                text=t(self.config, "common.print"),
                command=self._on_print,
                **style_primary(width=280, height=96, font_key="button_xl")
            )
            bind_pressed(self.print_btn, COLORS["primary"], COLORS["primary_pressed"])
            self.print_btn.pack(pady=(0, 0))
        else:
            self.print_btn = None

        # Druck-Info („3 Ausdrucke verfügbar")
        self.print_info = ctk.CTkLabel(
            side,
            text="",
            font=FONTS_UI["caption"],
            text_color=COLORS["text_secondary"],
            wraplength=280,
            justify="center",
            fg_color="transparent"
        )
        self.print_info.pack(pady=(12, 0))

        # FERTIG (Secondary 280×72)
        if not self.config.get("hide_finish_button", False):
            self.finish_btn = ctk.CTkButton(
                side,
                text=t(self.config, "common.finish"),
                command=self._on_finish,
                **style_secondary(width=280, height=72, font_key="button_s")
            )
            bind_pressed(self.finish_btn, COLORS["bg_light"], COLORS["pressed_secondary"])
            self.finish_btn.pack(pady=(20, 0))

    def _show_render_panel(self):
        """Zeigt das Render-Panel über der Bildfläche (Segment-Anzeige läuft an)."""
        self._render_panel.place(relx=0.5, rely=0.5, anchor="center",
                                 relwidth=1.0, relheight=1.0)
        self._render_panel.lift()
        self._render_segment_pos = 0
        for seg in self._render_segments:
            seg.configure(fg_color=COLORS["bg_light"])
        if self._render_anim_job is None:
            self._render_anim_job = self.after(1000, self._advance_render_segment)

    def _hide_render_panel(self):
        self._render_panel.place_forget()
        if self._render_anim_job is not None:
            try:
                self.after_cancel(self._render_anim_job)
            except Exception:
                pass
            self._render_anim_job = None

    def _advance_render_segment(self):
        """Füllt pro Sekunde ein Segment (max. 4 von 5 — das letzte gehört dem
        fertigen Bild). 1 configure/s, kein indeterminate-Geflacker."""
        self._render_anim_job = None
        if not self._render_panel.winfo_ismapped():
            return
        if self._render_segment_pos < 4:
            self._render_segments[self._render_segment_pos].configure(
                fg_color=COLORS["primary"]
            )
            self._render_segment_pos += 1
        self._render_anim_job = self.after(1000, self._advance_render_segment)

    def _set_header_state(self, ready: bool):
        """Titelzeile: „Dein Bild ist fertig!" vs. „Einen Moment …"."""
        if ready:
            self.title_label.configure(text=t(self.config, "final.title_ready"))
            self.sub_label.configure(text=t(self.config, "final.sub_ready"))
        else:
            self.title_label.configure(text=t(self.config, "final.title_rendering"))
            self.sub_label.configure(text=t(self.config, "final.rendering_sub"))

    def _render_final_image(self, photos, filter_name, boxes, overlay) -> Image.Image:
        """Rendert das finale Bild aus der übergebenen Momentaufnahme.

        Bewusst KEIN Zugriff auf self.app.photos_taken/template_boxes/
        overlay_image: Der Worker läuft weiter, wenn der Gast die Session
        schon beendet hat — reset_session() leert dann genau diese Felder
        und der Renderer würde eine leere weiße Vorlage speichern
        (Dauerlauf 05.09.2026: 9 von 30 Prints byte-identisch weiß).
        """
        logger.info(f"Rendere finales Bild: {len(photos)} Fotos, "
                     f"Filter '{filter_name}'")

        # Fotos vorab auf den Druckbedarf verkleinern: Das Template ist 1800x1200
        # (Boxen ~900x600) — 2000px lange Kante bleibt >2x überabgetastet, also
        # identische Druckqualität. Filter auf den 13,5/24-MP-Originalen dagegen
        # sättigten die 2 Atom-Kerne so, dass trotz Worker-Thread die UI ~3s
        # stand (Messung Dauerlauf 2026-07-02: UI-HITCH ~3,3s an jedem Final).
        prepared = []
        for photo in photos:
            scale = min(1.0, 2000 / max(photo.width, photo.height))
            if scale < 1.0:
                prepared.append(photo.resize(
                    (max(1, int(photo.width * scale)), max(1, int(photo.height * scale))),
                    Image.Resampling.LANCZOS
                ))
            else:
                prepared.append(photo)

        filtered_photos = [
            self.app.filter_manager.apply(photo, filter_name)
            for photo in prepared
        ]

        return self.app.renderer.render(
            filtered_photos,
            boxes,
            overlay
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

        # Redesign: Timer-Updates max. 2x/s
        self.after(500, self._update_countdown)

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
                    text_color=COLORS["primary"]
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
                        text_color=COLORS["primary"]
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
                fg_color=COLORS["primary_pressed"]
            )

        if quantity > 1:
            info_text = t(self.config, "final.jobs_sending", quantity=quantity)
        else:
            info_text = t(self.config, "final.job_sending")
        self.print_info.configure(text=info_text, text_color=COLORS["text_secondary"])

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
                    fg_color=COLORS["primary"]
                )
            self.print_info.configure(text=info_text, text_color=COLORS["text_secondary"])
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
                fg_color=COLORS["primary"] if printed_count > 0 else COLORS["bg_light"]
            )
        self.print_info.configure(
            text=info_text,
            text_color=COLORS["primary"] if printed_count > 0 else COLORS["text_muted"]
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
                fg_color=COLORS["primary"]
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
            border_color=COLORS["border_light"],
            border_width=2,
            corner_radius=RADII["dialog"]
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
                fg_color=COLORS["primary"],
                hover_color=COLORS["primary"],
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
            hover_color=COLORS["bg_light"],
            border_width=2,
            border_color=COLORS["border_light"],
            text_color=COLORS["text_primary"],
            corner_radius=RADII["button"],
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
            text_color=COLORS["text_primary"],
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
                text_color=COLORS["text_secondary"]
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
                        text_color=COLORS["primary"]
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
                text_color=COLORS["primary"]
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
                text_color=COLORS["primary"]
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
        self._set_header_state(ready=False)
        self._show_rendering_placeholder()
        if self.print_btn:
            self.print_btn.configure(state="disabled", fg_color=COLORS["bg_light"],
                                     text_color=COLORS["text_muted"])

        # Container-Größe VOR dem Thread ermitteln (Tk nur im UI-Thread nutzen)
        self.update_idletasks()
        container_w = self.image_frame.winfo_width()
        container_h = self.image_frame.winfo_height()
        if container_w < 100:
            container_w = 780
        if container_h < 100:
            container_h = 520

        # Session-Daten JETZT kopieren, nicht erst im Worker: Drückt der Gast
        # „Fertig", während noch gerendert wird, leert reset_session() Fotos,
        # Vorlagen-Felder und Overlay — mit der Momentaufnahme rendert der
        # Worker trotzdem das echte Bild zu Ende und speichert es.
        session_snapshot = (
            list(self.app.photos_taken),
            self.app.current_filter,
            list(self.app.template_boxes),
            self.app.overlay_image,
        )
        threading.Thread(
            target=self._render_final_worker,
            args=(container_w, container_h, session_snapshot),
            daemon=True,
        ).start()

        # Auto-Return-Countdown startet BEWUSST NOCH NICHT: Der Gast bekommt
        # die volle Zeit erst ab sichtbarem Bild + nutzbarem Druck-Button
        # (Start in _on_final_ready). Bis dahin: volle Leiste, kein Zähltext.
        self.auto_return_time = 0
        self.progress_bar.set(1.0)
        self.subtitle_label.configure(text="")

    def _show_rendering_placeholder(self):
        """Zeigt das Render-Panel und entfernt das Bild der Vorsession.

        Wichtig: Ohne das Leeren wäre bis zum Render-Ende noch das fertige Bild
        der VORHERIGEN Gäste sichtbar. CTkLabel löscht ein Bild nicht über
        image=None, daher ein 1x1-transparentes Platzhalterbild.
        """
        if not hasattr(self, "_blank_ctk"):
            blank = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
            self._blank_ctk = ctk.CTkImage(light_image=blank, dark_image=blank, size=(1, 1))
        self.preview_label.configure(image=self._blank_ctk, text="")
        self.preview_label.image = self._blank_ctk

        # Panel-Texte in aktueller Sprache + Segment-Anzeige starten
        self._render_title.configure(text=t(self.config, "final.rendering"))
        self._render_sub.configure(text=t(self.config, "final.rendering_sub"))
        self._show_render_panel()

    def _render_final_worker(self, container_w: int, container_h: int, session_snapshot):
        """Worker-Thread: finales Bild rendern, speichern, Vorschau vorbereiten."""
        started = time.perf_counter()
        photos, filter_name, boxes, overlay = session_snapshot
        final_image = None
        preview = None
        if not photos:
            # Ohne Fotos gäbe es nur eine leere weiße Vorlage — nicht speichern.
            logger.warning("Final-Rendern übersprungen: keine Fotos in der Momentaufnahme")
            self.after(0, lambda: self._on_final_ready(None))
            return
        try:
            final_image = self._render_final_image(photos, filter_name, boxes, overlay)
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

        # Auto-Return-Countdown startet erst JETZT — nicht schon während
        # "Druckdatei wird erzeugt" (Kundenwunsch: volle Zeit mit sichtbarem
        # Bild und aktiver Druckmöglichkeit). Läuft auch im Fehlerfall an,
        # damit die Box nie auf diesem Screen hängen bleibt.
        self.auto_return_time = time.time() + self.config.get("final_time", 30)
        self.progress_bar.set(1.0)
        self._update_countdown()
        self._hide_render_panel()
        self._set_header_state(ready=True)

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
            self.print_btn.configure(state="normal", fg_color=COLORS["primary"],
                                     text_color=COLORS["text_primary"])
            self._update_print_button_state()
        else:
            self.print_info.configure(
                text=t(self.config, "final.print_disabled"),
                text_color=COLORS["text_muted"]
            )

    def on_hide(self):
        """Screen wird verlassen"""
        self.is_active = False
        self._hide_render_panel()
        self._close_print_quantity_dialog()
