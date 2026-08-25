"""Canon EDSDK Python Wrapper (ctypes)

Low-level wrapper für Canon EDSDK DLL.
Basiert auf EDSDK v13.20.10
"""

import ctypes
from ctypes import c_uint, c_int, c_void_p, c_char_p, POINTER, byref, Structure, c_ubyte
import os
import queue
import sys
import threading
from typing import Optional, List, Tuple
from pathlib import Path

from src.utils.logging import get_logger

logger = get_logger(__name__)

# ============================================================================
# DLL Loading
# ============================================================================

EDSDK_DLL = None

def _find_edsdk_dll() -> Optional[str]:
    """Sucht die EDSDK.dll"""
    # Mögliche Pfade
    search_paths = [
        # Im Repo
        Path(__file__).parent.parent.parent / "EDSDK" / "EDSDKv132010W" / "EDSDKv132010W" / "Windows" / "EDSDK_64" / "Dll",
        # Im fexobooth Ordner auf Windows
        Path("C:/fexobooth/EDSDK_64/Dll"),
        Path("C:/fexobooth/fexobooth-v2/EDSDK/EDSDKv132010W/EDSDKv132010W/Windows/EDSDK_64/Dll"),
        # Neben der exe
        Path("."),
    ]
    
    for path in search_paths:
        dll_path = path / "EDSDK.dll"
        if dll_path.exists():
            logger.info(f"EDSDK.dll gefunden: {dll_path}")
            return str(dll_path.parent)
    
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
        os.add_dll_directory(dll_dir)
        
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
    0x0000a101,  # DEVICE_BUSY (EVF) - nächster Frame klappt wieder
}


def ist_verbindung_tot(err: int) -> bool:
    """True wenn dieser Fehlercode heißt: Kamera-Verbindung neu aufbauen."""
    return err in VERBINDUNG_TOT


# Zuletzt von check_error() gesehener Fehlercode. Die Kamera-Schicht (canon.py)
# liest ihn aus, um zu entscheiden ob ein Verbindungs-Neuaufbau nötig ist.
# Ohne das kam nur ein nacktes False zurück und der Grund ging verloren.
letzter_fehler: int = 0

# 2.4.56: Ist EdsSetObjectEventHandler auf diesem Rechner schon einmal haengen
# geblieben? Dann nie wieder aufrufen — siehe Begruendung dort.
_handler_haengt_dauerhaft: bool = False


def check_error(err: int, context: str = "") -> bool:
    """Prüft EDSDK Fehlercode

    2.4.46: Harmlose Codes (Live-View noch nicht warm) landen nur noch als DEBUG
    im Log. Vorher standen dafür pro Abend zehntausende rote ERROR-Zeilen drin,
    zwischen denen die echten Fehler untergingen.
    """
    global letzter_fehler

    if err == EDS_ERR_OK:
        return True

    letzter_fehler = err
    err_name = ERROR_NAMES.get(err, "UNBEKANNT")

    if err in HARMLOS:
        logger.debug(f"EDSDK {hex(err)} ({err_name}) bei {context} - normal, kein Fehler")
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
kEdsPropID_AvailableShots = 0x0000040a  # freie Aufnahmen
kEdsPropID_WhiteBalance = 0x00000106    # Weissabgleich (AWB schwankt pro Foto!)
kEdsPropID_ISOSpeed = 0x00000402        # ISO
kEdsPropID_Av = 0x00000405              # Blende
kEdsPropID_Tv = 0x00000406              # Belichtungszeit (Verwacklungsgefahr!)

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
    0x08: "f/1.0", 0x0b: "f/1.2", 0x10: "f/1.4", 0x15: "f/1.8", 0x18: "f/2.0",
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

WB_NAMEN = {
    0: "Auto (AWB) — schwankt pro Foto!", 1: "Tageslicht", 2: "Schatten",
    3: "Wolkig", 4: "Kunstlicht", 5: "Leuchtstoff", 6: "Blitz",
    8: "Manuell (fest)", 9: "Farbtemperatur (fest)",
}

