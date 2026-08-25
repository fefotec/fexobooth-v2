"""Prueft: Die Box darf NIEMALS einfrieren, auch wenn die Kamera haengt."""
import sys, time, ctypes
sys.path.insert(0, r"C:\Git-Projects\fexobooth-v2")
from src.camera import edsdk

class HaengendeDLL:
    """Simuliert genau den Fall vom 24.08.2026: Aufruf kehrt nie zurueck."""
    def EdsSetObjectEventHandler(self, ref, ev, cb, ctx):
        time.sleep(600)   # kehrt praktisch nie zurueck
        return 0

edsdk.EDSDK_DLL = HaengendeDLL()

print("Szenario: EdsSetObjectEventHandler kehrt nicht zurueck")
print("(genau das hat die Box beim Session-Start eingefroren)\n")

t0 = time.time()
ergebnis = edsdk.set_object_event_handler(object(), lambda e, o: 0)
dauer = time.time() - t0

print(f"\nRueckgabe : {ergebnis!r}")
print(f"Dauer     : {dauer:.1f}s")
print()

assert dauer < 6.0, f"ZU LANGE BLOCKIERT: {dauer:.1f}s -> Box wuerde einfrieren!"
assert ergebnis is None, f"Erwartet None (unklar), war {ergebnis!r}"
print("BESTANDEN: Die Box gibt nach fester Frist auf und laeuft weiter.")
print("           Rueckgabe 'None' = unklar -> Direktweg wird trotzdem probiert,")
print("           es wird NICHT faelschlich Erfolg gemeldet.")

# Gegenprobe: sauberer Erfolg.
# WICHTIG: Die Sperre aus 2.4.56 zuruecksetzen — sie merkt sich, dass der
# Aufruf schon einmal hing, und wuerde jeden weiteren sofort abweisen. Im
# echten Betrieb ist das genau richtig; fuer die Gegenprobe brauchen wir
# einen frischen Zustand.
edsdk._handler_haengt_dauerhaft = False

class OkDLL:
    def EdsSetObjectEventHandler(self, ref, ev, cb, ctx): return 0
edsdk.EDSDK_DLL = OkDLL()
t0 = time.time()
r = edsdk.set_object_event_handler(object(), lambda e, o: 0)
print(f"\nGegenprobe (Kamera antwortet normal): {r!r} nach {time.time()-t0:.2f}s")
assert r is True
print("BESTANDEN: Normalfall wird weiterhin sofort als Erfolg erkannt.")
