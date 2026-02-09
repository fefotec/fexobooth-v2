# Fortschritt - Fexobooth V2

Chronologisches Protokoll aller Änderungen.

---

## 2026-02-09

### Performance & UX Optimierungen (Tablet-Test Feedback)
- **VLC-Warmup:** Plugin-Cache wird beim App-Start im Hintergrund geladen (verhindert 57s Freeze beim ersten Video auf Miix 310)
- **VLC-Ladeanimation:** Subtile Punkte-Animation während VLC noch aufwärmt (statt schwarzer Freeze)
- **Hotspot im Hintergrund:** Start/Stop des Windows Mobile Hotspot blockiert nicht mehr den Hauptthread (~6s gespart)
- **LiveView Vollbild:** Kamera-Bild wird immer bildschirmfüllend angezeigt (kein Template-Overlay mehr in der Session)
- **Final-Screen Redesign:** Buttons als Overlay über dem Bild (größer, prominenter), Bild füllt den ganzen Screen
- **Foto-Wiederholen Button:** Neuer ↻ Button am rechten Rand des Final-Screens (gleiche Vorlage, neue Fotos, kein Video)
- **Taskmanager-Fix:** App erscheint jetzt als Vordergrund-Prozess (WS_EX_APPWINDOW via ctypes + overrideredirect)
- **Fullscreen-Bugfix:** Revert von attributes("-fullscreen") zurück zu overrideredirect(True) - deckt auf Miix 310 korrekt den ganzen Screen ab
- **Session-Screen vereinfacht:** Template-Preview-Rendering entfernt (~200 Zeilen weniger Code, bessere Performance)

### Bugfixes & UI-Verbesserungen (Tablet-Test Feedback Runde 2)
- **VLC-Ladebildschirm:** Richtiger Loading-Screen im StartScreen mit "Software wird geladen..." und Fortschrittsbalken (statt unsichtbare Punkte). Start-Button blockiert bis VLC warm
- **Flash-Image Fix:** Container-Größe Fallback (Screensize) wenn Container noch nicht gelayoutet ist + Logging
- **Final-Screen Bildrand:** Bild wird mit Rand angezeigt (nicht mehr edge-to-edge)
- **Druckanzahl-Text weiß:** Druck-Info im Final-Screen jetzt in weißer Schrift
- **Filter-Performance:** Main-Preview-Rendering im Hintergrund-Thread, kleinere Mini-Previews (BILINEAR statt LANCZOS)
- **App-Icon:** Eigenes fexobooth.ico (aus Cartoon-Maskottchen), eingebunden in Fenster, EXE, Installer und Desktop-Shortcut
- **Desktop-Icon Fix:** Explizites IconFilename für alle Shortcuts im Installer + Icon-Cache-Clear nach Installation

### Bugfixes & Features (Tablet-Test Feedback Runde 3)
- **Flash-Bild Fix:** CTkImage braucht `dark_image` Parameter im Dark Mode - ohne wird nichts angezeigt (gleicher Bug wie beim Logo)
- **Redo per Collage-Foto:** "↻ NOCHMAL" Button erscheint nach jedem Foto einer Collage (4s sichtbar). Erlaubt Wiederholung eines einzelnen Fotos statt der ganzen Collage. Retake-Button aus Final-Screen entfernt
- **Template-Persistenz:** USB-Template wird lokal nach `.booking_cache/cached_template.zip` kopiert. Bleibt auch nach USB-Abzug und Neustart verfügbar. Wird nur bei neuem Template überschrieben
- **Final-Screen Transparenz:** Schwarze Container-Hintergründe um Buttons und Texte entfernt (image_frame und button_frame sind jetzt transparent)
- **ICO Multi-Size:** App-Icon von 16x16 auf 7 Größen (16-256px) erweitert. Desktop-Icon nicht mehr verpixelt
- **Installer Robuster:** `ie4uinit.exe` mit vollem Systempfad + `skipifdoesntexist` Flag. Zusätzlich PowerShell-Fallback zum Löschen des Icon-Cache. Desktop-Shortcut wird immer erstellt (nicht nur bei Task-Auswahl)

### Bugfixes (Tablet-Test Feedback Runde 4)
- **Final-Screen Redesign:** Komplett auf Pack-Layout umgebaut (statt place()-Overlays). Bild zentriert mit 60px Rand, Buttons/Text darunter in eigenem Bereich. Keine Transparenz-Probleme mehr (kein dunkles Rechteck hinter Buttons)
- **Flash-Bild JPEG:** JPEG-Bilder werden jetzt als RGB geladen und direkt ohne Alpha-Maske gepastedt. Vorher: `.convert("RGBA")` + Paste mit Mask schlug bei JPEG fehl. PNG mit Transparenz wird weiterhin korrekt behandelt
- **Desktop-Icon Fix:** `SHChangeNotify(SHCNE_ASSOCCHANGED)` wird jetzt direkt im Installer-Pascal-Script aufgerufen (statt nur Icon-Cache-Dateien zu löschen). Benachrichtigt den Explorer sofort über neue Icons

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
