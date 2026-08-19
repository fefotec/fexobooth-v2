r"""Kamera-Messung: Wie schnell ist die Box bei welcher Aufloesung? (2.4.34)

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

Aufruf auf der Box:  fexobooth.exe --kamera-test
Ergebnis:            C:\FexoBooth\logs\kamera-messung.txt
"""

import time
from typing import List, Optional

import cv2
import numpy as np

try:                      # MSMF meldet lautstark, wenn eine Aufloesung nicht geht
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except Exception:
    pass


AUFLOESUNGEN = [(640, 480), (1280, 720), (1920, 1080)]
BILDER_PRO_MESSUNG = 30
AUFWAERM_BILDER = 5

# Groesse eines Foto-Fachs in der LiveView-Collage (aus dem Feld-Log:
# Template 1800x1200 wird auf 1002x668 skaliert, Fach 1 ist dann ~362x240).
FACH = (362, 240)


class Bericht:
    """Sammelt Zeilen fuer Konsole UND Datei gleichzeitig."""

    def __init__(self) -> None:
        self.zeilen: List[str] = []

    def __call__(self, text: str = "") -> None:
        print(text, flush=True)
        self.zeilen.append(text)

    def titel(self, text: str) -> None:
        self("")
        self("=" * 66)
        self("  " + text)
        self("=" * 66)

    def speichern(self) -> Optional[str]:
        from pathlib import Path

        ziele = []
        try:
            from src.utils.logging import LOG_PATH
            ziele.append(Path(LOG_PATH) / "kamera-messung.txt")
        except Exception:
            pass
        ziele.append(Path(r"C:\ProgramData\FexoBox") / "kamera-messung.txt")

        for ziel in ziele:
            try:
                ziel.parent.mkdir(parents=True, exist_ok=True)
                with open(ziel, "w", encoding="utf-8") as f:
                    f.write("\n".join(self.zeilen) + "\n")
                return str(ziel)
            except Exception:
                continue
        return None


def _oeffne(index: int, backend: int, breite: int, hoehe: int):
    """Kamera oeffnen und auf eine Aufloesung stellen."""
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, breite)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, hoehe)
    return cap


