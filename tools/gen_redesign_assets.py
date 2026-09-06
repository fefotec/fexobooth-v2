"""Erzeugt die statischen PNG-Assets des UI-Redesigns 2.4.70.

Einmalig laufen lassen (python tools/gen_redesign_assets.py) — die Ergebnisse
liegen versioniert in assets/ui/. Verläufe und Schatten sind hier bewusst
EINGEBACKEN: Als fertige PNGs kosten sie auf der Box zur Laufzeit nichts
(harte Grenze aus dem Design-Handoff: keine Echtzeit-Verläufe in Tk).

Wichtig fürs Glow-Bild: Tk kennt keine echte Transparenz — Text-Labels über
dem Hintergrundbild malen ihre Fläche in #08080C. Deshalb bleiben die Zonen,
in denen dynamischer Text liegt (Textblock links, unteres Drittel), im Asset
praktisch rein #08080C; die Glows sitzen nur in der oberen Ecke/Kante.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "ui"
OUT.mkdir(parents=True, exist_ok=True)

BG = (8, 8, 12)          # #08080C
PINK = (224, 6, 117)     # #E00675
VIOLET = (104, 127, 252)  # #687FFC
PAPER = (244, 242, 239)  # #F4F2EF


def _radial_glow(size, center, radius, color, max_alpha):
    """Weicher runder Glow als RGBA-Layer."""
    layer = Image.new("L", size, 0)
    d = ImageDraw.Draw(layer)
    d.ellipse(
        [center[0] - radius, center[1] - radius,
         center[0] + radius, center[1] + radius],
        fill=max_alpha,
    )
    layer = layer.filter(ImageFilter.GaussianBlur(radius * 0.55))
    glow = Image.new("RGBA", size, color + (0,))
    glow.putalpha(layer)
    return glow


def bg_glow_start():
    size = (1280, 800)
    img = Image.new("RGBA", size, BG + (255,))
    # Pink oben links, Blauviolett oben mittig-rechts — beide klar oberhalb
    # des Textblocks (y >= 128), unteres Drittel bleibt rein #08080C.
    img = Image.alpha_composite(img, _radial_glow(size, (40, -160), 420, PINK, 96))
    img = Image.alpha_composite(img, _radial_glow(size, (860, -220), 460, VIOLET, 70))
    # Textblock-Zone (x 60–900, y 110–620) und unteres Drittel hart auf
    # Grundfarbe zurückziehen, mit weichem Übergang.
    flat = Image.new("RGBA", size, BG + (0,))
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rectangle([0, 250, 1280, 800], fill=255)     # ab Kartenreihe: flach
    d.rectangle([48, 104, 920, 260], fill=255)     # Textblock: flach
    mask = mask.filter(ImageFilter.GaussianBlur(48))
    flat.putalpha(mask)
    solid = Image.new("RGBA", size, BG + (255,))
    img = Image.composite(solid, img, mask)
    img.convert("RGB").save(OUT / "bg_glow_start.png", optimize=True)


def icon_check(size):
    scale = 4  # supersampled zeichnen, dann verkleinern = saubere Kanten
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, s - 1, s - 1], fill=PINK + (255,))
    w = 3 * scale
    pts = [(int(s * 0.28), int(s * 0.52)), (int(s * 0.44), int(s * 0.68)),
           (int(s * 0.72), int(s * 0.34))]
    d.line(pts, fill=(255, 255, 255, 255), width=w, joint="curve")
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    img.save(OUT / f"icon_check_{size}.png", optimize=True)


def card_single():
    """Vorschau der Einzelfoto-Karte: heller Bildträger mit Platzhalter-Fläche."""
    img = Image.new("RGBA", (210, 140), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, 209, 139], radius=6, fill=PAPER + (255,))
    d.rounded_rectangle([14, 14, 195, 111], radius=4, fill=(200, 196, 212, 255))
    d.rectangle([14, 118, 195, 126], fill=(224, 221, 214, 255))
    img.save(OUT / "card_single.png", optimize=True)


def illu_rendering():
    """160×160-Kachel mit eingebackenem Pink→Blauviolett-Verlauf + Foto-Motiv."""
    s = 160
    grad = Image.new("RGB", (s, s))
    for y in range(s):
        for x in range(s):
            tt = (x + y) / (2 * s - 2)
            grad.putpixel((x, y), tuple(
                int(PINK[i] + (VIOLET[i] - PINK[i]) * tt) for i in range(3)
            ))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=32, fill=255)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # Foto-Rahmen-Motiv in Weiß
    d.rounded_rectangle([44, 52, 116, 112], radius=10, outline=(255, 255, 255, 255), width=5)
    d.ellipse([58, 64, 74, 80], fill=(255, 255, 255, 255))
    d.polygon([(52, 104), (82, 76), (96, 90), (104, 82), (110, 104)], fill=(255, 255, 255, 255))
    # Funkel oben rechts
    d.polygon([(126, 26), (131, 38), (143, 43), (131, 48), (126, 60), (121, 48), (109, 43), (121, 38)],
              fill=(255, 255, 255, 255))
    img.save(OUT / "illu_rendering_160.png", optimize=True)


if __name__ == "__main__":
    bg_glow_start()
    icon_check(40)
    icon_check(36)
    card_single()
    illu_rendering()
    for f in sorted(OUT.iterdir()):
        print(f.name, f.stat().st_size)
