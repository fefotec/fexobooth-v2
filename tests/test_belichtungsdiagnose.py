"""Korrigierte Canon-Mappings und ausfallsichere Dev-Bilddiagnose."""

import sys
from pathlib import Path

from PIL import Image
from PIL.TiffImagePlugin import IFDRational

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.camera import edsdk
from src.camera import canon as canon_module
from src.camera.canon import CanonCameraManager


# Die im August-Log falsch interpretierten Werte direkt festnageln.
assert "Lock" in edsdk.AE_MODE_NAMEN[8]
assert "Vollautomatik" in edsdk.AE_MODE_NAMEN[9]
assert "Blitz aus" in edsdk.AE_MODE_NAMEN[15]
assert "Intelligente" in edsdk.AE_MODE_NAMEN[22]
assert "Nachtszene" in edsdk.AE_MODE_NAMEN[23]
assert edsdk.WB_NAMEN[2] == "Wolkig"
assert edsdk.WB_NAMEN[3] == "Kunstlicht"
assert edsdk.WB_NAMEN[4] == "Leuchtstoff"
assert edsdk.WB_NAMEN[5] == "Blitz"
assert edsdk.WB_NAMEN[6] == "Manuell 1"
assert edsdk.WB_NAMEN[8] == "Schatten"
assert "Weißpriorität" in edsdk.WB_NAMEN[23]
assert edsdk.EXPOSURE_COMP_NAMEN[0] == "0 EV"
assert edsdk.EXPOSURE_COMP_NAMEN[0x08] == "+1 EV"
assert edsdk.EXPOSURE_COMP_NAMEN[0xF8] == "-1 EV"
assert edsdk.METERING_MODE_NAMEN[3] == "Mehrfeld"
assert edsdk.EVF_VIEW_TYPE_NAMEN[3] == "deaktiviert"


manager = CanonCameraManager()
manager._aktueller_capture_id = "test.1"
ereignisse = []
manager._diag = lambda event, **werte: ereignisse.append((event, werte))

alter_dev = canon_module.is_developer_mode
try:
    canon_module.is_developer_mode = lambda: True

    weiss = Image.new("RGB", (600, 400), (255, 255, 255))
    exif = weiss.getexif()
    exif[0x829A] = IFDRational(1, 125)
    exif[0x829D] = IFDRational(4, 1)
    exif[0x8827] = 400
    exif[0x9204] = IFDRational(1, 1)
    exif[0x8822] = 2
    exif[0x9207] = 5
    exif[0x9209] = 0
    exif[0xA403] = 0

    manager._log_foto_belichtung(weiss)
    event, werte = ereignisse[-1]
    assert event == "EXPOSURE-JPEG"
    assert werte["exif_tv_s"] == "0.008"
    assert werte["exif_f"] == "4"
    assert werte["exif_iso"] == "400"
    assert werte["exif_bias_ev"] == "1"
    assert werte["exif_program"] == "Programmautomatik"
    assert werte["exif_metering"] == "Mehrfeld"
    assert werte["exif_wb"] == "auto"
    assert float(werte["luma_mean"]) == 255.0
    assert float(werte["nearwhite_pct"]) == 100.0
    assert float(werte["shadow_pct"]) == 0.0

    schwarz = Image.new("RGB", (300, 200), (0, 0, 0))
    manager._log_foto_belichtung(schwarz)
    event, werte = ereignisse[-1]
    assert event == "EXPOSURE-JPEG"
    assert float(werte["luma_mean"]) == 0.0
    assert float(werte["nearwhite_pct"]) == 0.0
    assert float(werte["shadow_pct"]) == 100.0

    class KaputtesExifBild:
        def getexif(self):
            raise ValueError("kaputt")

    manager._log_foto_belichtung(KaputtesExifBild())
    assert ereignisse[-1][0] == "EXPOSURE-JPEG-ERROR"

    class DarfNichtAngefasstWerden:
        def getexif(self):
            raise AssertionError("Dev-off darf keine EXIF-/Pixelarbeit machen")

    vorher = len(ereignisse)
    canon_module.is_developer_mode = lambda: False
    manager._log_foto_belichtung(DarfNichtAngefasstWerden())
    assert len(ereignisse) == vorher
finally:
    canon_module.is_developer_mode = alter_dev


print("BESTANDEN: Canon-Mappings sowie EXIF-/Helligkeitsdiagnose sind korrekt und sicher.")
