"""Ein Capture-Aufruf sendet genau einen Ausloeser und reicht Fehler weiter."""

import ctypes
import importlib.util
import sys
import threading
import time
from dataclasses import FrozenInstanceError
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
        self.press_result = 0
        self.release_result = 0
        self.press_exception = None
        self.release_exception = None
        self.press_wait = None
        self.press_entered = threading.Event()
        self.commands = []
        self.thread_ids = []

    def EdsInitializeSDK(self):
        return 0

    def EdsGetEvent(self):
        return 0

    def EdsSendCommand(self, ref, command, parameter):
        self.commands.append(parameter)
        self.thread_ids.append(threading.get_ident())
        if parameter == edsdk.kEdsCameraCommand_ShutterButton_OFF:
            if self.release_exception is not None:
                raise self.release_exception
            return self.release_result
        self.press_entered.set()
        if self.press_wait is not None:
            self.press_wait.wait()
        if self.press_exception is not None:
            raise self.press_exception
        return self.press_result

    def EdsTerminateSDK(self):
        return 0


dll = DLL()
edsdk.EDSDK_DLL = dll
edsdk.load_edsdk = lambda: True
edsdk._setup_functions = lambda: None
edsdk._sdk_initialized = False
ref = ctypes.c_void_p(123)


def pruefe(press, release, erwartet, fehler):
    dll.press_result = press
    dll.release_result = release
    dll.commands.clear()
    dll.thread_ids.clear()
    dll.press_exception = None
    dll.release_exception = None
    dll.press_wait = None
    dll.press_entered.clear()
    edsdk.letzter_fehler = 0xDEADBEEF

    assert edsdk.take_picture(ref, live_view_aktiv=True) is erwartet
    assert dll.commands == [
        edsdk.kEdsCameraCommand_ShutterButton_Completely,
        edsdk.kEdsCameraCommand_ShutterButton_OFF,
    ], dll.commands
    assert edsdk.letzter_fehler == fehler, hex(edsdk.letzter_fehler)
    assert len(set(dll.thread_ids)) == 1
    assert dll.thread_ids[0] == edsdk._sdk_faden.ident


pruefe(edsdk.EDS_ERR_OK, edsdk.EDS_ERR_OK, True, edsdk.EDS_ERR_OK)
pruefe(edsdk.EDS_ERR_DEVICE_BUSY, edsdk.EDS_ERR_OK, False, edsdk.EDS_ERR_DEVICE_BUSY)
pruefe(
    edsdk.EDS_ERR_TAKE_PICTURE_AF_NG,
    edsdk.EDS_ERR_OK,
    False,
    edsdk.EDS_ERR_TAKE_PICTURE_AF_NG,
)
pruefe(
    edsdk.EDS_ERR_TAKE_PICTURE_CARD_NG,
    edsdk.EDS_ERR_OK,
    False,
    edsdk.EDS_ERR_TAKE_PICTURE_CARD_NG,
)
pruefe(
    edsdk.EDS_ERR_OK,
    edsdk.EDS_ERR_COMM_DISCONNECTED,
    False,
    edsdk.EDS_ERR_COMM_DISCONNECTED,
)


# Detailmodus: Der Canon-Manager erhaelt dasselbe Ergebnis unveraenderlich und
# mit monoton geordneten Zeiten direkt aus dem Owner-Auftrag.
dll.press_result = edsdk.EDS_ERR_OK
dll.release_result = edsdk.EDS_ERR_OK
dll.commands.clear()
dll.thread_ids.clear()
outcome = edsdk.take_picture(
    ref,
    live_view_aktiv=True,
    capture_id="7.3",
    return_outcome=True,
)
assert isinstance(outcome, edsdk.ShutterCommandOutcome)
assert outcome.capture_id == "7.3"
assert outcome.press_ok and outcome.release_ok and outcome.command_ok
assert (
    outcome.press_start_at
    <= outcome.press_return_at
    <= outcome.release_return_at
)
try:
    outcome.press_ok = False
    raise AssertionError("ShutterCommandOutcome muss eingefroren sein")
