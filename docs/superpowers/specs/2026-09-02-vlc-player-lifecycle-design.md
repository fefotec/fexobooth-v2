# VLC-Lebenszyklus ohne Ressourcenstau

**Datum:** 2026-09-02  
**Zielversion:** 2.4.64  
**Bereich:** interne FexoBooth V2, Video-Wiedergabe und Developer-Diagnose

## Ausgangslage

Der Belastungstest von Box 155 lief 121 Sitzungen beziehungsweise 608 Videos
lang. Alle 548 Webcam-Aufnahmen waren erfolgreich. Ab ungefähr Sitzung 110
stiegen System-RAM und CPU jedoch stark an; zugleich fiel die LiveView-Leistung
ab. Von 608 VLC-Wiedergaben wurden nur 574 Ressourcenfreigaben bestätigt. Bis
zum Logende standen 34 Freigaben aus, einige bereits seit mehreren Minuten.

Der aktuelle Video-Code erzeugt für jedes Video eine neue VLC-Instanz und einen
neuen Player. Beim Ende wird für jedes Paar ein eigener, unbegrenzter
Aufräum-Thread gestartet. Bleibt `stop()` oder `release()` in VLC hängen, läuft
die Anwendung weiter und erzeugt beim nächsten Video das nächste Paar samt
weiterem Thread. Dadurch kann ein einzelner nativer VLC-Stau zu einer
Ressourcenlawine werden.

Die Webcam ist nicht Teil dieses Fehlers. Ihr Aufnahmeweg, LiveView-Zugriff und
DirectShow-Locking bleiben unverändert.

## Betrachtete Lösungen

### A. Einen VLC-Player pro App-Lauf wiederverwenden (gewählt)

Der Video-Screen und sein VLC-Player bleiben über Bildschirmwechsel hinweg
bestehen. Ein neues Video tauscht nur das Medium aus. Eine native Freigabe ist
im Normalbetrieb nicht mehr nach jedem Clip erforderlich.

Vorteile:

- beseitigt die hunderte Male wiederholte Problemoperation;
- benötigt im Normalbetrieb nur eine VLC-Instanz und einen Player;
- erhält VLC-Hardwarebeschleunigung und den sichtbaren Ablauf;
- ist eng auf den nachgewiesenen Fehler begrenzt.

### B. Alle bisherigen Freigaben durch eine serielle Warteschlange schicken

Das würde unbegrenzt viele Threads verhindern. Hängt der erste VLC-Aufruf,
würden sich jedoch weiterhin Player und Instanzen in der Warteschlange sammeln.
Die Speicherursache wäre damit nur verschoben.

### C. VLC vollständig durch OpenCV oder eine andere Video-Technik ersetzen

Das wäre ein breiter, hardwarekritischer Umbau. OpenCV-Decoding belastet die
schwachen Tablets stärker und war historisch bereits Ursache schwarzer oder
ruckelnder Videos. Diese Lösung ist für den vorliegenden Fehler unverhältnismäßig.

## Gewähltes Design

### 1. Persistenter Video-Screen

`PhotoboothApp.show_screen()` behandelt den Video-Screen künftig als
langlebig. Session-, Filter- und Final-Screen behalten ihren bisherigen
Lebenszyklus. Der Video-Screen wird beim ersten Einsatz erstellt und danach nur
aus- beziehungsweise wieder eingeblendet.

Dadurch bleibt auch das Tk-Fensterhandle, in das VLC sein Bild einbettet,
stabil. Das Videoverhalten für den Gast ändert sich nicht.

### 2. Ein Besitzer für VLC

`VideoScreen` besitzt während des App-Laufs höchstens eine aktive
VLC-Instanz und einen VLC-Player. Beim nächsten Clip wird ein neues VLC-Medium
an denselben Player gebunden und die Wiedergabe erneut gestartet.

Bei einem normalen Videoende werden Player und Instanz nicht freigegeben. Der
Player wechselt nur in den Zustand "bereit". Die endgültige Freigabe erfolgt
bestmöglich beim wirklichen Beenden beziehungsweise beim Zerstören des
Video-Screens.

