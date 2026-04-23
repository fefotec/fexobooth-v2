"""FEXOSAFE Backup-Dialog

Kopiert alle Bilder auf den FEXOSAFE-Sicherungs-USB-Stick.
Zeigt Fortschritt und Ergebnis an.
"""

import shutil
import threading
from pathlib import Path

import customtkinter as ctk

from src.storage.local import SINGLES_PATH, PRINTS_PATH
from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

logger = get_logger(__name__)


class FexosafeBackupDialog(ctk.CTkToplevel):
    """Backup-Dialog für FEXOSAFE USB-Stick"""

    def __init__(self, parent, app, fexosafe_drive: str, on_complete: callable):
        super().__init__(parent)

        self.app = app
        self.fexosafe_drive = fexosafe_drive
        self._on_complete = on_complete
        self._backup_running = False
        self._destroyed = False

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
        logger.info(f"FEXOSAFE Backup Dialog geöffnet: {fexosafe_drive}")

    def _build_ui(self, screen_w: int, screen_h: int):
        """Baut die Dialog-UI auf"""
        bg_frame = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
        bg_frame.pack(fill="both", expand=True)
        bg_frame.bind("<Button-1>", lambda e: self._cancel())

        # Zentrierte Karte
        card_w = min(480, int(screen_w * 0.8))
        self.card = ctk.CTkFrame(
            bg_frame,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["info"],
            border_width=2,
            corner_radius=16
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.card.bind("<Button-1>", lambda e: "break")

        # Schließen-Button
        self.close_btn = ctk.CTkButton(
            self.card,
            text="✕",
            width=32,
            height=32,
            font=("Segoe UI", 16, "bold"),
            fg_color="transparent",
            hover_color=COLORS["error"],
            text_color=COLORS["text_muted"],
            corner_radius=16,
            command=self._cancel
        )
        self.close_btn.pack(anchor="e", padx=(0, 8), pady=(8, 0))

        # Icon
        icon_size = max(28, min(44, int(screen_h * 0.05)))
        ctk.CTkLabel(
            self.card,
            text="💾",
            font=("Segoe UI Emoji", icon_size)
        ).pack(pady=(0, 4))

        # Titel
        ctk.CTkLabel(
            self.card,
            text="FEXOSAFE erkannt",
            font=FONTS["heading"],
            text_color=COLORS["info"]
        ).pack(pady=(0, 4))

        ctk.CTkLabel(
            self.card,
            text="Bilder auf USB sichern?",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(pady=(0, 10))

        # Bilder-Statistik
        single_count, print_count = self._count_images()
        total = single_count + print_count
        ctk.CTkLabel(
            self.card,
            text=f"{single_count} Singles, {print_count} Prints auf Festplatte ({total} gesamt)",
            font=FONTS["small"],
            text_color=COLORS["text_muted"]
        ).pack(pady=(0, 15))

        # Buttons
        btn_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        btn_frame.pack(pady=(0, 5), padx=30)

        btn_w = min(280, int(card_w * 0.7))
        btn_h = max(50, min(60, int(screen_h * 0.07)))

        self.backup_btn = ctk.CTkButton(
            btn_frame,
            text="BILDER SICHERN",
            font=FONTS["button_large"],
            width=btn_w,
            height=btn_h,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            text_color=COLORS["text_primary"],
            corner_radius=SIZES["corner_radius"],
            command=self._start_backup
        )
        self.backup_btn.pack(pady=(0, 10))

        # Deaktivieren wenn keine Bilder vorhanden
        if total == 0:
            self.backup_btn.configure(state="disabled", fg_color=COLORS["bg_light"])

        self.cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            font=FONTS["button"],
            width=btn_w,
            height=btn_h - 8,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_secondary"],
            corner_radius=SIZES["corner_radius"],
            command=self._cancel
        )
        self.cancel_btn.pack()

        # Fortschrittsbereich (zunächst unsichtbar)
        self.progress_frame = ctk.CTkFrame(self.card, fg_color="transparent")

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            width=min(380, int(card_w * 0.8)),
            height=12,
            fg_color=COLORS["bg_dark"],
            progress_color=COLORS["info"],
            corner_radius=6
        )
        self.progress_bar.pack(pady=(5, 3))
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"]
        )
        self.progress_label.pack(pady=(0, 5))

        # Ergebnis-Label (zunächst unsichtbar)
        self.result_label = ctk.CTkLabel(
            self.card,
            text="",
            font=FONTS["body_bold"],
            text_color=COLORS["success"]
        )

        # OK-Button (zunächst unsichtbar)
        self.ok_btn = ctk.CTkButton(
            self.card,
            text="OK",
            font=FONTS["button_large"],
            width=160,
            height=50,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            corner_radius=SIZES["corner_radius"],
            command=self._close
        )

        # Escape-Taste
        self.bind("<Escape>", lambda e: self._cancel())

    def _count_images(self) -> tuple:
        """Zählt Bilder in beiden Ordnern"""
        single_count = 0
        print_count = 0
        if SINGLES_PATH.exists():
            single_count = len(list(SINGLES_PATH.glob("*.jpg")))
        if PRINTS_PATH.exists():
            print_count = len(list(PRINTS_PATH.glob("*.jpg")))
        return single_count, print_count

    def _start_backup(self):
        """Startet den Backup-Prozess"""
        if self._backup_running:
            return

        self._backup_running = True

        # Buttons ausblenden, Fortschritt einblenden
        self.backup_btn.configure(state="disabled", fg_color=COLORS["bg_light"])
        self.cancel_btn.configure(state="disabled")
        self.close_btn.configure(state="disabled")
        self.progress_frame.pack(fill="x", padx=30, pady=(10, 15))

        thread = threading.Thread(target=self._run_backup, daemon=True)
        thread.start()

    def _get_last_event_id(self) -> str:
        """Ermittelt die Buchungs-ID (Event-ID) für den Zielordner.

        Reihenfolge: aktive Buchung → aktuelle Statistik → letzte Historie →
        Fallback Datum.
        """
        # 1. Aktive Buchung
        try:
            if self.app.booking_manager.is_loaded:
                return self.app.booking_manager.booking_id
        except Exception as e:
            logger.debug(f"Event-ID aus booking_manager fehlgeschlagen: {e}")

        # 2. Statistik (laufend oder letzte Historie)
        try:
            from src.storage.statistics import get_statistics_manager
            stats = get_statistics_manager()
            if stats.current and stats.current.booking_id:
                return stats.current.booking_id

            all_stats = stats.get_all_stats()
            if all_stats:
                last = all_stats[-1]
                bid = last.get("booking_id", "")
                if bid:
                    return bid
        except Exception as e:
            logger.debug(f"Event-ID aus Statistik fehlgeschlagen: {e}")

        # 3. Fallback: Datum
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d_%H%M")

    def _run_backup(self):
        """Kopiert alle Bilder auf FEXOSAFE (Background-Thread)"""
        fexosafe_root = Path(self.fexosafe_drive)
        event_id = self._get_last_event_id() or "unbekannt"
        bilder_dest = fexosafe_root / event_id
        singles_dest = bilder_dest / "Single"
        prints_dest = bilder_dest / "Prints"

        logger.info(f"FEXOSAFE Backup-Ziel: {bilder_dest}")

        try:
            singles_dest.mkdir(parents=True, exist_ok=True)
            prints_dest.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.after(0, lambda: self._show_error(f"Ordner erstellen fehlgeschlagen: {e}"))
            return

        # Dateien sammeln
        file_list = []
        if SINGLES_PATH.exists():
            for f in SINGLES_PATH.glob("*.jpg"):
                file_list.append((f, singles_dest))
        if PRINTS_PATH.exists():
            for f in PRINTS_PATH.glob("*.jpg"):
                file_list.append((f, prints_dest))

        total = len(file_list)
        if total == 0:
            self.after(0, lambda: self._show_result(0, 0, 0))
            return

        copied = 0
        skipped = 0
        errors = 0

        for i, (src, dest_dir) in enumerate(file_list):
            if self._destroyed:
                return

            try:
                dest = dest_dir / src.name
                if dest.exists():
                    skipped += 1
                else:
                    shutil.copy2(str(src), str(dest))
                    copied += 1
            except Exception as e:
                errors += 1
                logger.warning(f"Backup-Fehler: {src.name}: {e}")

            # Progress alle 3 Dateien oder am Ende
            if i % 3 == 0 or i == total - 1:
                progress = (i + 1) / total
                text = f"Kopiere... {i + 1}/{total}"
                self.after(0, lambda t=text, p=progress: self._update_progress(t, p))

        self.after(0, lambda: self._show_result(copied, skipped, errors))

    def _update_progress(self, text: str, value: float):
        """Aktualisiert Fortschritt (thread-safe)"""
        if self._destroyed:
            return
        try:
            self.progress_bar.set(value)
            self.progress_label.configure(text=text)
        except Exception:
            pass

    def _show_result(self, copied: int, skipped: int, errors: int):
        """Zeigt Backup-Ergebnis"""
        if self._destroyed:
            return

        total = copied + skipped + errors

        if errors == 0:
            if skipped > 0:
                text = f"{copied} Bilder gesichert, {skipped} bereits vorhanden"
            else:
                text = f"{copied} Bilder gesichert!"
            color = COLORS["success"]
        else:
            text = f"{copied} gesichert, {errors} Fehler"
            color = COLORS["warning"]

        self.result_label.configure(text=text, text_color=color)
        self.result_label.pack(pady=(10, 5))
        self.ok_btn.pack(pady=(5, 20))

        # Fortschritt auf 100%
        self.progress_bar.set(1.0)
        self.progress_label.configure(text=f"Fertig: {total} Dateien verarbeitet")

        logger.info(f"FEXOSAFE Backup: {copied} kopiert, {skipped} übersprungen, {errors} Fehler")

    def _show_error(self, msg: str):
        """Zeigt Fehlermeldung"""
        if self._destroyed:
            return
        self.result_label.configure(text=msg, text_color=COLORS["error"])
        self.result_label.pack(pady=(10, 5))
        self.ok_btn.pack(pady=(5, 20))

    def _cancel(self):
        """Dialog abbrechen (nur wenn kein Backup läuft)"""
        if self._backup_running:
            return
        self._close()

    def _close(self):
        """Dialog schließen"""
        self._destroyed = True
        callback = self._on_complete
        self.grab_release()
        self.destroy()
        if callback:
            callback()

    def _emergency_quit(self):
        """Ctrl+Shift+Q - Dialog schließen und App beenden"""
        self._destroyed = True
        self.grab_release()
        self.destroy()
        if hasattr(self.app, '_emergency_quit'):
            self.app._emergency_quit()

    def destroy(self):
        """Override destroy um Flag zu setzen"""
        self._destroyed = True
        super().destroy()
