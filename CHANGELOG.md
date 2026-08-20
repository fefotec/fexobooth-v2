# Changelog

Alle wichtigen Änderungen an diesem Projekt werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

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
