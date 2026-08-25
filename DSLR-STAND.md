# DSLR-Baustelle — Stand und Übergabe

> **Zweck dieser Datei:** Vollständige Übergabe an die nächste Sitzung.
> Stand: **24.08.2026, Version 2.4.58**. Testgerät: **Box 245**, Canon EOS 2000D,
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

### Was nachweislich funktioniert

| | Nachweis |
|---|---|
| Kamera wird erkannt und verbunden | Box-Log: `Session erfolgreich geöffnet` |
| Kamera löst aus | Christian hört den Spiegel; Bildzähler auf der Karte steigt |
| Rückkanal feuert grundsätzlich | Box-Log: `>>> OBJECT EVENT: DirItemRequestTransfer_Alt` |
| Kamera meldet Dateiname + Größe | Box-Log: `IMG_0001.JPG (820393 bytes)` |
| Log-Versand ins Dashboard | Läuft, siehe „Werkzeuge" |

### Was noch nicht funktioniert

**Zuletzt gemeldet (2.4.57):** kein Live-View, Endlosschleife beim ersten Foto.

Ursache gefunden und in **2.4.58** behoben: eine übersehene Aufrufstelle
(`EdsGetLength` mit 32- statt 64-Bit-Variable), die **jedes** Vorschaubild
scheitern ließ — 166 Fehler pro Sitzung.

> **2.4.58 ist noch nicht auf der Box getestet.** Das ist der nächste Schritt.

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
| 2.4.57 | **EDSDK wurde aus zwei verschiedenen Programmfäden gestartet** → `EdsSetObjectEventHandler` hing → Kamera blockiert | behoben |
| 2.4.58 | **Aufrufstelle von `EdsGetLength` im Live-View übersehen** → kein Vorschaubild | behoben, **ungetestet** |

### Der rote Faden

**Fünf von acht Ursachen waren derselbe Fehlertyp:** ein 64-Bit-Wert der
Canon-Schnittstelle, der im Python-Code als 32 Bit stand. Vier Fundstellen
kosteten je eine Testrunde auf der echten Box, die fünfte entstand beim Beheben
der vierten.

**Deshalb gibt es jetzt `tests/test_edsdk_typen.py`.** Er findet diese ganze
Familie in Sekunden, ohne Kamera.

---

## Werkzeuge

### 1. Typenprüfung — vor jedem DSLR-Build ausführen

```
python tests/test_edsdk_typen.py
```

Prüft ohne Kamera:
1. Stimmen alle Signaturen mit dem Canon-Header überein?
2. Passen alle **Aufrufstellen** zu diesen Signaturen?

Gegenprobe ist gemacht: Baut man den Fehler von 2.4.57 künstlich wieder ein,
meldet der Test ihn mit Zeilennummer und gibt Rückgabewert 1.

> Der Canon-Header liegt im Repo unter
> `EDSDK/EDSDKv132010W/.../Header/EDSDK.h` und ist die **Wahrheitsquelle**.
> Niemals aus dem Gedächtnis oder aus einem Beispiel abschreiben.

### 2. Messmodus statt Raten

```
fexobooth.exe --dslr-test
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

**Dieser Messlauf wurde noch nie gefahren.** Er wäre der schnellste Weg aus
weiteren Rateschleifen.

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
ssh -i ~/.ssh/id_ed25519_claude c710394claude-code@admin.fexobox.de \
  "ls -lt --time-style=+%H:%M /web/admin-fexobox-de-app/storage/app/booth-logs/245/ | head"

ssh -i ~/.ssh/id_ed25519_claude c710394claude-code@admin.fexobox.de \
  "zcat /web/admin-fexobox-de-app/storage/app/booth-logs/245/<datei>.gz" > lokal.log
```

> **Prüfen, ob ein Upload wirklich ankam** (nicht darauf verlassen, dass er
> losgeschickt wurde):
> ```bash
> ssh ... "grep -a 'BoothLog: Log empfangen' \
>   /web/admin-fexobox-de-app/storage/logs/laravel.log | tail -3"
> ```

### 4. Logik-Tests ohne Hardware

Im Scratchpad der letzten Sitzung (`test_canon.py`, `test_freeze.py`,
`test_host.py`, `t56.py`, `t57.py`) — decken ab: Doppelbild-Sperre,
Endlosschleifen-Bremse, Einfrier-Schutz, kompletter Direktweg, Hänger-Sperre,
Kamera-Faden. **Sollten ins Repo unter `tests/` wandern**, damit sie nicht
verloren gehen.

