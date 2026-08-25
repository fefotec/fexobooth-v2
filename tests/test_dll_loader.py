"""Der installierte One-Folder-Build findet Canon-DLLs unter `_internal`."""

import ctypes
import importlib.util
import sys
import tempfile
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

hat_meipass = hasattr(edsdk.sys, "_MEIPASS")
alter_meipass = getattr(edsdk.sys, "_MEIPASS", None)
alter_platform = edsdk.sys.platform
alter_add = getattr(edsdk.os, "add_dll_directory", None)
hat_windll = hasattr(edsdk.ctypes, "WinDLL")
alter_windll = getattr(edsdk.ctypes, "WinDLL", None)

try:
    with tempfile.TemporaryDirectory() as tmp:
        internal = Path(tmp) / "_internal"
        internal.mkdir()
        (internal / "EDSDK.dll").write_bytes(b"fake")
        (internal / "EdsImage.dll").write_bytes(b"fake")
        edsdk.sys._MEIPASS = str(internal)

        assert Path(edsdk._find_edsdk_dll()) == internal

        handle = object()
        fake_dll = object()
        edsdk.EDSDK_DLL = None
        edsdk._dll_directory_handles.clear()
        edsdk.sys.platform = "win32"
        edsdk.os.add_dll_directory = lambda pfad: handle
        edsdk.ctypes.WinDLL = lambda pfad: fake_dll

        assert edsdk.load_edsdk()
        assert edsdk.EDSDK_DLL is fake_dll
        assert edsdk._dll_directory_handles == [handle]
finally:
    edsdk.sys.platform = alter_platform
    if hat_meipass:
        edsdk.sys._MEIPASS = alter_meipass
    else:
        try:
            del edsdk.sys._MEIPASS
        except AttributeError:
            pass
    if alter_add is None:
        try:
            del edsdk.os.add_dll_directory
        except AttributeError:
            pass
    else:
        edsdk.os.add_dll_directory = alter_add
    if hat_windll:
        edsdk.ctypes.WinDLL = alter_windll
    else:
        try:
            del edsdk.ctypes.WinDLL
        except AttributeError:
            pass

print("BESTANDEN: PyInstaller-_internal wird zuerst gefunden; DLL-Pfad bleibt aktiv.")
