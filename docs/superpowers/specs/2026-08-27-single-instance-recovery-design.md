# FexoBooth: Einzelinstanz, automatische Wiederherstellung und verlaessliches Beenden

**Datum:** 2026-08-27

**Status:** Von Christian inhaltlich freigegeben; Implementierung ausstehend

**Zielversion:** 2.4.63

**Bereich:** Interne FexoBooth V2, Programmstart und Programmende

## Ausgangslage

Der Logsatz von Box 027 mit Version 2.4.62 belegt zwei vollstaendige normale
FexoBooth-Instanzen. Sie starteten im Abstand von sechs Sekunden. Die zweite
Instanz hielt die Logitech-C922-Webcam, waehrend die erste Instanz die Kamera
177-mal nicht oeffnen konnte. Ein Beenden-Klick in einer Instanz kann immer nur
diese eine Instanz beenden; die andere bleibt im Task-Manager und wirkt dann wie
eine Prozessleiche.

Der aktuelle Startpfad besitzt keine atomare Einzelinstanz-Sperre. Desktop-
Verknuepfung, Autostart, Installer und Updater koennen dieselbe EXE erneut
starten. Noch kritischer fuer DSLR: Jeder normale Start beginnt asynchron ein
namensweites Aufraeumen von `FexoNikonBridge.exe`. Eine versehentlich gestartete
zweite Hauptinstanz kann damit die aktive Bridge der ersten Instanz beenden.

Der seit 2.4.35 vorhandene Beenden-Wachhund schliesst ebenfalls nicht alle
Faelle:

1. Der Service-Dialog wird geloest und zerstoert, bevor der Wachhund aktiviert
   wird. Haengt Tk bereits dabei, existiert noch kein Schutz.
2. Der Wachhund ist nur ein Python-Thread im zu beendenden Prozess. Ein nativer
   Aufruf, der den Interpreter festhaelt, kann auch diesen Thread stilllegen.
3. Der vermeintlich harte Ausstieg versucht vor `os._exit()` nochmals Bridge-
   und Logging-Aufraeumen. Beide Wege koennen auf Locks warten und damit den
   letzten Ausstieg selbst blockieren.
4. Ein uebrig gebliebener Prozess darf nicht dazu fuehren, dass ein Kunde ohne
   Tastatur vom erneuten Start ausgesperrt ist.

## Ziele

1. Auf einer Box darf hoechstens eine normale FexoBooth-Oberflaeche gleichzeitig
   Kamera, UI und Bridge besitzen.
2. Ein zweiter Start bringt eine gesunde vorhandene Instanz nach vorn und endet,
   ohne Kamera oder Bridge anzufassen.
3. Eine noch startende erste Instanz erhaelt ausreichend Schonzeit und wird
   nicht wegen eines schnellen Doppelklicks beendet.
4. Eine nachweislich nicht reagierende oder im Beenden festhaengende Altinstanz
   wird nach begrenzter Wartezeit automatisch und ohne Tastatur beendet. Der
   angeforderte Start uebernimmt danach und zeigt die Fotobox-Oberflaeche.
5. Nach einem Beenden-Klick muss ein vom Hauptprozess unabhaengiger Wachhund die
   exakte Instanz spaetestens nach zehn Sekunden beenden koennen.
6. Webcam-, Canon- und Nikon-Aufnahmeverhalten bleiben unveraendert. Die
   Aenderung liegt ausschliesslich um Start, Prozessbesitz und Beenden.

## Nicht-Ziele

- Kein pauschales `taskkill /IM fexobooth.exe` und kein Abschiessen aller
  gleichnamigen Prozesse.
- Kein automatisches Beenden einer vorhandenen Instanz allein deshalb, weil ein
  zweiter Start erkannt wurde.
- Kein Umbau von Live-View, Capture, Bildverarbeitung oder Druck.
- Kein Wiederherstellen einer noch nicht abgeschlossenen Fotosession nach einem
  echten Prozess-Haenger. Bereits gespeicherte Einzelbilder und Prints bleiben
  unangetastet; nur der fluechtige Sitzungszustand geht beim Not-Neustart
  verloren.
- Keine Sperre fuer absichtliche Werkzeugprozesse wie `--kamera-test`,
  `--dslr-test`, Wiederherstellungsanzeige oder Beenden-Wachhund.

## Gepruefte Ansaetze

### A. Nur nach Prozessnamen suchen

