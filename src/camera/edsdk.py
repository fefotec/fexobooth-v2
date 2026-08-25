"""Canon EDSDK Python Wrapper (ctypes)

Low-level wrapper für Canon EDSDK DLL.
Basiert auf EDSDK v13.20.10
"""

import ctypes
from ctypes import c_uint, c_int, c_void_p, c_char_p, POINTER, byref, Structure, c_ubyte
from functools import wraps
import itertools
import os
import queue
import sys
import threading
import time
import traceback
from typing import Optional, List, Tuple
from pathlib import Path

from src.utils.logging import get_logger, is_developer_mode

logger = get_logger(__name__)

# ============================================================================
# DLL Loading
# ============================================================================

EDSDK_DLL = None
_dll_directory_handles = []

def _find_edsdk_dll() -> Optional[str]:
    """Sucht die EDSDK.dll"""
    # PyInstaller legt Binaries im One-Folder-Build seit Version 6 standard-
    # maessig in `_internal` ab und setzt `sys._MEIPASS` genau auf diesen
    # Ordner. Das muss VOR Repo-/Altpfaden geprueft werden, sonst funktioniert
    # Canon aus dem Quellbaum, aber nicht in der frisch installierten EXE.
    search_paths = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        search_paths.append(Path(meipass))

    if getattr(sys, "frozen", False):
        exe_ordner = Path(sys.executable).resolve().parent
        search_paths.extend([exe_ordner / "_internal", exe_ordner])

    search_paths.extend([
        # Im Repo
        Path(__file__).parent.parent.parent / "EDSDK" / "EDSDKv132010W" / "EDSDKv132010W" / "Windows" / "EDSDK_64" / "Dll",
        # Im fexobooth Ordner auf Windows
        Path("C:/fexobooth/EDSDK_64/Dll"),
        Path("C:/fexobooth/fexobooth-v2/EDSDK/EDSDKv132010W/EDSDKv132010W/Windows/EDSDK_64/Dll"),
        # Neben der exe
        Path("."),
    ])
    
    for path in search_paths:
        dll_path = path / "EDSDK.dll"
        image_dll = path / "EdsImage.dll"
        if dll_path.exists() and image_dll.exists():
            logger.info(f"EDSDK.dll gefunden: {dll_path}")
            return str(dll_path.parent)
        if dll_path.exists():
            logger.error(
                f"EDSDK.dll gefunden, aber EdsImage.dll fehlt daneben: {path}"
            )
    
    return None


def load_edsdk() -> bool:
    """Lädt die EDSDK DLL"""
    global EDSDK_DLL
    
    if EDSDK_DLL is not None:
        return True
    
    if sys.platform != "win32":
        logger.warning("EDSDK ist nur unter Windows verfügbar")
        return False
    
    dll_dir = _find_edsdk_dll()
    if not dll_dir:
        logger.error("EDSDK.dll nicht gefunden!")
        return False
    
    try:
        # DLL-Verzeichnis zum Suchpfad hinzufügen
        # Das von add_dll_directory gelieferte Handle muss am Leben bleiben.
        # Wird es sofort freigegeben, entfernt CPython den Suchpfad wieder und
        # EDSDK.dll kann ihre Nachbar-DLL EdsImage.dll nicht mehr finden.
        _dll_directory_handles.append(os.add_dll_directory(dll_dir))
        
        # DLL laden
        dll_path = os.path.join(dll_dir, "EDSDK.dll")
        EDSDK_DLL = ctypes.WinDLL(dll_path)
        
        logger.info("EDSDK.dll erfolgreich geladen")
        return True
        
    except Exception as e:
        logger.error(f"Fehler beim Laden der EDSDK.dll: {e}")
        return False


# ============================================================================
# Error Codes
# ============================================================================

EDS_ERR_OK = 0x00000000
EDS_ERR_DEVICE_NOT_FOUND = 0x00000080

# 2.4.46 KORRIGIERT — beide Werte standen hier falsch (gegen EDSDKErrors.h geprüft):
#   DEVICE_BUSY stand auf 0xc0  -> 0xc0 ist COMM_PORT_IS_IN_USE, BUSY ist 0x81
#   SESSION_ALREADY_OPEN auf 0x2004 -> 0x2004 ist INVALID_TRANSACTIONID
# Folge: open_session() erkannte die "Kamera noch belegt"-Lage nie und gab auf,
# statt die Session zu schließen und neu zu öffnen.
EDS_ERR_DEVICE_BUSY = 0x00000081
EDS_ERR_COMM_PORT_IS_IN_USE = 0x000000c0
EDS_ERR_COMM_DISCONNECTED = 0x000000c1
EDS_ERR_SESSION_NOT_OPEN = 0x00002003
EDS_ERR_SESSION_ALREADY_OPEN = 0x0000201e
EDS_ERR_TAKE_PICTURE_AF_NG = 0x00008D01
EDS_ERR_TAKE_PICTURE_CARD_NG = 0x00008D07
EDS_ERR_OBJECT_NOTREADY = 0x0000A102
EDS_ERR_MEMORYSTATUS_NOTREADY = 0x0000A106

# Error-Code Namen für besseres Logging
#
# ACHTUNG (2.4.46): Diese Tabelle stand hier FALSCH und hat die Fehlersuche
# jahrelang in die Irre geführt. Sie ist jetzt 1:1 aus dem offiziellen
# Canon-Header EDSDKErrors.h erzeugt (liegt im Repo unter EDSDK/.../Header/).
#
# Die drei folgenschwersten Verwechslungen waren:
#   0x81   stand als "INVALID_PARAMETER"  -> ist in Wahrheit DEVICE_BUSY
#   0xc1   stand gar nicht drin ("UNKNOWN") -> ist COMM_DISCONNECTED (USB weg!)
#   0xa102 stand als "EVF_INTERNAL_ERROR" -> ist OBJECT_NOTREADY (harmlos)
#
# Wer im Box-Log "INVALID_PARAMETER" las, suchte den Fehler im eigenen Code.
# Tatsächlich meldete die Kamera "ich bin beschäftigt" bzw. "das USB-Kabel ist
# weg" — also ein Hardware-/Verbindungsproblem.
ERROR_NAMES = {
    0x00000000: "OK",
    0x00000001: "UNIMPLEMENTED",
    0x00000002: "INTERNAL_ERROR",
    0x00000003: "MEM_ALLOC_FAILED",
    0x00000004: "MEM_FREE_FAILED",
    0x00000005: "OPERATION_CANCELLED",
    0x00000006: "INCOMPATIBLE_VERSION",
    0x00000007: "NOT_SUPPORTED",
    0x00000008: "UNEXPECTED_EXCEPTION",
    0x00000009: "PROTECTION_VIOLATION",
    0x0000000a: "MISSING_SUBCOMPONENT",
    0x0000000b: "SELECTION_UNAVAILABLE",
    0x00000020: "FILE_IO_ERROR",
    0x00000021: "FILE_TOO_MANY_OPEN",
    0x00000022: "FILE_NOT_FOUND",
    0x00000023: "FILE_OPEN_ERROR",
    0x00000024: "FILE_CLOSE_ERROR",
    0x00000025: "FILE_SEEK_ERROR",
    0x00000026: "FILE_TELL_ERROR",
    0x00000027: "FILE_READ_ERROR",
    0x00000028: "FILE_WRITE_ERROR",
    0x00000029: "FILE_PERMISSION_ERROR",
    0x0000002a: "FILE_DISK_FULL_ERROR",
    0x0000002b: "FILE_ALREADY_EXISTS",
    0x0000002c: "FILE_FORMAT_UNRECOGNIZED",
    0x0000002d: "FILE_DATA_CORRUPT",
    0x0000002e: "FILE_NAMING_NA",
    0x00000040: "DIR_NOT_FOUND",
    0x00000041: "DIR_IO_ERROR",
    0x00000042: "DIR_ENTRY_NOT_FOUND",
    0x00000043: "DIR_ENTRY_EXISTS",
    0x00000044: "DIR_NOT_EMPTY",
    0x00000050: "PROPERTIES_UNAVAILABLE",
    0x00000051: "PROPERTIES_MISMATCH",
    0x00000053: "PROPERTIES_NOT_LOADED",
    0x00000060: "INVALID_PARAMETER",
    0x00000061: "INVALID_HANDLE",
    0x00000062: "INVALID_POINTER",
    0x00000063: "INVALID_INDEX",
    0x00000064: "INVALID_LENGTH",
    0x00000065: "INVALID_FN_POINTER",
    0x00000066: "INVALID_SORT_FN",
    0x00000080: "DEVICE_NOT_FOUND",
    0x00000081: "DEVICE_BUSY",
    0x00000082: "DEVICE_INVALID",
    0x00000083: "DEVICE_EMERGENCY",
    0x00000084: "DEVICE_MEMORY_FULL",
    0x00000085: "DEVICE_INTERNAL_ERROR",
    0x00000086: "DEVICE_INVALID_PARAMETER",
    0x00000087: "DEVICE_NO_DISK",
    0x00000088: "DEVICE_DISK_ERROR",
    0x00000089: "DEVICE_CF_GATE_CHANGED",
    0x0000008a: "DEVICE_DIAL_CHANGED",
    0x0000008b: "DEVICE_NOT_INSTALLED",
    0x0000008c: "DEVICE_STAY_AWAKE",
    0x0000008d: "DEVICE_NOT_RELEASED",
    0x000000a0: "STREAM_IO_ERROR",
    0x000000a1: "STREAM_NOT_OPEN",
    0x000000a2: "STREAM_ALREADY_OPEN",
    0x000000a3: "STREAM_OPEN_ERROR",
    0x000000a4: "STREAM_CLOSE_ERROR",
    0x000000a5: "STREAM_SEEK_ERROR",
    0x000000a6: "STREAM_TELL_ERROR",
    0x000000a7: "STREAM_READ_ERROR",
    0x000000a8: "STREAM_WRITE_ERROR",
    0x000000a9: "STREAM_PERMISSION_ERROR",
    0x000000aa: "STREAM_COULDNT_BEGIN_THREAD",
    0x000000ab: "STREAM_BAD_OPTIONS",
    0x000000ac: "STREAM_END_OF_STREAM",
    0x000000c0: "COMM_PORT_IS_IN_USE",
    0x000000c1: "COMM_DISCONNECTED",
    0x000000c2: "COMM_DEVICE_INCOMPATIBLE",
    0x000000c3: "COMM_BUFFER_FULL",
    0x000000c4: "COMM_USB_BUS_ERR",
    0x000000d0: "USB_DEVICE_LOCK_ERROR",
    0x000000d1: "USB_DEVICE_UNLOCK_ERROR",
    0x000000e0: "STI_UNKNOWN_ERROR",
    0x000000e1: "STI_INTERNAL_ERROR",
    0x000000e2: "STI_DEVICE_CREATE_ERROR",
    0x000000e3: "STI_DEVICE_RELEASE_ERROR",
    0x000000e4: "DEVICE_NOT_LAUNCHED",
    0x000000f0: "ENUM_NA",
    0x000000f1: "INVALID_FN_CALL",
    0x000000f2: "HANDLE_NOT_FOUND",
    0x000000f3: "INVALID_ID",
    0x000000f4: "WAIT_TIMEOUT_ERROR",
    0x000000f5: "LAST_GENERIC_ERROR_PLUS_ONE",
    0x00002003: "SESSION_NOT_OPEN",
    0x00002004: "INVALID_TRANSACTIONID",
    0x00002007: "INCOMPLETE_TRANSFER",
    0x00002008: "INVALID_STRAGEID",
    0x0000200a: "DEVICEPROP_NOT_SUPPORTED",
    0x0000200b: "INVALID_OBJECTFORMATCODE",
    0x00002011: "SELF_TEST_FAILED",
    0x00002012: "PARTIAL_DELETION",
    0x00002014: "SPECIFICATION_BY_FORMAT_UNSUPPORTED",
    0x00002015: "NO_VALID_OBJECTINFO",
    0x00002016: "INVALID_CODE_FORMAT",
    0x00002017: "UNKNOWN_VENDOR_CODE",
    0x00002018: "CAPTURE_ALREADY_TERMINATED",
    0x00002019: "PTP_DEVICE_BUSY",
    0x0000201a: "INVALID_PARENTOBJECT",
    0x0000201b: "INVALID_DEVICEPROP_FORMAT",
    0x0000201c: "INVALID_DEVICEPROP_VALUE",
    0x0000201e: "SESSION_ALREADY_OPEN",
    0x0000201f: "TRANSACTION_CANCELLED",
    0x00002020: "SPECIFICATION_OF_DESTINATION_UNSUPPORTED",
    0x00002021: "NOT_CAMERA_SUPPORT_SDK_VERSION",
    0x00008d01: "TAKE_PICTURE_AF_NG",
    0x00008d02: "TAKE_PICTURE_RESERVED",
    0x00008d03: "TAKE_PICTURE_MIRROR_UP_NG",
    0x00008d04: "TAKE_PICTURE_SENSOR_CLEANING_NG",
    0x00008d05: "TAKE_PICTURE_SILENCE_NG",
    0x00008d06: "TAKE_PICTURE_NO_CARD_NG",
    0x00008d07: "TAKE_PICTURE_CARD_NG",
    0x00008d08: "TAKE_PICTURE_CARD_PROTECT_NG",
    0x00008d09: "TAKE_PICTURE_MOVIE_CROP_NG",
    0x00008d0a: "TAKE_PICTURE_STROBO_CHARGE_NG",
    0x00008d0b: "TAKE_PICTURE_NO_LENS_NG",
    0x00008d0c: "TAKE_PICTURE_SPECIAL_MOVIE_MODE_NG",
    0x00008d0d: "TAKE_PICTURE_LV_REL_PROHIBIT_MODE_NG",
    0x00008d0e: "TAKE_PICTURE_MOVIE_MODE_NG",
    0x00008d0f: "TAKE_PICTURE_RETRUCTED_LENS_NG",
    0x0000a001: "UNKNOWN_COMMAND",
    0x0000a005: "OPERATION_REFUSED",
    0x0000a006: "LENS_COVER_CLOSE",
    0x0000a101: "LOW_BATTERY",
    0x0000a102: "OBJECT_NOTREADY",
    0x0000a104: "CANNOT_MAKE_OBJECT",
    0x0000a106: "MEMORYSTATUS_NOTREADY",
}

