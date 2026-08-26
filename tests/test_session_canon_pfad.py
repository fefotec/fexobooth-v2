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
    screen._capture_generation = 0
    screen._active_capture_context = None

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
        def __init__(self, target, daemon, args=(), kwargs=None):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}
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
    expected_flash = [] if camera_type == "canon" else ["flash"]
    assert flash_aufrufe == expected_flash, camera_type
    assert len(threads) == 1 and threads[0].daemon and threads[0].gestartet, (
        f"{camera_type}: Capture muss weiterhin in genau einem Daemon-Thread starten"
    )
    assert threads[0].args == (screen._active_capture_context,)
    assert screen._active_capture_context.camera_type == camera_type

    return screen, timer_aufrufe, threads


print("=" * 68)
print("TEST 1: Wartehinweis wird nur noch fuer Nikon geplant")

canon, canon_timer, _ = _capture_planen("canon")
nikon, nikon_timer, _ = _capture_planen("nikon")
webcam, webcam_timer, _ = _capture_planen("webcam")

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
print("  Canon wartet auf Press-OK; Nikon/Webcam blitzen weiter vor dem Worker")


print()
print("TEST 2: Canon-Blitz folgt Press-OK genau einmal und nur fuer aktiven Token")


def _payload(capture_id="1.1"):
    now = session_modul.time.monotonic()
    return SimpleNamespace(
        capture_id=capture_id,
        press_ok=True,
        press_start_at=now - 0.2,
        press_return_at=now,
        release_ok=True,
        release_return_at=now,
    )


def _flash_screen(token=1):
    screen = object.__new__(SessionScreen)
    context = session_modul._UICaptureContext(
        token=token,
        camera_type="canon",
        capture_started_at=session_modul.time.monotonic(),
        flash_haltend=False,
    )
    screen._capture_generation = token
    screen._active_capture_context = context
    screen._capture_in_progress = True
    screen.is_live = True
    queued = []
    flashes = []

    def after(delay, callback):
        queued.append((delay, callback))
        return f"after-{len(queued)}"

    screen.after = after
    screen._show_shutter_flash = lambda duration_ms=None: (
        flashes.append(duration_ms), True
    )[1]
    return screen, context, queued, flashes


flash_screen, context_a, queued, flashes = _flash_screen()
payload_a = _payload()
SessionScreen._request_canon_shutter_flash(flash_screen, context_a, payload_a)
assert flashes == [], "Worker darf Tk nicht direkt aufrufen"
assert len(queued) == 1 and queued[0][0] == 0

# Selbst eine fehlerhafte doppelte Manager-Rueckmeldung erzeugt keinen zweiten
# Tk-Auftrag und beim erneuten Ausfuehren des UI-Callbacks keinen zweiten Blitz.
SessionScreen._request_canon_shutter_flash(flash_screen, context_a, payload_a)
assert len(queued) == 1
queued[0][1]()
queued[0][1]()
assert flashes == [90]

# Capture A darf nicht mehr blitzen, sobald Capture B aktiv ist — auch wenn B
# gerade selbst `_capture_in_progress=True` gesetzt hat.
stale_screen, context_a, stale_queue, stale_flashes = _flash_screen(token=10)
SessionScreen._request_canon_shutter_flash(stale_screen, context_a, _payload("A"))
context_b = session_modul._UICaptureContext(
    token=11,
    camera_type="canon",
    capture_started_at=session_modul.time.monotonic(),
    flash_haltend=False,
)
stale_screen._active_capture_context = context_b
stale_screen._capture_in_progress = True
stale_queue[0][1]()
assert stale_flashes == []

