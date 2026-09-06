"""Tkinter-GC-Deadlock-Schutz (2.4.68). Braucht KEINE Box.

Sichert den Befund der drei Stress-Test-Freezes vom 06.09.2026 ab
(Stack-Dump Box 101): Der automatische Zyklen-Sammler sprang mitten in der
Geburt des LiveView-Threads an, raeumte ein tkinter.font.Font-Objekt weg,
dessen __del__ einen Tcl-Befehl aus dem fremden Thread schickte — waehrend
der Hauptthread in Thread.start() auf genau diesen Thread wartete. Deadlock.

Zwei Ebenen:
  1. Verhalten: Mit gc.disable() laeuft ein Zyklen-Finalizer NICHT mehr in
     einem fremden Thread; erst gc.collect() im Hauptthread raeumt ihn auf —
     und zwar IM Hauptthread.
  2. Vertrag (statisch): run() schaltet den Sammler ab und startet _gc_takt;
     _gc_takt sammelt im 30-s-Takt und haengt sich wieder ein.
"""
import gc
import sys
import threading
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
# 1. Verhalten
# ---------------------------------------------------------------------------

finalizer_threads = []


class Zeuge:
    """Steht stellvertretend fuer tkinter.font.Font: __del__ merkt sich,
    in welchem Thread er laeuft."""

    def __del__(self):
        finalizer_threads.append(threading.current_thread().name)


def zyklus_erzeugen():
    a = Zeuge()
    b = [a]
    a.selbst = b  # Referenzzyklus -> nur der Zyklen-Sammler raeumt das weg


def fremder_thread_muellt():
    # Viele Allokationen: Mit AKTIVEM Auto-Sammler wuerde hier frueher oder
    # spaeter die Schwelle reissen und der Zeuge in DIESEM Thread sterben.
    kram = []
    for _ in range(200_000):
        kram.append([object(), object()])
        if len(kram) > 500:
            kram.clear()


gc_war_an = gc.isenabled()
gc.disable()
try:
    gc.collect()  # sauberer Ausgangszustand
    finalizer_threads.clear()

    zyklus_erzeugen()

    t = threading.Thread(target=fremder_thread_muellt, name="fremder-thread")
    t.start()
    t.join(timeout=30)

    pruefe(
        "Mit gc.disable() stirbt der Zyklus NICHT im fremden Thread",
        finalizer_threads == [],
        f"Finalizer lief in: {finalizer_threads}",
    )

    gc.collect()  # wie _gc_takt: Aufraeumen im Hauptthread
    pruefe(
        "gc.collect() im Hauptthread raeumt den Zyklus auf — im Hauptthread",
        finalizer_threads == ["MainThread"],
        f"Finalizer lief in: {finalizer_threads}",
    )
finally:
    if gc_war_an:
        gc.enable()


# ---------------------------------------------------------------------------
# 2. Vertrag (statisch) gegen src/app.py
# ---------------------------------------------------------------------------

app = (ROOT / "src" / "app.py").read_text(encoding="utf-8")

pruefe(
    "run() schaltet den automatischen Zyklen-Sammler ab (gc.disable)",
    "gc.disable()" in app,
)
pruefe(
    "run() startet den Muellabfuhr-Takt",
    "self.root.after(30000, self._gc_takt)" in app,
)
pruefe(
    "_gc_takt sammelt (gc.collect) und haengt sich wieder ein",
    "def _gc_takt" in app
    and "gc.collect()" in app
    and app.count("self.root.after(30000, self._gc_takt)") >= 2,
)

print()
if FEHLER:
    print(f"  {len(FEHLER)} Pruefung(en) fehlgeschlagen")
    sys.exit(1)
print("  Alle Pruefungen bestanden")
