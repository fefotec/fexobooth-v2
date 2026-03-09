"""Webcam-Manager mit OpenCV"""

import cv2
import numpy as np
import time
from typing import Optional

from .base import CameraManager
from src.utils.logging import get_logger

logger = get_logger(__name__)


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
    
    def initialize(self, camera_index: int, width: int, height: int) -> bool:
        """Initialisiert die Kamera"""
        # Bereits initialisiert?
        if self._is_initialized and self.camera_index == camera_index:
            return True
        
        # Alte Verbindung schließen
        self.release()
        self.camera_index = camera_index
        
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
        
        # Einstellungen setzen
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimiert Latenz
        
        # Tatsächliche Auflösung loggen und als Preview-Auflösung merken
        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._preview_width = actual_w
        self._preview_height = actual_h
        logger.info(f"Kamera initialisiert: {actual_w}x{actual_h}")

        self._is_initialized = True
        return True
    
    def get_frame(self, use_cache: bool = True) -> Optional[np.ndarray]:
        """Holt ein Frame von der Kamera"""
        if not self._is_initialized or not self.cap:
            return None
        
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
    
    def get_high_res_frame(self, width: int = 1920, height: int = 1080) -> Optional[np.ndarray]:
        """Holt ein hochauflösendes Frame für Foto-Capture

        Schaltet temporär auf höhere Auflösung um, holt das Bild,
        und schaltet dann zurück auf Live-Preview-Auflösung.

        Optimiert für Logitech C920/C922 (native 1080p Support).

        Args:
            width: Gewünschte Breite (default: 1920 für Full HD)
            height: Gewünschte Höhe (default: 1080 für Full HD)

        Returns:
            numpy array mit dem hochauflösenden Frame, oder None bei Fehler
        """
        if not self.cap:
            logger.warning("get_high_res_frame: Keine Kamera initialisiert")
            return None

        # Gespeicherte Preview-Auflösung verwenden (nicht von Kamera lesen - kann 0x0 sein!)
        old_w = self._preview_width
        old_h = self._preview_height

        # Fallback: Von Kamera lesen wenn gespeicherte Werte fehlen
        if old_w <= 0 or old_h <= 0:
            old_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            old_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        logger.info(f"High-Res Capture: {old_w}x{old_h} -> {width}x{height}")

        # Wenn schon auf High-Res, direkt Frame holen
        if old_w >= width and old_h >= height:
            ret, frame = self.cap.read()
            if ret and frame is not None:
                logger.info(f"High-Res Frame (bereits aktiv): {frame.shape[1]}x{frame.shape[0]}")
                return frame
            logger.warning("High-Res Frame lesen fehlgeschlagen (bereits auf High-Res)")
            return None

        try:
            # Auf hohe Auflösung umschalten
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            # Prüfen ob die Kamera die Auflösung akzeptiert hat
            actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.info(f"Kamera-Auflösung nach Umschaltung: {actual_w}x{actual_h}")

            # Buffer leeren mit grab() statt read() (grab bewegt nur den Pointer,
            # dekodiert nicht - deutlich schneller als read!)
            for i in range(2):
                self.cap.grab()

            # Tatsächliches High-Res Frame holen
            ret, frame = self.cap.read()

            if ret and frame is not None:
                captured_h, captured_w = frame.shape[:2]
                logger.info(f"High-Res Frame erfolgreich: {captured_w}x{captured_h}")

                if captured_w < width or captured_h < height:
                    logger.warning(f"Kamera liefert weniger als angefordert: {captured_w}x{captured_h} statt {width}x{height}")
            else:
                logger.error("High-Res Frame lesen fehlgeschlagen nach Umschaltung")
                frame = None

        except Exception as e:
            logger.error(f"High-Res Capture Exception: {e}")
            frame = None
        finally:
            # WICHTIG: Immer zurück auf Preview-Auflösung!
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, old_w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, old_h)
            # Buffer mit grab() leeren (schneller als read)
            for _ in range(2):
                self.cap.grab()
            logger.debug(f"Zurück auf Preview-Auflösung: {old_w}x{old_h}")

        return frame
    
    def release(self):
        """Gibt Kamera-Ressourcen frei"""
        if self.cap:
            self.cap.release()
            self.cap = None
        self._is_initialized = False
        self.last_frame = None
        logger.info("Kamera freigegeben")
    
    @property
    def is_initialized(self) -> bool:
        return self._is_initialized
    
    @staticmethod
    def list_cameras(max_cameras: int = 5) -> list:
        """Listet verfügbare Kameras auf"""
        cameras = []
        
        for i in range(max_cameras):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                cameras.append({
                    "index": i,
                    "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                })
                cap.release()
        
        return cameras
