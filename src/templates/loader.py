"""Template-Loader für ZIP-Templates (DSLR-Booth Format)

Unterstützt nur ZIP-Templates mit:
- template.png (Overlay mit Transparenz)
- template.xml (Foto-Positionen im DSLR-Booth Format)
"""

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
    """Lädt ZIP-Templates im DSLR-Booth Format"""
    
    @staticmethod
    def load(path: str) -> Tuple[Optional[Image.Image], List[Dict]]:
        """Lädt ein Template aus einer ZIP-Datei
        
        Args:
            path: Pfad zur ZIP-Datei
            
        Returns:
            Tuple aus (Overlay-Bild, Liste von Photo-Boxen)
            Photo-Box: {"box": (x1, y1, x2, y2), "angle": float, "number": int}
        """
        if not os.path.exists(path):
            logger.error(f"Template nicht gefunden: {path}")
            return None, []
        
        if not path.lower().endswith(".zip"):
            logger.error(f"Nur ZIP-Templates werden unterstützt: {path}")
            return None, []
        
        return TemplateLoader._load_zip(path)
    
    @staticmethod
    def _load_zip(zip_path: str) -> Tuple[Optional[Image.Image], List[Dict]]:
        """Lädt ein ZIP-Template"""
        temp_dir = tempfile.mkdtemp(prefix="fexobooth_template_")
        
        try:
            # ZIP entpacken
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_dir)
            
            overlay = None
            boxes = []
            
            # Dateien finden
            png_path = None
            xml_path = None
            max_png_size = 0
            
            for root, dirs, files in os.walk(temp_dir):
                for fn in files:
                    full_path = os.path.join(root, fn)
                    lower_fn = fn.lower()
                    
                    # Größte PNG finden (ignoriert Thumbnails/Previews)
                    if lower_fn.endswith(".png"):
                        try:
                            size = os.path.getsize(full_path)
                            if size > max_png_size:
                                max_png_size = size
                                png_path = full_path
                        except OSError:
                            pass
                    
                    # XML finden
                    elif lower_fn.endswith(".xml"):
                        xml_path = full_path
            
            # PNG laden
            if png_path:
                overlay = Image.open(png_path).convert("RGBA")
                logger.info(f"Overlay geladen: {overlay.size[0]}x{overlay.size[1]}")
            else:
                logger.warning(f"Keine PNG-Datei im Template gefunden: {zip_path}")
            
            # XML parsen
            if xml_path:
                boxes = TemplateLoader._parse_xml(xml_path, overlay.size if overlay else None)
                logger.info(f"Template-Boxen geladen: {len(boxes)} Foto-Slots")
            else:
                logger.warning(f"Keine XML-Datei im Template gefunden: {zip_path}")
            
            # Fallback wenn keine Boxen gefunden
            if not boxes and overlay:
                w, h = overlay.size
                boxes = [{
                    "box": (0, 0, w - 1, h - 1),
                    "angle": 0.0,
                    "number": 1
                }]
                logger.info("Fallback: Eine Box über das gesamte Bild")
            
            return overlay, boxes
            
        except Exception as e:
            logger.error(f"Fehler beim Laden des ZIP-Templates: {e}")
            return None, []
        
        finally:
            # Temp-Verzeichnis aufräumen
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
    
    @staticmethod
    def _parse_xml(xml_path: str, overlay_size: Optional[Tuple[int, int]] = None) -> List[Dict]:
        """Parst die XML-Datei mit Photo-Positionen (DSLR-Booth Format)
        
        Unterstützte XML-Struktur:
        <Template>
          <Elements>
            <Photo PhotoNumber="1" Left="50" Top="100" Width="300" Height="200" Rotation="0"/>
            ...
          </Elements>
        </Template>
        """
        boxes = []
        
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Verschiedene XML-Strukturen unterstützen
            # Variante 1: <Template><Elements><Photo>
            elements = root.find("Elements")
            if elements is None:
                # Variante 2: Direkt <Photo> unter Root
                elements = root
            
            for photo in elements.findall("Photo"):
                try:
                    # Attribute lesen
                    x = int(float(photo.attrib.get("Left", photo.attrib.get("X", "0"))))
                    y = int(float(photo.attrib.get("Top", photo.attrib.get("Y", "0"))))
                    w = int(float(photo.attrib.get("Width", "300")))
                    h = int(float(photo.attrib.get("Height", "200")))
                    angle = float(photo.attrib.get("Rotation", photo.attrib.get("Angle", "0")))
                    number = int(photo.attrib.get("PhotoNumber", photo.attrib.get("Number", str(len(boxes) + 1))))
                    
                    # Box erstellen (x1, y1, x2, y2)
                    boxes.append({
                        "box": (x, y, x + w - 1, y + h - 1),
                        "angle": angle,
                        "number": number
                    })
                    
                except (ValueError, KeyError) as e:
                    logger.warning(f"Fehler beim Parsen eines Photo-Elements: {e}")
            
            # Nach PhotoNumber sortieren
            boxes.sort(key=lambda x: x.get("number", 0))
            
            logger.debug(f"XML geparst: {len(boxes)} Photo-Elemente gefunden")
            
        except ET.ParseError as e:
            logger.error(f"XML Parse-Fehler: {e}")
        except Exception as e:
            logger.error(f"Fehler beim Parsen der XML: {e}")
        
        return boxes
    
    @staticmethod
    def get_template_info(path: str) -> Optional[Dict]:
        """Gibt Informationen über ein Template zurück ohne es vollständig zu laden"""
        if not os.path.exists(path) or not path.lower().endswith(".zip"):
            return None
        
        info = {
            "path": path,
            "filename": os.path.basename(path),
            "size_bytes": os.path.getsize(path),
            "has_png": False,
            "has_xml": False,
            "photo_count": 0
        }
        
        try:
            with zipfile.ZipFile(path, "r") as zf:
                for name in zf.namelist():
                    lower = name.lower()
                    if lower.endswith(".png"):
                        info["has_png"] = True
                    elif lower.endswith(".xml"):
                        info["has_xml"] = True
                        
                        # XML parsen für Foto-Anzahl
                        try:
                            with zf.open(name) as f:
                                tree = ET.parse(f)
                                root = tree.getroot()
                                elements = root.find("Elements") or root
                                info["photo_count"] = len(elements.findall("Photo"))
                        except:
                            pass
        except:
            pass
        
        return info
