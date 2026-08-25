"""Parallelstart und Timeout duerfen keinen spaeten DSLR-Auftrag erzeugen."""

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


def neues_modul(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "src" / "camera" / "edsdk.py"
    )
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


class StartDLL:
    def __init__(self):
        self.gestartet = threading.Event()
        self.weiter = threading.Event()
        self.init_aufrufe = 0

    def EdsInitializeSDK(self):
        self.init_aufrufe += 1
        self.gestartet.set()
        assert self.weiter.wait(3.0)
        return 0

    def EdsGetEvent(self):
        return 0

    def EdsTerminateSDK(self):
        return 0


start_modul = neues_modul("fexobooth_start_race_edsdk")
start_dll = StartDLL()
start_modul.EDSDK_DLL = start_dll
start_modul.load_edsdk = lambda: True
start_modul._setup_functions = lambda: None
start_modul._sdk_initialized = False
ergebnisse = []


def initialisieren():
    ergebnisse.append(start_modul.initialize())


t1 = threading.Thread(target=initialisieren, name="init-eins")
t2 = threading.Thread(target=initialisieren, name="init-zwei")
t1.start()
assert start_dll.gestartet.wait(2.0)
t2.start()
time.sleep(0.1)
assert t2.is_alive(), "Paralleler Aufrufer wartete nicht auf SDK-Bereitschaft"
start_dll.weiter.set()
t1.join(3.0)
t2.join(3.0)
assert not t1.is_alive() and not t2.is_alive()
assert ergebnisse == [True, True], ergebnisse
assert start_dll.init_aufrufe == 1


class QueueDLL:
    def EdsInitializeSDK(self):
        return 0

    def EdsGetEvent(self):
        return 0

    def EdsTerminateSDK(self):
        return 0


queue_modul = neues_modul("fexobooth_queue_race_edsdk")
queue_modul.EDSDK_DLL = QueueDLL()
queue_modul.load_edsdk = lambda: True
queue_modul._setup_functions = lambda: None
queue_modul._sdk_initialized = False
assert queue_modul.initialize()

blockiert = threading.Event()
freigeben = threading.Event()
spaete_aufrufe = []


def callback_download_haengt():
    blockiert.set()
    assert freigeben.wait(3.0)


def spaeter_ausloeser():
    spaete_aufrufe.append("ausgefuehrt")
    return True


queue_modul.kamera_faden_asynchron(callback_download_haengt)
assert blockiert.wait(2.0)

start = time.monotonic()
assert queue_modul.im_kamera_faden(spaeter_ausloeser, timeout=0.1) is None
assert time.monotonic() - start < 0.5
assert "healthy=False" in queue_modul.owner_snapshot()

# Nach dem ersten Timeout muss jeder weitere Versuch sofort scheitern.
start = time.monotonic()
assert queue_modul.im_kamera_faden(spaeter_ausloeser, timeout=0.1) is None
assert time.monotonic() - start < 0.1

freigeben.set()
time.sleep(0.25)
assert not spaete_aufrufe, spaete_aufrufe

print("BESTANDEN: Parallelstart wartet; Timeout cancelt atomar und sperrt Owner.")
