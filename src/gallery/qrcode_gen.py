"""QR-Code Generator für Galerie-URL"""

import io
from typing import Optional
from PIL import Image

from src.utils.logging import get_logger

logger = get_logger(__name__)


def generate_qr_code(url: str, size: int = 200, border: int = 2) -> Optional[Image.Image]:
    """Generiert einen QR-Code als PIL Image
    
    Args:
        url: Die URL die der QR-Code enthalten soll
        size: Größe in Pixeln (Breite/Höhe)
        border: Rand in Modulen
        
    Returns:
        PIL Image oder None bei Fehler
    """
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=ERROR_CORRECT_M,
            box_size=10,
            border=border,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        # Als PIL Image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Auf gewünschte Größe skalieren
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        
        logger.debug(f"QR-Code generiert für: {url}")
        return img
        
    except ImportError:
        logger.warning("qrcode Modul nicht installiert - pip install qrcode")
        return None
    except Exception as e:
        logger.error(f"QR-Code Generierung fehlgeschlagen: {e}")
        return None


def generate_qr_with_label(url: str, label: str = "Galerie scannen", 
                           size: int = 250, font_size: int = 16) -> Optional[Image.Image]:
    """Generiert QR-Code mit Beschriftung
    
    Args:
        url: Die URL
        label: Text unter dem QR-Code
        size: Größe des QR-Codes
        font_size: Schriftgröße
        
    Returns:
        PIL Image mit QR-Code und Label
    """
    from PIL import ImageDraw, ImageFont
    
    qr_img = generate_qr_code(url, size=size)
    if not qr_img:
        return None
    
    # Neues Bild mit Platz für Label
    label_height = font_size + 20
    combined = Image.new('RGB', (size, size + label_height), 'white')
    combined.paste(qr_img, (0, 0))
    
    # Label hinzufügen
    draw = ImageDraw.Draw(combined)
    
    try:
        # Versuche System-Font zu laden
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        # Fallback auf Default-Font
        font = ImageFont.load_default()
    
    # Text zentriert
    bbox = draw.textbbox((0, 0), label, font=font)
    text_width = bbox[2] - bbox[0]
    x = (size - text_width) // 2
    y = size + 5
    
    draw.text((x, y), label, fill='black', font=font)
    
    return combined
