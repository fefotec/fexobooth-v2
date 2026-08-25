"""Gleicht kritische Canon-Konstanten direkt mit EDSDKTypes.h ab."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
quelle = (ROOT / "src" / "camera" / "edsdk.py").read_text(encoding="utf-8")
header = (
    ROOT
    / "EDSDK"
    / "EDSDKv132010W"
    / "EDSDKv132010W"
    / "Windows"
    / "EDSDK"
    / "Header"
    / "EDSDKTypes.h"
).read_text(encoding="utf-8", errors="replace")

NAMEN = [
    "EdsImageQuality_LJF",
    "EdsImageQuality_LJN",
    "EdsImageQuality_MJF",
    "EdsImageQuality_SJF",
    "kEdsObjectEvent_All",
    "kEdsObjectEvent_DirItemCreated",
    "kEdsObjectEvent_DirItemRequestTransfer",
    "kEdsStateEvent_All",
    "kEdsStateEvent_Shutdown",
    "kEdsStateEvent_WillSoonShutDown",
    "kEdsStateEvent_CaptureError",
    "kEdsStateEvent_InternalError",
    "kEdsPropID_SaveTo",
    "kEdsPropID_AvailableShots",
    "kEdsPropID_MeteringMode",
    "kEdsPropID_ExposureCompensation",
    "kEdsPropID_Evf_ViewType",
    "kEdsCameraStatusCommand_UILock",
    "kEdsCameraStatusCommand_UIUnLock",
]


def wert(text: str, name: str) -> int:
    match = re.search(
        rf"\b{re.escape(name)}\s*(?:=|\s)\s*(0x[0-9a-fA-F]+)", text
    )
    assert match, f"Konstante fehlt: {name}"
    return int(match.group(1), 16)


for name in NAMEN:
    ist = wert(quelle, name)
    soll = wert(header, name)
    assert ist == soll, f"{name}: Code={ist:#010x}, Canon={soll:#010x}"

assert "0x0000a101" not in re.search(
    r"HARMLOS\s*=\s*\{(.*?)\}", quelle, re.S
).group(1), "LOW_BATTERY darf nicht als harmlos gelten"

assert "EDSDK_DLL.EdsSendStatusCommand.argtypes = [c_void_p, c_uint, c_int]" in quelle

print(f"BESTANDEN: {len(NAMEN)} Konstanten stimmen mit dem Canon-Header ueberein.")
