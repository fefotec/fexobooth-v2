# Nikon-Developer-Diagnose fuer USB/PTP-Erkennung

**Datum:** 2026-09-01  
**Projekt:** interne FexoBooth V2  
**Zielversion:** 2.4.63

## Ausgangslage

Box 252 erkennt dieselbe Nikon D3300 nicht mehr, die am 03.07.2026 mit der
gleichen Bridge-Architektur 470 von 470 Aufnahmen erfolgreich geliefert hat.
Die Logs aus Version 2.4.62 grenzen den Fehler auf die Geraeteerkennung vor
Live View und Capture ein, verlieren aber die entscheidende Ursache:

- `FexoNikonBridge.exe` startet und beantwortet das Protokoll.
- `init` endet nach etwa 15 Sekunden mit `Keine Nikon-Kamera gefunden`.
- Der Admin-Scan liefert null Kameras.
- Die verwendete Bibliothek `CameraControl.Devices` faengt viele Windows-WPD-
  und Modellfehler intern ab. Die Bridge verwirft ihre Konsolenausgaben, damit
  sie das JSON-/JPEG-Protokoll nicht beschaedigen.
- Das aktuelle Developer-Log kennt weder die Windows-PnP-Geraeteliste noch
  alle relevanten Prozesse und Bridge-Abhaengigkeiten.

Christian hat fuer den naechsten Build bewusst einen reinen Diagnose-Schritt
gewaehlt. Verbindungsablauf, Zeitlimits und Oberflaeche bleiben vorerst
unveraendert.

## Ziele

Der naechste Hardware-Log muss eindeutig unterscheiden koennen zwischen:

1. Windows sieht die D3300 ueberhaupt nicht als USB-/WPD-/Bildgeraet.
2. Windows sieht sie und gleichzeitig laufen moegliche Konkurrenzprozesse;
   zusammen mit einem von WPD gemeldeten Busy-/Zugriffsfehler entsteht daraus
   ein belastbarer Beleg fuer eine wahrscheinliche Prozessbelegung. Eine reine
   Prozessliste allein gilt ausdruecklich nicht als Besitznachweis.
3. Die Bridge sieht einen Kandidaten, verwirft ihn jedoch wegen Modell,
   Verbindungsstatus oder eines internen Fehlers.
4. Eine Bridge-Abhaengigkeit fehlt oder unterscheidet sich vom funktionierenden
   Stand.
5. Die Bridge ist nur durch einen parallelen `list`-/`init`-Aufruf beschaeftigt.

Alle Diagnoseausgaben muessen im bestehenden Cloud-App-Log landen, damit auf
der Box kein Task-Manager und keine Tastatur benoetigt werden.

## Nicht-Ziele

- Keine Aenderung an Nikon-Erkennung, Wiederholungen, Zeitlimits oder
  Bridge-Neustarts.
- Keine Beseitigung der bereits belegten UI-Blockaden in diesem Schritt.
- Keine Aenderung am Admin-Platzhalter.
- Keine Aenderung an Live View, Capture, Bildgroesse oder Bildverarbeitung.
- Keine Aenderung an Canon oder Webcam; insbesondere bleibt
  `src/camera/webcam.py` semantisch unveraendert.
- Kein Austausch von `CameraControl.Devices` und kein Rueckgriff auf die
  sichtbare digiCamControl-App.

## Entwurf

### 1. Strukturierte Bridge-Diagnose

Die Bridge erhaelt ein rueckwaertskompatibles Kommando `diag`. Es fuehrt keine
neue Erkennung und keine Kamerafunktion aus, sondern liefert nur den bereits
vorhandenen Zustand:

- Bridge-Version und Prozess-ID,
- ob der `CameraDeviceManager` erzeugt wurde,
- Zeitpunkt, Dauer und Ergebnis des letzten Scan-Versuchs,
- Anzahl und Metadaten der Eintraege in `ConnectedDevices`,
- pro Eintrag: Typ, Geraetename, Seriennummer und `IsConnected`,
- letzte interne Bibliotheksmeldungen als begrenzter Ringpuffer,
- letzte Bridge-interne Ausnahme mit Typ, Meldung und Windows-Fehlercode,
- aktueller Kamerastatus und Zeitpunkt des letzten erfolgreichen `init`.

