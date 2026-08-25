"""Prueft die 2.4.46-Fixes ohne angeschlossene Kamera."""
import sys, types, time
import numpy as np

sys.path.insert(0, r"C:\Git-Projects\fexobooth-v2")

# --- edsdk faelschen, damit canon.py ohne DLL importierbar ist -------------
fake = types.ModuleType("src.camera.edsdk")
fake.letzter_fehler = 0
fake.ERROR_NAMES = {0x81: "DEVICE_BUSY", 0xc1: "COMM_DISCONNECTED", 0: "OK"}
fake.VERBINDUNG_TOT = {0x81, 0xc1, 0x80}
fake.ist_verbindung_tot = lambda e: e in fake.VERBINDUNG_TOT
fake.HARMLOS = {0xa102}
fake.EDSDK_DLL = None
fake.lv_darf_starten = False          # Steuerung fuer den Test
fake.frame_kommt = False
fake.kEdsPropID_BatteryLevel = 8
fake.kEdsPropID_AEMode = 0x400
fake.kEdsPropID_AFMode = 0x404

def _start_lv(ref):
    if fake.lv_darf_starten:
        return True
    fake.letzter_fehler = 0xc1        # COMM_DISCONNECTED
    return False
fake.start_live_view = _start_lv
fake.stop_live_view = lambda ref: None
fake.get_live_view_image = lambda ref: None
fake.get_event = lambda: True
fake.pump_windows_messages = lambda *a: 0
fake.get_property_uint = lambda ref, p: None
fake.initialize = lambda: True
fake.get_camera_list = lambda: []
fake.open_session = lambda ref: False
fake.close_session = lambda ref: None
fake.set_save_to_host = lambda ref: True
fake.set_save_to_camera = lambda ref: True
fake.set_object_event_handler = lambda ref, cb: True
fake.log_camera_settings = lambda ref: None
sys.modules["src.camera.edsdk"] = fake

from src.camera.canon import CanonCameraManager

cam = CanonCameraManager()
cam._is_initialized = True
cam._camera_ref = object()
cam._reconnect_abstand = 9999        # Neuaufbau im Test unterdruecken
cam._letzter_reconnect = time.monotonic()

# Ein "altes" Vorschaubild einlagern, wie es die Box hatte
altbild = np.full((704, 1056, 3), 42, dtype=np.uint8)
cam._last_frame = altbild
cam._last_frame_time = time.time() - 120   # 2 Minuten alt

print("=" * 62)
print("TEST 1: Vorschau darf das Altbild zeigen (kein schwarzer Schirm)")
f = cam.get_frame(use_cache=False, allow_stale=True)
print("  Ergebnis:", "Altbild geliefert  -> RICHTIG" if f is not None else "None -> FALSCH")
assert f is not None

print()
print("TEST 2: Foto-Notloesung darf das Altbild NICHT bekommen")
f = cam.get_frame(use_cache=False, allow_stale=False)
print("  Ergebnis:", "None -> RICHTIG (kein Doppelbild)" if f is None else "Altbild -> FALSCH!")
assert f is None

print()
print("TEST 3: Notloesung liefert lieber gar nichts als ein altes Bild")
t0 = time.time()
bild = cam._fallback_to_live_view(False)
dauer = time.time() - t0
print(f"  Ergebnis: {'None -> RICHTIG' if bild is None else 'Bild -> FALSCH!'} (nach {dauer:.1f}s)")
print(f"  Zaehler: echt={cam._fotos_echt} notloesung={cam._fotos_notloesung} leer={cam._fotos_leer}")
assert bild is None

print()
print("TEST 4: Endlosschleifen-Bremse greift")
cam._lv_fehler_serie = 0
cam._lv_gesperrt_bis = 0.0
t0 = time.time()
cam.start_live_view()                       # verliert die Runde, setzt Ruhepause
erste = time.time() - t0
t0 = time.time()
for _ in range(30):                         # frueher: 30 x 1,5s = 45 Sekunden
    cam.start_live_view()
dreissig = time.time() - t0
print(f"  Erste verlorene Runde: {erste:.2f}s (erkennt Abbruch sofort)")
print(f"  30 weitere Aufrufe:    {dreissig:.3f}s  (frueher waeren das ~45s Blockade)")
assert dreissig < 1.0, "Bremse greift nicht!"

print()
print("TEST 5: Doppelbild-Sperre bei eingefrorener Vorschau")
fake.frame_kommt = True
fake.lv_darf_starten = True
standbild = np.full((704, 1056, 3), 99, dtype=np.uint8)
def _immer_dasselbe(ref):
    import cv2
    return cv2.imencode(".jpg", standbild)[1].tobytes()
fake.get_live_view_image = _immer_dasselbe
cam._live_view_active = True
cam._last_frame = None
cam._letzter_fallback_fp = None
cam._fotos_leer = 0

b1 = cam._fallback_to_live_view(False)
b2 = cam._fallback_to_live_view(False)
print(f"  1. Notloesung: {'Bild' if b1 is not None else 'None'}  (darf durch)")
print(f"  2. Notloesung: {'Bild -> FALSCH!' if b2 is not None else 'None -> RICHTIG (Doppelbild geblockt)'}")
assert b1 is not None and b2 is None

print()
print("=" * 62)
print("ALLE TESTS BESTANDEN")
