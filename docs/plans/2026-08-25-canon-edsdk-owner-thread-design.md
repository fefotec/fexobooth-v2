# Canon-EDSDK: Ein Eigentümerfaden für alle DSLR-Aufrufe

Datum: 25.08.2026  
Status: von Christian freigegeben

## Ziel

Die Canon-DSLR soll wieder echte Fotos in voller Auflösung direkt auf den
Rechner übertragen. Die Live-Flotte besitzt in der Regel keine Speicherkarte,
deshalb ist `SaveTo=Host` der primäre und zwingend funktionierende Weg.

Der funktionierende Webcam-Pfad bleibt unverändert. Gemeinsamer UI-Code darf
nur dort angepasst werden, wo Canon derzeit irrtümlich ein zweites Mal
ausgelöst wird; das Webcam-Verhalten selbst wird nicht geändert.

## Belegte Ausgangslage

- Seit dem Webcam-Umbau `841de6c` laufen Canon-Aufnahme, Live-View,
  Event-Pump und Handler-Registrierung auf mehreren Threads.
- Der in 2.4.57 eingeführte Thread `edsdk-kamera` besitzt bisher nur
  Initialisierung, Kameraliste und `OpenSession`.
- Das offizielle Canon-Beispiel bindet Session und Callback an einen
  STA-Thread und serialisiert Kameraaktionen über einen Command Processor.
- Mehrere Konstanten weichen vom mitgelieferten `EDSDKTypes.h` ab, darunter
  Object-/State-Events und JPEG-Qualitäten.
- Box-Logs zeigen einen echten Transfer-Event `0x208` mit Dateiname und
  Dateigröße; die Kamera erzeugt das Bild, aber Registrierung bzw. Download
  scheitern im derzeitigen Thread-Mix.

## Architektur

### 1. Genau ein EDSDK-Eigentümer

Ein langlebiger, COM-initialisierter STA-Thread `edsdk-kamera` besitzt:

- SDK-Initialisierung und -Beendigung,
- alle Canon-Referenzen und die Session,
- Object- und State-Handler,
- Properties, SaveTo und Capacity,
- Live-View,
- Auslösung,
- Event-Verarbeitung,
- Download/Cancel und alle Releases,
- Kartenabfragen als Diagnose-/Notweg.

Kein anderer Thread darf `EDSDK_DLL.*` direkt aufrufen. Öffentliche
Python-Funktionen des Wrappers leiten Aufträge automatisch an den
Eigentümerfaden weiter und führen sie nur dann direkt aus, wenn der Aufrufer
bereits `edsdk-kamera` ist.

### 2. Callback bleibt kurz

Der native Object-Callback lädt kein Bild herunter. Er protokolliert das Event,
legt die Objekt-Referenz als Auftrag in die Queue des Eigentümerfadens und
kehrt sofort zur Canon-DLL zurück. Download oder `EdsDownloadCancel` sowie
`EdsRelease` erfolgen danach serialisiert auf dem Eigentümerfaden.

Ein separater State-Handler verarbeitet insbesondere `Shutdown (0x301)`.
Object- und State-Handler werden mit den offiziellen `All`-Konstanten auf dem
Session-Thread registriert.

### 3. Aufnahmefluss ohne Speicherkarte

1. Host-Speicherung setzen.
2. Object- und State-Handler bestätigt registrieren.
3. Vor jeder Aufnahme `SetCapacity` senden.
4. Alte Transferergebnisse verwerfen.
5. Kamera genau einmal auslösen.
6. Eigentümerfaden pumpt Events und verarbeitet den Transferauftrag.
7. JPEG laden, vollständig dekodieren und Auflösung protokollieren.

Ein fehlgeschlagener Canon-Capture darf nicht in den generischen
High-Resolution-Fallback fallen, weil dieser beim Canon-Manager erneut
`capture_photo()` aufruft. Der Webcam-Fallback bleibt unverändert.

Der Kartenweg erfasst seine Dateibestands-Baseline vor dem Auslösen. Er dient
als Diagnose-/Notweg, nicht als Voraussetzung für die Live-Flotte.

## Fehlerbehandlung

- Ein abgelaufener Queue-Auftrag wird nicht unbemerkt erneut ausgeführt.
- Ein im nativen Aufruf blockierter Eigentümerfaden wird eindeutig als solcher
  protokolliert; es werden keine weiteren Handler-Threads gestapelt.
- Ein fehlgeschlagener Transfer wird mit `EdsDownloadCancel` beendet.
- Jede übergebene Canon-Referenz wird genau einmal freigegeben.
- SDK-Neustarts verwenden keine Referenzen aus der alten SDK-Generation.
- Keine stillen Live-View- oder Altbild-Erfolge als Beweis für ein DSLR-Foto.

## Dev-Modus-Diagnose

Nur wenn `--dev` aktiv ist, protokolliert der Canon-Wrapper detailliert:

- Sequenznummer, Funktionsname, Ursprungsthread und Queue-Wartezeit jedes
  EDSDK-Auftrags,
- Start, Ende und Dauer jedes Auftrags,
- aktuellen Owner-Thread, Queue-Tiefe und gerade laufenden Auftrag,
- Handler-Registrierung und alle Object-/State-Eventcodes,
- SaveTo, Capacity, Auslösebefehl und finalen EDSDK-Fehler,
- Transfer-Dateiname, angekündigte und empfangene Bytezahl,
- JPEG-Dekodierung und echte Bildauflösung,
- Timeouts mit dem zu diesem Zeitpunkt blockierenden Auftrag.

Es werden keine Bilddaten, Kundendaten, Tokens oder andere Secrets geloggt.
Häufige Live-View-Aufträge werden zusammengefasst, damit die entscheidenden
Capture-Ereignisse im Dashboard-Log sichtbar bleiben.

## Validierung

- Statische Tests gleichen kritische Konstanten gegen Canon-Werte ab.
- Tests belegen, dass Wrapper-Aufrufe aus Fremdthreads auf
  `edsdk-kamera` ausgeführt werden.
- Tests belegen Callback-Queue, State-Handler, Transfer-Cancel/Release,
  Karten-Baseline vor Trigger und genau einen DSLR-Capture pro Countdown.
- Bestehende Windows-Tests und Syntax-/Importprüfungen müssen bestehen.
- Hardware-Erfolg gilt erst als bewiesen, wenn Box 245 ohne Speicherkarte im
  Dev-Modus Live-View und ein echtes DSLR-JPEG in ungefähr 6000×4000 liefert.

