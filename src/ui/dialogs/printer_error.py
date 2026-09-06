"""Drucker-Fehler Overlay - Blockierender Vollbild-Dialog

Zwei Modi:
1. CONSUMABLE: Papier/Tinte leer → Blockiert, User muss "Problem behoben" bestätigen
2. JAM/RESET: Papierstau → Zeigt Reset-Animation, danach Bestätigungs-Button

Das Overlay schließt sich NUR nach User-Bestätigung UND erfolgreicher Drucker-Prüfung.
Canon-Dialoge werden per SW_HIDE versteckt (nicht WM_CLOSE, da Canon sonst neu erstellt).
"""

import customtkinter as ctk
import threading
import time
from typing import Optional, TYPE_CHECKING

from src.ui.theme import (
    COLORS, FONTS, FONTS_UI, RADII, SEMIBOLD, bind_pressed, style_primary,
)
from src.ui.error_images import load_printer_error_image
from src.utils.logging import get_logger
from src.i18n import t

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)

# Fehler-Kategorien
CONSUMABLE_ERRORS = [
    "PAPIER LEER!", "KASSETTE LEER!", "KEIN PAPIER / KASSETTE!",
    "KEINE TINTENKASSETTE!", "TINTE LEER!", "KASSETTE PRÜFEN!",
    "KASSETTE FALSCH!", "PAPIER/KASSETTE LEER!",
    "DRUCKER PRÜFEN!", "KLAPPE OFFEN!",
]
JAM_ERRORS = ["PAPIERSTAU!"]
RESET_ERRORS = JAM_ERRORS + ["DRUCK BLOCKIERT!", "DRUCKER FEHLER!"]

# Fehler die NUR in der Top-Bar angezeigt werden (kein Overlay)
TOPBAR_ONLY_ERRORS = ["DRUCKER AUS!", "DRUCKER OFFLINE!", "DRUCKER FEHLT!"]


def classify_error(error_text: str, log: bool = True) -> str:
    """Klassifiziert einen Fehlertext in eine Kategorie.

    Returns: 'consumable', 'jam', 'other'
    - 'consumable': Overlay anzeigen, warten auf Bestätigung
    - 'jam': Overlay + automatischer Reset
    - 'other': Nur Top-Bar Warnung (offline, etc.)

    log=False unterdrückt die Log-Ausgabe (für den 1x/Sekunde-Poll bei
    unverändertem Status), ohne das Klassifizierungs-Ergebnis zu ändern.
    """
    if not error_text:
        return "other"
    upper = error_text.upper()

    # Explizit kein Overlay für Offline-Fehler
    for pattern in TOPBAR_ONLY_ERRORS:
        if pattern in upper:
            if log:
                logger.debug(f"classify_error('{error_text}') → other (Top-Bar only)")
            return "other"

    for pattern in JAM_ERRORS:
        if pattern in upper:
            if log:
                logger.info(f"classify_error('{error_text}') → jam")
            return "jam"

    for pattern in CONSUMABLE_ERRORS:
        if pattern in upper:
            if log:
                logger.info(f"classify_error('{error_text}') → consumable")
            return "consumable"

    # Unbekannter Fehlertext: Im Zweifel als consumable behandeln
    if log:
        logger.info(f"classify_error('{error_text}') → consumable (unbekannt)")
    return "consumable"


