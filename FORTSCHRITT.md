# Fortschritt - Fexobooth V2

Chronologisches Protokoll aller Änderungen.

---

## 2026-08-26 — Canon V2.4.62: Hostbetrieb ohne SD-Karte entblockt

**Hardwarebefund:** Box 248 lief mit EOS 2000D, Wahlrad `P` und ohne
SD-Karte. 2.4.61 fand die Kamera und oeffnete die Session bei jedem Versuch.
`SaveTo=Host`, UI-Lock, `EdsSetCapacity(reset=1)`, UI-Unlock und
`SaveTo`-Readback gelangen ebenfalls. Nur `AvailableShots` blieb bei null;
der neue 2.4.60-Guard behandelte das faelschlich als fatal und verwarf die
bereits verbundene Kamera.

**Korrektur 2.4.62 (nur Canon):** Null bleibt fuer eine Sekunde ein
Kaltstartsignal. Bleibt sie danach bestehen, gilt die Session auf Basis der
bestaetigten Hostschritte als bereit und schreibt eine eindeutige Warnung plus
`readiness=save_to+capacity`. Alle Pflichtfehler sowie andere unplausible
Werte bleiben fail-closed. Es gibt kein Dummyfoto, keinen Retry und keinen
Kartenfallback.

**Vorherige Hardware-Abnahme:** Der 2.4.61-Lauf auf Box 245 war sauber: vier
echte 6000-x-4000-JPEGs, erstes Foto vorhanden, pro Capture genau ein Press,
Release, Blitz, Transfer und Foto. Der Blitz folgte Press-Return nach 60 bis
65 ms. Dieser Ablauf wurde nicht veraendert.

**Validierung:** `python tests/alle_tests.py` unter Windows **18/18 gruen**;
isolierter Null-Readiness-Test und integrierter
`AvailableShots=0 -> genau ein Host-JPEG`-Test gruen; `py_compile` und
`git diff --check` gruen. `webcam.py`, `nikon.py`, `canon.py` und
`session.py` ohne Diff.

**Offen:** 2.4.62 auf Box 248 ohne SD-Karte im Dev-Modus bauen und eine
vollstaendige Session fahren. Erst echte 6000-x-4000-JPEGs und die komplette
Markerfolge schliessen den Flottennachweis ab.

---

## 2026-08-26 — Canon V2.4.61: Softwareblitz an Press-Return gekoppelt

**Hardwarebefund 2.4.60:** Box 245 lieferte mit EOS 2000D und eingesetzter
SD-Karte vier von vier echte 6000-x-4000-JPEGs per Host-Transfer. LiveView
blieb aktiv; kein `CARD_NG`, schwarzer Canon-Balken, Retry oder Doppelbild.
Der Softwareblitz lag aber 1.497 bis 1.569 ms vor der erfolgreichen Rueckkehr
von `ShutterButton_Completely`. Der hoerbare Kameraklick und das echte Foto
kamen spaeter, sodass eine Bewegung direkt nach dem Blitz noch auf dem Foto
landete.

**Umsetzung 2.4.61 (nur Canon):** Der Countdown startet den Worker ohne
vorgezogenen Blitz. Der EDSDK-Owner erfasst Press- und Release-Rueckkehr mit
monotonen Zeiten in einem eingefrorenen Ergebnis. Nach begonnenem Press wird
`ShutterButton_OFF` auch bei einer Exception im `finally` genau einmal
versucht. Der Canon-Manager ruft die optionale UI-Rueckmeldung nur im
aufrufenden Capture-Worker und nur bei synchronem `press_ok=True` auf; ein
Release- oder spaeterer Transferfehler bleibt ein Capture-Fehler.

Der Worker reiht den 90-ms-Blitz per `after(0)` in den Tk-Hauptthread ein.
Capture-eigene Generation-Tokens und Einmal-Guards verwerfen alte oder
doppelte Rueckmeldungen auch dann, wenn bereits ein neuer Capture laeuft.
Fehler beim Einreihen und Anzeigen sind nicht fatal. Das echte Canon-PIL-Foto
wird im passenden Completion-Callback sofort und genau einmal angezeigt.

**Abgrenzung:** Canons EDSDK meldet keinen exakten mechanischen
Verschlusszeitpunkt. Press-Return ist die beste risikoarme Naeherung und muss
auf Hardware gegen den hoerbaren Klick und die gespeicherte Pose bestaetigt
werden. Webcam- und Nikon-Ablauf bleiben unveraendert.

**Diagnose:** Neue korrelierte Marker sind `CANON-SHUTTER PRESS-START`,
`PRESS-RETURN`, `RELEASE-RETURN`, `CANON-FLASH REQUEST`, `CANON-FLASH SHOWN`
und `CANON-PHOTO SHOWN`. Die alten scheinbaren Shutter-Zeitfelder wurden als
Zeit seit Capture-Armierung eindeutig benannt.

**Validierung:** `python tests/alle_tests.py` unter Windows **18/18 gruen**;
gezielte Tests fuer Exceptions, Owner-Timeout, Callback-Thread/-Fehler,
Token-Races und Sofortanzeige gruen; `py_compile` gruen; `webcam.py` und
`nikon.py` ohne semantischen Diff.

**Offen:** 2.4.61 bauen und auf Box 245 mit eingesetzter SD-Karte im Dev-Modus
testen. Bis zum neuen Blitz stillhalten, direkt danach bewusst bewegen und
Bild/Marker vergleichen. Anschliessend separat ohne SD-Karte testen.

---

## 2026-08-25 — Canon V2.4.60: erstes Foto abgesichert, Anzeige beschleunigt

**Ausgangspunkt:** Der 2.4.59-Hardwaretest auf Box 245 war der Durchbruch:
Nach einem fehlgeschlagenen ersten Versuch kamen sieben echte Canon-JPEGs mit
6000 x 4000 Pixeln vollstaendig per Host-Transfer an. Owner, Event-Queue,
Download und Dekodierung sind damit auf echter Hardware bestaetigt. Nur der
erste Kaltstart-Capture wurde mit `TAKE_PICTURE_CARD_NG (0x8d07)` abgelehnt.

**Nachbesserung 2.4.60 (nur Canon):** Die Host-Bereitschaft wird nach
`OpenSession` atomar im EDSDK-Owner hergestellt: `SaveTo=Host`, `UILock`, ein
einmaliges `EdsSetCapacity(reset=1)`, garantiertes `UIUnlock` und begrenztes
Readback von `SaveTo`/`AvailableShots`. Erst danach wird das Host-Ready-Flag
gesetzt. Der bisherige Capacity-Reset unmittelbar vor jedem Foto ist entfernt;
ohne bestaetigte Bereitschaft gibt es keinen Shutter und bei `CARD_NG` keinen
automatischen Zweitversuch.

Der schwarze Hinweis `Foto wird aufgenommen ...` wird fuer Canon nicht mehr
geplant. Nikon behaelt ihn. Das Canon-JPEG bleibt fuer die Anzeige direkt im
PIL-Pfad; nur eine benoetigte 180-Grad-Drehung oder ein unerwarteter Farbmodus
erzeugt noch Arbeit. Erwartete Ersparnis gegenueber dem 2.4.59-Log: rund
300 ms Bildkonvertierung plus 40 bis 60 ms Capacity-Aufruf pro Foto.

AE-/Weissabgleich-Zuordnungen sind gegen Canon korrigiert. Die
Belichtungskorrektur wird beim Verbinden protokolliert und bei einem Wert
ungleich null gewarnt, aber nie automatisch geaendert. Im Dev-Modus kommen
pro JPEG EXIF- und Helligkeitsdaten hinzu. Die im ersten Test beobachtete
Ueberbelichtung war eine verstellte Kamerakorrektur und ist an der Kamera
behoben.

**Abgrenzung:** Webcam-Capture und `webcam.py` bleiben semantisch unveraendert.

**Validierung:** `python tests/alle_tests.py` unter Windows **18/18 gruen**;
`py_compile` gruen; `webcam.py` ohne semantischen Diff.

**Offen:** 2.4.60 bauen und auf Box 245 mit `--dev` erneut pruefen. Zuerst das
allererste Foto direkt nach Kamera-Kaltstart, danach eine komplette Session;
spaeter folgt der Flottennachweis ohne SD-Karte.

---

## 2026-08-25 — Canon V2.4.59: installierten Build und Host-Capture repariert

**Vollstaendige Uebergabe: [DSLR-STAND.md](DSLR-STAND.md)**

Die Analyse ging diesmal von Historie, Hersteller-Header, Paketinhalt und den
vorhandenen Box-Logs aus. Der wahrscheinlichste Bruch nach der Neuinstallation
liegt bereits vor dem ersten Kameraaufruf: Der PyInstaller-One-Folder-Build
packt `EDSDK.dll` und `EdsImage.dll` unter `_internal`, der Loader suchte dort
nicht. Er nutzt jetzt zuerst `sys._MEIPASS` und hält das DLL-Suchpfad-Handle
dauerhaft offen.

Der Canon-Weg wurde außerdem vollständig auf genau einen COM-STA-Owner
gebracht. Alle EDSDK-Aufrufe einschließlich Live-View, Handler, Event-Pump,
Shutter, Download und Cleanup laufen dort. Native Callbacks bleiben kurz und
stellen Folgearbeit nur in eine priorisierte Queue. Handler-Lebensdauer,
Parallelstart, native Timeouts und Queue-Abbruch sind fail-closed abgesichert.

Der Produktionscapture läuft immer direkt zum Host, ohne Speicherkarte. Eine
Capture-ID bindet Queue und Event unmittelbar vor dem Shutter an genau eine
Aufnahme; verspätete Events werden gecancelt. Es gibt exakt einen
Capture-Befehl, Shutter-OFF wird geprüft, und der generische Webcam-Fallback
kann Canon nicht ein zweites Mal auslösen.

Dev-Logs enthalten nun Owner-/Thread-ID, Auftrag-ID, Queue-/Call-Dauer,
Capture-ID, Shutter, Object-/State-Event, Transfer-Dateiname/-Format/-Bytes,
Auflösung und bei einem Timeout den Owner-Stack. `--dev --dslr-test` aktiviert
das normale Dashboard-Logging ebenfalls.

**Validierung:** `py_compile` grün; `python tests/alle_tests.py` unter Windows
**15/15 grün**. Darin enthalten ist eine integrierte Fake-Kette
`0x208 → Host-Download → Queue → 6000×4000-JPEG` sowie ein eigener Test für
den installierten `_internal`-DLL-Pfad. Zwei unabhängige Diff-/Testreviews
fanden danach keinen Build-Blocker. `webcam.py` hat keinen semantischen Diff.

**Hardware-Nachtrag:** Box 245 lieferte mit 2.4.59 nach einem `CARD_NG` beim
allerersten Versuch sieben echte 6000-x-4000-JPEGs ueber `SaveTo=Host`. Damit
ist die Grundreparatur bestaetigt; Kaltstart-Readiness und der abschliessende
Flottentest ohne Speicherkarte gehen in 2.4.60 weiter.

---

## 2026-08-24 (Abschluss der Sitzung) — Uebergabe DSLR (2.4.51 bis 2.4.58)

**Vollstaendige Uebergabe: [DSLR-STAND.md](DSLR-STAND.md)**

Diese Sitzung hat acht echte Ursachen der DSLR-Baustelle gefunden und behoben.
Die Box liefert trotzdem noch keine Fotos — 2.4.58 ist ungetestet.

**Behoben in dieser Sitzung:**

| Version | Ursache |
|---|---|
| 2.4.51 | Messmodus `--dslr-test` (statt einer Vermutung pro Build) |
| 2.4.52 | Auslösen und Live-View zurueck auf Canons Referenzweg (~4 s gespart) |
| 2.4.53 | Host-Capacity wurde damals vor jedes Foto verschoben; diese Annahme wurde mit Hardwaredaten in 2.4.60 korrigiert |
| 2.4.54 | Einfrieren beim Session-Start (Rueckschritt aus 2.4.49 behoben) |
| 2.4.55 | Download scheiterte: drei Funktionen mit 32- statt 64-Bit-Parametern |
| 2.4.56 | Haengender Aufruf blockierte die Kamera bei jedem Versuch erneut |
| 2.4.57 | **Kernursache:** EDSDK wurde aus zwei verschiedenen Faden gestartet |
| 2.4.58 | Uebersehene Aufrufstelle → kein Live-View (166 Fehler pro Sitzung) |

**Der rote Faden:** Fuenf von acht Ursachen waren derselbe Fehlertyp — ein
64-Bit-Wert der Canon-Schnittstelle, im Code als 32 Bit. Vier Fundstellen
kosteten je eine Testrunde auf der echten Box.

**Gegenmassnahme:** `python tests/alle_tests.py` — sechs Tests, keine Kamera
noetig, laeuft in Sekunden. Faengt die ganze Fehlerfamilie ab, bevor ein Build
entsteht. Gegenprobe gemacht: Der kuenstlich wieder eingebaute Fehler aus
2.4.57 wird mit Zeilennummer gemeldet.

**Ausserdem neu:** Log-Versand von der Box ins Dashboard per Knopfdruck
(Service-Menue → „Logs ans Dashboard senden", Dashboard → Fotoboxen →
Box-Logs). Spart bei jeder Testrunde den Weg mit dem USB-Stick. Dashboard-Seite
ist deployt und live.

**Zwei Rueckschritte in dieser Sitzung** (Einfrieren in 2.4.49, blockierte
Kamera ab 2.4.53) entstanden beide gleich: Aenderungen, die ohne Hardware nicht
pruefbar waren, gingen ungetestet auf die Box. Genau dagegen sind die Tests
und der Messmodus gedacht.

---

## 2026-08-24 — Zurueck auf Canons Referenzweg (2.4.51 + 2.4.52)

Christian hat die Herangehensweise grundsaetzlich in Frage gestellt: "dslr-booth
laeuft ja auch auf der gleichen hardware und das problemlos fluessig mit dslr".
Der Einwand war berechtigt — ueber vier Runden wurde jeweils eine Vermutung
geaendert und neu gebaut, ohne Ergebnis.

**2.4.51:** Messmodus `--dslr-test`. Probiert fuenf Ausloese-Varianten in einem
Durchlauf durch, beobachtet Karte und Direktdownload gleichzeitig und nennt die
schnellste funktionierende. Ersetzt das Raten pro Build.

**2.4.52:** Zwei Abweichungen von Canons Beispielcode zurueckgenommen — beide
stammten aus frueheren Reparaturversuchen:

1. Der halbe Ausloeserdruck mit 0,35 s Pause (aus 2.4.49) machte das Ausloesen
   2,5 s langsam und brachte trotzdem kein Foto. Canons Beispiel drueckt in
   einem Zug durch.
2. Der Live-View wurde vor jeder Aufnahme abgeschaltet und danach neu
   gestartet: 1,5 s pro Foto. Canons Beispiel fasst ihn nicht an — und genau
   das ist der sichtbare Unterschied zu anderer DSLR-Software.

**Ausserdem:** Wartehinweis bei Spiegelreflex. Nach dem Blitz stand das
eingefrorene Vorschaubild auf dem Schirm und wurde fuer das Foto gehalten.
Jetzt liegt "Foto wird aufgenommen…" darueber. Nur bei canon/nikon, die
Webcam-Flotte bleibt unberuehrt. Der Text war in allen sieben Sprachen bereits
vorhanden und ungenutzt.

**Offen:** Warum die Kamera trotz hoerbarem Ausloesen nichts ablegt. Der
Messlauf beantwortet das.

---

## 2026-08-21 (Nachmittag, Fortsetzung) — Foto lag auf der Karte (2.4.49 + 2.4.50)

**Log-Versand laeuft.** Box 245 hat ihre Logs selbst ins Dashboard geschickt —
kein USB-Stick mehr noetig. Ein Tippfehler blockierte ihn zunaechst
(`self.config` statt `self.config_data`; ersteres ist die geerbte Tk-Methode).

**2.4.49 — Die Kamera hat gar nicht ausgeloest.** `TakePicture` gibt der Kamera
den ganzen Ablauf inkl. Scharfstellen vor; findet der Autofokus nichts, loest
sie nicht aus und meldet trotzdem Erfolg. Jetzt wird wie mit dem Finger
ausgeloest: halb druecken (AF laeuft), ganz durch (ohne AF-Zwang), loslassen.
Ergebnis laut Christian: "vom geraeusch her macht die kamera fotos, ich hoere
den spiegel" — der Fix greift.

Ausserdem: Rueckkanal fuer Boxen OHNE Karte wiederhergestellt. Bis 09.03.2026
wurde er direkt registriert; danach lief der Aufruf in einem Hintergrundfaden
und blieb im COM-Marshaling haengen. Umgebaut wurde er in einem Commit, der
laut Betreff um Collage-Buttons ging.

**2.4.50 — Die Box sah das Foto nicht.** Das EDSDK friert den Inhalt eines
Verzeichnis-Objekts beim ersten Abfragen ein. Die Warteschleife befragte immer
dasselbe Objekt und bekam den alten Stand. Beweis: Bildanzahl 1726 (12:01) vs.
1729 (12:16) — drei Fotos dazugekommen, innerhalb der Wartezeit aber nie
bemerkt. Jetzt wird jedes Mal frisch nachgesehen; ein Foto wird nach ~1,4 s
erkannt statt nach 10 s Timeout ins Leere zu laufen.

**Offen:** Das Standbild zeigt einen anderen Bildausschnitt als das finale Foto
(Vorschau vs. Aufnahme). Wird angefasst, sobald die Aufnahme steht.

---

## 2026-08-21 (spaeter Nachmittag) — Die Speicherkarte war die ganze Zeit da (2.4.48)

Christian mitten im Test: "halt, bei dieser testbox ist doch eine sd karte in
der kamera drin! das ist aber nicht immer der fall"

Damit war klar: Die Box hat eine Karte uebersehen, die nachweislich steckte.

**Gefunden:** In der Struktur `EdsDirectoryItemInfo` stand `size` als 32-Bit-Zahl,
der Canon-Header sagt 64 Bit. Dadurch waren alle folgenden Felder um 4 Bytes
verschoben — `isFolder` las die oberen Bits der Dateigroesse (also 0), der
Dateiname kam leer an. Die Pruefung auf den DCIM-Ordner konnte nie zutreffen.

Nachgestellt mit den Bytes, die eine Kamera fuer "DCIM" schickt:
alter Code las `isFolder=0, Name=b''`, neuer Code liest `isFolder=1, Name=b'DCIM'`.

**Das erklaert den Totalausfall:** Es gibt zwei Wege, ein Foto zu holen — ueber
die Karte oder per Direktdownload. Beide waren kaputt (Karte: falsches Layout;
Download: nie eingerichteter Rueckkanal). Der Code wich automatisch vom einen
auf den anderen aus und verdeckte damit, dass es zwei Fehler waren.

**Ausserdem:** Eine leere Karte gilt nicht mehr als "keine Karte". Der
DCIM-Ordner entsteht erst mit dem ersten Foto; er wird jetzt waehrend der
Aufnahme erneut gesucht. Damit geht auch das erste Foto auf einer neuen Karte
nicht mehr verloren.

**Erwartung fuer den naechsten Test:** Box mit Karte laeuft ueber die Karte —
echte DSLR-Fotos in voller Aufloesung, keine 10 Sekunden Wartezeit, keine
verwaschenen Bilder. Boxen ohne Karte nutzen weiter den Direktdownload.

---

## 2026-08-21 (Nachmittag) — Log-Versand ans Dashboard + DSLR-Traegheit (2.4.47)

**Neu: Logs per Knopfdruck ins Dashboard.** Christian musste bisher bei jeder
Testrunde mit dem USB-Stick zur Box laufen. Da die Boxen in der Firma im WLAN
haengen, schicken sie ihre Logs jetzt selbst.

- Box: Service-Menue (3198) → „Logs ans Dashboard senden"
- Dashboard: Fotoboxen → Box-Logs (Filter je Box, Volltextsuche, Fehler farbig)
- Kanal: derselbe wie der Heartbeat, Adresse wird abgeleitet
  (`/booth/heartbeat` → `/booth/logs`) — **keine Konfigaenderung auf den ~280
  Boxen noetig**
- End-to-End getestet gegen einen simulierten Dashboard-Server mit echten
  Box-Logs: 5 von 5 Dateien angekommen, 86 KB → 12 KB gepackt, falscher
  Zugangsschluessel wird sauber abgefangen

**Kamera-Befund aus dem 2.4.46-Test (Box im Dev-Mode):** Die Reparaturen von
2.4.46 greifen — keine Endlosschleife, keine Doppelbilder mehr. Aber es kamen
weiterhin 0 echte DSLR-Fotos an. Die Ursache liegt tiefer als vermutet:

Die Registrierung des Kamera-Rueckkanals meldete Erfolg, obwohl der Aufruf
haengen geblieben war — im Code stand woertlich „Handler funktioniert
trotzdem". Diese Behauptung war falsch und hat die Fehlersuche blockiert. Der
Haupt-Faden pumpte nur 0,5 s Windows-Nachrichten, wodurch der Aufruf nie
zurueckkehren konnte. Jetzt 4 s, und bei Fehlschlag eine ehrliche Meldung.

**Traegheit behoben:** 12,7 s pro Foto, davon 10 s Warten ins Leere. Die
Wartezeit haengt jetzt davon ab, ob der Rueckkanal ueberhaupt existiert
(1,5 s / 4 s / 10 s).

**Offen:** Ob die verlaengerte Registrierung reicht, muss die Box zeigen. Der
zuverlaessigste Weg waere eine SD-Karte in der Kamera — dann faellt der ganze
Ereignis-Weg weg. Ausserdem erklaert sich damit die Unschaerfe: Es sind gar
keine Fotos, sondern hochgezogene Vorschaubilder (1056x704 statt 6000x4000).

---

## 2026-08-21 — DSLR-Boxen repariert: Fotos, Endlosschleife, Doppelbilder (2.4.46)

Christian hat die Software erstmals auf anderen Tablets und mit Spiegelreflex-
kamera getestet (Box 245 und Box 248, beide Canon EOS 2000D) und zwei Fehler
gemeldet: Endlosschleife und immer dasselbe Bild in der Collage.

**Befund aus den Box-Logs** — deutlicher als erwartet:

| | Box 245 | Box 248 |
|---|---|---|
| Aufnahmen | 133 | 79 |
| davon echte DSLR-Fotos | **0** | **0** |
| Kamera-Ereignisse empfangen | **0** | **0** |

Die Kamera hat kein einziges Foto geliefert. Alle Bilder waren Vorschaubilder
mit 1056x704 statt 6000x4000.

**Vier Ursachen gefunden und behoben:**

1. Die Foto-Meldungen der Kamera wurden im falschen Programmfaden abgeholt und
   blieben deshalb ungelesen liegen (Hauptursache). → Ereignis-Takt im
   Haupt-Faden, nur bei Canon.
2. Die Notlösung nahm ein altes Vorschaubild für ein frisches → dreimal
   dasselbe Bild in der Collage. → `allow_stale=False` + Fingerabdruck-Sperre.
3. Bei Verbindungsabbruch blockierte jeder Vorschau-Versuch 1,5 s, 1.611 mal
   über 29 Minuten, bis Windows die App abschoss. → Ruhepause nach verlorener
   Runde (30 Aufrufe: 0,000 s statt 45 s).
4. Die Wiederherstellung griff nur bei einem Fehlerfall, der nie auftrat. →
   Neuaufbau bei jedem Verbindungsfehler, gedrosselt.

**Nebenbefund:** Die EDSDK-Fehlertabelle war falsch. `0x81` wurde als
„INVALID_PARAMETER" übersetzt, heißt aber `DEVICE_BUSY`; `0xc1` heißt
`COMM_DISCONNECTED` (USB weg). Die Logs haben die Fehlersuche also aktiv in
die falsche Richtung geschickt. Tabelle jetzt aus dem Canon-Header erzeugt.

**Flotten-Sicherheit:** `webcam.py` und `session.py` wurden nicht angefasst.
`app.py` hat nur Ergänzungen bekommen, die hinter `camera_type == "canon"`
liegen. Logik ohne Hardware getestet (5 Tests, alle bestanden), Import-Test
für den Webcam-Pfad ebenfalls sauber.

**Offen:** Warum die Kamera-Verbindung auf den neuen Tablets überhaupt
abreißt (COMM_DISCONNECTED), ist noch nicht geklärt — Verdacht USB-Energie-
sparen. Das neue Logging soll das beim nächsten Test zeigen.

---

## 2026-08-20 (Nacht) — Etappe 2 nachgebessert nach Gegenprüfung (2.4.44)

Zwei unabhängige Gegenprüfungen von 2.4.43 haben sechs Stellen gefunden. Alle
sind behoben, nichts Neues gebaut.

**Zwei davon hätten Boxen mit AUSGESCHALTETEM Schalter getroffen:**

1. Die Puffer-Leerung (1x statt 2x) hing an „wurde gerade umgeschaltet?" statt am
   Schalter. Eine ganz normale Flottenbox, bei der ein Preview-Restore einmal nicht
   durchgeht, steht danach dauerhaft auf 1080p — und hätte ab da nur noch 1x geleert,
   ausgerechnet in der Lage mit dem höchsten Risiko für ein altes Pufferbild. Also
   genau das gemeldete Fehlerbild, ohne Schalter.
2. Session und System-Test haben die Betriebsart an einem reinen Auflösungsvergleich
   erkannt. Bei 640x480 gegen 1920x1080 harmlos — bei einer künftigen Kamera ohne
   640x480 (C922-Ablösung!) hätte sich die ganze neue Betriebsart von selbst
   eingeschaltet. Jetzt: Schalter AN **und** Kamera im Dauerbetrieb **und** kein
   Umschalten nötig.

**Vier für den Langlauf der Testbox:**

3. **Selbstheilung war weg.** Der klassische Weg setzte vor jedem Foto 1920x1080 neu
   und zog eine abgerutschte Kamera damit unbemerkt wieder gerade. Der Dauerbetrieb
   setzte nichts mehr und glaubte seinem Merker — nach einem USB-Wackler wären bis
   Abendende still Fotos in 640x480 gespeichert und gedruckt worden. Jetzt wird der
   Ist-Zustand am wirklich gelieferten Bild nachgezogen, die Box verlässt den
   Dauerbetrieb und macht für das betroffene Foto sofort einen zweiten Anlauf.
4. Das Warm-Öffnen prüfte 1080p nur an der gemeldeten Eigenschaft, nie an einem
   echten Bild. Jetzt wird ein Probebild gelesen und vermessen.
5. Der Rückfall ließ die Box in YUY2 zurück (dauerhafter MJPG-Merker), obwohl das Log
   „arbeitet wie die übrige Flotte" versprach — das wäre schlechter als klassisch.
6. Blitz-Notbremse 400 → 700 ms (400 ms war knapper als die gemessene Capture-Zeit),
   System-Test bricht bei krummer Foto-Auflösung nicht mehr ab.

**Ehrlicher formuliert:** Die Vorschau wird im Dauerbetrieb nicht „nicht flüssiger",
sondern **langsamer** — grob 7 statt 9,5 Bilder/s (Kamerabild 71,9 statt 33,6 ms,
Einpassen ins Fach ~15 ms mehr). Steht so jetzt im Changelog und im Admin-Menü.

**Speicher geprüft (Gegenprüfung):** Es sammelt sich nichts an — genau ein
Frame-Halter (`last_frame`), ein Ein-Bild-Steckplatz im LiveView, kein Verlauf.
Dauerhafter Mehrverbrauch rund +5 MB. Bei 4 GB unkritisch.

---

## 2026-08-20 (Nacht) — Kamera darf dauerhaft in Full HD laufen (2.4.43, Etappe 2 von 2)

Auftrag Christian: *„wenn eine session gemacht wird und ein foto geschossen wird
(blitz kommt) dann wird ganz kurz ein foto in der collage gezeigt aber das ist dann
nicht das foto was auch anschliessend im vollbild gezeigt wird... als wenn 2 fotos
geschossen werden!"*

**Die Ursache, aus dem Box-Log:** Die Kamera wird für JEDES Foto von 640x480 auf
1920x1080 umgeschaltet und danach zurück. `set=1572ms` hoch, `read=236ms`,
`set=1251ms` zurück. Sichtbare Wartezeit bis zur Fotoanzeige: **1842 ms.** Der Blitz
markiert also nicht die Aufnahme, sondern nur das Ende des Countdowns — belichtet wird
1,7 Sekunden später. Der Gast sieht erst das eingefrorene Vorschaubild aus der Pose
VOR dem Blitz und danach ein Foto aus einem ganz anderen Moment. Christians Diagnose
„als wenn 2 fotos geschossen werden" war exakt richtig.

**Was gebaut ist:** Ein Schalter, **Grundwert AUS**. Ist er an, wird die Kamera
einmal in Fotoauflösung geöffnet und bleibt dort; `get_high_res_frame` erkennt von
allein „Zielauflösung ist bereits aktiv" und schaltet nicht mehr um.

- Schalter: `camera_dauerbetrieb_hd` → Admin-Menü (3198) → Tab **Kamera** →
  „Kamera dauerhaft in Full HD (nur Testbox)". Liegt in `machine_settings.json`
  (ProgramData), überlebt also OTA-Updates.
- **Warm-Öffnen** statt kalt in 1080p: erst 640x480, ein Bild lesen, dann hochsetzen.
  Grund: Der Kalt-1080p-Open hat am 13.08. Box 224 eingefroren.
- **Rückfall**, wenn die Kamera kein 1080p liefert oder MJPG ablehnt: zurück auf
  640x480 + Warnung im Log, Box arbeitet wie die restliche Flotte.
- Blitz hält bis zum Foto (Notbremse 400 ms), Puffer-Leerung 1x statt 2x,
  Preview-Restore entfällt, System-Test folgt der echten Betriebsart mit eigener
  fps-Schwelle (9,0 bei HD).

**Grundlage:** Kamera-Messung auf der echten Box — 1920x1080 MJPG = 13,9 Bilder/s,
71,9 ms pro Bild, **davon 0 ms Warten auf die Kamera**. Der Dauerbetrieb wurde erst
durch Etappe 1 tragfähig (Aufbereitung 0,14 ms statt 4,19 ms bei 1080p).

**Ehrlich zur Erwartung:** Die Vorschau wird dadurch **nicht flüssiger**. Der Deckel
ist die Anzeigezeit im UI-Thread (`delay = max(..., display_ms*3)`), nicht die Kamera.
Gewinn sind der passende Blitz und — sichtbar — der passende Bildausschnitt: Die
Vorschau ist im Dauerbetrieb 16:9 wie das Foto, also links/rechts enger und
oben/unten weiter als heute.

**Auf den ~280 Boxen im Feld ändert sich ohne Umlegen des Schalters nichts.**
Der klassische Weg in `initialize()` ist Zeile für Zeile unverändert.

---

## 2026-08-20 (spät) — Vorschau umgedreht: erst verkleinern, dann spiegeln (2.4.41, Etappe 1 von 2)

Auftrag Christian: *„Nur die Vorschau-Aufbereitung umdrehen. Der Foto-Ablauf bleibt in
dieser Etappe UNANGETASTET."*

**Was war:** Für jedes Vorschaubild wurde erst das volle Kamerabild gespiegelt und
umgefärbt, dann auf das kleine Collagen-Fach verkleinert. Bei 640x480 liefen Spiegeln
und Umfärben also über 307.200 Punkte, obwohl davon nur 86.880 übrig blieben.

**Was ist:** Erst verkleinern und beschneiden, dann spiegeln, dann umfärben.
Nur `src/ui/screens/session.py` (`_prepare_live_frame`, `_compose_overlay_frame`,
`_fit_frame_to_box_np`, neu `_mirror_frame`). Foto-Pfad nicht angefasst.

**Ergebnis ehrlich:** 640x480 → 3,6x, 1280x720 → 9,4x auf dieser Kette.
**Aber bei 320x240 und 480x360 praktisch nichts** (1,0x / 1,1x), weil die Vorschau dort
kleiner ist als das Fach und der Cover-Fit vergrößert statt verkleinert. Die
`config.json` dieser Box steht auf 320 → **auf dieser Box ist kein Unterschied spürbar.**
Vorgabe in `defaults.py` ist 640, dort schon.

**Bild unverändert:** an echten Box-Fotos bei 640x480 mittlere Abweichung 0,00 von 255,
max 1. Gleicher Ausschnitt, gleiches Seitenverhältnis, gleicher Beschnitt — nachgerechnet
über 4 Auflösungen x 3 Fachformen x `rotate_180` an/aus.

**Bewusst NICHT gebaut:** `live_view_resolution` wurde nicht angefasst. Ob der LiveView
überhaupt höher laufen soll, ist Christians Entscheidung und Thema von Etappe 2.

---

## 2026-08-20 (Abend) — „0 gefundene Kameras", obwohl die Logitech dranhing (2.4.40)

Meldung Christian: *„der test zeigt 0 gefundene kamera aber die logitech ist ja dran."*

**Die Ursache in einem Satz:** Eine fehlgeschlagene **Namensabfrage** wurde als Beweis
gewertet, dass die Kamera **intern** ist. Das sind zwei völlig verschiedene Dinge — und
die Kamera stand überhaupt nur in der Liste, WEIL cv2 sie öffnen konnte.

### Umgesetzt in `src/camera/webcam.py`