# on_hide invalidiert den Capture vor dem Widget-Cleanup. Ein schon queued
# Callback bleibt danach wirkungslos.
hide_screen, hide_context, hide_queue, hide_flashes = _flash_screen(token=20)
SessionScreen._request_canon_shutter_flash(
    hide_screen, hide_context, _payload("hide")
)
hide_screen.is_countdown_active = True
hide_screen._lv_stop = SimpleNamespace(set=lambda: None)
hide_screen._hide_redo_button = lambda: None
hide_screen._hide_shutter_flash = lambda: None
hide_screen._cached_template_composite = object()
hide_screen._cached_template_boxes_scaled = [object()]
SessionScreen.on_hide(hide_screen)
hide_queue[0][1]()
assert hide_flashes == []
assert hide_screen._active_capture_context is None

# Fehler beim Tk-Einreihen und beim spaeteren Anzeigen duerfen nicht zum
# Capture-Callback zurueckpropagieren.
enqueue_screen, enqueue_context, _, _ = _flash_screen(token=30)
enqueue_screen.after = lambda *args, **kwargs: (_ for _ in ()).throw(
    RuntimeError("Tk ist weg")
)
SessionScreen._request_canon_shutter_flash(
    enqueue_screen, enqueue_context, _payload("enqueue")
)

display_screen, display_context, display_queue, _ = _flash_screen(token=31)
display_screen._show_shutter_flash = lambda duration_ms=None: (_ for _ in ()).throw(
    RuntimeError("Overlay ist weg")
)
SessionScreen._request_canon_shutter_flash(
    display_screen, display_context, _payload("display")
)
display_queue[0][1]()

print("  Request/Shown je einmal; stale Tokens und Tk-Fehler sind folgenlos")


print()
print("TEST 3: Canon-RGB ohne Drehung bleibt dasselbe PIL-Objekt")

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
        self.press_payload = None
        self.callback_aufrufe = 0

    def capture_photo(self, timeout, press_command_accepted=None):
        assert timeout == 10.0
        self.capture_aufrufe += 1
        if press_command_accepted is not None and self.press_payload is not None:
            self.callback_aufrufe += 1
            press_command_accepted(self.press_payload)
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

canon_context = session_modul._UICaptureContext(
    token=40,
    camera_type="canon",
    capture_started_at=session_modul.time.monotonic(),
    flash_haltend=False,
)
canon_manager.press_payload = _payload("manager.1")
weitergereicht = []
canon_foto = SessionScreen._capture_photo_camera_calls(
    canon_screen,
    capture_context=canon_context,
    press_command_accepted=weitergereicht.append,
)
assert canon_foto is rgb
assert weitergereicht == [canon_manager.press_payload]
assert canon_manager.callback_aufrufe == 1
assert canon_manager.capture_aufrufe == 2

canon_manager.foto = None
spaeter_fehler_callback = []
assert SessionScreen._capture_photo_camera_calls(
    canon_screen,
    capture_context=canon_context,
    press_command_accepted=spaeter_fehler_callback.append,
) is None
assert canon_manager.capture_aufrufe == 3
assert spaeter_fehler_callback == [canon_manager.press_payload]

grau = Image.new("L", (1, 1), 127)
konvertiert = session_modul._canon_foto_aufbereiten(grau, rotate_180=False)
assert konvertiert.mode == "RGB" and konvertiert.getpixel((0, 0)) == (127, 127, 127)

print("  Keine NumPy/OpenCV-Rundreise, kein Kopieren im RGB-Direktfall")
print("  PIL-Drehung erhaelt Positionen und Farben; Sondermodi werden RGB")


print()
print("TEST 4: Bestehende Nikon-/Webcam-Aufrufe bleiben unveraendert")


class _StrikterNikonManager:
    def __init__(self, foto):
        self.foto = foto
        self.aufrufe = []

    def capture_photo(self, timeout):
        self.aufrufe.append(timeout)
        return self.foto