class PrinterErrorOverlay(ctk.CTkToplevel):
    """Vollbild-Overlay das bei Druckerfehlern alles blockiert.

    - Bei Verbrauchsmaterial: Zeigt Fehler + Anweisung + Bestätigungs-Button
    - Bei Papierstau: Startet automatisch Reset, danach Bestätigungs-Button
    """

    def __init__(self, parent, app: "PhotoboothApp", error_text: str,
                 error_category: str):
        super().__init__(parent)

        self.app = app
        self.config = getattr(app, "config", {}) or {}
        self.error_text = error_text
        self.error_category = error_category  # 'consumable', 'jam'
        self._is_open = True
        self._animation_frame = 0
        self._reset_started = False
        self._checking = False  # Verhindert doppelte Prüfungen
        self._error_ctk_image = None
        self._error_image_label = None
        self._error_image_size = (0, 0)

        logger.info(
            f"PrinterErrorOverlay erstellt: '{error_text}' "
            f"(Kategorie: {error_category})"
        )

        # Vollbild-Overlay
        self.overrideredirect(True)
        self.configure(fg_color="#0a0a10")
        self.update_idletasks()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        self.geometry(f"{screen_w}x{screen_h}+0+0")

        # TOPMOST: Overlay IMMER über Canon-Dialog und allem anderen
        self.attributes('-topmost', True)

        # Modal
        self.transient(parent)
        self.grab_set()
        self.lift()
        self.focus_force()

        # Notfall-Shortcut
        self.bind("<Control-Shift-Q>", lambda e: self._emergency_quit())
        self.bind("<Control-Shift-q>", lambda e: self._emergency_quit())

        # Service-Ausstieg (Bug-Report #49): Hängt ein Druckjob ohne dass der
        # Drucker einen Fehler meldet, kam man aus dem Overlay nie wieder raus
        # (Bestätigungs-Check schlug endlos fehl; Ctrl+Shift+Q braucht eine
        # Tastatur, die am Tablet fehlt → Box musste hart ausgeschaltet werden).
        self._pin_frame = None
        self._pin_entry_value = ""

        # Canon-Dialog sofort verstecken (SW_HIDE, nicht WM_CLOSE!)
        self._hide_canon_dialogs()

        # UI bauen
        self._build_ui()

        # Periodisch Canon-Dialoge verstecken (falls neue erscheinen)
        self._periodic_hide_canon()

        # Aktion starten
        if error_category == "jam":
            self._start_reset()

    def _hide_canon_dialogs(self):
        """Versteckt Canon-Dialoge per SW_HIDE"""
        try:
            from src.printer.controller import get_printer_controller
            controller = get_printer_controller()
            hidden = controller.hide_canon_dialogs()
            if hidden:
                logger.info("Canon-Dialog(e) per SW_HIDE versteckt")
        except Exception as e:
            logger.debug(f"hide_canon_dialogs Fehler: {e}")

    def _periodic_hide_canon(self):
        """Versteckt Canon-Dialoge periodisch (falls neue erscheinen)"""
        if not self._is_open:
            return
        self._hide_canon_dialogs()

        # Overlay im Vordergrund halten
        try:
            self.lift()
            self.attributes('-topmost', True)
        except Exception:
            pass

        self.after(1000, self._periodic_hide_canon)

    def _build_ui(self):
        """Erstellt das UI je nach Fehler-Kategorie"""
        self.main_frame = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
        self.main_frame.pack(fill="both", expand=True)

        # Dezenter Service-Ausstieg oben rechts (PIN-geschützt, Bug #49).
        # Bewusst unauffällig (dunkelgrau auf dunklem Grund) – Gäste sollen ihn
        # nicht als Einladung verstehen, Service/Hotline kennt ihn.
        self._service_close_btn = ctk.CTkButton(
            self.main_frame,
            text="✕",
            width=44,
            height=44,
            font=("Segoe UI", 20, "bold"),
            fg_color="transparent",
            hover_color=COLORS["bg_medium"],
            text_color="#3a3a4a",
            corner_radius=22,
            command=self._show_service_pin
        )
        self._service_close_btn.place(relx=1.0, y=14, x=-14, anchor="ne")

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        compact = screen_h <= 820
        card_w = min(760, max(420, screen_w - 80))
        text_w = max(320, card_w - 120)
        title_size = 30 if compact else 34
        top_pad = 24 if compact else 40
        bottom_pad = 20 if compact else 36
        image_size = 148 if compact else 184
        self._error_image_size = (image_size, image_size)

        # Zentrierte Karte (Redesign 2.4.70: freundlich statt Alarm-Rot)
        self.card = ctk.CTkFrame(
            self.main_frame,
            width=card_w,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["border_light"],
            border_width=2,
            corner_radius=RADII["dialog"]
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center")

        title_text = self._get_friendly_title()
        if self.error_category == "jam":
            subtitle = t(self.config, "printer.body_jam")
        else:
            subtitle = self._get_friendly_body()

        # Illustration im weissen Träger (falls Asset existiert)
        self._create_error_image(top_pad)

        # Eyebrow „KURZE PAUSE" (Pink, Versalien)
        ctk.CTkLabel(
            self.card,
            text=t(self.config, "printer.eyebrow").upper(),
            font=FONTS_UI["label"],
            text_color=COLORS["primary"]
        ).pack(pady=(12 if self._error_image_label else top_pad, 0))

        # Titel (gastfreundlich, weiß)
        self.title_label = ctk.CTkLabel(
            self.card,
            text=title_text,
            font=("Segoe UI", title_size, "bold"),
            text_color=COLORS["text_primary"],
            wraplength=text_w,
            justify="center"
        )
        self.title_label.pack(pady=(6, 0))

        # Status/Anweisung (Body 20)
        self.status_label = ctk.CTkLabel(
            self.card,
            text=subtitle,
            font=FONTS_UI["body"],
            text_color=COLORS["text_secondary"],
            wraplength=text_w,
            justify="center"
        )
        self.status_label.pack(pady=(12, 0), padx=40)

        # Original-Fehlertext klein für Service/Hotline (Felix fragt danach)
        self.error_label = ctk.CTkLabel(
            self.card,
            text=self.error_text,
            font=FONTS_UI["micro"],
            text_color=COLORS["text_muted"],
            wraplength=text_w,
            justify="center"
        )
        self.error_label.pack(pady=(8, 0), padx=35)

        # animation_label bleibt als (jetzt statischer) Status-Platzhalter
        self.animation_label = ctk.CTkLabel(
            self.card,
            text="",
            font=FONTS_UI["body"],
            text_color=COLORS["text_secondary"]
        )
        self.animation_label.pack(pady=(2, 0))

        # 5-Segment-Fortschritt für den Papierstau-Reset (statt indeterminate)
        self._reset_segments_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self._reset_segments = []
        for _ in range(5):
            seg = ctk.CTkFrame(
                self._reset_segments_frame, width=56, height=8,
                fg_color=COLORS["bg_light"], corner_radius=4
            )
            seg.pack(side="left", padx=4)
            self._reset_segments.append(seg)
        self._reset_segment_pos = 0
        if self.error_category == "jam":
            self._reset_segments_frame.pack(pady=(12, 0))

        # ===== Bestätigungs-Button (für consumable Fehler) =====
        self.confirm_btn = ctk.CTkButton(
            self.card,
            text=self._get_button_text(),
            command=self._on_confirm,
            **style_primary(width=min(400, card_w - 120), height=88)
        )
        bind_pressed(self.confirm_btn, COLORS["primary"], COLORS["primary_pressed"])
        if self.error_category != "jam":
            self.confirm_btn.pack(pady=(24, 0))

        # Hinweis unten
        hint_text = (t(self.config, "printer.dont_turn_off")
                     if self.error_category == "jam"
                     else t(self.config, "printer.after_hint"))
        self.hint_label = ctk.CTkLabel(
            self.card,
            text=hint_text,
            font=FONTS_UI["micro"],
            text_color=COLORS["text_muted"],
            wraplength=text_w,
            justify="center"
        )
        self.hint_label.pack(pady=(16, bottom_pad), padx=50)

    def _get_friendly_title(self) -> str:
        """Gastfreundlicher Titel je Fehlerart (Redesign 2.4.70)."""
        upper = self.error_text.upper()
        if self.error_category == "jam":
            return t(self.config, "printer.title_jam")
        if "PAPIER" in upper:
            return t(self.config, "printer.title_paper")
        if "TINTE" in upper or "KASSETTE" in upper:
            return t(self.config, "printer.title_ink")
        if "KLAPPE" in upper:
            return t(self.config, "printer.title_cover")
        return t(self.config, "printer.title_generic")

    def _get_friendly_body(self) -> str:
        """Gastfreundlicher Erklärtext je Fehlerart."""
        upper = self.error_text.upper()
        if "PAPIER" in upper:
            return t(self.config, "printer.body_paper")
        if "TINTE" in upper or "KASSETTE" in upper:
            return t(self.config, "printer.body_ink")
        if "KLAPPE" in upper:
            return t(self.config, "printer.body_cover")
        return t(self.config, "printer.body_generic")

    def _advance_reset_segment(self):
        """Ein Reset-Schritt = ein Segment Pink (max. 4 — das letzte gehört
        dem erfolgreichen Abschluss in _switch_to_confirm_mode)."""
        try:
            if self._reset_segment_pos < 4:
                self._reset_segments[self._reset_segment_pos].configure(
                    fg_color=COLORS["primary"]
                )
                self._reset_segment_pos += 1
        except Exception:
            pass

    def _create_error_image(self, top_pad: int) -> bool:
        """Creates the compact error illustration if an asset is available."""
        self._error_ctk_image = load_printer_error_image(
            self.error_text,
            self._error_image_size
        )
        if not self._error_ctk_image:
            return False

        frame_size = self._error_image_size[0] + 16
        image_frame = ctk.CTkFrame(
            self.card,
            width=frame_size,
            height=frame_size,
            fg_color=COLORS["white"],
            corner_radius=20
        )
        image_frame.pack(pady=(top_pad, 0))
        image_frame.pack_propagate(False)

        self._error_image_label = ctk.CTkLabel(
            image_frame,
            text="",
            image=self._error_ctk_image,
            fg_color="#ffffff"
        )
        self._error_image_label.place(relx=0.5, rely=0.5, anchor="center")
        return True

    def _refresh_error_image(self):
        """Refreshes the illustration after the printer reports a new error."""
        if not self._error_image_label:
            return

        image = load_printer_error_image(self.error_text, self._error_image_size)
        if image:
            self._error_ctk_image = image
            self._error_image_label.configure(image=image, text="")

    def _get_instruction_text(self) -> str:
        """Gibt Anweisungstext je nach Fehler zurück"""
        upper = self.error_text.upper()
        if "PAPIER" in upper:
            return t(self.config, "printer.instruction_paper")
        elif "TINTE" in upper or "KASSETTE" in upper:
            return t(self.config, "printer.instruction_ink")
        elif "KLAPPE" in upper or "DOOR" in upper:
            return t(self.config, "printer.instruction_cover")
        else:
            return t(self.config, "printer.instruction_check")

    def _get_button_text(self) -> str:
        """Gibt Button-Text je nach Fehler zurück"""
        upper = self.error_text.upper()
        if "PAPIER" in upper:
            return t(self.config, "printer.button_paper")
        elif "TINTE" in upper or "KASSETTE" in upper:
            return t(self.config, "printer.button_cassette")
        elif "KLAPPE" in upper or "DOOR" in upper:
            return t(self.config, "printer.button_cover")
        else:
            return t(self.config, "printer.button_fixed")

    # ========== Bestätigungs-Button ==========

    def _on_confirm(self):
        """User hat bestätigt dass Problem behoben ist.

        Ablauf:
        1. Versteckte Canon-Dialoge per WM_CLOSE schließen (zwingt Treiber zur Neuprüfung)
        2. Jobs purgen (altes Zeug weg)
        3. 5 Sekunden warten (Treiber muss Zeit haben, neuen Dialog zu erstellen)
        4. Prüfen ob neuer Canon-Dialog erscheint (= Problem besteht noch)
        5. Falls kein Dialog: nochmal 3s warten und erneut prüfen (Doppel-Check)

        WICHTIG: Der SELPHY meldet Fehler NUR wenn ein Druckjob wartet.
        Ohne Job meldet get_error() IMMER None. Deshalb:
        - Wenn get_error()=None UND keine Jobs in der Queue: Overlay schließen
          (nächster Druckversuch zeigt ggf. erneut den Fehler)
        """
        if self._checking:
            return
        self._checking = True

        logger.info("User bestätigt: Problem behoben → prüfe Drucker...")

        # Button deaktivieren, Status ändern
        self.confirm_btn.configure(
            state="disabled",
            text=t(self.config, "printer.checking"),
            fg_color=COLORS["bg_light"]
        )
        self.status_label.configure(text=t(self.config, "printer.checking_printer"))
        self.animation_label.configure(text="")

        def _check():
            from src.printer.controller import get_printer_controller
            controller = get_printer_controller()

            # 1. Alle Canon-Dialoge schließen (auch versteckte!)
            #    WM_CLOSE auf sichtbare + ShowWindow(SW_SHOW) auf versteckte, dann WM_CLOSE
            self._close_all_canon_dialogs(controller)
            time.sleep(1)

            # 2. Jobs purgen
            logger.info("Bestätigung: Jobs purgen...")
            controller._step1_purge_jobs()
            time.sleep(3)

            # 3. Ersten Check machen
            error1 = controller.get_error()
            logger.info(f"Drucker-Check #1 nach Bestätigung: error='{error1}'")

            if error1:
                # Sofort Fehler gefunden
                if self._is_open:
                    self.after(0, lambda: self._handle_check_result(error1))
                return

            # 4. Kein Fehler beim ersten Check - nochmal warten und prüfen
            #    (Canon-Treiber braucht manchmal Zeit um Dialog zu erstellen)
            logger.info("Kein Fehler bei Check #1 → warte 5s für Doppel-Check...")
            time.sleep(5)

            error2 = controller.get_error()
            logger.info(f"Drucker-Check #2 nach Bestätigung: error='{error2}'")

            if self._is_open:
                self.after(0, lambda: self._handle_check_result(error2))

        threading.Thread(target=_check, daemon=True).start()

    def _close_all_canon_dialogs(self, controller):
        """Schließt ALLE Canon-Dialoge (sichtbare UND versteckte)"""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            WM_CLOSE = 0x0010
            SW_SHOW = 5
            WNDENUMPROC = ctypes.WINFUNCTYPE(
                wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
            )

            keywords = ["canon selphy", "canon cp", "druckerstatus", "printer status"]

            def enum_callback(hwnd, lParam):
                title_buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title_buf, 256)
                title = title_buf.value.lower()
                if title and any(kw in title for kw in keywords):
                    # Erst sichtbar machen (falls versteckt), dann schließen
                    visible = user32.IsWindowVisible(hwnd)
                    if not visible:
                        user32.ShowWindow(hwnd, SW_SHOW)
                        logger.debug(f"Canon-Dialog sichtbar gemacht: '{title_buf.value}'")
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                    logger.info(f"Canon-Dialog WM_CLOSE: '{title_buf.value}' (war {'sichtbar' if visible else 'versteckt'})")
                return True

            proc = WNDENUMPROC(enum_callback)
            user32.EnumWindows(proc, 0)

        except Exception as e:
            logger.debug(f"_close_all_canon_dialogs Fehler: {e}")

    def _handle_check_result(self, error: Optional[str]):
        """Verarbeitet das Ergebnis der Drucker-Prüfung nach User-Bestätigung"""
        self._checking = False

        if not error:
            # Drucker OK!
            logger.info("Drucker OK nach Bestätigung → Overlay wird geschlossen")
            self._show_resolved()
        else:
            # Fehler besteht noch
            logger.warning(f"Drucker meldet noch Fehler: '{error}'")
            self.error_text = error
            self._refresh_error_image()
            self.error_label.configure(text=error)
            self.status_label.configure(
                text=t(self.config, "printer.still_error", instruction=self._get_instruction_text()),
                text_color=COLORS["primary"]
            )
            self.animation_label.configure(text="")
            self.confirm_btn.configure(
                state="normal",
                text=self._get_button_text(),
                fg_color=COLORS["primary"]
            )
            # Canon-Dialoge wieder verstecken
            self._hide_canon_dialogs()

    # ========== Reset-Modus (Papierstau) ==========

    def _translate_reset_step(self, text: str) -> str:
        if text.startswith("Schritt 1/3"):
            return t(self.config, "printer.reset_step_jobs")
        if text.startswith("Schritt 2/3"):
            return t(self.config, "printer.reset_step_spooler")
        if text.startswith("Schritt 3/3"):
            return t(self.config, "printer.reset_step_usb")
        if "Status" in text:
            return t(self.config, "printer.reset_step_status")
        return text

    def _start_reset(self):
        """Startet den automatischen Drucker-Reset"""
        if self._reset_started:
            return
        self._reset_started = True

        from src.printer.controller import get_printer_controller
        controller = get_printer_controller()

        def on_step(text):
            if self._is_open:
                translated = self._translate_reset_step(text)
                def _update():
                    self.status_label.configure(text=translated)
                    self._advance_reset_segment()
                self.after(0, _update)

        def on_done(success, message):
            if not self._is_open:
                return
            # Nach Reset IMMER in Bestätigungs-Modus wechseln
            # (User muss bestätigen dass alles OK ist)
            self.after(0, lambda: self._switch_to_confirm_mode(success, message))

        controller.reset_printer(on_step=on_step, on_done=on_done)

    def _switch_to_confirm_mode(self, success: bool, message: str):
        """Nach Reset: Bestätigungs-Button anzeigen"""
        logger.info(f"Reset fertig (success={success}): {message}")

        self._reset_started = False
        if success:
            # Letztes Segment füllen: Reset komplett
            try:
                for seg in self._reset_segments:
                    seg.configure(fg_color=COLORS["primary"])
            except Exception:
                pass
            self.status_label.configure(
                text=t(self.config, "printer.reset_done"),
                text_color=COLORS["text_primary"]
            )
            self.animation_label.configure(text="")
        else:
            self.status_label.configure(
                text=t(self.config, "printer.manual_check", message=message),
                text_color=COLORS["text_primary"]
            )
            self.animation_label.configure(text="")

        # Bestätigungs-Button zeigen
        self.confirm_btn.configure(text=t(self.config, "printer.button_fixed"))
        self.confirm_btn.pack(pady=(24, 0))
        self.hint_label.configure(text=t(self.config, "printer.after_hint"))

    # ========== Service-Ausstieg mit PIN (Bug #49) ==========

    def _show_service_pin(self):
        """Zeigt die PIN-Karte für den Service-Ausstieg (Touch-Numpad)."""
        if self._pin_frame is not None:
            return
        logger.info("Service-Ausstieg: PIN-Karte geöffnet")

        self._pin_entry_value = ""

        screen_h = self.winfo_screenheight()
        btn_size = min(64, max(46, int(screen_h * 0.07)))

        self._pin_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=16
        )
        self._pin_frame.place(relx=0.5, rely=0.5, anchor="center")
        self._pin_frame.lift()

        ctk.CTkLabel(
            self._pin_frame,
            text=t(self.config, "printer.service_pin_title"),
            font=("Segoe UI", 18, "bold"),
            text_color=COLORS["text_primary"]
        ).pack(pady=(18, 8), padx=30)

        self._pin_display = ctk.CTkLabel(
            self._pin_frame,
            text="",
            font=("Segoe UI", 26, "bold"),
            text_color=COLORS["text_primary"],
            height=34
        )
        self._pin_display.pack(pady=(0, 4))

        self._pin_error_label = ctk.CTkLabel(
            self._pin_frame,
            text="",
            font=("Segoe UI", 13),
            text_color=COLORS["error"],
            height=18
        )
        self._pin_error_label.pack(pady=(0, 4))

        numpad = ctk.CTkFrame(self._pin_frame, fg_color="transparent")
        numpad.pack(pady=(0, 8), padx=20)
        for row in [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["⌫", "0", "✓"]]:
            row_frame = ctk.CTkFrame(numpad, fg_color="transparent")
            row_frame.pack()
            for key in row:
                ctk.CTkButton(
                    row_frame,
                    text=key,
                    width=btn_size,
                    height=btn_size,
                    font=("Segoe UI", int(btn_size * 0.36)),
                    fg_color=COLORS["bg_light"] if key.isdigit() else COLORS["bg_dark"],
                    hover_color=COLORS["bg_dark"],
                    corner_radius=10,
                    command=lambda k=key: self._pin_key(k)
                ).pack(side="left", padx=3, pady=3)

        ctk.CTkButton(
            self._pin_frame,
            text=t(self.config, "common.cancel"),
            font=("Segoe UI", 13),
            width=120,
            height=30,
            fg_color="transparent",
            hover_color=COLORS["bg_light"],
            text_color=COLORS["text_muted"],
            command=self._hide_service_pin
        ).pack(pady=(0, 14))

    def _hide_service_pin(self):
        if self._pin_frame is not None:
            self._pin_frame.destroy()
            self._pin_frame = None

    def _pin_key(self, key: str):
        """Numpad-Taste der Service-PIN-Karte."""
        if key == "⌫":
            self._pin_entry_value = self._pin_entry_value[:-1]
        elif key == "✓":
            self._check_service_pin()
            return
        else:
            self._pin_entry_value += key
            if len(self._pin_entry_value) >= 4:
                self._check_service_pin()
                return
        self._pin_display.configure(text="●" * len(self._pin_entry_value))

    def _check_service_pin(self):
        """Prüft Service-/Admin-PIN und schließt das Overlay erzwungen."""
        entered = self._pin_entry_value
        self._pin_entry_value = ""
        self._pin_display.configure(text="")

        valid_pins = []
        try:
            from src.ui.screens.service import SERVICE_PIN
            valid_pins.append(str(SERVICE_PIN))
        except Exception:
            pass
        valid_pins.append(str(self.config.get("admin_pin", "3198")))
        # Kundenmenü-PIN (2015, siehe admin.py): Die Hotline gibt diese PIN
        # bereits an Kunden heraus – so kann Felix das Fenster telefonisch
        # freigeben lassen, ohne die Service-PIN zu verraten.
        valid_pins.append("2015")

        if entered in valid_pins:
            logger.warning(
                f"Service-Ausstieg: Overlay per PIN geschlossen "
                f"(Fehler war: '{self.error_text}') – Auto-Overlay 10 Min pausiert"
            )
            self._force_close()
        else:
            logger.info("Service-Ausstieg: falsche PIN eingegeben")
            self._pin_error_label.configure(
                text=t(self.config, "printer.service_pin_wrong")
            )

    def _force_close(self):
        """Schließt das Overlay OHNE Drucker-Prüfung (Service-Entscheidung).

        Wichtig: Der Status-Poll in app.py würde das Overlay sonst beim
        nächsten Tick sofort wieder öffnen → Snooze setzen. Die rote
        Top-Bar-Warnung bleibt sichtbar, der Fehler wird also nicht versteckt.
        """
        try:
            if hasattr(self.app, "snooze_printer_overlay"):
                self.app.snooze_printer_overlay(600)
        except Exception as e:
            logger.debug(f"snooze_printer_overlay Fehler: {e}")
        self._close()

    # ========== Erfolg + Lifecycle ==========

    def _show_resolved(self):
        """Fehler behoben → Kurz Erfolg zeigen, dann schließen"""
        self.animation_label.configure(text="")
        self.status_label.configure(
            text=t(self.config, "printer.ready"),
            text_color=COLORS["primary"]
        )
        self.error_label.configure(
            text=t(self.config, "printer.resolved"),
            text_color=COLORS["text_secondary"]
        )
        self.confirm_btn.pack_forget()
        self.hint_label.configure(text="")

        self.after(2000, self._close)

    def _close(self):
        """Schließt das Overlay"""
        if not self._is_open:
            return
        self._is_open = False

        # Canon-Dialoge final aufräumen
        try:
            from src.printer.controller import get_printer_controller
            get_printer_controller().close_canon_dialogs()
        except Exception:
            pass

        try:
            self.attributes('-topmost', False)
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        logger.info("PrinterErrorOverlay geschlossen")

    def _emergency_quit(self):
        """Ctrl+Shift+Q - Dialog schließen und App beenden"""
        self._is_open = False
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if hasattr(self.app, '_emergency_quit'):
            self.app._emergency_quit()

    @property
    def is_open(self) -> bool:
        return self._is_open
