"""Drucker-Steuerung für Canon SELPHY"""

import re
from src.utils.logging import get_logger

logger = get_logger(__name__)


def _strip_copy_suffix(name: str) -> str:
    """Entfernt Windows-Kopie-Suffixe wie '(Kopie 1)', '(Copy 2)' etc."""
    return re.sub(r'\s*\((?:Kopie|Copy)\s*\d*\)\s*$', '', name).strip()


def find_matching_printer(configured_name: str, available_printers: list) -> str:
    """Findet den passenden Drucker auch wenn er als Kopie registriert ist.

    Windows erstellt Kopien wie 'Canon SELPHY CP1000 (Kopie 1)' wenn
    der Drucker an einem anderen USB-Port angeschlossen wird.
    Diese Funktion matcht trotzdem auf den richtigen Drucker.

    Args:
        configured_name: Der in der Config gespeicherte Druckername
        available_printers: Liste der verfügbaren Druckernamen

    Returns:
        Den passenden Druckernamen oder "" wenn keiner gefunden
    """
    if not configured_name or not available_printers:
        return ""

    # 1. Exaktes Match
    if configured_name in available_printers:
        return configured_name

    # 2. Basis-Name vergleichen (ohne Kopie-Suffix)
    base_name = _strip_copy_suffix(configured_name)

    for printer in available_printers:
        if _strip_copy_suffix(printer) == base_name:
            logger.info(
                f"Drucker-Kopie erkannt: '{configured_name}' → '{printer}' "
                f"(anderer USB-Port)"
            )
            return printer

    return ""