# Fehler, die bedeuten: Die Verbindung zur Kamera ist hinüber. Weiterprobieren
# auf derselben Session ist zwecklos, es hilft nur ein kompletter Neuaufbau.
VERBINDUNG_TOT = {
    0x00000081,  # DEVICE_BUSY        - Kamera hängt (bleibt oft dauerhaft)
    0x00000082,  # DEVICE_INVALID
    0x0000008b,  # DEVICE_NOT_INSTALLED
    0x000000c0,  # COMM_PORT_IS_IN_USE
    0x000000c1,  # COMM_DISCONNECTED  - USB-Verbindung abgerissen
    0x000000c4,  # COMM_USB_BUS_ERR
    0x00002003,  # SESSION_NOT_OPEN
    0x00000080,  # DEVICE_NOT_FOUND
}

# Fehler, die im Normalbetrieb erwartbar sind und NICHT als ERROR ins Log
# gehören (sonst stehen pro Abend zehntausend rote Zeilen drin).
HARMLOS = {
    0x0000a102,  # OBJECT_NOTREADY - Live-View braucht nach dem Start ~1-2s
}


def ist_verbindung_tot(err: int) -> bool:
    """True wenn dieser Fehlercode heißt: Kamera-Verbindung neu aufbauen."""
    return err in VERBINDUNG_TOT


# Zuletzt von check_error() gesehener Fehlercode. Die Kamera-Schicht (canon.py)
# liest ihn aus, um zu entscheiden ob ein Verbindungs-Neuaufbau nötig ist.
# Ohne das kam nur ein nacktes False zurück und der Grund ging verloren.
letzter_fehler: int = 0

def check_error(err: int, context: str = "") -> bool:
    """Prüft EDSDK Fehlercode

    2.4.46: Harmlose Codes (Live-View noch nicht warm) landen nur noch als DEBUG
    im Log. Vorher standen dafür pro Abend zehntausende rote ERROR-Zeilen drin,
    zwischen denen die echten Fehler untergingen.
    """
    global letzter_fehler

    if err == EDS_ERR_OK:
        letzter_fehler = EDS_ERR_OK
        return True

    letzter_fehler = err
    err_name = ERROR_NAMES.get(err, "UNBEKANNT")

    if err in HARMLOS:
        # Live-View OBJECT_NOTREADY wird im Owner alle fuenf Sekunden
        # zusammengefasst. Ein Eintrag pro Frame verdeckt die Capture-Spur.
        return False

    if ist_verbindung_tot(err):
        logger.error(
            f"EDSDK Fehler {hex(err)} ({err_name}) bei {context} "
            f">>> VERBINDUNG ZUR KAMERA IST HINÜBER (USB/Strom prüfen)"
        )
        return False

    logger.error(f"EDSDK Fehler {hex(err)} ({err_name}) bei {context}")
    return False


# ============================================================================
# Constants
# ============================================================================

# Property IDs
kEdsPropID_ProductName = 0x00000002
kEdsPropID_BodyIDEx = 0x00000015
kEdsPropID_BatteryLevel = 0x00000008
kEdsPropID_Evf_OutputDevice = 0x00000500
kEdsPropID_SaveTo = 0x0000000b
kEdsPropID_ImageQuality = 0x00000100

# 2.4.46 — für die Kamera-Diagnose im Dev-Mode (Werte aus EDSDKTypes.h)
kEdsPropID_AEMode = 0x00000400          # Programmwahlrad (P/Av/Tv/M/Vollautomatik)
kEdsPropID_AFMode = 0x00000404          # Fokus-Art (One-Shot / Servo / manuell)
kEdsPropID_MeteringMode = 0x00000403     # Belichtungsmessung
kEdsPropID_ExposureCompensation = 0x00000407  # Belichtungskorrektur
kEdsPropID_AvailableShots = 0x0000040a  # freie Aufnahmen
kEdsPropID_WhiteBalance = 0x00000106    # Weissabgleich (AWB schwankt pro Foto!)
kEdsPropID_ISOSpeed = 0x00000402        # ISO
kEdsPropID_Av = 0x00000405              # Blende
kEdsPropID_Tv = 0x00000406              # Belichtungszeit (Verwacklungsgefahr!)
kEdsPropID_Evf_ViewType = 0x01000513    # Live-View-Belichtungssimulation

# Belichtungszeit-Codes -> Klartext. Nur die fuer die Box interessanten Werte.
# Alles ab 1/60 abwaerts ist in einer Fotobox kritisch: Gaeste bewegen sich,
# das Bild wird unscharf.
TV_NAMEN = {
    0x10: "30s", 0x18: "15s", 0x20: "8s", 0x28: "4s", 0x30: "2s", 0x38: "1s",
    0x40: "1/2", 0x48: "1/4", 0x50: "1/8", 0x54: "1/10", 0x58: "1/15",
    0x5c: "1/20", 0x60: "1/30", 0x63: "1/40", 0x68: "1/60", 0x6b: "1/80",
    0x70: "1/125", 0x73: "1/160", 0x78: "1/250", 0x7b: "1/320",
    0x80: "1/500", 0x83: "1/640", 0x88: "1/1000", 0x90: "1/2000",
    0x98: "1/4000",
}

AV_NAMEN = {
    0x08: "f/1.0", 0x0b: "f/1.1", 0x0c: "f/1.2", 0x0d: "f/1.2",
    0x10: "f/1.4", 0x15: "f/1.8", 0x18: "f/2.0",
    0x1d: "f/2.5", 0x20: "f/2.8", 0x25: "f/3.5", 0x28: "f/4.0", 0x2d: "f/5.0",
    0x30: "f/5.6", 0x35: "f/7.1", 0x38: "f/8.0", 0x3d: "f/10", 0x40: "f/11",
    0x45: "f/14", 0x48: "f/16", 0x4d: "f/20", 0x50: "f/22",
}

ISO_NAMEN = {
    0x00: "Auto", 0x40: "50", 0x48: "100", 0x4b: "125", 0x4d: "160",
    0x50: "200", 0x53: "250", 0x55: "320", 0x58: "400", 0x5b: "500",
    0x5d: "640", 0x60: "800", 0x63: "1000", 0x65: "1250", 0x68: "1600",
    0x70: "3200", 0x78: "6400", 0x80: "12800",
}

AE_MODE_NAMEN = {
    0x00: "P (Programmautomatik)", 0x01: "Tv", 0x02: "Av", 0x03: "M (manuell)",
    0x04: "Bulb", 0x05: "A-DEP", 0x06: "DEP", 0x07: "C1/Custom",
    0x08: "AE-Lock", 0x09: "Vollautomatik (grünes Feld)",
    0x0A: "Nachtportrait", 0x0B: "Sport", 0x0C: "Portrait",
    0x0D: "Landschaft", 0x0E: "Makro", 0x0F: "Blitz aus",
    0x10: "C2", 0x11: "C3", 0x13: "Kreativautomatik", 0x14: "Video",
    0x15: "Foto im Video", 0x16: "Intelligente Automatik", 0x17: "Nachtszene",
    0x18: "HDR-Gegenlicht", 0x19: "SCN", 0x1A: "Kinder", 0x1B: "Speisen",
    0x1C: "Kerzenlicht", 0x1D: "Kreativfilter", 0x1E: "Körniges S/W",
    0x1F: "Weichzeichner", 0x20: "Spielzeugkamera", 0x21: "Fisheye",
    0x22: "Aquarell", 0x23: "Miniatur", 0x24: "HDR Standard",
    0x25: "HDR kräftig", 0x26: "HDR markant", 0x27: "HDR Relief",
    0x28: "Video Fantasy", 0x29: "Video Alt", 0x2A: "Video Erinnerung",
    0x2B: "Video Direkt-S/W", 0x2C: "Video Miniatur", 0x2D: "Mitziehen",
    0x2E: "Gruppenfoto", 0x32: "Selbstportrait", 0x33: "Hybrid Auto",
    0x34: "Glatte Haut", 0x35: "Panorama", 0x36: "Leise", 0x37: "Fv",
    0x38: "Ölgemälde", 0x39: "Feuerwerk", 0x3A: "Sternenportrait",
    0x3B: "Sternennacht", 0x3C: "Sternspuren", 0x3D: "Stern-Zeitraffer",
    0x3E: "Hintergrundunschärfe", 0x3F: "Video-Blog",
    0xFFFFFFFF: "unbekannt",
}

WB_NAMEN = {
    0: "Auto (AWB, Umgebungspriorität)", 1: "Tageslicht", 2: "Wolkig",
    3: "Kunstlicht", 4: "Leuchtstoff", 5: "Blitz", 6: "Manuell 1",
    8: "Schatten", 9: "Farbtemperatur", 10: "PC-Set 1", 11: "PC-Set 2",
    12: "PC-Set 3", 15: "Manuell 2", 16: "Manuell 3", 17: "Unterwasser",
    18: "Manuell 4",
    19: "Manuell 5", 20: "PC-Set 4", 21: "PC-Set 5",
    23: "Auto (AWB, Weißpriorität)", 24: "Farbtemperatur 2",
    25: "Farbtemperatur 3", 26: "Farbtemperatur 4",
    0xFFFFFFFE: "eingefügt", 0xFFFFFFFF: "unbekannt/Click",
}

METERING_MODE_NAMEN = {
    1: "Spot", 3: "Mehrfeld", 4: "Selektiv", 5: "Mittenbetont",
    0xFFFFFFFF: "unbekannt",
}

EXPOSURE_COMP_NAMEN = {
    0x28: "+5 EV", 0x25: "+4 2/3 EV", 0x24: "+4 1/2 EV", 0x23: "+4 1/3 EV",
    0x20: "+4 EV", 0x1D: "+3 2/3 EV", 0x1C: "+3 1/2 EV", 0x1B: "+3 1/3 EV",
    0x18: "+3 EV", 0x15: "+2 2/3 EV", 0x14: "+2 1/2 EV", 0x13: "+2 1/3 EV",
    0x10: "+2 EV", 0x0D: "+1 2/3 EV", 0x0C: "+1 1/2 EV", 0x0B: "+1 1/3 EV",
    0x08: "+1 EV", 0x05: "+2/3 EV", 0x04: "+1/2 EV", 0x03: "+1/3 EV",
    0x00: "0 EV", 0xFD: "-1/3 EV", 0xFC: "-1/2 EV", 0xFB: "-2/3 EV",
    0xF8: "-1 EV", 0xF5: "-1 1/3 EV", 0xF4: "-1 1/2 EV", 0xF3: "-1 2/3 EV",
    0xF0: "-2 EV", 0xED: "-2 1/3 EV", 0xEC: "-2 1/2 EV", 0xEB: "-2 2/3 EV",
    0xE8: "-3 EV", 0xE5: "-3 1/3 EV", 0xE4: "-3 1/2 EV", 0xE3: "-3 2/3 EV",
    0xE0: "-4 EV", 0xDD: "-4 1/3 EV", 0xDC: "-4 1/2 EV", 0xDB: "-4 2/3 EV",
    0xD8: "-5 EV", 0xFFFFFFFF: "unbekannt",
}

EVF_VIEW_TYPE_NAMEN = {
    0: "nur Abblendtaste", 1: "aktiv", 3: "deaktiviert",
    4: "Belichtung und Schärfentiefe", 0xFFFFFFFF: "unbekannt",
}

# Image Quality Werte (für JPG)
# Format: 0x00LLSSpp (LL=LargeSize, SS=SecondarySize, pp=Primary/Secondary type)
EdsImageQuality_LJF = 0x0013ff0f   # Large Fine JPG (beste JPG Qualität)
EdsImageQuality_LJN = 0x0012ff0f   # Large Normal JPG
EdsImageQuality_MJF = 0x0113ff0f   # Medium Fine JPG
EdsImageQuality_SJF = 0x0213ff0f   # Small Fine JPG

# EVF Output Device
kEdsEvfOutputDevice_TFT = 1
kEdsEvfOutputDevice_PC = 2

# Save To
kEdsSaveTo_Camera = 1
kEdsSaveTo_Host = 2
kEdsSaveTo_Both = 3

# Camera Commands
kEdsCameraCommand_TakePicture = 0x00000000
kEdsCameraCommand_PressShutterButton = 0x00000004

# Auslöser-Stellungen (wie beim Druck mit dem Finger)
kEdsCameraCommand_ShutterButton_OFF = 0x00000000
kEdsCameraCommand_ShutterButton_Halfway = 0x00000001          # halb: Autofokus läuft
kEdsCameraCommand_ShutterButton_Completely = 0x00000003        # ganz durch
kEdsCameraCommand_ShutterButton_Halfway_NonAF = 0x00010001
kEdsCameraCommand_ShutterButton_Completely_NonAF = 0x00010003  # ganz durch, ohne AF-Zwang
kEdsCameraCommand_ExtendShutDownTimer = 0x00000001
kEdsCameraCommand_BulbStart = 0x00000002
kEdsCameraCommand_BulbEnd = 0x00000003

# Camera State Commands
kEdsCameraStatusCommand_UILock = 0x00000000
kEdsCameraStatusCommand_UIUnLock = 0x00000001
kEdsCameraStatusCommand_EnterDirectTransfer = 0x00000002
kEdsCameraStatusCommand_ExitDirectTransfer = 0x00000003

# Object Events
kEdsObjectEvent_All = 0x00000200
kEdsObjectEvent_DirItemCreated = 0x00000204
kEdsObjectEvent_DirItemRequestTransfer = 0x00000208
kEdsObjectEvent_DirItemRequestTransferDT = 0x00000209

