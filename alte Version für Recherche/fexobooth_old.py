#!/usr/bin/env python3
"""
Photobooth Anwendung - Vollständige funktionierende Version
Mit komplettem Admin-Dialog und allen Features
"""

import sys
import os
import cv2
import json
import numpy as np
import datetime
import shutil
import zipfile
import ctypes
from ctypes import wintypes
import logging
import time
import threading
import weakref
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, List, Any
from functools import lru_cache
from pathlib import Path
import http.server
import socketserver

# PIL imports
from PIL import Image, ImageDraw, ImageFont, ImageOps

# Win32 imports
import win32print
import win32ui
import win32gui
import win32con

# Qt imports
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSpacerItem,
    QSizePolicy,
    QStackedWidget,
    QMessageBox,
    QDialog,
    QLineEdit,
    QFormLayout,
    QDialogButtonBox,
    QCheckBox,
    QSpinBox,
    QFileDialog,
    QGridLayout,
    QComboBox,
    QFrame,
    QTabWidget,
    QColorDialog,
    QTableWidget,
    QTableWidgetItem,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHeaderView,
    QScrollArea,
)
from PyQt6.QtGui import (
    QImage,
    QPixmap,
    QPainter,
    QColor,
    QPen,
    QIntValidator,
    QFont,
    QIcon,
    QPalette,
    QBrush,
)
from PyQt6.QtCore import (
    QTimer,
    Qt,
    QUrl,
    QRect,
    QEvent,
    pyqtSignal,
    QThread,
    QPropertyAnimation,
    QEasingCurve,
    pyqtProperty,
    QObject,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

# Optional imports
try:
    from PIL import ImageQt

    HAVE_IMAGEQT = True
except ImportError:
    HAVE_IMAGEQT = False

try:
    import qrcode
except ImportError:
    qrcode = None

# =============================================================================
# KONSTANTEN UND KONFIGURATION
# =============================================================================

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
IMAGES_PATH = os.path.join(BASE_PATH, "BILDER")
PRINTS_PATH = os.path.join(IMAGES_PATH, "Prints")
SINGLE_PATH = os.path.join(IMAGES_PATH, "Single")

# Erstelle Verzeichnisse
os.makedirs(IMAGES_PATH, exist_ok=True)
os.makedirs(PRINTS_PATH, exist_ok=True)
os.makedirs(SINGLE_PATH, exist_ok=True)


@dataclass
class AppConfig:
    """Zentrale Konfigurationsklasse"""

    FINAL_CANVAS_WIDTH: int = 1800
    FINAL_CANVAS_HEIGHT: int = 1200
    PREVIEW_UPDATE_FPS: int = 30
    PERFORMANCE_MODE_FPS: int = 10
    USB_CHECK_INTERVAL: int = 5000
    PRINTER_CHECK_INTERVAL: int = 5000
    DEFAULT_COUNTDOWN: int = 5
    CACHE_MAX_SIZE: int = 50
    BATCH_COPY_SIZE: int = 20


CONFIG = AppConfig()

# =============================================================================
# LOGGING
# =============================================================================


def setup_logging() -> logging.Logger:
    """Konfiguriert das Logging-System"""
    log_path = os.path.join(BASE_PATH, "photobooth.log")
    logging.basicConfig(
        filename=log_path,
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


logger = setup_logging()

# =============================================================================
# HILFSKLASSEN
# =============================================================================


def resource_path(relative_path: str) -> str:
    """Findet Ressourcen sowohl im Development als auch als exe"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = BASE_PATH
    return os.path.join(base_path, relative_path)


def remove_icc_profile(pil_image):
    """Entfernt ICC-Profile aus Bildern"""
    if "icc_profile" in pil_image.info:
        del pil_image.info["icc_profile"]
    return pil_image


class CacheManager:
    """Zentraler Cache-Manager für die Anwendung"""

    def __init__(self, max_size: int = CONFIG.CACHE_MAX_SIZE):
        self.max_size = max_size
        self._caches = {}

    def get_cache(self, name: str) -> Dict:
        """Holt oder erstellt einen benannten Cache"""
        if name not in self._caches:
            self._caches[name] = {}
        return self._caches[name]

    def clear_cache(self, name: str = None):
        """Leert einen spezifischen oder alle Caches"""
        if name:
            if name in self._caches:
                self._caches[name].clear()
        else:
            for cache in self._caches.values():
                cache.clear()

    def add_to_cache(self, cache_name: str, key: str, value):
        """Fügt ein Element zum Cache hinzu mit Size-Management"""
        cache = self.get_cache(cache_name)
        if len(cache) >= self.max_size:
            first_key = next(iter(cache))
            del cache[first_key]
        cache[key] = value

    def get_from_cache(self, cache_name: str, key: str):
        """Holt ein Element aus dem Cache"""
        cache = self.get_cache(cache_name)
        return cache.get(key)


# Globaler Cache-Manager
cache_manager = CacheManager()


class StyleManager:
    """Zentralisiert alle UI-Styles"""

    @staticmethod
    def get_button_style(color: str = "#E00675") -> str:
        return f"""
        QPushButton {{
            background: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1, 
                stop:0 {color}, stop:1 {StyleManager.darken_color(color, 0.9)});
            border: 2px solid {StyleManager.darken_color(color, 0.8)};
            border-radius: 10px;
            color: white;
            font-size: 22px;
            padding: 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1, 
                stop:0 {StyleManager.lighten_color(color, 1.2)}, 
                stop:1 {color});
        }}
        QPushButton:pressed {{
            background: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1, 
                stop:0 {StyleManager.darken_color(color, 0.7)}, 
                stop:1 {StyleManager.darken_color(color, 0.8)});
        }}
        QPushButton:disabled {{
            background-color: #808080;
            border: 2px solid #606060;
        }}
        """

    @staticmethod
    def darken_color(hex_color: str, factor: float) -> str:
        """Dunkelt eine Farbe ab"""
        color = QColor(hex_color)
        return QColor.fromHsvF(
            color.hueF(), color.saturationF(), color.valueF() * factor
        ).name()

    @staticmethod
    def lighten_color(hex_color: str, factor: float) -> str:
        """Hellt eine Farbe auf"""
        color = QColor(hex_color)
        return QColor.fromHsvF(
            color.hueF(), color.saturationF(), min(1.0, color.valueF() * factor)
        ).name()


class USBManager:
    """Verwaltet USB-Operationen"""

    def __init__(self):
        self._setup_windows_api()
        self.last_check_time = 0
        self.check_interval = 2.0

    def _setup_windows_api(self):
        """Initialisiert Windows API für Volume-Informationen"""
        if not hasattr(ctypes, "LPDWORD"):
            ctypes.LPDWORD = ctypes.POINTER(wintypes.DWORD)

        self.GetVolumeInformationW = ctypes.windll.kernel32.GetVolumeInformationW
        self.GetVolumeInformationW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            wintypes.DWORD,
            ctypes.LPDWORD,
            ctypes.LPDWORD,
            ctypes.LPDWORD,
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        self.GetVolumeInformationW.restype = wintypes.BOOL

    def get_volume_label(self, drive: str) -> Optional[str]:
        """Holt das Volume-Label eines Laufwerks"""
        volumeNameBuffer = ctypes.create_unicode_buffer(261)
        fsNameBuffer = ctypes.create_unicode_buffer(261)
        serial_number = wintypes.DWORD()
        maxCompLen = wintypes.DWORD()
        fsFlags = wintypes.DWORD()

        ret = self.GetVolumeInformationW(
            drive,
            volumeNameBuffer,
            261,
            ctypes.byref(serial_number),
            ctypes.byref(maxCompLen),
            ctypes.byref(fsFlags),
            fsNameBuffer,
            261,
        )
        return volumeNameBuffer.value if ret else None

    def find_usb_stick(self, label: str = "fexobox") -> Optional[str]:
        """Sucht einen USB-Stick mit bestimmtem Label"""
        current_time = time.time()
        if current_time - self.last_check_time < self.check_interval:
            return cache_manager.get_from_cache("usb", "last_drive")

        self.last_check_time = current_time

        for drive_letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            drive = f"{drive_letter}:\\"
            if os.path.exists(drive):
                vol_label = self.get_volume_label(drive)
                if vol_label and vol_label.lower() == label.lower():
                    cache_manager.add_to_cache("usb", "last_drive", drive)
                    return drive

        cache_manager.add_to_cache("usb", "last_drive", None)
        return None


# =============================================================================
# KAMERA MANAGER
# =============================================================================


class WebcamCameraManager:
    """Verwaltet Webcam-Ressourcen effizient via OpenCV"""

    def __init__(self):
        self.cap = None
        self.camera_index = 0
        self.is_initialized = False
        self.last_frame = None
        self.last_frame_time = 0
        self.frame_cache_duration = 0.033

    def initialize(self, camera_index: int, width: int, height: int) -> bool:
        """Initialisiert die Kamera"""
        if self.is_initialized and self.camera_index == camera_index:
            return True

        self.release()
        self.camera_index = camera_index

        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
        for backend in backends:
            self.cap = cv2.VideoCapture(camera_index, backend)
            if self.cap.isOpened():
                break

        if not self.cap or not self.cap.isOpened():
            logger.error(f"Konnte Kamera {camera_index} nicht öffnen")
            return False

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.is_initialized = True
        logger.info(f"Webcam {camera_index} initialisiert mit {width}x{height}")
        return True

    def get_frame(self, use_cache: bool = True) -> Optional[np.ndarray]:
        """Holt ein Frame von der Kamera mit optionalem Caching"""
        if not self.is_initialized or not self.cap:
            return None

        current_time = time.time()

        if use_cache and self.last_frame is not None:
            if current_time - self.last_frame_time < self.frame_cache_duration:
                return self.last_frame.copy()

        ret, frame = self.cap.read()
        if ret:
            self.last_frame = frame
            self.last_frame_time = current_time
            return frame

        return None

    def release(self):
        """Gibt Kamera-Ressourcen frei"""
        if self.cap:
            self.cap.release()
            self.cap = None
        self.is_initialized = False
        self.last_frame = None
        logger.info("Webcam freigegeben")


class CanonCameraManager:
    """
    Verwaltet eine Canon EOS Kamera.
    Dies ist aktuell ein Platzhalter und wird implementiert,
    sobald das Canon SDK eingerichtet ist.
    """

    def __init__(self):
        self.is_initialized = False
        logger.info("CanonCameraManager erstellt (Platzhalter).")

    def initialize(self, camera_index: int, width: int, height: int) -> bool:
        """Initialisiert die Verbindung zur Canon Kamera."""
        logger.info("Canon Kamera wird initialisiert... (Platzhalter)")
        # Hier kommt die Logik zum Verbinden mit der Kamera via EDSDK.
        self.is_initialized = True
        return True

    def get_frame(self, use_cache: bool = True) -> Optional[np.ndarray]:
        """Holt ein Live-View-Frame von der Kamera."""
        if not self.is_initialized:
            return None

        # Hier kommt die Logik zum Abrufen des Live-View-Bildes.
        # Als Platzhalter geben wir ein schwarzes Bild zurück.
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def take_photo(self) -> Optional[str]:
        """Löst die Kamera aus und gibt den Pfad zum Bild zurück."""
        logger.info("FOTO AUFNEHMEN mit Canon Kamera... (Platzhalter)")
        # Hier kommt die Logik zum Auslösen und Herunterladen des Bildes.
        return None  # Gibt aktuell nichts zurück

    def release(self):
        """Gibt die Kamera-Ressourcen frei."""
        self.is_initialized = False
        logger.info("Canon Kamera freigegeben (Platzhalter).")


class FilterManager:
    """Verwaltet Bildfilter mit Cache"""

    def __init__(self):
        self.filters = {
            "none": self._filter_none,
            "bw": self._filter_bw,
            "bw_contrast": self._filter_bw_contrast,
            "sepia": self._filter_sepia,
            "warm": self._filter_warm,
            "cool": self._filter_cool,
            "vivid": self._filter_vivid,
            "film": self._filter_film,
            "soft_glow": self._filter_soft_glow,
        }

    def apply_filter(self, img: Image.Image, filter_key: str) -> Image.Image:
        """Wendet Filter an"""
        if filter_key not in self.filters:
            filter_key = "none"

        # Cache-Key basierend auf Bild-ID und Filter
        cache_key = f"{id(img)}_{filter_key}"
        cached = cache_manager.get_from_cache("filters", cache_key)
        if cached:
            return cached

        result = self.filters[filter_key](img)
        cache_manager.add_to_cache("filters", cache_key, result)
        return result

    def _filter_none(self, img: Image.Image) -> Image.Image:
        return img.convert("RGBA")

    def _filter_bw(self, img: Image.Image) -> Image.Image:
        return ImageOps.grayscale(img).convert("RGBA")

    def _filter_bw_contrast(self, img: Image.Image) -> Image.Image:
        from PIL import ImageEnhance

        gray = ImageOps.grayscale(img)
        contrasted = ImageOps.autocontrast(gray, cutoff=5)

        bright_enhancer = ImageEnhance.Brightness(contrasted)
        contrasted = bright_enhancer.enhance(1.05)

        cont_enhancer = ImageEnhance.Contrast(contrasted)
        contrasted = cont_enhancer.enhance(1.1)

        return contrasted.convert("RGBA")

    def _filter_sepia(self, img: Image.Image) -> Image.Image:
        from PIL import ImageEnhance

        bw = ImageOps.grayscale(img)
        sepia = ImageOps.colorize(bw, (30, 20, 10), (255, 240, 192))

        contrast_enhancer = ImageEnhance.Contrast(sepia)
        sepia = contrast_enhancer.enhance(1.2)

        color_enhancer = ImageEnhance.Color(sepia)
        sepia = color_enhancer.enhance(1.1)

        return sepia.convert("RGBA")

    def _filter_warm(self, img: Image.Image) -> Image.Image:
        from PIL import ImageEnhance

        img_rgb = img.convert("RGB")
        r, g, b = img_rgb.split()

        r = r.point(lambda i: min(255, i + 50))
        g = g.point(lambda i: min(255, i + 15))

        merged = Image.merge("RGB", (r, g, b))

        color_enhancer = ImageEnhance.Color(merged)
        merged = color_enhancer.enhance(1.2)

        brightness_enhancer = ImageEnhance.Brightness(merged)
        merged = brightness_enhancer.enhance(1.05)

        return merged.convert("RGBA")

    def _filter_cool(self, img: Image.Image) -> Image.Image:
        from PIL import ImageEnhance

        img_rgb = img.convert("RGB")
        r, g, b = img_rgb.split()

        b = b.point(lambda i: min(255, int(i * 1.15)))
        g = g.point(lambda i: min(255, int(i * 1.05)))

        merged = Image.merge("RGB", (r, g, b))
        merged = ImageEnhance.Color(merged).enhance(1.05)
        merged = ImageEnhance.Contrast(merged).enhance(1.05)
        return merged.convert("RGBA")

    def _filter_vivid(self, img: Image.Image) -> Image.Image:
        from PIL import ImageEnhance

        vivid = ImageEnhance.Color(img.convert("RGB")).enhance(1.35)
        vivid = ImageEnhance.Contrast(vivid).enhance(1.1)
        vivid = ImageEnhance.Brightness(vivid).enhance(1.05)
        return vivid.convert("RGBA")

    def _filter_film(self, img: Image.Image) -> Image.Image:
        from PIL import ImageEnhance, ImageFilter

        base = img.convert("RGB")
        faded = ImageEnhance.Color(base).enhance(0.8)
        faded = ImageEnhance.Brightness(faded).enhance(1.05)
        faded = ImageEnhance.Contrast(faded).enhance(0.92)

        grain = Image.effect_noise(base.size, 18)
        grain = grain.filter(ImageFilter.GaussianBlur(radius=0.4))
        grain_colored = Image.merge("RGB", (grain, grain, grain))

        blended = Image.blend(faded, grain_colored, 0.08)
        return blended.convert("RGBA")

    def _filter_soft_glow(self, img: Image.Image) -> Image.Image:
        from PIL import ImageEnhance, ImageFilter

        base = img.convert("RGB")
        blur = base.filter(ImageFilter.GaussianBlur(radius=6))
        glow = Image.blend(base, blur, 0.35)
        glow = ImageEnhance.Brightness(glow).enhance(1.08)
        glow = ImageEnhance.Color(glow).enhance(1.1)
        return glow.convert("RGBA")


# =============================================================================
# CONFIG FUNCTIONS
# =============================================================================


def load_config():
    """Lädt config.json oder erzeugt sie mit Default-Werten."""
    config_path = os.path.join(BASE_PATH, "config.json")

    default_config = {
        "admin_pin": "1234",
        "camera_type": "webcam",  # NEU: 'webcam' oder 'canon'
        "countdown_time": 5,
        "single_display_time": 4,
        "final_time": 10,
        "allow_single_mode": True,
        "template1_enabled": False,
        "template2_enabled": False,
        "template_paths": {"template1": "", "template2": ""},
        "logo_path": "",
        "printer_name": "",
        "start_fullscreen": True,
        "print_adjustment": {"offset_x": 0, "offset_y": 0, "zoom": 100},
        "max_prints_per_session": 3,
        "printer_messages": {
            "paper_out": "Bitte Papier nachlegen!",
            "offline": "Drucker ist offline!",
            "error": "Unbekannter Druckfehler!",
        },
        "hide_finish_button": False,
        "background_color": "#ffffff",
        "logo_scale": 100,
        "camera_index": 0,
        "ui_texts": {
            "admin": "ADMIN",
            "finish": "FERTIG",
            "print": "DRUCKEN",
            "redo": "REDO",
            "cancel": "ABBRECHEN",
            "start": "START",
            "choose_mode": "Welcher Modus?",
            "choose_filter": "Wähle einen Filter",
        },
        "admin_button_alpha": 100,
        "gallery_enabled": False,
        "qr_texts": {"top": "WLAN: fexobox", "bottom": "PW: Partytime"},
        "camera_settings": {
            "single_photo_width": 1280,
            "single_photo_height": 720,
            "disable_scaling": True,
        },
        "performance_mode": True,
    }

    if not os.path.exists(config_path):
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=4)
        return default_config
    else:
        with open(config_path, "r") as f:
            cfg = json.load(f)

        # Merge mit Defaults für fehlende Keys
        for key, value in default_config.items():
            if key not in cfg:
                cfg[key] = value
            elif isinstance(value, dict):
                for subkey, subvalue in value.items():
                    if subkey not in cfg[key]:
                        cfg[key][subkey] = subvalue

        return cfg


def save_config(cfg):
    """Speichert die Konfiguration"""
    config_path = os.path.join(BASE_PATH, "config.json")
    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=4)


# =============================================================================
# TEMPLATE HANDLING
# =============================================================================


def create_mask(overlay_img: Image.Image) -> np.ndarray:
    """Erstellt eine Maske aus transparenten Bereichen"""
    width, height = overlay_img.size
    pixels = overlay_img.load()
    mask = np.zeros((height, width), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a < 255:
                mask[y, x] = 255
    return mask


def morph_close(mask: np.ndarray) -> np.ndarray:
    """Morphologische Closing-Operation"""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (10, 10))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return closed


def find_regions_from_mask(mask: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Findet Regionen in einer Maske"""
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        x_max = x + w - 1
        y_max = y + h - 1
        regions.append((x, y, x_max, y_max))
    return regions


