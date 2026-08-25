# Canon-Capture: Kaltstart, Warteanzeige, Laufzeit und Belichtungsdiagnose

**Status:** Von Christian am 25.08.2026 freigegeben

**Zielversion:** 2.4.60

**Geltungsbereich:** interne FexoBooth V2, Canon-DSLR-Pfad

## Ausgangslage

Der Hardwaretest von Version 2.4.59 auf Box 245 mit einer Canon EOS 2000D und
eingesetzter SD-Karte belegt, dass der neue Host-Transfer grundsaetzlich
funktioniert. Nach einem fehlgeschlagenen ersten Versuch kamen sieben echte
JPEGs mit 6000 x 4000 Pixeln fehlerfrei beim Tablet an.

Der erste Capture wurde synchron mit `TAKE_PICTURE_CARD_NG (0x8d07)`
abgelehnt und nochmals als Canon-`CaptureError` gemeldet. Der Code hatte zuvor
`SaveTo=Host` gelesen und `EdsSetCapacity` erfolgreich aufgerufen. Statt eines
echten Fotos lieferte die App ein 1056-x-704-Live-View-Bild als Notloesung.
Damit sind Download, Event-Queue und Autofokus nicht die Ursache dieses ersten
Fehlers. Die Kamera betrachtete ihr Speicherziel beim Kaltstart noch nicht als
aufnahmebereit.

Die sieben erfolgreichen Captures brauchten sichtbar 2,45 bis 3,18 Sekunden.
Davon lagen 1,29 bis 1,85 Sekunden im synchronen Autofokus-/Shutter-Aufruf der
Kamera. Nach dem Dekodieren verlor die App jeweils rund 300 Millisekunden durch
eine bei Canon meist wirkungslose Vollbild-Konvertierung von PIL nach NumPy,
RGB nach BGR, BGR nach RGB und zurueck nach PIL.

Der schwarze Balken `Foto wird aufgenommen ...` erscheint bei Canon nach 900
Millisekunden und ist deshalb bei jedem echten Foto sichtbar. Die gemeldete
Ueberbelichtung wurde inzwischen als verstellte Belichtungskorrektur an der
Kamera identifiziert. Die App setzt selbst keine Belichtungswerte.

## Ziele

1. Das erste Canon-Foto nach einem frischen Verbindungsaufbau darf nicht mehr
   in einen unvorbereiteten Host-Speicherzustand ausloesen.
2. Canon zeigt den schwarzen Wartebalken nicht mehr.
3. Sicher vermeidbare Nachbearbeitungszeit wird entfernt, ohne Autofokus oder
   Bildqualitaet zu veraendern.
4. Das Dev-Log zeigt kuenftig die tatsaechliche Belichtung und erkennt eine
   auffaellige Belichtungskorrektur.
5. Webcam-Verhalten und `webcam.py` bleiben semantisch unveraendert.

## Nicht-Ziele

- Kein automatischer zweiter Shutter bei `CARD_NG`, `AF_NG` oder Timeout.
- Kein Vorfokussieren waehrend des Countdowns.
- Keine automatische Aenderung von ISO, Zeit, Blende, AE-Modus,
  Belichtungskorrektur oder Weissabgleich.
- Kein Wechsel auf den SD-Karten-Pfad. Produktion bleibt `SaveTo=Host` und
  muss weiterhin auch ohne Karte funktionieren.
- Keine Aenderung am Nikon-Wartehinweis oder am Webcam-Capture.

## Entwurf

### 1. Host-Speicher einmal pro geoeffneter Session scharfstellen

Die Host-Konfiguration wird zu genau einem atomaren Auftrag im vorhandenen
EDSDK-Owner zusammengezogen. Nach `OpenSession` gilt die Reihenfolge aus
Canons Referenz:

1. `SaveTo=Host` setzen.
2. Kamera-UI sperren.
3. `EdsSetCapacity` mit `reset=1` einmal initial setzen.
4. Die UI in einem `finally`-Block garantiert wieder entsperren.
5. `SaveTo` alle 50 Millisekunden fuer hoechstens eine Sekunde zuruecklesen
   und nur bei bestaetigtem `Host` fortfahren.
