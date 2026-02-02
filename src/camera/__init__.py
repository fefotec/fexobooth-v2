"""Kamera-Modul"""
from .webcam import WebcamManager
from .base import CameraManager

# Canon EDSDK (optional, nur Windows)
try:
    from .canon import CanonCameraManager
    CANON_AVAILABLE = CanonCameraManager.is_available()
except ImportError:
    CanonCameraManager = None
    CANON_AVAILABLE = False


def get_camera_manager(camera_type: str = "webcam"):
    """Factory-Funktion für Kamera-Manager
    
    Args:
        camera_type: "webcam" oder "canon"
    
    Returns:
        CameraManager Instanz
    """
    if camera_type == "canon" and CANON_AVAILABLE:
        return CanonCameraManager()
    return WebcamManager()
