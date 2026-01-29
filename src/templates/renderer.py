"""Template-Renderer"""

from typing import List, Dict, Optional
from PIL import Image

from src.utils.logging import get_logger

logger = get_logger(__name__)


class TemplateRenderer:
    """Rendert Fotos in ein Template"""
    
    def __init__(self, canvas_width: int = 1800, canvas_height: int = 1200):
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
    
    def render(
        self,
        photos: List[Image.Image],
        boxes: List[Dict],
        overlay: Optional[Image.Image] = None,
        background_color: str = "#000000"
    ) -> Image.Image:
        """Rendert Fotos in Template
        
        Args:
            photos: Liste von Foto-Bildern
            boxes: Liste von Photo-Boxen {"box": (x1, y1, x2, y2), "angle": float}
            overlay: Overlay-Bild (optional)
            background_color: Hintergrundfarbe
            
        Returns:
            Fertiges Bild
        """
        # Canvas erstellen
        canvas = Image.new("RGBA", (self.canvas_width, self.canvas_height), background_color)
        
        # Fotos einfügen
        for i, box_info in enumerate(boxes):
            if i >= len(photos):
                break
            
            photo = photos[i]
            box = box_info["box"]
            angle = box_info.get("angle", 0.0)
            
            # Foto in Box einpassen
            fitted = self._fit_photo_to_box(photo, box)
            
            # Rotation anwenden
            if angle != 0:
                fitted = fitted.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
            
            # An Position einfügen
            x1, y1 = box[0], box[1]
            canvas.paste(fitted, (x1, y1), fitted if fitted.mode == "RGBA" else None)
        
        # Overlay anwenden
        if overlay:
            # Overlay auf Canvas-Größe skalieren falls nötig
            if overlay.size != (self.canvas_width, self.canvas_height):
                overlay = overlay.resize(
                    (self.canvas_width, self.canvas_height),
                    Image.Resampling.LANCZOS
                )
            canvas = Image.alpha_composite(canvas, overlay)
        
        return canvas
    
    def _fit_photo_to_box(self, photo: Image.Image, box: tuple) -> Image.Image:
        """Passt ein Foto in eine Box ein (Cover-Modus)"""
        x1, y1, x2, y2 = box
        box_width = x2 - x1 + 1
        box_height = y2 - y1 + 1
        
        photo_width, photo_height = photo.size
        
        # Aspect Ratios
        box_aspect = box_width / box_height
        photo_aspect = photo_width / photo_height
        
        if photo_aspect > box_aspect:
            # Foto ist breiter → auf Höhe skalieren, horizontal croppen
            new_height = box_height
            new_width = int(new_height * photo_aspect)
            resized = photo.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Horizontal zentriert croppen
            left = (new_width - box_width) // 2
            cropped = resized.crop((left, 0, left + box_width, box_height))
        else:
            # Foto ist höher → auf Breite skalieren, vertikal croppen
            new_width = box_width
            new_height = int(new_width / photo_aspect)
            resized = photo.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Vertikal zentriert croppen
            top = (new_height - box_height) // 2
            cropped = resized.crop((0, top, box_width, top + box_height))
        
        return cropped.convert("RGBA")
    
    def render_preview(
        self,
        photos: List[Image.Image],
        boxes: List[Dict],
        overlay: Optional[Image.Image] = None,
        max_size: int = 800
    ) -> Image.Image:
        """Rendert eine kleinere Vorschau"""
        # Vollständig rendern
        full = self.render(photos, boxes, overlay)
        
        # Skalieren
        ratio = min(max_size / full.width, max_size / full.height)
        if ratio < 1:
            new_size = (int(full.width * ratio), int(full.height * ratio))
            return full.resize(new_size, Image.Resampling.LANCZOS)
        
        return full
