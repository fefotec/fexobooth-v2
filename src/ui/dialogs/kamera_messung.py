"""Kamera-Messung als fester Bestandteil der Software.

Bisher lief die Messung nur ueber `fexobooth.exe --kamera-test` bzw. die Datei
`Kamera-Messung-starten.bat`. Das setzte voraus, dass jemand die Fotobox-Software
vorher beendet — auf einer Box im Feld ist das umstaendlich und fehleranfaellig.
Dieser Dialog macht daraus einen Knopf im Admin-Menue (Tab "Kamera").

WARUM EIN EIGENER PROZESS UND KEIN THREAD (Feldbefund Box, 20.08.2026)
---------------------------------------------------------------------
Die erste Fassung startete die Messung als Hintergrund-THREAD innerhalb der
laufenden App. Ergebnis auf der Box: Die komplette Software fror ein, liess sich
nicht mehr schliessen und musste hart ausgeschaltet werden. Das Log endet exakt
nach der letzten Zeile vor dem ersten Kamerazugriff der Messung:

    09:12:15.454 | Kamera freigegeben
    09:12:15.454 | Kamera-Messung: Kamera der App freigegeben
    << danach nichts mehr, auch kein Absturz-Eintrag >>

Ursachen — beide treffen zu und beide sind im Thread-Entwurf unvermeidbar:
  * Ein minutenlanger OpenCV-Kamerazugriff blockiert den Python-Prozess so, dass
    die Tk-Oberflaeche nicht mehr drankommt.
  * Die Messung haelt die gemeinsame Kamera-Sperre (`camera_hardware_lock`) ueber
    ihre ganze Laufzeit. Jeder andere Kamerazugriff der App wartet dann minutenlang.
Als Einzelprogramm (`--kamera-test`) faellt beides nicht auf, weil dort keine
Oberflaeche mitlaeuft — deshalb war der Fehler vorher unsichtbar.

Deshalb startet dieser Dialog die Messung jetzt als **eigenen Windows-Prozess** —
technisch derselbe Weg wie `Kamera-Messung-starten.bat`, nur ohne dass jemand die
Software vorher beenden muss. Das bringt drei Dinge:

  * Eigener Prozess = eigener Python-Interpreter und eigene Sperren. Die
    Oberflaeche der Fotobox-Software bleibt bedienbar, egal wie lange die
    Messung braucht.
  * **Abbrechen ist moeglich.** Ein blockierter OpenCV-Aufruf laesst sich
    innerhalb eines Prozesses nicht abbrechen — ein Prozess dagegen schon.
  * Die Messung laeuft in genau dem Modus, der auf der Box erprobt ist.

Die Kamera der App wird vorher freigegeben (sonst ist sie belegt) und danach
wieder bereitgestellt.
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

import customtkinter as ctk

from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Windows: Prozess ohne aufblitzendes Konsolenfenster starten
_CREATE_NO_WINDOW = 0x08000000

# Takt der Fortschrittsanzeige. Bewusst gemuetlich: poll() und ein Blick auf die
# Dateigroesse sind billig, aber die Box ist schwache Hardware.
_TAKT_MS = 500

# Notbremse. Laeuft die Messung laenger, stimmt etwas nicht — dann wird der
# Kindprozess beendet, damit er nicht dauerhaft die Kamera belegt.
_HOECHSTDAUER_S = 15 * 60


def _berichts_pfade() -> List[Path]:
    """Alle Orte, an denen der Messbericht landen kann (wie in Bericht.speichern)."""
    pfade: List[Path] = []
    try:
        from src.utils.logging import LOG_PATH
        pfade.append(Path(LOG_PATH) / "kamera-messung.txt")
    except Exception:
        pass
    pfade.append(Path(r"C:\ProgramData\FexoBox") / "kamera-messung.txt")
    return pfade


def _mess_befehl(kamera_index: int) -> Tuple[List[str], Optional[str]]:
    """Kommandozeile fuer den Messvorgang als eigenen Prozess.

    Returns:
        (Befehl, Arbeitsverzeichnis)
    """
    if getattr(sys, "frozen", False):
        # PyInstaller-Build: sys.executable IST die fexobooth.exe.
        # Exakt der Aufruf, den auch Kamera-Messung-starten.bat verwendet.
        return (
            [sys.executable, "--kamera-test", "--kamera-index", str(kamera_index)],
            str(Path(sys.executable).parent),
        )

    # Entwicklung: python src/main.py --kamera-test
    # Pfad aus dieser Datei ableiten (src/ui/dialogs/ -> src/main.py), damit
    # main.py nicht ein zweites Mal importiert werden muss.
    hier = Path(__file__).resolve()
    return (
        [sys.executable, str(hier.parents[2] / "main.py"),
         "--kamera-test", "--kamera-index", str(kamera_index)],
        str(hier.parents[3]),
    )


class KameraMessungDialog(ctk.CTkToplevel):
    """Startet die Kamera-Messung als eigenen Prozess und zeigt den Fortschritt."""

    def __init__(self, parent, app=None, kamera_index: int = 0):
        super().__init__(parent)

        self.parent_window = parent
        self.app = app
        self.kamera_index = kamera_index
        self.bericht_pfad: Optional[str] = None

        self._prozess: Optional[subprocess.Popen] = None
        self._start_zeit: float = 0.0
        self._takt_job = None
        self._kamera_freigegeben = False
        self._balken_zeigt_schritte = False

        self.title("Kamera-Messung")
        self.configure(fg_color="#0a0a10")

        # Modal + immer sichtbar (wie die anderen Dialoge im Kiosk-Modus)
        self.transient(parent)
        self.grab_set()
        self.overrideredirect(True)
        self.update_idletasks()
        self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()

        self._baue_oberflaeche()

    # ------------------------------------------------------------------
    # Oberflaeche
    # ------------------------------------------------------------------

    def _baue_oberflaeche(self):
        karte = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=16,
        )
        karte.place(relx=0.5, rely=0.5, anchor="center")

        innen = ctk.CTkFrame(karte, fg_color="transparent")
        innen.pack(padx=40, pady=30)

        ctk.CTkLabel(
            innen,
            text="📷  Kamera-Messung",
            font=("Segoe UI", 22, "bold"),
            text_color=COLORS["text_primary"],
        ).pack(pady=(0, 12))

        ctk.CTkLabel(
            innen,
            text=(
                "Die Messung prüft, wie schnell die Kamera bei verschiedenen\n"
                "Auflösungen arbeitet. Das Ergebnis wird als Textdatei gespeichert.\n\n"
                "Sie läuft als eigenes Programm — diese Oberfläche bleibt bedienbar\n"
                "und du kannst jederzeit abbrechen.\n\n"
                "Solange die Messung läuft, ist die Kamera belegt:\n"
                "Es kann keine Foto-Session gestartet werden."
            ),
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            justify="center",
        ).pack(pady=(0, 18))

        self.status_label = ctk.CTkLabel(
            innen,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            justify="center",
        )
        self.status_label.pack(pady=(0, 8))

        self.balken = ctk.CTkProgressBar(innen, width=420, mode="indeterminate")

        leiste = ctk.CTkFrame(innen, fg_color="transparent")
        leiste.pack(pady=(12, 0))

        self.start_btn = ctk.CTkButton(
            leiste,
            text="Messung starten",
            font=FONTS["body"],
            width=180,
            height=44,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            corner_radius=SIZES["corner_radius"],
            command=self._starten,
        )
        self.start_btn.pack(side="left")

        self.abbrechen_btn = ctk.CTkButton(
            leiste,
            text="Messung abbrechen",
            font=FONTS["body"],
            width=190,
            height=44,
            fg_color="#cc0000",
            hover_color="#990000",
            text_color="#ffffff",
            corner_radius=SIZES["corner_radius"],
            command=self._abbrechen,
        )
        # erscheint nur, waehrend die Messung laeuft

        self.schliessen_btn = ctk.CTkButton(
            leiste,
            text="Schließen",
            font=FONTS["body"],
            width=140,
            height=44,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            corner_radius=SIZES["corner_radius"],
            command=self._schliessen,
        )
        self.schliessen_btn.pack(side="left", padx=(12, 0))

        self.oeffnen_btn = ctk.CTkButton(
            leiste,
            text="Bericht öffnen",
            font=FONTS["body"],
            width=170,
            height=44,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            corner_radius=SIZES["corner_radius"],
            command=self._bericht_oeffnen,
        )
        # erscheint erst, wenn ein Bericht existiert

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def _starten(self):
        if self._prozess is not None:
            return

        self.start_btn.pack_forget()
        self.schliessen_btn.pack_forget()
        try:
            self.oeffnen_btn.pack_forget()
        except Exception:
            pass
        self.abbrechen_btn.pack(side="left")
        # Bis der erste Schritt im Bericht steht, kann nur "es lebt" angezeigt
        # werden — sobald "Schritt X von Y" dasteht, wird daraus ein echter
        # Fortschrittsbalken (siehe _fortschritt_setzen).
        self._balken_zurueck_auf_unbestimmt()
        self.balken.pack(pady=(4, 10))
        self.balken.start()
        self._status("Kamera wird freigegeben...")

        # Kamera der App freigeben — sonst ist sie fuer den Messprozess belegt.
        self._kamera_freigeben()

        # Alten Bericht wegraeumen: Sein Auftauchen ist unser "fertig"-Signal.
        for pfad in _berichts_pfade():
            try:
                if pfad.is_file():
                    pfad.unlink()
            except Exception as e:
                logger.debug(f"Alter Messbericht nicht loeschbar ({pfad}): {e}")

        befehl, arbeitsverzeichnis = _mess_befehl(self.kamera_index)
        logger.info(f"Kamera-Messung startet als eigener Prozess: {befehl}")

        try:
            self._prozess = subprocess.Popen(
                befehl,
                cwd=arbeitsverzeichnis,
                creationflags=_CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.exception(f"Messprozess liess sich nicht starten: {e}")
            self._abschluss_anzeigen(
                "Die Messung ließ sich nicht starten.\n"
                f"{str(e)[:140]}\n\n"
                "Bitte den Ordner C:\\FexoBooth\\logs mitschicken."
            )
            return

        self._start_zeit = time.time()
        self._takt()

    def _kamera_freigeben(self):
        if self.app is None or self._kamera_freigegeben:
            return
        try:
            self.app.camera_manager.release()
            self._kamera_freigegeben = True
            logger.info("Kamera-Messung: Kamera der App freigegeben")
        except Exception as e:
            logger.warning(f"Kamera-Messung: release() fehlgeschlagen: {e}")

    # ------------------------------------------------------------------
    # Fortschritt — laeuft im UI-Thread und ist absichtlich sehr billig
    # ------------------------------------------------------------------

    def _takt(self):
        self._takt_job = None
        if self._prozess is None:
            return

        laeuft_seit = time.time() - self._start_zeit
        rueckgabe = self._prozess.poll()

        if rueckgabe is None:
            if laeuft_seit > _HOECHSTDAUER_S:
                logger.warning(
                    f"Kamera-Messung laeuft laenger als {_HOECHSTDAUER_S // 60} "
                    "Minuten — wird beendet"
                )
                self._prozess_beenden()
                self._prozess = None
                self._abschluss_anzeigen(
                    f"Die Messung wurde nach {_HOECHSTDAUER_S // 60} Minuten "
                    "abgebrochen,\nweil sie nicht mehr weiterkam.\n\n"
                    "Bitte den Ordner C:\\FexoBooth\\logs mitschicken."
                )
                return

            self._status(
                f"Messung läuft seit {self._dauer_text(laeuft_seit)}.\n"
                f"{self._fortschritt_text()}\n\n"
                "Das darf einige Minuten dauern."
            )
            self._takt_job = self.after(_TAKT_MS, self._takt)
            return

        # Prozess ist fertig
        self._prozess = None
        pfad = self._bericht_suchen()
        if pfad:
            self.bericht_pfad = pfad
            logger.info(f"Kamera-Messung fertig nach {laeuft_seit:.0f}s: {pfad}")
            self._abschluss_anzeigen(
                f"Fertig nach {self._dauer_text(laeuft_seit)}!\n"
                f"Der Bericht wurde gespeichert:\n{pfad}\n\n"
                "Bitte diese Datei an Claude schicken.",
                bericht_vorhanden=True,
            )
        else:
            logger.warning(
                f"Kamera-Messung endete mit Code {rueckgabe}, aber ohne Bericht"
            )
            self._abschluss_anzeigen(
                "Die Messung ist beendet, hat aber keinen Bericht geschrieben.\n"
                f"(Rückmeldung des Programms: {rueckgabe})\n\n"
                "Bitte den Ordner C:\\FexoBooth\\logs mitschicken —\n"
                "in absturz.log steht dann, woran es lag."
            )

    def _fortschritt_text(self) -> str:
        """Echter Fortschritt aus dem Kopf der laufenden Berichtsdatei.

        Der Messprozess schreibt den Bericht seit 2.4.35 nach JEDEM Schritt neu
        und stellt ihm einen Statuskopf voran ("Fortschritt : Schritt 4 von 11",
        "Aktueller Schritt: ..."). Das hier ist genau derselbe Blick, den auch
        ein Mensch per Doppelklick auf die Datei haette — nur automatisch.
        Gelesen werden nur die ersten paar hundert Zeichen: Der Takt laeuft
        zweimal pro Sekunde und die Box ist schwache Hardware.
        """
        kopf = self._kopf_lesen()
        schritt = kopf.get("schritt")
        aktuell = kopf.get("aktuell")

        if schritt:
            nummer, gesamt = schritt
            self._fortschritt_setzen(nummer, gesamt)
            text = f"Schritt {nummer} von {gesamt}"
            if aktuell and aktuell != "-":
                text += f": {aktuell}"
            return text

        if kopf.get("vorhanden"):
            return "Der Bericht wird geschrieben."
        return "Die Kamera wird geöffnet und mehrfach umgestellt."

    def _kopf_lesen(self) -> dict:
        """Statuskopf der Berichtsdatei auslesen (best effort, nie werfend).

        Die Datei wird vom Messprozess atomar ersetzt (.tmp + os.replace) — sie
        ist also nie halb beschrieben. Trotzdem kann der Zugriff genau im
        Moment des Ersetzens scheitern; das ist harmlos, dann eben beim
        naechsten Takt.
        """
        ergebnis: dict = {"vorhanden": False}
        for pfad in _berichts_pfade():
            try:
                if not pfad.is_file() or pfad.stat().st_size <= 0:
                    continue
                with open(pfad, "r", encoding="utf-8", errors="replace") as f:
                    kopf = f.read(600)
            except Exception:
                continue

            ergebnis["vorhanden"] = True
            for zeile in kopf.splitlines():
                if zeile.startswith("Fortschritt"):
                    teile = zeile.split("Schritt")
                    if len(teile) > 1:
                        zahlen = teile[-1].split("von")
                        try:
                            ergebnis["schritt"] = (int(zahlen[0].strip()),
                                                   int(zahlen[1].strip()))
                        except Exception:
                            pass
                elif zeile.startswith("Aktueller Schritt"):
                    # Der "(begonnen 00:01:58)"-Anhang steht in der Datei fuer
                    # den Menschen; hier waere er nur Laerm, die Laufzeit steht
                    # eine Zeile darueber schon in der Statusanzeige.
                    aktuell = zeile.split(":", 1)[-1].strip()
                    ergebnis["aktuell"] = aktuell.split(" (begonnen")[0].strip()
            return ergebnis
        return ergebnis

    def _fortschritt_setzen(self, nummer: int, gesamt: int):
        """Aus der Animation einen echten Balken machen, sobald es Zahlen gibt."""
        if gesamt <= 0:
            return
        try:
            if not self._balken_zeigt_schritte:
                self.balken.stop()
                self.balken.configure(mode="determinate")
                self._balken_zeigt_schritte = True
            self.balken.set(min(1.0, max(0.0, nummer / float(gesamt))))
        except Exception:
            pass

    def _balken_zurueck_auf_unbestimmt(self):
        """Vor jedem Start: wieder Animation, bis der erste Schritt gemeldet ist."""
        self._balken_zeigt_schritte = False
        try:
            self.balken.configure(mode="indeterminate")
            self.balken.set(0)
        except Exception:
            pass

    @staticmethod
    def _dauer_text(sekunden: float) -> str:
        m, s = divmod(int(sekunden), 60)
        return f"{m}:{s:02d} Minuten" if m else f"{s} Sekunden"

    def _bericht_suchen(self) -> Optional[str]:
        for pfad in _berichts_pfade():
            try:
                if pfad.is_file() and pfad.stat().st_size > 0:
                    return str(pfad)
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Abbrechen / Abschluss
    # ------------------------------------------------------------------

    def _abbrechen(self):
        if self._prozess is None:
            return
        logger.info("Kamera-Messung: vom Benutzer abgebrochen")
        self._prozess_beenden()
        self._prozess = None

        pfad = self._bericht_suchen()
        if pfad:
            self.bericht_pfad = pfad
            self._abschluss_anzeigen(
                f"Abgebrochen. Ein Teilergebnis wurde gefunden:\n{pfad}",
                bericht_vorhanden=True,
            )
        else:
            self._abschluss_anzeigen(
                "Abgebrochen. Es wurde noch kein Bericht geschrieben."
            )

    def _prozess_beenden(self):
        """Messprozess sicher beenden — sonst belegt er weiter die Kamera."""
        if self._takt_job is not None:
            try:
                self.after_cancel(self._takt_job)
            except Exception:
                pass
            self._takt_job = None

        prozess = self._prozess
        if prozess is None:
            return
        try:
            prozess.terminate()
            try:
                prozess.wait(timeout=3)
            except Exception:
                # Reagiert nicht — haengt vermutlich in einem Kamera-Aufruf.
                # Genau dafuer ist der eigene Prozess da: hart beenden geht.
                prozess.kill()
                try:
                    prozess.wait(timeout=3)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Messprozess liess sich nicht beenden: {e}")

    def _abschluss_anzeigen(self, text: str, bericht_vorhanden: bool = False):
        try:
            self.balken.stop()
            self.balken.pack_forget()
        except Exception:
            pass
        try:
            self.abbrechen_btn.pack_forget()
        except Exception:
            pass

        self.start_btn.configure(text="Messung wiederholen")
        self.start_btn.pack(side="left")
        self.schliessen_btn.pack(side="left", padx=(12, 0))
        if bericht_vorhanden:
            self.oeffnen_btn.pack(side="left", padx=(12, 0))

        self._status(text)

    def _bericht_oeffnen(self):
        if not self.bericht_pfad or not os.path.isfile(self.bericht_pfad):
            return
        try:
            subprocess.Popen(
                ["notepad.exe", self.bericht_pfad],
                creationflags=_CREATE_NO_WINDOW,
            )
        except Exception as e:
            logger.warning(f"Bericht konnte nicht geoeffnet werden: {e}")

    # ------------------------------------------------------------------
    # Schliessen
    # ------------------------------------------------------------------

    def _schliessen(self):
        # Laeuft noch etwas, wird es beendet — ein weiterlaufender Messprozess
        # wuerde sonst dauerhaft die Kamera belegen und jede Session blockieren.
        if self._prozess is not None:
            self._prozess_beenden()
            self._prozess = None

        # Kamera wieder bereitstellen. `_pre_init_camera()` nimmt die richtigen
        # Werte aus der Config und macht nichts, wenn die Kamera schon offen ist.
        # Klappt es nicht, ist das unkritisch: Der Session-Start initialisiert
        # die Kamera ohnehin selbst, wenn sie nicht bereit ist (session.py).
        if self.app is not None and self._kamera_freigegeben:
            try:
                self.app._pre_init_camera()
                logger.info("Kamera-Messung: Kamera wieder bereitgestellt")
            except Exception as e:
                logger.warning(
                    f"Kamera-Messung: Kamera nicht neu geöffnet ({e}) — "
                    "der nächste Session-Start holt das nach"
                )

        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

        # Modalen Grab an den Admin-Dialog zurueckgeben. Ohne das bleibt der
        # Grab nach dem Schliessen bei niemandem haengen und der Admin-Dialog
        # reagiert nicht mehr zuverlaessig auf Klicks (gleiches Muster wie der
        # grab_release-Fix in AdminDialog.destroy).
        try:
            if self.parent_window.winfo_exists():
                self.parent_window.grab_set()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Hilfsmittel
    # ------------------------------------------------------------------

    def _status(self, text: str):
        try:
            self.status_label.configure(text=text)
        except Exception:
            pass
