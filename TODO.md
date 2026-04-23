# TODO - Fexobooth V2

Aufgabenliste mit Prioritäten.

---

## Hoch 🔴

- [x] KRITISCH: Canon DSLR Freeze bei Host-Download behoben (EdsSetObjectEventHandler blockierte Message-Pump)

---

## Mittel 🟡

- [ ] Admin-Menü: "Buchung zurücksetzen" Button
- [ ] Canon DSLR Live-View optimieren (EVF_INTERNAL_ERROR Retry-Logik)
- [ ] Print-Queue Anzeige
- [ ] Drucker-Reset + Fehler-Overlay auf echtem Tablet mit Canon SELPHY testen
- [ ] Event-Wechsel & Systemtest auf Tablet testen (echte Hardware)
- [ ] Erstes GitHub Release erstellen + OTA-Update auf Tablet testen
- [ ] Deployment: Referenz-Tablet einrichten und erstes Image testen
- [ ] Deployment: Clonezilla USB-Stick auf Miix 310 testen (Boot + Capture + Restore)

---

## Niedrig 🟢

_Aktuell keine niedrig priorisierten Aufgaben_

---

## Erledigt ✅

### 2026-04-23
- [x] Auto-Update im Firmen-WLAN (SSID-Whitelist + Internet-Check, still im Background)
- [x] FEXOSAFE-Backup mit Buchungs-ID als Überordner

### 2026-03-18
- [x] USB-Sync Dialog kommt nicht bei Stick-Wiedereinstecken (gleicher Event) — behoben
- [x] `_offer_sync_dialog`: try/except im Thread, Fallback auf pending_count, Logging

### 2026-03-17
- [x] `prepare_image.bat`: Windows-Optimierung + Daten-Bereinigung für Image-Erstellung
- [x] Script wird über Installer mitinstalliert (`deployment/` Ordner + Startmenü)

### 2026-03-13
- [x] Template-Karte: "Wunsch-Template" statt Buchungsnummer/Dateiname anzeigen
- [x] Header-Text anpassen bei nur einer Karte ("Dein Druckformat" statt "Wähle dein Layout!")
- [x] USB-Template vs. User-Template Trennung (Override-Flag)
- [x] Capture-Hintergrund: Weiß statt Schwarz
- [x] LiveView Template-Overlay Absicherung

### 2026-03-12
- [x] Template-Loader: preview.png nicht als Overlay verwenden (Default-Template Fix)
- [x] Start-Screen Refresh nach Template-Wechsel im Kunden-Menü (PIN 2015)
- [x] Galerie: Sharing-Erkennung + Hinweis bei HTTP (kein File-Share ohne HTTPS)

### 2026-03-11
- [x] Kunden-PIN "2015" mit Service-Menü (Template-Auswahl, Overlay-Toggle, Druckstau, Neustart)
- [x] 5x Icon-Tap Neustart entfernt (durch Kunden-PIN ersetzt)
- [x] Filter-Screen: Labels entfernt, Preview größer (Lenovo-Optimierung)
- [x] USB-Status-Indikator feste Breite (Frame-Container statt Label-Width)
- [x] Template-Auswahl mit Vorschau-Bildern aus assets/templates/ Ordner
- [x] Admin-Dialog: Kiosk-Modus ohne Fensterwechsel (alles als Fullscreen-Overlay)
- [x] Admin: Minimieren-Button im Kiosk-Modus

### 2026-03-10
- [x] Export-Dialog blockiert UI (Boot-Drives, grab_set)
- [x] ZIP-Validierung: Anwendungs-ZIPs (.exe, .dll, _internal/) als Template ablehnen
- [x] Default-Template.zip als Fallback einbauen (statt programmatisches 2x2-Grid)
- [x] Freeze-Analyse: Ursache gefunden (fexobooth.zip als Template → 6889x6889 Logo als Overlay → 41s Freeze)
- [x] PowerShell UTF-8 Encoding Fix (`[Console]::OutputEncoding` in allen Subprocess-Aufrufen)

### 2026-03-09
- [x] Drucker-Steuerung: Software-Reset bei Papierstau (3 Stufen: Purge → Spooler → USB)
- [x] Drucker-Steuerung: Canon-Dialoge per SW_HIDE verstecken + eigene Fehlermeldungen
- [x] Drucker-Steuerung: TOPMOST-Overlay mit Bestätigungs-Button ("PAPIER EINGELEGT")
- [x] Drucker-Steuerung: Canon-Dialog-Text per WM_GETTEXT lesen
- [x] Drucker-Steuerung: PowerShell/Konsole-Fenster versteckt (CREATE_NO_WINDOW)
- [x] Dev-Mode: "DRUCKER RESET" Test-Button in Top-Bar
- [x] Template-Overlay im LiveView als Option im Admin-Menü (Kamera-Tab)

