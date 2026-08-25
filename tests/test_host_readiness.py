"""Beweist den atomaren Canon-Host-Readiness-Vertrag ohne echte Kamera.

Aufruf:  python tests/test_host_readiness.py
"""

import ctypes
import importlib.util
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if not hasattr(ctypes, "WINFUNCTYPE"):
    ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE

spec = importlib.util.spec_from_file_location(
    "fexobooth_test_host_readiness", ROOT / "src" / "camera" / "edsdk.py"
)
edsdk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edsdk)

assert ctypes.sizeof(edsdk.EdsCapacity) == 12
assert edsdk.EdsCapacity.numberOfFreeClusters.offset == 0
assert edsdk.EdsCapacity.bytesPerSector.offset == 4
assert edsdk.EdsCapacity.reset.offset == 8


def _wert(value):
    return int(value.value) if hasattr(value, "value") else int(value)


class HostDLL:
    """Kleine EDSDK-Simulation mit steuerbaren Property-Antworten."""

    def __init__(
        self,
        *,
        save_to=None,
        available_shots=None,
        save_error=0,
        lock_error=0,
        save_read_error=0,
        available_error=0,
        capacity_error=0,
        capacity_exception=None,
        unlock_error=0,
    ):
        self.save_to = list(save_to or [edsdk.kEdsSaveTo_Host])
        self.available_shots = list(available_shots or [100])
        self.save_error = save_error
        self.lock_error = lock_error
        self.save_read_error = save_read_error
        self.available_error = available_error
        self.capacity_error = capacity_error
        self.capacity_exception = capacity_exception
        self.unlock_error = unlock_error
        self.calls = []
        self.capacities = []

    def _record(self, name, detail=None):
        self.calls.append((name, detail, threading.get_ident()))

    @staticmethod
    def _next(values):
        if len(values) > 1:
            return values.pop(0)
        return values[0]

    def EdsInitializeSDK(self):
        self._record("Initialize")
        return edsdk.EDS_ERR_OK

    def EdsGetEvent(self):
        self._record("Event")
        return edsdk.EDS_ERR_OK

    def EdsTerminateSDK(self):
        self._record("Terminate")
        return edsdk.EDS_ERR_OK

    def EdsSetPropertyData(self, ref, prop, index, size, value):
        prop = _wert(prop)
        assert prop == edsdk.kEdsPropID_SaveTo
        assert value._obj.value == edsdk.kEdsSaveTo_Host
        self._record("SaveTo", value._obj.value)
        return self.save_error

    def EdsSendStatusCommand(self, ref, command, parameter):
        command = _wert(command)
        if command == edsdk.kEdsCameraStatusCommand_UILock:
            self._record("UILock")
            return self.lock_error
        assert command == edsdk.kEdsCameraStatusCommand_UIUnLock
        self._record("UIUnlock")
        return self.unlock_error

    def EdsSetCapacity(self, ref, capacity):
        daten = (
            capacity.numberOfFreeClusters,
            capacity.bytesPerSector,
            capacity.reset,
        )
        self.capacities.append(daten)
        self._record("Capacity", daten)
        if self.capacity_exception is not None:
            raise self.capacity_exception
        return self.capacity_error

    def EdsGetPropertyData(self, ref, prop, index, size, out_value):
        prop = _wert(prop)
        if prop == edsdk.kEdsPropID_SaveTo:
            value = self._next(self.save_to)
            self._record("ReadSaveTo", value)
            if self.save_read_error:
                return self.save_read_error
            out_value._obj.value = value
            return edsdk.EDS_ERR_OK
        if prop == edsdk.kEdsPropID_AvailableShots:
            self._record("ReadAvailableShots", self.available_error)
            if self.available_error:
                return self.available_error
            value = self._next(self.available_shots)
            self.calls[-1] = (
                "ReadAvailableShots",
                value,
                self.calls[-1][2],
            )
            out_value._obj.value = value
            return edsdk.EDS_ERR_OK
        raise AssertionError(f"Unerwartete Property: {prop:#x}")


def relevante_namen(dll):
    return [
        name
        for name, _, _ in dll.calls
        if name not in {"Initialize", "Event"}
    ]


def im_owner(dll, expected=True):
    edsdk.EDSDK_DLL = dll
    result = edsdk.set_save_to_host(ctypes.c_void_p(123))
    assert result is expected, (result, relevante_namen(dll))
    owner_ids = {
        thread_id
        for name, _, thread_id in dll.calls
        if name not in {"Event"}
    }
    assert owner_ids == {edsdk._sdk_faden.ident}, owner_ids
    assert threading.get_ident() not in owner_ids
    return result


# Der erste Fall startet gleichzeitig den echten Python-Owner. Nur die native
# DLL ist simuliert; Polling, Dispatch und Fehlerbehandlung sind Produktionscode.
dll = HostDLL(
    save_to=[edsdk.kEdsSaveTo_Camera, edsdk.kEdsSaveTo_Host],
    available_shots=[0, 12],
)
edsdk.EDSDK_DLL = dll
edsdk.load_edsdk = lambda: True
edsdk._setup_functions = lambda: None
edsdk._sdk_initialized = False
edsdk._sdk_faden = None
edsdk._sdk_bereit = None
edsdk._sdk_ungesund = False

