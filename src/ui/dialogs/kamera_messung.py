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
import threading
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
# 2.4.37 von 500 auf 1000 ms: Der Takt liest jedes Mal den Kopf der
# Berichtsdatei und zeichnet den Balken neu — parallel zur laufenden Messung auf
# einem 2-Kern-Atom. Zweimal pro Sekunde war dafuer zu oft; einmal pro Sekunde
# fuehlt sich genauso lebendig an und kostet die Haelfte.
_TAKT_MS = 1000

# Notbremse. Laeuft die Messung laenger, stimmt etwas nicht — dann wird der
# Kindprozess beendet, damit er nicht dauerhaft die Kamera belegt.
_HOECHSTDAUER_S = 15 * 60

# Warten auf die laufende Kamera-Pruefung der App, bevor die Messung startet.
# 60 x 500 ms = 30 s. Klingt lang, ist aber gemessen: Auf der Box vom 20.08.2026
# brauchte eine einzige Pruefung ueber 10 s, weil die PowerShell-Kamerasuche in
# ihre Zeitgrenzen lief (10 s DirectShow-Enumeration + 5 s PnP, teils mehrfach).
# Mit den frueheren 3 s startete die Messung mitten hinein und maass nichts.
_WARTEN_AUF_KAMERA_MS = 500
_WARTEN_AUF_KAMERA_TAKTE = 60