Verworfen. Zwei nahezu gleichzeitige Starts koennen beide noch keinen anderen
Prozess sehen und danach beide fortfahren. Ausserdem wuerde eine Namenssuche
absichtliche Werkzeugprozesse mit einer Hauptinstanz verwechseln. Namensweites
Beenden koennte eine bereits neu gestartete gesunde Instanz treffen.

### B. Nur eine PID- oder Lockdatei verwenden

Verworfen. Eine Datei kann nach Stromverlust oder hartem Prozessende liegen
bleiben. PID-Wiederverwendung erfordert zusaetzliche Erkennung, und der
eigentliche Besitzwechsel bleibt ohne Betriebssystem-Sperre rennbehaftet.

### C. Windows-Mutex plus verifizierter Besitzer und externer Wachhund

Gewaehlt. Ein benannter Windows-Mutex entscheidet atomar, welche normale
Oberflaeche die Hauptinstanz ist. Windows schliesst das Mutex-Handle beim
Prozessende automatisch. Eine kleine Besitzerdatei liefert nur die fuer
Diagnose und Wiederherstellung benoetigten Daten; sie ist nicht selbst die
Sperre. Prozess-Handles und Erstellungszeit verhindern, dass eine
wiederverwendete PID oder ein fremder Prozess beendet wird.

Microsoft dokumentiert fuer `CreateMutexW` den atomaren
`ERROR_ALREADY_EXISTS`-Fall und das automatische Schliessen beim Prozessende.
Der Praefix `Global\\` stellt den Namen ueber Windows-Sitzungen hinweg bereit.
`OpenProcess`, `WaitForSingleObject` und im letzten Schritt `TerminateProcess`
arbeiten auf dem einmal geoeffneten konkreten Prozessobjekt statt erneut nach
einer moeglicherweise wiederverwendeten PID zu suchen.

## Architektur

### 1. Abgegrenztes Modul fuer Instanzbesitz

Ein neues Modul `src/utils/instance_guard.py` kapselt alle Windows-Aufrufe und
besitzt keine Abhaengigkeit zu Kamera, UI, Config oder dem normalen Logging.
Dadurch kann es vor dem Import der schweren Anwendungskomponenten laufen und
isoliert getestet werden.

Der normale UI-Prozess erstellt beziehungsweise oeffnet einen stabilen,
versionsunabhaengigen Mutex-Namen, sinngemaess:

```text
Global\FexoBooth.F3X0B00TH-2024-0001-0001-000000000001.MainUI
```

Das zurueckgegebene Handle bleibt fuer die gesamte Prozesslebensdauer in einem
Modulobjekt geoeffnet. `ERROR_ALREADY_EXISTS` bedeutet nicht automatisch
"Leiche", sondern nur "ein Besitzer oder ein gerade startender Besitzer
existiert".

Nach erfolgreichem Erstbesitz schreibt der Prozess atomar eine kleine Datei
unter `C:\ProgramData\FexoBox`, beispielsweise
`fexobooth-main-instance.json`. Sie enthaelt mindestens:

- Schema-Version,
- PID,
- Windows-Prozesserstellungszeit,
- kanonischen EXE-Pfad,
- zufaelliges Start-Token,
- Startzeit,
- Zustand `starting`, `running` oder `shutdown_requested`.

Die Datei darf veraltet sein; der Mutex bleibt die Wahrheit. PID,
Erstellungszeit und EXE-Pfad muessen vor jedem harten Eingriff gegen ein bereits
geoeffnetes Windows-Prozess-Handle geprueft werden. Zusaetzlich stehen die
Windows-Session-ID und eine absolute Beenden-Frist in der Datei.

#### Exakter Mutex-Vertrag

Der erste Versuch verwendet `CreateMutexW(..., bInitialOwner=True, ...)`:

- Neuer Mutex ohne `ERROR_ALREADY_EXISTS`: Der aufrufende Hauptthread besitzt
  ihn und publiziert sofort `starting`.
- Bestehender Mutex mit `ERROR_ALREADY_EXISTS`: Das zurueckgegebene Handle
  bedeutet ausdruecklich **keinen** Besitz. Der Kandidat darf weder Metadaten
  schreiben noch Kamera oder UI starten.
- Ein Kandidat, der nur eine gesunde Instanz nach vorn holt, schliesst sein
  Handle ohne `ReleaseMutex`.
- Ein Kandidat, der auf die Altinstanz wartet, benutzt
  `WaitForSingleObject`. Sowohl `WAIT_OBJECT_0` als auch `WAIT_ABANDONED`
  uebertragen ihm den Besitz; `WAIT_TIMEOUT` nicht. Auf das Verschwinden des
  benannten Objekts wird nie gewartet, weil offene Handles wartender Prozesse
  das Objekt erhalten koennen.
