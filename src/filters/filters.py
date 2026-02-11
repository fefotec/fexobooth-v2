"""Bildfilter"""

from typing import Dict, Callable, Optional
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
from functools import lru_cache

from src.utils.logging import get_logger

logger = get_logger(__name__)


# Verfügbare Filter
AVAILABLE_FILTERS = {
    "none": "Original",
    "bw": "Schwarz-Weiß",
    "bw_contrast": "BW Kontrast",
    "sepia": "Sepia",
    "cool": "Cool Breeze",
    "vivid": "Vivid Pop",
    "film": "Filmisch",
    "instagram": "Insta Glow",
}


class FilterManager:
    """Verwaltet Bildfilter mit Caching"""
    
    def __init__(self):
        self._filters: Dict[str, Callable] = {
            "none": self._filter_none,
            "bw": self._filter_bw,
            "bw_contrast": self._filter_bw_contrast,
            "sepia": self._filter_sepia,
            "cool": self._filter_cool,
            "vivid": self._filter_vivid,
            "film": self._filter_film,
            "instagram": self._filter_instagram,
        }
        self._cache: Dict[str, Image.Image] = {}
    
    def apply(self, image: Image.Image, filter_key: str) -> Image.Image:
        """Wendet einen Filter auf ein Bild an"""
        if filter_key not in self._filters:
            logger.warning(f"Unbekannter Filter: {filter_key}")
            filter_key = "none"
        
        # Cache-Key
        cache_key = f"{id(image)}_{filter_key}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Filter anwenden
        result = self._filters[filter_key](image)
        
        # Cache (max 50 Einträge)
        if len(self._cache) > 50:
            self._cache.clear()
        self._cache[cache_key] = result
        
        return result
    
    def clear_cache(self):
        """Leert den Filter-Cache"""
        self._cache.clear()
    
    def get_filter_names(self) -> Dict[str, str]:
        """Gibt verfügbare Filter zurück"""
        return AVAILABLE_FILTERS.copy()
    
    # --- Filter-Implementierungen ---
    
    def _filter_none(self, img: Image.Image) -> Image.Image:
        """Kein Filter"""
        return img.convert("RGBA")
    
    def _filter_bw(self, img: Image.Image) -> Image.Image:
        """Schwarz-Weiß"""
        return ImageOps.grayscale(img).convert("RGBA")
    
    def _filter_bw_contrast(self, img: Image.Image) -> Image.Image:
        """Schwarz-Weiß mit erhöhtem Kontrast"""
        gray = ImageOps.grayscale(img)
        contrasted = ImageOps.autocontrast(gray, cutoff=5)
        contrasted = ImageEnhance.Brightness(contrasted).enhance(1.05)
        contrasted = ImageEnhance.Contrast(contrasted).enhance(1.1)
        return contrasted.convert("RGBA")
    
    def _filter_sepia(self, img: Image.Image) -> Image.Image:
        """Sepia-Ton"""
        bw = ImageOps.grayscale(img)
        sepia = ImageOps.colorize(bw, (30, 20, 10), (255, 240, 192))
        sepia = ImageEnhance.Contrast(sepia).enhance(1.2)
        sepia = ImageEnhance.Color(sepia).enhance(1.1)
        return sepia.convert("RGBA")
    
    def _filter_cool(self, img: Image.Image) -> Image.Image:
        """Kühle Farbtöne"""
        rgb = img.convert("RGB")
        r, g, b = rgb.split()
        b = b.point(lambda i: min(255, int(i * 1.15)))
        g = g.point(lambda i: min(255, int(i * 1.05)))
        merged = Image.merge("RGB", (r, g, b))
        merged = ImageEnhance.Color(merged).enhance(1.05)
        merged = ImageEnhance.Contrast(merged).enhance(1.05)
        return merged.convert("RGBA")
    
    def _filter_vivid(self, img: Image.Image) -> Image.Image:
        """Lebhafte Farben"""
        rgb = img.convert("RGB")
        vivid = ImageEnhance.Color(rgb).enhance(1.35)
        vivid = ImageEnhance.Contrast(vivid).enhance(1.1)
        vivid = ImageEnhance.Brightness(vivid).enhance(1.05)
        return vivid.convert("RGBA")
    
    def _filter_film(self, img: Image.Image) -> Image.Image:
        """Film-Look mit leichtem Grain"""
        rgb = img.convert("RGB")
        faded = ImageEnhance.Color(rgb).enhance(0.8)
        faded = ImageEnhance.Brightness(faded).enhance(1.05)
        faded = ImageEnhance.Contrast(faded).enhance(0.92)
        
        # Grain-Effekt
        grain = Image.effect_noise(rgb.size, 18)
        grain = grain.filter(ImageFilter.GaussianBlur(radius=0.4))
        grain_rgb = Image.merge("RGB", (grain, grain, grain))
        
        blended = Image.blend(faded, grain_rgb, 0.08)
        return blended.convert("RGBA")
    
    def _filter_instagram(self, img: Image.Image) -> Image.Image:
        """Instagram-Style: Warmer Glow, leichte Entsättigung, angehobene Schatten"""
        rgb = img.convert("RGB")

        # Schatten anheben: Dunkle Pixel aufhellen (Fade-Effekt)
        r, g, b = rgb.split()
        # Schatten-Lift: min 25 statt 0 für matten Look
        r = r.point(lambda i: max(i, 25) if i < 40 else i)
        g = g.point(lambda i: max(i, 20) if i < 40 else i)
        b = b.point(lambda i: max(i, 30) if i < 40 else i)

        # Warmer Farbton: Rot/Orange leicht anheben
        r = r.point(lambda i: min(255, i + 12))
        g = g.point(lambda i: min(255, i + 5))

        merged = Image.merge("RGB", (r, g, b))

        # Leicht entsättigen für matten Look, dann Kontrast
        merged = ImageEnhance.Color(merged).enhance(0.88)
        merged = ImageEnhance.Contrast(merged).enhance(1.08)
        merged = ImageEnhance.Brightness(merged).enhance(1.06)

        # Sanfter Glow (dezenter als soft_glow)
        blur = merged.filter(ImageFilter.GaussianBlur(radius=3))
        result = Image.blend(merged, blur, 0.15)

        return result.convert("RGBA")