### 2026-02-26
- [x] KRITISCH: EDSDK Deadlock behoben (System-Test hing, Tablet musste hard-reboot)
- [x] System-Test: Globaler Timeout (90s) + Abbrechen-Button
- [x] Ctrl+Shift+Q funktioniert jetzt in ALLEN Dialogen (auch mit grab_set)
- [x] Kamera-Status-Anzeige in der Top-Bar (blinkend wenn keine Kamera angeschlossen)
- [x] Canon DSLR ohne SD-Karte: Host-Download entfernt (unzuverlässig), sofort LiveView-Fallback statt 10s Hänger
- [x] Taskleiste: atexit-Handler + Recovery beim App-Start (kein permanentes Verschwinden mehr nach Crash)
- [x] Fix: Permanentes `-topmost` blockierte ALLE Dialoge (USB-Sync, Export, Task-Manager)
- [x] Kiosk-Modus: topmost nur noch kurz bei Fenster-Positionierung (nicht permanent)
- [x] Windows-Benachrichtigungen via Registry unterdrücken (statt topmost-Overlay)
- [x] Notfall-Shortcut Ctrl+Shift+Q zum App-Beenden (auch im Kiosk-Modus)

### 2026-02-25
- [x] Kiosk-Modus: Taskleiste via Windows API verstecken (kein Durchblitzen mehr)
- [x] Kiosk-Modus: Fullscreen-Restore sofort nach Admin/Service-Dialog (nicht 10s Timer)
- [x] Kiosk-Modus: Escape/F11 blockiert (nur per Admin-PIN Vollbild verlassbar)
- [x] Kiosk-Modus: Sicherheitsnetz alle 5s re-assertet Taskleiste
- [x] Fix: Service-PIN Dialog hat Fullscreen nie wiederhergestellt
- [x] Fix: USB-Dialoge (Sync + Export) Vordergrund erzwingen (transient + lift + focus_force)
- [x] USB-Dialoge: Auto-Close nach Kopiervorgang (3s Erfolg, 4s Fehler)
- [x] Final-Screen: Template-Vorschau vollständig sichtbar (nicht mehr abgeschnitten)
- [x] Drucker-Lifetime-Zähler: Gesamt-Drucke im Admin-Menü anzeigen
- [x] Drucker-Lifetime-Zähler: Reset nur per Service-PIN (6588)

### 2026-02-12
- [x] Deployment-System: `deployment/` Ordner mit Clonezilla-Klon-Workflow
- [x] OTA-Update System: Service-Menü Button "Software aktualisieren"
- [x] update_from_github.bat: GitHub Releases statt Source-Archiv
- [x] build_installer.bat: Erstellt immer ZIP für OTA-Updates
- [x] Neues Modul: src/updater.py (GitHub API, Download, Update-Script)

### 2026-02-11
- [x] System-Test: Komplette Session mit Foto pro Slot + automatischer Testdruck
- [x] System-Test "Keine Template-Boxen geladen" Fix (reset_session Reihenfolge)
- [x] USB-Sync: Bestätigungsdialog statt Auto-Kopie (Fortschritt + Abbrechen)
- [x] Service-PIN 6588 Freeze behoben (Dialog-Erstellung nach wait_window)
- [x] Beenden-Button in Admin-Dialog verschoben (nicht mehr im Hauptfenster)
- [x] Galerie zeigt nur lokale Bilder (nicht USB) + No-Cache Headers
- [x] Event-Wechsel-Dialog bei neuem USB-Template (Annehmen/Ablehnen)
- [x] Automatischer System-Test nach Event-Wechsel (Kamera → Template → Druck)
- [x] FEXOSAFE Backup-Stick Erkennung und Bilder-Sicherung
- [x] Pending-Dialog-Queue (Dialoge warten auf StartScreen)
- [x] Strom-Status: Grüner/oranger Blitz in Top-Bar (Netz vs. Akku)
- [x] Drucker-Status blinkende Warnung wenn Drucker aus/offline (wie USB-Warnung)
- [x] Belastungstest-Button im Developer Mode (Top-Bar)

### 2026-02-10
- [x] Flash-Bild gecacht + update_idletasks() für zuverlässige Anzeige
- [x] Loading-Screen: "Das kann bis zu 2 Minuten dauern" Hinweis
- [x] Statistik-Texte weiß (text_primary statt text_muted)
- [x] Auto-Fullscreen nach 10s wenn nicht im Vollbild (nach Admin-Menü)
- [x] Hotspot Encoding-Fix (UnicodeDecodeError cp1252)
- [x] Desktop-Icon Fix: ICO separat in Installer kopiert (PyInstaller _internal-Pfad)
- [x] Offline-Hotspot: hotspot.py mit Multi-Methoden-Ansatz (Tethering + netsh hostednetwork)
- [x] Galerie-Deaktivierung Fix (Booking-Settings überschrieben Config)
- [x] Willkommensnachricht im VLC-Ladescreen (shipping_first_name)
- [x] `live_gallery` statt `online_gallery` als Booking-Meta-Feld
- [x] Bilder löschen: Auch Gallery-Server-Pfad leeren
- [x] Foto-Zähler "5 von 4" beim letzten Foto gefixt
- [x] Flash-Bild zuverlässiger (sofortige Anzeige statt Loop-Tick)
- [x] Template-Karten responsiv (1 Karte=groß, 2=mittel, 3+=klein)
- [x] Print-Vorschau vollständig sichtbar (padx 40→10)

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
