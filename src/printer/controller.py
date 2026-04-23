"""Drucker-Controller für Canon SELPHY

Funktionen:
- Software-Reset (Eskalation: Purge → Spooler Restart → USB Device Restart)
- Canon-Dialog-Erkennung und -Unterdrückung
- Druckerstatus-Abfrage
"""

import subprocess
import threading
import time
from typing import Optional, Callable

from src.utils.logging import get_logger

logger = get_logger(__name__)


class PrinterController:
    """Steuert den Canon SELPHY Drucker"""

    def __init__(self, printer_name: str = ""):
        self.printer_name = printer_name
        self._reset_in_progress = False

    def update_printer_name(self, name: str):
        """Aktualisiert den Druckernamen.

        Erkennt automatisch Drucker-Kopien (anderer USB-Port):
        'Canon SELPHY CP1000' matcht auch 'Canon SELPHY CP1000 (Kopie 1)'
        """
        if not name:
            self.printer_name = name
            return

        # Prüfen ob der Name exakt existiert
        try:
            import win32print
            available = [p[2] for p in win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )]
            if name not in available:
                from src.printer import find_matching_printer
                matched = find_matching_printer(name, available)
                if matched:
                    self.printer_name = matched
                    return
        except Exception:
            pass

        self.printer_name = name

    @property
    def is_resetting(self) -> bool:
        return self._reset_in_progress

    # ========== Status-Abfrage ==========

    def get_error(self) -> Optional[str]:
        """Prüft Drucker-Status und gibt Fehlertext zurück oder None wenn OK.

        Prüft 3 Ebenen:
        1. Spooler-Status-Flags
        2. Druckjob-Queue (pStatus)
        3. Canon-Fehlerfenster (EnumWindows)
        """
        error = self._check_spooler_status()
        if error:
            logger.debug(f"get_error() → Spooler: '{error}'")
            return error

        error = self._check_job_queue()
        if error:
            logger.debug(f"get_error() → Job-Queue: '{error}'")
            return error

        error = self._detect_canon_error_window()
        if error:
            logger.debug(f"get_error() → Canon-Dialog: '{error}'")
            return error

        return None

    def _check_spooler_status(self) -> Optional[str]:
        """Prüft Spooler-Status-Flags"""
        try:
            import win32print

            printer_name = self.printer_name or win32print.GetDefaultPrinter()
            if not printer_name:
                return "KEIN DRUCKER!"

            hPrinter = win32print.OpenPrinter(printer_name)
            try:
                info = win32print.GetPrinter(hPrinter, 2)
                status = info.get("Status", 0)
                attributes = info.get("Attributes", 0)

                is_offline = bool(status & 0x80) or bool(attributes & 0x400)
                is_not_available = bool(status & 0x1000)

                if is_offline or is_not_available:
                    return "DRUCKER AUS!"
                if status & 0x10:  # PAPER_OUT
                    return "PAPIER LEER!"
                if status & 0x40000:  # NO_TONER
                    return "KASSETTE LEER!"
                if status & 0x8:  # PAPER_JAM
                    return "PAPIERSTAU!"
                if status & 0x400000:  # DOOR_OPEN
                    return "KLAPPE OFFEN!"
                if status & 0x100000:  # USER_INTERVENTION
                    return "DRUCKER PRÜFEN!"
                if status & 0x2:  # ERROR
                    return "DRUCKER FEHLER!"
            finally:
                win32print.ClosePrinter(hPrinter)

        except Exception:
            return "DRUCKER FEHLT!"

        return None

    def _check_job_queue(self) -> Optional[str]:
        """Prüft Druckjobs auf Fehler.

        Verwendet Level 1 (JOB_INFO_1) statt Level 2,
        da Level 2 win32timezone benötigt (DateTime-Felder).
        Level 1 hat Status + pStatus - reicht für Fehlererkennung.
        """
        try:
            import win32print

            printer_name = self.printer_name or win32print.GetDefaultPrinter()
            if not printer_name:
                return None

            hPrinter = win32print.OpenPrinter(printer_name)
            try:
                # Level 1 statt 2! Level 2 braucht win32timezone für DateTime
                jobs = win32print.EnumJobs(hPrinter, 0, 10, 1)
                if not jobs:
                    return None

                JOB_STATUS_ERROR = 0x02
                JOB_STATUS_OFFLINE = 0x20
                JOB_STATUS_PAPEROUT = 0x40
                JOB_STATUS_BLOCKED = 0x200
                JOB_STATUS_USER_INTERVENTION = 0x400

                for job in jobs:
                    job_status = job.get("Status", 0)

                    # pStatus-Text (Canon-Treiber-Fehlermeldung)
                    status_text = job.get("pStatus", "")
                    if status_text:
                        lower = status_text.lower()
                        if "papier" in lower or "paper" in lower:
                            return "PAPIER LEER!"
                        elif "tintenkassette" in lower or "ink" in lower:
                            return "KASSETTE LEER!"
                        elif "kassette" in lower or "cartridge" in lower:
                            return "KASSETTE FALSCH!"
                        elif "jam" in lower or "stau" in lower:
                            return "PAPIERSTAU!"
                        elif "cover" in lower or "door" in lower or "klappe" in lower:
                            return "KLAPPE OFFEN!"
                        else:
                            short = status_text[:20]
                            return f"FEHLER: {short}"

                    if job_status & JOB_STATUS_PAPEROUT:
                        return "PAPIER/KASSETTE LEER!"
                    elif job_status & JOB_STATUS_USER_INTERVENTION:
                        return "DRUCKER PRÜFEN!"
                    elif job_status & JOB_STATUS_BLOCKED:
                        return "DRUCK BLOCKIERT!"
                    elif job_status & JOB_STATUS_OFFLINE:
                        return "DRUCKER OFFLINE!"
                    elif job_status & JOB_STATUS_ERROR:
                        return "DRUCK-FEHLER!"
            finally:
                win32print.ClosePrinter(hPrinter)

        except Exception as e:
            logger.debug(f"Job-Check Fehler: {e}")

        return None

    def _detect_canon_error_window(self) -> Optional[str]:
        """Erkennt Canon-Treiber-Fehlerfenster via EnumWindows.

        Sucht SOWOHL sichtbare ALS AUCH versteckte (SW_HIDE) Canon-Fenster,
        da wir sie beim Overlay per SW_HIDE verstecken.
        Verwendet WM_GETTEXT statt GetWindowTextW für Child-Controls.
        """
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            WM_GETTEXT = 0x000D
            WM_GETTEXTLENGTH = 0x000E
            WNDENUMPROC = ctypes.WINFUNCTYPE(
                wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
            )

            found_texts = []

            def _read_child_text(hwnd, lParam):
                """Liest Text aus Child-Controls via WM_GETTEXT"""
                try:
                    length = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
                    if length > 5:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.SendMessageW(hwnd, WM_GETTEXT, length + 1, buf)
                        text = buf.value.strip()
                        if text and len(text) > 5:
                            found_texts.append(text)

                    if not found_texts:
                        length2 = user32.GetWindowTextLengthW(hwnd)
                        if length2 > 5:
                            buf2 = ctypes.create_unicode_buffer(length2 + 1)
                            user32.GetWindowTextW(hwnd, buf2, length2 + 1)
                            text2 = buf2.value.strip()
                            if text2 and len(text2) > 5 and text2 not in found_texts:
                                found_texts.append(text2)
                except Exception:
                    pass
                return True

            child_proc = WNDENUMPROC(_read_child_text)
            found_window_info = [None, False]  # [title, is_hidden]

            def _find_canon_window(hwnd, lParam):
                # Prüfe ALLE Fenster (sichtbar UND versteckt)
                title_buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title_buf, 256)
                title = title_buf.value.lower()
                if "canon selphy" in title or "canon cp" in title:
                    is_visible = bool(user32.IsWindowVisible(hwnd))
                    found_window_info[0] = title_buf.value
                    found_window_info[1] = not is_visible  # hidden flag
                    user32.EnumChildWindows(hwnd, child_proc, 0)
                    return False
                return True

            enum_proc = WNDENUMPROC(_find_canon_window)
            user32.EnumWindows(enum_proc, 0)

            if found_window_info[0]:
                hidden_str = " (versteckt)" if found_window_info[1] else ""
                logger.info(
                    f"Canon-Dialog{hidden_str}: title='{found_window_info[0]}', "
                    f"child_texts={found_texts}"
                )

                if found_texts:
                    best_text = max(found_texts, key=len)
                    error_lower = best_text.lower()

                    if "kein papier" in error_lower:
                        return "KEIN PAPIER / KASSETTE!"
                    elif "papier" in error_lower and "kassette" in error_lower:
                        return "KEIN PAPIER / KASSETTE!"
                    elif "tintenkassette" in error_lower or "druckerpatrone" in error_lower:
                        return "KEINE TINTENKASSETTE!"
                    elif "kassette" in error_lower:
                        return "KASSETTE PRÜFEN!"
                    elif "tinte" in error_lower or "ink" in error_lower:
                        return "TINTE LEER!"
                    elif "stau" in error_lower or "jam" in error_lower:
                        return "PAPIERSTAU!"
                    elif "papier" in error_lower:
                        return "PAPIER LEER!"
                    else:
                        upper = best_text.upper()
                        mapped = upper[:30] if len(upper) > 30 else upper
                        logger.info(f"Canon-Dialog unbekannter Text → '{mapped}'")
                        return mapped
                else:
                    logger.warning(
                        "Canon-Dialog vorhanden aber Text nicht lesbar! "
                        "Behandle als KEIN PAPIER / KASSETTE"
                    )
                    return "KEIN PAPIER / KASSETTE!"

        except Exception as e:
            logger.error(f"Canon-Fenster-Erkennung Fehler: {e}", exc_info=True)

        return None

    # ========== Canon-Dialog-Unterdrückung ==========

    def hide_canon_dialogs(self):
        """Versteckt Canon/SELPHY Drucker-Dialoge per SW_HIDE.

        SW_HIDE macht den Dialog unsichtbar OHNE ihn zu schließen.
        Dadurch erstellt der Canon-Treiber keinen neuen Dialog.
        Der Dialog existiert weiterhin (nur unsichtbar).
        """
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            SW_HIDE = 0
            WNDENUMPROC = ctypes.WINFUNCTYPE(
                wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
            )

            keywords = ["canon selphy", "canon cp", "druckerstatus", "printer status"]
            hidden_count = [0]

            def enum_callback(hwnd, lParam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                title_buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title_buf, 256)
                title = title_buf.value.lower()
                if title and any(kw in title for kw in keywords):
                    user32.ShowWindow(hwnd, SW_HIDE)
                    hidden_count[0] += 1
                    logger.info(f"Canon-Dialog versteckt (SW_HIDE): '{title_buf.value}'")
                return True

            proc = WNDENUMPROC(enum_callback)
            user32.EnumWindows(proc, 0)
            return hidden_count[0] > 0

        except Exception as e:
            logger.debug(f"Dialog-Verstecken fehlgeschlagen: {e}")
            return False

    def close_canon_dialogs(self):
        """Schließt Canon/SELPHY Drucker-Dialoge per WM_CLOSE.

        Findet sowohl sichtbare als auch versteckte (SW_HIDE) Fenster.
        Nur verwenden wenn kein Overlay aktiv ist!
        """
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
                # Alle Fenster prüfen (sichtbar UND versteckt)
                title_buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title_buf, 256)
                title = title_buf.value.lower()
                if title and any(kw in title for kw in keywords):
                    # Versteckte erst sichtbar machen, dann schließen
                    if not user32.IsWindowVisible(hwnd):
                        user32.ShowWindow(hwnd, SW_SHOW)
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                    logger.info(f"Canon-Dialog geschlossen (WM_CLOSE): '{title_buf.value}'")
                return True

            proc = WNDENUMPROC(enum_callback)
            user32.EnumWindows(proc, 0)

        except Exception as e:
            logger.debug(f"Dialog-Schließen fehlgeschlagen: {e}")

    # ========== Drucker-Reset ==========

    def reset_printer(self, on_step: Optional[Callable] = None,
                      on_done: Optional[Callable] = None):
        """Startet Drucker-Reset im Hintergrund (3-stufige Eskalation).

        Args:
            on_step: Callback(step_text) für Fortschritts-Updates
            on_done: Callback(success, message) wenn fertig
        """
        if self._reset_in_progress:
            logger.warning("Reset bereits aktiv")
            return

        def _do_reset():
            self._reset_in_progress = True
            success = False
            message = "Reset fehlgeschlagen"

            try:
                # ALLE 3 Stufen immer durchlaufen!
                # Der SELPHY setzt keine Spooler-Status-Flags, deshalb kann
                # get_error() nach Purge fälschlich "OK" melden.

                # Schritt 1: Jobs purgen
                logger.info("Reset Schritt 1/3: Jobs purgen")
                if on_step:
                    on_step("Schritt 1/3: Druckaufträge löschen...")
                self._step1_purge_jobs()
                time.sleep(2)

                # Schritt 2: Spooler neustarten
                logger.info("Reset Schritt 2/3: Spooler neustarten")
                if on_step:
                    on_step("Schritt 2/3: Druckdienst neu starten...")
                self._step2_restart_spooler()
                time.sleep(4)

                # Schritt 3: USB-Gerät neustarten
                logger.info("Reset Schritt 3/3: USB-Device neustarten")
                if on_step:
                    on_step("Schritt 3/3: USB-Verbindung zurücksetzen...")
                self._step3_restart_usb_device()
                time.sleep(5)

                # Canon-Dialoge schließen die nach Reset erscheinen können
                if on_step:
                    on_step("Drucker-Status wird geprüft...")
                self.close_canon_dialogs()
                time.sleep(3)

                # Finale Prüfung
                error = self.get_error()
                if not error:
                    success = True
                    message = "Drucker bereit (Reset komplett)"
                    logger.info("Reset komplett → Drucker OK")
                else:
                    message = f"Drucker meldet noch: {error}"
                    logger.warning(f"Reset komplett → Fehler bleibt: {error}")

            except Exception as e:
                logger.error(f"Reset-Fehler: {e}", exc_info=True)
                message = f"Reset-Fehler: {e}"
            finally:
                self._reset_in_progress = False
                if on_done:
                    on_done(success, message)

        thread = threading.Thread(target=_do_reset, daemon=True)
        thread.start()

    def _step1_purge_jobs(self) -> bool:
        """Schritt 1: Alle Druckaufträge löschen"""
        try:
            import win32print

            printer_name = self.printer_name or win32print.GetDefaultPrinter()
            if not printer_name:
                return False

            h = win32print.OpenPrinter(printer_name)
            try:
                win32print.SetPrinter(h, 0, None, 3)  # PRINTER_CONTROL_PURGE
                win32print.SetPrinter(h, 0, None, 1)  # PRINTER_CONTROL_PAUSE
                time.sleep(1)
                win32print.SetPrinter(h, 0, None, 2)  # PRINTER_CONTROL_RESUME
                logger.info("Drucker-Jobs gepurged")
                return True
            finally:
                win32print.ClosePrinter(h)

        except Exception as e:
            logger.warning(f"Purge fehlgeschlagen: {e}")
            return False

    def _step2_restart_spooler(self):
        """Schritt 2: Windows Print Spooler neustarten"""
        try:
            import os
            import glob

            # CREATE_NO_WINDOW verhindert sichtbare Konsolenfenster
            CREATE_NO_WINDOW = 0x08000000

            subprocess.run(["net", "stop", "spooler"],
                           capture_output=True, timeout=15,
                           creationflags=CREATE_NO_WINDOW)

            # Spool-Dateien löschen
            spool_dir = os.path.join(
                os.environ.get('SystemRoot', 'C:\\Windows'),
                'System32', 'spool', 'PRINTERS'
            )
            for f in glob.glob(os.path.join(spool_dir, '*')):
                try:
                    os.remove(f)
                except OSError:
                    pass

            time.sleep(2)
            subprocess.run(["net", "start", "spooler"],
                           capture_output=True, timeout=15,
                           creationflags=CREATE_NO_WINDOW)
            logger.info("Spooler neugestartet")

        except Exception as e:
            logger.warning(f"Spooler-Restart fehlgeschlagen: {e}")

    def _step3_restart_usb_device(self):
        """Schritt 3: USB-Gerät per Disable/Enable-PnpDevice neustarten.

        Entspricht USB aus- und wieder einstecken. Aggressiver als pnputil.
        Sucht breit nach Canon-Druckern (nicht nur 'SELPHY' im Namen).
        """
        CREATE_NO_WINDOW = 0x08000000

        try:
            # Zuerst: Welche PnP-Geräte gibt es mit 'Canon'?
            # Das hilft beim Debugging wenn das Gerät nicht gefunden wird
            diag = subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                 "-Command",
                 "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                 "Get-PnpDevice | Where-Object {"
                 "$_.FriendlyName -like '*Canon*' -or "
                 "$_.FriendlyName -like '*SELPHY*' -or "
                 "$_.FriendlyName -like '*CP1000*' -or "
                 "$_.FriendlyName -like '*CP1500*'} | "
                 "Select-Object -Property InstanceId, FriendlyName, Status, Class "
                 "| Format-List"],
                capture_output=True, timeout=15, encoding="utf-8", errors="replace",
                creationflags=CREATE_NO_WINDOW
            )
            logger.info(f"PnP-Geräte mit 'Canon':\n{diag.stdout.strip()}")
            if diag.stderr.strip():
                logger.warning(f"PnP-Diagnose stderr: {diag.stderr.strip()}")

            # Jetzt: Disable + Enable für Canon-Drucker (= echtes USB aus/ein)
            # Sucht nach Class='Printer' UND Canon im Namen
            result = subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                 "-Command",
                 "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                 "$dev = Get-PnpDevice | Where-Object {"
                 "($_.FriendlyName -like '*Canon*' -or "
                 "$_.FriendlyName -like '*SELPHY*' -or "
                 "$_.FriendlyName -like '*CP1000*') -and "
                 "$_.Class -eq 'Printer'}; "
                 "if ($dev) { "
                 "  foreach ($d in $dev) { "
                 "    Write-Output \"Disabling: $($d.FriendlyName) [$($d.InstanceId)]\"; "
                 "    Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction SilentlyContinue; "
                 "  }; "
                 "  Start-Sleep -Seconds 3; "
                 "  foreach ($d in $dev) { "
                 "    Write-Output \"Enabling: $($d.FriendlyName) [$($d.InstanceId)]\"; "
                 "    Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction SilentlyContinue; "
                 "  }; "
                 "  Write-Output 'USB-Reset durchgeführt'; "
                 "} else { "
                 "  Write-Output 'WARNUNG: Kein Canon-Drucker als PnP-Gerät gefunden!'; "
                 "}"],
                capture_output=True, timeout=30, encoding="utf-8", errors="replace",
                creationflags=CREATE_NO_WINDOW
            )
            output = result.stdout.strip()
            logger.info(f"USB-Device Reset:\n{output}")
            if result.stderr.strip():
                logger.warning(f"USB-Reset stderr: {result.stderr.strip()}")

            if "Kein Canon-Drucker" in output:
                logger.warning(
                    "Canon-Drucker nicht als PnP-Gerät gefunden! "
                    "Fallback: pnputil /restart-device"
                )
                # Fallback: pnputil mit breiterer Suche
                subprocess.run(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                     "-Command",
                     "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                     "Get-PnpDevice | Where-Object {"
                     "$_.FriendlyName -like '*Canon*'} | "
                     "ForEach-Object { "
                     "  Write-Output \"pnputil restart: $($_.FriendlyName)\"; "
                     "  pnputil /restart-device $_.InstanceId "
                     "}"],
                    capture_output=True, timeout=30, encoding="utf-8", errors="replace",
                    creationflags=CREATE_NO_WINDOW
                )

        except Exception as e:
            logger.warning(f"USB-Restart fehlgeschlagen: {e}")


# Singleton
_instance: Optional[PrinterController] = None


def get_printer_controller() -> PrinterController:
    global _instance
    if _instance is None:
        _instance = PrinterController()
    return _instance
