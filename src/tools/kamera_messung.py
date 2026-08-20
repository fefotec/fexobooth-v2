r"""Kamera-Messung: Wie schnell ist die Box bei welcher Aufloesung? (2.4.35)

WARUM ES DAS BRAUCHT:
Beim Fotografieren wird die Kamera pro Bild kurz von der Vorschau-Aufloesung
(640x480) auf 1920x1080 umgeschaltet. Das kostet laut Feld-Logs ~1,5 Sekunden —
und genau deshalb passt der Ausloese-Blitz nicht zum Bild: Geblitzt wird sofort,
belichtet wird ~1,7 s spaeter. Wer sich dazwischen bewegt, ist nicht mehr drauf.

Die naheliegende Loesung waere, die Kamera DAUERHAFT auf 1920x1080 laufen zu
lassen und die Vorschau nur herunterzurechnen — dann entfaellt das Umschalten
komplett. Ob das auf dem Atom-Tablet fluessig genug ist, laesst sich aber NICHT
am Schreibtisch ausrechnen: Der entscheidende Posten ist das Dekodieren eines
1080p-MJPG-Bildes, und dabei bremst vor allem die Speicherbandbreite — die
skaliert auf schwacher Hardware voellig anders als reine Rechenleistung.
(Gegenprobe am Entwickler-PC: dort kam die Hochrechnung auf 21 ms pro Bild,
die Box meldet real 83 ms. Also messen statt rechnen.)

Beantwortet vier Fragen:
  1. Wie viele Bilder pro Sekunde schafft die Kamera bei 640x480 / 1280x720 / 1920x1080?
  2. Wie lange dauert das Umschalten der Aufloesung wirklich?
  3. Was kostet die Bildaufbereitung — und wie viel bringt es, ZUERST zu
     verkleinern und erst danach zu spiegeln/umzufaerben?
  4. Ist Media Foundation (MSMF) schneller als DirectShow (DSHOW)?

WARUM DIE DATEI SO UMSTAENDLICH AUSSIEHT (Feld-Befund 20.08.2026):
Christian meldete "ich warte nun schon 5 min aber der test wird immernoch
angezeigt". Das Box-Log endet exakt beim ERSTEN Kamerazugriff der Messung —
danach keine Zeile mehr, auch kein Absturz. Der Messcode selbst hatte naemlich
keine einzige Zeitgrenze: ueber 240 Bildabfragen, bei Fehlschlag nur `continue`.
Antwortet die Kamera nicht, steht `cap.read()` im C-Code von OpenCV endlos, und
niemand merkt es.
(2.4.36 hat bereits die FOLGE entschaerft — der Admin-Knopf startet die Messung
als eigenen Prozess, die Oberflaeche friert dadurch nicht mehr mit ein. Diese
Datei hier behebt die URSACHE: Der Messvorgang selbst haengt nicht mehr endlos
und hinterlaesst in jedem Fall ein Ergebnis.)

Dazu kam: Der Bericht wurde erst GANZ AM ENDE geschrieben — waehrend des
gesamten Laufs gab es kein einziges Lebenszeichen auf der Platte, und `print()`
faellt im Fenster-Build (console=False, sys.stdout ist None) ohnehin ins Leere.
Ein laufender Prozess war von einem toten nicht zu unterscheiden.

Daraus folgen die drei Bauprinzipien hier:
  * Der Bericht waechst MIT. Nach jedem Schritt landet er auf der Platte,
    mit Statuskopf ("Schritt 4 von 11, laeuft seit 00:02:13"). Ein Abbruch
    hinterlaesst damit alle bis dahin fertigen Messwerte statt gar nichts.
  * Jeder Kamerazugriff laeuft in einem Wegwerf-Thread mit Zeitgrenze
    (siehe `_mit_zeitlimit` — dort steht auch, warum "abbrechen" in
    Wirklichkeit "aufgeben" heisst).
  * Jeder ausgelassene Schritt hinterlaesst eine Zeile MIT Begruendung.
    Stilles `continue` macht einen Bericht unlesbar: Man kann "gemessen und
    leer" nicht von "stumm gescheitert" unterscheiden.

Aufruf auf der Box:  fexobooth.exe --kamera-test
Ergebnis:            C:\FexoBooth\logs\kamera-messung.txt
"""

import os
import sys
import threading
import time
import types
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

try:
    # 2.4.35: NICHT mehr stummschalten. Genau die Meldungen, die einen Haenger
    # erklaeren ("can't grab frame", "Stream tick detected", "ReadSample() ...")
    # waren vorher abgeschaltet — fuer ein Diagnose-Werkzeug die falsche
    # Richtung. Wohin sie geschrieben werden, regelt `_OpenCvMeldungen`.
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_WARNING)
except Exception:
    pass


AUFLOESUNGEN = [(640, 480), (1280, 720), (1920, 1080)]
BILDER_PRO_MESSUNG = 30
AUFWAERM_BILDER = 5

# Nach so vielen Fehlversuchen IN FOLGE bricht eine Zelle ab. Der Zaehler wird
# bei jedem angekommenen Bild zurueckgesetzt — eine Kamera mit gelegentlichen
# Aussetzern soll weitermessen duerfen, eine stumme aber nicht 30 Runden drehen.
MAX_FEHLER_IN_FOLGE = 5

# Zeitgrenzen pro Zelle. Gemessener Gutfall auf der Box liegt bei ~8-15 s,
# das ist also mehr als dreifache Reserve. Zu knapp waere schlimmer als zu
# grosszuegig: Ein abgeschnittener Gutfall wuerde als "zu langsam" fehlurteilen.
ZEITLIMIT_JE_AUFLOESUNG = {
    (640, 480): 25.0,
    (1280, 720): 35.0,
    (1920, 1080): 50.0,
}
ZEITLIMIT_UMSCHALTEN = 30.0

# Letzte Sicherung: Selbst wenn jedes Einzel-Limit greift, hat der ganze Lauf
# eine berechenbare Obergrenze. Sonst ist die Ansage in der BAT wieder falsch.
GESAMT_BUDGET_SEKUNDEN = 8 * 60.0

# Wartezeit auf die Kamera-Hardware-Sperre. Laenger warten bringt nichts: Haelt
# ein aufgegebener Thread sie, gibt er sie nie wieder her.
SPERRE_WARTEN_SEKUNDEN = 5.0

# Als Konstante, weil Abschnitt 3 genau diesen einen Grund ignorieren darf
# (er rechnet nur auf einem vorhandenen Bild und braucht keine Kamera).
GRUND_KAMERA_HAENGT = "vorheriger Schritt haengt noch und haelt die Kamera"

# Groesse eines Foto-Fachs in der LiveView-Collage (aus dem Feld-Log:
# Template 1800x1200 wird auf 1002x668 skaliert, Fach 1 ist dann ~362x240).
FACH = (362, 240)

# Ruhezeit zwischen zwei Kamera-Zellen. Eine USB-Kamera, die gerade
# freigegeben (oder aufgegeben) wurde, braucht einen Moment, bevor sie sich
# sauber neu oeffnen laesst. Bis 2.4.36 stand diese Pause nur im ERFOLGSFALL —
# also ausgerechnet dort NICHT, wo sie gebraucht wird: Nach einem Fehlversuch
# ging es ohne Pause sofort weiter, und der Folgefehler wurde dann als
# "keine Bilder erhalten" gebucht, also als Argument gegen 1080p.
USB_RUHE_SEKUNDEN = 0.3

# Merker: Wurde ein Kamera-Schritt aufgegeben, gehoert die Kamera bis zum
# Prozessende einem Thread, den niemand mehr stoppen kann.
_KAMERA_BLEIBT_BELEGT = False

# Zeitpunkt des letzten Kamerazugriffs — Grundlage fuer USB_RUHE_SEKUNDEN.
_LETZTER_KAMERA_ZUGRIFF = 0.0