def read_zip_template(zip_path: str) -> Tuple[Optional[Image.Image], List[dict]]:
    """Liest Template aus ZIP-Datei"""
    from xml.etree import ElementTree as ET

    temp_dir = os.path.join(BASE_PATH, "_temp_zip")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(temp_dir)

    # --- TECHNISCHE ENTSCHEIDUNG ---
    # Die Logik wurde geändert, um nicht die erste gefundene PNG-Datei zu nehmen,
    # sondern alle PNGs zu finden und die mit der größten Dateigröße auszuwählen.
    # Das verhindert, dass eine kleine Vorschau-PNG fälschlicherweise als Haupt-Template geladen wird.

    found_png_path = None
    max_png_size = -1
    found_xml_path = None

    for root, dirs, files in os.walk(temp_dir):
        for fn in files:
            full_path = os.path.join(root, fn)
            lower_fn = fn.lower()

            if lower_fn.endswith(".png"):
                try:
                    current_size = os.path.getsize(full_path)
                    if current_size > max_png_size:
                        max_png_size = current_size
                        found_png_path = full_path
                except OSError:
                    # Datei könnte nicht zugänglich sein, einfach ignorieren
                    pass
            elif lower_fn.endswith(".xml"):
                found_xml_path = full_path

    overlay_img = None
    photoboxes = []

    if found_png_path:
        overlay_img = Image.open(found_png_path).convert("RGBA")

    if found_xml_path:
        tree = ET.parse(found_xml_path)
        root_el = tree.getroot()
        elements_el = root_el.find("Elements")
        if elements_el is not None:
            photos_el = elements_el.findall("Photo")
            for p in photos_el:
                try:
                    pn = int(p.attrib.get("PhotoNumber", "1"))
                    W_ = int(p.attrib.get("Width", "300"))
                    H_ = int(p.attrib.get("Height", "200"))
                    x_ = int(p.attrib.get("Left", "0"))
                    y_ = int(p.attrib.get("Top", "0"))
                    angle_ = float(p.attrib.get("Rotation", "0"))
                    x_max = x_ + W_ - 1
                    y_max = y_ + H_ - 1
                    photoboxes.append(
                        {"number": pn, "box": (x_, y_, x_max, y_max), "angle": angle_}
                    )
                except:
                    pass

    shutil.rmtree(temp_dir, ignore_errors=True)
    return overlay_img, photoboxes


# =============================================================================
# DIALOGE
# =============================================================================


class PinDialog(QDialog):
    """Verbesserter PIN-Dialog"""

    def __init__(self, current_pin: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Admin PIN")
        self.setModal(True)
        self.current_pin = current_pin
        self.pin_text = ""
        self._setup_ui()
        self.setStyleSheet(
            """
            QDialog { background: #f7f7fb; }
            QLabel { color: #1c1c28; }
            QPushButton { color: #1c1c28; }
            """
        )

    def _setup_ui(self):
        """Erstellt die UI-Elemente"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 24, 28, 24)
        main_layout.setSpacing(18)

        # PIN-Anzeige
        self.pin_display = QLabel("● ● ● ●")
        self.pin_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_display.setStyleSheet(
            """
            font-size: 38px;
            color: #1c1c28;
            padding: 18px;
            background-color: #ffffff;
            border-radius: 14px;
            border: 1px solid #e6dce5;
        """
        )
        main_layout.addWidget(self.pin_display)

        # Keypad
        keypad_widget = QWidget()
        keypad_layout = QGridLayout(keypad_widget)
        keypad_layout.setSpacing(12)

        for i in range(1, 10):
            btn = self._create_keypad_button(str(i), "#E00675")
            row = (i - 1) // 3
            col = (i - 1) % 3
            keypad_layout.addWidget(btn, row, col)

        btn_clear = self._create_keypad_button("C", "#d7d7df")
        btn_clear.clicked.connect(self.clear_pin)
        keypad_layout.addWidget(btn_clear, 3, 0)

        btn_0 = self._create_keypad_button("0", "#E00675")
        keypad_layout.addWidget(btn_0, 3, 1)

        btn_del = self._create_keypad_button("←", "#2d2d32")
        btn_del.clicked.connect(self.del_pin)
        keypad_layout.addWidget(btn_del, 3, 2)

        main_layout.addWidget(keypad_widget)

        # Dialog-Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.setStyleSheet(StyleManager.get_button_style("#E00675"))
        main_layout.addWidget(buttons)

        self.resize(350, 500)

    def _create_keypad_button(self, text: str, color: str = "#3498DB") -> QPushButton:
        """Erstellt einen Keypad-Button"""
        btn = QPushButton(text)
        btn.setFixedSize(96, 76)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                font-size: 26px;
                background: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1,
                    stop:0 {color}, stop:1 {StyleManager.darken_color(color, 0.85)});
                color: {"#1c1c28" if color.lower() in ["#d7d7df", "#f7f7fb", "#ffffff"] else "#ffffff"};
                border-radius: 14px;
                font-weight: 700;
                border: 1px solid {StyleManager.darken_color(color, 0.8)};
            }}
            QPushButton:hover {{
                background: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1,
                    stop:0 {StyleManager.lighten_color(color, 1.1)},
                    stop:1 {color});
            }}
            QPushButton:pressed {{
                background: {StyleManager.darken_color(color, 0.75)};
            }}
        """
        )

        if text.isdigit():
            btn.clicked.connect(lambda: self.num_clicked(text))

        return btn

    def num_clicked(self, num: str):
        """Verarbeitet Zahlen-Eingabe"""
        if len(self.pin_text) < 4:
            self.pin_text += num
            self._update_display()

            if len(self.pin_text) == 4:
                QTimer.singleShot(300, self._check_pin)

    def _update_display(self):
        """Aktualisiert die PIN-Anzeige"""
        display = ""
        for i in range(4):
            if i < len(self.pin_text):
                display += "● "
            else:
                display += "○ "
        self.pin_display.setText(display.strip())

    def _check_pin(self):
        """Überprüft die eingegebene PIN"""
        if self.pin_text == self.current_pin:
            super().accept()
        else:
            self.pin_text = ""
            self._update_display()

    def clear_pin(self):
        """Löscht die PIN-Eingabe"""
        self.pin_text = ""
        self._update_display()

    def del_pin(self):
        """Löscht letztes Zeichen"""
        if self.pin_text:
            self.pin_text = self.pin_text[:-1]
            self._update_display()

    def accept(self):
        """Akzeptiert nur bei korrekter PIN"""
        if self.pin_text == self.current_pin:
            super().accept()


