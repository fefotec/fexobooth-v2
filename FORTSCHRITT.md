# Fortschritt - Fexobooth V2

Chronologisches Protokoll aller Änderungen.

---

## 2026-04-29

### Update-Pfade mit Timestamp gegen File-Lock-Konflikt (v2.3.0)

**Problem (User-Bericht):** Beim 2. Update kam Dialog „Update fehlgeschlagen — kann nicht auf die Datei zugreifen, da sie von einem anderen Prozess verwendet wird: `C:\Users\Selphy\AppData\Local\Temp\...`". Das erste Update lief sauber durch, das nächste hängt sich beim Download auf.

**Ursache:** [download_update()](src/updater.py) nutzte einen festen Dateinamen `%TEMP%\fexobooth_update.zip`. Beim ersten Update wird die Datei runtergeladen + nach erfolgreichem Update gelöscht — **aber Windows Defender Real-Time-Schutz** scannt frisch heruntergeladene ZIPs/EXEs noch einige Zeit nach Erstellung. Während dem Scan ist die Datei in einem nicht-löschbaren Zustand. Wenn der User direkt danach das nächste Update startet, schlägt `zip_path.unlink()` fehl, die Exception bricht den Update-Vorgang ab. Gleicher Effekt theoretisch auch für `fexobooth_updater.bat` und `fexobooth_update_extract/`.

**Fix:**
1. **Eindeutige Dateinamen pro Lauf** in [src/updater.py](src/updater.py): ZIP, BAT und Extract-Verzeichnis bekommen jetzt einen Timestamp + PID-Suffix (`fexobooth_update_<YYYYMMDD_HHMMSS>_<PID>.zip`). Damit kollidiert nie mit Resten vom letzten Update.
2. **Robustes unlink**: try/except um den unlink-Versuch + Alternativname als letzter Fallback.
3. **Orphan-Cleanup mit Glob-Patterns**: `cleanup_orphan_downloads()` nutzt jetzt `temp_dir.glob('fexobooth_update*.zip')` etc. — findet sowohl alte feste Namen (von v2.2.x) als auch neue Timestamp-Namen.

**Side-Note:** v2.3.0 ist gleichzeitig das erste Update das v2.2.9 → v2.3.0 testet ob die assets/videos/-Schutz-Logik aus v2.2.9 hält.

**Betroffen:** `src/updater.py`, `src/__init__.py` (2.2.9 → 2.3.0)

---

### Bug-Fixes: Admin-Dialog + OTA-Custom-Assets (v2.2.9)

**Bug 1: Admin-Dialog ging gelegentlich beim Öffnen sofort wieder zu** und der „ADMIN"-Button reagierte danach nicht mehr (User-Bericht). Im Log nur eine Zeile `Tab 'Allgemein' erstellt (lazy)`, dann nichts mehr von admin.py. Ursache: Im PIN-Dialog war `self.pin_frame.bind("<Button-1>", lambda e: self.destroy())` — Click-outside-zum-Schließen. Auf Touch-Screens kommt es vor dass Touch-Down auf der Karte und Touch-Up auf dem Hintergrund landet (kleine Finger-Bewegung) → Dialog schließt direkt nach Öffnen. Plus: ohne `grab_release()` blieb manchmal ein grab am Parent hängen, der ADMIN-Button reagierte dann nicht mehr.

Fix in [src/ui/screens/admin.py](src/ui/screens/admin.py):
1. `pin_frame.bind("<Button-1>", ...)` entfernt — User schließt jetzt nur über `✕`-Button oder ESC
2. `destroy()` Override eingebaut, der vor super().destroy() immer `grab_release()` aufruft

**Bug 2: OTA-Update überschrieb User-Videos und Custom-Bilder.** User-Bericht: Beim OTA-Update auf v2.2.8 wurden seine Einstellungen zu Capture-Bild und Video-Sequenzen gelöscht. Ursache: Das BAT-Script in `updater.py:create_update_script()` machte `xcopy assets/ /E /Y` — überschreibt `assets/videos/start.mp4`, `end.mp4` und ggf. ein Custom-Auslöse-Bild im `assets/`-Root mit den Defaults aus dem ZIP. `config.json` blieb zwar geschützt, aber die referenzierten Files waren weg.