# Ersatzsperre, falls dieses Werkzeug ohne die App laeuft (z.B. Direktaufruf
# aus dem Quellbaum). Im Normalfall gewinnt immer `camera_hardware_lock()`.
_ERSATZ_SPERRE = threading.RLock()


def kamera_bleibt_belegt() -> bool:
    """War in DIESEM Prozess ein Kamera-Schritt aufgegeben worden?

    Dann haelt ein nicht stoppbarer Thread Kamera UND Hardware-Sperre bis zum
    Programmende.

    EHRLICHE EINSCHRAENKUNG (2.4.37): Diese Auskunft gilt nur PROZESSINTERN.
    Der Admin-Dialog laeuft in einem anderen Prozess und kann sie gar nicht
    lesen — er erfaehrt es ueber den Statuskopf des Berichts ("ACHTUNG: Ein
    Kamera-Schritt musste aufgegeben werden"), den er ohnehin mitliest.
    Aufrufer hier: src/main.py, fuer den Rueckgabewert des Messmodus.
    """
    return _KAMERA_BLEIBT_BELEGT


def _kamera_ruhe():
    """Vor jedem Kamerazugriff: der USB-Kamera ihre Beruhigungspause geben.

    Bewusst als Wartezeit VOR dem Zugriff statt als sleep danach: So greift sie
    auf JEDEM Weg — auch nach einem Fehlschlag, nach einem Zeitlimit und nach
    einem uebersprungenen Schritt — und kostet gleichzeitig nichts, wenn seit
    dem letzten Zugriff ohnehin schon genug Zeit vergangen ist.
    """
    if not _LETZTER_KAMERA_ZUGRIFF:
        return
    rest = USB_RUHE_SEKUNDEN - (time.time() - _LETZTER_KAMERA_ZUGRIFF)
    if rest > 0:
        time.sleep(rest)


def _kamera_zugriff_vermerken():
    global _LETZTER_KAMERA_ZUGRIFF
    _LETZTER_KAMERA_ZUGRIFF = time.time()


# ----------------------------------------------------------------------
# Zielordner
# ----------------------------------------------------------------------

def _log_ordner():
    """Bevorzugt C:\\FexoBooth\\logs, sonst C:\\ProgramData\\FexoBox."""
    from pathlib import Path

    try:
        from src.utils.logging import LOG_PATH
        return Path(LOG_PATH)
    except Exception:
        return Path(r"C:\ProgramData\FexoBox")


# ----------------------------------------------------------------------
# Bericht
# ----------------------------------------------------------------------

