"""Webcam-Manager mit OpenCV"""

import cv2
import numpy as np
import ctypes
import json
import re
import time
import threading
from typing import Optional, Tuple

from .base import CameraManager
from src.utils.logging import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────
# EINE Sperre fuer JEDEN Kamera-Hardwarezugriff (2.4.31)
# ─────────────────────────────────────────────
# Absturz-Beweis (Box 044, absturz.log vom 19.08.2026, Code 0xc0000374 =
# HEAP CORRUPTION). Der faulthandler zeigte ZWEI Threads, die gleichzeitig
# DirectShow-Kameras oeffneten:
#
#   Thread A: src\app.py:2568 in _camera_status_probe   -> cv2.VideoCapture(...)
#   Thread B: src\camera\webcam.py:519 in list_cameras  -> cv2.VideoCapture(...)
#
# Ursache: `list_cameras()` ist eine @staticmethod und lief damit voellig
# an `self._camera_lock` vorbei — das ist eine INSTANZ-Sperre und schuetzt
# nur die Methoden am Objekt. Zwei parallele DirectShow-Oeffnungen auf
# denselben Geraeteindex zerlegen den Heap des Prozesses; Windows meldet das
# spaeter als Absturz in ntdll.dll (0xc0000005 / 0xc0000374).
#
# Deshalb: EINE modulweite Sperre, die sowohl die Instanz-Methoden als auch
# die statische Suche benutzen. Reentrant (RLock), damit verschachtelte
# Aufrufe im selben Thread nicht blockieren.
_CAMERA_HW_LOCK = threading.RLock()


def camera_hardware_lock() -> threading.RLock:
    """Sperre fuer JEDEN direkten Kamerazugriff — auch ausserhalb dieser Datei.

    Wer selbst `cv2.VideoCapture(...)` aufruft (z.B. die Kamera-Pruefung in
    app.py), MUSS diese Sperre nehmen. Sonst ist der Absturz zurueck.
    """
    return _CAMERA_HW_LOCK


# ═══════════════════════════════════════════════════════════════════════
# KAMERA-ERKENNUNG (2.4.40) — WARUM DAS HIER SO AUSSIEHT
# ═══════════════════════════════════════════════════════════════════════
# MELDUNG CHRISTIAN, 20.08.2026:
#   "der test zeigt 0 gefundene kamera aber die logitech ist ja dran."
#
# BEWEISKETTE AUS DEM BOX-LOG (20.08.2026):
#   10:27:31  DirectShow-Enumeration fehlgeschlagen: ... timed out after 10 seconds
#   10:27:31  DirectShow-Enumeration fehlgeschlagen, nutze PnP-Fallback
#   10:27:36  PnP Kamera-Abfrage fehlgeschlagen:     ... timed out after 5 seconds
#   10:27:36  Keine externe Kamera gefunden! Interne Kameras ignoriert: ['Kamera 0']
#   10:27:37  Kamera gefiltert (Ghost): [0] Kamera 0
#   10:27:47  DirectShow Kamera-Namen: ['c922 Pro Stream Webcam']   <- 11 s spaeter OK
#
# DER DENKFEHLER IN EINEM SATZ:
#   Eine fehlgeschlagene NAMENSABFRAGE wurde als Beweis gewertet, dass die
#   Kamera INTERN ist. Das sind zwei voellig verschiedene Dinge.
#   Die Kamera stand ueberhaupt nur in der Liste, WEIL cv2 sie oeffnen
#   konnte — sie ist also nachweislich da.
#
# WARUM DIE ALTE ABFRAGE SCHEITERTE:
#   `powershell Add-Type -TypeDefinition <C#>` startet bei JEDEM Aufruf einen
#   Prozess, laedt die CLR und ruft csc.exe zum Kompilieren auf. Gemessen:
#   ~4 ms echte Arbeit in ~560–670 ms Verpackung. Auf dem Atom x5-Z8350 mit
#   eMMC skaliert genau diese Verpackung und reisst die 10-s-Grenze — das ist
#   die Ursache der Fehlmeldung, nicht die Kamera. Dieselbe COM-Kette
#   in-process ueber ctypes braucht 3–25 ms.
#   Nebenbei fallen vier weitere Ausfallbilder weg: kein %TEMP% noetig, keine
#   frische DLL fuer Defender/AMSI, kein ConstrainedLanguageMode-Problem und
#   keine Codepage-Verstuemmelung bei Umlauten (BSTR ist UTF-16).
#   Und: subprocess.run(timeout=) ist auf Windows KEINE harte Grenze — nach
#   dem kill laeuft ein zweites communicate() OHNE Timeout, waehrend das
#   verwaiste csc.exe die Pipes haelt.
#
# DIE NEUE REGEL: DREI ANTWORTEN STATT ZWEI.
#   "extern" / "intern" / "unbestimmt" — und im dritten Fall wird NICHT
#   geraten. Eine unbestimmte Kamera wird nur unter EINER Bedingung doch noch
#   genommen: wenn genau dieses Geraet frueher schon einmal per Geraetename
#   UND eigenem USB-DevicePath als extern erkannt wurde und die Registry
#   (KSCATEGORY_VIDEO, Linked=1) es JETZT wieder als einzige Videoquelle des
#   Systems meldet.
#
# WAS DABEI FAST SCHIEFGEGANGEN WAERE (Nachbesserung nach Gegenpruefung):
#   Der erste Entwurf hat ein namenloses Geraet schon dann uebernommen, wenn
#   die Registry "genau eine USB-Videoquelle" meldete. Das beantwortet aber
#   eine ANDERE Frage: "haengt eine USB-Kamera am Bus?" statt "ist DIESER
#   cv2-Index diese Kamera?". Ist das USB-Kabel der C922 raus und die interne
#   Kamera selbst per USB angebunden (kommt bei Tablets vor), haette die Box
#   die abgeklebte Linse als Fotokamera gewaehlt. Nur der DevicePath stammt
#   aus DERSELBEN Aufzaehlung wie der Index und bindet beide wirklich
#   aneinander — deshalb ist er jetzt Pflicht, sowohl beim Merken als auch
#   beim Wiederverwenden.
#
# UNVERAENDERT BLEIBT DER GRUNDSATZ:
#   Die abgeklebte interne Tablet-Kamera bleibt gesperrt. Im Zweifel blinkt
#   weiterhin die Warnung — lieber das als schwarze Fotos beim Kunden.
#   Das gilt auch fuer den Index, der einfach nur in der Config steht: der
#   Grundwert 0 ist auf dem Miix genau diese interne Kamera. Ohne Beweis
#   (frische Erkennung, Gedaechtnis oder Handauswahl im Admin-Menue) wird er
#   abgeschaltet — siehe bestaetigter_index().
# ═══════════════════════════════════════════════════════════════════════

# Notbremse gegen eine kaputte Enumeration. Eine Fotobox hat 1–2 Kameras.
_MAX_DSHOW_GERAETE = 16

# HRESULT-Werte. Bewusst UNSIGNED vergleichen: `ctypes.windll` liefert c_int
# (vorzeichenbehaftet), 0x80010106 kommt also als -2147417850 zurueck.
# Deshalb jeden Rueckgabewert mit & 0xFFFFFFFF normalisieren.
_S_OK = 0x00000000
_S_FALSE = 0x00000001
_RPC_E_CHANGED_MODE = 0x80010106

# COM-Bezeichner der DirectShow-Kette — identisch zu dem, was der alte
# C#-Code ueber PowerShell gemacht hat (und identisch zu dem, was OpenCV
# CAP_DSHOW intern tut; nur deshalb stimmt die Reihenfolge mit den Indizes).
_CLSID_SYSTEM_DEVICE_ENUM = "{62BE5D10-60EB-11d0-BD3B-00A0C911CE86}"
_IID_ICREATE_DEV_ENUM = "{29840822-5B84-11D0-BD3B-00A0C911CE86}"
_CLSID_VIDEO_INPUT_CATEGORY = "{860BB310-5D01-11D0-BD3B-00A0C911CE86}"
_IID_IPROPERTY_BAG = "{55272A00-42CB-11CE-8135-00AA004BB851}"

# Registry-Gegenprobe: Geraeteklasse KSCATEGORY_VIDEO.
# WICHTIG: NICHT KSCATEGORY_CAPTURE nehmen — dort stehen auch Mikrofone drin.
_KSCATEGORY_VIDEO = "{6994ad05-93ef-11d0-a3cc-00a0c9223196}"
_DEVICECLASSES_PFAD = r"SYSTEM\CurrentControlSet\Control\DeviceClasses"

# Gedaechtnis- und Diagnosedatei (ProgramData, update-sicher).
_ERKENNUNG_DATEI = "kamera_erkennung.json"
_ERKENNUNG_SCHEMA = 1

# Woran eine INTERNE Kamera am NAMEN zu erkennen ist.
# Die deutschen Begriffe sind 2.4.40 dazugekommen: manche Treiber melden
# "Integrierte Kamera" statt "Integrated Camera". Ein falscher Treffer hier
# ist die SICHERE Richtung (Warnung blinkt), ein verpasster nicht.
_INTERNE_SCHLUESSELWOERTER = (
    "integrated", "internal", "ir camera", "infrarot",
    "front camera", "rear camera", "built-in", "avstream",
    "integrier", "eingebaut", "interne",
    # 2.4.40, Nachbesserung: die uebliche Namensfamilie der verbauten
    # Tablet-/Notebook-Kameras. "easycamera" ist der Lenovo-Name (und der
    # Miix 310 ist ein Lenovo), "user facing"/"world facing" die Windows-
    # Bezeichnung fuer Front-/Rueckkamera eines Tablets. Kein am Markt
    # ueblicher USB-Webcam-Name enthaelt diese Woerter — der Preis eines
    # Fehltreffers waere ohnehin nur die blinkende Warnung.
    "easycamera", "easy camera", "user facing", "world facing",
    "frontkamera", "rueckkamera", "tablet camera",
)

