# Fortschritt - Fexobooth V2

Chronologisches Protokoll aller Änderungen.

---

## 2026-03-27

### Bugfix: Template-Persistenz nach Neustart ohne USB-Stick (Regression)
- **Bug:** Nach App-Neustart ohne USB-Stick wurde das Default-Template angezeigt statt dem gecachten Template der letzten Buchung. Mehrere Ursachen:
  1. `cached_usb_template` wurde beim App-Start nie aus dem Cache geladen (erst in `on_show()`)
  2. `_cache_template_from_usb` im BookingManager suchte nur nach Dateien namens `template.zip` — alle anderen ZIP-Namen wurden ignoriert
  3. `_execute_event_change` setzte `_usb_stick_template` VOR `on_show()` → `on_show()` erkannte das Template als "unverändert" und übersprang `_persist_template_to_disk`
  4. Beim Wiedereinstecken des gleichen Sticks wurde das Template nicht in Memory restauriert
- **Fixes:**
  - `_restore_cached_template()` — lädt `cached_template.zip` VOR UI-Erstellung
  - `_cache_template_from_usb()` — sucht jetzt JEDE gültige Template-ZIP (nicht nur `template.zip`)
  - `_persist_template_to_cache()` — zentrale Methode, wird in `_execute_event_change` und `_load_settings_from_usb_immediately` aufgerufen
  - `_reload_template_from_usb()` — stellt Template bei Stick-Wiedereinstecken sofort wieder her
- **Betroffen:** `src/app.py`, `src/storage/booking.py`

### Fix: Installer — Cached Template überlebt keine Neuinstallation mehr
- **Bug:** `[InstallDelete]` löschte nur `{app}\.booking_cache`, aber der tatsächliche Cache liegt im PyInstaller-Build unter `{app}\_internal\.booking_cache\` — alte Templates überlebten Neuinstallationen.
- **Fix:** `_internal\.booking_cache` zu `[InstallDelete]` und `[UninstallDelete]` hinzugefügt. `.booking_cache` aus `[Dirs]` entfernt (wird erst im Produktionsbetrieb vom Code erstellt).
- **Betroffen:** `installer.iss`

---

## 2026-03-26

### Bugfix: Installer löscht jetzt Statistiken und Druckerzähler bei Neuinstallation
- **Bug:** Bei Neuinstallation via .exe blieben alte `fexobooth_statistics.json` und `printer_lifetime.json` bestehen → Events und Druckerzähler nicht bei 0
- **Fix:** `[InstallDelete]` Sektion in `installer.iss` ergänzt — löscht Statistik- und Lifetime-Dateien sowohl im App-Root als auch in `_internal/` vor der Installation. Auch `[UninstallDelete]` um diese Dateien erweitert
- **Betroffen:** `installer.iss`

### Bugfix: PIN-Eingabe für Drucker-Zähler-Reset funktioniert jetzt
- **Bug:** Der PIN-Dialog zum Zurücksetzen des Druckerzählers im Admin-Panel hatte keinen Numpad → auf dem Tablet ohne physische Tastatur war keine Eingabe möglich
- **Fix:** Virtuellen Numpad (0-9, ⌫, ✓) zum Reset-Dialog hinzugefügt, identisch zum Haupt-PIN-Dialog. Auto-Submit bei 4 Zeichen, Tastatur-Support über KeyRelease
- **Betroffen:** `src/ui/screens/admin.py` (`_reset_printer_lifetime`)

### Feature: Testdruck-Button im Admin-Panel
- **Neu:** Im Druck-Tab gibt es jetzt einen "Testdruck starten" Button
- **Funktion:** Lädt das aktuelle Template, erzeugt farbige Platzhalter-Bilder mit "TEST 1/2/3..." Text, rendert das Template und druckt es über GDI — ohne dass vorher Fotos gemacht werden müssen
- **Fallback:** Wenn kein Template konfiguriert ist, wird das Default-Template verwendet
- **Betroffen:** `src/ui/screens/admin.py` (`_create_print_tab`, `_execute_test_print`)

### Fix: NOCHMAL-Button vom Final-Screen entfernt
- **Bug:** Auf dem Druck-Screen konnte man "NOCHMAL" drücken und kam zurück zum Start — unerwünscht
- **Fix:** Button und `_on_redo()` Methode komplett entfernt. User kann nur noch drucken oder warten bis Auto-Return
- **Betroffen:** `src/ui/screens/final.py`

### Feature: Strom-Symbol blinkt wenn kein Netzteil angeschlossen
- **Vorher:** Bei Akkubetrieb wurde nur ein oranges ⚡-Symbol angezeigt — leicht zu übersehen
- **Nachher:** Ohne Strom blinkt ⚡ rot/gelb abwechselnd (1,5s). Mit Strom einfach grüner Blitz
- **Betroffen:** `src/app.py` (`_check_power_status`)

### Feature: Echte Kamera-Gerätenamen + Logitech-Priorisierung
- **Vorher:** Kamera-Dropdown zeigte nur "Webcam 0", "Webcam 1" etc. — kein Unterschied zwischen Logitech und interner Kamera erkennbar
- **Nachher:** Echte Gerätenamen via WMI/PowerShell (z.B. "Logitech C920", "Integrated Webcam") mit Auflösung
- **Auto-Auswahl:** Beim App-Start wird automatisch die beste Kamera gewählt: Logitech > externe USB-Kamera > interne Kamera. Nur wenn camera_type "webcam" ist (nicht bei DSLR)
- **Betroffen:** `src/camera/webcam.py` (`_get_device_names`, `list_cameras`, `find_best_camera`), `src/ui/screens/admin.py` (`_get_available_cameras`), `src/app.py` (Startup)

### Fix: Druck-Zoom jetzt zentriert statt oben-links
- **Bug:** Beim Erhöhen des Zoom-Werts dehnte sich das Druckbild nur nach rechts und unten aus → manuelles Nachkorrigieren mit Offset X/Y nötig
- **Fix:** Zoom-Offset wird jetzt automatisch so berechnet, dass sich das Bild gleichmäßig nach allen Seiten ausdehnt (zentrierter Zoom). Der manuelle Offset wirkt zusätzlich zur Zentrierung
- **Betroffen:** `src/ui/screens/final.py` (`_print_image`), `src/ui/dialogs/system_test.py` (`_print_via_gdi`), `src/ui/screens/admin.py` (Testdruck)

---

## 2026-03-18

### USB-Sync Dialog: Kommt jetzt zuverlässig bei Stick-Wiedereinstecken
- **Bug:** Gleichen USB-Stick abziehen → Fotos machen → wieder einstecken → kein Sync-Dialog obwohl Bilder fehlen
- **Ursache:** `_offer_sync_dialog()` zählte fehlende Bilder in Background-Thread ohne try/except. Bei jeder Exception (USB noch nicht fertig gemounted, IO-Fehler) starb der Thread leise — kein Dialog, kein Log, kein Retry
- **Fix 1:** try/except im Background-Thread mit Logging bei Fehler
- **Fix 2:** Fallback auf `pending_count` — wenn `count_missing()` 0 oder Exception zurückgibt aber Pending-Files existieren, wird der Dialog trotzdem angezeigt (`max(missing, pending_count)`)
- **Fix 3:** Logging bei USB-Transition (da→weg, weg→da) mit new_booking und pending-Status für Debugging
- **Betroffen:** `src/app.py` (`_check_usb_status`, `_offer_sync_dialog`)

---

## 2026-03-17

### prepare_image.bat: Tablet für Clonezilla-Image vorbereiten
- **Neues Script:** `deployment/01_referenz-tablet/prepare_image.bat` — Alles-in-einem Script für Image-Vorbereitung
- **Teil 1 — Dienste deaktivieren (25+):** Windows Update (komplett), Windows Search, SysMain/Superfetch, Windows Defender, Telemetrie (DiagTrack, dmwappushservice), Error Reporting, Xbox-Dienste, Maps, Bluetooth, Biometrie, Remote Registry, Fax, Windows Insider, Connected User Experiences
- **Teil 2 — Registry-Optimierungen:** Telemetrie aus, Cortana aus, visuelle Effekte auf Performance, Transparenz aus, Benachrichtigungen aus, Tips/Tricks/vorgeschlagene Apps aus, Hintergrund-Apps aus, OneDrive aus, Sperrbildschirm-Werbung aus, automatische Wartung aus, Storage Sense aus, Energiesparmodus (nie Standby/Bildschirm-Aus), Ruhezustand deaktiviert (spart ~3GB), Schnellstart aus, Defender per Policy aus, geplante Tasks (Defrag, Diagnose, CEIP) aus
- **Teil 3 — FexoBooth bereinigen:** BILDER/Single und Prints geleert, logs/ geleert, .booking_cache/ geleert, statistics.json und printer_lifetime.json gelöscht, gallery_cache/ gelöscht
- **Teil 4 — Windows Temp bereinigen:** User-Temp, Windows-Temp, Prefetch, Windows Update Cache, Thumbnail/Icon-Cache, Papierkorb, Delivery Optimization Cache, Event-Logs, automatische Datenträgerbereinigung (cleanmgr)
- **Installer:** Script wird über `installer.iss` nach `{app}\deployment\` installiert + Startmenü-Eintrag "Image vorbereiten"
- **Auch mitinstalliert:** `post_install_check.bat` zur Verifizierung vor dem Klonen

---

## 2026-03-13

### Start-Screen: Template-Karten-Text verbessert
- **Bug:** Template-Karte zeigte rohen Dateinamen (z.B. Buchungsnummer "134830_...") statt freundlichen Namen
- **Fix:** Aktive Template-Karte zeigt immer "Wunsch-Template"
- **Verbesserung:** Bei nur einer Karte (nichts zu wählen): Header wechselt von "Wähle dein Layout!" zu "Dein Druckformat" / "Tippe zum Starten"
- **Betroffen:** `src/ui/screens/start.py`

### USB-Template vs. User-Template Trennung
- USB-Stick Template wird automatisch geladen, aber User-Auswahl über PIN 2015 wird respektiert
- `_usb_stick_template` speichert Original vom Stick, `_user_template_override` Flag bei expliziter Wahl
- USB-Template bleibt als Extra-Karte wählbar wenn User anderes Template gewählt hat

### Capture-Hintergrund: Schwarz → Weiß
- Default-Hintergrund im TemplateRenderer von `#000000` auf `#FFFFFF` geändert
- Templates ohne Overlay-Frame rendern Fotos jetzt vor weißem Hintergrund