Fix im BAT-Script:
1. Vor dem `xcopy`: `assets/videos/` atomar nach `%TEMP%\fexobooth_user_assets\videos` movieren, Custom-PNGs/JPGs im `assets/`-Root nach `\root_images\` kopieren
2. Nach dem `xcopy`: User-Videos atomar zurück (überschreibt Default-Videos aus dem ZIP), User-Bilder zurück
3. Backup aufräumen
4. Hinweis-Liste „Geschuetzte Dateien" um `assets/videos/` und `assets/*.png/jpg` erweitert

Damit bleiben **alle User-Custom-Files** beim OTA erhalten.

**Betroffen:** `src/ui/screens/admin.py`, `src/updater.py`, `src/__init__.py` (2.2.8 → 2.2.9)

---

### Template & Settings vom USB neu laden (v2.2.8)

**Problem:** Kunden tauschen manchmal mitten in der Veranstaltung das Template auf dem USB-Stick (oder ändern eine Einstellung in `settings.json`). Da die `booking_id` gleich bleibt, hat [BookingManager.load_from_usb()](src/storage/booking.py) den Reload übersprungen ([Z. 317](src/storage/booking.py#L317)):
```python
if not force and new_booking_id == self.booking_id and self._settings:
    return True  # gleiche Buchung, überspringe
```
Bisherige Workarounds: Stick mit anderer booking_id präparieren oder Tablet neu starten. Beides umständlich.

**Fix:** Neuer Eintrag in beide PIN-Menüs (User-Wunsch: in beide):
1. **Service-Menü 6588** ([src/ui/screens/service.py](src/ui/screens/service.py)) — neuer Button „Template & Settings vom USB neu laden". Mit Progress-Anzeige + Status-Feedback.
2. **Kunden-Menü 2015** ([src/ui/screens/admin.py](src/ui/screens/admin.py)) — neuer Button „📂 Template neu einlesen". Vereinfachte UI für Vor-Ort-Helfer.

Beide rufen `booking_manager.load_from_usb(usb_root, force=True)` auf, dann `apply_settings_to_config(config)`, dann `app._restore_cached_template()`, dann Screen-Refresh. Das erzwingt das Reload aller relevanten USB-Daten ohne Tablet-Neustart.

**Anwendungsfall settings.json:** Auch das wird damit aktualisiert — bisher genauso ignoriert wie das Template, weil der Code-Pfad identisch ist.

**Betroffen:** `src/ui/screens/service.py`, `src/ui/screens/admin.py`, `src/__init__.py` (2.2.7 → 2.2.8)

---

## 2026-04-28

### Deploy: Smart-Fallback im Pre-Flight-Check (Tooling-Fix)

**Problem (User-Beobachtung):** Master-Tablet ist 64 GB (58 GB Disk), Windows wurde auf 28 GB geschrumpft, 30 GB unallocated am Ende. Beim Capture wird die GPT-Disk-Geometrie aber als 58 GB ins Image geschrieben (Position der GPT-secondary). Beim Deploy auf 32 GB Tablet bricht der Pre-Flight-Check ab: „Image 58 GB > Ziel 29 GB" — obwohl die echten NTFS-Daten ins Ziel passen würden und Clonezilla beim Restore proportional schrumpfen kann (`ocs-expand-gpt-pt -icds`).

**Fix:** Neue Helfer-Funktion `get_image_ntfs_used_bytes()` in [custom-ocs-deploy](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy) — streamt das größte NTFS-Partclone-Image durch `unxz | partclone.chkimg`, parst „Space in use" + „Block size", liefert die echte Datennutzung in Bytes.

**Smart-Fallback im Pre-Flight-Check:** Wenn der direkte Disk-Größen-Vergleich kein passendes Image findet (alle Images haben zu große Disk-Geometrie), wird pro Image die echte NTFS-Datennutzung ermittelt und gegen `Ziel-Bytes − 400 MB (EFI/MSR) − 1 GB (Sicherheits-Buffer)` verglichen. Wenn ein Image passt → wird gewählt mit Hinweis „Disk-Geometrie größer als Ziel, aber NTFS-Daten passen — Clonezilla shrinkt proportional". Wenn kein Image passt → Abbruch wie bisher (mit erweitertem Hinweis-Text).

**Performance:** Der `partclone.chkimg`-Lauf dauert pro Image ~30-60 s (Decompression eines mehrstündigen Streams nötig). Smart-Check läuft nur wenn der Direktvergleich versagt — Standard-Fall (passendes Image vorhanden) ist unverändert schnell.

**Bonus-Fix:** `exit 1` nach allen `reboot`-Aufrufen in den Fehlerpfaden (analog zum capture-Script-Fix). `reboot` ist non-blocking, der Code-Flow wäre sonst weitergelaufen.

**Wichtig:** Tooling-Fix auf dem Deploy-Stick. App-Code unverändert v2.2.5. User muss `prepare_usb_stick.bat` mit „Partitionen behalten" laufen lassen oder `custom-ocs-deploy` manuell rüberkopieren.

**Betroffen:** `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy`

---

### OTA-Update: SSL-Cert-Fix (v2.2.5)

**Problem (Foto vom Tablet):** v2.2.4 fand das Update via API (`check_for_update()` lief durch), aber der ZIP-Download brach sofort ab mit:
```
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
unable to get local issuer certificate
```

**Ursache:** Im PyInstaller-Build findet `urllib` kein CA-Bundle. Im Dev-Modus geht's, weil Python die Windows-Zertifikate über OpenSSL findet — aber in der gepackten EXE fehlt diese Anbindung. Der API-Check vorher klappte vermutlich nur weil GitHub den TLS-Handshake mit weniger strengen Defaults toleriert hat (wahrscheinlich ein Cache-Effekt nach dem ersten erfolgreichen Call); der eigentliche Download brach dann an einem anderen Endpoint (`objects.githubusercontent.com`) ab.

**Fix:**
1. `certifi>=2024.0.0` als explizite Dependency in `requirements.txt`.
2. In [fexobooth.spec](fexobooth.spec) `collect_all("certifi")` → `cacert.pem` und alle Datendateien werden in den Build gepackt. Plus `certifi` und `ssl` in `hiddenimports`.
3. In [src/updater.py](src/updater.py) eine neue Funktion `_build_ssl_context()` die einen `ssl.create_default_context(cafile=certifi.where())` zurückgibt. Der Context wird als Modul-globale `_SSL_CONTEXT` einmal beim Import gebaut und an beide `urlopen()`-Aufrufe weitergegeben (API + Download).
4. Fallback: Wenn certifi fehlt (z.B. broken Dev-Setup), wird auf System-Default zurückgegriffen mit Warning im Log.

**Catch-22 für bestehende Tablets:** v2.2.4 und älter können das Fix nicht via OTA bekommen — genau dieses SSL-Problem blockiert ja den Download. Diese Tablets müssen **einmalig manuell** über die Setup.exe vom FEXODATEN-Stick auf v2.2.5 aktualisiert werden. Ab v2.2.5 läuft OTA für alle weiteren Versionen.

**Betroffen:** `src/updater.py`, `requirements.txt`, `fexobooth.spec`, `src/__init__.py` (2.2.4 → 2.2.5)

---

### Capture: hiberfil.sys-Removal + drei weitere Bugs (Tooling-Fix, kein App-Release)

**Problem (User-Feedback nach zweitem Tooling-Fix):** Trotz präventivem `ntfsfix` versagte partclone weiterhin mit `is scheduled for a check or it was shutdown uncleanly`. Im Log: `ntfsfix` lief erfolgreich (`Mounting volume... OK`, `Processing of $MFT and $MFTMirr completed successfully`), aber `partclone.ntfs` blockierte trotzdem.

**Root Cause:** Windows-Schnellstart hinterlässt **zwei** Marker auf der NTFS-Partition:
1. NTFS Dirty Bit im Volume-Header (das räumt `ntfsfix` weg ✓)
2. **`hiberfil.sys`** mit Kernel-Session-Hibernation (das räumt `ntfsfix` NICHT weg)

`partclone.ntfs` (intern: `ntfsclone-ng`) prüft beides und verweigert das Klonen wenn auch nur einer der beiden gesetzt ist. ntfsfix alleine reichte deshalb nicht.

**Fix 1 — hiberfil.sys via ntfs-3g entfernen:** Nach `ntfsfix -d` wird die NTFS-Partition kurz mit `mount -t ntfs-3g -o remove_hiberfile,rw` gemounted. Diese Mount-Option löscht hiberfil.sys automatisch wenn vorhanden. Dann sofort wieder unmounten. Damit ist der Hibernation-Marker weg und partclone akzeptiert die Partition.

**Fix 2 — Verifikations-Marker robuster:** Beim ANSI-Stripping (`sed -E 's/\x1b\[[0-9;]*[a-zA-Z]//g'`) verschwindet manchmal das Whitespace zwischen Wortteilen, weil im Original `shutdown\x1b[8;11Huncleanly` stand → bereinigt zu `shutdownuncleanly` (ohne Space). Mein Regex `scheduled for a check or it was shutdown uncleanly` matchte deshalb nicht. Neu: `scheduled for a check.*shutdown.*uncleanly` mit `.*` zwischen Schlüsselwörtern.

**Fix 3 — Script-Flow nach Fehler:** Das Capture-Script logte am Ende eines Fehlerlaufs paradoxerweise `[FEHLER] Image-Verifikation fehlgeschlagen` UND `[OK] Image-Verifikation erfolgreich` zugleich. Ursache: `reboot` ist non-blocking — der Befehl scheduled nur den Reboot und kehrt zurück, das Script lief dann durch in den Erfolgspfad. Fix: Nach jedem `reboot` ein `exit 1` einfügen.

**Wichtig:** Tooling-Fix auf dem Capture-Stick. App-Code unverändert v2.2.3. User muss [custom-ocs-capture](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture) neu auf den Stick kopieren (oder `prepare_usb_stick.bat` mit „Partitionen behalten" laufen lassen).

**Betroffen:** `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture`

---

### Capture: Präventives ntfsfix + ANSI-robuste Marker-Detection (Tooling-Fix, kein App-Release)

**Problem (User-Feedback nach erstem Tooling-Fix):** Der erste Fix verifizierte korrekt dass die Image-Datei für `mmcblk0p3` fehlt, zeigte aber NICHT die spezifische "dirty NTFS"-Anleitung — obwohl genau das die Ursache war. Im Log stand `is scheduled for a check or it was shutdown uncleanly`, aber mein grep matchte nicht.

**Ursache (zwei separate Probleme):**

1. **partclone schreibt Terminal-Cursor-Steuerzeichen MITTEN in den Text.** Der zusammenhängende String "is scheduled for a check or it was shutdown uncleanly" steht im Log als `is scheduled fo\x1b[7;11Hr a check or it was shutdown\x1b[8;11Huncleanly`. Mein `grep -qE "is scheduled for a check..."` findet das nicht weil der Cursor-Code zwischen `fo` und `r` sitzt. → **Fix:** ANSI-Escape-Codes via `sed -E 's/\x1b\[[0-9;]*[a-zA-Z]//g'` strippen, dann gegen Clean-Copy matchen.

2. **Windows 10/11 "Schnellstart"** — beim normalen Shutdown wird das NTFS nicht clean unmounted, sondern in einen Hibernation-ähnlichen Zustand versetzt. partclone.ntfs sieht das als "uncleanly shutdown" und verweigert das Klonen. Selbst wenn der User „sauber herunterfährt", bleibt das dirty bit gesetzt, weil Windows das absichtlich tut für schnelleren Boot. → **Fix:** Vor dem Capture läuft `ntfsfix` präventiv auf alle NTFS-Partitionen der Quell-Disk. ntfsfix clearet das dirty bit und resettet `$LogFile` — das ist sicher solange das Filesystem nicht echt korrupt ist (was wir hier voraussetzen können, weil das Tablet ja bootbar ist).

**Zusätzlich:** Der „dirty NTFS"-Hinweistext im Fehlerfall enthält jetzt die echten Lösungsschritte: `powercfg /h off` + Schnellstart-Häkchen in Energieoptionen entfernen (statt der bisher unzureichenden „bitte sauber herunterfahren"-Anleitung).

**Wichtig:** Tooling-Fix auf dem Capture-Stick. App-Code unverändert v2.2.3. User muss [custom-ocs-capture](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture) neu auf den Stick kopieren.

**Betroffen:** `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture`

---

### Capture: Verifikation gegen halbfertige Images (Deployment-Tool-Fix, kein App-Release)

**Problem (vom User gemeldet):** Capture meldete „Image erfolgreich erstellt", obwohl im Log rot „**Das Image wurde NICHT erfolgreicht gesichert**" stand. User dachte, alles ok — wäre fast mit dem halbfertigen Image ein Tablet gebricked worden.

**Ursache:**
1. NTFS-Volume hatte das **dirty bit** gesetzt (Windows nicht sauber heruntergefahren). `partclone.ntfs` weigerte sich zu klonen.
2. **`ocs-sr` gibt Exit-Code 0 zurück** auch wenn `partclone` für eine einzelne Partition fehlschlägt — der Wrapper macht einfach mit Hardware-Info-Files weiter.
3. Die Exit-Code-Prüfung in [custom-ocs-capture](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture) (`if [ "$OCS_EXIT" -ne 0 ]`) war damit wirkungslos. Script meldete „ERFOLG", obwohl `mmcblk0p3.ntfs-ptcl-img.xz.aa` (die Windows-Partition mit ~35 GB) komplett fehlte. Image war nur 25 MB groß statt 15-20 GB.

**Fix:** Nach `ocs-sr` neue Verifikation:
1. `parts`-Datei aus Image-Verzeichnis lesen → erwartete Partitionen ermitteln
2. Für jede Partition prüfen ob `${PART}.*-ptcl-img.xz.aa` existiert (+Größe loggen)
3. Log zusätzlich nach Markern scannen: `is scheduled for a check or it was shutdown uncleanly`, `Failed to save partition`, `Failed to use partclone`
4. Bei „dirty NTFS": spezifische Anleitung zeigen (Tablet booten → Windows → sauber runterfahren → Capture wiederholen)
5. Bei jedem Fehler: Image-Verzeichnis nach `${IMAGE_NAME}_FAILED_${TIMESTAMP}` umbenennen, damit es im Deploy-Menü nicht erscheint
6. Bei Erfolg: Gesamtgröße des Images loggen (Sanity-Check)

**Wichtig:** Das Script liegt auf dem Capture-USB-Stick, nicht auf den Tablets. Fix wirkt erst nach Stick-Re-Erstellung mit `prepare_usb_stick.bat` oder manuellem Rüberkopieren der Datei. **Kein neuer App-Release** — App-Code (Tablets) ist unverändert v2.2.3.

**Betroffen:** `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture`

---

### Spiegel-Bug: Texte im Druck waren seitenverkehrt (v2.2.3)

**Problem:** LiveView wird absichtlich gespiegelt — User sehen sich wie in einem Spiegel, das ist intuitiv für Pose-Anpassung. Aber im Capture-Pfad ([src/ui/screens/session.py:_capture_worker](src/ui/screens/session.py)) wurde der Frame nach der Aufnahme **ebenfalls** mit `cv2.flip(frame, 1)` gespiegelt — sowohl im Webcam- als auch im Canon-DSLR-Zweig. Das gespeicherte JPG und der Druck waren damit seitenverkehrt: Texte auf T-Shirts, Logos, Schilder, Schriftzüge — alles unleserlich.

**Fix:** Die zwei `cv2.flip(frame, 1)` aus `_capture_worker` entfernt (Z. ~657 DSLR, ~683 Webcam). Der LiveView-Flip bei Z. ~279 bleibt erhalten. Erklärende Kommentare an allen drei Stellen ergänzt damit das später nicht versehentlich „korrigiert" wird.

**Konsequenz:** Im Final-Screen sieht der User sich jetzt nicht-gespiegelt — er winkt links und sieht sich links winken. Das ist gewünscht und konsistent mit dem Druck.

**Betroffen:** `src/ui/screens/session.py`, `src/__init__.py` (2.2.2 → 2.2.3)

---

## 2026-04-23

### Update-UI: Progress-Dialog + Orphan-Cleanup (v2.2.2)

**Problem:** Nach Klick auf "Jetzt updaten" sah der User nichts mehr. Der ServiceDialog hat kein `-topmost` gesetzt ([src/ui/screens/service.py:47](src/ui/screens/service.py#L47)), während der Confirm-Dialog es hatte. Sobald `confirm.destroy()` den Bestätigungsdialog zerstörte, fiel der ServiceDialog im Z-Stack zurück — die Kiosk-Haupt-App (ebenfalls Fullscreen-Overlay) überlagerte ihn. Der Download lief im Background-Thread brav weiter, aber die Progress-Bar (nur 12 px hoch) war hinter der Haupt-App versteckt. User denkt "abgestürzt", startet neu → Download verloren, Fragmente in `%TEMP%`.

**Fix 1 — Dedizierter Progress-Dialog:** Neues Modul [src/ui/dialogs/update_progress.py](src/ui/dialogs/update_progress.py) analog zu `FexosafeBackupDialog`. Fullscreen-Overlay mit `attributes("-topmost", True)`, 28 px hohe Progress-Bar, MB-Zähler (`52.3 / 143.4 MB`), Prozent-Anzeige und klarem Phasen-Text. `service._execute_update()` öffnet jetzt diesen Dialog (nach `self.withdraw()` des ServiceDialog) statt die Inline-Progressbar zu nutzen.

**Fix 2 — Orphan-Cleanup:** Neue Funktion `updater.cleanup_orphan_downloads(max_age_hours=1.0)`, beim App-Start aufgerufen. Löscht `%TEMP%\fexobooth_update.zip`, `%TEMP%\fexobooth_update_extract\`, `%TEMP%\fexobooth_updater.bat` wenn älter als 1 h. Verhindert zugemüllte Tablets bei abgebrochenen Updates. 1 h Mindestalter schützt laufende Downloads.

**Zusätzlich:** `src.ui.dialogs.update_progress` und `src.company_network` explizit in `fexobooth.spec` als hidden imports eingetragen — nicht strikt nötig (PyInstaller findet direkte Imports), aber robuster gegen spätere Refactorings.

**Betroffen:** `src/ui/dialogs/update_progress.py` (neu), `src/ui/screens/service.py`, `src/updater.py`, `src/app.py`, `src/__init__.py`, `fexobooth.spec`

---

### Updater: Repo war privat, Fehler-Logging ergänzt (v2.2.1)

**Problem:** Der Update-Button im Service-Menü zeigte auf allen Tablets "Keine Internetverbindung" – obwohl Browser-Internet funktionierte. Das GitHub-Repo `fefotec/fexobooth-v2` war auf **private** gesetzt. Unauthentifizierte API-Calls auf private Repos liefern **HTTP 404** (GitHub-Security-Feature, versteckt Existenz privater Repos). Der Code in [src/updater.py](src/updater.py) wrapped `URLError` (dessen Subklasse `HTTPError` ist) generisch in `ConnectionError` → UI zeigt "Keine Internetverbindung". Das heißt: **der OTA-Update-Mechanismus hat seit v2.0.0 nie funktioniert.**

**Zusätzliches Problem:** Der Service-Dialog-Handler ([src/ui/screens/service.py:_check_update](src/ui/screens/service.py)) schluckte die Exception komplett ohne Logging. Das Log zeigte nur "Prüfe auf Updates..." und dann nichts mehr — Fehlerdiagnose unmöglich.

**Fix:**
1. Repo auf **public** umgestellt (`gh repo edit --visibility public`). Sicherheits-Check vorher: keine committeten Secrets, nur ein hartkodiertes Hotspot-Default-Passwort (für den Galerie-Hotspot der Box, Kunden sehen es sowieso).
2. `updater.check_for_update()` unterscheidet jetzt explizit `HTTPError` (liefert `ValueError` mit exaktem Status-Code) von `URLError` (liefert `ConnectionError`). Beide loggen mit `exc_info=True`.
3. `service._check_update()` loggt die Exception vor dem UI-Dialog.

**Verifikation:** `curl https://api.github.com/repos/fefotec/fexobooth-v2/releases/latest` (ohne Auth) liefert jetzt v2.2.0-Metadaten. `urlopen()` im PyInstaller-Build sollte jetzt ebenfalls durchkommen.

**Betroffen:** `src/updater.py`, `src/ui/screens/service.py`, `src/__init__.py` (2.2.0 → 2.2.1)

---

### Auto-Update im Firmen-WLAN

**Idee:** Wenn eine Fotobox in der Firma eingeschaltet wird (z.B. vor einer Vermietung zum Bild-Ziehen), soll sie sich still aktualisieren. Beim Kunden besteht nie eine Internetverbindung, also kann dort niemals versehentlich ein Update laufen.

**Umsetzung:**
- Neue Datei [src/company_network.py](src/company_network.py) mit zwei Funktionen: `get_active_ssid()` (liest aktive WLAN-SSID via `netsh wlan show interfaces`) und `check_and_auto_update()` (Background-Thread, prüft SSID gegen Whitelist, bei Match triggert `updater.check_for_update()`).
- Firmen-SSIDs als Default in [src/config/defaults.py](src/config/defaults.py): `fexon WLAN`, `fexon_Buero_WLAN2`, `fexon_Buero_WLAN2_5GHZ`, `fexon Gast-WLAN`, `fexon_outdoor` (Whitelist, nicht Präfix-Match — robuster gegen zufällige Kunden-WLANs mit "fexon" im Namen).
- Trigger in [src/app.py](src/app.py) am Ende von `__init__`, 15s Verzögerung nach Start, als Daemon-Thread.
- Ohne Internet wird der `ConnectionError` aus `check_for_update()` still geschluckt → beim Kunden passiert nichts.

**Warum SSID + Internet-Check statt nur Internet:** Ein Kunde könnte theoretisch ein offenes WLAN oder einen Hotspot mit Internet haben. Mit dem SSID-Check ist das doppelt abgesichert: Box muss (1) in einem der fexon-WLANs sein UND (2) Internet haben.

**Version:** Bump auf `2.2.0` — erstes Feature-Release seit 2.1.1.

**Betroffen:** `src/company_network.py` (neu), `src/app.py`, `src/config/defaults.py`, `src/__init__.py`

---

### FEXOSAFE-Backup: Überordner = Buchungs-ID (Event-ID)

**Problem:** Der FEXOSAFE-Auto-Backup-Dialog (poppt auf, sobald ein FEXOSAFE-Stick eingesteckt wird) kopierte alle Bilder nach `USB:\BILDER\Single` bzw. `\Prints` – ohne Unterscheidung nach Buchung. Wurde derselbe Stick für mehrere Events genutzt, landeten alle Bilder zusammen im selben `BILDER/`-Ordner. Der Service-Menü-Backup (PIN 6588) machte es korrekt mit Event-ID als Überordner, der Auto-Dialog aber nicht.

**Fix in [src/ui/dialogs/backup.py](src/ui/dialogs/backup.py):** Neue Methode `_get_last_event_id()` (Logik analog zu `service.py:_get_last_event_id`): aktive Buchung → aktuelle Statistik → letzte Historie → Datum-Fallback. In `_run_backup()` wird der Zielpfad jetzt zu `fexosafe_root / event_id / {Single|Prints}` statt `fexosafe_root / "BILDER" / {Single|Prints}`.

**Betroffen:** `src/ui/dialogs/backup.py`

---

## 2026-04-22

### Deployment: Pre-Flight-Check verhindert Bricken kleinerer Tablets

**Problem:** Zwei Tablets wurden beim Image-Aufspielen unbrauchbar gemacht. Beide waren **32 GB Lenovo Miix 310** (Modell `MMC DF4032`), das Image stammt aber von einem **64 GB Tablet** (`MMC DF4064`). Mit `-icds -k1` versucht Clonezilla die Partitionen proportional zu schrumpfen - aber die NTFS-Daten (34,7 GB belegt) passen physisch nicht in die ~28 GB die nach EFI+MSR auf einem 32 GB Tablet uebrig bleiben. Restore stirbt mitten im NTFS-Schreiben mit `target seek ERROR: Invalid argument`. Der vorherige Pre-Wipe hat aber bereits die alte Partitionstabelle zerstoert -> Tablet hat halbe NTFS-Daten und keine bootbare Struktur mehr.

**Fix in [custom-ocs-deploy](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy):** Neuer **Pre-Flight Check VOR dem Pre-Wipe**:
- Liest die Original-Disk-Sektorzahl aus den Image-Metadaten (`<disk>-pt.sf`, Feld `last-lba`)
- Vergleicht mit Ziel-Disk-Sektorzahl
- Toleranz 5% (deckt eMMC-Chargen-Variationen ab, z.B. 8 MB Differenz zwischen 64 GB Tablets)
- Bei Ziel < 95% der Image-Groesse: **ABBRUCH bevor Pre-Wipe gestartet wird**
- Tablet bleibt unveraendert, klare Fehlermeldung mit Image- und Ziel-GB
- Log enthaelt Hinweis "Vermutlich 32 GB Tablet, Image von 64 GB Tablet"

**Betroffen:** `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy`

**Wichtig:** Tablets die aktuell in der Sammlung sind muessen vorher nach Disk-Groesse sortiert werden (`MMC DF4032` = 32 GB, `MMC DF4064` = 64 GB). Fuer 32 GB Tablets braucht es entweder ein separates Image oder das Referenz-Image mit C < 25 GB neu capturen.

---

## 2026-04-20

### Hotspot: Auto-Dummy-Profil fuer frisch geklonte Tablets

**Problem:** Nach dem Deployment starteten einige Tablets den Hotspot nicht. Die App-Logs zeigten `Tethering API fehlgeschlagen: NO_PROFILE`. Die Diagnose ergab: `NetworkOperatorTetheringManager.CreateFromConnectionProfile()` gibt `null` zurueck solange das Tablet kein einziges gespeichertes WLAN-Profil hat. Sobald sich das Tablet einmal mit einem beliebigen WLAN verbunden hatte (auch ohne Internet), lief der Hotspot ab da dauerhaft - inklusive Disconnect.

**Fix:** Neue Funktion `_ensure_wlan_profile_exists()` in [src/gallery/hotspot.py](src/gallery/hotspot.py) wird vor jedem `start_hotspot()` aufgerufen:
- Prueft via `netsh wlan show profiles` ob mind. ein Profil existiert
- Falls nicht: legt offenes, nicht-auto-verbindendes Dummy-Profil "FexoBoothDummy" via `netsh wlan add profile` an (aus Inline-XML, kein File-Dependency)
- Passiert genau EINMAL pro Tablet, ist danach persistent

Zusaetzlich in `start_hotspot()`: Die Erfolgs-Bedingung ignoriert explizit den `NO_PROFILE`-Status, damit der Fallback-Pfad nicht faelschlicherweise als Erfolg gewertet wird.

**Betroffen:** `src/gallery/hotspot.py`

**Wichtig:** Auf bereits deployte Tablets greift der Fix sofort nach dem OTA-Update - kein Handanlegen noetig. Auf diesen Tablets wird beim naechsten Hotspot-Start einmalig das Dummy-Profil angelegt, danach geht alles.

---

### UI: Start-Button wird vom Galerie-Banner abgeschnitten

**Problem:** Bei aktivierter Galerie wurde der START-Button auf dem Start-Screen vom Galerie-Banner ueberlappt. Ursache: Der Start-Button war im `inner_frame` gepackt, der mit `place(rely=0.5, anchor="center")` zentriert wird. Wenn der Inhalt (Titel + Untertitel + Template-Karten + Button) hoeher als das verfuegbare `center_frame` ist, schaut er oben und unten drueber raus - unten in den Galerie-Banner rein.

**Fix in [src/ui/screens/start.py](src/ui/screens/start.py):** Start-Button aus `inner_frame` rausgeloest und direkt ueber dem `gallery_banner` per `pack(side="bottom")` platziert. Der Button kann so nicht mehr vom zentrierten Inhalt verdeckt werden, der zentrierte Bereich schrumpft bei Bedarf.

**Betroffen:** `src/ui/screens/start.py`

---

### Setup: Hotspot-Diagnose- und Auto-Fix-Script

**Problem:** Auf einzelnen (aus dem gleichen Image geklonten) Tablets startet der WLAN-Hotspot nicht. Die Windows-UI zeigt "Ein mobiler Hotspot kann nicht eingerichtet werden, weil Ihr PC keine Ethernet-, WLAN- oder Datenverbindung aufweist." Das ist der Standard-Offline-Fehler und tritt auch bei funktionierenden Boxen auf - das eigentliche Problem liegt tiefer (Treiber-Zustand, ICS-Dienst, Power-Management, Hosted-Network-Support).

**Lösung:** Neues Script [setup/diagnose_hotspot.bat](setup/diagnose_hotspot.bat) (+ `diagnose_hotspot.ps1`):
- Sammelt alle relevanten Infos in ein Log auf dem Desktop (+ FEXODATEN-Stick falls eingesteckt): System-Info, alle Netzwerk-Adapter (inkl. hidden), `netsh wlan show interfaces/drivers`, Hosted-Network-Support, Status von WlanSvc/SharedAccess/icssvc, aktuelle Connection Profiles
- Auto-Fixes: Services starten, Power-Management am WLAN-Adapter deaktivieren, WLAN-Adapter re-enablen, Hosted Network neu konfigurieren, Tethering API als Fallback mit allen Profilen durchprobieren
- Klares Ergebnis am Ende: LAEUFT / LAEUFT NICHT + konkrete nächste Schritte

**Betroffen:** `setup/diagnose_hotspot.bat` (neu), `setup/diagnose_hotspot.ps1` (neu)

---

### Deployment: Clonezilla-Scripts mit Auto-Fixes + persistentem Logging

**Problem:** Beim Aufspielen des Images auf Ziel-Tablets brach Clonezilla bei einigen Lenovos mit "Disk too small" ab. Ursachen waren OEM-Recovery-/"ebackup"-Partitionen auf dem Ziel sowie minimal abweichende Sektorzahlen der eMMC zwischen Herstellerchargen. Ohne Logging war der Fehler nicht nachvollziehbar - das Tablet landete nur stumm im Clonezilla "Choose mode"-Menue.

**Lösung - drei Bausteine:**

1. **Persistentes Logging in [custom-ocs-deploy](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy) und [custom-ocs-capture](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture):**
   - Gesamte Script- und `ocs-sr`-Ausgabe via `tee` nach `FEXODATEN:\deploy-logs\deploy-YYYYMMDD-HHMMSS.log` (bzw. `capture-logs/` fuer Capture) schreiben
   - Log ueberlebt Reboot → kann am PC im Texteditor gelesen werden
   - `trap cleanup EXIT` garantiert eine Status-Zeile am Ende (ERFOLG / FEHLER + Fehlermeldung)
   - Bei Fehler: grosser ASCII-Banner auf dem Bildschirm mit Log-Pfad + Wartet auf Enter

2. **Auto-Fixes gegen "Disk too small" im Deploy-Script:**
   - **Pre-Wipe**: `sgdisk --zap-all` + `wipefs -a` + `dd` 10 MB Nullen vor dem Restore entfernt alle OEM-GPT-Strukturen und Recovery-Partitionen
   - **`ocs-sr` Flags erweitert**: `-icds` (ignore check disk size) + `-k1` (proportionale Partitionen) statt nur `-e1 auto`
   - **Post-Expand**: `parted resizepart 100%` + `ntfsresize` streckt die C-Partition nach dem Restore automatisch auf die volle Disk-Groesse - egal wie gross C im Image war

3. **Dokumentation:**
   - [deployment/04_tablets-klonen/ANLEITUNG_DEPLOY.md](deployment/04_tablets-klonen/ANLEITUNG_DEPLOY.md) → neuer Abschnitt "Log-Dateien bei Problemen" + erweitertes Troubleshooting
   - [ERKENNTNISSE.md](ERKENNTNISSE.md) → Lessons-Learned Eintrag "Deployment: Clonezilla 'Disk too small' + ebackup/Recovery-Partitionen auf Lenovos"

**Betroffen:** `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy`, `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture`, `deployment/04_tablets-klonen/ANLEITUNG_DEPLOY.md`, `ERKENNTNISSE.md`

**Wichtig:** Die `custom-ocs-*` Scripts liegen im Projekt-Repo, werden aber beim Ausfuehren vom **USB-Stick** gestartet. Nach diesen Aenderungen muss der USB-Stick neu erstellt werden (`deployment/02_usb-stick-erstellen/prepare_usb_stick.bat` ausfuehren), damit die neuen Scripts auf dem Stick landen.

---

## 2026-04-10

### Bugfix: Drucker wird nicht erkannt wenn an anderem USB-Port
- **Bug:** Canon SELPHY wird von Windows als Kopie registriert wenn er an einem anderen USB-Port angeschlossen wird (z.B. "Canon SELPHY CP1000 (Kopie 1)"). Der in der Config gespeicherte Name "Canon SELPHY CP1000" matcht dann nicht mehr → "DRUCKER FEHLT!"
- **Fix:** Neue `find_matching_printer()` Funktion in `src/printer/__init__.py` die den Basis-Druckernamen vergleicht und "(Kopie N)"/"(Copy N)"-Suffixe ignoriert. Eingebaut an allen Stellen: Druckvorgang (final.py), Drucker-Status-Check (controller.py), Admin-Dropdown (admin.py), System-Test (system_test.py)
- **Betroffen:** `src/printer/__init__.py` (neu), `src/printer/controller.py`, `src/ui/screens/final.py`, `src/ui/screens/admin.py`, `src/ui/dialogs/system_test.py`

### Bugfix: Falsche Kamera benutzt trotz korrekter Auswahl in der UI
- **Bug:** Obwohl im Admin-Panel und Auto-Auswahl nur die Logitech C922 angezeigt wurde, benutzte die App tatsächlich die interne Intel AVStream Camera des Tablets. Ursache: `_get_device_names()` sortierte PnP-Geräte nach `InstanceId` (PCI vor USB), aber OpenCV/DirectShow enumiert in anderer Reihenfolge → Name-zu-Index Mapping war vertauscht
- **Fix:** Neue `_get_dshow_device_names()` Methode nutzt C#/.NET DirectShow COM-Interop (`ICreateDevEnum`, `IEnumMoniker`, `IPropertyBag`) via PowerShell `Add-Type`. Liefert Kameranamen exakt in der OpenCV `CAP_DSHOW` Reihenfolge. Alte PnP-Abfrage bleibt als Fallback (ohne `Sort-Object`)
- **Betroffen:** `src/camera/webcam.py`

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

### Feature: Interne Tablet-Kamera wird ignoriert
- **Problem:** Die interne Kamera des Lenovo Miix 310 ist physisch verdeckt. Wenn keine externe Kamera angeschlossen war, fiel die App still auf die interne zurück → Kunde merkte nicht, dass die Logitech fehlt
- **Fix:** `find_best_camera()` gibt jetzt `-1` zurück wenn nur interne Kameras da sind (statt auf `cameras[0]` zu fallen). Der Kamera-Status-Check blinkt "KEINE KAMERA!" wenn `camera_index = -1`
- **Auto-Erkennung:** Wenn im laufenden Betrieb eine externe Kamera angesteckt wird, wird sie automatisch erkannt und aktiviert (periodischer Re-Scan bei `camera_index = -1`)
- **Betroffen:** `src/camera/webcam.py`, `src/app.py`

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