# Namen, die eine Kamera ZUVERLAESSIG als die externe Fotokamera ausweisen.
# WARUM DIE LISTE NOETIG IST: Der FriendlyName der Fotobox-Kamera lautet
# "C922 Pro Stream Webcam" — das Wort "logitech" kommt darin NICHT vor.
# Die alte Vorzugsregel ("logitech" im Namen) konnte deshalb nie greifen, und
# bei zwei extern eingestuften Geraeten gewann schlicht der kleinere Index —
# auf dem Miix ist das die abgeklebte interne Kamera.
_EXTERN_BEVORZUGT = (
    "logitech", "c922", "c920", "c925", "c930", "c270", "c310", "c505",
    "brio", "streamcam",
)

# Letzte Namensabfrage — nur fuer Log und Diagnosedatei, keine Entscheidung.
_LETZTE_ABFRAGE = {
    "namensquelle": "fehlt",   # "ctypes" | "powershell" | "fehlt"
    "abfrage_ok": False,
    "gemeldete_geraete": 0,
    "dauer_ms": 0,
}

# Letzter in die Diagnosedatei geschriebener Befund (Schreib-Bremse, siehe
# _erkennung_merken). Reiner Prozess-Zustand, ueberlebt keinen Neustart.
_LETZTE_MERKUNG = {"signatur": None, "zeit": 0.0}


class _GUID(ctypes.Structure):
    """Windows-GUID. Wird ueber CLSIDFromString befuellt — von Hand
    zusammengebaute Byte-Reihenfolgen sind eine klassische Fehlerquelle."""
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _VARIANT(ctypes.Structure):
    """Minimal-VARIANT: 8 Byte Kopf + Union.

    Die zwei Zeiger-Felder sorgen dafuer, dass die Struktur auf 32 Bit
    16 Byte und auf 64 Bit 24 Byte gross ist — also exakt so gross wie ein
    echter VARIANT. Zu klein waere ein Speicherfehler in fremdem Code.
    Wir lesen nur VT_BSTR (vt == 8), alles andere wird verworfen.
    """
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("reserviert1", ctypes.c_ushort),
        ("reserviert2", ctypes.c_ushort),
        ("reserviert3", ctypes.c_ushort),
        ("zeiger", ctypes.c_void_p),
        ("fuellung", ctypes.c_void_p),
    ]


_VT_BSTR = 8


def _hr(wert) -> int:
    """HRESULT vorzeichenlos machen (siehe Kommentar bei _S_OK)."""
    return int(wert) & 0xFFFFFFFF


def _com_methode(schnittstelle, slot: int, prototyp):
    """Holt Methode Nr. `slot` aus der vtable eines COM-Interfaces.

    Slot-Belegung (verifiziert, darf NICHT geraten werden):
      IUnknown          : 0 QueryInterface, 1 AddRef, 2 Release
      ICreateDevEnum    : 3 CreateClassEnumerator
      IEnumMoniker      : 3 Next
      IMoniker          : 9 BindToStorage  (IUnknown 0-2, IPersist 3,
                            IPersistStream 4-7, IMoniker ab 8)
      IPropertyBag      : 3 Read
    """
    vtable = ctypes.cast(schnittstelle, ctypes.POINTER(ctypes.c_void_p))[0]
    eintraege = ctypes.cast(vtable, ctypes.POINTER(ctypes.c_void_p))
    return prototyp(eintraege[slot])


def _com_freigeben(schnittstelle) -> None:
    """IUnknown::Release. Jedes geholte Interface MUSS hier durch —
    ein vergessenes Release ist auf einer Box, die tagelang laeuft, ein Leck."""
    if not schnittstelle:
        return
    try:
        prototyp = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        _com_methode(schnittstelle, 2, prototyp)(schnittstelle)
    except Exception:
        pass


def _guid_aus_text(text: str) -> _GUID:
    ole32 = ctypes.windll.ole32
    ole32.CLSIDFromString.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(_GUID)]
    ole32.CLSIDFromString.restype = ctypes.c_long
    kennung = _GUID()
    ergebnis = _hr(ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(kennung)))
    if ergebnis != _S_OK:
        raise OSError(f"CLSIDFromString({text}) -> 0x{ergebnis:08X}")
    return kennung


def _bag_text(lesen, bag, eigenschaft: str, oleaut32) -> str:
    """Liest eine Zeichenkette aus dem IPropertyBag eines DirectShow-Geraets.

    Fehlt die Eigenschaft (kommt vor, z.B. DevicePath bei manchen Treibern),
    ist das KEIN Fehler — dann gibt es eben keinen Zusatzbeweis.
    """
    variante = _VARIANT()
    oleaut32.VariantInit(ctypes.byref(variante))
    try:
        ergebnis = _hr(lesen(bag, ctypes.c_wchar_p(eigenschaft),
                             ctypes.byref(variante), None))
        if ergebnis != _S_OK or variante.vt != _VT_BSTR or not variante.zeiger:
            return ""
        # BSTR ist UTF-16 und nullterminiert -> c_wchar_p liefert eine
        # echte Python-Kopie. Die Kopie MUSS vor VariantClear entstehen.
        return ctypes.cast(ctypes.c_void_p(variante.zeiger), ctypes.c_wchar_p).value or ""
    except Exception:
        return ""
    finally:
        try:
            oleaut32.VariantClear(ctypes.byref(variante))
        except Exception:
            pass


def _dshow_geraete() -> Tuple[list, bool]:
    """Liest die DirectShow-Videogeraete DIREKT im Prozess (ctypes, kein PowerShell).

    Dieselbe COM-Kette wie frueher im C#-Code:
        ICreateDevEnum -> IEnumMoniker -> IMoniker -> IPropertyBag
    Pro Geraet werden ZWEI Eigenschaften gelesen: FriendlyName und DevicePath.

    Returns:
        (geraete, abfrage_ok)
        geraete    = [{"name": str, "device_path": str}, ...] in DirectShow-
                     Reihenfolge (= Reihenfolge der cv2-CAP_DSHOW-Indizes)
        abfrage_ok = True, wenn die Enumeration wirklich gelaufen ist.
                     Das ist der WICHTIGSTE Rueckgabewert: "0 Geraete gefunden"
                     und "ich konnte nicht nachsehen" sind zwei verschiedene
                     Aussagen — genau ihre Vermischung war der gemeldete Bug.
    """
    # WINFUNCTYPE erst hier bauen (ctypes cacht die Typen intern, kostet also
    # nichts) — so bleibt das Modul auch auf Nicht-Windows importierbar.
    p_create_enum = ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_ulong)
    p_next = ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_void_p, ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_ulong))
    p_bind_to_storage = ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
    p_bag_read = ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p,
        ctypes.c_void_p, ctypes.c_void_p)

    # windll, NICHT oledll! oledll wirft bei jedem HRESULT < 0 automatisch eine
    # OSError — dann fliegt die Funktion bei RPC_E_CHANGED_MODE (0x80010106)
    # raus, obwohl COM voellig in Ordnung ist. Nachgestellt und bestaetigt.
    ole32 = ctypes.windll.ole32
    oleaut32 = ctypes.windll.oleaut32

    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.restype = None
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID), ctypes.c_void_p, ctypes.c_ulong,
        ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoCreateInstance.restype = ctypes.c_long
    oleaut32.VariantInit.argtypes = [ctypes.c_void_p]
    oleaut32.VariantInit.restype = None
    oleaut32.VariantClear.argtypes = [ctypes.c_void_p]
    oleaut32.VariantClear.restype = ctypes.c_long

    # COINIT_APARTMENTTHREADED. Drei Antworten sind brauchbar:
    #   S_OK              = wir haben COM initialisiert
    #   S_FALSE           = war schon initialisiert (auch von uns)
    #   RPC_E_CHANGED_MODE= Thread laeuft bereits in einem ANDEREN Apartment
    #                       (typisch: Tk/Kamera-Thread). COM ist trotzdem
    #                       nutzbar — wir duerfen nur nicht uninitialisieren.
    co_ergebnis = _hr(ole32.CoInitializeEx(None, 0x2))
    if co_ergebnis not in (_S_OK, _S_FALSE, _RPC_E_CHANGED_MODE):
        logger.debug(f"CoInitializeEx abgelehnt: 0x{co_ergebnis:08X}")
        return [], False
    selbst_initialisiert = co_ergebnis in (_S_OK, _S_FALSE)

    geraete: list = []
    dev_enum = ctypes.c_void_p()
    enum_moniker = ctypes.c_void_p()
    try:
        klasse = _guid_aus_text(_CLSID_SYSTEM_DEVICE_ENUM)
        schnittstelle = _guid_aus_text(_IID_ICREATE_DEV_ENUM)
        ergebnis = _hr(ole32.CoCreateInstance(
            ctypes.byref(klasse), None, 1,  # CLSCTX_INPROC_SERVER
            ctypes.byref(schnittstelle), ctypes.byref(dev_enum)))
        if ergebnis != _S_OK or not dev_enum:
            logger.debug(f"ICreateDevEnum nicht erhalten: 0x{ergebnis:08X}")
            return [], False

        kategorie = _guid_aus_text(_CLSID_VIDEO_INPUT_CATEGORY)
        erzeuge_enum = _com_methode(dev_enum, 3, p_create_enum)
        ergebnis = _hr(erzeuge_enum(dev_enum, ctypes.byref(kategorie),
                                    ctypes.byref(enum_moniker), 0))
        if ergebnis == _S_FALSE or not enum_moniker:
            # Kategorie leer = KEIN Videogeraet am System. Die Abfrage hat
            # aber funktioniert -> abfrage_ok = True bei leerer Liste.
            return [], True
        if ergebnis != _S_OK:
            logger.debug(f"CreateClassEnumerator: 0x{ergebnis:08X}")
            return [], False

        naechster = _com_methode(enum_moniker, 3, p_next)
        bag_kennung = _guid_aus_text(_IID_IPROPERTY_BAG)

        while len(geraete) < _MAX_DSHOW_GERAETE:
            moniker = ctypes.c_void_p()
            geholt = ctypes.c_ulong(0)
            ergebnis = _hr(naechster(enum_moniker, 1, ctypes.byref(moniker),
                                     ctypes.byref(geholt)))
            if ergebnis != _S_OK or geholt.value != 1 or not moniker:
                break

            bag = ctypes.c_void_p()
            try:
                binden = _com_methode(moniker, 9, p_bind_to_storage)
                ergebnis = _hr(binden(moniker, None, None,
                                      ctypes.byref(bag_kennung), ctypes.byref(bag)))
                if ergebnis == _S_OK and bag:
                    lesen = _com_methode(bag, 3, p_bag_read)
                    geraete.append({
                        "name": _bag_text(lesen, bag, "FriendlyName", oleaut32).strip(),
                        "device_path": _bag_text(lesen, bag, "DevicePath", oleaut32).strip(),
                    })
                else:
                    # Geraet ist da, nur nicht lesbar. Platz MUSS trotzdem
                    # belegt werden, sonst verschieben sich alle folgenden
                    # Indizes — genau der Fehler, den wir hier abstellen.
                    geraete.append({"name": "", "device_path": ""})
            finally:
                _com_freigeben(bag)
                _com_freigeben(moniker)

        return geraete, True

    except Exception as e:
        # Absichtlich alles fangen: neuer COM-Code darf die Fotobox nie
        # mit ins Grab ziehen. Der PowerShell-Weg bleibt als Netz.
        logger.debug(f"DirectShow-Enumeration (ctypes) fehlgeschlagen: {e}")
        return [], False
    finally:
        _com_freigeben(enum_moniker)
        _com_freigeben(dev_enum)
        if selbst_initialisiert:
            try:
                ole32.CoUninitialize()
            except Exception:
                pass


