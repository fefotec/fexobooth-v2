"""Statischer Smoke-Test für die Nikon-D3300-Unterstützung (digiCamControl).

Prüft NUR statisch (kein Hardware-Zugriff, keine Kamera, kein cv2/numpy nötig),
ob der digiCamControl-Vertrag und die Kamera-Umschaltung im Code vorhanden sind.

Aufruf:
    python tools/nikon_smoke_test.py

Exit-Code 0 = alle Verträge erfüllt, 1 = mindestens ein Check fehlgeschlagen.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _check(condition: bool, label: str, errors: List[str]) -> None:
    if condition:
        print(f"  [OK]   {label}")
    else:
        print(f"  [FAIL] {label}")
        errors.append(label)


def _check_contains(haystack: str, needle: str, label: str, errors: List[str]) -> None:
    _check(needle in haystack, label, errors)


def main() -> int:
    errors: List[str] = []

    # --- Default-Config: Nikon-Block vorhanden und plausibel ---
    from src.config.defaults import DEFAULT_CONFIG

    nikon_cfg = DEFAULT_CONFIG.get("nikon_digicamcontrol", {})
    _check(nikon_cfg.get("port") == 5513, "defaults.py: Nikon digiCamControl-Port = 5513", errors)
    _check(nikon_cfg.get("host") == "127.0.0.1", "defaults.py: Nikon digiCamControl-Host = 127.0.0.1", errors)
    _check("startup_timeout_seconds" in nikon_cfg, "defaults.py: startup_timeout_seconds gesetzt", errors)
    _check("http_timeout_seconds" in nikon_cfg, "defaults.py: http_timeout_seconds gesetzt", errors)

    # --- Kamera-Factory routet Nikon und reicht Config durch ---
    camera_init = _read_text("src/camera/__init__.py")
    _check_contains(camera_init, "from .nikon import NikonCameraManager", "camera/__init__: Nikon-Import", errors)
    _check_contains(camera_init, "NIKON_AVAILABLE = True", "camera/__init__: NIKON_AVAILABLE = True (Import erfolgreich)", errors)
    _check_contains(camera_init, "NIKON_AVAILABLE = False", "camera/__init__: Nikon-Import defensiv (Fallback False)", errors)
    _check_contains(camera_init, 'camera_type == "nikon"', "camera/__init__: Nikon-Routing", errors)
    _check_contains(camera_init, "NikonCameraManager(config=config)", "camera/__init__: Config wird an Nikon übergeben", errors)
    _check_contains(camera_init, "NikonCameraManager is not None", "camera/__init__: Factory-Guard gegen fehlgeschlagenen Nikon-Import", errors)
    _check_contains(camera_init, "def get_camera_manager(camera_type", "camera/__init__: Factory vorhanden", errors)

    # --- Nikon-Manager erfüllt den digiCamControl-Vertrag ---
    nikon = _read_text("src/camera/nikon.py")
    for needle in [
        "DEFAULT_PORT = 5513",
        "CameraControl.exe",
        "liveview.jpg",
        "preview.jpg",
        "Save_to_PC_only",
        "LiveView_Capture",
        "session.folder",
        "session.filenametemplate",
        "lastcaptured",
        "class NikonCameraManager(CameraManager)",
    ]:
        _check_contains(nikon, needle, f"nikon.py: enthält digiCamControl-Vertrag {needle!r}", errors)

    # Drop-in-Interface: alle vom Session-/App-Flow benötigten Methoden vorhanden
    for method in [
        "def initialize(",
        "def get_frame(",
        "def capture_photo(",
        "def get_high_res_frame(",
        "def start_live_view(",
        "def stop_live_view(",
        "def release(",
        "def is_initialized(",
        "def update_config(",
        "def ensure_server_running(",
    ]:
        _check_contains(nikon, method, f"nikon.py: Methode {method!r} vorhanden", errors)

    # --- App: Manager-Rebuild + Nikon-Statuszweig ---
    app = _read_text("src/app.py")
    _check_contains(app, "def _sync_camera_manager_with_config", "app.py: Manager-Rebuild-Methode", errors)
    _check_contains(app, "CANON_AVAILABLE, NIKON_AVAILABLE", "app.py: NIKON_AVAILABLE importiert", errors)
    _check_contains(app, 'get_camera_manager(camera_type, config=self.config)', "app.py: Config an Factory übergeben", errors)
    _check_contains(app, 'elif camera_type == "nikon":', "app.py: Nikon-Statuszweig im Kamera-Check", errors)
    _check_contains(app, '"DCC FEHLT!"', "app.py: Statustext DCC FEHLT!", errors)
    _check_contains(app, '"KEINE NIKON!"', "app.py: Statustext KEINE NIKON!", errors)
    _check_contains(app, "def _warmup_nikon_async", "app.py: digiCamControl-Auto-Start-Warmup vorhanden", errors)
    _check_contains(app, "self._warmup_nikon_async()", "app.py: Warmup wird ausgelöst (Start/Wechsel)", errors)

    # --- Admin: Nikon im Dropdown + bevorzugte DSLR merken ---
    admin = _read_text("src/ui/screens/admin.py")
    _check_contains(admin, 'camera_types.append("nikon")', "admin.py: Nikon im Kameratyp-Dropdown", errors)
    _check_contains(admin, "NikonCameraManager.list_cameras(self.config_data)", "admin.py: Nikon-Kamera-Scan", errors)
    _check_contains(admin, 'self.config_data["dslr_camera_type"] = selected_camera_type', "admin.py: bevorzugte DSLR wird gespeichert", errors)

    # --- Booking: Reload springt nicht hart auf Canon zurück ---
    booking = _read_text("src/storage/booking.py")
    _check_contains(
        booking,
        'config.get("dslr_camera_type") or config.get("camera_type") or "canon"',
        "booking.py: DSLR-Reload respektiert dslr_camera_type",
        errors,
    )
    _check_contains(booking, 'config["dslr_camera_type"] = preferred_dslr', "booking.py: dslr_camera_type wird zurückgeschrieben", errors)

    # --- Service-Reload synchronisiert den Kamera-Manager ---
    service = _read_text("src/ui/screens/service.py")
    _check_contains(service, "_sync_camera_manager_with_config", "service.py: Manager-Sync nach Reload", errors)

    print("")
    if errors:
        print(f"NIKON SMOKE TEST: {len(errors)} Fehler")
        return 1
    print("NIKON SMOKE TEST: alle Verträge erfüllt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