# State Events
kEdsStateEvent_All = 0x00000300
kEdsStateEvent_Shutdown = 0x00000301
kEdsStateEvent_JobStatusChanged = 0x00000302
kEdsStateEvent_WillSoonShutDown = 0x00000303
kEdsStateEvent_ShutDownTimerUpdate = 0x00000304
kEdsStateEvent_CaptureError = 0x00000305
kEdsStateEvent_InternalError = 0x00000306


# ============================================================================
# Structures
# ============================================================================

class EdsDeviceInfo(Structure):
    _fields_ = [
        ("szPortName", ctypes.c_char * 256),
        ("szDeviceDescription", ctypes.c_char * 256),
        ("deviceSubType", c_uint),
        ("reserved", c_uint),
    ]


class EdsCapacity(Structure):
    _fields_ = [
        ("numberOfFreeClusters", c_int),
        ("bytesPerSector", c_int),
        ("reset", c_int),
    ]


class EdsDirectoryItemInfo(Structure):
    """Info über ein Verzeichnis-Item (Datei oder Ordner auf der Kamera)

    2.4.47 — HIER LAG EIN SCHWERWIEGENDER FEHLER.

    `size` stand als `c_uint` (32 Bit) drin. Der offizielle Canon-Header
    EDSDKTypes.h sagt aber `EdsUInt64 size` — 64 Bit:

        typedef struct tagEdsDirectoryItemInfo
        {
            EdsUInt64   size;        <-- 8 Bytes, nicht 4!
            EdsBool     isFolder;
            ...

    Folge: Ab dem zweiten Feld war ALLES um 4 Bytes verschoben.
    `isFolder` las die oberen 32 Bit der Dateigröße (bei normalen Dateien
    also 0 = "kein Ordner"), und `szFileName` las ab der falschen Stelle
    und lieferte Buchstabensalat.

    WAS DAS ANGERICHTET HAT: Die Box konnte auf der Speicherkarte nie den
    DCIM-Ordner finden — der Vergleich `name == "DCIM" and info.isFolder`
    konnte gar nicht zutreffen. Im Box-Log vom 21.08.2026 stand deshalb
    "Keine SD-Karte (DCIM nicht gefunden)", OBWOHL eine Karte in der Kamera
    steckte. Die Box fiel daraufhin auf den Host-Download zurück — und der
    war seinerseits kaputt (Rückkanal nie eingerichtet). Beide Wege zur
    Kamera waren damit gleichzeitig blockiert.

    Merke: Strukturen immer gegen den Hersteller-Header prüfen. Er liegt in
    diesem Repo unter EDSDK/EDSDKv132010W/.../Header/EDSDKTypes.h.
    """
    _fields_ = [
        ("size", ctypes.c_uint64),  # Dateigröße — 64 Bit (EdsUInt64)!
        ("isFolder", c_int),        # EdsBool: 1 wenn Ordner
        ("groupID", c_uint),        # Gruppen-ID
        ("option", c_uint),         # Option
        ("szFileName", ctypes.c_char * 256),  # Dateiname (EDS_MAX_NAME = 256)
        ("format", c_uint),         # Format (JPEG, RAW, etc.)
        ("dateTime", c_uint),       # Datum/Zeit
    ]


# Callback-Typ für Object Events
# typedef EdsError (EDSCALLBACK *EdsObjectEventHandler)(EdsObjectEvent inEvent, EdsBaseRef inRef, EdsVoid *inContext)
# EDSCALLBACK = __stdcall → WINFUNCTYPE (nicht CFUNCTYPE/cdecl!)
# Auf x64 sind beide Calling-Conventions identisch, aber WINFUNCTYPE
# aktiviert Windows SEH Exception Handling für den Callback.
EdsObjectEventHandler = ctypes.WINFUNCTYPE(c_uint, c_uint, c_void_p, c_void_p)

# typedef EdsError (EDSCALLBACK *EdsStateEventHandler)(
#     EdsStateEvent inEvent, EdsUInt32 inEventData, EdsVoid *inContext)
EdsStateEventHandler = ctypes.WINFUNCTYPE(c_uint, c_uint, c_uint, c_void_p)


# ============================================================================
# API Functions
# ============================================================================

def _setup_functions():
    """Konfiguriert die EDSDK Funktionen"""
    if EDSDK_DLL is None:
        return
    
    # EdsInitializeSDK
    EDSDK_DLL.EdsInitializeSDK.restype = c_uint
    EDSDK_DLL.EdsInitializeSDK.argtypes = []
    
    # EdsTerminateSDK
    EDSDK_DLL.EdsTerminateSDK.restype = c_uint
    EDSDK_DLL.EdsTerminateSDK.argtypes = []
    
    # EdsGetCameraList
    EDSDK_DLL.EdsGetCameraList.restype = c_uint
    EDSDK_DLL.EdsGetCameraList.argtypes = [POINTER(c_void_p)]
    
    # EdsGetChildCount
    EDSDK_DLL.EdsGetChildCount.restype = c_uint
    EDSDK_DLL.EdsGetChildCount.argtypes = [c_void_p, POINTER(c_int)]
    
    # EdsGetChildAtIndex
    EDSDK_DLL.EdsGetChildAtIndex.restype = c_uint
    EDSDK_DLL.EdsGetChildAtIndex.argtypes = [c_void_p, c_int, POINTER(c_void_p)]
    
    # EdsGetDeviceInfo
    EDSDK_DLL.EdsGetDeviceInfo.restype = c_uint
    EDSDK_DLL.EdsGetDeviceInfo.argtypes = [c_void_p, POINTER(EdsDeviceInfo)]
    
    # EdsOpenSession
    EDSDK_DLL.EdsOpenSession.restype = c_uint
    EDSDK_DLL.EdsOpenSession.argtypes = [c_void_p]
    
    # EdsCloseSession
    EDSDK_DLL.EdsCloseSession.restype = c_uint
    EDSDK_DLL.EdsCloseSession.argtypes = [c_void_p]
    
    # EdsRelease
    EDSDK_DLL.EdsRelease.restype = c_uint
    EDSDK_DLL.EdsRelease.argtypes = [c_void_p]

    # EdsRetain
    EDSDK_DLL.EdsRetain.restype = c_uint
    EDSDK_DLL.EdsRetain.argtypes = [c_void_p]
    
    # EdsSendCommand
    EDSDK_DLL.EdsSendCommand.restype = c_uint
    EDSDK_DLL.EdsSendCommand.argtypes = [c_void_p, c_uint, c_int]

    # EdsSendStatusCommand (UI-Lock fuer atomare Host-Speicher-Konfiguration)
    EDSDK_DLL.EdsSendStatusCommand.restype = c_uint
    EDSDK_DLL.EdsSendStatusCommand.argtypes = [c_void_p, c_uint, c_int]
    
    # EdsSetPropertyData
    EDSDK_DLL.EdsSetPropertyData.restype = c_uint
    EDSDK_DLL.EdsSetPropertyData.argtypes = [c_void_p, c_uint, c_int, c_uint, c_void_p]
    
    # EdsGetPropertyData
    EDSDK_DLL.EdsGetPropertyData.restype = c_uint
    EDSDK_DLL.EdsGetPropertyData.argtypes = [c_void_p, c_uint, c_int, c_uint, c_void_p]
    
    # EdsSetCapacity
    EDSDK_DLL.EdsSetCapacity.restype = c_uint
    EDSDK_DLL.EdsSetCapacity.argtypes = [c_void_p, EdsCapacity]
    
    # EdsDownloadEvfImage (Live View)
    EDSDK_DLL.EdsDownloadEvfImage.restype = c_uint
    EDSDK_DLL.EdsDownloadEvfImage.argtypes = [c_void_p, c_void_p]
    
    # EdsCreateEvfImageRef
    EDSDK_DLL.EdsCreateEvfImageRef.restype = c_uint
    EDSDK_DLL.EdsCreateEvfImageRef.argtypes = [c_void_p, POINTER(c_void_p)]
    
    # EdsCreateMemoryStream
    EDSDK_DLL.EdsCreateMemoryStream.restype = c_uint
    # ------------------------------------------------------------------
    # 2.4.55 — 64-BIT-PARAMETER. Hier lag der Grund, warum das Herunterladen
    # eines Fotos scheiterte ("Download fehlgeschlagen (keine Daten)").
    #
    # Diese drei Funktionen nehmen laut EDSDK.h EdsUInt64 — also 64 Bit:
    #
    #     EdsCreateMemoryStream( EdsUInt64 inBufferSize, ... )
    #     EdsDownload( ..., EdsUInt64 inReadSize, ... )
    #     EdsGetLength( ..., EdsUInt64* outLength )
    #
    # Im Code standen sie als c_uint (32 Bit). Bei einem Aufruf mit falscher
    # Parameterbreite werden die Register falsch belegt: Die DLL bekommt eine
    # unsinnige Groesse und bricht ab. Das Foto war da, die Kamera hatte es
    # gemeldet — abholen liess es sich trotzdem nicht.
    #
    # Das ist derselbe Fehler wie beim Speicher-Layout von
    # EdsDirectoryItemInfo (2.4.48): 64-Bit-Feld als 32 Bit gelesen. Wer hier
    # etwas aendert, gleicht es bitte gegen den Header im Repo ab:
    # EDSDK/EDSDKv132010W/.../Header/EDSDK.h
    # ------------------------------------------------------------------
    EDSDK_DLL.EdsCreateMemoryStream.argtypes = [ctypes.c_uint64, POINTER(c_void_p)]
    
    # EdsGetPointer
    EDSDK_DLL.EdsGetPointer.restype = c_uint
    EDSDK_DLL.EdsGetPointer.argtypes = [c_void_p, POINTER(c_void_p)]
    
    # EdsGetLength
    EDSDK_DLL.EdsGetLength.restype = c_uint
    EDSDK_DLL.EdsGetLength.argtypes = [c_void_p, POINTER(ctypes.c_uint64)]
    
    # EdsSetObjectEventHandler - für Bild-Download Events
    EDSDK_DLL.EdsSetObjectEventHandler.restype = c_uint
    EDSDK_DLL.EdsSetObjectEventHandler.argtypes = [c_void_p, c_uint, EdsObjectEventHandler, c_void_p]

    # EdsSetCameraStateEventHandler - für Shutdown/Verbindungsstatus
    EDSDK_DLL.EdsSetCameraStateEventHandler.restype = c_uint
    EDSDK_DLL.EdsSetCameraStateEventHandler.argtypes = [
        c_void_p, c_uint, EdsStateEventHandler, c_void_p
    ]
    
    # EdsGetDirectoryItemInfo - Info über aufgenommenes Bild
    EDSDK_DLL.EdsGetDirectoryItemInfo.restype = c_uint
    EDSDK_DLL.EdsGetDirectoryItemInfo.argtypes = [c_void_p, POINTER(EdsDirectoryItemInfo)]
    
    # EdsDownload - Bild herunterladen
    EDSDK_DLL.EdsDownload.restype = c_uint
    EDSDK_DLL.EdsDownload.argtypes = [c_void_p, ctypes.c_uint64, c_void_p]
    
    # EdsDownloadComplete - Download abschließen
    EDSDK_DLL.EdsDownloadComplete.restype = c_uint
    EDSDK_DLL.EdsDownloadComplete.argtypes = [c_void_p]

    # EdsDownloadCancel - fehlgeschlagenen Transfer sauber abbrechen
    EDSDK_DLL.EdsDownloadCancel.restype = c_uint
    EDSDK_DLL.EdsDownloadCancel.argtypes = [c_void_p]
    
    # EdsCreateFileStream - File Stream für Download
    EDSDK_DLL.EdsCreateFileStream.restype = c_uint
    EDSDK_DLL.EdsCreateFileStream.argtypes = [c_char_p, c_uint, c_uint, POINTER(c_void_p)]
    
    # EdsGetEvent - Event-Polling (WICHTIG für Windows!)
    EDSDK_DLL.EdsGetEvent.restype = c_uint
    EDSDK_DLL.EdsGetEvent.argtypes = []


# ============================================================================
# High-Level API
# ============================================================================

_sdk_initialized = False

# ============================================================================
# Kamera-Faden (2.4.57)
# ============================================================================
#
# WARUM DAS NOETIG IST — der Kern des ganzen DSLR-Problems:
#
# Canons Bibliothek arbeitet innen mit COM im STA-Modell. Sie bindet sich an
# den Programmfaden, der sie zuerst startet. Jeder spaetere Aufruf aus einem
# ANDEREN Faden muss von COM dorthin vermittelt werden — und diese Vermittlung
# gelingt nur, wenn der urspruengliche Faden gerade Windows-Nachrichten
# abarbeitet. Tut er das nicht, bleibt der Aufruf haengen. Genau das passierte
# mit `EdsSetObjectEventHandler`: Der wartende Aufruf hielt die Kamera besetzt,
# danach gab es weder Live-View noch Fotos (Box-Log 24.08.2026).
#
# In der App wurde die Kamera aus ZWEI verschiedenen Faden gestartet:
#   - src/app.py `_pre_init_camera`      -> Haupt-Faden (ueber root.after)
#   - src/ui/dialogs/system_test.py:297  -> eigener Hintergrund-Faden
# Je nachdem, was zuerst lief, war die Bibliothek an den einen oder anderen
# gebunden — und der jeweils andere Weg hing.
#
# Loesung: EIN eigener Faden, der die Bibliothek startet und danach dauerhaft
# Nachrichten abarbeitet. Alles, was empfindlich auf den Faden reagiert
# (Starten, Sitzung oeffnen, Rueckkanal einrichten), laeuft ueber ihn.
#
# Der Faden ist ein daemon: Er haelt die App beim Beenden nicht auf.

_sdk_auftraege: "queue.Queue" = None
_sdk_prioritaets_auftraege: "queue.Queue" = None
_sdk_faden: Optional[threading.Thread] = None
_sdk_bereit: Optional[threading.Event] = None
_sdk_start_sperre = threading.Lock()
_sdk_op_nummern = itertools.count(1)
_sdk_aktiver_auftrag = None
_sdk_native_phase = None
_sdk_letzter_fortschritt = 0.0
_sdk_ungesund = False

