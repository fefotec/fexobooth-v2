"""Ein Capture-Aufruf sendet genau einen Ausloeser und reicht Fehler weiter."""

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


class DLL:
    def __init__(self):
        self.press_result = 0
        self.release_result = 0
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
            return self.release_result
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

print("BESTANDEN: Genau ein Ausloeser; Capture- und OFF-Fehler bleiben sichtbar.")
