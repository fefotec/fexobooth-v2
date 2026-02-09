"""Final-Screen - Fertiges Bild mit Druck-Option

Bild bildschirmfüllend, Buttons als Overlay darüber.
Foto-Wiederholen Button am rechten Rand.
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
        """Erstellt die UI - Bild bildschirmfüllend, Buttons als Overlay"""
        # Bild-Container (mit etwas Rand für bessere Optik)
        self.image_frame = ctk.CTkFrame(self, fg_color="#000000", corner_radius=0)
        self.image_frame.pack(fill="both", expand=True, padx=30, pady=(15, 5))

        self.preview_label = ctk.CTkLabel(self.image_frame, text="", fg_color="transparent")
        self.preview_label.pack(expand=True, fill="both")

        # === Overlay-Elemente (über dem Bild via place) ===

        # Untertitel mit Countdown (oben)
        self.subtitle_label = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            fg_color="transparent"
        )
        self.subtitle_label.place(relx=0.5, rely=0.04, anchor="n")

        # Druck-Info (über den Buttons)
        self.print_info = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["body_bold"] if "body_bold" in FONTS else FONTS["body"],
            text_color=COLORS["text_primary"],
            fg_color="transparent"
        )
        self.print_info.place(relx=0.5, rely=0.80, anchor="center")

        # Button-Leiste (unten mittig, über dem Bild)
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.place(relx=0.5, rely=0.90, anchor="center")

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

        # DRUCKEN Button (groß, prominent)
        self.print_btn = ctk.CTkButton(
            button_frame,
            text=f"🖨️ {self.config.get('ui_texts', {}).get('print', 'DRUCKEN')}",
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

        # Progress-Bar (ganz unten)
        self.progress_bar = ctk.CTkProgressBar(
            self,
            width=500,
            height=4,
            fg_color=COLORS["bg_light"],
            progress_color=COLORS["primary"],
            corner_radius=2
        )
        self.progress_bar.place(relx=0.5, rely=0.97, anchor="center")
        self.progress_bar.set(1.0)

        # Foto-Wiederholen Button (rechter Rand)
        self.retake_btn = ctk.CTkButton(
            self,
            text="↻",
            font=("Segoe UI", 28),
            width=50,
            height=50,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["primary"],
            text_color=COLORS["text_primary"],
            corner_radius=25,
            command=self._on_retake
        )
        self.retake_btn.place(relx=0.97, rely=0.5, anchor="e")

    def _render_final_image(self) -> Image.Image:
        """Rendert das finale Bild"""
        # Filter auf alle Fotos anwenden
        filtered_photos = [
            self.app.filter_manager.apply(photo, self.app.current_filter)
            for photo in self.app.photos_taken
        ]

        # Template rendern
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

        # Nächstes Update
        self.after(100, self._update_countdown)

    def _on_redo(self):
        """Nochmal gedrückt"""
        logger.info("Redo - neue Session")
        self.is_active = False
        self.app.reset_session()
        # Video abspielen wenn konfiguriert
        self.app.play_video("video_end", "start")

    def _on_retake(self):
        """Foto wiederholen - gleiche Vorlage, neue Fotos"""
        logger.info("Foto wiederholen - neue Aufnahme mit gleicher Vorlage")
        self.is_active = False
        # Fotos zurücksetzen, Template behalten
        self.app.photos_taken = []
        self.app.current_photo_index = 0
        self.app.prints_in_session = 0
        # Kamera freigeben (wird von SessionScreen.on_show neu initialisiert)
        self.app.camera_manager.release()
        self.app.filter_manager.clear_cache()
        # Direkt zur Session (kein Video, kein Startscreen)
        self.app.show_screen("session")

    def _on_print(self):
        """Drucken gedrückt"""
        max_prints = self.config.get("max_prints_per_session", 1)

        if self.prints_count >= max_prints:
            self.print_info.configure(
                text="⚠️ Maximale Anzahl Drucke erreicht!",
                text_color=COLORS["warning"]
            )
            return

        logger.info("Drucke Bild...")

        # Button deaktivieren während Druck
        self.print_btn.configure(state="disabled", text="⏳ Wird gedruckt...")

        # Bild speichern und drucken
        if self.final_image:
            # Print speichern
            saved_path = self.app.local_storage.save_print(
                self.final_image.convert("RGB"),
                suffix=f"print_{self.prints_count + 1}"
            )

            if saved_path:
                # Auf USB kopieren
                self.app.usb_manager.copy_to_usb(saved_path, "Prints")

                # Drucken
                self._print_image(saved_path)

                self.prints_count += 1
                self.app.prints_in_session = self.prints_count

                # Statistik: Print erfasst
                self.app.statistics.record_print_success()

                # Info aktualisieren
                remaining = max_prints - self.prints_count
                if remaining > 0:
                    self.print_info.configure(
                        text=f"✓ Gedruckt! Noch {remaining} Druck(e) möglich",
                        text_color=COLORS["success"]
                    )
                    self.print_btn.configure(
                        state="normal",
                        text=f"🖨️ {self.config.get('ui_texts', {}).get('print', 'DRUCKEN')}"
                    )
                else:
                    self.print_info.configure(
                        text="✓ Gedruckt! Keine weiteren Drucke möglich",
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
        """Druckt ein Bild über GDI - einfache Methode wie in alter Version

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

            # Prüfen ob der Drucker existiert
            available_printers = [p[2] for p in win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )]

            if printer_name not in available_printers:
                logger.error(f"Drucker nicht gefunden: '{printer_name}'")
                logger.info(f"Verfügbare Drucker: {available_printers}")
                self.print_info.configure(
                    text=f"❌ Drucker '{printer_name}' nicht gefunden!\nBitte im Admin-Bereich konfigurieren.",
                    text_color=COLORS["error"]
                )
                return

            logger.info(f"Drucke auf: {printer_name}")
            logger.info(f"Bild: {image_path}")

            # Einstellungen aus Config
            adjustment = self.config.get("print_adjustment", {})
            offset_x = adjustment.get("offset_x", 0)
            offset_y = adjustment.get("offset_y", 0)
            zoom = adjustment.get("zoom", 100) / 100

            # Bild laden
            img = Image.open(image_path)
            logger.info(f"Original-Bild: {img.size}")

            # Feste Basisgröße für 10x15cm Fotodrucker (wie in alter Version)
            # 1772 x 1181 Pixel = 10x15cm bei 300dpi
            base_width = int(1772 * zoom)
            base_height = int(1181 * zoom)

            # Bild auf Zielgröße skalieren (mit Cover-Modus)
            img_ratio = img.width / img.height
            target_ratio = base_width / base_height

            if img_ratio > target_ratio:
                # Bild ist breiter - nach Höhe skalieren, dann horizontal beschneiden
                new_h = base_height
                new_w = int(new_h * img_ratio)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                left = (new_w - base_width) // 2
                img = img.crop((left, 0, left + base_width, base_height))
            else:
                # Bild ist höher - nach Breite skalieren, dann vertikal beschneiden
                new_w = base_width
                new_h = int(new_w / img_ratio)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                top = (new_h - base_height) // 2
                img = img.crop((0, top, base_width, top + base_height))

            logger.info(f"Bild skaliert auf: {img.size} (Zoom: {int(zoom*100)}%)")

            # Einfacher Drucker-DC (wie alte Version - funktioniert!)
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

            logger.info(f"✅ Gedruckt auf: {printer_name} "
                       f"(Größe: {base_width}x{base_height}, Offset: {offset_x},{offset_y})")

        except ImportError as e:
            logger.warning(f"Import-Fehler: {e} - Druck nur unter Windows")
            self.print_info.configure(
                text="⚠️ Druck nur unter Windows verfügbar",
                text_color=COLORS["warning"]
            )
        except Exception as e:
            logger.error(f"Druckfehler: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Benutzerfreundliche Fehlermeldung
            error_str = str(e)
            if "1801" in error_str or "unzulässig" in error_str.lower():
                msg = "❌ Drucker nicht erreichbar!\nBitte im Admin konfigurieren."
            elif "offline" in error_str.lower():
                msg = "❌ Drucker ist offline!"
            elif "paper" in error_str.lower() or "papier" in error_str.lower():
                msg = "❌ Kein Papier im Drucker!"
            else:
                msg = f"❌ Druckfehler"

            self.print_info.configure(
                text=msg,
                text_color=COLORS["error"]
            )

    def _save_final_image(self):
        """Speichert das finale Bild IMMER (nicht nur bei Druck)

        Wird bei on_show() aufgerufen, damit jedes erstellte Bild
        gespeichert wird, unabhängig ob gedruckt wird oder nicht.
        """
        if self.final_image is None:
            logger.warning("Kein finales Bild zum Speichern")
            return

        try:
            # In Prints-Ordner speichern
            saved_path = self.app.local_storage.save_print(
                self.final_image,
                suffix="final"
            )

            if saved_path:
                logger.info(f"✅ Finales Bild gespeichert: {saved_path}")
                # Auch auf USB kopieren wenn verfügbar
                self.app.usb_manager.copy_to_usb(saved_path, "Prints")
            else:
                logger.warning("Finales Bild konnte nicht gespeichert werden")

        except Exception as e:
            logger.error(f"Fehler beim Speichern des finalen Bildes: {e}")

    def _on_finish(self):
        """Fertig gedrückt"""
        logger.info("Session beendet")
        self.is_active = False

        # Statistik: Session erfasst
        self.app.statistics.record_session()

        self.app.reset_session()
        # Video abspielen wenn konfiguriert
        self.app.play_video("video_end", "start")

    def on_show(self):
        """Screen wird angezeigt"""
        logger.info("Final-Screen angezeigt")
        self.is_active = True
        self.prints_count = 0

        # Finales Bild rendern
        self.final_image = self._render_final_image()

        # IMMER speichern (nicht nur bei Druck!)
        self._save_final_image()

        # Vorschau bildschirmfüllend anzeigen
        self.update_idletasks()
        container_w = self.image_frame.winfo_width()
        container_h = self.image_frame.winfo_height()

        if container_w < 100:
            container_w = 1000
        if container_h < 100:
            container_h = 600

        preview = self.final_image.copy()
        preview.thumbnail((container_w, container_h), Image.Resampling.LANCZOS)

        ctk_img = ctk.CTkImage(light_image=preview, size=preview.size)
        self.preview_label.configure(image=ctk_img)
        self.preview_label.image = ctk_img

        # Druck-Button zurücksetzen
        max_prints = self.config.get("max_prints_per_session", 1)
        self.print_btn.configure(
            state="normal",
            text=f"🖨️ {self.config.get('ui_texts', {}).get('print', 'DRUCKEN')}",
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
