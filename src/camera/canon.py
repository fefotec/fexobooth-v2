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
        self._initializing = False  # True während initialize() läuft (Deadlock-Schutz)
        self._camera_ref: Optional[c_void_p] = None
        self._camera_info: Optional[Dict] = None
        self._live_view_active = False

        # Frame Cache
        self._last_frame: Optional[np.ndarray] = None
        self._last_frame_time: float = 0
        self._frame_cache_duration: float = 0.033  # ~30fps

        # Capture State & Mode
        self._photo_queue: Queue = Queue()
        self._capture_in_progress: bool = False
        self._captured_image: Optional[Image.Image] = None
        self._use_host_download: bool = False  # True = kein SD, Bild via Event-Handler empfangen
    
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

        # Deadlock-Schutz: Flag setzen BEVOR EDSDK-Aufrufe beginnen
        # Verhindert dass _check_camera_status() im UI-Thread gleichzeitig EDSDK aufruft
        self._initializing = True

        # Wenn bereits initialisiert, erst aufräumen
        if self._is_initialized:
            logger.info("Bereits initialisiert, führe Cleanup durch...")
            self.release()
        
        if not EDSDK_AVAILABLE:
            logger.error("EDSDK nicht verfügbar")
            self._initializing = False
            return False
        
        # SDK initialisieren
        logger.debug("SDK initialisieren...")
        if not edsdk.initialize():
            logger.error("SDK-Initialisierung fehlgeschlagen")
            self._initializing = False
            return False
        
        # Kamera-Liste holen
        logger.debug("Kamera-Liste abrufen...")
        cameras = edsdk.get_camera_list()
        logger.info(f"Gefundene Kameras: {len(cameras)}")
        
        if not cameras:
            logger.error("Keine Canon Kamera gefunden")
            self._initializing = False
            return False
        
        for i, cam in enumerate(cameras):
            logger.debug(f"  [{i}] {cam.get('name', 'Unknown')} @ {cam.get('port', '?')}")
        
        if camera_index >= len(cameras):
            logger.error(f"Kamera-Index {camera_index} ungültig (nur {len(cameras)} Kameras)")
            self._initializing = False
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
            self._initializing = False
            return False
        
        logger.info("Session erfolgreich geöffnet")
        
        # Speicherung konfigurieren: SD-Karte bevorzugt, Host-Download als Fallback
        self._use_host_download = False
        logger.debug("Konfiguriere SaveTo Camera (SD-Karte)...")
        if edsdk.set_save_to_camera(self._camera_ref):
            # Prüfen ob DCIM-Ordner erreichbar ist (= SD-Karte vorhanden)
            volume = edsdk.get_first_volume(self._camera_ref)
            if volume:
                dcim = edsdk.get_dcim_folder(volume)
                if dcim:
                    logger.info("SD-Karte erkannt (DCIM vorhanden) -> Directory-Polling Modus")
                    edsdk.EDSDK_DLL.EdsRelease(dcim)
                else:
                    logger.warning("Keine SD-Karte (DCIM nicht gefunden) -> Host-Download Modus")
                    self._use_host_download = True
                edsdk.EDSDK_DLL.EdsRelease(volume)
            else:
                logger.warning("Kein Volume gefunden -> Host-Download Modus")
                self._use_host_download = True
        else:
            logger.warning("SaveTo Camera fehlgeschlagen -> Host-Download Modus")
            self._use_host_download = True

        # Bei Host-Download: SaveTo auf Host setzen und Event-Handler registrieren
        if self._use_host_download:
            logger.info("Konfiguriere SaveTo Host + Event-Handler...")
            if edsdk.set_save_to_host(self._camera_ref):
                logger.info("SaveTo Host gesetzt")
            else:
                logger.error("SaveTo Host fehlgeschlagen!")
            edsdk.set_object_event_handler(self._camera_ref, self._on_object_event)
            logger.info("Host-Download Modus aktiv (Bild wird via USB zum Tablet übertragen)")

        # Bildqualität auf JPG Large Fine setzen (kein RAW!) - nicht kritisch wenn fehlschlägt
        try:
            if not edsdk.set_image_quality_jpg(self._camera_ref):
                logger.warning("Bildqualität konnte nicht auf JPG gesetzt werden - bitte manuell prüfen!")
        except Exception as e:
            logger.warning(f"set_image_quality_jpg Exception (ignoriert): {e}")

        self._is_initialized = True
        self._initializing = False
        logger.info(f"✅ Canon Kamera initialisiert: {self._camera_info['name']}")

        # Kamera-Einstellungen loggen (für Debugging)
        edsdk.log_camera_settings(self._camera_ref)
        
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
        self._initializing = False
        self._use_host_download = False
        self._last_frame = None

        logger.info("Canon Kamera freigegeben")
    
    def start_live_view(self) -> bool:
        """Startet Live View mit Retry-Logik"""
        logger.debug("start_live_view aufgerufen...")
        
        if not self._is_initialized or not self._camera_ref:
            logger.warning("start_live_view: Kamera nicht initialisiert")
            return False
        
        if self._live_view_active:
            logger.debug("Live View bereits aktiv")
            return True
        
        # Mehrere Versuche - Kamera braucht manchmal Zeit
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if edsdk.start_live_view(self._camera_ref):
                    self._live_view_active = True
                    # Warten bis Live View bereit ist
                    time.sleep(0.8)
                    logger.info(f"Live View gestartet (Versuch {attempt + 1})")
                    return True
                else:
                    logger.warning(f"start_live_view Versuch {attempt + 1} fehlgeschlagen")
                    time.sleep(0.5)
            except Exception as e:
                logger.error(f"start_live_view Exception (Versuch {attempt + 1}): {e}")
                time.sleep(0.5)
        
        logger.error("Live View konnte nach 3 Versuchen nicht gestartet werden")
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
            logger.debug("get_frame: nicht initialisiert")
            return None
        
        # Live View starten falls nicht aktiv
        if not self._live_view_active:
            logger.debug("get_frame: starte Live View...")
            if not self.start_live_view():
                logger.warning("get_frame: Live View konnte nicht gestartet werden")
                return self._last_frame  # Fallback
        
        current_time = time.time()
        
        # Cache nutzen
        if use_cache and self._last_frame is not None:
            if current_time - self._last_frame_time < self._frame_cache_duration:
                return self._last_frame.copy()
        
        # Live View Frame holen (JPEG bytes)
        try:
            jpeg_data = edsdk.get_live_view_image(self._camera_ref)
        except Exception as e:
            # Nicht bei jedem Frame loggen - nur gelegentlich
            if not hasattr(self, '_evf_error_count'):
                self._evf_error_count = 0
            self._evf_error_count += 1
            if self._evf_error_count <= 3 or self._evf_error_count % 100 == 0:
                logger.debug(f"get_live_view_image Fehler #{self._evf_error_count}: {e}")
            jpeg_data = None
        
        if jpeg_data is None:
            # Bei vielen Fehlern: Live-View neu starten
            if hasattr(self, '_evf_error_count') and self._evf_error_count > 0 and self._evf_error_count % 30 == 0:
                logger.warning(f"Viele Live-View Fehler ({self._evf_error_count}), versuche Neustart...")
                self._live_view_active = False
                self.start_live_view()
            return self._last_frame  # Fallback auf letztes Frame
        
        # Erfolg - Fehler-Counter zurücksetzen
        if hasattr(self, '_evf_error_count'):
            self._evf_error_count = 0
        
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
        """Callback für EDSDK Object Events (Host-Download Modus)

        Wird aufgerufen wenn die Kamera ein Bild bereit hat zum Download.
        Das Bild wird in den Speicher geladen und in die Photo-Queue gelegt.
        """
        event_names = {
            0x00000100: "DirItemCreated",
            0x00000108: "DirItemRequestTransfer",
        }
        event_name = event_names.get(event_type, f"0x{event_type:08x}")
        logger.info(f">>> OBJECT EVENT: {event_name}")

        # kEdsObjectEvent_DirItemRequestTransfer = 0x00000108
        if event_type == 0x00000108:
            try:
                image_data = edsdk.download_image_to_memory(obj_ref)
                if image_data:
                    self._photo_queue.put(image_data)
                    logger.info(f">>> Bild empfangen: {len(image_data)} bytes ({len(image_data)/1024/1024:.1f} MB)")
                else:
                    logger.error(">>> Download fehlgeschlagen (keine Daten)")
                    self._photo_queue.put(None)
            except Exception as e:
                logger.error(f">>> Download Exception: {e}")
                self._photo_queue.put(None)

            # Objekt freigeben
            try:
                if edsdk.EDSDK_DLL:
                    edsdk.EDSDK_DLL.EdsRelease(obj_ref)
            except Exception:
                pass

        return 0  # EDS_ERR_OK

    def capture_photo(self, timeout: float = 10.0) -> Optional[Image.Image]:
        """Nimmt ein Foto in voller DSLR-Auflösung auf

        Zwei Modi je nach SD-Karten-Verfügbarkeit:
        - MIT SD-Karte: Directory-Polling (Bild auf SD -> Download)
        - OHNE SD-Karte: Host-Download (Bild direkt via USB zum Tablet)

        Args:
            timeout: Maximale Wartezeit in Sekunden

        Returns:
            PIL Image in voller DSLR-Auflösung oder None bei Fehler
        """
        mode_text = "Host-Download" if self._use_host_download else "Directory-Polling"
        logger.info("=" * 60)
        logger.info(f"=== CAPTURE_PHOTO ({mode_text}) ===")
        logger.info("=" * 60)

        if not self._is_initialized or not self._camera_ref:
            logger.error("capture_photo: Kamera nicht initialisiert!")
            return None

        live_view_was_active = self._live_view_active

        try:
            # SCHRITT 1: LiveView stoppen (WICHTIG für echte Aufnahme!)
            if self._live_view_active:
                logger.info("[1/5] Stoppe LiveView für Foto-Aufnahme...")
                self.stop_live_view()
                time.sleep(0.5)
                logger.info("[1/5] ✓ LiveView gestoppt")
            else:
                logger.info("[1/5] LiveView war nicht aktiv")

            # SCHRITT 2: Photo-Queue leeren (für Host-Download)
            if self._use_host_download:
                while not self._photo_queue.empty():
                    try:
                        self._photo_queue.get_nowait()
                    except Empty:
                        break

            # SCHRITT 3: Foto auslösen
            logger.info("[2/5] Löse Kamera aus (TakePicture)...")
            if not edsdk.take_picture(self._camera_ref):
                logger.error("[2/5] ✗ TakePicture fehlgeschlagen!")
                return self._fallback_to_live_view(live_view_was_active)

            logger.info("[2/5] ✓ Kamera ausgelöst!")

            # SCHRITT 4: Auf Bild warten (je nach Modus)
            image_data = None

            if self._use_host_download:
                # HOST-MODUS: Bild kommt über Event-Handler in _photo_queue
                logger.info(f"[3/5] Warte auf Host-Download (max {timeout}s)...")
                start_time = time.time()
                while time.time() - start_time < timeout:
                    # Events pollen (WICHTIG - ohne das kommen keine Events auf Windows!)
                    edsdk.get_event()
                    try:
                        image_data = self._photo_queue.get(timeout=0.1)
                        if image_data:
                            logger.info(f"[3/5] ✓ Bild via Host-Download: {len(image_data)} bytes")
                            break
                        else:
                            logger.warning("[3/5] None aus Queue - Download fehlgeschlagen")
                            image_data = None
                    except Empty:
                        continue
            else:
                # SD-MODUS: Directory-Polling
                logger.info(f"[3/5] Warte auf Bild via Directory-Polling (max {timeout}s)...")
                image_data = edsdk.wait_for_new_image(self._camera_ref, timeout=timeout)

            if image_data is None:
                logger.error("[3/5] ✗ Kein Bild empfangen!")
                return self._fallback_to_live_view(live_view_was_active)

            logger.info(f"[3/5] ✓ Bild empfangen: {len(image_data)} bytes")

            # SCHRITT 5: Bild dekodieren
            logger.info("[4/5] Dekodiere Bild...")
            try:
                image = Image.open(io.BytesIO(image_data))
                image.load()
                logger.info(f"[4/5] ✓ Bild dekodiert: {image.size[0]}x{image.size[1]} ({image.mode})")
            except Exception as e:
                logger.error(f"[4/5] ✗ Fehler beim Dekodieren: {e}")
                return self._fallback_to_live_view(live_view_was_active)

            # SCHRITT 6: LiveView wieder starten
            if live_view_was_active:
                logger.info("[5/5] Starte LiveView wieder...")
                time.sleep(0.3)
                if self.start_live_view():
                    logger.info("[5/5] ✓ LiveView wieder aktiv")
                else:
                    logger.warning("[5/5] ⚠ LiveView konnte nicht neu gestartet werden")
            else:
                logger.info("[5/5] LiveView bleibt aus")

            logger.info("=" * 60)
            logger.info(f"=== CAPTURE ERFOLGREICH: {image.size[0]}x{image.size[1]} ===")
            logger.info("=" * 60)
            return image

        except Exception as e:
            logger.error(f"capture_photo Exception: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._fallback_to_live_view(live_view_was_active)

    def _fallback_to_live_view(self, restart_live_view: bool) -> Optional[Image.Image]:
        """Fallback: Gibt Live-View Frame zurück wenn DSLR-Aufnahme fehlschlägt

        Nach LiveView-Start braucht die Canon EOS 2000D ~1-2s bis gültige Frames
        kommen (EVF_INTERNAL_ERROR in den ersten Versuchen). Daher Retry-Logik.
        """
        logger.warning("=== FALLBACK auf Live-View Frame ===")

        # Live-View starten wenn nicht aktiv
        if not self._live_view_active:
            logger.info("Starte Live-View für Fallback...")
            self.start_live_view()

        # Mehrere Versuche - Kamera braucht nach LiveView-Start etwas Zeit
        frame = None
        for attempt in range(10):
            frame = self.get_frame(use_cache=False)
            if frame is not None:
                break
            time.sleep(0.3)

        if frame is None:
            logger.error("Fallback fehlgeschlagen: Kein Live-View Frame nach 10 Versuchen!")
            return None

        # OpenCV BGR zu PIL RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)

        logger.warning(f"Fallback-Bild: {image.size[0]}x{image.size[1]} (Live-View Auflösung)")
        return image
    
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