Die Antwort bleibt eine normale Protokollantwort mit `id`, `ok=true` und einem
Objekt `diagnostics`. Zeitpunkte werden als UTC-ISO-8601-Text, Dauern als ganze
Millisekunden, Zaehler als Ganzzahlen und fehlende Werte als `null` geliefert.
Ausnahmen enthalten nur `type`, `message` und – sofern vorhanden – einen
numerischen Windows-Fehlercode. Damit kann der Python-Client die Felder stabil
loggen, ohne menschenlesbaren Text parsen zu muessen.

`Console.Out` bleibt vom echten stdout-Protokoll getrennt. Statt die fremden
Bibliotheksausgaben komplett nach `TextWriter.Null` zu schicken, sammelt ein
threadsicherer, begrenzter `TextWriter` nur die letzten relevanten Zeilen. So
kann eine Canon-/EDSDK-Fremdmeldung niemals JSON oder JPEG beschaedigen und die
Nikon-relevante Fehlerursache geht trotzdem nicht verloren.

Alle Listen sind hart begrenzt, lange Texte werden gekuerzt und das
`diag`-Kommando antwortet auch dann, wenn einzelne Eigenschaften eines
Geraeteobjekts Ausnahmen werfen.

### 2. Developer-Diagnose im Python-Client

Nur bei `developer_mode=true` fragt `src/camera/nikon.py` den Bridge-Snapshot
ab und schreibt ihn mit einem eindeutigen Praefix ins normale App-Log. Die
Abfrage erfolgt:

- einmal nach dem Bridge-Start,
- nach einem fehlgeschlagenen Warmup-`init`,
- nach einem fehlgeschlagenen regulaeren `init`,
- bei einer leeren Admin-Liste, zeitlich gedrosselt gegen Log-Spam.

Jeder Bridge-Aufruf protokolliert ausserdem:

- Kommando und Request-ID,
- aufrufenden Thread,
- Wartezeit auf den Python-Bridge-Lock,
- reine Kommandozeit,
- Gesamtdauer und Ergebnis.

Damit wird `beschaeftigt` klar von `null Kameras` getrennt, ohne das Verhalten
der Aufrufe zu aendern.

### 3. Windows-Snapshot

Bei einem Nikon-Initialisierungsfehler startet der Developer Mode einmalig pro
Minute einen Daemon-Thread fuer einen read-only Windows-Snapshot. Er blockiert
weder Tk noch die Bridge und protokolliert:

- relevante PnP-Geraete aus `Win32_PnPEntity`, gefiltert auf Nikon, Kamera,
  Bildgeraet, WPD und USB-Kandidaten,
- Name, Hersteller, PnP-Klasse, Status, Service, Device-ID sowie
  `ConfigManagerErrorCode`,
- relevante Prozesse mit PID: FexoBooth, FexoNikonBridge, dslrBooth,
  digiCamControl/CameraControl und bekannte Nikon-Hilfsprogramme,
- Anzahl aller gleichzeitig laufenden FexoBooth- und Bridge-Prozesse.

Die Prozessliste ist ein Indiz, kein alleiniger Beweis fuer Geraetebesitz. Als
wahrscheinliche Prozessbelegung darf der Logbefund nur bezeichnet werden, wenn
Windows beziehungsweise die Bridge zusaetzlich einen passenden Busy-,
Access-Denied- oder Sharing-Fehler liefert. Ohne solches Signal lautet das
Urteil lediglich `moeglicher Konkurrenzprozess aktiv`.

Fehlt PowerShell/CIM oder laeuft eine Abfrage ins Zeitlimit, wird genau dieser
Diagnosefehler geloggt. Der Kameraablauf selbst bleibt davon unberuehrt.

### 4. Bridge-Dateiinventar

Einmal pro App-Start protokolliert der Developer Mode den tatsaechlich
verwendeten Bridge-Ordner. Fuer EXE und relevante DLLs werden Dateiname,
Dateigroesse, SHA-256 und – soweit ohne Zusatzinstallation verfuegbar – die
Windows-Dateiversion erfasst. Dadurch laesst sich Box 252 direkt mit dem
funktionierenden Release-Artefakt vergleichen.