_HEISSE_AUFTRAEGE = {
    "get_live_view_image",
    "get_event",
    "pump_windows_messages",
}


def _diag_aktiv() -> bool:
    """Dev-Modus dynamisch pruefen (beim Modulimport ist er noch nicht gesetzt)."""
    try:
        return is_developer_mode()
    except Exception:
        return False


def _thread_text(thread: Optional[threading.Thread] = None) -> str:
    thread = thread or threading.current_thread()
    return f"{thread.name}/{thread.ident}"


def _ergebnis_text(wert) -> str:
    """Sicherer Kurztext ohne Pointer, Bilddaten oder andere Nutzdaten."""
    if wert is None:
        return "None"
    if isinstance(wert, bool):
        return str(wert)
    if isinstance(wert, bytes):
        return f"bytes:{len(wert)}"
    if isinstance(wert, (list, tuple, dict)):
        return f"{type(wert).__name__}:{len(wert)}"
    if isinstance(wert, (int, float, str)):
        return type(wert).__name__
    return type(wert).__name__


def _owner_pruefen(context: str) -> bool:
    """Meldet jeden internen DLL-Einstieg außerhalb des Owner-Threads."""
    korrekt = threading.current_thread() is _sdk_faden
    if not korrekt:
        logger.error(
            "CANON-THREAD-VERSTOSS "
            f"op={context} ist={_thread_text()} "
            f"owner={_thread_text(_sdk_faden) if _sdk_faden else 'nicht-gestartet'}"
        )
    return korrekt


def _auftrag_anlegen(fn, args, kwargs, *, synchron: bool) -> dict:
    return {
        "id": next(_sdk_op_nummern),
        "fn": fn,
        "args": args,
        "kwargs": kwargs,
        "name": getattr(fn, "__name__", type(fn).__name__),
        "anforderer": _thread_text(),
        "eingestellt": time.monotonic(),
        "gestartet": None,
        "abgebrochen": False,
        "status": "queued",
        "sperre": threading.Lock(),
        "ergebnis": {},
        "fertig": threading.Event() if synchron else None,
    }


def _auftrag_einstellen(fn, *args, synchron: bool = False, **kwargs) -> dict:
    """Stellt auch aus einem nativen Callback nur asynchron in die Owner-Queue."""
    _sdk_faden_starten()
    auftrag = _auftrag_anlegen(fn, args, kwargs, synchron=synchron)
    ziel_queue = _sdk_auftraege if synchron else _sdk_prioritaets_auftraege
    ziel_queue.put(auftrag)
    if _diag_aktiv() and auftrag["name"] not in _HEISSE_AUFTRAEGE:
        logger.debug(
            "CANON-OWNER QUEUED "
            f"op_id={auftrag['id']} op={auftrag['name']} "
            f"from={auftrag['anforderer']} queue={_queue_tiefe()}"
        )
    return auftrag


def kamera_faden_asynchron(fn, *args, **kwargs) -> int:
    """Priorisierter Folgeauftrag; wichtig fuer kurze native Callbacks."""
    return _auftrag_einstellen(fn, *args, synchron=False, **kwargs)["id"]


def _queue_tiefe() -> int:
    normal = _sdk_auftraege.qsize() if _sdk_auftraege is not None else 0
    prio = (
        _sdk_prioritaets_auftraege.qsize()
        if _sdk_prioritaets_auftraege is not None else 0
    )
    return normal + prio


def _owner_stack() -> str:
    """Python-Stack des Owner-Threads fuer einen Dev-Mode-Timeout."""
    if not _sdk_faden or _sdk_faden.ident is None:
        return "Owner-Thread ohne Stack"
    frame = sys._current_frames().get(_sdk_faden.ident)
    if frame is None:
        return "Owner-Stack nicht verfuegbar"
    return "".join(traceback.format_stack(frame)).rstrip()


def _sdk_faden_schleife():
    """Besitzt SDK, Session, Referenzen, Handler und alle EDSDK-Aufrufe."""
    global _sdk_initialized, _sdk_aktiver_auftrag, _sdk_native_phase
    global _sdk_letzter_fortschritt

    com_hr = None
    if sys.platform == "win32":
        try:
            # COINIT_APARTMENTTHREADED = 0x2
            com_hr = ctypes.windll.ole32.CoInitializeEx(None, 0x2)
        except Exception as e:
            logger.error(f"CANON-OWNER CoInitializeEx fehlgeschlagen: {e}")

    if _diag_aktiv():
        logger.debug(
            "CANON-OWNER START "
            f"thread={_thread_text()} com_hr={com_hr} "
            f"python_bits={ctypes.sizeof(c_void_p) * 8}"
        )

    try:
        if not load_edsdk():
            return
        _setup_functions()
        _owner_pruefen("EdsInitializeSDK")
        err = EDSDK_DLL.EdsInitializeSDK()
        if check_error(err, "EdsInitializeSDK"):
            _sdk_initialized = True
            _sdk_letzter_fortschritt = time.monotonic()
            logger.info("EDSDK gestartet; Owner-Thread besitzt jetzt alle Canon-Aufrufe")
    except Exception as e:
        logger.error(f"EDSDK-Start im Owner-Thread fehlgeschlagen: {e}")
    finally:
        _sdk_bereit.set()

    if not _sdk_initialized:
        return

    from ctypes import wintypes
    user32 = ctypes.windll.user32 if sys.platform == "win32" else None
    msg = wintypes.MSG() if sys.platform == "win32" else None
    letzter_event_poll = 0.0
    lv_diag = {"seit": time.monotonic(), "anzahl": 0, "ok": 0, "ms": 0.0, "max_ms": 0.0}

    while True:
        try:
            auftrag = _sdk_prioritaets_auftraege.get_nowait()
        except queue.Empty:
            try:
                auftrag = _sdk_auftraege.get(timeout=0.02)
            except queue.Empty:
                auftrag = None

        if auftrag is not None:
            fertig = auftrag["fertig"]
            # Der Uebergang queued -> running/cancelled ist atomar. Sonst kann
            # ein Timeout genau zwischen der Abbruchpruefung und `gestartet`
            # landen und ein spaeterer Retry denselben Ausloeser verdoppeln.
            with auftrag["sperre"]:
                if auftrag["status"] == "cancelled":
                    abgebrochen = True
                else:
                    auftrag["status"] = "running"
                    auftrag["gestartet"] = time.monotonic()
                    abgebrochen = False

            if abgebrochen:
                auftrag["ergebnis"]["abgebrochen"] = True
                if fertig:
                    fertig.set()
            else:
                _sdk_aktiver_auftrag = auftrag
                warte_ms = (auftrag["gestartet"] - auftrag["eingestellt"]) * 1000
                heiss = auftrag["name"] in _HEISSE_AUFTRAEGE
                if _diag_aktiv() and not heiss:
                    logger.debug(
                        "CANON-OWNER START-OP "
                        f"op_id={auftrag['id']} op={auftrag['name']} "
                        f"from={auftrag['anforderer']} wait_ms={warte_ms:.1f} "
                        f"queue={_queue_tiefe()}"
                    )

                start = time.monotonic()
                try:
                    _owner_pruefen(auftrag["name"])
                    auftrag["ergebnis"]["wert"] = auftrag["fn"](
                        *auftrag["args"], **auftrag["kwargs"]
                    )
                except Exception as e:
                    auftrag["ergebnis"]["fehler"] = e
                    logger.exception(
                        f"CANON-OWNER EXCEPTION op_id={auftrag['id']} op={auftrag['name']}"
                    )
                finally:
                    dauer_ms = (time.monotonic() - start) * 1000
                    _sdk_letzter_fortschritt = time.monotonic()

                    if auftrag["name"] == "get_live_view_image":
                        lv_diag["anzahl"] += 1
                        lv_diag["ms"] += dauer_ms
                        lv_diag["max_ms"] = max(lv_diag["max_ms"], dauer_ms)
                        if auftrag["ergebnis"].get("wert"):
                            lv_diag["ok"] += 1
                    elif _diag_aktiv():
                        status = (
                            "exception" if "fehler" in auftrag["ergebnis"]
                            else _ergebnis_text(auftrag["ergebnis"].get("wert"))
                        )
                        logger.debug(
                            "CANON-OWNER END-OP "
                            f"op_id={auftrag['id']} op={auftrag['name']} "
                            f"call_ms={dauer_ms:.1f} result={status} "
                            f"queue={_queue_tiefe()}"
                        )

                    with auftrag["sperre"]:
                        auftrag["status"] = "finished"
                    _sdk_aktiver_auftrag = None
                    if fertig:
                        fertig.set()

        jetzt = time.monotonic()

        # Dieser Owner ist eine eigene, fensterlose STA. Deshalb hier zentral
        # EdsGetEvent pollen; UI- und Capture-Thread tun das nicht mehr.
        if _sdk_initialized and EDSDK_DLL is not None and jetzt - letzter_event_poll >= 0.05:
            letzter_event_poll = jetzt
            try:
                _owner_pruefen("EdsGetEvent/owner-loop")
                _sdk_native_phase = {
                    "name": "EdsGetEvent/owner-loop",
                    "gestartet": time.monotonic(),
                }
                err = EDSDK_DLL.EdsGetEvent()
                if err != EDS_ERR_OK and err not in HARMLOS:
                    check_error(err, "EdsGetEvent/owner-loop")
            except Exception as e:
                logger.debug(f"EdsGetEvent im Owner-Loop: {e}")
            finally:
                _sdk_native_phase = None
                _sdk_letzter_fortschritt = time.monotonic()

        if user32 is not None:
            try:
                while user32.PeekMessageW(byref(msg), None, 0, 0, 1):  # PM_REMOVE
                    user32.TranslateMessage(byref(msg))
                    user32.DispatchMessageW(byref(msg))
            except Exception as e:
                logger.debug(f"Windows-Message-Pump im Owner: {e}")

        if _diag_aktiv() and jetzt - lv_diag["seit"] >= 5.0:
            if lv_diag["anzahl"]:
                logger.debug(
                    "CANON-LIVEVIEW SUMMARY "
                    f"frames={lv_diag['anzahl']} ok={lv_diag['ok']} "
                    f"failed={lv_diag['anzahl'] - lv_diag['ok']} "
                    f"avg_ms={lv_diag['ms'] / lv_diag['anzahl']:.1f} "
                    f"max_ms={lv_diag['max_ms']:.1f} queue={_queue_tiefe()}"
                )
            lv_diag = {"seit": jetzt, "anzahl": 0, "ok": 0, "ms": 0.0, "max_ms": 0.0}


def _sdk_faden_starten() -> None:
    """Legt den einzigen Canon-Owner-Thread an und wartet auf SDK-Bereitschaft."""
    global _sdk_auftraege, _sdk_prioritaets_auftraege
    global _sdk_faden, _sdk_bereit, _sdk_ungesund

    with _sdk_start_sperre:
        if _sdk_faden is None or not _sdk_faden.is_alive():
            _sdk_auftraege = queue.Queue()
            _sdk_prioritaets_auftraege = queue.Queue()
            _sdk_bereit = threading.Event()
            _sdk_ungesund = False
            _sdk_faden = threading.Thread(
                target=_sdk_faden_schleife, daemon=True, name="edsdk-kamera"
            )
            _sdk_faden.start()

        # Auch der zweite parallele Aufrufer muss auf denselben Start warten.
        # Nur `Thread.is_alive()` bedeutet noch nicht, dass COM und EDSDK schon
        # initialisiert sind.
        bereit = _sdk_bereit

    if bereit is None or not bereit.wait(timeout=10.0):
        logger.error("CANON-OWNER wurde innerhalb von 10s nicht startbereit")


def im_kamera_faden(fn, *args, timeout: float = 20.0, **kwargs):
    """Fuehrt einen synchronen Auftrag garantiert im Canon-Owner-Thread aus."""
    global _sdk_ungesund

    _sdk_faden_starten()

    if threading.current_thread() is _sdk_faden:
        _owner_pruefen(getattr(fn, "__name__", type(fn).__name__))
        return fn(*args, **kwargs)

    if _sdk_ungesund:
        logger.error(
            "CANON-OWNER nimmt keinen weiteren Auftrag an, weil ein vorheriger "
            "nativer Aufruf nicht zurueckgekehrt ist"
        )
        return None

    auftrag = _auftrag_einstellen(fn, *args, synchron=True, **kwargs)
    fertig = auftrag["fertig"]
    if not fertig.wait(timeout):
        with auftrag["sperre"]:
            aktiv = auftrag["status"] == "running"
            if auftrag["status"] == "queued":
                # Noch nicht begonnen: Der Owner darf diesen veralteten Auftrag
                # spaeter nicht doch ausfuehren und damit einen Retry verdoppeln.
                auftrag["status"] = "cancelled"
                auftrag["abgebrochen"] = True

        # Auch wenn genau dieser Auftrag noch nicht begonnen hat, kann der
        # Owner in einem vorher priorisierten Callback-Download oder direkt in
        # EdsGetEvent feststecken. Nach einem synchronen Timeout wird deshalb
        # ausnahmslos gesperrt: Ein laufender ctypes-Aufruf kann in Python nicht
        # sicher beendet werden und weitere Auftraege duerfen sich nicht
        # dahinter stapeln.
        _sdk_ungesund = True

        owner_op = _sdk_aktiver_auftrag
        owner_name = (
            owner_op["name"] if owner_op
            else (_sdk_native_phase or {}).get("name", "kein Python-Auftrag")
        )
        owner_id = owner_op["id"] if owner_op else "-"
        logger.error(
            "CANON-OWNER TIMEOUT "
            f"op_id={auftrag['id']} op={auftrag['name']} timeout_s={timeout:.1f} "
            f"started={aktiv} owner_alive={bool(_sdk_faden and _sdk_faden.is_alive())} "
            f"owner_op_id={owner_id} owner_op={owner_name} "
            f"queue={_queue_tiefe()}"
        )
        if _diag_aktiv():
            logger.error("CANON-OWNER STACK\n" + _owner_stack())
        return None

    if auftrag["ergebnis"].get("abgebrochen"):
        return None
    if "fehler" in auftrag["ergebnis"]:
        raise auftrag["ergebnis"]["fehler"]
    return auftrag["ergebnis"].get("wert")