# Image Quality Werte (für JPG)
# Format: 0x00LLSSpp (LL=LargeSize, SS=SecondarySize, pp=Primary/Secondary type)
EdsImageQuality_LJF = 0x0013000f   # Large Fine JPG (beste JPG Qualität)
EdsImageQuality_LJN = 0x0012000f   # Large Normal JPG
EdsImageQuality_MJF = 0x0113000f   # Medium Fine JPG
EdsImageQuality_SJF = 0x0213000f   # Small Fine JPG

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
kEdsObjectEvent_DirItemRequestTransfer = 0x00000108
kEdsObjectEvent_DirItemCreated = 0x00000100

# State Events  
kEdsStateEvent_Shutdown = 0x00000001
kEdsStateEvent_WillSoonShutDown = 0x00000005


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
    
    # EdsSendCommand
    EDSDK_DLL.EdsSendCommand.restype = c_uint
    EDSDK_DLL.EdsSendCommand.argtypes = [c_void_p, c_uint, c_int]
    
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
    
    # EdsGetDirectoryItemInfo - Info über aufgenommenes Bild
    EDSDK_DLL.EdsGetDirectoryItemInfo.restype = c_uint
    EDSDK_DLL.EdsGetDirectoryItemInfo.argtypes = [c_void_p, POINTER(EdsDirectoryItemInfo)]
    
    # EdsDownload - Bild herunterladen
    EDSDK_DLL.EdsDownload.restype = c_uint
    EDSDK_DLL.EdsDownload.argtypes = [c_void_p, ctypes.c_uint64, c_void_p]
    
    # EdsDownloadComplete - Download abschließen
    EDSDK_DLL.EdsDownloadComplete.restype = c_uint
    EDSDK_DLL.EdsDownloadComplete.argtypes = [c_void_p]
    
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
_sdk_faden = None
_sdk_bereit = None


def _sdk_faden_schleife():
    """Startet die Bibliothek und arbeitet danach dauerhaft Nachrichten ab."""
    global _sdk_initialized

    # Eigenes COM-Apartment (STA) fuer diesen Faden anmelden. Ohne das steckt
    # ein Python-Faden in keinem definierten Apartment, und COM entscheidet
    # selbst — meist zu unseren Ungunsten.
    if sys.platform == "win32":
        try:
            # COINIT_APARTMENTTHREADED = 0x2
            ctypes.windll.ole32.CoInitializeEx(None, 0x2)
        except Exception as e:
            logger.debug(f"CoInitializeEx: {e}")

    try:
        if not load_edsdk():
            _sdk_bereit.set()
            return
        _setup_functions()

        err = EDSDK_DLL.EdsInitializeSDK()
        if check_error(err, "EdsInitializeSDK"):
            _sdk_initialized = True
            logger.info("EDSDK gestartet (eigener Kamera-Faden)")
    except Exception as e:
        logger.error(f"EDSDK-Start im Kamera-Faden fehlgeschlagen: {e}")
    finally:
        _sdk_bereit.set()

    # Dauerbetrieb: Auftraege abarbeiten UND Nachrichten pumpen. Das Pumpen ist
    # der eigentliche Zweck — nur dadurch koennen Aufrufe aus anderen Faden
    # ueberhaupt fertig werden, statt haengenzubleiben.
    from ctypes import wintypes
    user32 = ctypes.windll.user32 if sys.platform == "win32" else None
    msg = wintypes.MSG() if sys.platform == "win32" else None

    while True:
        try:
            auftrag = _sdk_auftraege.get(timeout=0.02)
        except Exception:
            auftrag = None

        if auftrag is not None:
            fn, args, kwargs, ergebnis, fertig = auftrag
            try:
                ergebnis["wert"] = fn(*args, **kwargs)
            except Exception as e:
                ergebnis["fehler"] = e
            finally:
                fertig.set()

        if user32 is not None:
            try:
                while user32.PeekMessageW(byref(msg), None, 0, 0, 1):  # PM_REMOVE
                    user32.TranslateMessage(byref(msg))
                    user32.DispatchMessageW(byref(msg))
            except Exception:
                pass