# Laeuft (oder haengt) gerade eine DirectShow-Enumeration? Modulweit, weil
# ein haengender COM-Aufruf sonst bei JEDEM Suchlauf einen neuen Thread
# hinterlaesst (App-Start, Waechter alle 20 s, Admin-Menue, Messung).
_DSHOW_LAEUFT = threading.Event()
_DSHOW_ZEITGRENZE = 6.0


def _dshow_geraete_mit_zeitgrenze(zeitgrenze: float = _DSHOW_ZEITGRENZE) -> Tuple[list, bool]:
    """`_dshow_geraete()` mit harter Zeitgrenze — die EINZIGE Absicherung
    gegen einen haengenden Kameratreiber.

    WARUM UEBERHAUPT: `_dshow_geraete()` laeuft in-process. Bleibt die COM-
    Enumeration stehen (klassisch: ein halb abgestuerzter USB-Treiber haelt
    seinen Moniker), kehrt der aufrufende Thread NIE zurueck. Betroffen waeren
    'cam-autoselect' (Start), 'camera-check' (Waechter) und der Admin-Scan —
    und beim Waechter bliebe `_camera_check_running` fuer immer True, die
    Kameraerkennung waere bis zum Neustart still tot. Genau das war frueher
    durch `subprocess.run(timeout=10)` abgedeckt; mit dem Wechsel auf ctypes
    ist diese Grenze weggefallen und muss hier ersetzt werden.

    Der aufgegebene Thread wird NICHT getoetet (das geht bei einem haengenden
    COM-Aufruf nicht gefahrlos). Stattdessen merkt sich das Modul, dass noch
    eine Enumeration haengt, und ueberspringt den ctypes-Weg beim naechsten
    Mal sofort — dann greift das vorhandene Netz (PowerShell-Weg) und es
    entsteht kein Thread-Stau.
    """
    if _DSHOW_LAEUFT.is_set():
        logger.warning(
            "DirectShow-Enumeration haengt noch aus einem frueheren Aufruf — "
            "ctypes-Weg wird uebersprungen (Netz: PowerShell-Weg)."
        )
        return [], False

    behaelter: dict = {}

    def _arbeiter():
        try:
            behaelter["daten"] = _dshow_geraete()
        except Exception as e:      # pragma: no cover - Notnagel
            logger.debug(f"DirectShow-Enumeration (Thread) fehlgeschlagen: {e}")
            behaelter["daten"] = ([], False)
        finally:
            _DSHOW_LAEUFT.clear()

    _DSHOW_LAEUFT.set()
    arbeiter = threading.Thread(target=_arbeiter, daemon=True, name="dshow-enum")
    arbeiter.start()
    arbeiter.join(zeitgrenze)

    if arbeiter.is_alive():
        logger.warning(
            f"DirectShow-Enumeration nach {zeitgrenze:.0f} s aufgegeben — "
            f"Netz: PowerShell-Weg. (Der Thread laeuft im Hintergrund weiter; "
            f"bis er zurueckkommt, wird der ctypes-Weg uebersprungen.)"
        )
        return [], False

    return behaelter.get("daten", ([], False))


def _bus_aus_pfad(device_path: str) -> str:
    """Liefert 'usb', 'intern' oder '' (= unbekannt) aus einem DevicePath.

    DevicePath sieht typischerweise so aus:
        \\\\?\\usb#vid_046d&pid_085c#...    -> externe USB-Kamera
        \\\\?\\root#media#0000#...          -> intern eingebunden
    Der Bus ist ein INDIZ, kein Freibrief: manche Tablets binden ihre interne
    Kamera intern per USB an. Deshalb steht die Namensregel in
    klassifiziere_kameras() bewusst VOR dieser Regel.
    Unbekannte Praefixe geben '' zurueck — lieber "weiss nicht" als geraten.
    """
    text = (device_path or "").strip().lower()
    if not text:
        return ""
    text = text.replace("\\", "#")
    while text.startswith("#"):
        text = text[1:]
    if text.startswith("?#"):
        text = text[2:]
    if text.startswith("usb#"):
        return "usb"
    for praefix in ("root#", "acpi#", "pci#"):
        if text.startswith(praefix):
            return "intern"
    return ""


def _vid_pid_aus_text(text: str) -> str:
    """Zieht 'VID:PID' (z.B. '046D:085C') aus einem Geraetepfad/-instanzpfad.

    IGNORECASE ist PFLICHT, kein Schoenheitsfehler: die Registry schreibt
    'USB\\VID_046D&PID_085C\\…' in GROSSbuchstaben, der DirectShow-DevicePath
    dagegen '\\\\?\\usb#vid_046d&pid_085c#…' in KLEINbuchstaben. Ohne
    IGNORECASE haette der Vergleich fuer echte Kameras nie getroffen und das
    Gedaechtnis waere still wirkungslos geblieben (im Test aufgefallen).
    Ausgegeben wird immer in Grossbuchstaben, damit beide Quellen vergleichbar sind.
    """
    treffer = re.search(r"VID_([0-9A-Fa-f]{4}).{0,3}PID_([0-9A-Fa-f]{4})",
                        text or "", re.IGNORECASE)
    if not treffer:
        return ""
    return f"{treffer.group(1).upper()}:{treffer.group(2).upper()}"


def _geraet_ist_verbunden(winreg, klassen_schluessel, geraete_name: str) -> bool:
    """True nur, wenn unter dem Geraet ein Control\\Linked = 1 steht.

    ZWINGEND: Abgezogene Geraete bleiben als Registry-Schluessel stehen
    (Karteileichen). Ohne diese Pruefung wuerde eine laengst entfernte Kamera
    weiter mitgezaehlt — und die ganze Gegenprobe waere wertlos.
    """
    try:
        with winreg.OpenKey(klassen_schluessel, geraete_name) as geraet:
            nummer = 0
            while nummer < 32:
                try:
                    referenz = winreg.EnumKey(geraet, nummer)
                except OSError:
                    return False
                nummer += 1
                try:
                    with winreg.OpenKey(geraet, referenz + r"\Control") as control:
                        wert, _typ = winreg.QueryValueEx(control, "Linked")
                        if int(wert) == 1:
                            return True
                except (OSError, ValueError, TypeError):
                    continue
    except OSError:
        return False
    return False


def _geraete_instanz(winreg, klassen_schluessel, geraete_name: str) -> str:
    """Instanzpfad des Geraets, z.B. 'USB\\VID_046D&PID_085C\\ABC123'."""
    try:
        with winreg.OpenKey(klassen_schluessel, geraete_name) as geraet:
            wert, _typ = winreg.QueryValueEx(geraet, "DeviceInstance")
            if isinstance(wert, str) and wert.strip():
                return wert.strip()
    except (OSError, ValueError, TypeError):
        pass
    # Notweg: der Schluesselname selbst kodiert die Instanz
    # (##?#USB#VID_046D&PID_085C#ABC123#{guid}).
    text = (geraete_name or "").replace("#", "\\")
    while text.startswith("\\"):
        text = text[1:]
    if text.startswith("?\\"):
        text = text[2:]
    return text


def verbundene_videogeraete() -> dict:
    """Zweite, voellig unabhaengige Quelle: haengt JETZT eine USB-Videoquelle dran?

    Liest HKLM\\SYSTEM\\CurrentControlSet\\Control\\DeviceClasses\\
    {6994ad05-…} (KSCATEGORY_VIDEO) mit `winreg`. Kosten: 0,2–0,4 ms, kein
    Prozessstart, kein Admin-Recht, und es wird KEINE Hardware angefasst —
    passt damit auf die schwache Box-Hardware.

    Das ist das Signal, das dem Code bisher komplett gefehlt hat: eine
    Ja/Nein-Antwort ueber die physische Anbindung, unabhaengig von PowerShell
    und unabhaengig von irgendeinem Geraetenamen.

    ACHTUNG — diese Liste ist ALPHABETISCH und hat NICHTS mit der
    DirectShow-Reihenfolge zu tun. Sie darf deshalb NIEMALS einen cv2-Index
    benennen; genau dieser Fehler hat 2.4.x zur DirectShow-Umstellung
    gezwungen (Vorfall 10.04.2026, Intel-AVStream-Kamera).

    Returns:
        {"bekannt": bool, "gesamt": int, "usb": int, "vid_pid": [str, ...]}
        bekannt=False heisst "weiss nicht" — NICHT "nichts da".
    """
    unbekannt = {"bekannt": False, "gesamt": 0, "usb": 0, "vid_pid": []}
    try:
        import winreg
    except Exception:
        return unbekannt

    pfad = _DEVICECLASSES_PFAD + "\\" + _KSCATEGORY_VIDEO
    ergebnis = {"bekannt": False, "gesamt": 0, "usb": 0, "vid_pid": []}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, pfad) as klasse:
            nummer = 0
            while nummer < 200:
                try:
                    geraete_name = winreg.EnumKey(klasse, nummer)
                except OSError:
                    break
                nummer += 1
                if not _geraet_ist_verbunden(winreg, klasse, geraete_name):
                    continue
                instanz = _geraete_instanz(winreg, klasse, geraete_name)
                ergebnis["gesamt"] += 1
                if instanz.upper().startswith("USB\\"):
                    ergebnis["usb"] += 1
                    vid_pid = _vid_pid_aus_text(instanz)
                    if vid_pid:
                        ergebnis["vid_pid"].append(vid_pid)
        ergebnis["bekannt"] = True
    except OSError as e:
        # Schluessel fehlt oder ist nicht lesbar -> "weiss nicht".
        logger.debug(f"Registry-Gegenprobe nicht moeglich ({pfad}): {e}")
        return unbekannt
    except Exception as e:
        logger.debug(f"Registry-Gegenprobe fehlgeschlagen: {e}")
        return unbekannt
    return ergebnis


