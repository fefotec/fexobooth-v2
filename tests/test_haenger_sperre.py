"""Statische Sicherung gegen die frueher gestapelten Handler-Threads."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
quelle = (ROOT / "src" / "camera" / "edsdk.py").read_text(encoding="utf-8")

assert 'name="edsdk-rueckkanal"' not in quelle
assert "_sdk_ungesund" in quelle
assert "CANON-OWNER TIMEOUT" in quelle
assert "nimmt keinen weiteren Auftrag an" in quelle

print("BESTANDEN: Kein Wegwerf-Handlerthread; Owner sperrt nach nativem Haenger.")
