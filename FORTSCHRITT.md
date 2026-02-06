# Fortschritt - Fexobooth V2

Chronologisches Protokoll aller Änderungen.

---

## 2026-02-06

### Diverse Fixes & Verbesserungen
- **Bug Fix:** Logo wird jetzt angezeigt (CTkImage braucht `dark_image` Parameter im Dark Mode)
- **Neuer Filter:** "Insta Glow" - Instagram-artiger Filter (warmer Glow, matte Schatten, leichte Entsättigung)
- **Entfernt:** Countdown-Beep und Foto-Beep komplett entfernt (`winsound.Beep` Aufrufe in session.py)

### Service-Menü (internes Wartungsmenü)
- **Neues Feature:** Service-Menü über separaten PIN (6588) erreichbar
- Menüpunkt "Bilder sichern": Kopiert alle Bilder (Singles + Prints) auf USB-Stick in Ordner mit Event-ID
- Menüpunkt "Alle Bilder löschen": Löscht alle lokalen Bilder (Datenschutz) mit Bestätigungsdialog
- Überschreiben-Abfrage wenn Event-ID Ordner bereits auf USB existiert
- Fortschrittsanzeige und Erfolgs-/Fehlermeldungen bei beiden Aktionen
- Neue Datei: `src/ui/screens/service.py`
- PIN-Dialog erweitert: Erkennt Service-PIN und öffnet Service-Menü statt Admin-Einstellungen
- App-Referenz am Root-Fenster gespeichert (`_photobooth_app`) für Service-Menü Zugriff

### Performance-Optimierung (VLC-Übergang)
- **Bug Fix:** Doppelter Screen-Wechsel nach Zwischen-Videos behoben (video.py)
- **Bug Fix:** VLC-Cleanup: Synchron bei Zwischen-Videos (Kamera braucht DXVA2), async bei Start/End-Videos
- Template-ZIP Cache: Gleiche Datei wird nur 1x entpackt statt 3x
- App-Level Overlay-Cache: LANCZOS-Resize nur 1x pro Session statt bei jedem Resume
- Resume-Delay nach Video: 500ms → 200ms (Kamera bleibt offen)

### PIN-Dialog verbessert
- Responsive Größe (passt sich an Bildschirmgröße an statt feste 400x500)
- Exakte Zentrierung (kein Offset mehr nach unten)
- Schließen-Button (X) oben rechts + Escape-Taste
- Eigene Hintergrundfarbe (bg_medium statt transparent)
- Numpad-Buttons skalieren mit Bildschirmgröße
- Kein Abschneiden mehr auf kleinen Screens

---

## 2026-02-05

### Arbeitsumgebung erstellt
- CLAUDE.md (Projektsteuerung)
- ARBEITSWEISE.md (KI-Zusammenarbeit)
- ROADMAP.md (Anforderungen)
- FORTSCHRITT.md (diese Datei)
- ERKENNTNISSE.md (Lessons Learned)
- TODO.md (Aufgabenliste)

---

## 2026-02-04

### Video-Fix für schwache Hardware
- Windows Media Foundation (MSMF) Backend implementiert
- Threading für Video-Wiedergabe (Frame-Queue)
- Status-Label bei Video-Fehlern
- Video-FPS auf max. 25 begrenzt

### Offline-Hotspot Setup
- Mehrere Fallback-Methoden für Hotspot ohne Internet
- Auto-Start Scheduled Task
- Manuelle Anleitung als letzter Fallback

### Behoben
- Video zeigt schwarzen Bildschirm auf Miix 310
- UI friert ein während Video-Wiedergabe
- Hotspot-Script schlägt fehl ohne Internet

---

## 2026-02-03

### Admin-Menü & Persistenz
- Galerie-Tab im Admin-Menü (SSID, Passwort, Port)
- Statistik-Tab im Admin-Menü (Export, Reset)
- QR-Code Widget überarbeitet (Pink Akzent-Rahmen)
- Buchung + Template Persistenz (.booking_cache/)
- Shared USBManager (Singleton-Pattern)

### Galerie & Statistik Module
- Lokale Galerie mit Flask-Webserver
- QR-Code Generator
- Statistik-Modul (Event-Tracking pro Buchung)
- Buchungsnummer in Top-Bar

### Behoben
- Pending-Files Counter aktualisiert sich nicht live
- Template nach Neustart weg

---

## 2026-02-02

### USB & Booking System
- settings.json Support
- USB-Sync Feature (Pending-Files Queue)

---

## Ältere Einträge

Siehe [CHANGELOG.md](CHANGELOG.md) für das vollständige Release-Changelog.