def klassifiziere_kameras(cameras: list) -> list:
    """Ordnet jede gefundene Kamera in 'extern' / 'intern' / 'unbestimmt' ein.

    DAS IST DIE KERNKORREKTUR: frueher gab es nur ZWEI Zustaende, und
    "Name unbekannt" landete stillschweigend bei "intern".

    Reihenfolge der Regeln (die Reihenfolge ist die halbe Sicherheit):
      1. Name enthaelt ein Intern-Schluesselwort  -> INTERN (schlaegt den Bus)
      2. DevicePath vorhanden und NICHT USB        -> INTERN
      3. echter Name vorhanden, kein Intern-Wort   -> EXTERN
      4. kein Name, aber DevicePath = USB          -> UNBESTIMMT (mit Indiz)
      5. sonst                                     -> UNBESTIMMT

    Schreibt 'einordnung', 'einordnung_grund' und 'bus' in die Eintraege.
    """
    for cam in cameras or []:
        name_lower = str(cam.get("name", "") or "").strip().lower()
        # Nur ein Name aus der DirectShow-Enumeration zaehlt als "echt".
        # "Kamera 0" ist ein Anzeigetext und darf NIE Entscheidungsgrundlage
        # sein — genau daran ist die alte Logik gescheitert.
        hat_echten_namen = (cam.get("namensquelle") == "dshow" and bool(name_lower))
        bus = _bus_aus_pfad(cam.get("device_path", ""))
        cam["bus"] = bus

        if hat_echten_namen and any(kw in name_lower for kw in _INTERNE_SCHLUESSELWOERTER):
            cam["einordnung"] = "intern"
            cam["einordnung_grund"] = "intern per Name (Schluesselwort im Geraetenamen)"
            continue

        if bus == "intern":
            cam["einordnung"] = "intern"
            cam["einordnung_grund"] = "intern per Bus (DevicePath ist kein USB-Geraet)"
            continue

        if hat_echten_namen:
            cam["einordnung"] = "extern"
            cam["einordnung_grund"] = "extern per Name"
            continue

        cam["einordnung"] = "unbestimmt"
        if bus == "usb":
            cam["einordnung_grund"] = "unbestimmt, Name fehlt (DevicePath = USB als Indiz)"
        else:
            cam["einordnung_grund"] = "unbestimmt, kein Geraetename ermittelbar"
    return cameras


def _erkennung_pfad():
    """Ort der Gedaechtnis-/Diagnosedatei (ProgramData, update-sicher)."""
    try:
        from src.storage.paths import persistent_data_path
        return persistent_data_path(_ERKENNUNG_DATEI)
    except Exception:
        import os
        from pathlib import Path
        basis = (os.environ.get("PROGRAMDATA")
                 or os.environ.get("ALLUSERSPROFILE") or r"C:\ProgramData")
        return Path(basis) / "FexoBox" / _ERKENNUNG_DATEI


def letzte_erkennung() -> dict:
    """Liest die Diagnosedatei. Leeres Dict = keine/kaputte Datei.

    Bewusst oeffentlich: der Heartbeat (company_network.py) meldet damit den
    Kamerazustand, OHNE eine neue Kamerasuche auszuloesen.
    """
    try:
        pfad = _erkennung_pfad()
        if not pfad.exists():
            return {}
        with open(pfad, "r", encoding="utf-8") as datei:
            daten = json.load(datei)
        return daten if isinstance(daten, dict) else {}
    except Exception as e:
        logger.debug(f"kamera_erkennung.json nicht lesbar: {e}")
        return {}


def _erkennung_schreiben(daten: dict) -> None:
    """Schreibt die Diagnosedatei. Fehler werden NUR geloggt.

    Diese Datei darf niemals einen Kamerapfad blockieren — sie ist Diagnose
    und Notnagel, nicht Betriebsvoraussetzung.
    """
    try:
        import os
        pfad = _erkennung_pfad()
        pfad.parent.mkdir(parents=True, exist_ok=True)
        # Erst vollstaendig daneben schreiben, dann in EINEM Schritt
        # umbenennen. Sonst kann ein Stromausfall (oder der parallel laufende
        # Mess-Prozess) eine halb geschriebene Datei hinterlassen — und das
        # Gedaechtnis, das die abgeklebte Kamera aussperren hilft, waere weg.
        # os.replace ist auf Windows atomar und ueberschreibt vorhandene Dateien.
        zwischendatei = pfad.with_suffix(pfad.suffix + ".tmp")
        with open(zwischendatei, "w", encoding="utf-8") as datei:
            json.dump(daten, datei, indent=2, ensure_ascii=False)
            datei.flush()
            os.fsync(datei.fileno())
        os.replace(zwischendatei, pfad)
    except Exception as e:
        logger.debug(f"kamera_erkennung.json nicht schreibbar: {e}")


def _gedaechtnis_kandidat(registry: dict) -> Optional[dict]:
    """Das gemerkte Geraet — aber nur, wenn es JETZT nachweislich wieder
    als EINZIGE Videoquelle des Systems am USB haengt.

    ═══ WARUM DIESE HUERDE SO HOCH IST (Nachbesserung 2.4.40) ═══
    Die Gegenpruefung hat zu Recht bemaengelt: Die Registry beantwortet die
    Frage "haengt eine USB-Kamera am Bus?" — aber NICHT die Frage "ist der
    cv2-Index N genau dieses Geraet?". Wer aus dem ersten das zweite
    schliesst, kann die abgeklebte interne Kamera auswaehlen, sobald sie
    selbst per USB angebunden ist (kommt bei Tablets vor, siehe
    _bus_aus_pfad). Deshalb gelten jetzt ALLE Bedingungen gleichzeitig:

      (a) Die Registry meldet GENAU EIN verbundenes Videogeraet, und das
          haengt am USB. Damit kann es die interne Kamera nur dann sein,
          wenn es ueberhaupt keine andere gibt — und dann muss ihre VID/PID
          zu (b) passen, was sie nur tut, wenn sie SELBST das gemerkte
          Geraet ist.
      (b) Die gemerkte VID/PID steht mit Linked=1 in der Registry.
      (c) Das Gedaechtnis stammt aus einer Erkennung MIT DevicePath
          ("beweis": "devicepath"). Nur dann war Index und Geraet damals
          wirklich aneinander gebunden; ein reiner Namenstreffer ohne
          DevicePath (PowerShell-Notweg) reicht ausdruecklich NICHT mehr.
      (e) Schema/Datei in Ordnung.

    KEIN Zeitablauf — das Risiko ist der Hardwaretausch, nicht das Alter.
    """
    if not registry.get("bekannt"):
        return None
    if registry.get("gesamt") != 1 or registry.get("usb") != 1:
        return None                                   # (a)

    daten = letzte_erkennung()
    if not daten or daten.get("schema") != _ERKENNUNG_SCHEMA:
        return None                                   # (e)

    # Das Gedaechtnis steht BEWUSST in einem eigenen Unterobjekt und wird nur
    # von einer frischen, per NAMEN UND DevicePath bestaetigten Erkennung
    # ueberschrieben. Waere es mit der laufenden Diagnose vermischt, wuerde
    # es sich beim ersten Zugriff selbst loeschen (im Test aufgefallen).
    gedaechtnis = daten.get("gedaechtnis")
    if not isinstance(gedaechtnis, dict):
        return None                                   # (e)
    if gedaechtnis.get("beweis") != "devicepath":
        return None                                   # (c)

    index = gedaechtnis.get("index")
    if not isinstance(index, int) or index < 0:
        return None

    gemerkt = str(gedaechtnis.get("vid_pid") or "").upper()
    if not gemerkt:
        return None
    jetzt = [str(v).upper() for v in registry.get("vid_pid", [])]
    if gemerkt not in jetzt:
        return None                                   # (b)

    # (g) Meldet die Geraeteaufzaehlung heute eine ANDERE Anzahl als beim
    # gemerkten Fund, ist mindestens ein Geraet dazugekommen oder
    # weggefallen — dann stimmt die Zuordnung Index <-> Geraet nicht mehr,
    # und genau die ist hier das Einzige, was zaehlt. Nur vergleichbar, wenn
    # die aktuelle Abfrage ueberhaupt lief.
    if _LETZTE_ABFRAGE.get("abfrage_ok") and gedaechtnis.get("gemeldete_geraete"):
        if int(_LETZTE_ABFRAGE.get("gemeldete_geraete", 0)) != int(
                gedaechtnis.get("gemeldete_geraete", 0)):
            return None                               # (g)
    return gedaechtnis


def bestaetigter_index(registry: Optional[dict] = None) -> int:
    """Index, der zuletzt per Geraetenamen UND DevicePath als EXTERN
    bestaetigt wurde und dessen Geraet gerade wieder am Bus haengt.

    Bewusst oeffentlich: Damit kann der Aufrufer (app.py) entscheiden, ob ein
    bestehender `camera_index` einen misslungenen Suchlauf ueberleben darf.
    "Der Index stand halt in der Config" ist KEIN Beweis dafuer, dass er auf
    die externe Kamera zeigt — auf einer frisch aufgesetzten Box steht dort
    die 0, und die 0 ist auf dem Miix die abgeklebte interne Kamera.

    Returns:
        Index >= 0 nur bei echtem Beweis, sonst -1.
    """
    if registry is None:
        registry = verbundene_videogeraete()
    gedaechtnis = _gedaechtnis_kandidat(registry)
    if not gedaechtnis:
        return -1
    index = gedaechtnis.get("index")
    return index if isinstance(index, int) and index >= 0 else -1


