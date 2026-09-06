"""UI-Redesign 2.4.70 — Verträge aus dem Design-Handoff. Braucht KEINE Box.

Sichert die harten Grenzen des Handoffs statisch ab:
  1. Gäste-Screens nutzen nur noch Pink + Neutraltöne (kein success/error/
     warning mehr — die bleiben Admin-/Service-Flächen vorbehalten).
  2. Keine Emojis/Pfeile in den Kiosk-Texten (de/en/fr).
  3. Alle neuen Redesign-Texte existieren in DE, EN und FR.
  4. Die gebackenen PNG-Assets liegen im Repo und bleiben unter dem Budget.
  5. bind_pressed neutralisiert Hover (Touch-Gerät).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FEHLER = []


def pruefe(name: str, bedingung: bool, detail: str = ""):
    if bedingung:
        print(f"  [ OK  ]  {name}")
    else:
        FEHLER.append(name)
        print(f"  [FEHLER] {name}  {detail}")


# 1. Keine Alarm-/Ampelfarben in den Gäste-Screens
GAESTE_SCREENS = [
    "src/ui/screens/start.py",
    "src/ui/screens/session.py",
    "src/ui/screens/filter.py",
    "src/ui/screens/final.py",
]
for rel in GAESTE_SCREENS:
    quelle = (ROOT / rel).read_text(encoding="utf-8")
    treffer = re.findall(r'COLORS\["(success|error|warning|info)"\]', quelle)
    pruefe(
        f"{Path(rel).name}: keine Ampelfarben (success/error/warning/info)",
        not treffer,
        f"gefunden: {sorted(set(treffer))}",
    )

# 2. + 3. Kiosk-Texte: neue Keys vorhanden und emoji-/pfeilfrei
from src.i18n import TRANSLATIONS

NEUE_KEYS = [
    "start.eyebrow", "gallery.banner_sub",
    "session.hint_countdown", "session.hint_review",
    "filter.auto_continue",
    "final.title_ready", "final.sub_ready", "final.title_rendering",
    "final.rendering_sub",
    "printer.eyebrow", "printer.title_paper", "printer.title_ink",
    "printer.title_cover", "printer.title_jam", "printer.title_generic",
    "printer.body_paper", "printer.body_jam", "printer.after_hint",
]
for locale in ("de-DE", "en-GB", "fr-FR"):
    fehlend = [k for k in NEUE_KEYS if k not in TRANSLATIONS.get(locale, {})]
    pruefe(
        f"i18n {locale}: alle Redesign-Texte vorhanden",
        not fehlend,
        f"fehlend: {fehlend}",
    )

KIOSK_KEYS = [
    "common.start", "common.finish", "common.print", "common.understood",
    "start.choose_mode", "start.tap_option",
    "session.redo", "session.continue",
    "filter.choose_style", "filter.hint", "filter.back_redo", "filter.continue",
    "final.rendering", "final.auto_return",
] + NEUE_KEYS
VERBOTENE_ZEICHEN = re.compile(r"[▶→←↻✨🎨📸🖤🟤📷🔥❄️☀️🎭🌸]|:\w+:")
for locale in ("de-DE", "en-GB", "fr-FR"):
    schmutzig = [
        k for k in KIOSK_KEYS
        if k in TRANSLATIONS.get(locale, {})
        and VERBOTENE_ZEICHEN.search(TRANSLATIONS[locale][k])
    ]
    pruefe(
        f"i18n {locale}: Kiosk-Texte ohne Emojis/Pfeile",
        not schmutzig,
        f"betroffen: {schmutzig}",
    )

# 4. Assets vorhanden und im Budget (Handoff: gesamt < 15 MB, Plan ≈ 2 MB)
ASSETS = [
    "bg_glow_start.png", "card_single.png", "icon_check_40.png",
    "icon_check_36.png", "illu_rendering_160.png", "fexobox-logo-weiss.png",
]
asset_dir = ROOT / "assets" / "ui"
fehlend = [a for a in ASSETS if not (asset_dir / a).exists()]
pruefe("Alle Redesign-Assets liegen in assets/ui/", not fehlend, f"fehlend: {fehlend}")
if not fehlend:
    gesamt = sum((asset_dir / a).stat().st_size for a in ASSETS)
    pruefe(
        f"Asset-Budget eingehalten ({gesamt / 1024:.0f} KB)",
        gesamt < 15 * 1024 * 1024,
    )

# 5. bind_pressed neutralisiert Hover und schützt deaktivierte Buttons
theme = (ROOT / "src" / "ui" / "theme.py").read_text(encoding="utf-8")
pruefe(
    "theme.bind_pressed: Hover = Normalfarbe, Disabled-Schutz",
    "def bind_pressed" in theme
    and "hover_color=normal" in theme
    and '"disabled"' in theme,
)
pruefe(
    "theme: FONTS_UI und RADII definiert",
    "FONTS_UI = {" in theme and "RADII = {" in theme,
)

print()
if FEHLER:
    print(f"  {len(FEHLER)} Pruefung(en) fehlgeschlagen")
    sys.exit(1)
print("  Alle Pruefungen bestanden")
