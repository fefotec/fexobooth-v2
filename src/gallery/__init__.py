"""Galerie-Modul - Lokaler Webserver für Foto-Galerie + Hotspot-Steuerung"""

from .server import start_server, stop_server, is_running, get_gallery_url
from .qrcode_gen import generate_qr_code, generate_qr_with_label
from .hotspot import start_hotspot, stop_hotspot, is_hotspot_active, ensure_hotspot_state

__all__ = [
    'start_server',
    'stop_server',
    'is_running',
    'get_gallery_url',
    'generate_qr_code',
    'generate_qr_with_label',
    'start_hotspot',
    'stop_hotspot',
    'is_hotspot_active',
    'ensure_hotspot_state'
]
