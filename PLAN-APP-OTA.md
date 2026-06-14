# PLAN: App-gestütztes OTA-Update der Box-Software (USB-los)

> Für die Umsetzung in einem neuen Chat. Voraussetzung: die Template/Settings-Push-
> Bugs aus `fexobox-app/HANDOFF.md` sind durch. Diese Funktion baut auf demselben
> App↔Box-Kanal auf.

---

## 1. Ziel & Motivation

Die Box-Software (`fexobooth.exe` / das `_internal/`-Paket) **per App lokal** auf das
Lenovo-Tablet aktualisieren — **statt USB-Stick**.

**Warum:** Das bestehende GitHub-OTA über das **Firmen-WLAN** ist langsam/bricht ab,
weil die Tablets in **Metallgehäusen** sitzen → schlechter Empfang zum **entfernten**
Router. Beim App-Update ist das Handy **direkt an der Box** (cm statt Meter) →
starkes lokales Signal → schnell + stabil. Bei **200+ Boxen** = großer operativer
Gewinn (kein USB-Hantieren mehr).

**Bandbreite ist NICHT das Problem:** lokales Box-WLAN schafft real ~20–40 Mbit/s →
~100–150 MB Paket in **~1–2 Min** pro Box. Das eigentliche Thema ist **Sicherheit
(Bricking vermeiden)** + **Verteilung**.

---

## 2. Bestätigte Entscheidungen (Christian)

| Frage | Entscheidung |
|---|---|
| **Verteilung** | **Dashboard** (admin.fexobox.de hostet die ZIP + Version/Checksum) |
| **Ablauf 200 Boxen** | **Einmal laden, viele Boxen** – Handy cached die ZIP, geht Box für Box (kein erneuter Download) |
| **Voll vs Delta** | **Komplett-ZIP (v1)**; Delta erst v2 (Beschleunigung) |
| **Anwenden** | **Checksum (SHA256) + bestehendes Rollback, sofort + Neustart** |
| **Auth** | **Mitarbeiter-Modus in der App via PIN 6588** schaltet die Funktion frei |

---

## 3. Architektur / End-to-End-Flow

```
GitHub-Build (Actions, Windows)
   └─ erzeugt fexobooth.zip + SHA256 + Version
   └─ lädt ZIP + Metadaten ins DASHBOARD hoch (Build-Secret)

Dashboard (admin.fexobox.de)
   └─ speichert: aktuelle Box-Version, ZIP, SHA256, Größe, Changelog
   └─ API für die App (Mitarbeiter-Auth)

App – Mitarbeiter-Modus (PIN 6588)
   1. (mit Internet) lädt die neueste ZIP EINMAL aufs Handy + cached sie
   2. geht zur Box, verbindet sich mit Box-WLAN
   3. liest Box-Version aus GET /api/v1/status → zeigt "läuft X, neu: Y"
   4. POST /api/v1/upload/software (ZIP + erwarteter SHA256, Fortschrittsbalken)

Box
   5. empfängt komplett → verifiziert SHA256 → ruft den BESTEHENDEN updater
      (apply_update_and_restart): App beenden, _internal tauschen, Rollback bei
      Fehler, Neustart. NUR im Idle (nicht mid-Event).
   6. nach Neustart zeigt /status (und Start-Screen) die neue Version
```

**Kern-Idee:** Wir erfinden den Update-Mechanismus NICHT neu. `updater.py` hat schon
die abgesicherte Apply-Logik mit **Rollback** (BAT-Skript: Pre-Check, Backup, atomarer
`_internal`-Tausch, Rollback bei Fehler). Wir füttern ihn nur mit einer **lokal vom
Handy hochgeladenen** ZIP statt einem GitHub-Download.

---

## 4. Aufgaben pro Repo

### Box (fexobooth-v2)
- [ ] **GET /api/v1/status** um `software_version` erweitern (für App-Vergleich + Anzeige).
- [ ] **Neuer Endpunkt `POST /api/v1/upload/software`** (server.py):
  - multipart `file` (ZIP), Feld/Header `sha256` = erwarteter Hash.
  - **Staff-Auth** (nicht der Kunden-Pairing-Token! → eigener Mechanismus, s. §6).
  - Größenlimit hoch (~250 MB; aktuell global 30 MB → für diesen Endpunkt separat).
  - Speichert ZIP nach `%TEMP%`, **verifiziert SHA256**, dann `updater.apply_update_and_restart(zip)`.
  - Nur anwenden, wenn Box **idle** (Startbildschirm), sonst ablehnen/markieren.
- [ ] **updater.py prüfen:** `apply_update_and_restart(zip_path)` nimmt schon einen
  lokalen ZIP-Pfad? (download_update ist getrennt von apply → vermutlich direkt nutzbar).
- [ ] **Versionsanzeige auf den Start-Screen** (dezent, Ecke) — deckt auch HANDOFF-P5 ab.

