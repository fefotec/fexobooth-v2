# TODO - Fexobooth V2

Aufgabenliste mit Prioritäten.

---

## Hoch 🔴

_Aktuell keine dringenden Aufgaben_

---

## Mittel 🟡

- [ ] Admin-Menü: "Buchung zurücksetzen" Button
- [ ] Canon DSLR Live-View optimieren
- [ ] Print-Queue Anzeige

---

## Niedrig 🟢

_Aktuell keine niedrig priorisierten Aufgaben_

---

## Erledigt ✅

### 2026-02-09
- [x] Flash-Bild Fix: CTkImage dark_image im Dark Mode (Auslöse-Bild wurde nicht angezeigt)
- [x] Redo pro Collage-Foto: "↻ NOCHMAL" Button nach jedem Einzelfoto statt am Ende
- [x] Template-Persistenz: USB-Template wird lokal gecacht (überlebt USB-Abzug + Neustart)
- [x] Final-Screen: Schwarze Container-Hintergründe entfernt (transparente Overlays)
- [x] App-Icon: Multi-Size ICO (16-256px) statt nur 16x16 (war verpixelt)
- [x] Installer: ie4uinit.exe Fehler behoben + PowerShell-Fallback + Desktop-Icon immer überschrieben
- [x] VLC-Warmup beim App-Start (57s Freeze auf Miix 310 behoben)
- [x] Hotspot Start/Stop in Hintergrund-Threads (6.3s Blockierung behoben)
- [x] LiveView immer Vollbild (Template-Overlay entfernt)
- [x] Final-Screen: Buttons größer als Overlay über Bild
- [x] App als Vordergrund-Prozess im Taskmanager (fullscreen statt overrideredirect)

### 2026-02-06
- [x] Bug Fix: Logo-Anzeige (CTkImage dark_image für Dark Mode)
- [x] Neuer Filter: "Insta Glow" (Instagram-Style)
- [x] Countdown-Ton und Foto-Beep komplett entfernt
- [x] Service-Menü: Internes Wartungsmenü über PIN 6588 (Bilder sichern, Bilder löschen)
- [x] PIN-Dialog: Responsive Größe, Zentrierung, Schließen-Button, eigene Farbe
- [x] Performance-Optimierung: Doppelter Screen-Wechsel, VLC-Cleanup, Template-Cache, Overlay-Cache

### 2026-02-05
- [x] Arbeitsumgebung erstellen (CLAUDE.md, ARBEITSWEISE.md, etc.)

### 2026-02-04
- [x] Video-Fix für schwache Hardware (MSMF Backend)
- [x] Threading für Video-Wiedergabe
- [x] Offline-Hotspot Setup überarbeiten

### 2026-02-03
- [x] Admin-Menü: Galerie-Tab
- [x] Admin-Menü: Statistik-Tab
- [x] QR-Code Widget überarbeiten
- [x] Buchung + Template Persistenz
- [x] Shared USBManager implementieren
- [x] Lokale Galerie mit Flask-Webserver
- [x] Statistik-Modul

### 2026-02-02
- [x] settings.json Support
- [x] USB-Sync Feature