| Was | Warum |
|---|---|
| Namensabfrage läuft in-process über `ctypes` (`ICreateDevEnum` → `IEnumMoniker` → `IPropertyBag`), PowerShell nur noch als zweiter Versuch | Gemessen: ~4 ms echte Arbeit in ~560–670 ms Verpackung (Prozessstart + CLR + `csc.exe` bei jedem Aufruf). Auf dem Atom reißt genau diese Verpackung die 10-s-Grenze. In-process hier gemessen: **2,6–6,6 ms**, 200 Durchläufe stabil |
| Rückgabe ist `(geraete, abfrage_ok)` statt nur einer Namensliste | „0 Geräte gefunden" und „ich konnte nicht nachsehen" sind zwei Aussagen. Ihre Vermischung **war** der Bug |
| PnP-Fallback als Namensquelle ersatzlos gestrichen | `Get-PnpDevice -Class Camera,Image` lieferte im Test **zwei Drucker und null Kameras**. Diese Namen wurden positionsweise auf cv2-Indizes geklebt → die abgeklebte Index-0-Kamera hätte „HP Color LaserJet…" geheißen und wäre als „extern" gewählt worden |
| Drei Zustände `extern` / `intern` / **`unbestimmt`**, Regel `name != "kamera N"` entfällt | Die alte Regel stammt vom 27.03.2026 und war gegen namenlose Phantom-Duplikate gebaut, nicht gegen eine gescheiterte Abfrage |
| Neue Registry-Gegenprobe (`KSCATEGORY_VIDEO`, nur `Linked=1`) | Zweite, völlig unabhängige Quelle für „hängt eine USB-Videoquelle dran?" — **0,08 ms gemessen**, kein Prozessstart, keine Hardware wird angefasst. `Linked=1` ist Pflicht: abgezogene Geräte bleiben als Karteileichen stehen |
| Namenszuordnung über den Geräteindex `i` statt über `len(cameras)` | Ließ sich ein Index gerade nicht öffnen, rutschten alle folgenden Namen um eine Position — dann trug die C922 den Namen der internen Kamera. Zweiter, vom Timeout unabhängiger Weg zu „0 Kameras" |
| Nur noch so viele Indizes öffnen, wie DirectShow meldet | Spart auf einer Ein-Kamera-Box vier Geräteöffnungen pro Suche und verkleinert die Kollisionsfläche für den Heap-Absturz von Box 044 |
| Neu: `C:\ProgramData\FexoBox\kamera_erkennung.json` | Gedächtnis **und** erstes dauerhaftes Diagnosemittel — im Feld existiert kein Log (nur mit `--dev`). Greift nur, wenn die Registry unabhängig bestätigt, dass genau diese VID/PID jetzt wieder am Bus hängt. Kein Zeitablauf, das Risiko ist der Hardwaretausch |

### `src/app.py`

- `camera_index` wird **nicht mehr aus Unwissen** auf `-1` gesetzt. Nur noch bei
  positivem „alles intern"-Befund oder bei mehreren unbestimmten Geräten ohne
  Bestätigung. Vorher überschrieb ein einziger PowerShell-Aussetzer eine
  nachweislich funktionierende Einstellung.
- Wächter: Blinken (2 s, reine Anzeige) und volle Suche (höchstens alle 20 s) sind
  getrennt. Vorher plante er im `-1`-Zustand alle 2 s eine Suche, die selbst über
  10 s dauerte — die Box war praktisch dauerhaft mit Kamerasuche beschäftigt.

### `src/config/config.py`

`camera_index = -1` wird nicht mehr nach ProgramData geschrieben und beim Lesen
ignoriert. Bis 2.4.39 drückte `_recover_machine_settings()` die `-1` bei **jedem**
Start wieder in die Config — ein einziger Aussetzer konnte eine Box dauerhaft blind
nageln. Betroffene Boxen werden beim ersten Start mit 2.4.40 davon befreit.

### `src/ui/screens/admin.py`

Ghost-Filter raus, Filter nach Einordnung rein: `intern` ausblenden, `unbestimmt`
**anzeigen und kennzeichnen** (`[0] Kamera 0 (Name unbekannt)`). Christian hat damit
wieder einen manuellen Notausgang. Der Notbehelf `[0] Standard-Kamera` wird zu
`Keine Kamera gefunden` **ohne Index** — vorher schrieb ein Klick auf Speichern
ungeprüft `camera_index = 0`, auf dem Miix also die abgeklebte Kamera.

### `src/company_network.py`

Heartbeat meldet zusätzlich `camera_type`, `camera_state` und `camera_index`
(rein additiv, löst **keine** Kamerasuche aus — liest nur die Diagnosedatei).
Bisher war unmöglich zu sagen, wie viele der ~280 Boxen gerade blind sind.
**Vor dem Rollout:** adminFexobox-Endpunkt muss unbekannte Felder tolerieren.

### Richtiggestellt

„Die abgeklebte interne Kamera liefert nie ein Bild" ist durch nichts belegt und
physikalisch unwahrscheinlich — Klebeband macht das Bild dunkel, es stoppt den Sensor
nicht. Steht jetzt korrekt in `src/main.py` und im Messbericht, damit daraus niemand
eine Erkennungsregel baut.

### Rollout

Erst Christians Box, dann zwei Testboxen, dann die Flotte. Auf der ersten echten Box
prüfen: (1) ist `DevicePath` gefüllt? (2) Registry-Ausgabe protokollieren.
(3) einmal mit abgezogener Kamera starten.

---

## 2026-08-20 (Nachmittag) — Die Messung selbst kann nicht mehr endlos hängen (2.4.36)

Der Umbau auf einen eigenen Prozess (siehe unten) hat die **Folge** entschärft: Die
Oberfläche friert nicht mehr mit ein. Die **Ursache** lag aber im Messcode selbst — er
hatte keine einzige Zeitgrenze und schrieb den Bericht erst ganz am Ende.

### Umgesetzt in `src/tools/kamera_messung.py`

| Was | Warum |
|---|---|
| Jeder Kamerazugriff läuft in einem Wegwerf-Thread mit Zeitgrenze (640×480 = 25 s, 720p = 35 s, 1080p = 50 s, Umschalt-Test = 30 s), dazu ein Gesamtbudget von 8 Minuten | Vorher: 5× `read()` + 30× `grab()` je Zelle ohne jede Abbruchbedingung. Ein blockierender cv2-Aufruf lässt sich nicht abbrechen — nur **aufgeben**; das steht so auch im Code |
| Bericht wird nach **jedem** Schritt atomar geschrieben (`.tmp` + `os.replace`), mit Statuskopf „Schritt 4 von 11 / läuft seit 00:02:13" | Einziges mögliches Lebenszeichen: `print()` fällt im Fenster-Build ins Leere. Ein Abbruch hinterlässt jetzt alle bis dahin fertigen Messwerte |
| Nach einem aufgegebenen Schritt werden alle weiteren Kamera-Schritte übersprungen und begründet | Der aufgegebene Thread besitzt Kamera **und** Sperre weiter — ein zweiter Zugriff wäre die Heap-Korruption aus 2.4.31 |
| Kamera-Sperre wird **im Worker-Thread** genommen, nicht außen | `camera_hardware_lock()` ist ein RLock und nur für denselben Thread reentrant |
| Liefert ein Backend schon bei 640×480 nichts, fallen seine restlichen Zellen weg (mit Zeile im Bericht) | Sonst dreimal volle Wartezeit für null Erkenntnis |
| Abschnitt 3 rechnet auf einem Bild aus Abschnitt 1 statt die Kamera erneut zu öffnen | Spart 3 Öffnungen + 18 blockierbare `read()`; die Kalt-1080p-Öffnung hatte am 13.08. schon einmal eine Box eingefroren |
| Auflösung **vor** dem Codec setzen, danach beides zurücklesen und im Bericht ausweisen (`1920x1080 MJPG`) | Genau umgekehrt zur eigenen Erkenntnis aus 2.4.13 — gemessen wurde vermutlich YUY2 statt MJPG, also nicht die zentrale Frage |
| OpenCV-Meldungen nicht mehr stumm, sondern (wenn möglich) in `kamera-messung-opencv.txt` | „can't grab frame" & Co. erklären den Hänger — für ein Diagnosewerkzeug war Stummschalten die falsche Richtung |

### `src/main.py` (`--kamera-test`)

