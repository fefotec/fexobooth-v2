"""Findet heraus, wie diese Canon wirklich ausgeloest werden will (2.4.51).

ANLASS (Christian, 24.08.2026): "das ergebnis ist katastrophal und nicht
verwendbar (...) ich denke die ganze herangehensweise ist fuer die dslr falsch.
dslr-booth laeuft ja auch auf der gleichen hardware und das problemlos fluessig
mit dslr!!"

Er hat recht. Bisher wurde nach jedem Testlauf EINE Vermutung geaendert und ein
neuer Build gebaut — das hat vier Runden gekostet und nichts gebracht.

Dieses Werkzeug dreht das um: Es probiert in EINEM Durchlauf alle sinnvollen
Kombinationen durch und misst, welche davon wirklich ein Foto liefert und wie
lange sie braucht. Danach ist keine Vermutung mehr noetig.

Aufruf auf der Box:

    fexobooth.exe --dslr-test

Es laeuft ohne die Oberflaeche, fasst nichts an der Konfiguration an und gibt
am Ende eine Empfehlung im Klartext aus.
"""

import time
from typing import Any, Dict, List, Optional

from src.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Die Varianten, die ueberhaupt in Frage kommen
# ---------------------------------------------------------------------------
#
# Zwei Fragen sind offen, und beide lassen sich nur an der Kamera beantworten:
#
#   1. Muss der Live-View fuer die Aufnahme aus sein?
#      Unser Ablauf schaltet ihn ab (kostet ~2,5 s pro Foto). Canons eigenes
#      Beispiel (EDSDK/.../sample/CSharp/.../TakePictureCommand.cs) tut das
#      NICHT — es sendet einfach den Ausloeser.
#
#   2. Welcher Ausloese-Befehl?
#      - TakePicture: gibt der Kamera den ganzen Ablauf inkl. Scharfstellen vor
#      - PressShutterButton: bildet den Fingerdruck nach (Canons Beispielweg)
#
VARIANTEN: List[Dict[str, Any]] = [
    {
        "name": "A",
        "titel": "Live-View AN + Ausloeser ganz durch (Canons Beispielweg)",
        "live_view": True,
        "methode": "shutter_completely",
    },
    {
        "name": "B",
        "titel": "Live-View AN + halb druecken, dann ganz durch ohne AF-Zwang",
        "live_view": True,
        "methode": "shutter_half_then_nonaf",
    },
    {
        "name": "C",
        "titel": "Live-View AN + TakePicture",
        "live_view": True,
        "methode": "take_picture",
    },
    {
        "name": "D",
        "titel": "Live-View AUS + TakePicture (bisheriger Weg der Box)",
        "live_view": False,
        "methode": "take_picture",
    },
    {
        "name": "E",
        "titel": "Live-View AUS + Ausloeser ganz durch",
        "live_view": False,
        "methode": "shutter_completely",
    },
]


def _trenner(zeichen: str = "=") -> None:
    print(zeichen * 74)


def _sende(edsdk, ref, methode: str) -> None:
    """Loest nach der gewaehlten Methode aus."""
    PRESS = edsdk.kEdsCameraCommand_PressShutterButton

    if methode == "take_picture":
        edsdk.send_command(ref, edsdk.kEdsCameraCommand_TakePicture, 0)
        return

    if methode == "shutter_completely":
        # Genau wie Canons Beispiel: ganz durch, dann loslassen.
        edsdk.send_command(
            ref, PRESS, edsdk.kEdsCameraCommand_ShutterButton_Completely
        )
        edsdk.send_command(
            ref, PRESS, edsdk.kEdsCameraCommand_ShutterButton_OFF
        )
        return

    if methode == "shutter_half_then_nonaf":
        edsdk.send_command(
            ref, PRESS, edsdk.kEdsCameraCommand_ShutterButton_Halfway
        )
        time.sleep(0.35)
        edsdk.send_command(
            ref, PRESS, edsdk.kEdsCameraCommand_ShutterButton_Completely_NonAF
        )
        edsdk.send_command(
            ref, PRESS, edsdk.kEdsCameraCommand_ShutterButton_OFF
        )
        return

    raise ValueError(f"Unbekannte Methode: {methode}")