### LiveView Template-Overlay Absicherung
- Try/Except um Template-Overlay im LiveView gegen Freeze bei fehlenden Attributen

---

## 2026-03-12

### Template-Loader: preview.png nicht mehr als Overlay verwenden
- **Bug:** Default-Template.zip enthielt nur `preview.png` (Vorschaubild mit Nummern 1-4), kein `template.png`
- **Ursache:** Loader wählte größtes PNG als Overlay → `preview.png` wurde über die Fotos gelegt und verdeckte sie
- **Fix:** PNG-Auswahl-Logik komplett überarbeitet:
  1. `template.png` wird bevorzugt (exakter Name)
  2. Andere PNGs (nicht preview) als Fallback
  3. `preview.png` wird NIE als Overlay verwendet wenn XML-Boxen vorhanden sind
  4. Templates ohne Overlay-Frame rendern korrekt (nur Fotos in Boxen)
- **Betroffen:** `src/templates/loader.py`, `src/ui/screens/start.py`, `src/ui/screens/admin.py`

### Start-Screen Refresh nach Template-Wechsel im Kunden-Menü
- **Bug:** Template über PIN 2015 gewechselt → Startscreen zeigte noch altes Template-Bild
- **Ursache:** `on_show()` wurde nur bei Admin-Settings aufgerufen (wenn `dialog.result` gesetzt), nicht nach Kunden-Menü
- **Fix:** Start-Screen wird IMMER nach AdminDialog-Schließung aktualisiert (auch nach PIN 2015)
- **Betroffen:** `src/app.py` (Admin-Dialog Nachbehandlung)

### Galerie: Foto-Sharing verbessert
- **Bug:** Web Share API `files`-Parameter wird auf HTTP stumm ignoriert (braucht HTTPS)
- **Fix:** Erkennung ob File-Sharing wirklich funktioniert (`canShare` mit Test-File)
- Bei HTTP: Hinweis "Erst Bild speichern, dann aus Galerie teilen" + WhatsApp/Facebook nur-Text-Fallback
- Bei HTTPS/nativem Support: Vollständiges File-Sharing mit Bild
- **Betroffen:** `src/gallery/server.py`

### Template-Cache und Overlay-Handling
- Template-Cache speichert jetzt auch Templates ohne Overlay (nur Boxen)
- `cached_usb_template` funktioniert korrekt mit `overlay=None`
- Start-Screen Preview: Lädt `preview.png` aus ZIP für Karten-Vorschau (getrennt vom Overlay)

---

## 2026-03-11

### Kunden-PIN Menü (PIN 2015)
- **Neues Feature:** Kunden können über PIN "2015" ein Service-Menü öffnen (ohne Admin-Zugang)
- **4 Optionen:**
  1. **Template wählen** — Zeigt Default-Template, konfigurierte Templates und USB-Template zur Auswahl
  2. **Live-View Overlay ein/aus** — Toggle für `liveview_template_overlay`, speichert sofort in Config
  3. **Druckstau beheben** — Stoppt/Startet Windows Print Spooler (behebt Druckerwarteschlange)
  4. **Windows Neustart** — Mit Bestätigungs-Dialog und Wartehinweis