def _sdk_faden_starten() -> None:
    """Legt den Kamera-Faden an (einmalig) und wartet, bis er bereit ist."""
    global _sdk_auftraege, _sdk_faden, _sdk_bereit

    if _sdk_faden is not None and _sdk_faden.is_alive():
        return

    import queue as _queue
    import threading as _threading

    _sdk_auftraege = _queue.Queue()
    _sdk_bereit = _threading.Event()
    _sdk_faden = _threading.Thread(
        target=_sdk_faden_schleife, daemon=True, name="edsdk-kamera"
    )
    _sdk_faden.start()
    _sdk_bereit.wait(timeout=10.0)


def im_kamera_faden(fn, *args, timeout: float = 20.0, **kwargs):
    """Fuehrt fn im Kamera-Faden aus und wartet auf das Ergebnis.

    Damit laufen alle empfindlichen Aufrufe garantiert im selben Faden, in dem
    die Bibliothek gestartet wurde — unabhaengig davon, wer sie anstoesst.
    """
    import threading as _threading

    _sdk_faden_starten()

    # Sind wir schon im Kamera-Faden? Dann direkt ausfuehren, sonst warten wir
    # auf uns selbst.
    if _threading.current_thread() is _sdk_faden:
        return fn(*args, **kwargs)

    ergebnis = {}
    fertig = _threading.Event()
    _sdk_auftraege.put((fn, args, kwargs, ergebnis, fertig))

    if not fertig.wait(timeout):
        logger.error(
            f"Kamera-Faden antwortet seit {timeout:.0f}s nicht "
            f"({getattr(fn, '__name__', fn)})"
        )
        return None

    if "fehler" in ergebnis:
        raise ergebnis["fehler"]
    return ergebnis.get("wert")


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
    """Beendet das EDSDK"""
    global _sdk_initialized
    
    if not _sdk_initialized or EDSDK_DLL is None:
        return
    
    EDSDK_DLL.EdsTerminateSDK()
    _sdk_initialized = False
    logger.info("EDSDK beendet")


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


