# Changelog

Alle wichtigen Änderungen an diesem Projekt werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

---

## [2.4.63] - 2026-09-01 - Nikon-Erkennungsdiagnose erweitert

> Dieser Build veraendert weder Nikon-Erkennung noch Kamera-Timeouts,
> Live View oder Capture. Canon und Webcam bleiben funktional unveraendert.
> Ziel ist ein belastbarer Cloud-Log vom D3300-Ausfall auf Box 252.

### Bridge-Zustand statt generischer Nullmeldung

- Die `FexoNikonBridge` 0.2.0 besitzt das read-only Kommando `diag`. Es startet
  keinen Scan, sondern liefert PID, Manager-/Init-Zustand, letzten Scan mit
  Anlass und Dauer, alle bereits bekannten Geraete sowie die letzte Ausnahme.
- Interne `CameraControl.Devices`-Events fuer WPD/WIA-Fehler werden jetzt in
  einem threadsicheren, begrenzten Speicherpuffer festgehalten. Auch fremde
  `Console.Out`-/`Console.Error`-Ausgaben bleiben vom JSON-/JPEG-Protokoll
  getrennt und sind begrenzt im Snapshot sichtbar.
- Das Protokoll bleibt rueckwaertskompatibel. Eine alte Bridge ohne `diag`
  wird als solche geloggt und veraendert das Kameraergebnis nicht.

### Developer-Cloud-Log

- Jeder Bridge-Aufruf nennt Kommando, Request-ID, Thread, Lock-Wartezeit,
  Kommandodauer, Gesamtdauer und Ergebnis. Damit wird eine belegte Pipe von
  `null Kameras` getrennt.
- Nach Bridge-Start, fehlgeschlagenem Warmup/Init und gedrosselt nach leerer
  Admin-Liste wird der Bridge-Snapshot asynchron ins normale Dev-Log geholt.
- Nach Init-Fehlern folgt hoechstens einmal pro Minute ein read-only
  Windows-Snapshot: relevante PnP-Geraete, Status/Service/Fehlercode und nur
  Namen/PIDs moeglicher Konkurrenzprozesse. Generische fremde WPD-IDs werden
  redigiert; eine Prozessliste allein wird nicht als Besitzbeweis bezeichnet.
- Einmal pro App-Start werden EXE/DLLs im tatsaechlich verwendeten
  Bridge-Ordner mit Groesse, SHA-256 und verfuegbarer Dateiversion geloggt.

### Build-Sicherheit

Der lokale Installer baut die Bridge nun zwingend frisch und fuehrt danach
denselben Protokolltest wie GitHub Actions aus. Er prueft den Developer-Pfad
mit `ping -> diag -> unbekannt -> quit` und separat den normalen Start ohne
Diagnoseflag. Eine alte Bridge-Binaerdatei kann damit nicht mehr unbemerkt in
einen neuen Installer geraten. App-Version und Builder-Default stehen auf
2.4.63.

### Validierung

- Windows-Bridge-Build: **0 Warnungen, 0 Fehler**; Protokolltest fuer
  Developer- und Produktionspfad bestanden.
- Nikon-Diagnosetests unter Windows: **11/11**; gesamte DSLR-Suite ohne
  Hardware: **20/20 Testgruppen** bestanden.
- Echter 15-Sekunden-Init ohne Kamera bestaetigt: sauberer Timeout,
  vollstaendiger Scanstatus und keine Flutung durch die bekannten
  Canon-EDSDK-Banner.
- `py_compile`, Nikon-Smoke-Test und die semantischen Canon-/Webcam-Diffchecks
  sind gruen. Fremde WPD-/Scanner-IDs werden redigiert, waehrend
  Busy-/Access-denied-/HRESULT-Informationen erhalten bleiben.

**Offen:** 2.4.63 auf Box 252 mit der Nikon D3300 im Developer Mode starten,
einmal Admin-Suche und einmal Session-Start ausfuehren und den Log ans
Dashboard senden. Erst dieser Lauf bestimmt den eigentlichen Folgefix.

---

## [2.4.62] - 2026-08-26 - Canon-Host-Readiness ohne SD-Karte korrigiert

> Ausschliesslich der interne Canon-Host-Readiness-Vertrag wurde korrigiert.
> Webcam, Nikon, Canon-Shutter, Softwareblitz und Bildverarbeitung bleiben
> unveraendert.

### Hardwarebefund auf Box 248

Die EOS 2000D wurde von EDSDK bei jedem Versuch gefunden und ihre Session
erfolgreich geoeffnet. Auch `SaveTo=Host`, `UILock`,
`EdsSetCapacity(reset=1)`, `UIUnlock` und der `SaveTo`-Readback waren
erfolgreich. Ohne SD-Karte blieb `AvailableShots` jedoch dauerhaft bei null.
2.4.61 wertete allein diesen Wert als fatal, gab die bereits verbundene Kamera
wieder frei und meldete irrefuehrend, sie koenne nicht initialisiert werden.

Die Kamera stand auf `P`; der Videomodus ist ausgeschlossen. Canons
mitgelieferte Dokumentation verlangt fuer den Hostweg die Capacity-Meldung,
aber keinen positiven `AvailableShots`-Readback. Auf manchen Bodies ist dieser
Wert nur eine Anzeige und ohne Karte nicht belastbar.

### Null ist nach bestaetigtem Hostweg kein Verbindungsfehler mehr

- Die Pflichtfolge `SaveTo=Host -> UILock -> SetCapacity -> UIUnlock ->
  SaveTo-Readback` bleibt unveraendert und fail-closed.
- `AvailableShots=0` wird weiterhin eine Sekunde lang abgefragt. Bleibt der
  Wert null, wird der kartelose Hostbetrieb deutlich gewarnt, danach aber auf
  Basis von `SaveTo=Host` plus erfolgreicher Capacity als bereit markiert.
- Positive Werte, Canons Unbekanntwert und nicht unterstuetzte Readbacks
  behalten ihre bisherigen Wege. Andere unplausible UInt32-Werte bleiben
  fatal; die Lockerung gilt ausschliesslich fuer die hardwarebelegte null.
- Der Readiness-Marker nennt seine Beweisgrundlage explizit, zum Beispiel
  `readiness=save_to+capacity` fuer die EOS ohne Karte.
- Es gibt kein Dummyfoto, keinen automatischen zweiten Shutter und keinen
  Rueckfall auf die Speicherkarte. Ein echtes `CARD_NG` invalidiert weiterhin
  die Session und wird nicht automatisch wiederholt.

### Vorheriger Timingtest bestanden

Der 2.4.61-Lauf auf Box 245 lieferte vier von vier echte
6000-x-4000-JPEGs. Press, Release, Blitz, Transfer und Fotoanzeige kamen je
Capture genau einmal; der Blitz folgte Press-Return nur 60 bis 65 ms spaeter.
Auch das erste Foto war vollstaendig. Damit bleibt der gerade bestaetigte
Shutter-/Blitzablauf in 2.4.62 bewusst unangetastet.

### Tests

`python tests/alle_tests.py`: **18/18 unter Windows bestanden**, ohne Kamera.
Der Readiness-Test deckt dauerhafte null, `0 -> positiv`, alle Pflichtfehler,
unbekannte/nicht lesbare Werte und einen weiterhin fatalen unplausiblen Wert
ab. Die integrierte Fake-Kette startet mit `AvailableShots=0`, erzeugt vor dem
Benutzercapture kein Testfoto und liefert danach mit genau einem Press ein
6000-x-4000-Host-JPEG. `py_compile` und `git diff --check` sind gruen;
Webcam-, Nikon-, Canon-Manager- und Session-Dateien haben keinen Diff.

**Offen:** 2.4.62 auf Box 248 ohne SD-Karte im Dev-Modus testen. Erwartet sind
Null-Warnung, `CANON-HOST READY ... readiness=save_to+capacity`, LiveView und
eine komplette Session mit echten 6000-x-4000-JPEGs ohne `CARD_NG`, Retry,
Doppelbild oder Notloesung.

---

## [2.4.61] - 2026-08-26 - Canon-Softwareblitz an den Shutter angenaehert

> Ausschliesslich der interne Canon-DSLR-Ablauf wurde veraendert. Webcam und
> Nikon behalten ihren bisherigen Capture- und Blitzpfad.

### Hardwarebefund aus 2.4.60

Box 245 lieferte mit der Canon EOS 2000D und eingesetzter SD-Karte vier von
vier echte JPEGs mit 6000 x 4000 Pixeln ueber den Host-Transfer. Es gab weder
`CARD_NG` noch einen schwarzen Wartebalken, Retry oder ein Doppelbild; der
LiveView blieb waehrend aller Aufnahmen aktiv.

Der weisse Softwareblitz erschien jedoch 1.497 bis 1.569 ms vor der Rueckkehr
des erfolgreichen `ShutterButton_Completely`-Aufrufs. Der mechanische Klick
kam hoerbar spaeter. Wer sich direkt nach dem Softwareblitz bewegte, stand
deshalb bereits anders auf dem echten Foto.

### Canon-Blitz folgt dem akzeptierten Press-Command

- Canon zeigt am Countdown-Ende keinen vorgezogenen Softwareblitz mehr.
- Der EDSDK-Owner liefert ein eingefrorenes Ergebnis mit Capture-ID, Press-/
  Release-Erfolg und monotonen Rueckkehrzeiten. Die bestehende boolesche API
  bleibt fuer alle anderen Aufrufer erhalten.
- Nach jedem begonnenen `ShutterButton_Completely` wird
  `ShutterButton_OFF` in einem `finally` genau einmal versucht, auch bei einer
  nativen Exception.
- Nur wenn der synchrone Press-Aufruf `EDS_ERR_OK` liefert, fordert der
  Canon-Manager im aufrufenden Capture-Worker genau einmal den UI-Blitz an.
  Release-, Transfer- und Decode-Fehler bleiben davon getrennt sichtbar.
- Der Tk-Hauptthread zeigt den bestehenden weissen Blitz fuer 90 ms. Ein
  capture-eigener Generation-Token verwirft alte Rueckmeldungen nach
  Screen-Wechsel, neuem Capture oder bereits abgeschlossenem Foto.
- Fehler beim Tk-Einreihen oder Anzeigen sind nicht fatal und erzeugen weder
  Retry noch einen zweiten Shutter.

`press_ok` ist bewusst nur die beste verfuegbare EDSDK-Naeherung. Canon stellt
kein Ereignis fuer den exakten physikalischen Verschlusszeitpunkt bereit.

### Ergebnis schneller sichtbar

Das bereits dekodierte Canon-PIL-Foto wird beim Eintreffen im Tk-Hauptthread
sofort und genau einmal ueber den bestehenden Anzeigeweg konfiguriert. Es
wartet nicht mehr bis zu einem weiteren LiveView-/UI-Takt. Der vorhandene
Webcam-HD-Sofortweg liegt in einem getrennten Zweig; Nikon bleibt unveraendert.

### Dev-Diagnose und Tests

Korrelierte Marker zeigen `PRESS-START`, `PRESS-RETURN`, `RELEASE-RETURN`,
`CANON-FLASH REQUEST`, `CANON-FLASH SHOWN` und `CANON-PHOTO SHOWN`. Alte
Timingfelder heissen nun eindeutig `since_capture_arm_ms` beziehungsweise
`capture_arm_to_queue_ms`; kein Marker behauptet einen physikalisch
nachgewiesenen Verschlusszeitpunkt.

`python tests/alle_tests.py`: **18/18 unter Windows bestanden**, ohne Kamera.
Zusaetzlich geprueft sind Press-/OFF-Exceptions, Owner-Timeout, unveraenderliches
Ergebnis, Callback-Thread und -Fehler, genau-einmal-Blitz, stale UI-Tokens,
Canon-Sofortanzeige sowie die unveraenderten Nikon-/Webcam-Grenzen.
`py_compile` ist gruen; `webcam.py` und `nikon.py` haben keinen semantischen
Diff.

**Offen:** 2.4.61 auf Box 245 im Dev-Modus mit eingesetzter SD-Karte testen:
bis zum neuen weissen Blitz stillhalten, direkt danach bewusst bewegen und
pruefen, dass das gespeicherte Bild noch die Pose am Blitzzeitpunkt zeigt.
Danach folgt der separate Flottentest ohne SD-Karte.

---

## [2.4.60] - 2026-08-25 - Canon-Kaltstart und Capture-Anzeige nachgebessert

> Ausschliesslich der interne Canon-DSLR-Pfad wurde nachgebessert. Nikon
> behaelt seinen Wartehinweis; der funktionierende Webcam-Pfad und
> `webcam.py` bleiben semantisch unveraendert.

### Ergebnis des ersten 2.4.59-Hardwaretests

Box 245 lieferte mit der EOS 2000D und eingesetzter SD-Karte nach dem ersten
Versuch sieben echte JPEGs mit 6000 x 4000 Pixeln sauber per Host-Transfer.
Damit sind Owner, Event-Queue, Download und Dekodierung erstmals auf Hardware
bestaetigt. Nur das allererste Foto nach dem Kaltstart wurde mit
`TAKE_PICTURE_CARD_NG (0x8d07)` abgelehnt und durch ein Live-View-Notbild
ersetzt.

Die zunaechst auffaellige Ueberbelichtung kam von einer verstellten
Belichtungskorrektur an der Kamera und ist dort behoben. FexoBooth aendert
weiterhin keine Belichtungswerte automatisch.

### Host-Speicher vor dem ersten Shutter verbindlich bereit

- `SaveTo=Host`, Kamera-`UILock`, ein einmaliges `EdsSetCapacity(reset=1)`,
  garantiertes `UIUnlock` und die Readiness-Pruefung laufen als ein atomarer
  Auftrag im EDSDK-Owner.
- `SaveTo` wird bis zu einer Sekunde auf `Host` zurueckgelesen. Ein
  `AvailableShots` von null wird ebenfalls begrenzt abgewartet; nicht
  unterstuetzte bzw. unbekannte Werte werden sichtbar protokolliert.
- Der Capacity-Reset erfolgt genau einmal pro geoeffneter Kamera-Session und
  nicht mehr unmittelbar vor jedem Foto.
- Ohne bestaetigtes Host-Ready-Flag wird kein Shutter gesendet. Ein
  `CARD_NG` verwirft den Zustand fuer den naechsten kontrollierten Aufbau,
  loest aber keinen automatischen zweiten Versuch aus.

### Ruhigere und schnellere Canon-Aufnahme

- Canon plant den schwarzen Balken `Foto wird aufgenommen ...` nicht mehr.
  Der kurze weisse Ausloeseblitz, die Capture-Sperren und das eingefrorene
  letzte Live-View-Bild bleiben erhalten.
- Das bereits dekodierte Canon-PIL-Bild wird ohne wirkungslose
  PIL-NumPy-OpenCV-PIL-Rundreise weitergereicht. Eine konfigurierte
  180-Grad-Drehung nutzt direkt PIL; nur unerwartete Bildmodi werden nach RGB
  konvertiert.
- Auf Box 245 sollten damit rund 300 ms Bildaufbereitung plus etwa 40 bis
  60 ms Capacity-Aufruf pro Foto entfallen. Der Autofokus-/Shutter-Anteil der
  Kamera bleibt bewusst unveraendert.

### Belichtung besser diagnostizierbar, aber nicht ferngesteuert

- AE-Modus, Weissabgleich, Messmethode und Belichtungskorrektur werden mit den
  Canon-Werten korrekt benannt.
- Die Belichtungskorrektur steht einmal beim Verbinden im normalen Log; ein
  Wert ungleich null erzeugt eine Warnung, wird aber nicht zurueckgesetzt.
- Nur im Dev-Modus werden pro Foto weitere EDSDK-Werte sowie JPEG-EXIF und
  eine kleine Helligkeitsanalyse protokolliert. Fehlende Diagnosedaten brechen
  kein Foto ab und das Originalbild wird nicht veraendert.

### Tests

`python tests/alle_tests.py`: **18/18 unter Windows bestanden**, ohne Kamera.
Die neuen Regressionen pruefen unter anderem Host-Reihenfolge und
Unlock-Fehlerpfade, Capacity genau einmal pro Session, Shutter-Guard,
Canon-/Nikon-/Webcam-Anzeigegrenzen, PIL-Fastpath sowie
Belichtungszuordnungen und fehlertolerante JPEG-Diagnose. `py_compile` ist
ebenfalls gruen; `webcam.py` hat keinen semantischen Diff.

**Offen:** 2.4.60 bauen und auf Box 245 erneut im Dev-Modus pruefen. Der
entscheidende Test ist direkt das erste Foto nach einem Kamera-Kaltstart:
kein `CARD_NG`, kein schwarzer Balken, genau ein Shutter und ein echtes
6000-x-4000-JPEG. Danach folgt mindestens ein Flottentest ohne SD-Karte.

---

## [2.4.59] - 2026-08-25 - Canon-Owner, installierte DLLs und Host-Capture repariert

> Ziel ist ausschließlich die interne Canon-DSLR. Der funktionierende
> Webcam-Pfad wurde nicht umgebaut.

### Wahrscheinlicher Installationsbruch gefunden

Der One-Folder-Build enthält `EDSDK.dll` und `EdsImage.dll` unter `_internal`,
der bisherige Loader suchte dort aber nicht. Damit konnte Canon im Quellbaum
gefunden werden und nach einer Neuinstallation trotzdem komplett fehlen. Der
Loader prüft nun zuerst PyInstallers `sys._MEIPASS` und hält das von
`os.add_dll_directory()` gelieferte Handle am Leben, damit auch `EdsImage.dll`
beim Nachladen erreichbar bleibt.

### Canon vollständig auf einen Owner gebracht

- Ein STA-Thread `edsdk-kamera` besitzt SDK, Referenzen, Handler, Session,
  Properties, Live-View, Shutter, Event-Pump, Downloads und Cleanup.
- Object- und State-Handler werden wie im Canon-Sample vor `OpenSession`
  registriert. Der native Callback reiht nur einen priorisierten Folgeauftrag
  ein; Download/Cancel/Release passieren erst nach seiner Rückkehr.
- `CloseSession → EdsRelease → Python-Callbackhalter entfernen` läuft atomar.
  Dadurch kann die DLL nie auf bereits freigegebenen ctypes-Callbackcode zeigen.
- Parallele Starter warten auf dieselbe SDK-Bereitschaft. Nach jedem nativen
  Timeout sperrt der Owner fail-closed; ein abgebrochener Queueauftrag kann
  später nicht doch noch auslösen.
- Recovery verwirft alte Handles und enumeriert vollständig neu.

### Host-Capture ohne Speicherkarte

- `SaveTo=Host` ist der feste Produktionsweg; kein stiller Wechsel auf Karte.
- Offizielle Werte aus `EDSDKTypes.h`: Object-All `0x200`, Transfer `0x208`,
  State-All `0x300`, Shutdown `0x301`, CaptureError `0x305`, InternalError
  `0x306` sowie die korrekten JPEG-Qualitäten.
- Pro App-Capture wird die Transfer-Queue unmittelbar vor dem Shutter
  scharfgeschaltet und mit einer Capture-ID versehen. Verspätete Events einer
  alten Aufnahme werden gecancelt, fremde Queuebilder verworfen.
- Genau ein Capture-Befehl plus Shutter-OFF. Kein automatischer AF-NG-
  Zweitauslöser und kein zweiter Canon-Capture über den Webcam-Fallback.
- Downloadpfade enden immer mit Complete oder Cancel und geben Stream/Objekt
  genau einmal frei. Dateiname, Format, Bytezahl und Laufzeit stehen im Log.
- Live-View-`None` zählt jetzt als echter Fehler; fatale EDSDK-Codes stoßen die
  vollständige Neu-Enumeration an.

### Dev-Diagnose

`--dev` protokolliert Owner-Start, Auftrag-ID, anfordernden/ausführenden Thread,
Queue-Wartezeit, native Laufzeit, Owner-Stack bei Timeout, Capture-ID, Shutter,
Object-/State-Event, Transfer und JPEG-Auflösung. `--dev --dslr-test` richtet
das Dashboard-Logging nun ebenfalls vor dem Messlauf ein. Pointer, Bilddaten,
Tokens und Konfiguration werden nicht geloggt.

### Tests

`python tests/alle_tests.py`: **15/15 unter Windows bestanden**, ohne Kamera.
Enthalten sind unter anderem Hersteller-Header, PyInstaller-`_internal`,
Thread-ID/Owner-Grenze, Parallelstart und Timeout-Races, exakt ein Auslöser,
Callback-Entkopplung, Transfer-Cleanup, verzögerte Events und die integrierte
Fake-Kette `0x208 → Host-Download → Queue → 6000×4000-JPEG`.

**Hardware-Nachtrag:** Box 245 lieferte mit EOS 2000D und eingesetzter Karte
nach einem `CARD_NG` beim ersten Versuch sieben echte 6000-x-4000-JPEGs ueber
`SaveTo=Host`. Damit ist 2.4.59 als Grundreparatur bestaetigt; Kaltstart und
der Flottennachweis ohne Karte werden mit 2.4.60 nachgetestet.

---

## [2.4.58] - 2026-08-24 - Live-View zurueck (uebersehene Aufrufstelle)

> Christian: "kein liveview! kamera in endlosschleife beim 1 foto! wird immer
> schlimmer!"

**Das war mein Fehler aus 2.4.55.** Er stand 166 Mal im Box-Log:

    Fehler beim Holen des Live View: argument 2: TypeError:
    expected LP_c_ulonglong instead of pointer to c_ulong

### Was passiert ist

In 2.4.55 wurde die Signatur von `EdsGetLength` korrekt auf 64 Bit umgestellt.
Die Aufrufstelle im Live-View blieb aber auf 32 Bit stehen — und damit
scheiterte **jedes einzelne Vorschaubild**. Kein Live-View, und weil die
Aufnahme darauf aufbaut, auch kein Foto.

ctypes prueft solche Typen erst zur Laufzeit. Beim Start faellt nichts auf,
Syntaxpruefung und Import laufen sauber durch — der Fehler zeigt sich erst auf
der Box.

### Behoben

- Die uebersehene Aufrufstelle nutzt jetzt `ctypes.c_uint64`.
- Eine systematische Suche ueber die ganze Datei bestaetigt: keine weitere
  32-Bit-Variable an einem 64-Bit-Parameter.

### Neu: `tests/test_edsdk_typen.py`

Ein Test, der ohne Kamera in Sekunden prueft:

1. Stimmen alle Signaturen mit dem Canon-Header ueberein?
2. Passen alle **Aufrufstellen** zu diesen Signaturen?

Gegenprobe gemacht: Baut man den Fehler von 2.4.57 kuenstlich wieder ein,
meldet der Test ihn mit Datei und Zeilennummer und gibt Rueckgabewert 1.

**Warum das noetig war:** Genau dieser Fehlertyp — 64-Bit-Wert als 32 Bit — war
im August 2026 fuenfmal die Ursache. Vier Fundstellen kosteten je eine
Testrunde auf der echten Box, die fuenfte entstand beim Beheben der vierten.
Dieser Test faengt die ganze Familie ab, bevor ein Build entsteht.

**Ab jetzt gilt: `python tests/test_edsdk_typen.py` vor jedem DSLR-Build.**

---

## [2.4.57] - 2026-08-24 - Ein Faden fuer die Kamera (Ursache des Haengens)

> Christian: "du musst kapieren das die geraete in der regel gar keine karte
> drin haben!! merk dir das!"

Damit ist der Kartenweg keine Loesung, sondern hoechstens ein Notbehelf fuer
die eine Testbox. Der Direktweg MUSS laufen — und der braucht den Rueckkanal,
der bisher haengenblieb. Diese Version geht an die Ursache.

### Die Ursache

Canons Bibliothek arbeitet innen mit COM im STA-Modell: Sie bindet sich an den
Programmfaden, der sie zuerst startet. Aufrufe aus einem ANDEREN Faden muessen
von COM dorthin vermittelt werden — und das gelingt nur, solange der
urspruengliche Faden Windows-Nachrichten abarbeitet.

In der App wurde die Kamera aus **zwei verschiedenen Faden** gestartet:

| Stelle | Faden |
|---|---|
| `src/app.py` `_pre_init_camera` | Haupt-Faden (ueber `root.after`) |
| `src/ui/dialogs/system_test.py:297` | eigener Hintergrund-Faden |

Je nachdem, was zuerst lief, war die Bibliothek an den einen oder anderen
gebunden — und der jeweils andere Weg hing. Danach meldete die Kamera
DEVICE_BUSY, es gab weder Live-View noch Fotos.

### Behoben

- **Ein fester Kamera-Faden.** Er meldet ein eigenes COM-Apartment an, startet
  die Bibliothek und arbeitet danach **dauerhaft** Nachrichten ab. Genau das
  hat vorher gefehlt: Frueher pumpte nur kurz jemand waehrend der
  Registrierung, danach war Ruhe — und der Aufruf blieb fuer immer haengen.
  Kameraliste und Sitzung laufen jetzt garantiert ueber diesen Faden, egal wer
  sie anstoesst.

- **Der Rueckkanal laeuft BEWUSST daneben.** Er kann haengen; laege er im
  Kamera-Faden, waere dieser blockiert und mit ihm Live-View, Aufnahme und
  Freigeben — aus einem Problem wuerde eine tote Box. (Dieser Fehler steckte im
  ersten Anlauf dieser Version und wurde vom Test gefunden, bevor er auf eine
  Box kam.)

### Getestet

    SDK-Start  -> Faden 'edsdk-kamera'
    Sitzung    -> Faden 'edsdk-kamera'      (angestossen aus 'system-test')
    Rueckkanal -> Faden 'edsdk-rueckkanal'  (blockiert den Kamera-Faden nicht)

Dazu: Der Kamera-Faden nimmt danach weiter Auftraege an; ein haengender
Registrierungs-Aufruf wird genau einmal versucht und blockiert nichts.

---

## [2.4.56] - 2026-08-24 - Rueckschritt behoben: kein Live-View, keine Kamera

> Christian: "kein liveview mehr, die kamera wird erst als nicht verbunden
> gezeigt, dann nach an und ab stecken wieder da. sie macht geraeusche aber ich
> sehe weder live view noch fotos! wird ja immer schlechter!"

**Das war ein Rueckschritt, den ich mit 2.4.53 eingebaut habe.** Die Box war
vorher benutzbar, danach nicht mehr.

### Was passiert ist

Das Box-Log zeigt die Kette:

    11:10:30  Rueckkanal-Registrierung nach 4s nicht abgeschlossen
    11:10:30  EDSDK Fehler 0x81 (DEVICE_BUSY)       <- Kamera blockiert
    11:12:47  Rueckkanal-Registrierung nach 4s ...  <- naechster Versuch
    11:13:07  Rueckkanal-Registrierung nach 4s ...
    11:13:27  Rueckkanal-Registrierung nach 4s ...

`EdsSetObjectEventHandler` bleibt auf dieser Hardware haengen. Der wartende
Aufruf haelt die Kamera besetzt — direkt danach meldet sie DEVICE_BUSY, es kommt
kein Live-View und kein Foto. Und weil bei jeder Neuinitialisierung erneut
registriert wurde, legte sich Blockade auf Blockade. Genau deshalb wurde es
"immer schlechter".

In 2.4.53 hatte ich den Direktweg zur ersten Wahl gemacht — und damit wurde
dieser Aufruf ueberhaupt erst bei jeder Box mit Karte ausgefuehrt.

### Behoben

- **Einmal haengen genuegt.** Bleibt die Registrierung haengen, wird sie auf
  diesem Rechner nie wieder angefasst. Getestet: Bei vier Versuchen erreicht
  genau EIN Aufruf die Kamera, die restlichen werden sofort abgewiesen.

- **Der Kamera-Zwischenspeicher hat wieder Vorrang.** Steckt eine Karte, wird
  der Rueckkanal gar nicht erst angefordert.

  **Wichtig zur Einordnung — das war ein Missverstaendnis meinerseits:** Die
  Fotos landen in BEIDEN Faellen auf der PC-Festplatte
  (`C:exobooth\BILDER`). Unterschiedlich ist nur der Transportweg aus der
  Kamera heraus. Ueber den Zwischenspeicher heisst NICHT, dass die Bilder auf
  der Karte bleiben — die Box holt jedes Foto sofort ab.

  Ohne Karte bleibt nur der Direktweg; dort wird der Rueckkanal weiterhin
  versucht, mit klarer Ansage im Log.

### Weiterhin gueltig aus 2.4.55