6. Wenn `AvailableShots` den Wert null liefert, ebenfalls alle 50
   Millisekunden fuer hoechstens eine Sekunde auf einen positiven Wert warten.

`SaveTo` liegt bewusst vor dem Lock-Block: Schlaegt dieser Setter fehl, wurde
noch kein Lock erworben und es ist kein Unlock noetig. Sobald `UILock`
erfolgreich war, liegt `EdsSetCapacity` in einem `try` und `UIUnlock` im
zugehoerigen `finally`. Readback und Ready-Pruefung folgen erst nach dem
Unlock.

Fuer `AvailableShots` gilt ein eindeutiger Vertrag:

- `1` bis `0x7fffffff`: Host-Speicher ist bereit.
- `0`: bis zur Ein-Sekunden-Grenze weiter pruefen; bleibt der Wert null,
  scheitert die Initialisierung und der Shutter bleibt gesperrt.
- Nicht lesbar, nicht unterstuetzt oder Canons Unbekanntwert `0xffffffff`:
  deutlich protokollieren, aber nicht blockieren. In diesem Fall bilden der
  erfolgreiche Capacity-Aufruf und der bestaetigte `SaveTo=Host` den
  Readiness-Nachweis.

Schlaegt ein Pflichtschritt fehl, gilt die Kamera nicht als initialisiert und
es wird kein Shutter gesendet. Recovery und Neu-Enumeration durchlaufen
dieselbe Host-Konfiguration erneut.

Der bisherige Aufruf `EdsSetCapacity(reset=1)` unmittelbar vor jedem Foto
entfaellt. Canon dokumentiert den Reset fuer die Initialisierung des
Host-Speichers; die Kamera zieht anschliessende Transfers selbst von der
gemeldeten Kapazitaet ab. Dadurch verschwindet zugleich ein moeglicher
Kaltstart-Race und es entfallen gemessen etwa 40 bis 60 Millisekunden pro Foto.

Vor einem Capture prueft der Manager sein bestaetigtes Host-Ready-Flag. Ist es
nicht gesetzt, wird nicht ausgeloest. Ein explizites `CARD_NG` bleibt ein
Fehler dieses einen Versuchs: ausfuehrlich loggen, Host-Zustand fuer den
naechsten kontrollierten Aufbau verwerfen, aber keinen zweiten Shutter senden.

### 2. Schwarzer Balken nur bei Canon unterdruecken

Im Session-Screen wird der 900-ms-Timer fuer den Wartehinweis bei Canon nicht
mehr geplant. Nikon behaelt den bestehenden Hinweis; Webcam plante ihn schon
bisher nicht und bleibt unveraendert.

Der kurze weisse Ausloeseblitz, das Pausieren der Live-View-Lesezugriffe
waehrend des Captures und alle Kamera-Sperren bleiben erhalten. Bis das echte
Foto angezeigt wird, bleibt bei Canon das letzte Live-View-Bild ohne schwarzen
Balken eingefroren.

### 3. Canon-Nachbearbeitung ohne wirkungslose Farb-Rundreise

Das bereits dekodierte Canon-PIL-Bild wird direkt weitergereicht. Ist keine
180-Grad-Drehung konfiguriert, finden keine NumPy- und OpenCV-Konvertierungen
statt. Bei aktivierter Drehung wird die PIL-Transpose-Funktion verwendet.
Nur ein unerwarteter Bildmodus wird nach RGB konvertiert.

Der Webcam-Zweig mit seinen bestehenden OpenCV-Konvertierungen wird nicht
veraendert. Erwartetes Einsparpotenzial auf Box 245: rund 300 Millisekunden pro
echtem Canon-Foto, zusaetzlich zu den 40 bis 60 Millisekunden der entfallenden
Capacity-Neuinitialisierung.

### 4. Belichtungsdiagnose ohne Eingriff in die Kamera

