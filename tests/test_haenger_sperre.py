"""Prueft: Ein haengender Registrierungs-Aufruf darf sich NICHT wiederholen."""
import sys, time
sys.path.insert(0, r"C:\Git-Projects\fexobooth-v2")
from src.camera import edsdk

AUFRUFE = []
class HaengendeDLL:
    def EdsSetObjectEventHandler(self, ref, ev, cb, ctx):
        AUFRUFE.append(time.time())
        time.sleep(600)
        return 0
edsdk.EDSDK_DLL = HaengendeDLL()

print("Szenario: Registrierung haengt (blockiert die Kamera)\n")
for runde in range(1, 5):
    t0 = time.time()
    r = edsdk.set_object_event_handler(object(), lambda e, o: 0)
    print(f"  Versuch {runde}: {r!r:6} nach {time.time()-t0:.1f}s")

print(f"\nTatsaechliche DLL-Aufrufe: {len(AUFRUFE)}")
assert len(AUFRUFE) == 1, f"Kamera wurde {len(AUFRUFE)}x blockiert statt 1x!"
print("BESTANDEN: Nur EIN blockierender Aufruf. Weitere werden abgewiesen,")
print("           die Kamera wird nicht zusaetzlich lahmgelegt.")
