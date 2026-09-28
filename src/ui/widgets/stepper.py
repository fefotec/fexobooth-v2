"""Zahlen-Einsteller mit großen − / + Tasten (ersetzt Slider am Touchscreen).

Slider waren auf dem Miix-Tablet kaum genau zu treffen (Christian, 28.09.2026:
„das geht beschissen"). Der Stepper:
- Tippen = ±1
- Gedrückt halten = wiederholt (nach 0,4 s alle 0,08 s, nach 15 Schritten ±5)
- get()/set() wie CTkSlider → bestehender Code (Testdruck, Speichern) bleibt gleich.
"""

import customtkinter as ctk

from src.ui.theme import COLORS
from src.utils.logging import get_logger

logger = get_logger(__name__)

_REPEAT_DELAY_MS = 400
_REPEAT_EVERY_MS = 80
_FAST_AFTER_STEPS = 15
_FAST_STEP = 5


class NumberStepper(ctk.CTkFrame):
    def __init__(self, parent, value: int, min_val: int, max_val: int,
                 suffix: str = "", name: str = "", button_size: int = 64):
        super().__init__(parent, fg_color="transparent")
        self._min = min_val
        self._max = max_val
        self._suffix = suffix
        self._name = name or "stepper"
        self._value = self._clamp(int(value))
        self._repeat_job = None
        self._repeat_count = 0

        self._minus = self._make_button("−", -1, button_size)
        self._minus.pack(side="left")

        self._label = ctk.CTkLabel(
            self,
            text="",
            width=int(button_size * 1.7),
            font=("Segoe UI", int(button_size * 0.42), "bold"),
            text_color=COLORS["primary"],
        )
        self._label.pack(side="left", padx=8)

        self._plus = self._make_button("+", +1, button_size)
        self._plus.pack(side="left")

        self._refresh()

    # ── API wie CTkSlider ───────────────────────────────────────────
    def get(self) -> int:
        return self._value

    def set(self, value) -> None:
        self._value = self._clamp(int(value))
        self._refresh()

    # ── intern ──────────────────────────────────────────────────────
    def _make_button(self, text: str, direction: int, size: int) -> ctk.CTkButton:
        # Bewusst ohne command: Schritt beim DRÜCKEN (sofortiges Feedback am
        # Touch) und Wiederholung beim Halten; command käme erst beim Loslassen
        # und würde doppelt zählen.
        btn = ctk.CTkButton(
            self,
            text=text,
            width=size,
            height=size,
            corner_radius=14,
            font=("Segoe UI", int(size * 0.55), "bold"),
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_light"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["primary"],
            border_width=2,
        )
        btn.bind("<ButtonPress-1>", lambda e: self._press(direction), add="+")
        btn.bind("<ButtonRelease-1>", lambda e: self._release(), add="+")
        return btn

    def _press(self, direction: int):
        self._cancel_repeat()
        self._repeat_count = 0
        self._step(direction)
        self._repeat_job = self.after(_REPEAT_DELAY_MS, lambda: self._repeat(direction))

    def _repeat(self, direction: int):
        self._repeat_count += 1
        amount = _FAST_STEP if self._repeat_count > _FAST_AFTER_STEPS else 1
        if not self._step(direction * amount):
            self._repeat_job = None
            return
        self._repeat_job = self.after(_REPEAT_EVERY_MS, lambda: self._repeat(direction))

    def _release(self):
        self._cancel_repeat()
        logger.debug(f"Stepper {self._name}: Wert {self._value}{self._suffix}")

    def _cancel_repeat(self):
        if self._repeat_job is not None:
            try:
                self.after_cancel(self._repeat_job)
            except Exception:
                pass
            self._repeat_job = None

    def _step(self, delta: int) -> bool:
        new_value = self._clamp(self._value + delta)
        if new_value == self._value:
            return False
        self._value = new_value
        self._refresh()
        return True

    def _clamp(self, value: int) -> int:
        return max(self._min, min(self._max, value))

    def _refresh(self):
        # Bereiche mit Minus (Offsets) zeigen das Vorzeichen, damit „+5" und
        # „-5" am Tablet eindeutig sind.
        shown = f"+{self._value}" if self._min < 0 < self._value else str(self._value)
        self._label.configure(text=f"{shown}{self._suffix}")
        # Am Anschlag die Taste dezent ausgrauen (kein state=disabled, sonst
        # käme das Loslassen nicht mehr an).
        self._minus.configure(text_color=COLORS["text_muted"] if self._value <= self._min else COLORS["text_primary"])
        self._plus.configure(text_color=COLORS["text_muted"] if self._value >= self._max else COLORS["text_primary"])

    def destroy(self):
        self._cancel_repeat()
        super().destroy()
