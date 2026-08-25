"""Prueft den Kamera-Faden: SDK und Sitzung im selben Faden, Rueckkanal daneben."""
import sys, threading
sys.path.insert(0, r"C:\Git-Projects\fexobooth-v2")
from src.camera import edsdk

FADEN = []
class DLL:
    def EdsInitializeSDK(self):
        FADEN.append(("SDK-Start", threading.current_thread().name)); return 0
    def EdsOpenSession(self, ref):
        FADEN.append(("Sitzung", threading.current_thread().name)); return 0
    def EdsSetObjectEventHandler(self, ref, ev, cb, ctx):
        FADEN.append(("Rueckkanal", threading.current_thread().name)); return 0
    def EdsTerminateSDK(self): return 0

edsdk.EDSDK_DLL = DLL()
edsdk.load_edsdk = lambda: True
edsdk._setup_functions = lambda: None
edsdk._sdk_initialized = False
edsdk._handler_haengt_dauerhaft = False

print("Szenario: Aufrufe kommen aus VERSCHIEDENEN Faden (wie in der App)\n")

edsdk.initialize()                                    # Haupt-Faden

def aus_nebenfaden():                                 # wie der System-Test
    edsdk.im_kamera_faden(edsdk.EDSDK_DLL.EdsOpenSession, object())
t = threading.Thread(target=aus_nebenfaden, name="system-test"); t.start(); t.join()

def noch_woanders():
    edsdk.set_object_event_handler(object(), lambda e, o: 0)
t2 = threading.Thread(target=noch_woanders, name="irgendwo"); t2.start(); t2.join(timeout=8)

print("Wo wurde die Kamera-Bibliothek tatsaechlich angesprochen?")
for was, faden in FADEN:
    print(f"  {was:<12} -> Faden '{faden}'")
print()

z = dict(FADEN)
assert z["SDK-Start"] == "edsdk-kamera", "SDK nicht im Kamera-Faden!"
assert z["Sitzung"] == "edsdk-kamera", f"Sitzung im falschen Faden: {z['Sitzung']}"
print("BESTANDEN 1: SDK-Start und Sitzung im SELBEN Faden ('edsdk-kamera') —")
print("             egal von wo der Aufruf kam. Genau das war die Ursache.")

assert z["Rueckkanal"] == "edsdk-rueckkanal", \
    "Rueckkanal im Kamera-Faden — ein Haenger wuerde alles blockieren!"
print("BESTANDEN 2: Der Rueckkanal laeuft daneben und kann den Kamera-Faden")
print("             nicht mitreissen, falls er haengt.")

lebt = edsdk.im_kamera_faden(lambda: threading.current_thread().name, timeout=3.0)
assert lebt == "edsdk-kamera", f"Kamera-Faden antwortet nicht ({lebt})"
print("BESTANDEN 3: Der Kamera-Faden nimmt danach weiter Auftraege an.")
