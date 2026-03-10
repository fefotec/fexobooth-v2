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

from src.ui.theme import COLORS, FONTS
from src.utils.logging import get_logger

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


def classify_error(error_text: str) -> str:
    """Klassifiziert einen Fehlertext in eine Kategorie.

    Returns: 'consumable', 'jam', 'other'
    - 'consumable': Overlay anzeigen, warten auf Bestätigung
    - 'jam': Overlay + automatischer Reset
    - 'other': Nur Top-Bar Warnung (offline, etc.)
    """
    if not error_text:
        return "other"
    upper = error_text.upper()

    # Explizit kein Overlay für Offline-Fehler
    for pattern in TOPBAR_ONLY_ERRORS:
        if pattern in upper:
            logger.debug(f"classify_error('{error_text}') → other (Top-Bar only)")
            return "other"

    for pattern in JAM_ERRORS:
        if pattern in upper:
            logger.info(f"classify_error('{error_text}') → jam")
            return "jam"

    for pattern in CONSUMABLE_ERRORS:
        if pattern in upper:
            logger.info(f"classify_error('{error_text}') → consumable")
            return "consumable"

    # Unbekannter Fehlertext: Im Zweifel als consumable behandeln
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
        self.error_text = error_text
        self.error_category = error_category  # 'consumable', 'jam'
        self._is_open = True
        self._animation_frame = 0
        self._reset_started = False
        self._checking = False  # Verhindert doppelte Prüfungen

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

        # Zentrierte Karte
        self.card = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["error"],
            border_width=3,
            corner_radius=20
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center")

        # Icon
        if self.error_category == "jam":
            icon_text = "⚙"
            title_text = "PAPIERSTAU"
            subtitle = "Wird automatisch behoben..."
            title_color = COLORS["warning"]
        else:
            icon_text = "⚠"
            title_text = "DRUCKER PROBLEM"
            subtitle = self._get_instruction_text()
            title_color = COLORS["error"]

        # Icon groß
        ctk.CTkLabel(
            self.card,
            text=icon_text,
            font=("Segoe UI", 72),
            text_color=title_color
        ).pack(pady=(40, 10))

        # Titel
        self.title_label = ctk.CTkLabel(
            self.card,
            text=title_text,
            font=("Segoe UI", 36, "bold"),
            text_color=title_color
        )
        self.title_label.pack(pady=(0, 5))

        # Fehlertext original
        self.error_label = ctk.CTkLabel(
            self.card,
            text=self.error_text,
            font=("Segoe UI", 20),
            text_color=COLORS["text_secondary"]
        )
        self.error_label.pack(pady=(0, 15))

        # Status/Anweisung
        self.status_label = ctk.CTkLabel(
            self.card,
            text=subtitle,
            font=("Segoe UI", 18),
            text_color=COLORS["text_primary"],
            wraplength=450,
            justify="center"
        )
        self.status_label.pack(pady=(0, 10))

        # Animations-Bereich (für Reset)
        self.animation_label = ctk.CTkLabel(
            self.card,
            text="",
            font=("Segoe UI", 28),
            text_color=COLORS["warning"]
        )
        self.animation_label.pack(pady=(5, 5))

        # Progress-Bar (für Reset)
        self.progress_bar = ctk.CTkProgressBar(
            self.card,
            width=350,
            height=8,
            fg_color=COLORS["bg_dark"],
            progress_color=COLORS["warning"],
            corner_radius=4,
            mode="indeterminate"
        )
        if self.error_category == "jam":
            self.progress_bar.pack(pady=(5, 10))
            self.progress_bar.start()

        # ===== Bestätigungs-Button (für consumable Fehler) =====
        self.confirm_btn = ctk.CTkButton(
            self.card,
            text=self._get_button_text(),
            font=("Segoe UI", 22, "bold"),
            fg_color=COLORS["success"],
            hover_color="#1a8f3a",
            text_color="#ffffff",
            height=60,
            width=400,
            corner_radius=12,
            command=self._on_confirm
        )
        if self.error_category != "jam":
            self.confirm_btn.pack(pady=(15, 10))

        # Hinweis unten
        hint_text = ("Bitte nicht ausschalten!"
                     if self.error_category == "jam"
                     else "Erst Material wechseln, dann bestätigen")
        self.hint_label = ctk.CTkLabel(
            self.card,
            text=hint_text,
            font=("Segoe UI", 13),
            text_color=COLORS["text_muted"]
        )
        self.hint_label.pack(pady=(5, 35), padx=50)

    def _get_instruction_text(self) -> str:
        """Gibt Anweisungstext je nach Fehler zurück"""
        upper = self.error_text.upper()
        if "PAPIER" in upper:
            return "Bitte Papier nachlegen und Kassette einsetzen"
        elif "TINTE" in upper or "KASSETTE" in upper:
            return "Bitte Tintenkassette wechseln"
        elif "KLAPPE" in upper or "DOOR" in upper:
            return "Bitte Druckerklappe schließen"
        else:
            return "Bitte Drucker prüfen"

    def _get_button_text(self) -> str:
        """Gibt Button-Text je nach Fehler zurück"""
        upper = self.error_text.upper()
        if "PAPIER" in upper:
            return "PAPIER EINGELEGT"
        elif "TINTE" in upper or "KASSETTE" in upper:
            return "KASSETTE GEWECHSELT"
        elif "KLAPPE" in upper or "DOOR" in upper:
            return "KLAPPE GESCHLOSSEN"
        else:
            return "PROBLEM BEHOBEN"

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
            text="Wird geprüft...",
            fg_color=COLORS["bg_light"]
        )
        self.status_label.configure(text="Drucker wird geprüft...")
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
            self.error_label.configure(text=error)
            self.status_label.configure(
                text="Fehler besteht noch!\n" + self._get_instruction_text(),
                text_color=COLORS["error"]
            )
            self.animation_label.configure(text="⚠", text_color=COLORS["error"])
            self.confirm_btn.configure(
                state="normal",
                text=self._get_button_text(),
                fg_color=COLORS["success"]
            )
            # Canon-Dialoge wieder verstecken
            self._hide_canon_dialogs()

    # ========== Reset-Modus (Papierstau) ==========

    def _start_reset(self):
        """Startet den automatischen Drucker-Reset"""
        if self._reset_started:
            return
        self._reset_started = True

        from src.printer.controller import get_printer_controller
        controller = get_printer_controller()

        # Animation starten
        self._animate_reset()

        def on_step(text):
            if self._is_open:
                self.after(0, lambda: self.status_label.configure(text=text))

        def on_done(success, message):
            if not self._is_open:
                return
            # Nach Reset IMMER in Bestätigungs-Modus wechseln
            # (User muss bestätigen dass alles OK ist)
            self.after(0, lambda: self._switch_to_confirm_mode(success, message))

        controller.reset_printer(on_step=on_step, on_done=on_done)

    def _animate_reset(self):
        """Zeigt rotierende Animation während Reset"""
        if not self._is_open:
            return

        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._animation_frame = (self._animation_frame + 1) % len(frames)
        self.animation_label.configure(text=frames[self._animation_frame])

        if self._reset_started and self._is_open:
            self.after(120, self._animate_reset)

    def _switch_to_confirm_mode(self, success: bool, message: str):
        """Nach Reset: Bestätigungs-Button anzeigen"""
        logger.info(f"Reset fertig (success={success}): {message}")

        self._reset_started = False
        self.progress_bar.stop()
        self.progress_bar.pack_forget()

        if success:
            self.status_label.configure(
                text="Reset durchgeführt.\nBitte prüfe ob der Drucker bereit ist.",
                text_color=COLORS["text_primary"]
            )
            self.animation_label.configure(text="")
        else:
            self.status_label.configure(
                text=f"{message}\nBitte Drucker manuell prüfen.",
                text_color=COLORS["warning"]
            )
            self.animation_label.configure(text="⚠", text_color=COLORS["warning"])

        # Bestätigungs-Button zeigen
        self.confirm_btn.configure(text="PROBLEM BEHOBEN")
        self.confirm_btn.pack(pady=(15, 10))
        self.hint_label.configure(text="Erst Problem beheben, dann bestätigen")

    # ========== Erfolg + Lifecycle ==========

    def _show_resolved(self):
        """Fehler behoben → Kurz Erfolg zeigen, dann schließen"""
        self.animation_label.configure(text="✓", text_color=COLORS["success"])
        self.status_label.configure(
            text="Drucker ist wieder bereit!",
            text_color=COLORS["success"]
        )
        self.error_label.configure(
            text="Problem behoben",
            text_color=COLORS["success"]
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
