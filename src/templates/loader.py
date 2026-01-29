"""Template-Loader für ZIP-Templates (DSLR-Booth Format)"""

import os
import zipfile
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from xml.etree import ElementTree as ET
from PIL import Image

from src.utils.logging import get_logger

logger = get_logger(__name__)


class TemplateLoader:
    """Lädt Templates aus ZIP-Dateien (DSLR-Booth Format)
    
    ZIP-Struktur:
    - template.png (Overlay mit Transparenz)
    - template.xml (Foto-Positionen)
    """
    
    @staticmethod
    def load(path: str) -> Tuple[Optional[Image.Image], List[Dict]]:
        """Lädt ein Template
        
        Args:
            path: Pfad zur ZIP- oder PNG-Datei
            
        Returns:
            Tuple aus (Overlay-Bild, Liste von Photo-Boxen)
            Photo-Box: {"box": (x1, y1, x2, y2), "angle": float}
        """
        if not os.path.exists(path):
            logger.error(f"Template nicht gefunden: {path}")
            return None, []
        
        if path.lower().endswith(".zip"):
            return TemplateLoader._load_zip(path)
        else:
            return TemplateLoader._load_image(path)
    
    @staticmethod
    def _load_zip(zip_path: str) -> Tuple[Optional[Image.Image], List[Dict]]:
        """Lädt ein ZIP-Template"""
        temp_dir = tempfile.mkdtemp(prefix="fexobooth_")
        
        try:
            # ZIP entpacken
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_dir)
            
            overlay = None
            boxes = []
            
            # Dateien finden
            png_path = None
            xml_path = None
            max_size = 0
            
            for root, dirs, files in os.walk(temp_dir):
                for fn in files:
                    full_path = os.path.join(root, fn)
                    lower_fn = fn.lower()
                    
                    # Größte PNG finden (ignoriert Thumbnails)
                    if lower_fn.endswith(".png"):
                        size = os.path.getsize(full_path)
                        if size > max_size:
                            max_size = size
                            png_path = full_path
                    
                    # XML finden
                    elif lower_fn.endswith(".xml"):
                        xml_path = full_path
            
            # PNG laden
            if png_path:
                overlay = Image.open(png_path).convert("RGBA")
                logger.info(f"Overlay geladen: {overlay.size}")
            
            # XML parsen
            if xml_path:
                boxes = TemplateLoader._parse_xml(xml_path)
                logger.info(f"Template-Boxen geladen: {len(boxes)}")
            
            return overlay, boxes
            
        except Exception as e:
            logger.error(f"Fehler beim Laden des ZIP-Templates: {e}")
            return None, []
        
        finally:
            # Temp-Verzeichnis aufräumen
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @staticmethod
    def _load_image(image_path: str) -> Tuple[Optional[Image.Image], List[Dict]]:
        """Lädt ein einfaches Bild-Template (Masken-Erkennung)"""
        try:
            overlay = Image.open(image_path).convert("RGBA")
            
            # Transparente Bereiche als Photo-Boxen erkennen
            boxes = TemplateLoader._detect_boxes_from_mask(overlay)
            
            if not boxes:
                # Fallback: Ein großer Bereich
                w, h = overlay.size
                boxes = [{"box": (0, 0, w-1, h-1), "angle": 0.0}]
            
            return overlay, boxes
            
        except Exception as e:
            logger.error(f"Fehler beim Laden des Bild-Templates: {e}")
            return None, []
    
    @staticmethod
    def _parse_xml(xml_path: str) -> List[Dict]:
        """Parst die XML-Datei mit Photo-Positionen"""
        boxes = []
        
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Suche nach Photo-Elementen
            elements = root.find("Elements")
            if elements is not None:
                for photo in elements.findall("Photo"):
                    try:
                        x = int(photo.attrib.get("Left", 0))
                        y = int(photo.attrib.get("Top", 0))
                        w = int(photo.attrib.get("Width", 300))
                        h = int(photo.attrib.get("Height", 200))
                        angle = float(photo.attrib.get("Rotation", 0))
                        
                        boxes.append({
                            "box": (x, y, x + w - 1, y + h - 1),
                            "angle": angle,
                            "number": int(photo.attrib.get("PhotoNumber", len(boxes) + 1))
                        })
                    except Exception as e:
                        logger.warning(f"Fehler beim Parsen eines Photo-Elements: {e}")
            
            # Nach PhotoNumber sortieren
            boxes.sort(key=lambda x: x.get("number", 0))
            
        except Exception as e:
            logger.error(f"Fehler beim Parsen der XML: {e}")
        
        return boxes
    
    @staticmethod
    def _detect_boxes_from_mask(image: Image.Image) -> List[Dict]:
        """Erkennt transparente Bereiche als Photo-Boxen"""
        import numpy as np
        
        # Alpha-Kanal extrahieren
        if image.mode != "RGBA":
            return []
        
        alpha = np.array(image.split()[-1])
        
        # Transparente Bereiche finden (Alpha < 128)
        mask = (alpha < 128).astype(np.uint8) * 255
        
        # Morphologisches Closing
        try:
            import cv2
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            
            # Konturen finden
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            boxes = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                
                # Mindestgröße prüfen (ignoriert kleine Artefakte)
                if w * h > 10000:  # Mindestens 100x100 Pixel Äquivalent
                    aspect = w / h
                    # Nur annähernd rechteckige Bereiche (0.5 - 2.0 Aspect Ratio)
                    if 0.5 <= aspect <= 2.0:
                        boxes.append({
                            "box": (x, y, x + w - 1, y + h - 1),
                            "angle": 0.0
                        })
            
            # Nach Größe sortieren (größte zuerst), max 4
            boxes.sort(key=lambda b: (b["box"][2] - b["box"][0]) * (b["box"][3] - b["box"][1]), reverse=True)
            return boxes[:4]
            
        except ImportError:
            logger.warning("OpenCV nicht verfügbar für Masken-Erkennung")
            return []
