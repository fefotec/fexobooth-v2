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
    ("Typen gegen Canon-Header", "test_edsdk_typen.py",
     "findet 64-/32-Bit-Verwechslungen (haeufigste Ursache)"),
    ("Doppelbild + Endlosschleife", "test_canon_logik.py",
     "kein Altbild in der Collage, keine Blockade bei toter Kamera"),
    ("Einfrier-Schutz", "test_einfrier_schutz.py",
     "haengender Aufruf legt die Box nicht lahm"),
    ("Haenger-Sperre", "test_haenger_sperre.py",
     "ein haengender Aufruf wiederholt sich nicht"),
    ("Kamera-Faden", "test_kamera_faden.py",
     "SDK und Sitzung im selben Faden"),
    ("Direktweg zum PC", "test_direktweg.py",
     "Foto kommt ohne Karte im Rechner an"),
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