- **Entfernt:** 5x Icon-Tap für Neustart (durch Kunden-PIN ersetzt)

### Filter-Screen optimiert für Lenovo Miix 310
- **Filter-Labels entfernt** auf kleinen Screens (mehr Platz für Vorschau-Thumbnails)
- **Subtitle-Text entfernt** auf kleinen Screens ("Tippe auf einen Filter...")
- **Vorschau-Titel entfernt** auf kleinen Screens ("📸 Vorschau")
- **Spalten-Gewichtung angepasst**: Filter-Grid bekommt weniger Platz (1:3 statt 2:3)
- **Preview-Auflösung erhöht**: max_preview_size jetzt 500 für alle Screens

### Template-Auswahl mit Vorschau-Bildern
- **Kunden-Menü Template-Auswahl** zeigt jetzt Vorschau-Bilder aus den ZIP-Dateien
- **Template-Ordner:** `assets/templates/` — einfach weitere ZIP-Dateien ablegen, werden automatisch erkannt
- **Build:** Ordner wird über `("assets", "assets")` automatisch in die EXE eingebaut
- **Preview:** Extrahiert `template.png` (oder erstes PNG) als Thumbnail aus jeder ZIP

### Admin-Dialog: Kiosk-Modus ohne Fensterwechsel
- **Problem:** Beim Öffnen der Einstellungen wechselte die App kurz in den Fenstermodus → Taskleiste blitzte auf, Fenster sprang
- **Lösung:** Im Kiosk-Modus bleibt alles fullscreen. PIN-Dialog, Kunden-Menü UND Admin-Einstellungen werden als Overlay innerhalb des Vollbildschirms angezeigt
- **Neuer Parameter:** `AdminDialog(parent, config, kiosk_mode=True)` — steuert ob Einstellungen als Fenster oder Fullscreen-Overlay dargestellt werden
- **Minimieren-Button:** Im Kiosk-Modus gibt es einen "Minimieren"-Button in den Admin-Einstellungen (zeigt Taskleiste, minimiert Dialog)
- **Taskleiste:** Wird beim Minimieren eingeblendet, beim Wiederherstellen automatisch versteckt

### USB-Status-Indikator: Feste Breite
- **Fix:** USB-Badge änderte Größe je nach Text ("USB OK" vs "⚠️ USB FEHLT! [13]") → Blitz-Icon sprang
- **Lösung:** Label in festem CTkFrame-Container (160x28, `pack_propagate(False)`)

---

## 2026-03-09

### Drucker-Steuerung: Software-Reset + Fehlermeldungen ersetzen
- **Neues Feature:** Drucker-Fehler werden jetzt mit eigenem Fullscreen-Overlay angezeigt statt Windows/Canon-Dialoge in den Vordergrund zu bringen
- **Canon-Dialog-Unterdrückung:** Canon SELPHY Fehlerdialoge werden automatisch geschlossen, eigene Meldungen übernehmen
- **Zwei Modi:**
  - **Papierstau:** Automatischer 3-stufiger Reset (Purge → Spooler Restart → USB Device Restart) mit Lade-Animation. Blockiert Bedienung bis behoben
  - **Verbrauchsmaterial (Papier/Tinte leer):** Blockierendes Overlay "Bitte Papier/Tinte nachfüllen". Verschwindet NUR wenn Drucker wieder OK meldet (Polling alle 3s)
- **Dev-Mode Button:** "DRUCKER RESET" Button in der Top-Bar zum Testen des Reset-Ablaufs
- **Neue Dateien:**
  - `src/printer/__init__.py` + `src/printer/controller.py` (PrinterController: Reset-Eskalation, Dialog-Unterdrückung, Status-Abfrage)
  - `src/ui/dialogs/printer_error.py` (PrinterErrorOverlay: Blockierendes Vollbild-Overlay)
- **Refactoring:** `_check_print_jobs()`, `_detect_canon_error_window()`, `_bring_printer_dialog_to_front()` aus `app.py` in `PrinterController` ausgelagert
- **Bugfix (Real-Hardware-Test):**
  - Canon-Dialog-Text per `WM_GETTEXT` statt `GetWindowTextW` lesen (Canon-Controls antworten nicht auf GetWindowTextW)
  - Alle Child-Controls enumerieren, längsten Text als Fehlermeldung verwenden
  - Falls Text nicht lesbar: sicher als "KEIN PAPIER / KASSETTE!" (consumable) behandeln
  - Canon-Dialog NICHT schließen wenn Overlay aktiv (Dialog = einziger Fehlerindikator beim SELPHY!)
  - Reset immer alle 3 Stufen durchlaufen (SELPHY setzt keine Spooler-Status-Flags)
  - Overlay: periodisches `lift()` + `focus_force()` gegen Canon-Dialog Focus-Stealing
  - Umfangreiches Debug-Logging für alle Drucker-Operationen

### Export-Dialog blockierte UI (Boot-Drives + grab_set)
- **Export-Dialog blockierte UI**: D:\ (SD-Karten-Slot im Miix 310) wurde als "unbekannter USB-Stick" erkannt → Export-Dialog mit `grab_set()` blockierte gesamte Interaktion. Fixes: (1) Boot-Drives werden beim Start erfasst und für Export ignoriert, (2) 15s Grace Period nach Boot, (3) Export-Dialog ohne `grab_set()` (non-blocking), (4) Abgezogene Boot-Drives werden aus Ignorier-Liste entfernt.

### ZIP-Validierung, Default-Template, Freeze-Fix, Encoding (2026-03-10 continued)
- **ZIP-Validierung**: Template-Loader und `find_usb_template()` erkennen jetzt Anwendungs-ZIPs (mit .exe, .dll, `_internal/`). Solche ZIPs werden abgelehnt. Das verhindert, dass fexobooth.zip (das Installationspaket) als Template interpretiert wird.
- **Default-Template.zip**: `create_default_template()` lädt jetzt `assets/Default-Template.zip` statt programmatisch ein 2x2-Grid zu generieren. ZIP ist bereits über `("assets", "assets")` im Build enthalten. Ergebnis wird gecacht.
- **Freeze-Ursache gefunden**: 41-Sekunden-Freeze beim Rendern des finalen Bildes — Ursache: USB-Stick enthielt `fexobooth.zip` (Anwendungspaket statt Template), Loader nahm Logo-PNG (6889x6889) als Overlay → Compositing dauerte 41s auf Miix 310. Fix: ZIP-Validierung.
- **PowerShell Encoding**: `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` zu allen PowerShell-Subprocess-Aufrufen hinzugefügt (behebt `durchgef�hrt` → `durchgeführt`)

