"""Dev-Mode muss die Owner-Kette mit Thread und Laufzeiten sichtbar machen."""

import ctypes
import importlib.util
import io
import logging
import sys
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
    def EdsInitializeSDK(self):
        return 0

    def EdsGetEvent(self):
        return 0

    def EdsOpenSession(self, ref):
        return 0

    def EdsTerminateSDK(self):
        return 0


stream = io.StringIO()
handler = logging.StreamHandler(stream)
root_logger = logging.getLogger("fexobooth")
alte_handler = list(root_logger.handlers)
alter_level = root_logger.level
root_logger.handlers = [handler]
root_logger.setLevel(logging.DEBUG)

try:
    edsdk.is_developer_mode = lambda: True
    edsdk.EDSDK_DLL = DLL()
    edsdk.load_edsdk = lambda: True
    edsdk._setup_functions = lambda: None
    edsdk._sdk_initialized = False

    assert edsdk.initialize()
    assert edsdk.open_session(ctypes.c_void_p(123))
finally:
    root_logger.handlers = alte_handler
    root_logger.setLevel(alter_level)

log = stream.getvalue()
for marker in (
    "CANON-OWNER START",
    "CANON-OWNER QUEUED",
    "CANON-OWNER START-OP",
    "CANON-OWNER END-OP",
    "thread=edsdk-kamera/",
    "wait_ms=",
    "call_ms=",
):
    assert marker in log, f"Dev-Logmarker fehlt: {marker}\n{log}"

assert "0x7b" not in log.lower(), "Pointer/Ref-Wert darf nicht geloggt werden"

main_quelle = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
dev_pos = main_quelle.index('developer_mode = "--dev" in sys.argv')
dslr_pos = main_quelle.index('if "--dslr-test" in sys.argv:')
setup_pos = main_quelle.index(
    "setup_logging(developer_mode=developer_mode)", dslr_pos
)
assert dev_pos < dslr_pos < setup_pos

print("BESTANDEN: Dev-Log zeigt Owner, Queue, Thread, Warte- und Laufzeit.")
print("BESTANDEN: --dev aktiviert Logging auch vor dem --dslr-test-Zweig.")
