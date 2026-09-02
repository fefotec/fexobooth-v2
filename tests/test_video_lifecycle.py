"""VLC-Lebenszyklus: 608 Clips ohne Player-/Thread-Lawine."""

import ast
import gc
import queue
import sys
import threading
import types
import weakref
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ui.vlc_player import PersistentVlcPlayer


class Logger:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class DeferredThread:
    created = []

    def __init__(self, target, daemon, name):
        self.target = target
        self.daemon = daemon
        self.name = name
        self.started = False
        self.finished = False
        self.__class__.created.append(self)

    def start(self):
        self.started = True

    def is_alive(self):
        return self.started and not self.finished

    def run(self):
        assert self.started and not self.finished
        try:
            self.target()
        finally:
            self.finished = True


class Media:
    def __init__(self, api, path):
        self.api = api
        self.path = path
        self.release_calls = 0
        self.released = False

    def add_option(self, option):
        assert option == "no-video-title-show"

    def release(self):
        self.release_calls += 1
        self.released = True
        self.api.media_releases += 1
        if self.api.fail_media_release:
            raise RuntimeError("media release kaputt")


class Player:
    def __init__(self, api):
        self.api = api
        self.media_path = None
        self.stop_calls = 0
        self.release_calls = 0

    def set_media(self, media):
        assert not media.released, "Caller-Media wurde vor set_media freigegeben"
        self.api.set_media_calls += 1
        self.media_path = media.path
        if self.api.fail_set_media:
            raise RuntimeError("set_media kaputt")

    def set_hwnd(self, hwnd):
        assert hwnd > 0
        self.api.hwnd_calls += 1

    def play(self):
        self.api.play_calls += 1
        return -1 if self.api.fail_play else 0

    def get_state(self):
        return "Ended"

    def stop(self):
        self.stop_calls += 1
        if self.api.fail_stop:
            raise RuntimeError("stop kaputt")

    def release(self):
        self.release_calls += 1
        if self.api.fail_player_release:
            raise RuntimeError("player release kaputt")


class Instance:
    def __init__(self, api):
        self.api = api
        self.player = None
        self.release_calls = 0

    def media_player_new(self):
        self.player = Player(self.api)
        self.api.players.append(self.player)
        return self.player

    def media_new(self, path):
        media = Media(self.api, path)
        self.api.media.append(media)
        return media

    def release(self):
        self.release_calls += 1
        if self.api.fail_instance_release:
            raise RuntimeError("instance release kaputt")


class FakeVlc:
    def __init__(self):
        self.instances = []
        self.players = []
        self.media = []
        self.media_releases = 0
        self.set_media_calls = 0
        self.hwnd_calls = 0
        self.play_calls = 0
        self.fail_set_media = False
        self.fail_media_release = False
        self.fail_play = False
        self.fail_stop = False
        self.fail_player_release = False
        self.fail_instance_release = False

    def Instance(self, args):
        assert "--avcodec-hw=dxva2" in args
        instance = Instance(self)
        self.instances.append(instance)
        return instance


def owner(api):
    return PersistentVlcPlayer(
        api,
        Logger(),
        ["--quiet", "--avcodec-hw=dxva2"],
        max_generations=2,
        thread_factory=DeferredThread,
    )


# Feldumfang Box 155: 608 Medien, aber nur ein Player und keine Normal-Cleanups.
DeferredThread.created.clear()
api = FakeVlc()
vlc = owner(api)
assert vlc.prepare()
erste_player_id = id(api.players[0])
for nummer in range(608):
    assert vlc.start(f"clip-{nummer}.mp4", 1234)
    vlc.mark_ended()

status = vlc.snapshot()
assert len(api.instances) == 1
assert len(api.players) == 1
assert id(api.players[0]) == erste_player_id
assert len(api.media) == 608
assert api.media_releases == 608
assert all(m.release_calls == 1 for m in api.media)
assert api.set_media_calls == api.play_calls == 608
assert status["generation"] == status["creations"] == 1
assert status["videos"] == 608
assert status["cleanup_pending"] == 0
assert status["state"] == "ready"
assert DeferredThread.created == []