def kamera_faden_aufruf(*, timeout: float = 20.0):
    """Decorator: Jede oeffentliche EDSDK-Operation passiert im Owner."""
    def dekorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return im_kamera_faden(fn, *args, timeout=timeout, **kwargs)

        wrapper._edsdk_owner_dispatch = True
        return wrapper
    return dekorator


def owner_snapshot(*, fail_if_busy: bool = False) -> str:
    """Kompakter, pointerfreier Zustand fuer Capture-Timeout-Logs."""
    global _sdk_ungesund

    aktiv = _sdk_aktiver_auftrag
    if aktiv and aktiv.get("gestartet"):
        aktiv_seit_ms = (time.monotonic() - aktiv["gestartet"]) * 1000
        aktiv_text = f"{aktiv['id']}:{aktiv['name']}:{aktiv_seit_ms:.0f}ms"
    elif _sdk_native_phase and _sdk_native_phase.get("gestartet"):
        aktiv_seit_ms = (
            time.monotonic() - _sdk_native_phase["gestartet"]
        ) * 1000
        aktiv_text = (
            f"native:{_sdk_native_phase['name']}:{aktiv_seit_ms:.0f}ms"
        )
    else:
        aktiv_text = "idle"

    if fail_if_busy and aktiv_text != "idle":
        war_gesund = not _sdk_ungesund
        _sdk_ungesund = True
        if war_gesund:
            logger.error(
                "CANON-OWNER STALLED-AT-CAPTURE-TIMEOUT "
                f"active={aktiv_text} queue={_queue_tiefe()}"
            )
            if _diag_aktiv():
                logger.error("CANON-OWNER STACK\n" + _owner_stack())
    return (
        f"alive={bool(_sdk_faden and _sdk_faden.is_alive())},"
        f"healthy={not _sdk_ungesund},"
        f"active={aktiv_text},"
        f"queue={_queue_tiefe()},"
        f"initialized={_sdk_initialized}"
    )


def initialize() -> bool:
    """Startet das EDSDK — immer im eigenen Kamera-Faden."""
    if _sdk_initialized:
        return True

    _sdk_faden_starten()

    if not _sdk_initialized:
        logger.error("EDSDK konnte nicht gestartet werden")
        return False
    return True


def terminate():
    """Beendet das EDSDK im Owner, startet es beim App-Ende aber nicht neu."""
    if not _sdk_initialized or EDSDK_DLL is None or _sdk_faden is None:
        return
    return im_kamera_faden(_terminate_im_owner, timeout=10.0)


def _terminate_im_owner():
    global _sdk_initialized
    if not _sdk_initialized or EDSDK_DLL is None:
        return
    _owner_pruefen("EdsTerminateSDK")
    EDSDK_DLL.EdsTerminateSDK()
    _sdk_initialized = False
    logger.info("EDSDK beendet")


@kamera_faden_aufruf(timeout=15.0)
def get_camera_list() -> List[dict]:
    """Gibt Liste der angeschlossenen Kameras zurück"""
    if not initialize():
        return []
    
    cameras = []
    camera_list = c_void_p()
    
    err = EDSDK_DLL.EdsGetCameraList(byref(camera_list))
    if not check_error(err, "EdsGetCameraList"):
        return []
    
    count = c_int()
    err = EDSDK_DLL.EdsGetChildCount(camera_list, byref(count))
    if not check_error(err, "EdsGetChildCount"):
        EDSDK_DLL.EdsRelease(camera_list)
        return []
    
    logger.info(f"Gefundene Kameras: {count.value}")
    
    for i in range(count.value):
        camera_ref = c_void_p()
        err = EDSDK_DLL.EdsGetChildAtIndex(camera_list, i, byref(camera_ref))
        
        if check_error(err, f"EdsGetChildAtIndex({i})"):
            # Device Info holen
            device_info = EdsDeviceInfo()
            err = EDSDK_DLL.EdsGetDeviceInfo(camera_ref, byref(device_info))
            
            if check_error(err, "EdsGetDeviceInfo"):
                cameras.append({
                    "index": i,
                    "ref": camera_ref,
                    "name": device_info.szDeviceDescription.decode('utf-8', errors='ignore'),
                    "port": device_info.szPortName.decode('utf-8', errors='ignore'),
                })
            else:
                EDSDK_DLL.EdsRelease(camera_ref)
    
    EDSDK_DLL.EdsRelease(camera_list)
    return cameras


@kamera_faden_aufruf(timeout=15.0)
def open_session(camera_ref: c_void_p) -> bool:
    """Öffnet eine Session mit der Kamera
    
    Bei DEVICE_BUSY wird genau einmal sauber geschlossen und erneut geoeffnet.
    Ein SDK-Neustart mit derselben alten Referenz ist ungueltig und findet hier
    bewusst nicht mehr statt.
    """
    if EDSDK_DLL is None:
        return False
    
    import time
    
    err = EDSDK_DLL.EdsOpenSession(camera_ref)
    
    # Wenn Device Busy oder Session bereits offen
    if err in (EDS_ERR_DEVICE_BUSY, EDS_ERR_SESSION_ALREADY_OPEN):
        logger.warning(f"Session-Fehler {hex(err)}, versuche Cleanup...")
        
        # Versuche Session zu schließen
        try:
            EDSDK_DLL.EdsCloseSession(camera_ref)
            logger.info("Vorherige Session geschlossen")
        except Exception as e:
            logger.debug(f"CloseSession Fehler (ignoriert): {e}")
        
        # Kurz warten
        time.sleep(0.5)
        
        # Erneut versuchen
        err = EDSDK_DLL.EdsOpenSession(camera_ref)
        
        if err in (EDS_ERR_DEVICE_BUSY, EDS_ERR_SESSION_ALREADY_OPEN):
            logger.error(
                "Session bleibt blockiert. Kein SDK-Neustart mit der alten "
                "Kamera-Referenz; der Manager muss vollstaendig neu enumerieren."
            )
    
    return check_error(err, "EdsOpenSession")


@kamera_faden_aufruf(timeout=10.0)
def close_session(camera_ref: c_void_p):
    """Schließt die Session"""
    if EDSDK_DLL is None:
        return
    
    EDSDK_DLL.EdsCloseSession(camera_ref)


@kamera_faden_aufruf(timeout=10.0)
def release(ref: c_void_p) -> bool:
    """Gibt eine Canon-Referenz ausschliesslich im Owner-Thread frei."""
    if EDSDK_DLL is None or not ref:
        return False
    # EdsRelease liefert den verbleibenden Referenzzaehler, keinen Fehlercode.
    EDSDK_DLL.EdsRelease(ref)
    return True


@kamera_faden_aufruf(timeout=15.0)
def dispose_camera(camera_ref: c_void_p, session_open: bool) -> bool:
    """Schliesst/freigibt eine Kamera atomar und loest erst dann Callbacks.

    Die ctypes-Callbackobjekte muessen bis NACH `EdsRelease` am Leben bleiben.
    Getrennte Auftraege fuer Close/Clear/Release liessen den Owner dazwischen
    Events pumpen und konnten dadurch einen nativen Callback auf bereits von
    Python freigegebenen Code ausloesen.
    """
    if not camera_ref:
        return False

    key = _ref_key(camera_ref)
    freigegeben = False
    try:
        if EDSDK_DLL is None:
            return False

        if session_open:
            err = EDSDK_DLL.EdsCloseSession(camera_ref)
            if err != EDS_ERR_OK:
                check_error(err, "EdsCloseSession/Dispose")

        # EdsRelease gibt einen Referenzzaehler zurueck, keinen EdsError.
        EDSDK_DLL.EdsRelease(camera_ref)
        freigegeben = True
        return True
    finally:
        # Niemals vorher entfernen: Bis EdsRelease zurueckkehrt, darf die DLL
        # die registrierten Funktionszeiger noch verwenden.
        if freigegeben or EDSDK_DLL is None:
            _object_event_handlers.pop(key, None)
            _state_event_handlers.pop(key, None)


@kamera_faden_aufruf(timeout=10.0)
def send_command(camera_ref: c_void_p, command: int, parameter: int) -> int:
    """Owner-sicherer Rohbefehl fuer das DSLR-Diagnosewerkzeug."""
    if EDSDK_DLL is None:
        return EDS_ERR_DEVICE_NOT_FOUND
    err = EDSDK_DLL.EdsSendCommand(camera_ref, command, parameter)
    check_error(err, f"EdsSendCommand({hex(command)}, {hex(parameter)})")
    return err


@kamera_faden_aufruf(timeout=10.0)
def cancel_download(dir_item: c_void_p) -> bool:
    """Beendet einen fehlgeschlagenen Host-Transfer und gibt die Kamera frei."""
    if EDSDK_DLL is None or not dir_item:
        return False
    err = EDSDK_DLL.EdsDownloadCancel(dir_item)
    if err == EDS_ERR_OK:
        logger.info("CANON-TRANSFER CANCEL erfolgreich")
        return True
    return check_error(err, "EdsDownloadCancel")


@kamera_faden_aufruf(timeout=10.0)
def take_picture(
    camera_ref: c_void_p,
    live_view_aktiv: bool = False,
    before_shutter=None,
) -> bool:
    """Loest die Kamera aus — genau so, wie Canons eigenes Beispiel es tut.

    2.4.52 — ZURUECK AUF DEN REFERENZWEG.

    Canons Beispielcode liegt im Repo unter
    EDSDK/.../sample/CSharp/CameraControl/Command/TakePictureCommand.cs
    und besteht aus genau zwei Zeilen:

        EdsSendCommand(cam, PressShutterButton, ShutterButton_Completely);
        EdsSendCommand(cam, PressShutterButton, ShutterButton_OFF);

    Kein halber Druck davor, keine Pause dazwischen, und der Live-View wird
    nicht abgeschaltet.

    In 2.4.49 wurde hier ein halber Druck mit 0,35 s Pause eingebaut, damit der
    Autofokus vorher arbeiten kann. Gut gemeint, aber es war eine Abweichung
    vom Referenzweg — und im Box-Log vom 24.08.2026 hat sie zwei Dinge
    angerichtet:

      - Das Ausloesen dauerte **2,5 Sekunden** statt Millisekunden
        (09:37:41.861 Befehl raus -> 09:37:44.427 bestaetigt), weil der
        Autofokus im halben Druck erst suchte.
      - Ein Foto kam trotzdem nicht an: Der Kartenstand blieb ueber den
        ganzen Testlauf bei 1735.

    Der Autofokus geht dabei nicht verloren: `ShutterButton_Completely`
    schliesst das Scharfstellen mit ein — das ist der normale Ablauf, wenn man
    den Ausloeser in einem Zug durchdrueckt.

    Args:
        camera_ref: Kamera-Referenz
        live_view_aktiv: nur fuers Log — welcher Zustand herrschte?

    Returns:
        True wenn die Kamera den Ausloesebefehl angenommen hat
    """
    global letzter_fehler

    if EDSDK_DLL is None:
        letzter_fehler = EDS_ERR_DEVICE_NOT_FOUND
        return False

    PRESS = kEdsCameraCommand_PressShutterButton

    # Der Hook laeuft im selben Owner-Auftrag unmittelbar vor dem nativen
    # Capture-Befehl. Der Manager nutzt ihn, um seine Queue erst NACH allen
    # vorher priorisierten Transfer-Events fuer genau diesen Capture zu
    # scharfschalten.
    if before_shutter is not None:
        try:
            before_shutter()
        except Exception as e:
            letzter_fehler = 0x00000008  # UNEXPECTED_EXCEPTION
            logger.exception(f"Capture konnte nicht scharfgeschaltet werden: {e}")
            return False

    err = EDSDK_DLL.EdsSendCommand(
        camera_ref, PRESS, kEdsCameraCommand_ShutterButton_Completely
    )

    # Ausloeser IMMER wieder freigeben — bleibt er gedrueckt, ignoriert die
    # Kamera den naechsten Befehl.
    release_err = None
    try:
        release_err = EDSDK_DLL.EdsSendCommand(
            camera_ref, PRESS, kEdsCameraCommand_ShutterButton_OFF
        )
    except Exception as e:
        logger.exception(f"Ausloeser freigeben warf eine Exception: {e}")

    logger.info(
        "CANON-CAPTURE SHUTTER "
        f"press={ERROR_NAMES.get(err, 'UNBEKANNT')}({hex(err)}) "
        f"release={ERROR_NAMES.get(release_err, 'EXCEPTION') if release_err is not None else 'EXCEPTION'}"
        f"({hex(release_err) if release_err is not None else '-'}) "
        f"live_view={'an' if live_view_aktiv else 'aus'}"
    )

    # Kein stiller zweiter Ausloeseversuch bei AF_NG: Ein Aufruf dieser
    # Funktion bedeutet exakt einen Capture-Befehl. Sonst koennte ein spaet
    # eintreffendes erstes Bild zusammen mit dem Retry zwei Fotos erzeugen.
    if err != EDS_ERR_OK:
        if release_err not in (None, EDS_ERR_OK):
            check_error(release_err, "PressShutterButton OFF nach Capture-Fehler")
        check_error(err, "PressShutterButton Completely")
        if err == EDS_ERR_TAKE_PICTURE_AF_NG:
            logger.error(
                "Autofokus fand keinen Halt; kein automatischer Zweitausloeser"
            )
        return False

    if release_err is None:
        letzter_fehler = 0x00000008  # UNEXPECTED_EXCEPTION
        return False
    if not check_error(release_err, "PressShutterButton OFF"):
        return False

    letzter_fehler = EDS_ERR_OK
    return True