Pfade ausserhalb des Bridge-Ordners und beliebige Benutzerdateien werden nicht
inventarisiert.

### 5. Datenschutz und Begrenzung

- Keine Umgebungsvariablen, WLAN-Schluessel, Buchungsinhalte oder Secrets.
- Geraete-IDs und Seriennummern werden nur fuer die lokal angeschlossene
  Kameradiagnose ausgegeben.
- Prozessargumente werden nicht geloggt; Name und PID reichen fuer die
  Belegungsdiagnose.
- Diagnose nur im Developer Mode.
- Ringpuffer, Textlaengen, Geraetezahl und Aufrufhaeufigkeit sind begrenzt.

## Fehlerverhalten

Jede neue Diagnose ist Best-Effort. Ein Fehler in WMI, PowerShell,
Dateiversion, Hash-Berechnung oder einer Bridge-Eigenschaft darf weder `init`
noch `list`, Live View, Capture oder das Beenden beeinflussen. Das bestehende
Ergebnis des Kameraaufrufs wird unveraendert an die Anwendung zurueckgegeben.

Bei alten Bridge-Versionen ohne `diag` erkennt der Python-Client das unbekannte
Kommando, loggt `Bridge-Diagnose nicht unterstuetzt` und arbeitet wie bisher
weiter. Damit bleibt ein kurzzeitig gemischter OTA-/Installer-Zustand
fehlertolerant.

## Versionierung

Der Diagnosebuild erhaelt Version **2.4.63**. Alle Quellen, die den Builder,
Installer und das Laufzeit-Reporting speisen, werden konsistent angehoben,
damit der erzeugte Installer nicht erneut als 2.4.62 erscheint.

## Verifikation

Ohne Nikon-Hardware lokal:

1. Python-Syntaxpruefung fuer alle geaenderten Python-Dateien.
2. Release-Build der `FexoNikonBridge` auf dem vorhandenen Windows-/CI-Weg.
3. Protokolltest fuer `ping`, `diag`, unbekanntes Kommando und `quit`.
4. Nikon-Smoke-Test erweitern: Diagnosevertrag vorhanden, alte Kommandos
   unveraendert, kein digiCamControl-App-Rueckfall.
5. Tests fuer Erfolgs-, Timeout-, alte-Bridge- und Diagnosefehler-Faelle.
6. Pruefung, dass Diagnose bei ausgeschaltetem Developer Mode nicht startet.
7. Bestehende Kamera-Grenztests ausfuehren und den Pfad-Diff pruefen:
   Webcam- und Canon-Aufnahmeverhalten bleiben unveraendert.
8. Versionskonsistenztest fuer 2.4.63 und Builder-/Installer-Namen.

Auf Box 252:

1. D3300 einschalten und direkt per USB verbinden.
2. FexoBooth 2.4.63 im Developer Mode starten.
3. Einmal Admin-Kamerasuche und einmal normalen Session-Start ausfuehren.
4. Logs ans Dashboard senden.
5. Anhand des Snapshots entscheiden, ob der Folgefix Windows/USB,
   Prozessbelegung, Bridge-Erkennung oder Abhaengigkeiten betrifft.

## Erfolgsbedingungen

- Der Builder erzeugt und meldet eindeutig 2.4.63.
- Der Cloud-Log zeigt bei einem Nikon-Fehler die Windows-Geraetesicht, relevante
  Prozesse, Bridge-Dateien, Bridge-Scanstatus und interne Bibliotheksmeldungen.
- Aus dem Log ist `Bridge beschaeftigt` von `Windows sieht kein Geraet`,
  `Bridge verwirft Geraet` und `moeglicher Konkurrenzprozess aktiv`
  unterscheidbar. Eine Prozessbelegung wird nur zusammen mit einem passenden
  Windows-/WPD-Fehlersignal als wahrscheinlich ausgewiesen.
- Keine neue UI-, Kamera- oder Capture-Semantik.
- Webcam und Canon bleiben funktional unveraendert.
