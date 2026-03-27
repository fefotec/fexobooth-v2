# Changelog

Alle wichtigen Änderungen an diesem Projekt werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

---

## [2.1.1] - 2026-03-27 - Template-Persistenz Fix, Kamera-Schutz

### Geändert
- **Interne Tablet-Kamera wird ignoriert** — Kein stiller Fallback auf die verdeckte interne Kamera mehr. Wenn keine externe Kamera angeschlossen ist, blinkt "KEINE KAMERA!" in der Status-Bar. Externe Kamera wird automatisch erkannt wenn sie im Betrieb angesteckt wird

### Behoben
- **Template-Persistenz nach Neustart ohne USB-Stick** — Template blieb nicht erhalten wenn die Box ohne Stick neu gestartet wurde. Ursache: `cached_template.zip` wurde erst beim Starten einer Session geschrieben, nicht beim Laden des Events
- **Template-Erkennung auf USB** — BookingManager erkannte nur ZIPs namens `template.zip`, alle anderen Dateinamen wurden ignoriert
- **Event-Wechsel verlor Template** — Bei Event-Wechsel wurde das Template in Memory geladen aber nicht auf Disk persistiert
- **Stick-Wiedereinstecken ohne Template** — Wenn die Box ohne Stick neu gestartet wurde und der Stick dann eingesteckt wurde, blieb das Fallback-Template bis zur nächsten Session
- **Installer: Gecachtes Template überlebte Neuinstallation** — `_internal\.booking_cache` wurde bei Install/Uninstall nicht gelöscht
- **Installer: `.booking_cache` wurde bei Installation vorab erstellt** — Verzeichnis entsteht jetzt erst im Produktionsbetrieb

---

## [2.0.0] - 2026-03-19 - Erster stabiler Release

### Hinzugefügt
- **Kunden-PIN "2015"** — Template wählen, Live-View Overlay togglen, Druckstau beheben, Windows neustarten (ohne Admin-Zugang)
- **Template-Vorschau** — Template-Auswahl zeigt Vorschau-Bilder aus ZIP-Dateien. Ordner `assets/templates/`
- **Minimieren-Button** in Admin-Einstellungen (nur im Kiosk-Modus)
- **prepare_image.bat** — Tablet für Clonezilla-Image vorbereiten (Windows-Optimierung + Daten-Bereinigung)
- **USB-Sync Dialog Fallback** — Pending-Count als Fallback wenn count_missing fehlschlägt

### Geändert
- **Admin-Dialog im Kiosk-Modus** — Fullscreen-Overlay statt Fenstermodus-Wechsel
- **Filter-Screen optimiert** für Lenovo Miix 310 — Labels entfernt, Preview größer
- **USB-Status-Indikator** hat jetzt feste Breite (Frame-Container)

### Entfernt
- **5x Icon-Tap Neustart** entfernt (durch Kunden-PIN "2015" ersetzt)

### Behoben
- **USB-Sync Dialog** kam nicht bei Stick-Wiedereinstecken (gleicher Event) — Background-Thread fehlte try/except + Fallback
- **Template-Loader:** `preview.png` nicht mehr als Overlay verwenden
- **Start-Screen Refresh:** Template-Wechsel über Kunden-PIN 2015 aktualisiert sofort die Karten
- **Galerie Sharing:** Erkennt ob Foto-Teilen möglich ist (HTTPS nötig)
- **Template-Karte:** Zeigt "Wunsch-Template" statt rohem Dateinamen
- **Capture-Hintergrund:** Weiß statt Schwarz bei Templates ohne Overlay-Frame
- **USB-Template:** Überschreibt nicht mehr die explizite User-Auswahl

### Bekannte Einschränkungen
- Galerie: Foto-Sharing mit Bild nur über HTTPS möglich (lokales HTTP → nur Text-Sharing)

---

## [2026-02-04] - Video-Fix für schwache Hardware & Offline-Hotspot

### Hinzugefügt
- **Windows Media Foundation (MSMF) Backend für Video-Wiedergabe**
  - Nutzt Windows-eigene H.264 Codecs
  - Fallback auf FFMPEG und Default-Backend
  - Verhindert schwarzen Bildschirm auf schwacher Hardware

- **Threading für Video-Wiedergabe**
  - Frame-Lesen in separatem Thread
  - Queue-basierte Kommunikation (Producer-Consumer Pattern)
  - Verhindert UI-Einfrieren auf schwacher Hardware (z.B. Lenovo Miix 310)

- **Status-Label bei Video-Fehlern**
  - Zeigt "Video konnte nicht geladen werden" bei Problemen
  - Automatischer Weitersprung nach 3 Sekunden

- **Offline-Hotspot Setup** (`setup/setup_hotspot.ps1`)
  - Mehrere Fallback-Methoden für Hotspot ohne Internet
  - Versucht: Loopback-Profil → Verfügbare Profile → netsh hostednetwork
  - Erstellt Auto-Start Scheduled Task
  - Manuelle Anleitung als letzter Fallback