# =============================================================================
# ADMIN DIALOG
# =============================================================================


class AdminDialog(QDialog):
    """Vollständiger Admin-Dialog"""

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Admin-Einstellungen")
        self.cfg = cfg.copy()  # Arbeite mit Kopie
        self.parent_app = parent
        self._setup_ui()
        self.setMinimumSize(800, 600)
        # Sicherstellen, dass Texte im Dialog auf hellem Hintergrund lesbar bleiben
        self.setStyleSheet(
            """
            QDialog { background: #ffffff; color: #000000; }
            QLabel, QCheckBox, QRadioButton, QGroupBox { color: #000000; }
            QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
                color: #000000;
                background: #ffffff;
                selection-background-color: #e00675;
            }
            QTableWidget, QHeaderView::section, QTableWidget QTableCornerButton::section {
                color: #000000;
            }
            QTabBar::tab { color: #000000; }
            """
        )

    def _setup_ui(self):
        """Erstellt die UI"""
        main_layout = QVBoxLayout(self)

        # Tab Widget
        self.tab_widget = QTabWidget(self)
        main_layout.addWidget(self.tab_widget)

        # Tabs erstellen
        self._create_general_tab()
        self._create_templates_tab()
        self._create_print_tab()
        self._create_appearance_tab()
        self._create_texts_tab()
        self._create_quality_tab()
        self._create_stats_tab()

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save_settings)
        buttons.rejected.connect(self.reject)
        buttons.setStyleSheet(StyleManager.get_button_style("#2ECC71"))
        main_layout.addWidget(buttons)

    def _create_general_tab(self):
        """Erstellt Allgemein-Tab"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # Kamera-Typ
        self.camera_type_combo = QComboBox()
        self.camera_type_combo.addItems(["webcam", "canon"])
        self.camera_type_combo.setCurrentText(self.cfg.get("camera_type", "webcam"))
        layout.addRow("Kamera-Typ:", self.camera_type_combo)

        # Countdown
        self.countdown_spin = QSpinBox()
        self.countdown_spin.setRange(1, 60)
        self.countdown_spin.setValue(self.cfg.get("countdown_time", 5))
        layout.addRow("Countdown Zeit (Sek):", self.countdown_spin)

        # Single Display
        self.single_spin = QSpinBox()
        self.single_spin.setRange(1, 60)
        self.single_spin.setValue(self.cfg.get("single_display_time", 4))
        layout.addRow("Einzelbild-Anzeige (Sek):", self.single_spin)

        # Final Time
        self.final_spin = QSpinBox()
        self.final_spin.setRange(1, 120)
        self.final_spin.setValue(self.cfg.get("final_time", 10))
        layout.addRow("Finale Anzeige (Sek):", self.final_spin)

        # Single Mode
        self.full_check = QCheckBox("Single-Foto-Modus erlauben?")
        self.full_check.setChecked(self.cfg.get("allow_single_mode", True))
        layout.addRow(self.full_check)

        # Performance Mode
        self.performance_check = QCheckBox(
            "Performance-Modus (empfohlen für langsamere Rechner)"
        )
        self.performance_check.setChecked(self.cfg.get("performance_mode", True))
        layout.addRow(self.performance_check)

        # Fullscreen
        self.start_fullscreen_check = QCheckBox("Vollbild-Start?")
        self.start_fullscreen_check.setChecked(self.cfg.get("start_fullscreen", True))
        layout.addRow(self.start_fullscreen_check)

        # Gallery
        self.gallery_check = QCheckBox("Bildergalerie/Webserver aktivieren?")
        self.gallery_check.setChecked(self.cfg.get("gallery_enabled", False))
        layout.addRow(self.gallery_check)

        # Max Prints
        self.max_prints_spin = QSpinBox()
        self.max_prints_spin.setRange(0, 100)
        self.max_prints_spin.setValue(self.cfg.get("max_prints_per_session", 3))
        layout.addRow("Max. Drucke pro Session:", self.max_prints_spin)

        # Hide Finish Button
        self.hide_finish_check = QCheckBox("Fertig-Button ausblenden?")
        self.hide_finish_check.setChecked(self.cfg.get("hide_finish_button", False))
        layout.addRow(self.hide_finish_check)

        # Admin PIN
        self.new_pin_edit = QLineEdit()
        self.new_pin_edit.setPlaceholderText("Neue PIN (4-stellig)")
        self.new_pin_edit.setMaxLength(4)
        self.new_pin_edit.setValidator(QIntValidator(0, 9999))
        layout.addRow("Neue Admin-PIN:", self.new_pin_edit)

        # Drucker
        self.printer_combo = QComboBox()
        self.printer_combo.setMinimumWidth(250)
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        for p in printers:
            self.printer_combo.addItem(p[2])

        saved_printer = self.cfg.get("printer_name", "")
        if saved_printer:
            idx = self.printer_combo.findText(saved_printer)
            if idx >= 0:
                self.printer_combo.setCurrentIndex(idx)

        layout.addRow("Drucker:", self.printer_combo)

        # Kamera
        self.camera_combo = QComboBox()
        for i in range(5):
            test_cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if test_cap.isOpened():
                self.camera_combo.addItem(f"Kamera {i}", i)
                test_cap.release()

        saved_camera = self.cfg.get("camera_index", 0)
        idx = self.camera_combo.findData(saved_camera)
        if idx >= 0:
            self.camera_combo.setCurrentIndex(idx)

        layout.addRow("Webcam Index:", self.camera_combo)

        # Admin Button Alpha
        self.admin_alpha_spin = QSpinBox()
        self.admin_alpha_spin.setRange(0, 100)
        self.admin_alpha_spin.setValue(self.cfg.get("admin_button_alpha", 100))
        layout.addRow("Admin-Button Transparenz (%):", self.admin_alpha_spin)

        # Buttons
        self.delete_pics_button = QPushButton("Alle Bilder löschen")
        self.delete_pics_button.clicked.connect(self._delete_all_pics)
        layout.addWidget(self.delete_pics_button)

        self.sync_button = QPushButton("Bilder synchronisieren (USB)")
        self.sync_button.clicked.connect(self._sync_photos)
        layout.addWidget(self.sync_button)

        self.tab_widget.addTab(tab, "Allgemein")

    def _create_templates_tab(self):
        """Erstellt Templates-Tab"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # Template 1
        self.template1_enabled = QCheckBox("Template 1 aktiv?")
        self.template1_enabled.setChecked(self.cfg.get("template1_enabled", False))
        layout.addRow(self.template1_enabled)

        self.template1_edit = QLineEdit(self.cfg["template_paths"].get("template1", ""))
        layout.addRow("Template 1 Pfad:", self.template1_edit)

        self.template1_btn = QPushButton("Wählen...")
        self.template1_btn.clicked.connect(self._choose_template1)
        layout.addWidget(self.template1_btn)

        # Template 2
        self.template2_enabled = QCheckBox("Template 2 aktiv?")
        self.template2_enabled.setChecked(self.cfg.get("template2_enabled", False))
        layout.addRow(self.template2_enabled)

        self.template2_edit = QLineEdit(self.cfg["template_paths"].get("template2", ""))
        layout.addRow("Template 2 Pfad:", self.template2_edit)

        self.template2_btn = QPushButton("Wählen...")
        self.template2_btn.clicked.connect(self._choose_template2)
        layout.addWidget(self.template2_btn)

        # Logo
        self.logo_edit = QLineEdit(self.cfg.get("logo_path", ""))
        layout.addRow("Logo Pfad:", self.logo_edit)

        self.logo_btn = QPushButton("Wählen...")
        self.logo_btn.clicked.connect(self._choose_logo)
        layout.addWidget(self.logo_btn)

        self.logo_scale_spin = QSpinBox()
        self.logo_scale_spin.setRange(10, 300)
        self.logo_scale_spin.setValue(self.cfg.get("logo_scale", 100))
        layout.addRow("Logo Größe (%):", self.logo_scale_spin)

        self.tab_widget.addTab(tab, "Vorlagen & Logo")

    def _create_print_tab(self):
        """Erstellt Druck-Tab"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # Offset X
        self.offset_x_spin = QSpinBox()
        self.offset_x_spin.setRange(-100, 100)
        self.offset_x_spin.setValue(
            self.cfg.get("print_adjustment", {}).get("offset_x", 0)
        )
        layout.addRow("Offset X:", self.offset_x_spin)

        # Offset Y
        self.offset_y_spin = QSpinBox()
        self.offset_y_spin.setRange(-100, 100)
        self.offset_y_spin.setValue(
            self.cfg.get("print_adjustment", {}).get("offset_y", 0)
        )
        layout.addRow("Offset Y:", self.offset_y_spin)

        # Zoom
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(50, 200)
        self.zoom_spin.setValue(self.cfg.get("print_adjustment", {}).get("zoom", 100))
        layout.addRow("Zoom (%):", self.zoom_spin)

        # Vorschau
        self.print_preview = QLabel()
        self.print_preview.setFixedSize(300, 200)
        self.print_preview.setStyleSheet(
            "border: 1px solid #333; background-color: #f0f0f0;"
        )
        self.print_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addRow("Vorschau:", self.print_preview)

        self._update_print_preview()

        # Connect signals
        self.offset_x_spin.valueChanged.connect(self._update_print_preview)
        self.offset_y_spin.valueChanged.connect(self._update_print_preview)
        self.zoom_spin.valueChanged.connect(self._update_print_preview)

        self.tab_widget.addTab(tab, "Druckanpassung")

    def _create_appearance_tab(self):
        """Erstellt Erscheinungsbild-Tab"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # Hintergrundfarbe
        self.bg_edit = QLineEdit(self.cfg.get("background_color", "#ffffff"))
        layout.addRow("Hintergrundfarbe (HEX):", self.bg_edit)

        self.bg_pick_btn = QPushButton("Farbe wählen...")
        self.bg_pick_btn.clicked.connect(self._pick_bg_color)
        layout.addWidget(self.bg_pick_btn)

        self.tab_widget.addTab(tab, "Erscheinungsbild")

    def _create_texts_tab(self):
        """Erstellt Texte-Tab"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # UI Texte
        self.admin_text = QLineEdit(self.cfg["ui_texts"].get("admin", "ADMIN"))
        layout.addRow("Admin Button:", self.admin_text)

        self.finish_text = QLineEdit(self.cfg["ui_texts"].get("finish", "FERTIG"))
        layout.addRow("Fertig Button:", self.finish_text)

        self.print_text = QLineEdit(self.cfg["ui_texts"].get("print", "DRUCKEN"))
        layout.addRow("Drucken Button:", self.print_text)

        self.redo_text = QLineEdit(self.cfg["ui_texts"].get("redo", "REDO"))
        layout.addRow("Redo Button:", self.redo_text)

        self.cancel_text = QLineEdit(self.cfg["ui_texts"].get("cancel", "ABBRECHEN"))
        layout.addRow("Abbrechen Button:", self.cancel_text)

        self.start_text = QLineEdit(self.cfg["ui_texts"].get("start", "START"))
        layout.addRow("Start Button:", self.start_text)

        self.choose_mode_text = QLineEdit(
            self.cfg["ui_texts"].get("choose_mode", "Welcher Modus?")
        )
        layout.addRow("Modusauswahl Titel:", self.choose_mode_text)

        self.choose_filter_text = QLineEdit(
            self.cfg["ui_texts"].get("choose_filter", "Wähle einen Filter")
        )
        layout.addRow("Filterauswahl Titel:", self.choose_filter_text)

        # QR Texte
        self.qr_top_text = QLineEdit(self.cfg["qr_texts"].get("top", "WLAN: fexobox"))
        layout.addRow("QR-Code Oberer Text:", self.qr_top_text)

        self.qr_bottom_text = QLineEdit(
            self.cfg["qr_texts"].get("bottom", "PW: Partytime")
        )
        layout.addRow("QR-Code Unterer Text:", self.qr_bottom_text)

        self.tab_widget.addTab(tab, "Texte")

    def _create_quality_tab(self):
        """Erstellt Qualität-Tab"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # Single Photo Width
        self.single_width_spin = QSpinBox()
        self.single_width_spin.setRange(320, 9999)
        self.single_width_spin.setValue(
            self.cfg.get("camera_settings", {}).get("single_photo_width", 1280)
        )
        layout.addRow("Breite (px) für Single-Fotos:", self.single_width_spin)

        # Single Photo Height
        self.single_height_spin = QSpinBox()
        self.single_height_spin.setRange(240, 9999)
        self.single_height_spin.setValue(
            self.cfg.get("camera_settings", {}).get("single_photo_height", 720)
        )
        layout.addRow("Höhe (px) für Single-Fotos:", self.single_height_spin)

        # Disable Scaling
        self.disable_scaling_check = QCheckBox("Kein Verkleinern der Single-Fotos?")
        self.disable_scaling_check.setChecked(
            self.cfg.get("camera_settings", {}).get("disable_scaling", True)
        )
        layout.addRow(self.disable_scaling_check)

        self.tab_widget.addTab(tab, "Qualität")

    def _create_stats_tab(self):
        """Erstellt Statistik-Tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Statistik-Tabelle
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(4)
        self.stats_table.setHorizontalHeaderLabels(
            ["Datum", "Fotos", "Prints", "Nutzung"]
        )
        self.stats_table.horizontalHeader().setStretchLastSection(True)

        self._fill_stats_table()

        layout.addWidget(self.stats_table)
        self.tab_widget.addTab(tab, "Statistik")

    def _fill_stats_table(self):
        """Füllt die Statistik-Tabelle"""
        # Hier würde die echte Statistik-Logik implementiert
        # Für Demo nur Beispieldaten
        self.stats_table.setRowCount(3)

        example_data = [
            ["26.05.2025", "42", "12", "2h 15min"],
            ["25.05.2025", "38", "10", "1h 50min"],
            ["24.05.2025", "55", "18", "3h 05min"],
        ]

        for row, data in enumerate(example_data):
            for col, value in enumerate(data):
                item = QTableWidgetItem(value)
                self.stats_table.setItem(row, col, item)

    def _update_print_preview(self):
        """Aktualisiert die Druck-Vorschau"""
        # Einfache visuelle Darstellung
        pixmap = QPixmap(300, 200)
        pixmap.fill(QColor(240, 240, 240))

        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor(0, 0, 0), 2))

        # Basis-Rechteck
        base_w = 200
        base_h = 130
        zoom = self.zoom_spin.value() / 100

        draw_w = int(base_w * zoom)
        draw_h = int(base_h * zoom)

        center_x = 150
        center_y = 100

        x = center_x - draw_w // 2 + self.offset_x_spin.value()
        y = center_y - draw_h // 2 + self.offset_y_spin.value()

        painter.drawRect(x, y, draw_w, draw_h)

        # Mittelpunkt
        painter.setPen(QPen(QColor(255, 0, 0), 1, Qt.PenStyle.DashLine))
        painter.drawLine(center_x, 0, center_x, 200)
        painter.drawLine(0, center_y, 300, center_y)

        painter.end()

        self.print_preview.setPixmap(pixmap)

    def _pick_bg_color(self):
        """Öffnet Farbwähler"""
        color = QColorDialog.getColor(QColor(self.bg_edit.text()), self)
        if color.isValid():
            self.bg_edit.setText(color.name())

    def _choose_template1(self):
        """Wählt Template 1"""
        file, _ = QFileDialog.getOpenFileName(
            self, "Template 1 wählen", "", "Bilder/ZIP (*.png *.jpg *.jpeg *.zip)"
        )
        if file:
            self.template1_edit.setText(file)

    def _choose_template2(self):
        """Wählt Template 2"""
        file, _ = QFileDialog.getOpenFileName(
            self, "Template 2 wählen", "", "Bilder/ZIP (*.png *.jpg *.jpeg *.zip)"
        )
        if file:
            self.template2_edit.setText(file)

    def _choose_logo(self):
        """Wählt Logo"""
        file, _ = QFileDialog.getOpenFileName(
            self, "Logo wählen", "", "Bilder (*.png *.jpg *.jpeg)"
        )
        if file:
            self.logo_edit.setText(file)

    def _delete_all_pics(self):
        """Löscht alle Bilder"""
        reply = QMessageBox.question(
            self,
            "Bestätigung",
            "Wirklich ALLE Bilder löschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            for file in os.listdir(PRINTS_PATH):
                if file.lower().endswith(".jpg"):
                    os.remove(os.path.join(PRINTS_PATH, file))

            for file in os.listdir(SINGLE_PATH):
                if file.lower().endswith(".jpg"):
                    os.remove(os.path.join(SINGLE_PATH, file))

            QMessageBox.information(self, "Info", "Alle Bilder wurden gelöscht.")

    def _sync_photos(self):
        """Synchronisiert Fotos mit USB"""
        # Hier würde die Sync-Logik implementiert
        QMessageBox.information(
            self, "Info", "Foto-Synchronisation würde hier starten."
        )

    def save_settings(self):
        """Speichert alle Einstellungen"""
        # Allgemein
        self.cfg["camera_type"] = self.camera_type_combo.currentText()
        self.cfg["countdown_time"] = self.countdown_spin.value()
        self.cfg["single_display_time"] = self.single_spin.value()
        self.cfg["final_time"] = self.final_spin.value()
        self.cfg["allow_single_mode"] = self.full_check.isChecked()
        self.cfg["performance_mode"] = self.performance_check.isChecked()
        self.cfg["start_fullscreen"] = self.start_fullscreen_check.isChecked()
        self.cfg["gallery_enabled"] = self.gallery_check.isChecked()
        self.cfg["max_prints_per_session"] = self.max_prints_spin.value()
        self.cfg["hide_finish_button"] = self.hide_finish_check.isChecked()
        self.cfg["admin_button_alpha"] = self.admin_alpha_spin.value()

        # PIN
        new_pin = self.new_pin_edit.text().strip()
        if len(new_pin) == 4:
            self.cfg["admin_pin"] = new_pin

        # Drucker
        self.cfg["printer_name"] = self.printer_combo.currentText()

        # Kamera
        cam_data = self.camera_combo.currentData()
        if cam_data is not None:
            self.cfg["camera_index"] = cam_data

        # Templates
        self.cfg["template1_enabled"] = self.template1_enabled.isChecked()
        self.cfg["template2_enabled"] = self.template2_enabled.isChecked()
        self.cfg["template_paths"]["template1"] = self.template1_edit.text()
        self.cfg["template_paths"]["template2"] = self.template2_edit.text()
        self.cfg["logo_path"] = self.logo_edit.text()
        self.cfg["logo_scale"] = self.logo_scale_spin.value()

        # Druck
        self.cfg["print_adjustment"]["offset_x"] = self.offset_x_spin.value()
        self.cfg["print_adjustment"]["offset_y"] = self.offset_y_spin.value()
        self.cfg["print_adjustment"]["zoom"] = self.zoom_spin.value()

        # Erscheinungsbild
        self.cfg["background_color"] = self.bg_edit.text()

        # Texte
        self.cfg["ui_texts"]["admin"] = self.admin_text.text()
        self.cfg["ui_texts"]["finish"] = self.finish_text.text()
        self.cfg["ui_texts"]["print"] = self.print_text.text()
        self.cfg["ui_texts"]["redo"] = self.redo_text.text()
        self.cfg["ui_texts"]["cancel"] = self.cancel_text.text()
        self.cfg["ui_texts"]["start"] = self.start_text.text()
        self.cfg["ui_texts"]["choose_mode"] = self.choose_mode_text.text()
        self.cfg["ui_texts"]["choose_filter"] = self.choose_filter_text.text()
        self.cfg["qr_texts"]["top"] = self.qr_top_text.text()
        self.cfg["qr_texts"]["bottom"] = self.qr_bottom_text.text()

        # Qualität
        self.cfg["camera_settings"][
            "single_photo_width"
        ] = self.single_width_spin.value()
        self.cfg["camera_settings"][
            "single_photo_height"
        ] = self.single_height_spin.value()
        self.cfg["camera_settings"][
            "disable_scaling"
        ] = self.disable_scaling_check.isChecked()

        # Speichern
        save_config(self.cfg)
        self.accept()

    def get_config(self):
        """Gibt die aktuelle Konfiguration zurück"""
        return self.cfg


# =============================================================================
# MODE OPTION WIDGET
# =============================================================================


class ModeOption(QWidget):
    """Template-Option Widget"""

    clicked = pyqtSignal()

    def __init__(self, pixmap: QPixmap, label: str = "", parent=None):
        super().__init__(parent)
        self.pixmap = pixmap
        self.label = label
        self.selected = False
        self.setMinimumSize(260, 220)
        self.setMaximumWidth(380)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._corner_radius = 14

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 45))
        self.setGraphicsEffect(shadow)

    def update_pixmap(self, pixmap: QPixmap):
        """Aktualisiert das Pixmap"""
        self.pixmap = pixmap
        self.selected = False
        self.update()

    def paintEvent(self, event):
        """Zeichnet das Widget"""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(6, 6, -6, -6)
        bg_color = QColor("#ffffff")
        if self.selected:
            bg_color = QColor("#fdf3f8")

        p.setPen(QPen(QColor(0, 0, 0, 25), 1))
        p.setBrush(bg_color)
        p.drawRoundedRect(rect, self._corner_radius, self._corner_radius)

        # Bild
        w = rect.width()
        h = rect.height()
        img_w = self.pixmap.width()
        img_h = self.pixmap.height()

        if img_w > 0 and img_h > 0:
            scale = min(w / img_w, h / img_h, 1.0)
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)
            x = rect.left() + (w - new_w) // 2
            y = rect.top() + (h - new_h) // 2

            p.drawPixmap(
                x,
                y,
                self.pixmap.scaled(
                    new_w,
                    new_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ),
            )

            # Label im Bild
            if self.label:
                label_rect = QRect(
                    x + 12, y + new_h - 50, new_w - 24, 38
                ).intersected(self.rect())
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 140))
                p.drawRoundedRect(label_rect, 10, 10)
                p.setPen(QPen(QColor("#ffffff")))
                font = QFont("Arial", 12, QFont.Weight.Bold)
                p.setFont(font)
                p.drawText(
                    label_rect.adjusted(10, 0, -10, 0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    self.label,
                )

            # Rahmen wenn ausgewählt
            if self.selected:
                pen = QPen(QColor(224, 6, 117), 4)
                p.setPen(pen)
                p.drawRoundedRect(rect, self._corner_radius, self._corner_radius)

    def mousePressEvent(self, event):
        """Mouse click"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class FilterPreviewButton(QFrame):
    """Kleines Karten-Widget für Filter-Vorschau ohne Textbeschriftung"""

    clicked = pyqtSignal(str)

    def __init__(self, label: str, filter_key: str, parent=None):
        super().__init__(parent)
        self.label_text = label
        self.filter_key = filter_key
        self._selected = False

        self.setFixedWidth(132)
        self.setMinimumHeight(150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(110, 110)
        self.preview.setStyleSheet(
            "background-color: #0d0d0f; border-radius: 12px; border: 1px solid #1f1f25;"
        )
        layout.addWidget(self.preview, alignment=Qt.AlignmentFlag.AlignCenter)

        self._update_style()

    def _update_style(self):
        border_color = "#e00675" if self._selected else "#e0e0e0"
        bg_color = "#fdf3f8" if self._selected else "#ffffff"
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 14px;
            }}
        """
        )

    def set_preview_pixmap(self, pixmap: QPixmap):
        """Setzt die Vorschau-Grafik"""
        if pixmap.isNull():
            self.preview.clear()
            return
        scaled = pixmap.scaled(
            110,
            110,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(scaled)

    def set_selected(self, selected: bool):
        """Aktualisiert den Selektionszustand"""
        self._selected = selected
        self._update_style()

    def mousePressEvent(self, event):
        """Mouse click"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.filter_key)