### Dashboard (adminFexobox) — additiv, live
- [ ] Speicher für aktuelle Box-Software: Version, ZIP (Storage/FTP), SHA256, Größe, Changelog.
- [ ] **Annahme der ZIP vom Build:** Endpunkt `POST /internal/box-software` mit Build-Secret
  (GitHub-Actions lädt nach dem Build hoch) — ODER manueller Upload im Dashboard-UI.
- [ ] **App-API (Mitarbeiter-Auth):**
  - `GET /api/v2/staff/box-software/latest` → `{version, sha256, size, download_url, changelog}`
  - `GET .../box-software/download` → die ZIP (Staff-Auth).

### App (fexobox-app)
- [ ] **Mitarbeiter-Modus:** PIN-6588-Gate (eigener Screen) schaltet "Box-Wartung" frei.
- [ ] **„Box-Software aktualisieren"-Flow:**
  - „Neueste laden" (mit Internet) → cache (`expo-file-system`, ~150 MB) — **einmal**, dann für viele Boxen nutzbar.
  - Ins Box-WLAN → Box-Version (aus /status) vs. verfügbar anzeigen.
  - „An Box übertragen" → `uploadAsync` mit **Fortschrittsbalken** (`createUploadTask`/Progress-Callback).
  - Ergebnis + „Box startet neu — gleich Version prüfen".
- [ ] Abbruch sauber: Box wendet erst nach **vollständigem** Empfang + Checksum-OK an → ein abgebrochener Upload kann die Box NICHT bricken.

---

## 5. Sicherheit (kritisch)
- **SHA256-Verifikation auf der Box VOR dem Anwenden** (Pflicht — kaputtes/abgebrochenes Paket darf nie angewendet werden).
- **Rollback** des bestehenden BAT-Updaters nutzen (Backup + Rollback bei Fehler).
- **Staff-Auth** (PIN 6588) für den Upload-Endpunkt, getrennt vom Kunden-Pairing-Token.
- Nur im **Idle** anwenden (nicht mid-Event), Box startet neu.
- Optional v2: **Boot-Verifikation** (Box prüft nach Update, ob sie hochfährt, sonst Auto-Rollback).

---

## 6. Offene Design-Details (im neuen Chat entscheiden)
- **Staff-Token-Mechanik:** Wie authentifiziert sich der Mitarbeiter-Modus gegen die
  **Box** (PIN 6588 → woraus wird der Box-Upload-Token? z.B. die Box akzeptiert einen
  aus PIN+Box-Secret abgeleiteten Token, oder ein festes Wartungs-Secret) und gegen das
  **Dashboard** (Admin-Login / Staff-Token)?
- **Build→Dashboard-Upload:** automatisch per Build-Secret oder manueller Dashboard-Upload?
- **Resumability:** für v1 vermutlich unnötig (Nahsignal stabil; Abbruch = neu hochladen,
  da Box erst nach Checksum-OK anwendet).

---

## 7. Risiken / Annahmen
- **Annahme (zuerst validieren!):** Das lokale Nahsignal ist deutlich besser als der
  Firmen-Router. Die WiFi-Antenne sitzt evtl. auch hinter Metall — aber cm-Abstand sollte
  reichen. **M0 unten misst das.**
- Laufende Prozesse (python-vlc etc.): vor dem `_internal`-Tausch muss die App beendet
  werden — macht der BAT-Updater schon.

---

## 8. Meilensteine
- **M0 – Machbarkeit messen:** Einmal eine ~150-MB-Datei lokal ans Box-WLAN pushen +
  Zeit/Stabilität messen. Bestätigt die ganze Idee. (Wenn lokal auch lahm → umdenken.)
- **M1 – Box:** `/api/v1/upload/software` + Checksum + Apply via updater (Test mit `curl`,
  inkl. absichtlich kaputter ZIP → Rollback muss greifen, kein Brick).
- **M2 – Dashboard:** ZIP-Hosting + Version-API + Build-Upload.
- **M3 – App:** Mitarbeiter-Modus (PIN 6588) + Update-Flow + Fortschritt.
- **M4 – End-to-End** auf einer echten Box + Rollback-Test.
- **M5 (später):** Delta-Updates, Auto-Versions-Check, Boot-Verifikation.

---

## 9. Wiederzuverwenden (Verweise)
- `fexobooth-v2/src/updater.py` – `apply_update_and_restart()` (BAT-Skript mit Rollback),
  `download_update`, `check_for_update`, `_build_ssl_context`.
- `fexobooth-v2/src/gallery/server.py` – Upload-Endpunkt-Muster (`/api/v1/upload/template`),
  Token-Auth (`_require_api_token`), MAX_CONTENT_LENGTH.
- `fexobox-app/src/lib/api/box.ts` – `uploadTemplate` (uploadAsync) als Vorlage für den
  Software-Upload (mit Progress).
- Build/Release: `fexobooth-v2/.github/workflows/build-release.yml` (erzeugt fexobooth.zip).
- Doku-Kontext: `fexobox-app/HANDOFF.md`.
