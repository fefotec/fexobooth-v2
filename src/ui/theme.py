"""Modernes Theme für Fexobooth

Responsive Design - passt sich automatisch an Bildschirmgröße an
"""

import tkinter as tk

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


# Screen-Größe cachen (wird beim ersten Aufruf gesetzt)
_screen_info = {
    "width": None,
    "height": None,
    "scale": 1.0
}


def get_screen_size():
    """Ermittelt die Bildschirmgröße und Skalierungsfaktor"""
    if _screen_info["width"] is None:
        try:
            root = tk._get_default_root()
            if root:
                _screen_info["width"] = root.winfo_screenwidth()
                _screen_info["height"] = root.winfo_screenheight()
            else:
                # Temporäres Fenster für Größenermittlung
                temp = tk.Tk()
                temp.withdraw()
                _screen_info["width"] = temp.winfo_screenwidth()
                _screen_info["height"] = temp.winfo_screenheight()
                temp.destroy()
        except:
            # Fallback auf Standard-Größe
            _screen_info["width"] = 1280
            _screen_info["height"] = 800

        # Skalierungsfaktor berechnen (Basis: 1280x800)
        width_scale = _screen_info["width"] / 1280
        height_scale = _screen_info["height"] / 800
        _screen_info["scale"] = min(width_scale, height_scale, 1.0)  # Nie größer als 1.0

    return _screen_info["width"], _screen_info["height"], _screen_info["scale"]


def scale(value: int) -> int:
    """Skaliert einen Wert basierend auf der Bildschirmgröße"""
    _, _, scale_factor = get_screen_size()
    return max(int(value * scale_factor), 1)


def is_small_screen() -> bool:
    """Prüft ob es ein kleiner Bildschirm ist (< 1280x800)"""
    width, height, _ = get_screen_size()
    return width < 1280 or height < 800


# Fonts - Responsive
# Auf kleinen Tablets (10 Zoll, 1280x800) sind Texte physisch klein,
# daher werden Nutzer-Texte deutlich größer als auf einem Desktop-Monitor.
def get_fonts():
    """Gibt Fonts zurück, angepasst an Bildschirmgröße"""
    s = get_screen_size()[2]  # scale factor

    return {
        "title": ("Segoe UI", max(int(40 * s), 24), "bold"),
        "heading": ("Segoe UI", max(int(28 * s), 18), "bold"),
        "subheading": ("Segoe UI", max(int(20 * s), 14), "bold"),
        "body": ("Segoe UI", max(int(18 * s), 13)),
        "body_bold": ("Segoe UI", max(int(18 * s), 13), "bold"),
        "small": ("Segoe UI", max(int(15 * s), 11)),
        "tiny": ("Segoe UI", max(int(12 * s), 10)),
        "countdown": ("Segoe UI", max(int(180 * s), 100), "bold"),
        "button": ("Segoe UI", max(int(18 * s), 13), "bold"),
        "button_large": ("Segoe UI", max(int(22 * s), 16), "bold"),
    }


# Statische Fonts (für Kompatibilität, gleiche Größen wie get_fonts bei scale=1.0)
FONTS = {
    "title": ("Segoe UI", 40, "bold"),
    "heading": ("Segoe UI", 28, "bold"),
    "subheading": ("Segoe UI", 20, "bold"),
    "body": ("Segoe UI", 18),
    "body_bold": ("Segoe UI", 18, "bold"),
    "small": ("Segoe UI", 15),
    "tiny": ("Segoe UI", 12),
    "countdown": ("Segoe UI", 180, "bold"),
    "button": ("Segoe UI", 18, "bold"),
    "button_large": ("Segoe UI", 22, "bold"),
}


# Größen - Responsive
def get_sizes():
    """Gibt Größen zurück, angepasst an Bildschirmgröße"""
    width, height, s = get_screen_size()
    small = is_small_screen()

    return {
        # Buttons
        "button_width": scale(140),
        "button_height": scale(45),
        "button_large_width": scale(200),
        "button_large_height": scale(55),

        # Template-Karten (StartScreen)
        "card_width": 220 if small else 280,
        "card_height": 190 if small else 240,

        # Filter-Karten (FilterScreen) - KLEINER für kleine Bildschirme
        "filter_card_width": 110 if small else 150,
        "filter_card_height": 100 if small else 130,
        "filter_thumb_width": 95 if small else 130,
        "filter_thumb_height": 65 if small else 85,

        # Abstände
        "corner_radius": 12 if not small else 10,
        "corner_radius_small": 8 if not small else 6,
        "padding": 15 if not small else 10,
        "padding_small": 8 if not small else 5,

        # Top-Bar
        "topbar_height": scale(50),

        # Filter-Buttons
        "filter_button_size": 60 if small else 80,
    }


# Statische Größen (für Kompatibilität)
SIZES = {
    "button_width": 140,
    "button_height": 45,
    "button_large_width": 200,
    "button_large_height": 55,
    "card_width": 280,
    "card_height": 240,
    "filter_card_width": 150,
    "filter_card_height": 130,
    "filter_thumb_width": 130,
    "filter_thumb_height": 85,
    "corner_radius": 12,
    "corner_radius_small": 8,
    "padding": 15,
    "padding_small": 8,
    "topbar_height": 50,
    "filter_button_size": 80,
}


def get_button_style(color: str = "primary"):
    """Gibt Button-Konfiguration zurück"""
    sizes = get_sizes()

    if color == "primary":
        return {
            "fg_color": COLORS["primary"],
            "hover_color": COLORS["primary_hover"],
            "text_color": COLORS["text_primary"],
            "corner_radius": sizes["corner_radius"],
        }
    elif color == "success":
        return {
            "fg_color": COLORS["success"],
            "hover_color": "#00e676",
            "text_color": COLORS["text_primary"],
            "corner_radius": sizes["corner_radius"],
        }
    elif color == "secondary":
        return {
            "fg_color": COLORS["bg_light"],
            "hover_color": COLORS["bg_card"],
            "text_color": COLORS["text_primary"],
            "corner_radius": sizes["corner_radius"],
        }
    elif color == "ghost":
        return {
            "fg_color": "transparent",
            "hover_color": COLORS["bg_light"],
            "text_color": COLORS["text_secondary"],
            "corner_radius": sizes["corner_radius"],
        }
    return get_button_style("primary")


def scale_for_dpi(value: int, base_width: int = 1280) -> int:
    """Skaliert einen Wert basierend auf der tatsächlichen Bildschirmbreite"""
    return scale(value)