- Der Besitzer gibt den Mutex waehrend des normalen Betriebs niemals vorzeitig
  frei. Bei einem kontrollierten Startabbruch vor Kamera/UI ruft derselbe
  Hauptthread `ReleaseMutex` und `CloseHandle`; beim normalen oder harten
  Prozessende schliesst Windows das Handle. Ein nach Prozessende gemeldetes
  `WAIT_ABANDONED` ist deshalb ein erwarteter, zu protokollierender
  Besitzwechsel.

Mehrere gleichzeitig gestartete Wiederhersteller werden mit einem zweiten,
kurzlebigen benannten Recovery-Mutex serialisiert. Nur dessen Besitzer darf
eine Altinstanz beenden. Alle anderen Kandidaten warten ausschliesslich auf den
Main-UI-Mutex und bewerten danach den inzwischen neu publizierten Besitzer.
Vor jedem harten Eingriff validiert der Recovery-Besitzer Prozess-Handle,
Erstellungszeit, EXE-Pfad, Session und Start-Token erneut.

#### Verbindliche Besitzer-Zustaende

`starting` wird vor dem Import von `PhotoboothApp` atomar publiziert. Scheitert
bereits dieses erste Publishing, wird der Mutex kontrolliert freigegeben und
der Prozess endet fail-closed, bevor Kamera oder UI importiert werden.

Der Uebergang zu `running` geschieht erst aus einem mit `root.after(0, ...)`
geplanten Callback, nachdem Tk seine Hauptschleife tatsaechlich verarbeitet.
Scheitert dieses Update, leitet die App den abgesicherten Exit ein; sie darf
nicht dauerhaft mit unzuverlaessigen Besitzdaten weiterlaufen.

`shutdown_requested` enthaelt Grund und die gemeinsame absolute Wachhundfrist.
Ein Prozess im Zustand `running`, der nach Ablauf der unten definierten
Schonfrist kein auffindbares Fenster mehr besitzt, ist ein eigener
Recovery-Fall und wird nicht mit einem jungen `starting`-Prozess verwechselt.

### 2. Reihenfolge im Hauptstart

`src/main.py` behandelt die Modi in dieser Reihenfolge:

1. Interner `--shutdown-watchdog`-Modus.
2. Interner Wiederherstellungsanzeige-Modus, sofern fuer die sichtbare
   Warteanzeige benoetigt.
3. Bestehende bewusste Werkzeuge `--kamera-test` und `--dslr-test`.
4. Erst danach Einzelinstanz-Pruefung fuer die normale Hauptoberflaeche.
5. Erst nach sicherem Besitz: Taskleisten-Recovery, Config, normales Logging,
   Waisenbereinigung, `PhotoboothApp` und Kamera.

Der bisherige Top-Level-Import von `PhotoboothApp` wird in den normalen
UI-Zweig verschoben. Abgewiesene oder als Wachhund gestartete Prozesse laden
dadurch weder CustomTkinter noch Kamera-SDKs.

Das Bridge-Waisenaufraeumen darf erst nach erfolgreichem Hauptinstanz-Besitz
laufen. Es darf nicht mehr als langsamer Hintergrund-`taskkill` spaeter mit
einer inzwischen frisch gestarteten Bridge kollidieren. Eine Bridge gilt nur
dann als verwaist, wenn ihr aufgezeichneter Parent-Prozess nach Pruefung von PID
und Prozesserstellungszeiten nicht mehr lebt. Eine Bridge eines lebenden
`--kamera-test`-, `--dslr-test`- oder anderen erlaubten Werkzeugprozesses bleibt
unangetastet. Vor der ersten Kamera-Initialisierung wird die Beendigung echter
Waisen synchron bestaetigt.

Jeder Prozess, der eine `FexoNikonBridge.exe` startet, legt sie unmittelbar
nach `Popen` in ein eigenes Windows-Jobobjekt mit
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. Das Job-Handle bleibt ausschliesslich im
startenden Haupt- beziehungsweise Werkzeugprozess. Die internen Watchdog- und
Recovery-Helfer werden diesem Bridge-Job nie zugeordnet. Endet der Besitzer
normal, per `os._exit()` oder per `TerminateProcess`, schliesst Windows dessen
letztes Job-Handle und beendet die Bridge automatisch. Kann die frisch
gestartete Bridge nicht sicher dem Job zugeordnet werden, wird sie sofort
beendet und Nikon gilt als nicht initialisiert; eine ungebundene Bridge darf
nicht in Betrieb gehen. Das verifizierte Startup-Waisenaufraeumen bleibt nur
als Kompatibilitaetsnetz fuer Altversionen und fehlgeschlagene fruehere Laeufe.

