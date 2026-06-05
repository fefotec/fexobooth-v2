"""Galerie-Modul - Lokaler Webserver für Foto-Galerie + Hotspot-Steuerung"""

from .server import (
    start_server,
    stop_server,
    is_running,
    get_gallery_url,
    get_app_pairing_url,
    get_app_landing_url,
    set_app_context as set_gallery_app_context,
    set_locale as set_gallery_locale,
)
from .qrcode_gen import generate_qr_code, generate_qr_with_label
from .hotspot import start_hotspot, stop_hotspot, is_hotspot_active, ensure_hotspot_state

__all__ = [
    'start_server',
    'stop_server',
    'is_running',
    'get_gallery_url',
    'get_app_pairing_url',
    'get_app_landing_url',
    'set_gallery_app_context',
    'set_gallery_locale',
    'generate_qr_code',
    'generate_qr_with_label',
    'start_hotspot',
    'stop_hotspot',
    'is_hotspot_active',
    'ensure_hotspot_state'
]
