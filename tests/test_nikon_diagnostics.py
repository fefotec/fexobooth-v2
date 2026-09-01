"""Gezielte Tests fuer die Nikon-Developerdiagnose ohne Kamera-Abhaengigkeiten."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "camera" / "nikon_diagnostics.py"
sys.path.insert(0, str(ROOT))


def _load_module():
    spec = importlib.util.spec_from_file_location("nikon_diagnostics_test_module", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.reset_diagnostic_state_for_tests()
    return module


class _ImmediateThread:
    def __init__(self, *, target, **_kwargs):
        self._target = target

    def start(self):
        self._target()


class _BrokenThread:
    def __init__(self, **_kwargs):
        pass

    def start(self):
        raise RuntimeError("thread unavailable")


class _FakeClient:
    def __init__(self, result=None, error=None):
        self.result = result or {"diagnostics": {"bridge_version": "0.2.0"}}
        self.error = error
        self.calls = []

    def is_running(self):
        return True

    def request(self, cmd, timeout):
        self.calls.append((cmd, timeout))
        if self.error:
            raise self.error
        return self.result, None


class NikonDiagnosticsTests(unittest.TestCase):
    def test_developer_mode_aus_startet_nichts(self):
        module = _load_module()
        client = _FakeClient()
        with mock.patch.object(module.threading, "Thread") as thread:
            self.assertFalse(module.schedule_bridge_diagnostics(client, {}, "off"))
            self.assertFalse(module.schedule_bridge_inventory(Path("bridge.exe"), {}))
            self.assertFalse(module.schedule_windows_snapshot({}, "off"))
        thread.assert_not_called()
        self.assertEqual(client.calls, [])

    def test_bridge_snapshot_und_alte_bridge_sind_best_effort(self):
        module = _load_module()
        client = _FakeClient()
        with mock.patch.object(module.threading, "Thread", _ImmediateThread):
            with self.assertLogs(module.logger, level="INFO") as captured:
                started = module.schedule_bridge_diagnostics(
                    client,
                    {"developer_mode": True},
                    "startup",
                )
        self.assertTrue(started)
        self.assertEqual(client.calls, [("diag", 2.0)])
        self.assertIn('"bridge_version":"0.2.0"', "\n".join(captured.output))

        module.reset_diagnostic_state_for_tests()
        old_client = _FakeClient(
            error=RuntimeError("FexoNikonBridge 'diag' fehlgeschlagen: Unbekanntes Kommando: diag")
        )
        with mock.patch.object(module.threading, "Thread", _ImmediateThread):
            with self.assertLogs(module.logger, level="INFO") as captured:
                module.schedule_bridge_diagnostics(
                    old_client,
                    {"developer_mode": True},
                    "old",
                )
        self.assertIn("unsupported_old_bridge", "\n".join(captured.output))

    def test_leere_admin_diagnose_wird_gedrosselt(self):
        module = _load_module()
        client = _FakeClient()
        with mock.patch.object(module.threading, "Thread", _ImmediateThread):
            first = module.schedule_bridge_diagnostics(
                client,
                {"developer_mode": True},
                "empty",
                minimum_interval_seconds=60,
                throttle_key="admin_list",
            )
            second = module.schedule_bridge_diagnostics(
                client,
                {"developer_mode": True},
                "empty-again",
                minimum_interval_seconds=60,
                throttle_key="admin_list",
            )
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(client.calls, [("diag", 2.0)])

    def test_erste_diagnose_wird_auch_kurz_nach_boot_nicht_gedrosselt(self):
        module = _load_module()
        client = _FakeClient()
        with (
            mock.patch.object(module.time, "monotonic", return_value=1.0),
            mock.patch.object(module.threading, "Thread", _ImmediateThread),
        ):
            started = module.schedule_bridge_diagnostics(
                client,
                {"developer_mode": True},
                "early",
                minimum_interval_seconds=60,
                throttle_key="admin_list",
            )
        self.assertTrue(started)
        self.assertEqual(client.calls, [("diag", 2.0)])

    def test_thread_start_fehler_bleiben_best_effort_und_setzen_status_frei(self):
        module = _load_module()
        client = _FakeClient()
        config = {"developer_mode": True}
        with mock.patch.object(module.threading, "Thread", _BrokenThread):
            self.assertFalse(module.schedule_bridge_diagnostics(client, config, "broken"))
        with mock.patch.object(module.threading, "Thread", _ImmediateThread):
            self.assertTrue(module.schedule_bridge_diagnostics(client, config, "broken"))

        with tempfile.TemporaryDirectory() as temp_dir:
            exe = Path(temp_dir) / "FexoNikonBridge.exe"
            exe.write_bytes(b"bridge")
            with mock.patch.object(module.threading, "Thread", _BrokenThread):
                self.assertFalse(module.schedule_bridge_inventory(exe, config))
            with mock.patch.object(module.threading, "Thread", _ImmediateThread):
                self.assertTrue(module.schedule_bridge_inventory(exe, config))

        module.reset_diagnostic_state_for_tests()
        with (
            mock.patch.object(module.os, "name", "nt"),
            mock.patch.object(module.threading, "Thread", _BrokenThread),
        ):
            self.assertFalse(module.schedule_windows_snapshot(config, "broken"))
        with (
            mock.patch.object(module.os, "name", "nt"),
            mock.patch.object(module.time, "monotonic", return_value=1.0),
            mock.patch.object(module.threading, "Thread", _ImmediateThread),
            mock.patch.object(module, "collect_windows_pnp", return_value={"devices": []}),
            mock.patch.object(module, "collect_relevant_processes", return_value={"items": []}),
        ):
            self.assertTrue(module.schedule_windows_snapshot(config, "retry"))

    def test_grosses_snapshot_log_bleibt_valid_und_behaelt_letzte_exception(self):
        module = _load_module()
        snapshot = {
            "bridge_version": "0.2.0",
            "last_scan": {"result": "completed"},
            "library_output": ["x" * 2000 for _ in range(100)],
            "last_exception": {"type": "WpdError", "message": "USB busy"},
        }
        encoded = module._bounded_json(snapshot)
        decoded = json.loads(encoded)
        self.assertLessEqual(len(encoded), module._MAX_LOG_JSON_CHARS)
        self.assertEqual(decoded["last_exception"]["type"], "WpdError")
        self.assertTrue(decoded["_log_truncated"])

    def test_bridge_request_timing_auf_windows_python(self):
        if importlib.util.find_spec("cv2") is None:
            self.skipTest("Kamera-Abhaengigkeiten in dieser Python-Umgebung nicht installiert")

        from src.camera import nikon

        class FakeProcess:
            def __init__(self):
                self.stdin = io.BytesIO()

            @staticmethod
            def poll():
                return None

        client = nikon._NikonBridgeClient({"developer_mode": True})
        client._process = FakeProcess()
        client._responses.put(({"id": 1, "ok": True, "bridge": "test"}, None))

        with mock.patch.object(nikon, "logger") as fake_logger:
            header, payload = client.request("ping", timeout=1.0)

        self.assertEqual(header["bridge"], "test")
        self.assertIsNone(payload)
        timing_calls = [
            call
            for call in fake_logger.debug.call_args_list
            if call.args and "NIKON-BRIDGE-CALL END" in call.args[0]
        ]
        self.assertEqual(len(timing_calls), 1)
        self.assertIn("lock_wait_ms", timing_calls[0].args[0])
        self.assertEqual(timing_calls[0].args[-1], "ok")

        off_client = nikon._NikonBridgeClient({"developer_mode": False})
        off_client._process = FakeProcess()
        off_client._responses.put(({"id": 1, "ok": True}, None))
        with mock.patch.object(nikon, "logger") as fake_logger:
            off_client.request("ping", timeout=1.0)
        fake_logger.debug.assert_not_called()

        class DeniedLock:
            @staticmethod
            def acquire(timeout):
                return False

        locked_client = nikon._NikonBridgeClient({"developer_mode": True})
        locked_client._io_lock = DeniedLock()
        with mock.patch.object(nikon, "logger") as fake_logger:
            with self.assertRaises(TimeoutError):
                locked_client.request("list", timeout=0.01)
        self.assertEqual(fake_logger.debug.call_args_list[-1].args[-1], "lock_timeout")

        timeout_client = nikon._NikonBridgeClient({"developer_mode": True})
        timeout_client._process = FakeProcess()
        with mock.patch.object(nikon, "logger") as fake_logger:
            with self.assertRaises(TimeoutError):
                timeout_client.request("ping", timeout=0.01)
        self.assertEqual(fake_logger.debug.call_args_list[-1].args[-1], "timeout")

    def test_inventar_bleibt_im_direkten_bridge_ordner(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            exe = root / "FexoNikonBridge.exe"
            dll = root / "CameraControl.Devices.dll"
            ignored = root / "not-a-library.txt"
            nested = root / "nested"
            nested.mkdir()
            exe.write_bytes(b"bridge")
            dll.write_bytes(b"library")
            ignored.write_text("ignore", encoding="utf-8")
            (nested / "hidden.dll").write_bytes(b"hidden")

            inventory = module.collect_bridge_inventory(exe)

        names = [item["name"] for item in inventory]
        self.assertEqual(names, ["CameraControl.Devices.dll", "FexoNikonBridge.exe"])
        self.assertTrue(all(len(item["sha256"]) == 64 for item in inventory))
        self.assertTrue(
            all("file_version" in item or "version_error" in item for item in inventory)
        )

    def test_pnp_json_wird_begrenzt_und_fremde_wpd_id_redigiert(self):
        module = _load_module()
        payload = {
            "devices": [
                {
                    "name": "Nikon D3300",
                    "manufacturer": "Nikon",
                    "pnp_class": "WPD",
                    "pnp_device_id": "USB\\VID_04B0&PID_0437\\NIKON-SERIAL",
                    "config_error": 0,
                },
                {
                    "name": "Telefon",
                    "manufacturer": "Fremd",
                    "pnp_class": "WPD",
                    "pnp_device_id": "USB\\VID_1234&PID_5678\\PRIVATE-SERIAL",
                    "config_error": 0,
                },
                {
                    "name": "HP Color LaserJet Scanner (USB)",
                    "manufacturer": "HP",
                    "pnp_class": "Image",
                    "pnp_device_id": "USB\\VID_03F0&PID_1234\\SCANNER-SERIAL",
                    "config_error": 0,
                },
            ]
        }
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(payload).encode("utf-8"),
            stderr=b"",
        )
        with mock.patch.object(module.subprocess, "run", return_value=completed):
            result = module.collect_windows_pnp()

        self.assertEqual(result["device_count"], 3)
        self.assertIn("VID_04B0", result["devices"][0]["pnp_device_id"])
        self.assertEqual(
            result["devices"][1]["pnp_device_id"],
            "<redacted-non-camera-wpd>",
        )
        self.assertEqual(
            result["devices"][2]["pnp_device_id"],
            "<redacted-non-camera-wpd>",
        )

    def test_bridge_snapshot_redigiert_fremde_ids_aber_nicht_nikon(self):
        module = _load_module()
        sanitized = module._sanitize_bridge_diagnostics(
            {
                "connected_devices": [
                    {"name": "Nikon D3300", "serial": "NIKON-123"},
                    {"name": "Telefon", "serial": "PRIVATE-456", "port": "WPD-PORT"},
                ],
                "library_output": [
                    "library:debug Connection device \\\\?\\swd#wpdbusenum#PRIVATE",
                    "library:error Nikon D3300 VID_04B0 failed",
                ],
                "library_errors": [
                    (
                        "library:error Unable to connect \\\\?\\swd#wpdbusenum#PRIVATE "
                        "| PortableDeviceLib.PortableDeviceException: Access denied"
                    ),
                    "library:error Nikon D3300 VID_04B0 timeout",
                ],
                "last_exception": {
                    "type": "PortableDeviceLib.PortableDeviceException",
                    "message": "Device SWD\\WPDBUSENUM\\PRIVATE-SERIAL is busy; Access denied",
                    "hresult": -2147024864,
                },
            }
        )
        self.assertEqual(sanitized["connected_devices"][0]["serial"], "NIKON-123")
        self.assertEqual(
            sanitized["connected_devices"][1]["serial"],
            "<redacted-non-nikon-device>",
        )
        self.assertNotIn("PRIVATE", sanitized["library_output"][0])
        self.assertIn("VID_04B0", sanitized["library_output"][1])
        self.assertNotIn("PRIVATE", sanitized["library_errors"][0])
        self.assertIn("library:error", sanitized["library_errors"][0])
        self.assertIn("PortableDeviceException", sanitized["library_errors"][0])
        self.assertIn("Access denied", sanitized["library_errors"][0])
        self.assertIn("VID_04B0", sanitized["library_errors"][1])
        self.assertNotIn("PRIVATE", sanitized["last_exception"]["message"])
        self.assertIn("is busy", sanitized["last_exception"]["message"])
        self.assertIn("Access denied", sanitized["last_exception"]["message"])

    def test_windows_snapshot_laeuft_hoechstens_einmal_pro_minute(self):
        module = _load_module()
        with (
            mock.patch.object(module.os, "name", "nt"),
            mock.patch.object(module.time, "monotonic", return_value=1.0),
            mock.patch.object(module.threading, "Thread", _ImmediateThread),
            mock.patch.object(module, "collect_windows_pnp", return_value={"devices": []}),
            mock.patch.object(module, "collect_relevant_processes", return_value={"items": []}),
        ):
            first = module.schedule_windows_snapshot({"developer_mode": True}, "init")
            second = module.schedule_windows_snapshot({"developer_mode": True}, "init-again")
        self.assertTrue(first)
        self.assertFalse(second)


if __name__ == "__main__":
    unittest.main()