### 3. Verhalten bei einem zweiten normalen Start

Der zweite Prozess fasst zu keinem Zeitpunkt Taskleiste, Kamera, Bridge oder
App-Konfiguration an. Er prueft ausschliesslich den bestehenden Besitzer.

#### Gesunder Besitzer

Der Besitzer-PID wird aus der Metadatei gelesen und gegen Prozess-Handle,
Erstellungszeit und EXE-Pfad geprueft. Seine sichtbaren Top-Level-Fenster werden
per PID ermittelt. Ein `WM_NULL` mit `SendMessageTimeoutW` und echtem Timeout
prueft, ob der UI-Thread Windows-Nachrichten verarbeitet.

Antwortet mindestens ein passendes Fenster, wird es wiederhergestellt und in
den Vordergrund geholt. Der zweite Prozess protokolliert den Vorgang in einem
kleinen Start-/Recovery-Log und beendet sich mit Erfolg. Er startet keine
zweite Oberflaeche.

#### Besitzer startet noch

Jeder verifizierte Besitzer im Zustand `starting` erhaelt unabhaengig davon, ob
Windows bereits ein Tk-Fenster findet, die volle Startschonzeit. Tk erzeugt das
Fenster vor `mainloop()`; dessen blosse Existenz beweist daher noch keine
laufende Nachrichtenverarbeitung. Der zweite Prozess wartet in kurzen
Intervallen und prueft erneut. Ein Doppelklick wie auf Box 027 darf den sechs
Sekunden aelteren ersten Start niemals beenden. Die gesamte Schonzeit wird
anhand echter Box-Startzeiten so gewaehlt, dass auch PyInstaller, Nikon-
Initialisierung und das langsame Miix-Tablet abgedeckt sind. Der
Produktionswert betraegt zunaechst 60 Sekunden und darf erst nach Feldmessungen
reduziert werden.

#### Besitzer wird gerade beendet

Steht die Metadatei auf `shutdown_requested`, wartet der zweite Start auf das
Signal des bereits geoeffneten Prozess-Handles und auf das Freigeben des
Mutex. Nach hoechstens zehn Sekunden sorgt der externe Wachhund fuer das Ende.
Der wartende Start versucht danach selbst atomar den Mutex zu erwerben und
faehrt als neue Hauptinstanz fort.

#### Besitzer reagiert nicht

Ein einzelner langsamer UI-Takt reicht nicht fuer eine Zwangsbeendigung. Beim
Nikon-Kaltstart koennen Bridge-Ping, Kamera-Init, Live-View-Start und erste
Frame-Wartezeit nacheinander rund 49 Sekunden beanspruchen; auch dieser
zusammengesetzte legitime Pfad darf keinen Auto-Kill ausloesen. Bei `running`
folgen deshalb nach dem ersten fehlgeschlagenen Ping mehrere Pruefungen ueber
insgesamt mindestens 90 Sekunden. Das enthaelt deutliche Reserve ueber den
dokumentierten Kamera-Fristen und den auf Box 027 gemessenen normalen UI-
Hitches von rund zwei Sekunden. Gleiches gilt fuer einen aelteren `running`-
Besitzer ohne auffindbares Fenster.

Die Zehn-Sekunden-Frist gilt nur fuer einen ausdruecklich angeforderten Exit im
Zustand `shutdown_requested`, nicht fuer die Diagnose eines unbekannten
UI-Stillstands. Kamera-Initialisierung und Capture erhalten eigene Tests, die
waehrend ihrer maximal erlaubten Laufzeit einen zweiten Start simulieren und
beweisen, dass die aktive Instanz nicht beendet wird.

Bleiben Fenster und UI waehrend der gesamten Frist nicht ansprechbar, startet
der neue Prozess eine schlichte, tastaturfreie Anzeige:

```text
FexoBooth wird wiederhergestellt …
Bitte kurz warten.
```