# Ruhezeit nach dem Beenden des Messprozesses, bevor die App die Kamera wieder
# oeffnet. Windows gibt den USB-Geraetehandle erst mit dem Prozessende frei;
# sofort danach zu oeffnen kostet auf dem Miix mehrere Sekunden Fehlversuch.
_KAMERA_RUHE_MS = 1500


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
    # `--aus-dialog` ist reine Buchfuehrung: Der Messprozess schreibt daraufhin
    # "Gestartet: Admin-Knopf ..." in den Bericht. Das ist wichtig, weil hier
    # die komplette Fotobox-Software waehrend der Messung weiterlaeuft und auf
    # dem Atom-Tablet Bilder/s kostet — ein Bericht von hier ist mit einem
    # Bericht aus der BAT nicht vergleichbar, und ohne diese Zeile sieht man
    # den Unterschied nicht.
    if getattr(sys, "frozen", False):
        # PyInstaller-Build: sys.executable IST die fexobooth.exe.
        # Exakt der Aufruf, den auch Kamera-Messung-starten.bat verwendet.
        return (
            [sys.executable, "--kamera-test",
             "--kamera-index", str(kamera_index), "--aus-dialog"],
            str(Path(sys.executable).parent),
        )

    # Entwicklung: python src/main.py --kamera-test
    # Pfad aus dieser Datei ableiten (src/ui/dialogs/ -> src/main.py), damit
    # main.py nicht ein zweites Mal importiert werden muss.
    hier = Path(__file__).resolve()
    return (
        [sys.executable, str(hier.parents[2] / "main.py"),
         "--kamera-test", "--kamera-index", str(kamera_index), "--aus-dialog"],
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
        # Start ist gewuenscht, aber der Prozess laeuft noch nicht (siehe
        # _warten_auf_freie_kamera). In diesem Fenster muss "Abbrechen"
        # trotzdem greifen — sonst startet die Messung nach dem Abbrechen doch.
        self._start_gewuenscht = False

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

        # Kamera-Waechter der App SOFORT pausieren, nicht erst beim Start.
        # Die App prueft bei sichtbarer Kamera-Warnung alle 2 s und braucht auf
        # dieser Hardware ueber 10 s pro Pruefung — sie waere also faktisch
        # dauernd an der Kamera. Wer den Dialog oeffnet, will messen; ab jetzt
        # startet keine neue Pruefung mehr und die laufende kann auslaufen,
        # waehrend der Bediener noch den Text liest.
        self._messung_flag(True)

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
                "Es kann keine Foto-Session gestartet werden.\n\n"
                "Hinweis: Hier läuft die Fotobox-Software nebenher mit und\n"
                "kostet etwas Leistung. Für den genauesten Wert die Datei\n"
                "„Kamera-Messung-starten.bat\" verwenden."
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
        if self._prozess is not None or self._start_gewuenscht:
            return
        self._start_gewuenscht = True

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

        # ZUERST den Kamera-Waechter der App stilllegen, DANN die Kamera
        # freigeben — nicht umgekehrt (siehe _messung_flag).
        self._messung_flag(True)

        # Kamera der App freigeben — sonst ist sie fuer den Messprozess belegt.
        self._kamera_freigeben()

        # Alten Bericht wegraeumen: Sein Auftauchen ist unser "fertig"-Signal.
        for pfad in _berichts_pfade():
            try:
                if pfad.is_file():
                    pfad.unlink()
            except Exception as e:
                logger.debug(f"Alter Messbericht nicht loeschbar ({pfad}): {e}")

        self._warten_auf_freie_kamera()

    def _warten_auf_freie_kamera(self, versuch: int = 0):
        """Erst starten, wenn keine Kamera-Pruefung der App mehr laeuft.

        Das Flag aus `_messung_flag` verhindert NEUE Pruefungen — eine bereits
        LAUFENDE (Hintergrund-Thread `_camera_status_probe`) haelt die Kamera
        aber vielleicht gerade noch offen. Wuerde der Messprozess jetzt starten,
        griffen zwei Prozesse gleichzeitig auf dieselbe DirectShow-Kamera zu;
        genau diese Klasse von Doppelzugriff war 2.4.31 der Absturz 0xc0000374.

        FELDBEFUND BOX 20.08.2026, 10:27 — WARUM HIER LANGE GEWARTET WIRD:
        Bis 2.4.37 wurde nur 3 s gewartet ("dauert normalerweise deutlich unter
        einer Sekunde") und danach trotzdem gestartet. Auf der echten Box dauert
        eine Pruefung aber ueber 10 Sekunden, weil die PowerShell-Kamerasuche in
        ihre Zeitgrenzen laeuft (10 s DirectShow-Enumeration + 5 s PnP, teils
        mehrfach). Ergebnis im Log:

            10:27:45.029 Kamera-Pruefung laeuft seit >3 s — Messung startet trotzdem
            10:27:45.030 Kamera-Messung startet als eigener Prozess
            10:27:47.922 DirectShow Kamera-Namen: ['c922 Pro Stream Webcam']   <- die APP
            10:27:48.585 Externe Kamera bevorzugt: [0] c922 Pro Stream Webcam  <- die APP

        Die Messung begann um 10:27:47 — genau waehrend die App die Kamera
        durchprobierte. Der Bericht meldete daraufhin "Kamera liess sich nicht
        oeffnen" und verurteilte 1080p zu Unrecht. Haette der Dialog nur drei
        Sekunden laenger gewartet, waere die Kamera frei gewesen.

        Deshalb: warten bis die Pruefung wirklich durch ist. Und wenn sie es
        nicht wird, NICHT starten — ein Messlauf, von dem wir schon wissen,
        dass er nichts messen kann, ist schlimmer als eine ehrliche Meldung.

        Gewartet wird ueber `after()`, nicht mit sleep: Die Oberflaeche bleibt
        bedienbar und der Abbrechen-Knopf funktioniert.
        """
        if self._prozess is not None or not self._start_gewuenscht:
            return
        laeuft = False
        try:
            laeuft = bool(getattr(self.app, "_camera_check_running", False))
        except Exception:
            laeuft = False

        if laeuft and versuch < _WARTEN_AUF_KAMERA_TAKTE:
            rest = int((_WARTEN_AUF_KAMERA_TAKTE - versuch) * _WARTEN_AUF_KAMERA_MS / 1000)
            self._status(
                "Die Fotobox-Software prüft gerade selbst die Kamera.\n"
                f"Warte, bis sie fertig ist (noch bis zu {rest} s)...\n\n"
                "Das ist normal und dauert auf dieser Box etwas."
            )
            self.after(_WARTEN_AUF_KAMERA_MS,
                       lambda: self._warten_auf_freie_kamera(versuch + 1))
            return

        if laeuft:
            # Nicht starten: Die Kamera ist nachweislich belegt, der Lauf
            # koennte nur "Kamera liess sich nicht oeffnen" liefern.
            logger.warning(
                "Kamera-Messung abgebrochen: Kamera-Pruefung der App laeuft seit "
                f"{int(_WARTEN_AUF_KAMERA_TAKTE * _WARTEN_AUF_KAMERA_MS / 1000)} s noch immer"
            )
            self._start_gewuenscht = False
            self._abschluss_anzeigen(
                "Die Fotobox-Software kommt nicht von der Kamera los.\n\n"
                "Eine Messung würde jetzt nur \"Kamera ließ sich nicht öffnen\""
                " melden — das wäre kein echtes Ergebnis.\n\n"
                "Bitte die Box einmal neu starten und es erneut versuchen.\n"
                "Oder: Software beenden und \"Kamera-Messung-starten.bat\" nutzen."
            )
            return

        self._prozess_starten()

    def _prozess_starten(self):
        self._status("Messung wird gestartet...")
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
            self._start_gewuenscht = False
            self._messung_flag(False)
            self._abschluss_anzeigen(
                "Die Messung ließ sich nicht starten.\n"
                f"{str(e)[:140]}\n\n"
                "Bitte den Ordner C:\\FexoBooth\\logs mitschicken."
            )
            return

        self._start_zeit = time.time()
        self._takt()

    def _messung_flag(self, an: bool):
        """Kamera-Waechter der App fuer die Dauer der Messung stilllegen.

        WARUM DAS NOETIG IST (Doppelzugriff ueber die PROZESSGRENZE):
        `_check_camera_status` in src/app.py probt die Kamera alle 15 s (bei
        blinkender Warnung alle 2 s) — aber nur, solange der Start-Screen zu
        sehen und die Kamera NICHT initialisiert ist. Genau diesen Zustand
        stellt dieser Dialog aktiv her: Er gibt die Kamera frei, und weil er
        nur ein modales Toplevel ist, bleibt `current_screen_name` "start" und
        die Tk-Mainloop feuert ihre after-Timer weiter.
        Ergebnis ohne diesen Riegel: Der App-Prozess oeffnet mitten in der
        Messung dieselbe DirectShow-Kamera, die der Messprozess gerade streamt.
        `camera_hardware_lock()` schuetzt davor NICHT — die Sperre gilt nur
        innerhalb eines Prozesses.

        Reihenfolge ist wichtig: erst das Flag setzen, dann die Kamera
        freigeben. Andersherum gaebe es ein Zeitfenster, in dem der Waechter
        die freie Kamera sieht und sofort losprobt.
        """
        if self.app is None:
            return
        try:
            self.app._kamera_messung_laeuft = bool(an)
            logger.debug(f"Kamera-Waechter der App {'pausiert' if an else 'wieder aktiv'}")
        except Exception as e:
            logger.warning(f"Kamera-Messung: Waechter-Flag nicht setzbar: {e}")

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
                self._start_gewuenscht = False
                self._messung_flag(False)
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
        # Startwunsch zuruecknehmen, sonst blockiert "Messung wiederholen".
        self._start_gewuenscht = False
        self._messung_flag(False)
        pfad = self._bericht_suchen()
        if pfad:
            self.bericht_pfad = pfad
            logger.info(f"Kamera-Messung fertig nach {laeuft_seit:.0f}s: {pfad}")
            # Musste ein Kamera-Schritt aufgegeben werden, haelt im Messprozess
            # ein nicht stoppbarer Thread die Kamera — der Prozess ist zwar
            # beendet und Windows hat den Handle zurueck, die Messwerte sind
            # aber unvollstaendig. Das steht im Statuskopf des Berichts; ohne
            # diesen Hinweis wuerde es niemand lesen.
            warnung = ""
            if self._kopf_lesen().get("kamera_belegt"):
                warnung = ("\n\nACHTUNG: Mindestens ein Kamera-Schritt musste "
                           "aufgegeben\nwerden — die Kamera hat nicht geantwortet. "
                           "Bitte die Box\neinmal neu starten und den Bericht "
                           "trotzdem mitschicken.")
            self._abschluss_anzeigen(
                f"Fertig nach {self._dauer_text(laeuft_seit)}!\n"
                f"Der Bericht wurde gespeichert:\n{pfad}\n\n"
                "Bitte diese Datei an Claude schicken." + warnung,
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
                    # 1200 statt 600 Zeichen: Der Statuskopf ist laenger
                    # geworden (Hinweisblock "Aendert sich diese Datei ..." und
                    # die ACHTUNG-Zeile zur belegten Kamera). Mit 600 haette
                    # die ACHTUNG-Zeile knapp ausserhalb liegen koennen.
                    kopf = f.read(1200)
            except Exception:
                continue

            ergebnis["vorhanden"] = True
            if "aufgegeben werden" in kopf:
                # Zeile aus Bericht._kopf(): "ACHTUNG: Ein Kamera-Schritt
                # musste aufgegeben werden."
                ergebnis["kamera_belegt"] = True
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
        if self._prozess is None and not self._start_gewuenscht:
            return
        logger.info("Kamera-Messung: vom Benutzer abgebrochen")
        # ZUERST den Startwunsch zuruecknehmen: Sonst startet ein noch
        # anstehendes _warten_auf_freie_kamera() die Messung gleich doch.
        self._start_gewuenscht = False
        self._prozess_beenden()
        self._prozess = None
        self._messung_flag(False)

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
        self._start_gewuenscht = False
        if self._prozess is not None:
            self._prozess_beenden()
            self._prozess = None

        self._kamera_spaeter_bereitstellen()

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

    def _kamera_spaeter_bereitstellen(self):
        """Kamera der App wieder oeffnen — VERZOEGERT und NICHT im UI-Thread.

        Bis 2.4.36 stand hier schlicht `self.app._pre_init_camera()`, direkt im
        Tk-UI-Thread und unmittelbar nach dem Abschiessen des Messprozesses.
        Beides ist falsch:
          * `WebcamManager.initialize` probiert DSHOW, MSMF und CAP_ANY
            nacheinander durch und nimmt dabei die Kamera-Hardware-Sperre.
            Auf einer gerade erst freigegebenen USB-Kamera dauert allein der
            MSMF-Fehlversuch auf dem Atom mehrere Sekunden — die Oberflaeche
            fror also ausgerechnet beim Knopf "Schliessen" ein. Genau dieses
            Einfrieren sollte 2.4.36 beseitigen.
          * Windows gibt den Geraetehandle erst mit dem Prozessende frei.
            Sofort danach zu oeffnen scheitert gern und kostet nur Zeit.
        Deshalb: kurz Ruhe geben, dann in einem Hintergrund-Thread oeffnen.
        Der Waechter bleibt bis dahin pausiert, damit er nicht parallel dazu
        dieselbe Kamera anfasst; er wird im Thread am Ende wieder freigegeben.

        Scheitert es, ist das unkritisch: Der Session-Start initialisiert die
        Kamera ohnehin selbst, wenn sie nicht bereit ist (session.py).
        """
        app = self.app
        if app is None:
            return
        if not self._kamera_freigegeben:
            self._messung_flag(False)
            return

        def oeffnen():
            try:
                app._pre_init_camera()
                logger.info("Kamera-Messung: Kamera wieder bereitgestellt")
            except Exception as e:
                logger.warning(
                    f"Kamera-Messung: Kamera nicht neu geöffnet ({e}) — "
                    "der nächste Session-Start holt das nach"
                )
            finally:
                # IMMER wieder freigeben, auch nach einem Fehlschlag — sonst
                # bliebe die Kamera-Warnung der Box dauerhaft stumm.
                try:
                    app._kamera_messung_laeuft = False
                except Exception:
                    pass

        def starten():
            threading.Thread(target=oeffnen, daemon=True,
                             name="kamera-nach-messung").start()

        try:
            # Bewusst ueber die Wurzel der App: Dieser Dialog ist zu dem
            # Zeitpunkt schon zerstoert.
            app.root.after(_KAMERA_RUHE_MS, starten)
        except Exception:
            starten()

    def destroy(self):
        """Letzte Sicherung: Der Waechter darf nie dauerhaft pausiert bleiben.

        `_schliessen` raeumt normal auf. Wird das Fenster auf einem anderen Weg
        zerstoert (Fehler im Ablauf, App faehrt herunter), waere der Kamera-
        Waechter sonst fuer den Rest der Laufzeit tot — die Box wuerde eine
        fehlende Kamera nie wieder melden.
        """
        try:
            if self._prozess is not None:
                self._prozess_beenden()
                self._prozess = None
                self._messung_flag(False)
        except Exception:
            pass
        return super().destroy()

    # ------------------------------------------------------------------
    # Hilfsmittel
    # ------------------------------------------------------------------

    def _status(self, text: str):
        try:
            self.status_label.configure(text=text)
        except Exception:
            pass