### Drucker-Steuerung: Kritische Bugfixes (2026-03-10)
- **Fix: `win32timezone` fehlte im PyInstaller-Build** — `EnumJobs` Level 2 braucht `win32timezone` für DateTime-Felder. JEDER Job-Queue-Check schlug im Build fehl (`No module named 'win32timezone'`). Drucker-Fehler bei aktiven Druckjobs wurden NIE erkannt!
  - Fix 1: `win32timezone` als `hiddenimport` in `fexobooth.spec`
  - Fix 2: `EnumJobs` mit Level 1 statt Level 2 (hat kein DateTime, braucht kein `win32timezone`)
- **Fix: Canon-Dialog-Erkennung findet jetzt auch versteckte Fenster** — `_detect_canon_error_window()` prüfte nur `IsWindowVisible()`. Fenster die wir per `SW_HIDE` versteckt hatten, wurden danach nicht mehr erkannt. Jetzt werden ALLE Fenster (sichtbar + versteckt) geprüft
- **Fix: `close_canon_dialogs()` findet jetzt versteckte Fenster** — Cleanup nach Overlay-Schließen fand versteckte Canon-Dialoge nicht
- **Cleanup: Debug-Spam für Child-Controls entfernt** — Jeder Child-Control-Scan loggte Klasse + Textlänge → massiver Log-Spam

### Collage: Nochmal + Weiter Buttons nach jedem Foto
- **Neues Verhalten:** Bei Collagen (>1 Foto) wird nach jedem Foto eine schwarze Button-Leiste am unteren Bildschirmrand eingeblendet
- **Buttons:** "↻ NOCHMAL" (rot, wiederholt das letzte Foto) + "WEITER →" (grün, geht zum nächsten Foto)
- **Timeout:** Leiste bleibt 60 Sekunden sichtbar, danach automatisch weiter zum nächsten Foto
- **Design:** Schwarze Leiste über volle Breite löst Transparenz-Problem. `tk.Frame` statt `CTkFrame` (CTk place/lift/z-order unzuverlässig)
- **Betrifft:** `session.py` (_setup_ui, _show_redo_button, _on_continue_photo)

### Template-Overlay: Default ON + kein Vollbild-Flicker beim Start
- **Default geändert:** `liveview_template_overlay` ist jetzt `True` (statt False)
- **Fix:** Template-Cache wird SYNCHRON aufgebaut bevor LiveView startet (kein kurzer Vollbild-Kamera-Blitz mehr)
- **Lade-Anzeige:** Während Webcam-Capture wird 📸 Emoji statt leerer Bildschirm gezeigt

### Fix: Webcam Buffer-Flush optimiert (grab statt read)
- **Problem:** `get_high_res_frame()` brauchte ~3-5s für Auflösungsumschaltung
- **Optimierung:** `cap.grab()` statt `cap.read()` für Buffer-Flush (grab dekodiert nicht), 2 statt 5/3 Flush-Frames
- **Betrifft:** `webcam.py` (get_high_res_frame), `session.py` (_capture_photo)

### Template-Overlay im LiveView (optional, Admin-Menü)
- **Neues Feature:** LiveView kann jetzt das Template als Overlay anzeigen, sodass der Kamera-Feed direkt an der Stelle positioniert wird, wo das Foto im Template landen wird
- **Konfigurierbar:** Neue Checkbox "Template im LiveView anzeigen" im Admin-Menü (Kamera-Tab). Standard: deaktiviert (Performance)
- **Funktionsweise:**
  - Template-Overlay wird einmalig beim Session-Start auf Display-Größe skaliert und gecacht
  - Bereits aufgenommene Fotos werden in ihren jeweiligen Boxen angezeigt
  - LiveView-Feed wird in die aktuelle Foto-Box eingesetzt (Cover-Modus)
  - Template-Rahmen wird als RGBA-Overlay darüber gelegt
  - Countdown wird über das Gesamtbild gerendert
- **Performance:** BILINEAR-Resampling statt LANCZOS für schnelles Scaling, Cache wird bei on_hide freigegeben
- **Hintergrund:** Feature war früher Standard (vor 2026-02-09) und wurde für Performance entfernt. Jetzt als Option zurück

---

## 2026-03-03

### KRITISCH: Canon DSLR Freeze bei Host-Download behoben (App friert ein)
- **Problem:** Canon EOS 2000D ohne SD-Karte → App friert ein. Sowohl beim Session-Start als auch beim Capture-Screen. Kamera löst nicht aus
- **Ursache:** `EdsSetObjectEventHandler` (EDSDK DLL) deadlockt - der DLL-Call kehrt nie zurück, registriert aber den Handler trotzdem (Events feuern nach ~150ms). EDSDK nutzt intern COM (STA)
- **Finaler Fix:** `set_object_event_handler()` in `edsdk.py`:
  1. DLL-Call in daemon Background-Thread (kehrt evtl. nie zurück - bekanntes Verhalten)
  2. Hauptthread pumpt 500ms Windows-Messages (reicht für Handler-Registrierung)
  3. Danach: Handler gilt als registriert, egal ob DLL returned (Events funktionieren)
  4. Daemon-Thread bleibt im Hintergrund, wird bei App-Exit automatisch beendet
- **Bonus-Fixes:**
  - `CFUNCTYPE` → `WINFUNCTYPE` für EDSDK Callback (korrekte Calling-Convention `__stdcall`)
  - Handle-Leak in `_check_camera_status()` gefixt: Kamera-Refs von `list_cameras()` werden nach dem Check freigegeben

### Fix: Canon EOS 2000D sendet falsches Event (0x208 statt 0x108)
- **Problem:** DSLR-Fotos kamen nie an (10s Timeout), Flash-Bild blieb ~10s sichtbar, bei Collagen fielen Fotos 3-4 aus (kein Auslösegeräusch mehr)
- **Ursache:** Canon EOS 2000D sendet bei Host-Download Event `0x00000208` (DirItemRequestTransfer_Alt) statt Standard `0x00000108`. Der Event-Handler erkannte dieses Event nicht → Bilder wurden nie heruntergeladen → 10s Timeout → LiveView-Fallback. Nach mehreren ignorierten Transfer-Events sendete die Kamera `0x00000301` (Shutdown) → alle weiteren EDSDK-Calls schlugen mit Fehler 0x61 fehl
- **Fix 1: Event-Handler erweitert** - `_on_object_event()` in `canon.py` erkennt jetzt `0x208` UND `0x108` als Download-Trigger. Zusätzlich wird `0x100` (DirItemCreated) als Fallback für andere Kamera-Modelle behandelt
- **Fix 2: Flash-Timing entkoppelt** - Flash wird jetzt am Anfang von `_capture_photo()` ausgeschaltet (mit `update_idletasks()` GUI-Redraw), BEVOR der blockierende Capture startet. Vorher blieb der Flash während des gesamten Capture-Timeouts sichtbar
- **Fix 3: Kamera-Recovery bei Shutdown** - Wenn Kamera `0x301` (Shutdown) sendet, wird dies erkannt und beim nächsten `capture_photo()` automatisch die Session geschlossen und neu geöffnet (Event-Handler wird neu registriert)

