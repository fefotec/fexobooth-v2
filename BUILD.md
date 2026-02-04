# FexoBooth Build & Installation Guide

## Übersicht

Diese Anleitung beschreibt, wie man FexoBooth als installierbares Programm erstellt und auf neuen Geräten einrichtet.

---

## Option 1: Installer erstellen (Empfohlen für Produktion)

### Voraussetzungen

1. **Python 3.10+** mit pip
2. **Inno Setup 6** - Download: https://jrsoftware.org/isdl.php
3. Alle Python-Dependencies installiert (`pip install -r requirements.txt`)

### Build-Prozess

1. Öffne eine Kommandozeile im Projektverzeichnis
2. Führe aus:
   ```batch
   build_installer.bat
   ```
3. Der Installer wird erstellt in: `installer_output\FexoBooth_Setup_2.0.exe`

### Was der Installer macht

- Installiert FexoBooth nach `C:\FexoBooth` (oder wählbarer Pfad)
- Erstellt Startmenü-Einträge
- Optional: Desktop-Verknüpfung
- Optional: Autostart beim Windows-Start
- Bietet an, den WLAN-Hotspot einzurichten
- Startet FexoBooth nach der Installation

### Installierte Dateien

Nach der Installation finden sich folgende Dateien in `C:\FexoBooth`:

```
C:\FexoBooth\
├── FexoBooth.exe          # Hauptprogramm
├── start_fexobooth.bat    # Start-Script
├── start_dev.bat          # Entwicklermodus
├── update_from_github.bat # Update ohne Git
├── config.json            # Konfiguration
├── config.example.json    # Beispiel-Konfiguration
├── assets/                # Icons, Templates, Videos
├── setup/                 # Hotspot-Setup-Scripte
├── BILDER/                # Ausgabe-Verzeichnisse
│   ├── Prints/
│   └── Single/
└── logs/                  # Log-Dateien
```

---

## Option 2: Entwicklungs-Setup auf neuem Tablet

Für Tests auf einem neuen Gerät (z.B. Tablet mit Webcam):

### Schnell-Setup

1. Kopiere `setup_new_tablet.bat` auf einen USB-Stick
2. Führe das Script auf dem neuen Tablet aus
3. Das Script:
   - Prüft Python-Installation
   - Lädt FexoBooth von GitHub
   - Installiert alle Dependencies
   - Erstellt Konfiguration
   - Bietet Hotspot-Setup an

### Manuelles Setup

1. **Python installieren**: https://www.python.org/downloads/
   - WICHTIG: "Add Python to PATH" aktivieren!

2. **Verzeichnis erstellen**:
   ```batch
   mkdir C:\FexoBooth-Dev
   cd C:\FexoBooth-Dev
   ```

3. **Code von GitHub holen**:
   ```batch
   update_from_github.bat
   ```
   Oder manuell: GitHub-ZIP herunterladen und entpacken

4. **Dependencies installieren**:
   ```batch
   pip install -r requirements.txt
   ```

5. **Konfiguration erstellen**:
   ```batch
   copy config.example.json config.json
   ```

6. **Starten**:
   ```batch
   start_dev.bat
   ```

---

## Updates

### Mit Git (falls installiert)
```batch
update_and_start.bat
```

### Ohne Git
```batch
update_from_github.bat
```

Das Script:
- Lädt die neueste Version als ZIP von GitHub
- Aktualisiert alle Quelldateien
- Behält die lokale `config.json`
- Bietet an, Dependencies zu aktualisieren

---

## BAT-Dateien Übersicht

| Datei | Zweck |
|-------|-------|
| `start_fexobooth.bat` | Startet FexoBooth normal |
| `start_dev.bat` | Startet im Entwicklermodus (Debug-Logging, CPU/RAM-Anzeige) |
| `update_and_start.bat` | Git pull + Start (benötigt Git) |
| `update_from_github.bat` | GitHub ZIP-Download + Update (ohne Git) |
| `setup_new_tablet.bat` | Komplette Erstinstallation für neues Gerät |
| `build_installer.bat` | Erstellt den Windows-Installer |

---

## Hotspot für Galerie

Der WLAN-Hotspot ermöglicht Gästen, die Fotos über QR-Code anzusehen.

### Einrichtung (einmalig)

1. Als Administrator ausführen:
   ```
   setup\einmalig_hotspot_einrichten.bat
   ```

2. Konfiguration:
   - SSID: `fexobox-gallery`
   - Passwort: `fotobox123`

3. Der Hotspot startet automatisch bei jedem Windows-Start.

---

## Autostart konfigurieren

### Bei Installer-Installation
Der Installer bietet eine Checkbox für Autostart.

### Manuell einrichten
1. Drücke `Win + R`
2. Tippe `shell:startup` und drücke Enter
3. Erstelle eine Verknüpfung zu:
   - Für Installer: `C:\FexoBooth\FexoBooth.exe`
   - Für Entwicklung: `C:\FexoBooth-Dev\start_fexobooth.bat`

---

## Troubleshooting

### "Python nicht gefunden"
- Python installieren von https://www.python.org/
- Bei Installation "Add Python to PATH" aktivieren
- Terminal neu starten

### "Module nicht gefunden"
```batch
pip install -r requirements.txt
```

### "Hotspot startet nicht"
- Script als Administrator ausführen
- Windows Mobile Hotspot in Einstellungen aktivieren
- WLAN-Adapter muss Hotspot unterstützen

### "Kamera nicht erkannt"
- In `config.json` prüfen: `camera_type` und `camera_index`
- Andere Programme schließen, die die Kamera nutzen

### Build schlägt fehl
- Alle Dependencies installiert?
- Inno Setup 6 installiert?
- Pfade in `fexobooth.spec` korrekt?

---

## Technische Details

### PyInstaller Konfiguration
Siehe `fexobooth.spec` für die EXE-Erstellung:
- Bündelt Python und alle Libraries
- Packt Assets (Icons, Templates, Videos) ein
- Enthält Canon EDSDK für DSLR-Unterstützung

### Inno Setup Konfiguration
Siehe `installer.iss` für den Installer:
- Standard-Pfad: `C:\FexoBooth`
- Autostart via Startmenü-Verknüpfung
- Erstellt alle benötigten Verzeichnisse
- Konfiguriert Deinstallation
