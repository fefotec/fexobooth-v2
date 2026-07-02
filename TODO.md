# TODO - Fexobooth V2

Aufgabenliste mit Prioritäten.

---

## Performance vor Release 🏎️ (Analyse-Lauf 2026-07-02 ausgewertet, Fixes in 2.4.12)

> Log `fexobooth_20260702_114253.log` (Nikon-Session): 4 Bremsen identifiziert und gefixt —
> Overlay-Foto-Skalierung pro Frame, Fotoanzeige-Refresh (380 ms/Tick), Filter auf 24-MP-Originalen,
> Final-Rendern im UI-Thread. Details in FORTSCHRITT.md.

- [ ] **Nachtest 2.4.12 auf der Fotobox** (Dev-Mode, Nikon): komplette Collage-Session + Filter
  antippen + Druck. Erwartung: LiveView konstant ~7–8 fps über alle 4 Fotos, keine
  `UI-HITCH`-Serien während der Fotoanzeige, Filterwechsel sofort (nach Precache),
  `Final-Rendern (Hintergrund)` im Log statt Einfrieren. Log wieder an Claude geben.
- [ ] **Webcam-Lauf gesondert messen** (der 2026-07-02-Lauf war Nikon): `High-Res Capture Timing`
  inkl. `fourcc` prüfen. Falls YUY2 aktiv → MJPG erzwingen; ggf. Auflösungs-Umschaltung hinter
  Countdown „1"/Blitz vorziehen (Umschaltung bleibt erhalten, wird nur versteckt).
- [ ] Optional (nach Nachtest, falls Grund-fps zu niedrig): Countdown-Ziffern vorrendern
  (Font + 8 Schatten laufen pro Frame); Basis-Anzeigepfad (CTkImage pro Frame) prüfen.
- [ ] Nikon-Capture-Feintuning (aktuell ~4,1 s sichtbar, kameraseitig): JPEG-Größe M an der
  D3300 testen (bleibt DSLR-Qualität, halbiert Transfer) und/oder `noaf`-Capture für
  vorfokussierte Box-Distanz.

---

## Bugs 🐞 (beim nächsten Software-Update nebenbei mitfixen)

