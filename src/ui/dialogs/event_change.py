"""Event-Wechsel Dialog

Fullscreen-Overlay wenn ein neues Event/Template auf dem USB-Stick erkannt wird.
Bietet Annehmen oder Ablehnen des neuen Events.
"""

import customtkinter as ctk

from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

logger = get_logger(__name__)


class EventChangeDialog(ctk.CTkToplevel):
    """Event-Wechsel Dialog - Fullscreen Overlay"""

    def __init__(self, parent, new_booking_id: str,
                 on_accept: callable, on_reject: callable):
        super().__init__(parent)

        self._on_accept = on_accept
        self._on_reject = on_reject
        self.new_booking_id = new_booking_id

        # Fullscreen Overlay (wie AdminDialog PIN-Overlay)
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
        logger.info(f"Event-Wechsel Dialog geöffnet: {new_booking_id}")

    def _build_ui(self, screen_w: int, screen_h: int):
        """Baut die Dialog-UI auf"""
        # Dunkler Fullscreen-Hintergrund
        bg_frame = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
        bg_frame.pack(fill="both", expand=True)
        bg_frame.bind("<Button-1>", lambda e: self._reject())

        # Zentrierte Karte
        card_w = min(480, int(screen_w * 0.8))
        card = ctk.CTkFrame(
            bg_frame,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["primary"],
            border_width=2,
            corner_radius=16
        )
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.bind("<Button-1>", lambda e: "break")

        # Schließen-Button
        close_btn = ctk.CTkButton(
            card,
            text="✕",
            width=32,
            height=32,
            font=("Segoe UI", 16, "bold"),
            fg_color="transparent",
            hover_color=COLORS["error"],
            text_color=COLORS["text_muted"],
            corner_radius=16,
            command=self._reject
        )
        close_btn.pack(anchor="e", padx=(0, 8), pady=(8, 0))

        # Icon
        icon_size = max(28, min(44, int(screen_h * 0.05)))
        ctk.CTkLabel(
            card,
            text="🔄",
            font=("Segoe UI Emoji", icon_size)
        ).pack(pady=(0, 4))

        # Titel
        ctk.CTkLabel(
            card,
            text="Neues Event erkannt",
            font=FONTS["heading"],
            text_color=COLORS["primary"]
        ).pack(pady=(0, 8))

        # Buchungs-Info
        ctk.CTkLabel(
            card,
            text=f"Buchung: {self.new_booking_id}",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(pady=(0, 20))

        # Buttons
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(pady=(0, 20), padx=30)

        btn_w = min(280, int(card_w * 0.7))
        btn_h = max(50, min(60, int(screen_h * 0.07)))

        # Neues Event starten (Primary)
        ctk.CTkButton(
            btn_frame,
            text="NEUES EVENT STARTEN",
            font=FONTS["button_large"],
            width=btn_w,
            height=btn_h,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            text_color=COLORS["text_primary"],
            corner_radius=SIZES["corner_radius"],
            command=self._accept
        ).pack(pady=(0, 10))

        # Aktuelles Event behalten (Secondary)
        ctk.CTkButton(
            btn_frame,
            text="Aktuelles Event behalten",
            font=FONTS["button"],
            width=btn_w,
            height=btn_h - 8,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_secondary"],
            corner_radius=SIZES["corner_radius"],
            command=self._reject
        ).pack()

        # Escape-Taste
        self.bind("<Escape>", lambda e: self._reject())

    def _accept(self):
        """Neues Event annehmen"""
        logger.info(f"Event-Wechsel ANGENOMMEN: {self.new_booking_id}")
        callback = self._on_accept
        self.grab_release()
        self.destroy()
        if callback:
            callback()

    def _reject(self):
        """Neues Event ablehnen"""
        logger.info(f"Event-Wechsel ABGELEHNT: {self.new_booking_id}")
        callback = self._on_reject
        self.grab_release()
        self.destroy()
        if callback:
            callback()
