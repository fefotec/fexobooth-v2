"""Canon DSLR Camera Manager (EDSDK)

High-level Kamera-Manager für Canon DSLRs via EDSDK.
Implementiert das CameraManager Interface für fexobooth.
"""

import cv2
import numpy as np
import time
import io
from typing import Optional, List, Dict, Any
from PIL import Image
from ctypes import c_void_p

from .base import CameraManager
from src.utils.logging import get_logger

logger = get_logger(__name__)

# EDSDK Import (nur auf Windows)
try:
    from . import edsdk
    EDSDK_AVAILABLE = True
except Exception as e:
    EDSDK_AVAILABLE = False
    logger.warning(f"EDSDK nicht verfügbar: {e}")


class CanonCameraManager(CameraManager):
    """Verwaltet Canon DSLR Kameras via EDSDK
    
    Unterstützt:
    - Live View Streaming
    - Foto-Capture in voller Auflösung
    - Kamera-Einstellungen (TODO)
    """
    
    def __init__(self):
        self._is_initialized = False
        self._camera_ref: Optional[c_void_p] = None
        self._camera_info: Optional[Dict] = None
        self._live_view_active = False
        
        # Frame Cache
        self._last_frame: Optional[np.ndarray] = None
        self._last_frame_time: float = 0
        self._frame_cache_duration: float = 0.033  # ~30fps
        
        # Captured Photo (wartet auf Download)
        self._captured_image: Optional[Image.Image] = None
    
    @staticmethod
    def is_available() -> bool:
        """Prüft ob EDSDK verfügbar ist"""
        return EDSDK_AVAILABLE
    
    @staticmethod
    def list_cameras() -> List[Dict[str, Any]]:
        """Listet verfügbare Canon Kameras"""
        if not EDSDK_AVAILABLE:
            return []
        
        return edsdk.get_camera_list()
    
    def initialize(self, camera_index: int = 0, width: int = 0, height: int = 0) -> bool:
        """Initialisiert die Kamera
        
        Args:
            camera_index: Index der Kamera (0 = erste Canon Kamera)
            width/height: Werden bei Canon ignoriert (Live View hat feste Auflösung)
        """
        if self._is_initialized:
            return True
        
        if not EDSDK_AVAILABLE:
            logger.error("EDSDK nicht verfügbar")
            return False
        
        # SDK initialisieren
        if not edsdk.initialize():
            return False
        
        # Kamera-Liste holen
        cameras = edsdk.get_camera_list()
        if not cameras:
            logger.error("Keine Canon Kamera gefunden")
            return False
        
        if camera_index >= len(cameras):
            logger.error(f"Kamera-Index {camera_index} ungültig (nur {len(cameras)} Kameras)")
            return False
        
        # Kamera auswählen
        self._camera_info = cameras[camera_index]
        self._camera_ref = self._camera_info["ref"]
        
        logger.info(f"Verbinde mit: {self._camera_info['name']}")
        
        # Session öffnen
        if not edsdk.open_session(self._camera_ref):
            logger.error("Session konnte nicht geöffnet werden")
            return False
        
        # Speicherung auf PC konfigurieren
        if not edsdk.set_save_to_host(self._camera_ref):
            logger.warning("SaveTo konnte nicht gesetzt werden")
        
        self._is_initialized = True
        logger.info(f"Canon Kamera initialisiert: {self._camera_info['name']}")
        
        return True
    
    def release(self):
        """Gibt Kamera-Ressourcen frei"""
        if self._live_view_active:
            self.stop_live_view()
        
        if self._camera_ref and self._is_initialized:
            edsdk.close_session(self._camera_ref)
            edsdk.EDSDK_DLL.EdsRelease(self._camera_ref)
        
        self._camera_ref = None
        self._camera_info = None
        self._is_initialized = False
        self._last_frame = None
        
        logger.info("Canon Kamera freigegeben")
    
    def start_live_view(self) -> bool:
        """Startet Live View"""
        if not self._is_initialized or not self._camera_ref:
            return False
        
        if self._live_view_active:
            return True
        
        if edsdk.start_live_view(self._camera_ref):
            self._live_view_active = True
            # Kurz warten bis Live View startet
            time.sleep(0.5)
            logger.info("Live View gestartet")
            return True
        
        return False
    
    def stop_live_view(self):
        """Stoppt Live View"""
        if self._camera_ref and self._live_view_active:
            edsdk.stop_live_view(self._camera_ref)
            self._live_view_active = False
            logger.info("Live View gestoppt")
    
    def get_frame(self, use_cache: bool = True) -> Optional[np.ndarray]:
        """Holt ein Frame vom Live View
        
        Returns:
            OpenCV BGR Frame oder None
        """
        if not self._is_initialized:
            return None
        
        # Live View starten falls nicht aktiv
        if not self._live_view_active:
            if not self.start_live_view():
                return None
        
        current_time = time.time()
        
        # Cache nutzen
        if use_cache and self._last_frame is not None:
            if current_time - self._last_frame_time < self._frame_cache_duration:
                return self._last_frame.copy()
        
        # Live View Frame holen (JPEG bytes)
        jpeg_data = edsdk.get_live_view_image(self._camera_ref)
        if jpeg_data is None:
            return self._last_frame  # Fallback auf letztes Frame
        
        try:
            # JPEG zu numpy array
            nparr = np.frombuffer(jpeg_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                self._last_frame = frame
                self._last_frame_time = current_time
                return frame
                
        except Exception as e:
            logger.error(f"Fehler beim Dekodieren des Frames: {e}")
        
        return self._last_frame
    
    def get_high_res_frame(self, width: int = 0, height: int = 0) -> Optional[np.ndarray]:
        """Holt ein hochauflösendes Foto (volle Kamera-Auflösung)
        
        Bei Canon: Löst Kamera aus und lädt das Bild.
        TODO: Vollständige Implementation mit Event Handling
        """
        if not self._is_initialized or not self._camera_ref:
            return None
        
        # Aktuell: Einfach ein Live View Frame nehmen
        # TODO: Echtes Foto-Capture implementieren
        return self.get_frame(use_cache=False)
    
    def take_picture(self) -> bool:
        """Löst die Kamera aus
        
        Returns:
            True wenn erfolgreich ausgelöst
        """
        if not self._is_initialized or not self._camera_ref:
            return False
        
        # Live View pausieren für Aufnahme
        was_live_view = self._live_view_active
        if was_live_view:
            self.stop_live_view()
            time.sleep(0.2)
        
        success = edsdk.take_picture(self._camera_ref)
        
        # Live View wieder starten
        if was_live_view:
            time.sleep(0.5)  # Warten bis Bild verarbeitet
            self.start_live_view()
        
        return success
    
    @property
    def is_initialized(self) -> bool:
        return self._is_initialized
    
    @property
    def camera_name(self) -> str:
        if self._camera_info:
            return self._camera_info.get("name", "Unknown Canon Camera")
        return "Not connected"
