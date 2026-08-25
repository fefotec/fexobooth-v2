# DSLR-Baustelle — Stand und Übergabe

> **Zweck dieser Datei:** Vollständige Übergabe an die nächste Sitzung.
> Stand: **25.08.2026, Version 2.4.60**. Testgerät: **Box 245**, Canon EOS 2000D,
> Surface-Tablet.
>
> **Wer hier neu einsteigt, liest zuerst „Die wichtigste Regel" und
> „Wo wir stehen".**

---

## Die wichtigste Regel

> **Die DSLR-Boxen haben in der Regel KEINE Speicherkarte in der Kamera.**
> Christian am 24.08.2026: *„du musst kapieren das die geräte in der regel gar
> keine karte drin haben!! merk dir das!"*

Daraus folgt zwingend:

- Der **Direktweg** (`SaveTo = Host`, Bild kommt über den Rückkanal in den
  Rechner) ist der **einzige Weg, der in der Flotte funktioniert**.
- Ein Rückfall auf den Kartenweg (Directory-Polling) ist **keine Lösung**, auch
  wenn er auf der Testbox funktioniert — nur die hatte zeitweise eine Karte.
- Diese Ausnahme hat die Fehlersuche **mehrfach in die falsche Richtung
  geschickt**. Nicht noch einmal darauf hereinfallen.

Zweite Regel, ebenso wichtig:

> **Der Autofokus muss aktiv bleiben** (Gäste stehen unterschiedlich weit weg),
> **es gibt keinen Blitz** (die Kamera muss bei dunkler werdender Location selbst
> nachregeln), und **Kunden dürfen an der Kamera nichts einstellen müssen**.
> Deshalb steht das Wahlrad auf **P** bzw. „Auto ohne Blitz" — das ist eine
> bewusste Entscheidung, kein Fehler.

---

## Wo wir stehen

### Was die bisherigen Hardware-Logs nachweisen

| | Nachweis |
|---|---|
| Kamera wird erkannt und verbunden | Box-Log: `Session erfolgreich geöffnet` |
| Kamera löst aus | Christian hört den Spiegel; Bildzähler auf der Karte steigt |
| Rückkanal feuert grundsätzlich | Box-Log: `>>> OBJECT EVENT: DirItemRequestTransfer_Alt` |
| Kamera meldet Dateiname + Größe | Box-Log: `IMG_0001.JPG (820393 bytes)` |
| 2.4.59-Host-Transfer funktioniert | Sieben echte JPEGs mit 6000 x 4000 Pixeln in Folge |
| Owner/Event/Download sind hardwaretauglich | Keine Owner-Timeouts, Thread-Verstösse oder Downloadfehler im erfolgreichen Lauf |
| Ein Kaltstart-Restfehler besteht | Erster Versuch: `TAKE_PICTURE_CARD_NG (0x8d07)`, danach funktionierte es |
| Log-Versand ins Dashboard | Läuft, siehe „Werkzeuge" |

### Aktueller Reparaturstand

**2.4.59 hat den Canon-Grundweg auf Hardware bestaetigt:** Der erste Capture
nach dem Kaltstart schlug noch mit `CARD_NG` fehl und wurde als
1056-x-704-Live-View-Notbild geliefert. Danach kamen sieben echte JPEGs mit
6000 x 4000 Pixeln sauber zum Tablet. Damit sind diese Teile belegt:

- genau ein STA-Owner `edsdk-kamera` für alle EDSDK-Aufrufe,
- installierter PyInstaller-Build findet `EDSDK.dll` und `EdsImage.dll` zuerst
  unter `sys._MEIPASS` (`_internal`) und hält den DLL-Suchpfad offen,
- Object- und State-Handler vor `OpenSession`, mit offiziellen Eventwerten,
- nativer Callback reiht nur einen priorisierten Auftrag ein; Download erst
  nach seiner Rückkehr,
- `SaveTo=Host` ist immer der Produktionsweg, keine SD-Karte erforderlich,
- kein Event-Polling mehr aus Tk-/Capture-/LiveView-Threads,
- kein zweites DSLR-Foto mehr über den generischen Webcam-Fallback,
- Capture-Queue ist pro Aufnahme scharfgeschaltet; verspätete Events der
  vorigen Aufnahme werden abgelehnt statt dem nächsten Foto zugeschlagen,
