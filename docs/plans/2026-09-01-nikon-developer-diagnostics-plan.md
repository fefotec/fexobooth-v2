# Nikon-Developer-Diagnose: Umsetzungsplan

**Datum:** 2026-09-01

**Zielversion:** 2.4.63

**Status:** Umgesetzt und automatisch validiert; Hardware-Abnahme auf Box 252 offen

**Grundlage:**
`docs/superpowers/specs/2026-09-01-nikon-developer-diagnostics-design.md`

## Ziel

Der naechste Developer-Log soll den Nikon-Erkennungsfehler vor Live View und
Capture eindeutig eingrenzen. Dafuer werden nur Diagnosepfade erweitert;
Erkennung, Timeouts, Warmup, Admin-Anzeige, Aufnahmeablauf sowie Canon und
Webcam bleiben funktional unveraendert.

## Schritt 1: Read-only-Diagnose in der Bridge

**Datei:** `bridge/FexoNikonBridge/Program.cs`

1. Das rueckwaertskompatible JSON-Kommando `diag` ergaenzen.
2. Bibliotheksausgaben weiterhin strikt vom stdout-Protokoll trennen, aber in
   einem threadsicheren, hart begrenzten Ringpuffer sammeln.
3. Scan-Start, Scan-Ende, Dauer, Anlass, Ergebnis und letzte Ausnahme erfassen.
4. Bereits bekannte `ConnectedDevices` defensiv und begrenzt ausgeben.
5. Bridge-Version, PID, Manager-, Kamera- und letztem Init-Zustand ausgeben.
6. Das Kommando darf keinen Scan und keine Kameraaktion ausloesen.

## Schritt 2: Developer-Diagnose im Python-Client

**Dateien:** `src/camera/nikon.py`, `src/camera/nikon_diagnostics.py`

1. Nur bei `developer_mode=true` Bridge-Aufrufe mit Request-ID, Thread,
   Lock-Wartezeit, Kommandodauer, Gesamtdauer und Ergebnis protokollieren.
2. `diag` nach Bridge-Start sowie bei leerer Liste und fehlgeschlagenem Warmup-
   oder regulaerem Init abrufen; wiederholte Abfragen drosseln.
3. Alte Bridges ohne `diag` best-effort erkennen und ohne Funktionsaenderung
   weiterverwenden.
4. Einmal pro Bridge-Start EXE und relevante DLLs im tatsaechlichen
   Bridge-Ordner mit Groesse und SHA-256 inventarisieren.
5. Nach Init-Fehlern hoechstens einmal pro Minute einen read-only Windows-
   Snapshot in einem Daemon-Thread starten: relevante PnP-Geraete, Prozesse
   und Prozessanzahlen, ohne Argumente oder Umgebungsvariablen.
6. Diagnosefehler nur loggen; sie duerfen kein Kameraergebnis veraendern.

## Schritt 3: Tests und Protokollvertrag

**Dateien:**

- `tools/nikon_smoke_test.py`
- gezielte neue Tests unter `tests/`

1. Den statischen Bridge-Vertrag um `diag`, Ringpuffer und Developer-Grenzen
   erweitern.
2. Dev-aus, Dev-an, alte Bridge, Diagnosefehler und Drosselung abdecken.
3. Python-Syntax und Nikon-Smoke-Test ausfuehren.
4. Bridge-Release-Build und einen Protokolltest fuer `ping`, `diag`, unbekanntes
   Kommando und `quit` ausfuehren, sofern .NET Framework im Arbeitsumfeld
   verfuegbar ist.
5. Bestehende Kamera-Grenztests ausfuehren und per Diff nachweisen, dass Canon-
   und Webcam-Laufzeitdateien nicht semantisch veraendert wurden.

## Schritt 4: Version und Dokumentation

**Dateien:**

- `src/__init__.py`
- `installer.iss`
- `CHANGELOG.md`
- `FORTSCHRITT.md`
- `ROADMAP.md`
- `TODO.md`

Die produktbestimmende Version und die Installer-Hinweise auf 2.4.63 setzen.
Nur den aktuellen Nikon-Diagnosestand ergaenzen; historische Versionsangaben
bleiben unveraendert.

## Hardware-Abnahme auf Box 252

1. Nikon D3300 direkt per USB anschliessen und einschalten.
2. FexoBooth 2.4.63 im Developer Mode frisch starten.
3. Einmal im Admin nach Kameras suchen und einmal eine Session starten.
4. Logs ans Dashboard uebertragen.
5. Windows-Geraetesicht, Bridge-Scan, Bibliotheksausgaben, Dateiinventar und
   moegliche Konkurrenzprozesse gemeinsam bewerten.

Erst dieser Lauf entscheidet, ob der Folgefix Windows/USB, Prozessbelegung,
Bridge-Erkennung oder eine abweichende Abhaengigkeit betrifft.

## Automatische Abnahme

- Bridge-Release-Build unter Windows: 0 Warnungen, 0 Fehler.
- Protokolltest: Developer-Pfad sowie normaler Start ohne Diagnoseflag gruen.
- Nikon-Diagnosetests: 11/11 unter Windows; gesamte DSLR-Suite: 20/20
  Testgruppen ohne Hardware.
- Kontrollierter 15-Sekunden-Init ohne Kamera: erwarteter Timeout, gueltiger
  Scanstatus, keine Canon-EDSDK-Banner im Ringpuffer.
- `py_compile`, Nikon-Smoke-Test und semantische Diffchecks fuer Canon/Webcam
  gruen.
