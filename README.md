# Fexobooth V2

Photobooth-Software für fexobox Mietgeräte.

## 🎯 Ziel-Hardware

| Gerät | Lenovo Miix 310 |
|-------|-----------------|
| Display | 1280 × 800 px @ 10.1" |
| RAM | 4 GB |
| OS | Windows 10/11 |
| Betrieb | **Offline** (kein Internet!) |

### ⚠️ Performance-Richtlinien

Die Software läuft auf schwacher Hardware. **Jede Zeile Code muss ressourcenschonend sein!**

- Keine unnötigen Hintergrund-Tasks
- Bilder effizient verarbeiten (nicht alles im RAM halten)
- GUI-Updates sparsam (kein 60fps Rendering)
- Flask-Server ist okay (~20-30 MB RAM)
- Große Bibliotheken vermeiden wenn möglich

### 🎬 Video-Wiedergabe

Video-Wiedergabe nutzt **Windows Media Foundation (MSMF)** als Backend:
- Nutzt Windows-eigene H.264 Codecs (kein VLC/FFmpeg nötig)
- Threading verhindert UI-Freeze auf schwacher Hardware
- Fallback auf FFMPEG wenn MSMF nicht verfügbar
- Max. 25 FPS für Performance

## 📁 Projekt-Struktur

```
fexobooth-v2/
├── src/
│   ├── app.py              # Hauptanwendung
│   ├── ui/                 # GUI-Komponenten
│   │   ├── screens/        # Start, Capture, Preview, Final
│   │   └── theme.py        # Farben, Fonts (optimiert für 1280x800)
│   ├── camera/             # Webcam + Canon DSLR Support
│   ├── storage/            # USB, Lokal, Booking, Statistik
│   ├── gallery/            # Flask Webserver + QR-Code
│   ├── templates/          # Template-Loader
│   └── config/             # Konfiguration
├── setup/
│   └── setup_hotspot.ps1   # Windows Hotspot einrichten
├── CHANGELOG.md            # Änderungsprotokoll
└── README.md               # Diese Datei
```

## 🚀 Features

- **USB-Template laden** - ZIP vom Stick wird automatisch erkannt
- **Buchungsnummer anzeigen** - Aus settings.json vom Dashboard
- **Lokale Galerie** - Gäste scannen QR-Code → sehen Fotos auf Handy
- **Statistik** - Fotos, Prints, Sessions pro Event
- **Persistenz** - Template + Buchung bleiben nach USB-Abzug/Neustart erhalten
- **Offline-Sync** - Bilder werden nachträglich auf USB kopiert

## 📋 Dokumentation

**WICHTIG:** Alle Änderungen müssen dokumentiert werden!

1. **CHANGELOG.md** - Was wurde wann geändert?
2. **Code-Kommentare** - Warum wurde etwas so gemacht?
3. **Diese README** - Architektur-Entscheidungen

### Warum?

- Software läuft auf 200+ Fotoboxen im Feld
- Debugging ohne Internet schwierig
- Nächster Entwickler muss verstehen was passiert

## 🔧 Entwicklung

### Voraussetzungen

```bash
Python 3.10+
pip install -r requirements.txt
```

### Starten

```bash
python main.py
```

### Auf Tablet deployen

1. PyInstaller Build erstellen
2. Auf Master-Tablet installieren + testen
3. Windows-Image erstellen
4. Image auf alle Tablets klonen

## 📱 Galerie-Hotspot einrichten

Einmalig auf jedem Tablet als Administrator ausführen:

```powershell
# PowerShell als Admin
cd setup
.\setup_hotspot.ps1 -SSID "fexobox-gallery" -Password "fotobox123"
```

Der Hotspot startet danach automatisch bei jedem Windows-Login.

## 🐛 Bugs & Issues

Siehe [CHANGELOG.md](CHANGELOG.md) für bekannte Probleme und Fixes.

---

**Repository:** [github.com/fefotec/fexobooth-v2](https://github.com/fefotec/fexobooth-v2)

## 🔧 Debugging & Logs

### Log-Dateien
Die Software schreibt detaillierte Logs nach:
```
logs/fexobooth_YYYYMMDD.log
```

**Log-Level:** DEBUG (alle Details)

### Wichtige Log-Einträge
- `📂 USB gefunden beim Start:` - USB wurde erkannt
- `✅ Settings vom USB geladen:` - settings.json wurde geladen
- `📋 Config nach Settings-Load:` - Zeigt aktive Einstellungen
- `📊 Statistiken geladen:` - Statistik-Datei gefunden

### Statistik-Datei
```
fexobooth_statistics.json  (im Projektordner, NICHT auf USB!)
```

## 🚀 Starten

Doppelklick auf `start_fexobooth.bat` oder:
```batch
python src/main.py
```