# Der Owner selbst behaelt keine Media-Pythonreferenz.
letztes_medium = weakref.ref(api.media[-1])
api.media.clear()
gc.collect()
assert letztes_medium() is None


# Ein Fehler erzeugt exakt einen ausstehenden Cleanup; 50 weitere Startversuche
# koennen weder neue VLC-Paare noch neue Threads stapeln.
api.fail_play = True
assert not vlc.start("kaputt.mp4", 1234)
assert len(DeferredThread.created) == 1
cleanup_eins = DeferredThread.created[-1]
assert cleanup_eins.name == "VLC-Cleanup-1"
assert vlc.snapshot()["cleanup_pending"] == 1
for nummer in range(50):
    assert not vlc.start(f"fallback-{nummer}.mp4", 1234)
    assert not vlc.prepare_async()
assert len(api.instances) == 1
assert len(DeferredThread.created) == 1

# Erst nach bestaetigter Freigabe darf genau Generation 2 entstehen.
api.fail_play = False
cleanup_eins.run()
assert vlc.snapshot()["cleanup_result"] == "succeeded"
assert vlc.prepare_async()
prepare_zwei = DeferredThread.created[-1]
assert prepare_zwei.name == "VLC-Prepare-2"
prepare_zwei.run()
assert vlc.start("wieder-da.mp4", 1234)
assert len(api.instances) == len(api.players) == 2
assert vlc.snapshot()["generation"] == 2

# Der zweite Player-Fehler wird noch aufgeraeumt, danach bleibt VLC dauerhaft
# deaktiviert und es kann keine dritte Generation entstehen.
api.fail_play = True
assert not vlc.start("zweiter-fehler.mp4", 1234)
cleanup_zwei = DeferredThread.created[-1]
assert cleanup_zwei.name == "VLC-Cleanup-2"
cleanup_zwei.run()
assert vlc.snapshot()["disabled"]
assert not vlc.prepare_async()
assert len(api.instances) == 2


# set_media-Fehler gibt die Caller-Media trotzdem exakt einmal frei.
DeferredThread.created.clear()
api = FakeVlc()
api.fail_set_media = True
vlc = owner(api)
assert vlc.prepare()
assert not vlc.start("set-media-fehler.mp4", 1234)
assert len(api.media) == api.media_releases == 1
assert api.media[0].release_calls == 1
assert len(DeferredThread.created) == 1

# Auch der kombinierte Fehler setzt erst Media frei und mustert danach das
# Player-Paar dauerhaft aus.
DeferredThread.created.clear()
api = FakeVlc()
api.fail_set_media = True
api.fail_media_release = True
vlc = owner(api)
assert vlc.prepare()
assert not vlc.start("doppelfehler.mp4", 1234)
assert api.media[0].release_calls == 1
DeferredThread.created[-1].run()
assert vlc.snapshot()["disabled"]


# Eine unbestaetigte Media-Freigabe sperrt VLC auch bei erfolgreichem
# Player-Cleanup dauerhaft.
DeferredThread.created.clear()
api = FakeVlc()
api.fail_media_release = True
vlc = owner(api)
assert vlc.prepare()
assert not vlc.start("media-release-fehler.mp4", 1234)
assert api.media[0].release_calls == 1
DeferredThread.created[-1].run()
assert vlc.snapshot()["disabled"]
assert not vlc.prepare_async()