### Performance: Session-Start massiv beschleunigt (7s → <1s)
- **Problem:** Nach jedem Video dauerte es 7 Sekunden bis der LiveView erschien (5.5s Kamera-Init + 1.5s LiveView-Start)
- **Ursache 1:** `reset_session()` gab die Kamera komplett frei → bei jeder neuen Session musste die gesamte EDSDK-Initialisierung neu durchlaufen werden (Session öffnen, SaveTo setzen, Event-Handler registrieren)
- **Ursache 2:** Event-Handler Timeout war 5s (jetzt 500ms, da Handler nach ~150ms funktioniert)
- **Fix 1: Kamera-Persistenz** - `reset_session()` gibt Kamera nicht mehr frei, nur LiveView wird gestoppt. `session.on_show()` prüft `is_initialized` und überspringt Neuinitialisierung
- **Fix 2: Kamera-Vorinitialisierung** - Wenn `play_video("video_start")` abgespielt wird, startet die Kamera-Init bereits nach 200ms parallel (VLC spielt in eigenem Thread weiter). Wenn das Video endet, ist die Kamera bereits bereit
- **Ergebnis:** Erste Session: Init während Video (~1s, unsichtbar). Folge-Sessions: 0s Init (Kamera bleibt aktiv)

---

## 2026-02-26

### Fix: Taskleiste verschwindet permanent nach App-Crash
- **Problem:** Wenn die App abstürzte oder per Force-Kill beendet wurde, blieb die Windows-Taskleiste permanent versteckt (`ShowWindow(SW_HIDE)` ist persistent). User musste Registry oder Explorer-Neustart machen um Taskleiste zurückzubekommen
- **Lösung:**
  1. **`atexit`-Handler** in `app.py`: `atexit.register(self._restore_taskbar_safe)` - fängt saubere Python-Exits ab
  2. **Recovery beim App-Start** in `main.py`: `_recover_taskbar()` wird VOR dem App-Start aufgerufen - stellt Taskleiste wieder her falls vorheriger Lauf gecrasht ist
  3. **Global Exception Handler** in `main.py`: Stellt Taskleiste auch bei unbehandelten Exceptions wieder her
- **Ergebnis:** Taskleiste wird jetzt in 3 Schichten geschützt - selbst nach hartem Crash wird sie beim nächsten App-Start wiederhergestellt

### Canon DSLR: Host-Download wiederhergestellt (Kamera funktioniert ohne SD-Karte)
- **Kontext:** Host-Download wurde vorher entfernt weil die App hing. Das Hängen war aber der EDSDK-Deadlock (jetzt gefixt), nicht der Host-Download selbst
- **Lösung:** Host-Download wiederhergestellt mit verbessertem Logging:
  - MIT SD-Karte: Directory-Polling (wie bisher, zuverlässigster Modus)
  - OHNE SD-Karte: Host-Download via Event-Handler (Bild wird via USB zum Tablet übertragen)
  - Kamera löst in BEIDEN Modi richtig aus (Autofokus, Spiegel, Shutter)
- **System-Test nutzt jetzt explizit LiveView** (braucht keine SD-Karte, ist schneller)
- **LiveView-Fallback** hat jetzt Retry-Logik (bis 10 Versuche mit 300ms Pause)
- **Kamera-Status** zeigt nur Kamera-Verbindung an, nicht SD-Karten-Status

### KRITISCH: EDSDK Deadlock behoben (System-Test hing, Tablet musste hart ausgeschaltet werden)
- **Problem:** `_check_camera_status()` rief `list_cameras()` (= EDSDK DLL-Aufrufe) vom UI-Thread auf, während gleichzeitig der System-Test-Thread EDSDK für `capture_photo()` nutzte. EDSDK ist NICHT thread-safe (Windows COM STA) → **Deadlock** → App komplett eingefroren, Ctrl+Shift+Q funktionierte nicht wegen `grab_set()` im Dialog
- **Fix 1:** `_check_camera_status()` prüft jetzt `is_initialized` ZUERST. Wenn Kamera aktiv ist (Session offen), werden KEINE EDSDK-Aufrufe vom UI-Thread gemacht
- **Fix 2:** System-Test hat jetzt **globalen Timeout** (90s) und **Abbrechen-Button**. Bei Timeout wird Kamera freigegeben und Fehler angezeigt
- **Fix 3:** `Ctrl+Shift+Q` funktioniert jetzt in ALLEN Dialogen mit `grab_set()` (System-Test, Event-Wechsel, Backup, Admin, Service, USB-Sync, Export). Jeder Dialog hat eigenen Keyboard-Binding

### Kamera-Status-Anzeige in der Top-Bar
- **Neu:** Blinkende Kamera-Warnung in der Top-Bar (📷 KEINE KAMERA!) wenn keine Kamera erreichbar
- Prüft Canon DSLR (via EDSDK `get_camera_list()`) und Webcam (via OpenCV `VideoCapture`)
- **WICHTIG:** Überspringt EDSDK-Check wenn Kamera bereits initialisiert (verhindert Deadlock!)
- Blinkend Rot/Gelb wie USB- und Drucker-Warnung, verschwindet wenn Kamera OK
- Prüfintervall: 2s bei Problem, 15s wenn OK

### Canon DSLR: Funktioniert jetzt auch ohne SD-Karte
- **Problem:** Auf einer echten Fotobox schlug der System-Test fehl weil die Canon EOS 2000D keine SD-Karte hatte. `SaveTo=Camera` setzte die Kamera auf SD-Karten-Speicherung, aber `wait_for_new_image()` fand keinen DCIM-Ordner → Foto-Capture komplett fehlgeschlagen
- **Lösung:** Automatische Erkennung ob SD-Karte vorhanden ist:
  1. Bei `initialize()`: SaveTo Camera setzen, dann DCIM-Ordner prüfen
  2. Wenn DCIM fehlt: Automatisch auf `SaveTo Host` umschalten + Event-Handler registrieren
  3. `capture_photo()` unterstützt jetzt zwei Modi:
     - **Directory-Polling** (mit SD): Wie bisher, pollt DCIM-Ordner
     - **Host-Download** (ohne SD): Bild kommt direkt via EDSDK Event-Handler über die Photo-Queue

### Kiosk-Modus: Permanentes topmost entfernt (kritischer Fix)
- **Problem:** Permanentes `-topmost=True` blockierte ALLE Fenster - auch eigene App-Dialoge (USB-Sync, Export, Event-Wechsel). App wurde unbedienbar wenn ein Dialog hinter dem Hauptfenster landete. Selbst Task-Manager konnte nicht in den Vordergrund
- **Lösung:** Drei-Säulen-Kiosk-Modus statt aggressivem topmost:
  1. **Taskleiste verstecken:** `_hide_taskbar()`/`_show_taskbar()` via Windows API bleibt (wird alle 5s re-assertet)
  2. **Windows-Benachrichtigungen unterdrücken:** Neue `_suppress_notifications()` Methode deaktiviert Windows-Toasts via Registry (`NOC_GLOBAL_SETTING_TOASTS_ENABLED`)
  3. **topmost nur kurz:** `-topmost=True` wird nur 500ms beim Fenster-Positionieren gesetzt, dann sofort wieder entfernt