Die fehlerhaften Klartextzuordnungen fuer Canon-AE-Modus und Weissabgleich
werden anhand des mitgelieferten Canon-Headers und der Canon-Samples
korrigiert. Bei der Initialisierung wird die Belichtungskorrektur einmal auch
im normalen Log gelesen; ein Wert ungleich null erzeugt eine gut sichtbare
Warnung, wird aber nicht automatisch zurueckgesetzt.

Alle zusaetzlichen EDSDK-Abfragen pro Foto sowie EXIF- und
Helligkeitsdiagnosen laufen ausschliesslich im Dev-Modus. Das Dev-Log liest
vor dem Shutter mindestens:

- Belichtungskorrektur,
- Messmethode,
- AE-Modus,
- ISO, Tv und Av,
- EVF-Belichtungssimulation, sofern die Kamera sie bereitstellt.

Unmittelbar nach dem Dekodieren des echten JPEGs werden dessen EXIF-Werte
protokolliert: Belichtungszeit, Blende, ISO, Belichtungskorrektur,
Belichtungsprogramm, Messmethode, Blitz und Weissabgleich. Im Dev-Modus wird
aus einem kleinen Vorschaubild zusaetzlich mittlere Helligkeit sowie der Anteil
fast weisser und fast schwarzer Pixel berechnet. Die Analyse darf weder das
Originalbild veraendern noch den Capture bei fehlenden EXIF-Daten scheitern
lassen.

## Fehlerverhalten

- `UIUnlock` wird nach jedem erfolgreichen `UILock` garantiert ausgefuehrt,
  auch wenn `SaveTo`, Capacity oder Readback fehlschlagen.
- Ohne bestaetigtes Host-Ziel gibt es keinen Shutter.
- Ein Shutter-Aufruf bleibt genau ein Shutter-Aufruf.
- Fehlende oder unbekannte Diagnose-Properties sind kein Capture-Fehler.
- Der bestehende Transferpfad bleibt bei `Complete` oder `Cancel` und gibt
  Referenzen weiterhin genau einmal frei.

## Tests

Die automatisierten Tests werden um folgende Nachweise erweitert:

1. Exakte Host-Initialisierungsreihenfolge und ein `UIUnlock` in allen
   Fehlerpfaden.
2. Verzoegert wirksames `SaveTo` wird begrenzt abgewartet; ohne bestaetigtes
   Host-Ziel wird nicht ausgeloest.
3. Capacity-Reset genau einmal pro geoeffneter Session, nicht pro Foto.
4. Erster Kaltstart-Capture sendet exakt einen Shutter.
5. Canon plant keinen schwarzen Balken; Nikon behaelt ihn; Webcam bleibt auf
   seinem bisherigen Pfad.
6. Canon ohne Drehung vermeidet die NumPy/OpenCV-Rundreise; 180-Grad-Drehung
   behaelt Orientierung und Farben.
7. AE-/WB-Zuordnungen entsprechen den Canon-Quellen; Belichtungskorrektur und
   EXIF-Diagnose sind auswertbar und fehlertolerant.
8. Die komplette bestehende DSLR-Suite, `py_compile` und der semantische
   Webcam-Diff bleiben gruen.

## Hardware-Abnahme

1. Version 2.4.60 frisch installieren und FexoBooth im Dev-Modus starten.
2. SD-Karte darf fuer den ersten Vergleich eingesetzt bleiben; `SaveTo=Host`
   muss im Log bestaetigt sein.
3. Direkt das allererste Foto nach dem Kamera-Kaltstart aufnehmen.
4. Erwartung: kein `CARD_NG`, kein schwarzer Balken, genau ein Shutter, echtes
   JPEG mit 6000 x 4000 Pixeln.
5. Mindestens eine komplette Vierer-Session aufnehmen und sichtbare Wartezeit
   mit 2.4.59 vergleichen.
6. Logs erneut ans Dashboard senden. Fuer den Flottennachweis folgt spaeter
   mindestens ein Test ohne SD-Karte.