except FrozenInstanceError:
    pass


# Scheitert der Hook noch vor dem nativen Press, darf weder Completely noch OFF
# gesendet werden und es gibt folglich keinen akzeptierten Press.
dll.commands.clear()
def hook_fehler():
    raise RuntimeError("arm kaputt")

outcome = edsdk.take_picture(
    ref,
    before_shutter=hook_fehler,
    capture_id="7.4",
    return_outcome=True,
)
assert isinstance(outcome, edsdk.ShutterCommandOutcome)
assert not outcome.press_ok and not outcome.command_ok
assert outcome.press_start_at == 0.0
assert dll.commands == []
assert edsdk.letzter_fehler == edsdk.EDS_ERR_UNEXPECTED_EXCEPTION


# Auch eine echte Exception im begonnenen Press muss den Ausloeser genau einmal
# freigeben. Die Exception wird als synchroner Capture-Fehler sichtbar.
dll.commands.clear()
dll.thread_ids.clear()
dll.press_exception = RuntimeError("press kaputt")
outcome = edsdk.take_picture(ref, capture_id="7.5", return_outcome=True)
assert not outcome.press_ok and outcome.release_ok and not outcome.command_ok
assert outcome.press_exception == "RuntimeError"
assert dll.commands == [
    edsdk.kEdsCameraCommand_ShutterButton_Completely,
    edsdk.kEdsCameraCommand_ShutterButton_OFF,
]
assert edsdk.letzter_fehler == edsdk.EDS_ERR_UNEXPECTED_EXCEPTION


# Press kann akzeptiert sein, obwohl OFF eine Exception wirft. Das ist spaeter
# der bewusste UI-Blitzfall, bleibt fuer den Capture selbst aber ein Fehler.
dll.commands.clear()
dll.thread_ids.clear()
dll.press_exception = None
dll.release_exception = RuntimeError("release kaputt")
outcome = edsdk.take_picture(ref, capture_id="7.6", return_outcome=True)
assert outcome.press_ok and not outcome.release_ok and not outcome.command_ok
assert outcome.release_exception == "RuntimeError"
assert dll.commands == [
    edsdk.kEdsCameraCommand_ShutterButton_Completely,
    edsdk.kEdsCameraCommand_ShutterButton_OFF,
]
assert edsdk.letzter_fehler == edsdk.EDS_ERR_UNEXPECTED_EXCEPTION


# Wenn der native Press laenger als der wartende Worker blockiert, erhaelt
# dieser None. Nach dem spaeteren Entblocken versucht der Owner OFF trotzdem
# genau einmal; ein spaetes Ergebnis kann keinen UI-Callback mehr ausloesen.
dll.commands.clear()
dll.thread_ids.clear()
dll.release_exception = None
dll.press_wait = threading.Event()
dll.press_entered.clear()
timeout_results = []

def timeout_aufruf():
    timeout_results.append(edsdk.im_kamera_faden(
        edsdk.take_picture.__wrapped__,
        ref,
        capture_id="7.7",
        return_outcome=True,
        timeout=0.25,
    ))

caller = threading.Thread(target=timeout_aufruf)
caller.start()
assert dll.press_entered.wait(1.0), "Press-Aufruf hat nicht begonnen"
caller.join(1.0)
assert not caller.is_alive()
assert timeout_results == [None]
dll.press_wait.set()
deadline = time.monotonic() + 1.0
while (
    dll.commands.count(edsdk.kEdsCameraCommand_ShutterButton_OFF) < 1
    and time.monotonic() < deadline
):
    time.sleep(0.01)
assert dll.commands == [
    edsdk.kEdsCameraCommand_ShutterButton_Completely,
    edsdk.kEdsCameraCommand_ShutterButton_OFF,
]

print(
    "BESTANDEN: Genau ein Ausloeser; Outcome, Exceptions, Timeout und OFF "
    "bleiben eindeutig."
)
