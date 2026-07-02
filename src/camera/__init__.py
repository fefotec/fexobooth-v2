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

# Nikon läuft über die FexoNikonBridge (stdio-Subprozess), keine native DLL nötig.
# Defensiv importieren (wie Canon): ein künftiger Import-Fehler in nikon.py darf
# NICHT die ganze App (auch Webcam-/Canon-Flotte!) am Start hindern.
try:
    from .nikon import NikonCameraManager
    NIKON_AVAILABLE = True
except Exception:
    NikonCameraManager = None
    NIKON_AVAILABLE = False


def get_camera_manager(camera_type: str = "webcam", config=None):
    """Factory-Funktion für Kamera-Manager

    Args:
        camera_type: "webcam", "canon" oder "nikon"
        config: App-Config (für Nikon-Bridge-Einstellungen)

    Returns:
        CameraManager Instanz
    """
    if camera_type == "canon" and CANON_AVAILABLE:
        return CanonCameraManager()
    if camera_type == "nikon" and NikonCameraManager is not None:
        return NikonCameraManager(config=config)
    return WebcamManager()
