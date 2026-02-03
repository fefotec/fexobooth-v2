"""Final-Screen - Fertiges Bild mit Druck-Option

Optimiert für Lenovo Miix 310 (1280x800)
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
        """Erstellt die UI - kompakt für 800px Höhe"""
        # Titel (kompakter)
        self.title_label = ctk.CTkLabel(
            self,
            text="🎉 Fertig!",
            font=FONTS["heading"],
            text_color=COLORS["text_primary"]
        )
        self.title_label.pack(pady=(10, 2))
        
        # Untertitel
        self.subtitle_label = ctk.CTkLabel(
            self,
            text="Dein Foto ist bereit",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"]
        )
        self.subtitle_label.pack(pady=(0, 10))
        
        # Hauptbereich (weniger Padding)
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20)
        
        # Bild-Container
        self.image_frame = ctk.CTkFrame(
            main_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=SIZES["corner_radius"],
            border_width=3,
            border_color=COLORS["primary"]
        )
        self.image_frame.pack(expand=True, fill="both", pady=10)
        
        self.preview_label = ctk.CTkLabel(self.image_frame, text="", fg_color="transparent")
        self.preview_label.pack(expand=True, padx=20, pady=20)
        
        # Progress-Bar für Auto-Return (schmaler)
        self.progress_bar = ctk.CTkProgressBar(
            self,
            width=500,
            height=6,
            fg_color=COLORS["bg_light"],
            progress_color=COLORS["primary"],
            corner_radius=3
        )
        self.progress_bar.pack(pady=(5, 10))
        self.progress_bar.set(1.0)
        
        # Button-Leiste (kompakter)
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(pady=(0, 15))
        
        # Nochmal-Button
        self.redo_btn = ctk.CTkButton(
            button_frame,
            text=self.config.get("ui_texts", {}).get("redo", "NOCHMAL"),
            font=FONTS["small"],
            width=SIZES["button_width"],
            height=SIZES["button_height"],
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            corner_radius=SIZES["corner_radius"],
            command=self._on_redo
        )
        self.redo_btn.pack(side="left", padx=8)
        
        # Drucken-Button (etwas kleiner)
        self.print_btn = ctk.CTkButton(
            button_frame,
            text=f"🖨️ {self.config.get('ui_texts', {}).get('print', 'DRUCKEN')}",
            font=FONTS["button"],
            width=SIZES["button_large_width"],
            height=SIZES["button_large_height"],
            fg_color=COLORS["success"],
            hover_color="#00e676",
            corner_radius=SIZES["corner_radius"],
            command=self._on_print
        )
        self.print_btn.pack(side="left", padx=8)
        
        # Fertig-Button (wenn nicht versteckt)
        if not self.config.get("hide_finish_button", False):
            self.finish_btn = ctk.CTkButton(
                button_frame,
                text=self.config.get("ui_texts", {}).get("finish", "FERTIG"),
                font=FONTS["small"],
                width=SIZES["button_width"],
                height=SIZES["button_height"],
                fg_color=COLORS["bg_light"],
                hover_color=COLORS["bg_card"],
                corner_radius=SIZES["corner_radius"],
                command=self._on_finish
            )
            self.finish_btn.pack(side="left", padx=8)
        
        # Druck-Info
        self.print_info = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["tiny"],
            text_color=COLORS["text_muted"]
        )
        self.print_info.pack(pady=(0, 5))
    
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
        self.print_btn.configure(state="disabled", text="Druckt...")
        
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
                        text_color=COLORS["text_muted"]
                    )
                    self.print_btn.configure(
                        state="disabled",
                        text="Limit erreicht",
                        fg_color=COLORS["bg_light"]
                    )
        
        # Auto-Return Timer zurücksetzen
        self.auto_return_time = time.time() + self.config.get("final_time", 30)
    
    def _print_image(self, image_path: Path):
        """Druckt ein Bild über Windows Shell (nutzt Drucker-Standardeinstellungen)

        Diese Methode nutzt die Windows-Druckfunktion, die die Treibereinstellungen
        respektiert (inkl. randlos wenn im Treiber konfiguriert).
        """
        try:
            import subprocess
            import os

            printer_name = self.config.get("printer_name")
            if not printer_name:
                import win32print
                printer_name = win32print.GetDefaultPrinter()

            logger.info(f"Drucke auf: {printer_name}")
            logger.info(f"Bild: {image_path}")

            # Methode 1: Versuche ShellExecute "print" (nutzt Standardprogramm)
            # Dies respektiert die Drucker-Einstellungen aus Windows
            try:
                import win32api
                import win32con

                # "print" Verb druckt mit Standardprogramm und Drucker-Settings
                result = win32api.ShellExecute(
                    0,                              # Handle
                    "print",                        # Verb
                    str(image_path),                # Datei
                    f'/d:"{printer_name}"',         # Parameter: Drucker
                    None,                           # Arbeitsverzeichnis
                    win32con.SW_HIDE                # Fenster verstecken
                )

                if result > 32:  # Erfolg
                    logger.info(f"✅ Druck gestartet via ShellExecute auf: {printer_name}")
                    return
                else:
                    logger.warning(f"ShellExecute fehlgeschlagen (Code {result}), versuche Fallback...")

            except Exception as e:
                logger.warning(f"ShellExecute Fehler: {e}, versuche Fallback...")

            # Methode 2: Fallback auf manuelles GDI-Drucken
            self._print_image_gdi(image_path, printer_name)

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
            self.print_info.configure(
                text=f"❌ Druckfehler: {e}",
                text_color=COLORS["error"]
            )

    def _print_image_gdi(self, image_path: Path, printer_name: str):
        """Fallback: Druckt über GDI mit Drucker-DEVMODE (Treibereinstellungen)"""
        import win32print
        import win32ui
        import win32con
        from PIL import ImageWin

        logger.info("Verwende GDI-Druck mit Treibereinstellungen...")

        # Bild laden
        img = Image.open(image_path)
        logger.info(f"Bild-Größe: {img.size}")

        # DEVMODE vom Drucker holen (enthält Randlos-Einstellung wenn konfiguriert)
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            # Drucker-Properties abrufen (DEVMODE)
            properties = win32print.GetPrinter(hPrinter, 2)
            devmode = properties.get("pDevMode")

            if devmode:
                logger.info(f"DEVMODE geladen: {devmode.PaperSize}x, Orientation={devmode.Orientation}")
        finally:
            win32print.ClosePrinter(hPrinter)

        # DC mit DEVMODE erstellen (nutzt Treibereinstellungen!)
        hDC = win32ui.CreateDC()
        if devmode:
            hDC.CreatePrinterDC(printer_name)
            # TODO: DEVMODE an CreateDC übergeben wenn möglich
        else:
            hDC.CreatePrinterDC(printer_name)

        # Druckbereich abfragen
        printable_width = hDC.GetDeviceCaps(8)   # HORZRES - druckbarer Bereich
        printable_height = hDC.GetDeviceCaps(10) # VERTRES
        dpi_x = hDC.GetDeviceCaps(88)
        dpi_y = hDC.GetDeviceCaps(90)

        logger.info(f"Druckbar: {printable_width}x{printable_height}px, DPI: {dpi_x}x{dpi_y}")

        # Druck-Einstellungen
        adjustment = self.config.get("print_adjustment", {})
        offset_x = adjustment.get("offset_x", 0)
        offset_y = adjustment.get("offset_y", 0)

        # Bild auf druckbaren Bereich skalieren (Cover-Modus)
        img_ratio = img.width / img.height
        target_ratio = printable_width / printable_height

        if img_ratio > target_ratio:
            new_h = printable_height
            new_w = int(new_h * img_ratio)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            left = (new_w - printable_width) // 2
            img = img.crop((left, 0, left + printable_width, printable_height))
        else:
            new_w = printable_width
            new_h = int(new_w / img_ratio)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            top = (new_h - printable_height) // 2
            img = img.crop((0, top, printable_width, top + printable_height))

        logger.info(f"Bild skaliert auf: {img.size}")

        # Drucken
        hDC.StartDoc("Fexobooth Print")
        hDC.StartPage()

        dib = ImageWin.Dib(img)
        dib.draw(
            hDC.GetHandleOutput(),
            (offset_x, offset_y, printable_width + offset_x, printable_height + offset_y)
        )

        hDC.EndPage()
        hDC.EndDoc()
        hDC.DeleteDC()

        logger.info(f"✅ GDI-Druck abgeschlossen auf: {printer_name}")
    
    def _on_finish(self):
        """Fertig gedrückt"""
        logger.info("Session beendet")
        self.is_active = False
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
        
        # Vorschau anzeigen (angepasst für 800px Bildschirmhöhe)
        preview = self.final_image.copy()
        
        # Auf Container-Größe skalieren (kleiner für 1280x800)
        container_width = 700
        container_height = 400
        
        preview.thumbnail((container_width, container_height), Image.Resampling.LANCZOS)
        
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
            text_color=COLORS["text_muted"]
        )
        
        # Auto-Return Timer starten
        self.auto_return_time = time.time() + self.config.get("final_time", 30)
        self.progress_bar.set(1.0)
        self._update_countdown()
    
    def on_hide(self):
        """Screen wird verlassen"""
        self.is_active = False