- **Notfall-Shortcut:** `Ctrl+Shift+Q` beendet die App sofort (auch im Kiosk-Modus), stellt Taskleiste und Benachrichtigungen wieder her
- **Entfernt:** topmost Re-Assertion in `_check_fullscreen_restore()` (war Ursache des Problems)
- **Alle Exit-Pfade** stellen jetzt Benachrichtigungen wieder her: `quit()`, `_emergency_quit()`, `_quit_app()` im Admin

---

## 2026-02-25

### Kiosk-Modus: Echte Vollbildsicherung
- **Fix:** Taskleiste blieb nach Admin-Dialog sichtbar - Fullscreen wurde nie korrekt wiederhergestellt
- **Ursache 1:** `show_admin_dialog()` hat nach Dialog-Schluss KEINEN `_enter_fullscreen()` Aufruf - verließ sich auf 10s-Timer der oft versagte
- **Ursache 2:** `_set_appwindow()` machte `withdraw()/deiconify()` Zyklus - in den 10ms konnte die Taskleiste den Fokus grabben
- **Ursache 3:** `-topmost` wurde nach 100ms wieder entfernt - Windows-Meldungen (USB etc.) konnten in den Vordergrund poppen
- **Lösung:** Komplett überarbeiteter Kiosk-Modus:
  1. **Taskleiste verstecken:** Neue `_hide_taskbar()`/`_show_taskbar()` via Windows API (`FindWindowW("Shell_TrayWnd")` + `ShowWindow`)
  2. **Sofortige Wiederherstellung:** `show_admin_dialog()` ruft `_enter_fullscreen()` direkt nach Dialog-Schluss auf (200ms Delay)
  3. **Escape/F11 blockiert:** Im Kiosk-Modus (`start_fullscreen=True`) kann Vollbild NUR über Admin-PIN verlassen werden
  4. **Sicherheitsnetz:** `_check_fullscreen_restore()` prüft alle 5s (statt 10s) und re-assertet Taskleiste
  5. **Kein withdraw/deiconify:** `_set_appwindow()` entfernt aus `_enter_fullscreen()` (verursachte den Bug)
  6. **Taskleiste bei App-Exit:** `quit()` und `_quit_app()` stellen Taskleiste wieder her
- **Bug Fix:** Service-PIN Dialog hat Fullscreen nie wiederhergestellt (`return` vor Restore-Code)
- **Bereinigt:** Redundanter `parent_window.overrideredirect(False)` Code im Admin-Dialog entfernt

### USB-Dialoge: Vordergrund + Auto-Close
- **Fix:** USB-Sync und Export-Dialoge landeten manchmal hinter dem Hauptfenster (unerreichbar, App blockiert)
- **Ursache:** Dialoge nutzten `transient()`, `lift()`, `focus_force()` nicht - bei topmost-Hauptfenster kamen sie nicht nach vorne
- **Lösung 1:** Beide Dialoge erzwingen jetzt Vordergrund: `transient(self.root)` + `lift()` + `focus_force()`
- **Lösung 2:** Auto-Close nach Kopiervorgang - kein OK-Button mehr nötig:
  - Erfolg: Dialog schließt automatisch nach 3 Sekunden
  - Fehler/Abbruch: Dialog schließt automatisch nach 4 Sekunden
- Betrifft: `_show_sync_dialog()` und `_show_export_dialog()` in `app.py`

### Konsolenfenster versteckt
- **Fix:** `start_fexobooth.bat` öffnete ein sichtbares Terminal-Fenster das beim Admin-Dialog zum Vorschein kam
- **Lösung 1:** `_hide_console_window()` in `main.py` - versteckt Konsole via `GetConsoleWindow()` + `ShowWindow(SW_HIDE)` beim App-Start (nur Produktion, nicht im Dev Mode)
- **Lösung 2:** BAT nutzt `pythonw` statt `python`, `pause` entfernt
- **Neue Datei:** `start_fexobooth_debug.bat` - Developer-Variante mit sichtbarer Konsole + `--dev` Flag

### Final-Screen: Template-Vorschau vollständig sichtbar
- **Fix:** Template/Druck-Vorschau wurde unten abgeschnitten (ging über Bildschirmrand)
- **Ursache:** `thumbnail()` nutzte die volle Container-Höhe, aber die Overlay-Buttons (DRUCKEN etc.) überdeckten die unteren 20%
- **Lösung:** Sichtbare Höhe auf 78% begrenzt (`visible_h = int(container_h * 0.78)`) - Template ist jetzt vollständig über den Buttons sichtbar

### Drucker-Lifetime-Zähler
- **Neues Feature:** Zählt die Gesamtanzahl aller Drucke über die Lebensdauer eines Druckers
- **Anzeige:** Neuer Bereich "🖨️ Drucker-Lifetime" im Statistik-Tab des Admin-Menüs
- **Persistenz:** Eigene Datei `printer_lifetime.json` - wird NICHT durch Event-Wechsel oder Statistik-Reset zurückgesetzt
- **Reset:** Nur über Service-PIN (6588) im Admin-Menü möglich (PIN-Abfrage im Dialog)
- **Zählung:** Jeder erfolgreiche Druck (auch Testdrucke) zählt hoch
- **Neue Datei:** `src/storage/printer_lifetime.py` (Singleton, JSON-Speicherung)
- **PyInstaller:** `src.storage.printer_lifetime` als Hidden Import in `fexobooth.spec` ergänzt

---

## 2026-02-12

### Deployment-System (Tablet-Klonen)
- **Neuer Ordner:** `deployment/` mit komplettem Klon-System für 200 Tablets
- **Ansatz:** Clonezilla-basiert (kein Sysprep nötig, kein Windows ADK)
- **Workflow:** Referenz-Tablet einrichten → Image erstellen → auf Ziel-Tablets klonen
- **Enthält:**
  - Schritt-für-Schritt Anleitungen (Deutsch, anfängerfreundlich)
  - `post_install_check.bat` — Prüft ob Referenz-Tablet bereit ist
  - `create_usb.bat` — Lädt Clonezilla + Rufus herunter
  - Clonezilla custom-ocs Scripts (auto-detect eMMC, deutsche Bootmenü-Einträge)
  - `set_computername.bat` — Optionale individuelle Tablet-Benennung
  - Druckbare Checkliste für den Deployment-Prozess
- **Zeitschätzung:** ~2 Arbeitstage für 200 Tablets (4 USB-Sticks parallel)

