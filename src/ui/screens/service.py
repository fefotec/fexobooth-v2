"""Service-Menü - Internes Wartungsmenü für fexobox-Geräte

Aufruf über Service-PIN 6588 (hardcodiert).
Funktionen:
- Alle Bilder löschen (Datenschutz)
- Bilder auf USB sichern (mit Event-ID Überordner)
- Software-Update von GitHub (manuell, nur bei Internetverbindung)
"""

import customtkinter as ctk
import shutil
import threading
from pathlib import Path
from typing import Optional

from src.ui.theme import COLORS, FONTS, SIZES
from src.storage.local import SINGLES_PATH, PRINTS_PATH, IMAGES_PATH
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Hardcodierter Service-PIN
SERVICE_PIN = "6588"


class ServiceDialog(ctk.CTkToplevel):
    """Service-Menü Dialog für interne Wartung"""

    def __init__(self, parent, app):
        super().__init__(parent)

        self.app = app
        self.parent_window = parent

        self.title("Service-Menü")
        self.configure(fg_color="#0a0a10")

        # Modal machen
        self.transient(parent)
        self.grab_set()

        # Ctrl+Shift+Q auch im Dialog abfangen (grab_set blockiert Root-Bindings!)
        self.bind("<Control-Shift-Q>", lambda e: self._emergency_quit())
        self.bind("<Control-Shift-q>", lambda e: self._emergency_quit())

        # Vollbild-Overlay
        self.overrideredirect(True)
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        self.geometry(f"{screen_w}x{screen_h}+0+0")

        self.lift()
        self.focus_force()

        # Escape zum Schließen
        self.bind("<Escape>", lambda e: self._close())

        self._show_menu()

    def _show_menu(self):
        """Zeigt das Service-Menü"""
        # Dunkler Hintergrund
        self.main_frame = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
        self.main_frame.pack(fill="both", expand=True)

        # Zentrierte Karte
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        card_w = min(500, int(screen_w * 0.85))

        card = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["warning"],
            border_width=2,
            corner_radius=16
        )
        card.place(relx=0.5, rely=0.5, anchor="center")

        # Schließen-Button
        close_btn = ctk.CTkButton(
            card,
            text="✕",
            width=36,
            height=36,
            font=("Segoe UI", 18, "bold"),
            fg_color="transparent",
            hover_color=COLORS["error"],
            text_color=COLORS["text_muted"],
            corner_radius=18,
            command=self._close
        )
        close_btn.pack(anchor="e", padx=(0, 10), pady=(10, 0))

        # Titel
        ctk.CTkLabel(
            card,
            text="SERVICE-MENU",
            font=("Segoe UI", 26, "bold"),
            text_color=COLORS["warning"]
        ).pack(pady=(0, 5))

        ctk.CTkLabel(
            card,
            text="Internes Wartungsmenü",
            font=FONTS["small"],
            text_color=COLORS["text_muted"]
        ).pack(pady=(0, 20))

        # Bilder-Info anzeigen
        single_count, print_count = self._count_images()
        info_text = f"Bilder auf Festplatte: {single_count} Singles, {print_count} Prints"
        self.info_label = ctk.CTkLabel(
            card,
            text=info_text,
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        )
        self.info_label.pack(pady=(0, 20))

        # Button-Container
        btn_container = ctk.CTkFrame(card, fg_color="transparent")
        btn_container.pack(pady=(0, 10), padx=30)

        # 1. Bilder sichern (USB)
        backup_btn = ctk.CTkButton(
            btn_container,
            text="Bilder sichern",
            font=("Segoe UI", 16, "bold"),
            width=min(380, int(card_w * 0.8)),
            height=60,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            corner_radius=SIZES["corner_radius"],
            command=self._backup_images
        )
        backup_btn.pack(pady=8)

        ctk.CTkLabel(
            btn_container,
            text="Kopiert alle Bilder auf USB-Stick (Ordner = Event-ID)",
            font=FONTS["tiny"],
            text_color=COLORS["text_muted"]
        ).pack(pady=(0, 12))

        # 2. Bilder löschen
        delete_btn = ctk.CTkButton(
            btn_container,
            text="Alle Bilder löschen",
            font=("Segoe UI", 16, "bold"),
            width=min(380, int(card_w * 0.8)),
            height=60,
            fg_color=COLORS["error"],
            hover_color="#ff6b7a",
            corner_radius=SIZES["corner_radius"],
            command=self._confirm_delete
        )
        delete_btn.pack(pady=8)

        ctk.CTkLabel(
            btn_container,
            text="Löscht Singles + Prints von der Festplatte (Datenschutz)",
            font=FONTS["tiny"],
            text_color=COLORS["text_muted"]
        ).pack(pady=(0, 12))

        # 3. Software-Update
        update_btn = ctk.CTkButton(
            btn_container,
            text="Software aktualisieren",
            font=("Segoe UI", 16, "bold"),
            width=min(380, int(card_w * 0.8)),
            height=60,
            fg_color=COLORS["info"],
            hover_color="#4dabf7",
            corner_radius=SIZES["corner_radius"],
            command=self._check_update
        )
        update_btn.pack(pady=8)

        # Versions-Info anzeigen
        from src.updater import get_current_version
        version = get_current_version()
        ctk.CTkLabel(
            btn_container,
            text=f"Aktuelle Version: {version} — Prüft GitHub auf neue Version",
            font=FONTS["tiny"],
            text_color=COLORS["text_muted"]
        ).pack(pady=(0, 12))

        # Status-Bereich (für Fortschrittsanzeige)
        self.status_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.status_frame.pack(fill="x", padx=30, pady=(0, 20))

        self.progress_bar = ctk.CTkProgressBar(
            self.status_frame,
            width=min(380, int(card_w * 0.8)),
            height=12,
            fg_color=COLORS["bg_dark"],
            progress_color=COLORS["primary"],
            corner_radius=6
        )
        # Nicht packen - wird bei Bedarf angezeigt

        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"]
        )
        # Nicht packen - wird bei Bedarf angezeigt

    def _count_images(self) -> tuple:
        """Zählt Bilder in lokalen Ordnern"""
        single_count = 0
        print_count = 0

        if SINGLES_PATH.exists():
            single_count = len(list(SINGLES_PATH.glob("*.jpg")))
        if PRINTS_PATH.exists():
            print_count = len(list(PRINTS_PATH.glob("*.jpg")))

        return single_count, print_count

    def _show_progress(self, text: str, value: float = 0.0):
        """Zeigt Fortschrittsanzeige"""
        self.progress_bar.pack(pady=(5, 3))
        self.progress_bar.set(value)
        self.status_label.configure(text=text)
        self.status_label.pack(pady=(0, 5))
        self.update_idletasks()

    def _update_progress(self, text: str, value: float):
        """Aktualisiert Fortschrittsanzeige (thread-safe)"""
        try:
            self.progress_bar.set(value)
            self.status_label.configure(text=text)
            self.update_idletasks()
        except Exception:
            pass  # Dialog wurde bereits geschlossen

    def _hide_progress(self):
        """Versteckt Fortschrittsanzeige"""
        self.progress_bar.pack_forget()
        self.status_label.pack_forget()

    # ========== Bilder löschen ==========

    def _confirm_delete(self):
        """Bestätigungsdialog vor dem Löschen"""
        single_count, print_count = self._count_images()
        total = single_count + print_count

        if total == 0:
            self._show_result("Keine Bilder vorhanden.", "info")
            return

        # Bestätigungsdialog
        confirm = ctk.CTkToplevel(self)
        confirm.overrideredirect(True)
        confirm.configure(fg_color=COLORS["bg_dark"])

        dialog_w, dialog_h = 380, 200
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - dialog_w) // 2
        y = (screen_h - dialog_h) // 2
        confirm.geometry(f"{dialog_w}x{dialog_h}+{x}+{y}")
        confirm.attributes("-topmost", True)
        confirm.grab_set()

        content = ctk.CTkFrame(
            confirm,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["error"],
            border_width=2,
            corner_radius=12
        )
        content.pack(fill="both", expand=True, padx=2, pady=2)

        ctk.CTkLabel(
            content,
            text=f"WIRKLICH {total} Bilder löschen?",
            font=("Segoe UI", 16, "bold"),
            text_color=COLORS["error"]
        ).pack(pady=(25, 5))

        ctk.CTkLabel(
            content,
            text=f"{single_count} Singles + {print_count} Prints\nDiese Aktion kann nicht rückgängig gemacht werden!",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            justify="center"
        ).pack(pady=(0, 20))

        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack()

        def do_delete():
            confirm.destroy()
            self._execute_delete()

        ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            width=120, height=45,
            font=FONTS["button"],
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            command=confirm.destroy
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="LÖSCHEN",
            width=120, height=45,
            font=FONTS["button"],
            fg_color=COLORS["error"],
            hover_color="#ff6b7a",
            command=do_delete
        ).pack(side="left", padx=10)

    def _execute_delete(self):
        """Führt das Löschen aller lokalen Bilder aus (USB bleibt unangetastet)"""
        self._show_progress("Lösche Bilder...", 0.0)

        def do_delete():
            deleted = 0
            errors = 0

            # Nur lokale JPGs sammeln
            all_files = []
            for folder in [SINGLES_PATH, PRINTS_PATH]:
                if folder.exists():
                    all_files.extend(list(folder.glob("*.jpg")))

            total = len(all_files)
            if total == 0:
                self.after(0, lambda: self._show_result("Keine Bilder zum Löschen.", "info"))
                return

            for i, file in enumerate(all_files):
                try:
                    file.unlink()
                    deleted += 1
                except Exception as e:
                    logger.warning(f"Löschen fehlgeschlagen: {file.name} - {e}")
                    errors += 1

                # Fortschritt aktualisieren (alle 5 Dateien oder am Ende)
                if i % 5 == 0 or i == total - 1:
                    progress = (i + 1) / total
                    text = f"Lösche... {i + 1}/{total}"
                    self.after(0, lambda t=text, p=progress: self._update_progress(t, p))

            # Ergebnis anzeigen
            if errors == 0:
                msg = f"{deleted} Bilder gelöscht."
                self.after(0, lambda: self._show_result(msg, "success"))
            else:
                msg = f"{deleted} gelöscht, {errors} Fehler."
                self.after(0, lambda: self._show_result(msg, "warning"))

            # Info-Label aktualisieren
            self.after(0, self._refresh_info)

        thread = threading.Thread(target=do_delete, daemon=True)
        thread.start()

    # ========== Bilder sichern ==========

    def _backup_images(self):
        """Sichert alle Bilder auf USB-Stick mit Event-ID Ordner"""
        # USB prüfen
        usb_drive = self.app.usb_manager.find_usb_stick()
        if not usb_drive:
            self._show_result("Kein USB-Stick gefunden! Bitte einstecken.", "error")
            return

        single_count, print_count = self._count_images()
        total = single_count + print_count

        if total == 0:
            self._show_result("Keine Bilder zum Sichern vorhanden.", "info")
            return

        # Event-ID für Ordnername ermitteln
        event_id = self._get_last_event_id()
        folder_name = event_id if event_id else "unbekannt"

        usb_root = Path(usb_drive)
        backup_base = usb_root / folder_name

        # Prüfen ob Ordner bereits existiert
        if backup_base.exists():
            self._confirm_overwrite(usb_root, folder_name, total)
            return

        self._execute_backup(usb_root, folder_name)

    def _confirm_overwrite(self, usb_root: Path, folder_name: str, total: int):
        """Fragt ob bestehender Ordner überschrieben werden soll"""
        confirm = ctk.CTkToplevel(self)
        confirm.overrideredirect(True)
        confirm.configure(fg_color=COLORS["bg_dark"])

        dialog_w, dialog_h = 420, 210
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - dialog_w) // 2
        y = (screen_h - dialog_h) // 2
        confirm.geometry(f"{dialog_w}x{dialog_h}+{x}+{y}")
        confirm.attributes("-topmost", True)
        confirm.grab_set()

        content = ctk.CTkFrame(
            confirm,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["warning"],
            border_width=2,
            corner_radius=12
        )
        content.pack(fill="both", expand=True, padx=2, pady=2)

        ctk.CTkLabel(
            content,
            text=f"Ordner '{folder_name}' existiert bereits!",
            font=("Segoe UI", 15, "bold"),
            text_color=COLORS["warning"]
        ).pack(pady=(25, 5))

        ctk.CTkLabel(
            content,
            text=f"Auf dem USB-Stick gibt es bereits einen Ordner\nmit dieser Event-ID. Überschreiben?",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            justify="center"
        ).pack(pady=(0, 20))

        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack()

        def do_overwrite():
            confirm.destroy()
            self._execute_backup(usb_root, folder_name)

        ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            width=130, height=45,
            font=FONTS["button"],
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            command=confirm.destroy
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="Überschreiben",
            width=130, height=45,
            font=FONTS["button"],
            fg_color=COLORS["warning"],
            hover_color="#ffd000",
            text_color="#000000",
            command=do_overwrite
        ).pack(side="left", padx=10)

    def _execute_backup(self, usb_root: Path, folder_name: str):
        """Führt die Sicherung auf USB aus"""
        self._show_progress(f"Sichere auf USB -> {folder_name}/...", 0.0)

        def do_backup():
            backup_base = usb_root / folder_name
            backup_singles = backup_base / "Single"
            backup_prints = backup_base / "Prints"

            try:
                backup_singles.mkdir(parents=True, exist_ok=True)
                backup_prints.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"USB-Ordner erstellen fehlgeschlagen: {e}")
                self.after(0, lambda: self._show_result("Fehler: Ordner erstellen fehlgeschlagen.", "error"))
                return

            copied = 0
            errors = 0

            # Alle Dateien sammeln
            file_list = []
            if SINGLES_PATH.exists():
                for f in SINGLES_PATH.glob("*.jpg"):
                    file_list.append((f, backup_singles))
            if PRINTS_PATH.exists():
                for f in PRINTS_PATH.glob("*.jpg"):
                    file_list.append((f, backup_prints))

            total_files = len(file_list)
            if total_files == 0:
                self.after(0, lambda: self._show_result("Keine Bilder gefunden.", "info"))
                return

            for i, (src, dest_dir) in enumerate(file_list):
                try:
                    dest = dest_dir / src.name
                    shutil.copy2(src, dest)
                    copied += 1
                except Exception as e:
                    logger.warning(f"USB-Kopie fehlgeschlagen: {src.name} - {e}")
                    errors += 1

                # Fortschritt (alle 3 Dateien oder am Ende)
                if i % 3 == 0 or i == total_files - 1:
                    progress = (i + 1) / total_files
                    text = f"Kopiere... {i + 1}/{total_files}"
                    self.after(0, lambda t=text, p=progress: self._update_progress(t, p))

            # Ergebnis
            if errors == 0:
                msg = f"{copied} Bilder gesichert nach\nUSB:/{folder_name}/"
                self.after(0, lambda: self._show_result(msg, "success"))
            else:
                msg = f"{copied} kopiert, {errors} Fehler."
                self.after(0, lambda: self._show_result(msg, "warning"))

        thread = threading.Thread(target=do_backup, daemon=True)
        thread.start()

    def _get_last_event_id(self) -> str:
        """Ermittelt die letzte Event-ID (Buchungsnummer)"""
        # 1. Aktive Buchung prüfen
        if self.app.booking_manager.is_loaded:
            return self.app.booking_manager.booking_id

        # 2. Statistik prüfen (letzte Buchung)
        try:
            from src.storage.statistics import get_statistics_manager
            stats = get_statistics_manager()
            if stats.current and stats.current.booking_id:
                return stats.current.booking_id

            # Letzte aus Historie
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

    # ========== Software-Update ==========

    def _check_update(self):
        """Prüft auf neue Version bei GitHub"""
        self._show_progress("Prüfe auf Updates...", 0.1)

        def do_check():
            try:
                from src.updater import check_for_update
                release = check_for_update()
            except ConnectionError as e:
                logger.error(f"Update-Check: Verbindung fehlgeschlagen: {e}", exc_info=True)
                self.after(0, lambda: self._show_result(
                    f"Keine Internetverbindung.\nBitte WLAN verbinden und erneut versuchen.",
                    "error"
                ))
                return
            except Exception as e:
                logger.error(f"Update-Check fehlgeschlagen: {e}", exc_info=True)
                err_msg = str(e)
                self.after(0, lambda: self._show_result(
                    f"Update-Prüfung fehlgeschlagen:\n{err_msg}",
                    "error"
                ))
                return

            if release is None:
                self.after(0, lambda: self._show_result(
                    "Software ist bereits aktuell.", "success"
                ))
                return

            # Update verfügbar → Bestätigungsdialog
            self.after(0, lambda: self._confirm_update(release))

        thread = threading.Thread(target=do_check, daemon=True)
        thread.start()

    def _confirm_update(self, release: dict):
        """Zeigt Dialog: Update verfügbar, jetzt installieren?"""
        self._hide_progress()

        confirm = ctk.CTkToplevel(self)
        confirm.overrideredirect(True)
        confirm.configure(fg_color=COLORS["bg_dark"])

        dialog_w, dialog_h = 420, 240
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - dialog_w) // 2
        y = (screen_h - dialog_h) // 2
        confirm.geometry(f"{dialog_w}x{dialog_h}+{x}+{y}")
        confirm.attributes("-topmost", True)
        confirm.grab_set()

        content = ctk.CTkFrame(
            confirm,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["info"],
            border_width=2,
            corner_radius=12
        )
        content.pack(fill="both", expand=True, padx=2, pady=2)

        ctk.CTkLabel(
            content,
            text="Update verfügbar!",
            font=("Segoe UI", 18, "bold"),
            text_color=COLORS["info"]
        ).pack(pady=(25, 5))

        # Version + Größe anzeigen
        from src.updater import get_current_version
        current = get_current_version()
        new_ver = release.get("version", "?")
        size_mb = release.get("size", 0) / (1024 * 1024)
        size_text = f" ({size_mb:.0f} MB)" if size_mb > 0 else ""

        ctk.CTkLabel(
            content,
            text=f"Version {current}  →  {new_ver}{size_text}\n\n"
                 f"Die App wird beendet, aktualisiert\nund automatisch neu gestartet.",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            justify="center"
        ).pack(pady=(0, 20))

        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack()

        def do_update():
            confirm.destroy()
            self._execute_update(release)

        ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            width=130, height=45,
            font=FONTS["button"],
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            command=confirm.destroy
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="Jetzt updaten",
            width=130, height=45,
            font=FONTS["button"],
            fg_color=COLORS["info"],
            hover_color="#4dabf7",
            command=do_update
        ).pack(side="left", padx=10)

    def _execute_update(self, release: dict):
        """Lädt Update herunter und startet Installation"""
        self._show_progress("Lade Update herunter...", 0.0)

        def do_download():
            try:
                from src.updater import download_update, apply_update_and_restart

                # Download mit Fortschritts-Callback
                def on_progress(progress, text):
                    self.after(0, lambda t=text, p=progress:
                               self._update_progress(t, p))

                zip_path = download_update(
                    release["download_url"],
                    progress_callback=on_progress
                )

                # Update-Script erstellen und starten
                self.after(0, lambda: self._update_progress(
                    "Starte Update-Installation...", 1.0
                ))

                apply_update_and_restart(zip_path)

                # App beenden (nach kurzer Verzögerung für UI-Update)
                self.after(500, self._quit_for_update)

            except Exception as e:
                self.after(0, lambda: self._show_result(
                    f"Update fehlgeschlagen:\n{e}",
                    "error"
                ))

        thread = threading.Thread(target=do_download, daemon=True)
        thread.start()

    def _quit_for_update(self):
        """Beendet die App für das Update"""
        logger.info("App wird für Update beendet...")
        try:
            self.grab_release()
            self.destroy()
        except Exception:
            pass
        # App sauber beenden
        self.app.quit()

    # ========== UI-Helpers ==========

    def _show_result(self, message: str, level: str = "info"):
        """Zeigt Ergebnis-Nachricht an"""
        self._hide_progress()

        color_map = {
            "success": COLORS["success"],
            "error": COLORS["error"],
            "warning": COLORS["warning"],
            "info": COLORS["info"],
        }
        icon_map = {
            "success": "✅",
            "error": "❌",
            "warning": "⚠️",
            "info": "ℹ️",
        }

        color = color_map.get(level, COLORS["text_primary"])
        icon = icon_map.get(level, "")

        self.status_label.configure(
            text=f"{icon} {message}",
            text_color=color
        )
        self.status_label.pack(pady=5)

        # Fortschrittsbalken auf 100% bei Erfolg
        if level == "success":
            self.progress_bar.set(1.0)
            self.progress_bar.configure(progress_color=COLORS["success"])
            self.progress_bar.pack(pady=(5, 3))

    def _refresh_info(self):
        """Aktualisiert die Bilder-Info"""
        try:
            single_count, print_count = self._count_images()
            self.info_label.configure(
                text=f"Bilder auf Festplatte: {single_count} Singles, {print_count} Prints"
            )
        except Exception:
            pass

    def _emergency_quit(self):
        """Ctrl+Shift+Q im Dialog - Dialog schließen und App beenden"""
        self.grab_release()
        self.destroy()
        if hasattr(self.app, '_emergency_quit'):
            self.app._emergency_quit()

    def _close(self):
        """Schließt das Service-Menü"""
        self.grab_release()
        self.destroy()
