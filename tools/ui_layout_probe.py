"""UI-Layout-Prüfstand: rendert Gäste-Screens OHNE Box und vermisst sie.

Aufruf:
    python tools/ui_layout_probe.py [scaling] [screenshot-verzeichnis]

Baut ein echtes 1280×800-CTk-Fenster, instanziiert StartScreen und
FilterScreen mit einer Attrappen-App, misst die Geometrie aller kritischen
Elemente und meldet Verstöße (Element ragt aus dem Bildschirm, Karte
überlappt QR-Panel, WEITER-Button nicht sichtbar …). Mit dem Scaling-
Argument lässt sich der DPI-Faktor der Box emulieren (Miix: ~1.0588).

Auf macOS werden zusätzlich Screenshots (screencapture) abgelegt.
Exit-Code 0 = alle Prüfungen bestanden.
"""
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw

SCALING = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
SHOT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else None

import customtkinter as ctk

FEHLER = []


def pruefe(name, bedingung, detail=""):
    status = "OK  " if bedingung else "FEHLER"
    print(f"  [{status}] {name}  {detail}")
    if not bedingung:
        FEHLER.append(name)


def rel_box(widget, root):
    """(x1, y1, x2, y2) des Widgets in Fenster-Koordinaten."""
    x = widget.winfo_rootx() - root.winfo_rootx()
    y = widget.winfo_rooty() - root.winfo_rooty()
    return (x, y, x + widget.winfo_width(), y + widget.winfo_height())


def overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


class AttrappenBookingManager:
    cached_template_path = None

    def template_file_fingerprint(self, path):
        return "probe"

    def cached_template_fingerprint(self):
        return "probe"

    is_loaded = False


class AttrappenApp:
    """Nur die Attribute, die Start-/Filter-Screen wirklich anfassen."""

    def __init__(self, root):
        self.root = root
        self.config = {
            "gallery_enabled": True,
            "gallery_show_qr": True,
            "allow_single_mode": True,
            "locale": "de-DE",
            "gallery": {"hotspot_ssid": "fexobox-gallery",
                        "hotspot_password": "fotobox123"},
        }
        overlay = Image.new("RGBA", (1800, 1200), (244, 242, 239, 255))
        d = ImageDraw.Draw(overlay)
        for bx in [(120, 140, 860, 560), (940, 140, 1680, 560),
                   (120, 640, 860, 1060), (940, 640, 1680, 1060)]:
            d.rectangle(bx, fill=(30, 30, 40, 255))
        self.cached_usb_template = {
            "path": "probe.zip", "name": "probe.zip", "overlay": overlay,
            "boxes": [{"box": (120, 140, 860, 560), "angle": 0}] * 4,
            "fingerprint": "probe", "source": "usb",
        }
        self._usb_stick_template = None
        self._user_template_override = False
        self._app_uploaded_template_active = False
        self.booking_manager = AttrappenBookingManager()
        self.stress_test_active = False
        self.current_screen_name = "filter"
        foto = Image.new("RGB", (1920, 1080), (60, 70, 90))
        ImageDraw.Draw(foto).ellipse([700, 200, 1220, 720], fill=(200, 170, 150))
        self.photos_taken = [foto.copy() for _ in range(4)]
        self.current_filter = "none"
        from src.filters import FilterManager
        self.filter_manager = FilterManager()

    def show_screen(self, name):
        pass


def galerie_stub():
    """Ersetzt src.gallery — der Prüfstand braucht keinen Flask-Server."""
    mod = types.ModuleType("src.gallery")
    qr = Image.new("RGB", (200, 200), "white")
    d = ImageDraw.Draw(qr)
    for i in range(0, 200, 20):
        d.rectangle([i, (i * 3) % 180, i + 10, (i * 3) % 180 + 10], fill="black")
    mod.generate_qr_code = lambda payload, size=200: qr.resize((size, size))
    mod.get_app_display_code = lambda: "272834"
    mod.get_app_pairing_url = lambda port: "fexobox://probe"
    mod.get_gallery_url = lambda port: "http://192.168.137.1:8080"
    mod.set_gallery_app_context = lambda ctx: None
    return mod


