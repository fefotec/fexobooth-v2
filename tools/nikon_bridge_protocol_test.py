"""Protokolltest fuer eine frisch gebaute FexoNikonBridge ohne Kamera-Scan."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = (
    ROOT
    / "bridge"
    / "FexoNikonBridge"
    / "bin"
    / "Release"
    / "net48"
    / "FexoNikonBridge.exe"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _read_responses(stdout: bytes) -> List[Dict[str, Any]]:
    responses: List[Dict[str, Any]] = []
    for raw_line in stdout.splitlines():
        if not raw_line.strip():
            continue
        value = json.loads(raw_line.decode("utf-8", errors="strict"))
        _require(isinstance(value, dict), "Antwort ist kein JSON-Objekt")
        responses.append(value)
    return responses


def _exchange(
    executable: Path,
    requests: List[Dict[str, Any]],
    *,
    developer_diagnostics: bool,
) -> List[Dict[str, Any]]:
    request_bytes = b"".join(
        (json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8")
        for request in requests
    )
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    command = [str(executable)]
    if developer_diagnostics:
        command.append("--developer-diagnostics")
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(executable.parent),
        creationflags=creationflags,
    )
    try:
        stdout, stderr = process.communicate(input=request_bytes, timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise AssertionError("Bridge-Protokolltest: Prozess-Timeout")

    _require(process.returncode == 0, f"Bridge Exit-Code {process.returncode}: {stderr[:500]!r}")
    return _read_responses(stdout)


def run_protocol_test(executable: Path) -> None:
    executable = executable.resolve()
    _require(executable.is_file(), f"Bridge-EXE fehlt: {executable}")

    requests = [
        {"id": 1, "cmd": "ping"},
        {"id": 2, "cmd": "diag"},
        {"id": 3, "cmd": "does_not_exist"},
        {"id": 4, "cmd": "quit"},
    ]
    responses = _exchange(executable, requests, developer_diagnostics=True)
    _require(len(responses) == 4, f"Erwartet 4 Antworten, erhalten: {len(responses)}")

    ping, diagnostics_reply, unknown, quit_reply = responses
    _require(ping.get("id") == 1 and ping.get("ok") is True, "ping fehlgeschlagen")
    _require(ping.get("bridge") == "FexoNikonBridge", "ping: falscher Bridge-Name")
    _require(ping.get("version") == "0.2.0", "ping: Bridge-Version ist nicht 0.2.0")

    diagnostics = diagnostics_reply.get("diagnostics")
    _require(
        diagnostics_reply.get("id") == 2
        and diagnostics_reply.get("ok") is True
        and isinstance(diagnostics, dict),
        "diag fehlgeschlagen",
    )
    _require(diagnostics.get("bridge_version") == "0.2.0", "diag: falsche Version")
    _require(
        diagnostics.get("developer_diagnostics_enabled") is True,
        "diag: Developer-Diagnose wurde nicht aktiviert",
    )
    _require(diagnostics.get("manager_created") is False, "diag darf keinen Manager erzeugen")
    _require(isinstance(diagnostics.get("connected_devices"), list), "diag: Geraeteliste fehlt")
    _require(isinstance(diagnostics.get("library_output"), list), "diag: Library-Puffer fehlt")
    _require(isinstance(diagnostics.get("library_errors"), list), "diag: Fehler-Puffer fehlt")

    _require(unknown.get("id") == 3 and unknown.get("ok") is False, "Fehlerkommando falsch")
    _require("Unbekanntes Kommando" in str(unknown.get("error")), "Fehlertext fehlt")
    _require(quit_reply.get("id") == 4 and quit_reply.get("ok") is True, "quit fehlgeschlagen")

    production_responses = _exchange(
        executable,
        [
            {"id": 10, "cmd": "ping"},
            {"id": 11, "cmd": "diag"},
            {"id": 12, "cmd": "quit"},
        ],
        developer_diagnostics=False,
    )
    _require(
        len(production_responses) == 3,
        f"Produktionspfad: erwartet 3 Antworten, erhalten: {len(production_responses)}",
    )
    production_ping, production_diag_reply, production_quit = production_responses
    _require(
        production_ping.get("id") == 10
        and production_ping.get("ok") is True
        and production_ping.get("version") == "0.2.0",
        "Produktionspfad: ping fehlgeschlagen",
    )
    production_diag = production_diag_reply.get("diagnostics")
    _require(
        production_diag_reply.get("id") == 11
        and production_diag_reply.get("ok") is True
        and isinstance(production_diag, dict),
        "Produktionspfad: diag fehlgeschlagen",
    )
    _require(
        production_diag.get("developer_diagnostics_enabled") is False,
        "Produktionspfad: Developer-Diagnose unerwartet aktiv",
    )
    _require(production_diag.get("manager_created") is False, "Produktions-diag erzeugt Manager")
    _require(production_diag.get("library_output") == [], "Produktionspfad sammelt Konsolenausgaben")
    _require(production_diag.get("library_errors") == [], "Produktionspfad sammelt Library-Fehler")
    _require(
        production_quit.get("id") == 12 and production_quit.get("ok") is True,
        "Produktionspfad: quit fehlgeschlagen",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", nargs="?", type=Path, default=DEFAULT_EXE)
    args = parser.parse_args()
    try:
        run_protocol_test(args.executable)
    except Exception as exc:
        print(f"NIKON BRIDGE PROTOCOL TEST: FEHLER: {exc}")
        return 1
    print("NIKON BRIDGE PROTOCOL TEST: Developer- und Produktionspfad OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
