# Canon-Hostbetrieb ohne SD-Karte

**Status:** Implementiert und automatisch validiert; Hardware-Abnahme offen

**Zielversion:** 2.4.62

**Geltungsbereich:** interne FexoBooth V2, ausschließlich Canon-DSLR

## Ausgangslage

Die DSLR-Flotte arbeitet in der Regel ohne Speicherkarte. Das Foto muss über
Canons direkten Hostweg (`SaveTo=Host`) zum Box-Rechner gelangen. Eine
Speicherkarte darf deshalb weder Voraussetzung noch stiller Ersatzweg sein.

Box 248 liefert mit Version 2.4.61 und einer Canon EOS 2000D ohne SD-Karte den
fehlenden Hardwarebeleg für einen Fehler im Readiness-Vertrag:

1. EDSDK und beide Canon-Bibliotheken werden geladen.
2. Die EOS 2000D wird als genau eine Kamera gefunden.
3. `OpenSession` gelingt.
4. `SaveTo=Host`, `UILock`, `EdsSetCapacity(reset=1)` und `UIUnlock` gelingen.
5. Der `SaveTo`-Readback bestätigt den Hostweg.
6. `AvailableShots` bleibt trotzdem auch nach einer Sekunde bei null.
7. 2.4.61 wertet diese null als fatal, verwirft die geöffnete Kamera und zeigt
   dadurch irreführend an, die Kamera sei nicht erkannt worden.

Die Kamera steht auf `P`; der Videomodus ist als Ursache ausgeschlossen. Auf
Box 245 meldete dieselbe Kamerabaureihe mit eingesetzter SD-Karte dagegen 1178
verfügbare Aufnahmen und lieferte vier echte 6000-x-4000-JPEGs. Damit ist die
positive Zahl kein verlässlicher Nachweis für den Hostweg, sondern auf dieser
Baureihe vom Kartenstatus abhängig.

Canons mitgelieferte Dokumentation verlangt nach `SaveTo=Host` die Meldung der
Hostkapazität über `EdsSetCapacity`. Sie sagt lediglich, dass manche Kameras
daraus eine verbleibende Bildzahl anzeigen können. Ein positiver
`AvailableShots`-Readback ist dort keine Voraussetzung für Host-Capture.

## Ziel

Eine EOS 2000D ohne SD-Karte muss nach erfolgreich aufgebautem Hostweg als
bereit gelten, Live-View liefern und genau ein echtes Vollauflösungs-JPEG pro
Benutzeraufnahme übertragen.

## Nicht-Ziele

- Kein Kartenweg und kein automatischer Wechsel zu `SaveTo=Camera`.
- Kein unsichtbares Testfoto und kein automatischer zweiter Shutter.
- Keine Änderung an Autofokus, Belichtung, Blitzzeitpunkt oder Bildverarbeitung.
- Keine Änderung an Webcam oder Nikon.
- Keine pauschale Abschaltung der Host-Sicherheitsprüfungen.

## Gewählter Ansatz

`AvailableShots` bleibt ein Diagnose- und Kaltstartsignal, aber kein
SD-abhängiger Pflichtnachweis mehr. Die bestehende Wartezeit von einer Sekunde
bleibt erhalten. Wird in dieser Zeit ein positiver Wert gemeldet, läuft der
bisherige Erfolgsweg unverändert. Bleibt der Wert null, darf die Session auf
Basis der bereits bestätigten Hostschritte fortfahren.

Zwei Alternativen werden bewusst verworfen:

- Den Readback vollständig entfernen: Das würde ein nützliches
  Kaltstartsignal und die bisherige kurze Schonfrist verlieren.
- Ein Vorabfoto als Funktionsprobe auslösen: Das erzeugt ein zusätzliches Bild
  und verletzt den Vertrag "ein Benutzerfoto = genau ein Shutter".

## Readiness-Vertrag

Folgende Schritte bleiben zwingend. Ein Fehler in einem dieser Schritte
blockiert weiterhin die Initialisierung:

1. `SaveTo=Host` setzen.
2. Kamera-UI sperren.
3. `EdsSetCapacity` genau einmal pro geöffneter Session mit `reset=1` senden.
4. Kamera-UI garantiert entsperren.
5. `SaveTo=Host` innerhalb der bestehenden Frist erfolgreich zurücklesen.

Erst danach wird `AvailableShots` bewertet:

| Wert | Verhalten |
|---|---|
| `1` bis `0x7fffffff` | Sofort host-ready; bestehender Weg bleibt unverändert. |
| `0` | Bis zu einer Sekunde weiter abfragen; bleibt null, deutlich warnen und als kartelosen Hostbetrieb akzeptieren. |
| `0xffffffff` | Wie bisher als unbekannt protokollieren und akzeptieren. |
| Property nicht lesbar/nicht unterstützt | Wie bisher warnen und auf Basis von `SaveTo` plus Capacity akzeptieren. |
| Sonstiger unerwarteter Wert | Weiterhin ablehnen und vollständig protokollieren. |

Bei akzeptierter null setzt der Wrapper seinen letzten Fehler wieder auf `OK`,
und der Canon-Manager darf sein bestehendes Host-ready-Flag setzen. Das Log
muss die Beweisgrundlage sichtbar unterscheiden, zum Beispiel:

```text
CANON-HOST AvailableShots bleibt 0; karteloser Host-Betrieb wird auf Basis von SaveTo=Host + SetCapacity fortgesetzt
CANON-HOST READY save_to=Host available_shots=0 readiness=save_to+capacity
```

## Capture- und Fehlerverhalten

Der Capturepfad selbst bleibt unverändert. Pro Foto wird genau ein Shutter
gesendet. Ein echtes `CARD_NG`, ein fehlender Transferevent oder ein
Downloadfehler bleiben Fehler des einen Versuchs; es gibt keinen versteckten
Retry und kein zweites Foto. Die bestehende Invalidierung des Host-ready-Flags
bei einem Canon-Speicherfehler bleibt erhalten.

Damit wird nur die falsche Verbindungsablehnung beseitigt. Die gerade auf Box
245 bestätigte Reihenfolge von Press, Release, Softwareblitz, Transfer und
Fotoanzeige bleibt unangetastet.

## Änderungen und Grenzen

Die Implementierung bleibt auf den Canon-Wrapper und seine Tests begrenzt:

- `src/camera/edsdk.py`: null nach der Schonfrist warnend akzeptieren und den
  finalen Readiness-Grund loggen.
- `tests/test_host_readiness.py`: kartelose null als erfolgreichen Hostaufbau
  beweisen; alle Pflichtfehler bleiben blockierend.
- bei Bedarf `tests/test_host_capture_integration.py`: nuller Readback führt zu
  genau einem Shutter und einem Hosttransfer.
- Versionsmetadaten und DSLR-Dokumentation auf 2.4.62 fortschreiben.

`src/camera/webcam.py`, `src/camera/nikon.py` und ihre Laufzeitpfade dürfen
keinen semantischen Diff erhalten.

## Automatische Abnahme

Die Tests müssen mindestens beweisen:

1. `AvailableShots=0` wird ungefähr eine Sekunde lang abgefragt und danach
   erfolgreich akzeptiert.
2. `EdsSetCapacity` läuft dabei weiterhin genau einmal.
3. Der letzte EDSDK-Fehler ist nach akzeptierter null `OK`.
4. Ein verzögertes `0 -> positiv` folgt weiterhin dem normalen Erfolgsweg.
5. Fehler in `SaveTo`, Lock, Capacity, Unlock oder `SaveTo`-Readback blockieren.
6. Unbekannte beziehungsweise nicht unterstützte `AvailableShots` bleiben
   nicht blockierend.
7. Die komplette DSLR-Suite, `py_compile` und `git diff --check` sind grün.
8. Webcam- und Nikon-Dateien sind unverändert.

## Hardware-Abnahme auf Box 248

1. SD-Karte bleibt entfernt; Wahlrad bleibt auf `P`.
2. 2.4.62 im Dev-Modus frisch starten.
3. Erwartete Initialisierung: EOS 2000D gefunden, Session geöffnet,
   `SaveTo=Host`, Capacity erfolgreich, Warnung für `AvailableShots=0`, danach
   `CANON-HOST READY` und funktionierender Live-View.
4. Eine vollständige Session aufnehmen.
5. Pro Aufnahme genau ein Press, Release, Blitz, Transfer und Foto.
6. Jedes Ergebnis ist ein echtes 6000-x-4000-JPEG; keine Notlösung, kein
   `CARD_NG`, kein Retry und kein Doppelbild.
7. Logs erneut ans Dashboard senden und gegen diese Marker prüfen.

Erst dieser Lauf schließt den dokumentierten Flottennachweis ohne SD-Karte ab.