### Geändert
- Video-FPS auf max. 25 begrenzt (Performance auf schwacher Hardware)
- Skip-Button erscheint erst wenn Video läuft oder Fehler auftritt

### Behoben
- **Video zeigt schwarzen Bildschirm auf Miix 310**
  - Ursache: OpenCV Default-Backend kann H.264/MP4 nicht decodieren
  - Fix: MSMF-Backend nutzt Windows-eigene Codecs

- **UI friert ein während Video-Wiedergabe**
  - Ursache: Frame-Lesen blockiert Main-Thread
  - Fix: Threading mit Frame-Queue

- **Hotspot-Script schlägt fehl ohne Internet**
  - Ursache: NetworkOperatorTetheringManager braucht Internetverbindung
  - Fix: Mehrere Fallback-Methoden inkl. netsh hostednetwork

### Technische Details
- `src/ui/screens/video.py` komplett überarbeitet
- `setup/setup_hotspot.ps1` komplett überarbeitet
- Getestet für: Lenovo Miix 310 (Atom CPU, 4GB RAM)

---

## [2026-02-03] - Admin-Menü & Persistenz

### Hinzugefügt
- **Galerie-Tab im Admin-Menü**
  - SSID konfigurierbar
  - Passwort konfigurierbar
  - Port konfigurierbar
  - Info-Box mit Anleitung

- **Statistik-Tab im Admin-Menü**
  - Aktuelle Session anzeigen (Fotos, Prints, Sessions)
  - Letzte 5 Events anzeigen
  - CSV-Export Button
  - Statistik zurücksetzen (mit Bestätigung)

- **QR-Code Widget überarbeitet**
  - Pink Akzent-Rahmen (fexobox Branding)
  - WLAN-Name (SSID) angezeigt
  - Passwort angezeigt
  - Kompakte Anleitung: "Verbinden → Scannen → Fertig!"

- **Buchung + Template Persistenz** (`src/storage/booking.py`)
  - Buchungsdaten werden lokal gecached (`.booking_cache/last_booking.json`)
  - Template-ZIP wird lokal kopiert (`.booking_cache/cached_template.zip`)
  - Nach Neustart: Letzte Buchung automatisch wiederhergestellt
  - Wechsel nur bei ANDERER booking_id

- **Shared USBManager** (`src/storage/local.py`)
  - Singleton-Pattern für USBManager
  - Alle Module teilen dieselbe pending_files Liste
  - Live-Counter für fehlende USB-Bilder

### Geändert
- Template-Labels umbenannt:
  - "Layout" → "Druck-Vorlage"
  - "Einzelfoto" → "Einzelbild"

- `find_usb_template()` prüft jetzt auch den Cache wenn kein USB da ist

- Galerie-Checkbox aus Allgemein-Tab entfernt (jetzt in eigenem Galerie-Tab)

### Behoben
- **Pending-Files Counter aktualisiert sich nicht live**
  - Ursache: LocalStorage hatte eigenen USBManager
  - Fix: Alle Module nutzen jetzt `get_shared_usb_manager()`

- **Template nach Neustart weg**
  - Ursache: Template wurde nur vom USB geladen, nicht gecached
  - Fix: Template wird in `.booking_cache/` kopiert und beim Start geladen

### Technische Details
- Neue Dateien:
  - `.booking_cache/last_booking.json` - Buchungsdaten Cache
  - `.booking_cache/cached_template.zip` - Template Cache
- `.gitignore` erweitert um Cache-Dateien

---

## [2026-02-03] - Galerie & Statistik Module

### Hinzugefügt
- **Lokale Galerie mit Webserver** (`src/gallery/`)
  - Flask-Server für Foto-Galerie
  - QR-Code Generator
  - Responsive HTML für Handys
  - Hotspot-Setup Script (`setup/setup_hotspot.ps1`)

- **Statistik-Modul** (`src/storage/statistics.py`)
  - Event-Tracking pro Buchung
  - Erfasst: Fotos, Prints, Sessions, Zeitraum
  - JSON-Export
  - `get_all_stats()` und `reset_all()` Methoden

- **Buchungsnummer in Top-Bar**
  - Zeigt aktive Buchungs-ID
  - Format: 📋 123456

---

## [2026-02-02] - USB & Booking System

### Hinzugefügt
- **settings.json Support** (`src/storage/booking.py`)
  - Lädt Buchungsdaten vom USB-Stick
  - Steuert Features: print_singles, online_gallery, dslr_camera

- **USB-Sync Feature** (`src/storage/usb.py`)
  - Pending-Files Queue wenn USB nicht verfügbar
  - Automatischer Sync bei USB-Einstecken
  - Dialog zur Bestätigung

---

## Legende

- ✅ Fertig & getestet
- 🚧 In Arbeit
- ❌ Bekannter Bug
- 💡 Idee/Vorschlag
