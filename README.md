# 📸 Fexobooth

Professionelle Photobooth-Software für fexobox-Mietgeräte.

## Features

- 🖼️ ZIP-Templates (DSLR-Booth kompatibel)
- 📷 Webcam & DSLR-Support (Canon Webcam Utility)
- 🎨 Bildfilter (SW, Sepia, Warm, Cool, etc.)
- 🖨️ Windows-Druck mit Offset-Anpassung
- 💾 USB-Stick Auto-Sync
- 🔐 Admin-Bereich mit PIN
- 🎬 Start/End-Videos für längere Sessions
- ⚡ Optimiert für schwache Hardware (4GB RAM)

## Tech-Stack

- **GUI:** CustomTkinter (modern, leicht)
- **Kamera:** OpenCV
- **Bildverarbeitung:** Pillow
- **Video:** python-vlc
- **Druck:** win32print

## Installation

```bash
# Repository klonen
git clone https://github.com/fefotec/fexobooth.git
cd fexobooth

# Dependencies installieren
pip install -r requirements.txt

# Starten
python src/main.py
```

## Für Tablets (C:\fexobooth)

```batch
# Update und Start
update_and_start.bat
```

## Konfiguration

Alle Einstellungen in `config.json`. USB-Stick mit `config.json` überschreibt lokale Config.

## Template-Format

ZIP-Dateien mit:
- `template.png` – Overlay mit transparenten Bereichen
- `template.xml` – Foto-Positionen (DSLR-Booth Format)

## Lizenz

Proprietär – fexon e.K.