class Bericht:
    """Sammelt Zeilen fuer Konsole UND Datei — und schreibt LAUFEND mit.

    Der Statuskopf steht bewusst NICHT in `self.zeilen`, sondern wird bei jedem
    Speichern frisch berechnet und der Liste nur vorangestellt. Landete er in
    der Liste, wuerde er sich bei jedem Schritt wiederholen und der Bericht
    waere nach ein paar Minuten unbrauchbar.
    """

    def __init__(self) -> None:
        self.zeilen: List[str] = []
        self.start = time.time()
        self.gesamt_schritte = 0
        self.schritt_nr = 0
        self.schritt_name = ""
        self.schritt_start = 0.0
        self.status = "LAEUFT NOCH"
        self.kamera_belegt = False
        self.melder: Optional[Callable[[int, int, str], None]] = None
        # Der beim ersten Mal erfolgreiche Pfad wird gemerkt: Bei ~22 Schreib-
        # vorgaengen sollen nicht jedes Mal beide Kandidaten durchprobiert werden.
        self._ziel = None

    # -- Ausgabe ------------------------------------------------------

    def __call__(self, text: str = "") -> None:
        # Im Fenster-Build (PyInstaller ohne Konsole) ist sys.stdout None —
        # ein normales print() wuerde dort mit AttributeError abstuerzen.
        # Die Datei ist ohnehin das Ergebnis, die Konsole nur Zugabe.
        try:
            print(text, flush=True)
        except Exception:
            pass
        self.zeilen.append(text)

    def titel(self, text: str) -> None:
        self("")
        self("=" * 66)
        self("  " + text)
        self("=" * 66)

    # -- Fortschritt --------------------------------------------------

    def schritt_beginnt(self, name: str) -> None:
        """Neuen Schritt anmelden und den Zwischenstand sofort sichern."""
        self.schritt_nr += 1
        self.schritt_name = name
        self.schritt_start = time.time()
        # ERST speichern, DANN melden: Wer auf die Meldung hin die Datei
        # oeffnet, soll den neuen Schritt schon darin finden.
        self.speichern()
        self._melden()

    def schritt_fertig(self) -> None:
        """Schritt abhaken und das Ergebnis sofort sichern."""
        self.schritt_name = ""
        self.speichern()

    def _melden(self) -> None:
        """Fortschritt an die Oberflaeche geben (Dialog), falls jemand zuhoert.

        Wird aus dem Mess-Thread aufgerufen. Der Empfaenger MUSS selbst dafuer
        sorgen, dass er Tk nur ueber `after(0, ...)` anfasst — deshalb hier
        alles in try/except: Ein Fehler in der Oberflaeche darf die Messung
        niemals beenden.
        """
        if self.melder is None:
            return
        try:
            self.melder(self.schritt_nr, self.gesamt_schritte, self.schritt_name)
        except Exception:
            pass

    # -- Datei --------------------------------------------------------

    @staticmethod
    def _dauer(sekunden: float) -> str:
        sekunden = max(0, int(sekunden))
        return "%02d:%02d:%02d" % (sekunden // 3600, (sekunden // 60) % 60, sekunden % 60)

    def _kopf(self) -> List[str]:
        """Statuskopf — bei JEDEM Speichern neu erzeugt, nie gespeichert."""
        laeuft_seit = self._dauer(time.time() - self.start)
        kopf = [
            "=" * 66,
            "  LAUFENDER BERICHT - Status oben, Messwerte darunter",
            "=" * 66,
            "Status           : " + self.status,
        ]
        if self.gesamt_schritte:
            kopf.append("Fortschritt      : Schritt %d von %d" % (self.schritt_nr, self.gesamt_schritte))
        kopf.append("Laeuft seit      : " + laeuft_seit)
        if self.schritt_name:
            begonnen = self._dauer(self.schritt_start - self.start)
            kopf.append("Aktueller Schritt: " + self.schritt_name + " (begonnen " + begonnen + ")")
        else:
            kopf.append("Aktueller Schritt: -")
        if self.status == "LAEUFT NOCH":
            kopf.append("")
            kopf.append("Aendert sich diese Datei 3 Minuten lang nicht mehr, haengt die")
            kopf.append("Messung fest. Dann: Strg+Umschalt+Esc, Reiter Details,")
            kopf.append("fexobooth.exe beenden - und die Box einmal neu starten.")
        if self.kamera_belegt:
            kopf.append("")
            kopf.append("ACHTUNG: Ein Kamera-Schritt musste aufgegeben werden. Die Kamera")
            kopf.append("bleibt bis zum Neustart der Box belegt - bitte Box neu starten.")
        kopf.append("")
        return kopf

    def speichern(self, status: Optional[str] = None) -> Optional[str]:
        """Bericht atomar auf die Platte schreiben. Darf NIE eine Ausnahme werfen.

        Erst in eine .tmp-Datei, dann `os.replace()` auf den Endnamen: So sieht
        Christian nie eine halb geschriebene Datei, wenn er sie mitten im Lauf
        oeffnet. Scheitert das Speichern (z.B. weil ein Editor die Zieldatei
        sperrt), laeuft die Messung trotzdem weiter — ein Schreibfehler darf
        niemals wertvolle Messzeit auf einer Box im Feld vernichten.
        """
        if status is not None:
            self.status = status

        inhalt = "\n".join(self._kopf() + self.zeilen) + "\n"

        if self._ziel is not None:
            ziele = [self._ziel]
        else:
            from pathlib import Path
            ziele = [_log_ordner() / "kamera-messung.txt",
                     Path(r"C:\ProgramData\FexoBox") / "kamera-messung.txt"]

        for ziel in ziele:
            try:
                ziel.parent.mkdir(parents=True, exist_ok=True)
                vorlaeufig = ziel.with_name(ziel.name + ".tmp")
                with open(vorlaeufig, "w", encoding="utf-8") as f:
                    f.write(inhalt)
                os.replace(str(vorlaeufig), str(ziel))
                self._ziel = ziel
                return str(ziel)
            except Exception:
                continue

        # Gemerkter Pfad hat versagt -> beim naechsten Mal wieder alle probieren
        self._ziel = None
        return None


# ----------------------------------------------------------------------
# OpenCV-Meldungen mitschreiben (optional, best effort)
# ----------------------------------------------------------------------

class _OpenCvMeldungen:
    """Leitet den C-Fehlerkanal von OpenCV in eine eigene Datei um.

    OpenCV meldet Haenger nicht ueber Python, sondern direkt auf Dateideskriptor
    2 ("videoio(MSMF): can't grab frame", "Stream tick detected"). Genau diese
    Zeilen erklaeren einen Haenger — und wachsen sogar noch, wenn die Messung
    selbst nicht mehr weiterkommt.

    HOCHRISIKO-STELLE, deshalb sehr defensiv: Im Fenster-Build ist
    `sys.__stderr__` None und Deskriptor 2 kann ungueltig sein; ein unbedachtes
    `os.dup2()` darauf beendet den Prozess sofort. Es wird deshalb nur
    umgeleitet, wenn ein echter, pruefbarer Deskriptor existiert. Jeder
    Fehlschlag bleibt folgenlos — die Messung braucht diese Datei nicht.
    """

    MAX_BYTES = 2 * 1024 * 1024

    def __init__(self) -> None:
        self.aktiv = False
        self.pfad: Optional[str] = None
        self._alt_fd: Optional[int] = None
        self._datei = None

    def start(self) -> None:
        try:
            if sys.__stderr__ is None:
                return
            try:
                fd = sys.__stderr__.fileno()
            except Exception:
                return
            if fd is None or fd < 0:
                return
            os.fstat(2)  # wirft, wenn Deskriptor 2 gar nicht existiert

            ziel = _log_ordner() / "kamera-messung-opencv.txt"
            ziel.parent.mkdir(parents=True, exist_ok=True)
            self._datei = open(str(ziel), "w", encoding="utf-8", errors="replace")
            self._alt_fd = os.dup(2)
            os.dup2(self._datei.fileno(), 2)
            self.aktiv = True
            self.pfad = str(ziel)
        except Exception:
            self.aktiv = False
            self._aufraeumen()

    def deckeln_pruefen(self) -> None:
        """Eine sehr geschwaetzige Kamera darf die Platte nicht vollschreiben."""
        if not self.aktiv or not self.pfad:
            return
        try:
            if os.path.getsize(self.pfad) > self.MAX_BYTES:
                self.stop()
        except Exception:
            pass

    def stop(self) -> None:
        try:
            if self.aktiv and self._alt_fd is not None:
                os.dup2(self._alt_fd, 2)
        except Exception:
            pass
        self.aktiv = False
        self._aufraeumen()

    def _aufraeumen(self) -> None:
        try:
            if self._alt_fd is not None:
                os.close(self._alt_fd)
        except Exception:
            pass
        self._alt_fd = None
        try:
            if self._datei is not None:
                self._datei.close()
        except Exception:
            pass
        self._datei = None


# ----------------------------------------------------------------------
# Zeitgrenze und Sperre
# ----------------------------------------------------------------------

def _mit_zeitlimit(arbeit: Callable[[], object], zeitlimit: float):
    """Fuehrt `arbeit` in einem Wegwerf-Thread aus und gibt nach `zeitlimit` auf.

    EHRLICH GESAGT: Ein blockierender cv2-Aufruf laesst sich in Python NICHT
    abbrechen. Der Aufruf steckt im C-Code von OpenCV, dorthin kommt weder ein
    Signal noch eine Exception. Wir koennen den Thread nur AUFGEBEN. Daraus
    folgen drei Regeln, die hier zwingend eingehalten werden:

      1. Der Worker ist ein Daemon-Thread — sonst liesse sich das Programm
         danach nicht mehr beenden.
      2. Nach dem Zeitlimit wird sein Ergebnis nie wieder gelesen. Der
         aufgegebene Thread darf spaeter noch hineinschreiben, das interessiert
         dann niemanden mehr.
      3. Der Aufrufer MUSS danach jeden weiteren Kamerazugriff sein lassen: Der
         aufgegebene Thread besitzt die Kamera weiterhin. Ein zweiter Zugriff
         waere genau die Heap-Korruption aus 2.4.31 (0xc0000374).

    Die zusaetzlich gesetzten CAP_PROP_*_TIMEOUT_MSEC (siehe `_video_capture`)
    beachtet nur Media Foundation, DirectShow ignoriert sie. Dieser Wachhund
    hier bleibt deshalb die eigentliche Absicherung und darf nicht durch sie
    ersetzt werden.

    Rueckgabe: (ergebnis, fehler). `fehler` ist None bei Erfolg, "zeitlimit"
    wenn aufgegeben wurde, sonst der Fehlertext.
    """
    ablage: Dict[str, object] = {}

    def lauf():
        try:
            ablage["wert"] = arbeit()
        except BaseException as e:  # auch der Worker darf nichts nach aussen werfen
            ablage["fehler"] = e.__class__.__name__ + ": " + str(e)

    t = threading.Thread(target=lauf, daemon=True, name="kamera-messung-schritt")
    t.start()
    t.join(zeitlimit)

    if t.is_alive():
        return None, "zeitlimit"
    if "fehler" in ablage:
        return None, str(ablage["fehler"])
    return ablage.get("wert"), None


def _hardware_sperre():
    """Die modulweite Kamera-Sperre der App (2.4.31) — oder ein Ersatz."""
    try:
        from src.camera.webcam import camera_hardware_lock
        return camera_hardware_lock()
    except Exception:
        return _ERSATZ_SPERRE


def _mit_sperre(arbeit: Callable[[], dict]) -> dict:
    """Nimmt die Kamera-Sperre IM AUFRUFENDEN THREAD und fuehrt `arbeit` aus.

    WICHTIG, WARUM HIER UND NICHT AUSSEN: `camera_hardware_lock()` liefert
    einen RLock, und ein RLock ist nur fuer DENSELBEN Thread wiedereintritts-
    faehig. Wuerde der Dialog-Thread die Sperre halten und die Messung ihre
    Arbeit in einen Worker-Thread verlagern, blockierte dieser FREMDE Thread
    fuer immer — bei einem bildschirmfuellenden, modalen Dialog waere die Box
    damit komplett tot. Deshalb haelt genau der Thread die Sperre, der auch
    `cv2.VideoCapture` aufruft. (Der Dialog darf sie folglich NICHT mehr selbst
    nehmen, siehe src/ui/dialogs/kamera_messung.py.)
    """
    sperre = _hardware_sperre()
    if not sperre.acquire(timeout=SPERRE_WARTEN_SEKUNDEN):
        return {"gesperrt": True}
    try:
        return arbeit()
    finally:
        sperre.release()


# ----------------------------------------------------------------------
# Kamera oeffnen und lesen
# ----------------------------------------------------------------------

def _video_capture(index: int, backend: int):
    """VideoCapture anlegen — Zeitgrenzen NUR fuer Media Foundation.

    FELDBEFUND BOX, 20.08.2026 — HIER STAND EINE FALSCHE ANNAHME:
    Die erste Fassung uebergab `CAP_PROP_OPEN_TIMEOUT_MSEC` /
    `CAP_PROP_READ_TIMEOUT_MSEC` an JEDES Backend, mit dem Kommentar "nur Media
    Foundation beachtet sie — sie kostet nichts". Das ist falsch. DirectShow
    ignoriert die Parameter nicht, es VERWEIGERT damit das Oeffnen:

        VIDEOIO(DSHOW): raised OpenCV exception:
        (-213) VIDEOIO: Failed to apply invalid or unsupported parameter:
        [53]=4000 in function 'cv::applyParametersFallback'
        VIDEOIO(DSHOW): backend is generally available but can't be used
        to capture by index

    Folge auf der Box: DirectShow lieferte bei 640x480 "Kamera liess sich nicht
    oeffnen", wurde daraufhin als totes Backend eingestuft und ALLE weiteren
    DirectShow-Messungen wurden uebersprungen. Die Messung lief sauber durch —
    nur ohne einen einzigen Messwert.

    Zwei Absicherungen, weil OpenCV den Fehler INTERN abfaengt und nur ein nicht
    geoeffnetes Objekt zurueckgibt (es fliegt also keine Python-Ausnahme, ein
    try/except allein haette nie gegriffen):
      1. Die Parameter gehen nur an Media Foundation.
      2. Ist die Kamera danach trotzdem nicht offen, wird ohne Parameter erneut
         versucht.
    """
    parameter_erlaubt = (
        hasattr(cv2, "CAP_MSMF") and backend == cv2.CAP_MSMF
    )
    open_to = getattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC", None)
    read_to = getattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC", None)

    if parameter_erlaubt and open_to is not None and read_to is not None:
        try:
            cap = cv2.VideoCapture(index, backend, params=[
                int(open_to), 4000,
                int(read_to), 3000,
            ])
            if cap is not None and cap.isOpened():
                return cap
            # Parameter wurden abgelehnt -> sauber schliessen und ohne versuchen
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
        except Exception:
            pass

    try:
        return cv2.VideoCapture(index, backend)
    except Exception:
        return None


def _fourcc_text(cap) -> str:
    """Aktiven Codec als vier Buchstaben lesen (MJPG / YUY2 / ...).

    Nutzt bewusst `WebcamManager._get_current_fourcc` wieder, damit die Messung
    exakt dasselbe liest wie die Software, deren Verhalten sie messen soll.
    """
    try:
        from src.camera.webcam import WebcamManager
        return WebcamManager._get_current_fourcc(types.SimpleNamespace(cap=cap))
    except Exception:
        pass
    try:
        wert = int(cap.get(cv2.CAP_PROP_FOURCC))
        if wert <= 0:
            return "unbekannt"
        return "".join(chr((wert >> 8 * i) & 0xFF) for i in range(4)).strip() or str(wert)
    except Exception:
        return "unbekannt"


def _mjpg_anfordern(cap, breite: int, hoehe: int) -> bool:
    """MJPG anfordern — mit Verifikation und Rueckfall, GENAU wie die App.

    Muss `WebcamManager._apply_mjpg` (src/camera/webcam.py) entsprechen, sonst
    misst die Messung eine andere Kamera-Konfiguration als die Fotobox im
    Betrieb wirklich faehrt. Bis 2.4.36 wurde der Codec hier genau EINMAL
    gesetzt und das Ergebnis nie geprueft: Lehnte der Treiber diesen Weg ab,
    mass die Messung YUY2, waehrend die App MJPG bekaeme — Urteil "1080p zu
    langsam", obwohl die Box es koennte.

    1) Codec NACH der Aufloesung anfordern und Ergebnis PRUEFEN.
    2) Rueckfall: Codec zuerst, dann dieselbe Aufloesung erneut setzen
       (manche Treiber wollen es so).
    """
    try:
        if _fourcc_text(cap) == "MJPG":
            return True
        mjpg = cv2.VideoWriter_fourcc(*"MJPG")

        cap.set(cv2.CAP_PROP_FOURCC, mjpg)
        if _fourcc_text(cap) == "MJPG":
            return True

        cap.set(cv2.CAP_PROP_FOURCC, mjpg)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, breite)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, hoehe)
        return _fourcc_text(cap) == "MJPG"
    except Exception:
        return False


