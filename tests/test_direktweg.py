"""Prueft den kompletten Direktweg: Kamera -> Rechner, ohne Karte."""
import sys, types, time, threading
import numpy as np
sys.path.insert(0, r"C:\Git-Projects\fexobooth-v2")

PROTOKOLL = []

fake = types.ModuleType("src.camera.edsdk")
fake.letzter_fehler = 0
fake.ERROR_NAMES = {0: "OK"}
fake.VERBINDUNG_TOT = set()
fake.ist_verbindung_tot = lambda e: False
fake.HARMLOS = set()
fake.EDSDK_DLL = None
fake.kEdsPropID_BatteryLevel = 8
fake.kEdsPropID_AEMode = 0x400
fake.kEdsPropID_AFMode = 0x404
fake.kEdsPropID_Tv = 0x406
fake.kEdsPropID_Av = 0x405
fake.kEdsPropID_ISOSpeed = 0x402
fake.kEdsPropID_WhiteBalance = 0x106
fake.TV_NAMEN = {}; fake.AV_NAMEN = {}; fake.ISO_NAMEN = {}; fake.WB_NAMEN = {}
fake.get_property_uint = lambda ref, p: None
fake.get_event = lambda: True
# 2.4.57: Alle faden-empfindlichen Aufrufe laufen ueber den Kamera-Faden.
# Im Test fuehren wir sie einfach direkt aus.
fake.im_kamera_faden = lambda fn, *a, timeout=20.0, **kw: fn(*a, **kw)
fake.pump_windows_messages = lambda *a: 0
fake.start_live_view = lambda ref: True
fake.stop_live_view = lambda ref: None
fake.get_live_view_image = lambda ref: None

def _melde_speicher(ref):
    PROTOKOLL.append("Speicherplatz gemeldet")
    return True
fake.melde_freien_speicher = _melde_speicher

KAMERA = {"handler": None}
def _take(ref, lv=False):
    PROTOKOLL.append(f"ausgeloest (LiveView={'an' if lv else 'aus'})")
    # Kamera liefert das Bild kurz darauf ueber den Rueckkanal
    def _liefern():
        time.sleep(0.4)
        PROTOKOLL.append("Kamera meldet: Bild fertig")
        KAMERA["handler"](0x00000208, object())
    threading.Thread(target=_liefern, daemon=True).start()
    return True
fake.take_picture = _take

import io
from PIL import Image
_buf = io.BytesIO()
Image.new("RGB", (6000, 4000), (120, 90, 60)).save(_buf, "JPEG", quality=60)
ECHTES_JPEG = _buf.getvalue()

fake.download_image_to_memory = lambda obj: ECHTES_JPEG
fake.initialize = lambda: True
fake.get_camera_list = lambda: [{"name": "Canon EOS 2000D", "ref": object(), "port": "usb"}]
fake.open_session = lambda ref: True
fake.close_session = lambda ref: None
fake.set_save_to_host = lambda ref: (PROTOKOLL.append("SaveTo = Rechner"), True)[1]
fake.set_save_to_camera = lambda ref: True
fake.get_first_volume = lambda ref: None
fake.set_image_quality_jpg = lambda ref: True
fake.log_camera_settings = lambda ref: None
def _handler(ref, cb):
    KAMERA["handler"] = cb
    PROTOKOLL.append("Rueckkanal eingerichtet")
    return True
fake.set_object_event_handler = _handler
sys.modules["src.camera.edsdk"] = fake

from src.camera.canon import CanonCameraManager

print("Szenario: Fotobox ohne Karte, Bild soll direkt auf die Festplatte\n")
cam = CanonCameraManager()
assert cam.initialize(), "Kamera liess sich nicht oeffnen"
cam._live_view_active = True

print("Ablauf beim Verbinden:")
for p in PROTOKOLL: print("  -", p)
print(f"\n  Modus: {'Direkt zum Rechner' if cam._use_host_download else 'ueber die Karte'}")
assert cam._use_host_download, "Box nimmt immer noch den Kartenweg!"

PROTOKOLL.clear()
print("\nAufnahme:")
t0 = time.time()
foto = cam.capture_photo(timeout=6.0)
dauer = time.time() - t0
for p in PROTOKOLL: print("  -", p)

print(f"\nErgebnis nach {dauer:.1f}s:")
if foto:
    print(f"  Foto: {foto.size[0]}x{foto.size[1]}  -> ECHTES DSLR-FOTO")
else:
    print("  kein Foto")
print(f"  Bilanz: {cam._fotos_echt} echt / {cam._fotos_notloesung} Notloesung")

assert foto is not None, "Kein Foto angekommen"
assert foto.size == (6000, 4000), f"Falsche Groesse: {foto.size}"
assert cam._fotos_echt == 1, "Nicht als echtes Foto gezaehlt"
assert dauer < 2.0, f"Zu langsam: {dauer:.1f}s"
print("\nBESTANDEN: Bild kommt direkt vom Chip in den Rechner, keine Karte beteiligt.")