def _karte_zaehlen(edsdk, ref) -> int:
    """Bilder auf der Speicherkarte zaehlen (frisch, nicht aus dem Zwischenspeicher)."""
    try:
        anzahl, folder = edsdk._zaehle_bilder_frisch(ref)
        if folder:
            edsdk.release(folder)
        return anzahl
    except Exception as e:
        logger.debug(f"Kartenzaehlung fehlgeschlagen: {e}")
        return -1


def _teste_variante(kamera, edsdk, variante: Dict[str, Any], wartezeit: float) -> Dict[str, Any]:
    """Probiert eine Variante und misst, ob und wie schnell ein Foto kommt."""
    ref = kamera._camera_ref
    name = variante["name"]
    ergebnis: Dict[str, Any] = {
        "name": name,
        "titel": variante["titel"],
        "erfolg": False,
        "sekunden": None,
        "quelle": None,
        "hinweis": "",
    }

    print()
    _trenner("-")
    print(f"  Variante {name}: {variante['titel']}")
    _trenner("-")

    try:
        # Live-View in den gewuenschten Zustand bringen
        if variante["live_view"]:
            if not kamera._live_view_active:
                kamera.start_live_view()
                time.sleep(0.6)
            zustand = "an" if kamera._live_view_active else "wollte nicht angehen"
        else:
            if kamera._live_view_active:
                kamera.stop_live_view()
                time.sleep(0.5)
            zustand = "aus"
        print(f"  Live-View: {zustand}")

        # Ausgangslage merken: Karte UND Rueckkanal
        vorher_karte = _karte_zaehlen(edsdk, ref)
        vorher_events = kamera._events_gesehen
        while not kamera._photo_queue.empty():
            try:
                kamera._photo_queue.get_nowait()
            except Exception:
                break

        print(f"  Bilder auf der Karte vorher: "
              f"{vorher_karte if vorher_karte >= 0 else 'keine Karte'}")
        print(f"  Ausloesen …")

        start = time.time()
        kamera._aktueller_capture_id = f"diagnose-{name}-{int(start * 1000)}"
        edsdk.im_kamera_faden(kamera._capture_scharfschalten)
        _sende(edsdk, ref, variante["methode"])

        # Warten und dabei BEIDE Wege beobachten
        while time.time() - start < wartezeit:
            if not kamera._photo_queue.empty():
                queue_capture, daten = kamera._photo_queue.get_nowait()
                if queue_capture != kamera._aktueller_capture_id:
                    print(f"  ! Fremdes Queue-Bild verworfen ({queue_capture})")
                    continue
                dauer = time.time() - start
                ergebnis.update(
                    erfolg=True, sekunden=round(dauer, 1), quelle="Direktdownload",
                    hinweis=f"{len(daten)/1024/1024:.1f} MB",
                )
                print(f"  ✓ Foto per Direktdownload nach {dauer:.1f}s "
                      f"({len(daten)/1024/1024:.1f} MB)")
                return ergebnis

            if vorher_karte >= 0:
                jetzt = _karte_zaehlen(edsdk, ref)
                if jetzt > vorher_karte:
                    dauer = time.time() - start
                    ergebnis.update(
                        erfolg=True, sekunden=round(dauer, 1), quelle="Speicherkarte",
                        hinweis=f"{vorher_karte} -> {jetzt}",
                    )
                    print(f"  ✓ Foto auf der Karte nach {dauer:.1f}s "
                          f"({vorher_karte} -> {jetzt})")
                    return ergebnis

            time.sleep(0.2)

        # Nichts gekommen — aber WAS genau ist ausgeblieben?
        neue_events = kamera._events_gesehen - vorher_events
        nachher_karte = _karte_zaehlen(edsdk, ref)
        ergebnis["hinweis"] = (
            f"Karte {vorher_karte}->{nachher_karte}, "
            f"{neue_events} Rueckmeldungen der Kamera"
        )
        print(f"  ✗ Kein Foto in {wartezeit:.0f}s. {ergebnis['hinweis']}")
        return ergebnis

    except Exception as e:
        ergebnis["hinweis"] = f"Fehler: {e}"
        print(f"  ✗ Abbruch: {e}")
        return ergebnis
    finally:
        kamera._capture_accepting = False
        kamera._aktueller_capture_id = None
        kamera._capture_gestartet = 0.0
        # Ausloeser sicherheitshalber loslassen — bleibt er gedrueckt, ignoriert
        # die Kamera den naechsten Befehl.
        try:
            edsdk.send_command(
                ref, edsdk.kEdsCameraCommand_PressShutterButton,
                edsdk.kEdsCameraCommand_ShutterButton_OFF,
            )
        except Exception:
            pass
        time.sleep(1.2)  # Kamera zwischen den Versuchen zur Ruhe kommen lassen