### OTA-Update System (Software aktualisieren)
- **Neues Feature:** Tablets können sich über GitHub Releases selbst aktualisieren
- **Service-Menü:** Neuer Button "Software aktualisieren" (PIN 6588)
  - Prüft GitHub API auf neuestes Release
  - Vergleicht Versionen automatisch
  - Download mit Fortschrittsanzeige
  - App beendet sich → BAT-Script ersetzt Dateien → Neustart
- **Standalone BAT:** `update_from_github.bat` komplett überarbeitet
  - Lädt jetzt von GitHub Releases statt Source-Archiv
  - Funktioniert auf Produktions-Tablets (kein Python/Git nötig)
  - Ersetzt EXE + `_internal/` + Assets
- **Geschützte Dateien:** config.json, BILDER/, logs/, .booking_cache/ werden NIE überschrieben
- **Build-Anpassung:** `build_installer.bat` erstellt immer ZIP für OTA-Updates
- **Neues Modul:** `src/updater.py` — GitHub Release API, Download, Update-Script-Generierung
- **Workflow:** Build → GitHub Release erstellen → ZIP hochladen → Tablets updaten

---

## 2026-02-11

### Bilder-Export auf unbekannte USB-Sticks
- **Neues Feature:** Wenn ein USB-Stick eingesteckt wird der weder "fexobox" noch "FEXOSAFE" heißt, wird ein Export-Dialog angeboten: "X Bild(er) auf den Stick kopieren?"
- Anwendungsfall: Kunden-Stick kaputt → eigenen USB-Stick einstecken → Bilder retten
- Dialog mit Fortschrittsbalken und Abbrechen-Button (wie Sync-Dialog)
- Bilder werden nach `BILDER/Single/` und `BILDER/Prints/` auf den Stick kopiert
- Dialog erscheint nur einmal pro Stick (Laufwerksbuchstabe wird gemerkt)
- Kein Dialog wenn keine lokalen Bilder vorhanden

### Event-Wechsel: Lösch-Bestätigung
- **Änderung:** Beim Event-Wechsel werden lokale Bilder gelöscht. Jetzt mit 2-Schritt-Bestätigung:
  1. Dialog zeigt "⚠️ X vorhandene Bilder werden gelöscht!" als Warnung
  2. Klick auf "NEUES EVENT STARTEN" → zweite Ansicht "Bilder löschen?" mit rotem "LÖSCHEN & NEUES EVENT" Button
  3. "Zurück"-Button führt zur Hauptansicht zurück
  4. Wenn keine Bilder vorhanden: direkt ohne Zwischenschritt
- USB-Sync bei neuem Stick war bereits korrekt deaktiviert (nur bei gleichem Event)

### System-Test: Komplette Session statt Einzelfoto
- **Änderung:** System-Test fotografiert jetzt **jeden Template-Slot einzeln** (z.B. 4 Fotos bei 4er-Collage) statt ein Foto zu duplizieren. Ergebnis wird automatisch gedruckt → echter Testausdruck mit Kunden-Template
- UI zeigt Live-Fortschritt: "Foto 2 von 4 aufnehmen..." mit anteiligem Fortschrittsbalken
- 2 Sekunden Pause zwischen Fotos (Kamera nachregeln)
- Erfolgsmeldung: "Alles OK! Testdruck mit X Fotos gesendet."

### System-Test "Keine Template-Boxen geladen" behoben
- **Fix:** System-Test schlug immer bei "Template anwenden" fehl, obwohl Template auf USB funktionierte. Ursache: `reset_session()` (Schritt 9) löschte `template_boxes` und `overlay_image`, die in Schritt 6 gerade erst geladen wurden. Lösung: `reset_session()` VOR dem Template-Laden ausführen (jetzt Schritt 4 statt 9)

### USB-Sync: Bestätigungsdialog statt Auto-Kopie
- **Änderung:** Bilder werden nicht mehr automatisch auf USB kopiert wenn der Stick eingesteckt wird. Neuer Flow:
  1. Neues Event (anderer USB-Stick) → Event-Wechsel-Dialog, KEINE Bilder kopieren
  2. Gleicher Stick wieder eingesteckt → Dialog "X Bilder fehlen auf USB. Jetzt kopieren?" mit Kopieren/Abbrechen
  3. Beim Kopieren: Fortschrittsbalken + Abbrechen-Button
  4. Am Ende: Ergebnis-Anzeige (X kopiert / abgebrochen / Fehler) + OK-Button
- USB-Manager: Neue `count_missing()` Methode, `sync_all_missing()` mit `progress_callback` und `cancel_event`

### Service-PIN Freeze behoben
- **Fix:** Service-PIN 6588 hat die App eingefroren. Ursache: ServiceDialog wurde innerhalb des `after`-Callbacks des bereits zerstörten AdminDialogs erstellt. Der neue Dialog landete hinter dem Hauptfenster, `grab_set()` blockierte Interaktionen → Freeze. Lösung: AdminDialog setzt nur ein Flag (`_open_service`), ServiceDialog wird erst nach `wait_window()` in `show_admin_dialog()` geöffnet

### Beenden-Button in Admin-Dialog verschoben
- **Änderung:** "App beenden"-Button war im Hauptfenster (Top-Bar, nur sichtbar nach Fullscreen-Exit). Jetzt in der Button-Leiste des Admin-Dialogs neben "Abbrechen" und "Speichern". Kein Fullscreen-Toggle mehr nötig um die App zu beenden

