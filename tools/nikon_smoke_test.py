"""Statischer Smoke-Test für die Nikon-D3300-Unterstützung (FexoNikonBridge).

Prüft NUR statisch (kein Hardware-Zugriff, keine Kamera, kein cv2/numpy nötig),
ob der Bridge-Vertrag (Variante 3) und die Kamera-Umschaltung im Code vorhanden
sind — und dass der verworfene digiCamControl-App-Ansatz (Variante 2) restlos
aus Code, Installer und CI entfernt wurde.

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


def _check_not_contains(haystack: str, needle: str, label: str, errors: List[str]) -> None:
    _check(needle not in haystack, label, errors)


def main() -> int:
    errors: List[str] = []

    # --- Default-Config: Bridge-Block vorhanden, digiCamControl-Block entfernt ---
    from src.config.defaults import DEFAULT_CONFIG

    bridge_cfg = DEFAULT_CONFIG.get("nikon_bridge", {})
    _check("exe_path" in bridge_cfg, "defaults.py: nikon_bridge.exe_path vorhanden", errors)
    _check("init_timeout_seconds" in bridge_cfg, "defaults.py: nikon_bridge.init_timeout_seconds gesetzt", errors)
    _check("command_timeout_seconds" in bridge_cfg, "defaults.py: nikon_bridge.command_timeout_seconds gesetzt", errors)
    _check("capture_timeout_seconds" in bridge_cfg, "defaults.py: nikon_bridge.capture_timeout_seconds gesetzt", errors)
    _check("nikon_digicamcontrol" not in DEFAULT_CONFIG, "defaults.py: alter nikon_digicamcontrol-Block entfernt", errors)

    # --- Kamera-Factory routet Nikon und reicht Config durch ---
    camera_init = _read_text("src/camera/__init__.py")
    _check_contains(camera_init, "from .nikon import NikonCameraManager", "camera/__init__: Nikon-Import", errors)
    _check_contains(camera_init, "NIKON_AVAILABLE = True", "camera/__init__: NIKON_AVAILABLE = True (Import erfolgreich)", errors)
    _check_contains(camera_init, "NIKON_AVAILABLE = False", "camera/__init__: Nikon-Import defensiv (Fallback False)", errors)
    _check_contains(camera_init, 'camera_type == "nikon"', "camera/__init__: Nikon-Routing", errors)
    _check_contains(camera_init, "NikonCameraManager(config=config)", "camera/__init__: Config wird an Nikon übergeben", errors)
    _check_contains(camera_init, "NikonCameraManager is not None", "camera/__init__: Factory-Guard gegen fehlgeschlagenen Nikon-Import", errors)
    _check_contains(camera_init, "def get_camera_manager(camera_type", "camera/__init__: Factory vorhanden", errors)

    # --- Nikon-Manager erfüllt den FexoNikonBridge-Vertrag ---
    nikon = _read_text("src/camera/nikon.py")
    for needle in [
        'BRIDGE_EXE_NAME = "FexoNikonBridge.exe"',
        "CREATE_NO_WINDOW",           # unsichtbarer Prozess, kein Fenster im Kiosk
        '"cmd": cmd',                 # JSON-Kommandos über stdin
        '"ping"',
        '"init"',
        '"lv_start"',
        '"lv_stop"',
        '"frame"',
        '"capture"',
        '"release"',
        "FEXOBOOTH_NIKON_BRIDGE_EXE",
        "class NikonCameraManager(CameraManager)",
        "class _NikonBridgeClient",
    ]:
        _check_contains(nikon, needle, f"nikon.py: enthält Bridge-Vertrag {needle!r}", errors)

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
        "def ensure_bridge_running(",
        "def is_available(",
        "def list_cameras(",
    ]:
        _check_contains(nikon, method, f"nikon.py: Methode {method!r} vorhanden", errors)
    _check_contains(nikon, "NIKON-DIAGNOSE", "nikon.py: Developer-Mode-Diagnose-Logging vorhanden", errors)
    # Verworfener digiCamControl-Ansatz darf nicht zurückkommen:
    _check_not_contains(nikon, "CameraControl.exe", "nikon.py: kein CameraControl.exe-Autostart mehr", errors)
    _check_not_contains(nikon, "5513", "nikon.py: kein digiCamControl-Webserver-Port mehr", errors)
    _check_not_contains(nikon, "urlopen", "nikon.py: kein HTTP-Polling mehr (stdio statt Webserver)", errors)

    # --- App: Manager-Rebuild + Nikon-Statuszweig + Bridge-Warmup ---
    app = _read_text("src/app.py")
    _check_contains(app, "def _sync_camera_manager_with_config", "app.py: Manager-Rebuild-Methode", errors)
    _check_contains(app, "CANON_AVAILABLE, NIKON_AVAILABLE", "app.py: NIKON_AVAILABLE importiert", errors)
    _check_contains(app, 'get_camera_manager(camera_type, config=self.config)', "app.py: Config an Factory übergeben", errors)
    _check_contains(app, 'elif camera_type == "nikon":', "app.py: Nikon-Statuszweig im Kamera-Check", errors)
    _check_contains(app, '"topbar.camera_bridge_missing"', "app.py: Nikon-Bridge-Statustext über i18n", errors)
    _check_contains(app, '"topbar.camera_nikon_missing"', "app.py: Nikon-Kamera-Statustext über i18n", errors)
    _check_contains(app, "def _warmup_nikon_async", "app.py: Bridge-Warmup vorhanden", errors)
    _check_contains(app, "self._warmup_nikon_async()", "app.py: Warmup wird ausgelöst (Start/Wechsel)", errors)
    _check_contains(app, "ensure_bridge_running", "app.py: Warmup nutzt ensure_bridge_running", errors)
    _check_not_contains(app, "ensure_server_running", "app.py: alter digiCamControl-Warmup entfernt", errors)
    _check_not_contains(app, "camera_dcc_missing", "app.py: alter DCC-Statustext entfernt", errors)

    i18n = _read_text("src/i18n.py")
    _check_contains(i18n, '"topbar.camera_bridge_missing"', "i18n.py: Nikon-Bridge-Top-Bar-Key vorhanden", errors)
    _check_contains(i18n, '"topbar.camera_nikon_missing"', "i18n.py: Nikon-Kamera-Top-Bar-Key vorhanden", errors)
    _check_not_contains(i18n, "camera_dcc_missing", "i18n.py: alter DCC-Key entfernt", errors)

    # --- Admin: Nikon im Dropdown + bevorzugte DSLR merken ---
    admin = _read_text("src/ui/screens/admin.py")
    _check_contains(admin, 'camera_types.append("nikon")', "admin.py: Nikon im Kameratyp-Dropdown", errors)
    _check_contains(admin, "NikonCameraManager.list_cameras(self.config_data)", "admin.py: Nikon-Kamera-Scan", errors)
    _check_contains(admin, 'self.config_data["dslr_camera_type"] = selected_camera_type', "admin.py: bevorzugte DSLR wird gespeichert", errors)
    _check_not_contains(admin, "digiCamControl", "admin.py: keine digiCamControl-Beschriftungen mehr", errors)

    # --- Installer/Build/CI: digiCamControl raus, Bridge rein ---
    installer = _read_text("installer.iss")
    build_script = _read_text("build_installer.bat")
    ci = _read_text(".github/workflows/build-release.yml")
    _check_not_contains(installer, "digiCamControlsetup", "installer.iss: digiCamControl-Installer entfernt", errors)
    _check_not_contains(installer, "ShouldInstallDigiCamControl", "installer.iss: DCC-Install-Logik entfernt", errors)
    _check_contains(build_script, "FexoNikonBridge", "build_installer.bat: Bridge wird beigelegt (falls gebaut)", errors)
    _check_not_contains(build_script, "digicamcontrol", "build_installer.bat: DCC-Download entfernt", errors)
    _check_contains(ci, "FexoNikonBridge", "build-release.yml: CI baut die Bridge", errors)
    _check_not_contains(ci, "digiCamControlsetup", "build-release.yml: DCC-Download entfernt", errors)

    # --- OTA-Update-Pfade liefern bridge/ mit aus (sonst erreicht Nikon nie bestehende Boxen) ---
    updater_py = _read_text("src/updater.py")
    ota_bat = _read_text("update_from_github.bat")
    _check_contains(updater_py, 'SOURCE_DIR%\\\\bridge', "updater.py: OTA-BAT kopiert bridge/ mit", errors)
    _check_contains(updater_py, "FexoNikonBridge.exe", "updater.py: OTA-BAT beendet/prueft die Bridge", errors)
    _check_contains(ota_bat, 'SOURCE_DIR%\\bridge', "update_from_github.bat: kopiert bridge/ mit", errors)
    _check_contains(ota_bat, "taskkill /F /IM \"FexoNikonBridge.exe\"", "update_from_github.bat: beendet laufende Bridge vor dem Kopieren", errors)

    # --- Bridge-Projekt: Gerüst vorhanden + richtige Basis ---
    csproj = _read_text("bridge/FexoNikonBridge/FexoNikonBridge.csproj")
    program = _read_text("bridge/FexoNikonBridge/Program.cs")
    _check_contains(csproj, "CameraControl.Devices", "csproj: CameraControl.Devices (MIT) als Motor", errors)
    _check_contains(csproj, "<TargetFramework>net48</TargetFramework>", "csproj: net48 (auf Win10/11 vorinstalliert)", errors)
    for needle in ['"ping"', '"list"', '"init"', '"lv_start"', '"lv_stop"', '"frame"', '"capture"', '"release"', '"quit"']:
        _check_contains(program, needle, f"Program.cs: Kommando {needle} implementiert", errors)
    _check_contains(program, "GetLiveViewImage", "Program.cs: LiveView über CameraControl.Devices", errors)
    _check_contains(program, "CaptureInSdRam", "Program.cs: Capture in den RAM (keine SD-Karte nötig)", errors)
    _check_contains(program, "TransferFile", "Program.cs: Vollbild-Transfer implementiert", errors)

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
