"""Ein nativer Haenger darf weder UI blockieren noch Auftraege stapeln."""

import ctypes
import importlib.util
import sys
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


class HaengendeDLL:
    def __init__(self):
        self.registrierungen = 0

    def EdsInitializeSDK(self):
        return 0

    def EdsGetEvent(self):
        return 0

    def EdsSetObjectEventHandler(self, ref, event, callback, context):
        self.registrierungen += 1
        time.sleep(60)
        return 0

    def EdsTerminateSDK(self):
        return 0


dll = HaengendeDLL()
edsdk.EDSDK_DLL = dll
edsdk.load_edsdk = lambda: True
edsdk._setup_functions = lambda: None
edsdk._sdk_initialized = False

ref = ctypes.c_void_p(123)
t0 = time.monotonic()
result = edsdk.set_object_event_handler(ref, lambda event, obj: True)
erste_dauer = time.monotonic() - t0

assert result is None, result
assert erste_dauer < 6.0, erste_dauer
assert dll.registrierungen == 1

# Der erste native Aufruf lebt weiter im einzigen Owner. Weitere Auftraege
# werden sofort abgewiesen, statt weitere Zombie-Threads zu erzeugen.
t1 = time.monotonic()
zweites = edsdk.set_object_event_handler(ref, lambda event, obj: True)
zweite_dauer = time.monotonic() - t1

assert zweites is None
assert zweite_dauer < 0.5, zweite_dauer
assert dll.registrierungen == 1
assert "healthy=False" in edsdk.owner_snapshot()

print("BESTANDEN: Nativer Haenger nach 5s gemeldet; kein zweiter Aufruf gestapelt.")