Die Anzeige laeuft in einem isolierten Hilfsprozess und besitzt eine harte
Eigenlaufzeitgrenze. Der Recovery-Koordinator behaelt ihr Prozess-Handle und
uebergibt ein zufaellig benanntes Close-Event. Bei erfolgreicher eigener
Besitzuebernahme, beim Gewinn eines anderen wartenden Kandidaten, bei Fehler
oder Abbruch signalisiert er das Event und wartet kurz auf das Anzeigenende;
notfalls beendet er nur diesen eigenen Anzeigeprozess. Ihr Ausfall darf die
Wiederherstellung nicht verhindern, und keine Anzeige darf nach einer
abgeschlossenen Uebernahme vor der neuen App stehen bleiben.

Anschliessend wird nur das bereits verifizierte alte Prozess-Handle beendet.
Der Hauptprozess wird zuerst beendet, damit er garantiert keine neue Bridge
mehr starten kann. Danach werden direkte `FexoNikonBridge.exe`-Kinder dieses
Besitzers anhand von Parent-PID, EXE-Pfad und Prozesszeiten ermittelt und genau
diese Kind-Handles beendet. Erst danach wartet der Recovery-Besitzer auf den
Main-UI-Mutex. Der Kandidat, der ihn mit `WAIT_OBJECT_0` oder
`WAIT_ABANDONED` erhaelt, fuehrt vor jeder Kamera-Initialisierung zusaetzlich
die verifizierte synchrone Waisenpruefung aus. Es gibt kein Zeitfenster mit zwei
Kamera-Eigentuemern.

Kann der alte Besitzer nicht eindeutig verifiziert oder mangels Windows-Recht
nicht beendet werden, wird fail-closed gehandelt: keine zweite Kamera-App.
Stattdessen erscheint ein oberstes, per Touch bedienbares Fenster mit
`Box neu starten` und `Abbrechen`. Auch ein Besitzer aus einer anderen
Windows-Session wird niemals per Fenster-Ping als vermeintlich haengend
eingestuft: Die Session-ID-Pruefung fuehrt in denselben fail-closed
Touch-Dialog. Damit bleibt der Mutex bewusst `Global\\`, ohne vorzugeben, ein
Fenster ueber Sitzungsgrenzen hinweg nach vorn holen zu koennen. Ein unbekannter
oder fremdsitzender Prozess wird niemals auf Verdacht beendet.

### 4. Externer Beenden-Wachhund

Beim expliziten Beenden wird zuerst eine absolute Frist von zehn Sekunden ab
dem Benutzerklick mit dem sitzungsuebergreifenden `GetTickCount64` berechnet.
Der Instanzzustand wird atomar auf `shutdown_requested` gesetzt und danach ein
unabhaengiger Hilfsprozess gestartet. Dies geschieht vor `grab_release()`,
Dialog-`destroy()`, Kamera-Freigabe, Bridge-Kommandos und Logging-Shutdown.

Der Hilfsprozess erhaelt PID, Prozesserstellungszeit, EXE-Pfad, Start-Token,
absolute Frist und den Namen eines zufaelligen Windows-Ready-Events. Er oeffnet
sofort ein konkretes Windows-Prozess-Handle mit den minimal erforderlichen
Rechten, verifiziert dessen Identitaet und signalisiert **erst danach** das
Ready-Event. Der Elternprozess wartet vor jedem weiteren Beenden-Schritt
begrenzt auf diese Bestaetigung.

Schlagen Prozessstart, Argumentpruefung, `OpenProcess`, Identitaetspruefung oder
Ready-Handschlag fehl, beginnt der Elternprozess kein moeglicherweise
blockierendes Aufraeumen mehr, sondern ruft unmittelbar `os._exit(0)` auf.
Windows gibt damit Hauptprozess und Kamera-Handles frei; das verpflichtende
Bridge-Jobobjekt beendet gleichzeitig jede Bridge dieses Prozesses. Das
Startup-Waisennetz bleibt nur fuer Altversionen. So ist auch der Fehlerfall
fuer einen Kunden ohne Task-Manager endlich.

Nach dem Ready-Signal wartet der Hilfsprozess nur noch die **verbleibende** Zeit
bis zur bereits beim Klick berechneten Frist. Seine eigene PyInstaller-
Startzeit verlaengert die zehn Sekunden nicht.

- Endet FexoBooth normal, schliesst der Wachhund sein Handle und beendet sich.
- Lebt exakt dieses Prozessobjekt an der absoluten Frist noch, schreibt der
  Wachhund eine rohe, vom Hauptlogging unabhaengige Diagnosezeile, ruft zuerst
  `TerminateProcess` auf dem bereits geoeffneten Hauptprozess-Handle auf und
  beendet nach dessen Signal nur die anschliessend verifizierten Bridge-Kinder.
