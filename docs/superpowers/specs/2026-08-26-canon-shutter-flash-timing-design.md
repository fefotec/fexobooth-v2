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
2. Nach dem Blitz darf sich der Gast bewegen, ohne dass dadurch erst die
   eigentliche Canon-Aufnahme entsteht.
3. Das fertige Canon-Foto wird ohne unnoetigen UI-Takt-Verzug angezeigt.
4. Ein fehlgeschlagener Canon-Ausloeser erzeugt keinen irrefuehrenden Blitz.
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
3. Der EDSDK-Owner sendet genau einmal
   `ShutterButton_Completely` und danach garantiert `ShutterButton_OFF`.
4. Nur wenn `edsdk.take_picture()` erfolgreich zurueckkehrt, meldet der
   Canon-Manager ueber einen optionalen Callback `shutter_accepted`.
5. Der Capture-Worker stellt diese Meldung mit `after(0, ...)` in den
   Tk-Hauptthread. Nur dort wird der weisse 90-ms-Blitz angezeigt.
6. Host-Event, JPEG-Download und Dekodierung laufen unveraendert weiter.
7. Sobald das echte PIL-Foto den Tk-Hauptthread erreicht, zeigt Canon es direkt
   ueber den bestehenden Anzeigeweg an. Es wartet nicht mehr auf den naechsten
   LiveView-/UI-Takt.

Der Callback ist reine Rueckmeldung. Eine Callback-Exception darf weder einen
zweiten Shutter ausloesen noch den bereits laufenden Bildtransfer abbrechen.

### Nikon und Webcam

Der bisherige Einstieg bleibt unveraendert: Beide erhalten ihren Softwareblitz
weiterhin an der bisherigen Stelle. Nikon behaelt ausserdem seinen verzoegerten
Wartehinweis. Die neue Callback-Signatur wird nur im expliziten Canon-Zweig
verwendet.

## Zustands- und Fehlervertrag

- Pro Canon-Capture wird der Softwareblitz hoechstens einmal angefordert.
- Ohne erfolgreichen Canon-Ausloesebefehl gibt es keinen Canon-Blitz.
- Ist der Session-Screen beim Eintreffen der Rueckmeldung nicht mehr aktiv oder
  der Capture bereits beendet, wird die Rueckmeldung verworfen.
- Ein nicht mehr vorhandenes Tk-Widget wird fehlertolerant behandelt.
- Fehler beim Anzeigen des Softwareblitzes werden geloggt, aendern aber nicht
  das Kameraergebnis.
- Der bestehende Shutter-Guard, `CARD_NG`-Recovery, die Capture-ID und der
  Vertrag "genau ein Ausloesebefehl" bleiben unveraendert.
- Ein JPEG wird weiterhin nur nach passender Capture-ID akzeptiert.

## Logging im Dev-Modus

Die naechste Hardware-Runde muss den sichtbaren Ablauf ohne Schaetzung belegen.
Dafuer kommen korrelierte Marker mit Session-/Capture-ID hinzu:

- `CANON-SHUTTER PRESS-START`
- `CANON-SHUTTER PRESS-RETURN` mit `press_ms` und Ergebnis
- `CANON-SHUTTER RELEASE-RETURN` mit `release_ms` und Ergebnis
- `CANON-FLASH REQUEST`
- `CANON-FLASH SHOWN` mit Wartezeit bis zum Tk-Hauptthread
- `CANON-PHOTO SHOWN` mit Zeit seit Press-Return und Capture-Start

Die bisherigen Bezeichnungen `since_shutter_ms` und `shutter_to_queue_ms`
werden inhaltlich als "seit Shutter-Command-Start" klargestellt oder passend
umbenannt. Das Logging veraendert keine Kameraeinstellung und schreibt keine
Bilddaten, Pointer oder Zugangsdaten.

## Tests

Automatische Tests muessen ohne Kamera nachweisen:

1. Canon zeigt vor dem erfolgreichen Shutter-Callback keinen Blitz.
2. Ein erfolgreicher Canon-Shutter fordert exakt einen Blitz im Tk-Hauptthread
   an.
3. Ein Canon-Fehler oder Fallback fordert keinen Blitz an.
4. Eine Callback-Exception verursacht weder Retry noch Capture-Abbruch.
5. Canon sendet weiterhin genau einmal `Completely` und garantiert `OFF`.
6. Das fertige Canon-Foto wird direkt angezeigt.
7. Der Nikon-Wartehinweis und Nikon-Blitz bleiben unveraendert.
8. Der Webcam-Farb-, Spiegel-, Capture- und Blitzpfad bleibt unveraendert.
9. Veraltete beziehungsweise nach Screen-Wechsel eintreffende Canon-Callbacks
   werden ignoriert.
10. Die bestehenden 18 DSLR-Regressionstests bleiben gruen.

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
