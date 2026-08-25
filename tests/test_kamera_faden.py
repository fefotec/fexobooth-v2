"""Beweist: ausnahmslos alle getesteten EDSDK-Aufrufe laufen im Owner."""

import ctypes
import importlib.util
import sys
import threading
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


AUFRUFE = []
HANDLER_EVENTS = {}


class DLL:
    def _log(self, name):
        AUFRUFE.append(
            (name, threading.current_thread().name, threading.get_ident())
        )

    def EdsInitializeSDK(self):
        self._log("EdsInitializeSDK")
        return 0

    def EdsOpenSession(self, ref):
        self._log("EdsOpenSession")
        return 0

    def EdsCloseSession(self, ref):
        self._log("EdsCloseSession")
        return 0

    def EdsSetObjectEventHandler(self, ref, event, callback, context):
        self._log("EdsSetObjectEventHandler")
        HANDLER_EVENTS["object"] = event
        return 0

    def EdsSetCameraStateEventHandler(self, ref, event, callback, context):
        self._log("EdsSetCameraStateEventHandler")
        HANDLER_EVENTS["state"] = event
        return 0

    def EdsSetPropertyData(self, *args):
        self._log("EdsSetPropertyData")
        return 0

    def EdsSendStatusCommand(self, ref, command, parameter):
        self._log("EdsSendStatusCommand")
        return 0

    def EdsSetCapacity(self, *args):
        self._log("EdsSetCapacity")
        return 0

    def EdsGetPropertyData(self, ref, prop, index, size, out_value):
        self._log("EdsGetPropertyData")
        if int(prop) == edsdk.kEdsPropID_SaveTo:
            out_value._obj.value = edsdk.kEdsSaveTo_Host
        elif int(prop) == edsdk.kEdsPropID_AvailableShots:
            out_value._obj.value = 100
        else:
            raise AssertionError(f"Unerwartete Property: {int(prop):#x}")
        return 0

    def EdsGetEvent(self):
        self._log("EdsGetEvent")
        return 0

    def EdsRelease(self, ref):
        self._log("EdsRelease")
        return 0

    def EdsTerminateSDK(self):
        self._log("EdsTerminateSDK")
        return 0


edsdk.EDSDK_DLL = DLL()
edsdk.load_edsdk = lambda: True
edsdk._setup_functions = lambda: None
edsdk._sdk_initialized = False

assert edsdk.initialize()
ref = ctypes.c_void_p(123)


def caller(name, fn):
    result = fn()
    assert result is not None, f"{name} lieferte unerwartet None"


threads = [
    threading.Thread(
        target=caller,
        args=("session", lambda: edsdk.open_session(ref)),
        name="system-test",
    ),
    threading.Thread(
        target=caller,
        args=("object", lambda: edsdk.set_object_event_handler(ref, lambda e, o: True)),
        name="handler-anmelder",
    ),
    threading.Thread(
        target=caller,
        args=("state", lambda: edsdk.set_state_event_handler(ref, lambda e, d: None)),
        name="status-anmelder",
    ),
    threading.Thread(
        target=caller,
        args=("save", lambda: edsdk.set_save_to_host(ref)),
        name="capture-worker",
    ),
]

for thread in threads:
    thread.start()
for thread in threads:
    thread.join(timeout=10)
    assert not thread.is_alive(), f"Aufrufer haengt: {thread.name}"

edsdk.dispose_camera(ref, session_open=True)

assert AUFRUFE, "Fake-DLL wurde nie aufgerufen"
falsche = [
    (name, thread, ident)
    for name, thread, ident in AUFRUFE
    if ident != edsdk._sdk_faden.ident
]
assert not falsche, f"EDSDK ausserhalb des Owners: {falsche}"
assert threading.get_ident() != edsdk._sdk_faden.ident
assert HANDLER_EVENTS["object"] == 0x00000200, HANDLER_EVENTS
assert HANDLER_EVENTS["state"] == 0x00000300, HANDLER_EVENTS
assert not any(thread == "edsdk-rueckkanal" for _, thread, _ in AUFRUFE)

print("BESTANDEN: Alle EDSDK-Aufrufe liefen ausschliesslich auf 'edsdk-kamera'.")
print("BESTANDEN: Object=0x200 und State=0x300 wurden registriert.")
