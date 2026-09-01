"""Best-effort-Developerdiagnose fuer die Nikon-Bridge.

Dieses Modul enthaelt bewusst nur Standardbibliotheks-Logik. Windows-Module
wie psutil und win32api werden erst im Diagnose-Thread importiert. Bei
ausgeschaltetem Developer Mode startet weder ein Thread noch ein Subprozess
oder Datei-Hash.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logging import get_logger

logger = get_logger(__name__)

_STATE_LOCK = threading.Lock()
_DIAG_LAST_STARTED: Dict[str, float] = {}
_DIAG_IN_FLIGHT: set[str] = set()
_INVENTORY_STARTED: set[str] = set()
_WINDOWS_LAST_STARTED: Optional[float] = None
_WINDOWS_IN_FLIGHT = False

_WINDOWS_SNAPSHOT_INTERVAL_SECONDS = 60.0
_MAX_LOG_JSON_CHARS = 24000

_PNP_SCRIPT = r"""
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$devices=@(
  Get-CimInstance -ClassName Win32_PnPEntity -OperationTimeoutSec 5 -ErrorAction Stop |
    Where-Object {
      $blob=@($_.Name,$_.Manufacturer,$_.PNPClass,$_.Status,$_.Service,$_.PNPDeviceID,$_.DeviceID)-join ' '
      $_.PNPClass -match '^(Camera|Image|WPD)$' -or
        $blob -match '(?i)(Nikon|D3300|VID_04B0|Portable Device|Still Image)' -or
        $blob -match '(?i)(^|[^A-Z])(MTP|PTP)([^A-Z]|$)'
    } |
    Select-Object -First 48 `
      @{n='name';e={$_.Name}},
      @{n='manufacturer';e={$_.Manufacturer}},
      @{n='pnp_class';e={$_.PNPClass}},
      @{n='status';e={$_.Status}},
      @{n='service';e={$_.Service}},
      @{n='pnp_device_id';e={if ($_.PNPDeviceID) {$_.PNPDeviceID} else {$_.DeviceID}}},
      @{n='config_error';e={$_.ConfigManagerErrorCode}}
)
@{devices=$devices}|ConvertTo-Json -Compress -Depth 4
""".strip()


def developer_diagnostics_enabled(config: Optional[Dict[str, Any]]) -> bool:
    return bool((config or {}).get("developer_mode"))


def schedule_bridge_diagnostics(
    client: Any,
    config: Optional[Dict[str, Any]],
    context: str,
    *,
    minimum_interval_seconds: float = 0.0,
    throttle_key: Optional[str] = None,
) -> bool:
    """Fragt `diag` asynchron ab; alte Bridges bleiben kompatibel."""
    if not developer_diagnostics_enabled(config):
        return False

    context = _short_text(context, 160)
    key = throttle_key or context
    now = time.monotonic()
    with _STATE_LOCK:
        if key in _DIAG_IN_FLIGHT:
            return False
        last_started = _DIAG_LAST_STARTED.get(key)
        if last_started is not None and now - last_started < max(0.0, minimum_interval_seconds):
            return False
        _DIAG_LAST_STARTED[key] = now
        _DIAG_IN_FLIGHT.add(key)

    def worker() -> None:
        try:
            if not client.is_running():
                logger.info(
                    "NIKON-DIAGNOSE BRIDGE context=%s result=bridge_not_running",
                    context,
                )
                return
            header, _ = client.request("diag", timeout=2.0)
            diagnostics = header.get("diagnostics") if isinstance(header, dict) else None
            if not isinstance(diagnostics, dict):
                logger.info(
                    "NIKON-DIAGNOSE BRIDGE context=%s result=invalid_schema",
                    context,
                )
                return
            diagnostics = _sanitize_bridge_diagnostics(diagnostics)
            logger.info(
                "NIKON-DIAGNOSE BRIDGE context=%s snapshot=%s",
                context,
                _bounded_json(diagnostics),
            )
        except Exception as exc:
            message = _short_text(str(exc), 500)
            lowered = message.lower()
            if "unbekanntes kommando" in lowered and "diag" in lowered:
                logger.info(
                    "NIKON-DIAGNOSE BRIDGE context=%s result=unsupported_old_bridge",
                    context,
                )
            else:
                logger.info(
                    "NIKON-DIAGNOSE BRIDGE context=%s result=failed error=%s",
                    context,
                    message,
                )
        finally:
            with _STATE_LOCK:
                _DIAG_IN_FLIGHT.discard(key)

    try:
        threading.Thread(
            target=worker,
            daemon=True,
            name="nikon-bridge-diag",
        ).start()
    except Exception as exc:
        with _STATE_LOCK:
            _DIAG_IN_FLIGHT.discard(key)
            _DIAG_LAST_STARTED.pop(key, None)
        _safe_info(
            "NIKON-DIAGNOSE BRIDGE context=%s result=thread_start_failed error=%s",
            context,
            _short_text(str(exc), 500),
        )
        return False
    return True


def schedule_bridge_inventory(
    bridge_exe: Path,
    config: Optional[Dict[str, Any]],
) -> bool:
    """Inventarisiert einmal pro App-Start nur den verwendeten Bridge-Ordner."""
    if not developer_diagnostics_enabled(config):
        return False
    try:
        exe_path = Path(bridge_exe).resolve()
        directory_key = os.path.normcase(str(exe_path.parent))
    except Exception as exc:
        _safe_info(
            "NIKON-DIAGNOSE INVENTAR result=path_error error=%s",
            _short_text(str(exc), 500),
        )
        return False

    with _STATE_LOCK:
        if directory_key in _INVENTORY_STARTED:
            return False
        _INVENTORY_STARTED.add(directory_key)

    def worker() -> None:
        try:
            inventory = collect_bridge_inventory(exe_path)
            logger.info(
                "NIKON-DIAGNOSE INVENTAR directory=%s files=%s",
                _short_text(str(exe_path.parent), 500),
                _bounded_json(inventory),
            )
        except Exception as exc:
            logger.info(
                "NIKON-DIAGNOSE INVENTAR result=failed error=%s",
                _short_text(str(exc), 500),
            )

    try:
        threading.Thread(
            target=worker,
            daemon=True,
            name="nikon-bridge-inventory",
        ).start()
    except Exception as exc:
        with _STATE_LOCK:
            _INVENTORY_STARTED.discard(directory_key)
        _safe_info(
            "NIKON-DIAGNOSE INVENTAR result=thread_start_failed error=%s",
            _short_text(str(exc), 500),
        )
        return False
    return True


def collect_bridge_inventory(bridge_exe: Path) -> List[Dict[str, Any]]:
    exe_path = Path(bridge_exe).resolve()
    directory = exe_path.parent
    result: List[Dict[str, Any]] = []
    candidates = sorted(
        (
            path
            for path in directory.iterdir()
            if path.suffix.lower() in {".exe", ".dll"} and not path.is_symlink()
        ),
        key=lambda path: path.name.lower(),
    )[:64]
    for path in candidates:
        item: Dict[str, Any] = {"name": _short_text(path.name, 240)}
        try:
            item["size"] = path.stat().st_size
            item["sha256"] = hash_file(path)
        except Exception as exc:
            item["file_error"] = _short_text(f"{type(exc).__name__}: {exc}", 300)
        try:
            item["file_version"] = file_version(path)
        except Exception as exc:
            item["version_error"] = _short_text(f"{type(exc).__name__}: {exc}", 300)
        result.append(item)
    return result


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def file_version(path: Path) -> Optional[str]:
    if os.name != "nt":
        return None
    import win32api  # type: ignore[import-not-found]

    info = win32api.GetFileVersionInfo(str(path), "\\")
    ms = int(info["FileVersionMS"])
    ls = int(info["FileVersionLS"])
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def schedule_windows_snapshot(
    config: Optional[Dict[str, Any]],
    context: str,
) -> bool:
    """Startet den read-only Windows-Snapshot hoechstens einmal pro Minute."""
    global _WINDOWS_IN_FLIGHT, _WINDOWS_LAST_STARTED

    if not developer_diagnostics_enabled(config) or os.name != "nt":
        return False
    now = time.monotonic()
    with _STATE_LOCK:
        if _WINDOWS_IN_FLIGHT:
            return False
        if (
            _WINDOWS_LAST_STARTED is not None
            and now - _WINDOWS_LAST_STARTED < _WINDOWS_SNAPSHOT_INTERVAL_SECONDS
        ):
            return False
        _WINDOWS_IN_FLIGHT = True
        _WINDOWS_LAST_STARTED = now

    context = _short_text(context, 160)

    def worker() -> None:
        global _WINDOWS_IN_FLIGHT
        try:
            snapshot: Dict[str, Any] = {"context": context}
            try:
                snapshot["pnp"] = collect_windows_pnp()
            except Exception as exc:
                snapshot["pnp"] = {
                    "error": _short_text(f"{type(exc).__name__}: {exc}", 500)
                }
            try:
                snapshot["processes"] = collect_relevant_processes()
            except Exception as exc:
                snapshot["processes"] = {
                    "error": _short_text(f"{type(exc).__name__}: {exc}", 500)
                }
            logger.info("NIKON-DIAGNOSE WINDOWS snapshot=%s", _bounded_json(snapshot))
        finally:
            with _STATE_LOCK:
                _WINDOWS_IN_FLIGHT = False

    try:
        threading.Thread(
            target=worker,
            daemon=True,
            name="nikon-windows-diag",
        ).start()
    except Exception as exc:
        with _STATE_LOCK:
            _WINDOWS_IN_FLIGHT = False
            _WINDOWS_LAST_STARTED = None
        _safe_info(
            "NIKON-DIAGNOSE WINDOWS result=thread_start_failed error=%s",
            _short_text(str(exc), 500),
        )
        return False
    return True


def collect_windows_pnp() -> Dict[str, Any]:
    encoded_script = base64.b64encode(_PNP_SCRIPT.encode("utf-16le")).decode("ascii")
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded_script,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=8,
        check=False,
        creationflags=creationflags,
    )
    stdout = completed.stdout.decode("utf-8-sig", errors="replace").strip()
    stderr = completed.stderr.decode("utf-8-sig", errors="replace").strip()
    if completed.returncode != 0:
        raise RuntimeError(
            f"PowerShell exit={completed.returncode}; stderr={_short_text(stderr, 500)}"
        )
    if not stdout:
        raise RuntimeError("PowerShell lieferte keine PnP-Daten")
    raw = json.loads(stdout)
    devices = raw.get("devices", []) if isinstance(raw, dict) else []
    if isinstance(devices, dict):
        devices = [devices]
    if not isinstance(devices, list):
        raise ValueError("Unerwartetes PnP-JSON-Schema")
    sanitized = [_sanitize_pnp_device(item) for item in devices[:48] if isinstance(item, dict)]
    return {"device_count": len(sanitized), "devices": sanitized}


def _sanitize_pnp_device(item: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "name",
        "manufacturer",
        "pnp_class",
        "status",
        "service",
        "pnp_device_id",
        "config_error",
    )
    result: Dict[str, Any] = {}
    for key in keys:
        value = item.get(key)
        if value is None or isinstance(value, (int, float, bool)):
            result[key] = value
        else:
            result[key] = _short_text(str(value), 500)

    identity_blob = " ".join(
        str(item.get(key) or "")
        for key in ("name", "manufacturer", "pnp_class", "pnp_device_id")
    ).lower()
    is_nikon_identity = (
        "nikon" in identity_blob
        or "d3300" in identity_blob
        or "vid_04b0" in identity_blob
    )
    if not is_nikon_identity and result.get("pnp_device_id"):
        result["pnp_device_id"] = "<redacted-non-camera-wpd>"
    return result


def _sanitize_bridge_diagnostics(diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    """Laesst Nikon-IDs sichtbar, redigiert zufaellige fremde WPD-Geraete."""
    result = dict(diagnostics)

    devices = diagnostics.get("connected_devices")
    if isinstance(devices, list):
        result["connected_devices"] = [
            _sanitize_bridge_device(item) for item in devices[:32] if isinstance(item, dict)
        ]

    camera = diagnostics.get("camera")
    if isinstance(camera, dict):
        result["camera"] = _sanitize_bridge_device(camera)

    last_exception = diagnostics.get("last_exception")
    if isinstance(last_exception, dict):
        result["last_exception"] = {
            key: _redact_non_nikon_device_ids(value) if isinstance(value, str) else value
            for key, value in last_exception.items()
        }

    device_snapshot_error = diagnostics.get("device_snapshot_error")
    if isinstance(device_snapshot_error, str):
        result["device_snapshot_error"] = _redact_non_nikon_device_ids(device_snapshot_error)

    for output_key, maximum_lines in (("library_output", 100), ("library_errors", 40)):
        output = diagnostics.get(output_key)
        if not isinstance(output, list):
            continue
        sanitized_lines: List[str] = []
        for raw_line in output[-maximum_lines:]:
            sanitized_lines.append(_redact_non_nikon_device_ids(raw_line))
        result[output_key] = sanitized_lines
    return result


def _redact_non_nikon_device_ids(value: Any) -> str:
    """Redigiert nur ID-Tokens; Fehlerart, HRESULT und Busy-Text bleiben stehen."""
    line = _short_text(value, 1100)
    lowered = line.lower()
    is_nikon_line = "nikon" in lowered or "d3300" in lowered or "vid_04b0" in lowered

    if not is_nikon_line:
        line = re.sub(
            r'(?i)(\bconnection device\s+)("[^"]+"|\S+)',
            r"\1<redacted-non-nikon-device>",
            line,
            count=1,
        )

    def replace_identifier(match: re.Match[str]) -> str:
        identifier = match.group(0)
        if "vid_04b0" in identifier.lower():
            return identifier
        return "<redacted-non-nikon-device>"

    line = re.sub(
        r"(?i)(?:\\\\\?\\)?(?:swd|wpd)(?:\\|#)wpdbusenum(?:\\|#)[^\s|;,]+",
        replace_identifier,
        line,
    )
    line = re.sub(
        r"(?i)(?:\\\\\?\\)?usb(?:\\|#)vid_[0-9a-f]{4}[^\s|;,]*",
        replace_identifier,
        line,
    )
    return line


def _sanitize_bridge_device(item: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(item)
    identity = " ".join(
        str(item.get(key) or "")
        for key in ("type", "name", "manufacturer", "serial", "port")
    ).lower()
    if not ("nikon" in identity or "d3300" in identity or "vid_04b0" in identity):
        if result.get("serial"):
            result["serial"] = "<redacted-non-nikon-device>"
        if result.get("port") and ("usb" in identity or "wpd" in identity or "mtp" in identity):
            result["port"] = "<redacted-non-nikon-device>"
    property_errors = item.get("property_errors")
    if isinstance(property_errors, list):
        result["property_errors"] = [
            _redact_non_nikon_device_ids(value) for value in property_errors[:16]
        ]
    return result


def collect_relevant_processes() -> Dict[str, Any]:
    import psutil  # type: ignore[import-not-found]

    processes: List[Dict[str, Any]] = []
    fexobooth_count = 0
    bridge_count = 0
    competitor_count = 0
    match_fragments = (
        "fexobooth",
        "fexonikonbridge",
        "dslrbooth",
        "digicamcontrol",
        "cameracontrol",
        "nikon",
        "nxstudio",
        "nx studio",
        "nkremote",
        "nktransfer",
    )
    for process in psutil.process_iter(["pid", "name"]):
        try:
            name = str(process.info.get("name") or "")
            pid = int(process.info.get("pid"))
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError, ValueError):
            continue
        lowered = name.lower()
        if "fexobooth" in lowered:
            fexobooth_count += 1
        if "fexonikonbridge" in lowered:
            bridge_count += 1
        if not any(fragment in lowered for fragment in match_fragments):
            continue
        is_own_process = "fexobooth" in lowered or "fexonikonbridge" in lowered
        if not is_own_process:
            competitor_count += 1
        if len(processes) < 64:
            processes.append(
                {
                    "name": _short_text(name, 240),
                    "pid": pid,
                    "role": "own" if is_own_process else "possible_competitor",
                }
            )
    return {
        "fexobooth_count": fexobooth_count,
        "bridge_count": bridge_count,
        "possible_competitor_count": competitor_count,
        "classification": (
            "possible_competitor_process_active" if competitor_count else "none_seen"
        ),
        "items": processes,
    }


def _bounded_json(value: Any) -> str:
    """Erzeugt stets gueltiges JSON und behält Kernfelder auch bei grossen Listen."""
    last_error: Optional[Exception] = None
    for maximum_items, maximum_text in (
        (32, 1000),
        (16, 700),
        (8, 500),
        (4, 300),
        (1, 200),
        (0, 160),
    ):
        truncated = [False]
        limited = _limit_log_value(
            value,
            maximum_items=maximum_items,
            maximum_text=maximum_text,
            key="",
            truncated=truncated,
        )
        if truncated[0] and isinstance(limited, dict):
            limited["_log_truncated"] = True
        try:
            text = json.dumps(
                limited,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
        except Exception as exc:
            last_error = exc
            continue
        if len(text) <= _MAX_LOG_JSON_CHARS:
            return text

    # Selbst bei einem unerwartet riesigen Schema bleibt das Ergebnis valides
    # JSON und der wichtigste strukturierte Fehler sichtbar.
    fallback: Dict[str, Any] = {"_log_truncated": True}
    if isinstance(value, dict):
        for key in (
            "context",
            "bridge_version",
            "pid",
            "manager_created",
            "camera_initialized",
            "last_scan",
            "last_init_result",
            "last_exception",
            "error",
        ):
            if key in value:
                fallback[key] = _limit_log_value(
                    value[key],
                    maximum_items=1,
                    maximum_text=160,
                    key=key,
                    truncated=[True],
                )
    if last_error is not None:
        fallback["serialization_error"] = _short_text(str(last_error), 300)
    return json.dumps(fallback, ensure_ascii=False, separators=(",", ":"), default=str)


def _limit_log_value(
    value: Any,
    *,
    maximum_items: int,
    maximum_text: int,
    key: str,
    truncated: List[bool],
) -> Any:
    if isinstance(value, dict):
        return {
            _short_text(name, 120): _limit_log_value(
                child,
                maximum_items=maximum_items,
                maximum_text=maximum_text,
                key=str(name),
                truncated=truncated,
            )
            for name, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        items = list(value)
        if len(items) > maximum_items:
            truncated[0] = True
            items = (
                items[-maximum_items:]
                if key in {"library_output", "library_errors"} and maximum_items
                else items[:maximum_items]
            )
        return [
            _limit_log_value(
                item,
                maximum_items=maximum_items,
                maximum_text=maximum_text,
                key=key,
                truncated=truncated,
            )
            for item in items
        ]
    if isinstance(value, str):
        shortened = _short_text(value, maximum_text)
        if shortened != value:
            truncated[0] = True
        return shortened
    if value is None or isinstance(value, (int, float, bool)):
        return value
    text = _short_text(value, maximum_text)
    truncated[0] = True
    return text


def _safe_info(message: str, *args: Any) -> None:
    try:
        logger.info(message, *args)
    except Exception:
        pass


def _short_text(value: Any, maximum_length: int) -> str:
    text = "" if value is None else str(value)
    if len(text) <= maximum_length:
        return text
    return text[:maximum_length] + "...[truncated]"


def reset_diagnostic_state_for_tests() -> None:
    """Setzt nur die modulinterne Drosselung fuer isolierte Tests zurueck."""
    global _WINDOWS_IN_FLIGHT, _WINDOWS_LAST_STARTED
    with _STATE_LOCK:
        _DIAG_LAST_STARTED.clear()
        _DIAG_IN_FLIGHT.clear()
        _INVENTORY_STARTED.clear()
        _WINDOWS_LAST_STARTED = None
        _WINDOWS_IN_FLIGHT = False