@kamera_faden_aufruf(timeout=10.0)
def set_save_to_host(camera_ref: c_void_p) -> bool:
    """Konfiguriert und bestaetigt den Host-Speicher einmal pro Session.

    Canon erwartet nach ``SaveTo=Host`` eine Capacity-Meldung. Beides wird
    hier in einem einzigen Owner-Auftrag eingerichtet. Erst nach bestaetigtem
    SaveTo-Readback und plausiblen freien Aufnahmen darf ausgelöst werden.
    """
    global letzter_fehler

    if EDSDK_DLL is None:
        letzter_fehler = EDS_ERR_DEVICE_NOT_FOUND
        return False

    start = time.monotonic()
    logger.info("CANON-HOST CONFIG START save_to=Host capacity_reset=1")

    save_to = c_uint(kEdsSaveTo_Host)
    err = EDSDK_DLL.EdsSetPropertyData(
        camera_ref,
        kEdsPropID_SaveTo,
        0,
        ctypes.sizeof(save_to),
        byref(save_to)
    )

    if not check_error(err, "SetSaveTo"):
        return False
    logger.info("CANON-HOST SAVE-TO SET value=Host")

    lock_err = EDSDK_DLL.EdsSendStatusCommand(
        camera_ref, kEdsCameraStatusCommand_UILock, 0
    )
    if not check_error(lock_err, "UILock vor SetCapacity"):
        return False
    logger.info("CANON-HOST UILOCK ok=True")

    capacity = EdsCapacity()
    capacity.numberOfFreeClusters = 0x7FFFFFFF
    capacity.bytesPerSector = 0x1000
    capacity.reset = 1

    capacity_ok = False
    try:
        capacity_err = EDSDK_DLL.EdsSetCapacity(camera_ref, capacity)
        capacity_ok = check_error(
            capacity_err, "SetCapacity beim Session-Aufbau"
        )
    finally:
        unlock_err = EDSDK_DLL.EdsSendStatusCommand(
            camera_ref, kEdsCameraStatusCommand_UIUnLock, 0
        )

    if unlock_err != EDS_ERR_OK:
        check_error(unlock_err, "UIUnLock nach SetCapacity")
        return False
    if not capacity_ok:
        return False
    logger.info("CANON-HOST CAPACITY ok=True reset=1")
    logger.info("CANON-HOST UIUNLOCK ok=True")

    def _lese_uint_roh(prop_id: int) -> Tuple[Optional[int], int]:
        wert = c_uint()
        lese_err = EDSDK_DLL.EdsGetPropertyData(
            camera_ref, prop_id, 0, ctypes.sizeof(wert), byref(wert)
        )
        return (wert.value if lese_err == EDS_ERR_OK else None), lese_err

    # Manche Bodies aktualisieren diese Werte erst einige Millisekunden nach
    # SetCapacity. Das kurze Polling verhindert CARD_NG beim Kaltstart.
    save_to_deadline = time.monotonic() + 1.0
    gelesenes_save_to = None
    while True:
        gelesenes_save_to, read_err = _lese_uint_roh(kEdsPropID_SaveTo)
        if read_err != EDS_ERR_OK:
            check_error(read_err, "GetSaveTo nach Host-Konfiguration")
            return False
        if gelesenes_save_to == kEdsSaveTo_Host:
            break
        if time.monotonic() >= save_to_deadline:
            logger.error(
                "CANON-HOST NOT-READY reason=save_to "
                f"expected={kEdsSaveTo_Host} actual={gelesenes_save_to}"
            )
            letzter_fehler = EDS_ERR_OBJECT_NOTREADY
            return False
        time.sleep(0.05)

    available_shots = None
    shots_deadline = time.monotonic() + 1.0
    while True:
        available_shots, shots_err = _lese_uint_roh(kEdsPropID_AvailableShots)
        if shots_err != EDS_ERR_OK:
            logger.warning(
                "CANON-HOST AvailableShots nicht auslesbar; "
                "SaveTo=Host und SetCapacity sind bestaetigt "
                f"error={ERROR_NAMES.get(shots_err, hex(shots_err))}"
            )
            available_shots = None
            break
        if available_shots == 0xFFFFFFFF:
            logger.warning(
                "CANON-HOST AvailableShots unbekannt (0xffffffff); "
                "SaveTo=Host und SetCapacity sind bestaetigt"
            )
            break
        if 1 <= available_shots <= 0x7FFFFFFF:
            break
        if available_shots == 0 and time.monotonic() < shots_deadline:
            time.sleep(0.05)
            continue
        logger.error(
            "CANON-HOST NOT-READY reason=available_shots "
            f"value={available_shots}"
        )
        letzter_fehler = EDS_ERR_MEMORYSTATUS_NOTREADY
        return False

    letzter_fehler = EDS_ERR_OK
    logger.info(
        "CANON-HOST READY "
        f"save_to=Host available_shots={available_shots} "
        f"duration_ms={(time.monotonic() - start) * 1000:.1f}"
    )
    return True

@kamera_faden_aufruf(timeout=10.0)
def set_save_to_camera(camera_ref: c_void_p) -> bool:
    """Konfiguriert Speicherung auf SD-Karte (für Directory-Polling Capture)

    Diese Einstellung ist notwendig wenn man das Bild über Directory-Enumeration
    herunterladen möchte statt über Event-Callbacks.
    """
    if EDSDK_DLL is None:
        return False

    # Save to Camera (SD-Karte)
    save_to = c_uint(kEdsSaveTo_Camera)
    err = EDSDK_DLL.EdsSetPropertyData(
        camera_ref,
        kEdsPropID_SaveTo,
        0,
        ctypes.sizeof(save_to),
        byref(save_to)
    )

    if check_error(err, "SetSaveTo(Camera)"):
        logger.info("SaveTo auf Camera (SD-Karte) gesetzt")
        return True
    return False


@kamera_faden_aufruf(timeout=10.0)
def set_image_quality_jpg(camera_ref: c_void_p) -> bool:
    """Setzt die Bildqualität auf JPG Large Fine (beste JPG Qualität, kein RAW)

    Returns:
        True wenn erfolgreich
    """
    if EDSDK_DLL is None:
        return False

    quality = c_uint(EdsImageQuality_LJF)
    err = EDSDK_DLL.EdsSetPropertyData(
        camera_ref,
        kEdsPropID_ImageQuality,
        0,
        ctypes.sizeof(quality),
        byref(quality)
    )

    if check_error(err, "SetImageQuality"):
        logger.info("Bildqualität auf JPG Large Fine gesetzt")
        return True
    else:
        logger.warning("Bildqualität konnte nicht gesetzt werden (evtl. manuell prüfen)")
        return False


@kamera_faden_aufruf(timeout=10.0)
def get_property_uint(camera_ref: c_void_p, prop_id: int) -> Optional[int]:
    """Liest eine Zahl-Eigenschaft der Kamera aus (Akku, Wahlrad, Fokus-Art ...).

    2.4.46 — Nur fuer die Diagnose im Log. Bewusst leise: Nicht jede Kamera
    kennt jede Eigenschaft, und ein "kann ich nicht" ist hier kein Fehler,
    sondern eine Information. Deshalb KEIN check_error() (das wuerde rote
    Zeilen ins Log schreiben, die niemanden interessieren).
    """
    if EDSDK_DLL is None:
        return None

    try:
        wert = c_uint()
        err = EDSDK_DLL.EdsGetPropertyData(
            camera_ref, prop_id, 0, ctypes.sizeof(wert), byref(wert)
        )
        if err == EDS_ERR_OK:
            return wert.value
        logger.debug(
            f"Eigenschaft 0x{prop_id:04x} nicht lesbar: "
            f"{ERROR_NAMES.get(err, 'UNBEKANNT')} ({hex(err)})"
        )
        return None
    except Exception as e:
        logger.debug(f"get_property_uint(0x{prop_id:04x}) Fehler: {e}")
        return None


@kamera_faden_aufruf(timeout=10.0)
def get_property_snapshot(camera_ref: c_void_p, prop_ids) -> dict:
    """Liest mehrere Diagnosewerte atomar in einem Owner-Auftrag.

    Nicht unterstützte Eigenschaften werden als ``None`` zurückgegeben. Das
    ist reine Dev-Diagnose und darf einen Capture nie verhindern.
    """
    ergebnis = {}
    if EDSDK_DLL is None:
        return {prop_id: None for prop_id in prop_ids}

    for prop_id in prop_ids:
        try:
            wert = c_uint()
            err = EDSDK_DLL.EdsGetPropertyData(
                camera_ref, prop_id, 0, ctypes.sizeof(wert), byref(wert)
            )
            ergebnis[prop_id] = wert.value if err == EDS_ERR_OK else None
        except Exception:
            ergebnis[prop_id] = None
    return ergebnis


@kamera_faden_aufruf(timeout=10.0)
def get_image_quality(camera_ref: c_void_p) -> Optional[int]:
    """Liest die aktuelle Bildqualität-Einstellung

    Returns:
        Bildqualität-Wert oder None bei Fehler
    """
    if EDSDK_DLL is None:
        return None

    quality = c_uint()
    err = EDSDK_DLL.EdsGetPropertyData(
        camera_ref,
        kEdsPropID_ImageQuality,
        0,
        ctypes.sizeof(quality),
        byref(quality)
    )

    if check_error(err, "GetImageQuality"):
        return quality.value
    return None


@kamera_faden_aufruf(timeout=10.0)
def get_save_to(camera_ref: c_void_p) -> Optional[int]:
    """Liest die aktuelle SaveTo-Einstellung

    Returns:
        1=Camera, 2=Host, 3=Both, oder None bei Fehler
    """
    if EDSDK_DLL is None:
        return None

    save_to = c_uint()
    err = EDSDK_DLL.EdsGetPropertyData(
        camera_ref,
        kEdsPropID_SaveTo,
        0,
        ctypes.sizeof(save_to),
        byref(save_to)
    )

    if check_error(err, "GetSaveTo"):
        return save_to.value
    return None


@kamera_faden_aufruf(timeout=15.0)
def log_camera_settings(camera_ref: c_void_p):
    """Loggt die aktuellen Kamera-Einstellungen (für Debugging)"""
    logger.info("=== Aktuelle Kamera-Einstellungen ===")

    # SaveTo
    save_to = get_save_to(camera_ref)
    save_to_names = {1: "Camera", 2: "Host", 3: "Both"}
    logger.info(f"  SaveTo: {save_to_names.get(save_to, f'Unknown({save_to})')}")

    # Image Quality
    quality = get_image_quality(camera_ref)
    quality_names = {
        EdsImageQuality_LJF: "JPG Large Fine",
        EdsImageQuality_LJN: "JPG Large Normal",
        EdsImageQuality_MJF: "JPG Medium Fine",
        EdsImageQuality_SJF: "JPG Small Fine",
    }
    quality_name = quality_names.get(quality, f"Unknown(0x{quality:08x})" if quality else "None")
    logger.info(f"  ImageQuality: {quality_name}")

    # 2.4.46: Zusätzliche Werte fürs Box-Protokoll. Auf den Tests am
    # 21.08.2026 stand im Log nur "ImageQuality: Unknown(0x0e13ff0f)" — damit
    # war weder Akkustand noch Programmwahlrad noch Fokus-Art zu sehen, obwohl
    # jeder dieser Punkte ein Auslösen verhindern kann.
    def _zeige(propid: int, name: str, namen: dict = None):
        wert = get_property_uint(camera_ref, propid)
        if wert is None:
            logger.info(f"  {name}: nicht auslesbar")
            return
        if namen and wert in namen:
            logger.info(f"  {name}: {namen[wert]}")
        else:
            logger.info(f"  {name}: 0x{wert:08x}")

    _zeige(kEdsPropID_BatteryLevel, "Akku", {
        0: "LEER (Kamera löst gleich nicht mehr aus!)",
        1: "sehr schwach",
        2: "schwach",
        4: "voll genug",
        0x7fffffff: "Netzteil/USB-Strom",
    })
    _zeige(kEdsPropID_AEMode, "Programmwahlrad", AE_MODE_NAMEN)
    _zeige(kEdsPropID_AFMode, "Fokus-Art", {
        0: "One-Shot AF", 1: "AI Servo AF", 2: "AI Focus AF",
        3: "MANUELL (MF) — gut für die Box",
        0xffffffff: "unbekannt",
    })
    _zeige(kEdsPropID_AvailableShots, "Freie Aufnahmen")

    belichtungskorrektur = get_property_uint(
        camera_ref, kEdsPropID_ExposureCompensation
    )
    if belichtungskorrektur is None:
        logger.info("  Belichtungskorrektur: nicht auslesbar")
    else:
        belichtung_text = EXPOSURE_COMP_NAMEN.get(
            belichtungskorrektur,
            EXPOSURE_COMP_NAMEN.get(
                belichtungskorrektur & 0xFF, f"0x{belichtungskorrektur:08x}"
            ),
        )
        logger.info(f"  Belichtungskorrektur: {belichtung_text}")
        if belichtungskorrektur not in (0, 0xFFFFFFFF):
            logger.warning(
                "CANON-BELICHTUNG WARNUNG: Belichtungskorrektur steht auf "
                f"{belichtung_text}; die Software verändert diesen Kamerawert nicht"
            )

    logger.info("=" * 40)


@kamera_faden_aufruf(timeout=10.0)
def start_live_view(camera_ref: c_void_p) -> bool:
    """Startet Live View"""
    if EDSDK_DLL is None:
        return False
    
    # Live View auf PC aktivieren
    device = c_uint(kEdsEvfOutputDevice_PC)
    err = EDSDK_DLL.EdsSetPropertyData(
        camera_ref,
        kEdsPropID_Evf_OutputDevice,
        0,
        ctypes.sizeof(device),
        byref(device)
    )
    
    return check_error(err, "StartLiveView")


