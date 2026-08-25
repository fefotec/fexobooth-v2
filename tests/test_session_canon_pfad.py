"""Regressionstests fuer Canon-Wartehinweis und PIL-Direktweg.

Braucht keine Kamera und kein gestartetes Tk-Fenster. Der Test ruft nur die
kleinen Session-Methoden auf, die den Capture planen beziehungsweise ein
bereits dekodiertes Canon-Foto aufbereiten.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ui.screens import session as session_modul


SessionScreen = session_modul.SessionScreen


class _KeinBildumweg:
    """Laesst den Test sofort scheitern, sobald NumPy/OpenCV benutzt wird."""

    def __getattr__(self, name):
        raise AssertionError(
            f"Canon-PIL-Direktweg darf NumPy/OpenCV nicht aufrufen: {name}"
        )


class _WebcamManager:
    def __init__(self, frame):
        self.frame = frame
        self.aufrufe = []

    def get_high_res_frame(self, width, height, restore_preview=False):
        self.aufrufe.append((width, height, restore_preview))
        return self.frame.copy()


def _capture_planen(camera_type):
    """Fuehrt nur die UI-Planung aus; der Worker selbst wird nicht gestartet."""
    screen = object.__new__(SessionScreen)
    screen.config = {"camera_type": camera_type}
    screen.app = SimpleNamespace(current_photo_index=0)
    screen._dauerbetrieb_aktiv = lambda: False

    flash_aufrufe = []
    screen._show_shutter_flash = lambda: flash_aufrufe.append("flash")
    screen._capture_photo_worker = lambda: None

    timer_aufrufe = []

    def after(delay, callback):
        timer_aufrufe.append((delay, callback))
        return f"timer-{len(timer_aufrufe)}"

    screen.after = after

    threads = []

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
            self.gestartet = False
            threads.append(self)

        def start(self):
            self.gestartet = True

    echtes_thread = session_modul.threading.Thread
    session_modul.threading.Thread = FakeThread
    try:
        SessionScreen._capture_photo(screen)
    finally:
        session_modul.threading.Thread = echtes_thread

    assert screen._capture_in_progress is True
    assert screen._capture_visible_started_at > 0
    assert flash_aufrufe == ["flash"], (
        f"{camera_type}: weisser Ausloeseblitz darf nicht entfallen"
    )
    assert len(threads) == 1 and threads[0].daemon and threads[0].gestartet, (
        f"{camera_type}: Capture muss weiterhin in genau einem Daemon-Thread starten"
    )

    return screen, timer_aufrufe


print("=" * 68)
print("TEST 1: Wartehinweis wird nur noch fuer Nikon geplant")

canon, canon_timer = _capture_planen("canon")
nikon, nikon_timer = _capture_planen("nikon")
webcam, webcam_timer = _capture_planen("webcam")

assert canon_timer == [], "Canon darf keinen 900-ms-Wartebalken planen"
assert webcam_timer == [], "Webcam darf weiterhin keinen Wartebalken planen"
assert len(nikon_timer) == 1, "Nikon muss seinen bestehenden Wartehinweis behalten"
assert nikon_timer[0][0] == 900
assert nikon_timer[0][1].__name__ == "_zeige_dslr_wartehinweis"
assert nikon._dslr_hinweis_timer == "timer-1"

# Selbst ein versehentlich stehen gebliebener Callback darf bei Canon kein
# schwarzes Overlay mehr erzeugen.
frame_aufrufe = []
echtes_frame = session_modul.tk.Frame
session_modul.tk.Frame = lambda *args, **kwargs: frame_aufrufe.append(
    (args, kwargs)
)
try:
    canon._dslr_wait_overlay = None
    SessionScreen._zeige_dslr_wartehinweis(canon)
finally:
    session_modul.tk.Frame = echtes_frame
assert frame_aufrufe == [], "Canon-Guard muss auch einen alten Timer abfangen"

print("  Canon: kein Timer/Overlay; Nikon: 900 ms; Webcam: kein Timer")
print("  Weisser Blitz, Capture-Sperre und Worker-Thread bleiben aktiv")


print()
print("TEST 2: Canon-RGB ohne Drehung bleibt dasselbe PIL-Objekt")

rgb = Image.new("RGB", (3, 2))
rgb.putdata(
    [
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (255, 255, 0),
        (255, 0, 255),
        (0, 255, 255),
    ]
)

echtes_np = session_modul.np
echtes_cv2 = session_modul.cv2
session_modul.np = _KeinBildumweg()
session_modul.cv2 = _KeinBildumweg()
try:
    direkt = session_modul._canon_foto_aufbereiten(rgb, rotate_180=False)
    gedreht = session_modul._canon_foto_aufbereiten(rgb, rotate_180=True)
finally:
    session_modul.np = echtes_np
    session_modul.cv2 = echtes_cv2

assert direkt is rgb, "RGB ohne Drehung muss ohne Kopie direkt weitergereicht werden"
assert list(direkt.getdata()) == list(rgb.getdata())
assert gedreht.size == rgb.size and gedreht.mode == "RGB"
assert list(gedreht.getdata()) == list(reversed(list(rgb.getdata()))), (
    "PIL-ROTATE_180 muss Orientierung und RGB-Farben exakt erhalten"
)


class _CanonManager:
    def __init__(self, foto):
        self.foto = foto
        self.capture_aufrufe = 0

    def capture_photo(self, timeout):
        assert timeout == 10.0
        self.capture_aufrufe += 1
        return self.foto

    def get_high_res_frame(self, *args, **kwargs):
        raise AssertionError("Canon darf nach capture_photo keinen zweiten Weg starten")


canon_manager = _CanonManager(rgb)
canon_screen = object.__new__(SessionScreen)
canon_screen.config = {"camera_type": "canon", "rotate_180": False}
canon_screen.app = SimpleNamespace(camera_manager=canon_manager)
session_modul.np = _KeinBildumweg()
session_modul.cv2 = _KeinBildumweg()
try:
    canon_foto = SessionScreen._capture_photo_camera_calls(canon_screen)
finally:
    session_modul.np = echtes_np
    session_modul.cv2 = echtes_cv2
assert canon_foto is rgb
assert canon_manager.capture_aufrufe == 1

canon_manager.foto = None
assert SessionScreen._capture_photo_camera_calls(canon_screen) is None
assert canon_manager.capture_aufrufe == 2

grau = Image.new("L", (1, 1), 127)
konvertiert = session_modul._canon_foto_aufbereiten(grau, rotate_180=False)
assert konvertiert.mode == "RGB" and konvertiert.getpixel((0, 0)) == (127, 127, 127)

print("  Keine NumPy/OpenCV-Rundreise, kein Kopieren im RGB-Direktfall")
print("  PIL-Drehung erhaelt Positionen und Farben; Sondermodi werden RGB")


print()
print("TEST 3: Bestehender Webcam-High-Res-Pfad bleibt BGR nach RGB")

webcam_frame = np.array(
    [
        [[255, 0, 0], [0, 255, 0]],
        [[0, 0, 255], [255, 255, 255]],
    ],
    dtype=np.uint8,
)
manager = _WebcamManager(webcam_frame)
webcam_screen = object.__new__(SessionScreen)
webcam_screen.config = {
    "camera_type": "webcam",
    "rotate_180": False,
    "camera_settings": {
        "single_photo_width": 1234,
        "single_photo_height": 567,
    },
}
webcam_screen.app = SimpleNamespace(camera_manager=manager)

webcam_foto = SessionScreen._capture_photo_camera_calls(webcam_screen)
assert manager.aufrufe == [(1234, 567, False)]
assert webcam_foto.mode == "RGB" and webcam_foto.size == (2, 2)
assert list(webcam_foto.getdata()) == [
    (0, 0, 255),
    (0, 255, 0),
    (255, 0, 0),
    (255, 255, 255),
]

print("  Aufloesung, restore_preview=False und BGR/RGB-Farben unveraendert")


print()
print("=" * 68)
print("ALLE SESSION-CANON-REGRESSIONSTESTS BESTANDEN")