Der Download-Fehler (`INTERNAL_ERROR`) ist behoben — drei EDSDK-Funktionen
bekamen 64-Bit-Werte als 32 Bit uebergeben. Genau dieser Fehler hat verhindert,
dass ein bereits gemeldetes Foto abgeholt werden konnte. Mit dem Weg ueber den
Zwischenspeicher greift diese Korrektur jetzt.

---

## [2.4.55] - 2026-08-24 - Das Foto war da, es liess sich nur nicht abholen

> Christian: "nun der dialog 'Bild wird geschossen' ist auch keine lösung!!
> nach wie vor alles buggy, liveview macht freeze und zeigt nicht das foto >
> dauert alles viel zu lange!"

### Der Durchbruch im Log

Zum ersten Mal ist die vollstaendige Kette sichtbar — und sie zeigt, dass alles
funktioniert bis auf den letzten Schritt:

    >>> OBJECT EVENT: DirItemRequestTransfer_Alt        <- Kamera meldet das Foto
    >>> Transfer-Event erkannt - starte Download...
    Lade Bild in Speicher: IMG_0001.JPG (820393 bytes)  <- Groesse korrekt gelesen
    EDSDK Fehler 0x2 (INTERNAL_ERROR) bei Download      <- HIER bricht es ab

Das Foto existiert, die Kamera bietet es an, der Dateiname und die Groesse
kommen sauber an. Nur das Abholen scheitert.

### Behoben — dieselbe Fehlerfamilie wie 2.4.48

Drei EDSDK-Funktionen bekamen 64-Bit-Werte als 32 Bit uebergeben. Gegen den
Canon-Header `EDSDK.h` geprueft:

| Funktion | Header | stand im Code |
|---|---|---|
| `EdsCreateMemoryStream(inBufferSize)` | EdsUInt64 | `c_uint` |
| `EdsDownload(…, inReadSize, …)` | EdsUInt64 | `c_uint` |
| `EdsGetLength(…, outLength)` | EdsUInt64* | `POINTER(c_uint)` |

Bei falscher Parameterbreite werden die Register falsch belegt: Die DLL bekommt
eine unsinnige Groesse und bricht mit INTERNAL_ERROR ab. Dazu schrieb
`EdsGetLength` 8 Byte in eine 4-Byte-Variable — ein Speicherueberlauf, der
lange unauffaellig bleibt.

Das ist derselbe Fehler wie beim Speicher-Layout von `EdsDirectoryItemInfo`
(2.4.48): ein 64-Bit-Wert als 32 Bit behandelt. Ein automatischer Abgleich
gegen den Header bestaetigt jetzt, dass alle benutzten Funktionen mit
64-Bit-Parametern stimmen.

Zusaetzlich: Die gemeldete Dateigroesse wird auf Plausibilitaet geprueft, bevor
damit Speicher angefordert wird. Ein absurder Wert wird als das gemeldet, was
er ist — ein falsch gelesenes Datenfeld, kein defektes Foto.

### Geaendert — der Wartehinweis erscheint nur noch, wenn es wirklich dauert

Der Hinweis aus 2.4.52 blitzte bei jedem Foto auf und war damit selbst eine
Stoerung. Jetzt gilt eine Schonfrist von 900 ms: Ist das Foto vorher da — so
soll es sein —, sieht der Gast ihn nie. Dauert es doch laenger, weiss er
wenigstens, dass das eingefrorene Bild nicht sein Foto ist.

---

## [2.4.54] - 2026-08-24 - Einfrieren beim Session-Start behoben

> Christian: "box friert ein sobald eine session gestartet wird"

**Das war ein Fehler, den ich in 2.4.49 eingebaut habe.**

### Ursache

Der Wachhund aus 2.4.49 hat es exakt gemeldet:

    EdsSetObjectEventHandler haengt seit 3 s. Das darf aus dem Haupt-Faden
    nicht passieren

Der DLL-Aufruf kehrt auf diesen Boxen nicht von allein zurueck — er wartet
darauf, dass der Programmfaden Windows-Nachrichten abarbeitet. Ruft man ihn
direkt im Haupt-Faden auf, blockiert er genau den Faden, der diese Nachrichten
abarbeiten muesste. Die Anwendung steht.

In 2.4.49 wurde der schuetzende Nebenfaden entfernt, weil eine aeltere Fassung
den direkten Aufruf hatte und als "lief frueher" galt. Das war ein Fehlschluss:
In jener Fassung wurde der Direktbetrieb praktisch nie benutzt, der Aufruf kam
also kaum vor.

### Behoben

- **Nebenfaden + Nachrichtenschleife + hartes Zeitlimit.** Der DLL-Aufruf laeuft
  im Nebenfaden, der Haupt-Faden arbeitet waehrenddessen Nachrichten ab (damit
  der Aufruf ueberhaupt fertig werden kann), und nach 4 Sekunden geht es weiter
  — komme was wolle. Getestet mit einem Aufruf, der nie zurueckkehrt: Die Box
  laeuft nach 4,0 s weiter statt einzufrieren.

- **Drei Antworten statt zwei.** Die Registrierung meldet jetzt
  *steht* / *unklar* / *abgelehnt*. Frueher wurde aus "unklar" entweder eine
  Falschmeldung ("steht") — die die Fehlersuche monatelang blockiert hat — oder
  ein unnoetiger Rueckfall auf den Kartenweg. Bei *unklar* wird der Direktweg
  jetzt trotzdem versucht, denn meist ist der Rueckkanal bereits eingetragen.

- **Selbstheilung im Betrieb.** Kam auf dem Direktweg noch NIE ein Ereignis an,
  stellt die Box einmalig auf die Speicherkarte um, statt bei jedem Foto erneut
  ins Leere zu laufen. Der Direktweg bleibt die erste Wahl — aber eine Box, die
  gar keine Fotos liefert, ist schlimmer als eine, die den langsameren Weg
  nimmt. Steckt keine Karte, sagt das Log klar, dass so kein Foto entstehen
  kann.

---

## [2.4.53] - 2026-08-24 - Fotos gehen direkt auf die PC-Festplatte

> Christian: "warte was meinst du damit?? die kamera hat doch fotos gemacht!
> autofokus hatte auch funktioniert! wir brauchen keine KARTE!!!! ich will nur
> auf die festplatte vom PC speichern!"

Das war ein Missverstaendnis auf meiner Seite, und es hat mehrere Runden
gekostet. In der Testbox steckte eine Speicherkarte — daraufhin wurde der Weg
ueber die Karte repariert, obwohl er fuer eine Fotobox gar nicht gewollt ist.

### Geaendert — der Direktweg ist jetzt der Hauptweg

Im Code stand woertlich: *"Speicherung konfigurieren: SD-Karte bevorzugt,
Host-Download als Fallback"*. Fuer eine Fotobox ist das genau verkehrt herum.
Steckte eine Karte in der Kamera, nahm die Box den Umweg

    Kamera speichert auf die Karte  ->  Box fragt die Karte staendig ab

Das ist langsam (erst schreiben, dann ueber USB wieder lesen), haengt am
Zustand der Karte, und die Bilder liegen am Ende doppelt.

**Jetzt gilt immer:** Die Kamera liefert das Bild direkt in den Rechner, es
landet in `C:exobooth\BILDER`. Die Karte kommt nur noch als Notnagel zum
Zug, falls sich der Rueckkanal nicht einrichten laesst.

**Nebenwirkung des alten Vorrangs:** Weil in der Testbox eine Karte lag, lief
die Box seit 2.4.48 ausschliesslich ueber die Karte — die Reparatur des
Direktwegs aus 2.4.49 kam nie zum Einsatz und blieb ungetestet.

### Damalige Aenderung, in 2.4.60 korrigiert

- **2.4.53 meldete der Kamera vor jeder Aufnahme freien Speicher.** Dahinter
  stand die nicht belegte Annahme, `EdsSetCapacity` verfalle nach jedem Foto.
  Der 2.4.59-Hardwaretest widersprach dem: Trotz Capacity unmittelbar vor
  jedem Foto scheiterte nur der erste Kaltstart-Capture, sieben weitere
  funktionierten. Seit 2.4.60 gilt deshalb der Canon-Vertrag: Capacity genau
  einmal im atomaren Host-Initialisierungsblock pro geoeffneter Session setzen
  und `SaveTo`/`AvailableShots` vor dem ersten Shutter begrenzt bestaetigen.

### Was dabei noch aufgefallen ist

`download_image_to_memory` liest die Dateigroesse aus derselben Struktur, in
der bis 2.4.48 das Speicher-Layout falsch war. Selbst wenn frueher ein Bild
gemeldet worden waere, haette der Download mit falscher Groesse fehlgeschlagen.
Das ist seit 2.4.48 behoben — hier nur zur Vollstaendigkeit, weil es erklaert,
warum der Direktweg auch vor dem 09.03.2026-Umbau schon anfaellig war.

### Gemessen (ohne Kamera, mit nachgebautem Ablauf)

    SaveTo = Rechner  ->  Rueckkanal eingerichtet
    Speicherplatz gemeldet  ->  ausgeloest (Live-View an)  ->  Bild fertig
    Ergebnis nach 0,4 s: 6000x4000, keine Karte beteiligt

---

## [2.4.52] - 2026-08-24 - Zurueck auf Canons Referenzweg + Wartehinweis

> Christian: "live view friert ein in der collage und man denkt das ist das
> foto > dann wird aber was ganz anderes angezeigt (wie bei webcam frueher)"
> und "wartezeit nach wie vor viel zu lange".

### Befund aus dem Box-Log (2.4.51, Box 245)

- Der Kartenstand blieb ueber den **ganzen** Testlauf bei 1735 — in diesem Lauf
  kam kein einziges Foto an.
- Das Ausloesen allein dauerte **2,5 Sekunden**
  (09:37:41.861 Befehl raus → 09:37:44.427 bestaetigt).

Beides geht auf zwei Stellen zurueck, an denen die Box von Canons eigenem
Beispielcode abweicht — und beide Abweichungen stammen aus frueheren
Reparaturversuchen, nicht aus einer Anforderung.

### Behoben — beide Abweichungen zurueckgenommen

- **Ausloesen wie in Canons Referenz.** Der Beispielcode im Repo
  (`EDSDK/.../sample/CSharp/.../TakePictureCommand.cs`) besteht aus zwei
  Zeilen: Ausloeser ganz durch, dann loslassen. In 2.4.49 kam ein halber Druck
  mit 0,35 s Pause dazu, damit der Autofokus vorher arbeiten kann — gut
  gemeint, aber genau das machte das Ausloesen 2,5 s langsam und brachte
  trotzdem kein Foto. Der Autofokus geht dabei nicht verloren: Ein Druck in
  einem Zug schliesst das Scharfstellen mit ein. Scheitert er doch, folgt
  automatisch ein zweiter Versuch ohne Fokus-Zwang.

- **Der Live-View bleibt waehrend der Aufnahme an.** Bisher wurde er vorher
  abgeschaltet und danach neu gestartet: gemessen 1,5 s pro Foto (0,7 s aus +
  0,8 s an). Canons Beispiel fasst den Live-View nicht an. Das war auch der
  sichtbare Unterschied zu anderer DSLR-Booth-Software auf derselben Hardware.

  Zusammen mit dem Punkt oben faellt damit rund die Haelfte der Wartezeit weg,
  noch bevor das Foto ueberhaupt eintrifft.

### Neu: Wartehinweis bei Spiegelreflex

Nach dem Blitz stand bisher das eingefrorene Vorschaubild auf dem Schirm — und
der Gast hielt es fuer sein Foto, bis Sekunden spaeter ein anderes Bild
erschien. Jetzt liegt ein deutlicher Balken mit "Foto wird aufgenommen…"
darueber, bis das echte Bild steht.

- **Nur bei Kameratyp canon/nikon.** Bei der Webcam-Flotte ist das Foto so
  schnell da, dass eine Einblendung nur flackern wuerde — dort aendert sich
  nichts.
- Der Text existierte bereits in allen sieben Sprachen
  (`session.capture_loading`) und war seit einem frueheren Umbau verwaist.

### Weiterhin offen

Warum die Kamera trotz hoerbarem Ausloesen nichts auf der Karte ablegt, ist
noch nicht abschliessend geklaert. Der Messmodus `--dslr-test` aus 2.4.51
beantwortet genau das in einem Durchlauf und wurde noch nicht gefahren.

---

## [2.4.51] - 2026-08-24 - Messen statt raten: DSLR-Ausloesetest

> Christian nach dem Test: "das ergebnis ist katastrophal und nicht verwendbar
> (...) ich denke die ganze herangehensweise ist fuer die dslr falsch.
> dslr-booth laeuft ja auch auf der gleichen hardware und das problemlos
> fluessig mit dslr!!"
>
> Der Einwand ist berechtigt. Ueber vier Testrunden wurde jeweils EINE
> Vermutung geaendert und ein neuer Build gebaut — ohne Ergebnis. Das war die
> falsche Methode.

### Befund aus dem Box-Log vom 24.08.2026

Die Kamera loest hoerbar aus (Spiegel), aber auf der Karte kommt nichts an:
Der Zaehler blieb ueber alle drei Aufnahmen bei **1732**.

Wohin die 13,5 Sekunden pro Foto gehen:

| Schritt | Dauer |
|---|---|
| Live-View stoppen | 0,7 s |
| Ausloesen | 1,0 s |
| **Warten auf ein Foto, das nicht kommt** | **10,3 s** |
| Live-View wieder starten | 0,8 s |
| Notbild bauen | 0,7 s |

### Neu: `--dslr-test`

Ein eigener Messmodus, der in EINEM Durchlauf fuenf Ausloese-Varianten
durchprobiert und misst, welche wirklich ein Foto liefert:

| | Variante |
|---|---|
| A | Live-View AN + Ausloeser ganz durch (Canons eigener Beispielweg) |
| B | Live-View AN + halb druecken, dann ganz durch ohne AF-Zwang |
| C | Live-View AN + TakePicture |
| D | Live-View AUS + TakePicture (der bisherige Weg der Box) |
| E | Live-View AUS + Ausloeser ganz durch |

Er beobachtet dabei BEIDE Wege gleichzeitig (Speicherkarte und
Direktdownload) und nennt am Ende die schnellste funktionierende Variante.
Liefert keine ein Foto, spricht das fuer die Kamera selbst statt fuer die
Software — auch das sagt der Bericht mit konkreten Pruefpunkten.

Aufruf: `fexobooth.exe --dslr-test`

### Geaendert

- **Wartezeit auf die Karte von 10 s auf 6 s.** Eine EOS 2000D schreibt ein
  JPEG in ein bis zwei Sekunden. Ist nach sechs Sekunden nichts da, kommt auch
  nichts mehr — weiteres Warten kostet den Gast nur Zeit vor einem
  eingefrorenen Bild.

### Bewusst NICHT geaendert

Der Ablauf schaltet den Live-View vor jeder Aufnahme ab und danach wieder an
(zusammen ~1,5 s). Canons eigenes Beispiel tut das nicht. Das ist der naechste
Verdacht — aber er wird erst nach dem Messlauf umgestellt, nicht auf Verdacht.
Genau dieses Vorgehen hat die letzten vier Runden gekostet.

### Weiterhin offen

- Foto in der Collage stimmt nicht mit dem Foto im Weiter-Bildschirm ueberein
- Aufnahmen sind ueberbelichtet

Beides betrifft aktuell die Notbilder aus dem Live-View, nicht echte Fotos.
Ob es danach noch besteht, zeigt sich erst, wenn die Aufnahme steht.

---

## [2.4.50] - 2026-08-21 - Das Foto lag auf der Karte, die Box sah es nur nicht

> Christian: "keine verbesserung aber vom geraeusch her macht die kamera fotos,
> ich hoere den spiegel" und "vor allem wenn das ausloesegeraeusch kam passiert
> ewig nichts"
>
> Das Spiegelgeraeusch war der entscheidende Hinweis: Die Kamera arbeitete, die
> Software bekam es nur nicht mit.

### Behoben

- **Die Box hat neue Fotos auf der Speicherkarte nicht bemerkt.** Das EDSDK
  merkt sich den Inhalt eines Verzeichnis-Objekts beim ersten Abfragen. Die
  Warteschleife holte das Verzeichnis EINMAL und befragte danach immer dasselbe
  Objekt — und bekam deshalb bis zum Timeout den eingefrorenen Stand von vorhin
  zurueck, auch nachdem die Kamera laengst gespeichert hatte.

  Der Beweis stand in zwei Logs derselben Box:

  | Test | Bildanzahl beim Start der Wartezeit |
  |---|---|
  | 12:01 | 1726 |
  | 12:16 | **1729** |

  Zwischen beiden Durchlaeufen sind DREI Fotos dazugekommen — die Kamera hat
  also ausgeloest und gespeichert. Innerhalb der Wartezeit stieg die Zahl
  trotzdem nie.

  Jetzt wird bei jedem Durchgang frisch nachgesehen (Karte → DCIM → Ordner neu
  geholt). Nachgestellt: Ein Foto, das 1,2 s nach dem Ausloesen auf der Karte
  landet, wird nach **1,4 s** erkannt statt gar nicht.

  Damit erledigt sich auch das "nach dem Ausloesegeraeusch passiert ewig
  nichts": Das waren die vollen 10 Sekunden Timeout bei jedem Foto.

- **Falscher Verwacklungs-Alarm bei jedem Foto.** Die Belichtungszeit `0x00`
  bedeutet "kein Wert" — in den Vollautomatik-Modi legt die Kamera Zeit und
  Blende erst beim Ausloesen fest. Das Log las das als "sehr lange Zeit" und
  warnte bei jeder Aufnahme vor Verwacklung.

### Hinweis zur Fehlersuche

Die Zeile "Aktuelle Bildanzahl: 1726" stand seit 2.4.48 im Log. Sie war die
ganze Zeit der Schluessel — sie musste nur mit dem naechsten Testlauf
verglichen werden. Deshalb schreibt die Wartschleife jetzt den Stand vorher
und nachher mit und meldet, wie lange es bis zum Auftauchen des Fotos gedauert
hat.

---

## [2.4.49] - 2026-08-21 - Die Kamera hat gar nicht ausgeloest

> Christian: "canon kameras liefen immer zuverlaessig ohne sd karte!" und
> "wie gesagt in einer alten version hat das schon mal viel besser
> funktioniert! ich will das das auch ohne sd karte funktioniert"

Beide Hinweise haben gestimmt und direkt zu zwei Fehlern gefuehrt.

### Behoben

- **Die Kamera hat auf den Ausloesebefehl gar nicht reagiert.** Der Befehl
  `TakePicture` gibt der Kamera den ganzen Ablauf inklusive Scharfstellen vor.
  Findet der Autofokus nichts — und im dunklen Box-Inneren findet er oft
  nichts — **loest die Kamera einfach nicht aus**. Der Befehl meldet trotzdem
  Erfolg, weil er korrekt uebermittelt wurde.

  Im Box-Log stand das schwarz auf weiss:

      [3/5] ✓ Kamera ausgeloest!
      Aktuelle Bildanzahl: 1726
      Timeout nach 10.0s - kein neues Bild erkannt

  Karte lesbar, Ordner gefunden, 1726 Bilder gezaehlt — und es kam keins dazu.

  Jetzt laeuft es wie bei einem Menschen am Ausloeser: **halb druecken**
  (Autofokus arbeitet), **ganz durchdruecken** (Aufnahme, auch bei unsicherem
  Fokus), **loslassen**. Der Autofokus bleibt damit voll aktiv — in einer
  Mietbox unverzichtbar, weil Gaeste unterschiedlich weit weg stehen und sich
  bewegen — kann die Aufnahme aber nicht mehr verhindern. Ein leicht
  unscharfes Foto ist besser als gar keines.