- Der Zwangspfad versucht vor `TerminateProcess` weder Python-Logging-Shutdown
  noch Kamera- oder Bridge-Kommandos. Damit kann er nicht an denselben
  Python-Locks wie die Altinstanz haengen.

Der bestehende interne Thread darf als zusaetzliche schnelle Absicherung
bleiben, ist aber nicht mehr die letzte Garantie. Sein eigener harter Pfad darf
vor `os._exit()` keine blockierenden Aufraeumarbeiten mehr ausfuehren.

Alle Beenden-Einstiege rufen dieselbe idempotente Vorbereitungsfunktion auf.
Insbesondere aktiviert der Service-Menue-Knopf den externen Wachhund, bevor er
den modalen Admin-Dialog anfasst. Mehrere Klicks duerfen nur einen Wachhund
erzeugen.

### 5. Verbindliche Lifecycle-Matrix

| Einstieg | Vertrag |
|---|---|
| Service-Menue `App beenden` | Externen Wachhund mit Ready-Handschlag als allererste Aktion sichern; danach Modal loesen und zentral aufraeumen. |
| Ctrl+Shift+Q und `quit()` | Direkt durch denselben idempotenten zentralen Weg. |
| `WM_DELETE_WINDOW` der Hauptoberflaeche | Auf denselben zentralen Weg binden; kein nacktes Tk-`destroy()`. |
| Normales Ende von `mainloop()` ohne vorherigen Request | Vor finalem Bridge-/Logging-Aufraeumen externen Wachhund bestaetigt aktivieren. |
| Exception bei Startup oder Mainloop | Crashbericht roh schreiben, externen Wachhund bestaetigen und dann begrenzt aufraeumen; bei fehlender Bestaetigung sofort `os._exit(1)` statt `sys.exit(1)`. |
| App-OTA und Update-Dialog | Wachhund vor BAT-Start beziehungsweise spaetestens vor Logging-Shutdown bestaetigen; danach der bestehende harte Update-Exit. Der Wachhund trifft nur Hauptprozess und seine Bridge, nie das Update-BAT. |
| `--kamera-test` / `--dslr-test` | Kein Main-UI-Mutex. Ihr bereits direkter Prozess-Exit bleibt ein eigener Werkzeugvertrag; sie duerfen nicht vom normalen Waisen-Cleanup getroffen werden. |
| Interne Wachhund-/Recovery-Helfer | Kein Main-UI-Mutex, keine Kameraimporte, direktes begrenztes Prozessende. |

Damit ist der bisherige `sys.exit(1)`-Sonderweg entfernt. Kein Lifecycle-Pfad
darf sich darauf verlassen, dass non-daemon Threads von selbst verschwinden.

### 6. Sichtbare und dauerhafte Diagnose

Jeder normale Hauptprozess loggt PID, Start-Token und Instanzzustand. Relevante
Marker sind sinngemaess:

```text
INSTANCE ACQUIRED pid=... token=...
INSTANCE DUPLICATE owner_pid=... state=running
INSTANCE FOREGROUND owner_pid=...
INSTANCE WAIT owner_pid=... reason=starting|shutdown_requested
INSTANCE RECOVERY owner_pid=... reason=unresponsive
INSTANCE RECOVERY COMPLETE new_pid=...
SHUTDOWN REQUESTED pid=... reason=...
SHUTDOWN WATCHDOG ARMED pid=... timeout_s=10
SHUTDOWN WATCHDOG FORCED pid=...
```

Da der normale Logger bei einem Haenger selbst blockiert sein kann, schreiben
Startschutz und externer Wachhund zusaetzlich in eine kleine begrenzte Datei
`instance-recovery.log`. Es werden keine Zugangsdaten oder Bilddaten
geschrieben.

## Fehler- und Sicherheitsvertrag

- Ein Fehler beim Erzeugen oder Oeffnen des globalen Mutex fuehrt zu einem
  klaren Startfehler, nicht zu zwei Instanzen.
- Eine fehlende Besitzerdatei bei vorhandenem Mutex fuehrt zunaechst zu
  Wiederholungen innerhalb der Startschonzeit. Ohne eindeutige Identitaet wird
  nicht beendet.
- PID allein ist niemals ausreichender Beweis. Prozess-Handle,
  Erstellungszeit und EXE-Pfad muessen zusammenpassen.
- Nach `TerminateProcess` wird auf das signalisierte Prozess-Handle und die
  erfolgreiche Main-UI-Mutex-Besitzuebernahme gewartet, bevor irgendeine
  Kamera initialisiert wird.
