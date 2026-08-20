"""Standard-Konfigurationswerte"""

DEFAULT_CONFIG = {
    # Sicherheit
    "admin_pin": "3198",
    
    # Timing
    "countdown_time": 7,
    "single_display_time": 3,
    "final_time": 20,
    "flash_duration": 100,  # Auslöse-Bild Dauer in Millisekunden
    
    # Modi
    "allow_single_mode": False,
    "performance_mode": True,
    "start_fullscreen": True,
    
    # Galerie (lokaler Webserver für QR-Code Download)
    "gallery_enabled": False,
    "gallery_port": 8080,
    "gallery_show_qr": True,  # QR-Code auf Final-Screen anzeigen
    "gallery": {
        "hotspot_ssid": "fexobox-gallery",
        "hotspot_password": "fotobox123",
        "port": 8080,
    },
    
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
    # Wurde camera_index im Admin-Menue von Hand gewaehlt? Grundwert False:
    # Eine frische Box hat camera_index 0 — auf dem Miix 310 ist das die
    # abgeklebte interne Kamera. Ohne Beweis (Erkennung oder Handauswahl)
    # wird dieser Index abgeschaltet, statt blind benutzt zu werden.
    "camera_index_manuell": False,
    "rotate_180": False,
    "liveview_template_overlay": True,  # Template-Overlay im LiveView anzeigen
    "camera_settings": {
        "single_photo_width": 1920,
        "single_photo_height": 1080,
        "live_view_resolution": 640
    },
    # Nikon DSLR über die eigene unsichtbare FexoNikonBridge (Variante 3, wie dslrBooth):
    # kleiner versteckter Hintergrundprozess (kein Fenster), spricht rohes PTP/MTP über
    # die Windows-WPD-API mit der Kamera. Kommunikation über stdin/stdout (keine Ports).
    # Leerer exe_path = Standardpfade verwenden ({app}\bridge\FexoNikonBridge.exe).
    "nikon_bridge": {
        "exe_path": "",
        "init_timeout_seconds": 20,
        "command_timeout_seconds": 4,
        "capture_timeout_seconds": 12,
        # JPEG-Größe an der Kamera: "M" (D3300: 4496x3000) reicht für den
        # 1800x1200-Druck locker und halbiert fast den USB-Transfer pro Foto.
        # "L" = volle Auflösung, "S" = klein, "" = Kamera-Einstellung nicht anfassen.
        "image_size": "M"
    },

    # Druck
    "printer_name": "",
    "max_prints_per_session": 1,
    "print_adjustment": {
        # Default-Kalibrierung Canon SELPHY CP1000 (10x15cm, randlos):
        # X+40, Y+30 und 103% werden bei jedem Eventwechsel wiederhergestellt.
        "offset_x": 40,     # Fein-Offset in Pixeln (horizontal)
        "offset_y": 30,     # Fein-Offset in Pixeln (vertikal)
        "zoom": 103,        # Zoom in Prozent (103% für randlosen Druck empfohlen)
        "bleed_mm": 3       # Überdrucken in mm pro Seite (für randlosen Druck)
    },
    
    # UI Texte
    "locale": "de-DE",
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
    "video_start": "assets/videos/Fexon - Fotobox Tutorial 1 By Videoboost.Undefined.mp4",
    "video_after_1": "assets/videos/Fexon - Fotobox Tutorial 3 By Videoboost.Undefined.mp4",
    "video_after_2": "assets/videos/Fexon - Fotobox Tutorial 4 By Videoboost.Undefined.mp4",
    "video_after_3": "assets/videos/Fexon - Fotobox Tutorial 5 By Videoboost.Undefined.mp4",
    "video_end": "assets/videos/Fexon - Fotobox Tutorial 7 By Videoboost.Undefined.mp4",
    "flash_image": "assets/icons/foto-screen.jpeg",
    
    # Canvas
    "canvas_width": 1800,
    "canvas_height": 1200,
    
    # Sonstiges
    "box_id": "",  # 3-stellige Box-ID, wird manuell im Admin-Menü gesetzt
    "admin_button_alpha": 0.1,
    "hide_finish_button": True,
    "print_enabled": True,
    
    # Developer Mode
    "developer_mode": False,  # Aktiviert: Logging, CPU/RAM Anzeige

    # Auto-Update (nur im Firmen-WLAN mit Internet)
    "auto_update_enabled": True,
    "monitoring_enabled": True,
    "monitoring_endpoint": "https://admin.fexobox.de/api/booth/heartbeat",
    "monitoring_token": "",
    "company_wifi_ssids": [
        "fexon WLAN",
        "fexon_Buero_WLAN2",
        "fexon_Buero_WLAN2_5GHZ",
        "fexon Gast-WLAN",
        "fexon_outdoor",
    ],
}
