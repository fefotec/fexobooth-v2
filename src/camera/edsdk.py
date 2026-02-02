"""Canon EDSDK Python Wrapper (ctypes)

Low-level wrapper für Canon EDSDK DLL.
Basiert auf EDSDK v13.20.10
"""

import ctypes
from ctypes import c_uint, c_int, c_void_p, c_char_p, POINTER, byref, Structure, c_ubyte
import os
import sys
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
EDS_ERR_SESSION_NOT_OPEN = 0x00002003
EDS_ERR_TAKE_PICTURE_AF_NG = 0x00008D01
EDS_ERR_TAKE_PICTURE_CARD_NG = 0x00008D07

def check_error(err: int, context: str = "") -> bool:
    """Prüft EDSDK Fehlercode"""
    if err == EDS_ERR_OK:
        return True
    logger.error(f"EDSDK Fehler {hex(err)} bei {context}")
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
    """Info über ein Verzeichnis-Item (Bild auf der Kamera)"""
    _fields_ = [
        ("size", c_uint),           # Dateigröße (32-bit, für große Dateien size64 nutzen)
        ("isFolder", c_int),        # 1 wenn Ordner
        ("groupID", c_uint),        # Gruppen-ID
        ("option", c_uint),         # Option
        ("szFileName", ctypes.c_char * 256),  # Dateiname
        ("format", c_uint),         # Format (JPEG, RAW, etc.)
        ("dateTime", c_uint),       # Datum/Zeit
    ]


# Callback-Typ für Object Events
# typedef EdsError (EDSCALLBACK *EdsObjectEventHandler)(EdsObjectEvent inEvent, EdsBaseRef inRef, EdsVoid *inContext)
EdsObjectEventHandler = ctypes.CFUNCTYPE(c_uint, c_uint, c_void_p, c_void_p)


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
    EDSDK_DLL.EdsCreateMemoryStream.argtypes = [c_uint, POINTER(c_void_p)]
    
    # EdsGetPointer
    EDSDK_DLL.EdsGetPointer.restype = c_uint
    EDSDK_DLL.EdsGetPointer.argtypes = [c_void_p, POINTER(c_void_p)]
    
    # EdsGetLength
    EDSDK_DLL.EdsGetLength.restype = c_uint
    EDSDK_DLL.EdsGetLength.argtypes = [c_void_p, POINTER(c_uint)]
    
    # EdsSetObjectEventHandler - für Bild-Download Events
    EDSDK_DLL.EdsSetObjectEventHandler.restype = c_uint
    EDSDK_DLL.EdsSetObjectEventHandler.argtypes = [c_void_p, c_uint, EdsObjectEventHandler, c_void_p]
    
    # EdsGetDirectoryItemInfo - Info über aufgenommenes Bild
    EDSDK_DLL.EdsGetDirectoryItemInfo.restype = c_uint
    EDSDK_DLL.EdsGetDirectoryItemInfo.argtypes = [c_void_p, POINTER(EdsDirectoryItemInfo)]
    
    # EdsDownload - Bild herunterladen
    EDSDK_DLL.EdsDownload.restype = c_uint
    EDSDK_DLL.EdsDownload.argtypes = [c_void_p, c_uint, c_void_p]
    
    # EdsDownloadComplete - Download abschließen
    EDSDK_DLL.EdsDownloadComplete.restype = c_uint
    EDSDK_DLL.EdsDownloadComplete.argtypes = [c_void_p]
    
    # EdsCreateFileStream - File Stream für Download
    EDSDK_DLL.EdsCreateFileStream.restype = c_uint
    EDSDK_DLL.EdsCreateFileStream.argtypes = [c_char_p, c_uint, c_uint, POINTER(c_void_p)]


# ============================================================================
# High-Level API
# ============================================================================

_sdk_initialized = False

def initialize() -> bool:
    """Initialisiert das EDSDK"""
    global _sdk_initialized
    
    if _sdk_initialized:
        return True
    
    if not load_edsdk():
        return False
    
    _setup_functions()
    
    err = EDSDK_DLL.EdsInitializeSDK()
    if not check_error(err, "EdsInitializeSDK"):
        return False
    
    _sdk_initialized = True
    logger.info("EDSDK initialisiert")
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
    """Öffnet eine Session mit der Kamera"""
    if EDSDK_DLL is None:
        return False
    
    err = EDSDK_DLL.EdsOpenSession(camera_ref)
    return check_error(err, "EdsOpenSession")


def close_session(camera_ref: c_void_p):
    """Schließt die Session"""
    if EDSDK_DLL is None:
        return
    
    EDSDK_DLL.EdsCloseSession(camera_ref)


def take_picture(camera_ref: c_void_p) -> bool:
    """Löst die Kamera aus"""
    if EDSDK_DLL is None:
        return False
    
    err = EDSDK_DLL.EdsSendCommand(camera_ref, kEdsCameraCommand_TakePicture, 0)
    return check_error(err, "TakePicture")


def set_save_to_host(camera_ref: c_void_p) -> bool:
    """Konfiguriert Speicherung zum PC"""
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
        
        # Daten aus Stream holen
        length = c_uint()
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


def set_object_event_handler(camera_ref: c_void_p, callback, context=None) -> bool:
    """Registriert einen Callback für Object Events (z.B. Bild aufgenommen)
    
    Args:
        camera_ref: Kamera-Referenz
        callback: Python-Funktion mit Signatur (event_type, object_ref) -> int
        context: Optionaler Kontext (wird nicht verwendet)
    
    Returns:
        True wenn erfolgreich
    """
    if EDSDK_DLL is None:
        return False
    
    # Wrapper für den Python-Callback
    def c_callback(event, obj_ref, ctx):
        try:
            return callback(event, obj_ref)
        except Exception as e:
            logger.error(f"Fehler im Object Event Handler: {e}")
            return EDS_ERR_OK
    
    # Callback-Objekt erstellen und speichern (sonst wird es garbage collected!)
    c_callback_obj = EdsObjectEventHandler(c_callback)
    _object_event_handlers[id(camera_ref)] = c_callback_obj
    
    # Alle Object Events abonnieren (0xFFFFFFFF)
    err = EDSDK_DLL.EdsSetObjectEventHandler(
        camera_ref,
        0xFFFFFFFF,  # kEdsObjectEvent_All
        c_callback_obj,
        None
    )
    
    return check_error(err, "SetObjectEventHandler")


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
        logger.info(f"Lade Bild in Speicher: {dir_info.szFileName.decode('utf-8', errors='ignore')} ({file_size} bytes)")
        
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
        
        length = c_uint()
        EDSDK_DLL.EdsGetLength(stream, byref(length))
        
        # Bytes kopieren
        data = ctypes.string_at(pointer, length.value)
        
        # Aufräumen
        EDSDK_DLL.EdsRelease(stream)
        
        logger.info(f"Bild erfolgreich in Speicher geladen: {len(data)} bytes")
        return data
        
    except Exception as e:
        logger.error(f"Fehler beim Herunterladen des Bildes in Speicher: {e}")
        return None


# Cleanup bei Programmende
import atexit
atexit.register(terminate)