def _cache_kandidat(cameras: list, registry: dict, hat_interne: bool) -> Optional[int]:
    """Darf das GEDAECHTNIS im unbestimmten Fall den Ausschlag geben?

    Zusaetzlich zu _gedaechtnis_kandidat():
      (c) Anzahl der oeffenbaren Geraete weicht vom letzten Erfolg ab
      (d) der gemerkte Index ist gar nicht in der Liste
      (f) das Geraet auf diesem Index nennt selbst eine ANDERE VID/PID
          (dann ist es nachweislich nicht das gemerkte)
    """
    if hat_interne:
        return None
    gedaechtnis = _gedaechtnis_kandidat(registry)
    if not gedaechtnis:
        return None

    index = gedaechtnis["index"]
    # (c) Gleich viele OEFFENBARE Geraete wie beim gemerkten Fund? (Die
    # Gegenprobe auf die AUFGEZAEHLTEN Geraete steckt in _gedaechtnis_kandidat.)
    if gedaechtnis.get("geraete_anzahl") != len(cameras):
        return None                                   # (c)
    kamera = next((c for c in cameras if c.get("index") == index), None)
    if kamera is None:
        return None                                   # (d)

    eigene = _vid_pid_aus_text(kamera.get("device_path", ""))
    if eigene and eigene != str(gedaechtnis.get("vid_pid") or "").upper():
        return None                                   # (f)
    return index


def _erkennung_merken(cameras: list, registry: dict, ergebnis: dict,
                      gewaehlte_kamera: Optional[dict], bestaetigt: bool) -> None:
    """Schreibt Gedaechtnis + Diagnose in kamera_erkennung.json.

    WARUM UEBERHAUPT EINE DATEI: Im Feld gibt es heute KEIN Log (Logging
    laeuft nur mit --dev). Diese Datei ist damit das erste dauerhafte
    Diagnosemittel fuer genau diese Frage — und ueberbrueckt nebenbei
    Aussetzer wie den vom 20.08. (11 s spaeter war alles wieder gut).
    """
    # Unveraenderten Befund nicht dauernd neu schreiben. Im Blindzustand ruft
    # der Waechter alle 20 s hier an — das waeren ~180 Schreibvorgaenge pro
    # Stunde auf die eMMC des Miix, fuer immer denselben Inhalt. Bei gleichem
    # Befund hoechstens alle 5 Minuten schreiben; jede echte AENDERUNG geht
    # sofort raus, denn genau die ist die Diagnose.
    signatur = (ergebnis.get("zustand"), ergebnis.get("index"),
                len(cameras or []), _LETZTE_ABFRAGE.get("namensquelle"))
    jetzt = time.time()
    if (_LETZTE_MERKUNG["signatur"] == signatur
            and (jetzt - _LETZTE_MERKUNG["zeit"]) < 300):
        return
    _LETZTE_MERKUNG["signatur"] = signatur
    _LETZTE_MERKUNG["zeit"] = jetzt

    # Gedaechtnis: NUR eine frische Erkennung, die BEIDES hatte — einen
    # echten Geraetenamen (= extern) UND einen eigenen DevicePath am USB —
    # schreibt es neu. In allen anderen Faellen wird der bisherige Eintrag
    # unveraendert mitgenommen; sonst wuerde ausgerechnet der Notfall, fuer
    # den das Gedaechtnis gedacht ist, es beim ersten Mal loeschen.
    #
    # WARUM DER DevicePath PFLICHT IST (Nachbesserung 2.4.40):
    # Vorher durfte die VID/PID auch aus der Registry stammen, wenn genau ein
    # USB-Videogeraet gemeldet war. Damit merkte sich die Box im ungluecklichen
    # Fall die VID/PID eines Geraets, das mit dem gewaehlten cv2-Index gar
    # nichts zu tun haben muss — im schlimmsten Fall die der internen Kamera,
    # und der Fehlgriff haette sich fuer alle spaeteren Suchlaeufe zementiert.
    # Nur der DevicePath kommt aus DERSELBEN Aufzaehlung wie der Index und
    # bindet beide wirklich aneinander.
    vorherige = letzte_erkennung()
    gedaechtnis = vorherige.get("gedaechtnis") if isinstance(vorherige, dict) else None
    if not isinstance(gedaechtnis, dict):
        gedaechtnis = None

    if bestaetigt and gewaehlte_kamera and ergebnis.get("index", -1) >= 0:
        vid_pid = _vid_pid_aus_text(gewaehlte_kamera.get("device_path", ""))
        if vid_pid and gewaehlte_kamera.get("bus") == "usb":
            gedaechtnis = {
                "index": ergebnis["index"],
                "vid_pid": vid_pid,
                "name": str(gewaehlte_kamera.get("name", "") or ""),
                "beweis": "devicepath",
                "geraete_anzahl": len(cameras or []),
                # Wie viele Geraete meldete die Aufzaehlung damals? Nur so
                # laesst sich spaeter erkennen, dass zwar gleich viele Geraete
                # OEFFENBAR sind, insgesamt aber mehr existieren — dann stimmt
                # die Index-Zuordnung nicht mehr und das Gedaechtnis darf nicht
                # greifen.
                "gemeldete_geraete": int(_LETZTE_ABFRAGE.get("gemeldete_geraete", 0)),
                "zeitpunkt": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }

    _erkennung_schreiben({
        "schema": _ERKENNUNG_SCHEMA,
        "zeitpunkt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "namensquelle": _LETZTE_ABFRAGE.get("namensquelle", "fehlt"),
        "abfrage_ok": bool(_LETZTE_ABFRAGE.get("abfrage_ok")),
        "dauer_ms": int(_LETZTE_ABFRAGE.get("dauer_ms", 0)),
        "geraete_anzahl": len(cameras or []),
        "geraete": [
            {
                "index": cam.get("index"),
                "name": cam.get("name", ""),
                "namensquelle": cam.get("namensquelle", ""),
                "bus": cam.get("bus", ""),
                "usb": cam.get("bus") == "usb",
                "vid_pid": _vid_pid_aus_text(cam.get("device_path", "")),
                "einordnung": cam.get("einordnung", ""),
            }
            for cam in (cameras or [])
        ],
        "registry": registry,
        "gewaehlter_index": ergebnis.get("index", -1),
        "zustand": ergebnis.get("zustand", ""),
        "begruendung": ergebnis.get("begruendung", ""),
        "gedaechtnis": gedaechtnis,
    })