# Jede native Cleanup-Ausnahme bleibt als genau ein Rueckstand sichtbar und
# verhindert einen seriellen Leak. Alle drei Operationen werden separat geprueft.
for fehler_attribut in ("fail_stop", "fail_player_release", "fail_instance_release"):
    DeferredThread.created.clear()
    api = FakeVlc()
    vlc = owner(api)
    assert vlc.prepare()
    setattr(api, fehler_attribut, True)
    assert vlc.retire_async(fehler_attribut)
    DeferredThread.created[-1].run()
    status = vlc.snapshot()
    assert status["cleanup_pending"] == 1, fehler_attribut
    assert status["cleanup_result"] == "failed", fehler_attribut
    assert status["disabled"], fehler_attribut
    assert not vlc.prepare_async(), fehler_attribut
    assert not vlc.retire_async("nochmal"), fehler_attribut
    vlc.disable("nochmal")
    vlc.close()
    assert len(DeferredThread.created) == 1, fehler_attribut
    assert api.players[0].stop_calls == 1, fehler_attribut
    assert api.players[0].release_calls == 1, fehler_attribut
    assert api.instances[0].release_calls == 1, fehler_attribut


# Shutdown ist idempotent und wartet nicht auf den kontrollierbaren Thread.
DeferredThread.created.clear()
api = FakeVlc()
vlc = owner(api)
assert vlc.prepare()
vlc.close()
vlc.close()
assert len(DeferredThread.created) == 1
assert vlc.snapshot()["closed"]


# Timeout/Shutdown waehrend eines noch laufenden Warmups duerfen kein spaet
# publiziertes Paar und keinen zweiten Aufbau erzeugen.
for spaete_aktion in ("disable", "close"):
    DeferredThread.created.clear()
    api = FakeVlc()
    vlc = owner(api)
    assert vlc.prepare_async()
    prepare_thread = DeferredThread.created[-1]
    assert not vlc.prepare_async()
    if spaete_aktion == "disable":
        vlc.disable("warmup_timeout")
    else:
        vlc.close()
    prepare_thread.run()
    assert not vlc.snapshot()["has_player"]
    assert len(api.instances) == 1
    assert len(DeferredThread.created) == 2
    cleanup_thread = DeferredThread.created[-1]
    assert cleanup_thread.name == "VLC-Cleanup-1"
    cleanup_thread.run()
    assert not vlc.prepare_async()


# Strukturelle Screen-Vertraege sind absichtlich headless pruefbar.
app_source = (ROOT / "src" / "app.py").read_text(encoding="utf-8")
video_source = (ROOT / "src" / "ui" / "screens" / "video.py").read_text(encoding="utf-8")
show_start = app_source.index("    def show_screen(")
show_end = app_source.index("    def show_admin_dialog(", show_start)
show_source = app_source[show_start:show_end]
assert 'screen_name in ["session", "filter", "final"]' in show_source
assert '"video"]' not in show_source
assert 'from src.ui.screens.video import shutdown_vlc' in app_source
assert "video_screen.close_video()" in app_source
assert "_playback_generation" in video_source
assert "token == self._playback_generation" in video_source
assert "self._scheduled_ids" in video_source
assert "self.vlc_surface" in video_source
assert "args=(cap, stop_event, frame_queue, target_fps)" in video_source
assert "_VLC_WARMUP_TIMEOUT_SECONDS = 120.0" in video_source
assert 'psutil.Process(os.getpid())' in video_source
assert '_vlc_owner.retire_async("unexpected_stopped")' in video_source


