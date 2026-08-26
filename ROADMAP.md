# Roadmap - Fexobooth V2

Diese Datei enthält die Anforderungen und geplanten Features.

---

## Aktuelle Version

**Status:** Produktiv im Einsatz; Canon-2.4.60-Host/Kaltstart mit Karte hardwarebestaetigt; 2.4.61-Blitz/Pose-Nachtest offen
**Version:** 2.4.61 (lokal, noch kein Hardware-/GitHub-Release)
**Letzte Änderung:** 2026-08-26

---

## Kern-Features (Implementiert)

- [x] Photobooth-Workflow (Start → Capture → Preview → Final)
- [x] Webcam + Canon DSLR Support
- [x] Nikon DSLR Support (D3300) über eigene FexoNikonBridge — **hardware-validiert 2026-07-02** (LiveView + 6000×4000-Capture auf der Fotobox, unsichtbar)
- [x] USB-Template laden (ZIP vom Stick)
- [x] Buchungsnummer aus settings.json
- [x] Lokale Galerie (Flask + QR-Code)
- [x] Statistik-Modul (Fotos, Prints, Sessions)
- [x] Persistenz (Template + Buchung nach Neustart)
- [x] Offline-USB-Sync
- [x] Admin-Menü
- [x] Video-Wiedergabe (MSMF Backend)
- [x] Offline-Hotspot Setup

---

## Nikon D3300 DSLR über eigene FexoNikonBridge (Variante 3) 📷

> Ziel: Nikon-D3300 als DSLR betreiben — **unsichtbar integriert wie bei dslrBooth**: kein fremdes
> Fenster, kein verdeckter Startscreen, LiveView im Session-Screen, Capture in DSLR-Qualität.
>
> **Variante 2 (digiCamControl-App) wurde am 2026-07-02 verworfen:** sichtbares DCC-Fenster beim
> Autostart + Webserver `127.0.0.1:5513` antwortet ohne manuelle Einmal-Aktivierung nie.
> Das offizielle Nikon-SDK ist keine Option (kein Modul für die gesamte D3xxx-Serie).

**Technischer Vertrag (implementiert, Bridge-Build offen):**
- `camera_type = "nikon"`, optional `dslr_camera_type = "nikon"` (überlebt Booking-/Event-Reload)
- Eigener unsichtbarer Hintergrundprozess `bridge\FexoNikonBridge.exe` (C#/.NET Framework 4.8,
  auf Win10/11 vorinstalliert; gestartet mit `CREATE_NO_WINDOW`). Motor: MIT-Bibliothek
  `CameraControl.Devices` (digiCamControl-Kern) — rohes PTP/MTP über die Windows-WPD-API,
  D3300 dort explizit unterstützt (LiveView + Vollauflösungs-Capture in den RAM).
- Kommunikation über stdin/stdout: JSON-Zeilen + längenpräfixierte JPEG-Binärdaten
  (`ping/list/init/lv_start/frame/capture/lv_stop/release/quit`) — keine Ports, keine
  Firewall-Dialoge, kein Konfigurationsschritt in Fremdsoftware.
- Die App startet die Bridge beim Programmstart automatisch unsichtbar vor (Warmup) und
  bei Bedarf in `initialize()` neu. Konfiguration unter `nikon_bridge` (exe_path + Timeouts).
