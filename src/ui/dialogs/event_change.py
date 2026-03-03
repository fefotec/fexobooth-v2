"""Event-Wechsel Dialog

Fullscreen-Overlay wenn ein neues Event/Template auf dem USB-Stick erkannt wird.
Bietet Annehmen oder Ablehnen des neuen Events.
Warnt über Bilder-Löschung und verlangt Bestätigung.
"""

import customtkinter as ctk

from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

logger = get_logger(__name__)


class EventChangeDialog(ctk.CTkToplevel):
    """Event-Wechsel Dialog - Fullscreen Overlay mit Lösch-Bestätigung"""

    def __init__(self, parent, new_booking_id: str,
                 on_accept: callable, on_reject: callable,
                 image_count: int = 0):
        super().__init__(parent)

        self._on_accept = on_accept
        self._on_reject = on_reject
        self.new_booking_id = new_booking_id
        self._image_count = image_count

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

        self._build_ui(screen_w, screen_h)
        logger.info(f"Event-Wechsel Dialog geöffnet: {new_booking_id} ({image_count} Bilder lokal)")

    def _build_ui(self, screen_w: int, screen_h: int):
        """Baut die Dialog-UI auf"""
        # Dunkler Fullscreen-Hintergrund
        bg_frame = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
        bg_frame.pack(fill="both", expand=True)
        bg_frame.bind("<Button-1>", lambda e: self._reject())

        # Zentrierte Karte
        card_w = min(480, int(screen_w * 0.8))
        self._card = ctk.CTkFrame(
            bg_frame,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["primary"],
            border_width=2,
            corner_radius=16
        )
        self._card.place(relx=0.5, rely=0.5, anchor="center")
        self._card.bind("<Button-1>", lambda e: "break")

        self._card_w = card_w
        self._screen_h = screen_h

        self._build_main_view()

    def _build_main_view(self):
        """Hauptansicht: Neues Event erkannt"""
        # Alten Inhalt leeren
        for widget in self._card.winfo_children():
            widget.destroy()

        card = self._card
        card_w = self._card_w
        screen_h = self._screen_h

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
        ).pack(pady=(0, 10))

        # Warn-Hinweis wenn Bilder vorhanden
        if self._image_count > 0:
            ctk.CTkLabel(
                card,
                text=f"⚠️ {self._image_count} vorhandene Bilder werden gelöscht!",
                font=FONTS["body_bold"],
                text_color=COLORS["warning"]
            ).pack(pady=(0, 10))

        # Buttons
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(pady=(0, 20), padx=30)

        btn_w = min(280, int(card_w * 0.7))
        btn_h = max(50, min(60, int(screen_h * 0.07)))

        # Neues Event starten
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
            command=self._confirm_step
        ).pack(pady=(0, 10))

        # Aktuelles Event behalten
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

    def _confirm_step(self):
        """Zweiter Schritt: Bestätigung der Bilder-Löschung"""
        # Wenn keine Bilder vorhanden, direkt annehmen
        if self._image_count == 0:
            self._accept()
            return

        # Bestätigungsansicht aufbauen
        self._build_confirm_view()

    def _build_confirm_view(self):
        """Bestätigungsansicht: Bilder wirklich löschen?"""
        # Alten Inhalt leeren
        for widget in self._card.winfo_children():
            widget.destroy()

        card = self._card
        card_w = self._card_w
        screen_h = self._screen_h

        # Warn-Icon
        icon_size = max(28, min(44, int(screen_h * 0.05)))
        ctk.CTkLabel(
            card,
            text="⚠️",
            font=("Segoe UI Emoji", icon_size)
        ).pack(pady=(20, 4))

        # Titel
        ctk.CTkLabel(
            card,
            text="Bilder löschen?",
            font=FONTS["heading"],
            text_color=COLORS["error"]
        ).pack(pady=(0, 8))

        # Warnung
        ctk.CTkLabel(
            card,
            text=f"{self._image_count} Bilder auf der Festplatte\nwerden unwiderruflich gelöscht!",
            font=FONTS["body"],
            text_color=COLORS["text_primary"],
            justify="center"
        ).pack(pady=(0, 5))

        ctk.CTkLabel(
            card,
            text="(USB-Stick bleibt unangetastet)",
            font=FONTS["small"],
            text_color=COLORS["text_muted"]
        ).pack(pady=(0, 15))

        # Buttons
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(pady=(0, 20), padx=30)

        btn_w = min(280, int(card_w * 0.7))
        btn_h = max(50, min(60, int(screen_h * 0.07)))

        # Bestätigen (Rot)
        ctk.CTkButton(
            btn_frame,
            text="LÖSCHEN & NEUES EVENT",
            font=FONTS["button_large"],
            width=btn_w,
            height=btn_h,
            fg_color="#cc3333",
            hover_color="#aa2222",
            text_color="#ffffff",
            corner_radius=SIZES["corner_radius"],
            command=self._accept
        ).pack(pady=(0, 10))

        # Zurück
        ctk.CTkButton(
            btn_frame,
            text="Zurück",
            font=FONTS["button"],
            width=btn_w,
            height=btn_h - 8,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_secondary"],
            corner_radius=SIZES["corner_radius"],
            command=self._build_main_view
        ).pack()

        self.bind("<Escape>", lambda e: self._build_main_view())

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

    def _emergency_quit(self):
        """Ctrl+Shift+Q - Dialog schließen und App beenden"""
        self.grab_release()
        self.destroy()
        if hasattr(self.master, '_photobooth_app'):
            self.master._photobooth_app._emergency_quit()
