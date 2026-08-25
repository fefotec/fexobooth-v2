"""Der native Callback darf keinen Download oder Nutzer-Callback reentrant ausfuehren."""

import ctypes
import importlib.util
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if not hasattr(ctypes, "WINFUNCTYPE"):
    ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE

spec = importlib.util.spec_from_file_location(
    "fexobooth_test_edsdk", ROOT / "src" / "camera" / "edsdk.py"
)
edsdk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edsdk)


class DLL:
    def __init__(self):
        self.object_callback = None
        self.pending = False
        self.im_native_callback = False
        self.releases = []

    def EdsInitializeSDK(self):
        return 0

    def EdsSetObjectEventHandler(self, ref, event, callback, context):
        self.object_callback = callback
        return 0

    def EdsGetEvent(self):
        if self.pending and self.object_callback is not None:
            self.pending = False
            self.im_native_callback = True
            self.object_callback(
                edsdk.kEdsObjectEvent_DirItemRequestTransfer,
                ctypes.c_void_p(456),
                None,
            )
            self.im_native_callback = False
        return 0

    def EdsRelease(self, ref):
        self.releases.append(threading.current_thread().name)
        return 0

    def EdsDownloadCancel(self, ref):
        raise AssertionError("Erfolgreich behandelter Transfer darf nicht gecancelt werden")

    def EdsTerminateSDK(self):
        return 0


dll = DLL()
edsdk.EDSDK_DLL = dll
edsdk.load_edsdk = lambda: True
edsdk._setup_functions = lambda: None
edsdk._sdk_initialized = False

fertig = threading.Event()
beobachtung = {}


def user_callback(event, obj_ref):
    beobachtung["reentrant"] = dll.im_native_callback
    beobachtung["thread"] = threading.current_thread().name
    beobachtung["event"] = event
    fertig.set()
    return True


assert edsdk.set_object_event_handler(ctypes.c_void_p(123), user_callback)
dll.pending = True
assert fertig.wait(3.0), "Transfer-Folgeauftrag wurde nicht ausgefuehrt"

deadline = time.monotonic() + 2.0
while len(dll.releases) < 1 and time.monotonic() < deadline:
    time.sleep(0.01)

assert beobachtung["reentrant"] is False
assert beobachtung["thread"] == "edsdk-kamera"
assert beobachtung["event"] == 0x00000208
assert dll.releases == ["edsdk-kamera"], dll.releases

print("BESTANDEN: Callback kehrt zuerst zur DLL zurueck; Verarbeitung danach im Owner.")
