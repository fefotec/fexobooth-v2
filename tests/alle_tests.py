"""Faehrt alle Tests der DSLR-Baustelle. Braucht KEINE Kamera.

Aufruf:  python tests/alle_tests.py

Vor jedem DSLR-Build ausfuehren. Der Hintergrund steht in DSLR-STAND.md:
Fuenf der acht Ursachen im August 2026 waren derselbe Fehlertyp, den diese
Tests in Sekunden finden — auf der Box kostete jeder eine ganze Testrunde.
"""
import subprocess
import sys
from pathlib import Path

TESTS = [
    ("Build-DLL-Pfad", "test_dll_loader.py",
     "installierte EXE findet EDSDK unter PyInstaller _internal"),
    ("Typen gegen Canon-Header", "test_edsdk_typen.py",
     "findet 64-/32-Bit-Verwechslungen (haeufigste Ursache)"),
    ("Konstanten gegen Canon-Header", "test_edsdk_konstanten.py",
     "Events und JPEG-Qualitaeten entsprechen dem Hersteller"),
    ("DSLR-Architekturgrenzen", "test_dslr_grenzen.py",
     "keine rohe DLL ausserhalb Owner, Baseline und Canon-Guard"),
    ("Host-Bereitschaft", "test_host_readiness.py",
     "SaveTo, UI-Lock, Capacity und Readback sind atomar"),
    ("Dev-Mode-Logging", "test_dev_logging.py",
     "Owner, Queue, Thread und Laufzeiten im Diagnose-Log"),
    ("Belichtungsdiagnose", "test_belichtungsdiagnose.py",
     "Canon-Mappings, EXIF und Pixel-Helligkeit sind belastbar"),
    ("Doppelbild + Endlosschleife", "test_canon_logik.py",
     "kein Altbild in der Collage, keine Blockade bei toter Kamera"),
    ("Callback-Queue", "test_event_queue.py",
     "kein Download reentrant im nativen Canon-Callback"),
    ("Transfer-Cleanup", "test_transfer_cleanup.py",
     "Downloadfehler endet mit Cancel und Release"),
    ("Einfrier-Schutz", "test_einfrier_schutz.py",
     "nativer Haenger wird gemeldet und nicht gestapelt"),
    ("Owner-Races", "test_owner_races.py",
     "Parallelstart wartet; Timeout kann nie spaeter ausloesen"),
    ("Haenger-Sperre", "test_haenger_sperre.py",
     "kein alter Wegwerf-Handlerthread im Code"),
    ("Kamera-Faden", "test_kamera_faden.py",
     "alle getesteten EDSDK-Aufrufe im selben Owner"),
    ("Ausloeser-Vertrag", "test_ausloeser.py",
     "genau ein Capture; Press- und OFF-Fehler bleiben sichtbar"),
    ("Direktweg zum PC", "test_direktweg.py",
     "Foto kommt ohne Karte im Rechner an"),
    ("Canon-UI und PIL-Pfad", "test_session_canon_pfad.py",
     "kein Canon-Balken; Nikon/Webcam und Farben bleiben stabil"),
    ("Host-Capture integriert", "test_host_capture_integration.py",
     "Owner, 0x208, JPEG, Queue und atomarer Cleanup als Gesamtkette"),
]

def main() -> int:
    hier = Path(__file__).resolve().parent
    print("=" * 70)
    print("  FEXOBOOTH — DSLR-Tests (ohne Kamera)")
    print("=" * 70)
    print()

    fehler = 0
    for name, datei, zweck in TESTS:
        pfad = hier / datei
        if not pfad.exists():
            print(f"  [FEHLT]  {name:<30} ({datei})")
            fehler += 1
            continue

        p = subprocess.run([sys.executable, str(pfad)],
                           capture_output=True, text=True)
        if p.returncode == 0:
            print(f"  [ OK  ]  {name:<30} {zweck}")
        else:
            fehler += 1
            print(f"  [FEHLER] {name:<30} {zweck}")
            for zeile in (p.stdout + p.stderr).strip().split("\n")[-6:]:
                print(f"           {zeile}")

    print()
    if fehler:
        print(f"  {fehler} Test(s) fehlgeschlagen — NICHT auf eine Box bringen.")
        return 1
    print("  Alle Tests bestanden.")
    print("  (Das heisst NICHT, dass die Kamera Fotos liefert — nur, dass die")
    print("   bekannten Fehlerklassen ausgeschlossen sind. Siehe DSLR-STAND.md.)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