- exakt ein Capture-Befehl; AF- und Shutter-OFF-Fehler bleiben im Log sichtbar,
- `Cancel + Release` bei Downloadfehlern,
- Karten-Baseline vor statt nach dem Auslösen,
- korrekte JPEG-Qualitäts- und Event-Konstanten aus `EDSDKTypes.h`,
- korreliertes Dev-Logging für Owner, Capture, Event und Download.

**2.4.60 beseitigt jetzt gezielt die verbliebenen Canon-Maengel:**

- Host-Speicher nach `OpenSession` atomar scharfstellen: `SaveTo=Host`,
  `UILock`, Capacity genau einmal, garantiertes `UIUnlock` und begrenztes
  Readback von `SaveTo`/`AvailableShots`,
- kein Capacity-Reset mehr unmittelbar vor jedem Foto,
- ohne bestaetigtes Host-Ready-Flag kein Shutter; bei `CARD_NG` kein
  automatischer zweiter Versuch,
- kein schwarzer Balken `Foto wird aufgenommen ...` mehr bei Canon; Nikon
  behaelt ihn,
- Canon-JPEG direkt im PIL-Pfad statt PIL-NumPy-OpenCV-PIL-Rundreise,
- korrigierte Canon-Namen fuer AE/Weissabgleich und bessere
  Belichtungs-/EXIF-/Helligkeitsdiagnose im Dev-Modus.

Die auffaellige Belichtung im 2.4.59-Test war eine verstellte
Belichtungskorrektur an der Kamera und ist dort behoben. FexoBooth setzt keine
Belichtungswerte automatisch.

> **2.4.60 ist der freigegebene Nachbesserungsstand; der Hardware-Retest ist
> noch offen.** Zuerst muss direkt das erste Foto nach einem Kamera-Kaltstart
> funktionieren. Der anschliessende Flottennachweis erfolgt ohne SD-Karte.

---

## Die Fehlerkette — was tatsächlich kaputt war

Wichtig zum Verständnis: Es waren **mehrere unabhängige Fehler übereinander**.
Jeder erklärte den Ausfall vollständig, keiner allein behob ihn. Dazu wich der
Code beim Scheitern des einen Weges automatisch auf den anderen aus und
verdeckte damit, dass es mehrere Fehler waren.

| Version | Ursache | Status |
|---|---|---|
| 2.4.46 | Endlosschleife: `start_live_view` blockierte 1,5 s pro Aufruf, 1.611× in 29 Min → Windows schoss die App ab | behoben |
| 2.4.46 | Doppelbilder: `get_frame()` gab bei toter Kamera stillschweigend ein Altbild zurück | behoben |
| 2.4.46 | Wiederherstellung griff nur bei Fehlercode `0x301`, der nie auftrat | behoben |
| 2.4.46 | **EDSDK-Fehlertabelle war falsch** — `0x81` hieß nicht INVALID_PARAMETER sondern DEVICE_BUSY, `0xc1` = COMM_DISCONNECTED | behoben |
| 2.4.48 | **`EdsDirectoryItemInfo.size` als 32 statt 64 Bit** → alle Felder um 4 Byte verschoben → Speicherkarte wurde nie erkannt | behoben |
| 2.4.55 | **`EdsCreateMemoryStream`, `EdsDownload`, `EdsGetLength` als 32 statt 64 Bit** → Download scheiterte mit INTERNAL_ERROR | behoben |
| 2.4.57 | **EDSDK wurde aus mehreren Programmfäden benutzt** → erster Owner-Versuch deckte nur Initialisierung/Liste/OpenSession ab | Teilfix, nicht behoben |
| 2.4.58 | **Aufrufstelle von `EdsGetLength` im Live-View übersehen** → kein Vorschaubild | behoben, mit 2.4.59 hardwarebestaetigt |
| 2.4.59 | Webcam-Optimierung `841de6c` verschob Canon-Capture/Handler auf Fremdthreads; falsche Event-/JPEG-Konstanten; Download reentrant im Callback | behoben, sieben echte Hardware-JPEGs |
| 2.4.59 | **Build legte Canon-DLLs nur unter `_internal` ab, Loader suchte dort nicht** → installierte EXE konnte Canon verlieren, obwohl der Quellbaum funktionierte | behoben, eigener Build-Pfad-Test |
| 2.4.60 | Erster Kaltstart-Shutter kam trotz gesetztem Host-Ziel zu frueh (`CARD_NG`); schwarzer Canon-Wartebalken und unnoetige Farb-Rundreise | im Code behoben, **Hardware-Retest offen** |