- Ein gesunder vorhandener Prozess wird nicht beendet, sondern nach vorn
  geholt.
- Ein Wiederherstellungs-Hilfsprozess erhaelt niemals den Main-UI-Mutex und
  importiert keine Kamera-Komponenten.
- Nur der normale Hauptprozess darf das Besitzer-Metadokument auf `running`
  setzen.
- Ein harter Exit beendet keine Kindprozesse automatisch. Der Hauptprozess wird
  deshalb nicht als alleinige Bridge-Garantie verwendet: Jede neue Bridge ist
  verpflichtend an das Kill-on-close-Jobobjekt ihres Besitzers gebunden.
  Verifizierte Waisen alter Versionen werden beim naechsten Besitzwechsel
  synchron vor der Kamera entfernt.
- Ein Prozess aus einer anderen Windows-Session wird weder gepingt noch
  beendet. Die Touch-Oberflaeche bietet stattdessen einen kontrollierten
  Box-Neustart an.

## Automatisierte Tests

Die Windows-Schicht wird hinter einer kleinen, injizierbaren Schnittstelle
gekapselt. Tests verwenden einen Fake-Backend und duerfen weder echte Prozesse
noch die Entwicklerkamera beenden.

Mindestens folgende Faelle werden dauerhaft abgedeckt:

1. Zwei gleichzeitige normale Starts erhalten atomar genau einen Besitzer.
2. Ein zweiter Start importiert beziehungsweise initialisiert weder UI noch
   Kamera und startet kein Bridge-Aufraeumen.
3. `--kamera-test`, `--dslr-test`, Wachhund und Recovery-Anzeige umgehen nur
   den Main-UI-Mutex wie vorgesehen.
4. Ein gesunder Besitzer wird nach vorn geholt und niemals beendet.
5. Ein sechs Sekunden alter `starting`-Besitzer wird mit und ohne bereits
   erzeugtem Tk-Fenster nicht beendet; gleiches gilt waehrend der vollen
   60-Sekunden-Startschonzeit.
6. Ein kurzfristig langsames Fenster sowie der zusammengesetzte simulierte
   Nikon-Kaltstart, Canon-/Nikon-Initialisierung und Capture erholen sich
   innerhalb der 90-Sekunden-Frist und werden nicht beendet.
7. Ein ueber die gesamte Frist nicht reagierender, vollstaendig verifizierter
   Besitzer wird exakt einmal beendet; danach wird der Mutex uebernommen.
8. PID-Wiederverwendung, anderer EXE-Pfad, andere Erstellungszeit und fehlende
   Rechte blockieren die Zwangsbeendigung.
9. `shutdown_requested` wartet auf das normale Ende und uebernimmt danach.
10. Der Service-Menue-Pfad aktiviert den externen Wachhund vor jedem
    Tk-`destroy()`.
11. Ein sauber endender Hauptprozess wird vom externen Wachhund nicht beendet.
12. Ein nach zehn Sekunden lebender exakter Prozess wird auch dann beendet,
    wenn Hauptlogging, Kamera-Freigabe oder Python-Threads haengen.
13. Nur verifizierte Bridge-Kinder des Zielprozesses werden beendet.
14. Mehrere Beenden-Aufrufe starten nur einen externen und einen internen
    Wachhund.
15. Der kritische Fehlerpfad in `main.py` endet ebenfalls garantiert und kann
    nicht mehr an non-daemon Threads stehen bleiben.
16. Bestehende Kamera-, Session- und DSLR-Regressionssuiten bleiben gruen;
    `src/camera/webcam.py`, Canon- und Nikon-Capturepfade erhalten keinen
    semantischen Diff.
17. Echte konkurrierende Windows-Testprozesse beweisen `WAIT_OBJECT_0`,
    `WAIT_ABANDONED`, genau einen Gewinner und mehrere passive Wiederhersteller.
18. Ein lebender erlaubter Werkzeugprozess mit eigener Bridge bleibt beim Start
    einer normalen UI unangetastet.
19. Ein alter `running`-Besitzer ohne Fenster wird nach der Produktionsfrist
    wiederhergestellt; ein Publishing-Fehler startet keine Kamera.
20. Fehlender Watchdog-Ready-Handschlag fuehrt vor jedem Tk-/Kamera-Schritt zum
    unmittelbaren Exit.
21. Ein fremdsitzender Besitzer wird fail-closed behandelt und erhaelt nur den
    Touch-Neustartweg.
