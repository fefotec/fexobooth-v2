"""Box 210/008: echte Methoden, kontrolliertes Rennen, keine Hardware/Tk-Fenster."""
import ast
import logging
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.camera import webcam
from src.ui.dialogs import system_test as dialog_module
from src.utils import logging as dev_logging

Dialog = dialog_module.SystemTestDialog


def app_class():
    # Nur die echten relevanten Methoden laden: kein App-Boot, Netzwerk oder USB.
    tree = ast.parse((ROOT / "src/app.py").read_text(encoding="utf-8"))
    names = {"_camera_probe_blocked", "_camera_status_probe", "_on_camera_status_result",
             "_check_camera_status", "_run_system_test"}
    methods = [n for cls in tree.body if isinstance(cls, ast.ClassDef)
               for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(methods) == len(names)
    ns = dict(time=time, threading=threading, logger=logging.getLogger("fexobooth.test"),
              t=lambda config, key: key, CANON_AVAILABLE=False)
    exec(compile(ast.Module(body=methods, type_ignores=[]), "src/app.py", "exec"), ns)
    return type("ProbeApp", (), {name: ns[name] for name in names})


App = app_class()


def make_app(path="quick"):
    app = App()
    app.config = {"camera_type": "webcam", "camera_index": -1 if path == "search" else 0}
    app.camera_manager = SimpleNamespace(is_initialized=False)
    app.current_screen_name = "start"
    app.current_screen = None
    app.root = SimpleNamespace(after=Mock())
    app.camera_status = Mock()
    app._mainloop_started = True
    app._camera_check_running = False
    app._camera_blink_state = False
    app._camera_probe_epoch = 0
    app._system_test_running = None
    app._letzte_vollpruefung = time.time() if path == "quick" else 0
    app._letzte_kamerasuche = 0
    return app


class FastCancel(threading.Event):
    def wait(self, timeout=None):
        return self.is_set() if timeout == 0.3 else super().wait(timeout)


def make_dialog():
    d = object.__new__(Dialog)
    d._destroyed = False
    d._cancelled = FastCancel()
    d._worker_started = True
    d._worker_done = threading.Event()
    d._close_requested = False
    d._errors, d._warnings, d._metrics = [], [], {}
    d._test_file = None
    d._test_photos, d._test_result = [object()], object()
    d._num_photos = 1
    d.STEPS = [(str(i), "status") for i in range(6)]
    d.calls = []
    d.release_threads = []
    d._camera_manager = SimpleNamespace(is_initialized=True)
    def release():
        d.calls.append("release")
        d.release_threads.append(threading.get_ident())
        d._camera_manager.is_initialized = False
    d._camera_manager.release = release
    d.app = SimpleNamespace(camera_manager=d._camera_manager)
    d._on_finished = Mock(side_effect=lambda: d.calls.append("finished"))
    d._on_complete = Mock()
    for name in ("system_check", "init_camera", "capture_photos", "apply_template", "print"):
        setattr(d, "_step_" + name, Mock(side_effect=lambda n=name: d.calls.append(n)))
    d.after = Mock()
    d._update_status = Mock()
    d._update_step = Mock()
    d._show_result = Mock()
    d._close = Mock()
    d.cancel_btn = Mock()
    return d


class ProbeTests(unittest.TestCase):
    def probe_io(self, app, lock):
        cap = Mock()
        cap.isOpened.return_value = True
        def opened(*args):
            self.assertTrue(lock._is_owned())
            return cap
        def listed():
            self.assertTrue(lock._is_owned())
            return [{"index": 0, "name": "C922"}]
        return (patch.object(webcam, "camera_hardware_lock", return_value=lock),
                patch("cv2.VideoCapture", side_effect=opened),
                patch.object(webcam.WebcamManager, "list_cameras", side_effect=listed),
                patch.object(webcam.WebcamManager, "erkenne_kamera", return_value={
                    "index": 0, "zustand": "extern", "begruendung": "Test", "kameras": []}))

    def test_waiting_probe_rechecks_every_path_and_owner(self):
        for path in ("quick", "full", "search"):
            for change in ("init", "test", "measurement", "screen"):
                with self.subTest(path=path, change=change):
                    app = make_app(path)
                    real_lock, entered = threading.RLock(), threading.Event()
                    class WaitingLock:
                        def acquire(self, **kwargs):
                            entered.set()
                            return real_lock.acquire(**kwargs)
                        def release(self):
                            real_lock.release()
                        def _is_owned(self):
                            return real_lock._is_owned()
                    guards = self.probe_io(app, WaitingLock())
                    with guards[0], guards[1] as capture, guards[2] as listing, guards[3]:
                        with real_lock:
                            worker = threading.Thread(target=app._camera_status_probe, daemon=True)
                            worker.start()
                            self.assertTrue(entered.wait(2), "Probe hat Lock nicht erreicht")
                            if change == "init":
                                app.camera_manager.is_initialized = True
                            elif change == "test":
                                app._system_test_running = object()
                            elif change == "measurement":
                                app._kamera_messung_laeuft = True
                            else:
                                app.current_screen_name = "session"
                        worker.join(2)
                        self.assertFalse(worker.is_alive())
                        capture.assert_not_called()
                        listing.assert_not_called()
                        self.assertEqual(app.root.after.call_count, 1)

    def test_idle_detection_still_runs_all_paths(self):
        for path in ("quick", "full", "search"):
            app, lock = make_app(path), threading.RLock()
            guards = self.probe_io(app, lock)
            with guards[0], guards[1] as capture, guards[2] as listing, guards[3]:
                app._camera_status_probe()
                self.assertEqual(capture.call_count, int(path == "quick"))
                self.assertEqual(listing.call_count, int(path != "quick"))
                app.root.after.call_args.args[1]()
                self.assertEqual(app.config["camera_index"], 0)

    def test_busy_lock_does_not_probe(self):
        app, lock = make_app(), Mock()
        lock.acquire.return_value = False
        with patch.object(webcam, "camera_hardware_lock", return_value=lock), \
                patch("cv2.VideoCapture") as capture:
            app._camera_status_probe()
        capture.assert_not_called()
        lock.release.assert_not_called()

    def test_stale_results_never_change_config_or_warning(self):
        for state in ("epoch", "active", "test"):
            app = make_app()
            if state == "epoch":
                app._camera_probe_epoch = 1
            elif state == "active":
                app.camera_manager.is_initialized = True
            else:
                app._system_test_running = object()
            app._on_camera_status_result("missing", -1, 0)
            self.assertEqual(app.config["camera_index"], 0)
            app.camera_status.configure.assert_not_called()
            self.assertFalse(app._camera_check_running)

    def test_scheduler_pauses_for_test(self):
        app = make_app()
        app._system_test_running = object()
        with patch.object(threading, "Thread") as worker:
            app._check_camera_status()
        worker.assert_not_called()
        self.assertEqual(app.root.after.call_args.args[0], 5000)

    def test_reservation_duplicate_failure_and_retry(self):
        app = make_app()
        with patch.object(dialog_module, "SystemTestDialog") as ctor:
            app._run_system_test()
            first_finish = ctor.call_args.kwargs["on_finished"]
            self.assertTrue(app._system_test_running)
            app._run_system_test()
            self.assertEqual(ctor.call_count, 1)
            first_finish()
            app._run_system_test()
            second_owner = app._system_test_running
            first_finish()  # spaeter alter Callback darf neuen Besitz nicht loesen
            self.assertIs(app._system_test_running, second_owner)
            ctor.call_args.kwargs["on_finished"]()
        with patch.object(dialog_module, "SystemTestDialog", side_effect=RuntimeError("Tk")):
            with self.assertRaises(RuntimeError):
                app._run_system_test()
        self.assertIsNone(app._system_test_running)


class LifecycleTests(unittest.TestCase):
    def test_success_and_every_step_failure_cleanup_once(self):
        for failure in (None, "system_check", "init_camera", "capture_photos", "apply_template", "print"):
            with self.subTest(failure=failure):
                d = make_dialog()
                if failure:
                    getattr(d, "_step_" + failure).side_effect = RuntimeError("test failure")
                d._run_test()
                self.assertEqual(d.calls[-2:], ["release", "finished"])
                self.assertEqual(d.calls.count("release"), 1)
                self.assertFalse(d._camera_manager.is_initialized)
                self.assertTrue(d._worker_done.is_set())
                self.assertEqual(d._test_photos, [])
                self.assertIsNone(d._test_result)
                if failure in ("init_camera", "capture_photos"):
                    d._step_print.assert_not_called()
                d._poll_test_finished()
                d._show_result.assert_called_once()

    def test_cancel_timeout_force_wait_for_worker_without_ui_release(self):
        for action in ("_on_cancel", "_on_timeout", "_force_abort"):
            d = make_dialog()
            entered, resume = threading.Event(), threading.Event()
            def capture():
                entered.set()
                if not resume.wait(3):
                    raise RuntimeError("test synchronization timeout")
            d._step_capture_photos.side_effect = capture
            worker = threading.Thread(target=d._run_test, daemon=True)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                getattr(d, action)()
                getattr(d, action)()  # wiederholter Touch/Timeout bleibt einmalig
                self.assertEqual(len(d._errors), 1)
                self.assertEqual(d.release_threads, [])
                self.assertFalse(d._worker_done.is_set())
                d._poll_test_finished()
                d._show_result.assert_not_called()
                d._close.assert_not_called()
            finally:
                resume.set()
                worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(d.release_threads, [worker.ident])
            d._step_print.assert_not_called()
            d._poll_test_finished()
            (d._close if action == "_force_abort" else d._show_result).assert_called_once()

    def test_cancel_before_start_and_timeout_after_finish(self):
        d = make_dialog()
        d._worker_started = False
        d._on_cancel()
        d._run_test()
        d._step_init_camera.assert_not_called()
        self.assertEqual(d.calls, ["release", "finished"])
        before = list(d._errors)
        d._on_timeout()
        self.assertEqual(d._errors, before)

    def test_destroyed_ui_cannot_skip_cleanup_or_release_new_manager(self):
        d = make_dialog()
        d.app.camera_manager = Mock()  # anderer spaeterer Manager
        d.after.side_effect = RuntimeError("window gone")
        d._destroyed = True
        d._run_test()
        self.assertEqual(d.calls, ["release", "finished"])
        d.app.camera_manager.release.assert_not_called()

    def test_cleanup_exception_still_finishes_and_frees_images(self):
        d = make_dialog()
        d._camera_manager.release = Mock(side_effect=RuntimeError("release failed"))
        d._run_test()
        self.assertTrue(d._worker_done.is_set())
        self.assertTrue(d._errors)
        self.assertEqual(d._test_photos, [])
        self.assertEqual(d.calls[-1], "finished")

    def test_destroy_before_worker_releases_reservation(self):
        d = make_dialog()
        d._worker_started = False
        with patch.object(dialog_module.ctk.CTkToplevel, "destroy"):
            d.destroy()
            d.destroy()
        self.assertEqual(d.calls, ["finished"])
        self.assertTrue(d._worker_done.is_set())

    def test_thread_start_failure_releases_reservation(self):
        d = make_dialog()
        d._worker_started = False
        with patch.object(threading, "Thread", side_effect=RuntimeError("no thread")):
            d._start_test()
        self.assertEqual(d.calls, ["finished"])
        self.assertTrue(d._errors)
        self.assertTrue(d._worker_done.is_set())

    def test_temporary_photo_file_is_removed(self):
        d = make_dialog()
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / "test.jpg"
            photo.touch()
            d._test_file = photo
            d._run_test()
            self.assertFalse(photo.exists())


if __name__ == "__main__":
    # Dev-Pfad wirklich ausfuehren, ohne vorhandene Box-Logs zu rotieren.
    with tempfile.TemporaryDirectory(prefix="fexobooth-camera-tests-") as tmp:
        dev_logging.LOG_PATH = Path(tmp)
        dev_logging.setup_logging(developer_mode=True)
        result = unittest.main(exit=False)
        logging.shutdown()
    sys.exit(not result.result.wasSuccessful())