### Der rote Faden

**Fünf von acht Ursachen waren derselbe Fehlertyp:** ein 64-Bit-Wert der
Canon-Schnittstelle, der im Python-Code als 32 Bit stand. Vier Fundstellen
kosteten je eine Testrunde auf der echten Box, die fünfte entstand beim Beheben
der vierten.

**Deshalb gibt es jetzt `tests/test_edsdk_typen.py`.** Er findet diese ganze
Familie in Sekunden, ohne Kamera.

---

## Werkzeuge

### 1. Komplette DSLR-Tests — vor jedem Build ausführen

```
python tests/alle_tests.py
```

Prüft ohne Kamera unter anderem:

1. Signaturen und Konstanten gegen die Canon-Header,
2. alle EDSDK-Aufrufe auf demselben Owner-Thread,
3. Callback-Queue statt reentrantem Download,
4. `Cancel + Release` bei Downloadfehlern,
5. Host-Transfer ohne Karte und genau eine Auslösung,
6. keine rohe DLL-Nutzung außerhalb des Wrappers,
7. Dev-Mode-Diagnosemarker und Canon-spezifischen UI-Guard,
8. PyInstaller-`_internal`, Parallelstart, Timeout-Races und atomaren Cleanup,
9. komplette Fake-Kette `0x208 → Download → Queue → 6000×4000-JPEG`.

Gegenprobe ist gemacht: Baut man den Typfehler von 2.4.58 künstlich wieder ein,
meldet der Test ihn mit Zeilennummer und gibt Rückgabewert 1.

> Der Canon-Header liegt im Repo unter
> `EDSDK/EDSDKv132010W/.../Header/EDSDK.h` und ist die **Wahrheitsquelle**.
> Niemals aus dem Gedächtnis oder aus einem Beispiel abschreiben.

### 2. Messmodus statt Raten

```text
fexobooth.exe --dev --dslr-test
```

Probiert in **einem Durchlauf** fünf Auslöse-Varianten durch und misst, welche
wirklich ein Foto liefert — statt eine Vermutung pro Build:

| | Variante |
|---|---|
| A | Live-View **an** + Auslöser ganz durch (Canons Beispielweg) |
| B | Live-View **an** + halb drücken, dann ganz durch |
| C | Live-View **an** + TakePicture |
| D | Live-View **aus** + TakePicture |
| E | Live-View **aus** + Auslöser ganz durch |

Beobachtet Karte **und** Direktweg gleichzeitig. Liefert keine Variante ein
Foto, spricht das für die Kamera selbst (Wahlrad, Objektiv, Akku) — auch das
sagt der Bericht mit konkreten Prüfpunkten.

**Dieser Messlauf wurde noch nie auf Hardware gefahren.** Seit 2.4.59 erzeugt
er mit `--dev` ein normales Dashboard-Log und nutzt ebenfalls nur den Owner.

### 3. Log-Versand ins Dashboard (läuft)

- **Auf der Box:** Service-Menü (PIN 3198) → Tab „Allgemein" →
  **„Logs ans Dashboard senden"**
- **Im Dashboard:** Fotoboxen → **Box-Logs** — nach Box filterbar, Volltextsuche,
  Fehler rot markiert, Download
- **Serverseitig:** `POST /api/booth/logs`, gleicher Bearer-Token wie der
  Heartbeat; Dateien unter `storage/app/booth-logs/<box>/`
- Kein Umkonfigurieren der ~280 Boxen nötig — die Adresse wird aus dem
  Heartbeat-Endpunkt abgeleitet

**Logs direkt vom Server lesen** (schneller als über die Weboberfläche):