@kamera_faden_aufruf(timeout=10.0)
def stop_live_view(camera_ref: c_void_p):
    """Stoppt Live View"""
    if EDSDK_DLL is None:
        return
    
    device = c_uint(0)
    EDSDK_DLL.EdsSetPropertyData(
        camera_ref,
        kEdsPropID_Evf_OutputDevice,
        0,
        ctypes.sizeof(device),
        byref(device)
    )


@kamera_faden_aufruf(timeout=10.0)
def get_live_view_image(camera_ref: c_void_p) -> Optional[bytes]:
    """Holt ein Live View Frame als JPEG bytes"""
    global letzter_fehler

    if EDSDK_DLL is None:
        return None

    stream = c_void_p()
    evf_image = c_void_p()
    try:
        err = EDSDK_DLL.EdsCreateMemoryStream(0, byref(stream))
        if not check_error(err, "CreateMemoryStream"):
            return None

        err = EDSDK_DLL.EdsCreateEvfImageRef(stream, byref(evf_image))
        if not check_error(err, "CreateEvfImageRef"):
            return None

        err = EDSDK_DLL.EdsDownloadEvfImage(camera_ref, evf_image)
        if not check_error(err, "DownloadEvfImage"):
            return None

        length = ctypes.c_uint64()
        err = EDSDK_DLL.EdsGetLength(stream, byref(length))
        if not check_error(err, "GetLength(EVF)"):
            return None
        if length.value <= 0 or length.value > 100 * 1024 * 1024:
            logger.error(f"Unplausible Live-View-Streamlaenge: {length.value}")
            return None

        pointer = c_void_p()
        err = EDSDK_DLL.EdsGetPointer(stream, byref(pointer))
        if not check_error(err, "GetPointer(EVF)"):
            return None

        return ctypes.string_at(pointer, length.value)

    except Exception as e:
        logger.error(f"Fehler beim Holen des Live View: {e}")
        return None
    finally:
        if evf_image:
            try:
                release(evf_image)
            except Exception:
                pass
        if stream:
            try:
                release(stream)
            except Exception:
                pass


# ============================================================================
# Image Download API
# ============================================================================

# File Stream Access Modes
kEdsAccess_Read = 0
kEdsAccess_Write = 1
kEdsAccess_ReadWrite = 2

# File Create Disposition
kEdsFileCreateDisposition_CreateNew = 0
kEdsFileCreateDisposition_CreateAlways = 1
kEdsFileCreateDisposition_OpenExisting = 2
kEdsFileCreateDisposition_OpenAlways = 3
kEdsFileCreateDisposition_TruncateExisting = 4

# Globaler Storage fuer native Callback-Objekte (muessen am Leben bleiben).
_object_event_handlers = {}
_state_event_handlers = {}

OBJECT_EVENT_NAMEN = {
    kEdsObjectEvent_DirItemCreated: "DirItemCreated",
    kEdsObjectEvent_DirItemRequestTransfer: "DirItemRequestTransfer",
    kEdsObjectEvent_DirItemRequestTransferDT: "DirItemRequestTransferDT",
}

STATE_EVENT_NAMEN = {
    kEdsStateEvent_Shutdown: "Shutdown",
    kEdsStateEvent_JobStatusChanged: "JobStatusChanged",
    kEdsStateEvent_WillSoonShutDown: "WillSoonShutDown",
    kEdsStateEvent_ShutDownTimerUpdate: "ShutDownTimerUpdate",
    kEdsStateEvent_CaptureError: "CaptureError",
    kEdsStateEvent_InternalError: "InternalError",
}


def _ref_key(ref) -> int:
    if isinstance(ref, c_void_p):
        return int(ref.value or 0)
    return int(ref or 0)


def _als_void_p(ref) -> c_void_p:
    return ref if isinstance(ref, c_void_p) else c_void_p(ref)


def _object_event_ausliefern(callback, event: int, obj_ref: c_void_p) -> None:
    """Laeuft nach Rueckkehr des nativen Callbacks als normaler Owner-Auftrag."""
    transfer = event in (
        kEdsObjectEvent_DirItemRequestTransfer,
        kEdsObjectEvent_DirItemRequestTransferDT,
    )
    behandelt = False
    try:
        behandelt = callback(event, obj_ref) is True
    except Exception:
        logger.exception(
            f"CANON-EVENT Verarbeitung fehlgeschlagen event=0x{event:08x}"
        )
    finally:
        if transfer and not behandelt:
            # Der Callback hat den Transfer nicht bis Complete/Cancel gebracht.
            # Ohne Cancel bleibt der Kamerapuffer belegt.
            try:
                cancel_download(obj_ref)
            except Exception as e:
                logger.error(f"CANON-TRANSFER Cancel nach Callback-Fehler: {e}")
        if obj_ref:
            try:
                release(obj_ref)
            except Exception as e:
                logger.error(f"CANON-EVENT Release fehlgeschlagen: {e}")


def _state_event_ausliefern(callback, event: int, event_data: int) -> None:
    try:
        callback(event, event_data)
    except Exception:
        logger.exception(
            f"CANON-STATE Verarbeitung fehlgeschlagen event=0x{event:08x}"
        )


@kamera_faden_aufruf(timeout=5.0)
def get_event() -> bool:
    """Pollt EDSDK Events (MUSS regelmäßig aufgerufen werden auf Windows!)

    Ohne diesen Aufruf werden Event-Callbacks nicht ausgeführt.
    Dies ist KRITISCH für die Foto-Aufnahme!

    Returns:
        True wenn erfolgreich
    """
    if EDSDK_DLL is None:
        return False

    try:
        err = EDSDK_DLL.EdsGetEvent()
        # Nur loggen wenn Fehler (nicht bei jedem Poll)
        if err != EDS_ERR_OK:
            logger.debug(f"EdsGetEvent returned: {hex(err)}")
        return err == EDS_ERR_OK
    except Exception as e:
        logger.debug(f"EdsGetEvent Exception: {e}")
        return False


@kamera_faden_aufruf(timeout=5.0)
def pump_windows_messages(max_nachrichten: int = 50) -> int:
    """Arbeitet wartende Windows-Nachrichten des aufrufenden Fadens ab.

    2.4.46 — Warum das nötig ist:

    Das EDSDK arbeitet innen mit COM. Wenn die Kamera meldet "Bild ist fertig",
    kommt das nicht als direkter Funktionsaufruf, sondern als Windows-Nachricht
    an den Programmfaden. Wird die Nachrichtenschlange nicht geleert, bleibt die
    Meldung liegen — der Rückruf im Programm feuert nie.

    Der Haupt-Faden mit der Bedienoberfläche tut das von allein (Tk macht das).
    Neben-Fäden — wie der Aufnahme-Faden seit dem Umbau — tun es NICHT. Genau
    dort wartete die Foto-Aufnahme, und genau deshalb kam nie ein Bild an.

    Returns:
        Anzahl abgearbeiteter Nachrichten
    """
    if sys.platform != "win32":
        return 0

    try:
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        msg = wintypes.MSG()
        anzahl = 0
        # PM_REMOVE = 1
        while anzahl < max_nachrichten and user32.PeekMessageW(byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))
            anzahl += 1
        return anzahl
    except Exception as e:
        logger.debug(f"pump_windows_messages Fehler: {e}")
        return 0


@kamera_faden_aufruf(timeout=5.0)
def set_object_event_handler(camera_ref: c_void_p, callback, context=None) -> bool:
    """Registriert den Object-Handler auf demselben STA wie SDK und Session.

    Der native Callback selbst stellt nur einen Folgeauftrag ein und kehrt
    sofort zur DLL zurueck. Download/Cancel/Release passieren erst danach.
    """
    global letzter_fehler

    if EDSDK_DLL is None:
        letzter_fehler = EDS_ERR_DEVICE_NOT_FOUND
        return False

    def c_callback(event, obj_ref, ctx):
        try:
            ref = _als_void_p(obj_ref) if obj_ref else c_void_p()
            op_id = kamera_faden_asynchron(
                _object_event_ausliefern, callback, int(event), ref
            )
            logger.info(
                "CANON-EVENT QUEUED "
                f"event=0x{int(event):08x} "
                f"name={OBJECT_EVENT_NAMEN.get(int(event), 'unbekannt')} "
                f"has_ref={bool(obj_ref)} op_id={op_id} callback_thread={_thread_text()}"
            )
        except Exception as e:
            logger.error(f"CANON-EVENT Callback konnte nicht eingereiht werden: {e}")
        return EDS_ERR_OK

    c_callback_obj = EdsObjectEventHandler(c_callback)
    key = _ref_key(camera_ref)
    _object_event_handlers[key] = c_callback_obj

    logger.info(
        "CANON-HANDLER REGISTER object "
        f"event_all=0x{kEdsObjectEvent_All:08x} thread={_thread_text()}"
    )
    err = EDSDK_DLL.EdsSetObjectEventHandler(
        camera_ref, kEdsObjectEvent_All, c_callback_obj, None
    )
    if not check_error(err, "EdsSetObjectEventHandler"):
        _object_event_handlers.pop(key, None)
        return False
    logger.info("CANON-HANDLER READY object")
    return True


@kamera_faden_aufruf(timeout=5.0)
def set_state_event_handler(camera_ref: c_void_p, callback, context=None) -> bool:
    """Registriert Shutdown-/Statusereignisse auf dem Canon-Owner-Thread."""
    if EDSDK_DLL is None:
        return False

    def c_callback(event, event_data, ctx):
        try:
            op_id = kamera_faden_asynchron(
                _state_event_ausliefern,
                callback,
                int(event),
                int(event_data),
            )
            logger.info(
                "CANON-STATE QUEUED "
                f"event=0x{int(event):08x} "
                f"name={STATE_EVENT_NAMEN.get(int(event), 'unbekannt')} "
                f"data={int(event_data)} op_id={op_id} callback_thread={_thread_text()}"
            )
        except Exception as e:
            logger.error(f"CANON-STATE Callback konnte nicht eingereiht werden: {e}")
        return EDS_ERR_OK

    c_callback_obj = EdsStateEventHandler(c_callback)
    key = _ref_key(camera_ref)
    _state_event_handlers[key] = c_callback_obj

    logger.info(
        "CANON-HANDLER REGISTER state "
        f"event_all=0x{kEdsStateEvent_All:08x} thread={_thread_text()}"
    )
    err = EDSDK_DLL.EdsSetCameraStateEventHandler(
        camera_ref, kEdsStateEvent_All, c_callback_obj, None
    )
    if not check_error(err, "EdsSetCameraStateEventHandler"):
        _state_event_handlers.pop(key, None)
        return False
    logger.info("CANON-HANDLER READY state")
    return True


@kamera_faden_aufruf(timeout=20.0)
def download_image(dir_item: c_void_p, save_path: str) -> bool:
    """Laedt ein Transferbild in eine Datei; immer Complete oder Cancel."""
    if EDSDK_DLL is None:
        return False

    stream = c_void_p()
    transfer_abgeschlossen = False
    try:
        dir_info = EdsDirectoryItemInfo()
        err = EDSDK_DLL.EdsGetDirectoryItemInfo(dir_item, byref(dir_info))
        if not check_error(err, "GetDirectoryItemInfo"):
            return False

        file_size = dir_info.size
        logger.info(f"CANON-TRANSFER DATEI START announced_bytes={file_size}")

        err = EDSDK_DLL.EdsCreateFileStream(
            save_path.encode('utf-8'),
            kEdsFileCreateDisposition_CreateAlways,
            kEdsAccess_ReadWrite,
            byref(stream)
        )
        if not check_error(err, "CreateFileStream"):
            return False
        
        err = EDSDK_DLL.EdsDownload(dir_item, file_size, stream)
        if not check_error(err, "Download"):
            return False

        err = EDSDK_DLL.EdsDownloadComplete(dir_item)
        if not check_error(err, "DownloadComplete"):
            return False
        transfer_abgeschlossen = True

        logger.info(f"CANON-TRANSFER DATEI COMPLETE bytes={file_size}")
        return True

    except Exception as e:
        logger.error(f"Fehler beim Herunterladen des Bildes: {e}")
        return False
    finally:
        if not transfer_abgeschlossen:
            try:
                cancel_download(dir_item)
            except Exception:
                pass
        if stream:
            try:
                release(stream)
            except Exception:
                pass


@kamera_faden_aufruf(timeout=20.0)
def download_image_to_memory(dir_item: c_void_p) -> Optional[bytes]:
    """Laedt ein Host-Transferbild; beendet jeden Weg mit Complete oder Cancel."""
    if EDSDK_DLL is None:
        return None

    stream = c_void_p()
    transfer_abgeschlossen = False
    start = time.monotonic()

    try:
        dir_info = EdsDirectoryItemInfo()
        err = EDSDK_DLL.EdsGetDirectoryItemInfo(dir_item, byref(dir_info))
        if not check_error(err, "GetDirectoryItemInfo"):
            return None

        file_size = dir_info.size
        dateiname = bytes(dir_info.szFileName).split(b"\0", 1)[0].decode(
            "utf-8", errors="replace"
        )
        logger.info(
            "CANON-TRANSFER START "
            f"file={dateiname or '-'} format=0x{int(dir_info.format):08x} "
            f"announced_bytes={file_size} thread={_thread_text()}"
        )

        if file_size <= 0 or file_size > 500 * 1024 * 1024:
            logger.error(
                f"CANON-TRANSFER unplausible Groesse: {file_size} Bytes"
            )
            return None

        err = EDSDK_DLL.EdsCreateMemoryStream(file_size, byref(stream))
        if not check_error(err, "CreateMemoryStream"):
            return None

        err = EDSDK_DLL.EdsDownload(dir_item, file_size, stream)
        if not check_error(err, "Download"):
            return None

        err = EDSDK_DLL.EdsDownloadComplete(dir_item)
        if not check_error(err, "DownloadComplete"):
            return None
        transfer_abgeschlossen = True

        pointer = c_void_p()
        err = EDSDK_DLL.EdsGetPointer(stream, byref(pointer))
        if not check_error(err, "GetPointer"):
            return None

        length = ctypes.c_uint64()
        err = EDSDK_DLL.EdsGetLength(stream, byref(length))
        if not check_error(err, "GetLength"):
            return None

        if length.value <= 0 or length.value > file_size:
            logger.error(
                "CANON-TRANSFER unplausibler Stream "
                f"announced_bytes={file_size} received_bytes={length.value}"
            )
            return None

        data = ctypes.string_at(pointer, length.value)
        logger.info(
            "CANON-TRANSFER COMPLETE "
            f"file={dateiname or '-'} format=0x{int(dir_info.format):08x} "
            f"announced_bytes={file_size} received_bytes={len(data)} "
            f"duration_ms={(time.monotonic() - start) * 1000:.1f}"
        )
        return data

    except Exception as e:
        logger.exception(f"CANON-TRANSFER Exception: {e}")
        return None
    finally:
        if not transfer_abgeschlossen:
            try:
                cancel_download(dir_item)
            except Exception as e:
                logger.error(f"CANON-TRANSFER Cancel fehlgeschlagen: {e}")
        if stream:
            try:
                release(stream)
            except Exception as e:
                logger.error(f"CANON-TRANSFER Stream-Release fehlgeschlagen: {e}")


