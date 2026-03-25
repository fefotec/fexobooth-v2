"""Druck-Modus Bestätigung Dialog

Fullscreen-Overlay das nach dem System-Test angezeigt wird.
Zeigt deutlich an ob die aktuelle Buchung MIT oder OHNE Druck ist.
"""

import customtkinter as ctk

from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PrintModeConfirmationDialog(ctk.CTkToplevel):
    """Druck-Modus Bestätigung - Fullscreen Overlay"""

    def __init__(self, parent, print_enabled: bool, booking_id: str = "",
                 on_confirm: callable = None):
        super().__init__(parent)

        self._on_confirm = on_confirm
        self._print_enabled = print_enabled

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
        self.bind("<Control-Shift-Q>", lambda e: self._emergency_quit())
        self.bind("<Control-Shift-q>", lambda e: self._emergency_quit())

        self._build_ui(screen_w, screen_h, booking_id)

        mode_text = "MIT DRUCK" if print_enabled else "OHNE DRUCK"
        logger.info(f"Druck-Modus Bestätigung angezeigt: {mode_text} (Buchung: {booking_id})")

    def _build_ui(self, screen_w: int, screen_h: int, booking_id: str):
        """Baut die Dialog-UI auf"""
        # Farben je nach Modus
        if self._print_enabled:
            accent_color = "#00c853"       # Grün
            accent_hover = "#00e676"
            title_text = "BUCHUNG MIT DRUCK"
            subtitle_text = "Druckfunktion ist aktiviert"
            icon_text = "🖨️"
        else:
            accent_color = "#ff3b30"       # Rot
            accent_hover = "#ff6b60"
            title_text = "BUCHUNG OHNE DRUCK"
            subtitle_text = "Druckfunktion ist deaktiviert"
            icon_text = "🚫"

        # Dunkler Fullscreen-Hintergrund
        bg_frame = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
        bg_frame.pack(fill="both", expand=True)

        # Zentrierte Karte
        card_w = min(520, int(screen_w * 0.85))
        card = ctk.CTkFrame(
            bg_frame,
            fg_color=COLORS["bg_medium"],
            border_color=accent_color,
            border_width=3,
            corner_radius=20
        )
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.bind("<Button-1>", lambda e: "break")

        # Icon
        icon_size = max(36, min(56, int(screen_h * 0.06)))
        ctk.CTkLabel(
            card,
            text=icon_text,
            font=("Segoe UI Emoji", icon_size)
        ).pack(pady=(30, 8))

        # Haupttitel - groß und farbig
        title_font_size = max(24, min(38, int(screen_h * 0.045)))
        ctk.CTkLabel(
            card,
            text=title_text,
            font=("Segoe UI", title_font_size, "bold"),
            text_color=accent_color
        ).pack(pady=(0, 8))

        # Untertitel
        ctk.CTkLabel(
            card,
            text=subtitle_text,
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(pady=(0, 8))

        # Buchungs-ID anzeigen falls vorhanden
        if booking_id:
            ctk.CTkLabel(
                card,
                text=f"Buchung: {booking_id}",
                font=FONTS["small"],
                text_color=COLORS["text_muted"]
            ).pack(pady=(0, 12))

        # Farbiger Balken als visueller Indikator
        bar = ctk.CTkFrame(
            card,
            fg_color=accent_color,
            height=4,
            corner_radius=2
        )
        bar.pack(fill="x", padx=40, pady=(4, 16))

        # OK-Button
        btn_w = min(280, int(card_w * 0.6))
        btn_h = max(50, min(60, int(screen_h * 0.07)))
        ctk.CTkButton(
            card,
            text="OK",
            font=FONTS["button_large"],
            width=btn_w,
            height=btn_h,
            fg_color=accent_color,
            hover_color=accent_hover,
            text_color="#ffffff",
            corner_radius=SIZES["corner_radius"],
            command=self._confirm
        ).pack(pady=(0, 28))

    def _confirm(self):
        """OK gedrückt - Dialog schließen und Callback aufrufen"""
        logger.info("Druck-Modus bestätigt")
        callback = self._on_confirm
        self.grab_release()
        self.destroy()
        if callback:
            callback()

    def _emergency_quit(self):
        """Ctrl+Shift+Q - Dialog schließen und App beenden"""
        self.grab_release()
        self.destroy()
        if hasattr(self.master, '_photobooth_app'):
            self.master._photobooth_app._emergency_quit()
