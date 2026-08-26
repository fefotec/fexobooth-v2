# Canon-Hostbetrieb ohne SD-Karte: Umsetzungsplan

**Datum:** 2026-08-26

**Zielversion:** 2.4.62

**Status:** Zur Umsetzung freigegeben

**Grundlage:**
`docs/superpowers/specs/2026-08-26-canon-no-sd-host-readiness-design.md`

## Ziel

Eine Canon EOS 2000D ohne SD-Karte wird nach bestaetigtem `SaveTo=Host` und
erfolgreicher Capacity-Meldung als host-ready behandelt, auch wenn
`AvailableShots` nach der bestehenden Ein-Sekunden-Schonfrist bei null bleibt.
Webcam, Nikon, Shutter-Timing und Transferpfad bleiben unveraendert.

## Schritt 1: Aktuelles Fehlerverhalten testseitig festhalten

**Dateien:**

- `tests/test_host_readiness.py`
- falls fuer den durchgaengigen Nachweis noetig:
  `tests/test_host_capture_integration.py`

**Umsetzung:**

1. Den bisherigen Null-Fall von "fatal" auf "host-ready ohne Karte" drehen.
2. Weiter beweisen, dass null bis zur bestehenden Frist gepollt wird und
   `EdsSetCapacity` genau einmal laeuft.
3. Nach akzeptierter null `letzter_fehler == EDS_ERR_OK` verlangen.
4. Den bestehenden Fall `0 -> positiv` unveraendert erfolgreich halten.
5. Pflichtfehler fuer `SaveTo`, UI-Lock, Capacity, UI-Unlock und
   `SaveTo`-Readback weiterhin als blockierend pruefen.
6. Wenn der Integrationstest ohne breiten Umbau konfigurierbar ist, dort
   `AvailableShots=0 -> genau ein Shutter -> genau ein Host-JPEG` abdecken.

Die Zeitgrenze wird mit der kleinsten bereits vorhandenen Testmechanik
geprueft. Eine neue Produktionsabstraktion nur zur Beschleunigung des Tests
wird nicht eingefuehrt.

## Schritt 2: Nuller Readback wird zu einem begrenzten Warnpfad

**Datei:**

- `src/camera/edsdk.py`

**Umsetzung:**

1. Die verpflichtende Reihenfolge `SaveTo -> UILock -> Capacity -> UIUnlock ->
   SaveTo-Readback` nicht veraendern.
2. `AvailableShots=0` weiterhin bis zu einer Sekunde alle 50 ms abfragen.
3. Bleibt der Wert null, nicht mehr `False` und
   `MEMORYSTATUS_NOTREADY` liefern, sondern eine eindeutige Warnung schreiben
   und auf Basis von bestaetigtem `SaveTo=Host` plus erfolgreicher Capacity
   fortfahren.
4. Positive, unbekannte, nicht lesbare und unerwartete Werte gemaess Spec
   behandeln.
5. Den finalen Marker wortgenau um die Beweisgrundlage ergaenzen:

   ```text
   CANON-HOST READY save_to=Host available_shots=<wert> readiness=<basis> duration_ms=<ms>
   ```

   Fuer null ist `<basis>` gleich `save_to+capacity`; fuer einen positiven
   Wert `available_shots`.
6. Nach jedem akzeptierten Readiness-Weg `letzter_fehler` auf `OK` setzen.

Kein Capture-, Callback-, UI- oder Kamera-Manager-Code wird fuer diese
Korrektur veraendert, sofern ein Test keinen unmittelbaren Vertragsbruch
nachweist.

## Schritt 3: Gezielte und komplette Validierung

1. `tests/test_host_readiness.py` ausfuehren.
2. Falls angepasst, `tests/test_host_capture_integration.py` ausfuehren.
3. Komplette DSLR-Suite mit `python tests/alle_tests.py` ausfuehren.
4. Geaenderte Python-Dateien mit `py_compile` pruefen.
5. `git diff --check` ausfuehren.
6. Explizit nachweisen, dass `src/camera/webcam.py`, `src/camera/nikon.py`,
   `src/ui/screens/session.py` und der Canon-Shutter-/Blitzblock keinen Diff
   erhalten haben.
7. Einen unabhaengigen Code-/Testreview gegen die freigegebene Spec einholen.

## Schritt 4: Version und Dokumentation

**Dateien nach erfolgreicher Validierung:**

- `src/__init__.py`
- `installer.iss`
- `CHANGELOG.md`
- `DSLR-STAND.md`
- `FORTSCHRITT.md`
- `ERKENNTNISSE.md`
- `TODO.md`
- nur falls der Prioritaetsstatus betroffen ist: `ROADMAP.md`

Version auf 2.4.62 setzen. Den Box-248-Befund, die korrigierte Bedeutung von
`AvailableShots=0` und die noch offene Hardware-Abnahme ohne Karte
dokumentieren. Die vorhandene lokale Loeschung unter
`alte Version fuer Recherche/` bleibt unangetastet und wird nicht committed.

## Hardware-Abnahme auf Box 248

1. SD-Karte bleibt entfernt; Wahlrad bleibt auf `P`.
2. 2.4.62 im Dev-Modus frisch starten.
3. Erwartung im Log: EOS 2000D gefunden, Session geoeffnet,
   `SaveTo=Host`, Capacity erfolgreich, Null-Warnung, danach
   `CANON-HOST READY ... readiness=save_to+capacity`.
4. Vollstaendige Session aufnehmen.
5. Pro Foto genau ein Press, Release, Blitz, Transfer und echtes
   6000-x-4000-JPEG; kein `CARD_NG`, Retry, Doppelbild oder Notloesung.
6. Logs ans Dashboard senden und vor der Flottenfreigabe auswerten.

## Rueckfallstrategie

Die Laufzeitaenderung bleibt auf die Bewertung des einen
`AvailableShots=0`-Readbacks beschraenkt. Bei einem Hardwareproblem kann der
2.4.62-Implementierungscommit einzeln zurueckgenommen werden, ohne den in
2.4.61 bestaetigten Webcam-, Nikon-, Canon-Shutter- oder UI-Ablauf anzufassen.