# ============================================================================
# Directory Enumeration API (für Polling-basiertes Capture)
# ============================================================================

@kamera_faden_aufruf(timeout=10.0)
def get_first_volume(camera_ref: c_void_p) -> Optional[c_void_p]:
    """Holt das erste Volume (Speicher) der Kamera

    Returns:
        Volume-Referenz oder None
    """
    if EDSDK_DLL is None:
        return None

    count = c_int()
    err = EDSDK_DLL.EdsGetChildCount(camera_ref, byref(count))
    if not check_error(err, "GetChildCount(camera)"):
        return None

    if count.value == 0:
        logger.warning("Keine Volumes auf der Kamera gefunden")
        return None

    volume = c_void_p()
    err = EDSDK_DLL.EdsGetChildAtIndex(camera_ref, 0, byref(volume))
    if not check_error(err, "GetChildAtIndex(volume)"):
        return None

    return volume


@kamera_faden_aufruf(timeout=10.0)
def get_dcim_folder(volume_ref: c_void_p) -> Optional[c_void_p]:
    """Findet den DCIM-Ordner auf dem Volume

    Returns:
        DCIM-Ordner Referenz oder None
    """
    if EDSDK_DLL is None:
        return None

    count = c_int()
    err = EDSDK_DLL.EdsGetChildCount(volume_ref, byref(count))
    if not check_error(err, "GetChildCount(volume)"):
        return None

    for i in range(count.value):
        item = c_void_p()
        err = EDSDK_DLL.EdsGetChildAtIndex(volume_ref, i, byref(item))
        if not check_error(err, f"GetChildAtIndex({i})"):
            continue

        info = EdsDirectoryItemInfo()
        err = EDSDK_DLL.EdsGetDirectoryItemInfo(item, byref(info))
        if check_error(err, "GetDirectoryItemInfo"):
            name = info.szFileName.decode('utf-8', errors='ignore').upper()
            if name == "DCIM" and info.isFolder:
                logger.debug(f"DCIM Ordner gefunden")
                return item

        EDSDK_DLL.EdsRelease(item)

    logger.warning("DCIM Ordner nicht gefunden")
    return None


@kamera_faden_aufruf(timeout=10.0)
def get_latest_folder(parent_ref: c_void_p) -> Optional[c_void_p]:
    """Findet den zuletzt erstellten Unterordner (z.B. 100CANON)

    Returns:
        Ordner-Referenz oder None
    """
    if EDSDK_DLL is None:
        return None

    count = c_int()
    err = EDSDK_DLL.EdsGetChildCount(parent_ref, byref(count))
    if not check_error(err, "GetChildCount(parent)"):
        return None

    if count.value == 0:
        return None

    # Letzten Ordner holen (neuester ist typischerweise der letzte)
    latest_folder = None
    latest_index = -1

    for i in range(count.value):
        item = c_void_p()
        err = EDSDK_DLL.EdsGetChildAtIndex(parent_ref, i, byref(item))
        if not check_error(err, f"GetChildAtIndex({i})"):
            continue

        info = EdsDirectoryItemInfo()
        err = EDSDK_DLL.EdsGetDirectoryItemInfo(item, byref(info))
        if check_error(err, "GetDirectoryItemInfo") and info.isFolder:
            name = info.szFileName.decode('utf-8', errors='ignore')
            # Den mit dem höchsten Index nehmen (z.B. 103CANON > 100CANON)
            if latest_folder is not None:
                EDSDK_DLL.EdsRelease(latest_folder)
            latest_folder = item
            latest_index = i
            logger.debug(f"Ordner gefunden: {name}")
        else:
            EDSDK_DLL.EdsRelease(item)

    return latest_folder


@kamera_faden_aufruf(timeout=10.0)
def get_latest_image_in_folder(folder_ref: c_void_p) -> Optional[c_void_p]:
    """Findet das neueste Bild in einem Ordner

    Returns:
        Bild-Referenz oder None
    """
    if EDSDK_DLL is None:
        return None

    count = c_int()
    err = EDSDK_DLL.EdsGetChildCount(folder_ref, byref(count))
    if not check_error(err, "GetChildCount(folder)"):
        return None

    if count.value == 0:
        logger.warning("Keine Dateien im Ordner")
        return None

    # Letzte Datei ist typischerweise das neueste Bild
    item = c_void_p()
    err = EDSDK_DLL.EdsGetChildAtIndex(folder_ref, count.value - 1, byref(item))
    if not check_error(err, "GetChildAtIndex(latest)"):
        return None

    info = EdsDirectoryItemInfo()
    err = EDSDK_DLL.EdsGetDirectoryItemInfo(item, byref(info))
    if check_error(err, "GetDirectoryItemInfo"):
        name = info.szFileName.decode('utf-8', errors='ignore')
        logger.info(f"Neuestes Bild: {name} ({info.size} bytes)")
        return item

    EDSDK_DLL.EdsRelease(item)
    return None


@kamera_faden_aufruf(timeout=10.0)
def count_images_in_folder(folder_ref: c_void_p) -> int:
    """Zählt die Bilder in einem Ordner

    Returns:
        Anzahl der Dateien
    """
    if EDSDK_DLL is None:
        return 0

    count = c_int()
    err = EDSDK_DLL.EdsGetChildCount(folder_ref, byref(count))
    if check_error(err, "GetChildCount"):
        return count.value
    return 0


@kamera_faden_aufruf(timeout=20.0)
def download_latest_image(camera_ref: c_void_p) -> Optional[bytes]:
    """Lädt das neueste Bild von der Kamera

    Navigiert durch: Camera -> Volume -> DCIM -> LatestFolder -> LatestImage

    Returns:
        Bild als bytes oder None
    """
    if EDSDK_DLL is None:
        return None

    volume = None
    dcim = None
    folder = None
    image = None

    try:
        # Volume holen
        volume = get_first_volume(camera_ref)
        if not volume:
            logger.error("Kein Volume gefunden")
            return None

        # DCIM finden
        dcim = get_dcim_folder(volume)
        if not dcim:
            logger.error("DCIM nicht gefunden")
            return None

        # Neuesten Unterordner finden
        folder = get_latest_folder(dcim)
        if not folder:
            logger.error("Kein Foto-Ordner gefunden")
            return None

        # Neuestes Bild finden
        image = get_latest_image_in_folder(folder)
        if not image:
            logger.error("Kein Bild im Ordner gefunden")
            return None

        # Bild herunterladen
        data = download_image_to_memory(image)
        return data

    finally:
        # Aufräumen (in umgekehrter Reihenfolge)
        if image:
            EDSDK_DLL.EdsRelease(image)
        if folder:
            EDSDK_DLL.EdsRelease(folder)
        if dcim:
            EDSDK_DLL.EdsRelease(dcim)
        if volume:
            EDSDK_DLL.EdsRelease(volume)


@kamera_faden_aufruf(timeout=10.0)
def _zaehle_bilder_frisch(camera_ref: c_void_p) -> Tuple[int, Optional[c_void_p]]:
    """Zaehlt die Bilder auf der Karte — mit FRISCH geholten Verzeichnis-Objekten.

    2.4.49 — DAS IST DER KERN DES PROBLEMS GEWESEN.

    Das EDSDK merkt sich den Inhalt eines Verzeichnis-Objekts beim ersten
    Abfragen. Ruft man `EdsGetChildCount` spaeter erneut auf DEMSELBEN Objekt
    auf, kommt weiterhin der alte Stand zurueck — auch wenn die Kamera
    inzwischen ein Foto abgelegt hat. Das Verzeichnis muss neu geholt werden.

    Genau das erklaert den Box-Log vom 21.08.2026:

        12:01 Test:  Aktuelle Bildanzahl: 1726  -> Timeout, kein neues Bild
        12:16 Test:  Aktuelle Bildanzahl: 1729  -> Timeout, kein neues Bild

    Zwischen beiden Tests sind DREI Fotos dazugekommen — die Kamera hat also
    sehr wohl ausgeloest und gespeichert (Christian hoerte den Spiegel). Nur
    innerhalb der Wartezeit stieg die Zahl nie, weil immer dieselbe
    eingefrorene Verzeichnisliste befragt wurde.

    Returns:
        (Anzahl Bilder, Ordner-Referenz) — die Referenz muss vom Aufrufer
        freigegeben werden, sie wird zum Herunterladen noch gebraucht.
    """
    if EDSDK_DLL is None:
        return 0, None

    volume = None
    dcim = None
    folder = None

    try:
        volume = get_first_volume(camera_ref)
        if not volume:
            return 0, None

        dcim = get_dcim_folder(volume)
        if not dcim:
            return 0, None

        folder = get_latest_folder(dcim)
        if not folder:
            return 0, None

        anzahl = count_images_in_folder(folder)
        # Ordner wandert zum Aufrufer, deshalb hier NICHT freigeben
        ergebnis_folder = folder
        folder = None
        return anzahl, ergebnis_folder
    finally:
        for ref in (folder, dcim, volume):
            if ref:
                try:
                    EDSDK_DLL.EdsRelease(ref)
                except Exception:
                    pass


def get_card_image_count(camera_ref: c_void_p) -> int:
    """Liest eine frische Karten-Baseline und gibt alle Hilfsreferenzen frei."""
    anzahl, folder = _zaehle_bilder_frisch(camera_ref)
    if folder:
        release(folder)
    return anzahl


def wait_for_new_image(
    camera_ref: c_void_p,
    timeout: float = 10.0,
    poll_interval: float = 0.3,
    baseline: Optional[int] = None,
) -> Optional[bytes]:
    """Wartet nach dem Ausloesen auf das neue Bild und laedt es von der Karte.

    2.4.49 — komplett ueberarbeitet. Vorher wurde das Verzeichnis EINMAL
    geholt und dann in der Schleife immer wieder dasselbe Objekt befragt. Das
    EDSDK liefert darauf aber den eingefrorenen Stand von vorhin, sodass ein
    neu hinzugekommenes Foto nie auffiel — die Schleife lief immer in den
    Timeout, obwohl das Bild laengst auf der Karte lag.

    Jetzt wird bei jedem Durchgang frisch nachgesehen.

    Args:
        camera_ref: Kamera-Referenz
        timeout: Maximale Wartezeit in Sekunden
        poll_interval: Zeit zwischen zwei Blicken auf die Karte

    Returns:
        Bild als bytes oder None bei Timeout/Fehler
    """
    import time

    if EDSDK_DLL is None:
        return None

    # Produktionscode liefert die Baseline VOR dem Ausloesen. Der optionale
    # Rueckfall erhaelt alte Diagnose-Aufrufer, darf aber nicht als korrekter
    # Capture-Ablauf missverstanden werden.
    if baseline is None:
        logger.warning(
            "Karten-Baseline wurde erst beim Warten angefordert; "
            "Produktionscode muss sie vor dem Ausloesen erfassen"
        )
        baseline = get_card_image_count(camera_ref)
    start_anzahl = baseline

    logger.info(f"Bilder auf der Karte vor der Aufnahme: {start_anzahl}")

    start_time = time.time()
    letzte_meldung = 0.0

    while time.time() - start_time < timeout:
        time.sleep(poll_interval)

        anzahl, folder = _zaehle_bilder_frisch(camera_ref)

        try:
            if anzahl > start_anzahl:
                vergangen = time.time() - start_time
                logger.info(
                    f"Neues Foto auf der Karte nach {vergangen:.1f}s "
                    f"({start_anzahl} -> {anzahl})"
                )

                if not folder:
                    logger.error("Ordner verschwunden, obwohl ein Bild gezaehlt wurde")
                    return None

                # Der Kamera einen Moment lassen, die Datei fertigzuschreiben.
                time.sleep(0.2)

                image = get_latest_image_in_folder(folder)
                if not image:
                    logger.error("Neues Bild gezaehlt, aber nicht auffindbar")
                    return None

                try:
                    return download_image_to_memory(image)
                finally:
                    release(image)

            # Alle 3 s ein Lebenszeichen, damit im Log steht, dass wirklich
            # nachgesehen wird (und nicht nur stumpf gewartet).
            vergangen = time.time() - start_time
            if vergangen - letzte_meldung >= 3.0:
                letzte_meldung = vergangen
                logger.debug(f"Warte auf Foto … {vergangen:.0f}s, Karte hat {anzahl} Bilder")
        finally:
            if folder:
                try:
                    release(folder)
                except Exception:
                    pass

    logger.error(
        f"Timeout nach {timeout}s — auf der Karte kam kein neues Foto an "
        f"(Stand blieb bei {start_anzahl}). Hat die Kamera ausgeloest?"
    )
    return None


# Cleanup bei Programmende
import atexit
atexit.register(terminate)