```bash
ssh -i ~/.ssh/adminfexobox_claude c710394claude-code@admin.fexobox.de \
  "ls -lt --time-style=+%H:%M /web/admin-fexobox-de-app/storage/app/booth-logs/245/ | head"

ssh -i ~/.ssh/adminfexobox_claude c710394claude-code@admin.fexobox.de \
  "zcat /web/admin-fexobox-de-app/storage/app/booth-logs/245/<datei>.gz" > lokal.log
```

> **Prüfen, ob ein Upload wirklich ankam** (nicht darauf verlassen, dass er
> losgeschickt wurde):
> ```bash
> ssh ... "grep -a 'BoothLog: Log empfangen' \
>   /web/admin-fexobox-de-app/storage/logs/laravel.log | tail -3"
> ```

### 4. Logik-Tests ohne Hardware

Die DSLR-Suite liegt dauerhaft unter `tests/`. 2.4.60 besteht **18/18 Tests
unter Windows**. Die Regressionen pruefen Host-Reihenfolge und
Unlock-Fehlerpfade, genau einen Capacity-Reset pro Session, den Shutter-Guard,
die kameratypgenaue Warteanzeige, den Canon-PIL-Pfad sowie
Belichtungszuordnungen und Diagnoselogging. `py_compile` ist gruen und
`webcam.py` hat keinen semantischen Diff. Das ersetzt den Hardware-Retest
nicht.

---

## Was im Log worauf hindeutet

| Logzeile | Bedeutung |
|---|---|
| `EDSDK.dll gefunden: ...\_internal\EDSDK.dll` | installierter Build nutzt die mitgelieferte Canon-DLL |
| `CANON-HANDLER READY object/state` | beide offiziellen Handler wurden im Owner registriert |
| `Speicherung: direkter Host-Transfer ohne Speicherkarte` | Produktionsweg ist korrekt |
| `CANON-HOST READY ... save_to=Host` | Host-Ziel, Capacity und Readback waren vor dem ersten Shutter bereit |
| `CANON-HOST NOT-READY` / `SHUTTER-BLOCKED` | Readiness-Vertrag nicht erfuellt; die App loest bewusst nicht aus |
| `CANON-CAPTURE ARMED capture=...` | Queue wurde unmittelbar vor genau diesem Auslöser gebunden |
| `CANON-CAPTURE SHUTTER press=OK ... release=OK` | genau ein Capture angenommen und Auslöser sauber losgelassen |
| `CANON-OWNER TIMEOUT` | genannter nativer Auftrag blockiert; nicht erneut probieren |
| `CANON-EVENT QUEUED ... 0x00000208` | Canon hat ein Transferbild bereitgestellt |
| `CANON-TRANSFER START/COMPLETE` | Dateiname/Format, angekündigte/empfangene Bytezahl und Dauer |
| `CANON-STATE EVENT ... CaptureError/InternalError` | asynchroner Canon-Fehler mit Capture-ID und Zeit seit Shutter |
| `STALE-EVENT-REJECTED` | verspäteter Transfer wurde bewusst gecancelt, nicht als neues Foto benutzt |
| `CANON-CAPTURE TIMEOUT ... owner=...` | Event/Download fehlte; Owner-Zustand steht in derselben Zeile |
| `CANON-THREAD-VERSTOSS` | harte Architekturverletzung; darf nie erscheinen |
| `CANON-BELICHTUNG WARNUNG` | Belichtungskorrektur an der Kamera steht nicht auf null; App aendert sie nicht |
| `CANON-DIAG EXPOSURE-JPEG` | Dev-only: EXIF und Helligkeitsverteilung des echten JPEGs |
| `EDSDK Fehler 0x81 (DEVICE_BUSY)` | Kamera belegt, meist Folge eines hängenden Aufrufs |
| `EDSDK Fehler 0xc1 (COMM_DISCONNECTED)` | USB-Verbindung abgerissen |
| `EDSDK 0xa102 (OBJECT_NOTREADY)` | **harmlos** — Live-View braucht Anlaufzeit |
| `expected LP_c_ulonglong` | 64-/32-Bit-Konflikt → `tests/test_edsdk_typen.py` |
| `Bilanz: X echt / Y Notlösung / Z leer` | **Die wichtigste Zeile.** `echt` muss steigen |
| `Notlösung geliefert: 1056x704` | Vorschaubild statt Foto — sieht verwaschen aus |

