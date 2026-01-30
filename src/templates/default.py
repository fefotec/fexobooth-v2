"""Standard-Template Generator

Erstellt ein einfaches 4-Foto Strip-Layout wenn kein Template konfiguriert ist.
"""

from PIL import Image, ImageDraw
from typing import List, Dict, Tuple

from src.utils.logging import get_logger

logger = get_logger(__name__)


# Standard Canvas-Größe (6x4 inch @ 300dpi)
DEFAULT_WIDTH = 1800
DEFAULT_HEIGHT = 1200


def create_default_template() -> Tuple[Image.Image, List[Dict]]:
    """Erstellt ein Standard 2x2 Layout
    
    Returns:
        Tuple aus (Overlay-Bild, Photo-Boxen)
    """
    # Transparentes Overlay erstellen
    overlay = Image.new("RGBA", (DEFAULT_WIDTH, DEFAULT_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Rahmen zeichnen (optional - hier dezenter grauer Rand)
    border_color = (40, 40, 50, 255)
    draw.rectangle([0, 0, DEFAULT_WIDTH-1, DEFAULT_HEIGHT-1], outline=border_color, width=3)
    
    # 2x2 Grid mit Padding
    padding = 30
    gap = 20
    
    # Foto-Größe berechnen
    photo_width = (DEFAULT_WIDTH - 2 * padding - gap) // 2
    photo_height = (DEFAULT_HEIGHT - 2 * padding - gap) // 2
    
    # Photo-Boxen definieren (2x2 Grid)
    boxes = []
    
    # Oben links
    x1, y1 = padding, padding
    boxes.append({
        "box": (x1, y1, x1 + photo_width - 1, y1 + photo_height - 1),
        "angle": 0.0,
        "number": 1
    })
    
    # Oben rechts
    x1 = padding + photo_width + gap
    boxes.append({
        "box": (x1, y1, x1 + photo_width - 1, y1 + photo_height - 1),
        "angle": 0.0,
        "number": 2
    })
    
    # Unten links
    x1, y1 = padding, padding + photo_height + gap
    boxes.append({
        "box": (x1, y1, x1 + photo_width - 1, y1 + photo_height - 1),
        "angle": 0.0,
        "number": 3
    })
    
    # Unten rechts
    x1 = padding + photo_width + gap
    boxes.append({
        "box": (x1, y1, x1 + photo_width - 1, y1 + photo_height - 1),
        "angle": 0.0,
        "number": 4
    })
    
    logger.info(f"Standard-Template erstellt: 2x2 Grid, {len(boxes)} Fotos")
    
    return overlay, boxes


def create_strip_template() -> Tuple[Image.Image, List[Dict]]:
    """Erstellt ein vertikales Strip-Layout (4 Fotos übereinander)
    
    Returns:
        Tuple aus (Overlay-Bild, Photo-Boxen)
    """
    # Strip ist schmaler und höher
    strip_width = 600
    strip_height = 1800
    
    overlay = Image.new("RGBA", (strip_width, strip_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Rahmen
    draw.rectangle([0, 0, strip_width-1, strip_height-1], outline=(40, 40, 50, 255), width=2)
    
    # 4 Fotos vertikal
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
