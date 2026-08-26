"""Integriert: Owner -> 0x208 -> Host-Download -> Capture-Queue -> JPEG."""

import ctypes
import io
import logging
import sys
import threading
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if not hasattr(ctypes, "WINFUNCTYPE"):
    ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE

from src.camera import edsdk
from src.camera import canon as canon_module
from src.camera.canon import CanonCameraManager


jpeg_stream = io.BytesIO()
Image.new("RGB", (6000, 4000), (80, 120, 160)).save(
    jpeg_stream, "JPEG", quality=70
)
JPEG = jpeg_stream.getvalue()


def ref_wert(ref):
    if isinstance(ref, ctypes.c_void_p):
        return int(ref.value or 0)
    return int(ref or 0)


class DLL:
    def __init__(self, available_shots=128):
        self.object_handler = None
        self.state_handler = None
        self.pending_transfer = False
        self.state_sent = False
        self.buffer = ctypes.create_string_buffer(JPEG)
        self.calls = []
        self.host_actions = []
        self.capacity_resets = []
        self.shutter = []
        self.download_complete = 0
        self.download_cancel = 0
        self.camera_release_hielt_callbacks = False
        self.available_shots = available_shots

    def _call(self, name):
        self.calls.append((name, threading.get_ident()))

    def EdsInitializeSDK(self):
        self._call("EdsInitializeSDK")
        return 0

    def EdsGetCameraList(self, out_list):
        self._call("EdsGetCameraList")
        out_list._obj.value = 100
        return 0

    def EdsGetChildCount(self, ref, out_count):
        self._call("EdsGetChildCount")
        out_count._obj.value = 1
        return 0

    def EdsGetChildAtIndex(self, ref, index, out_ref):
        self._call("EdsGetChildAtIndex")
        out_ref._obj.value = 123
        return 0

    def EdsGetDeviceInfo(self, ref, out_info):
        self._call("EdsGetDeviceInfo")
        out_info._obj.szDeviceDescription = b"Canon EOS 2000D"
        out_info._obj.szPortName = b"usb:fake"
        return 0

    def EdsSetObjectEventHandler(self, ref, event, callback, context):
        self._call("EdsSetObjectEventHandler")
        assert event == edsdk.kEdsObjectEvent_All
        self.object_handler = callback
        return 0

    def EdsSetCameraStateEventHandler(self, ref, event, callback, context):
        self._call("EdsSetCameraStateEventHandler")
        assert event == edsdk.kEdsStateEvent_All
        self.state_handler = callback
        return 0

    def EdsOpenSession(self, ref):
        self._call("EdsOpenSession")
        return 0

    def EdsCloseSession(self, ref):
        self._call("EdsCloseSession")
        return 0

    def EdsSetPropertyData(self, ref, prop, index, size, value):
        self._call("EdsSetPropertyData")
        if int(prop) == edsdk.kEdsPropID_SaveTo:
            assert value._obj.value == edsdk.kEdsSaveTo_Host
            self.host_actions.append("SaveTo=Host")
        return 0

    def EdsSendStatusCommand(self, ref, command, parameter):
        self._call("EdsSendStatusCommand")
        if int(command) == edsdk.kEdsCameraStatusCommand_UILock:
            self.host_actions.append("UILock")
        else:
            assert int(command) == edsdk.kEdsCameraStatusCommand_UIUnLock
            self.host_actions.append("UIUnlock")
        return 0

    def EdsGetPropertyData(self, ref, prop, index, size, out_value):
        self._call("EdsGetPropertyData")
        if int(prop) == edsdk.kEdsPropID_SaveTo:
            self.host_actions.append("ReadSaveTo")
            out_value._obj.value = edsdk.kEdsSaveTo_Host
        elif int(prop) == edsdk.kEdsPropID_AvailableShots:
            self.host_actions.append("ReadAvailableShots")
            out_value._obj.value = self.available_shots
        else:
            out_value._obj.value = 0
        return 0

    def EdsSetCapacity(self, ref, capacity):
        self._call("EdsSetCapacity")
        self.capacity_resets.append(capacity.reset)
        self.host_actions.append("Capacity(reset=1)")
        assert capacity.numberOfFreeClusters == 0x7FFFFFFF
        assert capacity.bytesPerSector == 0x1000
        assert capacity.reset == 1
        return 0

    def EdsSendCommand(self, ref, command, parameter):
        self._call("EdsSendCommand")
        self.shutter.append(parameter)
        if parameter == edsdk.kEdsCameraCommand_ShutterButton_Completely:
            self.pending_transfer = True
        return 0

    def EdsGetEvent(self):
        self._call("EdsGetEvent")
        if self.pending_transfer and self.object_handler is not None:
            self.pending_transfer = False
            if self.state_handler is not None and not self.state_sent:
                self.state_sent = True
                self.state_handler(
                    edsdk.kEdsStateEvent_CaptureError,
                    edsdk.EDS_ERR_DEVICE_BUSY,
                    None,
                )
            self.object_handler(
                edsdk.kEdsObjectEvent_DirItemRequestTransfer,
                ctypes.c_void_p(456),
                None,
            )
        return 0

    def EdsGetDirectoryItemInfo(self, ref, out_info):
        self._call("EdsGetDirectoryItemInfo")
        out_info._obj.size = len(JPEG)
        out_info._obj.szFileName = b"IMG_0001.JPG"
        out_info._obj.format = 0x00000001
        return 0

    def EdsCreateMemoryStream(self, size, out_stream):
        self._call("EdsCreateMemoryStream")
        out_stream._obj.value = 789
        return 0

    def EdsDownload(self, ref, size, stream):
        self._call("EdsDownload")
        assert int(size) == len(JPEG)
        return 0

    def EdsDownloadComplete(self, ref):
        self._call("EdsDownloadComplete")
        self.download_complete += 1
        return 0

    def EdsDownloadCancel(self, ref):
        self._call("EdsDownloadCancel")
        self.download_cancel += 1
        return 0

    def EdsGetPointer(self, stream, out_pointer):
        self._call("EdsGetPointer")
        out_pointer._obj.value = ctypes.addressof(self.buffer)
        return 0

    def EdsGetLength(self, stream, out_length):
        self._call("EdsGetLength")
        out_length._obj.value = len(JPEG)
        return 0

    def EdsRelease(self, ref):
        self._call("EdsRelease")
        if ref_wert(ref) == 123:
            self.camera_release_hielt_callbacks = (
                123 in edsdk._object_event_handlers
                and 123 in edsdk._state_event_handlers
            )
        return 0

    def EdsTerminateSDK(self):
        self._call("EdsTerminateSDK")
        return 0