def _oeffne(index: int, backend: int, breite: int, hoehe: int):
    """Kamera oeffnen und auf eine Aufloesung stellen.

    REIHENFOLGE IST HIER ENTSCHEIDEND: erst Aufloesung, DANN der Codec. Genau
    so macht es die Fotobox selbst (src/camera/webcam.py: "Codec NACH der
    Aufloesung anfordern — andersherum verhandelt DirectShow beim
    Aufloesungs-Setzen wieder auf YUY2 zurueck", Messung 2.4.13). Bis 2.4.34
    machte diese Messung es genau andersherum und mass damit vermutlich das
    Dekodieren von YUY2 statt MJPG — also gerade NICHT die zentrale Frage.
    ACHTUNG BEIM VERGLEICHEN: Aeltere Berichte (bis 2.4.34) sind deshalb NICHT
    mit neuen vergleichbar. Der Berichtskopf sagt das ausdruecklich.
    """
    cap = _video_capture(index, backend)
    if cap is None:
        return None
    try:
        if not cap.isOpened():
            cap.release()
            return None
    except Exception:
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, breite)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, hoehe)
    _mjpg_anfordern(cap, breite, hoehe)
    return cap


def _zustand(cap) -> Tuple[int, int, str]:
    """Was ist WIRKLICH aktiv? Zurueckgelesen statt geglaubt."""
    try:
        breite = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        hoehe = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    except Exception:
        breite, hoehe = 0, 0
    return breite, hoehe, _fourcc_text(cap)


def _messe_lesen(cap, anzahl: int = BILDER_PRO_MESSUNG) -> dict:
    """Dauer eines Bildes im DAUERBETRIEB - getrennt nach Warten und Rechnen.

    WICHTIG fuer die Auswertung: cap.read() macht ZWEI Dinge auf einmal und
    verschleiert damit die eigentliche Frage.
      grab()     = auf das naechste Bild der Kamera WARTEN (Bildrate/USB)
      retrieve() = das MJPG-Bild DEKODIEREN (reine Rechenzeit der CPU)

    Nur `retrieve` sagt uns, ob der Atom 1080p ueberhaupt schafft. Ist `grab`
    der grosse Posten, liegt es an der Kamera/USB - dann bringt eine schnellere
    Bildaufbereitung gar nichts.

    Die Kennzahlen sind unveraendert. Neu ist nur der Ausstieg nach
    MAX_FEHLER_IN_FOLGE Fehlversuchen und die Rueckgabe von `versuche`: Damit
    steht "nur 3 von 30 Bildern erhalten" im Bericht statt einer stillen Luecke,
    und eine duenne Messung ist als solche erkennbar.
    """
    for _ in range(AUFWAERM_BILDER):
        cap.read()

    warten: List[float] = []
    rechnen: List[float] = []
    gesamt: List[float] = []
    versuche = 0
    fehler_in_folge = 0
    letztes_bild = None

    for _ in range(anzahl):
        versuche += 1
        t0 = time.perf_counter()
        ok = cap.grab()
        t1 = time.perf_counter()
        if not ok:
            fehler_in_folge += 1
            if fehler_in_folge >= MAX_FEHLER_IN_FOLGE:
                break
            continue
        ok2, frame = cap.retrieve()
        t2 = time.perf_counter()
        if not ok2 or frame is None:
            fehler_in_folge += 1
            if fehler_in_folge >= MAX_FEHLER_IN_FOLGE:
                break
            continue

        fehler_in_folge = 0
        letztes_bild = frame
        warten.append((t1 - t0) * 1000)
        rechnen.append((t2 - t1) * 1000)
        gesamt.append((t2 - t0) * 1000)

    if not gesamt:
        return {"n": 0, "versuche": versuche, "bild": None}

    def kennzahlen(werte):
        werte = sorted(werte)
        return {
            "mittel": sum(werte) / len(werte),
            "min": werte[0],
            "max": werte[-1],
        }

    g = kennzahlen(gesamt)
    # EIN Bild fuer Abschnitt 3 beiseitelegen — dort wird nur Rechenzeit auf
    # einem vorhandenen Bild gemessen, dafuer muss die Kamera nicht noch einmal
    # geoeffnet werden (jede zusaetzliche Oeffnung ist nur eine Haenger-Chance).
    bild = None
    try:
        if letztes_bild is not None:
            bild = letztes_bild.copy()
    except Exception:
        bild = None

    return {
        "n": len(gesamt),
        "versuche": versuche,
        "bild": bild,
        "mittel": g["mittel"],
        "min": g["min"],
        "max": g["max"],
        "fps": 1000.0 / g["mittel"] if g["mittel"] > 0 else 0.0,
        "warten": kennzahlen(warten)["mittel"] if warten else 0.0,
        "rechnen": kennzahlen(rechnen)["mittel"] if rechnen else 0.0,
    }


