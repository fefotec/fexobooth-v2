"""Standard-Konfigurationswerte"""

DEFAULT_CONFIG = {
    # Sicherheit
    "admin_pin": "3198",
    
    # Timing
    "countdown_time": 5,
    "single_display_time": 2,
    "final_time": 20,
    "flash_duration": 300,  # Auslöse-Bild Dauer in Millisekunden
    
    # Modi
    "allow_single_mode": True,
    "performance_mode": True,
    "start_fullscreen": True,
    
    # Galerie (lokaler Webserver für QR-Code Download)
    "gallery_enabled": False,
    "gallery_port": 8080,
    "gallery_show_qr": True,  # QR-Code auf Final-Screen anzeigen
    
    # Templates
    "template1_enabled": True,
    "template2_enabled": False,
    "template_paths": {
        "template1": "assets/templates/Fexobox Standard.zip",
        "template2": ""
    },
    
    # Branding
    "logo_path": "",
    "logo_scale": 80,
    "background_color": "#1a1a2e",

    # Kamera
    "camera_type": "webcam",
    "camera_index": 0,
    "rotate_180": False,
    "liveview_template_overlay": True,  # Template-Overlay im LiveView anzeigen
    "camera_settings": {
        "single_photo_width": 1920,
        "single_photo_height": 1080,
        "live_view_resolution": 640
    },
    
    # Druck
    "printer_name": "",
    "max_prints_per_session": 1,
    "print_adjustment": {
        "offset_x": 0,      # Fein-Offset in Pixeln (horizontal)
        "offset_y": 0,      # Fein-Offset in Pixeln (vertikal)
        "zoom": 103,        # Zoom in Prozent (103% für randlosen Druck empfohlen)
        "bleed_mm": 3       # Überdrucken in mm pro Seite (für randlosen Druck)
    },
    
    # UI Texte
    "ui_texts": {
        "admin": "ADMIN",
        "finish": "FERTIG",
        "print": "DRUCKEN",
        "redo": "NOCHMAL",
        "cancel": "ABBRECHEN",
        "start": "START",
        "choose_mode": "Wähle dein Layout!",
        "choose_filter": "Wähle einen Filter"
    },
    
    # Videos
    "video_start": "assets/videos/start.mp4",
    "video_end": "assets/videos/end.mp4",
    
    # Canvas
    "canvas_width": 1800,
    "canvas_height": 1200,
    
    # Sonstiges
    "admin_button_alpha": 0.1,
    "hide_finish_button": True,
    "print_enabled": True,
    
    # Developer Mode
    "developer_mode": False,  # Aktiviert: Logging, CPU/RAM Anzeige

    # Auto-Update (nur im Firmen-WLAN mit Internet)
    "auto_update_enabled": True,
    "company_wifi_ssids": [
        "fexon WLAN",
        "fexon_Buero_WLAN2",
        "fexon_Buero_WLAN2_5GHZ",
        "fexon Gast-WLAN",
        "fexon_outdoor",
    ],
}
