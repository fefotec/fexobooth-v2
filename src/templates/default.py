"""Standard-Template Generator

Lädt das Default-Template aus assets/Default-Template.zip.
Falls die ZIP-Datei nicht gefunden wird, wird ein einfaches 2x2 Layout generiert.
"""

import os
import sys
from PIL import Image, ImageDraw
from typing import List, Dict, Tuple, Optional

from src.utils.logging import get_logger

logger = get_logger(__name__)


# Standard Canvas-Größe (6x4 inch @ 300dpi)
DEFAULT_WIDTH = 1800
DEFAULT_HEIGHT = 1200

# Modul-Level Cache für das Default-Template
_default_template_cache: Optional[Tuple[Image.Image, List[Dict]]] = None


def _get_default_template_zip_path() -> Optional[str]:
    """Findet den Pfad zur Default-Template.zip.

    Sucht in folgender Reihenfolge:
    1. PyInstaller _MEIPASS/assets/Default-Template.zip (im Build)
    2. Relativ zum Projektverzeichnis: assets/Default-Template.zip (Entwicklung)
    """
    candidates = []

    # PyInstaller Build
    if hasattr(sys, '_MEIPASS'):
        candidates.append(os.path.join(sys._MEIPASS, "assets", "Default-Template.zip"))

    # Entwicklungsmodus: relativ zum Projektroot
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates.append(os.path.join(project_root, "assets", "Default-Template.zip"))

    for path in candidates:
        if os.path.exists(path):
            return path

    return None


def create_default_template() -> Tuple[Image.Image, List[Dict]]:
    """Lädt das Standard-Template aus Default-Template.zip.

    Falls die ZIP nicht gefunden wird, wird ein programmatisches 2x2 Layout erzeugt.
    Ergebnis wird gecacht für wiederholte Aufrufe.

    Returns:
        Tuple aus (Overlay-Bild, Photo-Boxen)
    """
    global _default_template_cache

    # Cache prüfen
    if _default_template_cache is not None:
        logger.info("Default-Template aus Cache")
        return _default_template_cache

    # Default-Template.zip suchen und laden
    zip_path = _get_default_template_zip_path()
    if zip_path:
        try:
            from src.templates.loader import TemplateLoader
            overlay, boxes = TemplateLoader.load(zip_path, use_cache=True)
            if overlay and boxes:
                logger.info(f"Default-Template geladen: {zip_path} ({overlay.size[0]}x{overlay.size[1]}, {len(boxes)} Slots)")
                _default_template_cache = (overlay, boxes)
                return overlay, boxes
            else:
                logger.warning(f"Default-Template.zip konnte nicht geladen werden: {zip_path}")
        except Exception as e:
            logger.error(f"Fehler beim Laden von Default-Template.zip: {e}")
    else:
        logger.warning("Default-Template.zip nicht gefunden")

    # Fallback: Programmatisches 2x2 Layout
    logger.info("Fallback: Programmatisches 2x2 Template")
    result = _create_programmatic_2x2()
    _default_template_cache = result
    return result


def _create_programmatic_2x2() -> Tuple[Image.Image, List[Dict]]:
    """Erstellt ein einfaches programmatisches 2x2 Layout als Fallback."""
    overlay = Image.new("RGBA", (DEFAULT_WIDTH, DEFAULT_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Rahmen zeichnen
    border_color = (40, 40, 50, 255)
    draw.rectangle([0, 0, DEFAULT_WIDTH-1, DEFAULT_HEIGHT-1], outline=border_color, width=3)

    # 2x2 Grid mit Padding
    padding = 30
    gap = 20

    photo_width = (DEFAULT_WIDTH - 2 * padding - gap) // 2
    photo_height = (DEFAULT_HEIGHT - 2 * padding - gap) // 2

    boxes = []
    positions = [
        (padding, padding),                              # Oben links
        (padding + photo_width + gap, padding),           # Oben rechts
        (padding, padding + photo_height + gap),          # Unten links
        (padding + photo_width + gap, padding + photo_height + gap),  # Unten rechts
    ]

    for i, (x1, y1) in enumerate(positions):
        boxes.append({
            "box": (x1, y1, x1 + photo_width - 1, y1 + photo_height - 1),
            "angle": 0.0,
            "number": i + 1
        })

    logger.info(f"Programmatisches 2x2 Template erstellt: {len(boxes)} Fotos")
    return overlay, boxes


def create_strip_template() -> Tuple[Image.Image, List[Dict]]:
    """Erstellt ein vertikales Strip-Layout (4 Fotos übereinander)

    Returns:
        Tuple aus (Overlay-Bild, Photo-Boxen)
    """
    strip_width = 600
    strip_height = 1800

    overlay = Image.new("RGBA", (strip_width, strip_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    draw.rectangle([0, 0, strip_width-1, strip_height-1], outline=(40, 40, 50, 255), width=2)

    padding = 20
    gap = 15

    photo_width = strip_width - 2 * padding
    photo_height = (strip_height - 2 * padding - 3 * gap) // 4

    boxes = []
    y = padding

    for i in range(4):
        boxes.append({
            "box": (padding, y, padding + photo_width - 1, y + photo_height - 1),
            "angle": 0.0,
            "number": i + 1
        })
        y += photo_height + gap

    logger.info(f"Strip-Template erstellt: 4 Fotos vertikal")
    return overlay, boxes


def get_default_boxes_for_single() -> List[Dict]:
    """Gibt eine einzelne Box für Single-Foto zurück"""
    return [{
        "box": (0, 0, DEFAULT_WIDTH - 1, DEFAULT_HEIGHT - 1),
        "angle": 0.0,
        "number": 1
    }]