- **Der Rueckkanal fuer Boxen ohne Speicherkarte ist wiederhergestellt.** Bis
  zum 09.03.2026 wurde `EdsSetObjectEventHandler` direkt aufgerufen — in dieser
  Fassung liefen die Canon-Boxen ohne Karte. Im Commit 841de6c ("Collage
  Nochmal/Weiter Buttons, Template-Overlay Default, Capture-Optimierung")
  wurde der Aufruf beilaeufig in einen Hintergrundfaden verlegt.

  Das ist genau der Fehler: Das EDSDK arbeitet mit COM im STA-Modell, ein
  Rueckruf gehoert dem Faden, der die Kamera geoeffnet hat. Aus einem anderen
  Faden muss COM den Aufruf dorthin vermitteln — dabei blieb er haengen. Der
  Kommentar behauptete, der Handler sei "trotzdem registriert"; die Logs
  beweisen das Gegenteil.

  Der direkte Aufruf ist wiederhergestellt, mit einem Wachhund, der es ins Log
  schreibt, falls doch etwas haengt.

- **Log-Versand vom Service-Menue ging nicht** ("'function' object has no
  attribute 'get'"). Im Dialog heisst die Konfiguration `config_data`;
  `self.config` ist die geerbte Tk-Methode zum Einstellen von Widgets.

### Noch offen

- **Im Standbild wird etwas anderes gezeigt als im finalen Foto.** Zwei
  Ursachen: der Zeitversatz (schrumpft, sobald echte Fotos ankommen) und der
  unterschiedliche Bildausschnitt von Vorschau und Foto. Letzteres ist ein
  eigenes Thema und wird erst angefasst, wenn die Aufnahme steht.

---

## [2.4.48] - 2026-08-21 - Die Speicherkarte war die ganze Zeit da

> Christian, mitten im Test: "halt, bei dieser testbox ist doch eine sd karte
> in der kamera drin! das ist aber nicht immer der fall"
>
> Damit war klar, dass die Box eine Karte uebersehen hat, die nachweislich
> steckte — und die Suche fuehrte auf einen Fehler, der beide Wege zur Kamera
> gleichzeitig blockiert hat.

### Behoben

- **Ein falsches Speicher-Layout liess die Box jede Speicherkarte uebersehen.**
  In `EdsDirectoryItemInfo` stand `size` als 32-Bit-Zahl. Der offizielle
  Canon-Header EDSDKTypes.h sagt `EdsUInt64 size` — **64 Bit**:

  | Feld | bisher gelesen ab Byte | richtig ab Byte |
  |---|---|---|
  | size | 0 | 0 |
  | isFolder | 4 | **8** |
  | szFileName | 16 | **20** |

  Ab dem zweiten Feld war alles um 4 Bytes verschoben. `isFolder` las die
  oberen 32 Bit der Dateigroesse — bei normalen Dateien also 0, "kein Ordner".
  Der Dateiname wurde ab der falschen Stelle gelesen und kam leer an.

  Nachgestellt mit den Bytes, die eine Kamera fuer den Ordner "DCIM" schickt:

  | | isFolder | Name | Ergebnis |
  |---|---|---|---|
  | alter Code | 0 | `b''` | "Keine SD-Karte" |
  | neuer Code | 1 | `b'DCIM'` | Karte erkannt |

  Die Pruefung `name == "DCIM" and isFolder` konnte damit **nie** zutreffen.
  Die Box meldete "Keine SD-Karte (DCIM nicht gefunden)", obwohl eine Karte
  steckte, und wich auf den Host-Download aus — der seinerseits kaputt war
  (Rueckkanal nie eingerichtet, siehe 2.4.47). Beide Wege zur Kamera waren
  gleichzeitig blockiert. Das ist der Grund, warum ueberhaupt kein einziges
  echtes DSLR-Foto ankam.

- **Eine leere Speicherkarte gilt nicht mehr als "keine Karte".** Vorher war
  der DCIM-Ordner das Erkennungsmerkmal. Eine frisch formatierte Karte hat den
  aber noch nicht — die Kamera legt ihn erst mit dem ersten Foto an. Jetzt
  entscheidet, ob eine Karte da ist; fehlt der Ordner, wird er waehrend der
  Aufnahme erneut gesucht, sobald die Kamera ihn angelegt hat.

  Damit geht auch das erste Foto auf einer neuen Karte nicht mehr verloren.

### Was das fuer die Boxen bedeutet

- **Box MIT Karte** (wie die Testbox): laeuft ueber die Karte. Kein
  Ereignis-Weg, kein COM, keine 10 Sekunden Wartezeit — und echte DSLR-Fotos
  in voller Aufloesung statt hochgezogener Vorschaubilder.
- **Box OHNE Karte**: weiterhin Host-Download. Der bleibt der empfindlichere
  Weg; die Verbesserungen aus 2.4.47 greifen dort.

---

## [2.4.47] - 2026-08-21 - Log-Versand ans Dashboard + DSLR-Traegheit

> Christian nach dem 2.4.46-Test: "das ist alles viel zu traege und dauert
> ewig" — und: "koennen wir nicht einen button einbauen der die logs an das
> laravel dashboard schickt > dann kannst du sie direkt lesen und ich muss
> nicht immer mit dem stick hin und her kopieren?"

### Neu

- **Knopf „Logs ans Dashboard senden"** im Service-Menue (PIN 3198, Tab
  Allgemein). Die Box packt ihre juengsten Logdateien und schickt sie ueber
  denselben Kanal ans Dashboard, ueber den sie ohnehin schon ihren Heartbeat
  meldet. Dort stehen sie unter **Fotoboxen → Box-Logs**, nach Box gefiltert,
  mit Volltext-Filter und Farbmarkierung fuer Fehler und Warnungen.

  Keine Konfigurationsaenderung noetig: Die Adresse wird aus dem bereits
  hinterlegten Heartbeat-Endpunkt abgeleitet (`/booth/heartbeat` →
  `/booth/logs`), der Zugangsschluessel ist derselbe. Damit muss keine der
  rund 280 Boxen einzeln angefasst werden.

  Gemessen am echten Box-Log: 86 KB werden zu 12 KB gepackt uebertragen.

### Behoben

- **Der Rueckkanal der Kamera wurde nie eingerichtet — und die Software hat es
  behauptet.** In `set_object_event_handler` stand bisher der Kommentar
  „Handler funktioniert trotzdem" und die Funktion meldete Erfolg, obwohl der
  Aufruf haengen geblieben war. Das war eine Annahme, und sie war falsch: Im
  Box-Log vom 21.08.2026 kam bei ueber 200 Ausloesungen kein einziges
  Kamera-Ereignis an.

  Ursache: Der Aufruf laeuft in einem Nebenfaden und muss sein Ergebnis ueber
  COM an den Faden zurueckreichen, der die Kamera geoeffnet hat. Das gelingt
  nur, solange dieser Faden Windows-Nachrichten abarbeitet. Nach 0,5 Sekunden
  hoerte das auf — zu frueh. Jetzt sind es 4 Sekunden, und wenn es dann immer
  noch klemmt, meldet die Funktion ehrlich einen Fehlschlag.

- **12,7 Sekunden pro Foto.** Davon waren 10 Sekunden reines Warten auf ein
  Bild, das gar nicht kommen konnte. Die Wartezeit richtet sich jetzt nach der
  Lage: 1,5 s wenn der Rueckkanal nachweislich fehlt, 4 s wenn er da ist aber
  noch nie ein Bild gebracht hat, volle 10 s sobald einmal eines ankam. Damit
  ist auch der zu frueh wirkende Ausloese-Blitz weitgehend entschaerft — er
  kam nicht zu frueh, das Foto kam zu spaet.

### Bekannt und offen

- **Die Fotos sind unscharf, weil es keine Fotos sind.** Was in der Collage
  landet, ist das Vorschaubild mit 1056x704 statt eines DSLR-Fotos mit
  6000x4000 — auf Collagengroesse hochgezogen wirkt das zwangslaeufig
  verwaschen. Das loest sich erst, wenn echte Fotos ankommen.
- **Zuverlaessigster Ausweg waere eine SD-Karte in der Kamera.** Dann holt die
  Box die Bilder direkt von der Karte (Directory-Polling) und braucht den
  ganzen Ereignis-Weg nicht. Der Code kann das bereits; im Test meldete die
  Kamera „DCIM nicht gefunden" und fiel deshalb auf den Ereignis-Weg zurueck.

---

## [2.4.46] - 2026-08-21 - DSLR-Boxen: Fotos kamen nie an, Endlosschleife, Doppelbilder

> Anlass sind die Tests vom 21.08.2026 auf Box 245 und Box 248 (beide Canon
> EOS 2000D). Christian: „teilweise sind die boxen in einer art endlossschleife
> und manchmal wird immer wieder das gleiche bild in die collagen gelegt."
>
> Der Befund aus den Box-Logs war deutlicher als erwartet:
>
> | | Box 245 | Box 248 |
> |---|---|---|
> | Aufnahmen | 133 | 79 |
> | **davon echte DSLR-Fotos** | **0** | **0** |
> | Notloesung (Vorschaubild) | 133 | 79 |
> | Kamera-Ereignisse empfangen | **0** | **0** |
>
> Die Spiegelreflexkamera hat in diesen Tests kein einziges Foto geliefert.
> Jedes Bild in der Collage war in Wahrheit ein Vorschaubild mit 1056x704
> Pixeln statt eines 6000x4000-Fotos.

### Behoben

- **Die aufgenommenen Fotos kamen nie bei der App an.** Canons Kamera-Bibliothek
  meldet „Bild ist fertig" ueber die Windows-Nachrichtenschlange an den
  Programmfaden, der die Kamera geoeffnet hat — bei uns der Haupt-Faden mit der
  Bedienoberflaeche. Abgeholt wurde die Meldung aber nur in der Warteschleife
  der Aufnahme, und die laeuft seit dem Umbau auf Hintergrund-Aufnahme in einem
  NEBEN-Faden. Die Meldungen blieben ungelesen liegen.

  Beweis: In beiden Box-Logs steht kein einziges `>>> OBJECT EVENT` — der
  Rueckkanal hat bei 212 Ausloesungen kein einziges Mal gefeuert.

  Neu holt `app.py` die Ereignisse alle 50 ms im Haupt-Faden ab
  (`_starte_canon_event_takt`). **Nur bei Kameratyp `canon`** — bei den
  Webcam-Boxen der laufenden Flotte wird nicht einmal ein Timer angelegt.

- **Immer dasselbe Bild in der Collage.** `get_frame()` gab bei toter Kamera
  stillschweigend das zuletzt gelungene Vorschaubild zurueck — auch wenn es
  Minuten alt war. Die Foto-Notloesung hielt das fuer ein frisches Bild und
  brach ihre Wiederhol-Schleife nach dem ERSTEN Versuch ab. So landete dreimal
  exakt dasselbe Standbild in der Collage.

  Neu: Die Vorschau darf weiter ein Altbild zeigen (besser als ein schwarzer
  Schirm), die Foto-Aufnahme bekommt es nicht mehr (`allow_stale=False`).
  Zusaetzlich hat jedes Notbild einen Fingerabdruck — ein Wiederholungstaeter
  wird abgelehnt. Ein leerer Collagen-Platz ist besser als ein Doppelbild.

- **Endlosschleife bis zum Absturz.** Riss die USB-Verbindung ab, kostete jeder
  Vorschau-Versuch 1,5 Sekunden (3 Versuche à 0,5 s Pause) — und der
  Vorschau-Arbeiter ruft das mehrmals pro Sekunde. Box 245: 1.611 Fehlversuche
  ueber 29 Minuten. Box 248 fror komplett ein, Windows meldete sie um 10:28 als
  „reagiert nicht" (AppHang).

  Neu gilt nach einer verlorenen Runde eine Ruhepause von 5 Sekunden, in der
  sofort zurueckgekehrt wird. Gemessen: 30 Aufrufe brauchen jetzt 0,000 s
  statt rund 45 Sekunden Blockade.

- **Die Kamera fand nie zurueck.** Eine Wiederherstellung gab es nur fuer das
  Abschalt-Ereignis `0x301`. Die real auftretenden Faelle — DEVICE_BUSY und
  COMM_DISCONNECTED — haben sie nie ausgeloest. Neu wird die Verbindung bei
  jedem Verbindungsfehler neu aufgebaut (gedrosselt auf hoechstens alle 10 s).

- **Die EDSDK-Fehlertabelle war falsch und hat die Fehlersuche in die Irre
  gefuehrt.** Gegen den offiziellen Canon-Header `EDSDKErrors.h` geprueft
  (liegt im Repo unter `EDSDK/.../Header/`):

  | Code | stand im Log als | ist in Wahrheit |
  |---|---|---|
  | `0x81` | INVALID_PARAMETER | **DEVICE_BUSY** — Kamera belegt |
  | `0xc1` | UNKNOWN | **COMM_DISCONNECTED** — USB-Verbindung weg |
  | `0x88` | UNKNOWN | **DEVICE_DISK_ERROR** |
  | `0xa102` | EVF_INTERNAL_ERROR | **OBJECT_NOTREADY** — harmlos |

  Wer „INVALID_PARAMETER" las, suchte den Fehler im eigenen Code. Tatsaechlich
  meldete die Kamera „ich bin beschaeftigt" bzw. „das USB-Kabel ist weg" — ein
  Hardware-Problem. Ausserdem standen zwei Einzelkonstanten falsch
  (`EDS_ERR_DEVICE_BUSY`, `EDS_ERR_SESSION_ALREADY_OPEN`), weshalb
  `open_session()` die Lage „Kamera noch belegt" nie erkannte.

  `0xa102` laeuft jetzt als DEBUG statt als ERROR — es ist der Normalfall
  waehrend der Live-View-Anlaufzeit und hat pro Abend zehntausende rote Zeilen
  erzeugt, zwischen denen die echten Fehler untergingen.

### Dev-Mode-Logging

- **Foto-Bilanz in jeder Zeile**: `echt / Notloesung / leer`. Damit ist auf
  einen Blick sichtbar, ob die Kamera wirklich Fotos liefert — genau das war
  in den alten Logs nicht zu sehen.
- **Ereignis-Zaehler**: Jedes Kamera-Ereignis wird durchnummeriert. Bleibt der
  Zaehler auf 0, ist der Rueckkanal tot.
- **Diagnose bei „kein Bild"**: unterscheidet jetzt „Kamera hat nicht
  ausgeloest" von „ausgeloest, aber Download scheiterte".
- **Kamera-Zustand vor jedem Ausloesen**: Akkustand, Programmwahlrad,
  Fokus-Art — alle drei koennen ein Ausloesen verhindern, ohne dass die
  Software etwas falsch macht.
- **Bild-Fingerabdruck** bei jeder Notloesung: Doppelbilder sind im Log sofort
  erkennbar.
- **Klartext bei Ausloesefehlern**: z. B. „Kamera konnte nicht scharfstellen —
  Objektiv auf manuellen Fokus (MF) stellen."
- **Wiederholungen gedrosselt**: identische Fehler nur noch jede 20. Runde.

### Nicht angefasst

`webcam.py` und `session.py` wurden bewusst **nicht** veraendert — die laufende
Flotte arbeitet mit Webcams und darf von dieser Reparatur nicht beruehrt
werden. `app.py` hat ausschliesslich Ergaenzungen bekommen, die hinter einer
Abfrage auf `camera_type == "canon"` liegen.

---

## [2.4.45] - 2026-08-20 - Umschalten pro Foto ersatzlos raus, Aufloesung per Regler

> Christian, nachdem der Dauerbetrieb auf Box 101 ueber drei Sessions gemessen
> war: „die volle aufloesung macht den live view zwar etwas laggyer aber das
> ist verkraftbar. dafuer haben wir nicht den ausloesedelay." Und danach:
> „den umschaltmist verwerfen wir komplett".
> Anlass ist eine Kundenbeschwerde ueber die „doppelte Ausloesung".

### Geaendert

- **Die Kamera laeuft dauerhaft in EINER Aufloesung.** Das Umschalten pro Foto
  (Vorschau 640x480 → Foto 1920x1080 → zurueck) ist ersatzlos entfallen —
  auch als Schalter oder Notnagel. Gemessen auf Box 101, drei Sessions:

  | | Umschalten | fest |
  |---|---|---|
  | Ausloese-Verzoegerung | **1842 ms** | **86 ms** |
  | LiveView | 8,5 Bilder/s | 6,9 Bilder/s |

  Der Blitz kam bisher rund 1,8 Sekunden vor der Belichtung — genau das hat
  der Kunde als „zwei Ausloesungen" wahrgenommen. Der Preis sind 19 % weniger
  Vorschaubilder.

- **Regler statt zweier Textfelder.** Im Admin-Menue (Tab Kamera) waehlt ein
  Schieberegler die Aufloesung; sie gilt fuer Vorschau UND Foto, denn das Foto
  kommt aus demselben Bildstrom. Unter dem Regler steht die Folge der Wahl
  („1920 x 1080 — rund 14 Bilder/s · beste Fotoqualität"), damit niemand blind
  waehlt.

  **Grundwert ist die hoechste Stufe** — eine frisch installierte Box laeuft
  also in Full HD, ohne dass jemand etwas umlegen muss.

  Feste Stufen statt freiem Eintippen: Ein Tippfehler wie 2561x1440 ergibt
  eine Aufloesung, die keine Kamera liefert — die Box haette sich dann still
  etwas anderes ausgehandelt.

- **Untergrenze 1280x720.** Gemessen kostet 720p praktisch genauso wenig wie
  480p (30,5 gegen 29,8 Bilder/s), erst 1080p halbiert die Rate. Unterhalb von
  720p gewinnt man keine Fluessigkeit mehr, verliert aber Bildqualitaet — und
  da das Foto aus demselben Strom kommt, waere ein 640x480-Foto fuer den Druck
  unbrauchbar.

- **`camera_dauerbetrieb_hd` und `live_view_resolution` entfallen als
  Entscheidungsgrundlage.** Bestehende Boxen brauchen keine Handarbeit: Ihr
  Wert `single_photo_width/height` ist auf der ganzen Flotte 1920x1080 und
  wird nur noch auf die naechste gueltige Stufe gerundet.

### Behoben

- **Die Sekunde nach jedem Zwischen-Video ist weg.** In `_cleanup_vlc` stand
  ein `join(timeout=1.0)`, mit dem der Oberflaechen-Thread auf das
  VLC-Aufraeumen wartete. Das Aufraeumen braucht aber genau diesen Thread, um
  das VLC-Kindfenster abzubauen — das Warten hat die Verzoegerung also selbst
  verursacht und danach ohnehin aufgegeben. Belegt aus dem Feld-Log:

  ```
  41.196  Video zu Ende
  42.211  "VLC-Cleanup dauert >1s"      <- exakt 1,015 s = das Zeitlimit selbst
  43.051  "VLC-Ressourcen freigegeben"  <- erst 73 ms NACHDEM der Thread wieder lief
  ```

  Zusaetzlich rief der Aufraeum-Thread unnoetig `get_state()` und zog damit an
  derselben Sperre wie der Statusabruf im Oberflaechen-Thread.

### Weiterhin offen

- Der **Video-Freeze** ist NICHT behoben. Das Video nach Foto 2 lief zweimal
  viel zu lang (17,5 s und 33,5 s statt 2,0 s). Die Hypothese „kurz nach einer
  Kamera-Umschaltung" ist widerlegt — das Video mit dem kuerzesten Abstand
  (1,08 s) lief sauber. Der `join()`-Fix oben ist ein anderer Fehler.
- Hoehere Stufen als 1080p stehen in der Leiter bereit (1440p, 2160p), werden
  aber erst angeboten, wenn eine Kamera-Messung belegt, dass die
  angeschlossene Kamera sie liefert. Diese Verbindung fehlt noch.

---

## [2.4.44] - 2026-08-20 - Etappe 2 nachgebessert: Schalter haelt wirklich dicht, Kamera faengt sich selbst

> Ergebnis der Gegenpruefung von 2.4.43. Nichts davon ist eine neue Funktion —
> es sind die Loecher, die eine Testbox-Veranstaltung still ruiniert haetten,
> und zwei Stellen, an denen sich eine Box mit AUSGESCHALTETEM Schalter doch
> anders verhalten haette als die uebrige Flotte.

### Behoben — Boxen mit ausgeschaltetem Schalter

- **Der Puffer wird wieder immer 2x geleert, ausser im echten Dauerbetrieb.**
  Vorher haing die Ersparnis daran, ob gerade umgeschaltet wurde. Das trifft
  auch eine ganz normale Flottenbox: Geht ein Preview-Restore einmal nicht
  durch (das Log schreibt dann „nicht bestaetigt" und versucht es nie wieder),
  steht die Kamera weiter auf 1080p — und ausgerechnet in dieser Lage, mit der
  hoechsten Gefahr eines alten Pufferbildes, waere nur noch 1x geleert worden.
  Also genau das gemeldete „als wenn 2 Fotos geschossen werden", auf Boxen
  ohne Schalter. Jetzt haengt die Ersparnis strikt am Schalter.

- **Der Dauerbetrieb wird nicht mehr an der Aufloesung erraten.** Session und
  System-Test haben vorher allein verglichen, ob die Vorschau schon so gross
  ist wie das Foto. Bei 640x480 gegen 1920x1080 ging das gut — aber die
  Foto-Aufloesung ist im Admin frei eintippbar, und eine kuenftige Kamera, die
  kein 640x480 liefert, haette die ganze neue Betriebsart von selbst
  eingeschaltet. Jetzt muessen drei Dinge zusammenkommen: Schalter an, Kamera
  hat den Dauerbetrieb wirklich angenommen, und es steht kein Umschalten an.

- **Auch das Oeffnen haengt jetzt am Schalter** (`set_dauerbetrieb_hd()` vor
  `initialize()`). Vorher entschied allein die angeforderte Breite. Wer
  `live_view_resolution` von Hand hochsetzt, bekam damit die neue Betriebsart
  ungefragt. Das zweistufige Warm-Oeffnen bleibt aber bei jeder grossen
  Aufloesung aktiv — es ist der Schutz gegen das Einfrieren (Box 224) und
  nicht Teil der neuen Betriebsart.

### Behoben — Langlauf auf der Testbox

- **Die Selbstheilung ist zurueck.** Der klassische Weg hatte sie eingebaut,
  ohne dass es jemandem auffiel: Er setzte vor JEDEM Foto 1920x1080 neu.
  Rutschte die Kamera zwischendurch ab (USB-Wackler, Energiesparen,
  Treiber-Reset), zog der naechste Auslueser sie wieder gerade. Der
  Dauerbetrieb setzte gar nichts mehr und glaubte seinem eigenen Merker —
  ab dann waeren bis Abendende still Fotos in 640x480 gespeichert und
  gedruckt worden, ohne Fehlermeldung. Jetzt wird der Ist-Zustand nach jedem
  Foto am WIRKLICH gelieferten Bild nachgezogen; ist es zu klein, verlaesst
  die Box den Dauerbetrieb, macht **fuer dieses Foto sofort einen zweiten
  Anlauf auf dem klassischen Weg** und arbeitet danach wieder wie die Flotte.
  Auf Boxen mit ausgeschaltetem Schalter bleibt das folgenlos: Dort ueberschreibt
  der Preview-Restore nach jedem Foto denselben Wert ohnehin.

- **Das Warm-Oeffnen beweist 1080p jetzt an einem echten Bild.** Vorher wurde
  nur die gemeldete Eigenschaft geprueft (`cap.get(...)`) — das ist das
  Versprechen des Treibers, nicht die Wirklichkeit. Jetzt wird nach dem
  Hochsetzen ein Bild gelesen und seine Groesse geprueft. Geht das schief,
  passiert es beim Oeffnen waehrend des Intro-Videos statt beim ersten Foto
  vor einem Gast.

- **Der Rueckfall laesst die Box nicht mehr in YUY2 zurueck.** Lehnte die
  Kamera MJPG beim Hochsetzen auf 1080p ab, blieb der dauerhafte Merker
  „kann kein MJPG" stehen — auch nach dem Rueckfall auf 640x480. Die Box haette
  den ganzen Abend unkomprimiert gearbeitet (~5 Bilder/s) und waere damit
  SCHLECHTER dran gewesen als eine normale Flottenbox, obwohl das Log
  „arbeitet ab jetzt exakt wie die uebrige Flotte" versprach. Der Merker wird
  jetzt genau dann zurueckgenommen, wenn er erst beim HD-Versuch entstand.

- **Die Blitz-Notbremse steht auf 700 ms statt 400 ms.** Im Box-Log dauerte
  allein das Auslesen 236 ms; dazu kommen Sperre, Farbumwandlung auf 1080p und
  die Sofortanzeige. Bei 400 ms waere die Notbremse regelmaessig zu frueh
  gekommen — und haette den gemeldeten Effekt in klein wieder erzeugt.

- **Der System-Test bricht nicht mehr ab**, wenn in der Foto-Aufloesung etwas
  steht, das keine Zahl ist. Er laeuft dann klassisch weiter.

### Kleinigkeit

- `config.example.json` enthaelt `camera_dauerbetrieb_hd: false` jetzt
  ausdruecklich. Funktional aendert das nichts (der Grundwert griff auch
  vorher), aber der Schalter war in der Beispieldatei unsichtbar.

---

## [2.4.43] - 2026-08-20 - Etappe 2 von 2: Kamera dauerhaft in Full HD (umschaltbar)

> Anlass (Christian): „wenn eine session gemacht wird und ein foto geschossen
> wird (blitz kommt) dann wird ganz kurz ein foto in der collage gezeigt aber
> das ist dann nicht das foto was auch anschliessend im vollbild gezeigt
> wird... als wenn 2 fotos geschossen werden!"

### Das Problem

Die Kamera laeuft in der Vorschau auf 640x480 und wird fuer JEDES Foto auf
1920x1080 umgeschaltet und danach zurueck. Aus dem Box-Log:

```
High-Res Capture Timing: set=1572ms, verify=0ms, grab=0ms, read=236ms,
                         restore=0ms, total=1810ms
Sichtbare Capture-Wartezeit bis Fotoanzeige: 1842ms
Preview-Restore Timing: 1920x1080 -> 640x480, set=1251ms
```

Der Blitz kommt sofort, belichtet wird rund 1,8 Sekunden spaeter. Wer sich
dazwischen bewegt, ist auf dem Foto nicht mehr in der Pose — es sieht aus, als
haette die Box zwei verschiedene Fotos gemacht.

### Neu

- **Schalter „Kamera dauerhaft in Full HD (nur Testbox)"** im Admin-Menue
  (PIN 3198) → Tab **Kamera**, direkt unter „Template im LiveView anzeigen".
  Konfigschluessel: `camera_dauerbetrieb_hd`, **Grundwert AUS**.

  Ist er AN, wird die Kamera EINMAL in Fotoaufloesung geoeffnet und bleibt
  dort. Das Umschalten pro Foto entfaellt komplett — `get_high_res_frame`
  erkennt von allein „Zielaufloesung ist bereits aktiv". Erwartete sichtbare
  Wartezeit: **~150-300 ms statt 1842 ms.**

  Grundlage ist die Kamera-Messung auf der echten Box (Software beendet):

  | Aufloesung | Bilder/s | pro Bild | davon Warten | davon Rechnen |
  |---|---|---|---|---|
  | 640x480 MJPG | 29,8 | 33,6 ms | 0,0 ms | 33,5 ms |
  | 1280x720 MJPG | 30,5 | 32,8 ms | 0,0 ms | 32,7 ms |
  | 1920x1080 MJPG | 13,9 | 71,9 ms | 0,0 ms | 71,8 ms |

  „0 ms Warten" heisst: Die Kamera ist nie der Flaschenhals. Tragfaehig wurde
  der Dauerbetrieb erst durch Etappe 1 (2.4.41): Die Vorschau-Aufbereitung
  kostet bei 1080p jetzt 0,14 ms statt 4,19 ms.

- **Warm-Oeffnen statt Kalt-1080p.** Die Kamera wird zuerst klein geoeffnet
  (640x480), EIN Bild gelesen — damit der DirectShow-Graph laeuft — und erst
  dann hochgesetzt. Genau die Sequenz, die `get_high_res_frame` heute
  tausendfach pro Woche im Feld fehlerfrei faehrt. Grund: Ein KALTES Oeffnen
  in 1920x1080 hat am 13.08. Box 224 eingefroren (Log endet exakt bei
  „Kamera geöffnet").

- **Sauberer Rueckfall.** Liefert die Kamera kein 1080p oder lehnt sie MJPG ab
  (YUY2 passt bei 1080p nicht durch USB2 → ~5 Bilder/s), geht die Box von
  selbst auf 640x480 zurueck, schreibt eine deutliche Warnung ins Log und
  arbeitet exakt wie die uebrige Flotte weiter. Lieber langsam und richtig
  als kaputt.

- **Der Blitz haelt jetzt, bis das Foto da ist** (nur im Dauerbetrieb). Sonst
  waere zwischen Blitz-Ende (90 ms) und Fotoanzeige (~150-300 ms) wieder kurz
  das eingefrorene Vorschaubild zu sehen — dasselbe „zweite Foto", nur
  10x kuerzer. Notbremse nach 700 ms (bis 2.4.44: 400 ms), damit bei einem
  gescheiterten Capture nie ein weisser Bildschirm stehenbleibt.

### Geaendert

- Die Vorschau-Aufloesung wird nur noch an EINER Stelle bestimmt
  (`vorschau_aufloesung()` in `src/config/config.py`). Vorher stand die
  Rechnung `int(live_res * 0.75)` dreimal getrennt im Code — dieselbe Box
  haette je nach Weg (mit Intro-Video, ohne, im Selbsttest) in
  unterschiedlichen Aufloesungen laufen koennen.
- Der Puffer wird vor dem Foto nur noch 1x statt 2x geleert — **nur im
  Dauerbetrieb** (praezisiert in 2.4.44). Jedes ueberfluessige `grab()` kostet
  bei 1080p bis zu ein volles Bildintervall (71,9 ms) und wirft genau den
  Moment weg, in dem der Blitz kam.
- Der Preview-Restore nach dem Foto entfaellt im Dauerbetrieb ersatzlos
  (er pausierte den LiveView und bremste den naechsten Countdown aus).
- Der System-Test oeffnet die Kamera in der Betriebsart, die die Box wirklich
  hat, und bewertet die Bilder/s im HD-Betrieb gegen eine eigene Schwelle
  (9,0 statt 12,0) — sonst haette er auf der Testbox falschen Alarm gegeben.
- Vollbild-Vorschau (ohne Template-Overlay): Wird das Bild VERKLEINERT, kommt
  der Resize jetzt vor dem Spiegeln/Umfaerben. Bei 1080p spart das rund die
  Haelfte der Punkte pro Bild.

### Wichtig zu wissen

- **Auf den ~280 Boxen im Feld aendert sich ohne Umlegen des Schalters
  NICHTS.** Der klassische Weg in `initialize()` ist Zeile fuer Zeile
  unveraendert geblieben.
- **Das gespeicherte Foto aendert sich nicht** — 1920x1080, JPEG 95,
  ungespiegelt. Collage/Druck bleiben 1800x1200.
- **Die Vorschau wird nicht fluessiger, sondern etwas langsamer**
  (ehrlicher formuliert in 2.4.44): Das Kamerabild kostet bei 1080p 71,9 statt
  33,6 ms, das Einpassen ins Collagen-Fach rund 15 ms mehr. Grobe Erwartung:
  von heute ~9,5 auf ~7 Bilder/s. Gewinn dieser Etappe sind der passende Blitz
  und der passende Bildausschnitt — nicht mehr Bilder pro Sekunde.
- **Der Bildausschnitt der Vorschau aendert sich sichtbar** und das ist so
  gewollt: heute 4:3 (oben/unten beschnitten), im Dauerbetrieb 16:9 — also
  exakt derselbe Ausschnitt wie das spaetere Foto. Der Gast sieht endlich,
  was gedruckt wird.

---

## [2.4.42] - 2026-08-20 - Stress-Test laesst die Videos nicht mehr aus

> Anlass (Christian): „mir faellt gerade erst auf, dass im Stresstest im
> Dev-Mode die Videos uebersprungen werden! das ist ja auch bloed oder?" —
> und auf den Vorschlag, nur jede fuenfte Runde mit Video zu fahren:
> „nein die videos muessen immer laufen! sonst ist es nicht realistisch!"

### Geaendert

- **Der Stress-Test spielt jetzt alle Videos ab** — Start-, Zwischen- und
  Endvideo. Bisher wurden sie „fuer schnellere Zyklen" uebersprungen.

  Damit war ein ganzer Teilbereich vom Test ausgenommen: VLC starten, ins
  Fenster einbetten und wieder abbauen, Bildschirmwechsel
  Session → Video → Session, Kamera freigeben und neu holen, LiveView-Worker
  beenden und neu starten.

  **Genau dort trat am 20.08. auf Box 101 ein Freeze auf:** Ein Video von
  2,0 Sekunden lief 17,5 Sekunden, der Oberflaechen-Thread stand dabei
  16,7 Sekunden bei 22 % CPU. Der Stress-Test haette das nie gefunden, egal
  wie lange er laeuft — er lief durch und meldete „alles gut", waehrend das
  Loch genau dort war, wo er nicht hingeschaut hat.

  Der Preis sind weniger Foto-Zyklen pro Stunde. Das ist der Sinn der Sache:
  Ein Test, der nicht abbildet was im Betrieb passiert, ist keiner.

- `_stress_test_auto_proceed` greift beim Video-Bildschirm bewusst nicht ein
  (es behandelt nur „start", „filter" und „final"). Die Videos laufen also
  wirklich bis zum Ende durch, statt weggeklickt zu werden.

---

## [2.4.41] - 2026-08-20 - Vorschau: erst verkleinern, dann spiegeln (Etappe 1 von 2)

> Auftrag (Christian): „Nur die Vorschau-Aufbereitung umdrehen. Der Foto-Ablauf
> bleibt in dieser Etappe UNANGETASTET."

### Was geaendert wurde

Bisher wurde fuer JEDES Vorschaubild zuerst das **volle** Kamerabild gespiegelt und
umgefaerbt und erst danach auf das kleine Collagen-Fach verkleinert. Jetzt laeuft es
andersherum: **erst verkleinern und beschneiden, dann spiegeln und umfaerben.**
Spiegeln und Umfaerben arbeiten dadurch nur noch auf der Fachgroesse
(362x240 = 86.880 Punkte) statt auf dem ganzen Kameraframe.

Geaendert ausschliesslich in `src/ui/screens/session.py`:
`_prepare_live_frame`, `_compose_overlay_frame`, `_fit_frame_to_box_np`
(neu `_mirror_frame`). **Der Foto-Pfad ist nicht angefasst** — das gespeicherte Foto
bleibt 1920x1080, unskaliert und ungespiegelt.

### Was man davon merkt — ehrlich

Gemessen auf der Kette resize/spiegeln/beschneiden/umfaerben (ohne das
PIL-Compositing drumherum), Median aus 9 Serien:

| Vorschau-Aufloesung | vorher | nachher | Faktor |
|---|---|---|---|
| 320x240 | 0,13 ms | 0,13 ms | **1,0x — kein Gewinn** |
| 480x360 | 0,17 ms | 0,16 ms | 1,1x |
| 640x480 | 0,69 ms | 0,19 ms | 3,6x |
| 1280x720 | 2,47 ms | 0,26 ms | 9,4x |
| 1920x1080 | 5,42 ms | 2,82 ms | 1,9x |

**Wichtig:** Der Gewinn entsteht nur, wenn die Vorschau GROESSER ist als das
Collagen-Fach. Ist sie kleiner (320x240), vergroessert der Cover-Fit auf 362x271 —
dann sind es hinterher sogar minimal mehr Punkte, unterm Strich ein Nullsummenspiel.
Die `config.json` dieser Box steht auf `live_view_resolution: 320`, die Vorgabe in
`defaults.py` auf 640. **Auf einer Box mit 320 oder 480 wird man nichts merken.**
An `live_view_resolution` wurde bewusst nichts gedreht — das gehoert zu Etappe 2.

### Sieht die Vorschau anders aus?

Nein. Nachgerechnet ueber 320x240/640x480/1280x720/1920x1080 x drei Fachformen x
`rotate_180` an/aus: gleicher Bildausschnitt, gleiches Seitenverhaeltnis, gleicher
Beschnitt. Abweichung an echten Box-Fotos bei 640x480: **Mittelwert 0,00 von 255,
maximal 1** — praktisch bitgleich.

Ausnahme ab 1080p-Quelle: dort glaettet `pyrDown` vor dem Verkleinern (Aliasing-Schutz,
von Christian ausdruecklich gefordert). Das Bild wird dadurch etwas ruhiger, ist also
bewusst nicht woertlich identisch. Greift heute nicht — der Waechter verlangt
1704x960 Quellgroesse, bei 320/480/640/1280 macht er null Halbierungen.

### Zwei Fallen, die dabei vermieden wurden

- **Gespiegelt wird VOR dem Beschneiden.** Der mittige Beschnitt ist nicht immer
  symmetrisch (1920x1080 in ein 240x362-Fach: fit_w=643, Rest 403 = ungerade).
  Nach dem Beschnitt zu spiegeln haette den Ausschnitt um einen Pixel verschoben.
- **`fit_size` wird aus den ORIGINAL-Massen berechnet** und durchgereicht, nicht im
  Fit neu aus dem eventuell geschrumpften Bild — sonst haette ein `pyrDown` den
  Ausschnitt verschieben koennen.

---

## [2.4.40] - 2026-08-20 - Eine gescheiterte Namensabfrage galt als Beweis, dass die Kamera intern ist

> Anlass (Christian): „der test zeigt 0 gefundene kamera aber die logitech ist ja
> dran."

### Der Fehler in einem Satz

**Eine fehlgeschlagene NAMENSABFRAGE wurde als Beweis gewertet, dass die Kamera
INTERN ist.** Das sind zwei voellig verschiedene Dinge — und die Kamera stand
ueberhaupt nur in der Liste, WEIL cv2 sie erfolgreich oeffnen konnte. Sie war
also nachweislich da.

Aus dem Box-Log vom 20.08.2026:

```
10:27:31.176 DirectShow-Enumeration fehlgeschlagen: ... timed out after 10 seconds
10:27:31.177 DirectShow-Enumeration fehlgeschlagen, nutze PnP-Fallback
10:27:36.217 PnP Kamera-Abfrage fehlgeschlagen: ... timed out after 5 seconds
10:27:36.990 Keine externe Kamera gefunden! Interne Kameras ignoriert: ['Kamera 0']
10:27:37.639 Kamera gefiltert (Ghost): [0] Kamera 0
10:27:37.640 Webcams gefunden: 1 gesamt, 0 extern
10:27:47.922 DirectShow Kamera-Namen: ['c922 Pro Stream Webcam']   <- 11 s spaeter OK
```

Fehlte der Name, vergab `list_cameras()` den Platzhalter `"Kamera {i}"` —
und `find_best_camera()` warf genau diesen Platzhalter wieder weg
(`name_lower != f"kamera {cam['index']}"`). Ergebnis `-1` = „keine Kamera":
Warnung blinkt, Messung findet nichts, und der Waechter startete alle 2 s eine
neue Suche, die selbst ueber 10 s dauerte.

### Behoben

- **Die Namensabfrage laeuft nicht mehr ueber PowerShell, sondern in-process
  ueber `ctypes`** (keine neue Abhaengigkeit, Standardbibliothek). Dieselbe
  COM-Kette wie bisher im C#-Code: `ICreateDevEnum` → `IEnumMoniker` →
  `IPropertyBag`, jetzt zusaetzlich mit `DevicePath` neben `FriendlyName`.

  Gemessen waren **~4 ms echte Arbeit in ~560–670 ms Verpackung** (Prozessstart
  + CLR + `csc.exe`-Kompilierung bei JEDEM Aufruf). Auf dem Atom x5-Z8350 mit
  eMMC skaliert genau diese Verpackung und reisst die 10-s-Grenze — das war die
  Ursache der Fehlmeldung, nicht die Kamera. In-Process: **auf diesem Rechner
  2,6–6,6 ms** gemessen, ueber 200 Durchlaeufe stabil.

  Nebenbei fallen vier weitere Ausfallbilder weg: kein `%TEMP%` noetig, keine
  frische DLL fuer Defender/AMSI, kein ConstrainedLanguageMode-Problem, keine
  Codepage-Verstuemmelung bei Umlauten (BSTR ist UTF-16). Ausserdem ist
  `subprocess.run(timeout=)` auf Windows ohnehin keine harte Grenze: nach dem
  Kill laeuft ein zweites `communicate()` OHNE Timeout, waehrend das verwaiste
  `csc.exe` die Pipes haelt.

  Der PowerShell-Weg bleibt fuer diese Version als **zweiter Versuch** stehen —
  Robustheit vor Eleganz.

- **Drei Antworten statt zwei.** Jede Kamera wird als `extern`, `intern` oder
  **`unbestimmt`** eingeordnet. Die Regel `name_lower != f"kamera {index}"` ist
  ersatzlos entfallen; sie stammt vom 27.03.2026 und war gegen namenlose
  Phantom-Duplikate im Admin-Dropdown gebaut, nicht gegen eine gescheiterte
  Abfrage. Reihenfolge der Regeln: Name schlaegt Bus (interne Kameras haengen in
  manchen Geraeten intern per USB), danach Bus, danach Name-ohne-Intern-Wort.

- **Neue, unabhaengige Gegenprobe ueber die Registry** (`winreg`,
  KSCATEGORY_VIDEO, nur Eintraege mit `Control\Linked = 1`): „haengt gerade
  genau eine USB-Videoquelle dran?" Kosten **0,08 ms** gemessen, kein
  Prozessstart, kein Admin-Recht, keine Hardware wird angefasst. Ein
  `unbestimmtes` Geraet wird nur uebernommen, wenn ALLE vier Bedingungen
  gleichzeitig gelten: genau ein oeffenbares Geraet, Namensabfrage komplett
  gescheitert, kein Geraet als intern erkannt, und die Registry meldet genau ein
  verbundenes Videogeraet und das haengt am USB.

- **Der PnP-Fallback ist als Namensquelle ersatzlos gestrichen.** Er war
  gefaehrlicher als der gemeldete Bug: `Get-PnpDevice -Class Camera,Image` hat
  im Test **zwei Drucker und null Kameras** geliefert (die Klasse „Image"
  enthaelt Scanner/Multifunktionsgeraete). Diese Fremdnamen wurden positionsweise
  auf die cv2-Indizes geklebt — Index 0 (auf dem Miix die abgeklebte interne
  Kamera) haette „HP Color LaserJet…" geheissen, waere durch keinen Filter
  gefallen und als „externe Kamera" gewaehlt worden. Das haetten schwarze Fotos
  beim Kunden gegeben statt einer Warnung.

- **Namenszuordnung ueber den Geraeteindex statt ueber `len(cameras)`.** Vorher
  indizierte der Code mit der Anzahl der bisher erfolgreich geoeffneten Kameras:
  liess sich ein Index gerade nicht oeffnen (belegt vom Waechter, von der
  Messung, haengende interne Kamera), rutschten alle folgenden Namen um eine
  Position — dann trug die C922 den Namen der internen Kamera und wurde
  weggeworfen. Zweiter, vom Timeout voellig unabhaengiger Weg zu „0 gefundene
  Kameras".

- **`camera_index` wird nicht mehr aus Unwissen auf `-1` gesetzt** — aber auch
  nicht mehr aus Unwissen BEHALTEN. Bis 2.4.39 ueberschrieb ein einziger
  PowerShell-Aussetzer eine nachweislich funktionierende Einstellung —
  ausgerechnet in dem Fall, in dem die meisten Beweise fuer vorhandene Hardware
  vorlagen. Umgekehrt gilt aber genauso: ein Index, der einfach nur in der
  Config steht, ist kein Beweis fuer eine externe Kamera (der Grundwert ist `0`,
  und `0` ist auf dem Miix die abgeklebte interne Kamera). Ein bestehender Index
  bleibt deshalb nur mit **Beweis** stehen: in diesem Lauf per Geraetenamen
  bestaetigt, im Gedaechtnis per Name+DevicePath bestaetigt und laut Registry
  wieder am Bus, oder im Admin-Menue von Hand gewaehlt
  (`camera_index_manuell`). Sonst: `-1` und blinkende Warnung.

- **`-1` klebt nicht mehr fest.** `save_config()` schrieb die `-1` nach
  `C:\ProgramData\FexoBox`, und `_recover_machine_settings()` drueckte sie bei
  JEDEM Start wieder in die Config, bevor irgendetwas anderes passierte. Ein
  einziger Aussetzer konnte eine Box damit dauerhaft in den Blindzustand nageln.
  `-1` ist kein Maschinenwert, sondern ein Fehlerbefund — er wird nicht mehr
  gespeichert und ein bereits gespeicherter beim Lesen ignoriert. Betroffene
  Boxen werden beim ersten Start mit dieser Version davon befreit.

- **Kamera-Waechter: Blinken und Suchen sind getrennt.** Die Warnung blinkt
  weiter alle 2 s (reine Anzeige), die volle Suche laeuft im Problemfall
  hoechstens alle 20 s. Vorher plante der Waechter im `-1`-Zustand alle 2 s eine
  neue Suche, obwohl ein Durchlauf ueber 10 s dauerte — die Box war praktisch
  dauerhaft mit Kamerasuche beschaeftigt, auf einem Atom mit 4 GB. Genau dieser
  Zustand hat die groesste Kollisionsflaeche fuer den Heap-Absturz `0xc0000374`
  (Box 044). Preis: eine im Betrieb neu angesteckte Kamera wird schlimmstenfalls
  20 statt 2 Sekunden spaeter erkannt.

- **Es werden nur noch so viele Indizes geoeffnet, wie DirectShow meldet.** Auf
  einer Ein-Kamera-Box spart das vier Geraeteoeffnungen pro Suche — nach der
  PowerShell-Verpackung der groesste Einzelposten auf dem Atom.

### Admin-Menue

- Der Ghost-Filter (`name == "Kamera N"`) faellt. Gefiltert wird nach der
  Einordnung: `intern` ausblenden, `extern` normal, **`unbestimmt` anzeigen und
  kennzeichnen** (`[0] Kamera 0 (Name unbekannt)`). Bisher verschwand die
  einzige funktionierende Kamera in genau dem Moment auch aus dem Auswahlfeld —
  Christian hatte keinen manuellen Notausgang.
- Der Notbehelf `[0] Standard-Kamera` bei leerer Liste wird zu
  **`Keine Kamera gefunden`** — ohne Index. Vorher schrieb ein Klick auf
  Speichern ungeprueft `camera_index = 0`, auf dem Miix also die abgeklebte
  Kamera. Das war eines von drei Lecks in der Sperre.

### Neu: `kamera_erkennung.json`

Gedaechtnis **und** erstes dauerhaftes Diagnosemittel in einer Datei
(`C:\ProgramData\FexoBox`, update-sicher). Enthaelt Zeitpunkt, welcher Weg
genommen wurde (`ctypes` / `powershell` / gar keiner), Dauer, alle gefundenen
Geraete samt USB-Ja/Nein und VID/PID, den gewaehlten Index und die Begruendung
im Klartext.

Gelesen wird sie **nur** im unbestimmten Fall und nur mit dieser Aussage:
„Index N war zuletzt die bestaetigte externe Kamera, und genau dieses
USB-Geraet haengt laut Registry JETZT wieder dran." Verworfen wird sie, sobald
eine frische erfolgreiche Abfrage vorliegt, bei abweichender Geraetezahl, bei
nicht mehr verbundener VID/PID, bei mehrdeutiger Registry-Lage und bei kaputter
Datei. **Kein Zeitablauf** — das Risiko ist der Hardwaretausch, nicht das Alter.

Hintergrund: Am 20.08. lieferte dieselbe Box 11 Sekunden spaeter das richtige
Ergebnis; ein gemerktes Ergebnis haette den Aussetzer vollstaendig ueberbrueckt.
Und im Feld war bisher NICHTS sichtbar, weil das App-Log nur mit `--dev`
existiert.

### Monitoring

Der Heartbeat meldet drei zusaetzliche flache Felder: `camera_type`,
`camera_state` (`extern` / `unbestimmt` / `keine` / `unbekannt`) und
`camera_index`. Rein additiv, und er loest **keine** Kamerasuche aus — gelesen
wird nur `kamera_erkennung.json`. Bisher war voellig unmoeglich zu sagen, wie
viele der ~280 Boxen gerade blind sind.

> **Vor dem Rollout pruefen:** Der adminFexobox-Endpunkt muss unbekannte Felder
> tolerieren.

### Richtiggestellt

Die Behauptung, die abgeklebte interne Kamera „liefert nie ein Bild", ist im
gesamten Repo durch nichts belegt und physikalisch unwahrscheinlich: Klebeband
macht das Bild dunkel, es stoppt den Sensor nicht. Steht jetzt korrekt in
`src/main.py` und im Messbericht — wichtig, damit daraus niemand eine
Erkennungsregel baut („kein Frame = intern"). Der Rueckfall der Kamera-Messung
auf Index 0 bleibt, wird im Protokoll aber klar als **Notbehelf** benannt und
nutzt zuerst denselben Erkennungsweg wie die App.

### Bewusst NICHT gebaut

Kein Aufloesungstest (braucht ein Kalt-Oeffnen in 1080p — genau das hat Box 224
am 13.08. eingefroren), keine Helligkeits-/Schwarzbild-Schwelle (eine echte C922
in dunkler Location liefert ebenfalls dunkle Bilder — das wuerde die RICHTIGE
Kamera mitten im bezahlten Event verwerfen), kein MSMF-Gegencheck (unter MSMF
kann derselbe Index eine ANDERE Kamera treffen), kein MJPG-Test (der Code fuehrt
selbst einen `_mjpg_unsupported`-Merker), kein `comtypes`/`pywin32` (neue
Abhaengigkeit bzw. `CoCreateInstance` auf `ICreateDevEnum` scheitert dort
nachweislich), kein `pnputil`.

### Nachbesserung nach der Gegenpruefung (gleicher Tag)

Die Gegenpruefung hat am ersten Entwurf zwei Wege gefunden, auf denen die
abgeklebte interne Kamera doch als Fotokamera haette landen koennen, und eine
Abfrage ohne Zeitgrenze. Alle drei sind behoben:

- **Die „USB-Gegenprobe" ist ersatzlos raus.** Sie hat ein namenloses Geraet
  schon dann zur externen Kamera erklaert, wenn die Registry genau eine
  USB-Videoquelle meldete. Das beantwortet die falsche Frage: geprueft wurde
  „haengt eine USB-Kamera am Bus?", gebraucht wird „ist DIESER cv2-Index diese
  Kamera?". Ist das Kabel der C922 raus (bei ~280 Mietboxen der Normalfall) und
  die interne Kamera selbst per USB angebunden — das kommt bei Tablets vor —,
  meldet die Registry `gesamt=1, usb=1` fuer die INTERNE Kamera. Ergebnis waeren
  schwarze Fotos ohne Warnung gewesen.
- **Das Gedaechtnis braucht jetzt einen DevicePath-Beweis.** Gemerkt wird nur
  noch eine Erkennung, die BEIDES hatte: echten Geraetenamen UND eigenen
  `usb#`-DevicePath. Nur der DevicePath stammt aus derselben Aufzaehlung wie der
  Index und bindet beide wirklich aneinander. Zusaetzlich muss die Zahl der
  aufgezaehlten Geraete zum gemerkten Stand passen — sonst koennte ein
  nicht-oeffenbarer Eintrag der C922 die interne Kamera auf deren Index
  durchrutschen lassen.
- **Vorzugsregel repariert.** Bisher stand dort nur „logitech" — der
  FriendlyName der Fotobox-Kamera lautet aber `C922 Pro Stream Webcam` und
  enthaelt das Wort nicht. Die Regel konnte also nie greifen, und bei zwei per
  Namen extern eingestuften Geraeten gewann schlicht der kleinere Index (auf dem
  Miix die interne Kamera). Neu: bekannte Kameranamen (`c922`, `c920`, `brio`, …)
  zuerst, dann Geraete mit `usb#`-DevicePath, erst dann der kleinste Index.
  Zusaetzlich kennt die Intern-Wortliste jetzt `easycamera`, `user facing`,
  `world facing` und Verwandte.
- **Die ctypes-Abfrage hat wieder eine Zeitgrenze (6 s).** Sie war die einzige
  Kamera-Abfrage ohne eine solche; ein haengender Treiber haette den
  Waechter-Thread fuer immer stehen lassen und mit `_camera_check_running=True`
  die gesamte Kameraerkennung bis zum Neustart still totgelegt. Der aufgegebene
  Thread wird nicht getoetet (bei haengendem COM nicht gefahrlos moeglich),
  sondern gemerkt: solange er laeuft, wird der ctypes-Weg uebersprungen und das
  vorhandene Netz (PowerShell-Weg) benutzt. Zusaetzlich gibt der Waechter
  `_camera_check_running` nach 90 s selbst wieder frei.
- **Der Waechter tippt einen gesetzten Index nicht mehr nur an.** „Laesst sich
  Index N oeffnen?" beantwortet die abgeklebte Kamera mit Ja. Deshalb wird
  hoechstens jede Minute vollstaendig neu erkannt; zeigt der eingestellte Index
  nachweislich auf eine interne Kamera, wird sofort abgeschaltet.
- **`WebcamManager.initialize()` lehnt einen negativen Index ab.**
  `cv2.VideoCapture(-1)` heisst dort „irgendeine Kamera" — auf dem Miix waere
  das die interne. Jetzt scheitert es sauber, die Session zeigt ihre Meldung.
- `kamera_erkennung.json` wird atomar geschrieben (`.tmp` + `os.replace`).

### Noch auf einer echten Box zu pruefen

1. Ist `DevicePath` auf den Miix-Boxen wirklich gefuellt? Am Dev-PC nicht
   messbar (kein Videogeraet vorhanden). **Wichtig geworden:** Ohne DevicePath
   gibt es kein Gedaechtnis mehr — die Box funktioniert dann normal weiter,
   ueberbrueckt eine tote Namensabfrage aber nicht mehr, sondern blinkt.
2. Taucht die interne Kamera auf Christians Box in der Registry
   (`verbundene_videogeraete()`) auf? Davon haengt ab, ob das Gedaechtnis dort
   ueberhaupt greifen kann (`gesamt` muss 1 sein).
3. Einmal die Registry-Ausgabe protokollieren (verbundene Videogeraete, USB
   ja/nein).
4. Einmal mit **abgezogener** Kamera starten: Meldet die Abfrage null Geraete,
   wird bewusst kein Index mehr probiert — es muss die Warnung blinken, und es
   duerfen KEINE Fotos aus der internen Kamera entstehen.
5. Rollout-Reihenfolge: erst Christians Box, dann zwei Testboxen, dann die Flotte.

---

## [2.4.39] - 2026-08-20 - Messung wartet, bis die App die Kamera loslaesst

> Anlass: 2.4.37 lief auf der Box wieder sauber durch — und lieferte wieder
> keinen Messwert. Der Parameter-Fehler aus 2.4.36 war behoben (die OpenCV-Datei
> enthaelt ihn nicht mehr), aber DirectShow bekam die Kamera trotzdem nicht.

### Behoben

- **Die Messung startete mitten in die Kamera-Pruefung der App hinein.** Aus dem
  Box-Log, 20.08. 10:27:

  ```
  10:27:45.029 Kamera-Pruefung der App laeuft seit >3 s — Messung startet trotzdem
  10:27:45.030 Kamera-Messung startet als eigener Prozess
  10:27:47.922 DirectShow Kamera-Namen: ['c922 Pro Stream Webcam']   <- die APP
  10:27:48.585 Externe Kamera bevorzugt: [0] c922 Pro Stream Webcam  <- die APP
  ```

  Die Messung begann um 10:27:47 — genau waehrend die App dieselbe Kamera
  durchprobierte. Der Bericht meldete daraufhin "Kamera liess sich nicht
  oeffnen" und verurteilte 1080p zu Unrecht.

  Der Dialog wartete nur **3 Sekunden**, mit der Begruendung im Code, eine
  Pruefung dauere "normalerweise deutlich unter einer Sekunde". Auf der echten
  Box dauert sie **ueber 10 Sekunden**: Die PowerShell-Kamerasuche laeuft in ihre
  Zeitgrenzen (10 s DirectShow-Enumeration + 5 s PnP, teils mehrfach
  hintereinander). Drei Sekunden laenger warten haette gereicht.

  Jetzt: bis zu **30 Sekunden** warten, mit sichtbarer Restzeit. Wird die Kamera
  in der Zeit nicht frei, startet die Messung **gar nicht** — stattdessen eine
  ehrliche Meldung. Ein Lauf, von dem wir schon wissen, dass er nichts messen
  kann, ist schlimmer als keiner: Er produziert ein falsches Urteil.

- **Der Kamera-Waechter der App pausiert jetzt schon beim Oeffnen des Dialogs**,
  nicht erst beim Druck auf "Messung starten". Bei sichtbarer Kamera-Warnung
  prueft die App alle 2 s und braucht auf dieser Hardware ueber 10 s pro
  Pruefung — sie waere also faktisch dauernd an der Kamera. So laeuft die
  laufende Pruefung aus, waehrend der Bediener noch den Text liest.

### Hinweis zur Messgenauigkeit

Fuer die eigentliche 1080p-Entscheidung bleibt der Lauf ueber
`Kamera-Messung-starten.bat` (mit beendeter Software) der verlaessliche Weg —
der Bericht sagt das seit 2.4.37 auch selbst. Ueber den Admin-Knopf laeuft die
Fotobox-Software parallel mit und kostet Bilder/s.

---

## [2.4.38] - 2026-08-20 - Werkstatt-Knopf: ehrlicher Name, drei Sicherungen

> Anlass (Christian): „koennen wir den Button fuer die WLAN-Reparatur (hard) nun
> aus der Software entfernen? den brauchen wir doch nicht mehr weil der Fehler ja
> am Router lag!"

### Warum er NICHT entfernt wurde

Die Praemisse traegt nicht: Der Knopf setzt den Windows-Netzwerkstack zurueck und
loescht alle gespeicherten WLAN-Profile. Gegen einen vollen DHCP-Pool im Router
konnte er noch nie etwas ausrichten — er war nie das Gegenmittel gegen diese
Ursache und kann durch deren Behebung nicht ueberfluessig werden. Gebaut wurde er
fuer die 47 stummen Boxen bei 2.4.22 (kaputte Profile aus dem Klon-Image).

Ausserdem: Ursache 1 (eigener Hotspot blockiert die WLAN-Karte) ist erst in
2.4.29 behoben, die Flotte meldet aber weiterhin „Neuestes Release: v2.4.25" —
auf praktisch allen Boxen im Feld ist diese Ursache noch aktiv.

**Korrektur einer frueheren Aussage:** Das Argument „Boxen haengen beim Kunden an
fremden Routern" ist falsch. Es gibt in der Software keinen Weg, ein fremdes WLAN
zu verbinden (kein `netsh wlan connect` ausser fuer das Firmen-WLAN), und
`company_network.py` haelt fest: „Beim Kunden ist nie Internet". Beim Kunden
zaehlt allein der eigene Hotspot.

### Geaendert

- **Ehrlicher Name.** Aus „WLAN-Radikal-Reparatur" wird „Netzwerk-Werksreset
  ausführen (Box startet danach neu)", Ueberschrift „Werkstatt:
  Netzwerk-Werksreset". Der Knopf repariert nichts — er setzt zurueck. Der alte
  Name hat dazu verleitet, ihn an gesunden Boxen auszuprobieren.
- **Beim Kunden gesperrt.** Der erste Klick prueft im Hintergrund, ob das
  fexon WLAN in Funkreichweite ist. Wenn nicht: „Nicht möglich — fexon WLAN
  nicht in Reichweite", keine Scharfschaltung. Dort haette der Reset nicht
  geholfen, aber alle gespeicherten WLANs geloescht.
- **Neustart nur bei Erfolg.** Vorher lief `shutdown /r /f /t 10`
  bedingungslos — auch wenn ein Schritt fehlschlug; der Fehler stand nur im
  Knopftext und war nach dem Neustart weg. Jetzt bleibt die Box stehen und
  zeigt, was schiefging.
- **Sonderwarnung „kein Profil".** Wurden die Profile geloescht, aber das
  Firmen-Profil liess sich nicht neu anlegen, hat die Box NULL WLAN-Profile —
  und der Gaeste-Hotspot braucht mindestens eines. Der Knopf meldet dann rot:
  „Box hat jetzt KEIN WLAN-Profil! Nicht zum Kunden geben."

### Weiterhin offen

- Der Knopf wurde **nie auf einer echten Box ausprobiert** (TODO seit 2.4.27).
  Wir wissen also nicht, ob er im Ernstfall tut, was draufsteht. Das sollte
  einmal in der Werkstatt passieren.

---

## [2.4.37] - 2026-08-20 - Messung lief sauber durch, lieferte aber keine Werte

> Anlass: 2.4.36 hat auf der Box funktioniert — kein Einfrieren, sauberer
> Abbruch, Bericht nach 25 s. Nur stand in jeder Zeile "Kamera liess sich nicht
> oeffnen" bzw. "abgebrochen". Die Messtechnik war also in Ordnung, die Messung
> selbst kam nie an die Kamera.

### Behoben

- **DirectShow verweigerte das Oeffnen wegen der neuen Zeitgrenzen.** 2.4.36
  uebergab `CAP_PROP_OPEN_TIMEOUT_MSEC` / `CAP_PROP_READ_TIMEOUT_MSEC` an JEDES
  Backend, im Glauben, DirectShow ignoriere sie. Das tut es nicht — es lehnt sie
  ab und oeffnet die Kamera gar nicht erst. Aus `kamera-messung-opencv.txt` der
  Box:

  ```
  VIDEOIO(DSHOW): raised OpenCV exception:
  (-213) Failed to apply invalid or unsupported parameter: [53]=4000
  VIDEOIO(DSHOW): backend is generally available but can't be used to capture by index
  ```

  Folge: DirectShow scheiterte bei 640x480, wurde als totes Backend eingestuft,
  alle weiteren DirectShow-Messungen wurden uebersprungen. Danach lief Media
  Foundation in sein Zeitlimit — und der Bericht meldete faelschlich
  „1920x1080 lieferte KEINE Bilder", also ein reines Messartefakt.

  Die Zeitgrenzen gehen jetzt **nur noch an Media Foundation**. Zusaetzlich:
  Ist die Kamera nach dem Versuch mit Parametern nicht offen, wird ohne
  Parameter erneut geoeffnet. Beides ist noetig, weil OpenCV den Fehler INTERN
  abfaengt und nur ein nicht geoeffnetes Objekt zurueckgibt — es fliegt keine
  Python-Ausnahme, ein `try/except` allein haette nie gegriffen (im Test
  nachgestellt).

- **Kamera-Waechter der App legt sich waehrend der Messung schlafen.** Die
  Messung laeuft seit 2.4.36 als eigener Prozess — `camera_hardware_lock()`
  wirkt dort nicht mehr, denn die Sperre gilt nur INNERHALB eines Prozesses.
  Im Box-Log ist zu sehen, wie die App waehrend der laufenden Messung weiter
  Kameras suchte (10:03:33 bis 10:03:46). Fuer die Dauer der Messung ruht der
  Waechter jetzt.

- **Kamera-Wiederherstellung beim Schliessen blockiert die Oberflaeche nicht
  mehr.** Sie lief bisher direkt im UI-Thread; `initialize()` probiert DSHOW,
  MSMF und CAP_ANY nacheinander durch und haette ausgerechnet beim Knopf
  „Schließen" wieder einfrieren koennen. Laeuft jetzt verzoegert in einem
  Hintergrund-Thread.

### Bestaetigt aus dem Feld (2.4.36)

- Die Kamera-Messung liess sich **starten, beobachten und beenden, ohne die Box
  einzufrieren** — genau das war in 2.4.35 unmoeglich. Laufzeit 25 s, Status-Kopf
  im Bericht, aufgegebener Schritt sauber vermerkt, Urteil mit ehrlichem
  Vorbehalt („stuetzt sich nur auf die tatsaechlich gemessenen Zeilen").

---

## [2.4.36] - 2026-08-20 - Kamera-Messung friert die Box nicht mehr ein

> Anlass (Christian, auf der Box): „ich warte nun schon 5 min aber der test wird
> immernoch angezeigt! laeuft das ueberhaupt?" — und danach: „ich kann auch nicht
> schliessen, ich musste nun einen hard aus machen und die box neu starten."

### Behoben

- **Der Knopf „Kamera-Messung" fror die komplette Software ein.** In 2.4.35 lief
  die Messung als Hintergrund-Thread INNERHALB der laufenden App. Das Log endet
  exakt nach der letzten Zeile vor dem ersten Kamerazugriff der Messung:

  ```
  09:12:15.454 | Kamera freigegeben
  09:12:15.454 | Kamera-Messung: Kamera der App freigegeben
  << danach nichts mehr, auch kein Eintrag in absturz.log >>
  ```

  Also kein Absturz, sondern Stillstand. Zwei Ursachen, beide im Thread-Entwurf
  unvermeidbar: (1) Ein minutenlanger OpenCV-Kamerazugriff blockiert den
  Python-Prozess so, dass die Tk-Oberflaeche nicht mehr drankommt. (2) Die
  Messung hielt `camera_hardware_lock()` ueber ihre gesamte Laufzeit.

  **Die Messung laeuft jetzt als eigener Windows-Prozess** (`fexobooth.exe
  --kamera-test`) — technisch derselbe Weg wie `Kamera-Messung-starten.bat`, nur
  ohne dass die Software vorher beendet werden muss. Eigener Prozess = eigener
  Interpreter und eigene Sperren.

- **Abbrechen ist jetzt moeglich.** Ein blockierender `cv2`-Aufruf laesst sich
  innerhalb eines Prozesses NICHT abbrechen — der Aufruf steckt im C-Code von
  OpenCV, dorthin kommt weder Signal noch Exception. Ueber die Prozessgrenze geht
  es: Gegenprobe mit einem Testprozess, der das Beenden-Signal absichtlich
  ignoriert — trotzdem in 0,00 s beendet.

- **Fortschritt ist sichtbar.** Der Dialog zeigt die Laufzeit im
  Halbsekunden-Takt und meldet, sobald der Bericht auf der Platte waechst.
  Endet der Messprozess ohne Bericht, wird das gemeldet statt verschwiegen.

- **Notbremse:** Laeuft die Messung laenger als 15 Minuten, wird der Prozess
  beendet — sonst bliebe die Kamera dauerhaft belegt und keine Session mehr
  moeglich. Dasselbe passiert beim Schliessen des Dialogs.

### Ausserdem behoben: die Messung selbst haengt nicht mehr endlos

- **Zeitgrenzen, wo vorher keine waren.** Der Messcode fragte die Kamera ueber
  240-mal nach einem Bild und hatte fuer keinen dieser Versuche eine Zeitgrenze.
  Jetzt laeuft jeder Kamerazugriff in einem eigenen Wegwerf-Thread mit
  Zeitlimit (640x480 = 25 s, 720p = 35 s, 1080p = 50 s, Umschalt-Test = 30 s),
  dazu ein Gesamtbudget von 8 Minuten. Ein blockierender `cv2`-Aufruf laesst
  sich nicht abbrechen — nur aufgeben; danach werden alle weiteren
  Kamera-Schritte uebersprungen, weil der aufgegebene Thread die Kamera
  weiterhin besitzt.
- **Der Bericht waechst jetzt mit.** Er wird nach JEDEM Schritt atomar
  geschrieben und traegt oben einen Statuskopf: `Status`, `Schritt 4 von 11`,
  `Laeuft seit 00:02:13`, `Aktueller Schritt`. Damit ist waehrend des Laufs
  sichtbar, ob es noch vorangeht — vorher entstand die Datei erst ganz am Ende,
  und `print()` faellt im Fenster-Build ins Leere. Ein Abbruch hinterlaesst
  jetzt alle bis dahin fertigen Messwerte statt gar nichts.
- **Jeder ausgelassene Schritt hinterlaesst eine Zeile mit Begruendung.**
  Vorher liess sich "gemessen und leer" nicht von "stumm gescheitert"
  unterscheiden.
- **Richtiger Codec gemessen.** Die Aufloesung wird jetzt VOR dem Codec gesetzt
  (wie in `webcam.py`, Erkenntnis aus 2.4.13) und beides zurueckgelesen — der
  Bericht weist `1920x1080 MJPG` bzw. `YUY2 <-- nicht MJPG!` aus. Vorher wurde
  vermutlich das Dekodieren von YUY2 gemessen, also nicht die eigentliche Frage.
- **Kamera-Auswahl wie in der App**: `--kamera-index` schlaegt Config schlaegt
  `find_best_camera()`. Index und Geraetename stehen im Berichtskopf.
- **`Kamera-Messung-starten.bat`**: sagt 2 bis 4 Minuten an, erklaert die
  Fortschrittsanzeige ueber die mitwachsende Berichtsdatei, warnt dass das
  Zuklicken des schwarzen Fensters die Messung NICHT beendet, hebt den alten
  Bericht als `kamera-messung-vorher.txt` auf und prueft auch den Ausweichpfad.

### Bestaetigt aus dem Feld (2.4.35)

- Der **Beenden-Knopf im Service-Menue (3198)** arbeitet auf echter Hardware
  korrekt: Taskleiste → Benachrichtigungen → Kamera-Freigabe → beendet, komplett
  in **0,3 Sekunden**, ohne dass der Notausstieg einspringen musste. Auch die
  neue Pruefung `_root_lebt()` griff wie vorgesehen.

---

## [2.4.35] - 2026-08-20 - Beenden laesst keinen Prozess mehr stehen + Kamera-Messung als Knopf

> Anlass (Christian): „Der App-beenden-Button ueber 3198 beendet die App nicht
> richtig, sie geht zwar zu aber da bleibt ein Prozess am Taskmanager aktiv."
> Ausserdem sollte die Kamera-Messung fest in die Software statt nur als
> BAT-Datei.

### Behoben

- **Beenden ueber das Service-Menue (PIN 3198) laesst keinen Prozess mehr
  zurueck.** Es gab drei Ursachen, alle im selben Knopf:
  1. **Kamera wurde nicht freigegeben.** Der Notausstieg Ctrl+Shift+Q rief
     `camera_manager.release()`, der Beenden-Knopf nicht — es waren zwei
     getrennte Beenden-Wege mit eigenem Code. Jetzt laufen beide durch
     `PhotoboothApp.shutdown()`.
  2. **Kindprozess ueberlebte.** `main.py` endet bewusst mit `os._exit(0)` —
     das beendet aber NUR den Python-Prozess. Die unsichtbare
     `FexoNikonBridge.exe` ist ein eigener Windows-Prozess und blieb als Waise
     stehen (und hielt damit die Kamera belegt). Sie wird jetzt beim Beenden
     mitgenommen; neu ist `shutdown_bridge()` in `src/camera/nikon.py`.
  3. **Kein Netz, wenn die Hauptschleife haengt.** Beendet `root.destroy()` die
     Tk-Hauptschleife nicht, wird `os._exit(0)` nie erreicht: Fenster weg,
     Prozess laeuft unsichtbar weiter — genau das gemeldete Symptom. Ein
     Wachhund beendet den Prozess jetzt notfalls nach 8 Sekunden hart.
- **Der modale Grab wurde beim Beenden nie geloest** und der Admin-Dialog nie
  geschlossen — `destroy()` lief also gegen ein noch aktives Modal. Der Knopf
  macht das jetzt in derselben Reihenfolge wie der erprobte Notausstieg.
- **Arbeiten auf zerstoerten Fenstern nach dem Beenden.** Hinter jedem
  `wait_window(...)` in `src/app.py` lief Code weiter, der `current_screen`
  anfasste — nach dem Beenden existiert das Hauptfenster aber nicht mehr. Neue
  Pruefung `_root_lebt()` bricht dort sauber ab.
- **Verwaiste Bridge-Prozesse aus frueheren Abstuerzen** werden jetzt beim
  App-Start weggeraeumt (Hintergrund-Thread). Sie belegten sonst dauerhaft die
  Kamera und der naechste Start scheiterte daran.

### Neu

- **Knopf „Kamera-Messung starten"** im Admin-Menue → Tab **Kamera**. Macht aus
  `--kamera-test` einen normalen Bedienschritt: kein Beenden der Software, kein
  USB-Stick, kein BAT-Aufruf noetig. Zeigt Fortschritt an und bietet danach
  „Bericht oeffnen" an. Ergebnis wie gehabt in
  `C:\FexoBooth\logs\kamera-messung.txt`.
- Die Messung laeuft dabei zwingend unter `camera_hardware_lock()` und gibt
  vorher die Kamera der laufenden App frei. **Ohne die Sperre waere der Absturz
  aus 2.4.31 zurueck** (zwei Threads an derselben DirectShow-Kamera →
  Heap-Korruption 0xc0000374). Danach wird die Kamera wieder bereitgestellt.

### Technisch

- Neu: `src/utils/shutdown.py` (gemeinsames Beenden, Wachhund, Waisen-Aufraeumen)
- Neu: `src/ui/dialogs/kamera_messung.py` (Mess-Dialog)
- `beende_kindprozesse()` benutzt bewusst **kein** `taskkill` — der Aufruf ist
  ein eigener Prozessstart und dauerte im Test 5 s. Auf dem Beenden-Weg (auch
  Oberflaechen-Thread) waere das eine sichtbare Blockade. `taskkill` laeuft nur
  noch beim Start im Hintergrund, fuer Waisen fremder Laeufe.

---

## [2.4.34] - 2026-08-19 - Messmodus: Kann die Kamera dauerhaft in 1080p laufen?

> Anlass: Der Ausloese-Blitz kommt sofort, das Bild wird aber erst ~1,7 s spaeter
> belichtet — wer sich dazwischen bewegt, ist nicht mehr drauf. Ursache ist das
> Umschalten der Aufloesung pro Foto (640x480 → 1920x1080 kostet ~1,5 s).
> Die Frage „koennte die Kamera nicht einfach dauerhaft in 1080p laufen?" laesst
> sich am Entwickler-PC NICHT beantworten: Dort ergab die Hochrechnung 21 ms
> pro Bild, die Box meldet real 83 ms. Auf schwacher Hardware skaliert die
> Speicherbandbreite ganz anders als die Rechenleistung.

### Neu

- **`fexobooth.exe --kamera-test`** — eigener Messmodus, startet keine Fotobox.
  Misst auf der echten Box: Bildrate bei 640x480 / 1280x720 / 1920x1080, die
  tatsaechliche Dauer des Aufloesungs-Wechsels, den Nutzen einer geaenderten
  Reihenfolge in der Bildaufbereitung, und vergleicht DirectShow mit Media
  Foundation. Ergebnis als Klartext-Urteil in `C:\FexoBooth\logs\kamera-messung.txt`.
- Die Messung trennt dabei **Warten auf die Kamera** (`grab`) von **Rechenzeit
  fuers Dekodieren** (`retrieve`). Ohne diese Trennung sieht man nur die Summe
  und weiss nicht, ob die Kamera oder die CPU bremst — das entscheidet aber,
  welche Loesung ueberhaupt etwas bringt.

### Erkenntnis aus der Vorab-Analyse (Entwickler-PC)

- Die Bildaufbereitung spiegelt und faerbt das **volle** Kamerabild um und
  verkleinert erst danach. Dreht man die Reihenfolge um, kostet dieser Schritt
  bei 1080p statt 4,14 ms nur noch 0,19 ms (**21x**). Die Aufloesung waere fuer
  die Aufbereitung damit fast egal — der offene Posten ist allein das Dekodieren.

---

## [2.4.33] - 2026-08-19 - Router als Ursache belegt: Urteil praezisiert + DHCP-Diagnose

> **Befund aus den ersten echten `netzwerk.log`-Dateien** (Boxen 019 und 038, beide 2.4.32):
> ```
> IP-Adressen   : FEHLT | 169.254.27.205 (KEINE DHCP-Adresse/APIPA)
> Eig. Hotspot  : aus          <-- der Hotspot laeuft GAR NICHT
> Hotspot-Konfl.: nein
> ```
> Die 3-stufige Reparatur lief durch und fand nichts. Damit ist die Box entlastet:
> **Der Router vergibt diesen Boxen keine Adresse.** Passend dazu zeigt Windows bei genau
> diesen Boxen „fexon WLAN — Kein Internet, gesichert".

### Geändert

- **Das Urteil zeigt nicht mehr auf den Hotspot, wenn der gar nicht läuft.** Bisher stand
  auch bei ausgeschaltetem Hotspot „Verdacht: eigener Hotspot belegt die WLAN-Karte" im
  Bericht — das hat in die falsche Richtung gewiesen. Jetzt wird sauber getrennt:
  Hotspot AN → Hotspot verdächtig; Hotspot AUS → **„die Box ist entlastet, der ROUTER
  vergibt ihr keine Adresse"** samt Prüfliste (DHCP-Bereich voll, MAC-Sperre, Client-Limit).

### Neu

- **`Absturz-Infos-sammeln.bat` sammelt jetzt auch die DHCP-Lage**: `netsh wlan show
  interfaces`, die WLAN-Zeilen aus `ipconfig /all` (inkl. MAC-Adresse und ob ein DHCP-Server
  geantwortet hat) und die Windows-DHCP-Meldungen der letzten 7 Tage. Das ist der von der App
  unabhängige Gegenbeweis — und liefert die MAC-Adressen, die man am Router braucht.

---

## [2.4.32] - 2026-08-19 - Netz-Bilanz kommt sofort + Selbsttest misst richtig

> Anlass: Werkstatt 19.08. — die Boxen **19, 31 und 38** melden sich nicht im Dashboard, hatten
> aber **gar keine `netzwerk.log`**. Alle drei liefen laut `absturz.log` nur **2,5–3 Minuten**
> (zwei Start-Zeilen im Abstand von 2:29 bis 3:01). Ursache: Die Bilanz stand am Ende der
> Wiederholkette (20+30+45+60+90 s ≈ 4 Minuten). Wer die Box vorher ausschaltet, bekommt
> **kein einziges Protokoll**. Den blinden Fleck hatte ich in 2.4.29 nur für den Fall
> „keine IP-Adresse" beseitigt — nicht für „IP da, Meldung klemmt trotzdem".

### Behoben

- **Die Netz-Bilanz wird jetzt IMMER direkt nach dem ersten Melde-Versuch geschrieben** —
  spätestens ~40 Sekunden nach dem Start der Box, statt erst nach ~4 Minuten. Klappt die
  Meldung erst bei einer Wiederholung, kommt ein zweiter Eintrag („nach Wiederholung").
  Im Test: Eintrag nach **1,5 s** statt gar nicht.
- **Selbsttest meldete fälschlich „Hohe Hintergrund-Auslastung (Windows-Update/Defender?)".**
  Gemessen wurde die **Gesamt**-CPU — inklusive der App selbst, die während des Tests gerade
  Fotos rendert. Feld-Log Box 044 (19.08.) belegt es: CPU gesamt 20–48 %, davon `fexobooth.exe`
  19–39 %, `System Idle Process` 54–73 % — die Box war also gar nicht ausgelastet.
  Jetzt wird die **eigene Last abgezogen** und nur noch echte Fremdlast gemeldet; beide Werte
  stehen zusätzlich im Log.

- **`netzwerk.log` wird jetzt bei JEDEM App-Start geschrieben — ausnahmslos.** Bisher schwieg
  die Box komplett, wenn das Firmen-WLAN nicht in Reichweite war (`not_visible`). Das sollte
  „Box ist beim Kunden" bedeuten — ist aber nicht unterscheidbar von „der WLAN-Scan ist
  fehlgeschlagen" (netsh-Fehler, Funk aus, Adapter belegt). In der Werkstatt stand man dann
  wieder ohne jede Spur da. Jetzt gibt es auch dafür eine kurze Zeile mit Klartext-Hinweis.
  Kosten: eine Zeile pro Start, Datei wird bei 200 KB gekürzt.

### Bestätigt

- **`netzwerk.log` und `absturz.log` entstehen nachweislich OHNE Developer-Mode.** Gegengeprüft
  mit `setup_logging(developer_mode=False)` (NullHandler, Logger unterdrückt) — Datei wird
  trotzdem geschrieben. Feldbeweis zusätzlich: Boxen 19/31/38 hatten kein `fexobooth_*.log`
  (also kein Dev-Mode), aber sehr wohl eine `absturz.log` — gleicher Mechanismus, gleicher Ordner.
- **Der Absturz-Fix aus 2.4.31 wirkt.** Auf allen drei Boxen (19/31/38) enthält `absturz.log`
  nur noch Start-Zeilen — kein `fatal exception`, keine Heap-Zerstörung mehr.

---

## [2.4.31] - 2026-08-19 - ABSTURZ-URSACHE GEFUNDEN: zwei Threads an derselben Kamera

> Der `faulthandler` aus 2.4.30 hat geliefert. `absturz.log` von Box 044 (19.08. 08:44):
> ```
> Windows fatal exception: code 0xc0000374        <- HEAP CORRUPTION
> Current thread:  src\app.py:2568 in _camera_status_probe   -> cv2.VideoCapture(...)
> Thread:          src\camera\webcam.py:519 in list_cameras  -> cv2.VideoCapture(...)
>                  src\app.py:156 in _auto_select_webcam
> ```
> Damit ist die Ursache eindeutig: **Zwei Threads öffnen gleichzeitig dieselbe
> DirectShow-Kamera.** Das zerlegt den Heap des Prozesses — Windows meldet es später als
> Absturz in `ntdll.dll` (`0xc0000005` / `0xc0000374`).

### Behoben

- **Eine gemeinsame Sperre für JEDEN Kamera-Zugriff** (`camera_hardware_lock()` in
  `src/camera/webcam.py`). Der bisherige `self._camera_lock` war eine **Instanz**-Sperre —
  `WebcamManager.list_cameras()` ist aber eine `@staticmethod` und lief komplett daran vorbei.
  Jetzt teilen sich Instanz-Methoden und statische Kamera-Suche dieselbe modulweite Sperre.
- **Die Kamera-Prüfung in `app.py` nimmt die Sperre ebenfalls** — genau die Zeile aus dem
  Absturz-Protokoll (`cv2.VideoCapture(cam_idx, cv2.CAP_DSHOW)`) lief vorher ungeschützt.
- Nachweis im Test: mit Sperre **max. 1** gleichzeitiger Kamera-Zugriff, ohne Sperre **2**.

> **Warum es nur „vereinzelt" auftrat:** Beide Threads starten beim Hochfahren fast zeitgleich.
> Ob sie sich wirklich überlappen, hängt vom Timing ab (CPU-Last, wie schnell die Kamera
> antwortet). Deshalb traf es nur manche Boxen und war im Developer-Mode praktisch nie
> reproduzierbar — dort läuft alles etwas anders getaktet.

### Ebenfalls behoben

- **`StartScreen.on_show` auf zerstörtem Screen**: Nach dem Schliessen des Admin-Dialogs lief
  `on_show` auf einem bereits zerstörten StartScreen (`invalid command name ".!ctkbutton.!label"`,
  ebenfalls im `absturz.log` von Box 044). Der Tk-Handler aus 2.4.30 hat das abgefangen und die
  App lief weiter — jetzt wird der tote Screen sauber übersprungen, statt den Fehler zu erzeugen.

---

## [2.4.30] - 2026-08-18 - Abstürze werden endlich sichtbar (+ vermutliche Ursache entschärft)

> Anlass: Werkstatt 18.08. — zwei Boxen stürzten beim Hochfahren ab, andere beim Anstecken des
> USB-Sticks. **Im Developer-Mode nie reproduzierbar.** Die mitgelieferten Dev-Logs liefen beide
> sauber bis „FEXOBOOTH BEENDET" durch: Der Absturz war nirgends dokumentiert, weil die App im
> Normalbetrieb gar nichts schreibt.

### Neu

- **`C:\FexoBooth\logs\absturz.log`** — jeder unbehandelte Fehler landet dort mit Zeitstempel,
  Version und komplettem Stacktrace, **immer** und unabhängig vom Developer-Mode. Gleiche Stelle
  wie `netzwerk.log`, kommt also automatisch mit, wenn jemand den logs-Ordner kopiert. Erfasst
  werden: Hauptthread, Hintergrund-Threads und Tk-Callbacks.
- **Fehler aus Tk-Callbacks reissen die App nicht mehr mit.** Bisher gab es gar keinen
  `report_callback_exception`-Handler — Tkinter ging den Standardweg über `sys.stderr`. Im
  Fenster-Build ist der aber `None` (siehe Kommentar in `main.py` zum selben Thema beim Beenden).
  Jetzt wird der Fehler abgefangen, protokolliert, und die App läuft weiter.

- **Native Abstürze werden mitgeschrieben** (`faulthandler`): Bei einem Speicherzugriffsfehler
  in einer DLL stirbt der Prozess sofort — kein Python-Handler läuft mehr, `absturz.log` bliebe
  leer. `faulthandler` hängt sich unterhalb von Python ein und schreibt im Moment des Absturzes
  noch den Python-Stack **aller Threads** raus. Damit ist ablesbar, welche Stelle gerade lief
  (Kamera, VLC, Drucker …). Kostet zur Laufzeit praktisch nichts, läuft deshalb immer mit.

### Neu — Werkzeug für die Werkstatt

- **`Absturz-Infos-sammeln.bat`** — Doppelklick genügt, nichts zu tippen. Sammelt alles, was
  Windows über Abstürze der Box gespeichert hat (Ereignisprotokoll, Fehlerberichte, vorhandene
  Speicherabbilder, Inhalt des logs-Ordners und die letzten Zeilen von `absturz.log`) und legt
  es als Textdatei in `C:\FexoBooth\logs` ab. Danach nur noch den logs-Ordner auf den Stick
  kopieren. Liegt an zwei Stellen: **neben der Setup-EXE** (wandert beim Kopieren auf den
  USB-Stick automatisch mit) und **direkt in `C:\FexoBooth`** auf jeder installierten Box.
- Als Administrator gestartet schaltet dasselbe Skript zusätzlich das **Speicherabbild für den
  nächsten Absturz** ein (`C:\FexoBooth\logs\dumps`) — daraus lässt sich die schuldige DLL
  eindeutig bestimmen. Ohne Adminrechte läuft alles andere trotzdem durch.

> **Korrektur zum Tk-Handler:** Das Windows-Ereignisprotokoll einer betroffenen Box zeigt
> `ntdll.dll` / Ausnahmecode `0xc0000005` (Speicherzugriffsfehler). Das ist **kein**
> Python-Fehler — der Tk-Handler ist also NICHT die Ursache dieser Abstürze. Er bleibt als
> sinnvolles Sicherheitsnetz drin, aber die eigentliche Spur liefert `faulthandler`.

---

## [2.4.29] - 2026-08-18 - Reparatur testet den Hauptverdächtigen ZUERST (Fall endlich reproduziert)

> Anlass: Feld-Log 18.08. von **Box 056** (`fexobooth_20260818_111651.log`) — der erste Log, der
> den Fehler wirklich zeigt UND in dem die 2.4.27-Reparatur anspringt:
> ```
> 11:17:05 | Gefundene IPs: ['192.168.137.1', '169.254.166.159']
> 11:17:15 | Netz-Reparatur: ... hat aber KEINE brauchbare IP-Adresse — starte Reparatur
> 11:17:16 | Netz-Reparatur: Neue IP-Adresse anfordern (Adapter: WLAN)...
> 11:18:16 | Netz-Reparatur: renew Code 1 (TIMEOUT)      ← eine volle Minute vertan
> 11:18:36 | Netz-Reparatur: Stufe 2 — WLAN trennen und neu verbinden...
> 11:18:51 | FEXOBOOTH BEENDET                            ← Box ausgeschaltet, Stufe 3 nie erreicht
> ```
> Der entscheidende Test (Hotspot abschalten) stand ganz hinten und kam nie zum Zug.

### Geändert

- **Reihenfolge der Reparatur umgedreht.** Läuft der eigene Hotspot, wird er jetzt als **ERSTES**
  abgeschaltet statt als Letztes. Erkannt wird er kostenlos an der Adresse `192.168.137.x` —
  ohne zusätzliche Abfrage. Neue Reihenfolge: 1. Hotspot aus + neu verbinden, 2. DNS-Cache +
  neue IP anfordern, 3. WLAN trennen/neu verbinden.
- **`ipconfig /renew` bricht nach 20 s ab** statt nach 60 s. Antwortet der Router in 20 s nicht,
  antwortet er auch später nicht — dann sind die anderen Stufen wichtiger als das Warten.
- **Netz-Bilanz kommt sofort, nicht erst nach 4 Minuten.** Schlägt die Reparatur fehl, wird die
  Bilanz jetzt SOFORT festgehalten (`Frühbefund`). Vorher lief zuerst die komplette
  Wiederholkette (20+30+45+60+90 s = ~4 min) — so lange bleibt in der Werkstatt keine Box an,
  und das Protokoll blieb wieder leer.
- **Wartezeiten pro Stufe von 20 s auf 15 s gekürzt.** Ergebnis im Test: Ist der Hotspot der
  Störer, steht das Ergebnis nach **~6 Sekunden** fest (vorher: erst nach ~2,5 Minuten, also nie).
  Hilft keine Stufe, ist die komplette Reparatur nach gut 20 Sekunden durch — mit klarem Urteil
  „Router vergibt keine Adresse → Lease-Liste prüfen".

---

## [2.4.28] - 2026-08-18 - Netz-Protokoll auch OHNE Developer-Mode (Werkstatt-Test lieferte keine Spur)

> Anlass: Werkstatt-Test 18.08. mit 2.4.27 auf drei Boxen (073, 116, 016). Alle drei kamen ohne
> Befund zurück — weil die App im Normalbetrieb **überhaupt kein Log schreibt**
> (`setup_logging` hängt ohne Developer-Mode einen NullHandler ein). Zurück kamen nur die
> Installer-Logs, und die melden auf allen drei Boxen brav „Mit 'fexon WLAN' verbunden - Setup
> erfolgreich". Die eigentliche Frage — hatte die Box danach auch Netz? — war nicht beantwortbar.

### Neu

- **`C:\FexoBooth\logs\netzwerk.log`** wird ab jetzt **immer** geschrieben, unabhängig vom
  Developer-Mode. Inhalt: die NETZ-BILANZ mit Zeitstempel, Box-ID und Version. Die Datei liegt
  neben den Installer-Logs und kommt damit automatisch mit, wenn ein Mitarbeiter den
  `logs`-Ordner kopiert — kein Dev-Mode, keine Extra-Handgriffe.
- **Auch der Abbruch wird protokolliert:** Kommt die Box gar nicht erst ins Firmen-WLAN, steht das
  jetzt ebenfalls drin (Grund + Ergebnis der Selbstheilung + Klartext-Urteil). Vorher endete der
  Ablauf an dieser Stelle stumm.
- Sparsam gehalten: Geschrieben wird **nur im Firmen-WLAN** (beim Kunden nie), ein kurzer Block
  pro Start bzw. pro fehlgeschlagener Wiederholmeldung; die Datei wird bei ~200 KB vorne gekürzt.

---

## [2.4.27] - 2026-08-18 - Firmen-WLAN: Box war "verbunden" ohne Netz + Hotspot-Start war ein Blindgänger

> Anlass: Feld-Log 18.08. von Box 200 (`fexobooth_20260818_102651.log`). Die Box war laut
> Windows mit `fexon WLAN` VERBUNDEN, konnte aber nichts erreichen (`getaddrinfo failed`,
> 3 Versuche). Der Grund stand eine Zeile vorher im Log: Als IP-Adressen hatte die Box nur
> `169.254.183.239` (= Notfalladresse, der Router hat NICHTS vergeben) und `192.168.137.1`
> (= den eigenen Hotspot). Eine echte Adresse vom Firmen-Router war nirgends dabei.
> Nach außen sieht das aus wie "die Box verbindet sich nicht" — obwohl der WLAN-Name stimmt.

### Behoben

- **Hotspot-Start/-Stopp waren wirkungslos (stiller Blindgänger seit Langem).** In den
  PowerShell-Befehlen standen doppelte geschweifte Klammern (`{{ }}`) — ein Überbleibsel einer
  alten Textersetzung. PowerShell führt solche Blöcke NICHT aus, sondern gibt sie nur als Text
  aus. Python hat diese Textausgabe anschließend als Erfolg gewertet und
  "Hotspot erfolgreich gestartet" ins Log geschrieben. Tatsächlich hat die App den Hotspot nie
  gestartet, nie gestoppt und nie richtig geprüft. Jetzt laufen die Befehle wirklich, und nur
  eine echte Erfolgsmeldung von Windows gilt als Erfolg.
- **Der eigene Hotspot wird nicht mehr über das Firmen-WLAN aufgezogen.** Bisher nahm die App
  das erstbeste Netzwerk-Profil als Anker — im Firmen-WLAN also meist `fexon WLAN` selbst.
  Windows teilt dann die Firmen-Verbindung über dieselbe WLAN-Karte, und genau dabei verliert
  die Box ihre IP-Adresse vom Firmen-Router. Jetzt wird bevorzugt ein neutrales Profil
  (`FexoBoothDummy`) benutzt; das Firmen-Profil nur noch als Notnagel (mit Warnung im Log).
- **"Verbunden" wird nicht mehr am WLAN-Namen festgemacht.** Die Selbstheilung prüft jetzt, ob
  wirklich eine brauchbare IP-Adresse da ist. Vorher meldete sie "alles gut", sobald der
  richtige Netzwerkname dastand — auch wenn die Box gar kein Netz hatte.
- **Neue Reparatur bei "verbunden, aber keine IP-Adresse"** (läuft nur im Firmen-WLAN, beim
  Kunden nie), in drei Stufen: 1. DNS-Cache leeren + neue Adresse anfordern, 2. WLAN trennen
  und neu verbinden, 3. eigenen Hotspot abschalten und nochmal verbinden. Hilft Stufe 3, ist
  bewiesen, dass der Hotspot der Störer war — er bleibt dann für diesen Lauf im Firmen-WLAN aus
  (in der Werkstatt sind Dashboard-Meldung und Updates wichtiger als der Gast-Hotspot).

### Geändert

- **Reihenfolge beim Start in der Werkstatt:** Steht die Box im Firmen-WLAN, laufen jetzt zuerst
  Dashboard-Meldung und Update-Check, danach erst der eigene Hotspot (er teilt sich die
  WLAN-Karte). Beim Kunden ändert sich nichts — dort wartet der Hotspot keine Sekunde.

### Neu — Logging, das auch zeigt WENN es nicht hilft

- **NETZ-BILANZ im Log** (`src/utils/network_diag.py`): ein klar erkennbarer Block mit
  IP-Adressen, Router-Ping, Namensauflösung, Dashboard-Erreichbarkeit, Hotspot-Zustand und
  einem Klartext-URTEIL. Damit ist im nächsten Log auf einen Blick unterscheidbar:
  *keine IP-Adresse* ≠ *IP da, aber Router antwortet nicht* ≠ *kein DNS* ≠ *Dashboard down*.
  Die Bilanz wird beim Start im Firmen-WLAN geschrieben und danach bei jeder fehlgeschlagenen
  wiederkehrenden Meldung — ein nicht wirkender Fix fällt damit sofort auf.
- Bei "Dashboard nicht erreichbar" stehen jetzt direkt die eigenen IP-Adressen daneben.

### Nachgezogen nach dem ersten Feldtest (Box 200)

- **Bildschirm fror nach dem Admin-Speichern ~9 Sekunden ein:** Der Hotspot-Start lief dort direkt
  im Bildschirm-Ablauf statt im Hintergrund. Läuft jetzt im Hintergrund (bestand schon vorher, fiel
  erst durch das neue Logging auf).
- **Irreführende Warnung entfernt:** Lief der Hotspot bereits, meldete das Log trotzdem „musste das
  Firmen-WLAN als Anker nehmen" — obwohl gar nichts umgestellt wurde. Die Warnung kommt jetzt nur
  noch, wenn der Hotspot wirklich neu aufgezogen wird.
- **Weniger Last beim Start:** Der Hotspot-Zustand wird für die NETZ-BILANZ nur noch abgefragt,
  wenn die Dashboard-Meldung NICHT durchkam (spart einen PowerShell-Aufruf auf der schwachen Box).

---

## [2.4.26] - 2026-08-13 - Selbsttest öffnet die Kamera wie im Betrieb (Fehlalarm „langsame Kamera" + Einfrieren behoben)

> Anlass: Feld-Logs 13.08. von Box 224 (Webcam „HD Pro Webcam C920"). Der Selbsttest meldete
> „Kamera-Start langsam: 7,6s" — obwohl die Kamera kerngesund war (16 Bilder/s, Fotos in 0,1s,
> Test bestanden). Auffällig: dieselbe Box fror in einem anderen Lauf beim Selbsttest komplett
> ein — das Log endet exakt beim Öffnen der Kamera. Ursache: Der Selbsttest öffnete die Kamera
> KALT in voller Foto-Auflösung (1920×1080). Das ist NICHT der normale Ablauf und auf älteren
> C920 langsam/fragil. Im echten Betrieb läuft die Vorschau in 640×480 und schaltet nur kurz
> pro Foto auf 1080p — dieser Weg ist schnell und stabil.

### Behoben

- **Selbsttest nimmt jetzt exakt denselben Kamera-Weg wie eine echte Session:**
  - **Kamera öffnen** in der Vorschau-Auflösung (wie im Betrieb) statt kalt in 1920×1080.
    Damit verschwindet der Fehlalarm „Kamera langsam" auf gesunden C920 — und der gefährliche
    Einfrier-Punkt beim Kalt-Öffnen in 1080p ist weg.
  - **Testfoto** über den echten High-Res-Aufnahmepfad (`get_high_res_frame`, kurz auf 1080p
    und zurück) — volle Fotoqualität wird weiterhin geprüft, aber über den erprobten Weg.
  - Nach den Testfotos wird die Vorschau-Auflösung wiederhergestellt, damit die erste echte
    Vorschau nach dem Test nicht unnötig langsam ist.
  - Die DSLR (Canon/Nikon) bleibt unverändert: weiterhin LiveView-Frame ohne echtes Auslösen.

> Hinweis für die Flotte: Verzögert/hängend war eine Eigenheit einzelner Boxen beim Kalt-Öffnen
> in 1080p (USB-Zustand — Umstecken der Kamera setzt ihn zurück, deshalb „mit anderer Kamera
> geht's, mit der alten wieder auch"). Der neue Weg umgeht das grundsätzlich.

---

## [2.4.25] - 2026-08-12 - Dashboard-Meldung mit Wiederholung (Boxen meldeten sich nur einmal)

> Anlass: Feld-Logs 11.08. (Boxen 188/043/102) — die Boxen liefen 25+ Minuten im Firmen-WLAN,
> meldeten sich aber NIE im Dashboard: Der einzige Melde-Versuch ~15 s nach dem Start scheiterte
> an noch nicht bereitem DNS (`getaddrinfo failed`), direkt nach dem WLAN-Verbinden und dem
> gleichzeitigen Hochfahren des Box-eigenen Hotspots. Es gab keinen zweiten Versuch.

### Behoben

- **Boxen melden sich jetzt zuverlässig ans Dashboard:**
  - **Wiederholversuche beim Start:** Scheitert der erste Heartbeat an Netzwerk/DNS, versucht es
    die Box mehrfach mit wachsendem Abstand (nach 20/30/45/60/90 s), bis es klappt — überbrückt
    das kurze DNS-Loch nach dem WLAN-Verbinden.
  - **Wiederkehrende Meldung:** Danach meldet sich die Box dauerhaft ~alle 15 Minuten erneut
    (mit Zufallsstreuung), solange sie im Firmen-WLAN ist. So taucht sie auch auf, wenn der Start
    komplett daneben ging, und der Dashboard-Status bleibt aktuell.
  - Die Zufallsstreuung verteilt gleichzeitig startende Boxen automatisch — mehrere Boxen im
    selben WLAN sind unkritisch (die Meldung ist winzig; der Server verkraftet das mühelos).

---

## [2.4.24] - 2026-08-11 - Kamera-Absturz behoben + Admin-Kamera-Tab + Ladebalken (Nachschärfung)

> Anlass: Nachtest-Log 2.4.23 — der Kamera-Wächter stürzte beim Start ab (und blieb danach
> tot → Box erkannte die Kamera erst nach manuellem Eingriff), der Admin-Kamera-Tab fror
> weiterhin ~9s ein, und der Ladebalken bewegte sich weiter erst spät.

### Behoben

- **KRITISCH: Kamera-Wächter stürzte beim Start ab und blieb danach tot.** Der Hintergrund-
  Prüf-Thread rief `root.after()` auf, bevor die Tk-Hauptschleife lief → `RuntimeError: main
  thread is not in main loop` → der Thread starb und mit ihm die automatische Kamera-
  Wiederherstellung. Folge: Fand die Kamera-Suche beim Kaltstart (unter Last) nichts, blieb die
  Box „ohne Kamera", bis jemand ins Admin-Menü ging. Jetzt startet die Prüfung erst nach dem
  Mainloop-Start, und die Ergebnis-Rückgabe ist crash-sicher (Retry). Die Kamera erholt sich
  damit wieder von selbst innerhalb ~15s.
- **Admin-Kamera-Tab fror weiterhin ~9s ein:** Die Kamera-Suche lief bei der Tab-Erstellung
  noch synchron (2.4.23 hatte nur den Refresh-Button entkoppelt). Jetzt lädt der Tab sofort mit
  „Suche Kameras…" und füllt die Liste aus dem Hintergrund; die zuvor gewählte Kamera bleibt
  markiert.
- **Ladebalken bewegt sich jetzt von Anfang an:** Der Balken läuft im Startup-Screen monoton
  vorwärts (statt Ping-Pong) mit zusätzlichen Schritten während des StartScreen-Aufbaus. Der
  Flask-Server-Start (blockiert ~1,5s) wandert von 4s auf 7s nach dem Boot — er landet damit
  hinter dem Ladescreen statt mitten drin, wo er den Balken einfrieren ließ.

---

## [2.4.23] - 2026-08-11 - Kamera-Suche im Hintergrund + Ladebalken bewegt sich wieder

> Anlass: Nachtest-Log 2.4.22 — Box startete kurz „ohne Kamera" und fing sich dann selbst;
> der Kamera-Tab im Admin-Menü fror ~8s pro Aufruf ein; der Ladebalken im Willkommensscreen
> bewegte sich kaum. Alle drei haben dieselbe Wurzel: die Kamera-Suche (PowerShell-Geräte-
> Enumeration) lief auf dem Haupt-/Startup-Thread und blockierte die Oberfläche.

### Behoben

- **Kamera-Suche blockiert nicht mehr die Oberfläche:**
  - Beim Start läuft die Kamera-Auswahl jetzt im Hintergrund (früher bis ~16s Blockade beim
    Kaltstart unter Last → Box startete kurz „ohne Kamera"). Der laufende Kamera-Wächter
    korrigiert den Index, sobald die Kamera gefunden ist.
  - Der **Kamera-Tab im Admin-Menü** sucht jetzt im Hintergrund (zeigt „Suche Kameras…") und
    cacht das Ergebnis — vorher fror der Tab bei jedem Aufruf ~8s ein („Admin-Menü träge").
- **Ladebalken im Willkommensscreen bewegt sich wieder:** Der eingebaute „indeterminate"-Modus
  animiert nur bei freier Tk-Mainloop — beim Booten war der Haupt-Thread aber beschäftigt, der
  Balken fror ein und zuckte erst kurz vor dem Verschwinden. Jetzt eine eigene, ressourcen-
  schonende Ping-Pong-Animation, die zuverlässig „die Box arbeitet" signalisiert (Startscreen
  per after-Schleife, Startup-Screen schrittweise bei jedem Boot-Schritt).

---

## [2.4.22] - 2026-08-11 - Firmen-WLAN-Selbstheilung (47 stumme Boxen)

> Anlass: 47 Flotten-Boxen melden sich nie im Dashboard, weil die WLAN-Anmeldung klemmt —
> und ohne WLAN bekommen sie auch keine Updates (Teufelskreis). Das Mitarbeiter-Skript half
> nur teilweise, weil das exportierte Profil-Passwort maschinengebunden verschlüsselt ist
> (passt nur auf Boxen mit identischem Klon-Image).

### Neu

- **WLAN-Selbstheilung in der App** (`src/utils/company_wlan.py`): Beim Start prüft die Box,
  ob das Firmen-WLAN im Funk SICHTBAR, aber nicht verbunden ist (= Werkstatt, Anmeldung
  klemmt). Dann legt sie das Profil selbst frisch an — mit Klartext-Schlüssel (funktioniert
  auf jedem Image) und den zwei entscheidenden Einstellungen: automatisch verbinden AN,
  MAC-Randomisierung AUS — und verbindet. Zusätzlich werden Alt-Profile der anderen
  fexon-Netze entfernt — nur EIN Verbindungs-Profil pro Box (Erkenntnis Werkstatt: mehrere
  Auto-Verbinden-Profile lassen Windows zwischen den Netzen springen; die Erkennungs-
  Whitelist `company_wifi_ssids` bleibt unverändert). Beim Kunden ist das Netz nie
  sichtbar → dort passiert nie etwas. Auch als neuer Schnellhilfe-Schritt „Firmen-WLAN".
- **Installer richtet das Firmen-WLAN jetzt als Pflicht-Schritt ein** (still, kein Neustart
  nötig; `setup/company_wlan_setup.ps1`) — durchbricht bei den 47 stummen Boxen den
  Teufelskreis beim einmaligen USB-Update. Hotspot-Einrichtung ist im Installer jetzt
  standardmäßig angehakt (vorher abgewählt!).
- **3198-Menü: „WLAN-Radikal-Reparatur"** (Werkstatt, Zwei-Klick-Bestätigung): Netzwerk-
  Werksreset (TCP/IP, Winsock, DNS, alle Profile) + Firmen-WLAN-Profil sofort frisch
  anlegen (nie 0 Profile — der Gäste-Hotspot braucht mindestens eins!) + automatischer
  Neustart. Zusätzlich `setup/werkstatt_netzwerk_reset.bat` für Boxen, auf denen die App
  gar nicht startet.

---

## [2.4.21] - 2026-08-07 - Boxen melden Event-Statistiken automatisch ans Dashboard

### Neu

- **Event-Statistiken automatisch ans Dashboard** (Wunsch Christian): Der Monitoring-Heartbeat
  (läuft ohnehin bei jedem Start im Firmen-WLAN) sendet jetzt die Statistik der letzten bis zu
  10 Buchungen mit (Sessions, Fotos, Drucke erfolgreich/fehlgeschlagen, Zeitraum). Das Dashboard
  zeigt sie als Kachel „Box-Statistik" auf der Buchungs-Detailseite — bei Rückläufern mit Alarm
  genügt es also, die Box in der Werkstatt anzuschalten, und die Zahlen stehen an der Buchung.
  Kein Button, keine Handgriffe; Duplikate werden serverseitig zusammengeführt.

### Hinweis

- Release v2.4.20 wurde vor Verteilung pausiert (Draft) — der Rollout an die Flotte passiert
  mit dieser Version 2.4.21 in einem Rutsch.

---

## [2.4.20] - 2026-08-07 - Fehlerdialog beim Beenden behoben

### Behoben

- **PyInstaller-Fehlerdialog beim App-Beenden** („'NoneType' object has no attribute 'flush'",
  Screenshot Christian): Der harte Exit aus 2.4.18 rief `logging.shutdown()` ungeschützt auf —
  im Fenster-Build (ohne Konsole) wirft colorama beim Stream-Flush eine Exception. Jetzt
  abgefangen (gleiche Absicherung wie im OTA-Pfad `_quit_for_update`). Nachtest-Log 2.4.19
  bestätigt sonst alles: BILDER-Migration (583 Dateien), System-Test-Messwerte inkl.
  korrekter „DRUCKER AUS!"-Auffälligkeit, Schnellhilfe alle 5 Schritte ok.

---

## [2.4.19] - 2026-08-07 - System-Test misst jetzt wirklich (Selbsttest mit Schwellwerten)

### Geändert

- **System-Test nach Event-Wechsel ist jetzt ein echter Selbsttest** (Wunsch Christian):
  Bisher wurde nur das Template befüllt und gedruckt — Probleme fielen nicht auf. Jetzt wird
  jeder Schritt **gemessen und gegen Schwellwerte einer gesunden Box verglichen**:
  - **Neuer erster Schritt „System prüfen":** Speicherplatz (< 5 GB → Warnung),
    Festplatten-Schreibtest 8 MB mit echtem Sync (< 8 MB/s → „Festplatte sehr langsam" —
    eMMC-Frühwarnung), Hintergrund-CPU-Last (> 70 % → Warnung) + `SYSTEM-LAST`-Störer-Analyse
    ins Log.
  - **Kamera prüfen:** Startzeit (> 5 s → Warnung) und Liefergeschwindigkeit über 15 frische
    Frames — entlarvt den YUY2-Codec-Fallback (1080p bricht dann von ~30 auf ~5 fps ein)
    und lahme DSLR-Bridges.
  - **Template rendern** (> 4,5 s → Warnung) und **Druck-Übergabe an den Spooler**
    (> 10 s → Warnung); vor dem Druck wird zusätzlich der Drucker-Status abgefragt und
    eine Fehlermeldung als Auffälligkeit angezeigt.
  - Ergebnis: Grün „Alle Messwerte im Normalbereich", Orange „Test bestanden, aber mit
    Auffälligkeiten: …" (Klartext mit Handlungshinweis), Rot wie bisher bei echten Fehlern.
    Alle Messwerte landen als eine `SYSTEMTEST-MESSWERTE:`-Zeile im Log (gut vergleichbar).
  - Testdruck und Ablauf bleiben wie gewohnt; Timeout 90 → 120 s (neue Messungen).

### Behoben

- **KRITISCH: OTA-Update löschte alle Fotos.** Die Bilder lagen im Build unter
  `_internal\BILDER` (Pfad wurde relativ zum Code aufgelöst) — das Update-BAT ersetzt
  `_internal` aber atomar und löscht den alten Stand; sein „BILDER/ wird geschützt" galt nur
  für den Install-Root. **Fix:** BILDER liegt jetzt neben der EXE (`C:\FexoBooth\BILDER`,
  gleiches Muster wie `config.json`); beim ersten Start werden vorhandene Bilder automatisch
  aus `_internal\BILDER` dorthin migriert (Log: `BILDER-Migration: N Dateien …`). Zusätzlich
  rettet das ab jetzt erzeugte Update-BAT als Sicherheitsnetz Rest-Fotos aus
  `_internal_OLD\BILDER` vor dem Löschen. ⚠️ Achtung: Beim Update **AUF** diese Version läuft
  noch das alte BAT der Vorversion — dort vorher Bilder sichern!

### Geändert (Auto-Update)

- **Updates brauchen jetzt eine Bestätigung am Bildschirm** (Wunsch Christian): Statt sofort
  loszulegen zeigt der Update-Dialog „Update verfügbar — Soll das Update jetzt installiert
  werden?" mit Warnhinweis auf ungesicherte Bilder und den Buttons **„Jetzt installieren"** /
  **„Später"**. Ohne Antwort schließt sich der Dialog nach 5 Minuten und es wird NICHTS
  installiert (beim nächsten App-Start kommt die Frage erneut). Der frühere stille
  Fallback-Pfad (Update ohne UI) installiert ebenfalls nicht mehr, sondern loggt nur.

---

## [2.4.18] - 2026-08-07 - Schnellhilfe-Button im Kunden-Menü + sauberes App-Beenden

### Neu

- **„🔧 Schnellhilfe" im Kunden-Menü (PIN 2015):** Ein Button für die Telefon-Hotline bei
  „Box ist langsam / hängt". Führt automatisch aus (jeder Schritt einzeln geloggt mit Präfix
  `SCHNELLHILFE:`): Systemlast-Diagnose ins Log → Prozess-Priorität + Leistungsregler neu
  setzen → alte Template-Temp-Ordner aufräumen (>24h) → Druckerwarteschlange zurücksetzen
  (Spooler-Neustart) → Kamera-Reset. Danach Empfehlung mit **Neustart-Button** (echter
  Windows-Neustart = wirksamster Schritt). Alle 7 Sprachen (`service.quick_fix*`),
  Felix-Hotline-Runbook + Übersetzungs-Inventar aktualisiert.

### Behoben

- **EXE lief nach Menü-Beenden mit 0 % weiter** (Befund Christian beim Update-Installieren:
  „Anwendung läuft noch", Task-Manager nötig): Nach dem Ende der Tk-Hauptschleife hielten
  non-daemon Hintergrund-Threads (Galerie-Server/Hotspot) den Prozess am Leben. Jetzt beendet
  `main.py` den Prozess nach dem Aufräumen hart (`os._exit(0)` — gleiches Muster wie beim
  App-OTA). Gilt für alle Beenden-Wege (Admin-Menü 3198, Notfall-Beenden, Fehlerpfad).

---

## [2.4.17] - 2026-08-07 - Kamera-Check ohne UI-Freeze, Auslöse-Screen entfernt, Windows-Fixes

> Anlass: Nachtest-Log 2.4.16 (`fexobooth_20260807_101128.log`) — die LiveView-Umbauten greifen
> (8,5 statt 2,5–5 fps, Anzeige nur noch 56 ms im UI-Thread), aber das Log zeigte drei neue
> Bremsen und Christian wünschte den Wegfall des Auslöse-Bild-Screens.

### Behoben

- **Kamera-Status-Check blockierte den UI-Thread massiv:** Ohne konfigurierte Kamera lief die
  volle PowerShell-Geräte-Enumeration (Timeouts!) auf dem UI-Thread → beim Start bis zu
  **16,5 s eingefrorene Oberfläche**, danach alle 15 s eine cv2-Testöffnung (~500 ms Hänger im
  Leerlauf — exakt der Takt aus dem Log). Die Prüfung läuft jetzt im Hintergrund-Thread; geprüft
  wird nur auf dem Start-Screen bei nicht initialisierter Kamera (keine Kollision mit
  Session-Start/EDSDK), immer nur eine Prüfung gleichzeitig.
- **Prozess-Priorität griff nicht** (`SetPriorityClass=0` im Log): Der ctypes-Aufruf übergab den
  GetCurrentProcess-Pseudo-Handle falsch. Jetzt über psutil — verifiziert (nice=32768).
- **Leistungsregler mit Verifikation:** Die API meldete Erfolg, der Regler stand aber nicht auf
  Maximum. Jetzt wird nach dem Setzen das tatsächlich aktive Overlay zurückgelesen und geloggt
  (VERIFIZIERT / Warnung mit aktivem Zustand); zusätzlich wird geprüft, ob überhaupt der
  Basis-Plan „Ausbalanciert" aktiv ist — nur dort existiert der Regler.

### Entfernt

- **Auslöse-Bild-Screen („foto-screen.jpeg") + „Foto wird aufgenommen…"-Text** (Wunsch
  Christian): Beides überbrückte die früher lange Umschaltzeit; seit dem LiveView-Worker wirkt es
  nur noch als Geflacker. Ablauf jetzt: Countdown → kurzer weißer Auslöse-Blitz → letztes
  LiveView-Bild steht ~1,8 s → Foto erscheint. Admin-Menü: Datei-Wahl „Bild beim Foto-Auslösen"
  und Regler „Auslöse-Bild" entfernt (Config-Keys `flash_image`/`flash_duration` bleiben
  ignoriert bestehen — kein Migrationsbedarf).

---

## [2.4.16] - 2026-08-07 - LiveView-Performance: Bildaufbereitung raus aus dem UI-Thread

> Anlass: Stresstest-Log `fexobooth_20260806_142249.log` (Miix, Webcam-Box) — LiveView schaffte
> 2,5–5 fps statt 20, weil die komplette Bildaufbereitung (~150 ms/Frame) im Tk-UI-Thread lief;
> dazu >140 UI-Hitches in 16 Minuten. In Einzelfällen kippt das mit Windows-Hintergrundlast
> (Defender/Update) ins „Box hängt".

### Geändert

- **LiveView-Worker-Thread:** Kamera-Read, Spiegeln, Template-Overlay, Countdown-Zahl und die
  komplette Skalierung auf Anzeigegröße laufen jetzt in einem Hintergrund-Thread. Der UI-Thread
  zeigt nur noch das fertige Bild an (Frames werden exakt auf die CTkImage-Zielgröße vorskaliert
  → PIL-Copy-Fastpath, keine Skalierung mehr im UI-Thread). Touch/Buttons bleiben dadurch auch
  bei voller LiveView-Last reaktionsfähig.
- **Overlay-Schnellpfad:** Statisches Komposit (bereits aufgenommene Fotos + Template-Overlay)
  wird pro Foto-Wechsel EINMAL vorberechnet; pro Frame wird nur noch die aktuelle Box gefüllt
  und der kleine Overlay-Ausschnitt darübergelegt (Cover-Fit per OpenCV statt PIL). Ergebnis
  pixelidentisch (headless verifiziert), ~1,4× schneller.
- **Adaptive Taktung statt starrer 20 fps:** Der Worker hält nach jedem Frame mindestens ~1/3
  der Frame-Zeit Pause (sättigt die CPU nie komplett); der UI-Anzeige-Takt passt sich den
  gemessenen Anzeige-Kosten an (Vorschau darf max. ~1/3 der UI-Thread-Zeit kosten).
- **Countdown-Font gecacht** (wurde bisher pro Frame neu von Platte geladen).

### Neu

- **Windows-Leistung beim Start:** Prozess-Priorität wird auf ABOVE_NORMAL gehoben und der
  Windows-Leistungsregler automatisch auf „Beste Leistung" gestellt (PowerSetActiveOverlayScheme —
  dieselbe API wie der Schieberegler im Akku-Flyout, kein Admin nötig; der Miix drosselt im
  Standard-Modus spürbar). Neues Modul `src/utils/system_load.py`.
- **Systemlast-Diagnose (Dev-Mode):** Beim App-Start und bei UI-Hängern > 1 s loggt die Box
  `SYSTEM-LAST: ...` mit CPU/RAM, Top-3-Prozessen und benannten Störern (Defender-Scan,
  Windows-Update-Installer, Such-Indexer, …) — Feld-Hänger sind damit im Log sofort erklärbar.
  Max. 1 Schnappschuss/Minute, läuft im Hintergrund-Thread.

---

## [2.4.15] - 2026-08-06 - Drucker-Fehlerfenster: Service-Ausstieg per PIN

### Behoben

- **Blockierendes Drucker-Fehlerfenster ließ sich nicht schließen** (Bug-Report #49 Werkstatt):
  Hing ein Druckjob, ohne dass der Drucker selbst einen Fehler meldete, schlug der
  „Problem behoben"-Check endlos fehl — die Box musste hart ausgeschaltet werden.
  Jetzt sitzt oben rechts im Fehlerfenster ein unauffälliges ✕: Nach PIN-Eingabe
  (Service 6588, Admin-PIN oder Kundenmenü 2015 für die Hotline) schließt sich das
  Fenster und bleibt 10 Minuten weg; die rote Top-Bar-Warnung bleibt sichtbar.
  Neue i18n-Keys `printer.service_pin_title`/`printer.service_pin_wrong` (7 Sprachen),
  Felix-Hotline-Runbook ergänzt.

---

## [Unreleased] - App-Plattform-Fundament (Box-Seite)

Einmaliger, zukunftssicherer Box-Umbau, damit künftige Features rein per App-Update kommen.
Alles additiv und performance-neutral; die gebuchte Galerie verhält sich unverändert.

### Neu

- **Thumbnail-Cache `BILDER/.thumbs/`** (Plan „Offline-Galerie" Etappe 2, 2026-07-03): Jedes
  Galerie-Thumbnail wird nur noch EINMAL gerechnet (Pillow) und danach als Datei direkt
  ausgeliefert (`send_file`) — vorher rechnete die Box dasselbe Thumbnail bei JEDEM Abruf neu
  (5 scrollende Gäste = 5× dieselbe Last auf dem Miix 310). Web-Galerie (`/thumb/...`) und
  App-API (`/api/v1/thumb/...`) teilen sich denselben Cache; wird ein Foto ersetzt (Quelle
  neuer als Cache), rechnet die Box automatisch neu. Der Event-Wechsel
  (`delete_all_images()`) räumt `.thumbs` mit ab. Cache-Schreiben ist best-effort und atomar
  (tmp + `os.replace`), Fehler stören die Auslieferung nie.

- **Startscreen zeigt die lokale Software-Version.** Oben links neben `FEXOBOOTH` steht jetzt die
  Build-Version aus `src/__init__.py`; die lokale Build-Quelle ist auf `2.4.14` angehoben, auch ohne
  bereits veröffentlichten GitHub-Release.
- **Webcam-Foto: MJPG-Codec statt unkomprimiertem YUY2.** Die Auflösungs-Umschaltung auf 1080p
  bleibt erhalten, kostete aber bisher ~1,3 s + ~0,7 s Auslesen pro Foto (Messung Miix 310).
  Der Codec wird jetzt NACH der Auflösung gesetzt und das Ergebnis verifiziert (der erste
  Versuch in 2.4.13 wurde von DirectShow zurückverhandelt und kostete sogar Zeit); lehnt die
  Kamera MJPG ab, merkt sich die Software das und verschwendet keine Zeit mehr pro Foto.
- **Final-Screen ruckelt nicht mehr beim Erzeugen:** Das Druckbild wird aus vorab verkleinerten
  Fotos gerechnet (2000 px, weiterhin >2× über dem 1800×1200-Druckbedarf — Qualität identisch).
  Vorher sättigten die 24/13,5-MP-Originale beide Prozessorkerne und die Bedienung stand ~3 s.
- **Filter-Screen:** Doppeltes Vorschau-Rechnen beim Betreten behoben; die Hintergrund-Vorschau
  macht kurze Pausen, damit Touch/LiveView flüssig bleiben.
- **Deutlich flüssiger auf dem Miix 310 (Messung per Dev-Log, Build 2.4.11 mit Nikon D3300):**
  - LiveView bricht nicht mehr mit jedem aufgenommenen Foto ein (vorher 7,7 → 1,8 fps): die
    bereits aufgenommenen Fotos werden im Template-Overlay nur noch beim Foto-Wechsel skaliert,
    nicht mehr bei jedem Frame.
  - Während der Fotoanzeige blockiert die Bedienung nicht mehr (vorher wurde das 24-MP-Foto
    10×/Sekunde neu skaliert → Dauer-Hänger ~300 ms; jetzt einmalig gecacht).
  - **Filter-Screen reagiert sofort:** Vorschauen rechnen auf verkleinerten Arbeitskopien statt
    auf den 24-MP-Originalen (vorher 96 MP pro Klick), und alle Filter werden im Hintergrund
    vorgerendert. Das gedruckte Bild rendert unverändert aus den Originalen.
  - **Final-Screen friert nicht mehr ein** (vorher 3,3 s UI-Blockade): Rendern + Speichern laufen
    im Hintergrund, der Gast sieht sofort „Druckdatei wird erzeugt..." (neuer i18n-Text
    `final.rendering` in allen 7 Sprachen), der Druck-Button ist bis zur Fertigstellung gesperrt.
    **Der Auto-Zurück-Countdown startet erst, wenn das Bild sichtbar ist und gedruckt werden
    kann** — die Wartezeit während des Erzeugens geht nicht mehr von der Gast-Zeit ab.
- **Nikon fotografiert in Größe „M" statt 24 MP** (neu: `nikon_bridge.image_size`, Standard `"M"`):
  Die Bridge stellt die JPEG-Größe der Kamera beim Verbinden automatisch um (D3300: 4496×3000
  statt 6000×4000). Für den 1800×1200-Druck mehr als ausreichend, und der USB-Transfer pro Foto
  wird deutlich kürzer (weniger sichtbare Wartezeit nach dem Auslösen). `"L"` = volle Auflösung,
  `""` = Kamera-Einstellung unangetastet lassen.
- **Nikon-Anbindung komplett neu: unsichtbare FexoNikonBridge statt digiCamControl.** Die D3300 wird
  vom offiziellen Nikon-SDK nicht unterstützt (kein Modul für die gesamte D3xxx-Serie); der bisherige
  digiCamControl-Ansatz scheiterte im Realtest (sichtbares Fremdfenster vor FexoBooth + Webserver auf
  `127.0.0.1:5513` antwortet ohne manuelle Einmal-Aktivierung nie). Neu: eigener versteckter
  Hintergrundprozess `bridge\FexoNikonBridge.exe` (C#/.NET 4.8, kein Fenster), Motor ist die
  MIT-lizenzierte digiCamControl-Kernbibliothek `CameraControl.Devices` (rohes PTP/MTP über die
  Windows-WPD-API — derselbe Weg wie dslrBooth). FexoBooth spricht die Bridge über stdin/stdout an
  (keine Ports, keine Firewall-Dialoge). `src/camera/nikon.py` ist jetzt der Bridge-Client;
  Config-Block `nikon_digicamcontrol` wurde durch `nikon_bridge` ersetzt.
- **Nikon-Developer-Diagnose** loggt im Developer Mode die effektive Nikon-Konfiguration, den
  Bridge-Status und alle geprüften `FexoNikonBridge.exe`-Pfade mit Trefferstatus.
- **Dev-Mode misst jetzt Performance:** `LIVEVIEW-PERF`-Summenzeile (~alle 5 s: effektive fps,
  ms pro Frame getrennt nach Kamera/Anzeige) und `UI-HITCH`-Monitor (loggt blockierte
  Tk-Hauptschleife >200 ms). Nur im Developer Mode aktiv, Live-Betrieb unverändert.
- **OTA-Updates liefern `bridge/` mit aus.** Sowohl das In-App-Update als auch
  `update_from_github.bat` kopieren den neuen `bridge\`-Ordner (FexoNikonBridge) mit und beenden
  eine ggf. noch laufende Bridge vor dem Kopieren. (Bootstrap-Hinweis: Das jeweils ERSTE Update
  auf diese Version läuft noch mit dem alten Update-Script — Nikon-Boxen einmalig per Installer
  aktualisieren.)
- **Lokaler Service-Kanal läuft dauerhaft.** Hotspot und lokale API laufen jetzt immer (4 s verzögert),
  entkoppelt von der gebuchten Galerie. Dadurch sind Template-/Settings-Korrektur und Software-Update
  per App auch ohne gebuchte Online-Galerie möglich.
- **`GET /api/v1/status`** meldet zusätzlich `software_version`, `gallery_enabled` und eine Capability-Liste
  (`settings_patch`, `template_upload`, `asset_upload`, `software_ota`, `feature_flags`), damit die App nur
  anbietet, was diese Box kann (Vorwärtskompatibilität).
- **Generische Apply-Endpunkte:** `POST /api/v1/apply/settings`, `apply/template` (Aliase auf die bestehenden
  `upload/*`), `apply/assets` (sicheres ZIP-Staging) und `apply/software` (Software-Update per App).
- **Software-Update per App (App-OTA):** `POST /api/v1/apply/software` mit SHA256-Verifikation und dem
  bestehenden Rollback; angewendet nur im Idle, abgesichert mit der Service-PIN 6588 (als HMAC, nicht im
  Klartext). Ersetzt das unzuverlässige Firmen-WLAN-OTA / USB-Hantieren.

### Geändert

- **Kunden-Menü (PIN 2015): „Windows Neustart" → „Neustart / Ausschalten".** Der bestehende Button
  öffnet jetzt eine Rückfrage mit **Neustart**, **Ausschalten** und **Abbrechen** — so kann die Box
  am Event-Ende auch sauber heruntergefahren werden (nicht nur neu gestartet). Kein zusätzlicher
  Button; Texte in allen 7 Sprachen, Felix-Hotline-Prompt entsprechend angepasst.
- **Foto-Galerie bleibt zahlendes Feature.** Obwohl der Server immer läuft, liefern alle Foto-/Galerie-Routes
  ohne gebuchte Galerie weiterhin nur eine Sperrseite bzw. 403. Am Box-Bildschirm ändert sich für
  Nicht-Galerie-Kunden nichts (kein QR, kein Banner).
- **Soft-Mode für settings.json bleibt bewusst aktiv** (keine Signaturpflicht); die irreführende
  Log-Warnung „in v2.5.0 wird das abgelehnt" wurde entfernt.

### Behoben

- **Top-Bar-Alarmmeldungen folgen jetzt der eingestellten Sprache.** USB-, Kamera- und Druckerwarnungen
  in der oberen Status-Leiste bleiben nicht mehr deutsch, wenn `locale` auf Englisch, Französisch,
  Niederländisch, Italienisch, Spanisch oder Polnisch steht. Interne Drucker-Fehlercodes bleiben deutsch,
  damit Overlay-Klassifizierung und Support-Runbooks stabil bleiben.
- **Druck-Korrektur aus dem 2015er-Menü bleibt jetzt dauerhaft erhalten.** Bisher wurden im
  Service-Menü angepasste Druckwerte (Offset X/Y, Zoom) bei jedem Neustart auf die Produktionswerte
  (40/30/103) zurückgesetzt, weil `print_adjustment` fälschlich in den bei jedem Start erzwungenen
  Produktions-Overrides stand. Ursache entfernt; der Start-Default kommt weiterhin aus `defaults.py`
  (identische Werte), der gewollte Reset pro Eventwechsel bleibt über `reset_event_defaults()` aktiv.
  Wichtig für den Einrichtungsflow (Box testen → herunterfahren → Kunde startet neu).
- **Nikon-Diagnoselogger crasht nicht mehr bei Windows-Encoding.** Der frühere `tasklist`-Prozess-Snapshot
  erzeugte auf deutschem Windows `UnicodeDecodeError`-Thread-Exceptions; mit der neuen Bridge-Architektur
  ist der `tasklist`-Aufruf komplett entfallen (die App kennt ihren eigenen Bridge-Prozess direkt).

## [2.4.7] - 2026-06-12 - Produktions-Defaults und persistente Box-Daten

### Behoben

- **OTA-Updates konnten Videos, Auslösebild und Produktions-Defaults verlieren.** Beim Start stellt die Software jetzt die festen Produktionswerte wieder her: Countdown `7 s`, Foto-Anzeige `3 s`, Auto-Return `20 s`, Auslösebild `100 ms`, max. Drucke `1`, Single-Foto aus, Performance-Modus an, Vollbild beim Start an, Fertig-Button ausgeblendet und Drucken aktiv.
- **Default-Medien sind fest verdrahtet:** Start-/Zwischenvideos, End-Video und Auslösebild werden auf die eingebauten Assets gesetzt und im PyInstaller-Build automatisch auf den echten `_internal\assets\...` Pfad aufgelöst.
- **WLAN-Hotspot bleibt auf Produktionsstandard:** SSID `fexobox-gallery`, Passwort `fotobox123`, Port `8080`.
- **Druck-Anpassung wird wieder auf Produktionswert gesetzt:** `X +40 px`, `Y +30 px`, `Zoom 103 %`, `Bleed 3 mm`.
- **Kunden-Begrüßungsscreen beim Start ist wieder sichtbar und bleibt mindestens 4 Sekunden stehen.** Zusätzlich erscheint ein früher Ladescreen direkt nach dem Kiosk-Fensteraufbau, während Kamera, USB, Templates und VLC vorbereitet werden.
- **Kurzes Konsolenfenster beim Firmen-WLAN-Check verhindert:** `netsh wlan show interfaces` läuft jetzt versteckt.
- **Statistik-Speichern nach OTA/Installer robuster:** `C:\ProgramData\FexoBox` wird vom Installer für den Kiosk-Benutzer beschreibbar gesetzt; falls eine alte Installation bereits falsche Rechte hinterlassen hat, nutzt die App einen update-sicheren lokalen Fallback.
- **USB-Sync-Check startet nicht mehr vor der Tk-Hauptschleife.** Dadurch verschwindet der Logfehler `main thread is not in main loop` beim Start.
- **Wiederholte Signatur-Warnungen reduziert:** Die periodische USB-Prüfung loggt unsignierte `settings.json` nicht mehr jede Sekunde, der Hinweis bleibt beim echten Laden der Buchung sichtbar.

### Geändert

- **Druck-Anpassung wird bei jedem Eventwechsel zurückgesetzt.** Auch wenn vorher im Admin-Menü anders kalibriert wurde, startet jedes neue Event wieder mit `X +40`, `Y +30`, `103 %`.
- **Box-spezifische Maschinenwerte werden nach ProgramData ausgelagert:** Box-ID, Drucker-Auswahl und Kamera-Grundwerte werden nach `C:\ProgramData\FexoBox\machine_settings.json` gespiegelt und nach Updates zurückgeholt.
- **Statistik und Drucker-Lifetime liegen update-sicher in ProgramData:** `fexobooth_statistics.json` und `printer_lifetime.json` werden nach `C:\ProgramData\FexoBox\` migriert.
- Der Installer löscht alte Statistik-/Lifetime-Dateien im Installationsordner nicht mehr, damit der erste Start von v2.4.7 sie migrieren kann.
- Die Begrüßung nutzt jetzt als Fallback den ersten Teil aus `customer.name`, wenn `shipping_first_name` in der `settings.json` fehlt.
- Im Kunden-Menü `2015` heißt `Template neu einlesen` jetzt `Event-Neu Einlesen`.

> Hinweis: Falls eine alte OTA-Version Statistikdateien bereits vor dem ersten Start von v2.4.7 gelöscht hat, kann die Software diese Werte nicht rekonstruieren. Ab v2.4.7 werden sie nicht mehr im ersetzten Installationsordner gespeichert.

---

## [2.4.6] - 2026-06-11 - Box-ID update-sicher außerhalb des Installationsordners

### Behoben

- **Box-ID konnte beim Update auf v2.4.5 trotzdem verloren gehen.** Ursache: Das Script, das beim OTA-Update die Dateien ersetzt, wird immer von der **alten, laufenden Version** erzeugt — nicht von der neuen. Eine Box, die von v2.4.4 (oder älter) auf v2.4.5 aktualisiert, führt also noch das fehlerhafte BAT-Script von v2.4.4 aus. Der v2.4.5-Schutz greift damit erst beim übernächsten Update (Selbst-Updater-Bootstrap-Problem).

### Neu

- **Box-ID wird zusätzlich außerhalb des Installationsordners gespeichert** (`C:\ProgramData\FexoBox\box_id.json`). Dieser Ort wird von keinem Update-Script jemals angefasst.
- Beim Speichern der Box-ID (Admin-Menü) wird sie automatisch dorthin gespiegelt.
- Beim Start wird die Box-ID von dort wiederhergestellt, falls `config.json` keine enthält — z.B. nach einem fehlerhaften Update.
- Damit überlebt die Box-ID **jedes** Update, unabhängig davon, welche Version das ersetzende Script erzeugt hat oder ob künftig ein Fehler im Updater auftritt.

> **Hinweis:** Boxen, die ihre ID bereits beim Update auf v2.4.5 verloren haben, müssen sie einmalig neu setzen. Danach ist sie dauerhaft geschützt.

---

## [2.4.5] - 2026-06-11 - Hotfix: Box-ID bleibt bei Updates erhalten

### Behoben

- **Box-ID/Seriennummer konnte beim GitHub-Update verloren gehen.** Ursache war ein Pfadproblem im PyInstaller-Build: Die App speicherte `config.json` je nach Laufzeit unter `_internal\config.json`, der OTA-Updater schützte aber nur `C:\FexoBooth\config.json`. Da `_internal` beim Update ersetzt wird, konnte die dort gespeicherte Box-ID verschwinden.
- `config.json` wird im EXE-Build künftig dauerhaft neben der EXE im Installationsordner gespeichert (`C:\FexoBooth\config.json`) und nicht mehr in `_internal`.
- Beim Start wird eine alte `_internal\config.json` automatisch erkannt, bevorzugt wenn sie eine Box-ID enthält, und in den neuen sicheren Pfad migriert.
- Der OTA-Updater und das manuelle `update_from_github.bat` sichern vor dem Ersetzen von `_internal` jetzt sowohl Root- als auch Legacy-Config und stellen die beste vorhandene Config nach dem Update wieder her.
- Der Installer übernimmt eine vorhandene Legacy-Config aus `_internal`, falls noch keine Root-Config existiert.

---

## [2.4.4] - 2026-06-11 - Tablet-UI, Filter-Timeout und Fehlerbilder

### Neu

- **Filter-Screen läuft nach Inaktivität automatisch weiter:** Nach 15 Sekunden ohne Touch-/Maus-Aktivität wird automatisch fortgesetzt. Sobald der Gast Filter antippt oder den Touchscreen berührt, startet der Timer neu.
- **Kompakter Filter-Screen für 10"-Tablets:** Die Template-Vorschau ist größer und die Filterauswahl liegt auf kleinen Displays als kompakte Leiste darunter.
- **Fehlerbilder für Druckerfehler:** Der große Drucker-Fehlerscreen und die kleine Warnung vor dem Druck zeigen passende Illustrationen aus `assets/error_images/`, wenn vorhanden.
- **Auslöse-Blitz:** Beim tatsächlichen Capture erscheint ein sehr kurzer weißer Flash über dem LiveView, damit der Gast den Aufnahmezeitpunkt erkennt.

### Behoben

- **Drucker-Fehlerscreen schnitt Text ab:** Karte, Schriftgrößen und Textumbrüche sind jetzt responsiver, damit Fehlertext, Anweisung und Button auf 1280x800 sichtbar bleiben.
- **QR-Code überlappte Template-Anzeige:** Der Startscreen verkleinert Template-Karten und QR-Banner auf kompakten Displays, wenn Galerie-QR aktiv ist.
- **Admin-Minimieren ohne Funktion:** Der Admin-Dialog kann jetzt kiosk-sicher ausgeblendet und über einen kleinen Restore-Button wieder geöffnet werden, ohne Windows/Taskleiste freizugeben.
- **Finalscreen-Druckerwarnung ordnet Papier/Kassette/Tinte konsistenter zu:** `KEIN PAPIER / KASSETTE!` wird nicht mehr als "Drucker aus" behandelt.

### Geändert

- **Default für Auslösebild-Anzeigedauer:** `flash_duration` ist für neue Installationen jetzt `100 ms` statt `300 ms`. Bestehende `config.json`-Werte werden dadurch nicht überschrieben.

---

## [2.4.3] - 2026-05-04 - BAT-Script-Härtung + Update-Überspringen-Button

### Neu — Druck-Defaults: +30 / +30 / 103 %

`print_adjustment` Default-Werte in [defaults.py](src/config/defaults.py) angepasst auf die Werte, die sich auf den meisten Boxen ohne weitere Kalibrierung als Standard etabliert haben:

- `offset_x: 30` (vorher 0)
- `offset_y: 30` (vorher 0)
- `zoom: 103` (unverändert)
- `bleed_mm: 3` (unverändert)

**Wichtig:** Gilt nur für **frische Installationen**. Bestehende `config.json` wird beim Update **nicht** überschrieben — Boxen mit individuell kalibrierten Werten behalten ihre.

### Neu — "Überspringen"-Button im UpdateProgressDialog

Wenn ein Update gerade läuft (Auto-Update im Firmen-WLAN oder manuell), kann es jetzt am Display abgelehnt werden. Hintergrund: Updates beim Eintreffen einer Kunden-Box können stören (Box wird gerade vorbereitet, kein guter Zeitpunkt für ungeplanten Neustart).

- Kleiner sekundärer Button **"Überspringen"** unten im Dialog während des Downloads.
- Klick → `cancel_event` wird gesetzt → `download_update()` bricht im Read-Loop zwischen Chunks ab → ZIP wird gelöscht → Dialog schließt sich → alte App läuft normal weiter.
- Sobald die Installations-Phase begonnen hat (BAT-Script läuft gleich), wird der Button automatisch ausgeblendet — Cancel ist ab dem Punkt nicht mehr sicher möglich.
- Beim **nächsten** App-Start (oder beim nächsten Auto-Update-Check) wird das Update wieder angeboten — kein dauerhaftes Verstecken dieser Version.

Implementierung:
- `UpdateCancelled` Exception in [updater.py](src/updater.py)
- `download_update()` bekommt optionalen `cancel_event: threading.Event` Parameter
- Cancel-Check zwischen jedem Chunk im Download-Loop
- `UpdateProgressDialog`-Worker fängt `UpdateCancelled` ab und macht KEIN Apply



### Behoben

**1. Update-Bug v2: Halbherzige Updates ließen pywin32 verschwinden**

Trotz v2.4.2-ZIP-Validierung in Python kam beim Kunden derselbe Fehler nochmal — Box war noch auf einer älteren Version (vor v2.4.2), daher griff die Python-Validierung nicht. Folgen:
- "Druck nur unter Windows verfügbar" im Service-Test, weil `pywin32` (= `win32print`) im halbherzig kopierten `_internal/` fehlte.
- Druck-Korrekturwerte (`offset_x/y`, `zoom`) auf Defaults zurückgesetzt — `config.json` ging beim teilweise gelaufenen Update kaputt, App erzeugte sie mit Defaults neu.

**Root Cause:** `xcopy /E /I /Y /Q` setzt `errorlevel` auf 0 auch wenn 0 Files kopiert wurden (wenn das Source-Verzeichnis leer war). Das alte BAT-Script erkannte den teilweise erfolgreichen Update nicht und überschrieb `_internal/` mit einem unvollständigen Stand.

### Fix in [updater.py](src/updater.py) — knallharte BAT-Härtung

1. **Pre-Check VOR jedem Anfassen** des Install-Dirs:
   - `%SOURCE_DIR%\_internal\` muss existieren
   - `%SOURCE_DIR%\_internal\base_library.zip` muss existieren (Pflicht-File jeder PyInstaller-Build)
   - `%SOURCE_DIR%\_internal\win32\` ODER `pywin32_system32\` muss existieren (sonst geht der Druck nicht)
   - Wenn auch nur einer dieser Checks fehlschlägt → **Abbruch BEVOR irgendwas am Tablet berührt wird**, alte App startet automatisch neu.

2. **Post-Check nach xcopy:** explizit prüfen ob `_internal\base_library.zip` im Ziel angekommen ist — falls nicht trotz `errorlevel 0`: erzwungener Rollback.

3. **`config.json`-Backup vor jedem Eingriff:** Datei wird nach `%TEMP%\fexobooth_config_backup_<RANDOM>.json` kopiert. Falls sie während des Updates verloren geht → automatisches Restore am Ende (sowohl im Erfolgs- als auch im Fehlerpfad). Schützt vor Druck-Korrekturwerte-Reset.

4. **`pause` raus, `timeout /t 8 /nobreak` rein:** CMD-Fenster schließt sich nach 8 s automatisch — auch im Fehlerpfad. Verhindert dass das schwarze Fenster das UI blockiert (Bug 04.05.2026).

5. **Auto-Restart der alten App** in **jedem** Fehlerpfad. Kein Pfad führt mehr zu einer Box ohne UI:
   - Pre-Check fehlgeschlagen → `:restart_old`
   - `_internal/` gelockt → `:restart_old`
   - xcopy-Fehler → `:rollback_internal` → `:restart_old`
   - Post-Check Pflicht-Datei fehlt → `:rollback_internal` → `:restart_old`

6. **Selbst-Löschung des BAT-Scripts** in beiden Exit-Pfaden (Erfolg + Fehler). Keine alten Update-Scripts in `%TEMP%`.

### Was die Box macht wenn das nächste Update kaputt ankommt

- Schwarzes CMD-Fenster für maximal 8 Sekunden, danach weg.
- Photobooth-UI startet automatisch wieder mit alter Version.
- Druck-Korrekturwerte bleiben erhalten (config.json-Backup).
- Druck funktioniert weiter (kein halbherziger pywin32-Replace).

### Wichtig

Wie alle BAT-Script-Verbesserungen wirkt das **erst wenn die Box bereits v2.4.3 läuft** (das BAT wird vom laufenden Updater erzeugt). Boxen auf älteren Versionen müssen einmalig manuell via `FexoBooth_Setup_2.1.exe` aktualisiert werden, danach sind sie geschützt.

---

## [2.4.2] - 2026-05-04 - Update-ZIP-Validierung + Service-Menü Z-Order

### Behoben

**1. Update-Bug: BAT-Script scheiterte an truncated ZIP, Box ohne UI**

Symptom (Bild von Christian): nach Auto-Update bleibt ein schwarzes CMD-Fenster sichtbar mit:
> *"Das Ende des Datensatzes im zentralen Verzeichnis wurde nicht gefunden"*

Anschließend: *"Datei _internal nicht gefunden, 0 Datei(en) kopiert, FEHLER: Kopieren fehlgeschlagen — Rollback auf alte Version"*. Box hat zwar die alte Version, aber kein Photobooth-UI mehr (CMD-Fenster blockiert).

**Ursache:** `download_update()` validierte weder `Content-Length` noch ZIP-Integrität. Wenn das WLAN während des Downloads kurz wegbrach, schrieb der Code eine teilweise ZIP und meldete trotzdem "Download abgeschlossen". `apply_update_and_restart()` startete dann das BAT-Script mit kaputter ZIP, App machte `os._exit(0)`, BAT scheiterte beim Entpacken — und zeigte nur noch das CMD-Fenster.

**Fix in [updater.py](src/updater.py):**
- **`f.flush()` + `os.fsync()`** nach Download — Disk-Buffer ist garantiert geschrieben bevor wir validieren oder die App terminiert wird.
- **Content-Length-Check:** Wenn der Server "150 MB" angekündigt hat aber nur 80 MB ankamen → `ConnectionError` mit klarer Meldung. ZIP wird gelöscht, kein BAT-Start.
- **`zipfile.testzip()`-Validierung:** Doppelte Sicherheit, prüft die internen Checksummen aller Einträge. Falls trotz korrekter Bytes-Anzahl irgendwo ein Bit kippte, wird das hier erkannt.
- Bei beiden Fehlern: ZIP wird sofort gelöscht, `download_update()` wirft `ConnectionError`. Der UpdateProgressDialog zeigt "Update fehlgeschlagen", die alte App läuft weiter.

**2. Service-Menü (PIN 6588) ploppte in den Hintergrund — Box reagierte nicht mehr**

Gleicher Bug wie Admin-Dialog vor v2.3.2: dem ServiceDialog fehlte `attributes("-topmost", True)`. Daraufhin konnte das Root-Window (durch `_check_fullscreen_restore()` oder andere Win32-Calls) den Dialog überdecken — Foto-UI sichtbar, aber Service-Menü unerreichbar.

**Fix in [service.py:55](src/ui/screens/service.py):** `self.attributes("-topmost", True)` direkt nach `overrideredirect(True)`. Identische Lösung wie für AdminDialog in v2.3.2.

---

## [2.4.1] - 2026-04-30 - Auto-Update sichtbar + Deploy-Skript-Fallback

### Behoben
- **Auto-Update lief vollkommen unsichtbar.** Wenn die Box im Firmen-WLAN war und ein Update geladen hat, sah der Mitarbeiter nur, dass die Box plötzlich neu startete — wie ein Crash. Im Code stand explizit "*Wird VOLLKOMMEN still ausgeführt — keine UI, keine Dialoge*". Daraufhin nicht mehr klar, ob das Update lief, abstürzte oder etwas anderes passierte.

### Fix — UpdateProgressDialog auch beim Auto-Update
- [company_network.py](src/company_network.py): `check_and_auto_update()` bekommt einen optionalen `app`-Parameter. Wenn vorhanden, öffnet der Background-Worker bei verfügbarem Update den **gleichen Fullscreen-`UpdateProgressDialog`** wie beim manuellen Update über Service-Menü 6588 (Titel, MB-Counter, Progress-Bar, "Bitte nicht ausschalten").
- Dialog erledigt Download + Apply + `os._exit(0)` selbst — keine doppelte Logik.
- Bei Fehlern beim Dialog-Öffnen: Fallback auf den alten stillen Pfad (`_silent_fallback()`), damit das Update auch ohne UI durchlaufen kann.
- Aufruf in [app.py](src/app.py) erweitert: `check_and_auto_update(..., app=self)`.

### Bonus — Deploy-Skript: Drei-Stufen-Fallback bei Image-Auswahl
- [custom-ocs-deploy](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy): Smart-Check zur NTFS-Datennutzung hatte nur einen Pfad (`partclone.chkimg`). Wenn der fehlschlug → Abbruch, Tablet bleibt unverändert. Auf 32-GB-Tablets mit 64-GB-Master-Image war das ein Showstopper.
- **Stufe 1 (genau, wie bisher):** `partclone.chkimg` streamt das XZ-Image und liefert die exakte NTFS-Datennutzung.
- **Stufe 2 (NEU, Schätzung):** XZ-Image-Größe × 2.2 als konservative Obergrenze (NTFS-XZ-Ratio ~45–50 %).
- **Stufe 3 (NEU, Worst-Case):** NTFS-Partitionsgröße aus `dev-fs.list`. Wenn die Partition selbst ins Ziel passt, schrumpft Clonezilla mit `ocs-expand-gpt-pt -icds` proportional.
- Bei `partclone.chkimg`-Fehler wird das Failure-Log nun nach `/home/partimag/deploy-logs/chkimg-failure-*.log` kopiert (statt stillem `rm`), damit Diagnose im Nachhinein möglich ist.
- 64→64-Pfad bleibt unverändert (Direct-Match in [Zeile 343](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy#L343)) — Fallback-Logik wird nur betreten, wenn Direct-Match versagt.

---

## [2.4.0] - 2026-04-30 - HMAC-Signatur (Soft-Mode) + Spiegel-Bug im Auto-Test

### Behoben
- **System-Test (Auto-Test für neue Events) spiegelte das Test-Foto fälschlicherweise.** [system_test.py:384](src/ui/dialogs/system_test.py#L384) hatte ein verschollenes `cv2.flip(frame, 1)`, obwohl die Capture-Pfade in [session.py](src/ui/screens/session.py) bewusst nicht spiegeln (siehe v2.2.3-Fix). Folge: der Print im Systemtest sah seitenverkehrt aus, obwohl echte Capture-Prints korrekt waren.

### Neu — settings.json HMAC-Signatur (Soft-Mode)
Vorbereitung für nachträgliche Upgrade-Buchungen über das Kundenportal: settings.json kann ab sofort vom Laravel-Backend mit HMAC-SHA256 signiert werden. Verhindert, dass Kunden lokal Features wie `dslr_camera`, `fullframe_prints` oder `max_prints` manipulieren.

- **Neues Feld `_signature`** in der settings.json (Format: `hmac_sha256:<hex>`)
- **Soft-Mode aktiv (v2.4.x):**
  - Unsigned-JSONs werden weiterhin akzeptiert, aber mit Log-Warning markiert (Migration zu Laravel-Signing).
  - Signed-JSONs mit korrektem HMAC werden akzeptiert.
  - **Signed-JSONs mit falschem HMAC werden IMMER abgelehnt** — auch im Soft-Mode (Manipulationsversuch).
- **Geprüft an drei Einstiegspunkten** in [booking.py](src/storage/booking.py):
  1. `_find_settings_file()` — manipulierte JSONs werden gar nicht erst als Kandidat aufgenommen.
  2. `check_usb_for_new_booking()` — keine "neue Buchung erkannt"-Meldung bei kaputter Signatur.
  3. `load_from_usb()` — Final-Check vor dem Cachen.
- **Cache** (`.booking_cache/last_booking.json`) bleibt unsigniert — wird nur lokal von der Box selbst geschrieben, ist nicht über USB einspielbar.
- **Strict-Mode geplant für v2.5.0** nach Stabilisierungsphase.

### Konfiguration
- HMAC-Geheimnis aktuell als Konstante `_HMAC_SECRET` in `src/storage/booking.py`. Muss identisch zum Laravel-`SETTINGS_HMAC_SECRET` sein, sobald Laravel Signing scharf schaltet. Build-Zeit-Override via PyInstaller folgt sobald Laravel-Seite produktiv signiert.

---

## [2.3.3] - 2026-04-30 - Service-Menü: responsiv für Quer- und Hochformat

### Behoben
- **Service-Menü (PIN 6588) war im Querformat unten abgeschnitten** — Card war 500 px breit + Buttons untereinander gestapelt, das ergab eine schmale hohe Card die auf 1280×800 nicht in die Höhe passte.

### Fix — adaptives Layout
- **Querformat (Width ≥ Height):** Card 900 × 650, Buttons in **2×2 Grid** angeordnet. Passt komfortabel auf 1280×800.
- **Hochformat (Width < Height):** Card 520 × 92% Höhe, Buttons untereinander wie vorher.
- **Compact-Modus bei `screen_height < 700`:** kleinere Buttons + Paddings.
- **Status-Bereich + Versions-Info am unteren Rand der Card** — immer sichtbar, nicht in einem Scrollbereich versteckt.

---

## [2.3.2] - 2026-04-30 - Admin-Dialog: topmost + Datei-Dialog-Fix

### Behoben
- **Admin-Dialog verschwand wenn ein Datei-Auswahl-Dialog geöffnet wurde** (📁-Button im Admin-Menü). Der Dialog wurde nicht zerstört — er rutschte hinter das Kiosk-Root-Fullscreen, weil ihm `attributes("-topmost", True)` fehlte. Andere Dialoge in der App (FexosafeBackup, UpdateProgress) hatten das schon korrekt.

### Fix
1. `AdminDialog.__init__()`: `attributes("-topmost", True)` gesetzt — Dialog bleibt immer vor dem Root sichtbar.
2. `_create_file_picker()` browse-Funktion: Vor `filedialog.askopenfilename()` topmost kurz auf `False` (damit der Datei-Dialog überhaupt **vor** dem Admin-Dialog erscheinen kann), danach wieder `True` + `lift()` + `focus_force()`. Plus `parent=self` als Hinweis ans OS.
3. CSV-Export (`asksaveasfilename`): identische Logik.

---

## [2.3.1] - 2026-04-29 - Admin-Dialog: Z-Order-Fix + Diagnose-Logging

### Behoben
- **Admin-Dialog (PIN 3198) schloss sich nach wenigen Sekunden** und der ADMIN-Button reagierte danach nicht mehr (User-Bericht: tritt auch mit Maus auf, also nicht Touch-Race). Mein Fix in v2.2.9 (Click-outside-Handler entfernt) war nicht der echte Grund.
- Wahrscheinliche Ursache: `_check_fullscreen_restore()` läuft alle 5 s und rief `_hide_taskbar()` auf (Win32-`ShowWindow`-Calls) — auch bei offenem Dialog (kein Toplevel-Check im else-Zweig). Win32-Calls können den Z-Order stören → Dialog verschwindet hinter dem Root-Window.

### Fix
- `_check_fullscreen_restore()` macht jetzt **gar nichts** wenn ein Toplevel-Dialog offen ist — auch keine Taskleisten-Operationen.
- Toplevel-Erkennung erweitert: prüft `winfo_class()=="Toplevel"` UND `isinstance(child, CTkToplevel)`.

### Diagnose
- `AdminDialog.destroy()` loggt jetzt den **vollständigen Caller-Stack**. Falls der Bug doch nochmal auftritt, zeigt das Log direkt wer den Dialog schließt.

---

## [2.3.0] - 2026-04-29 - Update-Pfade mit Timestamp (kein File-Lock-Konflikt mehr)

### Behoben
- **„Update fehlgeschlagen — Datei wird von anderem Prozess verwendet"**: Die `download_update()` nutzte einen festen Dateinamen `%TEMP%\fexobooth_update.zip`. Wenn Windows Defender das ZIP nach dem letzten erfolgreichen Update noch scannte (Real-Time-Schutz lockt frische ZIPs/EXEs für einige Sekunden bis Minuten), schlug der nächste Update-Versuch fehl. Auch `fexobooth_updater.bat` und `fexobooth_update_extract/` hatten feste Namen — gleiche Gefahr.

### Fix
- **Eindeutige Dateinamen pro Update-Lauf**: ZIP, BAT und Extract-Verzeichnis bekommen jetzt einen Timestamp + PID-Suffix:
  - `fexobooth_update_<YYYYMMDD_HHMMSS>_<PID>.zip`
  - `fexobooth_updater_<timestamp>.bat`
  - `fexobooth_update_extract_<timestamp>/`
- **Robustes `unlink()`**: Falls die Datei doch existiert (extrem unwahrscheinlich wegen Timestamp+PID), wird der Lösch-Versuch in `try/except` gepackt und im Notfall ein Alternativname verwendet.
- **Orphan-Cleanup mit Glob-Patterns**: `cleanup_orphan_downloads()` findet jetzt alle alten Update-Reste (sowohl alte feste Namen als auch neue Timestamp-Namen) via `glob('fexobooth_update*.zip')` etc.

---

## [2.2.9] - 2026-04-29 - Bug-Fixes: Admin-Dialog + OTA-Custom-Assets

### Behoben
- **Admin-Dialog (PIN 3198) ging gelegentlich beim Öffnen sofort wieder zu** und der ADMIN-Button reagierte danach nicht mehr. Ursache: Der PIN-Dialog hatte `pin_frame.bind("<Button-1>", lambda e: self.destroy())` (Click-outside-zum-Schließen). Auf Touch-Screens kommt es vor, dass Touch-Down auf der Karte und Touch-Up auf dem Hintergrund landet → Dialog schließt direkt. Plus: ein hängender `grab` am Parent verhinderte weitere Klicks. Fix: Click-outside-Handler entfernt (User schließt nur noch über `✕` oder ESC), `destroy()` Override garantiert `grab_release`.
- **OTA-Update überschrieb User-Videos und Custom-Bilder.** `assets/videos/start.mp4` + `end.mp4` wurden mit den Defaults aus dem ZIP überschrieben, ebenso ggf. ein Custom-`flash_image` im `assets/`-Root. Fix: Vor dem `xcopy` wird `assets/videos/` atomar nach `%TEMP%\fexobooth_user_assets` gemoved + alle `*.png/.jpg/.jpeg` aus `assets/` Root gesichert. Nach dem xcopy werden die User-Files atomar zurück, was die Defaults aus dem ZIP überschreibt.

### Neue geschützte Pfade beim OTA
- `config.json`
- `BILDER/`
- `logs/`
- `.booking_cache/`
- **`assets/videos/`** (NEU — User-Videos)
- **`assets/*.png/.jpg/.jpeg`** (NEU — User-Bilder im `assets/`-Root, z.B. Auslöse-Bild)

---

## [2.2.8] - 2026-04-29 - Template & Settings vom USB neu laden

### Hinzugefügt
- **Service-Menü (PIN 6588): „Template & Settings vom USB neu laden"** — erzwingt Reload der `settings.json` und des Template-ZIPs vom USB-Stick, auch wenn die `booking_id` gleich bleibt. Use Case: Kunde tauscht mitten in der Veranstaltung das Template, ändert eine Einstellung. Vorher wurde das ignoriert (BookingManager überspringt Reload bei gleicher booking_id).
- **Kunden-Menü (PIN 2015): „Template neu einlesen"** — gleiche Funktion, vereinfacht für Vor-Ort-Helfer ohne Service-PIN.

### Hintergrund
[BookingManager.load_from_usb()](src/storage/booking.py) hat in Z. 317 eine Optimierung:
```python
if not force and new_booking_id == self.booking_id and self._settings:
    return True  # gleiche Buchung, überspringe
```
Diese Optimierung war zwar gewollt (kein unnötiges Reload bei jedem Stick-Plug), aber für Inline-Anpassungen im laufenden Event musste der User vorher den Stick mit anderer booking_id präparieren oder das Tablet neu starten. Beide Buttons rufen jetzt `force=True` auf und triggern danach `_restore_cached_template()` + Screen-Refresh.

---

## [2.2.7] - 2026-04-29 - KRITISCH: OTA-Update Race-Condition gefixt

### Behoben
- **Tablets crashten beim Boot nach OTA-Update** mit `FileNotFoundError: 'C:\FexoBooth\_internal\setuptools\_vendor\jaraco\text\Lorem ipsum.txt'`. Race-Condition zwischen App-Beendigung und BAT-Update-Script:
  1. `app.quit()` beendet zwar den Mainloop, aber Hintergrund-Threads (Camera, Galerie-Server) hielten den Prozess am Leben
  2. BAT wartete 30 s, fuhr dann „warnend" fort obwohl App noch lief
  3. `rmdir /s /q "_internal"` schlug **partiell** fehl (gelockte DLLs), `xcopy` mit `>nul 2>&1` unterdrückte alle Fehler
  4. Mixed state: manche Files weg, andere nicht ersetzt → App startet nicht mehr

### Drei-fach-Fix
1. **`os._exit(0)` statt `app.quit()`** ([src/ui/dialogs/update_progress.py](src/ui/dialogs/update_progress.py)) — terminiert den Prozess sofort, ohne auf Threads zu warten. Logging wird vorher geflushed.
2. **BAT-Script atomic mit Rollback** ([src/updater.py](src/updater.py)) — `_internal` wird zuerst nach `_internal_OLD` umbenannt (atomic, scheitert wenn gelockt), dann neu kopiert. Bei xcopy-Fehler: Rollback auf alten Stand. Tablet bleibt **immer funktional**, auch wenn das Update scheitert.
3. **`setuptools` via `collect_all`** ([fexobooth.spec](fexobooth.spec)) — extra Absicherung damit alle vendored Daten-Files (jaraco.text/Lorem ipsum.txt etc.) zuverlässig im Build landen.

### Plus
- BAT-Wait-Timeout von 30 s auf 15 s reduziert (App sollte mit `os._exit` sofort sterben)
- Nach 15 s zusätzlich `taskkill /F /IM` als Fallback
- xcopy nutzt jetzt `/Q` (quiet) aber meldet Errors per `errorlevel`

### Wichtig
Tablets auf v2.2.6 mit dem kaputten State müssen einmalig manuell via `FexoBooth_Setup_2.1.exe` vom Stick auf v2.2.7 gehoben werden — Inno Setup repariert die fehlenden Dateien.

---

## [2.2.6] - 2026-04-29 - Test-Release: OTA-Update verifizieren

App-Code **identisch zu v2.2.5**. Reiner Versions-Bump um den OTA-Update-Pfad auf bereits-installierten v2.2.5-Tablets zu verifizieren.

Erwartet:
- Tablet auf v2.2.5 → Service-Menü → „Software aktualisieren" findet v2.2.6
- Download läuft durch (kein SSL-Fehler mehr, weil v2.2.5 das certifi-Bundle hat)
- Fullscreen-Progress-Dialog zeigt MB-Fortschritt
- Nach Install: Tablet auf v2.2.6

---

## [2.2.5] - 2026-04-28 - SSL-Fix für OTA-Update (certifi mitgepackt)

### Behoben
- **OTA-Update scheiterte am SSL-Cert-Verify** — Im PyInstaller-Build fand `urllib` kein CA-Bundle, der ZIP-Download von GitHub brach mit `[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate` ab. Im Dev-Modus klappte es weil Python die System-Zertifikate fand, aber im EXE-Build fehlten sie.
- Lösung: `certifi` als explizite Dependency aufgenommen, `cacert.pem` über `collect_all("certifi")` in den Build gepackt, und `urlopen()` in [src/updater.py](src/updater.py) nutzt jetzt einen expliziten `ssl.create_default_context(cafile=certifi.where())`. Beide HTTPS-Calls (API-Check + ZIP-Download) gehen über denselben Context.

### Wichtig
v2.2.4 und älter können dieses Update **nicht via OTA** bekommen — genau dieses SSL-Problem blockiert das ja. Die Tablets müssen **einmalig manuell** auf v2.2.5 gehoben werden (`FexoBooth_Setup_2.1.exe` vom Stick installieren). Ab v2.2.5 funktioniert OTA.

---

## [2.2.4] - 2026-04-28 - Test-Release zur Verifikation des Update-Mechanismus

App-Code ist **identisch zu v2.2.3** — nur Versions-Bump zur Verifikation des OTA-Update-Pfades vom Tablet.

Was getestet werden soll:
- Service-Menü (PIN 6588) → „Software aktualisieren" findet v2.2.4
- Fullscreen-Progress-Dialog mit `-topmost` ist sichtbar
- Download durchläuft, BAT-Script übernimmt, App startet neu
- Im Service-Menü steht nach dem Update v2.2.4

Parallel (außerhalb dieses Release): Capture-Tooling-Verbesserungen für USB-Stick, siehe [FORTSCHRITT.md](FORTSCHRITT.md) — `custom-ocs-capture` räumt jetzt `hiberfil.sys` weg, ANSI-robuste Verifikations-Marker, sauberer Abbruch nach Fehler.

---

## [2.2.3] - 2026-04-28 - Spiegel-Fix für gedruckte/gespeicherte Fotos

### Behoben
- **Texte auf Kleidung waren im Druck und in den gespeicherten Singles seitenverkehrt.** Die LiveView-Spiegelung (gewollt: Spiegel-Effekt für intuitive Bewegung) hat sich auch auf den Capture-Pfad ausgewirkt — Webcam und Canon DSLR speicherten gespiegelte Fotos. Jetzt: LiveView bleibt gespiegelt, aber gespeicherte Fotos und Drucke sind korrekt orientiert (Texte lesbar).

---

## [2.2.2] - 2026-04-23 - Update-UI + Orphan-Cleanup

### Behoben
- **Download-Fortschritt war im Kiosk-Modus unsichtbar** — Der ServiceDialog hatte kein `-topmost`, sobald der Confirm-Dialog zerstört wurde, fiel der Dialog hinter die Kiosk-Haupt-App zurück. Der Download lief weiter, aber der User sah nichts und dachte die App sei abgestürzt.
- Neuer **Fullscreen-Update-Progress-Dialog** mit `-topmost`, deutlich größerer Progress-Bar (28 px statt 12), MB-Zähler (`52.3 / 143.4 MB`) und klarem Phasen-Text ("Lade Update herunter..." → "Installation läuft, App startet neu...").

### Hinzugefügt
- **Orphan-Download-Cleanup beim App-Start** — Wenn ein Update abbricht (Stromausfall, Crash mitten im Download), bleiben ~150 MB in `%TEMP%\fexobooth_update.zip` liegen. Beim nächsten App-Start werden alle Update-Reste älter als 1 Stunde automatisch gelöscht → Tablets können sich nicht mehr zumüllen.
- `src.ui.dialogs.update_progress` und `src.company_network` explizit in `fexobooth.spec` als hidden imports eingetragen.

---

## [2.2.1] - 2026-04-23 - Updater-Diagnose + Repo-Access

### Hinzugefügt
- **Besseres Error-Logging im Updater** — bei Update-Check-Fehlern wird jetzt der volle Stack-Trace ins Log geschrieben (vorher komplett geschluckt → Problem unsichtbar).
- **HTTPError vs URLError unterscheiden** — HTTP 404/403/500 wird nicht mehr fälschlich als "Keine Internetverbindung" verkauft. Stattdessen exakte API-Fehlermeldung.

### Behoben
- **Update-Mechanismus hat seit v2.0.0 nie funktioniert** — das GitHub-Repo `fefotec/fexobooth-v2` war privat und lieferte ohne Auth ein HTTP 404 zurück, was der Code als "kein Internet" interpretierte. Repo ist jetzt public, API-Zugriff ohne Token funktioniert, OTA-Updates triggern.

---

## [2.2.0] - 2026-04-23 - Auto-Update, Deployment-Schutz, Hotspot-Fix

### Hinzugefügt
- **Auto-Update beim App-Start** — Wenn die Box im Firmen-WLAN (fexon-SSIDs) eingeschaltet wird und Internet verfügbar ist, prüft sie automatisch GitHub auf neue Releases und installiert sie still. Beim Kunden passiert nichts, da dort nie Internet besteht.
  - Firmen-SSID-Whitelist in `config.company_wifi_ssids` (default: `fexon WLAN`, `fexon_Buero_WLAN2`, `fexon_Buero_WLAN2_5GHZ`, `fexon Gast-WLAN`, `fexon_outdoor`)
  - Ein/Aus-Schalter via `config.auto_update_enabled` (default: `true`)
  - 15s Verzögerung, Background-Daemon, ohne Internet still geschluckt
- **Deployment Pre-Flight-Check** (`custom-ocs-deploy`) — verhindert das Bricken kleinerer Tablets. Prüft vor dem Pre-Wipe ob die Zieldisk groß genug für das Image ist (5% Toleranz). 32-GB-Tablets werden nicht mehr mit 64-GB-Images zerstört.
- **Hotspot Auto-Dummy-Profil** — Frisch geklonte Tablets starten den Hotspot jetzt zuverlässig. `_ensure_wlan_profile_exists()` legt beim ersten Start ein Dummy-WLAN-Profil an, damit die Tethering-API keinen `NO_PROFILE`-Fehler wirft.
- **Hotspot-Diagnose-Script** (`setup/diagnose_hotspot.ps1`) — zeigt WLAN-Adapter, gespeicherte Profile und Tethering-Status für Troubleshooting.
- **Clonezilla Auto-Fixes + persistentes Logging** — `custom-ocs-capture` und `custom-ocs-deploy` überleben jetzt Retries und loggen nach `/home/partimag/deploy-logs/`.

### Behoben
- **FEXOSAFE-Backup nutzt jetzt Buchungs-ID als Überordner** — Der Auto-Backup-Dialog beim FEXOSAFE-Stick erstellt nun `USB:\{event_id}\Single` und `\Prints` statt pauschal `BILDER/`. Logik identisch zum Service-Menü-Backup (PIN 6588).
- **Start-Button wurde vom Galerie-Banner abgeschnitten** — Button aus `inner_frame` rausgelöst und direkt über `gallery_banner` per `pack(side="bottom")` platziert.
- **Drucker wurde nicht erkannt an anderem USB-Port** — Controller erkennt den SELPHY jetzt unabhängig vom USB-Port.
- **Falsche Kamera trotz korrekter Auswahl in der UI** — Webcam-Index aus Config wurde ignoriert; jetzt korrekt übernommen.

---

## [2.1.1] - 2026-03-27 - Template-Persistenz Fix, Kamera-Schutz

### Geändert
- **Interne Tablet-Kamera wird ignoriert** — Kein stiller Fallback auf die verdeckte interne Kamera mehr. Wenn keine externe Kamera angeschlossen ist, blinkt "KEINE KAMERA!" in der Status-Bar. Externe Kamera wird automatisch erkannt wenn sie im Betrieb angesteckt wird

### Behoben
- **Template-Persistenz nach Neustart ohne USB-Stick** — Template blieb nicht erhalten wenn die Box ohne Stick neu gestartet wurde. Ursache: `cached_template.zip` wurde erst beim Starten einer Session geschrieben, nicht beim Laden des Events
- **Template-Erkennung auf USB** — BookingManager erkannte nur ZIPs namens `template.zip`, alle anderen Dateinamen wurden ignoriert
- **Event-Wechsel verlor Template** — Bei Event-Wechsel wurde das Template in Memory geladen aber nicht auf Disk persistiert
- **Stick-Wiedereinstecken ohne Template** — Wenn die Box ohne Stick neu gestartet wurde und der Stick dann eingesteckt wurde, blieb das Fallback-Template bis zur nächsten Session
- **Installer: Gecachtes Template überlebte Neuinstallation** — `_internal\.booking_cache` wurde bei Install/Uninstall nicht gelöscht
- **Installer: `.booking_cache` wurde bei Installation vorab erstellt** — Verzeichnis entsteht jetzt erst im Produktionsbetrieb

---

## [2.0.0] - 2026-03-19 - Erster stabiler Release

### Hinzugefügt
- **Kunden-PIN "2015"** — Template wählen, Live-View Overlay togglen, Druckstau beheben, Windows neustarten (ohne Admin-Zugang)
- **Template-Vorschau** — Template-Auswahl zeigt Vorschau-Bilder aus ZIP-Dateien. Ordner `assets/templates/`
- **Minimieren-Button** in Admin-Einstellungen (nur im Kiosk-Modus)
- **prepare_image.bat** — Tablet für Clonezilla-Image vorbereiten (Windows-Optimierung + Daten-Bereinigung)
- **USB-Sync Dialog Fallback** — Pending-Count als Fallback wenn count_missing fehlschlägt

### Geändert
- **Admin-Dialog im Kiosk-Modus** — Fullscreen-Overlay statt Fenstermodus-Wechsel
- **Filter-Screen optimiert** für Lenovo Miix 310 — Labels entfernt, Preview größer
- **USB-Status-Indikator** hat jetzt feste Breite (Frame-Container)

### Entfernt
- **5x Icon-Tap Neustart** entfernt (durch Kunden-PIN "2015" ersetzt)

### Behoben
- **USB-Sync Dialog** kam nicht bei Stick-Wiedereinstecken (gleicher Event) — Background-Thread fehlte try/except + Fallback
- **Template-Loader:** `preview.png` nicht mehr als Overlay verwenden
- **Start-Screen Refresh:** Template-Wechsel über Kunden-PIN 2015 aktualisiert sofort die Karten
- **Galerie Sharing:** Erkennt ob Foto-Teilen möglich ist (HTTPS nötig)
- **Template-Karte:** Zeigt "Wunsch-Template" statt rohem Dateinamen
- **Capture-Hintergrund:** Weiß statt Schwarz bei Templates ohne Overlay-Frame
- **USB-Template:** Überschreibt nicht mehr die explizite User-Auswahl

### Bekannte Einschränkungen
- Galerie: Foto-Sharing mit Bild nur über HTTPS möglich (lokales HTTP → nur Text-Sharing)

---

## [2026-02-04] - Video-Fix für schwache Hardware & Offline-Hotspot

### Hinzugefügt
- **Windows Media Foundation (MSMF) Backend für Video-Wiedergabe**
  - Nutzt Windows-eigene H.264 Codecs
  - Fallback auf FFMPEG und Default-Backend
  - Verhindert schwarzen Bildschirm auf schwacher Hardware

- **Threading für Video-Wiedergabe**
  - Frame-Lesen in separatem Thread
  - Queue-basierte Kommunikation (Producer-Consumer Pattern)
  - Verhindert UI-Einfrieren auf schwacher Hardware (z.B. Lenovo Miix 310)

- **Status-Label bei Video-Fehlern**
  - Zeigt "Video konnte nicht geladen werden" bei Problemen
  - Automatischer Weitersprung nach 3 Sekunden

- **Offline-Hotspot Setup** (`setup/setup_hotspot.ps1`)
  - Mehrere Fallback-Methoden für Hotspot ohne Internet
  - Versucht: Loopback-Profil → Verfügbare Profile → netsh hostednetwork
  - Erstellt Auto-Start Scheduled Task
  - Manuelle Anleitung als letzter Fallback

### Geändert
- Video-FPS auf max. 25 begrenzt (Performance auf schwacher Hardware)
- Skip-Button erscheint erst wenn Video läuft oder Fehler auftritt

### Behoben
- **Video zeigt schwarzen Bildschirm auf Miix 310**
  - Ursache: OpenCV Default-Backend kann H.264/MP4 nicht decodieren
  - Fix: MSMF-Backend nutzt Windows-eigene Codecs

- **UI friert ein während Video-Wiedergabe**
  - Ursache: Frame-Lesen blockiert Main-Thread
  - Fix: Threading mit Frame-Queue

- **Hotspot-Script schlägt fehl ohne Internet**
  - Ursache: NetworkOperatorTetheringManager braucht Internetverbindung
  - Fix: Mehrere Fallback-Methoden inkl. netsh hostednetwork

### Technische Details
- `src/ui/screens/video.py` komplett überarbeitet
- `setup/setup_hotspot.ps1` komplett überarbeitet
- Getestet für: Lenovo Miix 310 (Atom CPU, 4GB RAM)

---

## [2026-02-03] - Admin-Menü & Persistenz

### Hinzugefügt
- **Galerie-Tab im Admin-Menü**
  - SSID konfigurierbar
  - Passwort konfigurierbar
  - Port konfigurierbar
  - Info-Box mit Anleitung

- **Statistik-Tab im Admin-Menü**
  - Aktuelle Session anzeigen (Fotos, Prints, Sessions)
  - Letzte 5 Events anzeigen
  - CSV-Export Button
  - Statistik zurücksetzen (mit Bestätigung)

- **QR-Code Widget überarbeitet**
  - Pink Akzent-Rahmen (fexobox Branding)
  - WLAN-Name (SSID) angezeigt
  - Passwort angezeigt
  - Kompakte Anleitung: "Verbinden → Scannen → Fertig!"

- **Buchung + Template Persistenz** (`src/storage/booking.py`)
  - Buchungsdaten werden lokal gecached (`.booking_cache/last_booking.json`)
  - Template-ZIP wird lokal kopiert (`.booking_cache/cached_template.zip`)
  - Nach Neustart: Letzte Buchung automatisch wiederhergestellt
  - Wechsel nur bei ANDERER booking_id

- **Shared USBManager** (`src/storage/local.py`)
  - Singleton-Pattern für USBManager
  - Alle Module teilen dieselbe pending_files Liste
  - Live-Counter für fehlende USB-Bilder

### Geändert
- Template-Labels umbenannt:
  - "Layout" → "Druck-Vorlage"
  - "Einzelfoto" → "Einzelbild"

- `find_usb_template()` prüft jetzt auch den Cache wenn kein USB da ist

- Galerie-Checkbox aus Allgemein-Tab entfernt (jetzt in eigenem Galerie-Tab)

### Behoben
- **Pending-Files Counter aktualisiert sich nicht live**
  - Ursache: LocalStorage hatte eigenen USBManager
  - Fix: Alle Module nutzen jetzt `get_shared_usb_manager()`

- **Template nach Neustart weg**
  - Ursache: Template wurde nur vom USB geladen, nicht gecached
  - Fix: Template wird in `.booking_cache/` kopiert und beim Start geladen

### Technische Details
- Neue Dateien:
  - `.booking_cache/last_booking.json` - Buchungsdaten Cache
  - `.booking_cache/cached_template.zip` - Template Cache
- `.gitignore` erweitert um Cache-Dateien

---

## [2026-02-03] - Galerie & Statistik Module

### Hinzugefügt
- **Lokale Galerie mit Webserver** (`src/gallery/`)
  - Flask-Server für Foto-Galerie
  - QR-Code Generator
  - Responsive HTML für Handys
  - Hotspot-Setup Script (`setup/setup_hotspot.ps1`)

- **Statistik-Modul** (`src/storage/statistics.py`)
  - Event-Tracking pro Buchung
  - Erfasst: Fotos, Prints, Sessions, Zeitraum
  - JSON-Export
  - `get_all_stats()` und `reset_all()` Methoden

- **Buchungsnummer in Top-Bar**
  - Zeigt aktive Buchungs-ID
  - Format: 📋 123456

---

## [2026-02-02] - USB & Booking System

### Hinzugefügt
- **settings.json Support** (`src/storage/booking.py`)
  - Lädt Buchungsdaten vom USB-Stick
  - Steuert Features: print_singles, online_gallery, dslr_camera

- **USB-Sync Feature** (`src/storage/usb.py`)
  - Pending-Files Queue wenn USB nicht verfügbar
  - Automatischer Sync bei USB-Einstecken
  - Dialog zur Bestätigung

---

## Legende

- ✅ Fertig & getestet
- 🚧 In Arbeit
- ❌ Bekannter Bug
- 💡 Idee/Vorschlag
