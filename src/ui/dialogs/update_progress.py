"""Update-Progress-Dialog

Fullscreen-Overlay mit `-topmost`, damit der Download-Fortschritt auch im
Kiosk-Modus garantiert sichtbar ist. Ersetzt die alte Inline-Progressbar im
ServiceDialog (die hinter der Haupt-App verschwunden ist).

Phasen:
1. Download — Progress-Bar läuft von 0 % bis 100 %, MB-Zähler aktualisiert sich
2. Installation — Text wechselt auf "Installation läuft, App startet neu..."
3. App wird vom BAT-Script beendet + neu gestartet

Bei Fehler: Error-Text + OK-Button zum Schließen.
"""

import threading
from typing import Callable, Optional

import customtkinter as ctk

from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

logger = get_logger(__name__)


class UpdateProgressDialog(ctk.CTkToplevel):
    """Fullscreen-Progress-Dialog für Software-Updates."""

    def __init__(self, parent, app, release: dict, on_done: Optional[Callable] = None):
        super().__init__(parent)

        self.app = app
        self.release = release
        self._on_done = on_done
        self._destroyed = False
        self._finished = False

        # Fullscreen-Overlay (wie FexosafeBackupDialog)
        self.overrideredirect(True)
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        self.geometry(f"{screen_w}x{screen_h}+0+0")
        self.configure(fg_color="#0a0a10")
        self.attributes("-topmost", True)
        self.transient(parent)
        self.grab_set()
        self.focus_force()
        self.lift()

        # Emergency-Quit auch hier abfangen
        self.bind("<Control-Shift-Q>", lambda e: self._emergency_quit())
        self.bind("<Control-Shift-q>", lambda e: self._emergency_quit())

        self._build_ui(screen_w, screen_h)

        new_ver = release.get("version", "?")
        size_mb = release.get("size", 0) / (1024 * 1024)
        logger.info(f"Update-Progress-Dialog geöffnet: v{new_ver} ({size_mb:.1f} MB)")

        # Download automatisch starten
        self._start_download()

    def _build_ui(self, screen_w: int, screen_h: int):
        bg = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
        bg.pack(fill="both", expand=True)

        card_w = min(560, int(screen_w * 0.85))
        self.card = ctk.CTkFrame(
            bg,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["info"],
            border_width=2,
            corner_radius=16,
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center")

        # Icon
        icon_size = max(32, min(52, int(screen_h * 0.06)))
        ctk.CTkLabel(
            self.card,
            text="⬇️",
            font=("Segoe UI Emoji", icon_size),
        ).pack(pady=(30, 6))

        # Titel
        new_ver = self.release.get("version", "?")
        self.title_label = ctk.CTkLabel(
            self.card,
            text=f"Update wird installiert — v{new_ver}",
            font=FONTS["heading"],
            text_color=COLORS["info"],
        )
        self.title_label.pack(pady=(0, 4), padx=40)

        # Status-Text
        self.status_label = ctk.CTkLabel(
            self.card,
            text="Lade Update herunter...",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
        )
        self.status_label.pack(pady=(0, 18))

        # Progress-Bar (deutlich größer als vorher)
        bar_w = min(460, int(card_w * 0.85))
        self.progress_bar = ctk.CTkProgressBar(
            self.card,
            width=bar_w,
            height=28,
            fg_color=COLORS["bg_dark"],
            progress_color=COLORS["info"],
            corner_radius=14,
        )
        self.progress_bar.pack(pady=(0, 10))
        self.progress_bar.set(0)

        # MB-Counter
        total_mb = self.release.get("size", 0) / (1024 * 1024)
        self.mb_label = ctk.CTkLabel(
            self.card,
            text=f"0.0 / {total_mb:.1f} MB",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
        )
        self.mb_label.pack(pady=(0, 6))

        # Prozent-Text
        self.percent_label = ctk.CTkLabel(
            self.card,
            text="0 %",
            font=("Segoe UI", 14, "bold"),
            text_color=COLORS["text_secondary"],
        )
        self.percent_label.pack(pady=(0, 18))

        # Hinweis-Text
        self.hint_label = ctk.CTkLabel(
            self.card,
            text="Bitte nicht ausschalten.\nDie App startet nach dem Update automatisch neu.",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            justify="center",
        )
        self.hint_label.pack(pady=(0, 30), padx=40)

        # OK-Button (nur bei Fehler gepackt)
        self.ok_btn = ctk.CTkButton(
            self.card,
            text="OK",
            font=FONTS["button_large"],
            width=180,
            height=50,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            corner_radius=SIZES["corner_radius"],
            command=self._close,
        )

    # ================= Download =================

    def _start_download(self):
        def worker():
            try:
                from src.updater import download_update, apply_update_and_restart

                def on_progress(progress: float, text: str):
                    # Thread-safe UI-Update
                    self.after(0, lambda p=progress, t=text: self._on_progress(p, t))

                zip_path = download_update(
                    self.release["download_url"],
                    progress_callback=on_progress,
                )

                # Installations-Phase
                self.after(0, self._switch_to_install_phase)

                apply_update_and_restart(zip_path)

                # App beenden damit BAT-Script übernimmt
                self.after(800, self._quit_for_update)

            except Exception as e:
                logger.error(f"Update-Download/Apply fehlgeschlagen: {e}", exc_info=True)
                err_msg = str(e)
                self.after(0, lambda: self._show_error(err_msg))

        threading.Thread(target=worker, daemon=True, name="UpdateDownload").start()

    def _on_progress(self, progress: float, text: str):
        if self._destroyed:
            return
        try:
            self.progress_bar.set(progress)
            self.percent_label.configure(text=f"{int(progress * 100)} %")

            # Text könnte z.B. "Lade herunter... 52.3 / 143.4 MB" sein
            # Für MB-Label nur den Zahlenteil extrahieren, für Status-Label den Prefix
            if " / " in text and "MB" in text:
                # Parse "Lade herunter... 52.3 / 143.4 MB" → MB-Teil extrahieren
                try:
                    parts = text.split("... ", 1)
                    if len(parts) == 2:
                        self.status_label.configure(text="Lade Update herunter...")
                        self.mb_label.configure(text=parts[1])
                    else:
                        self.mb_label.configure(text=text)
                except Exception:
                    self.mb_label.configure(text=text)
            else:
                self.status_label.configure(text=text)
            self.update_idletasks()
        except Exception:
            pass

    def _switch_to_install_phase(self):
        if self._destroyed:
            return
        self.status_label.configure(text="Installation läuft, App startet neu...")
        self.progress_bar.set(1.0)
        self.percent_label.configure(text="100 %")
        self.mb_label.configure(text="Download abgeschlossen")
        self.hint_label.configure(
            text="Die App beendet sich gleich.\nDas Update wird installiert und die App startet automatisch.",
        )
        self.update_idletasks()

    def _quit_for_update(self):
        """Beendet die App damit das BAT-Script übernehmen kann."""
        if self._finished:
            return
        self._finished = True
        logger.info("App wird für Update beendet (Progress-Dialog)...")
        try:
            self.grab_release()
        except Exception:
            pass
        # App sauber beenden — BAT-Script wartet darauf
        try:
            self.app.quit()
        except Exception:
            # Harter Fallback damit BAT übernehmen kann
            import os
            os._exit(0)

    def _show_error(self, message: str):
        """Zeigt Fehlermeldung + OK-Button."""
        if self._destroyed:
            return
        self.title_label.configure(text="Update fehlgeschlagen", text_color=COLORS["error"])
        self.status_label.configure(text=message[:200], text_color=COLORS["error"])
        try:
            self.progress_bar.configure(progress_color=COLORS["error"])
        except Exception:
            pass
        self.hint_label.configure(
            text="Das Update konnte nicht installiert werden.\nDie aktuelle Version bleibt erhalten.",
        )
        self.ok_btn.pack(pady=(0, 30))

    def _close(self):
        """Dialog schließen (nur bei Fehler/Abbruch)."""
        self._destroyed = True
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        if self._on_done:
            try:
                self._on_done()
            except Exception:
                pass

    def _emergency_quit(self):
        self._destroyed = True
        try:
            self.grab_release()
            self.destroy()
        except Exception:
            pass
        if hasattr(self.app, "_emergency_quit"):
            self.app._emergency_quit()

    def destroy(self):
        self._destroyed = True
        super().destroy()
