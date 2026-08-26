# Canon-Softwareblitz am echten Ausloesezeitpunkt

**Datum:** 2026-08-26

**Status:** Von Christian als Loesungsrichtung freigegeben

**Zielversion:** 2.4.61

**Bereich:** Interne FexoBooth V2, ausschliesslich Canon DSLR

## Ausgangslage

Der erste Hardwaretest von 2.4.60 auf Box 245 mit einer Canon EOS 2000D war
funktional erfolgreich: Vier von vier Aufnahmen kamen als echte JPEGs mit
6000 x 4000 Pixeln ueber den Host-Transfer an. Es gab weder `CARD_NG` noch eine
doppelte Ausloesung oder einen Transferfehler.

Die sichtbare Rueckmeldung liegt jedoch am falschen Zeitpunkt. Der kurze weisse
Softwareblitz erscheint bereits beim Ende des Countdowns. Danach startet erst
der Capture-Worker, wartet gegebenenfalls auf den Kamera-Lock und sendet den
Canon-Ausloesebefehl. Im Test lagen zwischen Softwareblitz und Rueckkehr des
erfolgreichen Canon-Ausloesebefehls:

| Foto | Versatz |
|---|---:|
| 1 | 1.497 ms |
| 2 | 1.547 ms |
| 3 | 1.569 ms |
| 4 | 1.568 ms |

Christian bestaetigte, dass der mechanische Canon-Klick erst nach dem sichtbaren
Blitz kommt. Bewegt sich der Gast direkt nach dem Softwareblitz, zeigt das echte
Foto deshalb bereits eine andere Pose. Das ist eine falsche Handlungsanweisung
an den Gast.

## Technischer Befund

FexoBooth beendet den Canon-LiveView fuer die Aufnahme nicht. Das Log bestaetigt
bei allen vier Captures `live_view=an`. Die EOS verarbeitet den Autofokus und
die mechanische Aufnahme innerhalb von
`EdsSendCommand(..., ShutterButton_Completely)`. Die Belichtungszeiten betrugen
nur 1/30 beziehungsweise 1/40 Sekunde; der rund 1,5 Sekunden lange Vorlauf ist
damit kein Software-Umschalten zwischen LiveView und Fotomodus.

Canons EDSDK stellt kein separates, exakt auf den mechanischen Verschluss
zeitgestempeltes Ereignis bereit. Die sichere Transferanforderung
`DirItemRequestTransfer` kam im Test erst 463 bis 678 ms nach Rueckkehr des
Ausloesebefehls und ist fuer den Softwareblitz sichtbar zu spaet. Die Rueckkehr
des erfolgreichen `ShutterButton_Completely`-Aufrufs ist deshalb der beste
verfuegbare, risikoarme Naeherungspunkt.

Historisch gab es keine besser gekoppelte Canon-Version. Seit Einfuehrung des
Tk-Blitzes wurde dieser vor dem Capture-Thread angezeigt. Aeltere Varianten
stoppten zusaetzlich den LiveView oder bauten einen halben Ausloesedruck ein und
waren langsamer beziehungsweise unzuverlaessiger.

## Ziele

1. Der Canon-Softwareblitz liegt so nah wie mit dem vorhandenen EDSDK-Vertrag
   sicher moeglich am hoerbaren Kameraklick.
2. Der Hardwaretest muss bestaetigen, dass eine Bewegung direkt nach dem neuen
   Blitz die aufgenommene Pose nicht mehr veraendert. EDSDK selbst liefert
   dafuer keine physikalische Verschlussgarantie.
3. Das fertige Canon-Foto wird ohne unnoetigen UI-Takt-Verzug angezeigt.
4. Ein vor oder waehrend `ShutterButton_Completely` synchron abgelehnter
   Canon-Ausloeser erzeugt keinen irrefuehrenden Blitz.
5. Webcam und Nikon bleiben funktional und semantisch unveraendert.
6. Schwarzer Wartebalken, Vorfokus und feste Schaetzverzoegerungen kommen nicht
   zurueck.

## Nicht-Ziele

- Kein Umbau des Canon-Host-Transfers, Owner-Threads oder Event-Handlers.
- Kein Stoppen oder Neustarten des LiveViews pro Foto.
- Kein `Halfway`-/`NonAF`-Ablauf und keine zweite Ausloesung.
- Keine Veraenderung von Autofokus, Belichtung, Weissabgleich oder Bilddaten.
- Keine Zusage, die kamerainterne Autofokuszeit von rund 1,5 Sekunden zu
  verkuerzen.
- Keine Aenderung am 90-ms-Blitz fuer Webcam oder am Nikon-Ablauf.

## Gewaehlter Ablauf

### Canon

1. Der Countdown endet und der Capture-Worker startet. Es erscheint noch kein
   Softwareblitz.