def run(wartezeit: float = 8.0) -> int:
    """Fuehrt den Test durch. Rueckgabe: 0 wenn eine Variante funktioniert hat."""
    _trenner()
    print("  FEXOBOOTH — DSLR-AUSLOESETEST")
    _trenner()
    print()
    print("  Probiert der Reihe nach durch, wie diese Kamera ausgeloest werden")
    print("  will. Dauert etwa eine Minute. Bitte die Kamera auf ein normales")
    print("  Motiv richten (nicht auf eine weisse Wand — sonst findet der")
    print("  Autofokus nichts und das Ergebnis ist nicht aussagekraeftig).")
    print()

    try:
        from src.camera import edsdk
        from src.camera.canon import CanonCameraManager
    except Exception as e:
        print(f"  FEHLER: Canon-Unterstuetzung nicht ladbar: {e}")
        return 2

    kamera = CanonCameraManager()
    print("  Kamera wird geoeffnet …")
    if not kamera.initialize():
        print()
        print("  FEHLER: Keine Canon gefunden oder Verbindung nicht moeglich.")
        print("  Pruefen: Kamera an? USB-Kabel? Steht sie im Auto-Modus statt")
        print("  in einem Kreativprogramm (P/Av/Tv/M)?")
        return 2

    print(f"  Verbunden mit: {kamera._camera_info.get('name', '?')}")
    modus = "Direktdownload (keine Karte)" if kamera._use_host_download else "Speicherkarte"
    print(f"  Die Box wuerde aktuell nutzen: {modus}")
    if kamera._use_host_download and not kamera._host_storage_ready:
        print("  FEHLER: Host-Speicher wurde von der Kamera nicht bestätigt.")
        kamera.release()
        return 2
    if kamera._use_host_download:
        print("  Host-Speicher: beim Session-Aufbau bestätigt")

    ergebnisse: List[Dict[str, Any]] = []
    try:
        for variante in VARIANTEN:
            ergebnisse.append(_teste_variante(kamera, edsdk, variante, wartezeit))
    finally:
        try:
            kamera.release()
        except Exception:
            pass

    # ---------------- Auswertung ----------------
    print()
    _trenner()
    print("  ERGEBNIS")
    _trenner()
    print()

    erfolgreiche = [e for e in ergebnisse if e["erfolg"]]

    for e in ergebnisse:
        if e["erfolg"]:
            print(f"  ✓ {e['name']}  {e['sekunden']:>4.1f}s  ueber {e['quelle']:<16} {e['titel']}")
        else:
            print(f"  ✗ {e['name']}     —                      {e['titel']}")
            if e["hinweis"]:
                print(f"       {e['hinweis']}")

    print()
    if not erfolgreiche:
        print("  KEINE Variante hat ein Foto geliefert.")
        print()
        print("  Das spricht dafuer, dass die Kamera selbst die Aufnahme")
        print("  verweigert — nicht die Software. Haeufigste Gruende:")
        print("    - Programmwahlrad steht auf Video oder einem gesperrten Modus")
        print("    - Objektiv meldet sich nicht (Kontakte, nicht eingerastet)")
        print("    - Akku/Netzteil zu schwach fuer die Aufnahme")
        print("    - Karte schreibgeschuetzt (kleiner Schieber an der Karte)")
        print()
        print("  Gegenprobe: Am Kameragehaeuse selbst ausloesen. Kommt dabei")
        print("  ein Bild, liegt es an der Ansteuerung; kommt keins, an der Kamera.")
        return 1

    schnellste = min(erfolgreiche, key=lambda e: e["sekunden"])
    print(f"  EMPFEHLUNG: Variante {schnellste['name']} — {schnellste['titel']}")
    print(f"  Sie war mit {schnellste['sekunden']}s die schnellste "
          f"(ueber {schnellste['quelle']}).")
    print()
    print("  Diese Ausgabe bitte an Claude schicken — danach wird der Ablauf")
    print("  der Box genau darauf umgestellt, ohne weiteres Ausprobieren.")
    return 0
