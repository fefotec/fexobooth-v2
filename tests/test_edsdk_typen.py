"""Prueft die ctypes-Anbindung an die Canon-Bibliothek.

WARUM ES DIESEN TEST GIBT (2.4.58):

Die DSLR-Fehlersuche im August 2026 hat ueber Wochen immer denselben Fehlertyp
zutage gefoerdert: ein 64-Bit-Wert der Canon-Schnittstelle, der im Python-Code
als 32 Bit stand. Vier Fundstellen, vier Testrunden auf der echten Box.

Beim Beheben der letzten drei entstand prompt der naechste Fehler derselben
Familie: Die Signatur von EdsGetLength wurde korrigiert, eine Aufrufstelle im
Live-View aber uebersehen. Auf der Box hiess das 166 Mal

    argument 2: TypeError: expected LP_c_ulonglong instead of pointer to c_ulong

und kein einziges Vorschaubild. ctypes prueft solche Typen erst zur Laufzeit —
beim Start faellt nichts auf.

Dieser Test findet beides in Sekunden, ohne Kamera:
  1. Stimmen die Signaturen mit dem Hersteller-Header ueberein?
  2. Passen alle Aufrufstellen zu den Signaturen?

Aufruf:  python tests/test_edsdk_typen.py
"""

import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
QUELLE = WURZEL / "src" / "camera" / "edsdk.py"
HEADER = (WURZEL / "EDSDK" / "EDSDKv132010W" / "EDSDKv132010W" / "Windows"
          / "EDSDK" / "Header" / "EDSDK.h")


def pruefe_signaturen(quelle: str, header: str) -> list:
    """Vergleicht die argtypes im Code mit dem Canon-Header."""
    fehler = []

    header_64 = {}
    for m in re.finditer(r"EdsError\s+EDSAPI\s+(\w+)\s*\(([^)]*)\)", header):
        name, args = m.group(1), m.group(2)
        anzahl = len(re.findall(r"Eds(?:U)?Int64", args))
        if anzahl:
            header_64[name] = anzahl

    for name, anzahl_header in sorted(header_64.items()):
        m = re.search(rf"EDSDK_DLL\.{name}\.argtypes\s*=\s*\[([^\]]*)\]", quelle)
        if not m:
            continue  # Funktion wird nicht verwendet
        py = m.group(1)
        anzahl_py = py.count("c_uint64") + py.count("c_int64")
        if anzahl_py < anzahl_header:
            fehler.append(
                f"{name}: Header verlangt {anzahl_header}x 64 Bit, "
                f"Code hat {anzahl_py}x  ->  {py.strip()}"
            )
    return fehler


def pruefe_aufrufstellen(quelle: str) -> list:
    """Sucht Aufrufe, die 32-Bit-Variablen an 64-Bit-Parameter reichen."""
    fehler = []

    mit_64 = {
        m.group(1) for m in
        re.finditer(r"EDSDK_DLL\.(\w+)\.argtypes\s*=\s*\[([^\]]*)\]", quelle)
        if "c_uint64" in m.group(2) or "c_int64" in m.group(2)
    }

    zeilen = quelle.split("\n")
    for i, z in enumerate(zeilen):
        for fn in mit_64:
            if f"EDSDK_DLL.{fn}(" not in z:
                continue
            umfeld = "\n".join(zeilen[max(0, i - 8):i + 1])
            for vm in re.finditer(r"(\w+)\s*=\s*c_uint\(\)", umfeld):
                var = vm.group(1)
                if f"byref({var})" in z or re.search(rf"\b{var}\b\s*[,)]", z):
                    fehler.append(
                        f"Zeile {i+1}: {fn}() bekommt '{var}' als 32-Bit-Wert "
                        f"(muss ctypes.c_uint64 sein)\n      {z.strip()}"
                    )
    return fehler


def main() -> int:
    if not QUELLE.exists():
        print(f"Quelle nicht gefunden: {QUELLE}")
        return 2
    if not HEADER.exists():
        print(f"Canon-Header nicht gefunden: {HEADER}")
        print("(Der Test braucht ihn als Wahrheitsquelle.)")
        return 2

    quelle = QUELLE.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8", errors="replace")

    print("=" * 68)
    print("  EDSDK-Typenpruefung (ohne Kamera)")
    print("=" * 68)

    f1 = pruefe_signaturen(quelle, header)
    print("\n1. Signaturen gegen den Canon-Header:")
    if f1:
        for f in f1:
            print(f"   FEHLER  {f}")
    else:
        print("   OK — alle benutzten 64-Bit-Funktionen stimmen.")

    f2 = pruefe_aufrufstellen(quelle)
    print("\n2. Aufrufstellen gegen die Signaturen:")
    if f2:
        for f in f2:
            print(f"   FEHLER  {f}")
    else:
        print("   OK — keine 32-Bit-Variable an einem 64-Bit-Parameter.")

    print()
    if f1 or f2:
        print(f"{len(f1) + len(f2)} Problem(e) gefunden — NICHT auf eine Box bringen.")
        return 1

    print("Alles in Ordnung.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