Die bestehende VLC-Aufwärmung bleibt erhalten. Sie dient weiterhin nur dazu,
den Plugin-Cache vor dem ersten sichtbaren Video zu laden.

### 3. Begrenzte Fehlerbehandlung

Meldet VLC einen echten Fehler oder scheitert der Start, wird das fehlerhafte
Paar aus dem aktiven Weg genommen. Es darf zu jedem Zeitpunkt höchstens eine
asynchrone VLC-Freigabe laufen.

Solange diese Freigabe noch läuft, wird keine weitere VLC-Instanz erzeugt. Ein
nachfolgendes Video nutzt in diesem Ausnahmefall den vorhandenen OpenCV-Fallback.
Nach erfolgreicher Freigabe darf VLC bei einem späteren Video genau einmal neu
aufgebaut werden. Bleibt die Freigabe hängen, bleibt der Rückstand trotzdem auf
ein Paar und einen Thread begrenzt.

Ein fehlerhaftes Video darf den Fotoablauf nicht blockieren. Der bestehende
Wechsel zum nächsten Screen bleibt erhalten.

### 4. Rückrufe und Medienreferenzen

Nach einem Videoende werden der Abschluss-Rückruf und nicht mehr benötigte
Medienreferenzen gelöst. Damit hält der persistente Video-Screen keine alte
Session unnötig fest. Doppelte End-Rückrufe bleiben wie bisher verhindert.

### 5. Developer-Diagnose

Im Developer Mode protokolliert der Video-Code kompakte
`VLC-LIFECYCLE`-Zeilen mit:

- Anzahl abgespielter Videos;
- Player-Generation und Anzahl echter Player-Erstellungen;
- Zustand "bereit", "spielt", "Aufräumen läuft" oder "Fallback";
- Zahl offener VLC-Aufräumarbeiten, technisch auf null oder eins begrenzt;
- Prozess-Arbeitsspeicher von `fexobooth.exe`;
- gesamten belegten System-RAM;
- aktuelle Python-Threadanzahl.

Die Diagnose ist fehlertolerant. Kann eine Kennzahl nicht gelesen werden,
beeinflusst das weder Video noch Kamera.

## Bewusst nicht enthalten

- keine Änderung in `src/camera/webcam.py`;
- keine Änderung am Webcam-Capture oder LiveView;
- keine Änderung an Canon- oder Nikon-Auslösung;
- kein kompletter Austausch von VLC;
- kein breiter Umbau der Session-, Filter- oder Final-Screens;
- keine Änderung an Videozeiten, Reihenfolge oder sichtbarer Bedienung.

## Tests und Abnahme

Automatisierte Tests verwenden eine künstliche VLC-Bibliothek und prüfen:

1. Mehrere hundert Videos erzeugen genau eine normale VLC-Instanz und einen
   Player.
2. Ein normales Videoende startet keinen Aufräum-Thread.
3. Bei einem simulierten VLC-Fehler gibt es höchstens eine ausstehende
   Freigabe und keine neue VLC-Instanz, solange diese hängt.
4. Während der begrenzten Freigabe funktioniert der OpenCV-Fallback.
5. Ein erfolgreicher kontrollierter Wiederaufbau erhöht die Player-Generation
   genau einmal.
6. Abschluss-Rückrufe laufen genau einmal und halten keine alte Session fest.
7. `show_screen("video")` verwendet denselben Video-Screen erneut; andere
   dynamische Screens werden weiterhin frisch aufgebaut.
8. Versionsquellen und Builder melden einheitlich 2.4.64.
9. Bestehende Webcam-, Canon-, Nikon-, Shutdown- und Video-Regressionstests
   bleiben grün.

Auf echter Tablet-Hardware folgt ein mehrstündiger Developer-Belastungstest.
Erfolg bedeutet: konstante Player-Anzahl, kein wachsender VLC-Cleanup-Rückstand,
kein fortlaufender RAM-Anstieg durch VLC und weiterhin erfolgreiche Fotos.

## Auslieferung

Die Änderung wird Teil des gemeinsamen internen Builds 2.4.64. Es entsteht
kein separater Webcam-Fork. Der Build kann zuerst auf der auffälligen Webcam-Box
getestet werden; die DSLR-Funktionen aus 2.4.63 bleiben enthalten.