2. LiveView-Zugriff und Dev-Diagnose laufen wie bisher.
3. Der EDSDK-Owner sendet genau einmal `ShutterButton_Completely`. Sobald der
   native Aufruf zurueckkehrt, haelt er Ergebnis und monotone Zeit fest. Nach
   begonnenem Press-Aufruf wird `ShutterButton_OFF` in einem `finally` immer
   versucht; auch Press-Exception und Release-Fehler bleiben sichtbar.
4. Der Owner liefert ausschliesslich ein unveraenderliches Ergebnisobjekt
   zurueck. Er fuehrt niemals Tk-Code aus. Das Ergebnis trennt mindestens
   `press_ok`, `press_start_at`, `press_return_at`, `release_ok` und
   `release_return_at`.
5. Ist `press_ok=True`, meldet der Canon-Manager im Capture-Worker ueber einen
   optionalen Callback `press_command_accepted(payload)`. Ein Release-Fehler
   bleibt ein Capture-Fehler, nimmt aber nicht die Tatsache zurueck, dass der
   Press-Command bereits akzeptiert wurde.
6. Der Capture-Worker stellt diese Meldung zusammen mit seinem UI-Capture-Token
   per `after(0, ...)` in den Tk-Hauptthread. Nur dort wird bei weiterhin
   gueltigem Token der weisse 90-ms-Blitz angezeigt.
7. Host-Event, JPEG-Download und Dekodierung laufen unveraendert weiter.
8. Sobald das echte PIL-Foto den Tk-Hauptthread erreicht, zeigt Canon es direkt
   ueber den bestehenden Anzeigeweg an. Es wartet nicht mehr auf den naechsten
   LiveView-/UI-Takt.

`press_ok` bedeutet ausschliesslich, dass der synchrone
`ShutterButton_Completely`-Aufruf mit `EDS_ERR_OK` zurueckkam. Laut Canon ist das
keine Garantie, dass der mechanische Verschluss nachweislich betaetigt wurde.
Ein spaeteres `kEdsStateEvent_CaptureError`, ein fehlender Transfer oder ein
Decode-Fehler kann trotz bereits gezeigtem Blitz auftreten. Der Callback ist
deshalb eine bewusst benannte UI-Naeherung und keine neue Erfolgswahrheit fuer
den Capture.

Der Callback ist reine Rueckmeldung. Eine Callback-Exception darf weder einen
zweiten Shutter ausloesen noch den bereits laufenden Bildtransfer abbrechen.

### Nikon und Webcam

Der bisherige Einstieg bleibt unveraendert: Beide erhalten ihren Softwareblitz
weiterhin an der bisherigen Stelle. Nikon behaelt ausserdem seinen verzoegerten
Wartehinweis. Die neue Callback-Signatur wird nur im expliziten Canon-Zweig
verwendet.

## Schnittstellen und Threadgrenzen

Der Canon-Manager erweitert seinen internen Capture-Aufruf sinngemaess auf:

```text
capture_photo(timeout, press_command_accepted=None)
```

Der optionale Callback erhaelt ein unveraenderliches Payload mit:

- `capture_id`
- `press_ok`
- `press_start_at`
- `press_return_at`
- `release_ok`
- `release_return_at`

Der EDSDK-Owner erzeugt die Daten und gibt sie an den blockierten
Capture-Worker zurueck. Erst der Capture-Worker ruft
`press_command_accepted(payload)` genau einmal auf, wenn `press_ok=True` ist.
Die Callback-Exception wird dort abgefangen. Der Callback darf nur einen
Tk-Auftrag einreihen und keine Kamera-API aufrufen.

Der Session-Screen erzeugt fuer jeden UI-Capture einen monotonen
Generation-Token. Kameraart, Token und Einmal-Guard werden am Capture-Start
festgehalten und an Worker sowie UI-Callback weitergereicht. `on_hide()`, ein
neuer Capture und `_on_capture_complete()` invalidieren den alten Token.

## Zustands- und Fehlervertrag

- Pro Canon-Capture wird der Softwareblitz hoechstens einmal angefordert und
  hoechstens einmal im Tk-Hauptthread konfiguriert.
- Bei einem synchronen Fehler vor oder im Press-Command gibt es keinen
  Canon-Blitz. Nach `press_ok=True` darf ein spaeterer asynchroner CaptureError,
  Transferfehler oder Decode-Fallback den bereits gezeigten Blitz nicht
  nachtraeglich umdeuten.
- Ist der Session-Screen beim Eintreffen der Rueckmeldung nicht mehr aktiv, der
  Generation-Token veraltet oder der Capture bereits beendet, wird die
  Rueckmeldung verworfen. `is_live` und `_capture_in_progress` allein reichen
  dafuer nicht.
- Ein nicht mehr vorhandenes Tk-Widget wird fehlertolerant behandelt.
- Fehler beim Einreihen mit `after(0, ...)` und Fehler beim spaeteren Anzeigen
  des Softwareblitzes werden getrennt geloggt, aendern aber nicht das
  Kameraergebnis.
- Der bestehende Shutter-Guard, `CARD_NG`-Recovery, die Capture-ID und der
  Vertrag "genau ein Ausloesebefehl" bleiben unveraendert.
