# Changelog

Alle wichtigen Änderungen an diesem Projekt werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

---

## [2.4.0] - 2026-04-30 - HMAC-Signatur (Soft-Mode) + Spiegel-Bug im Auto-Test

### Behoben
- **System-Test (Auto-Test für neue Events) spiegelte das Test-Foto fälschlicherweise.** [system_test.py:384](src/ui/dialogs/system_test.py#L384) hatte ein verschollenes `cv2.flip(frame, 1)`, obwohl die Capture-Pfade in [session.py](src/ui/screens/session.py) bewusst nicht spiegeln (siehe v2.2.3-Fix). Folge: der Print im Systemtest sah seitenverkehrt aus, obwohl echte Capture-Prints korrekt waren.

### Neu — settings.json HMAC-Signatur (Soft-Mode)
Vorbereitung für nachträgliche Upgrade-Buchungen über das Kundenportal: settings.json kann ab sofort vom Laravel-Backend mit HMAC-SHA256 signiert werden. Verhindert, dass Kunden lokal Features wie `dslr_camera`, `fullframe_prints` oder `max_prints` manipulieren.

- **Neues Feld `_signature`** in der settings.json (Format: `hmac_sha256:<hex>`)
- **Soft-Mode aktiv (v2.4.x):**
  - Unsigned-JSONs werden weiterhin akzeptiert, aber mit Log-Warning markiert (Migration zu Laravel-Signing).
  - Signed-JSONs mit korrektem HMAC werden akzeptiert.
  - **Signed-JSONs mit falschem HMAC werden IMMER abgelehnt** — auch im Soft-Mode (Manipulationsversuch).
- **Geprüft an drei Einstiegspunkten** in [booking.py](src/storage/booking.py):
  1. `_find_settings_file()` — manipulierte JSONs werden gar nicht erst als Kandidat aufgenommen.
  2. `check_usb_for_new_booking()` — keine "neue Buchung erkannt"-Meldung bei kaputter Signatur.
  3. `load_from_usb()` — Final-Check vor dem Cachen.
- **Cache** (`.booking_cache/last_booking.json`) bleibt unsigniert — wird nur lokal von der Box selbst geschrieben, ist nicht über USB einspielbar.
- **Strict-Mode geplant für v2.5.0** nach Stabilisierungsphase.

### Konfiguration
- HMAC-Geheimnis aktuell als Konstante `_HMAC_SECRET` in `src/storage/booking.py`. Muss identisch zum Laravel-`SETTINGS_HMAC_SECRET` sein, sobald Laravel Signing scharf schaltet. Build-Zeit-Override via PyInstaller folgt sobald Laravel-Seite produktiv signiert.

---

## [2.3.3] - 2026-04-30 - Service-Menü: responsiv für Quer- und Hochformat

### Behoben
- **Service-Menü (PIN 6588) war im Querformat unten abgeschnitten** — Card war 500 px breit + Buttons untereinander gestapelt, das ergab eine schmale hohe Card die auf 1280×800 nicht in die Höhe passte.

### Fix — adaptives Layout
- **Querformat (Width ≥ Height):** Card 900 × 650, Buttons in **2×2 Grid** angeordnet. Passt komfortabel auf 1280×800.
- **Hochformat (Width < Height):** Card 520 × 92% Höhe, Buttons untereinander wie vorher.
- **Compact-Modus bei `screen_height < 700`:** kleinere Buttons + Paddings.
- **Status-Bereich + Versions-Info am unteren Rand der Card** — immer sichtbar, nicht in einem Scrollbereich versteckt.

---

## [2.3.2] - 2026-04-30 - Admin-Dialog: topmost + Datei-Dialog-Fix

### Behoben
- **Admin-Dialog verschwand wenn ein Datei-Auswahl-Dialog geöffnet wurde** (📁-Button im Admin-Menü). Der Dialog wurde nicht zerstört — er rutschte hinter das Kiosk-Root-Fullscreen, weil ihm `attributes("-topmost", True)` fehlte. Andere Dialoge in der App (FexosafeBackup, UpdateProgress) hatten das schon korrekt.

### Fix
1. `AdminDialog.__init__()`: `attributes("-topmost", True)` gesetzt — Dialog bleibt immer vor dem Root sichtbar.
2. `_create_file_picker()` browse-Funktion: Vor `filedialog.askopenfilename()` topmost kurz auf `False` (damit der Datei-Dialog überhaupt **vor** dem Admin-Dialog erscheinen kann), danach wieder `True` + `lift()` + `focus_force()`. Plus `parent=self` als Hinweis ans OS.
3. CSV-Export (`asksaveasfilename`): identische Logik.

---

## [2.3.1] - 2026-04-29 - Admin-Dialog: Z-Order-Fix + Diagnose-Logging

### Behoben
- **Admin-Dialog (PIN 3198) schloss sich nach wenigen Sekunden** und der ADMIN-Button reagierte danach nicht mehr (User-Bericht: tritt auch mit Maus auf, also nicht Touch-Race). Mein Fix in v2.2.9 (Click-outside-Handler entfernt) war nicht der echte Grund.
- Wahrscheinliche Ursache: `_check_fullscreen_restore()` läuft alle 5 s und rief `_hide_taskbar()` auf (Win32-`ShowWindow`-Calls) — auch bei offenem Dialog (kein Toplevel-Check im else-Zweig). Win32-Calls können den Z-Order stören → Dialog verschwindet hinter dem Root-Window.

### Fix
- `_check_fullscreen_restore()` macht jetzt **gar nichts** wenn ein Toplevel-Dialog offen ist — auch keine Taskleisten-Operationen.
- Toplevel-Erkennung erweitert: prüft `winfo_class()=="Toplevel"` UND `isinstance(child, CTkToplevel)`.

### Diagnose
- `AdminDialog.destroy()` loggt jetzt den **vollständigen Caller-Stack**. Falls der Bug doch nochmal auftritt, zeigt das Log direkt wer den Dialog schließt.

---

## [2.3.0] - 2026-04-29 - Update-Pfade mit Timestamp (kein File-Lock-Konflikt mehr)

### Behoben
- **„Update fehlgeschlagen — Datei wird von anderem Prozess verwendet"**: Die `download_update()` nutzte einen festen Dateinamen `%TEMP%\fexobooth_update.zip`. Wenn Windows Defender das ZIP nach dem letzten erfolgreichen Update noch scannte (Real-Time-Schutz lockt frische ZIPs/EXEs für einige Sekunden bis Minuten), schlug der nächste Update-Versuch fehl. Auch `fexobooth_updater.bat` und `fexobooth_update_extract/` hatten feste Namen — gleiche Gefahr.

### Fix
- **Eindeutige Dateinamen pro Update-Lauf**: ZIP, BAT und Extract-Verzeichnis bekommen jetzt einen Timestamp + PID-Suffix:
  - `fexobooth_update_<YYYYMMDD_HHMMSS>_<PID>.zip`
  - `fexobooth_updater_<timestamp>.bat`
  - `fexobooth_update_extract_<timestamp>/`
- **Robustes `unlink()`**: Falls die Datei doch existiert (extrem unwahrscheinlich wegen Timestamp+PID), wird der Lösch-Versuch in `try/except` gepackt und im Notfall ein Alternativname verwendet.
- **Orphan-Cleanup mit Glob-Patterns**: `cleanup_orphan_downloads()` findet jetzt alle alten Update-Reste (sowohl alte feste Namen als auch neue Timestamp-Namen) via `glob('fexobooth_update*.zip')` etc.

---

## [2.2.9] - 2026-04-29 - Bug-Fixes: Admin-Dialog + OTA-Custom-Assets

### Behoben
- **Admin-Dialog (PIN 3198) ging gelegentlich beim Öffnen sofort wieder zu** und der ADMIN-Button reagierte danach nicht mehr. Ursache: Der PIN-Dialog hatte `pin_frame.bind("<Button-1>", lambda e: self.destroy())` (Click-outside-zum-Schließen). Auf Touch-Screens kommt es vor, dass Touch-Down auf der Karte und Touch-Up auf dem Hintergrund landet → Dialog schließt direkt. Plus: ein hängender `grab` am Parent verhinderte weitere Klicks. Fix: Click-outside-Handler entfernt (User schließt nur noch über `✕` oder ESC), `destroy()` Override garantiert `grab_release`.
- **OTA-Update überschrieb User-Videos und Custom-Bilder.** `assets/videos/start.mp4` + `end.mp4` wurden mit den Defaults aus dem ZIP überschrieben, ebenso ggf. ein Custom-`flash_image` im `assets/`-Root. Fix: Vor dem `xcopy` wird `assets/videos/` atomar nach `%TEMP%\fexobooth_user_assets` gemoved + alle `*.png/.jpg/.jpeg` aus `assets/` Root gesichert. Nach dem xcopy werden die User-Files atomar zurück, was die Defaults aus dem ZIP überschreibt.

### Neue geschützte Pfade beim OTA
- `config.json`
- `BILDER/`
- `logs/`
- `.booking_cache/`
- **`assets/videos/`** (NEU — User-Videos)
- **`assets/*.png/.jpg/.jpeg`** (NEU — User-Bilder im `assets/`-Root, z.B. Auslöse-Bild)

---

## [2.2.8] - 2026-04-29 - Template & Settings vom USB neu laden

### Hinzugefügt
- **Service-Menü (PIN 6588): „Template & Settings vom USB neu laden"** — erzwingt Reload der `settings.json` und des Template-ZIPs vom USB-Stick, auch wenn die `booking_id` gleich bleibt. Use Case: Kunde tauscht mitten in der Veranstaltung das Template, ändert eine Einstellung. Vorher wurde das ignoriert (BookingManager überspringt Reload bei gleicher booking_id).
- **Kunden-Menü (PIN 2015): „Template neu einlesen"** — gleiche Funktion, vereinfacht für Vor-Ort-Helfer ohne Service-PIN.

### Hintergrund
[BookingManager.load_from_usb()](src/storage/booking.py) hat in Z. 317 eine Optimierung:
```python
if not force and new_booking_id == self.booking_id and self._settings:
    return True  # gleiche Buchung, überspringe
```
Diese Optimierung war zwar gewollt (kein unnötiges Reload bei jedem Stick-Plug), aber für Inline-Anpassungen im laufenden Event musste der User vorher den Stick mit anderer booking_id präparieren oder das Tablet neu starten. Beide Buttons rufen jetzt `force=True` auf und triggern danach `_restore_cached_template()` + Screen-Refresh.

---

## [2.2.7] - 2026-04-29 - KRITISCH: OTA-Update Race-Condition gefixt

### Behoben
- **Tablets crashten beim Boot nach OTA-Update** mit `FileNotFoundError: 'C:\FexoBooth\_internal\setuptools\_vendor\jaraco\text\Lorem ipsum.txt'`. Race-Condition zwischen App-Beendigung und BAT-Update-Script:
  1. `app.quit()` beendet zwar den Mainloop, aber Hintergrund-Threads (Camera, Galerie-Server) hielten den Prozess am Leben
  2. BAT wartete 30 s, fuhr dann „warnend" fort obwohl App noch lief
  3. `rmdir /s /q "_internal"` schlug **partiell** fehl (gelockte DLLs), `xcopy` mit `>nul 2>&1` unterdrückte alle Fehler
  4. Mixed state: manche Files weg, andere nicht ersetzt → App startet nicht mehr

### Drei-fach-Fix
1. **`os._exit(0)` statt `app.quit()`** ([src/ui/dialogs/update_progress.py](src/ui/dialogs/update_progress.py)) — terminiert den Prozess sofort, ohne auf Threads zu warten. Logging wird vorher geflushed.
2. **BAT-Script atomic mit Rollback** ([src/updater.py](src/updater.py)) — `_internal` wird zuerst nach `_internal_OLD` umbenannt (atomic, scheitert wenn gelockt), dann neu kopiert. Bei xcopy-Fehler: Rollback auf alten Stand. Tablet bleibt **immer funktional**, auch wenn das Update scheitert.
3. **`setuptools` via `collect_all`** ([fexobooth.spec](fexobooth.spec)) — extra Absicherung damit alle vendored Daten-Files (jaraco.text/Lorem ipsum.txt etc.) zuverlässig im Build landen.

### Plus
- BAT-Wait-Timeout von 30 s auf 15 s reduziert (App sollte mit `os._exit` sofort sterben)
- Nach 15 s zusätzlich `taskkill /F /IM` als Fallback
- xcopy nutzt jetzt `/Q` (quiet) aber meldet Errors per `errorlevel`

### Wichtig
Tablets auf v2.2.6 mit dem kaputten State müssen einmalig manuell via `FexoBooth_Setup_2.1.exe` vom Stick auf v2.2.7 gehoben werden — Inno Setup repariert die fehlenden Dateien.

---

## [2.2.6] - 2026-04-29 - Test-Release: OTA-Update verifizieren

App-Code **identisch zu v2.2.5**. Reiner Versions-Bump um den OTA-Update-Pfad auf bereits-installierten v2.2.5-Tablets zu verifizieren.

Erwartet:
- Tablet auf v2.2.5 → Service-Menü → „Software aktualisieren" findet v2.2.6
- Download läuft durch (kein SSL-Fehler mehr, weil v2.2.5 das certifi-Bundle hat)
- Fullscreen-Progress-Dialog zeigt MB-Fortschritt
- Nach Install: Tablet auf v2.2.6

---

## [2.2.5] - 2026-04-28 - SSL-Fix für OTA-Update (certifi mitgepackt)

### Behoben
- **OTA-Update scheiterte am SSL-Cert-Verify** — Im PyInstaller-Build fand `urllib` kein CA-Bundle, der ZIP-Download von GitHub brach mit `[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate` ab. Im Dev-Modus klappte es weil Python die System-Zertifikate fand, aber im EXE-Build fehlten sie.
- Lösung: `certifi` als explizite Dependency aufgenommen, `cacert.pem` über `collect_all("certifi")` in den Build gepackt, und `urlopen()` in [src/updater.py](src/updater.py) nutzt jetzt einen expliziten `ssl.create_default_context(cafile=certifi.where())`. Beide HTTPS-Calls (API-Check + ZIP-Download) gehen über denselben Context.

### Wichtig
v2.2.4 und älter können dieses Update **nicht via OTA** bekommen — genau dieses SSL-Problem blockiert das ja. Die Tablets müssen **einmalig manuell** auf v2.2.5 gehoben werden (`FexoBooth_Setup_2.1.exe` vom Stick installieren). Ab v2.2.5 funktioniert OTA.

---

## [2.2.4] - 2026-04-28 - Test-Release zur Verifikation des Update-Mechanismus

App-Code ist **identisch zu v2.2.3** — nur Versions-Bump zur Verifikation des OTA-Update-Pfades vom Tablet.

Was getestet werden soll:
- Service-Menü (PIN 6588) → „Software aktualisieren" findet v2.2.4
- Fullscreen-Progress-Dialog mit `-topmost` ist sichtbar
- Download durchläuft, BAT-Script übernimmt, App startet neu
- Im Service-Menü steht nach dem Update v2.2.4

Parallel (außerhalb dieses Release): Capture-Tooling-Verbesserungen für USB-Stick, siehe [FORTSCHRITT.md](FORTSCHRITT.md) — `custom-ocs-capture` räumt jetzt `hiberfil.sys` weg, ANSI-robuste Verifikations-Marker, sauberer Abbruch nach Fehler.

---

## [2.2.3] - 2026-04-28 - Spiegel-Fix für gedruckte/gespeicherte Fotos

### Behoben
- **Texte auf Kleidung waren im Druck und in den gespeicherten Singles seitenverkehrt.** Die LiveView-Spiegelung (gewollt: Spiegel-Effekt für intuitive Bewegung) hat sich auch auf den Capture-Pfad ausgewirkt — Webcam und Canon DSLR speicherten gespiegelte Fotos. Jetzt: LiveView bleibt gespiegelt, aber gespeicherte Fotos und Drucke sind korrekt orientiert (Texte lesbar).

---

## [2.2.2] - 2026-04-23 - Update-UI + Orphan-Cleanup

### Behoben
- **Download-Fortschritt war im Kiosk-Modus unsichtbar** — Der ServiceDialog hatte kein `-topmost`, sobald der Confirm-Dialog zerstört wurde, fiel der Dialog hinter die Kiosk-Haupt-App zurück. Der Download lief weiter, aber der User sah nichts und dachte die App sei abgestürzt.
- Neuer **Fullscreen-Update-Progress-Dialog** mit `-topmost`, deutlich größerer Progress-Bar (28 px statt 12), MB-Zähler (`52.3 / 143.4 MB`) und klarem Phasen-Text ("Lade Update herunter..." → "Installation läuft, App startet neu...").

### Hinzugefügt
- **Orphan-Download-Cleanup beim App-Start** — Wenn ein Update abbricht (Stromausfall, Crash mitten im Download), bleiben ~150 MB in `%TEMP%\fexobooth_update.zip` liegen. Beim nächsten App-Start werden alle Update-Reste älter als 1 Stunde automatisch gelöscht → Tablets können sich nicht mehr zumüllen.
- `src.ui.dialogs.update_progress` und `src.company_network` explizit in `fexobooth.spec` als hidden imports eingetragen.

---

## [2.2.1] - 2026-04-23 - Updater-Diagnose + Repo-Access

### Hinzugefügt
- **Besseres Error-Logging im Updater** — bei Update-Check-Fehlern wird jetzt der volle Stack-Trace ins Log geschrieben (vorher komplett geschluckt → Problem unsichtbar).
- **HTTPError vs URLError unterscheiden** — HTTP 404/403/500 wird nicht mehr fälschlich als "Keine Internetverbindung" verkauft. Stattdessen exakte API-Fehlermeldung.

### Behoben
- **Update-Mechanismus hat seit v2.0.0 nie funktioniert** — das GitHub-Repo `fefotec/fexobooth-v2` war privat und lieferte ohne Auth ein HTTP 404 zurück, was der Code als "kein Internet" interpretierte. Repo ist jetzt public, API-Zugriff ohne Token funktioniert, OTA-Updates triggern.

---

## [2.2.0] - 2026-04-23 - Auto-Update, Deployment-Schutz, Hotspot-Fix

### Hinzugefügt
- **Auto-Update beim App-Start** — Wenn die Box im Firmen-WLAN (fexon-SSIDs) eingeschaltet wird und Internet verfügbar ist, prüft sie automatisch GitHub auf neue Releases und installiert sie still. Beim Kunden passiert nichts, da dort nie Internet besteht.
  - Firmen-SSID-Whitelist in `config.company_wifi_ssids` (default: `fexon WLAN`, `fexon_Buero_WLAN2`, `fexon_Buero_WLAN2_5GHZ`, `fexon Gast-WLAN`, `fexon_outdoor`)
  - Ein/Aus-Schalter via `config.auto_update_enabled` (default: `true`)
  - 15s Verzögerung, Background-Daemon, ohne Internet still geschluckt
- **Deployment Pre-Flight-Check** (`custom-ocs-deploy`) — verhindert das Bricken kleinerer Tablets. Prüft vor dem Pre-Wipe ob die Zieldisk groß genug für das Image ist (5% Toleranz). 32-GB-Tablets werden nicht mehr mit 64-GB-Images zerstört.
- **Hotspot Auto-Dummy-Profil** — Frisch geklonte Tablets starten den Hotspot jetzt zuverlässig. `_ensure_wlan_profile_exists()` legt beim ersten Start ein Dummy-WLAN-Profil an, damit die Tethering-API keinen `NO_PROFILE`-Fehler wirft.
- **Hotspot-Diagnose-Script** (`setup/diagnose_hotspot.ps1`) — zeigt WLAN-Adapter, gespeicherte Profile und Tethering-Status für Troubleshooting.
- **Clonezilla Auto-Fixes + persistentes Logging** — `custom-ocs-capture` und `custom-ocs-deploy` überleben jetzt Retries und loggen nach `/home/partimag/deploy-logs/`.

### Behoben
- **FEXOSAFE-Backup nutzt jetzt Buchungs-ID als Überordner** — Der Auto-Backup-Dialog beim FEXOSAFE-Stick erstellt nun `USB:\{event_id}\Single` und `\Prints` statt pauschal `BILDER/`. Logik identisch zum Service-Menü-Backup (PIN 6588).
- **Start-Button wurde vom Galerie-Banner abgeschnitten** — Button aus `inner_frame` rausgelöst und direkt über `gallery_banner` per `pack(side="bottom")` platziert.
- **Drucker wurde nicht erkannt an anderem USB-Port** — Controller erkennt den SELPHY jetzt unabhängig vom USB-Port.
- **Falsche Kamera trotz korrekter Auswahl in der UI** — Webcam-Index aus Config wurde ignoriert; jetzt korrekt übernommen.

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