def waehle_kamera(cameras: list) -> dict:
    """Entscheidet, WELCHE Kamera benutzt wird — und sagt WARUM.

    Returns:
        {
          "index":       gewaehlter cv2-Index, -1 wenn nichts waehlbar
          "zustand":     "extern"             -> Kamera gefunden
                         "intern"             -> alle sichtbaren Geraete sind intern
                         "unbestimmt_einzeln" -> ein Geraet, kein Befund
                         "unbestimmt_mehrere" -> mehrere Geraete, kein Befund
                         "leer"               -> gar kein oeffenbares Geraet
          "begruendung": Klartext fuer Log, Diagnosedatei und Messbericht
          "kameras":     die eingeordnete Liste
          "bestaetigter_index":
                         Index, der zuletzt per Name UND DevicePath als extern
                         bestaetigt wurde und dessen Geraet gerade wieder am
                         Bus haengt; sonst -1 (siehe bestaetigter_index()).
        }

    Der Aufrufer darf `camera_index` NUR bei "intern" und
    "unbestimmt_mehrere" auf -1 setzen. Bei "unbestimmt_einzeln" und "leer"
    darf ein bestehender Index stehen bleiben — ABER NUR, wenn er dem
    "bestaetigter_index" entspricht. Ein Index, der einfach nur in der Config
    steht (Grundwert 0 = auf dem Miix die abgeklebte interne Kamera), ist kein
    Beweis fuer irgendetwas und muss weiterhin zur Warnung fuehren.
    """
    cameras = klassifiziere_kameras(cameras or [])
    registry = verbundene_videogeraete()
    sicherer_index = bestaetigter_index(registry)

    def fertig(index, zustand, begruendung, kamera=None, bestaetigt=False):
        ergebnis = {"index": index, "zustand": zustand,
                    "begruendung": begruendung, "kameras": cameras,
                    "bestaetigter_index": sicherer_index}
        _erkennung_merken(cameras, registry, ergebnis, kamera, bestaetigt)
        return ergebnis

    if not cameras:
        return fertig(-1, "leer", "kein oeffenbares DirectShow-Geraet gefunden")

    extern = [c for c in cameras if c.get("einordnung") == "extern"]
    interne = [c for c in cameras if c.get("einordnung") == "intern"]
    unbestimmt = [c for c in cameras if c.get("einordnung") == "unbestimmt"]

    # ── Priorität 1: eine bekannte Fotobox-Kamera am Namen ──────────────
    # Nachbesserung 2.4.40: Frueher stand hier nur "logitech". Der
    # FriendlyName der Fotobox-Kamera ist aber "C922 Pro Stream Webcam" —
    # ohne das Wort Logitech. Die Vorzugsregel konnte also NIE greifen, und
    # bei zwei extern eingestuften Geraeten entschied der kleinere Index.
    # Auf dem Miix ist der kleinere Index die abgeklebte interne Kamera.
    for cam in extern:
        name_lower = str(cam.get("name", "")).lower()
        if any(kw in name_lower for kw in _EXTERN_BEVORZUGT):
            return fertig(cam["index"], "extern",
                          f"extern per Name (bekannte Fotobox-Kamera): {cam.get('name')}",
                          cam, bestaetigt=True)

    # ── Priorität 2: extern MIT DevicePath-Beweis am USB ────────────────
    # Ein Geraet, dessen eigener DevicePath mit "usb#" beginnt, haengt
    # nachweislich am USB-Bus. Das schlaegt jedes namenlose Ratespiel und
    # vor allem den blossen Index-Vergleich.
    for cam in extern:
        if cam.get("bus") == "usb":
            return fertig(cam["index"], "extern",
                          f"extern per Name + USB-DevicePath: {cam.get('name')}",
                          cam, bestaetigt=True)

    # ── Priorität 3: jede andere per Namen extern eingestufte Kamera ────
    # Hier gibt es keinen DevicePath (typisch: PowerShell-Notweg). Der Name
    # ist dann das einzige Signal — das war schon vor 2.4.40 so. Ein solcher
    # Treffer wird bewusst NICHT ins Gedaechtnis geschrieben (siehe
    # _erkennung_merken), damit ein Fehlgriff sich nicht zementiert.
    if extern:
        cam = extern[0]
        if len(extern) > 1:
            logger.warning(
                f"Mehrere Kameras gelten per Namen als extern, keine davon mit "
                f"USB-Beweis: {[c.get('name') for c in extern]} — genommen wird "
                f"[{cam['index']}] {cam.get('name')}."
            )
        return fertig(cam["index"], "extern",
                      f"extern per Name (ohne DevicePath): {cam.get('name')}",
                      cam, bestaetigt=True)

    # Ab hier ist NICHTS sicher extern.
    if not unbestimmt:
        # Positiver Befund: alle sichtbaren Geraete sind nachweislich intern.
        namen = [c.get("name", "?") for c in cameras]
        return fertig(-1, "intern",
                      f"alle sichtbaren Geraete sind intern: {namen}")

    einzeln = (len(cameras) == 1 and len(unbestimmt) == 1)
    kandidat = unbestimmt[0] if einzeln else None

    if kandidat is not None:
        # ── EINZIGER Rettungsweg: das Gedaechtnis ───────────────────────
        # Nur ein Geraet, das frueher schon einmal per NAMEN als extern
        # erkannt wurde UND damals seinen eigenen USB-DevicePath nannte,
        # darf hier ohne Namen wieder zum Zug kommen — und auch nur, wenn
        # die Registry genau diese VID/PID JETZT als einzige Videoquelle
        # des Systems meldet (siehe _gedaechtnis_kandidat).
        #
        # ═══ WARUM DIE FRUEHERE REGEL (B) ERSATZLOS RAUS IST ═══
        # (B) hat ein namenloses Geraet allein deshalb zur externen Kamera
        # erklaert, weil die Registry genau eine USB-Videoquelle meldete.
        # Das ist ein Fehlschluss: geprueft wurde "es haengt eine USB-Kamera
        # am Bus", gebraucht wird aber "DIESER cv2-Index IST diese Kamera".
        # Der praktische Fall, der dabei schiefgeht: Das USB-Kabel der C922
        # ist raus (bei ~280 Mietboxen der Normalfall) und die interne Kamera
        # des Tablets ist selbst per USB angebunden — das kommt vor, siehe
        # die Erklaerung bei _bus_aus_pfad. Dann meldet die Registry
        # "gesamt=1, usb=1" fuer die INTERNE Kamera, und (B) haette
        # ausgerechnet die abgeklebte Linse als Fotokamera ausgewaehlt:
        # schwarze Fotos beim Kunden statt blinkender Warnung.
        gemerkt = _cache_kandidat(cameras, registry, bool(interne))
        if gemerkt is not None:
            cam = next(c for c in cameras if c.get("index") == gemerkt)
            return fertig(gemerkt, "extern",
                          "unbestimmt, aus Gedaechtnis bestaetigt (dieselbe "
                          "VID/PID wie beim letzten Fund per Name+DevicePath, "
                          "laut Registry einzige Videoquelle am USB)",
                          cam)

        return fertig(-1, "unbestimmt_einzeln",
                      "unbestimmt, ein Geraet — kein Beweis, dass es die externe "
                      f"Kamera ist (Namensquelle={kandidat.get('namensquelle')}, "
                      f"Bus={kandidat.get('bus') or 'unbekannt'}, "
                      f"Registry bekannt={registry.get('bekannt')}, "
                      f"gesamt={registry.get('gesamt')}, usb={registry.get('usb')})")

    return fertig(-1, "unbestimmt_mehrere",
                  f"unbestimmt, mehrere Geraete — keine Auswahl "
                  f"({len(unbestimmt)} unbestimmt, {len(interne)} intern)")