### Galerie zeigt gelöschte Bilder - behoben
- **Fix:** Web-Galerie zeigte nach "Alle Bilder löschen" im Service-Menü weiterhin alte Bilder. Zwei Ursachen:
  1. **Galerie las von USB statt lokal:** Galerie bevorzugte USB-Pfad (`F:\BILDER\`). Löschen betrifft nur lokale Festplatte, USB ist Backup und bleibt unangetastet. Lösung: Galerie liest jetzt **immer** vom lokalen Pfad
  2. **Browser-Cache:** Handy-Browser cachte Thumbnails und HTML. Lösung: `Cache-Control: no-store` Header auf allen Gallery-Server-Responses

### Event-Wechsel-System, System-Test & FEXOSAFE Backup
- **Automatischer Event-Wechsel-Dialog:** Wenn ein USB-Stick ("fexobox") mit einer neuen Buchung/Template erkannt wird, erscheint ein Fullscreen-Dialog "Neues Event erkannt" mit Annehmen/Ablehnen. Wartet auf StartScreen wenn User in aktiver Session
- **Event-Wechsel Logik:** Bei Annehmen: Neue Buchung + Template laden, alle lokalen Bilder löschen, Caches leeren, neues Statistik-Event starten, automatischen Systemtest durchführen
- **Automatischer System-Test:** Nach Event-Wechsel testet die App die komplette Kette (Kamera init → Testfoto → Template anwenden → Testdruck → Aufräumen). Zeigt Schritt-für-Schritt-Fortschritt und Ergebnis ("Alles OK!" oder Fehlerdetails)
- **FEXOSAFE Backup-Stick:** Neuer USB-Stick-Typ mit Label "FEXOSAFE" für Bilder-Sicherung. Wird automatisch erkannt, zeigt Backup-Dialog mit Bilderzähler und Fortschrittsbalken. Kopiert BILDER/Single/ und BILDER/Prints/ auf den Stick. 30s Cooldown nach Backup
- **Pending-Dialog-Queue:** Dialoge (Event-Wechsel, FEXOSAFE) werden in Queue gespeichert wenn User in aktiver Session ist, und erst beim Rückkehr zum StartScreen angezeigt

### Strom-Status-Anzeige
- **Strom-Indikator in Top-Bar:** Grünes ⚡ bei Netzbetrieb, oranges ⚡ mit Prozentanzeige bei Akkubetrieb. Nutzt `GetSystemPowerStatus` (kernel32 Syscall, < 0.1ms). Prüfung alle 10 Sekunden

### Drucker-Status-Warnung (Canon Selphy)
- **Blinkende Drucker-Warnung:** Drucker-Status-Check in der Top-Bar zeigt jetzt blinkende Rot/Gelb-Warnung (wie USB-Stick), wenn der Drucker nicht bereit ist. Erkennt: Drucker aus/offline, Papier leer, Papierstau, Drucker-Fehler, Drucker nicht gefunden. Bei Problem 1-Sekunden-Blink-Intervall, bei OK nur alle 5s Prüfung. Nutzt nur win32print API (< 1ms pro Call, kein Netzwerk)
- **Canon-Fehlerfenster-Erkennung:** Canon SELPHY zeigt Fehler (Kein Papier, Kassette falsch) über eigene Treiber-Dialogfenster. Neue `_detect_canon_error_window()` Methode erkennt diese via `EnumWindows` API und zeigt den Fehler in der Top-Bar an. Liest Fehlertext aus Static-Child-Controls des Canon-Fensters. `_bring_printer_dialog_to_front()` holt das Canon-Fenster vor die Fullscreen-App

### Belastungstest realistisch (Developer Mode)
- **Realistische Simulation:** Stress-Test simuliert jetzt echtes Nutzerverhalten statt stur den gleichen Pfad. Zufällige Template-Auswahl, zufällige Filter (mit 40% Chance mehrere durchzuprobieren), 25% Redo-Chance auf Final-Screen, 15% Redo pro Collage-Foto im Session-Screen. Zufällige Delays zwischen allen Aktionen (300-4000ms). Logging zeigt Session-Nummer und Redo-Statistik. Ziel: Race Conditions, Memory Leaks und UI-Freezes provozieren

---

## 2026-02-10

### Bugfixes & UI-Verbesserungen (Tablet-Test Feedback Runde 5)
- **Foto-Zähler Fix:** "Foto 5 von 4" beim letzten Foto behoben - `_update_progress` zeigt jetzt maximal `total_photos` an (min-Cap)
- **Flash-Bild zuverlässiger:** `_display_flash()` wird jetzt direkt in `_take_photo()` aufgerufen statt auf den nächsten Loop-Tick (50ms) zu warten. Verhindert intermittierendes Fehlen des Auslösebilds beim 2. Foto
- **Responsive Template-Karten:** Template-Karten auf dem Startscreen passen sich an die Anzahl an: 1 Karte = 360x280 (groß), 2 Karten = 270x230 (mittel), 3+ Karten = 220x190 (klein). Interne Größen (Preview, Titel-Font, Icon) skalieren proportional
- **Print-Vorschau vollständig:** padx im Final-Screen von 40px auf 10px reduziert - Print wird jetzt deutlich größer und vollständiger angezeigt

### Bugfixes & Features (Tablet-Test Feedback Runde 6)
- **Galerie-Deaktivierung Fix:** `_is_gallery_enabled()` prüft nur noch `config["gallery_enabled"]` statt direkt die Booking-Settings. Booking-Settings fließen via `apply_settings_to_config()` in die Config - Admin-Änderungen werden nicht mehr überschrieben
- **Willkommensnachricht:** Persönliche Begrüßung im VLC-Ladescreen mit `shipping_first_name` aus Booking-Meta ("Hallo [Name], vielen Dank für deine Buchung bei fexobox!")
- **`live_gallery` Meta-Feld:** Booking-Settings lesen jetzt `features.live_gallery` statt `features.online_gallery` für Galerie-Aktivierung
- **Bilder löschen komplett:** Service-Menü "Alle Bilder löschen" löscht jetzt auch Bilder im Gallery-Server-Pfad (kann auf USB zeigen). Verhindert dass Bilder im Live-Server sichtbar bleiben

### Desktop-Icon & Offline-Hotspot (Tablet-Test Feedback Runde 7)
- **Desktop-Icon Fix:** ICO-Datei wird jetzt separat in `{app}\assets\` kopiert im Installer. PyInstaller 6.x legt Assets in `_internal/assets/` ab, aber Desktop-Verknüpfung referenziert `{app}\assets\fexobooth.ico`
- **Offline-Hotspot:** `hotspot.py` komplett überarbeitet - funktioniert jetzt auch OHNE Internetverbindung! Versucht zuerst Windows Tethering API mit allen Connection Profiles (nicht nur Internet-Profil), dann Fallback auf `netsh wlan hostednetwork`. SSID/Passwort werden aus Config übergeben

### Bugfixes & UX (Tablet-Test Feedback Runde 8)
- **Flash-Bild zuverlässig sichtbar:** Flash-Bild wird einmalig beim Session-Start gecacht (statt bei jedem Foto neu aus JPEG laden). `update_idletasks()` erzwingt GUI-Redraw vor der blockierenden Kamera-Aufnahme. Bild auf 80% der Container-Größe vergrößert (vorher 60%)
- **Ladezeit-Hinweis:** "Das kann bis zu 2 Minuten dauern." Text im VLC-Loading-Screen (mit und ohne Kundenname)
- **Statistik-Texte weiß:** Alle Texte im Statistik-Tab des Admin-Menüs jetzt in `text_primary` (#ffffff) statt `text_secondary`/`text_muted`
- **Auto-Fullscreen:** Wenn `start_fullscreen=True` aber Fenster nicht im Fullscreen ist (z.B. nach Admin), wird nach 10s automatisch Fullscreen wiederhergestellt. Fullscreen-Restore nach Admin nutzt jetzt `_enter_fullscreen()` mit korrektem `_set_appwindow()` und `withdraw()/deiconify()`
- **Hotspot Encoding-Fix:** `UnicodeDecodeError` bei PowerShell-Output auf deutschem Windows behoben (cp1252 → UTF-8 mit errors='replace')

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
