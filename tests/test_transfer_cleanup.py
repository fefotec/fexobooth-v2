"""Ein fehlgeschlagener Host-Download muss Cancel senden und Streams freigeben."""

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
        self.cancel = []
        self.release = []

    def EdsInitializeSDK(self):
        return 0

    def EdsGetEvent(self):
        return 0

    def EdsGetDirectoryItemInfo(self, ref, out_info):
        out_info._obj.size = 1024
        return 0

    def EdsCreateMemoryStream(self, size, out_stream):
        out_stream._obj.value = 789
        return 0

    def EdsDownload(self, ref, size, stream):
        return 0x00000002  # INTERNAL_ERROR

    def EdsDownloadCancel(self, ref):
        self.cancel.append(threading.current_thread().name)
        return 0

    def EdsRelease(self, ref):
        self.release.append(threading.current_thread().name)
        return 0

    def EdsTerminateSDK(self):
        return 0


dll = DLL()
edsdk.EDSDK_DLL = dll
edsdk.load_edsdk = lambda: True
edsdk._setup_functions = lambda: None
edsdk._sdk_initialized = False

result = edsdk.download_image_to_memory(ctypes.c_void_p(456))

assert result is None
assert dll.cancel == ["edsdk-kamera"], dll.cancel
assert dll.release == ["edsdk-kamera"], dll.release

print("BESTANDEN: Downloadfehler -> Cancel und Stream-Release im Owner.")