def open_session(camera_ref: c_void_p) -> bool:
    """Öffnet eine Session mit der Kamera
    
    Behandelt DEVICE_BUSY (0xc0) durch:
    1. Versuch die Session erst zu schließen
    2. Kurz warten und erneut versuchen
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
            logger.warning("Session immer noch blockiert, versuche SDK-Neustart...")
            
            # SDK komplett neu initialisieren
            global _sdk_initialized
            try:
                EDSDK_DLL.EdsTerminateSDK()
            except:
                pass
            _sdk_initialized = False
            
            time.sleep(1.0)
            
            if not initialize():
                logger.error("SDK-Neustart fehlgeschlagen")
                return False
            
            # Letzter Versuch
            err = EDSDK_DLL.EdsOpenSession(camera_ref)
    
    return check_error(err, "EdsOpenSession")


def close_session(camera_ref: c_void_p):
    """Schließt die Session"""
    if EDSDK_DLL is None:
        return
    
    EDSDK_DLL.EdsCloseSession(camera_ref)


def take_picture(camera_ref: c_void_p, live_view_aktiv: bool = False) -> bool:
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
    if EDSDK_DLL is None:
        return False

    PRESS = kEdsCameraCommand_PressShutterButton

    err = EDSDK_DLL.EdsSendCommand(
        camera_ref, PRESS, kEdsCameraCommand_ShutterButton_Completely
    )

    # Ausloeser IMMER wieder freigeben — bleibt er gedrueckt, ignoriert die
    # Kamera den naechsten Befehl.
    try:
        EDSDK_DLL.EdsSendCommand(
            camera_ref, PRESS, kEdsCameraCommand_ShutterButton_OFF
        )
    except Exception as e:
        logger.debug(f"Ausloeser freigeben fehlgeschlagen: {e}")

    if err == EDS_ERR_OK:
        return True

    name = ERROR_NAMES.get(err, "UNBEKANNT")

    if err == EDS_ERR_TAKE_PICTURE_AF_NG:
        # Autofokus hat nichts gefunden. Zweiter Versuch ohne AF-Zwang, damit
        # ueberhaupt ein Bild entsteht.
        logger.warning(
            "Autofokus fand keinen Halt — zweiter Versuch ohne Fokus-Zwang"
        )
        err2 = EDSDK_DLL.EdsSendCommand(
            camera_ref, PRESS, kEdsCameraCommand_ShutterButton_Completely_NonAF
        )
        try:
            EDSDK_DLL.EdsSendCommand(
                camera_ref, PRESS, kEdsCameraCommand_ShutterButton_OFF
            )
        except Exception:
            pass
        if err2 == EDS_ERR_OK:
            return True
        name = ERROR_NAMES.get(err2, "UNBEKANNT")

    logger.error(
        f"Ausloesen abgelehnt: {name} ({hex(err)}), "
        f"Live-View war {'an' if live_view_aktiv else 'aus'}"
    )
    return False


def set_save_to_host(camera_ref: c_void_p) -> bool:
    """Konfiguriert Speicherung zum PC (für Event-basiertes Capture)"""
    if EDSDK_DLL is None:
        return False

    # Save to Host
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

    # Capacity setzen (damit Kamera weiß dass PC genug Platz hat)
    capacity = EdsCapacity()
    capacity.numberOfFreeClusters = 0x7FFFFFFF
    capacity.bytesPerSector = 0x1000
    capacity.reset = 1

    err = EDSDK_DLL.EdsSetCapacity(camera_ref, capacity)
    return check_error(err, "SetCapacity")


def melde_freien_speicher(camera_ref: c_void_p) -> bool:
    """Sagt der Kamera, dass am Rechner Platz fuer das naechste Foto ist.

    2.4.53 — Warum das VOR JEDER Aufnahme noetig ist:

    Im Direktbetrieb (Kamera liefert ans Notebook statt auf die Karte) glaubt
    die Kamera nur dann, dass sie ausloesen darf, wenn ihr jemand freien
    Speicher gemeldet hat. Diese Meldung ist fluechtig: Nach einer Aufnahme,
    nach einem Verbindungswackler oder nach dem Aufwachen aus dem Ruhezustand
    steht sie wieder auf null — und dann bewegt die Kamera zwar den Spiegel,
    legt das Bild aber nirgends ab.

    Genau dieses Bild zeigte das Box-Log vom 24.08.2026: Ausloesen hoerbar,
    danach kam nichts an.

    Der Aufruf kostet Millisekunden. Ihn vor jeder Aufnahme zu wiederholen ist
    billiger, als einmal pro Abend ein Foto zu verlieren.
    """
    if EDSDK_DLL is None:
        return False

    capacity = EdsCapacity()
    capacity.numberOfFreeClusters = 0x7FFFFFFF
    capacity.bytesPerSector = 0x1000
    capacity.reset = 1

    err = EDSDK_DLL.EdsSetCapacity(camera_ref, capacity)
    return check_error(err, "SetCapacity")


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
        0x0013000f: "JPG Large Fine",
        0x0012000f: "JPG Large Normal",
        0x0113000f: "JPG Medium Fine",
        0x0213000f: "JPG Small Fine",
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
    _zeige(kEdsPropID_AEMode, "Programmwahlrad", {
        0: "P (Programmautomatik)", 1: "Tv", 2: "Av", 3: "M (manuell)",
        4: "Bulb", 5: "A-DEP", 6: "DEP", 8: "Vollautomatik (grünes Feld)",
        9: "Blitz aus", 11: "Portrait", 12: "Landschaft", 13: "Makro",
        14: "Sport", 15: "Nachtportrait", 19: "Kreativautomatik",
        20: "Video", 0x17: "Szeneautomatik",
    })
    _zeige(kEdsPropID_AFMode, "Fokus-Art", {
        0: "One-Shot AF", 1: "AI Servo AF", 2: "AI Focus AF",
        3: "MANUELL (MF) — gut für die Box",
        0xffffffff: "unbekannt",
    })
    _zeige(kEdsPropID_AvailableShots, "Freie Aufnahmen")

    logger.info("=" * 40)


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


def get_live_view_image(camera_ref: c_void_p) -> Optional[bytes]:
    """Holt ein Live View Frame als JPEG bytes"""
    if EDSDK_DLL is None:
        return None
    
    try:
        # Memory Stream erstellen
        stream = c_void_p()
        err = EDSDK_DLL.EdsCreateMemoryStream(0, byref(stream))
        if not check_error(err, "CreateMemoryStream"):
            return None
        
        # EVF Image Ref erstellen
        evf_image = c_void_p()
        err = EDSDK_DLL.EdsCreateEvfImageRef(stream, byref(evf_image))
        if not check_error(err, "CreateEvfImageRef"):
            EDSDK_DLL.EdsRelease(stream)
            return None
        
        # Live View Image holen
        err = EDSDK_DLL.EdsDownloadEvfImage(camera_ref, evf_image)
        if not check_error(err, "DownloadEvfImage"):
            EDSDK_DLL.EdsRelease(evf_image)
            EDSDK_DLL.EdsRelease(stream)
            return None
        
        # Daten aus Stream holen.
        #
        # 2.4.58: c_uint64, NICHT c_uint. In 2.4.55 wurde die Signatur von
        # EdsGetLength korrekt auf 64 Bit umgestellt — aber DIESE Aufrufstelle
        # blieb auf c_uint stehen. Ergebnis auf der Box: 166 Mal
        # "expected LP_c_ulonglong instead of pointer to c_ulong", kein
        # einziges Vorschaubild, schwarzer Schirm.
        #
        # Lehre: Wer eine Signatur aendert, muss JEDE Aufrufstelle mitziehen —
        # ctypes prueft das erst zur Laufzeit, der Fehler faellt beim Start
        # nicht auf.
        length = ctypes.c_uint64()
        EDSDK_DLL.EdsGetLength(stream, byref(length))

        pointer = c_void_p()
        EDSDK_DLL.EdsGetPointer(stream, byref(pointer))
        
        # Bytes kopieren
        data = ctypes.string_at(pointer, length.value)
        
        # Aufräumen
        EDSDK_DLL.EdsRelease(evf_image)
        EDSDK_DLL.EdsRelease(stream)
        
        return data
        
    except Exception as e:
        logger.error(f"Fehler beim Holen des Live View: {e}")
        return None


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

# Globaler Storage für Event-Handler (muss am Leben bleiben!)
_object_event_handlers = {}


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


def set_object_event_handler(camera_ref: c_void_p, callback, context=None) -> bool:
    """Richtet den Rueckkanal ein, ueber den die Kamera fertige Fotos meldet.

    2.4.54 — DIESE FUNKTION HAT DIE BOX EINGEFROREN. Hier steht, warum, damit
    es niemand wieder "vereinfacht".

    Der DLL-Aufruf `EdsSetObjectEventHandler` kehrt auf diesen Boxen nicht von
    allein zurueck: Er wartet darauf, dass der Programmfaden Windows-Nachrichten
    abarbeitet. Ruft man ihn direkt im Haupt-Faden auf, blockiert er genau den
    Faden, der diese Nachrichten abarbeiten muesste — die Anwendung steht.

    Das ist am 24.08.2026 passiert: Die Box fror beim Start jeder Session ein.
    Im Log stand die Wachhund-Meldung "EdsSetObjectEventHandler haengt seit 3 s".

    In 2.4.49 wurde der Nebenfaden entfernt, weil eine aeltere Fassung den
    direkten Aufruf hatte und als "lief frueher" galt. Das war ein Fehlschluss:
    In jener Fassung wurde der Direktbetrieb praktisch nie benutzt, der Aufruf
    kam also kaum vor.

    RICHTIG IST BEIDES ZUSAMMEN:
      - Der DLL-Aufruf laeuft in einem Nebenfaden (blockiert dort niemanden).
      - Der Haupt-Faden arbeitet waehrenddessen Nachrichten ab, damit der
        Aufruf ueberhaupt fertig werden kann.
      - Nach einer festen Frist geht es weiter — komme was wolle. Die Box darf
        unter keinen Umstaenden stehenbleiben, nur weil eine Kamera zickt.

    Und anders als frueher wird nicht behauptet, der Rueckkanal stehe, wenn das
    gar nicht feststeht. Genau diese Falschmeldung hat die Fehlersuche ueber
    Monate blockiert.

    Args:
        camera_ref: Kamera-Referenz
        callback: Python-Funktion mit Signatur (event_type, object_ref) -> int
        context: Optionaler Kontext (wird nicht verwendet)

    Returns:
        True  — der Rueckkanal steht nachweislich
        None  — unklar (Aufruf haengt noch); der Direktweg ist trotzdem einen
                Versuch wert, denn oft ist der Handler bereits eingetragen
        False — die Kamera hat abgelehnt; hier hilft nur noch die Karte
    """
    if EDSDK_DLL is None:
        return False

    import threading
    import time
    from ctypes import wintypes

    # ------------------------------------------------------------------
    # 2.4.56 — EINMAL HAENGEN GENUEGT.
    #
    # Bleibt dieser Aufruf haengen, haelt der wartende Aufruf die Kamera
    # besetzt: Direkt danach meldet sie DEVICE_BUSY, es kommt kein Live-View
    # und kein Foto mehr. Jeder weitere Versuch legt einen weiteren haengenden
    # Aufruf obendrauf — die Box wird also mit jedem Versuch SCHLECHTER.
    #
    # Box-Log vom 24.08.2026 (Christian: "wird ja immer schlechter!"):
    #     11:10:30  Registrierung nach 4s nicht abgeschlossen
    #     11:10:30  EDSDK Fehler 0x81 (DEVICE_BUSY)
    #     11:12:47  Registrierung nach 4s nicht abgeschlossen
    #     11:13:07  Registrierung nach 4s nicht abgeschlossen
    #     11:13:27  Registrierung nach 4s nicht abgeschlossen
    #
    # Deshalb: Hat der Aufruf auf diesem Rechner einmal gehangen, wird er nicht
    # noch einmal angefasst. Lieber ohne Rueckkanal weiterarbeiten (dann greift
    # der Weg ueber den Kamera-Zwischenspeicher) als die Kamera endgueltig
    # lahmzulegen.
    # ------------------------------------------------------------------
    global _handler_haengt_dauerhaft
    if _handler_haengt_dauerhaft:
        logger.warning(
            "Rückkanal wird nicht erneut angefordert — der Aufruf blieb schon "
            "einmal hängen und würde die Kamera blockieren."
        )
        return False

    # Wrapper für den Python-Callback
    def c_callback(event, obj_ref, ctx):
        try:
            return callback(event, obj_ref)
        except Exception as e:
            logger.error(f"Fehler im Object Event Handler: {e}")
            return EDS_ERR_OK

    # Callback-Objekt festhalten, sonst raeumt Python es weg und die Kamera
    # ruft ins Leere (Absturz).
    c_callback_obj = EdsObjectEventHandler(c_callback)
    _object_event_handlers[id(camera_ref)] = c_callback_obj

    ergebnis = {"err": None}

    def _registrieren():
        try:
            ergebnis["err"] = EDSDK_DLL.EdsSetObjectEventHandler(
                camera_ref,
                0xFFFFFFFF,  # kEdsObjectEvent_All
                c_callback_obj,
                None,
            )
        except Exception as e:
            logger.error(f"Rueckkanal-Registrierung Ausnahme: {e}")
            ergebnis["err"] = -1

    # 2.4.57 — WICHTIG: Dieser eine Aufruf laeuft BEWUSST NICHT im Kamera-Faden.
    #
    # Er kann haengen. Wuerde er im Kamera-Faden laufen, waere dieser dauerhaft
    # blockiert — und damit auch jeder spaetere Aufruf: Live-View, Aufnahme,
    # Freigeben. Aus einem Problem wuerde eine tote Box.
    #
    # Stattdessen: eigener Wegwerf-Faden. Fertig werden kann der Aufruf
    # trotzdem, weil der Kamera-Faden dauerhaft Windows-Nachrichten abarbeitet
    # — genau das hat vorher gefehlt. Frueher pumpte nur kurz jemand waehrend
    # der Registrierung; danach war Ruhe und der Aufruf blieb fuer immer haengen.
    _sdk_faden_starten()

    faden = threading.Thread(target=_registrieren, daemon=True,
                             name="edsdk-rueckkanal")
    faden.start()

    MAX_WARTEN = 4.0
    faden.join(MAX_WARTEN)

    if not faden.is_alive():
        err = ergebnis["err"]
        if err == EDS_ERR_OK:
            logger.info("Rückkanal der Kamera steht — Fotos können abgeholt werden")
            return True
        name = ERROR_NAMES.get(err, "UNBEKANNT") if err is not None else "?"
        logger.error(f"Rückkanal-Registrierung abgelehnt: {name}")
        return False

    # Aufruf haengt noch. Der Nebenfaden laeuft als daemon weiter und stoert
    # niemanden; die Box macht weiter. Ob der Rueckkanal trotzdem funktioniert,
    # zeigt der Ereigniszaehler im Betrieb — behauptet wird es hier NICHT.
    _handler_haengt_dauerhaft = True
    logger.error(
        f"Rückkanal-Registrierung hängt seit {MAX_WARTEN:.0f}s. Sie wird auf "
        f"diesem Rechner NICHT mehr versucht — jeder weitere Versuch würde die "
        f"Kamera zusätzlich blockieren. Die Box arbeitet ohne Rückkanal weiter; "
        f"eine Speicherkarte in der Kamera ist dann der zuverlässige Weg."
    )
    return None


def download_image(dir_item: c_void_p, save_path: str) -> bool:
    """Lädt ein Bild von der Kamera herunter
    
    Args:
        dir_item: Referenz auf das Directory Item (aus dem Event)
        save_path: Pfad wo das Bild gespeichert werden soll
    
    Returns:
        True wenn erfolgreich
    """
    if EDSDK_DLL is None:
        return False
    
    try:
        # Datei-Info holen
        dir_info = EdsDirectoryItemInfo()
        err = EDSDK_DLL.EdsGetDirectoryItemInfo(dir_item, byref(dir_info))
        if not check_error(err, "GetDirectoryItemInfo"):
            return False
        
        file_size = dir_info.size
        logger.info(f"Lade Bild herunter: {dir_info.szFileName.decode('utf-8', errors='ignore')} ({file_size} bytes)")
        
        # File Stream erstellen
        stream = c_void_p()
        err = EDSDK_DLL.EdsCreateFileStream(
            save_path.encode('utf-8'),
            kEdsFileCreateDisposition_CreateAlways,
            kEdsAccess_ReadWrite,
            byref(stream)
        )
        if not check_error(err, "CreateFileStream"):
            return False
        
        # Bild herunterladen
        err = EDSDK_DLL.EdsDownload(dir_item, file_size, stream)
        if not check_error(err, "Download"):
            EDSDK_DLL.EdsRelease(stream)
            return False
        
        # Download abschließen
        err = EDSDK_DLL.EdsDownloadComplete(dir_item)
        if not check_error(err, "DownloadComplete"):
            EDSDK_DLL.EdsRelease(stream)
            return False
        
        # Aufräumen
        EDSDK_DLL.EdsRelease(stream)
        
        logger.info(f"Bild erfolgreich heruntergeladen: {save_path}")
        return True
        
    except Exception as e:
        logger.error(f"Fehler beim Herunterladen des Bildes: {e}")
        return False


def download_image_to_memory(dir_item: c_void_p) -> Optional[bytes]:
    """Lädt ein Bild von der Kamera in den Speicher
    
    Args:
        dir_item: Referenz auf das Directory Item (aus dem Event)
    
    Returns:
        Bild als bytes oder None bei Fehler
    """
    if EDSDK_DLL is None:
        return None
    
    try:
        # Datei-Info holen
        dir_info = EdsDirectoryItemInfo()
        err = EDSDK_DLL.EdsGetDirectoryItemInfo(dir_item, byref(dir_info))
        if not check_error(err, "GetDirectoryItemInfo"):
            return None
        
        file_size = dir_info.size
        dateiname = dir_info.szFileName.decode('utf-8', errors='ignore')
        logger.info(f"Lade Bild in den Speicher: {dateiname} ({file_size/1024/1024:.1f} MB)")

        # 2.4.55: Groesse plausibilisieren, bevor damit Speicher angefordert
        # wird. Ist das Layout der Struktur einmal falsch (das war es bis
        # 2.4.48), kommen hier absurde Werte an — und EdsCreateMemoryStream
        # scheitert mit einer Meldung, die nach einem Download-Problem aussieht,
        # obwohl der Fehler viel frueher liegt.
        if file_size <= 0 or file_size > 500 * 1024 * 1024:
            logger.error(
                f"Unplausible Dateigröße vom Gerät: {file_size} Bytes. "
                f"Das deutet auf ein falsch gelesenes Datenfeld hin, nicht auf "
                f"ein defektes Foto."
            )
            return None

        # Memory Stream erstellen
        stream = c_void_p()
        err = EDSDK_DLL.EdsCreateMemoryStream(file_size, byref(stream))
        if not check_error(err, "CreateMemoryStream"):
            return None
        
        # Bild herunterladen
        err = EDSDK_DLL.EdsDownload(dir_item, file_size, stream)
        if not check_error(err, "Download"):
            EDSDK_DLL.EdsRelease(stream)
            return None
        
        # Download abschließen
        err = EDSDK_DLL.EdsDownloadComplete(dir_item)
        if not check_error(err, "DownloadComplete"):
            EDSDK_DLL.EdsRelease(stream)
            return None
        
        # Daten aus Stream holen
        pointer = c_void_p()
        EDSDK_DLL.EdsGetPointer(stream, byref(pointer))
        
        # 2.4.55: c_uint64, NICHT c_uint. EdsGetLength schreibt laut Header
        # 64 Bit (EdsUInt64*). In eine 32-Bit-Variable geschrieben, ueberschreibt
        # der Aufruf benachbarten Speicher und liefert obendrein einen falschen
        # Wert — beides unauffaellig, bis es knallt.
        length = ctypes.c_uint64()
        EDSDK_DLL.EdsGetLength(stream, byref(length))

        if length.value <= 0:
            logger.error("Das Gerät hat einen leeren Datenstrom geliefert")
            EDSDK_DLL.EdsRelease(stream)
            return None

        # Bytes kopieren
        data = ctypes.string_at(pointer, length.value)
        
        # Aufräumen
        EDSDK_DLL.EdsRelease(stream)
        
        logger.info(f"Foto vollständig geladen: {len(data)/1024/1024:.1f} MB")
        return data
        
    except Exception as e:
        logger.error(f"Fehler beim Herunterladen des Bildes in Speicher: {e}")
        return None


# ============================================================================
# Directory Enumeration API (für Polling-basiertes Capture)
# ============================================================================

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


def wait_for_new_image(camera_ref: c_void_p, timeout: float = 10.0, poll_interval: float = 0.3) -> Optional[bytes]:
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

    # Ausgangsstand. Ein leerer Ordner (frische Karte) ist ausdruecklich in
    # Ordnung — dann ist die Ausgangszahl eben 0.
    start_anzahl, folder = _zaehle_bilder_frisch(camera_ref)
    if folder:
        EDSDK_DLL.EdsRelease(folder)

    logger.info(f"Bilder auf der Karte vor der Aufnahme: {start_anzahl}")

    start_time = time.time()
    letzte_meldung = 0.0

    while time.time() - start_time < timeout:
        get_event()
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
                    EDSDK_DLL.EdsRelease(image)

            # Alle 3 s ein Lebenszeichen, damit im Log steht, dass wirklich
            # nachgesehen wird (und nicht nur stumpf gewartet).
            vergangen = time.time() - start_time
            if vergangen - letzte_meldung >= 3.0:
                letzte_meldung = vergangen
                logger.debug(f"Warte auf Foto … {vergangen:.0f}s, Karte hat {anzahl} Bilder")
        finally:
            if folder:
                try:
                    EDSDK_DLL.EdsRelease(folder)
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
