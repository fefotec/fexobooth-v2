"""Modernes Theme für Fexobooth

Responsive Design - passt sich automatisch an Bildschirmgröße an
"""

import tkinter as tk

# Farbpalette - Modern Dark mit Pink Akzent
# (Refresh 2026-06: Hintergründe vertieft + Borders subtiler -> mehr Tiefe und
#  Premium-Look; Pink-Markenfarbe bleibt unverändert. Reine Farb-Tokens, kein
#  Layout-Einfluss, performance-neutral.)
COLORS = {
    # Primärfarben (Marke – NICHT ändern)
    "primary": "#e00675",           # Fexobox Pink
    "primary_hover": "#e00675",     # Touch-Geraet: Hover = Normalfarbe (Redesign 2.4.70)
    "primary_dark": "#b8005e",
    "primary_pressed": "#b8005e",   # Gedrückt-Zustand (Redesign 2.4.70)

    # Hintergrund – tiefer gestaffelt für mehr Kontrast/Tiefe
    "bg_dark": "#08080c",           # Fast-Schwarz (tiefer als vorher)
    "bg_medium": "#14141c",         # Dunkles Panel
    "bg_light": "#1f1f29",          # Helleres Panel
    "bg_card": "#212130",           # Karten-Hintergrund

    # Text
    "text_primary": "#ffffff",
    "text_secondary": "#a6a6b6",
    "text_muted": "#5c5c6c",

    # Akzente (Gäste-UI nutzt seit dem Redesign 2.4.70 nur noch Pink;
    # success/warning/error bleiben für Admin-/Service-Flächen und Top-Bar)
    "success": "#00d26a",
    "warning": "#ffb800",
    "error": "#ff4757",
    "info": "#3498db",

    # Borders – subtiler, damit der Pink-Akzent stärker führt
    "border": "#2c2c3a",
    "border_light": "#3a3a48",
    "pressed_secondary": "#2c2c3a",  # Secondary/Tertiary gedrückt (Fläche)

    # Träger-Flächen (Redesign 2.4.70)
    "paper": "#f4f2ef",             # Collagen-Träger in Vorschauen
    "white": "#ffffff",             # QR-/Illustrations-Träger
}


# ─────────────────────────────────────────────
# Redesign 2.4.70: Gäste-UI-Tokens (Handoff „Fexobox UI-Redesign Modern")
# Feste Werte für 1280×800 — die Gäste-Screens sind auf diese eine
# Zielauflösung gestaltet (alle Boxen: Lenovo Miix 310).
# ─────────────────────────────────────────────

# Segoe UI Semibold ist in Tk eine EIGENE Font-Family (weight bleibt normal)
SEMIBOLD = "Segoe UI Semibold"

FONTS_UI = {
    "display": ("Segoe UI", 44, "bold"),        # Start-Titel
    "h1": ("Segoe UI", 36, "bold"),             # Filter-/Final-Titel
    "h2": (SEMIBOLD, 28),                        # „Dein Bild wird erstellt …"
    "h3": (SEMIBOLD, 26),                        # Kartentitel, „Foto 2 von 4"
    "button_xl": ("Segoe UI", 28, "bold"),      # START, DRUCKEN
    "button": ("Segoe UI", 26, "bold"),         # WEITER, NOCHMAL, VERSTANDEN
    "button_s": ("Segoe UI", 22, "bold"),       # FERTIG
    "body": ("Segoe UI", 20),                    # Untertitel, Dialog-Text
    "label": (SEMIBOLD, 18),                     # Filter-Namen, Tertiary, Eyebrow
    "caption": ("Segoe UI", 16),                 # „3 Ausdrucke verfügbar"
    "small": ("Segoe UI", 15),                   # QR-Panel Zeilen
    "small_semibold": (SEMIBOLD, 15),
    "micro": ("Segoe UI", 14),                   # Dialog-Hinweis
}

RADII = {
    "dialog": 28,
    "card": 24,
    "button": 20,
    "tile": 16,
    "thumb": 12,
}


def bind_pressed(button, normal: str, pressed: str):
    """Gedrückt-Feedback für Touch: nur Farbwechsel, kein Hover.

    Genau EIN configure-Aufruf je Ereignis (Performance-Richtlinie Miix).
    Deaktivierte Buttons bleiben unangetastet — sonst würde ein Touch auf
    einen grauen Button ihn dauerhaft in die Normalfarbe zurückfärben.
    """
    def _set(color):
        try:
            if button.cget("state") != "disabled":
                button.configure(fg_color=color)
        except Exception:
            pass

    button.configure(hover_color=normal)
    button.bind("<ButtonPress-1>", lambda e: _set(pressed), add="+")
    button.bind("<ButtonRelease-1>", lambda e: _set(normal), add="+")


def style_primary(width: int = 320, height: int = 88, font_key: str = "button") -> dict:
    """Primary-Button (Pink) — der EINE dominante Button pro Screen."""
    return {
        "width": width, "height": height,
        "corner_radius": RADII["button"],
        "font": FONTS_UI[font_key],
        "fg_color": COLORS["primary"],
        "hover_color": COLORS["primary"],
        "text_color": COLORS["text_primary"],
    }


def style_secondary(width: int = 320, height: int = 88, font_key: str = "button") -> dict:
    """Secondary-Button (dunkle Fläche mit Rahmen)."""
    return {
        "width": width, "height": height,
        "corner_radius": RADII["button"],
        "font": FONTS_UI[font_key],
        "fg_color": COLORS["bg_light"],
        "hover_color": COLORS["bg_light"],
        "border_width": 2,
        "border_color": COLORS["border_light"],
        "text_color": COLORS["text_primary"],
    }


def style_tertiary(width: int = 0, height: int = 56) -> dict:
    """Tertiary-Button (Abbrechen, Fotos nochmal) — zurückhaltend."""
    style = {
        "height": height,
        "corner_radius": RADII["tile"],
        "font": FONTS_UI["label"],
        "fg_color": COLORS["bg_medium"],
        "hover_color": COLORS["bg_medium"],
        "border_width": 2,
        "border_color": COLORS["border"],
        "text_color": COLORS["text_secondary"],
    }
    if width:
        style["width"] = width
    return style


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