# Flottenfall: EOS 2000D im Fotomodus P, aber ohne SD-Karte. Der Body meldet
# trotz bestaetigtem Hostziel und erfolgreicher Capacity dauerhaft 0.
dll = DLL(available_shots=0)
edsdk.EDSDK_DLL = dll
edsdk.load_edsdk = lambda: True
edsdk._setup_functions = lambda: None
edsdk._sdk_initialized = False
edsdk._sdk_faden = None
edsdk._sdk_bereit = None
edsdk._sdk_ungesund = False
edsdk._object_event_handlers.clear()
edsdk._state_event_handlers.clear()
edsdk.is_developer_mode = lambda: True
canon_module.is_developer_mode = lambda: True

log_text = io.StringIO()
log_handler = logging.StreamHandler(log_text)
edsdk.logger.addHandler(log_handler)
edsdk.logger.setLevel(logging.DEBUG)
canon_module.logger.addHandler(log_handler)
canon_module.logger.setLevel(logging.DEBUG)

try:
    manager = CanonCameraManager()
    assert manager.initialize()
    assert manager._host_storage_ready
    assert dll.host_actions[:6] == [
        "SaveTo=Host",
        "UILock",
        "Capacity(reset=1)",
        "UIUnlock",
        "ReadSaveTo",
        "ReadAvailableShots",
    ], dll.host_actions
    assert dll.capacity_resets == [1]
    assert "AvailableShots bleibt 0" in log_text.getvalue()
    assert "readiness=save_to+capacity" in log_text.getvalue()
    assert dll.shutter == [], "Host-Pruefung darf kein unsichtbares Testfoto machen"

    manager._live_view_active = True
    callback_payloads = []
    callback_threads = []

    def press_accepted(payload):
        callback_payloads.append(payload)
        callback_threads.append(threading.get_ident())
        raise RuntimeError("UI-Rueckmeldung absichtlich defekt")

    foto = manager.capture_photo(
        timeout=3.0,
        press_command_accepted=press_accepted,
    )

    assert foto is not None
    assert foto.size == (6000, 4000)
    assert manager._fotos_echt == 1
    assert dll.shutter == [
        edsdk.kEdsCameraCommand_ShutterButton_Completely,
        edsdk.kEdsCameraCommand_ShutterButton_OFF,
    ]
    assert dll.shutter.count(
        edsdk.kEdsCameraCommand_ShutterButton_Completely
    ) == 1
    assert len(callback_payloads) == 1
    assert callback_payloads[0].capture_id == "1.1"
    assert callback_payloads[0].press_ok
    assert callback_threads == [threading.get_ident()]
    assert callback_threads[0] != edsdk._sdk_faden.ident
    # Capacity gehoert ausschliesslich zum Session-Aufbau. Der erste Capture
    # darf weder neu melden noch einen zweiten Shutter als Retry senden.
    assert dll.capacity_resets == [1]
    assert dll.download_complete == 1
    assert dll.download_cancel == 0
    assert "file=IMG_0001.JPG" in log_text.getvalue()
    assert "format=0x00000001" in log_text.getvalue()
    for marker in (
        "CANON-DIAG event=CAPTURE-START",
        "CANON-CAPTURE ARMED",
        "CANON-SHUTTER PRESS-START",
        "CANON-SHUTTER PRESS-RETURN",
        "CANON-SHUTTER RELEASE-RETURN",
        "CANON-CAPTURE SHUTTER press=OK",
        "CANON-SHUTTER ACCEPTED-CALLBACK-ERROR",
        "CANON-CAPTURE EVENT",
        "event=0x00000208",
        "CANON-CAPTURE DOWNLOAD-QUEUED",
        "CANON-TRANSFER COMPLETE",
        "ECHTES DSLR-FOTO",
        "CANON-DIAG event=CAPTURE-END",
    ):
        assert marker in log_text.getvalue(), marker
    assert "name=CaptureError" in log_text.getvalue()
    assert "capture=-" not in next(
        zeile for zeile in log_text.getvalue().splitlines()
        if "name=CaptureError" in zeile
    )
    assert not manager._photo_queue.qsize()
    # DEVICE_BUSY als State-Event ist kein Beleg fuer verlorene Host-Capacity.
    assert manager._host_storage_ready
    assert not manager._camera_shutdown

    # CARD_NG kann auch asynchron kommen, obwohl der synchrone Shutter OK war.
    manager._on_state_event(
        edsdk.kEdsStateEvent_CaptureError,
        edsdk.EDS_ERR_TAKE_PICTURE_CARD_NG,
    )
    assert manager._host_storage_ready is False
    assert manager._camera_shutdown is True

    shutter_vor_blockade = list(dll.shutter)
    manager._camera_shutdown = False  # isoliert hier ausschliesslich den Guard
    assert manager.capture_photo(timeout=0.1) is None
    assert dll.shutter == shutter_vor_blockade
    assert "CANON-HOST SHUTTER-BLOCKED" in log_text.getvalue()
    manager._host_storage_ready = True

    main_thread = threading.get_ident()
    owner_ids = {thread_id for _, thread_id in dll.calls}
    assert owner_ids == {edsdk._sdk_faden.ident}, owner_ids
    assert main_thread not in owner_ids

    manager.release()
    assert dll.camera_release_hielt_callbacks
    assert 123 not in edsdk._object_event_handlers
    assert 123 not in edsdk._state_event_handlers
finally:
    edsdk.logger.removeHandler(log_handler)
    canon_module.logger.removeHandler(log_handler)

print(
    "BESTANDEN: Host-Setup einmalig; erster Capture genau einmal; "
    "ohne Readiness kein Shutter."
)
