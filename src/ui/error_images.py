"""Helpers for loading small error illustration assets."""

from functools import lru_cache
from pathlib import Path
from typing import Optional
import sys

import customtkinter as ctk
from PIL import Image

from src.utils.logging import get_logger

logger = get_logger(__name__)


PRINTER_IMAGE_FILES = {
    "no_paper": ("printer_no_paper.png",),
    "ink_cassette": (
        "printer_ink_cassette.png",
        "printer_ink_casette.png",
        "printer_cassette.png",
    ),
    "cassette": ("printer_cassette.png", "printer_ink_casette.png"),
    "paper_jam": ("printer_paper_jam.png",),
    "cover_open": ("printer_cover_open.png", "printer_generic.png"),
    "offline": ("printer_offline.png", "printer_offline.png.png"),
    "generic": ("printer_generic.png",),
}


def _asset_roots() -> list[Path]:
    roots: list[Path] = []

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        roots.append(Path(bundle_root) / "assets" / "error_images")

    project_root = Path(__file__).resolve().parents[2]
    roots.append(project_root / "assets" / "error_images")
    roots.append(Path.cwd() / "assets" / "error_images")
    return roots


def _printer_image_key(error_text: str) -> str:
    upper = (error_text or "").upper()

    if "STAU" in upper or "JAM" in upper:
        return "paper_jam"
    if "PAPIER" in upper or "PAPER" in upper:
        return "no_paper"
    if "KLAPPE" in upper or "DOOR" in upper or "COVER" in upper:
        return "cover_open"
    if "TINTE" in upper or "INK" in upper or "TINTENKASSETTE" in upper:
        return "ink_cassette"
    if "KASSETTE" in upper or "CARTRIDGE" in upper:
        return "cassette"
    if (
        "OFFLINE" in upper
        or "AUS" in upper
        or "FEHLT" in upper
        or "KEIN DRUCKER" in upper
    ):
        return "offline"
    return "generic"


def _find_asset(candidates: tuple[str, ...]) -> Optional[Path]:
    for root in _asset_roots():
        for filename in candidates:
            path = root / filename
            if path.exists():
                return path
    return None


@lru_cache(maxsize=16)
def _load_pil_image(path_str: str) -> Optional[Image.Image]:
    try:
        with Image.open(path_str) as image:
            return image.convert("RGBA")
    except Exception as exc:
        logger.warning(f"Fehlerbild konnte nicht geladen werden: {path_str} ({exc})")
        return None


def load_printer_error_image(
    error_text: str,
    size: tuple[int, int],
) -> Optional[ctk.CTkImage]:
    """Load a CTkImage for a printer error, or None if no asset exists."""
    key = _printer_image_key(error_text)
    path = _find_asset(PRINTER_IMAGE_FILES.get(key, ()))
    if not path:
        return None

    image = _load_pil_image(str(path))
    if not image:
        return None

    return ctk.CTkImage(light_image=image, dark_image=image, size=size)