def _messe_aufbereitung(frame: np.ndarray, wiederholungen: int = 20):
    """Heutige Reihenfolge gegen 'erst verkleinern' vergleichen."""

    def zeit(fn):
        fn()
        t0 = time.perf_counter()
        for _ in range(wiederholungen):
            fn()
        return (time.perf_counter() - t0) / wiederholungen * 1000

    def heute():
        # Genau die heutige Reihenfolge: Vollbild spiegeln + umfaerben,
        # danach erst verkleinern.
        gespiegelt = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(gespiegelt, cv2.COLOR_BGR2RGB)
        return cv2.resize(rgb, FACH, interpolation=cv2.INTER_AREA)

    def vorschlag():
        # Zweistufig verkleinern: pyrDown glaettet und halbiert sehr guenstig,
        # der letzte kleine Schritt dann sauber mit INTER_AREA.
        # (Einstufig INTER_LINEAR waere zwar noch schneller, flimmert aber
        # sichtbar - bei 1080p auf ein 362px-Fach ist das Faktor 5.)
        klein = frame
        while klein.shape[1] >= FACH[0] * 4 and klein.shape[0] >= FACH[1] * 4:
            klein = cv2.pyrDown(klein)
        klein = cv2.resize(klein, FACH, interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(cv2.flip(klein, 1), cv2.COLOR_BGR2RGB)

    return zeit(heute), zeit(vorschlag)


def _backends():
    liste = [("DirectShow (aktuell)", cv2.CAP_DSHOW)]
    if hasattr(cv2, "CAP_MSMF"):
        liste.append(("Media Foundation", cv2.CAP_MSMF))
    return liste


# ----------------------------------------------------------------------
# Kamera-AUSWAHL (laeuft VOR der Messung — und braucht dieselbe Absicherung)
# ----------------------------------------------------------------------

# Grosszuegig: `list_cameras()` oeffnet fuenf DirectShow-Indizes nacheinander
# und fragt vorher per PowerShell die Geraetenamen ab (bis 10 s Timeout). Im
# Gutfall sind das auf dem Miix rund 16 s.
ZEITLIMIT_KAMERA_SUCHE = 40.0


def kamera_suchen(zeitlimit: float = ZEITLIMIT_KAMERA_SUCHE) -> Tuple[int, Optional[str], List[str]]:
    """Beste externe Kamera suchen — mit Zeitgrenze und mit Lebenszeichen.

    WARUM DAS HIER STEHT UND NICHT MEHR IN main.py (Feld-Befund 20.08.2026):
    Der komplette Wachhund-Apparat dieser Datei nuetzte nichts, solange die
    Kamera-SUCHE davor ungeschuetzt lief. `WebcamManager.list_cameras()` oeffnet
    fuenf DirectShow-Indizes im aufrufenden Thread, ohne jede Zeitgrenze — und
    zwar BEVOR der Bericht ueberhaupt existiert. Haengt einer dieser Indizes
    (typisch: die interne, abgeklebte Miix-Kamera), sieht Christian exakt das
    alte Bild: schwarzes Fenster, keine Datei, kein Ende.

    Deshalb hier: erst eine Berichtszeile auf die Platte (damit ein Haenger an
    DIESER Stelle sichtbar wird), dann die Suche im Wegwerf-Thread.

    Die Hardware-Sperre wird bewusst NICHT vom Aufrufer genommen:
    `list_cameras()` nimmt sie selbst (webcam.py), und sie ist ein RLock — der
    Hauptthread duerfte sie also gar nicht halten, waehrend ein Worker-Thread
    sie braucht (das waere ein garantierter Deadlock statt eines Zeitlimits).

    Rueckgabe: (index, geraetename|None, protokoll) — `protokoll` gehoert in
    den spaeteren Messbericht, damit dort steht, WIE die Kamera gewaehlt wurde.
    """
    global _KAMERA_BLEIBT_BELEGT

    stummel = Bericht()
    stummel.status = "LAEUFT NOCH"
    stummel.titel("FEXOBOOTH - KAMERA-MESSUNG")
    stummel("Zeitpunkt : " + time.strftime("%d.%m.%Y %H:%M:%S"))
    stummel("")
    stummel("Schritt 0: Die zu messende Kamera wird gesucht.")
    stummel("Das dauert normalerweise unter 20 Sekunden. Bleibt diese Datei")
    stummel("laenger als eine Minute unveraendert, haengt die KAMERA-SUCHE -")
    stummel("dann bitte einmal mit fester Kamera nachmessen:")
    stummel("  fexobooth.exe --kamera-test --kamera-index 0")
    stummel.schritt_name = "Kamera-Suche"
    stummel.schritt_start = stummel.start
    stummel.speichern()

    protokoll: List[str] = []

    def arbeit():
        from src.camera.webcam import WebcamManager
        kameras = WebcamManager.list_cameras()
        return kameras, WebcamManager.find_best_camera(kameras)

    t0 = time.time()
    wert, fehler = _mit_zeitlimit(arbeit, zeitlimit)
    dauer = time.time() - t0

    if fehler == "zeitlimit":
        # Der aufgegebene Such-Thread haelt jetzt Kamera UND Hardware-Sperre.
        # Genau wie bei den Messschritten gilt: kein zweiter Zugriff mehr.
        _KAMERA_BLEIBT_BELEGT = True
        protokoll.append("Kamera-Suche nach %.0f s aufgegeben - eine Kamera antwortet nicht."
                         % dauer)
        protokoll.append("Es wird mit Index 0 weitergemessen; die Werte unten koennen")
        protokoll.append("deshalb unvollstaendig sein (die Suche haelt die Kamera noch).")
        return 0, None, protokoll

    if fehler:
        protokoll.append("Kamera-Suche fehlgeschlagen (" + fehler[:60] + ") - nehme Index 0.")
        return 0, None, protokoll

    kameras, bester = wert if wert else ([], -1)
    _kamera_zugriff_vermerken()
    gefunden = ", ".join("[%s] %s" % (k.get("index"), k.get("name")) for k in kameras) or "keine"
    protokoll.append("Gefundene Kameras: " + gefunden + (" (%.0f s)" % dauer))

    if bester is not None and bester >= 0:
        name = next((k.get("name") for k in kameras if k.get("index") == bester), None)
        protokoll.append("Gewaehlt wurde die externe Kamera, die auch die Fotobox nimmt.")
        return bester, name, protokoll

    protokoll.append("Keine EXTERNE Kamera erkannt - gemessen wird Index 0.")
    protokoll.append("Auf dem Miix ist das die interne, abgeklebte Tablet-Kamera:")
    protokoll.append("Sie laesst sich oeffnen, liefert aber nie ein Bild.")
    return 0, None, protokoll


# ----------------------------------------------------------------------
# Die eigentlichen Kamera-Schritte (laufen IMMER im Wegwerf-Thread)
# ----------------------------------------------------------------------

def _schritt_dauerbetrieb(kamera_index: int, backend: int, breite: int, hoehe: int) -> dict:
    """Kompletter Zyklus einer Zelle: oeffnen, messen, freigeben.

    Der Worker macht ALLES selbst und gibt nur fertige Zahlen zurueck. Der
    Hauptablauf fasst das `cap`-Objekt nie an — sonst wuerde er nach einem
    aufgegebenen Thread auf eine Kamera zugreifen, die diesem noch gehoert.
    """

    def arbeit() -> dict:
        cap = _oeffne(kamera_index, backend, breite, hoehe)
        if cap is None:
            return {"offen": False}
        try:
            ist_b, ist_h, fourcc = _zustand(cap)
            werte = _messe_lesen(cap)
        finally:
            try:
                cap.release()
            except Exception:
                pass
        werte.update({"offen": True, "ist_b": ist_b, "ist_h": ist_h, "fourcc": fourcc})
        return werte

    return _mit_sperre(arbeit)


def _schritt_umschalten(kamera_index: int, backend: int) -> dict:
    """Misst den Wechsel 640x480 -> 1920x1080 -> 640x480 (kompletter Zyklus)."""

    def arbeit() -> dict:
        cap = _oeffne(kamera_index, backend, 640, 480)
        if cap is None:
            return {"offen": False}
        try:
            gelesen = False
            for _ in range(AUFWAERM_BILDER):
                ok, _f = cap.read()
                gelesen = gelesen or ok
            if not gelesen:
                return {"offen": True, "bilder": False}

            t0 = time.perf_counter()
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            hoch_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            cap.read()
            erstes_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            runter_ms = (time.perf_counter() - t0) * 1000
        finally:
            try:
                cap.release()
            except Exception:
                pass

        return {
            "offen": True,
            "bilder": True,
            "hoch_ms": hoch_ms,
            "erstes_ms": erstes_ms,
            "runter_ms": runter_ms,
        }

    return _mit_sperre(arbeit)


# ----------------------------------------------------------------------
# Hauptablauf
# ----------------------------------------------------------------------

def messung_ausfuehren(kamera_index: int = 0,
                       melder: Optional[Callable[[int, int, str], None]] = None,
                       abbruch: Optional[threading.Event] = None,
                       kamera_name: Optional[str] = None,
                       herkunft: Optional[str] = None,
                       vorlauf: Optional[List[str]] = None) -> Optional[str]:
    """Fuehrt die komplette Messung aus und gibt den Pfad des Berichts zurueck.

    melder:   optional, wird nach jedem Schritt mit (nummer, gesamt, text)
              gerufen — aus dem Mess-Thread! Der Empfaenger muss Tk selbst ueber
              `after(0, ...)` bedienen.
    abbruch:  optional, wird ZWISCHEN zwei Schritten geprueft. Mitten in einem
              cv2-Aufruf geht das nicht (siehe `_mit_zeitlimit`).
    herkunft: Klartext, WIE die Messung gestartet wurde. Gehoert zwingend in den
              Bericht: Ueber den Admin-Knopf laeuft die komplette Fotobox-
              Software parallel weiter (Tk-Oberflaeche, Fortschrittsanzeige),
              ueber die BAT nicht. Auf einem 2-Kern-Atom druckt das die
              gemessenen Bilder/s nach unten — zwei Berichte derselben Box waeren
              ohne diese Zeile unbemerkt nicht vergleichbar.
    vorlauf:  Protokollzeilen der Kamera-Suche (siehe `kamera_suchen`).
    """
    global _KAMERA_BLEIBT_BELEGT
    # NICHT hart auf False: Hat schon die Kamera-Suche aufgeben muessen, gehoert
    # die Kamera bereits einem nicht stoppbaren Thread — das darf hier nicht
    # wieder vergessen werden.
    vorab_belegt = _KAMERA_BLEIBT_BELEGT

    b = Bericht()
    b.melder = melder

    backends = _backends()
    # 3 Aufloesungen je Backend (Abschnitt 1) + 1 Umschalt-Test je Backend
    # (Abschnitt 2) + 3 Aufbereitungs-Messungen (Abschnitt 3).
    b.gesamt_schritte = len(backends) * len(AUFLOESUNGEN) + len(backends) + len(AUFLOESUNGEN)

    opencv_log = _OpenCvMeldungen()
    opencv_log.start()

    # Backends, die schon bei 640x480 nichts geliefert haben. Fuer die lohnt
    # kein weiterer Versuch — sie wuerden nur dreimal ins Zeitlimit laufen.
    tote_backends = set()
    # Bilder aus Abschnitt 1 fuer Abschnitt 3 (je ~6 MB bei 1080p, werden
    # unmittelbar nach der Auswertung wieder freigegeben).
    bilder: Dict[Tuple[int, int], object] = {}
    ergebnisse: Dict[Tuple[str, int, int], dict] = {}
    aufgegeben = vorab_belegt
    if vorab_belegt:
        b.kamera_belegt = True

    def stop_grund() -> Optional[str]:
        """Warum darf der naechste Schritt nicht laufen? (None = er darf)"""
        if abbruch is not None and abbruch.is_set():
            return "Abbruch durch Bediener"
        if time.time() - b.start > GESAMT_BUDGET_SEKUNDEN:
            return "Gesamt-Zeitlimit erreicht"
        if aufgegeben:
            # Der aufgegebene Thread besitzt Kamera UND Sperre weiterhin.
            return GRUND_KAMERA_HAENGT
        return None

    def res_text(breite: int, hoehe: int) -> str:
        return str(breite) + "x" + str(hoehe)

    b.titel("FEXOBOOTH - KAMERA-MESSUNG")
    b("Zeitpunkt : " + time.strftime("%d.%m.%Y %H:%M:%S"))
    b("OpenCV    : " + cv2.__version__)
    try:
        from src import __version__ as fassung
        b("FexoBooth : " + fassung)
    except Exception:
        pass
    b("Kamera    : Index " + str(kamera_index) + (" - " + kamera_name if kamera_name else ""))
    b("Gestartet : " + (herkunft or "unbekannt"))
    if opencv_log.aktiv and opencv_log.pfad:
        b("OpenCV-Log: " + opencv_log.pfad)
    b("")
    b("Gemessen wird, ob die Kamera dauerhaft in 1920x1080 laufen kann.")
    b("Dann entfaellt das Umschalten pro Foto - und der Blitz passt zum Bild.")
    b("Bitte waehrenddessen nichts anderes auf der Box starten.")
    b("")
    b("SO SIND DIESE ZAHLEN ZU LESEN (bitte nicht ueberspringen):")
    b(" * Seit 2.4.37 wird der Codec wie in der Fotobox angefordert: erst die")
    b("   Aufloesung, DANN MJPG - und mit Nachpruefung. Bis 2.4.34 war es")
    b("   umgekehrt und ohne Pruefung, dort wurde vermutlich YUY2 gemessen.")
    b("   Aeltere Berichte sind mit diesem hier deshalb NICHT vergleichbar.")
    b(" * Vergleiche immer nur Berichte mit derselben Zeile 'Gestartet':")
    b("   Ueber den Admin-Knopf laeuft die Fotobox-Software waehrend der")
    b("   Messung mit und kostet auf diesem Tablet spuerbar Bilder/s.")
    b("   Fuer die 1080p-Entscheidung zaehlt der Lauf ueber die BAT.")
    if opencv_log.aktiv:
        b(" * Die OpenCV-Meldungen werden mitgeschrieben (Datei oben). Das ist")
        b("   fuer die Fehlersuche noetig, kostet aber bei sehr geschwaetzigen")
        b("   Treibern einen Hauch Messzeit - eher zu langsam als zu schnell.")
    if vorlauf:
        b("")
        b("Kamera-Auswahl:")
        for zeile in vorlauf:
            b("  " + zeile)
    b.speichern()

    try:
        # --------------------------------------------------------------
        b.titel("1. DAUERBETRIEB - wie viele Bilder pro Sekunde?")
        for backend_name, backend in backends:
            b("")
            b(backend_name + ":")
            b("  " + "Aufloesung".rjust(18) + " | " + "Bilder/s".rjust(9) + " | "
              + "pro Bild".rjust(10) + " | " + "davon Warten".rjust(13) + " | "
              + "davon Rechnen".rjust(14) + " | " + "langsamstes".rjust(11))
            b("  " + "-" * 88)

            for breite, hoehe in AUFLOESUNGEN:
                soll = res_text(breite, hoehe)
                b.schritt_beginnt(backend_name + " " + soll)

                grund = stop_grund()
                if grund:
                    b("  " + soll.rjust(18) + " | uebersprungen (" + grund + ")")
                    b.schritt_fertig()
                    continue

                if backend_name in tote_backends:
                    b("  " + soll.rjust(18) + " | uebersprungen - Backend lieferte bei 640x480"
                      + " keine Bilder (bei Bedarf einzeln nachmessen)")
                    b.schritt_fertig()
                    continue

                limit = ZEITLIMIT_JE_AUFLOESUNG.get((breite, hoehe), 50.0)
                # Beruhigungspause VOR dem Zugriff — greift damit auf jedem
                # Ausgang der letzten Zelle, auch nach einem Fehlversuch.
                _kamera_ruhe()
                t_start = time.time()
                wert, fehler = _mit_zeitlimit(
                    lambda bb=backend, w=breite, h=hoehe: _schritt_dauerbetrieb(kamera_index, bb, w, h),
                    limit,
                )
                dauer = time.time() - t_start
                _kamera_zugriff_vermerken()
                opencv_log.deckeln_pruefen()

                if fehler == "zeitlimit":
                    # Ab hier ist die Kamera fuer diesen Prozess verloren.
                    aufgegeben = True
                    b.kamera_belegt = True
                    _KAMERA_BLEIBT_BELEGT = True
                    b("  " + soll.rjust(18) + " | abgebrochen nach " + ("%.0f s" % dauer)
                      + " - Kamera antwortete nicht")
                    if (breite, hoehe) == AUFLOESUNGEN[0]:
                        tote_backends.add(backend_name)
                    b.schritt_fertig()
                    continue

                if fehler:
                    b("  " + soll.rjust(18) + " | Fehler: " + fehler[:60])
                    b.schritt_fertig()
                    continue

                if wert is None or wert.get("gesperrt"):
                    b("  " + soll.rjust(18)
                      + " | Kamera von anderem Programmteil belegt, uebersprungen")
                    b.schritt_fertig()
                    continue

                if not wert.get("offen"):
                    b("  " + soll.rjust(18) + " | Kamera liess sich nicht oeffnen")
                    if (breite, hoehe) == AUFLOESUNGEN[0]:
                        tote_backends.add(backend_name)
                    b.schritt_fertig()
                    continue

                ist_b = wert.get("ist_b", 0)
                ist_h = wert.get("ist_h", 0)
                fourcc = wert.get("fourcc", "unbekannt")

                if wert.get("n", 0) <= 0:
                    b("  " + soll.rjust(18) + " | keine Bilder erhalten (0 von "
                      + str(wert.get("versuche", 0)) + " Versuchen, " + fourcc + ")")
                    if (breite, hoehe) == AUFLOESUNGEN[0]:
                        tote_backends.add(backend_name)
                    b.schritt_fertig()
                    continue

                ergebnisse[(backend_name, breite, hoehe)] = wert
                # Ein Bild fuer Abschnitt 3 aufheben (nur das erste je
                # ANGEFORDERTER Aufloesung — Abschnitt 3 sucht unter genau
                # diesem Schluessel und weist die echte Groesse dann selbst aus).
                if wert.get("bild") is not None and bilder.get((breite, hoehe)) is None:
                    bilder[(breite, hoehe)] = wert["bild"]
                wert["bild"] = None

                hinweise = ""
                if (ist_b, ist_h) != (breite, hoehe):
                    hinweise += "   <-- angefordert war " + soll
                if fourcc != "MJPG":
                    hinweise += "   <-- nicht MJPG!"
                if wert["n"] < wert.get("versuche", wert["n"]):
                    hinweise += "   <-- nur " + str(wert["n"]) + " von " \
                        + str(wert["versuche"]) + " Bildern erhalten"

                b("  " + (res_text(ist_b, ist_h) + " " + fourcc).rjust(18) + " | "
                  + ("%.1f" % wert["fps"]).rjust(9) + " | "
                  + ("%.1f ms" % wert["mittel"]).rjust(10) + " | "
                  + ("%.1f ms" % wert["warten"]).rjust(13) + " | "
                  + ("%.1f ms" % wert["rechnen"]).rjust(14) + " | "
                  + ("%.1f ms" % wert["max"]).rjust(11) + hinweise)
                b.schritt_fertig()

        # --------------------------------------------------------------
        b.titel("2. UMSCHALTEN DER AUFLOESUNG (der eigentliche Uebeltaeter)")
        b("So laeuft es heute bei JEDEM Foto:")
        b("Vorschau 640x480 -> Foto 1920x1080 -> zurueck auf 640x480.")

        for backend_name, backend in backends:
            b.schritt_beginnt("Umschalt-Test " + backend_name)
            b("")
            b(backend_name + ":")

            grund = stop_grund()
            if grund:
                b("   uebersprungen (" + grund + ")")
                b.schritt_fertig()
                continue

            if backend_name in tote_backends:
                b("   uebersprungen - Backend lieferte bei 640x480 keine Bilder")
                b.schritt_fertig()
                continue

            _kamera_ruhe()
            t_start = time.time()
            wert, fehler = _mit_zeitlimit(
                lambda bb=backend: _schritt_umschalten(kamera_index, bb),
                ZEITLIMIT_UMSCHALTEN,
            )
            dauer = time.time() - t_start
            _kamera_zugriff_vermerken()
            opencv_log.deckeln_pruefen()

            if fehler == "zeitlimit":
                aufgegeben = True
                b.kamera_belegt = True
                _KAMERA_BLEIBT_BELEGT = True
                b("   abgebrochen nach " + ("%.0f s" % dauer) + " - Kamera antwortete nicht")
                b.schritt_fertig()
                continue
            if fehler:
                b("   Fehler: " + fehler[:80])
                b.schritt_fertig()
                continue
            if wert is None or wert.get("gesperrt"):
                b("   Kamera von anderem Programmteil belegt, uebersprungen")
                b.schritt_fertig()
                continue
            if not wert.get("offen"):
                b("   Kamera liess sich nicht oeffnen (belegt? anderes Programm laeuft?)")
                b.schritt_fertig()
                continue
            if not wert.get("bilder"):
                b("   Kamera geoeffnet, liefert aber keine Bilder - Messung ungueltig")
                b.schritt_fertig()
                continue

            b("   hochschalten 640x480 -> 1920x1080 : " + ("%.0f ms" % wert["hoch_ms"]).rjust(9))
            b("   erstes Bild danach                : " + ("%.0f ms" % wert["erstes_ms"]).rjust(9))
            b("   zurueck auf 640x480               : " + ("%.0f ms" % wert["runter_ms"]).rjust(9))
            b("   -> Luecke zwischen Blitz und Bild : "
              + ("%.0f ms" % (wert["hoch_ms"] + wert["erstes_ms"])).rjust(9))
            b.schritt_fertig()

        # --------------------------------------------------------------
        b.titel("3. BILDAUFBEREITUNG - lohnt 'erst verkleinern'?")
        b("Heute wird das VOLLE Bild gespiegelt und umgefaerbt und erst danach")
        b("verkleinert. Umgekehrt waere deutlich weniger Arbeit.")
        b("")
        b("Gerechnet wird auf den Bildern aus Abschnitt 1 - dafuer muss die")
        b("Kamera nicht noch einmal geoeffnet werden (das hat auf Box 224 am")
        b("13.08. schon einmal eine Box eingefroren).")
        if aufgegeben:
            b("")
            b("ACHTUNG: Weiter oben musste ein Kamera-Schritt aufgegeben werden.")
            b("Der aufgegebene Thread existiert noch (er wartet auf die Kamera und")
            b("rechnet dabei normalerweise nicht). Die Zeiten hier sind deshalb")
            b("brauchbar, aber nicht garantiert stoerungsfrei.")
        b("")
        b("  " + "Aufloesung".rjust(12) + " | " + "heute".rjust(10) + " | "
          + "erst verkleinern".rjust(18) + " | " + "Faktor".rjust(7))
        b("  " + "-" * 56)

        for breite, hoehe in AUFLOESUNGEN:
            soll = res_text(breite, hoehe)
            b.schritt_beginnt("Bildaufbereitung " + soll)

            grund = stop_grund()
            # Abschnitt 3 fasst die Kamera NICHT an - ein aufgegebener
            # Kamera-Thread ist hier also kein Grund zum Ueberspringen.
            if grund == GRUND_KAMERA_HAENGT:
                grund = None
            if grund:
                b("  " + soll.rjust(12) + " | uebersprungen (" + grund + ")")
                b.schritt_fertig()
                continue

            frame = bilder.get((breite, hoehe))
            if frame is None:
                b("  " + soll.rjust(12) + " | kein Bild aus Abschnitt 1 vorhanden - uebersprungen")
                b.schritt_fertig()
                continue

            # Echte Bildgroesse ausweisen: Die Kamera kann etwas anderes
            # geliefert haben, als angefordert war.
            try:
                ist = res_text(int(frame.shape[1]), int(frame.shape[0]))
            except Exception:
                ist = soll

            fehlertext = None
            heute_ms = neu_ms = 0.0
            try:
                heute_ms, neu_ms = _messe_aufbereitung(frame)
            except Exception as e:
                fehlertext = str(e)[:50]
            # Speicher sofort zurueckgeben: 1080p-BGR sind rund 6 MB je Bild,
            # und die Box hat nur 4 GB.
            bilder[(breite, hoehe)] = None
            frame = None

            if fehlertext:
                b("  " + ist.rjust(12) + " | Fehler beim Rechnen: " + fehlertext)
                b.schritt_fertig()
                continue

            faktor = (heute_ms / neu_ms) if neu_ms > 0 else 0.0
            b("  " + ist.rjust(12) + " | "
              + ("%.2f ms" % heute_ms).rjust(10) + " | "
              + ("%.2f ms" % neu_ms).rjust(18) + " | "
              + ("%.1fx" % faktor).rjust(7))
            b.schritt_fertig()

        bilder.clear()

        # --------------------------------------------------------------
        b.titel("4. URTEIL")
        # Ein Urteil aus einem unvollstaendigen Lauf darf nicht wie ein
        # vollstaendiges aussehen — sonst wird es spaeter falsch zitiert.
        if abbruch is not None and abbruch.is_set():
            b("ACHTUNG: Der Lauf wurde abgebrochen. Das Urteil stuetzt sich nur")
            b("auf die oben tatsaechlich gemessenen Zeilen.")
            b("")
        elif aufgegeben:
            b("ACHTUNG: Mindestens ein Schritt musste aufgegeben werden. Das")
            b("Urteil stuetzt sich nur auf die oben tatsaechlich gemessenen Zeilen.")
            b("")

        bestes_1080 = None
        for schluessel, werte in ergebnisse.items():
            backend_name, breite, hoehe = schluessel
            if (breite, hoehe) == (1920, 1080):
                if bestes_1080 is None or werte["fps"] > bestes_1080[1]["fps"]:
                    bestes_1080 = (backend_name, werte)

        if bestes_1080 is None:
            b("1920x1080 lieferte KEINE Bilder. Dauerbetrieb in 1080p ist auf dieser")
            b("Box damit keine Option. Bitte den Bericht mitschicken.")
            b("")
            b("Wenn oben ueberall 'keine Bilder erhalten' oder 'abgebrochen nach'")
            b("steht, kann es auch an der Kamera-AUSWAHL liegen: Auf manchen Boxen")
            b("ist Index 0 die interne, abgeklebte Tablet-Kamera - die laesst sich")
            b("oeffnen, liefert aber nie ein Bild. (Auf anderen Boxen ist Index 0")
            b("genau richtig, dort haengt die C922 auf 0.) Welche Kamera gemessen")
            b("wurde, steht oben im Kopf. Zum Gegenpruefen einmal")
            b("  fexobooth.exe --kamera-test --kamera-index 1")
            b("laufen lassen.")
        else:
            name, werte = bestes_1080
            b("Bester 1080p-Dauerbetrieb: " + ("%.1f" % werte["fps"]) + " Bilder/s ueber " + name)
            b("(" + ("%.0f" % werte["mittel"]) + " ms pro Bild, langsamstes "
              + ("%.0f" % werte["max"]) + " ms, Format " + str(werte.get("fourcc", "?")) + ")")
            b("   davon Warten auf die Kamera : " + ("%.0f" % werte["warten"]) + " ms")
            b("   davon Rechnen (Dekodieren)  : " + ("%.0f" % werte["rechnen"]) + " ms")
            if werte["rechnen"] > werte["warten"]:
                b("   -> Die CPU bremst. Schnelleres Dekodieren wuerde helfen.")
            else:
                b("   -> Die KAMERA bremst (Bildrate/USB), nicht die CPU. Eine")
                b("      schnellere Bildaufbereitung wuerde daran nichts aendern.")
            if werte.get("fourcc") != "MJPG":
                b("   ACHTUNG: Gemessen wurde " + str(werte.get("fourcc"))
                  + ", nicht MJPG - die Werte sind mit MJPG-Laeufen nicht vergleichbar.")
            b("")
            if werte["fps"] >= 12:
                b("=> GUT. Die Kamera kann dauerhaft in 1080p laufen. Das Umschalten")
                b("   kann entfallen - der Blitz wuerde dann zum Bild passen.")
            elif werte["fps"] >= 7:
                b("=> GRENZWERTIG. Etwa so fluessig wie die Vorschau heute (~8,5 Bilder/s).")
                b("   Machbar, aber nur zusammen mit dem Umbau aus Punkt 3.")
            else:
                b("=> ZU LANGSAM fuer dauerhaften 1080p-Betrieb. Bessere Wege:")
                b("   1280x720 als Mittelweg, oder beim Umschalten bleiben und")
                b("   stattdessen den Blitz auf den echten Ausloesemoment legen.")

        b("")
        b("Bitte die Datei kamera-messung.txt aus C:\\FexoBooth\\logs mitschicken.")

    except BaseException:
        # ABSICHTLICH BaseException: Auch Strg+C (KeyboardInterrupt) und
        # SystemExit sollen noch einen Bericht hinterlassen — bis hierher
        # gemessene Werte sind wertvoll und waeren sonst weg. Der Fehler wird
        # danach unveraendert weitergereicht (`raise`), nichts wird verschluckt.
        try:
            b("")
            b("!! Die Messung wurde unerwartet beendet. Der Bericht enthaelt nur")
            b("!! die bis dahin fertigen Werte.")
        except Exception:
            pass
        raise
    finally:
        # Hier darf NUR noch das Berichtsobjekt angefasst werden — ein
        # aufgegebener Worker-Thread koennte noch an einem `cap` haengen.
        opencv_log.stop()
        if abbruch is not None and abbruch.is_set():
            schluss = "ABGEBROCHEN"
        elif b.kamera_belegt:
            schluss = "FERTIG (mit aufgegebenen Schritten)"
        else:
            schluss = "FERTIG"
        b.schritt_name = ""
        try:
            b("")
            b("== ENDE DES BERICHTS ==")
        except Exception:
            pass
        pfad = b.speichern(status=schluss)
        try:
            print("")
            if pfad:
                print("Bericht gespeichert: " + pfad)
            else:
                print("WARNUNG: Bericht konnte nicht gespeichert werden.")
        except Exception:
            pass

    return pfad