- Installer/CI: GitHub-Actions baut die Bridge (`dotnet build`) und legt sie unter `{app}\bridge\`
  bei; es wird keine Fremdsoftware mehr installiert.

**Status: ✅ HARDWARE-VALIDIERT (2026-07-02, Build 2.4.11 auf der Fotobox):** unsichtbarer
Bridge-Warmup in ~1,4 s, LiveView 640×424 im Session-Screen, 4 Captures in voller
6000×4000-Auflösung, kein Fremdfenster. Performance-Fixes danach in 2.4.12
(Overlay-/Fotoanzeige-Cache, Filter-Arbeitskopien, Final-Rendern im Hintergrund).
**Offen:** Nachtest 2.4.12 + Capture-Feintuning (~4,1 s, kameraseitig). Siehe [TODO.md](TODO.md).

---

## Geplante Features

> Hier vom User zu ergänzen

### Priorität Hoch

- [ ] _Feature hier eintragen_

### Priorität Mittel

- [ ] Admin-Menü: "Buchung zurücksetzen" Button
- [ ] Canon DSLR Live-View optimieren
- [ ] Print-Queue Anzeige

### Priorität Niedrig

- [ ] _Feature hier eintragen_

---

## Heim-WLAN-Workflow (Auto-Aktionen wenn Box im Firmen-WLAN)

**Idee:** Die Box erkennt schon heute via `src/company_network.py` ob sie im Firmen-WLAN
hängt (Whitelist `fexon WLAN`, `fexon_Buero_WLAN2` etc.). Heute wird damit nur der
GitHub-Auto-Update-Check getriggert. Das soll in drei Phasen ausgebaut werden, damit
die Box bei Rückkehr im Lager automatisch das Richtige tut.

**Performance-Garantie für alle Phasen:** Aktionen laufen ausschließlich in einem
Background-Thread, der **als Allererstes** die SSID prüft. Wenn die Box beim Kunden
steht (SSID nicht in der Whitelist), kehrt der Thread sofort zurück. Beim Kunden gibt
es keinerlei Mehrbelastung — gleiche Logik wie der heutige Auto-Updater.

**Idempotenz:** Ein Heim-Check pro Buchungs-ID, nicht pro Tag/Boot. Markierung in
einer kleinen lokalen Datei. Box hängt typischerweise eh nur einmal pro Booking im
Heim-WLAN, aber Mehrfach-Trigger werden so sauber unterbunden.

### Phase 1 — "Bilder sichern"-Screen lokal (kein Backend nötig)

**Trigger:** Heim-WLAN erkannt UND `last_booking.online_gallery == True` UND
Bilder zur Booking-ID liegen noch in `BILDER/<booking_id>/`.

**Aktion:** Modaler Fullscreen-Screen "Bilder dieser Buchung jetzt auf FEXOSAFE
sichern" mit Button, der den vorhandenen `FexosafeBackupDialog` startet
(`src/ui/dialogs/backup.py`).

**Voraussetzung im Booth-Code:**
- Booking-Parser um Feld `online_gallery` erweitern. Das Dashboard schreibt es
  schon längst in die settings.json (`AppointmentController::downloadSettingsJson`,
  Zeile 3264 + 3328), der Booth liest es aber bisher nicht.
- Drei Zeilen Änderung: Feld in `BookingSettings` dataclass, Mapping in `from_dict`,
  Default in to_dict.
- Idempotenz-Flag `homecheck_handled_for_booking_id` in `.booking_cache/`.

**Aufwand:** ca. 1-2 Tage. Kein Backend-Code, keine API, keine neue Identität.

**Begriffsklärung:** `online_gallery` = post-event Online-Galerie-Upgrade
(Kunde lädt Bilder online runter). NICHT zu verwechseln mit `live_gallery` =
`live_smartphone`-Upgrade (QR-Code-Live-Anzeige während des Events).

### Phase 2 — Box-Identität lernen + Heim-Check-API

**Ziel:** Box weiß ihre eigene `box_barcode` und kann mit dem Laravel-Dashboard
sprechen. Damit lassen sich situative Aktionen je nach aktueller Dashboard-Lage
auslösen (z.B. Defekt-Alarm gesetzt → Service-Screen).

**Identity-Learning (Pfad B):**
- Bei Heim-WLAN-Erkennung: wenn `box_identity.json` fehlt, ruft die Box
  `POST /api/v1/box/learn-identity` mit den letzten ~3 Booking-IDs aus dem Cache
  und einem HMAC-signierten Timestamp (gleiches Secret das schon
  `settings.json` signiert).
- Backend schaut in der Photobox-Booking-Verknüpfung nach, nimmt die jüngste
  Booking-ID die mit einer Box verknüpft ist (Fallback wenn die allerletzte
  Verknüpfung mal vergessen wurde).
- Backend liefert `box_barcode` + frischen Sanctum-Token zurück.
- Booth speichert beides in `box_identity.json` (write-once, vom Update-Skript
  geschützt wie `config.json`).
- Endpoint serverseitig per IP-Allowlist auf Firmen-WLAN beschränken.

**Heim-Check-API:**
- `GET /api/v1/box/{barcode}/homecheck` (Sanctum-Auth) liefert:
  - Letzte Buchung + welche Upgrades sie hatte (`online_gallery`, etc.)
  - Aktive Alerts der Box (Defekt-Alarm, ausstehende Online-Galerie, ...)
  - Liste pending-Aktionen (`upload_gallery_images`, `service_inspection`, ...)
- Box wertet aus und zeigt situative Screens: "Bilder sichern", "Box defekt
  gemeldet — bitte zur Werkstatt", "Service-Inspektion fällig", ...

**Admin-Anzeige in Booth-Software (`src/ui/screens/admin.py`):**
- Kleine Zeile oben: "Box-Identität: FB-042 ✅" (grün wenn gelernt) oder
  "nicht gesetzt ⚠️" (gelb).
- Mitarbeiter kann jederzeit mit dem Barcode-Aufkleber auf der Box vergleichen.
- "Identität zurücksetzen"-Button mit Sicherheitsabfrage für den seltenen Fall
  Tablet-Tausch zwischen Boxen.

**Aufwand:** ca. 1 Woche (Booth + Laravel + Token-Tabelle/Sanctum + Admin-UI).

### Phase 3 — Auto-Upload der Bilder ins Dashboard (optional)

**Ziel:** Wenn `online_gallery` gebucht wurde, lädt die Box bei Heimkehr die
Eventbilder direkt ins Dashboard hoch. Spart den FEXOSAFE-Stick + manuellen
Import-Schritt.

**Endpoint:** `POST /api/v1/box/{barcode}/gallery-image` mit Sanctum-Token,
Booking-ID und File-Hash (idempotent, mehrfach-Upload überschreibt nicht).

**Booth-seitig:** Upload-Queue mit Resume bei Verbindungsabbruch, Throttling
gegen Bandbreiten-Sättigung wenn mehrere Boxen gleichzeitig heimkommen, lokales
Markieren erfolgreich hochgeladener Bilder.

**Vor-Implementierung zu klären:**
- Datenschutz: Upload nur bei `online_gallery == True` der Buchung (Kunden-Zustimmung).
- Mitarbeiter-Freigabe vor Sichtbarmachung für den Kunden? (Schutz vor Test-/
  Müll-Bildern in der Kundengalerie.)
- Bandbreite: Upload-Queue server-side throttlen, damit eine Heimkehr-Welle die
  Leitung nicht sättigt.

**Aufwand:** ca. 2-3 Wochen + Datenschutz-Klärung.

---

## Update-Strategie / Staged Rollout

**Problem:** Heute ziehen alle Boxen automatisch das aktuellste GitHub-Release.
Wenn ein Update einen Bug hat, ist die ganze Flotte betroffen. Es gibt keine
Möglichkeit, ein Update erst auf wenigen Boxen zu testen, bevor es ausgerollt wird.

**Heute schon nutzbar (ohne Code-Änderung):**
GitHub's `/releases/latest`-API liefert standardmäßig keine Pre-Releases. Wenn
neue Versionen als "Pre-Release" markiert werden, ignoriert die Flotte sie.
Test auf Werkstatt-Tablet via manuelle ZIP-Installation. Wenn alles gut →
Pre-Release-Haken entfernen → Flotte zieht es. Reicht als Disziplin-Lösung
solange die Phase-2-Backend-Anbindung nicht steht.

**Mit Phase 2 — zentrale Verwaltung im Dashboard:**

Sobald Box ↔ Dashboard kommuniziert, wird der Update-Kanal pro Box im Heim-Check-
Response mitgeliefert. Dashboard-UI:

- Pro Photobox-Eintrag: Dropdown `stable / beta / freeze` und optionaler
  Version-Pin ("Diese Box bleibt auf v2.4.7 bis manuell geändert").
- "freeze" = Box updated nicht (z.B. wenn am Wochenende eine wichtige Hochzeit
  ansteht).

**Release-Manager mit Wellen (Staged Rollout):**

Pro GitHub-Release im Dashboard eine Übersicht mit Wellen-Steuerung:

- Übersicht: welche Box auf welcher Version, letzter Heim-Kontakt, Health-Status
  (läuft sauber / Smoke-Test fehlgeschlagen / Update läuft).
- "Welle starten" mit Auswahl: explizite Box-IDs **oder** "die nächsten N Boxen
  die heimkommen" **oder** "X % der Flotte nach Box-ID-Hash".
- "Welle stoppen": keine weiteren Boxen ziehen das Update; bestehende rollen
  ggf. via Auto-Rollback zurück.
- "Auf alle ausrollen": Pins entfernen, GitHub-Release als "Latest" markieren,
  Rest der Flotte zieht im Stable-Channel.
- "Box auf v2.X.Y fixieren": Notfall-Tool wenn eine Box reproduzierbar Probleme
  macht und auf einer alten Version festgenagelt werden soll.

**Datenmodell:** Neue Laravel-Tabelle `photobox_version_pins` (`photobox_id`,
`target_version`, `channel`, `set_at`). Boxen ohne Pin folgen dem globalen
Stable-Channel.

**Workflow-Beispiel:**
1. v2.5.0 als Pre-Release auf GitHub veröffentlichen.
2. Dashboard: "v2.5.0 → Welle 1: Werkstatt-Tablet FB-001" → Pin gesetzt → Box
   zieht beim nächsten Heim-Kontakt.
3. 3 Tage später alles gut: "Welle 2: 5 Boxen".
4. 1 Woche später alles gut: "Auf alle ausrollen" → Pre-Release-Flag entfernen
   → Rest der Flotte zieht.

**Auto-Rollback (Sicherheitsnetz, unabhängig vom Rollout-Mechanismus):**

Nach jedem Update läuft beim ersten App-Start ein Smoke-Test (Kamera findet,
Drucker findet, Konfig parst, Galerie-Server startet). Wenn der scheitert →
automatischer Rollback auf die vorherige Version aus `_internal_OLD/`.
Heute wird `_internal_OLD` direkt nach erfolgreichem Kopieren gelöscht
([src/updater.py:587](src/updater.py#L587)) — Änderung: 24 h aufheben, beim
nächsten Start Smoke-Test, bei Fehler zurückrollen.

**Aufwand:**
- Auto-Rollback Stufe 3: ca. 1 Tag, eigenständig.
- Release-Manager + Dashboard-UI: ca. 1 Woche, setzt Phase 2 voraus.

---

## Bekannte Einschränkungen

- Video-Wiedergabe max. 25 FPS (Performance)
- Hotspot benötigt WLAN-Adapter mit AP-Unterstützung
- Canon EDSDK nur für bestimmte Kamera-Modelle

---

## Technische Schulden

> Hier technische Verbesserungen notieren, die nicht dringend sind

- [ ] _Hier eintragen_

---

## Anmerkungen

_Platz für zusätzliche Notizen vom User_
