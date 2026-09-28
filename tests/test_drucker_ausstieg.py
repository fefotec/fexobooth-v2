"""Drucker-Fehler verlassbar + Druckkorrektur-Tasten (28.09.2026). Braucht KEINE Box.

Sichert ab:
  1. Das Fehlerfenster hat einen SICHTBAREN Service-Knopf (nicht nur das ✕).
  2. Nach dem PIN-Ausstieg bleibt das Overlay zu, bis der Drucker fehlerfrei
     meldet – keine 10-Minuten-Pause mehr, Aufhebung im OK-Zweig des Polls.
  3. Die − / + Tasten zählen richtig, halten die Grenzen und liefern get()
     wie der frühere Slider (Testdruck/Speichern rufen int(x.get())).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

overlay_src = (ROOT / "src/ui/dialogs/printer_error.py").read_text(encoding="utf-8")
app_src = (ROOT / "src/app.py").read_text(encoding="utf-8")
admin_src = (ROOT / "src/ui/screens/admin.py").read_text(encoding="utf-8")

# ── 1. Sichtbarer Ausstieg ───────────────────────────────────────
assert 'text=t(self.config, "printer.service_exit")' in overlay_src
assert "command=self._show_service_pin" in overlay_src.split("self.service_exit_btn")[1]

# ── 2. Unterdrückung bis behoben ─────────────────────────────────
assert "suppress_printer_overlay_until_resolved()" in overlay_src
assert "snooze_printer_overlay" not in overlay_src + app_src, "alte 10-Min-Pause ist zurück"
ok_zweig = app_src.split("# Alles OK -> Warnung verstecken")[1].split("def _show_printer_error_overlay")[0]
assert "self._printer_overlay_suppressed = False" in ok_zweig, "Sperre muss bei fehlerfreiem Drucker fallen"
anzeige = app_src.split("def _show_printer_error_overlay")[1].split("category = classify_error")[0]
assert "if self._printer_overlay_suppressed:" in anzeige and "return" in anzeige

# ── 3. Stepper ───────────────────────────────────────────────────
assert "ctk.CTkSlider" not in admin_src.split("def _create_print_slider")[1].split("def _get_available_printers")[0]

import customtkinter as ctk  # noqa: E402
from src.ui.widgets.stepper import NumberStepper  # noqa: E402

root = ctk.CTk()
root.withdraw()
try:
    s = NumberStepper(root, value=-3, min_val=-100, max_val=100, suffix=" px")
    s._press(+1); s._release()
    s._press(+1); s._release()
    assert s.get() == -1, s.get()
    assert s._label.cget("text") == "-1 px"
    s.set(0); s._press(+1); s._release()
    assert s._label.cget("text") == "+1 px", "Offsets zeigen das Vorzeichen"
    s.set(500)
    assert s.get() == 100, "set() hält die Obergrenze"
    s._press(+1); s._release()
    assert s.get() == 100, "+ am Anschlag bleibt stehen"
    # Halten: 15 Einzelschritte, danach 5er-Schritte
    s.set(0)
    for _ in range(17):
        s._repeat(+1)
    assert s.get() == 15 + 2 * 5, s.get()
    z = NumberStepper(root, value=103, min_val=50, max_val=150, suffix=" %")
    z._press(-1); z._release()
    assert z.get() == 102 and z._label.cget("text") == "102 %"
    assert int(z.get()) / 100 == 1.02
finally:
    root.destroy()

print("OK: Service-Ausstieg sichtbar, Sperre bis behoben, -/+ Tasten korrekt")
