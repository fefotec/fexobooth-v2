"""Weisse-Print-Race (2.4.66). Braucht KEINE Box.

Sichert den Befund vom Dauerlauf 05.09.2026 (Box 101) ab: 9 von 30
Print-Dateien waren byte-identisch weiss. Ursache: Der Gast (bzw. der
Stress-Test) beendete die Session, waehrend das finale Bild noch im
Hintergrund gerendert wurde — reset_session() leerte Fotos, Vorlagen-Felder
und Overlay, der Renderer speicherte eine leere weisse Vorlage.

Zwei Ebenen:
  1. Verhalten: Der TemplateRenderer liefert mit leeren Boxen wirklich eine
     rein weisse Flaeche (der Fehler-Mechanismus), und eine Momentaufnahme
     der Session-Daten uebersteht ein gleichzeitiges reset_session().
  2. Vertrag (statisch): Worker und Renderfunktion greifen NIE auf die
     lebenden Session-Felder der App zu, sondern nur auf die Momentaufnahme,
     und on_show erstellt die Momentaufnahme vor dem Thread-Start.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image

from src.templates.renderer import TemplateRenderer

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

renderer = TemplateRenderer()
rotes_foto = Image.new("RGB", (400, 300), "#FF0000")
boxen = [{"box": (100, 100, 899, 699), "angle": 0.0}]


def ist_rein_weiss(bild: Image.Image) -> bool:
    extrema = bild.convert("RGB").getextrema()
    return all(kanal == (255, 255) for kanal in extrema)


leer = renderer.render([], [], None)
pruefe(
    "Leere Boxen ergeben die weisse Flaeche (Fehler-Mechanismus belegt)",
    ist_rein_weiss(leer),
    f"extrema={leer.convert('RGB').getextrema()}",
)

voll = renderer.render([rotes_foto], boxen, None)
pruefe(
    "Mit Foto und Box ist das Bild nicht weiss",
    not ist_rein_weiss(voll),
)

# Momentaufnahme wie in on_show: list(...) kopiert, dann "reset_session"
lebende_fotos = [rotes_foto]
lebende_boxen = list(boxen)
schnappschuss_fotos = list(lebende_fotos)
schnappschuss_boxen = list(lebende_boxen)
lebende_fotos.clear()   # reset_session(): photos_taken = [] / Liste weg
lebende_boxen.clear()   # reset_session(): template_boxes = []

danach = renderer.render(schnappschuss_fotos, schnappschuss_boxen, None)
pruefe(
    "Momentaufnahme uebersteht gleichzeitiges Session-Ende (kein weisses Bild)",
    not ist_rein_weiss(danach),
)


# ---------------------------------------------------------------------------
# 2. Vertrag (statisch) gegen src/ui/screens/final.py
# ---------------------------------------------------------------------------

quelle = (ROOT / "src" / "ui" / "screens" / "final.py").read_text(encoding="utf-8")
baum = ast.parse(quelle)

funktionen = {}
knoten_map = {}
for knoten in ast.walk(baum):
    if isinstance(knoten, ast.FunctionDef):
        funktionen[knoten.name] = ast.get_source_segment(quelle, knoten) or ""
        knoten_map[knoten.name] = knoten

VERBOTEN = {"photos_taken", "template_boxes", "overlay_image", "current_filter"}


def lebende_session_zugriffe(funktion: ast.FunctionDef):
    """Echte Code-Zugriffe self.app.<sessionfeld> — Docstrings zaehlen nicht."""
    treffer = []
    for k in ast.walk(funktion):
        if (isinstance(k, ast.Attribute) and k.attr in VERBOTEN
                and isinstance(k.value, ast.Attribute) and k.value.attr == "app"
                and isinstance(k.value.value, ast.Name) and k.value.value.id == "self"):
            treffer.append(f"self.app.{k.attr}")
    return treffer


for fname in ("_render_final_worker", "_render_final_image"):
    knoten = knoten_map.get(fname)
    pruefe(f"{fname} existiert", knoten is not None)
    treffer = lebende_session_zugriffe(knoten) if knoten else ["Funktion fehlt"]
    pruefe(
        f"{fname} nutzt nur die Momentaufnahme (keine lebenden Session-Felder)",
        not treffer,
        f"gefunden: {treffer}",
    )

on_show = funktionen.get("on_show", "")
pruefe(
    "on_show kopiert die Session-Daten (list(...)-Momentaufnahme)",
    "list(self.app.photos_taken)" in on_show
    and "list(self.app.template_boxes)" in on_show,
)
pruefe(
    "on_show erstellt die Momentaufnahme VOR dem Thread-Start",
    on_show.find("session_snapshot") != -1
    and on_show.find("session_snapshot") < on_show.find("threading.Thread"),
)
pruefe(
    "Worker bekommt die Momentaufnahme als Argument",
    "session_snapshot" in funktionen.get("_render_final_worker", ""),
)

worker = funktionen.get("_render_final_worker", "")
pruefe(
    "Worker speichert NICHT ohne Fotos (kein leeres weisses Bild auf Platte)",
    "if not photos" in worker,
)

print()
if FEHLER:
    print(f"  {len(FEHLER)} Pruefung(en) fehlgeschlagen")
    sys.exit(1)
print("  Alle Pruefungen bestanden")