class WebcamManager(CameraManager):
    """Verwaltet Webcam-Zugriff via OpenCV

    Funktioniert auch mit Canon Webcam Utility für DSLR-Support!
    """

    def __init__(self):
        self.cap: Optional[cv2.VideoCapture] = None
        self.camera_index: int = 0
        self._is_initialized: bool = False
        self.last_frame: Optional[np.ndarray] = None
        self.last_frame_time: float = 0
        self.frame_cache_duration: float = 0.033  # ~30fps
        self._preview_width: int = 0  # Gespeicherte Preview-Auflösung
        self._preview_height: int = 0
        self._active_width: int = 0
        self._active_height: int = 0
        self._mjpg_unsupported: bool = False  # Latch: Kamera lehnt MJPG ab
        # Bewusst die MODULWEITE Sperre (nicht pro Objekt): Die statische
        # Kamera-Suche laeuft sonst parallel dazu und korrumpiert den Heap.
        self._camera_lock = _CAMERA_HW_LOCK

    def initialize(self, camera_index: int, width: int, height: int) -> bool:
        """Initialisiert die Kamera"""
        # Negativer Index heisst "es wurde KEINE externe Kamera gefunden".
        # Das darf NIE bei cv2 landen: cv2.VideoCapture(-1) bedeutet dort
        # "irgendeine Kamera" — auf dem Miix waere das die abgeklebte interne.
        # Sauber scheitern ist hier richtig; die Session zeigt dann ihre
        # Fehlermeldung und der Waechter blinkt weiter.
        if camera_index is None or camera_index < 0:
            logger.error(
                f"Kamera-Initialisierung abgelehnt: camera_index={camera_index} "
                f"bedeutet 'keine externe Kamera gefunden'. Es wird bewusst KEINE "
                f"Ersatzkamera geoeffnet (interne Kamera bleibt gesperrt)."
            )
            return False

        with self._camera_lock:
            # Bereits initialisiert?
            if self._is_initialized and self.camera_index == camera_index:
                return True

            # Alte Verbindung schließen
            self.release()
            self.camera_index = camera_index
            self._mjpg_unsupported = False  # neue Kamera = neuer Versuch

            # Verschiedene Backends probieren
            backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]

            for backend in backends:
                logger.debug(f"Versuche Backend: {backend}")
                self.cap = cv2.VideoCapture(camera_index, backend)

                if self.cap.isOpened():
                    logger.info(f"Kamera {camera_index} geöffnet mit Backend {backend}")
                    break

            if not self.cap or not self.cap.isOpened():
                logger.error(f"Konnte Kamera {camera_index} nicht öffnen")
                return False

            # Einstellungen setzen — Codec NACH der Auflösung anfordern
            # (Messung 2.4.13: andersherum verhandelt DirectShow beim
            # Auflösungs-Setzen wieder auf YUY2 zurück)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimiert Latenz
            self._apply_mjpg()

            # Tatsächliche Auflösung loggen und als Preview-Auflösung merken
            actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self._preview_width = actual_w
            self._preview_height = actual_h
            self._active_width = actual_w
            self._active_height = actual_h
            logger.info(
                f"Kamera initialisiert: {actual_w}x{actual_h}, "
                f"fourcc={self._get_current_fourcc()}"
            )

            self._is_initialized = True
            return True

    def _apply_mjpg(self) -> bool:
        """Aktiviert den MJPG-Codec — mit VERIFIKATION und Merker bei Ablehnung.

        Warum: YUY2 (unkomprimiert) macht 1080p-Umschaltung + Auslesen über
        USB2 langsam (~1,3s + ~0,7s pro Foto, Messung Miix 310). Der erste
        Fix (2.4.13) setzte den Codec VOR der Auflösung — DirectShow
        verhandelte beim Auflösungs-Setzen zurück auf YUY2, und der nutzlose
        Versuch kostete zusätzlich ~600ms pro Foto. Daher jetzt:
        1) Codec NACH der Auflösung setzen und Ergebnis PRÜFEN,
        2) Fallback: Codec-zuerst-Variante (manche Treiber wollen es so),
        3) bei endgültiger Ablehnung dauerhaft merken → nie wieder Zeit
           pro Foto verschwenden.
        """
        if self._mjpg_unsupported or not self.cap:
            return False
        try:
            if self._get_current_fourcc() == "MJPG":
                return True
            mjpg = cv2.VideoWriter_fourcc(*"MJPG")

            # Versuch 1: Codec nach bereits gesetzter Auflösung anfordern
            self.cap.set(cv2.CAP_PROP_FOURCC, mjpg)
            if self._get_current_fourcc() == "MJPG":
                logger.info("Webcam-Codec: MJPG aktiv")
                return True

            # Versuch 2: Codec zuerst, dann dieselbe Auflösung erneut setzen
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.cap.set(cv2.CAP_PROP_FOURCC, mjpg)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            if self._get_current_fourcc() == "MJPG":
                logger.info("Webcam-Codec: MJPG aktiv (Codec-zuerst-Variante)")
                return True

            self._mjpg_unsupported = True
            logger.info(
                f"Webcam-Codec: Kamera lehnt MJPG ab, bleibt bei "
                f"{self._get_current_fourcc()} (keine weiteren Versuche)"
            )
        except Exception as e:
            self._mjpg_unsupported = True
            logger.debug(f"MJPG-Anforderung fehlgeschlagen: {e}")
        return False

    def get_frame(self, use_cache: bool = True) -> Optional[np.ndarray]:
        """Holt ein Frame von der Kamera"""
        if not self._is_initialized or not self.cap:
            return None

        with self._camera_lock:
            current_time = time.time()

            # Cache nutzen wenn möglich
            if use_cache and self.last_frame is not None:
                if current_time - self.last_frame_time < self.frame_cache_duration:
                    return self.last_frame.copy()

            # Neues Frame holen
            ret, frame = self.cap.read()

            if ret and frame is not None:
                self.last_frame = frame
                self.last_frame_time = current_time
                return frame

            logger.warning("Konnte kein Frame lesen")
            return None

    def get_high_res_frame(
        self,
        width: int = 1920,
        height: int = 1080,
        restore_preview: bool = True
    ) -> Optional[np.ndarray]:
        """Holt ein hochauflösendes Frame für Foto-Capture

        Schaltet temporär auf höhere Auflösung um und holt das Bild.
        Das Zurückschalten auf die Live-Preview-Auflösung kann verzögert
        werden, damit die sichtbare Aufnahmezeit kürzer wird.

        Optimiert für Logitech C920/C922 (native 1080p Support).

        Args:
            width: Gewünschte Breite (default: 1920 für Full HD)
            height: Gewünschte Höhe (default: 1080 für Full HD)
            restore_preview: True = direkt zurückschalten, False = später
                per restore_preview_resolution() zurückschalten.

        Returns:
            numpy array mit dem hochauflösenden Frame, oder None bei Fehler
        """
        if not self.cap:
            logger.warning("get_high_res_frame: Keine Kamera initialisiert")
            return None

        with self._camera_lock:
            total_start = time.perf_counter()
            set_ms = 0.0
            verify_ms = 0.0
            grab_ms = 0.0
            read_ms = 0.0
            restore_ms = 0.0
            switched_resolution = False
            frame = None

            preview_w, preview_h = self._get_preview_resolution()
            active_w = self._active_width or int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            active_h = self._active_height or int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            logger.info(
                "High-Res Capture Start: "
                f"preview={preview_w}x{preview_h}, active={active_w}x{active_h}, "
                f"target={width}x{height}, restore_preview={restore_preview}, "
                f"fourcc={self._get_current_fourcc()}"
            )

            try:
                if active_w >= width and active_h >= height:
                    logger.info("High-Res Capture: Zielauflösung ist bereits aktiv")
                else:
                    t0 = time.perf_counter()
                    ok_w = self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    ok_h = self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    self._apply_mjpg()
                    set_ms = (time.perf_counter() - t0) * 1000

                    t0 = time.perf_counter()
                    active_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    active_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    verify_ms = (time.perf_counter() - t0) * 1000
                    switched_resolution = True
                    self._active_width = active_w
                    self._active_height = active_h
                    self.last_frame = None
                    self.last_frame_time = 0

                    logger.info(
                        "High-Res Capture Umschaltung: "
                        f"set_ok={ok_w}/{ok_h}, actual={active_w}x{active_h}, "
                        f"set={set_ms:.0f}ms, verify={verify_ms:.0f}ms"
                    )

                # Buffer leeren mit grab() statt read() (grab bewegt nur den Pointer,
                # dekodiert nicht - deutlich schneller als read!)
                t0 = time.perf_counter()
                for _ in range(2):
                    self.cap.grab()
                grab_ms = (time.perf_counter() - t0) * 1000

                # Tatsächliches High-Res Frame holen
                t0 = time.perf_counter()
                ret, frame = self.cap.read()
                read_ms = (time.perf_counter() - t0) * 1000

                if ret and frame is not None:
                    captured_h, captured_w = frame.shape[:2]
                    logger.info(f"High-Res Frame erfolgreich: {captured_w}x{captured_h}")

                    if captured_w < width or captured_h < height:
                        logger.warning(
                            f"Kamera liefert weniger als angefordert: "
                            f"{captured_w}x{captured_h} statt {width}x{height}"
                        )
                else:
                    logger.error("High-Res Frame lesen fehlgeschlagen nach Umschaltung")
                    frame = None

            except Exception as e:
                logger.error(f"High-Res Capture Exception: {e}")
                frame = None
            finally:
                if restore_preview and switched_resolution:
                    t0 = time.perf_counter()
                    self.restore_preview_resolution()
                    restore_ms = (time.perf_counter() - t0) * 1000
                elif switched_resolution:
                    logger.info(
                        "High-Res Capture: Preview-Restore auf nachgelagerten "
                        "Background-Task verschoben"
                    )

                total_ms = (time.perf_counter() - total_start) * 1000
                logger.info(
                    "High-Res Capture Timing: "
                    f"set={set_ms:.0f}ms, verify={verify_ms:.0f}ms, "
                    f"grab={grab_ms:.0f}ms, read={read_ms:.0f}ms, "
                    f"restore={restore_ms:.0f}ms, total={total_ms:.0f}ms"
                )

            return frame

    def restore_preview_resolution(self) -> bool:
        """Schaltet zurück auf die gespeicherte Live-Preview-Auflösung."""
        if not self.cap:
            logger.warning("Preview-Restore: Keine Kamera initialisiert")
            return False

        with self._camera_lock:
            target_w, target_h = self._get_preview_resolution()
            if target_w <= 0 or target_h <= 0:
                logger.warning("Preview-Restore: Keine gültige Preview-Auflösung gespeichert")
                return False

            total_start = time.perf_counter()
            before_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            before_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            if before_w == target_w and before_h == target_h:
                self._active_width = before_w
                self._active_height = before_h
                self.last_frame = None
                self.last_frame_time = 0
                logger.debug(f"Preview-Restore: Bereits aktiv ({target_w}x{target_h})")
                return True

            t0 = time.perf_counter()
            ok_w = self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
            ok_h = self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
            self._apply_mjpg()
            set_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            verify_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            for _ in range(2):
                self.cap.grab()
            flush_ms = (time.perf_counter() - t0) * 1000

            self._active_width = actual_w
            self._active_height = actual_h
            self.last_frame = None
            self.last_frame_time = 0

            total_ms = (time.perf_counter() - total_start) * 1000
            logger.info(
                "Preview-Restore Timing: "
                f"{before_w}x{before_h} -> {actual_w}x{actual_h} "
                f"(target={target_w}x{target_h}, set_ok={ok_w}/{ok_h}), "
                f"set={set_ms:.0f}ms, verify={verify_ms:.0f}ms, "
                f"flush={flush_ms:.0f}ms, total={total_ms:.0f}ms"
            )
            return actual_w == target_w and actual_h == target_h

    def release(self):
        """Gibt Kamera-Ressourcen frei"""
        with self._camera_lock:
            if self.cap:
                self.cap.release()
                self.cap = None
            self._is_initialized = False
            self.last_frame = None
            self._active_width = 0
            self._active_height = 0
            logger.info("Kamera freigegeben")

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    def _get_preview_resolution(self) -> Tuple[int, int]:
        """Liefert die gemerkte Preview-Auflösung mit Kamera-Fallback."""
        preview_w = self._preview_width
        preview_h = self._preview_height

        if (preview_w <= 0 or preview_h <= 0) and self.cap:
            preview_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            preview_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        return preview_w, preview_h

    def _get_current_fourcc(self) -> str:
        """Liest den aktiven Kamera-Codec best-effort für Timing-Diagnose."""
        if not self.cap:
            return "unknown"

        try:
            fourcc_value = int(self.cap.get(cv2.CAP_PROP_FOURCC))
            if fourcc_value <= 0:
                return "unknown"
            chars = "".join(chr((fourcc_value >> 8 * i) & 0xFF) for i in range(4))
            return chars.strip() or str(fourcc_value)
        except Exception:
            return "unknown"

    @staticmethod
    def _get_dshow_device_names() -> list:
        """ZWEITER VERSUCH (Netz): Gerätenamen via PowerShell + C#-Interop.

        Seit 2.4.40 ist das NICHT mehr der Hauptweg — den macht `_dshow_geraete()`
        in-process über ctypes (3–25 ms statt 560–670 ms Verpackung, siehe den
        großen Kommentarblock oben). Dieser Weg bleibt bewusst noch stehen,
        falls die ctypes-Abfrage auf irgendeiner Box wider Erwarten scheitert:
        Robustheit vor Eleganz. Er darf raus, sobald die neue Abfrage auf einer
        nennenswerten Zahl Boxen sauber läuft.

        Er liefert NUR Namen, keinen DevicePath — die Registry-Gegenprobe ist
        dann das einzige Zusatzsignal.

        Returns:
            Liste von Gerätenamen in DirectShow-Reihenfolge.
            Leere Liste wenn Abfrage fehlschlägt.
        """
        try:
            import subprocess
            # C# DirectShow-Enumeration via PowerShell Add-Type
            # Nutzt dieselbe COM-API wie OpenCV CAP_DSHOW
            csharp_code = r'''
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Collections.Generic;
public class DShowEnum {
    [ComImport, Guid("62BE5D10-60EB-11d0-BD3B-00A0C911CE86")]
    class SystemDeviceEnum {}
    [ComImport, Guid("29840822-5B84-11D0-BD3B-00A0C911CE86"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ICreateDevEnum {
        [PreserveSig] int CreateClassEnumerator(
            [In] ref Guid type, [Out] out IEnumMoniker enumMoniker, [In] int flags);
    }
    [ComImport, Guid("55272A00-42CB-11CE-8135-00AA004BB851"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyBag {
        [PreserveSig] int Read(
            [In, MarshalAs(UnmanagedType.LPWStr)] string name,
            [In, Out] ref object val, [In] IntPtr errorLog);
        [PreserveSig] int Write(
            [In, MarshalAs(UnmanagedType.LPWStr)] string name, [In] ref object val);
    }
    public static string[] GetVideoDevices() {
        var names = new List<string>();
        try {
            var devEnum = (ICreateDevEnum)new SystemDeviceEnum();
            IEnumMoniker enumMon;
            var cat = new Guid("860BB310-5D01-11D0-BD3B-00A0C911CE86");
            if (devEnum.CreateClassEnumerator(ref cat, out enumMon, 0) == 0 && enumMon != null) {
                var mon = new IMoniker[1];
                while (enumMon.Next(1, mon, IntPtr.Zero) == 0) {
                    try {
                        Guid iid = typeof(IPropertyBag).GUID;
                        object bagObj;
                        mon[0].BindToStorage(null, null, ref iid, out bagObj);
                        var bag = (IPropertyBag)bagObj;
                        object nameVal = "";
                        bag.Read("FriendlyName", ref nameVal, IntPtr.Zero);
                        names.Add(nameVal != null ? nameVal.ToString() : "");
                        Marshal.ReleaseComObject(bagObj);
                    } catch {} finally { Marshal.ReleaseComObject(mon[0]); }
                }
                Marshal.ReleaseComObject(enumMon);
            }
        } catch {}
        return names.ToArray();
    }
}
'''
            ps_command = (
                f'Add-Type -TypeDefinition @"\n{csharp_code}\n"@ -Language CSharp; '
                '[DShowEnum]::GetVideoDevices() | ForEach-Object { $_ }'
            )
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps_command],
                capture_output=True, text=True, timeout=10,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            if result.returncode == 0 and result.stdout.strip():
                names = [n.strip() for n in result.stdout.strip().split('\n') if n.strip()]
                logger.info(f"DirectShow Kamera-Namen (korrekte Reihenfolge): {names}")
                return names
            else:
                if result.stderr:
                    logger.debug(f"DirectShow-Enumeration stderr: {result.stderr[:200]}")
        except Exception as e:
            logger.debug(f"DirectShow-Enumeration fehlgeschlagen: {e}")
        return []

    @staticmethod
    def _geraete_namen() -> Tuple[list, bool, str]:
        """Ermittelt die DirectShow-Geräte — und ob die Abfrage überhaupt lief.

        WARUM DER PnP-FALLBACK ERSATZLOS GESTRICHEN IST (2.4.40):
        `Get-PnpDevice -Class Camera,Image` hat im Test ZWEI DRUCKER und NULL
        Kameras geliefert — die Klasse "Image" enthält Scanner und
        Multifunktionsgeräte. Diese Fremdnamen wurden bisher positionsweise auf
        die cv2-Indizes geklebt: Index 0 (auf dem Miix die abgeklebte interne
        Kamera) hätte den Namen "HP Color LaserJet…" bekommen, wäre durch
        keinen Filter gefallen und als "externe Kamera" ausgewählt worden.
        Ergebnis wären schwarze Fotos beim Kunden gewesen — schlimmer als der
        gemeldete Bug. Dazu war die PnP-Reihenfolge noch nie die
        DirectShow-Reihenfolge (Vorfall 10.04.2026, Intel-AVStream-Kamera).

        Kommt keine Namensliste, gibt es künftig KEINE erfundene, sondern den
        ehrlichen Zustand "Namen unbekannt".

        Returns:
            (geraete, abfrage_ok, quelle)
            geraete    = [{"name": str, "device_path": str}, ...]
            abfrage_ok = True, wenn wirklich nachgesehen werden konnte
            quelle     = "ctypes" | "powershell" | "fehlt"
        """
        start = time.perf_counter()

        # 1. Hauptweg: in-process über ctypes (siehe Kommentarblock oben) —
        #    IMMER mit Zeitgrenze, sonst hängt ein kaputter Treiber den
        #    aufrufenden Thread für immer auf (siehe _dshow_geraete_mit_zeitgrenze).
        geraete, abfrage_ok = _dshow_geraete_mit_zeitgrenze()
        if abfrage_ok:
            dauer_ms = int((time.perf_counter() - start) * 1000)
            _LETZTE_ABFRAGE.update({"namensquelle": "ctypes", "abfrage_ok": True,
                                    "gemeldete_geraete": len(geraete),
                                    "dauer_ms": dauer_ms})
            logger.info(
                f"Kamera-Namen: Weg=ctypes/DirectShow, {len(geraete)} Gerät(e), "
                f"{dauer_ms} ms -> {[g.get('name') or '(ohne Namen)' for g in geraete]}"
            )
            return geraete, True, "ctypes"

        # 2. Netz: alter PowerShell-Weg. Liefert nur Namen, keinen DevicePath.
        logger.warning("ctypes-DirectShow-Abfrage fehlgeschlagen — versuche PowerShell-Weg")
        namen = WebcamManager._get_dshow_device_names()
        dauer_ms = int((time.perf_counter() - start) * 1000)
        if namen:
            geraete = [{"name": n, "device_path": ""} for n in namen]
            _LETZTE_ABFRAGE.update({"namensquelle": "powershell", "abfrage_ok": True,
                                    "gemeldete_geraete": len(geraete),
                                    "dauer_ms": dauer_ms})
            logger.info(
                f"Kamera-Namen: Weg=powershell, {len(geraete)} Gerät(e), {dauer_ms} ms "
                f"(ohne DevicePath) -> {namen}"
            )
            return geraete, True, "powershell"

        # 3. Beide Wege tot: NICHT raten. "Namen unbekannt" ist ein eigener
        #    Zustand und ausdrücklich KEIN Beweis für "interne Kamera".
        _LETZTE_ABFRAGE.update({"namensquelle": "fehlt", "abfrage_ok": False,
                                "gemeldete_geraete": 0, "dauer_ms": dauer_ms})
        logger.warning(
            f"Kamera-Namen: KEIN Weg erfolgreich ({dauer_ms} ms) — Zustand "
            f"'Namen unbekannt'. Das heißt NICHT, dass keine Kamera da ist."
        )
        return [], False, "fehlt"

    @staticmethod
    def list_cameras(max_cameras: int = 5) -> list:
        """Listet verfügbare Kameras mit echten Gerätenamen auf.

        Jeder Eintrag: index, name, width, height, device_path, namensquelle.
        `namensquelle` ist "dshow" (echter Name), "luecke" (Abfrage lief, kennt
        diesen Index aber nicht) oder "fehlt" (Abfrage komplett gescheitert).
        Der Anzeigetext "Kamera N" bleibt — er ist aber ab 2.4.40 NUR noch
        Anzeige und nie mehr Entscheidungsgrundlage.
        """
        geraete, abfrage_ok, _quelle = WebcamManager._geraete_namen()

        # Nur so viele Indizes öffnen, wie DirectShow wirklich meldet.
        # WARUM: Auf einer Ein-Kamera-Box spart das VIER Geräteöffnungen pro
        # Suche — auf dem Atom der größte Einzelposten, und jede eingesparte
        # Öffnung verkleinert die Kollisionsfläche für den Heap-Absturz von
        # Box 044. Meldet die Abfrage NULL Geräte, wird bewusst KEIN Index
        # probiert: DirectShow ist hier die Wahrheit, cv2 CAP_DSHOW kann ohne
        # DirectShow-Gerät ohnehin nichts öffnen.
        anzahl = min(max_cameras, len(geraete)) if abfrage_ok else max_cameras

        cameras = []
        # Ab hier wird echte Hardware angefasst -> Sperre PFLICHT (2.4.31).
        # (Die Namens-Ermittlung oben fasst KEINE Hardware an — sie liest nur
        # die COM-Geräteliste bzw. die Registry. Sie bleibt außerhalb der Sperre.)
        with _CAMERA_HW_LOCK:
          for i in range(anzahl):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()

                # Namenszuordnung über den GERÄTEINDEX i — nicht über
                # len(cameras)! Vorher indizierte der Code mit der Anzahl der
                # bisher ERFOLGREICH geöffneten Kameras: ließ sich ein Index
                # gerade nicht öffnen (belegt vom Wächter, von der Messung,
                # hängende interne Kamera), rutschten alle folgenden Namen um
                # eine Position — dann trug die C922 den Namen der internen
                # Kamera und wurde weggeworfen. Zweiter, vom Timeout völlig
                # unabhängiger Weg zu "0 gefundene Kameras".
                eintrag = geraete[i] if i < len(geraete) else {}
                name = str(eintrag.get("name", "") or "").strip()
                if name:
                    namensquelle = "dshow"
                elif abfrage_ok:
                    namensquelle = "luecke"
                else:
                    namensquelle = "fehlt"

                cameras.append({
                    "index": i,
                    "name": name or f"Kamera {i}",
                    "width": w,
                    "height": h,
                    "device_path": str(eintrag.get("device_path", "") or ""),
                    "namensquelle": namensquelle,
                })

        return cameras

    @staticmethod
    def erkenne_kamera(cameras: Optional[list] = None) -> dict:
        """Vollständiger Befund: Index, Zustand und Begründung im Klartext.

        Das ist der Weg, den App, Admin-Menü und Kamera-Messung nehmen sollen,
        wenn sie mehr wissen wollen als nur den Index (siehe waehle_kamera()).
        """
        if cameras is None:
            cameras = WebcamManager.list_cameras()
        ergebnis = waehle_kamera(cameras)

        if ergebnis["index"] >= 0:
            logger.info(
                f"Kamera gewählt: [{ergebnis['index']}] — {ergebnis['begruendung']}"
            )
        else:
            logger.warning(
                f"Keine Kamera gewählt (Zustand '{ergebnis['zustand']}'): "
                f"{ergebnis['begruendung']}"
            )
        return ergebnis

    @staticmethod
    def find_best_camera(cameras: list) -> int:
        """Findet die beste externe Webcam (interne Kameras bleiben gesperrt!).

        Die interne Tablet-Kamera (z.B. Lenovo Miix 310) ist physisch abgeklebt
        und darf NIE als Fotokamera dienen. Findet sich keine brauchbare
        externe Kamera, kommt -1 zurück → Kamera-Warnung blinkt.

        2.4.40: Die alte Regel `name_lower != f"kamera {index}"` ist ERSATZLOS
        entfallen. Sie stammt vom 27.03.2026 und war gegen namenlose
        Phantom-Duplikate im Admin-Dropdown gebaut — nicht gegen eine
        gescheiterte Namensabfrage. Genau diese Verwechslung ("Name unbekannt"
        = "Kamera ist intern") hat Christians Box am 20.08. blind gemeldet.
        Der ursprüngliche Phantom-Fall ist jetzt strukturell ausgeschlossen,
        weil list_cameras() nur noch so viele Indizes probiert, wie DirectShow
        überhaupt meldet.

        Args:
            cameras: Liste von list_cameras()

        Returns:
            Kamera-Index der besten externen Kamera, oder -1 wenn keine
        """
        return WebcamManager.erkenne_kamera(cameras)["index"]
