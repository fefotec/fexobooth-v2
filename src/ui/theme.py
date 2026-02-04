"""Modernes Theme für Fexobooth

Optimiert für Lenovo Miix 310 (1280x800 @ 10.1")
"""

# Farbpalette - Modern Dark mit Pink Akzent
COLORS = {
    # Primärfarben
    "primary": "#e00675",           # Fexobox Pink
    "primary_hover": "#ff1493",
    "primary_dark": "#b8005e",
    
    # Hintergrund
    "bg_dark": "#0d0d12",           # Sehr dunkles Schwarz-Blau
    "bg_medium": "#1a1a24",         # Dunkles Panel
    "bg_light": "#252532",          # Helleres Panel
    "bg_card": "#2a2a3a",           # Karten-Hintergrund
    
    # Text
    "text_primary": "#ffffff",
    "text_secondary": "#a0a0b0",
    "text_muted": "#606070",
    
    # Akzente
    "success": "#00d26a",
    "warning": "#ffb800",
    "error": "#ff4757",
    "info": "#3498db",
    
    # Borders
    "border": "#3a3a4a",
    "border_light": "#4a4a5a",
}

# Fonts - Optimiert für 1280x800 Display
FONTS = {
    "title": ("Segoe UI", 32, "bold"),        # War 42
    "heading": ("Segoe UI", 22, "bold"),      # War 28
    "subheading": ("Segoe UI", 16, "bold"),   # War 20
    "body": ("Segoe UI", 14),                 # War 16
    "body_bold": ("Segoe UI", 14, "bold"),
    "small": ("Segoe UI", 12),                # War 14
    "tiny": ("Segoe UI", 11),                 # War 12
    "countdown": ("Segoe UI", 180, "bold"),   # War 280 - für 800px Höhe
    "button": ("Segoe UI", 14, "bold"),       # War 18
    "button_large": ("Segoe UI", 18, "bold"), # War 24
}

# Größen - Angepasst für 1280x800
SIZES = {
    # Buttons
    "button_width": 140,              # War 200
    "button_height": 45,              # War 60
    "button_large_width": 200,        # War 280
    "button_large_height": 55,        # War 80
    
    # Template-Karten (größer für bessere Erkennbarkeit)
    "card_width": 280,                # Größer für 1280px Breite
    "card_height": 240,               # Größer für bessere Vorschau
    
    # Abstände
    "corner_radius": 12,              # War 16
    "corner_radius_small": 8,         # War 10
    "padding": 15,                    # War 20
    "padding_small": 8,               # War 10
    
    # Top-Bar
    "topbar_height": 50,              # War 70
    
    # Filter-Buttons
    "filter_button_size": 80,         # Kompakter für alle Filter sichtbar
}


def get_button_style(color: str = "primary"):
    """Gibt Button-Konfiguration zurück"""
    if color == "primary":
        return {
            "fg_color": COLORS["primary"],
            "hover_color": COLORS["primary_hover"],
            "text_color": COLORS["text_primary"],
            "corner_radius": SIZES["corner_radius"],
        }
    elif color == "success":
        return {
            "fg_color": COLORS["success"],
            "hover_color": "#00e676",
            "text_color": COLORS["text_primary"],
            "corner_radius": SIZES["corner_radius"],
        }
    elif color == "secondary":
        return {
            "fg_color": COLORS["bg_light"],
            "hover_color": COLORS["bg_card"],
            "text_color": COLORS["text_primary"],
            "corner_radius": SIZES["corner_radius"],
        }
    elif color == "ghost":
        return {
            "fg_color": "transparent",
            "hover_color": COLORS["bg_light"],
            "text_color": COLORS["text_secondary"],
            "corner_radius": SIZES["corner_radius"],
        }
    return get_button_style("primary")


def scale_for_dpi(value: int, base_width: int = 1280) -> int:
    """Skaliert einen Wert basierend auf der tatsächlichen Bildschirmbreite"""
    # Kann später für DPI-Skalierung verwendet werden
    return value
