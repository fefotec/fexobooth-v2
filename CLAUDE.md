# Fexobooth V2 - Projektsteuerung

## Projekt-Info

| Feld | Wert |
|------|------|
| **Name** | Fexobooth V2 |
| **Beschreibung** | Photobooth-Software für fexobox Mietgeräte |
| **Stack** | Python 3.10+, CustomTkinter, OpenCV, Pillow, Flask, PyInstaller |
| **Ziel-Hardware** | Lenovo Miix 310 (1280×800, 4GB RAM, Offline-Betrieb) |
| **Arbeitsumgebung erstellt** | 2026-02-05 |

---

## Pflichtanweisungen

### Bei jedem relevanten Prompt:

1. **Dokumentation lesen** - Lies die relevanten Projektdateien:
   - `ROADMAP.md` - Anforderungen und Ziele
   - `FORTSCHRITT.md` - Was wurde bereits gemacht?
   - `ERKENNTNISSE.md` - Lessons Learned und Tech-Entscheidungen
   - `TODO.md` - Offene Aufgaben

2. **Dokumentation pflegen** - Aktualisiere selbstständig ohne Aufforderung:
   - `FORTSCHRITT.md` - Nach jeder abgeschlossenen Änderung
   - `ERKENNTNISSE.md` - Bei neuen Erkenntnissen oder Tech-Entscheidungen
   - `TODO.md` - Aufgaben hinzufügen/abhaken
   - `CHANGELOG.md` - Für Release-relevante Änderungen

---

## Performance-Richtlinien (WICHTIG!)

Die Software läuft auf schwacher Hardware. **Jede Zeile Code muss ressourcenschonend sein!**

- Keine unnötigen Hintergrund-Tasks
- Bilder effizient verarbeiten (nicht alles im RAM halten)
- GUI-Updates sparsam (kein 60fps Rendering)
- Flask-Server ist okay (~20-30 MB RAM)
- Große Bibliotheken vermeiden wenn möglich
- Video max. 25 FPS

---

## Projekt-Struktur

```
fexobooth-v2/
├── src/
│   ├── app.py              # Hauptanwendung
│   ├── ui/                 # GUI-Komponenten (Screens, Theme)
│   ├── camera/             # Webcam + Canon DSLR Support
│   ├── storage/            # USB, Lokal, Booking, Statistik
│   ├── gallery/            # Flask Webserver + QR-Code
│   ├── templates/          # Template-Loader
│   └── config/             # Konfiguration
├── setup/                  # Setup-Scripts (Hotspot, Tablet)
├── assets/                 # Icons, Templates, Videos
└── BILDER/                 # Ausgabe (Prints, Singles)
```

---

## Verwandte Dokumentation

- [README.md](README.md) - Projekt-Übersicht und Architektur
- [BUILD.md](BUILD.md) - Build & Installation Guide
- [CHANGELOG.md](CHANGELOG.md) - Release-Changelog