nikon_manager = _StrikterNikonManager(rgb)
nikon_screen = object.__new__(SessionScreen)
nikon_screen.config = {"camera_type": "nikon", "rotate_180": False}
nikon_screen.app = SimpleNamespace(camera_manager=nikon_manager)
nikon_context = session_modul._UICaptureContext(
    token=41,
    camera_type="nikon",
    capture_started_at=session_modul.time.monotonic(),
    flash_haltend=False,
)
nikon_foto = SessionScreen._capture_photo_camera_calls(
    nikon_screen,
    capture_context=nikon_context,
    press_command_accepted=lambda payload: (_ for _ in ()).throw(
        AssertionError("Nikon darf keinen Canon-Callback erhalten")
    ),
)
assert nikon_foto is not None
assert nikon_manager.aufrufe == [10.0]

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
print("TEST 5: Canon-Sofortanzeige nutzt eingefrorene Kameraart genau einmal")


class _Statistik:
    def __init__(self):
        self.aufrufe = 0

    def record_photo(self):
        self.aufrufe += 1


def _abschluss_screen(camera_type, flash_haltend):
    screen = object.__new__(SessionScreen)
    context = session_modul._UICaptureContext(
        token=50,
        camera_type=camera_type,
        capture_started_at=session_modul.time.monotonic() - 0.1,
        flash_haltend=flash_haltend,
    )
    screen._capture_generation = 50
    screen._active_capture_context = context
    screen._capture_in_progress = True
    screen._flash_haltend = flash_haltend
    screen._capture_visible_started_at = 0.0
    screen._photo_display_key = object()
    screen._redo_visible = False
    screen.total_photos = 1
    screen.photo_display_until = 0
    # Absichtlich eine andere aktuelle Config: Entscheidend ist die am Start
    # eingefrorene Kameraart im Context.
    screen.config = {"camera_type": "webcam", "single_display_time": 2}
    screen.app = SimpleNamespace(
        photos_taken=[],
        statistics=_Statistik(),
        current_photo_index=0,
        camera_manager=SimpleNamespace(),
    )
    displays = []
    hides = []
    screen.after = lambda delay, callback: f"after-{delay}"
    screen._save_photo_async = lambda *args: None
    screen._verstecke_dslr_wartehinweis = lambda: None
    screen._display_photo_cached = lambda photo: displays.append(photo)
    screen._hide_shutter_flash = lambda: hides.append("hide")
    screen._update_progress = lambda **kwargs: None
    screen._restore_preview_after_capture = lambda: None
    screen._show_redo_button = lambda: None
    screen._next_photo_or_finish = lambda: None
    return screen, context, displays, hides


for camera_type, flash_haltend, expected_displays in (
    ("canon", False, 1),
    ("webcam", True, 1),
    ("webcam", False, 0),
    ("nikon", False, 0),
):
    finish_screen, finish_context, displays, hides = _abschluss_screen(
        camera_type, flash_haltend
    )
    SessionScreen._on_capture_complete(
        finish_screen,
        rgb,
        finish_context,
        _payload(f"finish-{camera_type}"),
    )
    assert len(displays) == expected_displays, camera_type
    assert finish_screen._active_capture_context is None
    assert finish_screen._capture_in_progress is False
    assert finish_screen.app.photos_taken == [rgb]
    assert finish_screen.app.statistics.aufrufe == 1
    assert len(hides) == (1 if camera_type == "webcam" and flash_haltend else 0)

# Ein altes Completion darf einen neueren aktiven Capture nicht abschliessen.
stale_finish, old_context, displays, _ = _abschluss_screen("canon", False)
new_context = session_modul._UICaptureContext(
    token=51,
    camera_type="canon",
    capture_started_at=session_modul.time.monotonic(),
    flash_haltend=False,
)
stale_finish._active_capture_context = new_context
SessionScreen._on_capture_complete(
    stale_finish, rgb, old_context, _payload("old-complete")
)
assert stale_finish._active_capture_context is new_context
assert stale_finish._capture_in_progress is True
assert stale_finish.app.photos_taken == []
assert displays == []

print("  Canon und Webcam-HD je einmal; klassisch/Nikon nicht; stale ignoriert")


print()
print("=" * 68)
print("ALLE SESSION-CANON-REGRESSIONSTESTS BESTANDEN")