---

## Was im Log worauf hindeutet

| Logzeile | Bedeutung |
|---|---|
| `Speicherung: über den Kamera-Zwischenspeicher` | Kartenweg — auf der Flotte falsch, nur Testbox |
| `Speicherung: direkt auf die PC-Festplatte` | Direktweg — so soll es sein |
| `Rückkanal-Registrierung hängt seit 4s` | `EdsSetObjectEventHandler` blockiert die Kamera |
| `>>> OBJECT EVENT` fehlt komplett | Rückkanal tot — ohne Karte kommt kein Foto |
| `EDSDK Fehler 0x81 (DEVICE_BUSY)` | Kamera belegt, meist Folge eines hängenden Aufrufs |
| `EDSDK Fehler 0xc1 (COMM_DISCONNECTED)` | USB-Verbindung abgerissen |
| `EDSDK 0xa102 (OBJECT_NOTREADY)` | **harmlos** — Live-View braucht Anlaufzeit |
| `expected LP_c_ulonglong` | 64-/32-Bit-Konflikt → `tests/test_edsdk_typen.py` |
| `Bilanz: X echt / Y Notlösung / Z leer` | **Die wichtigste Zeile.** `echt` muss steigen |
| `Notlösung geliefert: 1056x704` | Vorschaubild statt Foto — sieht verwaschen aus |

---

## Offene Punkte

### 1. Läuft 2.4.58 auf der Box? (offen, höchste Priorität)

Der Live-View-Fehler ist behoben, aber ungetestet.

**Prüfen:**
- Live-View sichtbar? (war zuletzt komplett weg)
- Im Log: `=== ECHTES DSLR-FOTO: 6000x4000 ===` statt `NOTLÖSUNG`?
- Am Zeilenende: steigt `echt` in der Bilanz?

### 2. Funktioniert der Direktweg ohne Karte? (offen, entscheidend für die Flotte)

Alle bisherigen Tests liefen auf der Box **mit** Karte. Die Flotte hat keine.
Zwingend nötig: ein Testlauf **ohne Karte in der Kamera**.

### 3. Standbild zeigt anderen Bildausschnitt als das finale Foto (offen)

Christian mehrfach: *„liveview macht freeze und zeigt nicht das foto"*.
Zwei Anteile:
- **Zeitversatz** — schrumpft, sobald Fotos schnell ankommen
- **Unterschiedlicher Bildausschnitt** zwischen Vorschau und Aufnahme —
  eigenes Thema, noch nicht angefasst