def _messe_lesen(cap, anzahl: int = BILDER_PRO_MESSUNG):
    """Dauer eines Bildes im DAUERBETRIEB - getrennt nach Warten und Rechnen.

    WICHTIG fuer die Auswertung: cap.read() macht ZWEI Dinge auf einmal und
    verschleiert damit die eigentliche Frage.
      grab()     = auf das naechste Bild der Kamera WARTEN (Bildrate/USB)
      retrieve() = das MJPG-Bild DEKODIEREN (reine Rechenzeit der CPU)

    Nur `retrieve` sagt uns, ob der Atom 1080p ueberhaupt schafft. Ist `grab`
    der grosse Posten, liegt es an der Kamera/USB - dann bringt eine schnellere
    Bildaufbereitung gar nichts.
    """
    for _ in range(AUFWAERM_BILDER):
        cap.read()

    warten, rechnen, gesamt = [], [], []
    for _ in range(anzahl):
        t0 = time.perf_counter()
        ok = cap.grab()
        t1 = time.perf_counter()
        if not ok:
            continue
        ok2, frame = cap.retrieve()
        t2 = time.perf_counter()
        if not ok2 or frame is None:
            continue
        warten.append((t1 - t0) * 1000)
        rechnen.append((t2 - t1) * 1000)
        gesamt.append((t2 - t0) * 1000)

    if not gesamt:
        return None

    def kennzahlen(werte):
        werte = sorted(werte)
        return {
            "mittel": sum(werte) / len(werte),
            "min": werte[0],
            "max": werte[-1],
        }

    g = kennzahlen(gesamt)
    return {
        "n": len(gesamt),
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


def messung_ausfuehren(kamera_index: int = 0) -> None:
    b = Bericht()

    b.titel("FEXOBOOTH - KAMERA-MESSUNG")
    b("Zeitpunkt : " + time.strftime("%d.%m.%Y %H:%M:%S"))
    b("OpenCV    : " + cv2.__version__)
    try:
        from src import __version__ as fassung
        b("FexoBooth : " + fassung)
    except Exception:
        pass
    b("Kamera    : Index " + str(kamera_index))
    b("")
    b("Gemessen wird, ob die Kamera dauerhaft in 1920x1080 laufen kann.")
    b("Dann entfaellt das Umschalten pro Foto - und der Blitz passt zum Bild.")
    b("Bitte waehrenddessen nichts anderes auf der Box starten.")

    ergebnisse = {}

    # ------------------------------------------------------------------
    b.titel("1. DAUERBETRIEB - wie viele Bilder pro Sekunde?")
    for backend_name, backend in _backends():
        b("")
        b(backend_name + ":")
        b("  " + "Aufloesung".rjust(12) + " | " + "Bilder/s".rjust(9) + " | "
          + "pro Bild".rjust(10) + " | " + "davon Warten".rjust(13) + " | "
          + "davon Rechnen".rjust(14) + " | " + "langsamstes".rjust(11))
        b("  " + "-" * 82)

        for breite, hoehe in AUFLOESUNGEN:
            cap = _oeffne(kamera_index, backend, breite, hoehe)
            if cap is None:
                b("  " + (str(breite) + "x" + str(hoehe)).rjust(12) + " | Kamera liess sich nicht oeffnen")
                continue

            ist_b = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            ist_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            werte = _messe_lesen(cap)
            cap.release()

            if werte:
                ergebnisse[(backend_name, breite, hoehe)] = werte
                hinweis = "" if (ist_b, ist_h) == (breite, hoehe) else "   <-- lieferte " + str(ist_b) + "x" + str(ist_h)
                b("  " + (str(ist_b) + "x" + str(ist_h)).rjust(12) + " | "
                  + ("%.1f" % werte["fps"]).rjust(9) + " | "
                  + ("%.1f ms" % werte["mittel"]).rjust(10) + " | "
                  + ("%.1f ms" % werte["warten"]).rjust(13) + " | "
                  + ("%.1f ms" % werte["rechnen"]).rjust(14) + " | "
                  + ("%.1f ms" % werte["max"]).rjust(11) + hinweis)
            else:
                b("  " + (str(breite) + "x" + str(hoehe)).rjust(12) + " | keine Bilder erhalten")
            time.sleep(0.3)

    # ------------------------------------------------------------------
    b.titel("2. UMSCHALTEN DER AUFLOESUNG (der eigentliche Uebeltaeter)")
    b("So laeuft es heute bei JEDEM Foto:")
    b("Vorschau 640x480 -> Foto 1920x1080 -> zurueck auf 640x480.")

    for backend_name, backend in _backends():
        cap = _oeffne(kamera_index, backend, 640, 480)
        if cap is None:
            b("")
            b(backend_name + ": Kamera liess sich nicht oeffnen (belegt? anderes Programm laeuft?)")
            continue
        gelesen = False
        for _ in range(AUFWAERM_BILDER):
            ok, _f = cap.read()
            gelesen = gelesen or ok
        if not gelesen:
            b("")
            b(backend_name + ": Kamera geoeffnet, liefert aber keine Bilder - Messung ungueltig")
            cap.release()
            continue

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
        cap.release()

        b("")
        b(backend_name + ":")
        b("   hochschalten 640x480 -> 1920x1080 : " + ("%.0f ms" % hoch_ms).rjust(9))
        b("   erstes Bild danach                : " + ("%.0f ms" % erstes_ms).rjust(9))
        b("   zurueck auf 640x480               : " + ("%.0f ms" % runter_ms).rjust(9))
        b("   -> Luecke zwischen Blitz und Bild : " + ("%.0f ms" % (hoch_ms + erstes_ms)).rjust(9))
        time.sleep(0.3)

    # ------------------------------------------------------------------
    b.titel("3. BILDAUFBEREITUNG - lohnt 'erst verkleinern'?")
    b("Heute wird das VOLLE Bild gespiegelt und umgefaerbt und erst danach")
    b("verkleinert. Umgekehrt waere deutlich weniger Arbeit.")
    b("")
    b("  " + "Aufloesung".rjust(12) + " | " + "heute".rjust(10) + " | "
      + "erst verkleinern".rjust(18) + " | " + "Faktor".rjust(7))
    b("  " + "-" * 56)

    for breite, hoehe in AUFLOESUNGEN:
        cap = _oeffne(kamera_index, cv2.CAP_DSHOW, breite, hoehe)
        if cap is None:
            continue
        for _ in range(AUFWAERM_BILDER):
            cap.read()
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            continue

        heute_ms, neu_ms = _messe_aufbereitung(frame)
        faktor = (heute_ms / neu_ms) if neu_ms > 0 else 0.0
        b("  " + (str(frame.shape[1]) + "x" + str(frame.shape[0])).rjust(12) + " | "
          + ("%.2f ms" % heute_ms).rjust(10) + " | "
          + ("%.2f ms" % neu_ms).rjust(18) + " | "
          + ("%.1fx" % faktor).rjust(7))
        time.sleep(0.3)

    # ------------------------------------------------------------------
    b.titel("4. URTEIL")
    bestes_1080 = None
    for schluessel, werte in ergebnisse.items():
        backend_name, breite, hoehe = schluessel
        if (breite, hoehe) == (1920, 1080):
            if bestes_1080 is None or werte["fps"] > bestes_1080[1]["fps"]:
                bestes_1080 = (backend_name, werte)

    if bestes_1080 is None:
        b("1920x1080 lieferte KEINE Bilder. Dauerbetrieb in 1080p ist auf dieser")
        b("Box damit keine Option. Bitte den Bericht mitschicken.")
    else:
        name, werte = bestes_1080
        b("Bester 1080p-Dauerbetrieb: " + ("%.1f" % werte["fps"]) + " Bilder/s ueber " + name)
        b("(" + ("%.0f" % werte["mittel"]) + " ms pro Bild, langsamstes "
          + ("%.0f" % werte["max"]) + " ms)")
        b("   davon Warten auf die Kamera : " + ("%.0f" % werte["warten"]) + " ms")
        b("   davon Rechnen (Dekodieren)  : " + ("%.0f" % werte["rechnen"]) + " ms")
        if werte["rechnen"] > werte["warten"]:
            b("   -> Die CPU bremst. Schnelleres Dekodieren wuerde helfen.")
        else:
            b("   -> Die KAMERA bremst (Bildrate/USB), nicht die CPU. Eine")
            b("      schnellere Bildaufbereitung wuerde daran nichts aendern.")
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

    pfad = b.speichern()
    print("")
    if pfad:
        print("Bericht gespeichert: " + pfad)
    else:
        print("WARNUNG: Bericht konnte nicht gespeichert werden - Ausgabe oben gilt trotzdem.")
