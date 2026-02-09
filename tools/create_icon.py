"""Erzeugt fexobooth.ico aus dem PNG-Quellbild

Schneidet den schwarzen Rand ab und erstellt ICO mit allen nötigen Größen.
Einmalig ausführen: python tools/create_icon.py
"""

from PIL import Image
from pathlib import Path

# Pfade
SRC_IMAGE = Path(r"C:\Users\cfisc\Dropbox\PC\Downloads\freepik__take-the-head-of-cartoon-character-shown-in-img1-a__43083.png")
OUTPUT_ICO = Path(__file__).parent.parent / "assets" / "fexobooth.ico"
OUTPUT_PNG = Path(__file__).parent.parent / "assets" / "fexobooth_icon.png"

# Bild laden
img = Image.open(SRC_IMAGE).convert("RGBA")
print(f"Original: {img.size}")

# Schwarzen Rand automatisch entfernen (BoundingBox des nicht-schwarzen Bereichs)
# Pixel mit Alpha > 0 UND nicht komplett schwarz finden
pixels = img.load()
w, h = img.size

# BoundingBox finden: Bereich wo Pixel nicht schwarz/transparent sind
min_x, min_y, max_x, max_y = w, h, 0, 0
for y in range(h):
    for x in range(w):
        r, g, b, a = pixels[x, y]
        # Pixel ist "nicht schwarzer Rand" wenn es heller als reines Schwarz ist
        if a > 128 and (r > 15 or g > 15 or b > 15):
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)

print(f"Content-Bereich: ({min_x}, {min_y}) - ({max_x}, {max_y})")

# Etwas Padding lassen (2px)
pad = 2
min_x = max(0, min_x - pad)
min_y = max(0, min_y - pad)
max_x = min(w, max_x + pad)
max_y = min(h, max_y + pad)

# Zuschneiden
cropped = img.crop((min_x, min_y, max_x, max_y))
print(f"Zugeschnitten: {cropped.size}")

# Quadratisch machen (zentriert)
size = max(cropped.size)
square = Image.new("RGBA", (size, size), (0, 0, 0, 0))
offset_x = (size - cropped.width) // 2
offset_y = (size - cropped.height) // 2
square.paste(cropped, (offset_x, offset_y))
print(f"Quadratisch: {square.size}")

# PNG-Version speichern (256x256 für App-Nutzung)
OUTPUT_PNG.parent.mkdir(parents=True, exist_ok=True)
png_256 = square.copy()
png_256.thumbnail((256, 256), Image.Resampling.LANCZOS)
png_256.save(OUTPUT_PNG, "PNG")
print(f"PNG gespeichert: {OUTPUT_PNG}")

# ICO mit allen Standard-Größen erzeugen
ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
ico_images = []

for s in ico_sizes:
    resized = square.copy()
    resized = resized.resize(s, Image.Resampling.LANCZOS)
    ico_images.append(resized)

# ICO speichern
ico_images[0].save(
    OUTPUT_ICO,
    format="ICO",
    sizes=ico_sizes,
    append_images=ico_images[1:]
)
print(f"ICO gespeichert: {OUTPUT_ICO}")
print("Fertig!")