def main() -> int:
    sys.modules["src.gallery"] = galerie_stub()

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("1280x800+0+25")
    root.title(f"Layout-Probe scaling={SCALING}")
    # Fuer Screenshots muss das Fenster VOR anderen liegen (sonst landet der
    # Browser des Entwicklers im Bild). Nur relevant, wenn SHOT_DIR gesetzt ist.
    if SHOT_DIR:
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()
    if abs(SCALING - 1.0) > 0.0001:
        ctk.set_widget_scaling(SCALING)

    from src.ui.screens.start import StartScreen
    from src.ui.screens.filter import FilterScreen

    ergebnisse = {}

    # ---------- StartScreen ----------
    app = AttrappenApp(root)
    start = StartScreen(root, app)
    start.pack(fill="both", expand=True)
    # Boesester Fall vom Box-Foto 06.09.: Position wurde OHNE aktives Panel
    # berechnet (Galerie-Flag kommt erst spaeter aus den Booking-Settings) —
    # danach blendet _update_qr_code das Panel ein. Seit dem Fix zieht
    # _update_qr_code die Kartenposition selbst nach.
    app.config["gallery_enabled"] = False
    start._refresh_template_cards()
    start._position_main_content()
    app.config["gallery_enabled"] = True
    start._update_qr_code()
    root.update_idletasks()
    root.update()
    time.sleep(0.3)
    root.update()

    print(f"\n== StartScreen (scaling {SCALING}) ==")
    banner = rel_box(start.gallery_banner, root)
    print(f"  QR-Panel: {banner}")
    for key, card in start.cards.items():
        cb = rel_box(card, root)
        print(f"  Karte '{key}': {cb}")
        pruefe(f"Karte '{key}' komplett im Bild",
               cb[0] >= 0 and cb[2] <= 1280 and cb[3] <= 800, str(cb))
        pruefe(f"Karte '{key}' überlappt QR-Panel nicht",
               not overlap(cb, banner), f"Karte {cb} vs Panel {banner}")
    sb = rel_box(start.start_btn, root)
    pruefe("START-Button komplett im Bild", sb[3] <= 800 and sb[0] >= 0, str(sb))
    pruefe("START-Button überlappt QR-Panel nicht", not overlap(sb, banner),
           f"Button {sb} vs Panel {banner}")
    pruefe("QR-Panel komplett im Bild",
           banner[0] >= 0 and banner[2] <= 1280 and banner[3] <= 800, str(banner))

    if SHOT_DIR and sys.platform == "darwin":
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        import subprocess
        x, y = root.winfo_rootx(), root.winfo_rooty()
        subprocess.run(["screencapture", f"-R{x},{y},1280,800",
                        str(SHOT_DIR / f"start_{SCALING}.png")], check=False)

    start.destroy()

    # ---------- FilterScreen ----------
    filt = FilterScreen(root, app)
    filt.pack(fill="both", expand=True)
    filt.on_show()
    # Thumbs zusaetzlich synchron erzeugen: der after()-Weg aus dem Worker-
    # Thread braucht den echten Tk-mainloop; die update()-Schleife des
    # Pruefstands stellt ihn nicht zuverlaessig nach (auf der Box laeuft er).
    filt._generate_filter_previews()
    ende = time.time() + 1.0
    while time.time() < ende:
        root.update()
        time.sleep(0.02)

    print(f"\n== FilterScreen (scaling {SCALING}) ==")
    for key, card in filt.filter_buttons.items():
        cb = rel_box(card, root)
        pruefe(f"Kachel '{key}' komplett im Bild",
               cb[0] >= 0 and cb[2] <= 1280 and cb[3] <= 800, str(cb))
        pruefe(f"Kachel '{key}' hat ein Vorschaubild",
               getattr(card, "preview_ctk", None) is not None)
    wb = rel_box(filt.continue_btn, root)
    print(f"  WEITER: {wb}, gemappt={filt.continue_btn.winfo_ismapped()}")
    pruefe("WEITER-Button sichtbar und komplett im Bild",
           filt.continue_btn.winfo_ismapped() and wb[3] <= 800 and wb[1] >= 0,
           str(wb))
    ab = rel_box(filt.auto_label, root)
    pruefe("Auto-Weiter-Text sichtbar", filt.auto_label.winfo_ismapped() and ab[3] <= 800, str(ab))

    if SHOT_DIR and sys.platform == "darwin":
        import subprocess
        x, y = root.winfo_rootx(), root.winfo_rooty()
        subprocess.run(["screencapture", f"-R{x},{y},1280,800",
                        str(SHOT_DIR / f"filter_{SCALING}.png")], check=False)

    filt.on_hide()
    root.destroy()

    print()
    if FEHLER:
        print(f"{len(FEHLER)} Layout-Verstoß/Verstöße bei scaling={SCALING}")
        return 1
    print(f"Alle Layout-Prüfungen bestanden (scaling={SCALING})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
