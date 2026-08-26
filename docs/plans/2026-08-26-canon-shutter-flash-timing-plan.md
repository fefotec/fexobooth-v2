# Canon-Shutter-Blitz-Timing: Umsetzungsplan

**Datum:** 2026-08-26

**Zielversion:** 2.4.61

**Status:** Implementiert und automatisch validiert; Hardware-Abnahme offen

**Grundlage:**
`docs/superpowers/specs/2026-08-26-canon-shutter-flash-timing-design.md`

## Ziel

Der weisse Softwareblitz wird fuer Canon nicht mehr vor dem Capture-Worker,
sondern erst nach der erfolgreichen Rueckkehr von
`ShutterButton_Completely` angefordert. Das fertige Canon-Foto wird beim
Eintreffen im Tk-Hauptthread sofort angezeigt. Webcam und Nikon behalten ihren
bisherigen Ablauf.

## Schritt 1: EDSDK-Ergebnisvertrag absichern

**Dateien:**

- `src/camera/edsdk.py`
- `tests/test_ausloeser.py`

**Umsetzung:**

1. Ein unveraenderliches Ergebnisobjekt fuer Press und Release einfuehren.
2. Den Beginn sowie die Rueckkehr beider nativen Aufrufe monoton erfassen.
3. Nach jedem begonnenen Press-Aufruf `ShutterButton_OFF` in einem `finally`
   genau einmal versuchen, auch wenn der Press-Aufruf eine Exception wirft.
4. Das Ergebnis ueber eine optionale reine Datensenke an den blockierten
   Canon-Aufruf zurueckgeben; die bestehende boolesche `take_picture()`-API fuer
   vorhandene Aufrufer beibehalten.
5. Separate Dev-Marker fuer Press-Start, Press-Return und Release-Return
   ausgeben. Press- und Release-Fehler duerfen sich nicht gegenseitig verdecken.

**Tests:**

- Erfolgsweg: genau ein `Completely`, genau ein `OFF`, vollstaendiges Ergebnis.
- Synchroner Press-Fehler: kein Erfolg, aber genau ein `OFF`.
- Press-Exception: `OFF` wird trotzdem versucht und die Ausnahme wird als
  Capture-Fehler sichtbar.
- Fehler der optionalen Datensenke beeinflusst das Kameraergebnis nicht.

## Schritt 2: Canon-Manager meldet akzeptierten Press

**Dateien:**

- `src/camera/canon.py`
- relevante Canon-Tests unter `tests/`

**Umsetzung:**

1. `capture_photo()` um den optionalen Callback
   `press_command_accepted(payload)` erweitern.
2. Pro Capture eine lokale, thread-sichere Ergebnisuebergabe und eine stabile
   Capture-ID verwenden.
3. Den Callback nur im Capture-Worker und nur einmal bei `press_ok=True`
   aufrufen. Ein anschliessender Release-, Transfer- oder Decode-Fehler bleibt
   davon unabhaengig sichtbar.
4. Callback-Exceptions nur protokollieren; kein Retry, keine zweite Ausloesung
   und kein Abbruch des Host-Transfers.
5. Bestehende Zeitfelder eindeutig als Zeit seit Beginn des
   Shutter-Commands benennen.

**Tests:**

- Callback genau einmal nach akzeptiertem Press.
- Kein Callback bei synchron abgelehntem Press.
- Callback-Exception ist nicht fatal und loest keinen zweiten Shutter aus.
- Spaeterer Transferfehler kann nach einem bereits gemeldeten Press auftreten.

## Schritt 3: Canon-Blitz sicher in den Tk-Hauptthread bringen

**Dateien:**

- `src/ui/screens/session.py`
- `tests/test_session_canon_pfad.py` oder ein eng begrenzter neuer
  Session-Timing-Test

**Umsetzung:**

1. Am Start jedes UI-Captures einen monotonen Generation-Token sowie die
   Kameraart festhalten.
2. Den bisherigen fruehen Blitz nur fuer Canon auslassen; Webcam und Nikon
   rufen ihn unveraendert am bisherigen Punkt auf.
3. Dem Canon-Manager einen Callback geben, der ausschliesslich einen
   `after(0, ...)`-Auftrag einreiht.
4. Im Tk-Hauptthread Token, aktiven Screen, Capture-Zustand und Einmal-Guard
   pruefen und erst dann den bestehenden 90-ms-Blitz anzeigen.
5. Fehler beim Einreihen und beim Anzeigen getrennt protokollieren und fuer
   den Capture folgenlos halten.
6. Token bei `on_hide()`, beim naechsten Capture und bei
   `_on_capture_complete()` invalidieren.
7. Das fertige Canon-Foto in `_on_capture_complete()` anhand der beim Start
   festgehaltenen Kameraart sofort und genau einmal anzeigen. Den bestehenden
   Webcam-HD-Sofortweg und den Nikon-Weg unveraendert lassen.

**Tests:**

- Kein Canon-Blitz vor akzeptiertem Press; danach genau einmal im Tk-Thread.
- Veraltete Rueckmeldung wird bei Screen-Wechsel und waehrend eines neuen
  Captures ignoriert.
- Fehler in `after()` und im Blitz-Callback beeinflussen das Foto nicht.
- Canon-Sofortanzeige genau einmal; Webcam-HD und Nikon behalten ihre Semantik.

## Schritt 4: Gesamtvalidierung

1. Gezielte Ausloeser-, Canon- und Session-Tests ausfuehren.
2. `tests/alle_tests.py` mit der vorhandenen Windows-Python-Installation
   ausfuehren.
3. `py_compile` fuer alle geaenderten Python-Dateien ausfuehren.
4. Mit einem Scope-Diff sicherstellen, dass `src/camera/webcam.py` und
   `src/camera/nikon.py` keinen semantischen Diff erhalten haben.
5. Fehler- und Race-Vertrag unabhaengig gegen die freigegebene Spezifikation
   pruefen.

## Schritt 5: Version und Dokumentation

**Dateien nach erfolgreicher Validierung:**

- `src/__init__.py`
- `installer.iss`
- `CHANGELOG.md`
- `DSLR-STAND.md`
- `FORTSCHRITT.md`
- `ERKENNTNISSE.md`
- `TODO.md`
- falls der Status betroffen ist: `ROADMAP.md`

Version auf 2.4.61 setzen, den exakten Naeherungsvertrag dokumentieren und den
Hardware-Abnahmetest auf Box 245 als offen markieren. Die vorhandene lokale
Loeschung unter `alte Version fuer Recherche/` bleibt unangetastet und wird
nicht committed.

## Hardware-Abnahme

Mit eingesetzter SD-Karte eine Vierer-Serie im Dev-Modus aufnehmen. Bis zum
neuen weissen Blitz stillhalten und direkt danach bewusst bewegen. Pro Capture
muessen genau ein Press, ein Release, ein Blitz und ein 6000-x-4000-JPEG im Log
stehen. Erst nach dieser Runde folgt der separate Test ohne SD-Karte.

## Rueckfallstrategie

Die Aenderung ist auf EDSDK-Ergebnisuebergabe, Canon-Callback und den
Canon-Zweig der Session begrenzt. Bei einem Hardwareproblem kann dieser Block
als einzelner Commit zurueckgenommen werden, ohne Webcam-, Nikon- oder
Host-Transfer-Architektur umzubauen.
