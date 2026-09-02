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

Ein appweiter, thread-sicherer VLC-Besitzer existiert unabhängig vom
`VideoScreen`. Er besitzt während des App-Laufs höchstens eine aktive
VLC-Instanz und einen VLC-Player. Deshalb gehören auch Warmup vor dem ersten
Video, Wiedergabe und Shutdown sicher demselben Besitzer. Beim nächsten Clip
wird ein neues VLC-Medium an denselben Player gebunden und die Wiedergabe
erneut gestartet.

Bei einem normalen Videoende werden Player und Instanz nicht freigegeben. Der
Player wechselt nur in den Zustand "bereit". Die endgültige Freigabe erfolgt
bestmöglich beim wirklichen Beenden beziehungsweise beim Zerstören des
Video-Screens.

Die bestehende VLC-Aufwärmung bleibt erhalten. Sie dient weiterhin nur dazu,
den Plugin-Cache vor dem ersten sichtbaren Video zu laden. Die dabei erzeugte
Instanz wird nicht mehr sofort wieder freigegeben, sondern direkt zum einen
persistenten Player des App-Laufs. Damit besitzt auch die Aufwärmung keinen
zweiten, unkontrollierten Freigabeweg.

Hängt bereits die native VLC-Erstellung, wartet die Bedienoberfläche nicht
unbegrenzt: Nach 120 Sekunden wird VLC für diesen App-Lauf deaktiviert und der
OpenCV-Fallback freigegeben. Der eine bereits laufende Aufwärm-Thread darf
auslaufen, erzeugt aber keine weiteren Instanzen. Kommt er verspätet zurück,
wird sein Paar nur über denselben begrenzten Aufräumweg entsorgt. Das gilt auch,
wenn gleichzeitig das Zeitlimit oder der App-Shutdown eintritt; die
Veröffentlichung des Paars wird atomar gegen `disabled` und `closed` geprüft.

### 3. Begrenzte Fehlerbehandlung

Meldet VLC einen echten Fehler oder scheitert der Start, wird das fehlerhafte
Paar unter einem kurzen Lock aus dem aktiven Weg genommen. Der Zustandsautomat
trennt Wiedergabe (`ready`/`playing`/`fallback`) und Freigabe
(`none`/`running`/`succeeded`/`failed`). Es darf im gesamten App-Lauf zu jedem
Zeitpunkt höchstens ein ausgemustertes Paar und ein asynchroner
VLC-Freigabe-Thread existieren.

Solange diese Freigabe noch läuft, wird keine weitere VLC-Instanz erzeugt. Ein
nachfolgendes Video nutzt in diesem Ausnahmefall den vorhandenen OpenCV-Fallback.
Nur wenn `stop()`, `player.release()` und `instance.release()` alle ohne
Ausnahme zurückkehren, gilt die Freigabe als bestätigt. Dann darf VLC bei einem
späteren Video insgesamt genau einmal neu aufgebaut werden. Hängt ein Aufruf
oder wirft er eine Ausnahme, bleibt der Rückstand bei einem Paar und VLC für den
Rest des Prozesses gesperrt. Eine Ausnahme aus dem Caller-eigenen
`media.release()` sperrt VLC ebenfalls dauerhaft.

Ein fehlerhaftes Video darf den Fotoablauf nicht blockieren. Der bestehende
Wechsel zum nächsten Screen bleibt erhalten.

### 4. Rückrufe und Medienreferenzen

Jeder Aufruf von `media_new()` erzeugt eine eigene native Referenz. Direkt nach
`set_media()` wird diese vom Aufrufer gehaltene Referenz deshalb in einem
`finally`-Block mit exakt einem `media.release()` freigegeben. Der Player hält
seine eigene Referenz bis zum nächsten `set_media()` beziehungsweise bis zu
seiner endgültigen Freigabe. Das wird mit einem Zähler-Fake getestet.

Nach einem Videoende werden der Abschluss-Rückruf und nicht mehr benötigte
Python-Referenzen gelöst. Damit hält der persistente Video-Screen keine alte
Session unnötig fest. Doppelte End-Rückrufe bleiben wie bisher verhindert.

Alle verzögerten Tk-Aufrufe (Aufwärmen, Einbetten, Statusprüfung, Fehlerhinweis
und OpenCV-Bildanzeige) tragen die Nummer der zugehörigen Wiedergabe. Nach einem
Screenwechsel oder einem neuen `play()` darf ein alter Rückruf nichts mehr
starten, beenden oder navigieren.