---

## Offene Punkte

### 1. Funktioniert direkt das erste 2.4.60-Foto? (offen, höchste Priorität)

Der Canon-Grundweg ist seit 2.4.59 hardwarebestaetigt. Offen ist nur die neue
Kaltstart-Readiness aus 2.4.60.

**Prüfen:**
- Kamera frisch verbinden bzw. kalt starten und direkt das erste Foto nehmen
- Im Log: `CANON-HOST READY` vor `CANON-CAPTURE SHUTTER`
- Kein `TAKE_PICTURE_CARD_NG`, kein schwarzer Wartebalken
- Im Log: `=== ECHTES DSLR-FOTO: capture=... 6000x4000` statt `NOTLÖSUNG`?
- Am Zeilenende: steigt `echt` in der Bilanz?

### 2. Funktioniert der Direktweg ohne Karte? (offen, entscheidend für die Flotte)

Der 2.4.59-Erfolg wurde mit eingesetzter Karte erzielt, aber laut Log ueber
`SaveTo=Host`. Fuer den ersten direkten A/B-Vergleich darf die Karte in 2.4.60
noch eingesetzt bleiben. Sobald Kaltstart und komplette Session sauber sind,
muss mindestens ein Nachweis **ohne Karte** folgen; das ist der echte
Flottenweg.

### 3. Standbild zeigt anderen Bildausschnitt als das finale Foto (offen)

Christian mehrfach: *„liveview macht freeze und zeigt nicht das foto"*.
Zwei Anteile:
- **Zeitversatz** — schrumpft, sobald Fotos schnell ankommen
- **Unterschiedlicher Bildausschnitt** zwischen Vorschau und Aufnahme —
  eigenes Thema, noch nicht angefasst