- `install_faulthandler()` läuft jetzt **auch** in diesem Zweig (die BAT verspricht
  „in absturz.log steht dann, woran es lag" — vorher gab es dort keinen).
- Kamera-Index nicht mehr hart 0: `--kamera-index` > Config > `find_best_camera()`.
  Index **und Gerätename** stehen im Berichtskopf, damit sofort sichtbar ist, welche
  Kamera gemessen wurde. (Auf Christians Box war 0 richtig — die C922 hängt dort auf 0.
  Auf Boxen mit interner Tablet-Kamera ist 0 die abgeklebte.)
- Exit-Code 0 = Bericht geschrieben, 1 = nicht.

### `setup/Kamera-Messung-starten.bat`

Alter Bericht wird als `kamera-messung-vorher.txt` aufgehoben statt gelöscht; nach
`taskkill` wird per `tasklist` nachgesehen statt blind 5 s gewartet; der Ausweichpfad
`C:\ProgramData\FexoBox` wird geprüft; neuer Text sagt 2–4 Minuten an, erklärt die
Fortschrittsanzeige über die mitwachsende Berichtsdatei und warnt: Das schwarze Fenster
zuzuklicken beendet die Messung **nicht**.

### Geprüft (lokal)

| Test | Ergebnis |
|---|---|
| `python -m py_compile` alle drei Dateien | fehlerfrei |
| Kamera, die nie ein Bild liefert (simuliert) | nach 3 s aufgegeben, Rest übersprungen **mit Begründung**, Bericht vorhanden |
| Gesunde Kamera (simuliert) | alle 11 Schritte, Spalten sauber, Format MJPG ausgewiesen |
| Abbruch mitten im Lauf | Status `ABGEBROCHEN`, gemessener Teil bleibt erhalten |
| Bericht während des Laufs geöffnet | Kopf zeigt Schritt, Laufzeit und Warnhinweis |
| Warteschleife der BAT (isoliert) | verlässt die Schleife nach der ersten Runde |

---

## 2026-08-20 (Mittag) — Kamera-Messung fror die Box ein: Umbau auf eigenen Prozess (2.4.36)

**Meldung Christian:** Erst „ich warte nun schon 5 min aber der test wird immernoch
angezeigt! laeuft das ueberhaupt?", dann „ich kann auch nicht schliessen, ich musste
nun einen hard aus machen und die box neu starten."

### Beweislage aus `D:\logs` (Box mit 2.4.35)

`fexobooth_20260820_090921.log` endet exakt an dieser Stelle:

```
09:12:06.930 | Kamera-Messung wird geoeffnet (Kamera-Index 0)
09:12:09.559 | Webcams gefunden: 1 gesamt, 1 extern
09:12:15.454 | Kamera freigegeben
09:12:15.454 | Kamera-Messung: Kamera der App freigegeben
<< danach keine einzige Zeile mehr >>
```

Danach fehlt auch der UI-Hitch-Wachhund, der vorher regelmaessig meldete. `absturz.log`
enthaelt nur Start-Zeilen, keinen Absturz. Also **Stillstand, kein Absturz** — und zwar
ab dem ersten Kamerazugriff der Messung.

**Gegengeprueft und verworfen:** Die Analyse vermutete, die Messung ziele auf die
interne Tablet-Kamera (Index 0). Das Log widerlegt es: `Externe Kamera bevorzugt:
[0] c922 Pro Stream Webcam` — Index 0 IST die C922 auf dieser Box.

### Ursache

Mein Entwurf war falsch: Die Messung lief als Hintergrund-THREAD in der laufenden App.
Zwei Effekte, beide dort unvermeidbar:
1. Ein minutenlanger OpenCV-Kamerazugriff blockiert den Python-Prozess so, dass die
   Tk-Oberflaeche nicht mehr drankommt.
2. Die Messung hielt `camera_hardware_lock()` ueber ihre gesamte Laufzeit.

Als Einzelprogramm (`--kamera-test`) war derselbe Code unauffaellig — dort gibt es
keine Oberflaeche, die einfrieren koennte. Genau dieser Unterschied wurde uebersehen.

### Umgesetzt

`src/ui/dialogs/kamera_messung.py` komplett neu: Der Knopf startet die Messung als
**eigenen Windows-Prozess** (`fexobooth.exe --kamera-test --kamera-index N`) und pollt
ihn im 500-ms-Takt per `after()`. Eigener Prozess = eigener Interpreter und eigene
Sperren. Dazu: Abbrechen-Knopf, Laufzeitanzeige, Lebenszeichen aus der wachsenden
Berichtsdatei, Notbremse nach 15 Minuten, Kamera-Rueckgabe beim Schliessen.

### Geprueft (lokal)

| Test | Ergebnis |
|---|---|
| Durchstich: Messprozess starten → Bericht | Code 0, Bericht 2605 Bytes |
| **Haengenden Prozess abbrechen** (ignoriert SIGTERM absichtlich) | in 0,00 s beendet |
| Fortschritt im 500-ms-Takt | Laufzeit + „Bericht wird geschrieben (N Zeichen)" |
| Prozess endet ohne Bericht | wird gemeldet statt verschwiegen |
| Notbremse nach 15 Min | Prozess beendet, Kamera frei |

### Bestaetigt aus dem Feld

Im selben Log-Satz steckt die Gegenprobe fuer 2.4.35: Der **Beenden-Knopf (3198)** lief
um 09:08:52 sauber durch — Taskleiste → Benachrichtigungen → **Kamera-Freigabe** →
`_root_lebt()`-Abbruch → `FEXOBOOTH BEENDET`, komplett in **0,3 Sekunden**, ohne dass
der Notausstieg einspringen musste.

---

## 2026-08-20 — Beenden-Knopf laesst keinen Prozess mehr stehen + Kamera-Messung als Knopf (2.4.35)

**Meldung Christian:** „Der App beenden Button ueber 3198 beendet die App nicht richtig,
sie geht zwar zu aber da bleibt ein Prozess am Taskmanager aktiv." Ausserdem: „Bau den
Kamera-Test der die .txt schreibt als Button in der Software fest ein."

### Ursachenanalyse Beenden-Knopf

Der Vergleich mit dem seit langem funktionierenden Notausstieg Ctrl+Shift+Q hat es gezeigt:
Es gab **zwei getrennte Beenden-Wege mit eigenem Code**, und der Knopf-Weg war der duennere.

| | Notausstieg Ctrl+Shift+Q | Beenden-Knopf (3198) |
|---|---|---|
| Grab loesen + Dialog schliessen | ja | **nein** |
| Taskleiste/Benachrichtigungen | ja | ja |
| `camera_manager.release()` | ja | **nein** |
| Netz, falls mainloop haengt | nein | **nein** |

Dazu zwei Dinge, die BEIDE Wege betrafen:

- **`os._exit(0)` nimmt Kindprozesse nicht mit.** `main.py` beendet den Prozess bewusst hart
  (Kommentar dort: non-daemon Threads hielten die EXE sonst am Leben). Das beendet aber nur
  den Python-Prozess — die unsichtbare `FexoNikonBridge.exe` ist ein eigenstaendiger
  Windows-Prozess und blieb als Waise stehen. `NikonCameraManager.release()` laesst sie sogar
  ausdruecklich weiterlaufen („Bridge bleibt aktiv"), damit der naechste Session-Start keinen
  Kaltstart hat — beim echten Beenden ist das aber falsch. Ein `stop()` existierte, wurde beim
  Beenden nur nie gerufen.
- **Hinter jedem `wait_window(...)`** in `src/app.py` lief Code weiter, der `current_screen`
  anfasst. Nach dem Beenden existiert das Hauptfenster nicht mehr → TclError mitten im Beenden.

### Umgesetzt

- Neu `src/utils/shutdown.py`: gemeinsames Aufraeumen, Wachhund, Waisen-Aufraeumen.
- Neu `PhotoboothApp.shutdown(grund)` — **einziger** Beenden-Weg. `_emergency_quit()`, `quit()`
  und der 3198-Knopf laufen jetzt alle hier durch. Jeder Aufraeum-Schritt einzeln abgesichert.
- **Wachhund:** Beim Einleiten des Beendens scharf, beendet den Prozess nach 8 s notfalls hart.
  Feuert im Normalfall nie (gemessen: Beenden dauert 0,02 s).
- Neu `shutdown_bridge()` in `src/camera/nikon.py`.
- Neu `PhotoboothApp._root_lebt()` + Abbruch hinter allen drei `wait_window`-Stellen.
- Waisen frueherer Abstuerze werden beim **App-Start** im Hintergrund weggeraeumt.

### Kamera-Messung als fester Knopf

Neu `src/ui/dialogs/kamera_messung.py` + Knopf im Admin-Menue → Tab **Kamera**. Damit
entfaellt: Software beenden, USB-Stick, BAT-Aufruf. Fortschrittsanzeige, danach
„Bericht oeffnen". Die Messung laeuft **zwingend unter `camera_hardware_lock()`** — sie
oeffnet die Kamera mit eigenen `cv2.VideoCapture`-Aufrufen, und ohne die Sperre waere der
Absturz aus 2.4.31 zurueck (Heap-Korruption 0xc0000374 bei doppeltem Kamerazugriff).
Vorher wird die Kamera der App freigegeben, danach ueber `_pre_init_camera()` wieder
bereitgestellt.

### Geprueft (lokal, ohne Box)

- `shutdown()` beendet `mainloop()` in **0,02 s**; Reihenfolge Taskleiste →
  Benachrichtigungen → Kamera-Freigabe stimmt.
- Ein Fehler in einem Aufraeum-Schritt stoppt die folgenden nicht.
- Beenden-Knopf: Grab geloest → Dialog zu → gemeinsamer Weg. Ohne App-Objekt greift der
  harte Ausstieg.
- Mess-Dialog: Kamera zuerst frei, Messung **unter gehaltener Sperre** (aus einem zweiten
  Thread geprueft, weil ein RLock im eigenen Thread reentrant ist), Sperre danach frei —
  auch wenn die Messung eine Ausnahme wirft.
- **Nebenbefund:** `taskkill` blockierte im Test **5 Sekunden**. Deshalb laeuft es NICHT
  mehr auf dem Beenden-Weg, sondern nur beim Start im Hintergrund. Sonst haette der Fix
  eine sichtbare 5-Sekunden-Blockade beim Beenden eingebaut.

### Offen

- Auf einer echten Box gegenpruefen, ob nach „App beenden" wirklich kein Prozess mehr
  im Task-Manager steht (der lokale Test hatte keine laufende Bridge).

---

## 2026-08-19 (Nachmittag) — GELOEST: Der Router war die Hauptursache

Gemeinsam mit Christian die Router-Oberflaeche durchgegangen (Telekom Digitalisierungsbox
Premium = bintec elmeg be.IP plus, Firmware 11.01.03.115, PBX-Modus).

**Befund:** Der DHCP-Adressbereich fuer LAN + fexon WLAN (beide auf Bridge `br0`) umfasste
`192.168.2.200`–`.250` = **51 Adressen** — bei 200+ Fotoboxen plus PCs, Gigaset-Telefonen,
bintec-Access-Points und diversen Smart-Home-Geraeten. Dazu **120 Minuten Lease Time**.
Die Router-Liste *IP/MAC-Bindung* zeigte **"Summe der Objekte: 53"** = 51 Haupt-Pool + 2 Gaeste:
**der Pool war zu 100 % belegt.** Boxen, die danach kamen, bekamen nichts → `169.254.x.x`.

**Gegenprobe per Netzwerk-Scan** (von Christians PC, 192.168.2.212): Unterhalb von `.200` waren
nur `192.168.2.1` (Router) und `192.168.2.116` belegt — der ganze Bereich lag brach.

**Aenderung im Router:**
| Einstellung | vorher | nachher |
|---|---|---|
| Pool "DHCP Adressbereich" | `192.168.2.200`–`.250` (51) | **`192.168.2.130`–`.250` (121)** |
| Lease Time (`br0`) | 120 Min. | **30 Min.** |

Start bei `.130` mit Sicherheitsabstand: Der Scan sieht nur eingeschaltete Geraete, `.2`–`.129`
bleibt Reserve fuer feste Adressen.

**Dokumentiert** in ERKENNTNISSE.md ("GELOEST: Firmen-WLAN + Router") inkl. Router-Daten,
Netz-Aufbau, komplettem Klickpfad zur versteckten Experten-Navigation, den DHCP-Optionen die
man NICHT anfassen darf, und dem Scan-Befehl. Zusaetzlich als projektuebergreifende Notiz
gesichert (Memory `reference_fexon_firmen_wlan_router`).

**Rueckblick auf die ganze Kette — es waren DREI Probleme, die sich gegenseitig versteckt haben:**
1. Der eigene Hotspot blockierte auf manchen Boxen die WLAN-Karte (2.4.29)
2. Zwei Threads an derselben Kamera → Abstuerze mit Heap-Zerstoerung (2.4.31)
3. **Der Router-Pool war voll** (heute, ohne Software-Aenderung)

Der Durchbruch kam nicht durch Code, sondern dadurch, dass die Boxen ab 2.4.28 **von selbst
protokollieren** (`netzwerk.log`, `absturz.log`) — ohne Developer-Mode. Erst die Zeile
`Eig. Hotspot: aus` + `KEINE IP-ADRESSE` hat die Box entlastet und den Router ueberfuehrt.

---

## 2026-08-19 (nachmittags) — Absturz-Fix bestaetigt, neuer blinder Fleck geschlossen (2.4.32)

**Absturz-Fix wirkt:** Boxen 19, 31 und 38 laufen mit 2.4.31; `absturz.log` enthaelt auf allen
dreien nur noch `Start (Absturz-Ueberwachung aktiv)` — kein `fatal exception` mehr.

**Neues Problem:** Dieselben drei Boxen melden sich nicht im Dashboard und hatten **gar keine
`netzwerk.log`**. Aus den Start-Zeitstempeln in `absturz.log`:

| Box | Start 1 | Start 2 | Laufzeit |
|---|---|---|---|
| 19 | 11:43:48 | 11:46:49 | 3:01 |
| 31 | 10:15:30 | 10:17:59 | 2:29 |
| 38 | 14:55:43 | 14:58:31 | 2:48 |

Die Bilanz stand am Ende der Wiederholkette (20+30+45+60+90 s ≈ 4 Min) — die Boxen waren vorher
aus. Mein Rat „3 Minuten reichen" war also fuer diesen Fall falsch: Er galt nur fuer
„keine IP-Adresse" (dort schreibt seit 2.4.29 ein Fruehbefund).

**Fix 2.4.32:** Erst melden, Bilanz SOFORT schreiben, dann erst die Wiederholkette.
Test: Eintrag nach 1,5 s statt gar nicht.

**Zweiter Fund (Box 044, Foto vom Selbsttest):** Warnung „Hohe Hintergrund-Auslastung: CPU 75 %
(Windows-Update/Defender?)" war ein **Fehlalarm**. `psutil.cpu_percent()` misst die GESAMT-Last
inklusive der App. Das Log derselben Box zeigt: CPU gesamt 20–48 %, davon `fexobooth.exe`
19–39 %, `System Idle Process` 54–73 %. Die Box war nicht ausgelastet, und Windows-Update/
Defender waren unbeteiligt. Jetzt wird die eigene Last abgezogen (`cpu_fremd_prozent`).

**Weiterhin offen:** Warum sich 19/31/38 nicht melden. Dazu gibt es bislang KEINE Daten.

---

## 2026-08-19 — ABSTURZ GELOEST: zwei Threads an derselben Kamera (2.4.31)

**Der `faulthandler` aus 2.4.30 hat geliefert.** `absturz.log` von Box 044 (19.08. 08:44:02):

```
Windows fatal exception: code 0xc0000374          <- HEAP CORRUPTION
Current thread 0x000016bc:
  src\app.py line 2568 in _camera_status_probe     -> cv2.VideoCapture(cam_idx, CAP_DSHOW)
Thread 0x000005e4:
  src\camera\webcam.py line 519 in list_cameras    -> cv2.VideoCapture(i, CAP_DSHOW)
  src\app.py line 156 in _auto_select_webcam
```

**Ursache:** `WebcamManager.list_cameras()` ist eine `@staticmethod` und lief damit komplett an
`self._camera_lock` vorbei (das ist eine INSTANZ-Sperre). Beim Start laufen zwei Threads los —
die Kamera-Auto-Auswahl (`app.py:156`) und der Kamera-Waechter (`app.py:2568`) — und oeffnen
zeitgleich dieselbe DirectShow-Kamera. Das zerstoert den Heap; Windows meldet den Absturz erst
spaeter und woanders (`ntdll.dll` / `0xc0000005`). Aus dem Ereignisprotokoll allein war das
NICHT ableitbar.

**Warum nur „vereinzelt" und nie im Dev-Mode:** Ob sich die beiden Threads wirklich ueberlappen,
haengt am Timing (CPU-Last, Antwortzeit der Kamera). Im Developer-Mode laeuft alles anders
getaktet — das Zeitfenster war dort schlicht meist zu klein.

**Fix (2.4.31):**
- `src/camera/webcam.py`: modulweite `_CAMERA_HW_LOCK` + oeffentliche `camera_hardware_lock()`;
  Instanz-Sperre zeigt jetzt auf dieselbe Sperre; `list_cameras()` haelt sie beim Hardware-Teil
  (die Namens-Ermittlung laeuft in einem eigenen Prozess und bleibt bewusst draussen).
- `src/app.py`: die Kamera-Pruefung nimmt dieselbe Sperre.
- `src/ui/screens/start.py`: `on_show` bricht ab, wenn der Screen schon zerstoert ist
  (der zweite Fund aus demselben `absturz.log`, 08:43:54 — vom Tk-Handler abgefangen).

**Test:** Zwei „Sucher"-Threads + ein „Pruefer"-Thread gegen einen Zaehler laufen lassen:
mit Sperre **max. 1** gleichzeitiger Zugriff, ohne Sperre **2**. Damit ist die Ueberlappung
nachweislich weg.

---

## 2026-08-19 — Absturz-Signatur eingegrenzt (Box 044) + Speicherabbild-Sammler

**Datenlage aus den zwei Werkstatt-Berichten:**

| | Box 087 | Box 044 |
|---|---|---|
| EXE installiert | 11.08. 10:57 (**alte Version**) | 18.08. 12:42 (2.4.29) |
| `netzwerk.log` vorhanden | nein | ja |
| Abstürze in 21 Tagen | **keine** | 2 |

Box 087 ist damit **kein Vergleichsfall** — sie läuft gar nicht auf 2.4.29 (der einzige Eintrag
dort ist ein AppHang vom 09.02.2026 mit `FexoBooth.exe 2.0.0.0`, ein halbes Jahr alt).

**Box 044 — die Signatur ist identisch zu der Meldung vom Vortag:**
```
fexobooth.exe 0.0.0.0 | Modul ntdll.dll 10.0.19041.6456
Ausnahmecode 0xc0000005 | Fehleroffset 0x00000000000649e6
```
Zweimal exakt dieselben Werte (18.08. 14:13:45 und 15:16:03) → **derselbe Fehler, reproduzierbar**.
Absturz in `ntdll` bei stets gleichem Offset ist das typische Muster für einen
**Speicherverwaltungsfehler (Heap)**: Der Verursacher ist meist eine andere DLL, die über ihren
Speicher hinausschreibt — `ntdll` fällt erst später darüber.

**Wichtige Korrektur zur Annahme „stürzt beim Start ab":**
`netzwerk.log` von Box 044 zeigt Starts um 13:35:16, 14:45:45 und 14:47:48 (jeder App-Start im
Firmen-WLAN schreibt einen Block). Der letzte Start war **14:47**, der Absturz **15:16** — also
**29 Minuten später, mitten im Betrieb**, nicht beim Hochfahren. Die Start-Abstürze müssen andere
Boxen betroffen haben oder ein anderes Phänomen sein.

**Zeitliche Auffälligkeit (Hinweis, kein Beweis):** Die wiederkehrende Dashboard-Meldung läuft
alle 900 s ± 120 s. Ab Start 14:47 wäre die zweite Meldung zwischen 15:15:50 und 15:21:50 fällig —
der Absturz um 15:16:03 fällt genau in dieses Fenster. Das ist zu prüfen, sobald `faulthandler`
(2.4.30) den Python-Stack liefert.

**Umgesetzt:** `setup/Absturz-Infos-sammeln.bat` sammelt jetzt zusätzlich die **Speicherabbilder,
die Windows beim Absturz selbst angelegt hat** (`WER\ReportArchive` und `WER\Temp`) und kopiert
sie nach `C:\FexoBooth\logs\dumps`. Der Bericht von Box 044 nannte eine solche Datei
(`WER2CEE.tmp.dmp`) — mein Skript hatte sie vorher übersehen.

---

## 2026-08-18 (Box 056) — Fehler ENDLICH reproduziert, Reparatur zu langsam (2.4.29)

**Der Log, auf den wir gewartet haben** (`fexobooth_20260818_111651.log`, Box 056, Buchung
NX-141859, 2.4.27, Dev-Mode):

| Zeit | Zeile | Bedeutung |
|---|---|---|
| 11:17:05.377 | `Hotspot wartet: Firmen-WLAN 'fexon WLAN' erkannt` | Reihenfolge-Fix greift |
| 11:17:05.704 | `Gefundene IPs: ['192.168.137.1', '169.254.166.159']` | **Hotspot AN, keine DHCP-Adresse** — und zwar BEVOR die App den Hotspot startet |
| 11:17:15.769 | `... KEINE brauchbare IP-Adresse — starte Reparatur` | IP-Prüfung greift |
| 11:17:16.271 | `Neue IP-Adresse anfordern (Adapter: WLAN)...` | Stufe 1 alt |
| 11:18:16.444 | `renew Code 1 (TIMEOUT)` | **60 s vertan, kein DHCP-Server antwortet** |
| 11:18:36.463 | `Stufe 2 — WLAN trennen und neu verbinden...` | |
| 11:18:51.424 | `FEXOBOOTH BEENDET` | Box ausgeschaltet — Stufe 3 nie erreicht |

**Zwei harte Erkenntnisse:**
1. Die Hotspot-Adresse `192.168.137.1` ist schon **vor** dem App-Hotspot-Start da (der wartete ja
   noch auf das Netz-Fenster). Der Windows-Hotspot/ICS läuft also **ab dem Boot** — die App kann
   ihn nur noch abschalten, nicht verhindern. Genau dazu passt, dass `ipconfig /renew` ins Leere
   lief: Auf der Funkkarte läuft der AP, DHCP bekommt keine Antwort.
2. `ipconfig /release` lief ohne Fehler durch (kein Elevation-Problem auf diesen Boxen) —
   die Kiosk-Rechte reichen also für die Reparatur.

**Umgesetzt (2.4.29):** Reihenfolge umgedreht (Hotspot zuerst, erkannt an `192.168.137.x` ohne
Extra-Abfrage), `renew`-Timeout 60 s → 20 s, Wartezeiten 20 s → 15 s.

**Test:** Feld-Situation von Box 056 nachgestellt → Hotspot als Ursache steht nach **6,0 s** fest,
Konflikt-Merker wird gesetzt. Gegenprobe „nichts hilft" → sauberes Nein nach 21 s, Merker bleibt
korrekt aus.

---

## 2026-08-18 (nachmittags) — Werkstatt-Test ohne Befund → Netz-Protokoll ohne Dev-Mode (2.4.28)

**Befund:** Drei Boxen (073, 116, 016) mit 2.4.27 in der Werkstatt getestet, alle drei „geht wieder
nicht". Von D:\ kamen pro Box aber nur **zwei Installer-Logs** zurück (`company_wlan_setup.log`,
`windows_update_lockdown.log`) — **kein einziges App-Log**.

**Ursache dafür:** `src/utils/logging.py` → `setup_logging(developer_mode=False)` setzt einen
NullHandler. Im Normalbetrieb schreibt die App also *nichts*. Die ganze NETZ-BILANZ aus 2.4.27 war
in der Werkstatt damit unsichtbar — sie existiert nur, wenn jemand `start_dev.bat` benutzt.

**Was die vorhandenen Logs sagen:** Auf allen drei Boxen lief das WLAN-Setup sauber durch
(`11:36:52` / `11:56:32` / `11:56:19` jeweils „Mit 'fexon WLAN' verbunden - Setup erfolgreich"),
und der Installer lief mehrfach (Lockdown-Läufe 11:33–11:58). Die Funk-Anmeldung klappt also —
ob danach eine IP-Adresse kam, ist aus diesen Logs **nicht** ablesbar. Das deckt sich exakt mit dem
Muster von Box 200 am Vormittag.

**Umgesetzt (2.4.28):**
- `src/utils/network_diag.py`: `write_network_report()` + `log_network_verdict(persist=True)` →
  schreibt nach `C:\FexoBooth\logs\netzwerk.log` (Fallback `C:\ProgramData\FexoBox`), mit
  Zeitstempel/Box-ID/Version, Selbstkürzung bei ~200 KB.
- `src/company_network.py`: Bilanz wird persistiert; zusätzlich neuer Kurzeintrag über
  `_persist_short_report()`, wenn die Box **gar nicht** ins Firmen-WLAN kommt (inkl.
  Selbstheilungs-Status). Gate: nur wenn das Firmen-WLAN in Reichweite war (`not_visible` =
  Kundenbetrieb → es wird nichts geschrieben).

**Test:** Bewusst **ohne** `setup_logging(developer_mode=True)` ausgeführt (= Werkstatt-Situation);
`netzwerk.log` wurde angelegt und enthielt beide Blöcke (kaputter Fall mit Urteil „KEINE
IP-ADRESSE" und der Fall „NICHT im Firmen-WLAN").

---

## 2026-08-18 — Firmen-WLAN: "verbunden ohne Netz" + wirkungsloser Hotspot-Start (2.4.27)

**Feld-Befund** (`D:\fexobooth_20260818_102651.log`, Box 200, 2 Minuten Laufzeit):
- `10:27:16 | Firmennetzwerk: Firmen-WLAN erkannt ('fexon WLAN')` — der Name stimmte also.
- Direkt danach 3× `Dashboard nicht erreichbar (<urlopen error [Errno 11001] getaddrinfo failed>)`
  (10:27:16 / 10:27:37 / 10:28:07). Die Box wurde danach ausgeschaltet, die späteren
  Retry-Versuche (2.4.25) kamen nie zum Zug.
- Entscheidende Zeile davor: `10:27:05 | Gefundene IPs: ['169.254.183.239', '192.168.137.1']`.
  Das sind ALLE IPv4-Adressen des Rechners: eine Notfalladresse (APIPA = der Router hat nichts
  vergeben) und der eigene Hotspot. **Keine Adresse vom Firmen-Router.**
- Ergänzend `D:\company_wlan_setup.log` (09:21): Profil-Setup lief sauber durch und war
  verbunden — der Installer-Schritt aus 2.4.22 funktioniert also. Das Problem sitzt danach.
- `D:\windows_update_lockdown.log`: für dieses Thema ohne Befund (nur Update-Dienste/Tasks,
  nichts Netzwerk-Relevantes).

**Zweiter Fund bei der Code-Prüfung (der eigentliche Hammer):** In `src/gallery/hotspot.py`
standen in den PowerShell-Befehlen doppelte geschweifte Klammern (`{{ }}`) — Rest einer alten
`.format()`-Nutzung. Am echten PowerShell verifiziert: `if (...) {{ ... }}` wird **nicht
ausgeführt**, sondern nur als Text ausgegeben. Der Rückgabewert war dadurch 6.287 Zeichen
Script-Text bei Exit-Code 0 — und die Python-Bedingung
`success and "Error" not in output and output != "NO_PROFILE"` wertete genau das als Erfolg.
**Die App hat den Hotspot also nie gestartet, nie gestoppt, nie korrekt geprüft** und trotzdem
immer „Hotspot erfolgreich gestartet (Tethering)" geloggt. Der Hotspot auf den Boxen stammt vom
einmaligen Einrichten (`einmalig_hotspot_einrichten.bat`) und lief unabhängig von der App weiter.

**Zusammenhang:** Der Windows-Hotspot (ICS, `192.168.137.1`) belegt dieselbe WLAN-Karte wie die
Firmen-Verbindung. Wird er über das Firmen-Profil aufgezogen, verliert die Box ihre DHCP-Adresse
→ verbunden, aber ohne Netz. Das erklärt auch, warum es nur EINIGE Boxen trifft: Es hängt vom
WLAN-Chip (kann er gleichzeitig Client + Access Point?) und der Profil-Reihenfolge ab.

**Umgesetzt:**
1. `src/gallery/hotspot.py` — Klammer-Bug behoben (Syntax am echten PowerShell gegengeprüft),
   Profilwahl meidet das verbundene Firmen-WLAN (neutraler Anker `FexoBoothDummy`, jetzt immer
   vorhanden), ehrliche Auswertung (`_parse_tethering_output`) statt „alles außer Error = ok",
   Konflikt-Merker: Hotspot bleibt im Firmen-WLAN aus, wenn er dort nachweislich stört.
2. `src/utils/network_diag.py` (NEU) — IP-Bewertung (APIPA/eigener Hotspot zählen nicht als Netz),
   Router-Ping, DNS- und Dashboard-Probe, DHCP-Erneuerung, **NETZ-BILANZ** mit Klartext-Urteil.
3. `src/utils/company_wlan.py` — Selbstheilung prüft jetzt die IP-Adresse statt nur den Namen;
   neue 3-Stufen-Reparatur `repair_missing_ip()`; neue Rückgaben `ip_repaired` / `no_ip`.
4. `src/company_network.py` — Startfenster (`wait_for_startup_network_window`), IP-Prüfung vor
   dem Melden, NETZ-BILANZ nach dem Start und bei jeder fehlgeschlagenen Wiederholmeldung,
   eigene IPs direkt an der Fehlermeldung.
5. `src/app.py` — im Firmen-WLAN erst Netz-Arbeit, dann Hotspot (beim Kunden unverändert).
6. `src/ui/screens/admin.py` — Schnellhilfe kennt die neuen Status.

**Tests (Dev-Mode-Logging aktiv):**
- PowerShell-Semantik der doppelten Klammern reproduziert (Blöcke werden als Text ausgegeben,
  Funktion liefert `ScriptBlock` statt Ergebnis) und das echte Alt-Script gegen Python geprüft:
  Fehlbewertung „Erfolg" bestätigt.
- Neue Scripts: Syntaxprüfung über `PSParser::Tokenize` (START/STOP/CHECK fehlerfrei),
  Profilauswahl live getestet — ohne Ausschluss wurde Profil A gewählt, mit Ausschluss Profil B.
  Der eigentliche Tethering-Start wurde dabei bewusst NICHT ausgeführt (Test-PC).
- NETZ-BILANZ gegen ein gesundes Netz (alles grün) und gegen die nachgestellte Box-200-Lage
  (`169.254.183.239` + `192.168.137.1`) → korrektes Urteil „KEINE IP-ADRESSE".
- Startfenster: Kunde wartet 0,00 s / Werkstatt wartet bis fertig (1,50 s) / Hänger bricht nach
  Timeout ab (2,00 s) — der Hotspot kann also nie dauerhaft blockiert werden.
- Selbstheilung: 4 Fälle durchgespielt → `already_connected` / `ip_repaired` / `no_ip` /
  `not_visible` (beim Kunden wird keine Reparatur angefasst).
- Ausgabe-Auswertung: 7 Fälle inkl. der alten kaputten Textausgabe → wird jetzt korrekt als
  Fehler gewertet.

### Feldtest 2.4.27 auf Box 200 (Log `fexobooth_20260818_112955.log`) — Ergebnis

**Was nachweislich funktioniert:**
- `11:30:09 | Hotspot wartet: Firmen-WLAN 'fexon WLAN' erkannt — erst Dashboard-Meldung/Update,
  dann Hotspot` → die neue Reihenfolge greift.
- `11:30:20 | Monitoring: Version 2.4.27 für Box-ID 200 gemeldet` → **beim ERSTEN Versuch
  zugestellt**, 14 s bevor der Hotspot überhaupt startet (11:30:34). Genau der gewünschte Effekt;
  in 2.4.26 scheiterten an dieser Stelle alle Versuche.
- NETZ-BILANZ wird geschrieben: IP-Adressen / Router-Ping / Namensauflösung / Dashboard alle OK,
  `URTEIL: ALLES GRÜN`. Die Box hatte diesmal eine echte Adresse (`192.168.2.224`) — der Fehler
  vom Vormittag (nur `169.254.x.x`) trat also NICHT auf, die Reparatur-Stufen liefen folgerichtig
  nicht an.

**Was NICHT wie geplant wirkt (wichtig):**
- `11:30:44 | Hotspot: Kein neutrales Profil gefunden — musste doch das Firmen-WLAN als Anker nehmen`
  Das Dummy-Profil `FexoBoothDummy` wurde zwar angelegt (11:30:35), aber Windows liefert über
  `GetConnectionProfiles()` **nur tatsächliche Verbindungen** — ein gespeichertes, nie verbundenes
  WLAN-Profil taucht dort nicht auf. Auf einer Box mit nur einer WLAN-Karte bleibt im Firmen-WLAN
  also zwangsläufig `fexon WLAN` der einzige Anker. Der Ausschluss greift nur, wenn es eine zweite
  Verbindung gibt (z.B. LAN). **Wirksam gegen das Problem ist damit die Reihenfolge, nicht der
  Anker-Tausch.**
- Die Warnung war in diesem Lauf zudem irreführend: Der Hotspot lief bereits (`ALREADY_ON`), es
  wurde also gar nichts umgestellt. → korrigiert, Warnung kommt jetzt nur noch, wenn der Hotspot
  wirklich neu über die Firmen-Verbindung aufgezogen wird.

**Zwei Nebenbefunde aus demselben Log, beide behoben:**
- `11:31:43 | UI-HITCH: Tk-Hauptschleife war ~9207ms blockiert` nach dem Admin-Speichern:
  `_start_gallery_if_needed()` rief `start_hotspot()` direkt im UI-Thread auf (PowerShell,
  ~8 s). Läuft jetzt im Hintergrund-Thread — kein eingefrorener Bildschirm mehr.
  (Bestand schon vor 2.4.27, fiel nur durch das neue Logging auf.)
- Kamera-Erkennung lief in Timeouts (`DirectShow-Enumeration ... timed out after 10 seconds`,
  `Get-PnpDevice ... timed out after 5 seconds`, kurzzeitig „Keine externe Kamera gefunden!").
  Die Box hatte 83 % CPU-Last beim Start und mehrere PowerShell-Aufrufe gleichzeitig. Die
  NETZ-BILANZ fragt den Hotspot-Zustand deshalb nur noch ab, **wenn die Meldung NICHT durchkam** —
  im Normalfall ein PowerShell-Aufruf weniger.

**Offen:** Der eigentliche Fehlerfall (verbunden ohne IP-Adresse) ist damit noch nicht im Feld
gegengeprüft — dafür braucht es eine Box, die ihn zeigt. Das Log würde ihn jetzt eindeutig
ausweisen (siehe TODO).

---

**Offen:** Test auf echter Hardware (Build 2.4.27 auf einer betroffenen Box), siehe TODO.

---

## 2026-08-13 — Selbsttest öffnet Kamera wie im Betrieb (Fehlalarm + Einfrieren behoben) (2.4.26)

**Feld-Befund** (zwei Logs von D:\, beide **dieselbe Box 224**, Webcam „HD Pro Webcam C920"):
- `D:\kameraverzögerung\...055502.log`: Selbsttest **bestanden mit 1 Auffälligkeit** —
  „Kamera-Start langsam: 7,6s / 7,7s". Aber die Kamera war **kerngesund**: `kamera_fps=16.2`,
  drei Fotos je in ~0,1 s aufgenommen ((1920,1080)). Also KEIN echtes Kameraproblem.
- `D:\Absturz bei Selbsttest\...054921.log`: Im Selbsttest **komplett eingefroren** — das Log
  endet exakt bei `Kamera 0 geöffnet mit Backend 700` (DirectShow), also mitten im Kalt-Öffnen
  auf 1080p, VOR `Kamera initialisiert: 1920x1080`.

**Ursache:** Der Selbsttest öffnete die Kamera **kalt in voller Foto-Auflösung (1920×1080)**.
Das ist nicht der Normalablauf: Im Betrieb läuft die Vorschau in 640×480 und schaltet nur kurz
pro Foto auf 1080p (`get_high_res_frame`) — schnell (~1,5 s) und robust. Der Kalt-1080p-Open ist
auf älteren C920 langsam (~7,6 s) und kann sogar hängen. Das „mit anderer Kamera geht's, mit der
alten auch wieder" = USB-Zustand wird beim Umstecken zurückgesetzt.

**Fix (`src/ui/dialogs/system_test.py`):**
- `_step_init_camera`: öffnet jetzt in der Vorschau-Auflösung — exakt wie die Vor-Init in
  `app.py:3038` (`live_res = live_view_resolution`; `initialize(idx, live_res, int(live_res*0.75))`).
- `_capture_single_photo`: Webcam nutzt jetzt `get_high_res_frame(w, h, restore_preview=False)`
  (echter Aufnahmeweg, volle Qualität). DSLR unverändert (LiveView-Frame).
- `_step_capture_photos`: nach den Testfotos `restore_preview_resolution()`, damit die Kamera
  nicht auf 1080p stehen bleibt.

**Nebenbefund (nicht kritisch):** Box 224 läuft auf Energieplan **Höchstleistung**
(GUID 8c5e7fda-…) — dort existiert der Windows-Leistungsregler-Overlay nicht, deshalb die
Log-Warnung „Regler existiert auf diesem Plan nicht". Performance ist trotzdem am Anschlag
(Höchstleistung = CPU voll), also unbedenklich. Ebenfalls im Log: ein einmaliger
UI-Hitch ~2,5 s beim Template-Karten-Refresh vor dem Test (kein Dauerproblem).

Version → **2.4.26**. Kompiliert. Noch **kein Release** — wartet auf Box-Test durch Christian.

---

## 2026-08-12 — Release v2.4.25 veroeffentlicht

Build lokal erstellt (build_installer.bat) + GitHub-Release **v2.4.25** mit dem OTA-ZIP
veroeffentlicht. Auf Wunsch Christian direkt raus (ohne vorherigen Box-Test; Fix ist headless
getestet + rein additiv am Monitoring). /releases/latest = v2.4.25, Flotte updatet ab jetzt.
Nachtest-Logs folgen von Christian.

---

## 2026-08-12 — Dashboard-Meldung mit Wiederholung (Boxen meldeten sich nur einmal) (2.4.25)

**Feld-Befund** (Logs 11.08. Box 188/043/102 von D:\): Boxen liefen 25+ min im Firmen-WLAN,
meldeten sich aber NIE im Dashboard. Ursache im Log eindeutig: Der einzige Melde-Versuch
~15 s nach Start scheiterte an `getaddrinfo failed` (Errno 11001) — DNS direkt nach dem
WLAN-Verbinden + gleichzeitigem Hotspot-Start noch nicht bereit. `check_and_auto_update`-Worker
lief EINMALIG (`time.sleep(15)` → 1 Heartbeat → Ende), KEIN Retry, KEIN periodischer Heartbeat.
Box 188: 25 min online, 1 Versuch 14:30:02 (DNS-Fehler), danach Funkstille.

**Fix (`src/company_network.py`):**
- `_send_monitoring_heartbeat` gibt jetzt True/False/None zurück (Erfolg / Netz-DNS-Fehler
  retrybar / Konfig-fehlt-oder-abgelehnt).
- `_heartbeat_with_retry`: Startversuche nach 0/20/30/45/60/90 s, prüft vor jedem Retry, ob
  noch im Firmen-WLAN; stoppt bei Erfolg oder Ablehnung.
- `_start_periodic_monitoring`: Daemon-Thread meldet danach alle ~15 min (± 120 s Jitter),
  nur bei bestehendem Firmen-WLAN; idempotent (ein Thread pro Prozess).
- Jitter verteilt gleichzeitig startende Boxen → Christians „5-6 Boxen gleichzeitig"-Sorge ist
  unkritisch: Payload ist winzig, Laravel-Endpoint macht nur Lookup+Upsert.
Headless getestet (Retry bis Erfolg, Sofort-Stopp bei Ablehnung).

---

## 2026-08-11 (spaetnachmittags) — Release v2.4.24 veroeffentlicht

Nachtest 2.4.24 (`fexobooth_20260811_111604.log`) komplett sauber: Kamera-Waechter ohne Crash,
Kamera beim Start automatisch gefunden, Admin-Kamera-Tab ohne 9s-Freeze (Enumeration im
Hintergrund, nur ~0,6s Tab-Hitch), System-Test ERFOLGREICH mit Messwerten, Event-Wechsel auf
NX-FR-141705 + volle Session + Druck fehlerfrei, WLAN-Selbstheilung + Statistiken ok.

GitHub-Release **v2.4.24** mit dem getesteten Build (11.08. 10:59) veroeffentlicht
(Sammel-Release v2.4.21→v2.4.24; 2.4.22/23 waren Test-Builds). /releases/latest liefert jetzt
v2.4.24 — Flotte updatet ab jetzt. Dashboard-Ankuendigung #70 (high, 30 Tage): WLAN-
Selbstheilung + stumme-Boxen-USB-Hinweis + Ruecklaeufer-Bilder-Regel. Uebergangsregel bleibt:
Boxen <=2.4.21 verlieren beim Update noch keine Bilder (BILDER-Fix ist ab 2.4.19 drin), aber
Boxen <=2.4.14 loeschen noch mit altem BAT -> vor Update Bilder sichern, bis Flotte durch ist.

---

## 2026-08-11 (nachmittags) — Kamera-Wächter-Crash + Admin-Tab + Ladebalken (2.4.24)

**Nachtest-Log 2.4.23** (`fexobooth_20260811_104550.log`): WLAN-Selbstheilung erneut perfekt
(Setup-Log), Statistiken/BILDER/Session ok. Drei Befunde:

1. **KRITISCH — `_camera_status_probe` Crash:** `RuntimeError: main thread is not in main loop`
   (Thread `camera-check`, 10:45:58). Der Probe-Thread rief `root.after()` VOR Mainloop-Start
   auf → Thread starb → `_on_camera_status_result` (reschedule + Flag-Reset) lief nie → die
   periodische Kamera-Prüfung war DAUERHAFT tot. Kaltstart-Enum (cam-autoselect, unter 99% CPU
   + CompatTelRunner) timeoutete → Index -1 → Box blieb kameralos bis manueller Admin-Eingriff.
   **Fix:** `_check_camera_status` spawnt den Thread erst wenn `_mainloop_started`; die
   Ergebnis-Zustellung `root.after(0,…)` ist mit Retry/try-except gegen die RuntimeError
   abgesichert (Flag-Reset im Fehlerfall, damit die Prüfung nie hängen bleibt).
2. **Admin-Kamera-Tab fror weiter ~9s ein** (`UI-HITCH ~9597ms`, `~8625ms`): 2.4.23 hatte nur
   `_refresh_cameras` (Button) entkoppelt, aber `_create_camera_tab` rief `_get_available_cameras()`
   bei Tab-Erstellung synchron. **Fix:** Dropdown startet mit „Suche Kameras…", `_refresh_cameras`
   (Hintergrund + Cache) füllt es; neue `_select_current_camera()` markiert den aktiven Index.
3. **Ladebalken bewegt sich erst spät:** Haupt-Thread beim Boot in ~1s-Blöcken blockiert (v.a.
   Flask-Server-Start), jede Tk-Animation friert mit ein. **Fix:** Startup-Balken monoton (statt
   Ping-Pong) + Extra-Pumps um `show_screen("start")`; `_init_gallery_server`-Delay 4s→7s, damit
   der blockierende Server-Start hinter dem Ladescreen liegt statt mittendrin.

Kompiliert. `cam-autoselect` (2.4.23) berührt kein Tk → unproblematisch.

---

## 2026-08-11 (mittags) — Kamera-Suche entkoppelt + Ladebalken-Fix (2.4.23)

**Nachtest-Log 2.4.22** (`fexobooth_20260811_101834.log`) ausgewertet: WLAN-Selbstheilung
perfekt (Setup-Log: 4 Alt-Profile entfernt, in 3s verbunden), Statistiken/BILDER/USB/Session
alles sauber. **3 Befunde, eine Wurzel:** Die Webcam-Enumeration (PowerShell C#-Add-Type +
cv2-Öffnungsversuche, ~8-16s) lief auf dem UI-/Startup-Thread:
1. Kaltstart unter 98% CPU → Enumeration-Timeout → Box kurz „ohne Kamera" (fing sich via
   Hintergrund-`_check_camera_status` aus 2.4.17 nach ~1min selbst — daher „dann ging es").
2. Admin „Kamera"-Tab: 5x hintereinander `UI-HITCH ~8200ms` (bei jedem Enumerieren) →
   „Admin-Menü träge" (war vorher schon so, jetzt via Hitch-Log bewiesen).
3. Willkommens-Ladebalken bewegte sich kaum: CTk-`indeterminate` animiert nur bei freier
   Mainloop; beim Booten blockiert → fror ein.

**Fixes:**
- `app.py __init__`: Webcam-Auto-Auswahl in Daemon-Thread (`cam-autoselect`) statt 16s-Block.
- `admin.py _refresh_cameras`: Enumeration in Daemon-Thread (`admin-cam-scan`), „Suche
  Kameras…"-Platzhalter, Ergebnis-Cache `_camera_list_cache` (Cache-Reset bei Typ-Wechsel);
  `_get_available_cameras(camera_type)` bekommt den Typ übergeben (kein Tk-Zugriff im Thread).
- Ladebalken: beide Screens auf determinate + eigene Ping-Pong-Animation. `start.py` per
  `after(90ms)`-Schleife (`_animate_loading_bar`, sauber in `_hide_loading_overlay` gestoppt),
  `app.py`-Startup-Screen schrittweise in `_pump_startup_loading_screen`.

Kompiliert; reine UI-/Threading-Verbesserung, WLAN-/Statistik-Stand von 2.4.22 unberührt.

---

## 2026-08-11 (nachmittags)

### Firmen-WLAN-Selbstheilung gebaut — 47 stumme Boxen (Version 2.4.22)

**Befund:** Dashboard zeigt 231x 2.4.14 (melden = WLAN ok, updaten beim naechsten
Werkstatt-Start), aber **47x "Ohne Meldung"** = WLAN-Anmeldung klemmt → kein Heartbeat,
kein OTA (Teufelskreis). Mitarbeiter-Skripte analysiert (hotspot-on.ps1, Profil-XML,
2 BATs): Kern-Fix = sauberes Profil mit Auto-Verbinden AN + **MAC-Randomisierung AUS**;
Schwaeche = exportiertes Passwort ist DPAPI-maschinengebunden (wirkt nur auf identischen
Klon-Images — erklaert die Teil-Erfolge). Passwort von Christian erhalten.

**Umsetzung (3 Ebenen + Werkzeug):**
1. `src/utils/company_wlan.py`: Profil-Erzeugung mit key=clear (Template 1:1 wie die
   funktionierende Mitarbeiter-XML inkl. SSID-Hex), `self_heal_company_wlan()` mit sicherem
   Ausloeser "SSID sichtbar aber nicht verbunden" (sprachunabhaengiges netsh-Parsing:
   SSID-Zeile in `show interfaces` erscheint nur bei bestehender Verbindung);
   user=all mit Fallback user=current; `radical_network_reset()` legt nach dem
   Profile-Loeschen SOFORT das Firmenprofil neu an (Lesson: Hotspot braucht >=1 Profil).
2. App-Start: Selbstheilung im company_network-Worker VOR dem Firmen-WLAN-Check
   (heilt auch OTA-aktualisierte Boxen); zusaetzlich Schnellhilfe-Schritt 5 "Firmen-WLAN".
3. Installer: `setup/company_wlan_setup.ps1` als Pflicht-[Run]-Schritt (still, elevated,
   kein Neustart noetig, Log company_wlan_setup.log); Hotspot-Postinstall-Haken jetzt
   standardmaessig AN (war `unchecked` — erklaert nie eingerichtete Boxen!).
4. 3198-Menue (Tab Allgemein): "WLAN-Radikal-Reparatur" mit Zwei-Klick-Bestaetigung
   (10s-Entschaerfung), Worker-Thread, danach Auto-Neustart. Plus
   `setup/werkstatt_netzwerk_reset.bat` (mit optionalem Umbenennen) fuer App-tote Boxen.

`src.utils.company_wlan` in fexobooth.spec hiddenimports. Read-only-Tests auf Dev-PC
bestanden (XML valide, Hex identisch zur Mitarbeiter-XML). Passwort liegt bewusst im
privaten Repo (Modul + Setup-Skript, 2 Stellen) — Entscheidung Christian.

---

## 2026-08-11

### Release v2.4.21 veroeffentlicht - Flotten-Rollout gestartet

End-zu-End-Test bestanden (Log 085732 + DB-Gegenprobe): 10 Event-Statistiken der Test-Box
korrekt im Dashboard an den Buchungen (booth_event_stats), Bilder in C:/FexoBooth/BILDER,
Version 2.4.21 gemeldet. Windows-Update-Lockdown-Log geprueft: Skript (setup/
disable_windows_update.ps1) wirkt seit 16.06. bei jedem Boot; die 2 WARNs (WaaSMedicSvc/
DoSvc sc.exe Exit 5) sind bekannt-harmlos, Fallback greift.

GitHub-Release v2.4.21 mit dem getesteten Build (11.08. 08:51) veroeffentlicht;
Draft v2.4.20 + Tag geloescht. /releases/latest liefert v2.4.21 - Flotte updatet ab jetzt
(Boxen <=2.4.14 noch still mit altem BAT -> Werkstatt-Regel aus Ankuendigung #68 gilt:
Ruecklaeufer-Bilder sichern BEVOR die Box ins Firmen-WLAN kommt, bis die Flotte durch ist).
Ankuendigung #68 auf "Ab sofort verteilt sich 2.4.21" aktualisiert.

---

## 2026-08-07

### Event-Statistiken automatisch ans Dashboard + Release pausiert (2.4.21)

**Christian-Wunsch:** Statistik einer Buchung ins Dashboard übertragen — per Button oder
automatisch bei Alarm-Boxen. **Umgesetzt als einfachere Automatik:** Der bestehende
Monitoring-Heartbeat sendet IMMER die letzten Events mit (`event_stats`, max. 10, nur mit
Buchungsnummer; neue Methode `StatisticsManager.get_events_for_reporting()` merged das
laufende Event ohne Duplikat — headless getestet). Kein Box-Button, keine Alarm-Abfrage
nötig: Das Dashboard weiß selbst, welche Buchung einen Alarm hat.

**Dashboard-Seite (adminFexobox, Commit 43078492, Auto-Deploy):** Tabelle `booth_event_stats`
(Unique box_id+booking_id+start_time, Upsert), `BoothHeartbeatController` validiert/persistiert
`event_stats`, Kachel „Box-Statistik (vom Gerät gemeldet)" auf BEIDEN Detailseiten
(Standard + NX, Partial `appointments/partials/booth_event_stats.blade.php`).

**Release-Steuerung:** v2.4.20 auf Christians Wunsch VOR Verteilung pausiert
(`gh release edit --draft` → `/releases/latest` liefert wieder v2.4.14, Flotte bleibt still);
Dashboard-Ankündigung #68 auf „in Kürze" umformuliert. Rollout dann mit v2.4.21.

---

### Release v2.4.20 veröffentlicht + Dashboard-Ankündigung (2026-08-07, ~12:10)

GitHub-Release **v2.4.20** erstellt (Tag + `fexobooth.zip` aus Christians lokalem Build 11:52,
enthält den Exit-Fix von 11:49). Release-Notes decken den Sammelstand v2.4.15→v2.4.20 ab;
die `### Highlights`-Bullets erscheinen im Update-Bestätigungsdialog der Boxen — erste Zeile
ist die Bilder-Warnung. **Ab jetzt gilt:** Flotten-Boxen (≤2.4.14) updaten sich beim ersten
Start im Firmen-WLAN noch STILL mit dem alten BAT → Bilder werden dabei gelöscht. Werkstatt-
Anweisung (Dashboard-Ankündigung #68, Priorität high, 30 Tage): Rückläufer-Bilder IMMER
sichern, BEVOR die Box ins Firmen-WLAN kommt. Ab 2.4.20 fragt jede Box vor dem Update.

---

### Nachtest 2.4.19 + Exit-Crash-Fix (Version 2.4.20)

**Nachtest 2.4.19** (`fexobooth_20260807_113438.log`): BILDER-Migration verschob **583 Dateien**
nach `C:\FexoBooth\BILDER` ✓, Speicherpfad korrekt ✓, System-Test-Messwerte sauber
(disk 54,7 MB/s, 20,9 GB frei, Kamera 34,3 fps, Render 0,9 s, Druck-Übergabe 0,8 s) inkl.
korrekt gemeldeter Auffälligkeit „DRUCKER AUS!" ✓, Schnellhilfe alle 5 Schritte ok ✓.

**Ein Fehler:** Beim Beenden erschien ein PyInstaller-Fehlerdialog — der harte Exit (2.4.18)
rief `logging.shutdown()` ungeschützt auf; im Fenster-Build wirft colorama beim Flush des
nicht vorhandenen Konsolen-Streams `AttributeError: 'NoneType' … 'flush'`. Fix: try/except
um `logging.shutdown()` (exakt wie im OTA-Pfad `_quit_for_update`, der das schon abfing).

---

### KRITISCH: OTA-Update löschte alle Fotos → Root-Cause-Fix + Update-Bestätigung (2.4.19)

**Anlass:** Christian: „Bei zurückkommenden Boxen müssen erst die Bilder gezogen werden —
nach dem Auto-Update sind auf einmal alle Bilder weg. Updates sollen erst bestätigt werden."

**Root-Cause gefunden:** `src/storage/local.py` löste `BASE_PATH` relativ zu `__file__` auf —
im PyInstaller-Build zeigt das nach `_internal` → `IMAGES_PATH = C:\FexoBooth\_internal\BILDER`
(bestätigt durch Log „Speicherpfade initialisiert: …\_internal\BILDER"). Das Update-BAT
ersetzt `_internal` atomar (move → xcopy → rmdir `_internal_OLD`); der dokumentierte
„BILDER/-Schutz" galt nur für den Install-Root, wo keine Bilder lagen. **Jedes OTA-Update
löschte sämtliche Fotos.**

**Dreifacher Fix:**
1. `_resolve_images_base()`: BILDER liegt im Build jetzt neben der EXE (`C:\FexoBooth\BILDER`,
   Muster von `config.py`); Dev-Mode unverändert Repo-Root. Einmal-Migration
   `_migrate_legacy_internal_images()` beim LocalStorage-Init verschiebt Bestandsbilder
   (merge, best-effort, Log `BILDER-Migration: N Dateien`). Headless getestet ✓.
2. Update-BAT (`create_update_script`): Sicherheitsnetz rettet `_internal_OLD\BILDER` →
   Root-`BILDER` vor dem Löschen. **Merke (Bootstrap-Lektion):** greift erst bei Updates,
   die VON 2.4.19+ ausgehen — beim Update AUF 2.4.19 läuft noch das alte BAT!
3. **Update-Bestätigung** (`update_progress.py`): neue Phase vor dem Download —
   „Update verfügbar — jetzt installieren?" mit Bilder-Warnhinweis, Buttons „Jetzt
   installieren"/„Später", 5-Minuten-Timeout ohne Antwort = KEIN Update (nächster Start fragt
   erneut). `_silent_fallback` (company_network.py) installiert nicht mehr, loggt nur noch
   (Bestätigungspflicht). Alle Alt-Pfade kompilieren; Migrationslogik per Skript verifiziert.

---

### System-Test → echter Selbsttest mit Messwerten (Version 2.4.19)

**Anlass:** Christian: „Das ist kein richtiger Test — Template wird befüllt und gedruckt,
deckt nichts auf." Freigabe für das Mess-Konzept direkt erteilt.

**Umbau (`src/ui/dialogs/system_test.py`):** 6 statt 5 Schritte, alle gemessen:
1. **System prüfen** (neu, wirft nie): Speicherplatz App-Laufwerk, 8-MB-Schreibtest mit
   `os.fsync` (echtes Platten-Tempo, eMMC-Frühwarnung), `psutil.cpu_percent` Fremdlast,
   `snapshot_system_load("System-Test")` für Störer-Namen im Log.
2. **Kamera prüfen:** `initialize()` gestoppt + 15 frische `get_frame(use_cache=False)` →
   fps. Schwellen: Webcam 12 fps (YUY2-Fallback-Detektor bei 1080p), DSLR 5 fps, Init 5 s.
3. Fotos (wie bisher, plus Latenz erstes Foto als Messwert).
4. Render gestoppt (Schwelle 4,5 s).
5. Druck: vorab `get_printer_controller().get_error()` als Warnung, GDI-Übergabe gestoppt
   (Schwelle 10 s).
6. Aufräumen (unverändert).
Warnungen (`_warn`) brechen NICHT ab — Ergebnis dreistufig grün/orange/rot; Messwerte als
eine Zeile `SYSTEMTEST-MESSWERTE: …`, Auffälligkeiten als `SYSTEMTEST-AUFFÄLLIG: …`.
Schwellwerte als Modul-Konstanten mit Kalibrier-Kommentaren (Miix-Logs 2026-08).
Timeout 90 → 120 s. Headless-Test des System-Check-Schritts auf Dev-PC bestanden.

---

### Schnellhilfe-Button (Kunden-Menü 2015) + Exit-Bug behoben (Version 2.4.18)

**Nachtest 2.4.17** (`fexobooth_20260807_104712.log`): Prozess-Priorität greift ✓,
Kamera-Check-Freezes weg ✓ (nur noch moderate Hitches 250–1400 ms bei Screen-Wechseln/Filter).
**Leistungsregler-Rätsel gelöst:** Die Box läuft auf einem benutzerdefinierten Energiesparplan
(GUID d1de12ad-…, nicht „Ausbalanciert") — auf dem existiert der Schieberegler im Akku-Flyout
gar nicht, deshalb sah Christian ihn nicht. Das Overlay wird trotzdem gesetzt und wurde
VERIFIZIERT — Box läuft auf voller Leistung, kein Handlungsbedarf.

**Exit-Bug behoben:** Beenden über das 3198-Menü ließ die EXE mit 0 % CPU weiterlaufen
(non-daemon Galerie-/Hotspot-Threads überleben das Ende der Tk-Hauptschleife) → Installer
meldete „Anwendung läuft noch". Fix: `main.py` beendet nach „FEXOBOOTH BEENDET" hart mit
`logging.shutdown()` + `os._exit(0)` (Muster vom App-OTA `_hard_exit_for_update`).

**Neu: „🔧 Schnellhilfe" im Kunden-Menü PIN 2015** (`_customer_quick_fix` in admin.py):
Hotline-tauglicher Ein-Knopf-Reparaturlauf, Schritte je einzeln best-effort + geloggt
(`SCHNELLHILFE:`): (1) `snapshot_system_load("Schnellhilfe")` → Diagnose ins Log,
(2) Priorität + Leistungsregler neu setzen, (3) `%TEMP%\fexobooth_template_*` älter 24 h
löschen (aktueller Ordner ist vom laufenden App-Start und bleibt), (4) Spooler stop/start
(wie „Druckstau beheben"), (5) `camera_manager.release()` (Kundenmenü = idle, nächste Session
initialisiert frisch). Abschluss-Dialog mit „Neustart" (shutdown /r /f /t 5) + „Schließen".
i18n: `service.quick_fix`, `_title`, `_running`, `_done` in allen 7 Sprachen; Dialog-Buttons
nutzen bestehende Keys. Felix-Runbook (Service-Menü-Block, Wann-anbieten-Tabelle,
Schritt-für-Schritt) + Übersetzungs-Inventar (fexobox-next, Abschnitte 0.000/3.4 L) gepflegt.

---

### Nachtest 2.4.16 ausgewertet → drei neue Bremsen gefixt + Auslöse-Screen entfernt (2.4.17)

**Nachtest-Ergebnis 2.4.16** (`fexobooth_20260807_101128.log`, Miix, Webcam):
LiveView-Worker greift — **8,1–8,6 fps** (vorher 2,5–5), Aufbereitung 85–90 ms komplett im
Worker, Overlay nur noch **11–17 ms** (vorher 40–58), Anzeige im UI-Thread **56 ms** avg bei
adaptivem UI-Takt ~165 ms. Session-Hitches drastisch reduziert. ABER drei neue Funde:

1. **Kamera-Check = UI-Killer:** `_check_camera_status` lief auf dem UI-Thread. Ohne
   konfigurierte Kamera (Box bootet, USB-Hub braucht Zeit): volle `list_cameras()` mit
   PowerShell-Enumeration, die auf der Box in **Timeouts** lief → UI-Freezes **16,5 s / 15,7 s /
   8,4 s** beim Start. Mit Kamera: `cv2.VideoCapture`-Testöffnung alle 15 s → die ~500-ms-Hitches
   im 15,6-s-Takt im Leerlauf. **Fix:** Probe in Hintergrund-Thread (`_camera_status_probe` +
   `_on_camera_status_result`), nur auf Start-Screen + Kamera nicht initialisiert (keine
   EDSDK-/DirectShow-Kollision mit Session-Start), nur eine Prüfung gleichzeitig. Blink-Takt
   folgt jetzt der Probe-Dauer. Hinweis: Die einmalige Auto-Auswahl beim App-Start (Ladescreen)
   bleibt synchron — dort zeigt die Box eine Lade-Anzeige.
2. **Prozess-Priorität griff nicht** (`SetPriorityClass=0`): ctypes + GetCurrentProcess-
   Pseudo-Handle (-1) scheitert; jetzt `psutil.Process().nice(ABOVE_NORMAL_PRIORITY_CLASS)` —
   lokal verifiziert (nice=32768).
3. **Leistungsregler:** API meldete Erfolg, Regler stand laut Christian trotzdem nicht auf max.
   Jetzt: aktiven Basis-Plan loggen (Overlays wirken NUR auf „Ausbalanciert"!), nach dem Setzen
   per `PowerGetEffectiveOverlayScheme` zurücklesen → Log sagt „VERIFIZIERT" oder warnt mit dem
   tatsächlichen Zustand. Nächstes Box-Log zeigt damit die Ursache.

**Auslöse-Screen + Ladetext entfernt (Wunsch Christian):** `foto-screen.jpeg`-Vollbild und
„Foto wird aufgenommen…"-Balken waren Überbrückung für die früher lange Umschaltzeit — jetzt
Geflacker. Neu: Countdown → weißer Kurz-Blitz (bleibt) → letztes LiveView-Bild steht → Foto.
Entfernt: `show_flash`/`_display_flash`/`_build_flash_cache`/`_show_capture_loading` (session.py),
Admin-Controls „Bild beim Foto-Auslösen" + „Auslöse-Bild"-Regler (admin.py). Config-Keys bleiben
ignoriert bestehen. Hinweis für später: Bei Nikon dauert das Capture ~3,7 s — falls Gäste dort
Feedback vermissen, gezielt NUR für DSLR einen dezenten Hinweis wieder einbauen.

---

### LiveView-Performance: Bildaufbereitung raus aus dem UI-Thread (Version 2.4.16)

**Anlass:** Einzelne Miix-Boxen laufen „übel langsam" bis „hängt". Stresstest-Log
`fexobooth_20260806_142249.log` ausgewertet: LiveView 2,5–5 fps statt Ziel 20; pro Frame
Kamera nur 1–4 ms, aber Aufbereitung+Anzeige 140–175 ms (davon Overlay 40–58 ms) — **alles im
Tk-UI-Thread**. Dazu >140 UI-Hitches (200–2700 ms) in 16 Minuten. Grundlast am Anschlag +
Windows-Hintergrundlast (Defender/Update) = gefühlter Hänger. Keine Verschlechterung über die
Zeit, kein Speicherleck, kein Absturz im Log.

**Umbau (Christian hat P1/P3/P4/P5 freigegeben, P2 „Kamera dauerhaft 1080p" bewusst verworfen):**

1. **LiveView-Worker-Thread** (`session.py`): kompletter Aufbereitungspfad (get_frame, Spiegeln,
   Overlay, Countdown, Skalieren) im Daemon-Thread; `self._lv_latest` hält nur den neuesten
   fertigen Frame (kein Rückstau). UI-Takt zeigt fertige Bilder nur noch an. Frames werden auf
   exakt `round(logisch*scaling)` vorskaliert → CTkImage trifft den PIL-Copy-Fastpath (PIL
   `resize()` mit identischer Größe = `copy()`, verifiziert). `winfo_*` bleibt im UI-Thread
   (Worker bekommt Zielgröße über `self._lv_target`). Neuer `_cam_access_lock` serialisiert
   LiveView-Reads gegen High-Res-Capture/Preview-Restore (zusätzlich zu den bestehenden Flags).
2. **Overlay-Schnellpfad:** `_get_overlay_static_composite()` (Basis-Canvas + Overlay einmal pro
   Foto-Wechsel) + `_get_overlay_box_crop()` (Overlay-Ausschnitt pro Box, einmal geschnitten);
   pro Frame nur noch: Box füllen (Cover-Fit per `cv2.resize`) + kleinen Ausschnitt compositen.
   Headless-Äquivalenztest: außerhalb der Box pixelidentisch, innerhalb mittlere Diff 0,03
   (Bilinear-Implementierung cv2 vs. PIL). Benchmark Dev-PC: 20,1 → 14,0 ms/Frame (1,4×),
   der eigentliche Gewinn ist aber die Verlagerung aus dem UI-Thread.
3. **Adaptive Taktung:** Worker pausiert nach jedem Frame mind. ~35 % der Frame-Zeit (CPU nie
   sättigen); UI-Anzeige-Takt = max(Config-Takt, 3× gemessene Anzeige-Kosten, gedeckelt 250 ms).
4. **Windows-Leistung** (`src/utils/system_load.py`, neu; in `app.py.__init__` verdrahtet):
   Prozess-Priorität ABOVE_NORMAL + Leistungsregler „Beste Leistung" per
   `PowerSetActiveOverlayScheme` (kein Admin nötig, Windows merkt sich das pro Stromquelle).
5. **Systemlast-Diagnose (Dev-Mode):** `SYSTEM-LAST:`-Logzeile beim App-Start und bei
   UI-Hitches > 1 s (max. 1×/Minute, im Hintergrund-Thread): CPU/RAM, Top-3-Prozesse, benannte
   Störer (MsMpEng=Defender-Scan, TiWorker=Update-Installer, SearchIndexer, …).

**Log-Format geändert:** `LIVEVIEW-PERF`-Aufbereitungszeile kommt jetzt aus dem Worker
(`[Worker-Thread]`-Suffix, Feld heißt `Aufbereitung` statt `Aufbereitung+Anzeige`); neue Zeile
`LIVEVIEW-PERF: Anzeige (UI-Thread): …` zeigt die verbleibenden UI-Kosten. Erwartung Nachtest:
Anzeige-avg deutlich unter ~40 ms, UI-Hitches drastisch reduziert, fps-Anstieg.

**Ergänzend:** `src.utils.system_load` in `fexobooth.spec` hiddenimports aufgenommen (gleiche
Falle wie damals `src.camera.nikon`). Test-Skript (headless, ohne Tk):
Scratchpad `test_liveview_pipeline.py` — 4/4 Tests bestanden.

---

## 2026-08-06

### Drucker-Fehlerfenster: Service-Ausstieg per PIN (Bug-Report #49 Werkstatt, Version 2.4.15)

**Problem:** Hängt ein Druckjob, ohne dass der SELPHY selbst einen Fehler meldet, blieb das
blockierende Fehler-Overlay endlos stehen — der „Problem behoben"-Check schlug immer wieder fehl,
und der einzige Ausweg (Strg+Shift+Q) braucht eine Tastatur, die am Tablet fehlt. Werkstatt/Kunden
mussten die Box hart ausschalten (Fall NX-138947).

**Lösung:**
- [printer_error.py](src/ui/dialogs/printer_error.py): Unauffälliges ✕ oben rechts im Overlay →
  Touch-Numpad-PIN-Karte. Gültige PINs: Service (6588), Admin (config `admin_pin`), Kundenmenü (2015,
  damit die Hotline telefonisch helfen kann). Bei korrekter PIN wird das Overlay OHNE Drucker-Check
  geschlossen.
- [app.py](src/app.py): Neues `snooze_printer_overlay(600)` — nach dem PIN-Schließen öffnet der
  Sekunden-Poll das Overlay 10 Minuten lang nicht erneut (sonst wäre es sofort wieder da). Die rote
  Top-Bar-Warnung läuft unverändert weiter, der Fehler wird also nicht versteckt.
- [i18n.py](src/i18n.py): Neue Keys `printer.service_pin_title` / `printer.service_pin_wrong` in
  allen 7 Sprachen.
- [HOTLINE_PROMPT_FELIX.md](support/HOTLINE_PROMPT_FELIX.md): Neues Runbook „Großes Fehlerfenster
  lässt sich nicht schließen" (ab 2.4.15) inkl. Fallback für ältere Versionen.

**Getestet (Dev-Smoke-Test):** Overlay öffnet mit ✕; falsche PIN → bleibt offen; PIN 6588/3198
schließt + setzt 600 s Snooze; Klassifizierung (consumable/jam/other) unverändert.

## 2026-07-03

### Kunden-Menü PIN 2015: „Neustart / Ausschalten" mit Rückfrage (Kundenwunsch Christian)

**Wunsch:** Bisher konnte man im 2015er-Menü nur Windows neu starten. Der Kunde soll die Box am
Event-Ende auch **sauber herunterfahren** können — über **denselben** Button (kein zusätzlicher).

**Umsetzung:**
- **[src/ui/screens/admin.py](src/ui/screens/admin.py):** Button „Windows Neustart" → „Neustart /
  Ausschalten"; `_customer_restart` → `_customer_power_options`. Der Bestätigungsdialog zeigt jetzt
  **drei** Buttons: Neustart (`shutdown /r`), Ausschalten (`shutdown /s`, rot), Abbrechen. Gemeinsame
  `do_power(action)`-Funktion mit passendem Wartehinweis je Aktion.
- **[src/i18n.py](src/i18n.py):** `service.restart_windows/_title/_hint` → `service.power_options/
  _title/_hint`; neu `service.shutdown_confirm` + `service.shutdown_running`; `restart_confirm/
  _running` + `abort` bleiben. Alle **7 Sprachen** gepflegt (de-AT erbt de-DE per Fallback — mit
  `t()` verifiziert). Übersetzungs-Inventar (`../fexobox-next/docs/MULTILINGUAL-...md`) aktualisiert.
- **[support/HOTLINE_PROMPT_FELIX.md](support/HOTLINE_PROMPT_FELIX.md):** Alle „Windows Neustart"-
  Stellen auf „Neustart / Ausschalten" + Rückfrage-Hinweis umgestellt (Pflicht bei 2015er-Änderung).

**Checks:** `py_compile` OK; i18n-Key-Parität + `t()`-Fallback für alle 7 Sprachen geprüft; keine
verwaisten Alt-Keys mehr im Code. Geht in denselben Build-Kandidaten (2.4.14) wie Thumbnail-Cache
+ MJPG-Fix.

### Thumbnail-Cache `BILDER/.thumbs/` gebaut (Etappe 2 App-Plan „Offline-Galerie + Cloud-Relay")

> Detailplan: [../fexobox-app/docs/PLAN-OFFLINE-GALERIE-CLOUD-RELAY.md](../fexobox-app/docs/PLAN-OFFLINE-GALERIE-CLOUD-RELAY.md) §5.
> Commit betrifft NUR `src/gallery/server.py` + `src/storage/local.py` (bewusst getrennt von der
> parallel laufenden 2.4.14-Performance-Arbeit).

- **Gemeinsamer Kern `_serve_thumbnail()`** in `server.py`: Erster Abruf rechnet das Thumbnail wie
  bisher (Pillow LANCZOS, JPEG q80) und legt es unter `BILDER/.thumbs/{Folder}/{filename}` ab;
  jeder weitere Abruf liefert die Datei direkt per `send_file` — **keine Pillow-Arbeit mehr pro
  Abruf**. Beide Routen (`/thumb/...` Web-Galerie und `/api/v1/thumb/...` App) nutzen DENSELBEN Cache.
- **Invalidierung:** Ist die Quelle neuer als die Cache-Datei (Foto ersetzt), wird neu gerechnet.
- **Robustheit:** Cache-Schreiben ist best-effort und atomar (zufälliger tmp-Name + `os.replace`) —
  parallele Anfragen kollidieren nicht, eine halbe Datei wird nie ausgeliefert, Schreibfehler
  (z. B. Handle-Lock unter Windows) stören die Antwort nicht (Dev-Log `Thumb-Cache HIT/MISS/…`).
- **Lebenszyklus:** `delete_all_images()` (Event-Wechsel, [local.py](src/storage/local.py)) löscht
  `.thumbs` mit. `_collect_photos` listet nur `Prints`/`Single` → der Cache taucht nie in der
  Galerie/App-Liste auf.
- **Verifiziert (automatisierter Test, Flask-Testclient):** ① Erst-Abruf 200 + Cache-Datei angelegt,
  ② API-Route liefert aus demselben Cache, ③ Quelle ersetzt → neu gerechnet + Cache erneuert,
  ④ Feature-Gate 403 unverändert, ⑤ Event-Reset löscht Bilder UND `.thumbs`. Zusätzlich
  `py_compile` beider Dateien sauber.
- **Test-Checkliste für den nächsten Build-Kandidaten** (sobald die parallele 2.4.14-Arbeit
  committet ist): siehe TODO.md-Abschnitt bzw. Übergabe an Christian.

### 2.4.13-Webcam-Log ausgewertet: 3 von 4 Fixes greifen, MJPG-Fix korrigiert → Build 2.4.14

**Log `fexobooth_20260703_085633.log` (Webcam-Box, 5 Sessions, 18 Captures, 0 Fehler):**
- ✅ **Final-Screen-Hänger weg:** `Final-Rendern (Hintergrund)` 1,0–2,7 s, KEIN ~3,3-s-UI-HITCH
  mehr am Final (größte Hänger jetzt: Startscreen-Template-Rebuild ~2,9 s zwischen Sessions
  und Kamera-Vorinit während des Videos — beide ohne Gast-Kontakt, bekannt).
- ✅ **Fotoanzeige-Cache perfekt:** Refreshes `avg=0ms` (49×/5 s aus dem Cache).
- ✅ **Kein Doppel-Rendern mehr:** jeder Filter exakt 1× pro Screen; Arbeitskopien 220–295 ms;
  alle Vorschauen in ~9 s vorgerendert („Filter-Vorschauen komplett vorgerendert").
- ✅ **Overlay-Frage beantwortet:** Overlay nur ~40–55 ms von ~160 ms Aufbereitung → das
  Box-Region-Composite lohnt kaum; der Rest ist der Tk-Anzeigepfad (~110 ms/Frame) — bewusst
  nicht angefasst (riskant, LiveView mit ~4,7 fps akzeptabel).
- ❌ **MJPG griff NICHT** (`fourcc=YUY2` überall) und machte die Umschaltung sogar langsamer
  (set 600 → ~1300 ms): Der Codec wurde VOR der Auflösung gesetzt, DirectShow verhandelte beim
  Auflösungs-Setzen zurück auf YUY2 — der nutzlose Versuch kostete ~600 ms pro Foto extra.

**Fix in 2.4.14 ([webcam.py](src/camera/webcam.py) `_apply_mjpg`):** Codec NACH der Auflösung
setzen + Ergebnis VERIFIZIEREN (Log: „Webcam-Codec: MJPG aktiv"), Fallback Codec-zuerst-Variante,
und bei endgültiger Ablehnung Latch `_mjpg_unsupported` → nie wieder Renegotiation-Kosten pro
Foto (Latch wird bei Kamera-Neuinitialisierung zurückgesetzt). Kein lokaler Webcam-Test möglich
(Work-PC ohne Kamera) → Verifikation über den nächsten Box-Log.

**Checks:** `py_compile` OK, Smoke-Test grün.

---

### Dauerlauf-Logs ausgewertet: Fixes bestätigt + 4 neue Befunde → Build 2.4.13

**Datenbasis:** Zwei Stresstests vom 2026-07-02 — `ready` (Nikon, 2¾ h, **647 Captures**,
140+ Sessions) und `selphy` (Webcam + USB-Template + SELPHY, **über Nacht 17 h, 2.356 Sessions,
0 Errors/Warnings in 212.000 Zeilen** — Stabilität exzellent, kein Leak, kein Crash).

**Bestätigt (2.4.12-Fixes wirken):**
- LiveView **konstant ~7,5 fps über 2¾ h** (vorher Einbruch 7,7→1,8) — Overlay-Basis-Cache ✓
- Fotoanzeige-Refresh **1× pro Foto ~160 ms** (vorher 10×/s à 380 ms) ✓
- **Bildgröße M aktiv**: alle 647 Captures 4496×3000; Capture-Worker 4,06 s → **3,65 s** ✓
- Filter-Vorschauen 0,35–2,2 s statt vieler Sekunden; Final-Rendern läuft im Worker ✓

**Neue Befunde → gefixt in 2.4.13:**
1. **Webcam bestätigt auf YUY2** (`fourcc=YUY2`): 1080p-Umschaltung set≈600 ms + read≈550–690 ms
   → [webcam.py](src/camera/webcam.py) fordert jetzt **MJPG** an (bei Init, High-Res-Wechsel,
   Preview-Restore); Kameras ohne MJPG ignorieren es einfach.
2. **UI stand ~3,3 s an JEDEM Final-Screen trotz Worker-Threads**: Filter+Rendern auf den
   13,5-MP-Originalen sättigt die 2 Atom-Kerne (GIL/CPU) → [final.py](src/ui/screens/final.py)
   verkleinert die Fotos vorm Filtern auf **2000 px lange Kante** (Template 1800×1200, Boxen
   ~900×600 → weiterhin >2× überabgetastet, Druckqualität identisch).
3. **Filter 'none' wurde pro Screen doppelt gerechnet** (Klick-Worker + Precache gleichzeitig,
   4.697 statt ~2.356 Renders) → In-Flight-Merkliste in [filter.py](src/ui/screens/filter.py);
   Precache macht zudem 150 ms Pause zwischen Filtern (2 Kerne atmen lassen).
4. Kosmetik: Kamera-PTP-String enthielt `\x00` („4496x3000\x00") → Bridge trimmt die Antwort.

**Zusätzliche Messung eingebaut:** `LIVEVIEW-PERF` weist jetzt den **Overlay-Anteil** separat aus
(`davon Overlay=#ms`) — im Selphy-Lauf kostete die Aufbereitung mit USB-Template 173 ms/Frame
(nur 4,5 fps) vs. 63 ms mit Default-Template; der nächste Log zeigt, ob das Alpha-Compositing
der Treiber ist (dann lohnt ein Box-Region-Composite statt Vollflächen-Composite).

**Bekannt, bewusst NICHT angefasst:** ~3 s Hänger beim tatsächlichen SELPHY-Druck (2× beobachtet,
Druckpfad ist live-flotten-kritisch → nicht vor dem Release umbauen); vereinzelte ~1,2 s
Bridge-Frame-Stalls alle ~60–75 s im Nikon-Lauf (selten, unkritisch); Startscreen-Neuaufbau
mit USB-Template ~5 s zwischen den Sessions (kein Gast-Kontakt).

**Checks:** `py_compile` OK, Bridge-Build 0 Fehler, Smoke-Test grün. → Build-Kandidat **2.4.13**.

---

## 2026-07-02

### 🎉 Nikon D3300 HARDWARE-VALIDIERT + Performance-Analyse ausgewertet → 4 Fixes (Build 2.4.12)

**Meilenstein:** Testlog `fexobooth_20260702_114253.log` (Fotobox, Build 2.4.11): Die Nikon D3300
läuft über die FexoNikonBridge — Warmup „bereit" in ~1,4 s, LiveView 640×424, **4 Captures in
voller 6000×4000-Auflösung**, kein sichtbares Fremdfenster. Variante 3 funktioniert.

**Performance-Analyse (die neue LIVEVIEW-PERF/UI-HITCH-Messung hat alle Bremsen exakt beziffert):**

| Befund | Messwert | Ursache |
|---|---|---|
| LiveView bricht mit jedem Foto ein | 7,7 → 3,5 → 2,4 → 1,8 fps (Aufbereitung 64→551 ms/Frame) | `_apply_template_overlay` skalierte die bereits aufgenommenen 6000×4000-Fotos **bei jedem Frame** neu (+~160 ms pro Foto pro Frame) |
| Dauer-UI-Blockade während Fotoanzeige | ~380 ms pro 100-ms-Tick, UI-HITCH ~280–450 ms im Halbsekundentakt über die ganze 60-s-Anzeige | Statisches 24-MP-Foto wurde 10×/s neu auf Bildschirmgröße skaliert |
| Filter-Klick „gefühlt ewig" | (nicht instrumentiert, jetzt mit Timing-Log) | Filter lief auf allen **Originalen** (4 × 24 MP = 96 MP pro Klick), erst danach Verkleinerung |
| Screenwechsel zu „final" friert ein | UI-HITCH **3347 ms** | Finales Rendern + Speichern liefen synchron im UI-Thread |
| Nikon-Capture | konstant ~4,1 s sichtbar | Kamera-seitig (AF + 24-MP-Transfer) — akzeptabel, Feintuning später (JPEG-Größe M / NoAf) |

**Fixes (alle in `2.4.12`):**
- **[session.py](src/ui/screens/session.py):** (F1) Fotoanzeige gecacht — statisches Foto wird pro
  Foto nur noch EINMAL skaliert (`_display_photo_cached`, Invalidierung bei neuem Capture).
  (F2) Overlay-**Basis-Canvas** gecacht — Fotos werden nur noch beim Foto-Wechsel in ihre Boxen
  skaliert, pro Frame bleiben Kopie + LiveView-Paste + Composite.
- **[filter.py](src/ui/screens/filter.py):** (F3) Alle Vorschauen rechnen auf ~1000-px-**Arbeitskopien**
  (einmal erstellt) statt auf den Originalen; zusätzlich werden **alle Filter sequentiell
  vorgerendert** (Precache im Hintergrund) → Antippen wechselt sofort. Timing-Logs neu
  (`Filter-Vorschau 'x' gerendert: …ms`). Druckbild rendert weiter aus den Originalen.
- **[final.py](src/ui/screens/final.py):** (F4) Rendern + Speichern im **Worker-Thread**; Screen
  erscheint sofort mit „Dein Bild wird erstellt..." (neuer i18n-Key `final.rendering`, alle
  7 Sprachen; Platzhalter entfernt auch das Bild der Vorsession), Druck-Button bis
  Fertigstellung gesperrt. Timing-Log `Final-Rendern (Hintergrund): …ms`.
- **[src/i18n.py](src/i18n.py):** `final.rendering` in DE/EN/FR/NL/IT/ES/PL; Übersetzungs-Inventar
  in `../fexobox-next/docs/MULTILINGUAL-UEBERSETZUNGS-PROMPT.md` (0.000 + 3.4 L) gepflegt.

**Erwartung für den Nachtest:** LiveView konstant ~7–8 fps über alle 4 Fotos (statt Einbruch auf
1,8), keine UI-HITCH-Serien während der Fotoanzeige, Filterwechsel < 1 s (nach Precache sofort),
Final-Screen ohne Einfrieren. **Verifiziert:** `py_compile` OK, Nikon-Smoke-Test 86/86 OK.

**Nachtrag (gleicher Tag, Kundenwünsche Christian):**
- Final-Screen-Text: „Dein Bild wird erstellt..." → **„Druckdatei wird erzeugt..."** (alle 7 Sprachen).
- **Auto-Zurück-Countdown startet erst ab fertigem Bild** (sichtbar + Druck-Button aktiv) —
  Start verlagert von `on_show` nach `_on_final_ready` (läuft auch im Fehlerfall an, damit die
  Box nie hängen bleibt); während des Erzeugens: volle Leiste, kein Zähltext.
- **Nikon-Bildgröße „M" statt 24 MP** (Christian: „M reicht auf jeden Fall"): neue Option
  `nikon_bridge.image_size` (Default `"M"`), die Bridge setzt beim `init` die Kamera-Property
  „Image Size" (PTP 0x5003, per `AdvancedProperties`/`SetValue` — API gegen die echten
  digiCamControl-Quellen verifiziert). Auswahl-Heuristik: Werte nach Breite sortiert,
  L=größte/M=zweitgrößte/S=kleinste → kameraunabhängig. D3300: 4496×3000 statt 6000×4000
  (~44 % weniger Pixel → spürbar kürzerer Transfer nach dem Auslösen). Best-effort: fehlt die
  Property, bleibt die Kamera unangetastet; das Log zeigt „Nikon Bildgröße gesetzt: …".
- Bridge neu gebaut (0 Fehler), Protokolltest OK, `py_compile` OK, Smoke-Test grün.

---

### Dev-Mode-Performance-Messung für den Miix-Analyse-Lauf eingebaut

**Ziel:** Vor dem 2.4.11-Release soll ein Dev-Log vom Lenovo-Tablet zeigen, wo die Zeit wirklich
hingeht (Webcam-Foto dauert zu lang; Gesamteindruck soll flüssiger werden).

**Bestandsaufnahme:** Die Webcam-Capture-Strecke ist bereits voll instrumentiert
(`High-Res Capture Timing: set/verify/grab/read/restore`, `Capture-Worker Timing`,
`Sichtbare Capture-Wartezeit`, `Preview-Restore Timing` — inkl. `fourcc`-Ausgabe).
Was fehlte: Messung der LiveView-Schleife und der UI-Thread-Hänger.

**Änderung (beides NUR im Developer Mode aktiv, Live-Betrieb 0 Overhead):**
- **[src/ui/screens/session.py](src/ui/screens/session.py):** `LIVEVIEW-PERF`-Summenzeile alle ~5 s
  (effektive fps vs. Ziel, avg/max ms pro Frame, getrennt Kamera-Read vs. Aufbereitung+Anzeige,
  übersprungene Frames) + Messung der Fotoanzeige-Refreshes (statisches Foto wird derzeit alle
  100 ms neu skaliert — Verdachtskandidat).
- **[src/app.py](src/app.py):** `UI-HITCH`-Monitor: after(200ms)-Herzschlag loggt, wenn der
  Tk-Hauptthread >200 ms blockiert war — die Zeitmarke zeigt, welche Aktion davor lief
  (Sekunden-Polls Drucker/USB/Kamera, Screen-Wechsel, synchrone Arbeit).

**Verdachtskandidaten aus dem Code (mit dem Log zu bestätigen):** Webcam-`fourcc` (YUY2 statt MJPG
macht 1080p-Umschaltung+Read langsam), Auflösungs-Umschaltung hinter Countdown/Blitz vorziehen,
Fotoanzeige-Refresh cachen, Countdown-Ziffern vorrendern (Font+8 Schatten pro Frame),
Sekunden-Polls auf dem UI-Thread.

---

### Nikon-Neustart: digiCamControl verworfen, eigene unsichtbare FexoNikonBridge (Build 2.4.11)

**Auslöser:** Testlog `D:\fexobooth_20260702_090008.log` (Build 2.4.10): Der automatisch gestartete
`CameraControl.exe` öffnet ein **sichtbares digiCamControl-Fenster** vor FexoBooth (Kiosk-No-Go,
verlangsamt den Start) und der Webserver `127.0.0.1:5513` antwortet **trotzdem nicht** — die
Webserver-Aktivierung ist eine persistente DCC-Einstellung, die die Standardinstallation nie setzt.
Der digiCamControl-App-Ansatz (Variante 2) ist damit **verworfen**.

**Recherche (Multi-Agent, 7 Themen, jede Kernaussage adversarial verifiziert, 2026-07-02):**
- Offizielles Nikon-SDK: **kein Modul für die gesamte D3xxx-Serie** → MAID/NikonCSWrapper unmöglich.
- Nikon Webcam Utility: D3300 gar nicht unterstützt (und nur 1024×768-Webcam, kein Capture).
- Camera Control Pro 2 / NX Tether: D3xxx nie unterstützt; CCP2 eingestellt, nur GUI.
- libgphoto2 auf Windows: Zadig/WinUSB-Treibertausch nötig (killt MTP, kein Hotplug) → nicht kiosk-tauglich.
- **dslrBooth unterstützt die D3300 inkl. LiveView** per direktem USB-PTP → eigener PTP-Stack ist der Weg.
- **CameraControl.Devices** (Kern von digiCamControl, **MIT-Lizenz**): D3300 explizit im Code gemappt
  (`"D3300"` → `NikonD600Base`), rohes PTP über die Windows-WPD-API, headless ohne GUI nutzbar.

**Änderung (Variante 3, Build-Kandidat `2.4.11`):**
- **NEU [bridge/FexoNikonBridge/](bridge/README.md):** eigener unsichtbarer C#-Hintergrundprozess
  (.NET Framework 4.8 = auf Win10/11 vorinstalliert, `CREATE_NO_WINDOW`), Motor `CameraControl.Devices`.
  Protokoll: JSON über stdin/stdout + längenpräfixierte JPEG-Binärdaten (keine Ports, keine
  Firewall-Dialoge). Kommandos: `ping/list/init/lv_start/frame/capture/lv_stop/release/quit`.
- **[src/camera/nikon.py](src/camera/nikon.py):** komplett neu als Bridge-Client (gleiches
  Drop-in-Interface wie Canon; `ensure_bridge_running()` für den Warmup; Developer-Diagnose
  loggt Bridge-Status + alle geprüften EXE-Pfade; kein `tasklist`, kein HTTP mehr).
- **[src/app.py](src/app.py):** Warmup startet jetzt die unsichtbare Bridge statt DCC;
  Top-Bar-Status `BRIDGE FEHLT!` (i18n-Key `topbar.camera_bridge_missing`, alle 8 Sprachen).
- **[src/config/defaults.py](src/config/defaults.py):** `nikon_digicamcontrol` → `nikon_bridge`
  (exe_path + Timeouts).
- **Rückbau:** digiCamControl-Download/-Einbettung aus [build_installer.bat](build_installer.bat),
  [installer.iss](installer.iss) und [.github/workflows/build-release.yml](.github/workflows/build-release.yml)
  entfernt. CI baut stattdessen die Bridge (`dotnet build`, `continue-on-error`) und legt sie unter
  `{app}\bridge\` bei; lokale Builds ohne .NET-SDK bauen weiter, nur ohne Nikon-Support.
- **[support/HOTLINE_PROMPT_FELIX.md](support/HOTLINE_PROMPT_FELIX.md):** `DCC FEHLT!` → `BRIDGE FEHLT!`.
- **[tools/nikon_smoke_test.py](tools/nikon_smoke_test.py):** komplett auf den Bridge-Vertrag umgestellt,
  prüft zusätzlich, dass der DCC-Ansatz restlos entfernt ist.

**Verifiziert (KEIN echtes Nikon-Gerät am Entwicklungsrechner):**
- Smoke-Test: 82/82 Checks OK; `py_compile` aller geänderten Dateien OK.
- End-to-End-Protokolltest gegen eine protokollgetreue Fake-Bridge: 11/11 OK
  (Spawn → ping → list → init → LiveView-Frame 640×424 → Vollbild-Capture 6000×4000 →
  release → Prozess-Stop).
- Ohne Bridge-EXE: sauberes `is_available()=False` / `list_cameras()=[]` / `initialize()=False`.

**Multi-Agent-Review (3 Linsen: Python-Client, C#-API-Abgleich gegen echte digiCamControl-Quellen,
Integration; jedes Finding adversarial verifiziert) — 15 bestätigte Findings, alle gefixt:**
- **(critical) Eingefrorener Cache-Frame als „Foto":** Stirbt Bridge/Kamera mitten in der Session, lieferte
  `get_frame` unbegrenzt den letzten Frame; der Capture-Fallback hätte ein Minuten altes Standbild gedruckt.
  → Stale-Grenze 1,5 s (`_recent_cached_frame`), danach `None`.
- **(critical) Kein Recovery nach Bridge-Tod:** `_is_initialized` blieb True, Bridge wurde nie neu gestartet,
  Status-Check schwieg. → `_handle_bridge_error()` in allen Request-Fehlerpfaden: setzt Status zurück,
  nächste Session re-initialisiert (startet die Bridge neu). Per Test verifiziert (Kill + Recovery).
- **(critical) x64/x86:** Die DLLs des 2018er-NuGet-Pakets sind 32-bit → `PlatformTarget` auf **x86**
  (sonst BadImageFormatException bei jedem Kamera-Aufruf).
- **(critical) OTA lieferte `bridge/` nie aus:** In-App-OTA (`src/updater.py`-BAT) und
  `update_from_github.bat` kopieren jetzt `bridge/` mit (inkl. `taskkill` gegen gelockte EXE).
  Achtung Selbst-Updater-Bootstrap: Das ERSTE Update auf 2.4.11 läuft noch mit dem alten BAT →
  für die Nikon-Testbox den **Installer** nutzen, nicht OTA.
- **(major)** UI-Hänger: `request()`-Timeout deckt jetzt auch das Lock-Warten ab; Warmup verbindet die
  Kamera zusätzlich vor (`init` im Hintergrund), damit die erste Session keinen Kamera-Connect auf dem
  UI-Thread abwartet. **(major)** Tablet-Webcam konnte als „Nikon" gebunden werden → `DetectWebcams=false`
  + gezielte Geräteauswahl. **(major)** `[STAThread]` + blockierendes ReadLine hätte WPD-COM-Events
  verhungern lassen → MTA. **(major)** Hot-Plug: `list` scannt jetzt gedrosselt (3 s) neu.
- **(minor)** AF-Fehlschlag im Dunkeln → `CapturePhotoNoAf`-Fallback; Reader-Queue fest an ihren
  Bridge-Prozess gebunden (kein EOF-Poisoning nach Neustart); CI-Gate: Run scheitert, wenn die Bridge
  fehlt (außer Input `allow_no_bridge=true`); Smoke-Test prüft jetzt auch beide OTA-Pfade.
- Widerlegt (kein Fix nötig): angebliches stdout-Fehlerbanner der Library.

**Verifiziert nach den Fixes:** Smoke-Test 86/86 OK; Fake-Bridge-E2E 19/19 OK (inkl. neuem
Crash-Szenario: Bridge-Kill → LiveView liefert `None` statt Standbild → `initialize()` startet
Bridge neu → LiveView+Capture wieder da); `py_compile` OK.

**Nachtrag (gleicher Tag): Bridge lokal gebaut + gegen echte EXE getestet.**
- .NET-SDK 8 auf dem Work-PC installiert; csproj um `Microsoft.NETFramework.ReferenceAssemblies`
  ergänzt → `dotnet build` funktioniert ohne Visual Studio. **Build: 0 Fehler.**
- Realtest deckte auf: Die Library schreibt Banner (`**CRITICAL ERROR** ... EDSDK.dll is missing`,
  Canon-Teil, für Nikon irrelevant) **auf stdout in den Protokollstrom** — das im Review widerlegte
  Finding war also doch real. Fix: `Console.SetOut(TextWriter.Null)` vor Library-Nutzung; unser
  Protokoll schreibt über den vorher gesicherten Raw-Handle. Ausgabe danach sauber.
- Echte-Bridge-Test 8/8 OK: EXE-Suchpfad, unsichtbarer Spawn, ping, `list` = `[]` ohne Kamera,
  `init` scheitert ohne Kamera sauber nach 15 s („Keine Nikon-Kamera gefunden"), sauberer Stop.

**Offen (Blocker):** Nur noch der Hardware-Test mit echter D3300 auf der Fotobox
(Installer `2.4.11` lokal bauen → USB → offline installieren; Checkliste in TODO.md).
Der CI-Build-Schritt ist damit optional (lokaler Build bewiesen), sollte beim nächsten Push
aber einmal mitlaufen.

---

### Nikon-Testlog 2.4.9 ausgewertet: DCC fehlt auf dem Tablet, Installer legt DCC jetzt bei (VERALTET — Ansatz verworfen, siehe oben)

**Log:** `D:\fexobooth_20260702_083043.log` vom Test-Tablet.

**Befund:** Der Diagnosebuild läuft korrekt und die App ist auf `camera_type=nikon` gestellt. Der Fehler
liegt weiterhin vor dem eigentlichen Nikon-/LiveView-/Capture-Zugriff:
- `/session.json` auf `http://127.0.0.1:5513` antwortet nicht.
- Alle geprüften `CameraControl.exe`-Pfade sind `FEHLT` (`Program Files`, `Program Files (x86)`,
  `%LOCALAPPDATA%`, `%APPDATA%`, `%ProgramData%`).
- Deshalb ist `DCC FEHLT!` in der oberen Leiste korrekt: digiCamControl ist auf dem Tablet nicht installiert
  bzw. nicht auffindbar.

**Zusatzbefund:** Das neue Diagnose-Logging selbst erzeugte bei `tasklist` auf dem deutschen Windows eine
`UnicodeDecodeError`-Thread-Exception. Das war Log-Rauschen, nicht die Nikon-Ursache.

**Änderung:**
- **[src/camera/nikon.py](src/camera/nikon.py):** `tasklist` wird nicht mehr mit `text=True` gelesen, sondern
  als Bytes und robust mit `errors="replace"` decodiert.
- **[src/__init__.py](src/__init__.py):** Testbuild auf `2.4.10` angehoben.
- **[build_installer.bat](build_installer.bat) + [installer.iss](installer.iss):** Lokale Builds laden den
  offiziellen stabilen digiCamControl-Installer `2.1.7.0`, prüfen SHA256 und betten ihn in die FexoBooth-Setup.exe
  ein. Beim Installieren wird DCC nur gestartet, wenn `CameraControl.exe` fehlt.
- **[tools/nikon_smoke_test.py](tools/nikon_smoke_test.py):** Smoke-Test prüft den robusten `tasklist`-Pfad
  und die DCC-Installer-Beilage.

**Nächster Test:** `FexoBooth_Setup_2.4.10.exe` auf dem Tablet installieren. Danach muss im Log nicht mehr
`CameraControl.exe` überall `FEHLT` stehen. Falls DCC installiert ist, aber `/session.json` weiterhin nicht
antwortet, ist der nächste Block die einmalige Webserver-Aktivierung/Autokonfiguration in digiCamControl.

---

## 2026-07-01

### Nikon-Diagnosebuild 2.4.9: Developer-Logging für DCC FEHLT ausgebaut

**Ziel:** Christian kann auf dem Tablet keine PowerShell-/Suchbefehle ausführen. Der nächste Installer
muss deshalb selbst genug Diagnose loggen, wenn oben `DCC FEHLT!` steht.

**Änderung:**
- **[src/__init__.py](src/__init__.py):** Build-Kandidat auf `2.4.9` angehoben, damit das nächste Log
  eindeutig dem Diagnosebuild zugeordnet werden kann.
- **[src/camera/nikon.py](src/camera/nikon.py):** Im Developer Mode schreibt der Nikon-Adapter jetzt
  `NIKON-DIAGNOSE`-Blöcke mit effektiver Config (`host`, `port`, `app_path`, Timeouts), HTTP-Probe auf
  `/session.json`, relevanten Windows-Umgebungsvariablen, allen geprüften `CameraControl.exe`-Kandidaten
  inklusive `OK/FEHLT/ORDNER`, sowie `tasklist`-Snapshot für `CameraControl.exe`/`digiCamControl.exe`.
- Die automatische Suche prüft zusätzlich typische Per-User-Pfade unter `%LOCALAPPDATA%`, `%APPDATA%`
  und `%ProgramData%`.
- **[.github/workflows/build-release.yml](.github/workflows/build-release.yml):** Testbuild-Default auf
  `2.4.9` gesetzt und Installer-Dateiname auf die vollständige Patch-Version korrigiert.

**Erwartung beim nächsten Test:** Wenn `DCC FEHLT!` wieder erscheint, stehen im Log direkt die konkreten
Pfade und Prozess-/Webserver-Ergebnisse. Damit muss auf dem Tablet nichts manuell ausgeführt werden.

---

### Startscreen-Version sichtbar + lokaler Build-Bump auf 2.4.8

**Ziel:** Vor dem EXE-Build muss die Box bereits eine neue Versionsnummer anzeigen, auch wenn es
noch keinen GitHub-Release gibt.

**Änderung:**
- **[src/__init__.py](src/__init__.py):** lokale Software-Version von `2.4.7` auf `2.4.8` angehoben.
- **[src/app.py](src/app.py):** Top-Bar links zeigt neben Logo/`FEXOBOOTH` jetzt `v2.4.8` aus derselben
  Versionsquelle. Dadurch passt Startscreen-Anzeige, `/api/v1/status` und Installer-Build-Quelle zusammen.
- **[PLAN-APP-OTA.md](PLAN-APP-OTA.md):** erledigten Punkt „Versionsanzeige auf den Start-Screen" abgehakt.

**Wichtig:** Die Anzeige hängt nicht an einem GitHub-Release-Tag. Wer lokal die EXE/Setup baut,
bekommt die Version aus `src/__init__.py`.

---

### Nikon-Hardware-Test ausgewertet: digiCamControl nicht erreichbar/gefunden

**Log:** `D:\fexobooth_20260701_131311.log` vom Windows-Testgerät.

**Befund:** Die App kommt noch nicht bis zum Nikon-/LiveView-/Capture-Vertrag. Sie scheitert vorher,
weil digiCamControl weder als laufender Webserver auf `127.0.0.1:5513` antwortet noch `CameraControl.exe`
in den bekannten Standardpfaden gefunden wird. Relevante Logstellen:
`digiCamControl-Warmup: nicht erreichbar`, `digiCamControl nicht gefunden`,
`Kamera konnte nicht initialisiert werden`.

**Änderung:** [src/camera/nikon.py](src/camera/nikon.py) loggt beim nächsten Fehlschlag zusätzlich
die geprüften `CameraControl.exe`-Pfade. Damit ist sofort sichtbar, ob digiCamControl fehlt oder nur
anders installiert wurde.

**Nächster Test:** digiCamControl installieren, Webserver in digiCamControl einmalig aktivieren
(Port `5513`) oder `nikon_digicamcontrol.app_path` auf den echten `CameraControl.exe`-Pfad setzen.
Danach muss im Log `digiCamControl-Warmup: bereit` erscheinen, bevor LiveView/Capture sinnvoll
bewertet werden können.

---

### Bugfix: Top-Bar-Alarmmeldungen sind jetzt mehrsprachig

**Problem:** Die sichtbaren Alarmtexte oben in der Status-Leiste blieben unabhängig von `locale`
deutsch (`KEIN USB!`, `USB FEHLT!`, Kamera- und Druckerwarnungen).

**Fix:**
- **[src/i18n.py](src/i18n.py):** eigener `TOPBAR_TRANSLATIONS`-Block für alle unterstützten Locales
  (`de-DE`, `de-AT`, `en-GB`, `fr-FR`, `nl-NL`, `it-IT`, `es-ES`, `pl-PL`) ergänzt.
- **[src/app.py](src/app.py):** USB- und Kamera-Badges nutzen jetzt `t(self.config, ...)`.
  Druckerwarnungen werden nur für die Anzeige über `_translate_topbar_printer_problem()` übersetzt;
  die internen deutschen Fehlercodes aus `PrinterController.get_error()` bleiben unverändert für
  Overlay-Klassifizierung, Logging und Support-Kompatibilität.
- **[support/HOTLINE_PROMPT_FELIX.md](support/HOTLINE_PROMPT_FELIX.md):** Felix-Hinweis ergänzt:
  Status-Leisten-Warnungen können jetzt übersetzt sein; Support soll nach Symbol/Bedeutung fragen,
  nicht nur nach exakt deutschem Wortlaut.

**Verifiziert:**
- `python3 -m py_compile src/i18n.py src/app.py`
- Übersetzungsabdeckungs-Check für alle neuen `topbar.*`-Keys über alle `SUPPORTED_LOCALES`.

---

## 2026-06-22

### Feature: Nikon D3300 als DSLR über digiCamControl (Variante 2, wie dslrBooth)

**Ziel:** Nikon D3300 als DSLR betreiben — ohne Nikon Webcam Utility. digiCamControl ist die
externe Windows-Steuerungsschicht und stellt einen lokalen Webserver bereit (`127.0.0.1:5513`);
fexobooth spricht nur HTTP/Single-Command. Sauberer, **additiver** Port aus `fexobooth-consumer`,
auf die v2-Architektur angepasst. Canon-/Webcam-Pfade **unverändert**.

**Geändert/Neu:**
- **NEU [src/camera/nikon.py](src/camera/nikon.py):** `NikonCameraManager` (dünner Adapter um den
  digiCamControl-Vertrag: LiveView `/liveview.jpg`, Capture via `capture` mit Fallback
  `LiveView_Capture`, Bildübergabe über `session.folder`+`session.filenametemplate`+`lastcaptured`
  → lokale Datei, sonst `/image/<name>`, zuletzt `/preview.jpg`; Auto-Start `CameraControl.exe`
  aus Standardpfaden). Interface-kompatibel zu Canon (Drop-in für Session-/App-Flow).
- **[src/camera/__init__.py](src/camera/__init__.py):** Factory routet `camera_type=="nikon"` und
  reicht die Config durch. Nikon-Import **defensiv** (try/except wie Canon) + Factory-Guard
  `NikonCameraManager is not None` → ein künftiger Import-Fehler in nikon.py legt die Flotte nicht lahm.
- **[src/config/defaults.py](src/config/defaults.py):** additiver Block `nikon_digicamcontrol`
  (Host/Port/app_path/capture_folder/Timeouts). (v2 hat keine `config.example.json` — defaults.py ist die Quelle.)
- **[src/storage/booking.py](src/storage/booking.py):** `apply_settings_to_config` respektiert bei
  DSLR-Buchungen jetzt `dslr_camera_type` (Fallback `camera_type`, sonst `canon`) **und** schreibt
  es zurück → Booking-/Event-Reload springt **nicht mehr hart auf Canon** zurück.
- **[src/app.py](src/app.py):** `NIKON_AVAILABLE` importiert; `camera_type` als `self._camera_type`
  gemerkt; neue Methode `_sync_camera_manager_with_config()` baut den Manager nur bei Typ-Wechsel neu
  (sonst nur `update_config`); Sync nach **allen** Apply-/Reload-Pfaden (Init, App-Upload-Reload,
  Admin-Speichern, Event-Wechsel); Nikon-Statuszweig in `_check_camera_status` (`DCC FEHLT!`/`KEINE NIKON!`).
- **Auto-Start von digiCamControl ([src/app.py](src/app.py) `_warmup_nikon_async` + [src/camera/nikon.py](src/camera/nikon.py)
  `ensure_server_running`):** Bei `camera_type=="nikon"` startet die App digiCamControl beim Programmstart
  (und bei Laufzeit-Wechsel auf Nikon) **automatisch im Hintergrund-Thread** vor. Der Betreiber muss
  digiCamControl **nicht mehr manuell vor der App starten**; zugleich trifft der erste Capture nicht den
  Kaltstart-Poll auf dem UI-Thread (entschärft den Major-Freeze des Reviews). Idempotent/no-op, wenn der
  Webserver schon läuft. *(Der Webserver muss in digiCamControl einmalig aktiviert sein — Port 5513 —
  das bleibt ein einmaliger Installations-Schritt, siehe TODO.)*
- **[src/ui/screens/admin.py](src/ui/screens/admin.py):** Nikon im Kameratyp-Dropdown + Kamera-Scan
  über digiCamControl; Admin-Speichern merkt die bevorzugte DSLR (`dslr_camera_type`); **Kundenmenü
  „Template/Settings neu laden" (PIN 2015) synchronisiert jetzt ebenfalls den Kamera-Manager**
  (Main-Thread via `self.after(0, ...)`) — diese Lücke fand das Review.
- **[src/ui/screens/service.py](src/ui/screens/service.py):** Service-Reload synchronisiert den Kamera-Manager.
- **[support/HOTLINE_PROMPT_FELIX.md](support/HOTLINE_PROMPT_FELIX.md):** neue Top-Bar-Status-Texte
  `KEINE NIKON!`/`DCC FEHLT!` zu RUNBOOK C ergänzt (Pflicht laut CLAUDE.md bei Status-Anzeige-Änderungen).
- **NEU [tools/nikon_smoke_test.py](tools/nikon_smoke_test.py):** statischer Vertrags-Smoke-Test (stdlib-only).

**Verifiziert (statisch, KEIN echtes Nikon-Gerät am Testrechner — NICHT hardware-validiert):**
- `py_compile` aller geänderten Dateien grün.
- `tools/nikon_smoke_test.py`: alle Verträge grün.
- Laufzeit-Import + `NikonCameraManager`: ohne digiCamControl sauberes `is_available()=False`/`list_cameras()=[]`;
  Factory-Guard fällt bei kaputtem Import sauber auf Webcam zurück.
- Unit-Test `apply_settings_to_config`: DSLR+nikon bleibt nikon, DSLR ohne Angabe→canon, Müll→canon,
  kein-DSLR→`camera_type` unangetastet (6/6 Fälle korrekt).
- **Adversariale Multi-Agent-Review (14 Agenten):** 7 Findings bestätigt, 2 widerlegt. Behoben: fehlender
  Kamera-Sync im PIN-2015-Reload (minor) + ungeschützter Nikon-Import (minor). Der Major-Freeze
  (`initialize()` bei digiCamControl-Kaltstart auf dem UI-Thread) ist durch den **Auto-Start-Warmup**
  (s.o.) entschärft — DCC läuft beim ersten Capture i.d.R. schon. Dokumentiert für den Hardware-Test
  (alle Nikon-only, 0 Live-Flotten-Impact): ~1.5 s Status-Check-Hitch, Doppel-Capture im Fehlerfall,
  Capture-Erfolg per Antworttext, sowie der Restfall „DCC stirbt zur Laufzeit" (dann greift wieder der
  Auto-Launch in `initialize()`). Widerlegt u.a.: `dslr_camera_type` müsse in `_MACHINE_SETTINGS_KEYS`
  (der `or camera_type`-Fallback + geschütztes `camera_type` garantiert, dass Nikon einen OTA-Verlust übersteht).

**Offen:** Hardware-Test mit echter D3300 (LiveView + Capture End-to-End) + die o.g. Nikon-Runtime-Punkte
auf dem Testgerät prüfen. Siehe [TODO.md](TODO.md).

---

## 2026-06-19

### Bugfix: Druck-Korrektur (2015er-Menü) überlebt Neustart jetzt dauerhaft

**Problem:** Im 2015er-Kunden-/Service-Menü angepasste Druckwerte (Offset X/Y, Zoom)
wurden zwar in `config.json` gespeichert, aber bei **jedem Neustart** wieder auf die
Produktionswerte (40/30/103) zurückgesetzt. Für den Einrichtungsflow fatal: Box wird
nach dem Test heruntergefahren, Kunde startet neu → Korrektur weg.

**Ursache:** `print_adjustment` stand in `_PRODUCTION_DEFAULT_OVERRIDES`
([src/config/config.py](src/config/config.py)). Diese Overrides werden bei **jedem**
`load_config()` über `_apply_production_defaults()` erzwungen – also auch über die
gerade gespeicherten Werte. Speichern war korrekt, der nächste Start überschrieb es.

**Fix:** `print_adjustment` aus `_PRODUCTION_DEFAULT_OVERRIDES` entfernt. Der Start-Default
kommt jetzt ausschließlich aus [src/config/defaults.py](src/config/defaults.py) (identische
40/30/103/3) und wird durch die gespeicherte `config.json` per Deep-Merge überschrieben.
Der **gewollte** Reset pro Eventwechsel bleibt über `reset_event_defaults()` erhalten.
Zusätzlich Dev-Logging in `load_config()`: loggt den tatsächlich geladenen `print_adjustment`-Wert.

**Verifiziert:** Skript-Test (Speichern → Neustart simuliert → Werte bleiben; Eventwechsel-Reset
setzt weiterhin auf 40/30/103 zurück). Alle drei Pfade grün.

---

## 2026-06-14

### App-Plattform-Fundament gebaut (Box-Seite) – „dünne Box, dicke App"

**Ziel:** Einmaliger, zukunftssicherer Box-Umbau, damit danach Features rein per
**App-Update** kommen (App ändern = billig, Box ändern = teuer). Strategie:
[../fexobox-app/PLATTFORM-STRATEGIE.md](../fexobox-app/PLATTFORM-STRATEGIE.md). Alles **additiv**,
performance-neutral, mit Dev-Logging; auf macOS per Flask-`test_client` verifiziert (35 Checks grün)
und durch ein Multi-Agent-Review geprüft (0 kritische/hohe Findings; 5 Findings behoben).

**1. KEYSTONE – lokaler Service-Kanal dauerhaft + entkoppelt:** Hotspot + Flask-API
([src/app.py](src/app.py) `_init_gallery_server`, `_start_gallery_if_needed`) laufen ab jetzt
**immer** (4 s verzögert), unabhängig von `gallery_enabled`. Damit ist Template-/Settings-Korrektur
auch **ohne** gebuchte Galerie möglich. Die beiden Event-Caller (Admin-Speichern, Event-Wechsel)
stellen den Kanal immer sicher; der Hotspot wird nicht mehr abgewürgt.

**2. Foto-Feature serverseitig gegated (Produkt-/Sicherheitsregel):** Neues Modul-Flag
`_gallery_feature_enabled` + `set_gallery_feature_enabled()` in [src/gallery/server.py](src/gallery/server.py).
Alle 9 foto-ausliefernden Routes liefern **403**, wenn keine Galerie gebucht ist; Web-Root zeigt eine
**neutrale fexobox-Seite**. Support-/Infrastruktur-Routes (status, manifest, pairing, pair-by-code,
event, upload/apply) laufen **immer**. Der **Box-Screen bleibt unverändert** – [start.py](src/ui/screens/start.py)
**nicht angefasst**, QR/Banner weiter strikt an `gallery_enabled`.

**3. `GET /api/v1/status` erweitert:** meldet jetzt `software_version`, `gallery_enabled` und eine
Capability-Liste (`settings_patch`, `template_upload`, `asset_upload`, `software_ota`,
`feature_flags:[live_gallery, print_enabled, print_singles, dslr_camera, max_prints]`) →
App bietet nur an, was DIESE Box kann (Vorwärtskompatibilität).

**4. Generische Apply-Endpunkte:** `apply/settings` + `apply/template` (Aliase auf die bestehenden
`upload/*`), `apply/assets` (sicheres ZIP-Staging: kein Path-Traversal, keine ausführbaren Dateien),
`apply/software` (OTA). Soft-Mode ignoriert unbekannte Settings-Keys → neues „Schalter"-Upgrade = null Box-Code.

**5. App-OTA (`POST apply/software` | `upload/software`):** SHA256-Verifikation
([booking.py](src/storage/booking.py) `stage_software_update`, streamend) **vor** dem Anwenden, dann der
**bestehende** Updater (Backup + Rollback + Neustart) via Apply-Marker **nur im Idle**, danach harter Exit.
Staff-Auth = **Service-PIN 6588 als HMAC-SHA256(key=PIN, msg=Nonce)** im Header `X-FexoBox-Service-Auth`
(PIN nicht im Klartext, Nonce pro Server-Start gegen Replay) – **nicht** der Kunden-Pairing-Token.

**6. Soft-Mode bleibt bewusst** (keine Signaturpflicht, siehe PLATTFORM-STRATEGIE.md §2); die alte
Log-Warnung „in v2.5.0 wird das abgelehnt" entschärft.

**Wichtig:** Teure Box-Änderung → vor dem Flotten-Rollout auf **einer echten Box** testen. Build =
GitHub-Actions-**Artefakt** (kein Release/Tag), damit keine Box ungewollt per OTA zieht.

---

### Verbindliche Regel: Dev-Mode-Logging bei jeder Änderung mitziehen

**Prozess-Regel** (kein Code): Ab sofort gilt in [ARBEITSWEISE.md](ARBEITSWEISE.md) als
**Kernprinzip 8** und als Pflichtanweisung in [CLAUDE.md](CLAUDE.md): Bei **jeder**
Software-Änderung wird **sofort** das Dev-Mode-Logging mit erweitert (nicht erst, wenn
etwas nicht funktioniert), und neue Funktionen werden **zuerst im Dev-Mode**
(`python src/main.py --dev`) getestet, bevor sie als fertig gelten.

**Warum:** 200+ Boxen ohne Internet im Feld – das Log (`logs/fexobooth_*.log`) ist dort
oft die einzige Fehler-Spur. Logs, die schon beim Bauen mitgeschrieben werden, sparen
Ferndiagnose. Im Live-Betrieb 0 Overhead (Logging nur im Dev-Mode aktiv, sonst NullHandler).
Konkreter Pflicht-Ablauf (5 Schritte) steht in ARBEITSWEISE.md Kernprinzip 8.

---

## 2026-06-11

### v2.4.6 – Box-ID update-sicher außerhalb des Installationsordners

**Problem aus dem Test:** Trotz des v2.4.5-Hotfixes ging die Box-ID beim WLAN-Update von GitHub erneut verloren.

**Diagnose:** Selbst-Updater-Bootstrap-Problem. Das ersetzende BAT-Script wird von der *alten*, laufenden Version erzeugt ([src/updater.py](src/updater.py#L397)). Beim Update v2.4.4 → v2.4.5 lief also noch das fehlerhafte BAT von v2.4.4, das die in `_internal/config.json` liegende Box-ID nicht rettete. Der v2.4.5-Schutz greift prinzipbedingt erst beim *übernächsten* Update.

**Lösung (in [src/config/config.py](src/config/config.py)):**
- Neue Funktionen `_persistent_store_path()`, `_read_persistent_identity()`, `_write_persistent_identity()`, `_recover_identity_from_store()`
- Box-ID wird zusätzlich nach `C:\ProgramData\FexoBox\box_id.json` gespiegelt (Dev/macOS: `~/.fexobooth/box_id.json`) — ein Ort, den kein Update-Script anfasst
- `save_config()` spiegelt jede gültige Box-ID dorthin
- `load_config()` holt die Box-ID von dort zurück, wenn `config.json` keine enthält, und schreibt sie zurück in `config.json`
- Leere ID überschreibt den Speicher nie
- Version-Bump auf 2.4.6, CHANGELOG + ERKENNTNISSE aktualisiert

**Hinweis:** Boxen, die ihre ID schon beim v2.4.5-Update verloren haben, müssen sie einmalig neu setzen — danach dauerhaft geschützt. Logik mit isoliertem Smoke-Test verifiziert (alle 4 Fälle grün).

---

## 2026-06-10

### Hotline-Prompt „Felix" nach V2-Anrufauswertung nachgeschärft

Auswertung der Gmail/Fonio-Anrufe mit Betreff „Anruf bei Technik-KI" seit V2-Rollout am 2026-05-20. Der Prompt unter [support/HOTLINE_PROMPT_FELIX.md](support/HOTLINE_PROMPT_FELIX.md) wurde anhand der bestätigten Support-Regeln aktualisiert:

- **Template/Layout getrennt von Live-View Overlay:** Felix darf `Live-View Overlay` nicht mehr als Lösung für Drucklayout, Wunsch-Template oder 1-statt-4-Bilder nennen
- **Einzelbild & Multiprint:** Als kostenpflichtige Aufpreisfunktionen dokumentiert, nachträglich im Kundenbereich buchbar; Kunde wurde per Mail bei Ankunft der Box informiert
- **Wunsch-Template fehlt:** Kein Service-Menü-Fix, sondern Callback, weil Mitarbeiter prüfen müssen
- **Default-Template erklärt:** 4 Bilder ohne eigenes Template können normal sein, wenn kein Template ausgewählt wurde; dann `Template wählen` anbieten
- **Service-Menü PIN 2015 erweitert:** `Template wählen` und `Template neu einlesen` aufgenommen; `Druck-Korrektur` bewusst noch nicht anbieten
- **USB-Speicherung:** Nach Port-/Neustartversuchen E-Mail an `problem@fexobox.de`; Bilder werden von der Festplatte gesichert und als Download bereitgestellt
- **„Limit erreicht":** Als Hinweis auf 1 erlaubten Ausdruck/MultiPrint-Upgrade behandelt, nicht als Papier- oder Druckerfehler
- **Dauerlicht statt Blitz:** Fotos dunkel/„Blitz geht nicht" führt zum weißen Drehschalter für Dauerlicht in der Box
- **Callback-Erfassung:** Rückrufnummer wird nicht mehr abgefragt, Rückruf erfolgt automatisch an die anrufende Nummer

---

## 2026-05-20

### Hotline-Prompt „Felix" auf V2-only umgestellt

Alle Fexoboxen im Umlauf sind auf V2 aktualisiert. Der Felix-Prompt unter [support/HOTLINE_PROMPT_FELIX.md](support/HOTLINE_PROMPT_FELIX.md) wurde entsprechend bereinigt:

- **Versions-Gate entfernt** – keine Frage mehr „V1 oder V2?"
- **V1-Fallbacks entfernt** in STROM-GATE, RUNBOOK B/C/D (USB-Hub-Lampen-Diagnose komplett raus)
- **Hard-Reset vereinfacht** – nur noch „bis Display schwarz wird"
- **Service-Menü** verliert den „nur V2"-Marker, gilt jetzt für alle Boxen
- **Buchungsnummer-Regel** vereinfacht – immer vom Display ablesen lassen
- Header-Vermerk: „V2 only (alle Boxen sind auf V2)" mit Datum 2026-05-20

---

## 2026-05-06

### Hotline-Prompt „Felix" für V1 + V2 erstellt

Telefon-KI-Prompt unter [support/HOTLINE_PROMPT_FELIX.md](support/HOTLINE_PROMPT_FELIX.md) angelegt. Deckt beide Box-Versionen ab über ein Versions-Gate („Sehen Sie oben rechts Buchungsnummer und Blitz-Symbol?").

**V2-Spezifika integriert:**
- STROM-GATE über das ⚡-Symbol oben rechts statt „rote Lampe in der Box suchen"
- Drucker-Diagnose über die konkreten Display-Fehlertexte aus `printer_error.py` (`PAPIERSTAU!`, `KASSETTE LEER!`, `KLAPPE OFFEN!`, `DRUCKER OFFLINE!` etc.)
- USB-/Kamera-Status direkt vom Kunden ablesbar
- Kunden-Service-Menü (PIN 2015, unsichtbarer Button oben rechts in der Ecke) als Eskalationsstufe vor dem Callback — mit „Druckstau beheben", „Windows Neustart" und „Live-View Overlay EIN/AUS" für den Wunsch nach Vollbild-Kamerabild

**Pflege-Anweisung in [CLAUDE.md](CLAUDE.md) ergänzt:** Prompt muss bei Änderungen an Top-Bar, Fehlertexten oder Kunden-Menü mit aktualisiert werden.

**TODO ergänzt** ([TODO.md](TODO.md)): Am 2026-05-11 (Mo) auf reinen V2-Modus umstellen, V1-Fallbacks dann entfernen.

---

## 2026-04-30

### Service-Menü responsiv: 2x2-Grid im Querformat (v2.3.3)

**Problem (User-Bericht):** Service-Menü (PIN 6588) im Querformat (1280×800) unten abgeschnitten — „Aktuelle Version"-Zeile + untere Steuerelemente nicht sichtbar.

**Ursache:** Layout war 1-spaltig vertikal: 4 Buttons à 60 px + 4 Beschreibungen + Header + Footer ≈ 600+ px. Die Card hatte `place(relx=0.5, rely=0.5)` ohne Höhen-Begrenzung — auf 800-px-Höhe + Border + Header sprengt das den Rahmen.

**Fix in [src/ui/screens/service.py](src/ui/screens/service.py):**
- Layout-Logik prüft Screen-Aspect-Ratio:
  - **Querformat (w ≥ h):** Card 900 × 650, **2×2-Grid** für Buttons. Jede Zelle = 1 Button + Beschreibung.
  - **Hochformat (w < h):** Card 520 × 92%, Buttons in 1 Spalte gestapelt (wie vorher).
- Compact-Modus bei `screen_height < 700`: kleinere Buttons + Paddings.
- Status- und Versions-Info am unteren Card-Rand fixiert (`side="bottom"`), nicht im scrollbaren Bereich versteckt.

**Betroffen:** `src/ui/screens/service.py`, `src/__init__.py` (2.3.2 → 2.3.3)

---

### Admin-Dialog: topmost + Datei-Dialog-Z-Order-Fix (v2.3.2)

**Problem (User-Bericht klar reproduziert):** Im Admin-Menü auf 📁 klicken → Windows-Datei-Auswahl-Dialog öffnet sich → in dem Moment **verschwindet der Admin-Dialog**. Datei wählen oder abbrechen ändert nichts: Admin-Dialog bleibt unsichtbar. User vermutet (richtig): er rutscht hinter das Kiosk-Vollbild.

**Root Cause:** [AdminDialog](src/ui/screens/admin.py) hatte **kein `attributes("-topmost", True)`** im `__init__()` — andere Dialoge (FexosafeBackup, UpdateProgress) hatten das schon. Der Admin-Dialog hatte nur `overrideredirect(True)` + `lift()` + `focus_force()`. Wenn der Windows-File-Dialog kommt und wieder geht, erbt das Z-Top wieder zum Root (Kiosk-Fullscreen) → Admin-Dialog ist hinter Root verborgen.

**Fix:**
1. `AdminDialog.__init__()`: `self.attributes("-topmost", True)` direkt nach `lift()` gesetzt.
2. `_create_file_picker()` `browse()` und `asksaveasfilename()`: vor dem `filedialog`-Aufruf topmost auf `False` setzen (sonst überlagert der Admin-Dialog den File-Dialog), nach Schließen sofort wieder `True` + `lift()` + `focus_force()`.
3. `parent=self` als Hinweis fürs OS, damit der File-Dialog den Admin-Dialog als Owner kennt.

**Damit ist meine v2.3.1-Theorie widerlegt:** Es war nicht `_check_fullscreen_restore()` — der Fix von gestern ist trotzdem sinnvoll als Prävention. Der echte Z-Order-Bug war einfach das fehlende topmost.

**Betroffen:** `src/ui/screens/admin.py`, `src/__init__.py` (2.3.1 → 2.3.2)

---

## 2026-04-29

### Admin-Dialog Z-Order-Fix + Diagnose-Logging (v2.3.1)

**Problem (User-Bericht):** Admin-Dialog (PIN 3198) schließt sich nach wenigen Sekunden von alleine, ADMIN-Button reagiert danach nicht mehr — App muss über Taskmanager beendet werden. Tritt auch mit Maus-Bedienung auf (also nicht Touch-Race wie in v2.2.9 vermutet).

**Root Cause:** `_check_fullscreen_restore()` ([src/app.py](src/app.py)) läuft alle 5 s. Im else-Zweig (Fullscreen aktiv) wurde `_hide_taskbar()` aufgerufen **auch bei offenen Dialogen**. `_hide_taskbar()` macht Win32-`ShowWindow(SW_HIDE)`-Calls die den Z-Order beeinflussen. Wenn der Code annahm „Fullscreen verloren", wurde `_enter_fullscreen()` aufgerufen — das macht `root.lift()` + `attributes("-topmost")`, was Toplevels mit `overrideredirect=True` dahinter rutschen lässt. Mein v2.2.9-Fix (Click-outside-Handler entfernt) war damit nicht der echte Grund — der Dialog wurde nicht durch User-Interaktion geschlossen, sondern durch Hintergrund-Status-Check.

**Fix:**
1. `_check_fullscreen_restore()` macht jetzt **gar nichts** wenn ein Toplevel offen ist — keine Win32-Calls, keine Lift-Operationen. Status-Check wird erst nach Dialog-Schließung wieder aktiv.
2. Toplevel-Erkennung erweitert: prüft `winfo_class()=="Toplevel"` UND `isinstance(child, CTkToplevel)`.

**Diagnose:** `AdminDialog.destroy()` loggt jetzt den vollständigen Caller-Stack. Falls der Bug doch nochmal auftritt (andere Ursache), zeigt das Log direkt wer den Dialog schließt.

**Betroffen:** `src/app.py`, `src/ui/screens/admin.py`, `src/__init__.py` (2.3.0 → 2.3.1)

---

### Update-Pfade mit Timestamp gegen File-Lock-Konflikt (v2.3.0)

**Problem (User-Bericht):** Beim 2. Update kam Dialog „Update fehlgeschlagen — kann nicht auf die Datei zugreifen, da sie von einem anderen Prozess verwendet wird: `C:\Users\Selphy\AppData\Local\Temp\...`". Das erste Update lief sauber durch, das nächste hängt sich beim Download auf.

**Ursache:** [download_update()](src/updater.py) nutzte einen festen Dateinamen `%TEMP%\fexobooth_update.zip`. Beim ersten Update wird die Datei runtergeladen + nach erfolgreichem Update gelöscht — **aber Windows Defender Real-Time-Schutz** scannt frisch heruntergeladene ZIPs/EXEs noch einige Zeit nach Erstellung. Während dem Scan ist die Datei in einem nicht-löschbaren Zustand. Wenn der User direkt danach das nächste Update startet, schlägt `zip_path.unlink()` fehl, die Exception bricht den Update-Vorgang ab. Gleicher Effekt theoretisch auch für `fexobooth_updater.bat` und `fexobooth_update_extract/`.

**Fix:**
1. **Eindeutige Dateinamen pro Lauf** in [src/updater.py](src/updater.py): ZIP, BAT und Extract-Verzeichnis bekommen jetzt einen Timestamp + PID-Suffix (`fexobooth_update_<YYYYMMDD_HHMMSS>_<PID>.zip`). Damit kollidiert nie mit Resten vom letzten Update.
2. **Robustes unlink**: try/except um den unlink-Versuch + Alternativname als letzter Fallback.
3. **Orphan-Cleanup mit Glob-Patterns**: `cleanup_orphan_downloads()` nutzt jetzt `temp_dir.glob('fexobooth_update*.zip')` etc. — findet sowohl alte feste Namen (von v2.2.x) als auch neue Timestamp-Namen.

**Side-Note:** v2.3.0 ist gleichzeitig das erste Update das v2.2.9 → v2.3.0 testet ob die assets/videos/-Schutz-Logik aus v2.2.9 hält.

**Betroffen:** `src/updater.py`, `src/__init__.py` (2.2.9 → 2.3.0)

---

### Bug-Fixes: Admin-Dialog + OTA-Custom-Assets (v2.2.9)

**Bug 1: Admin-Dialog ging gelegentlich beim Öffnen sofort wieder zu** und der „ADMIN"-Button reagierte danach nicht mehr (User-Bericht). Im Log nur eine Zeile `Tab 'Allgemein' erstellt (lazy)`, dann nichts mehr von admin.py. Ursache: Im PIN-Dialog war `self.pin_frame.bind("<Button-1>", lambda e: self.destroy())` — Click-outside-zum-Schließen. Auf Touch-Screens kommt es vor dass Touch-Down auf der Karte und Touch-Up auf dem Hintergrund landet (kleine Finger-Bewegung) → Dialog schließt direkt nach Öffnen. Plus: ohne `grab_release()` blieb manchmal ein grab am Parent hängen, der ADMIN-Button reagierte dann nicht mehr.

Fix in [src/ui/screens/admin.py](src/ui/screens/admin.py):
1. `pin_frame.bind("<Button-1>", ...)` entfernt — User schließt jetzt nur über `✕`-Button oder ESC
2. `destroy()` Override eingebaut, der vor super().destroy() immer `grab_release()` aufruft

**Bug 2: OTA-Update überschrieb User-Videos und Custom-Bilder.** User-Bericht: Beim OTA-Update auf v2.2.8 wurden seine Einstellungen zu Capture-Bild und Video-Sequenzen gelöscht. Ursache: Das BAT-Script in `updater.py:create_update_script()` machte `xcopy assets/ /E /Y` — überschreibt `assets/videos/start.mp4`, `end.mp4` und ggf. ein Custom-Auslöse-Bild im `assets/`-Root mit den Defaults aus dem ZIP. `config.json` blieb zwar geschützt, aber die referenzierten Files waren weg.

Fix im BAT-Script:
1. Vor dem `xcopy`: `assets/videos/` atomar nach `%TEMP%\fexobooth_user_assets\videos` movieren, Custom-PNGs/JPGs im `assets/`-Root nach `\root_images\` kopieren
2. Nach dem `xcopy`: User-Videos atomar zurück (überschreibt Default-Videos aus dem ZIP), User-Bilder zurück
3. Backup aufräumen
4. Hinweis-Liste „Geschuetzte Dateien" um `assets/videos/` und `assets/*.png/jpg` erweitert

Damit bleiben **alle User-Custom-Files** beim OTA erhalten.

**Betroffen:** `src/ui/screens/admin.py`, `src/updater.py`, `src/__init__.py` (2.2.8 → 2.2.9)

---

### Template & Settings vom USB neu laden (v2.2.8)

**Problem:** Kunden tauschen manchmal mitten in der Veranstaltung das Template auf dem USB-Stick (oder ändern eine Einstellung in `settings.json`). Da die `booking_id` gleich bleibt, hat [BookingManager.load_from_usb()](src/storage/booking.py) den Reload übersprungen ([Z. 317](src/storage/booking.py#L317)):
```python
if not force and new_booking_id == self.booking_id and self._settings:
    return True  # gleiche Buchung, überspringe
```
Bisherige Workarounds: Stick mit anderer booking_id präparieren oder Tablet neu starten. Beides umständlich.

**Fix:** Neuer Eintrag in beide PIN-Menüs (User-Wunsch: in beide):
1. **Service-Menü 6588** ([src/ui/screens/service.py](src/ui/screens/service.py)) — neuer Button „Template & Settings vom USB neu laden". Mit Progress-Anzeige + Status-Feedback.
2. **Kunden-Menü 2015** ([src/ui/screens/admin.py](src/ui/screens/admin.py)) — neuer Button „📂 Template neu einlesen". Vereinfachte UI für Vor-Ort-Helfer.

Beide rufen `booking_manager.load_from_usb(usb_root, force=True)` auf, dann `apply_settings_to_config(config)`, dann `app._restore_cached_template()`, dann Screen-Refresh. Das erzwingt das Reload aller relevanten USB-Daten ohne Tablet-Neustart.

**Anwendungsfall settings.json:** Auch das wird damit aktualisiert — bisher genauso ignoriert wie das Template, weil der Code-Pfad identisch ist.

**Betroffen:** `src/ui/screens/service.py`, `src/ui/screens/admin.py`, `src/__init__.py` (2.2.7 → 2.2.8)

---

## 2026-04-28

### Deploy: Smart-Fallback im Pre-Flight-Check (Tooling-Fix)

**Problem (User-Beobachtung):** Master-Tablet ist 64 GB (58 GB Disk), Windows wurde auf 28 GB geschrumpft, 30 GB unallocated am Ende. Beim Capture wird die GPT-Disk-Geometrie aber als 58 GB ins Image geschrieben (Position der GPT-secondary). Beim Deploy auf 32 GB Tablet bricht der Pre-Flight-Check ab: „Image 58 GB > Ziel 29 GB" — obwohl die echten NTFS-Daten ins Ziel passen würden und Clonezilla beim Restore proportional schrumpfen kann (`ocs-expand-gpt-pt -icds`).

**Fix:** Neue Helfer-Funktion `get_image_ntfs_used_bytes()` in [custom-ocs-deploy](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy) — streamt das größte NTFS-Partclone-Image durch `unxz | partclone.chkimg`, parst „Space in use" + „Block size", liefert die echte Datennutzung in Bytes.

**Smart-Fallback im Pre-Flight-Check:** Wenn der direkte Disk-Größen-Vergleich kein passendes Image findet (alle Images haben zu große Disk-Geometrie), wird pro Image die echte NTFS-Datennutzung ermittelt und gegen `Ziel-Bytes − 400 MB (EFI/MSR) − 1 GB (Sicherheits-Buffer)` verglichen. Wenn ein Image passt → wird gewählt mit Hinweis „Disk-Geometrie größer als Ziel, aber NTFS-Daten passen — Clonezilla shrinkt proportional". Wenn kein Image passt → Abbruch wie bisher (mit erweitertem Hinweis-Text).

**Performance:** Der `partclone.chkimg`-Lauf dauert pro Image ~30-60 s (Decompression eines mehrstündigen Streams nötig). Smart-Check läuft nur wenn der Direktvergleich versagt — Standard-Fall (passendes Image vorhanden) ist unverändert schnell.

**Bonus-Fix:** `exit 1` nach allen `reboot`-Aufrufen in den Fehlerpfaden (analog zum capture-Script-Fix). `reboot` ist non-blocking, der Code-Flow wäre sonst weitergelaufen.

**Wichtig:** Tooling-Fix auf dem Deploy-Stick. App-Code unverändert v2.2.5. User muss `prepare_usb_stick.bat` mit „Partitionen behalten" laufen lassen oder `custom-ocs-deploy` manuell rüberkopieren.

**Betroffen:** `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy`

---

### OTA-Update: SSL-Cert-Fix (v2.2.5)

**Problem (Foto vom Tablet):** v2.2.4 fand das Update via API (`check_for_update()` lief durch), aber der ZIP-Download brach sofort ab mit:
```
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
unable to get local issuer certificate
```

**Ursache:** Im PyInstaller-Build findet `urllib` kein CA-Bundle. Im Dev-Modus geht's, weil Python die Windows-Zertifikate über OpenSSL findet — aber in der gepackten EXE fehlt diese Anbindung. Der API-Check vorher klappte vermutlich nur weil GitHub den TLS-Handshake mit weniger strengen Defaults toleriert hat (wahrscheinlich ein Cache-Effekt nach dem ersten erfolgreichen Call); der eigentliche Download brach dann an einem anderen Endpoint (`objects.githubusercontent.com`) ab.

**Fix:**
1. `certifi>=2024.0.0` als explizite Dependency in `requirements.txt`.
2. In [fexobooth.spec](fexobooth.spec) `collect_all("certifi")` → `cacert.pem` und alle Datendateien werden in den Build gepackt. Plus `certifi` und `ssl` in `hiddenimports`.
3. In [src/updater.py](src/updater.py) eine neue Funktion `_build_ssl_context()` die einen `ssl.create_default_context(cafile=certifi.where())` zurückgibt. Der Context wird als Modul-globale `_SSL_CONTEXT` einmal beim Import gebaut und an beide `urlopen()`-Aufrufe weitergegeben (API + Download).
4. Fallback: Wenn certifi fehlt (z.B. broken Dev-Setup), wird auf System-Default zurückgegriffen mit Warning im Log.

**Catch-22 für bestehende Tablets:** v2.2.4 und älter können das Fix nicht via OTA bekommen — genau dieses SSL-Problem blockiert ja den Download. Diese Tablets müssen **einmalig manuell** über die Setup.exe vom FEXODATEN-Stick auf v2.2.5 aktualisiert werden. Ab v2.2.5 läuft OTA für alle weiteren Versionen.

**Betroffen:** `src/updater.py`, `requirements.txt`, `fexobooth.spec`, `src/__init__.py` (2.2.4 → 2.2.5)

---

### Capture: hiberfil.sys-Removal + drei weitere Bugs (Tooling-Fix, kein App-Release)

**Problem (User-Feedback nach zweitem Tooling-Fix):** Trotz präventivem `ntfsfix` versagte partclone weiterhin mit `is scheduled for a check or it was shutdown uncleanly`. Im Log: `ntfsfix` lief erfolgreich (`Mounting volume... OK`, `Processing of $MFT and $MFTMirr completed successfully`), aber `partclone.ntfs` blockierte trotzdem.

**Root Cause:** Windows-Schnellstart hinterlässt **zwei** Marker auf der NTFS-Partition:
1. NTFS Dirty Bit im Volume-Header (das räumt `ntfsfix` weg ✓)
2. **`hiberfil.sys`** mit Kernel-Session-Hibernation (das räumt `ntfsfix` NICHT weg)

`partclone.ntfs` (intern: `ntfsclone-ng`) prüft beides und verweigert das Klonen wenn auch nur einer der beiden gesetzt ist. ntfsfix alleine reichte deshalb nicht.

**Fix 1 — hiberfil.sys via ntfs-3g entfernen:** Nach `ntfsfix -d` wird die NTFS-Partition kurz mit `mount -t ntfs-3g -o remove_hiberfile,rw` gemounted. Diese Mount-Option löscht hiberfil.sys automatisch wenn vorhanden. Dann sofort wieder unmounten. Damit ist der Hibernation-Marker weg und partclone akzeptiert die Partition.

**Fix 2 — Verifikations-Marker robuster:** Beim ANSI-Stripping (`sed -E 's/\x1b\[[0-9;]*[a-zA-Z]//g'`) verschwindet manchmal das Whitespace zwischen Wortteilen, weil im Original `shutdown\x1b[8;11Huncleanly` stand → bereinigt zu `shutdownuncleanly` (ohne Space). Mein Regex `scheduled for a check or it was shutdown uncleanly` matchte deshalb nicht. Neu: `scheduled for a check.*shutdown.*uncleanly` mit `.*` zwischen Schlüsselwörtern.

**Fix 3 — Script-Flow nach Fehler:** Das Capture-Script logte am Ende eines Fehlerlaufs paradoxerweise `[FEHLER] Image-Verifikation fehlgeschlagen` UND `[OK] Image-Verifikation erfolgreich` zugleich. Ursache: `reboot` ist non-blocking — der Befehl scheduled nur den Reboot und kehrt zurück, das Script lief dann durch in den Erfolgspfad. Fix: Nach jedem `reboot` ein `exit 1` einfügen.

**Wichtig:** Tooling-Fix auf dem Capture-Stick. App-Code unverändert v2.2.3. User muss [custom-ocs-capture](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture) neu auf den Stick kopieren (oder `prepare_usb_stick.bat` mit „Partitionen behalten" laufen lassen).

**Betroffen:** `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture`

---

### Capture: Präventives ntfsfix + ANSI-robuste Marker-Detection (Tooling-Fix, kein App-Release)

**Problem (User-Feedback nach erstem Tooling-Fix):** Der erste Fix verifizierte korrekt dass die Image-Datei für `mmcblk0p3` fehlt, zeigte aber NICHT die spezifische "dirty NTFS"-Anleitung — obwohl genau das die Ursache war. Im Log stand `is scheduled for a check or it was shutdown uncleanly`, aber mein grep matchte nicht.

**Ursache (zwei separate Probleme):**

1. **partclone schreibt Terminal-Cursor-Steuerzeichen MITTEN in den Text.** Der zusammenhängende String "is scheduled for a check or it was shutdown uncleanly" steht im Log als `is scheduled fo\x1b[7;11Hr a check or it was shutdown\x1b[8;11Huncleanly`. Mein `grep -qE "is scheduled for a check..."` findet das nicht weil der Cursor-Code zwischen `fo` und `r` sitzt. → **Fix:** ANSI-Escape-Codes via `sed -E 's/\x1b\[[0-9;]*[a-zA-Z]//g'` strippen, dann gegen Clean-Copy matchen.

2. **Windows 10/11 "Schnellstart"** — beim normalen Shutdown wird das NTFS nicht clean unmounted, sondern in einen Hibernation-ähnlichen Zustand versetzt. partclone.ntfs sieht das als "uncleanly shutdown" und verweigert das Klonen. Selbst wenn der User „sauber herunterfährt", bleibt das dirty bit gesetzt, weil Windows das absichtlich tut für schnelleren Boot. → **Fix:** Vor dem Capture läuft `ntfsfix` präventiv auf alle NTFS-Partitionen der Quell-Disk. ntfsfix clearet das dirty bit und resettet `$LogFile` — das ist sicher solange das Filesystem nicht echt korrupt ist (was wir hier voraussetzen können, weil das Tablet ja bootbar ist).

**Zusätzlich:** Der „dirty NTFS"-Hinweistext im Fehlerfall enthält jetzt die echten Lösungsschritte: `powercfg /h off` + Schnellstart-Häkchen in Energieoptionen entfernen (statt der bisher unzureichenden „bitte sauber herunterfahren"-Anleitung).

**Wichtig:** Tooling-Fix auf dem Capture-Stick. App-Code unverändert v2.2.3. User muss [custom-ocs-capture](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture) neu auf den Stick kopieren.

**Betroffen:** `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture`

---

### Capture: Verifikation gegen halbfertige Images (Deployment-Tool-Fix, kein App-Release)

**Problem (vom User gemeldet):** Capture meldete „Image erfolgreich erstellt", obwohl im Log rot „**Das Image wurde NICHT erfolgreicht gesichert**" stand. User dachte, alles ok — wäre fast mit dem halbfertigen Image ein Tablet gebricked worden.

**Ursache:**
1. NTFS-Volume hatte das **dirty bit** gesetzt (Windows nicht sauber heruntergefahren). `partclone.ntfs` weigerte sich zu klonen.
2. **`ocs-sr` gibt Exit-Code 0 zurück** auch wenn `partclone` für eine einzelne Partition fehlschlägt — der Wrapper macht einfach mit Hardware-Info-Files weiter.
3. Die Exit-Code-Prüfung in [custom-ocs-capture](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture) (`if [ "$OCS_EXIT" -ne 0 ]`) war damit wirkungslos. Script meldete „ERFOLG", obwohl `mmcblk0p3.ntfs-ptcl-img.xz.aa` (die Windows-Partition mit ~35 GB) komplett fehlte. Image war nur 25 MB groß statt 15-20 GB.

**Fix:** Nach `ocs-sr` neue Verifikation:
1. `parts`-Datei aus Image-Verzeichnis lesen → erwartete Partitionen ermitteln
2. Für jede Partition prüfen ob `${PART}.*-ptcl-img.xz.aa` existiert (+Größe loggen)
3. Log zusätzlich nach Markern scannen: `is scheduled for a check or it was shutdown uncleanly`, `Failed to save partition`, `Failed to use partclone`
4. Bei „dirty NTFS": spezifische Anleitung zeigen (Tablet booten → Windows → sauber runterfahren → Capture wiederholen)
5. Bei jedem Fehler: Image-Verzeichnis nach `${IMAGE_NAME}_FAILED_${TIMESTAMP}` umbenennen, damit es im Deploy-Menü nicht erscheint
6. Bei Erfolg: Gesamtgröße des Images loggen (Sanity-Check)

**Wichtig:** Das Script liegt auf dem Capture-USB-Stick, nicht auf den Tablets. Fix wirkt erst nach Stick-Re-Erstellung mit `prepare_usb_stick.bat` oder manuellem Rüberkopieren der Datei. **Kein neuer App-Release** — App-Code (Tablets) ist unverändert v2.2.3.

**Betroffen:** `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture`

---

### Spiegel-Bug: Texte im Druck waren seitenverkehrt (v2.2.3)

**Problem:** LiveView wird absichtlich gespiegelt — User sehen sich wie in einem Spiegel, das ist intuitiv für Pose-Anpassung. Aber im Capture-Pfad ([src/ui/screens/session.py:_capture_worker](src/ui/screens/session.py)) wurde der Frame nach der Aufnahme **ebenfalls** mit `cv2.flip(frame, 1)` gespiegelt — sowohl im Webcam- als auch im Canon-DSLR-Zweig. Das gespeicherte JPG und der Druck waren damit seitenverkehrt: Texte auf T-Shirts, Logos, Schilder, Schriftzüge — alles unleserlich.

**Fix:** Die zwei `cv2.flip(frame, 1)` aus `_capture_worker` entfernt (Z. ~657 DSLR, ~683 Webcam). Der LiveView-Flip bei Z. ~279 bleibt erhalten. Erklärende Kommentare an allen drei Stellen ergänzt damit das später nicht versehentlich „korrigiert" wird.

**Konsequenz:** Im Final-Screen sieht der User sich jetzt nicht-gespiegelt — er winkt links und sieht sich links winken. Das ist gewünscht und konsistent mit dem Druck.

**Betroffen:** `src/ui/screens/session.py`, `src/__init__.py` (2.2.2 → 2.2.3)

---

## 2026-04-23

### Update-UI: Progress-Dialog + Orphan-Cleanup (v2.2.2)

**Problem:** Nach Klick auf "Jetzt updaten" sah der User nichts mehr. Der ServiceDialog hat kein `-topmost` gesetzt ([src/ui/screens/service.py:47](src/ui/screens/service.py#L47)), während der Confirm-Dialog es hatte. Sobald `confirm.destroy()` den Bestätigungsdialog zerstörte, fiel der ServiceDialog im Z-Stack zurück — die Kiosk-Haupt-App (ebenfalls Fullscreen-Overlay) überlagerte ihn. Der Download lief im Background-Thread brav weiter, aber die Progress-Bar (nur 12 px hoch) war hinter der Haupt-App versteckt. User denkt "abgestürzt", startet neu → Download verloren, Fragmente in `%TEMP%`.

**Fix 1 — Dedizierter Progress-Dialog:** Neues Modul [src/ui/dialogs/update_progress.py](src/ui/dialogs/update_progress.py) analog zu `FexosafeBackupDialog`. Fullscreen-Overlay mit `attributes("-topmost", True)`, 28 px hohe Progress-Bar, MB-Zähler (`52.3 / 143.4 MB`), Prozent-Anzeige und klarem Phasen-Text. `service._execute_update()` öffnet jetzt diesen Dialog (nach `self.withdraw()` des ServiceDialog) statt die Inline-Progressbar zu nutzen.

**Fix 2 — Orphan-Cleanup:** Neue Funktion `updater.cleanup_orphan_downloads(max_age_hours=1.0)`, beim App-Start aufgerufen. Löscht `%TEMP%\fexobooth_update.zip`, `%TEMP%\fexobooth_update_extract\`, `%TEMP%\fexobooth_updater.bat` wenn älter als 1 h. Verhindert zugemüllte Tablets bei abgebrochenen Updates. 1 h Mindestalter schützt laufende Downloads.

**Zusätzlich:** `src.ui.dialogs.update_progress` und `src.company_network` explizit in `fexobooth.spec` als hidden imports eingetragen — nicht strikt nötig (PyInstaller findet direkte Imports), aber robuster gegen spätere Refactorings.

**Betroffen:** `src/ui/dialogs/update_progress.py` (neu), `src/ui/screens/service.py`, `src/updater.py`, `src/app.py`, `src/__init__.py`, `fexobooth.spec`

---

### Updater: Repo war privat, Fehler-Logging ergänzt (v2.2.1)

**Problem:** Der Update-Button im Service-Menü zeigte auf allen Tablets "Keine Internetverbindung" – obwohl Browser-Internet funktionierte. Das GitHub-Repo `fefotec/fexobooth-v2` war auf **private** gesetzt. Unauthentifizierte API-Calls auf private Repos liefern **HTTP 404** (GitHub-Security-Feature, versteckt Existenz privater Repos). Der Code in [src/updater.py](src/updater.py) wrapped `URLError` (dessen Subklasse `HTTPError` ist) generisch in `ConnectionError` → UI zeigt "Keine Internetverbindung". Das heißt: **der OTA-Update-Mechanismus hat seit v2.0.0 nie funktioniert.**

**Zusätzliches Problem:** Der Service-Dialog-Handler ([src/ui/screens/service.py:_check_update](src/ui/screens/service.py)) schluckte die Exception komplett ohne Logging. Das Log zeigte nur "Prüfe auf Updates..." und dann nichts mehr — Fehlerdiagnose unmöglich.

**Fix:**
1. Repo auf **public** umgestellt (`gh repo edit --visibility public`). Sicherheits-Check vorher: keine committeten Secrets, nur ein hartkodiertes Hotspot-Default-Passwort (für den Galerie-Hotspot der Box, Kunden sehen es sowieso).
2. `updater.check_for_update()` unterscheidet jetzt explizit `HTTPError` (liefert `ValueError` mit exaktem Status-Code) von `URLError` (liefert `ConnectionError`). Beide loggen mit `exc_info=True`.
3. `service._check_update()` loggt die Exception vor dem UI-Dialog.

**Verifikation:** `curl https://api.github.com/repos/fefotec/fexobooth-v2/releases/latest` (ohne Auth) liefert jetzt v2.2.0-Metadaten. `urlopen()` im PyInstaller-Build sollte jetzt ebenfalls durchkommen.

**Betroffen:** `src/updater.py`, `src/ui/screens/service.py`, `src/__init__.py` (2.2.0 → 2.2.1)

---

### Auto-Update im Firmen-WLAN

**Idee:** Wenn eine Fotobox in der Firma eingeschaltet wird (z.B. vor einer Vermietung zum Bild-Ziehen), soll sie sich still aktualisieren. Beim Kunden besteht nie eine Internetverbindung, also kann dort niemals versehentlich ein Update laufen.

**Umsetzung:**
- Neue Datei [src/company_network.py](src/company_network.py) mit zwei Funktionen: `get_active_ssid()` (liest aktive WLAN-SSID via `netsh wlan show interfaces`) und `check_and_auto_update()` (Background-Thread, prüft SSID gegen Whitelist, bei Match triggert `updater.check_for_update()`).
- Firmen-SSIDs als Default in [src/config/defaults.py](src/config/defaults.py): `fexon WLAN`, `fexon_Buero_WLAN2`, `fexon_Buero_WLAN2_5GHZ`, `fexon Gast-WLAN`, `fexon_outdoor` (Whitelist, nicht Präfix-Match — robuster gegen zufällige Kunden-WLANs mit "fexon" im Namen).
- Trigger in [src/app.py](src/app.py) am Ende von `__init__`, 15s Verzögerung nach Start, als Daemon-Thread.
- Ohne Internet wird der `ConnectionError` aus `check_for_update()` still geschluckt → beim Kunden passiert nichts.

**Warum SSID + Internet-Check statt nur Internet:** Ein Kunde könnte theoretisch ein offenes WLAN oder einen Hotspot mit Internet haben. Mit dem SSID-Check ist das doppelt abgesichert: Box muss (1) in einem der fexon-WLANs sein UND (2) Internet haben.

**Version:** Bump auf `2.2.0` — erstes Feature-Release seit 2.1.1.

**Betroffen:** `src/company_network.py` (neu), `src/app.py`, `src/config/defaults.py`, `src/__init__.py`

---

### FEXOSAFE-Backup: Überordner = Buchungs-ID (Event-ID)

**Problem:** Der FEXOSAFE-Auto-Backup-Dialog (poppt auf, sobald ein FEXOSAFE-Stick eingesteckt wird) kopierte alle Bilder nach `USB:\BILDER\Single` bzw. `\Prints` – ohne Unterscheidung nach Buchung. Wurde derselbe Stick für mehrere Events genutzt, landeten alle Bilder zusammen im selben `BILDER/`-Ordner. Der Service-Menü-Backup (PIN 6588) machte es korrekt mit Event-ID als Überordner, der Auto-Dialog aber nicht.

**Fix in [src/ui/dialogs/backup.py](src/ui/dialogs/backup.py):** Neue Methode `_get_last_event_id()` (Logik analog zu `service.py:_get_last_event_id`): aktive Buchung → aktuelle Statistik → letzte Historie → Datum-Fallback. In `_run_backup()` wird der Zielpfad jetzt zu `fexosafe_root / event_id / {Single|Prints}` statt `fexosafe_root / "BILDER" / {Single|Prints}`.

**Betroffen:** `src/ui/dialogs/backup.py`

---

## 2026-04-22

### Deployment: Pre-Flight-Check verhindert Bricken kleinerer Tablets

**Problem:** Zwei Tablets wurden beim Image-Aufspielen unbrauchbar gemacht. Beide waren **32 GB Lenovo Miix 310** (Modell `MMC DF4032`), das Image stammt aber von einem **64 GB Tablet** (`MMC DF4064`). Mit `-icds -k1` versucht Clonezilla die Partitionen proportional zu schrumpfen - aber die NTFS-Daten (34,7 GB belegt) passen physisch nicht in die ~28 GB die nach EFI+MSR auf einem 32 GB Tablet uebrig bleiben. Restore stirbt mitten im NTFS-Schreiben mit `target seek ERROR: Invalid argument`. Der vorherige Pre-Wipe hat aber bereits die alte Partitionstabelle zerstoert -> Tablet hat halbe NTFS-Daten und keine bootbare Struktur mehr.

**Fix in [custom-ocs-deploy](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy):** Neuer **Pre-Flight Check VOR dem Pre-Wipe**:
- Liest die Original-Disk-Sektorzahl aus den Image-Metadaten (`<disk>-pt.sf`, Feld `last-lba`)
- Vergleicht mit Ziel-Disk-Sektorzahl
- Toleranz 5% (deckt eMMC-Chargen-Variationen ab, z.B. 8 MB Differenz zwischen 64 GB Tablets)
- Bei Ziel < 95% der Image-Groesse: **ABBRUCH bevor Pre-Wipe gestartet wird**
- Tablet bleibt unveraendert, klare Fehlermeldung mit Image- und Ziel-GB
- Log enthaelt Hinweis "Vermutlich 32 GB Tablet, Image von 64 GB Tablet"

**Betroffen:** `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy`

**Wichtig:** Tablets die aktuell in der Sammlung sind muessen vorher nach Disk-Groesse sortiert werden (`MMC DF4032` = 32 GB, `MMC DF4064` = 64 GB). Fuer 32 GB Tablets braucht es entweder ein separates Image oder das Referenz-Image mit C < 25 GB neu capturen.

---

## 2026-04-20

### Hotspot: Auto-Dummy-Profil fuer frisch geklonte Tablets

**Problem:** Nach dem Deployment starteten einige Tablets den Hotspot nicht. Die App-Logs zeigten `Tethering API fehlgeschlagen: NO_PROFILE`. Die Diagnose ergab: `NetworkOperatorTetheringManager.CreateFromConnectionProfile()` gibt `null` zurueck solange das Tablet kein einziges gespeichertes WLAN-Profil hat. Sobald sich das Tablet einmal mit einem beliebigen WLAN verbunden hatte (auch ohne Internet), lief der Hotspot ab da dauerhaft - inklusive Disconnect.

**Fix:** Neue Funktion `_ensure_wlan_profile_exists()` in [src/gallery/hotspot.py](src/gallery/hotspot.py) wird vor jedem `start_hotspot()` aufgerufen:
- Prueft via `netsh wlan show profiles` ob mind. ein Profil existiert
- Falls nicht: legt offenes, nicht-auto-verbindendes Dummy-Profil "FexoBoothDummy" via `netsh wlan add profile` an (aus Inline-XML, kein File-Dependency)
- Passiert genau EINMAL pro Tablet, ist danach persistent

Zusaetzlich in `start_hotspot()`: Die Erfolgs-Bedingung ignoriert explizit den `NO_PROFILE`-Status, damit der Fallback-Pfad nicht faelschlicherweise als Erfolg gewertet wird.

**Betroffen:** `src/gallery/hotspot.py`

**Wichtig:** Auf bereits deployte Tablets greift der Fix sofort nach dem OTA-Update - kein Handanlegen noetig. Auf diesen Tablets wird beim naechsten Hotspot-Start einmalig das Dummy-Profil angelegt, danach geht alles.

---

### UI: Start-Button wird vom Galerie-Banner abgeschnitten

**Problem:** Bei aktivierter Galerie wurde der START-Button auf dem Start-Screen vom Galerie-Banner ueberlappt. Ursache: Der Start-Button war im `inner_frame` gepackt, der mit `place(rely=0.5, anchor="center")` zentriert wird. Wenn der Inhalt (Titel + Untertitel + Template-Karten + Button) hoeher als das verfuegbare `center_frame` ist, schaut er oben und unten drueber raus - unten in den Galerie-Banner rein.

**Fix in [src/ui/screens/start.py](src/ui/screens/start.py):** Start-Button aus `inner_frame` rausgeloest und direkt ueber dem `gallery_banner` per `pack(side="bottom")` platziert. Der Button kann so nicht mehr vom zentrierten Inhalt verdeckt werden, der zentrierte Bereich schrumpft bei Bedarf.

**Betroffen:** `src/ui/screens/start.py`

---

### Setup: Hotspot-Diagnose- und Auto-Fix-Script

**Problem:** Auf einzelnen (aus dem gleichen Image geklonten) Tablets startet der WLAN-Hotspot nicht. Die Windows-UI zeigt "Ein mobiler Hotspot kann nicht eingerichtet werden, weil Ihr PC keine Ethernet-, WLAN- oder Datenverbindung aufweist." Das ist der Standard-Offline-Fehler und tritt auch bei funktionierenden Boxen auf - das eigentliche Problem liegt tiefer (Treiber-Zustand, ICS-Dienst, Power-Management, Hosted-Network-Support).

**Lösung:** Neues Script [setup/diagnose_hotspot.bat](setup/diagnose_hotspot.bat) (+ `diagnose_hotspot.ps1`):
- Sammelt alle relevanten Infos in ein Log auf dem Desktop (+ FEXODATEN-Stick falls eingesteckt): System-Info, alle Netzwerk-Adapter (inkl. hidden), `netsh wlan show interfaces/drivers`, Hosted-Network-Support, Status von WlanSvc/SharedAccess/icssvc, aktuelle Connection Profiles
- Auto-Fixes: Services starten, Power-Management am WLAN-Adapter deaktivieren, WLAN-Adapter re-enablen, Hosted Network neu konfigurieren, Tethering API als Fallback mit allen Profilen durchprobieren
- Klares Ergebnis am Ende: LAEUFT / LAEUFT NICHT + konkrete nächste Schritte

**Betroffen:** `setup/diagnose_hotspot.bat` (neu), `setup/diagnose_hotspot.ps1` (neu)

---

### Deployment: Clonezilla-Scripts mit Auto-Fixes + persistentem Logging

**Problem:** Beim Aufspielen des Images auf Ziel-Tablets brach Clonezilla bei einigen Lenovos mit "Disk too small" ab. Ursachen waren OEM-Recovery-/"ebackup"-Partitionen auf dem Ziel sowie minimal abweichende Sektorzahlen der eMMC zwischen Herstellerchargen. Ohne Logging war der Fehler nicht nachvollziehbar - das Tablet landete nur stumm im Clonezilla "Choose mode"-Menue.

**Lösung - drei Bausteine:**

1. **Persistentes Logging in [custom-ocs-deploy](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy) und [custom-ocs-capture](deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture):**
   - Gesamte Script- und `ocs-sr`-Ausgabe via `tee` nach `FEXODATEN:\deploy-logs\deploy-YYYYMMDD-HHMMSS.log` (bzw. `capture-logs/` fuer Capture) schreiben
   - Log ueberlebt Reboot → kann am PC im Texteditor gelesen werden
   - `trap cleanup EXIT` garantiert eine Status-Zeile am Ende (ERFOLG / FEHLER + Fehlermeldung)
   - Bei Fehler: grosser ASCII-Banner auf dem Bildschirm mit Log-Pfad + Wartet auf Enter

2. **Auto-Fixes gegen "Disk too small" im Deploy-Script:**
   - **Pre-Wipe**: `sgdisk --zap-all` + `wipefs -a` + `dd` 10 MB Nullen vor dem Restore entfernt alle OEM-GPT-Strukturen und Recovery-Partitionen
   - **`ocs-sr` Flags erweitert**: `-icds` (ignore check disk size) + `-k1` (proportionale Partitionen) statt nur `-e1 auto`
   - **Post-Expand**: `parted resizepart 100%` + `ntfsresize` streckt die C-Partition nach dem Restore automatisch auf die volle Disk-Groesse - egal wie gross C im Image war

3. **Dokumentation:**
   - [deployment/04_tablets-klonen/ANLEITUNG_DEPLOY.md](deployment/04_tablets-klonen/ANLEITUNG_DEPLOY.md) → neuer Abschnitt "Log-Dateien bei Problemen" + erweitertes Troubleshooting
   - [ERKENNTNISSE.md](ERKENNTNISSE.md) → Lessons-Learned Eintrag "Deployment: Clonezilla 'Disk too small' + ebackup/Recovery-Partitionen auf Lenovos"

**Betroffen:** `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-deploy`, `deployment/02_usb-stick-erstellen/custom-ocs/custom-ocs-capture`, `deployment/04_tablets-klonen/ANLEITUNG_DEPLOY.md`, `ERKENNTNISSE.md`

**Wichtig:** Die `custom-ocs-*` Scripts liegen im Projekt-Repo, werden aber beim Ausfuehren vom **USB-Stick** gestartet. Nach diesen Aenderungen muss der USB-Stick neu erstellt werden (`deployment/02_usb-stick-erstellen/prepare_usb_stick.bat` ausfuehren), damit die neuen Scripts auf dem Stick landen.

---

## 2026-04-10

### Bugfix: Drucker wird nicht erkannt wenn an anderem USB-Port
- **Bug:** Canon SELPHY wird von Windows als Kopie registriert wenn er an einem anderen USB-Port angeschlossen wird (z.B. "Canon SELPHY CP1000 (Kopie 1)"). Der in der Config gespeicherte Name "Canon SELPHY CP1000" matcht dann nicht mehr → "DRUCKER FEHLT!"
- **Fix:** Neue `find_matching_printer()` Funktion in `src/printer/__init__.py` die den Basis-Druckernamen vergleicht und "(Kopie N)"/"(Copy N)"-Suffixe ignoriert. Eingebaut an allen Stellen: Druckvorgang (final.py), Drucker-Status-Check (controller.py), Admin-Dropdown (admin.py), System-Test (system_test.py)
- **Betroffen:** `src/printer/__init__.py` (neu), `src/printer/controller.py`, `src/ui/screens/final.py`, `src/ui/screens/admin.py`, `src/ui/dialogs/system_test.py`

### Bugfix: Falsche Kamera benutzt trotz korrekter Auswahl in der UI
- **Bug:** Obwohl im Admin-Panel und Auto-Auswahl nur die Logitech C922 angezeigt wurde, benutzte die App tatsächlich die interne Intel AVStream Camera des Tablets. Ursache: `_get_device_names()` sortierte PnP-Geräte nach `InstanceId` (PCI vor USB), aber OpenCV/DirectShow enumiert in anderer Reihenfolge → Name-zu-Index Mapping war vertauscht
- **Fix:** Neue `_get_dshow_device_names()` Methode nutzt C#/.NET DirectShow COM-Interop (`ICreateDevEnum`, `IEnumMoniker`, `IPropertyBag`) via PowerShell `Add-Type`. Liefert Kameranamen exakt in der OpenCV `CAP_DSHOW` Reihenfolge. Alte PnP-Abfrage bleibt als Fallback (ohne `Sort-Object`)
- **Betroffen:** `src/camera/webcam.py`

---

## 2026-03-27

### Bugfix: Template-Persistenz nach Neustart ohne USB-Stick (Regression)
- **Bug:** Nach App-Neustart ohne USB-Stick wurde das Default-Template angezeigt statt dem gecachten Template der letzten Buchung. Mehrere Ursachen:
  1. `cached_usb_template` wurde beim App-Start nie aus dem Cache geladen (erst in `on_show()`)
  2. `_cache_template_from_usb` im BookingManager suchte nur nach Dateien namens `template.zip` — alle anderen ZIP-Namen wurden ignoriert
  3. `_execute_event_change` setzte `_usb_stick_template` VOR `on_show()` → `on_show()` erkannte das Template als "unverändert" und übersprang `_persist_template_to_disk`
  4. Beim Wiedereinstecken des gleichen Sticks wurde das Template nicht in Memory restauriert
- **Fixes:**
  - `_restore_cached_template()` — lädt `cached_template.zip` VOR UI-Erstellung
  - `_cache_template_from_usb()` — sucht jetzt JEDE gültige Template-ZIP (nicht nur `template.zip`)
  - `_persist_template_to_cache()` — zentrale Methode, wird in `_execute_event_change` und `_load_settings_from_usb_immediately` aufgerufen
  - `_reload_template_from_usb()` — stellt Template bei Stick-Wiedereinstecken sofort wieder her
- **Betroffen:** `src/app.py`, `src/storage/booking.py`

### Feature: Interne Tablet-Kamera wird ignoriert
- **Problem:** Die interne Kamera des Lenovo Miix 310 ist physisch verdeckt. Wenn keine externe Kamera angeschlossen war, fiel die App still auf die interne zurück → Kunde merkte nicht, dass die Logitech fehlt
- **Fix:** `find_best_camera()` gibt jetzt `-1` zurück wenn nur interne Kameras da sind (statt auf `cameras[0]` zu fallen). Der Kamera-Status-Check blinkt "KEINE KAMERA!" wenn `camera_index = -1`
- **Auto-Erkennung:** Wenn im laufenden Betrieb eine externe Kamera angesteckt wird, wird sie automatisch erkannt und aktiviert (periodischer Re-Scan bei `camera_index = -1`)
- **Betroffen:** `src/camera/webcam.py`, `src/app.py`

### Fix: Installer — Cached Template überlebt keine Neuinstallation mehr
- **Bug:** `[InstallDelete]` löschte nur `{app}\.booking_cache`, aber der tatsächliche Cache liegt im PyInstaller-Build unter `{app}\_internal\.booking_cache\` — alte Templates überlebten Neuinstallationen.
- **Fix:** `_internal\.booking_cache` zu `[InstallDelete]` und `[UninstallDelete]` hinzugefügt. `.booking_cache` aus `[Dirs]` entfernt (wird erst im Produktionsbetrieb vom Code erstellt).
- **Betroffen:** `installer.iss`

---

## 2026-03-26

### Bugfix: Installer löscht jetzt Statistiken und Druckerzähler bei Neuinstallation
- **Bug:** Bei Neuinstallation via .exe blieben alte `fexobooth_statistics.json` und `printer_lifetime.json` bestehen → Events und Druckerzähler nicht bei 0
- **Fix:** `[InstallDelete]` Sektion in `installer.iss` ergänzt — löscht Statistik- und Lifetime-Dateien sowohl im App-Root als auch in `_internal/` vor der Installation. Auch `[UninstallDelete]` um diese Dateien erweitert
- **Betroffen:** `installer.iss`

### Bugfix: PIN-Eingabe für Drucker-Zähler-Reset funktioniert jetzt
- **Bug:** Der PIN-Dialog zum Zurücksetzen des Druckerzählers im Admin-Panel hatte keinen Numpad → auf dem Tablet ohne physische Tastatur war keine Eingabe möglich
- **Fix:** Virtuellen Numpad (0-9, ⌫, ✓) zum Reset-Dialog hinzugefügt, identisch zum Haupt-PIN-Dialog. Auto-Submit bei 4 Zeichen, Tastatur-Support über KeyRelease
- **Betroffen:** `src/ui/screens/admin.py` (`_reset_printer_lifetime`)

### Feature: Testdruck-Button im Admin-Panel
- **Neu:** Im Druck-Tab gibt es jetzt einen "Testdruck starten" Button
- **Funktion:** Lädt das aktuelle Template, erzeugt farbige Platzhalter-Bilder mit "TEST 1/2/3..." Text, rendert das Template und druckt es über GDI — ohne dass vorher Fotos gemacht werden müssen
- **Fallback:** Wenn kein Template konfiguriert ist, wird das Default-Template verwendet
- **Betroffen:** `src/ui/screens/admin.py` (`_create_print_tab`, `_execute_test_print`)

### Fix: NOCHMAL-Button vom Final-Screen entfernt
- **Bug:** Auf dem Druck-Screen konnte man "NOCHMAL" drücken und kam zurück zum Start — unerwünscht
- **Fix:** Button und `_on_redo()` Methode komplett entfernt. User kann nur noch drucken oder warten bis Auto-Return
- **Betroffen:** `src/ui/screens/final.py`

### Feature: Strom-Symbol blinkt wenn kein Netzteil angeschlossen
- **Vorher:** Bei Akkubetrieb wurde nur ein oranges ⚡-Symbol angezeigt — leicht zu übersehen
- **Nachher:** Ohne Strom blinkt ⚡ rot/gelb abwechselnd (1,5s). Mit Strom einfach grüner Blitz
- **Betroffen:** `src/app.py` (`_check_power_status`)

### Feature: Echte Kamera-Gerätenamen + Logitech-Priorisierung
- **Vorher:** Kamera-Dropdown zeigte nur "Webcam 0", "Webcam 1" etc. — kein Unterschied zwischen Logitech und interner Kamera erkennbar
- **Nachher:** Echte Gerätenamen via WMI/PowerShell (z.B. "Logitech C920", "Integrated Webcam") mit Auflösung
- **Auto-Auswahl:** Beim App-Start wird automatisch die beste Kamera gewählt: Logitech > externe USB-Kamera > interne Kamera. Nur wenn camera_type "webcam" ist (nicht bei DSLR)
- **Betroffen:** `src/camera/webcam.py` (`_get_device_names`, `list_cameras`, `find_best_camera`), `src/ui/screens/admin.py` (`_get_available_cameras`), `src/app.py` (Startup)

### Fix: Druck-Zoom jetzt zentriert statt oben-links
- **Bug:** Beim Erhöhen des Zoom-Werts dehnte sich das Druckbild nur nach rechts und unten aus → manuelles Nachkorrigieren mit Offset X/Y nötig
- **Fix:** Zoom-Offset wird jetzt automatisch so berechnet, dass sich das Bild gleichmäßig nach allen Seiten ausdehnt (zentrierter Zoom). Der manuelle Offset wirkt zusätzlich zur Zentrierung
- **Betroffen:** `src/ui/screens/final.py` (`_print_image`), `src/ui/dialogs/system_test.py` (`_print_via_gdi`), `src/ui/screens/admin.py` (Testdruck)

---

## 2026-03-18

### USB-Sync Dialog: Kommt jetzt zuverlässig bei Stick-Wiedereinstecken
- **Bug:** Gleichen USB-Stick abziehen → Fotos machen → wieder einstecken → kein Sync-Dialog obwohl Bilder fehlen
- **Ursache:** `_offer_sync_dialog()` zählte fehlende Bilder in Background-Thread ohne try/except. Bei jeder Exception (USB noch nicht fertig gemounted, IO-Fehler) starb der Thread leise — kein Dialog, kein Log, kein Retry
- **Fix 1:** try/except im Background-Thread mit Logging bei Fehler
- **Fix 2:** Fallback auf `pending_count` — wenn `count_missing()` 0 oder Exception zurückgibt aber Pending-Files existieren, wird der Dialog trotzdem angezeigt (`max(missing, pending_count)`)
- **Fix 3:** Logging bei USB-Transition (da→weg, weg→da) mit new_booking und pending-Status für Debugging
- **Betroffen:** `src/app.py` (`_check_usb_status`, `_offer_sync_dialog`)

---

## 2026-03-17

### prepare_image.bat: Tablet für Clonezilla-Image vorbereiten
- **Neues Script:** `deployment/01_referenz-tablet/prepare_image.bat` — Alles-in-einem Script für Image-Vorbereitung
- **Teil 1 — Dienste deaktivieren (25+):** Windows Update (komplett), Windows Search, SysMain/Superfetch, Windows Defender, Telemetrie (DiagTrack, dmwappushservice), Error Reporting, Xbox-Dienste, Maps, Bluetooth, Biometrie, Remote Registry, Fax, Windows Insider, Connected User Experiences
- **Teil 2 — Registry-Optimierungen:** Telemetrie aus, Cortana aus, visuelle Effekte auf Performance, Transparenz aus, Benachrichtigungen aus, Tips/Tricks/vorgeschlagene Apps aus, Hintergrund-Apps aus, OneDrive aus, Sperrbildschirm-Werbung aus, automatische Wartung aus, Storage Sense aus, Energiesparmodus (nie Standby/Bildschirm-Aus), Ruhezustand deaktiviert (spart ~3GB), Schnellstart aus, Defender per Policy aus, geplante Tasks (Defrag, Diagnose, CEIP) aus
- **Teil 3 — FexoBooth bereinigen:** BILDER/Single und Prints geleert, logs/ geleert, .booking_cache/ geleert, statistics.json und printer_lifetime.json gelöscht, gallery_cache/ gelöscht
- **Teil 4 — Windows Temp bereinigen:** User-Temp, Windows-Temp, Prefetch, Windows Update Cache, Thumbnail/Icon-Cache, Papierkorb, Delivery Optimization Cache, Event-Logs, automatische Datenträgerbereinigung (cleanmgr)
- **Installer:** Script wird über `installer.iss` nach `{app}\deployment\` installiert + Startmenü-Eintrag "Image vorbereiten"
- **Auch mitinstalliert:** `post_install_check.bat` zur Verifizierung vor dem Klonen

---

## 2026-03-13

### Start-Screen: Template-Karten-Text verbessert
- **Bug:** Template-Karte zeigte rohen Dateinamen (z.B. Buchungsnummer "134830_...") statt freundlichen Namen
- **Fix:** Aktive Template-Karte zeigt immer "Wunsch-Template"
- **Verbesserung:** Bei nur einer Karte (nichts zu wählen): Header wechselt von "Wähle dein Layout!" zu "Dein Druckformat" / "Tippe zum Starten"
- **Betroffen:** `src/ui/screens/start.py`

### USB-Template vs. User-Template Trennung
- USB-Stick Template wird automatisch geladen, aber User-Auswahl über PIN 2015 wird respektiert
- `_usb_stick_template` speichert Original vom Stick, `_user_template_override` Flag bei expliziter Wahl
- USB-Template bleibt als Extra-Karte wählbar wenn User anderes Template gewählt hat

### Capture-Hintergrund: Schwarz → Weiß
- Default-Hintergrund im TemplateRenderer von `#000000` auf `#FFFFFF` geändert
- Templates ohne Overlay-Frame rendern Fotos jetzt vor weißem Hintergrund

### LiveView Template-Overlay Absicherung
- Try/Except um Template-Overlay im LiveView gegen Freeze bei fehlenden Attributen

---

## 2026-03-12

### Template-Loader: preview.png nicht mehr als Overlay verwenden
- **Bug:** Default-Template.zip enthielt nur `preview.png` (Vorschaubild mit Nummern 1-4), kein `template.png`
- **Ursache:** Loader wählte größtes PNG als Overlay → `preview.png` wurde über die Fotos gelegt und verdeckte sie
- **Fix:** PNG-Auswahl-Logik komplett überarbeitet:
  1. `template.png` wird bevorzugt (exakter Name)
  2. Andere PNGs (nicht preview) als Fallback
  3. `preview.png` wird NIE als Overlay verwendet wenn XML-Boxen vorhanden sind
  4. Templates ohne Overlay-Frame rendern korrekt (nur Fotos in Boxen)
- **Betroffen:** `src/templates/loader.py`, `src/ui/screens/start.py`, `src/ui/screens/admin.py`

### Start-Screen Refresh nach Template-Wechsel im Kunden-Menü
- **Bug:** Template über PIN 2015 gewechselt → Startscreen zeigte noch altes Template-Bild
- **Ursache:** `on_show()` wurde nur bei Admin-Settings aufgerufen (wenn `dialog.result` gesetzt), nicht nach Kunden-Menü
- **Fix:** Start-Screen wird IMMER nach AdminDialog-Schließung aktualisiert (auch nach PIN 2015)
- **Betroffen:** `src/app.py` (Admin-Dialog Nachbehandlung)

### Galerie: Foto-Sharing verbessert
- **Bug:** Web Share API `files`-Parameter wird auf HTTP stumm ignoriert (braucht HTTPS)
- **Fix:** Erkennung ob File-Sharing wirklich funktioniert (`canShare` mit Test-File)
- Bei HTTP: Hinweis "Erst Bild speichern, dann aus Galerie teilen" + WhatsApp/Facebook nur-Text-Fallback
- Bei HTTPS/nativem Support: Vollständiges File-Sharing mit Bild
- **Betroffen:** `src/gallery/server.py`

### Template-Cache und Overlay-Handling
- Template-Cache speichert jetzt auch Templates ohne Overlay (nur Boxen)
- `cached_usb_template` funktioniert korrekt mit `overlay=None`
- Start-Screen Preview: Lädt `preview.png` aus ZIP für Karten-Vorschau (getrennt vom Overlay)

---

## 2026-03-11

### Kunden-PIN Menü (PIN 2015)
- **Neues Feature:** Kunden können über PIN "2015" ein Service-Menü öffnen (ohne Admin-Zugang)
- **4 Optionen:**
  1. **Template wählen** — Zeigt Default-Template, konfigurierte Templates und USB-Template zur Auswahl
  2. **Live-View Overlay ein/aus** — Toggle für `liveview_template_overlay`, speichert sofort in Config
  3. **Druckstau beheben** — Stoppt/Startet Windows Print Spooler (behebt Druckerwarteschlange)
  4. **Windows Neustart** — Mit Bestätigungs-Dialog und Wartehinweis
- **Entfernt:** 5x Icon-Tap für Neustart (durch Kunden-PIN ersetzt)

### Filter-Screen optimiert für Lenovo Miix 310
- **Filter-Labels entfernt** auf kleinen Screens (mehr Platz für Vorschau-Thumbnails)
- **Subtitle-Text entfernt** auf kleinen Screens ("Tippe auf einen Filter...")
- **Vorschau-Titel entfernt** auf kleinen Screens ("📸 Vorschau")
- **Spalten-Gewichtung angepasst**: Filter-Grid bekommt weniger Platz (1:3 statt 2:3)
- **Preview-Auflösung erhöht**: max_preview_size jetzt 500 für alle Screens

### Template-Auswahl mit Vorschau-Bildern
- **Kunden-Menü Template-Auswahl** zeigt jetzt Vorschau-Bilder aus den ZIP-Dateien
- **Template-Ordner:** `assets/templates/` — einfach weitere ZIP-Dateien ablegen, werden automatisch erkannt
- **Build:** Ordner wird über `("assets", "assets")` automatisch in die EXE eingebaut
- **Preview:** Extrahiert `template.png` (oder erstes PNG) als Thumbnail aus jeder ZIP

### Admin-Dialog: Kiosk-Modus ohne Fensterwechsel
- **Problem:** Beim Öffnen der Einstellungen wechselte die App kurz in den Fenstermodus → Taskleiste blitzte auf, Fenster sprang
- **Lösung:** Im Kiosk-Modus bleibt alles fullscreen. PIN-Dialog, Kunden-Menü UND Admin-Einstellungen werden als Overlay innerhalb des Vollbildschirms angezeigt
- **Neuer Parameter:** `AdminDialog(parent, config, kiosk_mode=True)` — steuert ob Einstellungen als Fenster oder Fullscreen-Overlay dargestellt werden
- **Minimieren-Button:** Im Kiosk-Modus gibt es einen "Minimieren"-Button in den Admin-Einstellungen (zeigt Taskleiste, minimiert Dialog)
- **Taskleiste:** Wird beim Minimieren eingeblendet, beim Wiederherstellen automatisch versteckt

### USB-Status-Indikator: Feste Breite
- **Fix:** USB-Badge änderte Größe je nach Text ("USB OK" vs "⚠️ USB FEHLT! [13]") → Blitz-Icon sprang
- **Lösung:** Label in festem CTkFrame-Container (160x28, `pack_propagate(False)`)

---

## 2026-03-09

### Drucker-Steuerung: Software-Reset + Fehlermeldungen ersetzen
- **Neues Feature:** Drucker-Fehler werden jetzt mit eigenem Fullscreen-Overlay angezeigt statt Windows/Canon-Dialoge in den Vordergrund zu bringen
- **Canon-Dialog-Unterdrückung:** Canon SELPHY Fehlerdialoge werden automatisch geschlossen, eigene Meldungen übernehmen
- **Zwei Modi:**
  - **Papierstau:** Automatischer 3-stufiger Reset (Purge → Spooler Restart → USB Device Restart) mit Lade-Animation. Blockiert Bedienung bis behoben
  - **Verbrauchsmaterial (Papier/Tinte leer):** Blockierendes Overlay "Bitte Papier/Tinte nachfüllen". Verschwindet NUR wenn Drucker wieder OK meldet (Polling alle 3s)
- **Dev-Mode Button:** "DRUCKER RESET" Button in der Top-Bar zum Testen des Reset-Ablaufs
- **Neue Dateien:**
  - `src/printer/__init__.py` + `src/printer/controller.py` (PrinterController: Reset-Eskalation, Dialog-Unterdrückung, Status-Abfrage)
  - `src/ui/dialogs/printer_error.py` (PrinterErrorOverlay: Blockierendes Vollbild-Overlay)
- **Refactoring:** `_check_print_jobs()`, `_detect_canon_error_window()`, `_bring_printer_dialog_to_front()` aus `app.py` in `PrinterController` ausgelagert
- **Bugfix (Real-Hardware-Test):**
  - Canon-Dialog-Text per `WM_GETTEXT` statt `GetWindowTextW` lesen (Canon-Controls antworten nicht auf GetWindowTextW)
  - Alle Child-Controls enumerieren, längsten Text als Fehlermeldung verwenden
  - Falls Text nicht lesbar: sicher als "KEIN PAPIER / KASSETTE!" (consumable) behandeln
  - Canon-Dialog NICHT schließen wenn Overlay aktiv (Dialog = einziger Fehlerindikator beim SELPHY!)
  - Reset immer alle 3 Stufen durchlaufen (SELPHY setzt keine Spooler-Status-Flags)
  - Overlay: periodisches `lift()` + `focus_force()` gegen Canon-Dialog Focus-Stealing
  - Umfangreiches Debug-Logging für alle Drucker-Operationen

### Export-Dialog blockierte UI (Boot-Drives + grab_set)
- **Export-Dialog blockierte UI**: D:\ (SD-Karten-Slot im Miix 310) wurde als "unbekannter USB-Stick" erkannt → Export-Dialog mit `grab_set()` blockierte gesamte Interaktion. Fixes: (1) Boot-Drives werden beim Start erfasst und für Export ignoriert, (2) 15s Grace Period nach Boot, (3) Export-Dialog ohne `grab_set()` (non-blocking), (4) Abgezogene Boot-Drives werden aus Ignorier-Liste entfernt.

### ZIP-Validierung, Default-Template, Freeze-Fix, Encoding (2026-03-10 continued)
- **ZIP-Validierung**: Template-Loader und `find_usb_template()` erkennen jetzt Anwendungs-ZIPs (mit .exe, .dll, `_internal/`). Solche ZIPs werden abgelehnt. Das verhindert, dass fexobooth.zip (das Installationspaket) als Template interpretiert wird.
- **Default-Template.zip**: `create_default_template()` lädt jetzt `assets/Default-Template.zip` statt programmatisch ein 2x2-Grid zu generieren. ZIP ist bereits über `("assets", "assets")` im Build enthalten. Ergebnis wird gecacht.
- **Freeze-Ursache gefunden**: 41-Sekunden-Freeze beim Rendern des finalen Bildes — Ursache: USB-Stick enthielt `fexobooth.zip` (Anwendungspaket statt Template), Loader nahm Logo-PNG (6889x6889) als Overlay → Compositing dauerte 41s auf Miix 310. Fix: ZIP-Validierung.
- **PowerShell Encoding**: `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` zu allen PowerShell-Subprocess-Aufrufen hinzugefügt (behebt `durchgef�hrt` → `durchgeführt`)

### Drucker-Steuerung: Kritische Bugfixes (2026-03-10)
- **Fix: `win32timezone` fehlte im PyInstaller-Build** — `EnumJobs` Level 2 braucht `win32timezone` für DateTime-Felder. JEDER Job-Queue-Check schlug im Build fehl (`No module named 'win32timezone'`). Drucker-Fehler bei aktiven Druckjobs wurden NIE erkannt!
  - Fix 1: `win32timezone` als `hiddenimport` in `fexobooth.spec`
  - Fix 2: `EnumJobs` mit Level 1 statt Level 2 (hat kein DateTime, braucht kein `win32timezone`)
- **Fix: Canon-Dialog-Erkennung findet jetzt auch versteckte Fenster** — `_detect_canon_error_window()` prüfte nur `IsWindowVisible()`. Fenster die wir per `SW_HIDE` versteckt hatten, wurden danach nicht mehr erkannt. Jetzt werden ALLE Fenster (sichtbar + versteckt) geprüft
- **Fix: `close_canon_dialogs()` findet jetzt versteckte Fenster** — Cleanup nach Overlay-Schließen fand versteckte Canon-Dialoge nicht
- **Cleanup: Debug-Spam für Child-Controls entfernt** — Jeder Child-Control-Scan loggte Klasse + Textlänge → massiver Log-Spam

### Collage: Nochmal + Weiter Buttons nach jedem Foto
- **Neues Verhalten:** Bei Collagen (>1 Foto) wird nach jedem Foto eine schwarze Button-Leiste am unteren Bildschirmrand eingeblendet
- **Buttons:** "↻ NOCHMAL" (rot, wiederholt das letzte Foto) + "WEITER →" (grün, geht zum nächsten Foto)
- **Timeout:** Leiste bleibt 60 Sekunden sichtbar, danach automatisch weiter zum nächsten Foto
- **Design:** Schwarze Leiste über volle Breite löst Transparenz-Problem. `tk.Frame` statt `CTkFrame` (CTk place/lift/z-order unzuverlässig)
- **Betrifft:** `session.py` (_setup_ui, _show_redo_button, _on_continue_photo)

### Template-Overlay: Default ON + kein Vollbild-Flicker beim Start
- **Default geändert:** `liveview_template_overlay` ist jetzt `True` (statt False)
- **Fix:** Template-Cache wird SYNCHRON aufgebaut bevor LiveView startet (kein kurzer Vollbild-Kamera-Blitz mehr)
- **Lade-Anzeige:** Während Webcam-Capture wird 📸 Emoji statt leerer Bildschirm gezeigt

### Fix: Webcam Buffer-Flush optimiert (grab statt read)
- **Problem:** `get_high_res_frame()` brauchte ~3-5s für Auflösungsumschaltung
- **Optimierung:** `cap.grab()` statt `cap.read()` für Buffer-Flush (grab dekodiert nicht), 2 statt 5/3 Flush-Frames
- **Betrifft:** `webcam.py` (get_high_res_frame), `session.py` (_capture_photo)

### Template-Overlay im LiveView (optional, Admin-Menü)
- **Neues Feature:** LiveView kann jetzt das Template als Overlay anzeigen, sodass der Kamera-Feed direkt an der Stelle positioniert wird, wo das Foto im Template landen wird
- **Konfigurierbar:** Neue Checkbox "Template im LiveView anzeigen" im Admin-Menü (Kamera-Tab). Standard: deaktiviert (Performance)
- **Funktionsweise:**
  - Template-Overlay wird einmalig beim Session-Start auf Display-Größe skaliert und gecacht
  - Bereits aufgenommene Fotos werden in ihren jeweiligen Boxen angezeigt
  - LiveView-Feed wird in die aktuelle Foto-Box eingesetzt (Cover-Modus)
  - Template-Rahmen wird als RGBA-Overlay darüber gelegt
  - Countdown wird über das Gesamtbild gerendert
- **Performance:** BILINEAR-Resampling statt LANCZOS für schnelles Scaling, Cache wird bei on_hide freigegeben
- **Hintergrund:** Feature war früher Standard (vor 2026-02-09) und wurde für Performance entfernt. Jetzt als Option zurück

---

## 2026-03-03

### KRITISCH: Canon DSLR Freeze bei Host-Download behoben (App friert ein)
- **Problem:** Canon EOS 2000D ohne SD-Karte → App friert ein. Sowohl beim Session-Start als auch beim Capture-Screen. Kamera löst nicht aus
- **Ursache:** `EdsSetObjectEventHandler` (EDSDK DLL) deadlockt - der DLL-Call kehrt nie zurück, registriert aber den Handler trotzdem (Events feuern nach ~150ms). EDSDK nutzt intern COM (STA)
- **Finaler Fix:** `set_object_event_handler()` in `edsdk.py`:
  1. DLL-Call in daemon Background-Thread (kehrt evtl. nie zurück - bekanntes Verhalten)
  2. Hauptthread pumpt 500ms Windows-Messages (reicht für Handler-Registrierung)
  3. Danach: Handler gilt als registriert, egal ob DLL returned (Events funktionieren)
  4. Daemon-Thread bleibt im Hintergrund, wird bei App-Exit automatisch beendet
- **Bonus-Fixes:**
  - `CFUNCTYPE` → `WINFUNCTYPE` für EDSDK Callback (korrekte Calling-Convention `__stdcall`)
  - Handle-Leak in `_check_camera_status()` gefixt: Kamera-Refs von `list_cameras()` werden nach dem Check freigegeben

### Fix: Canon EOS 2000D sendet falsches Event (0x208 statt 0x108)
- **Problem:** DSLR-Fotos kamen nie an (10s Timeout), Flash-Bild blieb ~10s sichtbar, bei Collagen fielen Fotos 3-4 aus (kein Auslösegeräusch mehr)
- **Ursache:** Canon EOS 2000D sendet bei Host-Download Event `0x00000208` (DirItemRequestTransfer_Alt) statt Standard `0x00000108`. Der Event-Handler erkannte dieses Event nicht → Bilder wurden nie heruntergeladen → 10s Timeout → LiveView-Fallback. Nach mehreren ignorierten Transfer-Events sendete die Kamera `0x00000301` (Shutdown) → alle weiteren EDSDK-Calls schlugen mit Fehler 0x61 fehl
- **Fix 1: Event-Handler erweitert** - `_on_object_event()` in `canon.py` erkennt jetzt `0x208` UND `0x108` als Download-Trigger. Zusätzlich wird `0x100` (DirItemCreated) als Fallback für andere Kamera-Modelle behandelt
- **Fix 2: Flash-Timing entkoppelt** - Flash wird jetzt am Anfang von `_capture_photo()` ausgeschaltet (mit `update_idletasks()` GUI-Redraw), BEVOR der blockierende Capture startet. Vorher blieb der Flash während des gesamten Capture-Timeouts sichtbar
- **Fix 3: Kamera-Recovery bei Shutdown** - Wenn Kamera `0x301` (Shutdown) sendet, wird dies erkannt und beim nächsten `capture_photo()` automatisch die Session geschlossen und neu geöffnet (Event-Handler wird neu registriert)

### Performance: Session-Start massiv beschleunigt (7s → <1s)
- **Problem:** Nach jedem Video dauerte es 7 Sekunden bis der LiveView erschien (5.5s Kamera-Init + 1.5s LiveView-Start)
- **Ursache 1:** `reset_session()` gab die Kamera komplett frei → bei jeder neuen Session musste die gesamte EDSDK-Initialisierung neu durchlaufen werden (Session öffnen, SaveTo setzen, Event-Handler registrieren)
- **Ursache 2:** Event-Handler Timeout war 5s (jetzt 500ms, da Handler nach ~150ms funktioniert)
- **Fix 1: Kamera-Persistenz** - `reset_session()` gibt Kamera nicht mehr frei, nur LiveView wird gestoppt. `session.on_show()` prüft `is_initialized` und überspringt Neuinitialisierung
- **Fix 2: Kamera-Vorinitialisierung** - Wenn `play_video("video_start")` abgespielt wird, startet die Kamera-Init bereits nach 200ms parallel (VLC spielt in eigenem Thread weiter). Wenn das Video endet, ist die Kamera bereits bereit
- **Ergebnis:** Erste Session: Init während Video (~1s, unsichtbar). Folge-Sessions: 0s Init (Kamera bleibt aktiv)

---

## 2026-02-26

### Fix: Taskleiste verschwindet permanent nach App-Crash
- **Problem:** Wenn die App abstürzte oder per Force-Kill beendet wurde, blieb die Windows-Taskleiste permanent versteckt (`ShowWindow(SW_HIDE)` ist persistent). User musste Registry oder Explorer-Neustart machen um Taskleiste zurückzubekommen
- **Lösung:**
  1. **`atexit`-Handler** in `app.py`: `atexit.register(self._restore_taskbar_safe)` - fängt saubere Python-Exits ab
  2. **Recovery beim App-Start** in `main.py`: `_recover_taskbar()` wird VOR dem App-Start aufgerufen - stellt Taskleiste wieder her falls vorheriger Lauf gecrasht ist
  3. **Global Exception Handler** in `main.py`: Stellt Taskleiste auch bei unbehandelten Exceptions wieder her
- **Ergebnis:** Taskleiste wird jetzt in 3 Schichten geschützt - selbst nach hartem Crash wird sie beim nächsten App-Start wiederhergestellt

### Canon DSLR: Host-Download wiederhergestellt (Kamera funktioniert ohne SD-Karte)
- **Kontext:** Host-Download wurde vorher entfernt weil die App hing. Das Hängen war aber der EDSDK-Deadlock (jetzt gefixt), nicht der Host-Download selbst
- **Lösung:** Host-Download wiederhergestellt mit verbessertem Logging:
  - MIT SD-Karte: Directory-Polling (wie bisher, zuverlässigster Modus)
  - OHNE SD-Karte: Host-Download via Event-Handler (Bild wird via USB zum Tablet übertragen)
  - Kamera löst in BEIDEN Modi richtig aus (Autofokus, Spiegel, Shutter)
- **System-Test nutzt jetzt explizit LiveView** (braucht keine SD-Karte, ist schneller)
- **LiveView-Fallback** hat jetzt Retry-Logik (bis 10 Versuche mit 300ms Pause)
- **Kamera-Status** zeigt nur Kamera-Verbindung an, nicht SD-Karten-Status

### KRITISCH: EDSDK Deadlock behoben (System-Test hing, Tablet musste hart ausgeschaltet werden)
- **Problem:** `_check_camera_status()` rief `list_cameras()` (= EDSDK DLL-Aufrufe) vom UI-Thread auf, während gleichzeitig der System-Test-Thread EDSDK für `capture_photo()` nutzte. EDSDK ist NICHT thread-safe (Windows COM STA) → **Deadlock** → App komplett eingefroren, Ctrl+Shift+Q funktionierte nicht wegen `grab_set()` im Dialog
- **Fix 1:** `_check_camera_status()` prüft jetzt `is_initialized` ZUERST. Wenn Kamera aktiv ist (Session offen), werden KEINE EDSDK-Aufrufe vom UI-Thread gemacht
- **Fix 2:** System-Test hat jetzt **globalen Timeout** (90s) und **Abbrechen-Button**. Bei Timeout wird Kamera freigegeben und Fehler angezeigt
- **Fix 3:** `Ctrl+Shift+Q` funktioniert jetzt in ALLEN Dialogen mit `grab_set()` (System-Test, Event-Wechsel, Backup, Admin, Service, USB-Sync, Export). Jeder Dialog hat eigenen Keyboard-Binding

### Kamera-Status-Anzeige in der Top-Bar
- **Neu:** Blinkende Kamera-Warnung in der Top-Bar (📷 KEINE KAMERA!) wenn keine Kamera erreichbar
- Prüft Canon DSLR (via EDSDK `get_camera_list()`) und Webcam (via OpenCV `VideoCapture`)
- **WICHTIG:** Überspringt EDSDK-Check wenn Kamera bereits initialisiert (verhindert Deadlock!)
- Blinkend Rot/Gelb wie USB- und Drucker-Warnung, verschwindet wenn Kamera OK
- Prüfintervall: 2s bei Problem, 15s wenn OK

### Canon DSLR: Funktioniert jetzt auch ohne SD-Karte
- **Problem:** Auf einer echten Fotobox schlug der System-Test fehl weil die Canon EOS 2000D keine SD-Karte hatte. `SaveTo=Camera` setzte die Kamera auf SD-Karten-Speicherung, aber `wait_for_new_image()` fand keinen DCIM-Ordner → Foto-Capture komplett fehlgeschlagen
- **Lösung:** Automatische Erkennung ob SD-Karte vorhanden ist:
  1. Bei `initialize()`: SaveTo Camera setzen, dann DCIM-Ordner prüfen
  2. Wenn DCIM fehlt: Automatisch auf `SaveTo Host` umschalten + Event-Handler registrieren
  3. `capture_photo()` unterstützt jetzt zwei Modi:
     - **Directory-Polling** (mit SD): Wie bisher, pollt DCIM-Ordner
     - **Host-Download** (ohne SD): Bild kommt direkt via EDSDK Event-Handler über die Photo-Queue

### Kiosk-Modus: Permanentes topmost entfernt (kritischer Fix)
- **Problem:** Permanentes `-topmost=True` blockierte ALLE Fenster - auch eigene App-Dialoge (USB-Sync, Export, Event-Wechsel). App wurde unbedienbar wenn ein Dialog hinter dem Hauptfenster landete. Selbst Task-Manager konnte nicht in den Vordergrund
- **Lösung:** Drei-Säulen-Kiosk-Modus statt aggressivem topmost:
  1. **Taskleiste verstecken:** `_hide_taskbar()`/`_show_taskbar()` via Windows API bleibt (wird alle 5s re-assertet)
  2. **Windows-Benachrichtigungen unterdrücken:** Neue `_suppress_notifications()` Methode deaktiviert Windows-Toasts via Registry (`NOC_GLOBAL_SETTING_TOASTS_ENABLED`)
  3. **topmost nur kurz:** `-topmost=True` wird nur 500ms beim Fenster-Positionieren gesetzt, dann sofort wieder entfernt
- **Notfall-Shortcut:** `Ctrl+Shift+Q` beendet die App sofort (auch im Kiosk-Modus), stellt Taskleiste und Benachrichtigungen wieder her
- **Entfernt:** topmost Re-Assertion in `_check_fullscreen_restore()` (war Ursache des Problems)
- **Alle Exit-Pfade** stellen jetzt Benachrichtigungen wieder her: `quit()`, `_emergency_quit()`, `_quit_app()` im Admin

---

## 2026-02-25

### Kiosk-Modus: Echte Vollbildsicherung
- **Fix:** Taskleiste blieb nach Admin-Dialog sichtbar - Fullscreen wurde nie korrekt wiederhergestellt
- **Ursache 1:** `show_admin_dialog()` hat nach Dialog-Schluss KEINEN `_enter_fullscreen()` Aufruf - verließ sich auf 10s-Timer der oft versagte
- **Ursache 2:** `_set_appwindow()` machte `withdraw()/deiconify()` Zyklus - in den 10ms konnte die Taskleiste den Fokus grabben
- **Ursache 3:** `-topmost` wurde nach 100ms wieder entfernt - Windows-Meldungen (USB etc.) konnten in den Vordergrund poppen
- **Lösung:** Komplett überarbeiteter Kiosk-Modus:
  1. **Taskleiste verstecken:** Neue `_hide_taskbar()`/`_show_taskbar()` via Windows API (`FindWindowW("Shell_TrayWnd")` + `ShowWindow`)
  2. **Sofortige Wiederherstellung:** `show_admin_dialog()` ruft `_enter_fullscreen()` direkt nach Dialog-Schluss auf (200ms Delay)
  3. **Escape/F11 blockiert:** Im Kiosk-Modus (`start_fullscreen=True`) kann Vollbild NUR über Admin-PIN verlassen werden
  4. **Sicherheitsnetz:** `_check_fullscreen_restore()` prüft alle 5s (statt 10s) und re-assertet Taskleiste
  5. **Kein withdraw/deiconify:** `_set_appwindow()` entfernt aus `_enter_fullscreen()` (verursachte den Bug)
  6. **Taskleiste bei App-Exit:** `quit()` und `_quit_app()` stellen Taskleiste wieder her
- **Bug Fix:** Service-PIN Dialog hat Fullscreen nie wiederhergestellt (`return` vor Restore-Code)
- **Bereinigt:** Redundanter `parent_window.overrideredirect(False)` Code im Admin-Dialog entfernt

### USB-Dialoge: Vordergrund + Auto-Close
- **Fix:** USB-Sync und Export-Dialoge landeten manchmal hinter dem Hauptfenster (unerreichbar, App blockiert)
- **Ursache:** Dialoge nutzten `transient()`, `lift()`, `focus_force()` nicht - bei topmost-Hauptfenster kamen sie nicht nach vorne
- **Lösung 1:** Beide Dialoge erzwingen jetzt Vordergrund: `transient(self.root)` + `lift()` + `focus_force()`
- **Lösung 2:** Auto-Close nach Kopiervorgang - kein OK-Button mehr nötig:
  - Erfolg: Dialog schließt automatisch nach 3 Sekunden
  - Fehler/Abbruch: Dialog schließt automatisch nach 4 Sekunden
- Betrifft: `_show_sync_dialog()` und `_show_export_dialog()` in `app.py`

### Konsolenfenster versteckt
- **Fix:** `start_fexobooth.bat` öffnete ein sichtbares Terminal-Fenster das beim Admin-Dialog zum Vorschein kam
- **Lösung 1:** `_hide_console_window()` in `main.py` - versteckt Konsole via `GetConsoleWindow()` + `ShowWindow(SW_HIDE)` beim App-Start (nur Produktion, nicht im Dev Mode)
- **Lösung 2:** BAT nutzt `pythonw` statt `python`, `pause` entfernt
- **Neue Datei:** `start_fexobooth_debug.bat` - Developer-Variante mit sichtbarer Konsole + `--dev` Flag

### Final-Screen: Template-Vorschau vollständig sichtbar
- **Fix:** Template/Druck-Vorschau wurde unten abgeschnitten (ging über Bildschirmrand)
- **Ursache:** `thumbnail()` nutzte die volle Container-Höhe, aber die Overlay-Buttons (DRUCKEN etc.) überdeckten die unteren 20%
- **Lösung:** Sichtbare Höhe auf 78% begrenzt (`visible_h = int(container_h * 0.78)`) - Template ist jetzt vollständig über den Buttons sichtbar

### Drucker-Lifetime-Zähler
- **Neues Feature:** Zählt die Gesamtanzahl aller Drucke über die Lebensdauer eines Druckers
- **Anzeige:** Neuer Bereich "🖨️ Drucker-Lifetime" im Statistik-Tab des Admin-Menüs
- **Persistenz:** Eigene Datei `printer_lifetime.json` - wird NICHT durch Event-Wechsel oder Statistik-Reset zurückgesetzt
- **Reset:** Nur über Service-PIN (6588) im Admin-Menü möglich (PIN-Abfrage im Dialog)
- **Zählung:** Jeder erfolgreiche Druck (auch Testdrucke) zählt hoch
- **Neue Datei:** `src/storage/printer_lifetime.py` (Singleton, JSON-Speicherung)
- **PyInstaller:** `src.storage.printer_lifetime` als Hidden Import in `fexobooth.spec` ergänzt

---

## 2026-02-12

### Deployment-System (Tablet-Klonen)
- **Neuer Ordner:** `deployment/` mit komplettem Klon-System für 200 Tablets
- **Ansatz:** Clonezilla-basiert (kein Sysprep nötig, kein Windows ADK)
- **Workflow:** Referenz-Tablet einrichten → Image erstellen → auf Ziel-Tablets klonen
- **Enthält:**
  - Schritt-für-Schritt Anleitungen (Deutsch, anfängerfreundlich)
  - `post_install_check.bat` — Prüft ob Referenz-Tablet bereit ist
  - `create_usb.bat` — Lädt Clonezilla + Rufus herunter
  - Clonezilla custom-ocs Scripts (auto-detect eMMC, deutsche Bootmenü-Einträge)
  - `set_computername.bat` — Optionale individuelle Tablet-Benennung
  - Druckbare Checkliste für den Deployment-Prozess
- **Zeitschätzung:** ~2 Arbeitstage für 200 Tablets (4 USB-Sticks parallel)

### OTA-Update System (Software aktualisieren)
- **Neues Feature:** Tablets können sich über GitHub Releases selbst aktualisieren
- **Service-Menü:** Neuer Button "Software aktualisieren" (PIN 6588)
  - Prüft GitHub API auf neuestes Release
  - Vergleicht Versionen automatisch
  - Download mit Fortschrittsanzeige
  - App beendet sich → BAT-Script ersetzt Dateien → Neustart
- **Standalone BAT:** `update_from_github.bat` komplett überarbeitet
  - Lädt jetzt von GitHub Releases statt Source-Archiv
  - Funktioniert auf Produktions-Tablets (kein Python/Git nötig)
  - Ersetzt EXE + `_internal/` + Assets
- **Geschützte Dateien:** config.json, BILDER/, logs/, .booking_cache/ werden NIE überschrieben
- **Build-Anpassung:** `build_installer.bat` erstellt immer ZIP für OTA-Updates
- **Neues Modul:** `src/updater.py` — GitHub Release API, Download, Update-Script-Generierung
- **Workflow:** Build → GitHub Release erstellen → ZIP hochladen → Tablets updaten

---

## 2026-02-11

### Bilder-Export auf unbekannte USB-Sticks
- **Neues Feature:** Wenn ein USB-Stick eingesteckt wird der weder "fexobox" noch "FEXOSAFE" heißt, wird ein Export-Dialog angeboten: "X Bild(er) auf den Stick kopieren?"
- Anwendungsfall: Kunden-Stick kaputt → eigenen USB-Stick einstecken → Bilder retten
- Dialog mit Fortschrittsbalken und Abbrechen-Button (wie Sync-Dialog)
- Bilder werden nach `BILDER/Single/` und `BILDER/Prints/` auf den Stick kopiert
- Dialog erscheint nur einmal pro Stick (Laufwerksbuchstabe wird gemerkt)
- Kein Dialog wenn keine lokalen Bilder vorhanden

### Event-Wechsel: Lösch-Bestätigung
- **Änderung:** Beim Event-Wechsel werden lokale Bilder gelöscht. Jetzt mit 2-Schritt-Bestätigung:
  1. Dialog zeigt "⚠️ X vorhandene Bilder werden gelöscht!" als Warnung
  2. Klick auf "NEUES EVENT STARTEN" → zweite Ansicht "Bilder löschen?" mit rotem "LÖSCHEN & NEUES EVENT" Button
  3. "Zurück"-Button führt zur Hauptansicht zurück
  4. Wenn keine Bilder vorhanden: direkt ohne Zwischenschritt
- USB-Sync bei neuem Stick war bereits korrekt deaktiviert (nur bei gleichem Event)

### System-Test: Komplette Session statt Einzelfoto
- **Änderung:** System-Test fotografiert jetzt **jeden Template-Slot einzeln** (z.B. 4 Fotos bei 4er-Collage) statt ein Foto zu duplizieren. Ergebnis wird automatisch gedruckt → echter Testausdruck mit Kunden-Template
- UI zeigt Live-Fortschritt: "Foto 2 von 4 aufnehmen..." mit anteiligem Fortschrittsbalken
- 2 Sekunden Pause zwischen Fotos (Kamera nachregeln)
- Erfolgsmeldung: "Alles OK! Testdruck mit X Fotos gesendet."

### System-Test "Keine Template-Boxen geladen" behoben
- **Fix:** System-Test schlug immer bei "Template anwenden" fehl, obwohl Template auf USB funktionierte. Ursache: `reset_session()` (Schritt 9) löschte `template_boxes` und `overlay_image`, die in Schritt 6 gerade erst geladen wurden. Lösung: `reset_session()` VOR dem Template-Laden ausführen (jetzt Schritt 4 statt 9)

### USB-Sync: Bestätigungsdialog statt Auto-Kopie
- **Änderung:** Bilder werden nicht mehr automatisch auf USB kopiert wenn der Stick eingesteckt wird. Neuer Flow:
  1. Neues Event (anderer USB-Stick) → Event-Wechsel-Dialog, KEINE Bilder kopieren
  2. Gleicher Stick wieder eingesteckt → Dialog "X Bilder fehlen auf USB. Jetzt kopieren?" mit Kopieren/Abbrechen
  3. Beim Kopieren: Fortschrittsbalken + Abbrechen-Button
  4. Am Ende: Ergebnis-Anzeige (X kopiert / abgebrochen / Fehler) + OK-Button
- USB-Manager: Neue `count_missing()` Methode, `sync_all_missing()` mit `progress_callback` und `cancel_event`

### Service-PIN Freeze behoben
- **Fix:** Service-PIN 6588 hat die App eingefroren. Ursache: ServiceDialog wurde innerhalb des `after`-Callbacks des bereits zerstörten AdminDialogs erstellt. Der neue Dialog landete hinter dem Hauptfenster, `grab_set()` blockierte Interaktionen → Freeze. Lösung: AdminDialog setzt nur ein Flag (`_open_service`), ServiceDialog wird erst nach `wait_window()` in `show_admin_dialog()` geöffnet

### Beenden-Button in Admin-Dialog verschoben
- **Änderung:** "App beenden"-Button war im Hauptfenster (Top-Bar, nur sichtbar nach Fullscreen-Exit). Jetzt in der Button-Leiste des Admin-Dialogs neben "Abbrechen" und "Speichern". Kein Fullscreen-Toggle mehr nötig um die App zu beenden

### Galerie zeigt gelöschte Bilder - behoben
- **Fix:** Web-Galerie zeigte nach "Alle Bilder löschen" im Service-Menü weiterhin alte Bilder. Zwei Ursachen:
  1. **Galerie las von USB statt lokal:** Galerie bevorzugte USB-Pfad (`F:\BILDER\`). Löschen betrifft nur lokale Festplatte, USB ist Backup und bleibt unangetastet. Lösung: Galerie liest jetzt **immer** vom lokalen Pfad
  2. **Browser-Cache:** Handy-Browser cachte Thumbnails und HTML. Lösung: `Cache-Control: no-store` Header auf allen Gallery-Server-Responses

### Event-Wechsel-System, System-Test & FEXOSAFE Backup
- **Automatischer Event-Wechsel-Dialog:** Wenn ein USB-Stick ("fexobox") mit einer neuen Buchung/Template erkannt wird, erscheint ein Fullscreen-Dialog "Neues Event erkannt" mit Annehmen/Ablehnen. Wartet auf StartScreen wenn User in aktiver Session
- **Event-Wechsel Logik:** Bei Annehmen: Neue Buchung + Template laden, alle lokalen Bilder löschen, Caches leeren, neues Statistik-Event starten, automatischen Systemtest durchführen
- **Automatischer System-Test:** Nach Event-Wechsel testet die App die komplette Kette (Kamera init → Testfoto → Template anwenden → Testdruck → Aufräumen). Zeigt Schritt-für-Schritt-Fortschritt und Ergebnis ("Alles OK!" oder Fehlerdetails)
- **FEXOSAFE Backup-Stick:** Neuer USB-Stick-Typ mit Label "FEXOSAFE" für Bilder-Sicherung. Wird automatisch erkannt, zeigt Backup-Dialog mit Bilderzähler und Fortschrittsbalken. Kopiert BILDER/Single/ und BILDER/Prints/ auf den Stick. 30s Cooldown nach Backup
- **Pending-Dialog-Queue:** Dialoge (Event-Wechsel, FEXOSAFE) werden in Queue gespeichert wenn User in aktiver Session ist, und erst beim Rückkehr zum StartScreen angezeigt

### Strom-Status-Anzeige
- **Strom-Indikator in Top-Bar:** Grünes ⚡ bei Netzbetrieb, oranges ⚡ mit Prozentanzeige bei Akkubetrieb. Nutzt `GetSystemPowerStatus` (kernel32 Syscall, < 0.1ms). Prüfung alle 10 Sekunden

### Drucker-Status-Warnung (Canon Selphy)
- **Blinkende Drucker-Warnung:** Drucker-Status-Check in der Top-Bar zeigt jetzt blinkende Rot/Gelb-Warnung (wie USB-Stick), wenn der Drucker nicht bereit ist. Erkennt: Drucker aus/offline, Papier leer, Papierstau, Drucker-Fehler, Drucker nicht gefunden. Bei Problem 1-Sekunden-Blink-Intervall, bei OK nur alle 5s Prüfung. Nutzt nur win32print API (< 1ms pro Call, kein Netzwerk)
- **Canon-Fehlerfenster-Erkennung:** Canon SELPHY zeigt Fehler (Kein Papier, Kassette falsch) über eigene Treiber-Dialogfenster. Neue `_detect_canon_error_window()` Methode erkennt diese via `EnumWindows` API und zeigt den Fehler in der Top-Bar an. Liest Fehlertext aus Static-Child-Controls des Canon-Fensters. `_bring_printer_dialog_to_front()` holt das Canon-Fenster vor die Fullscreen-App

### Belastungstest realistisch (Developer Mode)
- **Realistische Simulation:** Stress-Test simuliert jetzt echtes Nutzerverhalten statt stur den gleichen Pfad. Zufällige Template-Auswahl, zufällige Filter (mit 40% Chance mehrere durchzuprobieren), 25% Redo-Chance auf Final-Screen, 15% Redo pro Collage-Foto im Session-Screen. Zufällige Delays zwischen allen Aktionen (300-4000ms). Logging zeigt Session-Nummer und Redo-Statistik. Ziel: Race Conditions, Memory Leaks und UI-Freezes provozieren

---

## 2026-02-10

### Bugfixes & UI-Verbesserungen (Tablet-Test Feedback Runde 5)
- **Foto-Zähler Fix:** "Foto 5 von 4" beim letzten Foto behoben - `_update_progress` zeigt jetzt maximal `total_photos` an (min-Cap)
- **Flash-Bild zuverlässiger:** `_display_flash()` wird jetzt direkt in `_take_photo()` aufgerufen statt auf den nächsten Loop-Tick (50ms) zu warten. Verhindert intermittierendes Fehlen des Auslösebilds beim 2. Foto
- **Responsive Template-Karten:** Template-Karten auf dem Startscreen passen sich an die Anzahl an: 1 Karte = 360x280 (groß), 2 Karten = 270x230 (mittel), 3+ Karten = 220x190 (klein). Interne Größen (Preview, Titel-Font, Icon) skalieren proportional
- **Print-Vorschau vollständig:** padx im Final-Screen von 40px auf 10px reduziert - Print wird jetzt deutlich größer und vollständiger angezeigt

### Bugfixes & Features (Tablet-Test Feedback Runde 6)
- **Galerie-Deaktivierung Fix:** `_is_gallery_enabled()` prüft nur noch `config["gallery_enabled"]` statt direkt die Booking-Settings. Booking-Settings fließen via `apply_settings_to_config()` in die Config - Admin-Änderungen werden nicht mehr überschrieben
- **Willkommensnachricht:** Persönliche Begrüßung im VLC-Ladescreen mit `shipping_first_name` aus Booking-Meta ("Hallo [Name], vielen Dank für deine Buchung bei fexobox!")
- **`live_gallery` Meta-Feld:** Booking-Settings lesen jetzt `features.live_gallery` statt `features.online_gallery` für Galerie-Aktivierung
- **Bilder löschen komplett:** Service-Menü "Alle Bilder löschen" löscht jetzt auch Bilder im Gallery-Server-Pfad (kann auf USB zeigen). Verhindert dass Bilder im Live-Server sichtbar bleiben

### Desktop-Icon & Offline-Hotspot (Tablet-Test Feedback Runde 7)
- **Desktop-Icon Fix:** ICO-Datei wird jetzt separat in `{app}\assets\` kopiert im Installer. PyInstaller 6.x legt Assets in `_internal/assets/` ab, aber Desktop-Verknüpfung referenziert `{app}\assets\fexobooth.ico`
- **Offline-Hotspot:** `hotspot.py` komplett überarbeitet - funktioniert jetzt auch OHNE Internetverbindung! Versucht zuerst Windows Tethering API mit allen Connection Profiles (nicht nur Internet-Profil), dann Fallback auf `netsh wlan hostednetwork`. SSID/Passwort werden aus Config übergeben

### Bugfixes & UX (Tablet-Test Feedback Runde 8)
- **Flash-Bild zuverlässig sichtbar:** Flash-Bild wird einmalig beim Session-Start gecacht (statt bei jedem Foto neu aus JPEG laden). `update_idletasks()` erzwingt GUI-Redraw vor der blockierenden Kamera-Aufnahme. Bild auf 80% der Container-Größe vergrößert (vorher 60%)
- **Ladezeit-Hinweis:** "Das kann bis zu 2 Minuten dauern." Text im VLC-Loading-Screen (mit und ohne Kundenname)
- **Statistik-Texte weiß:** Alle Texte im Statistik-Tab des Admin-Menüs jetzt in `text_primary` (#ffffff) statt `text_secondary`/`text_muted`
- **Auto-Fullscreen:** Wenn `start_fullscreen=True` aber Fenster nicht im Fullscreen ist (z.B. nach Admin), wird nach 10s automatisch Fullscreen wiederhergestellt. Fullscreen-Restore nach Admin nutzt jetzt `_enter_fullscreen()` mit korrektem `_set_appwindow()` und `withdraw()/deiconify()`
- **Hotspot Encoding-Fix:** `UnicodeDecodeError` bei PowerShell-Output auf deutschem Windows behoben (cp1252 → UTF-8 mit errors='replace')

---

## 2026-02-09

### Performance & UX Optimierungen (Tablet-Test Feedback)
- **VLC-Warmup:** Plugin-Cache wird beim App-Start im Hintergrund geladen (verhindert 57s Freeze beim ersten Video auf Miix 310)
- **VLC-Ladeanimation:** Subtile Punkte-Animation während VLC noch aufwärmt (statt schwarzer Freeze)
- **Hotspot im Hintergrund:** Start/Stop des Windows Mobile Hotspot blockiert nicht mehr den Hauptthread (~6s gespart)
- **LiveView Vollbild:** Kamera-Bild wird immer bildschirmfüllend angezeigt (kein Template-Overlay mehr in der Session)
- **Final-Screen Redesign:** Buttons als Overlay über dem Bild (größer, prominenter), Bild füllt den ganzen Screen
- **Foto-Wiederholen Button:** Neuer ↻ Button am rechten Rand des Final-Screens (gleiche Vorlage, neue Fotos, kein Video)
- **Taskmanager-Fix:** App erscheint jetzt als Vordergrund-Prozess (WS_EX_APPWINDOW via ctypes + overrideredirect)
- **Fullscreen-Bugfix:** Revert von attributes("-fullscreen") zurück zu overrideredirect(True) - deckt auf Miix 310 korrekt den ganzen Screen ab
- **Session-Screen vereinfacht:** Template-Preview-Rendering entfernt (~200 Zeilen weniger Code, bessere Performance)

### Bugfixes & UI-Verbesserungen (Tablet-Test Feedback Runde 2)
- **VLC-Ladebildschirm:** Richtiger Loading-Screen im StartScreen mit "Software wird geladen..." und Fortschrittsbalken (statt unsichtbare Punkte). Start-Button blockiert bis VLC warm
- **Flash-Image Fix:** Container-Größe Fallback (Screensize) wenn Container noch nicht gelayoutet ist + Logging
- **Final-Screen Bildrand:** Bild wird mit Rand angezeigt (nicht mehr edge-to-edge)
- **Druckanzahl-Text weiß:** Druck-Info im Final-Screen jetzt in weißer Schrift
- **Filter-Performance:** Main-Preview-Rendering im Hintergrund-Thread, kleinere Mini-Previews (BILINEAR statt LANCZOS)
- **App-Icon:** Eigenes fexobooth.ico (aus Cartoon-Maskottchen), eingebunden in Fenster, EXE, Installer und Desktop-Shortcut
- **Desktop-Icon Fix:** Explizites IconFilename für alle Shortcuts im Installer + Icon-Cache-Clear nach Installation

### Bugfixes & Features (Tablet-Test Feedback Runde 3)
- **Flash-Bild Fix:** CTkImage braucht `dark_image` Parameter im Dark Mode - ohne wird nichts angezeigt (gleicher Bug wie beim Logo)
- **Redo per Collage-Foto:** "↻ NOCHMAL" Button erscheint nach jedem Foto einer Collage (4s sichtbar). Erlaubt Wiederholung eines einzelnen Fotos statt der ganzen Collage. Retake-Button aus Final-Screen entfernt
- **Template-Persistenz:** USB-Template wird lokal nach `.booking_cache/cached_template.zip` kopiert. Bleibt auch nach USB-Abzug und Neustart verfügbar. Wird nur bei neuem Template überschrieben
- **Final-Screen Transparenz:** Schwarze Container-Hintergründe um Buttons und Texte entfernt (image_frame und button_frame sind jetzt transparent)
- **ICO Multi-Size:** App-Icon von 16x16 auf 7 Größen (16-256px) erweitert. Desktop-Icon nicht mehr verpixelt
- **Installer Robuster:** `ie4uinit.exe` mit vollem Systempfad + `skipifdoesntexist` Flag. Zusätzlich PowerShell-Fallback zum Löschen des Icon-Cache. Desktop-Shortcut wird immer erstellt (nicht nur bei Task-Auswahl)

### Bugfixes (Tablet-Test Feedback Runde 4)
- **Final-Screen Redesign:** Komplett auf Pack-Layout umgebaut (statt place()-Overlays). Bild zentriert mit 60px Rand, Buttons/Text darunter in eigenem Bereich. Keine Transparenz-Probleme mehr (kein dunkles Rechteck hinter Buttons)
- **Flash-Bild JPEG:** JPEG-Bilder werden jetzt als RGB geladen und direkt ohne Alpha-Maske gepastedt. Vorher: `.convert("RGBA")` + Paste mit Mask schlug bei JPEG fehl. PNG mit Transparenz wird weiterhin korrekt behandelt
- **Desktop-Icon Fix:** `SHChangeNotify(SHCNE_ASSOCCHANGED)` wird jetzt direkt im Installer-Pascal-Script aufgerufen (statt nur Icon-Cache-Dateien zu löschen). Benachrichtigt den Explorer sofort über neue Icons

---

## 2026-02-06

### Diverse Fixes & Verbesserungen
- **Bug Fix:** Logo wird jetzt angezeigt (CTkImage braucht `dark_image` Parameter im Dark Mode)
- **Neuer Filter:** "Insta Glow" - Instagram-artiger Filter (warmer Glow, matte Schatten, leichte Entsättigung)
- **Entfernt:** Countdown-Beep und Foto-Beep komplett entfernt (`winsound.Beep` Aufrufe in session.py)

### Service-Menü (internes Wartungsmenü)
- **Neues Feature:** Service-Menü über separaten PIN (6588) erreichbar
- Menüpunkt "Bilder sichern": Kopiert alle Bilder (Singles + Prints) auf USB-Stick in Ordner mit Event-ID
- Menüpunkt "Alle Bilder löschen": Löscht alle lokalen Bilder (Datenschutz) mit Bestätigungsdialog
- Überschreiben-Abfrage wenn Event-ID Ordner bereits auf USB existiert
- Fortschrittsanzeige und Erfolgs-/Fehlermeldungen bei beiden Aktionen
- Neue Datei: `src/ui/screens/service.py`
- PIN-Dialog erweitert: Erkennt Service-PIN und öffnet Service-Menü statt Admin-Einstellungen
- App-Referenz am Root-Fenster gespeichert (`_photobooth_app`) für Service-Menü Zugriff

### Performance-Optimierung (VLC-Übergang)
- **Bug Fix:** Doppelter Screen-Wechsel nach Zwischen-Videos behoben (video.py)
- **Bug Fix:** VLC-Cleanup: Synchron bei Zwischen-Videos (Kamera braucht DXVA2), async bei Start/End-Videos
- Template-ZIP Cache: Gleiche Datei wird nur 1x entpackt statt 3x
- App-Level Overlay-Cache: LANCZOS-Resize nur 1x pro Session statt bei jedem Resume
- Resume-Delay nach Video: 500ms → 200ms (Kamera bleibt offen)

### PIN-Dialog verbessert
- Responsive Größe (passt sich an Bildschirmgröße an statt feste 400x500)
- Exakte Zentrierung (kein Offset mehr nach unten)
- Schließen-Button (X) oben rechts + Escape-Taste
- Eigene Hintergrundfarbe (bg_medium statt transparent)
- Numpad-Buttons skalieren mit Bildschirmgröße
- Kein Abschneiden mehr auf kleinen Screens

---

## 2026-02-05

### Arbeitsumgebung erstellt
- CLAUDE.md (Projektsteuerung)
- ARBEITSWEISE.md (KI-Zusammenarbeit)
- ROADMAP.md (Anforderungen)
- FORTSCHRITT.md (diese Datei)
- ERKENNTNISSE.md (Lessons Learned)
- TODO.md (Aufgabenliste)

---

## 2026-02-04

### Video-Fix für schwache Hardware
- Windows Media Foundation (MSMF) Backend implementiert
- Threading für Video-Wiedergabe (Frame-Queue)
- Status-Label bei Video-Fehlern
- Video-FPS auf max. 25 begrenzt

### Offline-Hotspot Setup
- Mehrere Fallback-Methoden für Hotspot ohne Internet
- Auto-Start Scheduled Task
- Manuelle Anleitung als letzter Fallback

### Behoben
- Video zeigt schwarzen Bildschirm auf Miix 310
- UI friert ein während Video-Wiedergabe
- Hotspot-Script schlägt fehl ohne Internet

---

## 2026-02-03

### Admin-Menü & Persistenz
- Galerie-Tab im Admin-Menü (SSID, Passwort, Port)
- Statistik-Tab im Admin-Menü (Export, Reset)
- QR-Code Widget überarbeitet (Pink Akzent-Rahmen)
- Buchung + Template Persistenz (.booking_cache/)
- Shared USBManager (Singleton-Pattern)

### Galerie & Statistik Module
- Lokale Galerie mit Flask-Webserver
- QR-Code Generator
- Statistik-Modul (Event-Tracking pro Buchung)
- Buchungsnummer in Top-Bar

### Behoben
- Pending-Files Counter aktualisiert sich nicht live
- Template nach Neustart weg

---

## 2026-02-02

### USB & Booking System
- settings.json Support
- USB-Sync Feature (Pending-Files Queue)

---

## Ältere Einträge

Siehe [CHANGELOG.md](CHANGELOG.md) für das vollständige Release-Changelog.