# Die Callback-/Timer-Regeln werden mit einem winzigen headless Widget-Fake
# wirklich ausgefuehrt; dazu ist weder Tk noch ein Bildschirm erforderlich.
class FakeWidget:
    def __init__(self, *args, **kwargs):
        self.afters = {}
        self.cancelled = set()
        self.after_counter = 0
        self.visible = False
        self.image = None

    def pack(self, *args, **kwargs):
        self.visible = True

    def pack_forget(self):
        self.visible = False

    def configure(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def update_idletasks(self):
        pass

    def after(self, delay, callback):
        self.after_counter += 1
        after_id = f"after-{self.after_counter}"
        self.afters[after_id] = callback
        return after_id

    def after_cancel(self, after_id):
        self.cancelled.add(after_id)
        self.afters.pop(after_id, None)

    def winfo_id(self):
        return 1234

    def winfo_width(self):
        return 1280

    def winfo_height(self):
        return 800


fake_ctk = types.ModuleType("customtkinter")
fake_ctk.CTkFrame = FakeWidget
fake_ctk.CTkLabel = FakeWidget
fake_ctk.CTkImage = FakeWidget
sys.modules["customtkinter"] = fake_ctk

if "PIL" not in sys.modules:
    fake_pil = types.ModuleType("PIL")
    fake_pil.Image = object()
    sys.modules["PIL"] = fake_pil

import importlib.util
video_spec = importlib.util.spec_from_file_location(
    "fexobooth_test_video_screen", ROOT / "src" / "ui" / "screens" / "video.py"
)
video_module = importlib.util.module_from_spec(video_spec)
video_spec.loader.exec_module(video_module)


class FakeApp:
    def __init__(self):
        self.navigation = []

    def show_screen(self, name):
        self.navigation.append(name)


class TimeoutOwner:
    def __init__(self):
        self.disabled = []

    def disable(self, reason):
        self.disabled.append(reason)


timeout_owner = TimeoutOwner()
video_module._vlc_owner = timeout_owner
video_module._vlc_warm = False
video_module._vlc_warmup_started_at = 1000.0
alte_monotonic = video_module.time.monotonic
video_module.time.monotonic = lambda: 1120.1
assert video_module.is_vlc_warm()
assert timeout_owner.disabled == ["warmup_timeout"]
assert video_module.is_vlc_warm()
assert timeout_owner.disabled == ["warmup_timeout"]
video_module.time.monotonic = alte_monotonic


class PendingOwner:
    def __init__(self):
        self.prepare_calls = 0

    def snapshot(self):
        return {
            "has_player": False,
            "cleanup_pending": 1,
            "state": "cleanup",
            "generation": 1,
            "creations": 1,
            "videos": 1,
            "cleanup_result": "running",
            "preparing": 0,
        }

    def prepare_async(self):
        self.prepare_calls += 1
        return False


# Ein Clip waehrend eines haengenden VLC-Cleanups geht genau einmal sichtbar
# auf OpenCV, ohne Navigation oder einen weiteren VLC-Aufbau.
pending_owner = PendingOwner()
video_module._vlc_owner = pending_owner
video_module._vlc_available = True
video_module._vlc_warm = True
alte_platform = video_module.sys.platform
alte_exists = video_module.os.path.exists
video_module.sys.platform = "win32"
video_module.os.path.exists = lambda path: True
fallback_screen = video_module.VideoScreen(FakeWidget(), FakeApp())
fallback_calls = []
fallback_screen._play_opencv = lambda path, token: fallback_calls.append((path, token))
try:
    fallback_screen.play("fallback-waehrend-cleanup.mp4", "session")
finally:
    video_module.sys.platform = alte_platform
    video_module.os.path.exists = alte_exists
assert len(fallback_calls) == 1
assert fallback_calls[0][0] == "fallback-waehrend-cleanup.mp4"
assert pending_owner.prepare_calls == 1
assert fallback_screen.app.navigation == []


screen = video_module.VideoScreen(FakeWidget(), FakeApp())
screen._stop_playback("test_start")
screen._stop_event = threading.Event()
screen._end_called = False
token_a = screen._playback_generation
timer_calls = []
old_id = screen._schedule(50, lambda: timer_calls.append("A"), token_a)
old_callback = screen.afters[old_id]

# A wird abgebrochen, B beginnt. Selbst ein bereits aus Tk geholter Callback
# von A darf B nicht beeinflussen.
screen._stop_playback("a_to_b")
screen._stop_event = threading.Event()
screen._end_called = False
token_b = screen._playback_generation
new_id = screen._schedule(50, lambda: timer_calls.append("B"), token_b)
old_callback()
assert timer_calls == []
screen.afters[new_id]()
assert timer_calls == ["B"]


class CallbackOwner:
    def __init__(self, target_screen, calls):
        self.screen = target_screen
        self.calls = calls

    def done(self):
        assert self.screen.on_complete is None
        assert self.screen.video_path is None
        assert self.screen.next_screen == "start"
        self.calls.append("done")


callback_calls = []
callback_owner = CallbackOwner(screen, callback_calls)
callback_ref = weakref.ref(callback_owner)
screen.on_complete = callback_owner.done
screen.video_path = "alt.mp4"
screen.next_screen = "session"
screen._end_called = False
screen._stop_event = threading.Event()
callback_token = screen._playback_generation
screen._on_video_end(callback_token)
assert callback_calls == ["done"]
assert screen.app.navigation == []
screen._on_video_end(callback_token)
assert callback_calls == ["done"]
del callback_owner
gc.collect()
assert callback_ref() is None

# Callback-Exception navigiert einmal. Startet der Callback reentrant einen
# neuen Lauf, darf die alte Exception weder navigieren noch neue Werte loeschen.
screen.app.navigation.clear()
screen._end_called = False
screen._stop_event = threading.Event()
screen.next_screen = "final"
screen.on_complete = lambda: (_ for _ in ()).throw(RuntimeError("kaputt"))
error_token = screen._playback_generation
screen._on_video_end(error_token)
screen._on_video_end(error_token)
assert screen.app.navigation == ["final"]

screen.app.navigation.clear()
screen._end_called = False
screen._stop_event = threading.Event()
screen.video_path = "alt.mp4"
screen.next_screen = "final"

def reentrant_und_fehlerhaft():
    screen._stop_playback("reentrant")
    screen._stop_event = threading.Event()
    screen._end_called = False
    screen.video_path = "neu.mp4"
    screen.next_screen = "session"
    raise RuntimeError("alter Callback scheitert spaet")

screen.on_complete = reentrant_und_fehlerhaft
old_token = screen._playback_generation
screen._on_video_end(old_token)
assert screen.app.navigation == []
assert screen.video_path == "neu.mp4"
assert screen.next_screen == "session"


class EofCapture:
    def __init__(self):
        self.released = False

    def read(self):
        return False, None

    def release(self):
        self.released = True


# Auch bei voller 3er-Queue muss der OpenCV-Reader sein EOF garantiert
# zustellen; sonst wuerde die Anzeige nach einem kurzen UI-Stau endlos pollen.
eof_queue = queue.Queue(maxsize=3)
for frame in ("alt-1", "alt-2", "alt-3"):
    eof_queue.put_nowait(frame)
eof_event = threading.Event()
eof_capture = EofCapture()
screen._video_reader_thread(eof_capture, eof_event, eof_queue, 25)
assert None in list(eof_queue.queue)

eof_callbacks = []
screen._frame_queue = eof_queue
screen._stop_event = eof_event
screen._end_called = False
screen._backend = "opencv"
screen.is_playing = True
screen.cap = eof_capture
screen.on_complete = lambda: eof_callbacks.append("ende")
screen.next_screen = "session"
screen._show_frame = lambda frame: None
eof_token = screen._playback_generation
while not screen._end_called:
    screen._display_next_frame(eof_token)
assert eof_callbacks == ["ende"]
assert eof_capture.released

embed_start = video_source.index("    def _vlc_embed_and_play(")
embed_end = video_source.index("    def _vlc_check_status(", embed_start)
embed_source = video_source[embed_start:embed_end]
assert embed_source.index("self._show_vlc_surface()") < embed_source.index("winfo_id()")


# show_screen-Verhalten aus dem echten AST ausfuehren: Video bleibt dasselbe
# Objekt, die drei Session-Screens werden weiterhin frisch erzeugt.
class TestLogger:
    def info(self, *args, **kwargs):
        pass


def make_screen_class(name):
    class Screen(FakeWidget):
        created = 0

        def __init__(self, parent, app):
            super().__init__(parent)
            self.__class__.created += 1
            self.app = app
            self.destroy_calls = 0
            self.hide_calls = 0
            self.show_calls = 0

        def destroy(self):
            self.destroy_calls += 1

        def on_hide(self):
            self.hide_calls += 1

        def on_show(self, **kwargs):
            self.show_calls += 1

    Screen.__name__ = name
    return Screen


screen_modules = {
    "start": make_screen_class("StartScreen"),
    "session": make_screen_class("SessionScreen"),
    "filter": make_screen_class("FilterScreen"),
    "final": make_screen_class("FinalScreen"),
    "video": make_screen_class("VideoScreen"),
}
fake_screens_package = types.ModuleType("src.ui.screens")
fake_screens_package.__path__ = []
sys.modules["src.ui.screens"] = fake_screens_package
for module_name, class_name in (
    ("start", "StartScreen"),
    ("session", "SessionScreen"),
    ("filter", "FilterScreen"),
    ("final", "FinalScreen"),
    ("video", "VideoScreen"),
):
    module = types.ModuleType(f"src.ui.screens.{module_name}")
    setattr(module, class_name, screen_modules[module_name])
    sys.modules[module.__name__] = module

app_tree = ast.parse(app_source)
app_class = next(
    node for node in app_tree.body
    if isinstance(node, ast.ClassDef) and node.name == "PhotoboothApp"
)
show_function = next(
    node for node in app_class.body
    if isinstance(node, ast.FunctionDef) and node.name == "show_screen"
)
show_module = ast.fix_missing_locations(ast.Module(body=[show_function], type_ignores=[]))
show_namespace = {"logger": TestLogger()}
exec(compile(show_module, str(ROOT / "src" / "app.py"), "exec"), show_namespace)


class AppUnderTest:
    pass


AppUnderTest.show_screen = show_namespace["show_screen"]
app_under_test = AppUnderTest()
app_under_test.current_screen = None
app_under_test.current_screen_name = None
app_under_test.screens = {}
app_under_test.container = FakeWidget()
app_under_test.top_bar = FakeWidget()
app_under_test.root = FakeWidget()
app_under_test.config = {"developer_mode": False}
app_under_test.stress_test_active = False
app_under_test._check_pending_dialogs = lambda: None
app_under_test._stress_test_auto_proceed = lambda name: None

app_under_test.show_screen("video")
erstes_video = app_under_test.screens["video"]
app_under_test.show_screen("session")
erste_session = app_under_test.screens["session"]
app_under_test.show_screen("video")
assert app_under_test.screens["video"] is erstes_video
assert erstes_video.destroy_calls == 0
app_under_test.show_screen("session")
assert app_under_test.screens["session"] is not erste_session
assert erste_session.destroy_calls == 1
assert screen_modules["video"].created == 1
assert screen_modules["session"].created == 2

for kurzlebig in ("filter", "final"):
    app_under_test.show_screen(kurzlebig)
    erster = app_under_test.screens[kurzlebig]
    app_under_test.show_screen("video")
    app_under_test.show_screen(kurzlebig)
    assert app_under_test.screens[kurzlebig] is not erster
    assert erster.destroy_calls == 1
    assert screen_modules[kurzlebig].created == 2

print("BESTANDEN: 608 Videos nutzen einen Player und releasen 608 Medien exakt.")
print("BESTANDEN: Cleanup, Wiederaufbau, Fehler-Rueckstand und Shutdown sind begrenzt.")
print("BESTANDEN: Persistenter Screen, echte Playback-Token und Callback-Freigabe stehen.")
print("BESTANDEN: Warmup-Grenze, getrennte Ausgaben und Dev-Metriken stehen.")