VLC und OpenCV erhalten getrennte, ein- und ausblendbare Ausgabeflächen. Jeder
OpenCV-Lauf besitzt außerdem sein eigenes Stop-Event, Capture-Objekt und seine
eigene Frame-Queue. Ein verspätet endender Reader kann deshalb weder auf die
Ressourcen des nächsten Clips zugreifen noch dessen Bilder beeinflussen.

Ein natürliches `Ended` setzt den Besitzer vor der Navigation auf `ready`.
Das anschließende `on_hide()` sieht keine laufende Wiedergabe und behält das
Paar. Ein vorzeitiges Hide entwertet dagegen zuerst alle Timer und Rückrufe und
mustert ein noch spielendes VLC-Paar genau einmal aus. Weil der aktive Pfad
selbst nie `stop()` aufruft, gilt auch ein beobachtetes `Stopped` als Fehler und
das Paar wird nicht wiederverwendet. Startfehler versuchen den aktuellen Clip
über OpenCV; ein später Laufzeitfehler setzt den Fotoablauf ohne Wiederholung
des Clips fort.

### 5. Geordnetes Beenden

`PhotoboothApp.shutdown()` ruft vor dem Zerstören des Hauptfensters einen
expliziten Video-Close-Hook auf. Der Hook blockiert den Tk-Hauptfaden nicht:
Er trennt das höchstens eine VLC-Paar ab und übergibt es dem einzigen erlaubten
Aufräum-Thread. Der bereits vorhandene Notausstiegs-Wachhund bleibt das letzte
Sicherheitsnetz.

### 6. Developer-Diagnose

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

Der belegte Fehler und die Zusage dieses Umbaus beziehen sich auf blockierende
Freigaben. Die bereits vorhandenen synchronen LibVLC-Aufrufe `set_media()`,
`set_hwnd()`, `play()` und `get_state()` bleiben zunächst unverändert; ein dort
auftretender harter nativer Hang wäre ein gesonderter Befund.

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
2. Jede Caller-Referenz aus `media_new()` wird nach `set_media()` auch bei einer
   Ausnahme genau einmal freigegeben.
3. Ein normales Videoende startet keinen Aufräum-Thread.
4. Bei einem simulierten VLC-Fehler gibt es höchstens eine ausstehende
   Freigabe und keine neue VLC-Instanz, solange diese hängt.
5. Während der begrenzten Freigabe funktioniert der OpenCV-Fallback.
6. Ein erfolgreicher kontrollierter Wiederaufbau erhöht die Player-Generation
   genau einmal.
7. Verspätete Rückrufe einer alten Wiedergabe werden wirkungslos.
8. Abschluss-Rückrufe laufen genau einmal und halten keine alte Session fest.
9. `show_screen("video")` verwendet denselben Video-Screen erneut; andere
   dynamische Screens werden weiterhin frisch aufgebaut.
10. Warmup-Zeitlimit und expliziter Shutdown-Hook sind abgedeckt.
11. Versionsquellen und Builder melden einheitlich 2.4.64.
12. Bestehende Webcam-, Canon-, Nikon-, Shutdown- und Video-Regressionstests
   bleiben grün.

Auf echter Tablet-Hardware folgt mindestens der belegte Umfang von 608 Videos
und 548 Aufnahmen. Erfolg bedeutet: 548/548 erfolgreiche Aufnahmen, genau eine
Player-Erstellung im Normalpfad, `cleanup_pending=0`, kein monotoner
RSS-/System-RAM-Anstieg über die letzten 100 Videos und kein erneuter Einbruch
der LiveView-FPS beziehungsweise Anstieg der Prozess-/System-CPU wie im
Box-155-Fehlerlauf. Die `VLC-LIFECYCLE`-Zeilen werden dafür zusammen mit den
bereits vorhandenen Kamera- und Systemlastzeilen ausgewertet.

## Auslieferung

Die Änderung wird Teil des gemeinsamen internen Builds 2.4.64. Es entsteht
kein separater Webcam-Fork. Der Build kann zuerst auf der auffälligen Webcam-Box
getestet werden; die DSLR-Funktionen aus 2.4.63 bleiben enthalten.