22. Jede gestartete Nikon-Bridge wird erfolgreich einem Besitzer-Jobobjekt
    zugeordnet oder sofort beendet; `os._exit()` und `TerminateProcess` des
    Besitzers lassen keine Bridge zurueck.
23. Bei mehreren wartenden Kandidaten wird jede gestartete Recovery-Anzeige
    unmittelbar geschlossen, auch wenn ein anderer Kandidat den Main-Mutex
    gewinnt.

Zusaetzlich zu den Fake-Backend-Tests laufen Windows-only Integrationstests mit
eindeutig benannten Wegwerf-Mutexen und ausschliesslich selbst gestarteten
Dummy-Prozessen. Sie pruefen reale Handle-Signalisierung, Abandonment,
gleichzeitige Starts, Ready-Event, sauberes Ende und `TerminateProcess`. Die
Tests verwenden nie den Produktions-Mutex, fremde PIDs oder eine Kamera.

## Hardware-Abnahme

### Webcam-Box

1. Box neu starten und pruefen: genau eine normale `fexobooth.exe`.
2. Desktop-Symbol innerhalb von sechs Sekunden zweimal antippen. Erwartung:
   eine Hauptinstanz, eine Kamera-Initialisierung und keine Kamera-belegt-
   Warnung.
3. Bei laufender gesunder App das Symbol erneut antippen. Erwartung: vorhandene
   App kommt nach vorn; kein zweiter Start.
4. Eine vollstaendige Fotosession aufnehmen und danach ueber PIN 3198 beenden.
   Nach spaetestens zehn Sekunden darf keine normale `fexobooth.exe` mehr
   laufen.
5. Nach einem mehrstuendigen Stresslauf denselben Beenden-Test wiederholen.

### DSLR-Box

1. Vor dem Test genau eine Hauptinstanz und hoechstens ihre eine Bridge
   bestaetigen.
2. Mehrfachstart provozieren. Erwartung: keine zweite Hauptinstanz, kein
   Bridge-Kill und unveraenderter Live-View der ersten Instanz.
3. Eine komplette Canon- beziehungsweise Nikon-Session aufnehmen.
4. Ueber PIN 3198 beenden. Hauptinstanz und zugehoerige Bridge muessen nach
   spaetestens zehn Sekunden verschwunden sein.
5. Direkt ueber das Desktop-Symbol neu starten. Die Kamera muss ohne Task-
   Manager, Tastatur oder Box-Neustart wieder erkannt werden.

### Erzwungene Wiederherstellung

In einem kontrollierten Dev-Test wird eine Testinstanz so angehalten, dass sie
ihren Mutex behaelt und auf Fenster-Pings nicht antwortet. Ein Antippen des
Desktop-Symbols muss die Wiederherstellungsanzeige zeigen, nur diese Test-PID
beenden, den Mutex uebernehmen und die App einmal neu starten. Eine gesunde
Vergleichs-PID mit aehnlichem Namen darf unangetastet bleiben.

## Dokumentation und Rollout

- Version auf 2.4.63 erhoehen.
- `CHANGELOG.md`, `FORTSCHRITT.md`, `ERKENNTNISSE.md` und den offenen
  Hardware-Nachtest aktualisieren.
- Im Dev-Log alle Instanz- und Wachhundmarker aktivieren; die knappen
  sicherheitsrelevanten Marker bleiben auch ausserhalb des Dev-Modus in
  `instance-recovery.log` erhalten.
- Zuerst Webcam-Box testen, danach mindestens eine DSLR-Box. Die Aenderung wird
  erst nach beiden Mehrfachstart-/Beenden-Nachweisen fuer die Flotte
  freigegeben.

## Primaerquellen fuer die Windows-Vertraege

- Microsoft: `CreateMutexW` und `ERROR_ALREADY_EXISTS`
  https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createmutexw
- Microsoft: globale und sitzungsbezogene Kernelobjekt-Namensraeume
  https://learn.microsoft.com/en-us/windows/win32/termserv/kernel-object-namespaces
- Microsoft: `SendMessageTimeoutW` mit `SMTO_ABORTIFHUNG`
  https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendmessagetimeoutw
- Microsoft: `OpenProcess` und Prozess-Handles
  https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess
- Microsoft: `WaitForSingleObject`
  https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject
- Microsoft: Prozessende und getrennt weiterlebende Kindprozesse
  https://learn.microsoft.com/en-us/windows/win32/procthread/terminating-a-process
