"""Haenge-Waechter (2.4.67). Braucht KEINE Box.

Sichert die Freeze-Diagnose vom 06.09.2026 ab (Box 101: zwei UI-Freezes im
Stress-Test, Log endet kommentarlos, kein Windows-Crash, kein Dump):

  1. Verhalten: faulthandler.dump_traceback_later feuert nach dem Timeout
     wirklich und schreibt die Thread-Stacks in die Zieldatei; erneutes
     Armieren setzt den Timer zurueck (Herzschlag-Prinzip); cancel entwaffnet.
  2. Vertrag (statisch): App und crashlog sind richtig verdrahtet —
     Herzschlag in run(), Re-Arm im 5-s-Takt, Timeout 30 s, exit=False
     (kein App-Abschuss), Entschaerfen im shutdown().
"""
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FEHLER = []


def pruefe(name: str, bedingung: bool, detail: str = ""):
    if bedingung:
        print(f"  [ OK  ]  {name}")
    else:
        FEHLER.append(name)
        print(f"  [FEHLER] {name}  {detail}")


# ---------------------------------------------------------------------------
# 1. Verhalten — im Subprozess, damit der faulthandler-Zustand dieses
#    Testlaufs nicht verseucht wird.
# ---------------------------------------------------------------------------

SZENARIO = textwrap.dedent("""
    import faulthandler, sys, time, threading

    pfad = sys.argv[1]
    f = open(pfad, "a", buffering=1, encoding="utf-8", errors="replace")

    def schlafender_thread():
        time.sleep(10)

    t = threading.Thread(target=schlafender_thread, daemon=True, name="test-schlaefer")
    t.start()

    # Herzschlag-Prinzip: zweimal armieren, dazwischen weniger als das
    # Timeout warten -> darf NICHT feuern (Re-Arm setzt den Timer zurueck)
    faulthandler.dump_traceback_later(0.8, repeat=False, file=f, exit=False)
    time.sleep(0.4)
    faulthandler.dump_traceback_later(0.8, repeat=False, file=f, exit=False)
    time.sleep(0.4)
    f.flush()
    groesse_ohne_feuer = len(open(pfad, encoding="utf-8", errors="replace").read())

    # Jetzt den Stillstand simulieren: armieren und das Timeout verstreichen
    # lassen -> MUSS feuern und die Stacks aller Threads schreiben
    faulthandler.dump_traceback_later(0.5, repeat=False, file=f, exit=False)
    time.sleep(1.2)
    faulthandler.cancel_dump_traceback_later()
    f.flush()

    print(groesse_ohne_feuer)
""")

with tempfile.TemporaryDirectory() as tmp:
    dump_pfad = str(Path(tmp) / "haenger_test.txt")
    p = subprocess.run(
        [sys.executable, "-c", SZENARIO, dump_pfad],
        capture_output=True, text=True, timeout=30,
    )
    inhalt = Path(dump_pfad).read_text(encoding="utf-8", errors="replace")

pruefe("Szenario-Subprozess lief durch", p.returncode == 0, p.stderr[-300:])
groesse_ohne_feuer = int(p.stdout.strip() or "-1")
pruefe(
    "Re-Arm innerhalb des Timeouts verhindert den Dump (Herzschlag-Prinzip)",
    groesse_ohne_feuer == 0,
    f"vorzeitig geschrieben: {groesse_ohne_feuer} Zeichen",
)
pruefe(
    "Nach Timeout-Ablauf wird der Dump geschrieben ('Timeout'-Marke)",
    "Timeout" in inhalt,
    f"Dateianfang: {inhalt[:120]!r}",
)
pruefe(
    "Dump enthaelt die Stacks ALLER Threads (auch test-schlaefer)",
    inhalt.count("Thread 0x") >= 1 and "schlafender_thread" in inhalt,
)


# ---------------------------------------------------------------------------
# 2. Vertrag (statisch)
# ---------------------------------------------------------------------------

crashlog = (ROOT / "src" / "utils" / "crashlog.py").read_text(encoding="utf-8")
app = (ROOT / "src" / "app.py").read_text(encoding="utf-8")

pruefe(
    "crashlog: arm_hang_watchdog nutzt exit=False (kein App-Abschuss)",
    "def arm_hang_watchdog" in crashlog
    and "exit=False" in crashlog and "repeat=False" in crashlog,
)
pruefe(
    "crashlog: cancel_hang_watchdog vorhanden",
    "def cancel_hang_watchdog" in crashlog
    and "cancel_dump_traceback_later" in crashlog,
)
pruefe(
    "crashlog: Thread-Legende wird geschrieben (IDs -> Namen)",
    "Thread-Legende" in crashlog,
)
pruefe(
    "app: Herzschlag startet in run()",
    "self.root.after(1000, self._haenge_waechter_takt)" in app,
)
pruefe(
    "app: Herzschlag re-armiert im 5-s-Takt mit 30-s-Timeout",
    "self.root.after(5000, self._haenge_waechter_takt)" in app
    and "arm_hang_watchdog(30.0)" in app,
)
pruefe(
    "app: shutdown entschaerft den Waechter",
    "cancel_hang_watchdog()" in app,
)

print()
if FEHLER:
    print(f"  {len(FEHLER)} Pruefung(en) fehlgeschlagen")
    sys.exit(1)
print("  Alle Pruefungen bestanden")
