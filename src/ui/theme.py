"""Modernes Theme für Fexobooth"""

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

# Fonts
FONTS = {
    "title": ("Segoe UI", 42, "bold"),
    "heading": ("Segoe UI", 28, "bold"),
    "subheading": ("Segoe UI", 20, "bold"),
    "body": ("Segoe UI", 16),
    "body_bold": ("Segoe UI", 16, "bold"),
    "small": ("Segoe UI", 14),
    "tiny": ("Segoe UI", 12),
    "countdown": ("Segoe UI", 280, "bold"),
    "button": ("Segoe UI", 18, "bold"),
    "button_large": ("Segoe UI", 24, "bold"),
}

# Größen
SIZES = {
    "button_width": 200,
    "button_height": 60,
    "button_large_width": 280,
    "button_large_height": 80,
    "card_width": 320,
    "card_height": 280,
    "corner_radius": 16,
    "corner_radius_small": 10,
    "padding": 20,
    "padding_small": 10,
}

# Button Styles
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