Der Wartehinweis („Foto wird aufgenommen…") erscheint seit 2.4.55 erst nach
900 ms — bei schnellem Foto sieht man ihn nie. Christian hatte zu Recht gesagt,
dass ein Dialog bei jedem Foto keine Lösung ist.

### 4. Überbelichtete Fotos (offen)

Bisher betraf das nur Notbilder aus dem Live-View. Ob es bei echten Fotos
bleibt, zeigt sich erst, wenn welche ankommen.

### 5. Belichtungszeit im Auge behalten

Ohne Blitz wählt die Automatik bei dunkler Location lange Zeiten → verwackelte
Fotos. Das Log schreibt Zeit, Blende, ISO und Weißabgleich vor jedem Foto mit.
**Erst messen, dann diskutieren** — und Christians Randbedingungen beachten
(kein Blitz, AF an, Kunde stellt nichts ein).

---

## Fallstricke für die nächste Sitzung

**1. Nicht mehrere Vermutungen pro Build bündeln.**
Das war der teuerste Fehler dieser Sitzung. Jede Runde kostet Christian Build,
Aufbau und Testlauf. Wenn zwei Runden am selben Symptom scheitern, ist nicht die
dritte Vermutung das Problem — die **Methode** ist es. Dann lohnt ein Werkzeug,
das den Suchraum in einem Lauf abdeckt (`--dslr-test`).

**2. „Lief früher mal so" beweist nicht, dass die Zeile richtig war.**
In 2.4.49 wurde ein schützender Nebenfaden entfernt, weil eine ältere Fassung
den direkten Aufruf hatte. Ergebnis: Die Box fror beim Session-Start ein. In
jener Fassung wurde der Pfad praktisch nie durchlaufen. **Vor dem Zurückbauen
prüfen, ob der fragliche Pfad damals überhaupt lief.**

**3. Jeder Aufruf an die Kamera braucht ein hartes Zeitlimit.**
Eine Box darf langsam sein, aber nie stehen.

**4. Ein hängender Aufruf darf sich nie wiederholen.**
`EdsSetObjectEventHandler` blockiert bei jedem Versuch die Kamera zusätzlich —
vier Versuche machten die Box unbenutzbar. Seit 2.4.56 gilt: einmal hängen
genügt, danach wird er nicht mehr angefasst.

**5. Der Rückkanal-Aufruf darf NICHT im Kamera-Faden laufen.**
Sonst blockiert ein Hänger auch Live-View, Aufnahme und Freigeben. Er läuft
bewusst daneben; der Kamera-Faden arbeitet dauerhaft Nachrichten ab, damit der
Aufruf trotzdem fertig werden kann.

**6. Erfolgsmeldungen nie behaupten.**
Im Code stand jahrelang „Handler funktioniert trotzdem" — das war eine
ungeprüfte Annahme und hat die Fehlersuche über Monate blockiert. Wenn eine
Funktion nicht sicher weiß, ob sie erfolgreich war, muss sie das sagen dürfen
(`True` / `None` / `False`).

**7. Die Webcam-Flotte nicht anfassen.**
`webcam.py` blieb in dieser ganzen Sitzung unberührt. Alle Eingriffe in
`app.py` und `session.py` liegen hinter einer Abfrage auf
`camera_type == "canon"` bzw. `_ist_dslr()`.

---

## Geänderte Dateien (noch nicht committet!)

```
src/__init__.py              Version 2.4.58
src/camera/edsdk.py          Fehlertabelle, 64-Bit-Typen, Kamera-Faden,
                             Auslösen nach Canon-Referenz, Hänger-Sperre
src/camera/canon.py          Doppelbild-Sperre, Endlosschleifen-Bremse,
                             Wiederherstellung, Speicherplatz-Meldung, Diagnose
src/app.py                   Canon-Ereignis-Takt (nur bei camera_type=canon)
src/ui/screens/session.py    Wartehinweis bei DSLR (ab 900 ms)
src/ui/screens/admin.py      Knopf „Logs ans Dashboard senden"
src/main.py                  Modus --dslr-test
src/utils/log_upload.py      NEU — Log-Versand
src/tools/dslr_test.py       NEU — Messmodus
tests/test_edsdk_typen.py    NEU — Typenprüfung
CHANGELOG.md, ERKENNTNISSE.md, FORTSCHRITT.md, TODO.md
```

**Im Dashboard (adminFexobox) — bereits deployt und live:**

```
app/Http/Controllers/Api/BoothLogController.php    NEU
app/Http/Controllers/BoothLogViewController.php    NEU
app/Models/BoothLog.php                            NEU
database/migrations/..._create_booth_logs_table.php NEU
resources/views/booth-logs/                        NEU
routes/api.php, routes/web.php, layouts/app.blade.php
```

---

## Empfehlung für den Einstieg

1. **`python tests/test_edsdk_typen.py`** — muss sauber durchlaufen
2. **2.4.58 bauen und auf Box 245 testen** — kommt der Live-View zurück?
3. Falls Fotos ankommen: **Karte aus der Kamera nehmen** und erneut testen.
   Das ist der Zustand der echten Flotte.
4. Falls weiterhin keine Fotos: **`--dslr-test` fahren**, bevor irgendetwas
   geändert wird. Der Messlauf beantwortet in einer Minute, was vier
   Testrunden nicht geschafft haben.
5. Falls die Box gar nicht mehr brauchbar ist: **auf einen älteren Stand
   zurück** (2.4.45 war der letzte vor dieser Baustelle) und von dort in
   einzeln prüfbaren Schritten vorgehen.

---

## Ehrliche Einordnung

In dieser Sitzung wurden acht echte Ursachen gefunden und behoben. Trotzdem
liefert die Box bis heute keine Fotos, und zwischendurch war sie zweimal
schlechter dran als vorher (Einfrieren in 2.4.49, blockierte Kamera ab 2.4.53).

Beide Rückschritte entstanden gleich: Änderungen, die nicht ohne Hardware
prüfbar waren, gingen ungetestet auf die Box. Die Gegenmaßnahme ist die
Typenprüfung und der Messmodus — beides prüft ohne Kamera bzw. ersetzt das
Raten durch Messen. **Diese Werkzeuge zuerst nutzen, bevor weiter am Code
geändert wird.**