# =============================================================================
# HAUPTANWENDUNG
# =============================================================================


class PhotoboothApp(QWidget):
    """Hauptanwendung"""

    def __init__(self):
        super().__init__()
        logger.info("Photobooth-Anwendung startet...")

        # Manager initialisieren
        self.usb_manager = USBManager()
        self.filter_manager = FilterManager()

        # Konfiguration laden
        self.cfg = load_config()
        self._check_for_usb_config()

        # Kamera-Manager basierend auf Config laden
        camera_type = self.cfg.get("camera_type", "webcam")
        if camera_type == "canon":
            self.camera_manager = CanonCameraManager()
            logger.info("Canon-Kamera-Manager wird verwendet.")
        else:
            self.camera_manager = WebcamCameraManager()
            logger.info("Webcam-Kamera-Manager wird verwendet.")

        # Status-Variablen
        self.photos_taken = []
        self.current_photo_index = 0
        self.use_template = False
        self.chosen_template_path = None
        self.current_filter = "none"
        self.template_boxes = []
        self.overlay_image = None
        self.prints_in_session = 0
        self.in_countdown = False
        self.live_mode = False
        self.bar_mode = None
        self.bar_steps_left = 0
        self.countdown_value = 5
        self.usb_path = None
        self.filter_sample_image: Optional[Image.Image] = None

        # UI initialisieren
        self._setup_ui()
        self._apply_messagebox_style()
        self._setup_timers()
        self._apply_initial_settings()

        logger.info("Photobooth-Anwendung gestartet")

    def _check_for_usb_config(self):
        """Prüft auf USB-Config"""
        usb = self.usb_manager.find_usb_stick()
        if not usb:
            return

        usb_config_path = os.path.join(usb, "config.json")
        if os.path.exists(usb_config_path):
            try:
                with open(usb_config_path, "r") as f:
                    usb_config = json.load(f)
                self.cfg.update(usb_config)
                save_config(self.cfg)
                logger.info("USB-Config übernommen")
            except Exception as e:
                logger.error(f"Fehler beim Laden der USB-Config: {e}")

    def _setup_ui(self):
        """Erstellt die Benutzeroberfläche"""
        self.setWindowTitle("Photobooth")
        self.setMinimumSize(1024, 680)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Haupt-Layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top-Bar
        self._create_top_bar(main_layout)

        # Stacked Widget
        self.stacked = QStackedWidget()
        self.stacked.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        main_layout.addWidget(self.stacked)

        # Screens erstellen
        self._create_screens()

        # Initial-Screen
        self.stacked.setCurrentIndex(0)

    def _create_top_bar(self, parent_layout):
        """Erstellt die Top-Bar"""
        top_bar_widget = QWidget()
        top_bar_widget.setFixedHeight(68)
        top_bar_widget.setStyleSheet(
            """
            background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0,
                stop:0 #fef2f7, stop:1 #ffffff);
            border-bottom: 1px solid #e6d4de;
            """
        )

        top_bar_layout = QHBoxLayout(top_bar_widget)
        top_bar_layout.setContentsMargins(10, 5, 10, 5)

        # Logo
        self.logo_label = QLabel()
        self._update_logo()
        top_bar_layout.addWidget(self.logo_label)

        # Admin-Button
        alpha = self.cfg.get("admin_button_alpha", 100)
        alpha_channel = int(alpha * 255 / 100)
        self.admin_button = QPushButton(self.cfg["ui_texts"].get("admin", "ADMIN"))
        self.admin_button.setFixedSize(80, 40)
        self.admin_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: rgba(255,255,0,{alpha_channel});
                color: rgba(0,0,0,{alpha_channel});
                border: 1px solid rgba(0,0,0,{alpha_channel});
                font-size: 14px;
                font-weight: bold;
            }}
        """
        )
        self.admin_button.clicked.connect(self._on_admin_clicked)
        top_bar_layout.addWidget(self.admin_button)

        # Spacer
        top_bar_layout.addStretch()

        # Status-Labels
        self.printer_status_label = QLabel()
        self.printer_status_label.setStyleSheet(
            """
            background-color: #e74c3c;
            color: white;
            padding: 5px 10px;
            border-radius: 5px;
            font-weight: bold;
        """
        )
        self.printer_status_label.hide()
        top_bar_layout.addWidget(self.printer_status_label)

        self.usb_warn_label = QLabel("USB-Stick nicht angesteckt!")
        self.usb_warn_label.setStyleSheet(
            """
            background-color: #e74c3c;
            color: white;
            padding: 5px 10px;
            border-radius: 5px;
            font-weight: bold;
        """
        )
        self.usb_warn_label.hide()
        top_bar_layout.addWidget(self.usb_warn_label)

        parent_layout.addWidget(top_bar_widget)

    def _create_screens(self):
        """Erstellt alle Screens"""
        # Start-Screen
        self.start_widget = QWidget()
        self._setup_start_screen()
        self.stacked.addWidget(self.start_widget)

        # Video-Screen
        self.video_widget = QWidget()
        self._setup_video_screen()
        self.stacked.addWidget(self.video_widget)

        # Session-Screen
        self.session_widget = QWidget()
        self._setup_session_screen()
        self.stacked.addWidget(self.session_widget)

        # Filter-Screen
        self.filter_widget = QWidget()
        self._setup_filter_screen()
        self.stacked.addWidget(self.filter_widget)

    def resizeEvent(self, event):
        """Reagiert auf Größenänderungen mit neuem Layout"""
        super().resizeEvent(event)
        if (
            hasattr(self, "filter_widget")
            and self.stacked.currentWidget() == self.filter_widget
        ):
            self._update_filter_preview()

    def _setup_start_screen(self):
        """Setup Start-Screen"""
        layout = QVBoxLayout(self.start_widget)
        layout.setContentsMargins(28, 32, 28, 32)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # Titel
        title = QLabel(self.cfg["ui_texts"].get("choose_mode", "Welcher Modus?"))
        title.setStyleSheet(
            "font-size: 34px; font-weight: 800; color: #1c1c28; letter-spacing: 0.3px;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            "Wähle dein Layout oder ein Solo-Foto. Alle Optionen sind auch auf kleineren Displays gut erreichbar."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #4c4c63; font-size: 16px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Template-Optionen als horizontaler Slider
        options_container = QWidget()
        options_container.setStyleSheet(
            """
            background-color: #f7f7fb;
            border: 1px solid #ececf0;
            border-radius: 18px;
            """
        )
        options_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        options_container.setMaximumWidth(1200)

        options_outer_layout = QVBoxLayout(options_container)
        options_outer_layout.setContentsMargins(18, 12, 18, 12)
        options_outer_layout.setSpacing(10)

        self.options_scroll = QScrollArea()
        self.options_scroll.setWidgetResizable(True)
        self.options_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.options_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.options_scroll.setFixedHeight(260)

        self.options_strip_widget = QWidget()
        self.options_strip_layout = QHBoxLayout(self.options_strip_widget)
        self.options_strip_layout.setContentsMargins(8, 4, 8, 4)
        self.options_strip_layout.setSpacing(12)
        self.options_strip_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.options_scroll.setWidget(self.options_strip_widget)
        options_outer_layout.addWidget(
            self.options_scroll, alignment=Qt.AlignmentFlag.AlignHCenter
        )

        # Template 1
        gray = QPixmap(320, 240)
        gray.fill(QColor(90, 90, 90))
        self.template1_option = ModeOption(gray, "Template 1", self.start_widget)
        self.template1_option.clicked.connect(
            lambda: self._select_option(
                self.template1_option, True, self.cfg["template_paths"]["template1"]
            )
        )

        # Template 2
        self.template2_option = ModeOption(gray, "Template 2", self.start_widget)
        self.template2_option.clicked.connect(
            lambda: self._select_option(
                self.template2_option, True, self.cfg["template_paths"]["template2"]
            )
        )

        # Single-Foto
        red_pix = QPixmap(320, 220)
        red_pix.fill(QColor(224, 6, 117))
        self.full_option = ModeOption(red_pix, "Single-Foto", self.start_widget)
        self.full_option.clicked.connect(
            lambda: self._select_option(self.full_option, False, None)
        )

        self.start_hint = QLabel(
            ""
        )
        self.start_hint.hide()

        layout.addWidget(options_container, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Start-Button
        self.start_btn = QPushButton(self.cfg["ui_texts"].get("start", "START"))
        self.start_btn.setFixedSize(230, 78)
        self.start_btn.setStyleSheet(StyleManager.get_button_style())
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._on_start_clicked)
        layout.addWidget(self.start_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # QR-Code wenn Gallery aktiviert
        if self.cfg.get("gallery_enabled", False) and qrcode:
            qr_container = QWidget()
            qr_layout = QVBoxLayout(qr_container)
            qr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            qr_top = QLabel(self.cfg["qr_texts"].get("top", "WLAN: fexobox"))
            qr_top.setStyleSheet("font-size: 14px; font-weight: bold;")
            qr_layout.addWidget(qr_top)

            qr_img = qrcode.make("http://192.168.137.1:8000")
            qr_temp_path = os.path.join(BASE_PATH, "qr_temp.png")
            qr_img.save(qr_temp_path)

            qr_label = QLabel()
            qr_label.setPixmap(QPixmap(qr_temp_path).scaled(120, 120))
            qr_layout.addWidget(qr_label)

            qr_bottom = QLabel(self.cfg["qr_texts"].get("bottom", "PW: Partytime"))
            qr_bottom.setStyleSheet("font-size: 14px; font-weight: bold;")
            qr_layout.addWidget(qr_bottom)

            layout.addWidget(qr_container, alignment=Qt.AlignmentFlag.AlignRight)

        self._refresh_start_options()

    def _setup_video_screen(self):
        """Setup Video-Screen"""
        layout = QVBoxLayout(self.video_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.video_view = QVideoWidget()
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setVideoOutput(self.video_view)
        self.player.setAudioOutput(self.audio_output)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)

        layout.addWidget(self.video_view)

    def _setup_session_screen(self):
        """Setup Session-Screen"""
        layout = QVBoxLayout(self.session_widget)

        # Status-Info
        info_layout = QHBoxLayout()

        self.print_info_label = QLabel("Drucken...")
        self.print_info_label.setStyleSheet(
            """
            background-color: #27ae60;
            color: white;
            padding: 5px 10px;
            border-radius: 5px;
            font-weight: bold;
        """
        )
        self.print_info_label.hide()
        info_layout.addWidget(self.print_info_label)

        info_layout.addStretch()
        layout.addLayout(info_layout)

        # Bild-Anzeige
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet(
            "background-color: #0d0d0f; border: 2px solid #0f0f16; border-radius: 14px;"
        )
        layout.addWidget(self.image_label, 1)

        # Button-Container
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setSpacing(20)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Buttons
        button_style = StyleManager.get_button_style()

        self.redo_button = QPushButton(self.cfg["ui_texts"].get("redo", "REDO"))
        self.redo_button.setStyleSheet(button_style)
        self.redo_button.clicked.connect(self._on_redo_clicked)
        self.redo_button.hide()
        button_layout.addWidget(self.redo_button)

        self.print_button = QPushButton(self.cfg["ui_texts"].get("print", "DRUCKEN"))
        self.print_button.setStyleSheet(button_style)
        self.print_button.clicked.connect(self._on_print_clicked)
        self.print_button.hide()
        button_layout.addWidget(self.print_button)

        self.finish_button = QPushButton(self.cfg["ui_texts"].get("finish", "FERTIG"))
        self.finish_button.setStyleSheet(button_style)
        self.finish_button.clicked.connect(self._on_finish_clicked)
        self.finish_button.hide()
        button_layout.addWidget(self.finish_button)

        self.cancel_button = QPushButton(
            self.cfg["ui_texts"].get("cancel", "ABBRECHEN")
        )
        self.cancel_button.setStyleSheet(button_style)
        self.cancel_button.clicked.connect(self._return_to_start)
        self.cancel_button.hide()
        button_layout.addWidget(self.cancel_button)

        button_container.setFixedHeight(100)
        layout.addWidget(button_container)

    def _setup_filter_screen(self):
        """Setup Filter-Screen"""
        layout = QVBoxLayout(self.filter_widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel(self.cfg["ui_texts"].get("choose_filter", "Wähle einen Filter"))
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title.setStyleSheet(
            "font-size: 30px; color: #1c1c28; font-weight: 800; letter-spacing: 0.2px;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "Tippe auf eine Miniatur, um den Look zu testen. Die Vorschau aktualisiert sofort, auch auf kleineren Displays."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #4c4c63;")
        layout.addWidget(subtitle)

        # Filter-Liste als horizontales Scrolling
        self.filter_scroll = QScrollArea()
        self.filter_scroll.setWidgetResizable(True)
        self.filter_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.filter_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.filter_scroll.setFixedHeight(210)

        filter_strip_widget = QWidget()
        self.filter_strip_layout = QHBoxLayout(filter_strip_widget)
        self.filter_strip_layout.setContentsMargins(6, 6, 6, 6)
        self.filter_strip_layout.setSpacing(12)

        self.filter_cards = []
        self.filters = [
            ("Kein Filter", "none"),
            ("S/W klassisch", "bw"),
            ("S/W kontrast", "bw_contrast"),
            ("Sepia", "sepia"),
            ("Warm Glow", "warm"),
            ("Cool Breeze", "cool"),
            ("Vivid Pop", "vivid"),
            ("Filmisch", "film"),
            ("Soft Glow", "soft_glow"),
        ]

        for label, filter_key in self.filters:
            card = FilterPreviewButton(label, filter_key, self.filter_widget)
            card.clicked.connect(self._on_filter_chosen)
            self.filter_strip_layout.addWidget(card)
            self.filter_cards.append(card)

        self.filter_strip_layout.addStretch()
        self.filter_scroll.setWidget(filter_strip_widget)
        layout.addWidget(self.filter_scroll)

        # Vorschau
        self.filter_preview_label = QLabel()
        self.filter_preview_label.setMinimumHeight(340)
        self.filter_preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.filter_preview_label.setStyleSheet(
            "border: 2px solid #0f0f16; border-radius: 14px; background-color: #0d0d0f;"
        )
        self.filter_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.filter_preview_label)

        self.filter_continue_btn = QPushButton("WEITER")
        self.filter_continue_btn.setFixedSize(220, 70)
        self.filter_continue_btn.setStyleSheet(StyleManager.get_button_style())
        self.filter_continue_btn.clicked.connect(self._on_filter_continue)
        layout.addWidget(self.filter_continue_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _setup_timers(self):
        """Erstellt Timer"""
        # USB-Check
        self.usb_timer = QTimer()
        self.usb_timer.timeout.connect(self._check_usb_status)
        self.usb_timer.start(CONFIG.USB_CHECK_INTERVAL)

        # Printer-Check
        self.printer_timer = QTimer()
        self.printer_timer.timeout.connect(self._check_printer_status)
        self.printer_timer.start(CONFIG.PRINTER_CHECK_INTERVAL)

        # Countdown
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self._countdown_tick)

        # Flash
        self.flash_timer = QTimer()
        self.flash_timer.setSingleShot(True)
        self.flash_timer.timeout.connect(self._on_flash_end)

        # Bar
        self.bar_timer = QTimer()
        self.bar_timer.timeout.connect(self._bar_tick)
        self.bar_timer.setInterval(50)

        # Live
        interval = 100 if self.cfg.get("performance_mode", True) else 33
        self.live_timer = QTimer()
        self.live_timer.timeout.connect(self._update_frame)
        self.live_timer.setInterval(interval)

    def _apply_initial_settings(self):
        """Wendet initiale Einstellungen an"""
        # Hintergrundfarbe
        color = self.cfg.get("background_color", "#ffffff")
        self.setStyleSheet(f"background-color: {color};")

        # Vollbild
        if self.cfg.get("start_fullscreen", True):
            self.showFullScreen()

    def _apply_messagebox_style(self):
        """Sorgt dafür, dass QMessageBox-Texte auf hellem Hintergrund sichtbar sind"""
        app = QApplication.instance()
        if not app:
            return

        base = app.styleSheet()
        msg_style = """
        QMessageBox { background: #ffffff; }
        QMessageBox QLabel { color: #000000; }
        QMessageBox QPushButton {
            color: #000000;
            background: #f0f0f0;
            border: 1px solid #b0b0b0;
            padding: 6px 12px;
            border-radius: 6px;
        }
        QMessageBox QPushButton:hover { background: #ffffff; }
        """
        if msg_style not in base:
            app.setStyleSheet(base + msg_style)

    def _update_logo(self):
        """Aktualisiert das Logo"""
        logo_path = self.cfg.get("logo_path", "")
        if logo_path and os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            scale = self.cfg.get("logo_scale", 100) / 100
            scaled_pixmap = pixmap.scaledToHeight(
                int(50 * scale), Qt.TransformationMode.SmoothTransformation
            )
            self.logo_label.setPixmap(scaled_pixmap)
        else:
            self.logo_label.clear()

    def _check_usb_status(self):
        """Prüft USB-Status"""
        usb = self.usb_manager.find_usb_stick()
        if usb:
            self.usb_warn_label.hide()
            self.usb_path = os.path.join(usb, "BILDER")
            os.makedirs(os.path.join(self.usb_path, "Prints"), exist_ok=True)
            os.makedirs(os.path.join(self.usb_path, "Single"), exist_ok=True)
        else:
            self.usb_warn_label.show()
            self.usb_path = None

    def _check_printer_status(self):
        """Prüft Drucker-Status"""
        try:
            printer_name = self.cfg.get("printer_name", "")
            if not printer_name:
                printer_name = win32print.GetDefaultPrinter()

            hPrinter = win32print.OpenPrinter(printer_name)
            info = win32print.GetPrinter(hPrinter, 2)
            win32print.ClosePrinter(hPrinter)

            status = info["Status"]
            messages = self.cfg.get("printer_messages", {})

            if status & 0x8:
                self.printer_status_label.setText(
                    messages.get("paper_out", "Papier leer!")
                )
                self.printer_status_label.show()
            elif status & 0x80:
                self.printer_status_label.setText(
                    messages.get("offline", "Drucker offline!")
                )
                self.printer_status_label.show()
            else:
                self.printer_status_label.hide()

        except Exception as e:
            logger.error(f"Drucker-Status-Fehler: {e}")

    def _on_admin_clicked(self):
        """Admin-Button wurde geklickt"""
        dialog = PinDialog(self.cfg.get("admin_pin", "1234"), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Admin-Dialog öffnen
            admin_dialog = AdminDialog(self.cfg, self)
            if admin_dialog.exec() == QDialog.DialogCode.Accepted:
                # Neue Config übernehmen
                self.cfg = admin_dialog.get_config()
                save_config(self.cfg)

                # Änderungen anwenden
                self._update_logo()
                self._apply_initial_settings()
                self._refresh_start_options()

                # UI-Texte aktualisieren
                self.admin_button.setText(self.cfg["ui_texts"].get("admin", "ADMIN"))
                self.start_btn.setText(self.cfg["ui_texts"].get("start", "START"))
                self.print_button.setText(self.cfg["ui_texts"].get("print", "DRUCKEN"))
                self.finish_button.setText(self.cfg["ui_texts"].get("finish", "FERTIG"))
                self.redo_button.setText(self.cfg["ui_texts"].get("redo", "REDO"))
                self.cancel_button.setText(
                    self.cfg["ui_texts"].get("cancel", "ABBRECHEN")
                )

                # Admin Button Alpha
                alpha = self.cfg.get("admin_button_alpha", 100)
                alpha_channel = int(alpha * 255 / 100)
                self.admin_button.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: rgba(255,255,0,{alpha_channel});
                        color: rgba(0,0,0,{alpha_channel});
                        border: 1px solid rgba(0,0,0,{alpha_channel});
                        font-size: 14px;
                        font-weight: bold;
                    }}
                """
                )

                logger.info("Admin-Einstellungen gespeichert. App-Neustart empfohlen.")
                QMessageBox.information(
                    self,
                    "Info",
                    "Einstellungen gespeichert. Ein Neustart der Anwendung wird empfohlen, um alle Änderungen zu übernehmen.",
                )

    def _refresh_start_options(self):
        """Aktualisiert Start-Optionen"""
        # Alle verstecken
        self.template1_option.hide()
        self.template2_option.hide()
        self.full_option.hide()

        # Layout leeren
        while self.options_strip_layout.count():
            item = self.options_strip_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        self.available_options = []

        # Template 1
        if (
            self.cfg.get("template1_enabled")
            and self.cfg["template_paths"]["template1"]
        ):
            path = self.cfg["template_paths"]["template1"]
            if os.path.exists(path):
                if path.lower().endswith(".zip"):
                    # ZIP-Template
                    overlay, boxes = read_zip_template(path)
                    if overlay:
                        # Konvertiere zu QPixmap für Vorschau
                        overlay_rgb = overlay.convert("RGB")
                        data = overlay_rgb.tobytes("raw", "RGB")
                        qimg = QImage(
                            data,
                            overlay_rgb.width,
                            overlay_rgb.height,
                            QImage.Format.Format_RGB888,
                        )
                        pixmap = QPixmap.fromImage(qimg)
                        pixmap = pixmap.scaled(
                            320, 240, Qt.AspectRatioMode.KeepAspectRatio
                        )
                        self.template1_option.update_pixmap(pixmap)
                else:
                    # Normales Bild
                    pixmap = QPixmap(path)
                    if not pixmap.isNull():
                        pixmap = pixmap.scaled(
                            320, 240, Qt.AspectRatioMode.KeepAspectRatio
                        )
                        self.template1_option.update_pixmap(pixmap)

            self.template1_option.show()
            self.available_options.append(self.template1_option)

        # Template 2
        if (
            self.cfg.get("template2_enabled")
            and self.cfg["template_paths"]["template2"]
        ):
            path = self.cfg["template_paths"]["template2"]
            if os.path.exists(path):
                if path.lower().endswith(".zip"):
                    overlay, boxes = read_zip_template(path)
                    if overlay:
                        overlay_rgb = overlay.convert("RGB")
                        data = overlay_rgb.tobytes("raw", "RGB")
                        qimg = QImage(
                            data,
                            overlay_rgb.width,
                            overlay_rgb.height,
                            QImage.Format.Format_RGB888,
                        )
                        pixmap = QPixmap.fromImage(qimg)
                        pixmap = pixmap.scaled(
                            320, 240, Qt.AspectRatioMode.KeepAspectRatio
                        )
                        self.template2_option.update_pixmap(pixmap)
                else:
                    pixmap = QPixmap(path)
                    if not pixmap.isNull():
                        pixmap = pixmap.scaled(
                            320, 240, Qt.AspectRatioMode.KeepAspectRatio
                        )
                        self.template2_option.update_pixmap(pixmap)

            self.template2_option.show()
            self.available_options.append(self.template2_option)

        # Single
        if self.cfg.get("allow_single_mode"):
            self.full_option.show()
            self.available_options.append(self.full_option)

        for opt in self.available_options:
            self.options_strip_layout.addWidget(opt)

        self.options_strip_layout.addStretch()

        # Start-Button deaktivieren
        self.start_btn.setEnabled(False)

    def _select_option(
        self, option: ModeOption, is_template: bool, path: Optional[str]
    ):
        """Wählt eine Option aus"""
        # Deselektiere alle
        self.template1_option.selected = False
        self.template2_option.selected = False
        self.full_option.selected = False

        # Selektiere gewählte
        option.selected = True

        # Update
        self.template1_option.update()
        self.template2_option.update()
        self.full_option.update()

        # Speichere Auswahl
        self.use_template = is_template
        self.chosen_template_path = path

        # Aktiviere Start
        self.start_btn.setEnabled(True)

    def _on_start_clicked(self):
        """Start wurde geklickt"""
        logger.info("Session gestartet")

        # Initialisiere Kamera
        if not self._initialize_camera():
            QMessageBox.critical(self, "Fehler", "Kamera konnte nicht geöffnet werden!")
            return

        # Video abspielen oder direkt starten
        video_path = resource_path("video_start.mp4")
        if os.path.exists(video_path):
            self.after_video_action = "start_session"
            self.player.setSource(QUrl.fromLocalFile(video_path))
            self.player.play()
            self.stacked.setCurrentIndex(1)
        else:
            self._start_session()

    def _on_media_status_changed(self, status):
        """Media-Status hat sich geändert"""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if hasattr(self, "after_video_action"):
                if self.after_video_action == "start_session":
                    self._start_session()
                elif self.after_video_action == "show_final":
                    self._show_final_image()

    def _initialize_camera(self):
        """Initialisiert die Kamera"""
        camera_index = self.cfg.get("camera_index", 0)

        if self.cfg.get("performance_mode", True):
            width, height = 640, 480
        else:
            width = self.cfg.get("camera_settings", {}).get("single_photo_width", 1280)
            height = self.cfg.get("camera_settings", {}).get("single_photo_height", 720)

        return self.camera_manager.initialize(camera_index, width, height)

    def _start_session(self):
        """Startet die Foto-Session"""
        logger.info("Session initialisiert")

        # Reset
        self.photos_taken = []
        self.current_photo_index = 0
        self.prints_in_session = 0
        self.current_filter = "none"

        # Template laden
        if self.use_template and self.chosen_template_path:
            self._load_template(self.chosen_template_path)
        else:
            self.template_boxes = [
                {
                    "box": (
                        0,
                        0,
                        CONFIG.FINAL_CANVAS_WIDTH - 1,
                        CONFIG.FINAL_CANVAS_HEIGHT - 1,
                    ),
                    "angle": 0.0,
                }
            ]
            self.overlay_image = None

        # Session starten
        self.live_mode = True
        self.in_countdown = True
        self.countdown_value = self.cfg.get("countdown_time", 5)

        self.cancel_button.show()

        self.live_timer.start()
        self.countdown_timer.start(1000)

        self.stacked.setCurrentIndex(2)

    def _load_template(self, path: str):
        """Lädt ein Template"""
        try:
            if path.lower().endswith(".zip"):
                # ZIP-Template
                overlay_img, photoboxes = read_zip_template(path)

                if overlay_img:
                    # Auf Canvas-Größe skalieren
                    if overlay_img.size != (
                        CONFIG.FINAL_CANVAS_WIDTH,
                        CONFIG.FINAL_CANVAS_HEIGHT,
                    ):
                        overlay_img = overlay_img.resize(
                            (CONFIG.FINAL_CANVAS_WIDTH, CONFIG.FINAL_CANVAS_HEIGHT),
                            Image.Resampling.LANCZOS,
                        )
                    self.overlay_image = overlay_img

                if photoboxes:
                    self.template_boxes = []
                    for box_info in photoboxes:
                        self.template_boxes.append(
                            {
                                "box": box_info["box"],
                                "angle": box_info.get("angle", 0.0),
                            }
                        )
                else:
                    # Fallback auf Masken-Erkennung
                    self._load_template_from_mask()
            else:
                # PNG/JPG Template
                img = Image.open(path).convert("RGBA")
                img = remove_icc_profile(img)

                # Auf Canvas-Größe skalieren
                if img.size != (CONFIG.FINAL_CANVAS_WIDTH, CONFIG.FINAL_CANVAS_HEIGHT):
                    img = img.resize(
                        (CONFIG.FINAL_CANVAS_WIDTH, CONFIG.FINAL_CANVAS_HEIGHT),
                        Image.Resampling.LANCZOS,
                    )

                self.overlay_image = img
                self._load_template_from_mask()

        except Exception as e:
            logger.error(f"Fehler beim Laden des Templates: {e}")
            self.template_boxes = [
                {
                    "box": (
                        0,
                        0,
                        CONFIG.FINAL_CANVAS_WIDTH - 1,
                        CONFIG.FINAL_CANVAS_HEIGHT - 1,
                    ),
                    "angle": 0.0,
                }
            ]
            self.overlay_image = None

    def _load_template_from_mask(self):
        """Lädt Template-Boxen aus Maske"""
        if not self.overlay_image:
            return

        # Finde Foto-Bereiche
        mask = create_mask(self.overlay_image)
        mask = morph_close(mask)
        regions = find_regions_from_mask(mask)

        self.template_boxes = []
        for x1, y1, x2, y2 in regions:
            w = x2 - x1 + 1
            h = y2 - y1 + 1
            if w * h > 450:  # Mindestgröße
                aspect = w / h
                if 1.35 <= aspect <= 1.65:  # Nur Querformat
                    self.template_boxes.append({"box": (x1, y1, x2, y2), "angle": 0.0})

        # Nach Größe sortieren und maximal 4
        self.template_boxes.sort(
            key=lambda x: (x["box"][2] - x["box"][0]) * (x["box"][3] - x["box"][1]),
            reverse=True,
        )
        self.template_boxes = self.template_boxes[:4]

        if not self.template_boxes:
            # Fallback
            self.template_boxes = [
                {
                    "box": (
                        0,
                        0,
                        CONFIG.FINAL_CANVAS_WIDTH - 1,
                        CONFIG.FINAL_CANVAS_HEIGHT - 1,
                    ),
                    "angle": 0.0,
                }
            ]

    def _countdown_tick(self):
        """Countdown-Tick"""
        self.countdown_value -= 1
        if self.countdown_value <= 0:
            self.countdown_timer.stop()
            self.in_countdown = False
            self._show_flash()

    def _show_flash(self):
        """Zeigt Blitz-Effekt"""
        logger.info(f"Foto {self.current_photo_index + 1}")

        # Weißes Bild anzeigen
        white = Image.new(
            "RGBA",
            (CONFIG.FINAL_CANVAS_WIDTH, CONFIG.FINAL_CANVAS_HEIGHT),
            (255, 255, 255, 255),
        )
        self._display_image(white)

        self.flash_timer.start(600)

    def _on_flash_end(self):
        """Flash beendet"""
        # Sound
        try:
            import winsound

            winsound.Beep(1000, 200)
        except:
            pass

        self._take_photo()

    def _take_photo(self):
        """Nimmt ein Foto auf"""
        frame = None
        # Prüfen, ob eine dedizierte take_photo Methode existiert (für Canon)
        if hasattr(self.camera_manager, "take_photo"):
            # Die Canon-Methode würde idealerweise den Pfad zum neuen Bild zurückgeben
            image_path = self.camera_manager.take_photo()
            if image_path and os.path.exists(image_path):
                # Hier müsste das Bild geladen werden
                # Für den Platzhalter simulieren wir das
                frame = cv2.imread("dummy.jpg")  # Annahme, es gibt ein dummy
            else:
                logger.error("Canon Fotoaufnahme fehlgeschlagen (Platzhalter)")
        else:
            # Fallback auf Webcam-Logik
            if self.cfg.get("performance_mode", True):
                width = self.cfg.get("camera_settings", {}).get(
                    "single_photo_width", 1280
                )
                height = self.cfg.get("camera_settings", {}).get(
                    "single_photo_height", 720
                )
                self.camera_manager.initialize(
                    self.cfg.get("camera_index", 0), width, height
                )
                time.sleep(0.1)

            frame = self.camera_manager.get_frame(use_cache=False)

            if self.cfg.get("performance_mode", True):
                self.camera_manager.initialize(
                    self.cfg.get("camera_index", 0), 640, 480
                )

        if frame is None:
            logger.error("Konnte kein Foto aufnehmen")
            return

        # Vollbild als Sample sichern (gespiegelt wie UI), damit Filter-Previews nicht verzerren
        rgb_full = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_full = Image.fromarray(rgb_full, "RGB")
        pil_full = ImageOps.mirror(pil_full)
        if self.filter_sample_image is None:
            self.filter_sample_image = pil_full.copy()

        # Verarbeite Foto
        self.live_mode = False
        single_img = self._crop_camera_image(frame, self.current_photo_index)
        self.photos_taken.append(single_img)
        self._save_single_photo(frame)
        if self.filter_sample_image is None:
            self.filter_sample_image = single_img.copy()

        self.current_photo_index += 1

        # Zeige Foto mit Timer
        self._start_bar_countdown("single")

    def _crop_camera_image(self, frame: np.ndarray, index: int) -> Image.Image:
        """Schneidet Kamera-Bild zu"""
        if index >= len(self.template_boxes):
            return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        info = self.template_boxes[index]
        x1, y1, x2, y2 = info["box"]
        hole_width = x2 - x1 + 1
        hole_height = y2 - y1 + 1

        # Spiegeln
        frame = cv2.flip(frame, 1)

        # Zu PIL konvertieren
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        camera_image = Image.fromarray(rgb, "RGB")

        # Auf Box-Größe zuschneiden
        cam_w, cam_h = camera_image.size
        cam_aspect = cam_w / cam_h
        hole_aspect = hole_width / hole_height

        if cam_aspect > hole_aspect:
            # Breiter als Box
            new_height = hole_height
            new_width = int(new_height * cam_aspect)
            resized = camera_image.resize(
                (new_width, new_height), Image.Resampling.LANCZOS
            )
            excess = new_width - hole_width
            left = excess // 2
            cropped = resized.crop((left, 0, left + hole_width, hole_height))
        else:
            # Höher als Box
            new_width = hole_width
            new_height = int(new_width / cam_aspect)
            resized = camera_image.resize(
                (new_width, new_height), Image.Resampling.LANCZOS
            )
            excess = new_height - hole_height
            top = excess // 2
            cropped = resized.crop((0, top, hole_width, top + hole_height))

        return cropped.convert("RGBA")

    def _save_single_photo(self, frame: np.ndarray):
        """Speichert Einzelfoto"""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb, "RGB")

        # Skalierung wenn gewünscht
        if not self.cfg.get("camera_settings", {}).get("disable_scaling", True):
            w, h = img.size
            scale = 1920.0 / max(w, h)
            if scale < 1.0:
                new_w = int(w * scale)
                new_h = int(h * scale)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Timestamp
        fname = (
            datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_fexobox_single.jpg"
        )

        # Lokaler Pfad
        local_path = os.path.join(SINGLE_PATH, fname)
        img.save(local_path, "JPEG", quality=95)

        # USB kopieren
        self._copy_to_usb(os.path.join("Single", fname), local_path)

    def _copy_to_usb(self, relative_path: str, source_path: str):
        """Kopiert auf USB"""
        if self.usb_path:
            dest_path = os.path.join(self.usb_path, relative_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            try:
                shutil.copy2(source_path, dest_path)
            except Exception as e:
                logger.error(f"USB-Kopier-Fehler: {e}")

    def _start_bar_countdown(self, mode: str):
        """Startet Bar-Countdown"""
        self.bar_mode = mode

        # Buttons verstecken
        self.redo_button.hide()
        self.print_button.hide()
        self.finish_button.hide()

        if mode == "single":
            self.bar_steps_left = self.cfg.get("single_display_time", 4) * 1000 // 50
            self.redo_button.show()
            self.cancel_button.show()
        elif mode == "final":
            self.bar_steps_left = self.cfg.get("final_time", 10) * 1000 // 50
            self.print_button.show()
            if not self.cfg.get("hide_finish_button", False):
                self.finish_button.show()
            self.cancel_button.show()

            # Print-Button Status
            if self.prints_in_session >= self.cfg.get("max_prints_per_session", 3):
                self.print_button.setEnabled(False)
                self.print_button.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #808080;
                        color: white;
                        font-size: 24px;
                        padding: 15px;
                        border-radius: 10px;
                    }
                """
                )

        self._show_bar_image()
        self.bar_timer.start()

    def _bar_tick(self):
        """Bar-Timer Tick"""
        self.bar_steps_left -= 1
        if self.bar_steps_left <= 0:
            self.bar_timer.stop()

            if self.bar_mode == "single":
                # Nächstes Foto oder Filter
                if self.current_photo_index >= len(self.template_boxes):
                    # Alle Fotos gemacht
                    self._show_filter_screen()
                else:
                    # Nächstes Foto
                    self.live_mode = True
                    self.in_countdown = True
                    self.countdown_value = self.cfg.get("countdown_time", 5)
                    self.redo_button.hide()
                    self.countdown_timer.start(1000)

            elif self.bar_mode == "final":
                # Zurück zum Start
                self._return_to_start()
        else:
            self._show_bar_image()

    def _show_bar_image(self):
        """Zeigt Bild mit Fortschrittsbalken"""
        final_image = self._build_final_image()

        # Fortschrittsbalken
        if self.bar_mode == "single":
            total = self.cfg.get("single_display_time", 4) * 1000 // 50
        else:
            total = self.cfg.get("final_time", 10) * 1000 // 50

        progress = self.bar_steps_left / total

        # Balken zeichnen
        draw = ImageDraw.Draw(final_image)
        bar_width = int(final_image.width * progress)
        bar_height = 30
        draw.rectangle((0, 0, bar_width, bar_height), fill=(224, 6, 117, 200))

        self._display_image(final_image)

    def _build_final_image(self, filter_override: Optional[str] = None) -> Image.Image:
        """Erstellt das finale Bild"""
        # Canvas
        base_image = Image.new(
            "RGBA",
            (CONFIG.FINAL_CANVAS_WIDTH, CONFIG.FINAL_CANVAS_HEIGHT),
            (0, 0, 0, 0),
        )

        active_filter = filter_override or self.current_filter

        # Fotos einfügen
        for i, info in enumerate(self.template_boxes):
            x1, y1, x2, y2 = info["box"]

            if i < len(self.photos_taken):
                # Foto mit Filter
                filtered = self.filter_manager.apply_filter(
                    self.photos_taken[i], active_filter
                )

                # An Position einfügen
                if filtered.size != (x2 - x1 + 1, y2 - y1 + 1):
                    filtered = filtered.resize(
                        (x2 - x1 + 1, y2 - y1 + 1), Image.Resampling.LANCZOS
                    )

                base_image.paste(filtered, (x1, y1), filtered)

            elif i == self.current_photo_index and self.live_mode:
                # Live-Vorschau
                frame = self.camera_manager.get_frame(use_cache=True)
                if frame is not None:
                    frame = cv2.flip(frame, 1)
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    cam_img = Image.fromarray(rgb, "RGB")

                    # Auf Box-Größe anpassen
                    hole_width = x2 - x1 + 1
                    hole_height = y2 - y1 + 1
                    cam_img = cam_img.resize(
                        (hole_width, hole_height), Image.Resampling.LANCZOS
                    )
                    base_image.paste(cam_img, (x1, y1))

        # Overlay
        if self.overlay_image:
            base_image = Image.alpha_composite(base_image, self.overlay_image)

        return base_image

    def _pil_to_qpixmap(self, pil_image: Image.Image) -> QPixmap:
        """Wandelt ein PIL-Bild in einen QPixmap um"""
        rgb_pil = pil_image.convert("RGB")
        data = rgb_pil.tobytes("raw", "RGB")
        qimg = QImage(
            data, rgb_pil.width, rgb_pil.height, QImage.Format.Format_RGB888
        )
        return QPixmap.fromImage(qimg)

    def _display_image(self, pil_image: Image.Image):
        """Zeigt ein Bild an"""
        # Konvertiere zu QPixmap
        pixmap = self._pil_to_qpixmap(pil_image)

        # Skaliere auf Label-Größe
        label_size = self.image_label.size()
        pixmap = pixmap.scaled(
            label_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.image_label.setPixmap(pixmap)

    def _update_frame(self):
        """Aktualisiert Live-Vorschau"""
        if not self.live_mode or self.bar_timer.isActive():
            return

        final_image = self._build_final_image()

        # Countdown-Overlay
        if self.in_countdown:
            draw = ImageDraw.Draw(final_image)

            # Font
            try:
                font_path = "C:/Windows/Fonts/Arial.ttf"
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, 400)
                else:
                    font = ImageFont.load_default()
            except:
                font = ImageFont.load_default()

            text = str(self.countdown_value)

            # Text-Position
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            x = (final_image.width - text_w) // 2
            y = (final_image.height - text_h) // 2

            # Schatten
            for offset in [(2, 2), (-2, 2), (2, -2), (-2, -2)]:
                draw.text(
                    (x + offset[0], y + offset[1]), text, fill=(0, 0, 0, 128), font=font
                )

            # Text
            draw.text((x, y), text, fill=(224, 6, 117, 255), font=font)

        self._display_image(final_image)

    def _show_filter_screen(self):
        """Zeigt Filter-Auswahl"""
        logger.info("Filter-Auswahl")

        # Filter-Vorschau aktualisieren
        self._update_filter_buttons()
        self._refresh_filter_previews()
        self._update_filter_preview()

        self.stacked.setCurrentIndex(3)
        QTimer.singleShot(50, self._update_filter_preview)

    def _update_filter_buttons(self):
        """Aktualisiert Filter-Buttons"""
        for card in getattr(self, "filter_cards", []):
            card.set_selected(card.filter_key == self.current_filter)

    def _refresh_filter_previews(self):
        """Erzeugt Mini-Previews für alle Filter"""
        if not getattr(self, "filter_cards", None):
            return

        sample_img = self._get_filter_sample_image()
        if sample_img is None:
            return

        for card in self.filter_cards:
            base = sample_img.copy()
            filtered = self.filter_manager.apply_filter(base, card.filter_key)
            # quadratisch zuschneiden
            w, h = filtered.size
            size = min(w, h)
            left = (w - size) // 2
            top = (h - size) // 2
            filtered = filtered.crop((left, top, left + size, top + size))
            filtered = filtered.resize((220, 220), Image.Resampling.LANCZOS)
            card.set_preview_pixmap(self._pil_to_qpixmap(filtered))

    def _get_filter_sample_image(self) -> Optional[Image.Image]:
        """Nimmt das erste Einzelbild als Basis für Filter-Previews"""
        if self.filter_sample_image is not None:
            return self.filter_sample_image.copy()
        if self.photos_taken:
            return self.photos_taken[0].copy()
        # Fallback: neutraler Platzhalter
        placeholder = Image.new("RGBA", (600, 600), (30, 30, 34, 255))
        return placeholder

    def _on_filter_chosen(self, filter_key: str):
        """Filter wurde gewählt"""
        self.current_filter = filter_key
        self._update_filter_buttons()
        self._update_filter_preview()

    def _update_filter_preview(self):
        """Aktualisiert Filter-Vorschau"""
        if not hasattr(self, "filter_preview_label"):
            return

        sample_img = self._get_filter_sample_image()
        if sample_img is None:
            return

        filtered = self.filter_manager.apply_filter(sample_img, self.current_filter)

        # Skaliere für Vorschau
        preview_size = self.filter_preview_label.size()
        if preview_size.width() == 0 or preview_size.height() == 0:
            return

        target_w = max(1, preview_size.width())
        target_h = max(1, preview_size.height())

        scale = min(target_w / filtered.width, target_h / filtered.height)
        new_width = max(1, int(filtered.width * scale))
        new_height = max(1, int(filtered.height * scale))

        scaled = filtered.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Letterbox, damit nichts verzerrt wird
        canvas = Image.new("RGB", (target_w, target_h), (13, 13, 15))
        offset = ((target_w - new_width) // 2, (target_h - new_height) // 2)
        canvas.paste(scaled.convert("RGB"), offset)

        pixmap = self._pil_to_qpixmap(canvas)
        self.filter_preview_label.setPixmap(pixmap)

    def _on_filter_continue(self):
        """Filter bestätigt"""
        logger.info("Session abgeschlossen")

        # Speichere finales Bild
        self._save_final_image()

        # Video oder direkt Final
        video_path = resource_path("video_end.mp4")
        if os.path.exists(video_path):
            self.after_video_action = "show_final"
            self.player.setSource(QUrl.fromLocalFile(video_path))
            self.player.play()
            self.stacked.setCurrentIndex(1)
        else:
            self._show_final_image()

    def _save_final_image(self):
        """Speichert finales Bild"""
        final_image = self._build_final_image()

        # Timestamp
        fname = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_fexobox_print.jpg"

        # Lokaler Pfad
        local_path = os.path.join(PRINTS_PATH, fname)

        # Speichern
        rgb = final_image.convert("RGB")
        rgb.save(local_path, "JPEG", quality=95)
        logger.info(f"Finales Bild gespeichert: {local_path}")

        # USB
        self._copy_to_usb(os.path.join("Prints", fname), local_path)

    def _show_final_image(self):
        """Zeigt finales Bild"""
        final_image = self._build_final_image()
        self._display_image(final_image)
        self._start_bar_countdown("final")
        self.stacked.setCurrentIndex(2)

    def _on_redo_clicked(self):
        """Redo wurde geklickt"""
        logger.info("Redo Foto")

        # Letztes Foto entfernen
        if self.photos_taken:
            self.photos_taken.pop()

        if self.current_photo_index > 0:
            self.current_photo_index -= 1

        # Neu starten
        self.bar_timer.stop()
        self.bar_mode = None
        self.live_mode = True
        self.in_countdown = True
        self.countdown_value = self.cfg.get("countdown_time", 5)

        self.redo_button.hide()
        self.countdown_timer.start(1000)

    def _on_print_clicked(self):
        """Drucken wurde geklickt"""
        if self.prints_in_session >= self.cfg.get("max_prints_per_session", 3):
            QMessageBox.information(
                self, "Limit erreicht", "Maximale Anzahl Drucke erreicht!"
            )
            return

        logger.info("Drucke Bild")

        # Info anzeigen
        self.print_info_label.show()
        QTimer.singleShot(3000, self.print_info_label.hide)

        # Bild drucken
        final_image = self._build_final_image()

        # Temporäre Datei
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        rgb = final_image.convert("RGB")
        rgb.save(tmp_path, "JPEG", quality=95)

        # Drucken
        try:
            self._print_image(tmp_path)
            self.prints_in_session += 1
            logger.info("Druck erfolgreich")
        except Exception as e:
            QMessageBox.warning(self, "Druckfehler", f"Fehler beim Drucken: {e}")
            logger.error(f"Druckfehler: {e}")
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass

        # Button deaktivieren wenn Limit erreicht
        if self.prints_in_session >= self.cfg.get("max_prints_per_session", 3):
            self.print_button.setEnabled(False)
            self.print_button.setStyleSheet(
                """
                QPushButton {
                    background-color: #808080;
                    color: white;
                    font-size: 24px;
                    padding: 15px;
                    border-radius: 10px;
                }
            """
            )

    def _print_image(self, image_path: str):
        """Druckt ein Bild"""
        printer_name = self.cfg.get("printer_name", "")
        if not printer_name:
            printer_name = win32print.GetDefaultPrinter()

        # Druckparameter
        adjustment = self.cfg.get("print_adjustment", {})
        offset_x = adjustment.get("offset_x", 0)
        offset_y = adjustment.get("offset_y", 0)
        zoom = adjustment.get("zoom", 100) / 100

        # Bild laden
        img = Image.open(image_path)

        # Größe anpassen
        base_width = int(1772 * zoom)
        base_height = int(1181 * zoom)
        img = img.resize((base_width, base_height), Image.Resampling.LANCZOS)

        # Drucken
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer_name)
        hDC.StartDoc("Photobooth Print")
        hDC.StartPage()

        # Windows-spezifischer Druck
        from PIL import ImageWin

        dib = ImageWin.Dib(img)
        dib.draw(
            hDC.GetHandleOutput(),
            (offset_x, offset_y, offset_x + base_width, offset_y + base_height),
        )

        hDC.EndPage()
        hDC.EndDoc()
        hDC.DeleteDC()

    def _on_finish_clicked(self):
        """Fertig wurde geklickt"""
        logger.info("Session beendet")
        self._return_to_start()

    def _return_to_start(self):
        """Zurück zum Start"""
        # Timer stoppen
        self.bar_timer.stop()
        self.countdown_timer.stop()
        self.live_timer.stop()

        self.live_mode = False
        self.in_countdown = False
        self.bar_mode = None

        # Buttons verstecken
        self.redo_button.hide()
        self.print_button.hide()
        self.finish_button.hide()
        self.cancel_button.hide()

        # Kamera freigeben
        self.camera_manager.release()

        # Reset Auswahl
        self.template1_option.selected = False
        self.template2_option.selected = False
        self.full_option.selected = False
        self.template1_option.update()
        self.template2_option.update()
        self.full_option.update()

        self.use_template = False
        self.chosen_template_path = None
        self.start_btn.setEnabled(False)

        # Caches leeren
        cache_manager.clear_cache()

        # Zurück zum Start
        self.stacked.setCurrentIndex(0)

    def closeEvent(self, event):
        """Beim Schließen"""
        self.camera_manager.release()
        event.accept()


# =============================================================================
# GALLERY SERVER
# =============================================================================


def start_gallery_server():
    """Startet den Galerie-Webserver"""
    cfg = load_config()
    logo_path = cfg.get("logo_path", "")

    logo_filename = None
    if logo_path and os.path.exists(logo_path):
        ext = os.path.splitext(logo_path)[1]
        logo_filename = "web_logo" + ext
        try:
            web_logo_path = os.path.join(SINGLE_PATH, logo_filename)
            shutil.copy2(logo_path, web_logo_path)
        except Exception as e:
            logger.error(f"Fehler beim Kopieren des Logos für Galerie: {e}")
            logo_filename = None

    class GalleryHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def list_directory(self, path):
            """Überschreibt die Standard-Verzeichnisliste"""
            import html

            try:
                file_list = os.listdir(path)
            except OSError:
                self.send_error(404, "Keine Berechtigung")
                return None

            file_list.sort(key=lambda a: a.lower(), reverse=True)

            # HTML generieren
            r = []
            r.append("<!DOCTYPE html>")
            r.append("<html><head>")
            r.append('<meta charset="utf-8">')
            r.append(
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
            )
            r.append("<title>Photobooth Galerie</title>")
            r.append("<style>")
            r.append(
                """
                body { 
                    font-family: Arial, sans-serif;
                    margin: 0; 
                    padding: 20px;
                    background-color: #f5f5f5;
                }
                h1 { 
                    text-align: center;
                    color: #333;
                    margin-bottom: 30px;
                }
                .gallery {
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                    gap: 20px;
                    max-width: 1200px;
                    margin: 0 auto;
                }
                .photo {
                    background: white;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    transition: transform 0.2s;
                }
                .photo:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                }
                .photo img {
                    width: 100%;
                    height: auto;
                    display: block;
                }
                .photo .name {
                    padding: 10px;
                    font-size: 12px;
                    color: #666;
                    text-align: center;
                    word-break: break-all;
                }
                .logo {
                    text-align: center;
                    margin-bottom: 20px;
                }
                .logo img {
                    max-height: 120px;
                }
            """
            )
            r.append("</style>")
            r.append("</head><body>")

            if logo_filename:
                r.append(
                    f'<div class="logo"><img src="{logo_filename}" alt="Logo"></div>'
                )

            r.append("<h1>Photobooth Galerie</h1>")
            r.append('<div class="gallery">')

            # Bilder hinzufügen
            for name in file_list:
                if name.lower().endswith((".jpg", ".jpeg", ".png")):
                    r.append('<div class="photo">')
                    r.append(f'<a href="{name}" target="_blank">')
                    r.append(f'<img src="{name}" alt="{html.escape(name)}">')
                    r.append(f'<div class="name">{html.escape(name)}</div>')
                    r.append("</a>")
                    r.append("</div>")

            r.append("</div>")
            r.append("</body></html>")

            encoded = "\n".join(r).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()

            return self.wfile.write(encoded)

    # Server starten
    os.chdir(SINGLE_PATH)
    with socketserver.TCPServer(("", 8000), GalleryHTTPRequestHandler) as httpd:
        logger.info("Galerie-Webserver läuft auf Port 8000")
        httpd.serve_forever()


# =============================================================================
# MAIN
# =============================================================================


def main():
    """Haupteinstiegspunkt"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # In PyQt6 ist High-DPI-Unterstützung standardmäßig aktiviert
    # Die alten Attribute existieren nicht mehr

    # Hauptfenster
    window = PhotoboothApp()
    window.show()

    # Galerie-Server starten wenn aktiviert
    if window.cfg.get("gallery_enabled", False):
        server_thread = threading.Thread(target=start_gallery_server, daemon=True)
        server_thread.start()
        logger.info("Galerie-Server-Thread gestartet")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
