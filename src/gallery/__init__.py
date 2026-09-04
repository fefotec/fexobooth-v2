"""Galerie-Modul - Lokaler Webserver für Foto-Galerie + Hotspot-Steuerung"""

from .server import (
    start_server,
    stop_server,
    is_running,
    get_gallery_url,
    get_app_pairing_url,
    get_app_display_code,
    get_app_landing_url,
    set_app_context as set_gallery_app_context,
    set_locale as set_gallery_locale,
    set_gallery_feature_enabled,
    is_gallery_feature_enabled,
)
from .qrcode_gen import generate_qr_code, generate_qr_with_label
from .hotspot import start_hotspot, stop_hotspot, is_hotspot_active, ensure_hotspot_state
from .hotspot_watchdog import start_watchdog as start_hotspot_watchdog
from .hotspot_watchdog import stop_watchdog as stop_hotspot_watchdog
from .hotspot_watchdog import watchdog_status_line as hotspot_watchdog_status_line

__all__ = [
    'start_hotspot_watchdog',
    'stop_hotspot_watchdog',
    'hotspot_watchdog_status_line',
    'start_server',
    'stop_server',
    'is_running',
    'get_gallery_url',
    'get_app_pairing_url',
    'get_app_display_code',
    'get_app_landing_url',
    'set_gallery_app_context',
    'set_gallery_locale',
    'set_gallery_feature_enabled',
    'is_gallery_feature_enabled',
    'generate_qr_code',
    'generate_qr_with_label',
    'start_hotspot',
    'stop_hotspot',
    'is_hotspot_active',
    'ensure_hotspot_state'
]
