"""Statische Architekturgrenzen fuer Canon, UI-Fallback und Karten-Baseline."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

treffer = []
for path in SRC.rglob("*.py"):
    if path == SRC / "camera" / "edsdk.py":
        continue
    for nr, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "EDSDK_DLL." in line:
            treffer.append(f"{path.relative_to(ROOT)}:{nr}")
assert not treffer, f"Rohe EDSDK-Aufrufe ausserhalb des Wrappers: {treffer}"

edsdk_quelle = (SRC / "camera" / "edsdk.py").read_text(encoding="utf-8")
baum = ast.parse(edsdk_quelle)
owner_intern = {"_setup_functions", "_sdk_faden_schleife", "_terminate_im_owner"}
ungeschuetzt = []
for funktion in (knoten for knoten in baum.body if isinstance(knoten, ast.FunctionDef)):
    hat_dll_aufruf = any(
        isinstance(knoten, ast.Attribute)
        and isinstance(knoten.value, ast.Name)
        and knoten.value.id == "EDSDK_DLL"
        for knoten in ast.walk(funktion)
    )
    hat_owner_decorator = any(
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Name)
        and decorator.func.id == "kamera_faden_aufruf"
        for decorator in funktion.decorator_list
    )
    if hat_dll_aufruf and not hat_owner_decorator and funktion.name not in owner_intern:
        ungeschuetzt.append(funktion.name)
assert not ungeschuetzt, f"Rohe EDSDK-Funktion ohne Owner-Decorator: {ungeschuetzt}"
assert edsdk_quelle.count("EDSDK_DLL.EdsSetCapacity(") == 1, \
    "Capacity darf nur im atomaren Host-Session-Aufbau gesetzt werden"

canon = (SRC / "camera" / "canon.py").read_text(encoding="utf-8")
session = (SRC / "ui" / "screens" / "session.py").read_text(encoding="utf-8")

init = canon[canon.index("    def initialize("):canon.index("    def release(")]
assert init.index("set_object_event_handler") < init.index("open_session")
assert init.index("set_state_event_handler") < init.index("open_session")
assert "set_save_to_host" in init
assert "set_save_to_camera" not in init

capture = canon[canon.index("    def capture_photo("):canon.index("    def _fallback_to_live_view(")]
assert capture.index("get_card_image_count") < capture.index("take_picture")
assert capture.index("take_picture") < capture.index("wait_for_new_image")
assert "baseline=karten_baseline" in capture
assert "edsdk.get_event(" not in capture
assert "edsdk.pump_windows_messages(" not in capture
assert "before_shutter=self._capture_scharfschalten" in capture
assert "queue_capture_id != self._aktueller_capture_id" in capture
assert "melde_freien_speicher" not in capture
assert "_host_storage_ready" in capture
assert "SHUTTER-BLOCKED" in capture
assert canon.count("edsdk.take_picture(") == 1, \
    "Kein zweiter Canon-API-Weg darf Host-/Queue-Readiness umgehen"

handler = canon[canon.index("    def _on_object_event("):canon.index("    def _on_state_event(")]
assert "STALE-EVENT-REJECTED" in handler
assert "self._photo_queue.put((capture_id, image_data))" in handler

dispose = edsdk_quelle[
    edsdk_quelle.index("def dispose_camera("):
    edsdk_quelle.index("def send_command(")
]
close_call = dispose.index("err = EDSDK_DLL.EdsCloseSession")
release_call = dispose.index("EDSDK_DLL.EdsRelease(camera_ref)")
callback_pop = dispose.index("_object_event_handlers.pop")
assert close_call < release_call < callback_pop

assert 'ist_canon = self.config.get("camera_type", "webcam") == "canon"' in session
assert "if photo is None and not ist_canon:" in session
assert "if self._zeigt_dslr_wartehinweis():" in session
assert 'lower() == "nikon"' in session
assert "_canon_foto_aufbereiten" in session

print("BESTANDEN: Owner-Grenze, Host-Guard, Nikon-Hinweis und Canon-PIL-Pfad.")