- [ ] **Filter-Screen läuft nicht automatisch ab.** Der Filter-Screen soll automatisch weiterlaufen/ablaufen, tut das aber erst, nachdem man **einmal den Filter gewechselt** hat. (Wahrscheinlich startet der Auto-Ablauf-Timer erst beim ersten Filter-Wechsel statt direkt beim Anzeigen des Screens.)
- [ ] **Box friert nach dem ersten Video ein.** Nach dem ersten Video hängt die Software; ein Tipp auf den Touchscreen löst sie wieder. Vermutlich UI-Thread / Video-Handling (evtl. Zusammenhang mit dem Galerie-Server prüfen). Muss stabilisiert werden.
- [ ] **Drucker-Status-Log entspammen** (nur Loghygiene, kein Verhaltensfehler). Bei ausgeschaltetem Drucker loggt die Box `DRUCKER AUS!` + „Overlay wird gezeigt / kein Overlay" **jede Sekunde** (im Dev-Log aus 2026-06-14: tausende identische Zeilen über ~40 Min) und verdeckt echte Events. Fix: nur bei **Status-WECHSEL** loggen (in `src/app.py` Drucker-Status-Check + `src/printer/controller.py get_error`), Poll-/Klassifizierungs-/Overlay-Logik unverändert lassen. Die INFO-Zeile „Drucker-Fehler erkannt → Overlay wird gezeigt" ist zudem irreführend (danach folgt „kein Overlay (other)") → mitklären. **Erst im Dev-Mode testen** (Kernprinzip 8), nicht in einen Same-Day-Flotten-Build.

---

## Nikon D3300 DSLR (FexoNikonBridge, Variante 3) 📷

> digiCamControl-App-Ansatz (Variante 2) am 2026-07-02 **verworfen** (sichtbares Fenster +
> Webserver antwortet nie). Neu: eigene unsichtbare `FexoNikonBridge.exe` (C#/.NET 4.8,
> Motor: MIT-Bibliothek `CameraControl.Devices`, rohes PTP über Windows-WPD — wie dslrBooth).
> Python-Seite fertig + gegen Fake-Bridge End-to-End verifiziert.
> Vertrag/Details: [bridge/README.md](bridge/README.md) + [ROADMAP.md](ROADMAP.md).

- [x] **Bridge lokal gebaut + ohne Kamera getestet (2026-07-02):** .NET-SDK 8 auf dem Work-PC
  installiert, `dotnet build` → 0 Fehler; ping/list/init/quit gegen die echte EXE sauber
  (Library-stdout-Banner entdeckt + stummgeschaltet). Python-Client gegen echte Bridge 8/8 OK.
- [ ] **Bridge solo mit angesteckter D3300 prüfen** (am Work-PC möglich, vor dem Fotobox-Test):
  PowerShell: `'{"id":1,"cmd":"init"}' | bridge\FexoNikonBridge\bin\Release\net48\FexoNikonBridge.exe`
  → muss `"ok":true,"camera":"..."` liefern; danach `frame`/`capture` durchspielen
  (oder direkt den kompletten Booth-Flow im Dev-Mode: `python src\main.py --dev`).
- [ ] **CI-Build einmal mitlaufen lassen** (beim nächsten Push; GitHub → Actions → Version `2.4.11`):
  bestätigt, dass auch der Cloud-Build die Bridge baut (Gate schlägt sonst an).
- [ ] **Setup 2.4.11 auf der Fotobox installieren**, `camera_type = nikon` (Admin-Menü),
  Dev-Mode starten. Prüfen: Log „Nikon-Bridge-Warmup: bereit" kurz nach dem Start,
  **kein sichtbares Fremdfenster**, Startscreen bleibt vorn.
- [ ] **LiveView prüfen:** Bild im Session-Screen? (Log: „Nikon/FexoNikonBridge bereit: …")
- [ ] **Capture prüfen:** Vollauflösungs-Foto (≈6000×4000) kommt zurück, kein LiveView-Fallback-Log.
- [ ] **Robustheit:** USB ab-/anstecken während Idle → Status-Warnung erscheint/verschwindet;
  Bridge-Prozess stirbt (Taskmanager) → nächste Session startet ihn neu (initialize-Pfad).
- [ ] **Erst nach erfolgreichem Hardware-Test** als „hardware-validiert" in ROADMAP/FORTSCHRITT markieren.

**Bekannte offene Punkte (Nikon-only, 0 Live-Flotten-Impact):**
- [ ] **(major, entschärft) Erste Session initialisiert auf dem UI-Thread.** Durch den Warmup
  (Bridge-Start + Kamera-Vorverbindung im Hintergrund) bleiben normal nur `lv_start` + erster
  Frame (~1–3 s). Sauberer Fix wäre `initialize()` in einen Worker-Thread in `session.py`
  (Muster `_capture_photo_worker`) — erst nach dem Hardware-Test angehen, betrifft auch Canon-Flow.
- [ ] **(minor) Doppel-Capture** im Fehlerfall: schlägt `capture_photo()` mit `None` fehl, ruft der
  Webcam-Fallthrough in `session.py` `get_high_res_frame()` → erneut `capture_photo()`.
  Spiegelt Canon-Verhalten; ggf. DSLR-Pfad autoritativ machen + Log-Zeile.
- [ ] **(minor) Capture blockiert Frames:** während `capture` läuft, wartet `get_frame()` am
  Bridge-Lock (eine Anfrage gleichzeitig; Timeout deckt das Lock-Warten jetzt ab). Für den
  Booth-Flow okay (LiveView pausiert beim Auslösen sowieso).
- [ ] **OTA-Bootstrap beachten:** Das ERSTE Update auf 2.4.11 läuft noch mit dem alten
  Update-BAT (kopiert `bridge/` nicht) → Nikon-Testbox per **Installer** aktualisieren, nicht OTA.

---

## App-Plattform-Fundament (kommendes Box-Update) 🧱

> Einmaliges, zukunftssicheres Fundament, damit danach Features rein per **App-Update**
> kommen können (App ändern = billig, Box ändern = teuer). Strategie + Begründung:
> [../fexobox-app/PLATTFORM-STRATEGIE.md](../fexobox-app/PLATTFORM-STRATEGIE.md).
>
> **PRODUKTREGEL (wichtig):** Kunden OHNE gebuchte Galerie dürfen auf dem Box-Screen
> **NICHTS** Zusätzliches sehen (kein QR, kein Banner) – sonst denken sie „ist hier was
> versteckt?". Der Kanal läuft **unsichtbar im Hintergrund**; Verbinden ohne Galerie
> läuft komplett über die App (Event-Code + SSID/PW in der App).

**Box-Seite gebaut + verifiziert am 2026-06-14** (Flask `test_client` + Multi-Agent-Review,
0 kritische/hohe Findings). Build/Test auf echter Box steht noch aus (siehe unten).

- [x] **Lokalen Kanal entkoppeln + dauerhaft:** Hotspot + Flask-API laufen unabhängig von
  `gallery_enabled`, Start weiterhin 4 s verzögert. Screen-UI (QR/Banner) unverändert an `gallery_enabled`.
- [x] **Verbinden ohne Galerie nur über App:** `/api/v1/pair-by-code` läuft jetzt immer (Support-Route),
  die Box zeigt nichts an. (App-Seite „Verbinden OHNE QR" bleibt fexobox-app-TODO.)
- [x] **`GET /api/v1/status` erweitert:** `software_version` + `gallery_enabled` + Capability-Liste
  (`settings_patch`, `template_upload`, `asset_upload`, `software_ota`,
  `feature_flags:[live_gallery, print_enabled, print_singles, dslr_camera, max_prints]`).
- [x] **Generische Apply-Endpunkte:** `apply/settings` + `apply/template` (Aliase auf `upload/*`),
  `apply/assets` (sicheres ZIP-Staging) + `apply/software` (OTA). `upload/settings`+`upload/template` bleiben.
- [x] **Feature-Flag-Registry + ehrliche Meldung in `/status`** (Mechanismus steht). _Hinweis:_ Box-UI
  rendert die heute bekannten Flags bereits; konkrete UI für **neue** Flags kommt mit dem jeweiligen Feature.
- [x] **App-OTA-Upload:** `POST apply/software` mit SHA256-Verifikation + bestehendem Rollback,
  Staff-Auth Service-PIN 6588 (als HMAC), nur im Idle. Detailplan: [PLAN-APP-OTA.md](PLAN-APP-OTA.md).
- [x] **Soft-Mode bleibt** – keine Signatur-Prüfung; Log-Warnung „in v2.5.0…" entschärft.

**Noch offen (folgt mit den jeweiligen Features / App-Seite):**
- [ ] **`apply/assets`-Verbraucher:** Endpunkt nimmt Asset-ZIPs sicher entgegen + legt sie ab (Staging).
  Ein konkreter Box-seitiger Verbraucher (z. B. neues Loading-Video übernehmen) wird mit dem Feature nachgezogen.
- [ ] **App-OTA auf einer echten Box testen** (M4 aus PLAN-APP-OTA.md): inkl. absichtlich kaputter ZIP →
  Rollback muss greifen (kein Brick). Vorher: M0 lokale Bandbreite messen.
- [ ] **Optional härter:** Service-PIN für OTA ist 4-stellig (HMAC schützt vor Klartext, nicht vor
  Brute-Force im lokalen Netz). Falls je nötig: zusätzlich Pairing-Token verlangen oder PIN verlängern.

---

## Hoch 🔴

- [x] KRITISCH: Canon DSLR Freeze bei Host-Download behoben (EdsSetObjectEventHandler blockierte Message-Pump)

---

## Mittel 🟡

- [ ] Hotline-Prompt: `Druck-Korrektur` erst aufnehmen, wenn die Funktion offiziell ausgerollt und der Supportablauf bestätigt ist
- [ ] Admin-Menü: "Buchung zurücksetzen" Button
- [ ] Canon DSLR Live-View optimieren (EVF_INTERNAL_ERROR Retry-Logik)
- [ ] Print-Queue Anzeige
- [ ] Drucker-Reset + Fehler-Overlay auf echtem Tablet mit Canon SELPHY testen
- [ ] Event-Wechsel & Systemtest auf Tablet testen (echte Hardware)
- [ ] Erstes GitHub Release erstellen + OTA-Update auf Tablet testen
- [ ] Deployment: Referenz-Tablet einrichten und erstes Image testen
- [ ] Deployment: Clonezilla USB-Stick auf Miix 310 testen (Boot + Capture + Restore)

### Heim-WLAN-Workflow Phase 1 — "Bilder sichern"-Screen lokal

Details siehe ROADMAP.md Abschnitt "Heim-WLAN-Workflow". Kein Backend nötig.

- [ ] `BookingSettings` um Feld `online_gallery: bool` erweitern (`src/storage/booking.py`)
- [ ] `from_dict` mappt `features.online_gallery` aus settings.json
- [ ] `to_dict` schreibt das Feld in den Cache
- [ ] Idempotenz-Datei `.booking_cache/homecheck_handled.json` (Liste verarbeiteter Booking-IDs)
- [ ] Heim-Check-Logik in `src/company_network.py` ergänzen: nach Auto-Update-Block prüfen, ob `last_booking.online_gallery == True` UND `BILDER/<booking_id>/` nicht leer UND Booking-ID noch nicht abgehakt
- [ ] Neuer Modal-Screen "Bilder dieser Buchung jetzt sichern?" (am `FexosafeBackupDialog` orientiert)
- [ ] Button startet vorhandenen `FexosafeBackupDialog`, danach Booking-ID in Idempotenz-Datei abhaken
- [ ] Test: am Tablet im Firmen-WLAN mit echter Online-Galerie-Buchung verifizieren

### Heim-WLAN-Workflow Phase 2 — Box-Identität + Heim-Check-API

Details siehe ROADMAP.md. Setzt Phase 1 voraus, braucht Laravel-Backend-Code.

- [ ] [laravel] `POST /api/v1/box/learn-identity`: Booking-IDs + HMAC-Timestamp → `box_barcode` + Sanctum-Token
- [ ] [laravel] `GET /api/v1/box/{barcode}/homecheck` (Sanctum): letzte Buchung, Alerts, pending Aktionen
- [ ] [laravel] Sanctum auf `Photobox`-Model oder eigene `photobox_tokens`-Tabelle
- [ ] [laravel] IP-Allowlist auf den beiden Endpoints (nur fexon-WLAN)
- [ ] Booth: `box_identity.json` (write-once), Erweiterung im Update-Skript zum Schutz
- [ ] Booth: kleine `booking_history.json` mit den letzten ~3 Booking-IDs
- [ ] Booth: Identity-Learning-Call beim ersten Heim-WLAN-Erkennung wenn keine Identität da
- [ ] Booth: Heim-Check-Call bei jeder Heim-WLAN-Erkennung (Sanctum-Token), auswerten + Screen anzeigen
- [ ] Admin-Screen: kleine Zeile "Box-Identität: FB-XXX ✅" + "Zurücksetzen"-Button
- [ ] Test: gesamter Flow auf Tablet im Firmen-WLAN

### Update-Strategie / Staged Rollout

Details siehe ROADMAP.md Abschnitt "Update-Strategie / Staged Rollout".
Bis Phase 2 steht: Disziplin mit GitHub-Pre-Release-Flag (kein Code).

**Stufe Auto-Rollback (eigenständig, unabhängig von Phase 2):**
- [ ] `src/updater.py`: `_internal_OLD/` 24 h aufbewahren statt sofort löschen
- [ ] Beim ersten App-Start nach Update: Smoke-Test (Kamera/Drucker/Config/Galerie-Server)
- [ ] Bei Smoke-Test-Fehler: automatischer Rollback auf `_internal_OLD/`
- [ ] Markierung in `update_history.json` damit kein Endlos-Rollback-Loop entsteht

**Stufe Release-Manager (mit Phase 2):**
- [ ] [laravel] Tabelle `photobox_version_pins` (photobox_id, target_version, channel, set_at)
- [ ] [laravel] Heim-Check-Response um `update_channel` + optional `target_version` erweitern
- [ ] Booth: `update_channel` + optionalen Pin im Updater berücksichtigen (statt nur GitHub-Latest)
- [ ] [laravel] Release-Manager-UI: Übersicht aller Boxen pro Release mit Status + Health
- [ ] [laravel] Wellen-Steuerung: explizite Box-Auswahl / Anzahl / Prozent
- [ ] [laravel] "Welle stoppen", "Auf alle ausrollen", "Box auf Version fixieren"
- [ ] Booth meldet aktuelle Version + Smoke-Test-Status im Heim-Check für Dashboard-Übersicht

---

## Niedrig 🟢

### Heim-WLAN-Workflow Phase 3 — Auto-Upload (optional, nach DSGVO-Klärung)

Details siehe ROADMAP.md. Datenschutz vorab klären, dann erst angehen.

- [ ] Datenschutz prüfen: Upload nur bei `online_gallery == True` reicht als Zustimmung?
- [ ] Workflow definieren: Mitarbeiter-Freigabe vor Sichtbarmachung in Kundengalerie?
- [ ] [laravel] `POST /api/v1/box/{barcode}/gallery-image` (idempotent per File-Hash)
- [ ] [laravel] Server-side Throttling damit Heimkehr-Welle die Leitung nicht sättigt
- [ ] Booth: Upload-Queue mit Resume bei Verbindungsabbruch
- [ ] Booth: lokale Markierung erfolgreich hochgeladener Bilder
- [ ] Booth: Auto-Upload-Trigger wenn Heim-Check sagt "Bilder fehlen für diese Buchung"

---

## Erledigt ✅

### 2026-07-02
- [x] **🎉 Nikon D3300 hardware-validiert:** FexoNikonBridge auf der Fotobox erfolgreich —
  unsichtbarer Warmup, LiveView, 4× Capture in 6000×4000. (Log `fexobooth_20260702_114253.log`)
- [x] Performance-Analyse-Lauf ausgewertet + 4 Fixes umgesetzt (Overlay-Basis-Cache,
  Fotoanzeige-Cache, Filter-Arbeitskopien + Precache, Final-Rendern im Worker) → Build `2.4.12`.
- [x] digiCamControl-Ansatz verworfen und restlos zurückgebaut (Autostart, Installer-Einbettung,
  CI-Download, i18n `DCC FEHLT!`, Felix-Runbook). Neue Architektur FexoNikonBridge (Variante 3)
  vorbereitet: C#-Bridge-Gerüst + Python-Client + CI-Build-Schritt; Build-Kandidat `2.4.11`.
  Verifiziert: Smoke-Test 82/82, Fake-Bridge-E2E 11/11.

### 2026-07-01
- [x] Nikon-DCC-Logging im Developer Mode erweitert und Build-Kandidat auf `2.4.9` gesetzt.
- [x] Startscreen-Version umgesetzt: Top-Bar zeigt links neben `FEXOBOOTH` die lokale Version aus
  `src/__init__.py`; Build-Kandidat auf `2.4.8` gesetzt.

### 2026-06-19
- [x] **Druck-Korrektur (2015er-Menü) wird beim Neustart nicht mehr zurückgesetzt.** `print_adjustment` stand fälschlich in den bei jedem Start erzwungenen Produktions-Overrides (`_PRODUCTION_DEFAULT_OVERRIDES` in `src/config/config.py`) → Override gewann gegen die gespeicherten Werte. Entfernt; Start-Default kommt aus `defaults.py`, Eventwechsel-Reset bleibt über `reset_event_defaults()`. Mit simuliertem Neustart verifiziert.

### 2026-06-14
- [x] App-Template-Push stabilisiert: wiederholte Template-Uploads nutzen eindeutige `app_template_*.zip` Dateien statt gesperrte `cached_template.zip` zu überschreiben; Apply-Marker fuer Settings/Template werden getrennt bestaetigt. Regressionsnotizen in `docs/FEXOBOX-APP-API.md`.

### 2026-05-20
- [x] Hotline-Prompt „Felix" auf reinen V2-Modus umgestellt (alle Boxen jetzt auf V2). V1-Blöcke, Versions-Gate und USB-Hub-Lampen-Diagnose aus `support/HOTLINE_PROMPT_FELIX.md` entfernt.

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
