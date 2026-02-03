"""Canon DSLR Camera Manager (EDSDK)

High-level Kamera-Manager für Canon DSLRs via EDSDK.
Implementiert das CameraManager Interface für fexobooth.
"""

import cv2
import numpy as np
import time
import io
import threading
from queue import Queue, Empty
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
        
        # Capture State
        self._photo_queue: Queue = Queue()
        self._capture_in_progress: bool = False
        self._captured_image: Optional[Image.Image] = None
        
        # Captured Photo Queue (für async Download)
        self._photo_queue: Queue = Queue()
        self._capture_in_progress: bool = False
    
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
        logger.info(f"=== Canon Kamera initialisieren (index={camera_index}) ===")
        
        # Wenn bereits initialisiert, erst aufräumen
        if self._is_initialized:
            logger.info("Bereits initialisiert, führe Cleanup durch...")
            self.release()
        
        if not EDSDK_AVAILABLE:
            logger.error("EDSDK nicht verfügbar")
            return False
        
        # SDK initialisieren
        logger.debug("SDK initialisieren...")
        if not edsdk.initialize():
            logger.error("SDK-Initialisierung fehlgeschlagen")
            return False
        
        # Kamera-Liste holen
        logger.debug("Kamera-Liste abrufen...")
        cameras = edsdk.get_camera_list()
        logger.info(f"Gefundene Kameras: {len(cameras)}")
        
        if not cameras:
            logger.error("Keine Canon Kamera gefunden")
            return False
        
        for i, cam in enumerate(cameras):
            logger.debug(f"  [{i}] {cam.get('name', 'Unknown')} @ {cam.get('port', '?')}")
        
        if camera_index >= len(cameras):
            logger.error(f"Kamera-Index {camera_index} ungültig (nur {len(cameras)} Kameras)")
            return False
        
        # Kamera auswählen
        self._camera_info = cameras[camera_index]
        self._camera_ref = self._camera_info["ref"]
        
        logger.info(f"Verbinde mit: {self._camera_info['name']}")
        
        # Session öffnen (mit Retry-Logik in edsdk.open_session)
        logger.debug("Öffne Kamera-Session...")
        if not edsdk.open_session(self._camera_ref):
            logger.error("Session konnte nicht geöffnet werden")
            self._camera_ref = None
            self._camera_info = None
            return False
        
        logger.info("Session erfolgreich geöffnet")
        
        # Speicherung auf PC konfigurieren
        logger.debug("Konfiguriere SaveTo Host...")
        if not edsdk.set_save_to_host(self._camera_ref):
            logger.warning("SaveTo konnte nicht gesetzt werden (nicht kritisch)")
        
        # Bildqualität auf JPG Large Fine setzen (kein RAW!) - nicht kritisch wenn fehlschlägt
        try:
            if not edsdk.set_image_quality_jpg(self._camera_ref):
                logger.warning("Bildqualität konnte nicht auf JPG gesetzt werden - bitte manuell prüfen!")
        except Exception as e:
            logger.warning(f"set_image_quality_jpg Exception (ignoriert): {e}")
        
        # Event-Handler für Bild-Download registrieren - nicht kritisch wenn fehlschlägt
        # (capture_photo funktioniert auch ohne Event-Handler, nur langsamer)
        try:
            if not edsdk.set_object_event_handler(self._camera_ref, self._on_object_event):
                logger.warning("Object Event Handler konnte nicht registriert werden")
        except Exception as e:
            logger.warning(f"set_object_event_handler Exception (ignoriert): {e}")
        
        self._is_initialized = True
        logger.info(f"✅ Canon Kamera initialisiert: {self._camera_info['name']}")
        
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
    
    def _on_object_event(self, event_type: int, obj_ref: c_void_p) -> int:
        """Callback für EDSDK Object Events (wird aufgerufen wenn Bild bereit ist)"""
        logger.debug(f"Object Event empfangen: {hex(event_type)}")
        
        # kEdsObjectEvent_DirItemRequestTransfer = 0x00000108
        if event_type == 0x00000108:
            logger.info("Bild-Download Event empfangen (DirItemRequestTransfer)")
            
            try:
                # Bild direkt in Speicher laden
                image_data = edsdk.download_image_to_memory(obj_ref)
                
                if image_data:
                    # In Queue für capture_photo() legen
                    self._photo_queue.put(image_data)
                    logger.info(f"Bild in Queue gelegt: {len(image_data)} bytes")
                else:
                    logger.error("Bild-Download fehlgeschlagen")
                    self._photo_queue.put(None)  # Signal dass Download fehlschlug
                    
            except Exception as e:
                logger.error(f"Fehler beim Verarbeiten des Bild-Events: {e}")
                self._photo_queue.put(None)
            
            # Objekt freigeben
            if edsdk.EDSDK_DLL:
                edsdk.EDSDK_DLL.EdsRelease(obj_ref)
        
        return 0  # EDS_ERR_OK
    
    def capture_photo(self, timeout: float = 10.0) -> Optional[Image.Image]:
        """Nimmt ein Foto in voller DSLR-Auflösung auf
        
        Args:
            timeout: Maximale Wartezeit in Sekunden
            
        Returns:
            PIL Image in voller Auflösung oder None bei Fehler
        """
        logger.info(f"=== capture_photo aufgerufen (timeout={timeout}s) ===")
        
        if not self._is_initialized or not self._camera_ref:
            logger.error("Kamera nicht initialisiert")
            return None
        
        if self._capture_in_progress:
            logger.warning("Capture bereits in Progress")
            return None
        
        self._capture_in_progress = True
        was_live_view = self._live_view_active
        
        try:
            # Queue leeren (falls alte Events drin sind)
            queue_cleared = 0
            while not self._photo_queue.empty():
                try:
                    self._photo_queue.get_nowait()
                    queue_cleared += 1
                except Empty:
                    break
            if queue_cleared:
                logger.debug(f"Queue geleert: {queue_cleared} alte Items")
            
            # Live View pausieren für bessere Bildqualität
            if was_live_view:
                logger.debug("Pausiere Live View...")
                self.stop_live_view()
                time.sleep(0.3)
            
            # Kamera auslösen
            logger.info("Löse Kamera aus...")
            if not edsdk.take_picture(self._camera_ref):
                logger.error("Kamera auslösen fehlgeschlagen")
                if was_live_view:
                    self.start_live_view()
                return None
            
            logger.info("Kamera ausgelöst, warte auf Bild...")
            
            # Auf Bild warten (kommt via Event-Handler in die Queue)
            # WICHTIG: Wir müssen EdsGetEvent() pollen damit Callbacks aufgerufen werden!
            start_time = time.time()
            image_data = None
            poll_count = 0
            
            while time.time() - start_time < timeout:
                # Events pollen (WICHTIG für Windows!)
                try:
                    edsdk.get_event()
                except Exception as e:
                    logger.debug(f"get_event Fehler: {e}")
                
                poll_count += 1
                
                # Prüfen ob Bild in Queue ist
                try:
                    image_data = self._photo_queue.get_nowait()
                    logger.info(f"Bild aus Queue erhalten nach {poll_count} polls ({time.time()-start_time:.1f}s)")
                    break
                except Empty:
                    pass
                
                # Kurz warten um CPU zu schonen
                time.sleep(0.05)
            
            elapsed = time.time() - start_time
            
            if image_data is None:
                logger.error(f"Timeout beim Warten auf Bild ({elapsed:.1f}s, {poll_count} polls)")
                logger.warning("Event-Handler hat kein Bild geliefert - prüfe ob Kamera auf JPG steht!")
                if was_live_view:
                    self.start_live_view()
                return None
            
            # Live View wieder starten
            if was_live_view:
                time.sleep(0.2)
                self.start_live_view()
            
            # JPEG bytes zu PIL Image konvertieren
            try:
                image = Image.open(io.BytesIO(image_data))
                logger.info(f"✅ Foto aufgenommen: {image.size[0]}x{image.size[1]} ({len(image_data)} bytes)")
                return image
            except Exception as e:
                logger.error(f"Fehler beim Dekodieren des Bildes: {e}")
                return None
        
        except Exception as e:
            logger.error(f"Unerwarteter Fehler in capture_photo: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
                
        finally:
            self._capture_in_progress = False
            # Sicherstellen dass Live View wieder läuft
            if was_live_view and not self._live_view_active:
                try:
                    self.start_live_view()
                except:
                    pass
    
    def get_high_res_frame(self, width: int = 0, height: int = 0) -> Optional[np.ndarray]:
        """Holt ein hochauflösendes Foto (volle Kamera-Auflösung)
        
        Bei Canon: Nutzt capture_photo() für echte DSLR-Qualität.
        Gibt numpy array zurück für Kompatibilität mit Webcam-Interface.
        """
        image = self.capture_photo()
        if image is None:
            return None
        
        # PIL Image zu numpy array (BGR für OpenCV)
        rgb = np.array(image)
        if len(rgb.shape) == 3 and rgb.shape[2] == 3:
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            return bgr
        return rgb
    
    def take_picture(self) -> bool:
        """Löst die Kamera aus (ohne auf Bild zu warten)
        
        Für manuelles Auslösen. Nutze capture_photo() wenn du das Bild brauchst.
        
        Returns:
            True wenn erfolgreich ausgelöst
        """
        if not self._is_initialized or not self._camera_ref:
            return False
        
        return edsdk.take_picture(self._camera_ref)
    
    @property
    def is_initialized(self) -> bool:
        return self._is_initialized
    
    @property
    def camera_name(self) -> str:
        if self._camera_info:
            return self._camera_info.get("name", "Unknown Canon Camera")
        return "Not connected"