- Ein JPEG wird weiterhin nur nach passender Capture-ID akzeptiert.
- Die am Capture-Start festgehaltene Kameraart steuert die Ergebnisanzeige.
  Nur Canon ruft in `_on_capture_complete()` genau einmal
  `_display_photo_cached(photo)` auf. Dieser Weg ist unabhaengig von
  `_flash_haltend`; Nikon und Webcam behalten ihren bisherigen Anzeigeweg.

## Logging im Dev-Modus

Die naechste Hardware-Runde muss den sichtbaren Ablauf ohne Schaetzung belegen.
Dafuer kommen korrelierte Marker mit Session-/Capture-ID hinzu:

- `CANON-SHUTTER PRESS-START`
- `CANON-SHUTTER PRESS-RETURN` mit `press_ms` und Ergebnis
- `CANON-SHUTTER RELEASE-RETURN` mit `release_ms` und Ergebnis
- `CANON-FLASH REQUEST`
- `CANON-FLASH SHOWN` mit Wartezeit bis zum Tk-Hauptthread
- `CANON-PHOTO SHOWN` mit Zeit seit Press-Return und Capture-Start

`FLASH SHOWN` und `PHOTO SHOWN` bedeuten, dass das jeweilige Tk-Widget im
Hauptthread konfiguriert wurde. Sie garantieren weder einen bereits erneuerten
physischen Display-Pixel noch den mechanischen Verschlusszeitpunkt.

Die bisherigen Bezeichnungen `since_shutter_ms` und `shutter_to_queue_ms`
werden inhaltlich als "seit Shutter-Command-Start" klargestellt oder passend
umbenannt. Das Logging veraendert keine Kameraeinstellung und schreibt keine
Bilddaten, Pointer oder Zugangsdaten.

## Tests

Automatische Tests muessen ohne Kamera nachweisen:

1. Canon zeigt vor `press_ok=True` keinen Blitz.
2. Ein akzeptierter Canon-Press-Command fordert exakt einen Blitz im
   Tk-Hauptthread an.
3. Ein synchroner Fehler vor oder waehrend des Press-Commands fordert keinen
   Blitz an. Transfer-/Decode-Fallback und asynchroner CaptureError nach
   `press_ok=True` duerfen dagegen auf einen bereits angeforderten Blitz
   treffen und muessen separat geloggt bleiben.
4. Eine Callback-Exception verursacht weder Retry noch Capture-Abbruch.
5. Canon sendet weiterhin genau einmal `Completely`; nach begonnenem Press wird
   `OFF` auch bei Exception oder Fehler genau einmal versucht.
6. Das fertige Canon-Foto wird anhand der am Capture-Start festgehaltenen
   Kameraart direkt und genau einmal angezeigt.
7. Der Nikon-Wartehinweis und Nikon-Blitz bleiben unveraendert.
8. Der Webcam-Farb-, Spiegel-, Capture- und Blitzpfad bleibt unveraendert.
9. Veraltete beziehungsweise nach Screen-Wechsel eintreffende Canon-Callbacks
   werden ueber den Generation-Token ignoriert, auch wenn bereits ein neuer
   Capture laeuft.
10. Fehler beim Tk-Einreihen und beim Tk-Anzeigen bleiben fuer den eigentlichen
    Canon-Capture folgenlos.
11. Die bestehenden 18 DSLR-Regressionstests bleiben gruen.

Zusaetzlich werden `py_compile`, ein Scope-Diff fuer `webcam.py` und `nikon.py`
sowie ein unabhaengiges Abschlussreview ausgefuehrt.

## Hardware-Abnahme auf Box 245

1. 2.4.61 im Dev-Modus mit geschlossener Fremdsoftware und laufendem Canon-
   LiveView starten.
2. Eine komplette Vierer-Serie aufnehmen; die SD-Karte darf fuer diesen Test
   eingesetzt bleiben.
3. Bei jedem Foto bis zum weissen Bildschirmblitz stillhalten und direkt danach
   bewusst die Pose veraendern.
4. Das gespeicherte Foto muss die Pose vom Blitzzeitpunkt zeigen und darf nicht
   erst die Bewegung danach aufnehmen.
5. Im Log muessen genau ein Press, ein Release, ein Flash und ein passendes
   6000-x-4000-JPEG je Capture stehen.
6. Es darf weder einen schwarzen Canon-Wartebalken noch `CARD_NG`, Retry oder
   Doppelbild geben.
7. Die Zeit zwischen `PRESS-RETURN` und `FLASH-SHOWN` wird gemessen. Falls der
   Blitz auf der Hardware wahrnehmbar nach dem mechanischen Klick liegt, wird
   nur dieser UI-Uebergabepunkt nachjustiert; ein fester 1,5-Sekunden-Timer und
   ein Half-Press bleiben ausgeschlossen.

Nach erfolgreicher Abnahme folgt wie bereits geplant ein separater Canon-Test
ohne SD-Karte.