start = time.monotonic()
im_owner(dll)
dauer = time.monotonic() - start
assert relevante_namen(dll) == [
    "SaveTo",
    "UILock",
    "Capacity",
    "UIUnlock",
    "ReadSaveTo",
    "ReadSaveTo",
    "ReadAvailableShots",
    "ReadAvailableShots",
]
assert dll.capacities == [(0x7FFFFFFF, 0x1000, 1)]
assert dauer >= 0.08, f"50-ms-Polling wurde offenbar umgangen: {dauer:.3f}s"


# Ohne erfolgreiches Setzen beziehungsweise ohne erworbenen Lock darf es
# keinen Unlock geben. Entsperrt wird ausschließlich ein erfolgreicher Lock.
dll = HostDLL(save_error=edsdk.EDS_ERR_DEVICE_BUSY)
im_owner(dll, expected=False)
assert relevante_namen(dll) == ["SaveTo"]
assert not dll.capacities

dll = HostDLL(lock_error=edsdk.EDS_ERR_DEVICE_BUSY)
im_owner(dll, expected=False)
assert relevante_namen(dll) == ["SaveTo", "UILock"]
assert not dll.capacities


# Auch ein von der DLL gelieferter Capacity-Fehler muss nach erfolgreichem Lock
# immer erst entsperren. Danach darf kein Readback mehr stattfinden.
dll = HostDLL(capacity_error=edsdk.EDS_ERR_DEVICE_BUSY)
im_owner(dll, expected=False)
assert relevante_namen(dll) == ["SaveTo", "UILock", "Capacity", "UIUnlock"]


# Ein echter SaveTo-Readback-Fehler ist anders als ein nicht unterstütztes
# AvailableShots: Der zentrale Host-Nachweis fehlt und muss blockieren.
dll = HostDLL(save_read_error=edsdk.EDS_ERR_DEVICE_BUSY)
im_owner(dll, expected=False)
assert relevante_namen(dll) == [
    "SaveTo", "UILock", "Capacity", "UIUnlock", "ReadSaveTo"
]
assert dll.capacities == [(0x7FFFFFFF, 0x1000, 1)]


# Gleiches gilt fuer eine native/Python-Exception in EdsSetCapacity.
dll = HostDLL(capacity_exception=RuntimeError("simulierter Capacity-Abbruch"))
edsdk.EDSDK_DLL = dll
try:
    edsdk.set_save_to_host(ctypes.c_void_p(123))
except RuntimeError as error:
    assert "Capacity-Abbruch" in str(error)
else:
    raise AssertionError("Capacity-Exception wurde unerwartet verschluckt")
assert relevante_namen(dll) == ["SaveTo", "UILock", "Capacity", "UIUnlock"]


# Ein fehlgeschlagener Unlock macht die gesamte Bereitschaft ungueltig.
dll = HostDLL(unlock_error=edsdk.EDS_ERR_DEVICE_BUSY)
im_owner(dll, expected=False)
assert relevante_namen(dll) == ["SaveTo", "UILock", "Capacity", "UIUnlock"]


# Bleibt der SaveTo-Readback auf "Kamera", darf AvailableShots gar nicht erst
# als Ersatzbeweis dienen. Auch dieser Readback ist auf rund eine Sekunde
# begrenzt.
dll = HostDLL(save_to=[edsdk.kEdsSaveTo_Camera], available_shots=[100])
start = time.monotonic()
im_owner(dll, expected=False)
dauer = time.monotonic() - start
assert 0.9 <= dauer < 2.5, f"SaveTo-Timeout falsch: {dauer:.3f}s"
assert not any(name == "ReadAvailableShots" for name, _, _ in dll.calls)
assert dll.capacities == [(0x7FFFFFFF, 0x1000, 1)]
assert edsdk.letzter_fehler == edsdk.EDS_ERR_OBJECT_NOTREADY


# 0 freie Aufnahmen ist kein unbekannter Wert: Nach maximal rund einer Sekunde
# muss der Aufbau scheitern, statt einen wahrscheinlich erfolglosen Shutter zu
# erlauben.
dll = HostDLL(available_shots=[0])
start = time.monotonic()
im_owner(dll, expected=False)
dauer = time.monotonic() - start
assert 0.9 <= dauer < 2.5, f"AvailableShots-Timeout falsch: {dauer:.3f}s"
assert sum(name == "Capacity" for name, _, _ in dll.calls) == 1
assert sum(name == "ReadAvailableShots" for name, _, _ in dll.calls) >= 10
assert edsdk.letzter_fehler == edsdk.EDS_ERR_MEMORYSTATUS_NOTREADY


# Canon darf "unbekannt" oder "Property nicht unterstuetzt" melden. SaveTo
# und die einmalige Capacity-Meldung reichen dann als Bereitschaftsnachweis.
for dll in (
    HostDLL(available_shots=[0xFFFFFFFF]),
    HostDLL(available_error=0x00000007),  # EDS_ERR_NOT_SUPPORTED
):
    im_owner(dll)
    assert dll.capacities == [(0x7FFFFFFF, 0x1000, 1)]
    assert relevante_namen(dll)[:4] == [
        "SaveTo", "UILock", "Capacity", "UIUnlock"
    ]
    assert edsdk.letzter_fehler == edsdk.EDS_ERR_OK


print(
    "BESTANDEN: Host-Bereitschaft ist atomar; Unlock, Polling und "
    "AvailableShots-Grenzfaelle stimmen."
)
