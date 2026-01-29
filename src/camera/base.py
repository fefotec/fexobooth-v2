"""Abstrakte Kamera-Basisklasse"""

from abc import ABC, abstractmethod
from typing import Optional
import numpy as np


class CameraManager(ABC):
    """Abstrakte Basisklasse für Kamera-Manager"""
    
    @abstractmethod
    def initialize(self, camera_index: int, width: int, height: int) -> bool:
        """Initialisiert die Kamera"""
        pass
    
    @abstractmethod
    def get_frame(self, use_cache: bool = True) -> Optional[np.ndarray]:
        """Holt ein Frame von der Kamera"""
        pass
    
    @abstractmethod
    def release(self):
        """Gibt Kamera-Ressourcen frei"""
        pass
    
    @property
    @abstractmethod
    def is_initialized(self) -> bool:
        """Gibt zurück ob Kamera initialisiert ist"""
        pass