Der Wartehinweis („Foto wird aufgenommen…") wurde seit 2.4.55 nach 900 ms
eingeblendet. 2.4.60 plant ihn fuer Canon nicht mehr; bis das JPEG da ist,
bleibt das letzte Live-View-Bild stehen. Nikon behaelt den Hinweis.

### 4. Überbelichtete Fotos (Ursache geklaert)

Die Belichtungskorrektur war an der Kamera komplett verstellt und ist dort
wieder korrigiert. Die App hatte ISO, Zeit, Blende und Korrektur nicht gesetzt.
2.4.60 warnt beim Verbinden vor einer Korrektur ungleich null; im Dev-Log stehen
zusätzlich EXIF und eine Helligkeitsprobe des echten JPEGs.

### 5. Belichtungszeit im Auge behalten

Ohne Blitz wählt die Automatik bei dunkler Location lange Zeiten → verwackelte
Fotos. Im Dev-Modus schreibt das Log Zeit, Blende, ISO, Weissabgleich,
Belichtungskorrektur und die EXIF-Werte des echten JPEGs mit.
**Erst messen, dann diskutieren** — und Christians Randbedingungen beachten
(kein Blitz, AF an, Kunde stellt nichts ein).

---

## Fallstricke für die nächste Sitzung

**1. Nach zwei Fehlversuchen nicht dieselbe Architektur weiterflicken.**
2.4.46 bis 2.4.58 reparierten echte Einzelursachen, ließen die verteilte
EDSDK-Nutzung aber bestehen. 2.4.59 behebt deshalb den zusammenhängenden
Owner-/Callback-Vertrag und versieht ihn mit messbaren Logmarkern.

**2. Alte Versionen sind Verhaltens-Baselines, keine Kopiervorlagen.**
`ffbbf36` ist der beste historische Hinweis auf Host-Transfer ohne Karte.
Seine 32-/64-Bit-Typen und Konstanten waren aber teilweise falsch. Nicht
komplett zurückrollen; nur das belegte Verhalten vergleichen.

**3. Jeder Auftrag an die Kamera braucht ein hartes Zeitlimit.**
Ein bereits im nativen DLL-Aufruf blockierter Thread kann in Python nicht
sicher abgebrochen werden. Dann wird der Owner als ungesund markiert und nimmt
keine weiteren Aufträge an; das Log enthält Auftrag und Owner-Stack.

**4. Ein hängender Aufruf darf sich nie wiederholen.**
Kein zweiter Owner und kein Wegwerf-Handlerthread. `CANON-OWNER TIMEOUT` ist
ein Abbruchsignal für diesen Prozess, keine Einladung zum Retry.

**5. Auch der Rückkanal muss im Kamera-Owner registriert werden.**
Die frühere Aussage „Handler bewusst daneben" ist widerlegt. Canons Sample
registriert Object und State auf demselben STA vor `OpenSession`. Der native
Callback selbst bleibt kurz und stellt den Download nur priorisiert in die
Owner-Queue.

**6. Erfolgsmeldungen nie behaupten.**
Im Code stand jahrelang „Handler funktioniert trotzdem" — das war eine
ungeprüfte Annahme und hat die Fehlersuche über Monate blockiert. Wenn eine
Funktion nicht sicher weiß, ob sie erfolgreich war, muss sie das sagen dürfen
Ein Handler gilt nur bei Rückgabe `EDS_ERR_OK` als registriert; ein Foto nur
nach empfangenem, dekodiertem JPEG in echter DSLR-Auflösung.

**7. Die Webcam-Flotte nicht anfassen.**
`webcam.py` blieb in dieser ganzen Sitzung unberührt. Alle Eingriffe in
`app.py` und `session.py` liegen hinter einer expliziten Abfrage des
Kameratyps. Canon unterdrueckt den Balken, Nikon behaelt ihn und der
Webcam-Capture folgt weiterhin seinem bisherigen Pfad.

---

## Relevante Dateien in 2.4.60

```
src/__init__.py              Version 2.4.60
src/camera/edsdk.py          vollständiger Owner, Handler/Callback-Queue,
                             Host-Readiness, Konstanten, Dev-Diagnose
src/camera/canon.py          Host-Flow, State-Handler, Capture-Korrelation,
                             Host-Ready-Guard, EXIF-/Helligkeitsdiagnose
src/app.py                   Handle-Release über den Owner
src/ui/screens/session.py    kein Canon-Wartebalken, direkter PIL-Bildpfad,
                             kein zweiter Canon-Capture im Webcam-Fallback
src/main.py                  Dev-Logging auch bei --dslr-test
src/tools/dslr_test.py       keine rohen DLL-Aufrufe mehr
tests/                       18/18 DSLR-Regressionen ohne Kamera (Windows)
CHANGELOG.md, ERKENNTNISSE.md, FORTSCHRITT.md, TODO.md
```

---

## Empfehlung für den Einstieg

1. **`python tests/alle_tests.py`** — muss komplett sauber durchlaufen.
2. **2.4.60 bauen und mit `--dev` auf Box 245 starten; dslrBooth schließen.**
3. Kamera kalt starten und direkt genau ein Foto aufnehmen. Die Karte darf
   fuer den ersten Vergleich eingesetzt bleiben; `SaveTo=Host` muss im Log
   bestaetigt sein.
4. Log ins Dashboard senden. Entscheidend ist die Kette
   `HANDLER READY → HOST READY → CAPTURE → EVENT 0x208 → TRANSFER COMPLETE →
   ECHTES DSLR-FOTO`.
5. Eine komplette Session fahren; danach denselben Nachweis mindestens einmal
   ohne SD-Karte erbringen.
6. Bei `CARD_NG`, `CANON-OWNER TIMEOUT` oder fehlender Kette nichts auf
   Verdacht ändern; zuerst dieses eine Log auswerten. Optional danach
   `--dev --dslr-test`.

---

## Ehrliche Einordnung

2.4.59 hat nach dem ersten Kaltstartfehler sieben echte 6000-x-4000-JPEGs
geliefert. Der Canon-Grundweg ist damit nicht mehr nur eine Theorie. 2.4.60
schliesst gezielt das Readiness-Race, entfernt den schwarzen Canon-Balken und
die unnoetige Bildkonvertierung und erweitert die Diagnose. Der ehrliche
Status lautet: **Grundweg hardwarebestaetigt; 2.4.60-Kaltstart und Betrieb ohne
SD-Karte noch abzunehmen.**
