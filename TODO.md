# TODO - Fexobooth V2

Aufgabenliste mit Prioritäten.

---

## 2.4.43 Dauerbetrieb HD auf EINER Testbox prüfen 🔴

> Etappe 2 von 2. Der Schalter ist überall aus — er muss auf genau einer Box
> von Hand angeschaltet werden: **3198 → Tab Kamera → „Kamera dauerhaft in
> Full HD (nur Testbox)" → Speichern.**

- [ ] **Erst mit Schalter AUS eine Session machen.** Alles muss sein wie immer.
      Das ist die Gegenprobe, dass die Flotte nichts abbekommen hat.
- [ ] Schalter AN, speichern, Session starten: Nach dem Blitz muss das Foto
      **fast sofort** da sein (heute rund 2 Sekunden Pause) — und es muss die
      Pose zeigen, die beim Blitz zu sehen war.
- [ ] **Bildausschnitt:** Die Vorschau ist jetzt links/rechts enger und
      oben/unten weiter. **Das ist so gewollt** — sie zeigt genau das, was
      später gedruckt wird.
- [ ] **In einem dunklen Raum fotografieren**, Schalter an und aus im
      Vergleich. Die Aufnahme fällt jetzt in den Blitz hinein; falls die Fotos
      dunkler oder heller werden als vorher, unbedingt melden.
- [ ] Ein Foto **drucken** und mit dem Vorschaubild vergleichen — Ausschnitt
      und Qualität müssen unverändert gut sein.
- [ ] **Dev-Mode-Log an Claude.** Darin stehen drei Zeilen, die alles klären:
      „Dauerbetrieb HD: warm geöffnet …", „High-Res Capture Timing: …
      Betriebsart=…" und „Sichtbare Capture-Wartezeit bis Fotoanzeige: …".

---

## Werkstatt-Knopf „Netzwerk-Werksreset" endlich einmal testen 🟡

> Steht seit 2.4.27 unabgehakt. Der Knopf ist die einzige per Fingertipp
> erreichbare Stelle, die `netsh int ip reset` / `winsock reset` ausfuehrt —
> aber es gibt bis heute keinen Beleg, dass er je etwas geheilt hat.

- [ ] In der Werkstatt (fexon WLAN in Reichweite): 3198 → Allgemein →
      1. Tippen zeigt „Prüfe Firmen-WLAN...", dann Warnung; 10 s warten →
      entschaerft sich von selbst.
- [ ] 2x tippen → Reset laeuft, Box startet neu und verbindet sich danach.
- [ ] **Ausserhalb** des Firmen-WLAN antippen → muss „Nicht möglich — fexon
      WLAN nicht in Reichweite" zeigen und NICHTS tun.
- [ ] Danach pruefen: `netsh wlan show profiles` — es muss mindestens das
      Firmen-Profil dastehen (bei 0 Profilen geht der Gaeste-Hotspot nicht).

---

## Version 2.4.36 auf einer echten Box gegenpruefen 🔴

- [ ] **Kamera-Messung-Knopf:** Admin-Menue → Tab Kamera → Messung starten.
      Die Oberflaeche muss BEDIENBAR bleiben (Laufzeit zaehlt sichtbar hoch).
- [ ] **Abbrechen** waehrend die Messung laeuft → Dialog reagiert sofort,
      danach startet eine normale Foto-Session wieder.
- [ ] Messung durchlaufen lassen → `kamera-messung.txt` mitschicken. Erst damit
      ist die 1080p-/Backend-Frage entscheidbar.
- [ ] Nach der Messung Task-Manager pruefen: kein zweites `fexobooth.exe` uebrig.

- [x] ✅ **2.4.35 Beenden-Knopf (3198) — auf der Box bestaetigt** (Log 20.08.,
      09:08:52): sauber beendet in 0,3 s inkl. Kamera-Freigabe.
- [ ] **Nikon-Box:** Nach dem Beenden pruefen, ob `FexoNikonBridge.exe` wirklich
      verschwindet (bisher nur auf einer Webcam-Box getestet).

---

## ROUTER pruefen — Boxen bekommen keine IP-Adresse 🔴🔴

> Belegt durch `netzwerk.log` von Box 019 (19.08. 12:31) und Box 038 (18.08. 15:40), beide 2.4.32:
> nur `169.254.x.x`, **eigener Hotspot AUS**, Reparatur erfolglos. Die Box ist entlastet.
> Auffaellig: Arbeitende Boxen bekamen `192.168.2.207 / .208 / .224 / .235` — alles im oberen
> Bereich. Bei 200+ Boxen liegt ein zu kleiner DHCP-Bereich sehr nahe.

- [x] ✅ **ERLEDIGT 19.08.2026 — Ursache war der Router.** DHCP-Pool war zu 100 % voll
      (51 Adressen fuer 200+ Boxen + PCs + Telefone + Access Points + Smart-Home).
      Geaendert: Pool `192.168.2.200-.250` → **`192.168.2.130-.250`** (51 → 121 Adressen),
      Lease Time **120 → 30 Minuten**. Details + Klickpfad in ERKENNTNISSE.md.
- [ ] Gegentest: Box 19 oder 38 einschalten, 2 Min. laufen lassen, `netzwerk.log` muss
      `ALLES GRÜN` zeigen
- [ ] ~~Am Router pruefen~~ (erledigt, siehe oben):
      1. Wie gross ist der DHCP-Adressbereich? Reicht er fuer alle Boxen, die durch die
         Werkstatt laufen? (Arbeitende Boxen liegen bei .207-.235!)
      2. Wie lang ist die Lease-Dauer? Zu lang = alte Boxen blockieren Adressen wochenlang.
      3. MAC-Sperre / Zugangsliste aktiv?
      4. Limit fuer gleichzeitige WLAN-Geraete erreicht?
- [ ] Lease-Liste mit den MAC-Adressen der stummen Boxen abgleichen
      (Box 019 laut Foto: `CC-79-CF-A7-4B-3E`, Realtek RTL8723BS)
- [ ] Gegenprobe: Eine stumme Box am Router eine feste IP-Adresse zuweisen (Reservierung).
      Meldet sie sich dann → DHCP-Bereich/Lease ist die Ursache, endgueltig bewiesen.

## Boxen 19/31/38 melden sich nicht (offen) 🔴

> Werkstatt 19.08. Alle drei mit 2.4.31, **kein Absturz mehr** (absturz.log nur Start-Zeilen),
> WLAN-Setup laut Installer-Log erfolgreich verbunden — aber **keine netzwerk.log**.

- [x] Ursache fuer die fehlende netzwerk.log gefunden: Boxen liefen nur 2,5-3 Min, die Bilanz
      kam aber erst nach der Wiederholkette (~4 Min). Gefixt in 2.4.32 (Bilanz sofort).
- [x] Gegengeprueft: `netzwerk.log` entsteht auch OHNE Dev-Mode (Test mit
      `setup_logging(developer_mode=False)`). Zweites Loch dabei gefunden und geschlossen:
      bei `not_visible` (Firmen-WLAN nicht in Reichweite) wurde vorher GAR NICHTS geschrieben —
      ununterscheidbar von einem fehlgeschlagenen WLAN-Scan.
- [ ] ⚠️ **WARUM sie sich nicht melden, wissen wir weiterhin NICHT** — es gibt schlicht keine
      Daten. Mit 2.4.32 nochmal starten, diesmal reichen ~2 Minuten.
- [ ] Danach `netzwerk.log` auswerten: Zeile `URTEIL` sagt, ob IP, Router, DNS oder das
      Dashboard das Problem ist.

## Abstuerze im Normalbetrieb (2.4.30) 🔴

> Werkstatt 18.08.: 2 Boxen stuerzen beim Hochfahren ab, andere beim Anstecken des USB-Sticks —
> im Developer-Mode NICHT reproduzierbar. Die Dev-Logs liefen beide sauber durch.

- [x] `absturz.log` gebaut: jeder unbehandelte Fehler wird ab jetzt IMMER protokolliert
      (Hauptthread, Threads, Tk-Callbacks) — unabhaengig vom Developer-Mode
- [x] Tk-Fehler-Handler gesetzt (fehlte komplett) — Fehler in Callbacks reissen die App
      nicht mehr mit
- [x] **Ereignisprotokoll ausgewertet** (Mitarbeiter, 18.08. 14:13:45):
      `fexobooth.exe` / fehlerhaftes Modul `ntdll.dll` / Ausnahmecode `0xc0000005`
      = Speicherzugriffsfehler in nativem Code. **Damit ist der Tk-Handler als Ursache
      widerlegt** — bei so einem Absturz laeuft kein Python-Code mehr.
- [x] `faulthandler` eingebaut: schreibt bei genau diesem Absturztyp den Python-Stack aller
      Threads nach `absturz.log` (mit echter Access Violation im Worker-Thread getestet ✓)
- [ ] **Naechster Schritt auf einer abstuerzenden Box:** Absturz-Speicherabbild aktivieren
      (WER LocalDumps, Registry-Befehl siehe unten) ODER vorhandene WER-Berichte einsammeln:
      `C:\ProgramData\Microsoft\Windows\WER\ReportArchive\*fexobooth*`
- [x] **Signatur bestaetigt** (Box 044, 2 Abstuerze am 18.08. mit identischen Werten:
      `ntdll.dll` / `0xc0000005` / Offset `0x649e6`) → reproduzierbarer Heap-Fehler.
      Box 087 taugt NICHT als Vergleich: laeuft noch die Version vom 11.08., keine Abstuerze.
- [x] **Korrektur:** Der Absturz auf Box 044 war NICHT beim Start — laut `netzwerk.log`
      Start um 14:47, Absturz um 15:16 (29 Min. Laufzeit).
- [x] ✅ **URSACHE GEFUNDEN** (absturz.log Box 044, 19.08. 08:44, Code `0xc0000374`):
      Zwei Threads oeffneten gleichzeitig dieselbe DirectShow-Kamera
      (`_camera_status_probe` + `list_cameras`/`_auto_select_webcam`) → Heap-Zerstoerung.
      Gefixt in 2.4.31 mit gemeinsamer Kamera-Sperre (Test: max. 1 statt 2 parallele Zugriffe).
      Die Vermutung „haengt mit der Dashboard-Meldung zusammen" war FALSCH.
- [ ] Nachtest 2.4.31 auf Box 044: mind. 35 Min. laufen lassen, `absturz.log` muss danach nur
      noch Start-Zeilen enthalten (keine `fatal exception`)
- [ ] Pruefen, ob der Absturz mit der wiederkehrenden Dashboard-Meldung (alle 900 s ± 120 s)
      zusammenhaengt — das Zeitfenster passt. Beweis liefert der Python-Stack aus 2.4.30.
- [ ] Verdaechtige bei `ntdll` + `0xc0000005` eingrenzen: Kamera (OpenCV/DirectShow), VLC,
      Druckertreiber. Die 2.4.29-Aenderungen sind reines Python + Subprozesse und koennen
      so einen Absturz nicht direkt ausloesen — sie haben aber das Timing veraendert
      (Hotspot-Start jetzt im Hintergrund-Thread), was einen latenten Fehler sichtbar machen kann.
- [ ] Zweiter Befund pruefen: „Fehlermeldung bei Testdruck: zu hohe CPU-Hintergrundauslastung"
      (Box 044) — Netz-Bilanz dort komplett gruen, also kein Netzproblem; vermutlich der
      Selbsttest-Schwellwert. Separat ansehen.

## Vor dem Flotten-Rollout von 2.4.29 🔴

- [x] **Ursache bewiesen** (Box 056, 18.08.): Hotspot aus → IP-Adresse da → Meldung im Dashboard
      angekommen (serverseitig gegengeprueft)
- [ ] ⚠️ **Hotspot-Rueckkehr beim Kunden testen** — bis 2.4.26 waren Start UND Stopp wirkungslos,
      der Hotspot lief einfach immer. Seit 2.4.29 schalten wir ihn in der Werkstatt WIRKLICH ab.
      Damit haengt der Gast-Betrieb erstmals daran, dass das EINSCHALTEN funktioniert — ein Pfad,
      der im Feld noch nie echt gelaufen ist. Test: Box aus der Werkstatt nehmen, ausserhalb des
      Firmen-WLAN starten, pruefen ob `fexobox-gallery` wieder auftaucht.
- [ ] GitHub-Release veroeffentlichen, falls die Flotte 2.4.29 per Auto-Update bekommen soll
      (Box meldet aktuell: „Neuestes Release: v2.4.25" → Auto-Update verteilt NICHTS)
- [ ] Danach: restliche stumme Boxen (073/116/016) mit 2.4.29 durchtesten

## Firmen-WLAN 2.4.27 auf echter Hardware prüfen 🔴

> Gebaut 2026-08-18 nach dem Feld-Log von Box 200. Alles ist am PC getestet (Logik, Scripts,
> Bilanz), aber der entscheidende Beweis geht nur auf einer betroffenen Box.

- [ ] Build 2.4.27 auf einer Box installieren, die sich bisher NICHT im Dashboard meldet,
      in der Werkstatt einschalten und ~5 Minuten laufen lassen
- [ ] Dev-Mode-Log auswerten: Block `NETZ-BILANZ [Firmen-WLAN]` suchen → Zeile `URTEIL`
      sagt direkt, woran es liegt
- [ ] Falls `URTEIL: KEINE IP-ADRESSE` UND `Hotspot-Konfl.: nein` → der Hotspot ist NICHT die
      Ursache: DHCP-Bereich/Lease-Liste im Firmen-Router prüfen (bei 200+ Boxen realistisch,
      dass der Adressbereich zu klein ist)
- [ ] Falls `Hotspot-Konfl.: JA` → betroffene Boxen sammeln und prüfen, ob es an einem
      bestimmten WLAN-Chip/Treiber hängt (dann Treiber-Update statt Software-Workaround)
- [ ] Nachziehen: `setup/setup_hotspot.ps1` und `setup/diagnose_hotspot.ps1` nutzen noch die
      alte „erstes Profil"-Logik ohne Firmen-WLAN-Ausschluss (nur Werkstatt-Skripte, laufen
      nicht im Kundenbetrieb — aber irgendwann angleichen)
- [x] Erster Feldtest auf Box 200 gelaufen (18.08., Log `fexobooth_20260818_112955.log`):
      Reihenfolge greift, Meldung kam beim ERSTEN Versuch durch, NETZ-BILANZ „ALLES GRÜN" —
      *aber der Fehlerfall selbst trat dort nicht auf, die Box hatte eine gültige IP*
- [ ] ⚠️ Der Anker-Tausch (neutrales Profil statt Firmen-WLAN) wirkt auf WLAN-only-Boxen NICHT —
      Windows liefert gespeicherte Profile nicht als Connection Profile (Details in ERKENNTNISSE).
      Falls sich der Hotspot doch als echter Störer bestätigt: Gegenmittel ist dann das gezielte
      Abschalten (Stufe 3 der Reparatur), nicht der Anker

## Galerie-Server: Thumbnail-Cache 🟡 (Etappe 2 des App-Plans „Offline-Galerie + Cloud-Relay", 2026-07-03)

> Detailplan: [../fexobox-app/docs/PLAN-OFFLINE-GALERIE-CLOUD-RELAY.md](../fexobox-app/docs/PLAN-OFFLINE-GALERIE-CLOUD-RELAY.md) §5.
> Hintergrund: `server.py` rechnet jedes Thumbnail bei JEDEM Abruf neu (Pillow/LANCZOS, kein Cache) –
> bei mehreren verbundenen Smartphones der größte Lastfaktor auf der schwachen Box-Hardware.

- [x] Thumbnail-Cache `BILDER/.thumbs/{folder}/{filename}`: beim ersten Abruf einmal rechnen + speichern,
  danach nur noch `send_file` (Routen `/thumb/...` UND `/api/v1/thumb/...` auf denselben Cache) —
  *gebaut 2026-07-03, gemeinsamer Kern `_serve_thumbnail()` in `server.py`, atomares Schreiben,
  Invalidierung wenn Quelle neuer; 5 automatisierte Tests bestanden (HIT/MISS/Invalidierung/403/Reset)*
- [x] Aufräumen: `.thumbs` folgt dem BILDER-Lebenszyklus — *`delete_all_images()` (Event-Wechsel) löscht
  `.thumbs` mit; `_collect_photos` listet nur Prints/Single und sieht den Cache nie*
- [ ] Optional: Thumb direkt beim Foto-Speichern erzeugen (kein Gast zahlt die Erst-Wartezeit)
- [ ] Eigener Build-Kandidat mit kurzer Test-Checkliste (Live-Flotte, getrennt von anderen Änderungen) —
  ⚠️ Arbeitsbaum enthält parallel laufende 2.4.14-Arbeit (Nikon/Webcam) → Build-Kandidat erst
  schnüren, wenn die parallele Session committet hat; Checkliste liegt bereit (FORTSCHRITT.md)

## Performance vor Release 🏎️ (Analyse-Lauf 2026-07-02 ausgewertet, Fixes in 2.4.12)

> Log `fexobooth_20260702_114253.log` (Nikon-Session): 4 Bremsen identifiziert und gefixt —
> Overlay-Foto-Skalierung pro Frame, Fotoanzeige-Refresh (380 ms/Tick), Filter auf 24-MP-Originalen,
> Final-Rendern im UI-Thread. Details in FORTSCHRITT.md.

- [x] **Nachtest 2.4.12 bestanden** (Dauerläufe 2026-07-02: Nikon 647 Captures + Webcam/SELPHY
  17 h über Nacht, 0 Fehler): LiveView konstant ~7,5 fps, Fotoanzeige 1×/Foto, Bildgröße M aktiv
  (Capture 3,65 s statt 4,06 s), Filter < 2,2 s, Final im Worker.
- [x] **Nachtest 2.4.13 (Webcam-Box) ausgewertet:** Final-Hänger weg ✓, Fotoanzeige-Cache ✓,
  kein Doppel-Rendern ✓, Overlay nur ~45 ms (Box-Region-Composite lohnt nicht) ✓ —
  aber MJPG griff nicht (falsche Reihenfolge, DirectShow verhandelte zurück) → in 2.4.14 korrigiert.
- [ ] **Nachtest 2.4.14 (Webcam-Box, kurz):** Eine Session reicht. Im Log muss stehen:
  „Webcam-Codec: MJPG aktiv" und im `High-Res Capture Timing` `fourcc=MJPG` mit `set`+`read`
  deutlich unter den bisherigen ~1300+700 ms. Falls stattdessen „Kamera lehnt MJPG ab" →
  Kamera-Modell notieren; dann bleibt YUY2, aber ohne Zusatzkosten (Latch).
- [x] Tk-Anzeigepfad (~110 ms/Frame, größter LiveView-Posten laut Overlay-Split) —
  *erledigt 2.4.16 (2026-08-07): komplette Aufbereitung im LiveView-Worker-Thread, Frames auf
  CTkImage-Zielgröße vorskaliert (PIL-Copy-Fastpath), Countdown-Font gecacht; Details FORTSCHRITT.md*
- [x] **Nachtest 2.4.16 (Miix, Webcam-Box):** bestanden 2026-08-07 — 8,5 fps (vorher 2,5–5),
  Anzeige 56 ms, Session-Hitches weg. *Neue Funde (Kamera-Check-Freezes, Priorität, Regler)
  → gefixt in 2.4.17, siehe FORTSCHRITT.md.*
- [x] **Nachtest 2.4.17 (Miix, Webcam-Box):** bestanden 2026-08-07 — Priorität ✓, Regler
  VERIFIZIERT ✓ (Box nutzt Custom-Energieplan ohne Flyout-Slider — kein Handlungsbedarf),
  Start-/Idle-Freezes weg ✓.
- [ ] **Nachtest 2.4.18:** (1) App über 3198-Menü beenden → EXE darf NICHT mehr im
  Task-Manager stehen, Installer läuft ohne Meldung durch. (2) Kunden-Menü 2015 →
  „🔧 Schnellhilfe" drücken → Lauftext, dann „Schnellhilfe abgeschlossen" + Neustart-Button;
  im Log `SCHNELLHILFE:`-Zeilen für alle 5 Schritte.
- [x] **Echter System-Test bei neuem Event** — *umgesetzt in 2.4.19 (2026-08-07): 6 Schritte
  mit Zeitmessung + Schwellwerten, dreistufiges Ergebnis (grün/orange/rot),
  `SYSTEMTEST-MESSWERTE:`-Zeile im Log; Details FORTSCHRITT.md.*
- [ ] **Nachtest 2.4.19:** Event-Wechsel auslösen → System-Test zeigt 6 Schritte („System
  prüfen" + „Kamera prüfen" neu), am Ende grüne „Alle Messwerte im Normalbereich"-Meldung
  (oder orange Auffälligkeiten in Klartext); im Log `SYSTEMTEST-MESSWERTE:`-Zeile prüfen.
  Zusätzlich: Log-Zeile `Speicherpfade initialisiert:` muss jetzt `C:\FexoBooth\BILDER`
  zeigen (NICHT mehr `_internal`), ggf. `BILDER-Migration: N Dateien` beim ersten Start;
  im Firmen-WLAN muss der Update-Dialog FRAGEN statt sofort zu installieren.
  Idee für später: Messwerte zusätzlich ans Monitoring/Dashboard melden (Box-Gesundheit
  vor Event-Versand sichtbar).
- [ ] **Nachtest 2.4.22 (Werkstatt, idealerweise eine der 47 stummen Boxen):**
  (1) Installer durchlaufen lassen → Schritt "Firmen-WLAN wird eingerichtet" + Log
  `logs/company_wlan_setup.log`; Box haengt danach OHNE Neustart im fexon WLAN.
  (2) App-Log: bei geklemmtem WLAN `WLAN-Selbstheilung: ... repariere Profil` →
  `Erfolgreich mit Firmen-WLAN verbunden`; Box taucht im Dashboard auf.
  (3) Schnellhilfe zeigt Schritt "Firmen-WLAN" im Log. (4) 3198-Menue → Allgemein →
  WLAN-Radikal-Reparatur: 1. Klick warnt, 10s warten → entschaerft sich; 2x Klick →
  Reset laeuft, Box startet neu, verbindet sich danach.
- [ ] ⚠️ **Rollout-Hinweis Flotte:** Beim Update AUF 2.4.19 läuft noch das alte BAT der
  Vorversion → dort werden `_internal\BILDER`-Fotos noch gelöscht. Werkstatt-Anweisung:
  vor dem 2.4.19-Update Bilder ziehen (danach ist das Problem dauerhaft behoben).
- [ ] Bekannt, nach dem Release angehen: ~3 s UI-Hänger beim tatsächlichen SELPHY-Druck
  (Druckpfad ist live-flotten-kritisch — nicht vorher umbauen); Startscreen-Neuaufbau mit
  USB-Template ~5 s (läuft zwischen Sessions, kein Gast-Kontakt).
- [x] Nikon-Capture-Feintuning Teil 1: **JPEG-Größe „M" wird jetzt automatisch gesetzt**
  (`nikon_bridge.image_size`, Bridge setzt „Image Size" beim Verbinden; D3300: 4496×3000).
  Wirkung im Nachtest messen.
- [ ] Nikon-Capture-Feintuning Teil 2 (optional, falls immer noch zu langsam): `noaf`-Capture
  für vorfokussierte Box-Distanz (Bridge kann CapturePhotoNoAf bereits als AF-Fallback).

---

## Bugs 🐞 (beim nächsten Software-Update nebenbei mitfixen)

- [ ] **Filter-Screen läuft nicht automatisch ab.** Der Filter-Screen soll automatisch weiterlaufen/ablaufen, tut das aber erst, nachdem man **einmal den Filter gewechselt** hat. (Wahrscheinlich startet der Auto-Ablauf-Timer erst beim ersten Filter-Wechsel statt direkt beim Anzeigen des Screens.)
- [ ] **Box friert nach dem ersten Video ein.** Nach dem ersten Video hängt die Software; ein Tipp auf den Touchscreen löst sie wieder. Vermutlich UI-Thread / Video-Handling (evtl. Zusammenhang mit dem Galerie-Server prüfen). Muss stabilisiert werden.
- [ ] **Drucker-Status-Log entspammen** (nur Loghygiene, kein Verhaltensfehler). Bei ausgeschaltetem Drucker loggt die Box `DRUCKER AUS!` + „Overlay wird gezeigt / kein Overlay" **jede Sekunde** (im Dev-Log aus 2026-06-14: tausende identische Zeilen über ~40 Min) und verdeckt echte Events. Fix: nur bei **Status-WECHSEL** loggen (in `src/app.py` Drucker-Status-Check + `src/printer/controller.py get_error`), Poll-/Klassifizierungs-/Overlay-Logik unverändert lassen. Die INFO-Zeile „Drucker-Fehler erkannt → Overlay wird gezeigt" ist zudem irreführend (danach folgt „kein Overlay (other)") → mitklären. **Erst im Dev-Mode testen** (Kernprinzip 8), nicht in einen Same-Day-Flotten-Build.
- [ ] **Windows-Update-Lockdown härter machen** (nicht dringend, entschieden 2026-07-03: erstmal so lassen). `windows_update_lockdown.log` endet „mit Warnungen": `sc.exe konnte Starttyp nicht setzen: WaaSMedicSvc (Exit 5)` und `DoSvc (Exit 5)` — diese zwei besonders geschützten Dienste lassen sich per `sc.exe config` nicht deaktivieren (Exit 5 = Zugriff verweigert). Ausgerechnet **WaaSMedicSvc** (Update Medic) kann abgeschaltete Updates theoretisch reaktivieren. In der Praxis greift der Lockdown (seit 15.06. keine ungewollten Updates/Neustarts), aber nicht 100 % wasserdicht. **Fix-Idee:** in `setup/disable_windows_update.ps1` für diese zwei Dienste den `Start`-Wert direkt in der Registry (`HKLM\SYSTEM\CurrentControlSet\Services\WaaSMedicSvc` bzw. `DoSvc` → `Start=4`) setzen statt über `sc.exe`; ggf. Registry-Owner/ACL vorher übernehmen. **Live-Flotten-Boot-Script → separat + vorsichtig testen**, nicht in einen Same-Day-Build.

---

## Nikon D3300 DSLR (FexoNikonBridge, Variante 3) 📷

> digiCamControl-App-Ansatz (Variante 2) am 2026-07-02 **verworfen** (sichtbares Fenster +
> Webserver antwortet nie). Neu: eigene unsichtbare `FexoNikonBridge.exe` (C#/.NET 4.8,
> Motor: MIT-Bibliothek `CameraControl.Devices`, rohes PTP über Windows-WPD — wie dslrBooth).
> Python-Seite fertig + gegen Fake-Bridge End-to-End verifiziert.
> Vertrag/Details: [bridge/README.md](bridge/README.md) + [ROADMAP.md](ROADMAP.md).

- [x] **Bridge lokal gebaut + ohne Kamera getestet (2026-07-02):** .NET-SDK 8 auf dem Work-PC
  installiert, `dotnet build` → 0 Fehler; ping/list/init/quit gegen die echte EXE sauber
  (Library-stdout-Banner entdeckt + stummgeschaltet). Python-Client gegen echte Bridge 8/8 OK.
- [ ] **Bridge solo mit angesteckter D3300 prüfen** (am Work-PC möglich, vor dem Fotobox-Test):
  PowerShell: `'{"id":1,"cmd":"init"}' | bridge\FexoNikonBridge\bin\Release\net48\FexoNikonBridge.exe`
  → muss `"ok":true,"camera":"..."` liefern; danach `frame`/`capture` durchspielen
  (oder direkt den kompletten Booth-Flow im Dev-Mode: `python src\main.py --dev`).
- [ ] **CI-Build einmal mitlaufen lassen** (beim nächsten Push; GitHub → Actions → Version `2.4.11`):
  bestätigt, dass auch der Cloud-Build die Bridge baut (Gate schlägt sonst an).
- [ ] **Setup 2.4.11 auf der Fotobox installieren**, `camera_type = nikon` (Admin-Menü),
  Dev-Mode starten. Prüfen: Log „Nikon-Bridge-Warmup: bereit" kurz nach dem Start,
  **kein sichtbares Fremdfenster**, Startscreen bleibt vorn.
- [ ] **LiveView prüfen:** Bild im Session-Screen? (Log: „Nikon/FexoNikonBridge bereit: …")
- [ ] **Capture prüfen:** Vollauflösungs-Foto (≈6000×4000) kommt zurück, kein LiveView-Fallback-Log.
- [ ] **Robustheit:** USB ab-/anstecken während Idle → Status-Warnung erscheint/verschwindet;
  Bridge-Prozess stirbt (Taskmanager) → nächste Session startet ihn neu (initialize-Pfad).
- [ ] **Erst nach erfolgreichem Hardware-Test** als „hardware-validiert" in ROADMAP/FORTSCHRITT markieren.

**Bekannte offene Punkte (Nikon-only, 0 Live-Flotten-Impact):**
- [ ] **(major, entschärft) Erste Session initialisiert auf dem UI-Thread.** Durch den Warmup
  (Bridge-Start + Kamera-Vorverbindung im Hintergrund) bleiben normal nur `lv_start` + erster
  Frame (~1–3 s). Sauberer Fix wäre `initialize()` in einen Worker-Thread in `session.py`
  (Muster `_capture_photo_worker`) — erst nach dem Hardware-Test angehen, betrifft auch Canon-Flow.
- [ ] **(minor) Doppel-Capture** im Fehlerfall: schlägt `capture_photo()` mit `None` fehl, ruft der
  Webcam-Fallthrough in `session.py` `get_high_res_frame()` → erneut `capture_photo()`.
  Spiegelt Canon-Verhalten; ggf. DSLR-Pfad autoritativ machen + Log-Zeile.
- [ ] **(minor) Capture blockiert Frames:** während `capture` läuft, wartet `get_frame()` am
  Bridge-Lock (eine Anfrage gleichzeitig; Timeout deckt das Lock-Warten jetzt ab). Für den
  Booth-Flow okay (LiveView pausiert beim Auslösen sowieso).
- [ ] **OTA-Bootstrap beachten:** Das ERSTE Update auf 2.4.11 läuft noch mit dem alten
  Update-BAT (kopiert `bridge/` nicht) → Nikon-Testbox per **Installer** aktualisieren, nicht OTA.

---

## App-Plattform-Fundament (kommendes Box-Update) 🧱

> Einmaliges, zukunftssicheres Fundament, damit danach Features rein per **App-Update**
> kommen können (App ändern = billig, Box ändern = teuer). Strategie + Begründung:
> [../fexobox-app/PLATTFORM-STRATEGIE.md](../fexobox-app/PLATTFORM-STRATEGIE.md).
>
> **PRODUKTREGEL (wichtig):** Kunden OHNE gebuchte Galerie dürfen auf dem Box-Screen
> **NICHTS** Zusätzliches sehen (kein QR, kein Banner) – sonst denken sie „ist hier was
> versteckt?". Der Kanal läuft **unsichtbar im Hintergrund**; Verbinden ohne Galerie
> läuft komplett über die App (Event-Code + SSID/PW in der App).

**Box-Seite gebaut + verifiziert am 2026-06-14** (Flask `test_client` + Multi-Agent-Review,
0 kritische/hohe Findings). Build/Test auf echter Box steht noch aus (siehe unten).

- [x] **Lokalen Kanal entkoppeln + dauerhaft:** Hotspot + Flask-API laufen unabhängig von
  `gallery_enabled`, Start weiterhin 4 s verzögert. Screen-UI (QR/Banner) unverändert an `gallery_enabled`.
- [x] **Verbinden ohne Galerie nur über App:** `/api/v1/pair-by-code` läuft jetzt immer (Support-Route),
  die Box zeigt nichts an. (App-Seite „Verbinden OHNE QR" bleibt fexobox-app-TODO.)
- [x] **`GET /api/v1/status` erweitert:** `software_version` + `gallery_enabled` + Capability-Liste
  (`settings_patch`, `template_upload`, `asset_upload`, `software_ota`,
  `feature_flags:[live_gallery, print_enabled, print_singles, dslr_camera, max_prints]`).
- [x] **Generische Apply-Endpunkte:** `apply/settings` + `apply/template` (Aliase auf `upload/*`),
  `apply/assets` (sicheres ZIP-Staging) + `apply/software` (OTA). `upload/settings`+`upload/template` bleiben.
- [x] **Feature-Flag-Registry + ehrliche Meldung in `/status`** (Mechanismus steht). _Hinweis:_ Box-UI
  rendert die heute bekannten Flags bereits; konkrete UI für **neue** Flags kommt mit dem jeweiligen Feature.
- [x] **App-OTA-Upload:** `POST apply/software` mit SHA256-Verifikation + bestehendem Rollback,
  Staff-Auth Service-PIN 6588 (als HMAC), nur im Idle. Detailplan: [PLAN-APP-OTA.md](PLAN-APP-OTA.md).
- [x] **Soft-Mode bleibt** – keine Signatur-Prüfung; Log-Warnung „in v2.5.0…" entschärft.

**Noch offen (folgt mit den jeweiligen Features / App-Seite):**
- [ ] **`apply/assets`-Verbraucher:** Endpunkt nimmt Asset-ZIPs sicher entgegen + legt sie ab (Staging).
  Ein konkreter Box-seitiger Verbraucher (z. B. neues Loading-Video übernehmen) wird mit dem Feature nachgezogen.
- [ ] **App-OTA auf einer echten Box testen** (M4 aus PLAN-APP-OTA.md): inkl. absichtlich kaputter ZIP →
  Rollback muss greifen (kein Brick). Vorher: M0 lokale Bandbreite messen.
- [ ] **Optional härter:** Service-PIN für OTA ist 4-stellig (HMAC schützt vor Klartext, nicht vor
  Brute-Force im lokalen Netz). Falls je nötig: zusätzlich Pairing-Token verlangen oder PIN verlängern.

---

## Hoch 🔴

- [x] KRITISCH: Canon DSLR Freeze bei Host-Download behoben (EdsSetObjectEventHandler blockierte Message-Pump)

---

## Mittel 🟡

- [ ] Hotline-Prompt: `Druck-Korrektur` erst aufnehmen, wenn die Funktion offiziell ausgerollt und der Supportablauf bestätigt ist
- [ ] Admin-Menü: "Buchung zurücksetzen" Button
- [ ] Canon DSLR Live-View optimieren (EVF_INTERNAL_ERROR Retry-Logik)
- [ ] Print-Queue Anzeige
- [ ] Drucker-Reset + Fehler-Overlay auf echtem Tablet mit Canon SELPHY testen
- [ ] Event-Wechsel & Systemtest auf Tablet testen (echte Hardware)
- [ ] Erstes GitHub Release erstellen + OTA-Update auf Tablet testen
- [ ] Deployment: Referenz-Tablet einrichten und erstes Image testen
- [ ] Deployment: Clonezilla USB-Stick auf Miix 310 testen (Boot + Capture + Restore)

### Heim-WLAN-Workflow Phase 1 — "Bilder sichern"-Screen lokal

Details siehe ROADMAP.md Abschnitt "Heim-WLAN-Workflow". Kein Backend nötig.

- [ ] `BookingSettings` um Feld `online_gallery: bool` erweitern (`src/storage/booking.py`)
- [ ] `from_dict` mappt `features.online_gallery` aus settings.json
- [ ] `to_dict` schreibt das Feld in den Cache
- [ ] Idempotenz-Datei `.booking_cache/homecheck_handled.json` (Liste verarbeiteter Booking-IDs)
- [ ] Heim-Check-Logik in `src/company_network.py` ergänzen: nach Auto-Update-Block prüfen, ob `last_booking.online_gallery == True` UND `BILDER/<booking_id>/` nicht leer UND Booking-ID noch nicht abgehakt
- [ ] Neuer Modal-Screen "Bilder dieser Buchung jetzt sichern?" (am `FexosafeBackupDialog` orientiert)
- [ ] Button startet vorhandenen `FexosafeBackupDialog`, danach Booking-ID in Idempotenz-Datei abhaken
- [ ] Test: am Tablet im Firmen-WLAN mit echter Online-Galerie-Buchung verifizieren

### Heim-WLAN-Workflow Phase 2 — Box-Identität + Heim-Check-API

Details siehe ROADMAP.md. Setzt Phase 1 voraus, braucht Laravel-Backend-Code.

- [ ] [laravel] `POST /api/v1/box/learn-identity`: Booking-IDs + HMAC-Timestamp → `box_barcode` + Sanctum-Token
- [ ] [laravel] `GET /api/v1/box/{barcode}/homecheck` (Sanctum): letzte Buchung, Alerts, pending Aktionen
- [ ] [laravel] Sanctum auf `Photobox`-Model oder eigene `photobox_tokens`-Tabelle
- [ ] [laravel] IP-Allowlist auf den beiden Endpoints (nur fexon-WLAN)
- [ ] Booth: `box_identity.json` (write-once), Erweiterung im Update-Skript zum Schutz
- [ ] Booth: kleine `booking_history.json` mit den letzten ~3 Booking-IDs
- [ ] Booth: Identity-Learning-Call beim ersten Heim-WLAN-Erkennung wenn keine Identität da
- [ ] Booth: Heim-Check-Call bei jeder Heim-WLAN-Erkennung (Sanctum-Token), auswerten + Screen anzeigen
- [ ] Admin-Screen: kleine Zeile "Box-Identität: FB-XXX ✅" + "Zurücksetzen"-Button
- [ ] Test: gesamter Flow auf Tablet im Firmen-WLAN

### Update-Strategie / Staged Rollout

Details siehe ROADMAP.md Abschnitt "Update-Strategie / Staged Rollout".
Bis Phase 2 steht: Disziplin mit GitHub-Pre-Release-Flag (kein Code).

**Stufe Auto-Rollback (eigenständig, unabhängig von Phase 2):**
- [ ] `src/updater.py`: `_internal_OLD/` 24 h aufbewahren statt sofort löschen
- [ ] Beim ersten App-Start nach Update: Smoke-Test (Kamera/Drucker/Config/Galerie-Server)
- [ ] Bei Smoke-Test-Fehler: automatischer Rollback auf `_internal_OLD/`
- [ ] Markierung in `update_history.json` damit kein Endlos-Rollback-Loop entsteht

**Stufe Release-Manager (mit Phase 2):**
- [ ] [laravel] Tabelle `photobox_version_pins` (photobox_id, target_version, channel, set_at)
- [ ] [laravel] Heim-Check-Response um `update_channel` + optional `target_version` erweitern
- [ ] Booth: `update_channel` + optionalen Pin im Updater berücksichtigen (statt nur GitHub-Latest)
- [ ] [laravel] Release-Manager-UI: Übersicht aller Boxen pro Release mit Status + Health
- [ ] [laravel] Wellen-Steuerung: explizite Box-Auswahl / Anzahl / Prozent
- [ ] [laravel] "Welle stoppen", "Auf alle ausrollen", "Box auf Version fixieren"
- [ ] Booth meldet aktuelle Version + Smoke-Test-Status im Heim-Check für Dashboard-Übersicht

---

## Niedrig 🟢

### Heim-WLAN-Workflow Phase 3 — Auto-Upload (optional, nach DSGVO-Klärung)

Details siehe ROADMAP.md. Datenschutz vorab klären, dann erst angehen.

- [ ] Datenschutz prüfen: Upload nur bei `online_gallery == True` reicht als Zustimmung?
- [ ] Workflow definieren: Mitarbeiter-Freigabe vor Sichtbarmachung in Kundengalerie?
- [ ] [laravel] `POST /api/v1/box/{barcode}/gallery-image` (idempotent per File-Hash)
- [ ] [laravel] Server-side Throttling damit Heimkehr-Welle die Leitung nicht sättigt
- [ ] Booth: Upload-Queue mit Resume bei Verbindungsabbruch
- [ ] Booth: lokale Markierung erfolgreich hochgeladener Bilder
- [ ] Booth: Auto-Upload-Trigger wenn Heim-Check sagt "Bilder fehlen für diese Buchung"

---

## Erledigt ✅

### 2026-07-02
- [x] **🎉 Nikon D3300 hardware-validiert:** FexoNikonBridge auf der Fotobox erfolgreich —
  unsichtbarer Warmup, LiveView, 4× Capture in 6000×4000. (Log `fexobooth_20260702_114253.log`)
- [x] Performance-Analyse-Lauf ausgewertet + 4 Fixes umgesetzt (Overlay-Basis-Cache,
  Fotoanzeige-Cache, Filter-Arbeitskopien + Precache, Final-Rendern im Worker) → Build `2.4.12`.
- [x] digiCamControl-Ansatz verworfen und restlos zurückgebaut (Autostart, Installer-Einbettung,
  CI-Download, i18n `DCC FEHLT!`, Felix-Runbook). Neue Architektur FexoNikonBridge (Variante 3)
  vorbereitet: C#-Bridge-Gerüst + Python-Client + CI-Build-Schritt; Build-Kandidat `2.4.11`.
  Verifiziert: Smoke-Test 82/82, Fake-Bridge-E2E 11/11.

### 2026-07-01
- [x] Nikon-DCC-Logging im Developer Mode erweitert und Build-Kandidat auf `2.4.9` gesetzt.
- [x] Startscreen-Version umgesetzt: Top-Bar zeigt links neben `FEXOBOOTH` die lokale Version aus
  `src/__init__.py`; Build-Kandidat auf `2.4.8` gesetzt.

### 2026-06-19
- [x] **Druck-Korrektur (2015er-Menü) wird beim Neustart nicht mehr zurückgesetzt.** `print_adjustment` stand fälschlich in den bei jedem Start erzwungenen Produktions-Overrides (`_PRODUCTION_DEFAULT_OVERRIDES` in `src/config/config.py`) → Override gewann gegen die gespeicherten Werte. Entfernt; Start-Default kommt aus `defaults.py`, Eventwechsel-Reset bleibt über `reset_event_defaults()`. Mit simuliertem Neustart verifiziert.

### 2026-06-14
- [x] App-Template-Push stabilisiert: wiederholte Template-Uploads nutzen eindeutige `app_template_*.zip` Dateien statt gesperrte `cached_template.zip` zu überschreiben; Apply-Marker fuer Settings/Template werden getrennt bestaetigt. Regressionsnotizen in `docs/FEXOBOX-APP-API.md`.

### 2026-05-20
- [x] Hotline-Prompt „Felix" auf reinen V2-Modus umgestellt (alle Boxen jetzt auf V2). V1-Blöcke, Versions-Gate und USB-Hub-Lampen-Diagnose aus `support/HOTLINE_PROMPT_FELIX.md` entfernt.

### 2026-04-23
- [x] Auto-Update im Firmen-WLAN (SSID-Whitelist + Internet-Check, still im Background)
- [x] FEXOSAFE-Backup mit Buchungs-ID als Überordner

### 2026-03-18
- [x] USB-Sync Dialog kommt nicht bei Stick-Wiedereinstecken (gleicher Event) — behoben
- [x] `_offer_sync_dialog`: try/except im Thread, Fallback auf pending_count, Logging

### 2026-03-17
- [x] `prepare_image.bat`: Windows-Optimierung + Daten-Bereinigung für Image-Erstellung
- [x] Script wird über Installer mitinstalliert (`deployment/` Ordner + Startmenü)

### 2026-03-13
- [x] Template-Karte: "Wunsch-Template" statt Buchungsnummer/Dateiname anzeigen
- [x] Header-Text anpassen bei nur einer Karte ("Dein Druckformat" statt "Wähle dein Layout!")
- [x] USB-Template vs. User-Template Trennung (Override-Flag)
- [x] Capture-Hintergrund: Weiß statt Schwarz
- [x] LiveView Template-Overlay Absicherung

### 2026-03-12
- [x] Template-Loader: preview.png nicht als Overlay verwenden (Default-Template Fix)
- [x] Start-Screen Refresh nach Template-Wechsel im Kunden-Menü (PIN 2015)
- [x] Galerie: Sharing-Erkennung + Hinweis bei HTTP (kein File-Share ohne HTTPS)

### 2026-03-11
- [x] Kunden-PIN "2015" mit Service-Menü (Template-Auswahl, Overlay-Toggle, Druckstau, Neustart)
- [x] 5x Icon-Tap Neustart entfernt (durch Kunden-PIN ersetzt)
- [x] Filter-Screen: Labels entfernt, Preview größer (Lenovo-Optimierung)
- [x] USB-Status-Indikator feste Breite (Frame-Container statt Label-Width)
- [x] Template-Auswahl mit Vorschau-Bildern aus assets/templates/ Ordner
- [x] Admin-Dialog: Kiosk-Modus ohne Fensterwechsel (alles als Fullscreen-Overlay)
- [x] Admin: Minimieren-Button im Kiosk-Modus

### 2026-03-10
- [x] Export-Dialog blockiert UI (Boot-Drives, grab_set)
- [x] ZIP-Validierung: Anwendungs-ZIPs (.exe, .dll, _internal/) als Template ablehnen
- [x] Default-Template.zip als Fallback einbauen (statt programmatisches 2x2-Grid)
- [x] Freeze-Analyse: Ursache gefunden (fexobooth.zip als Template → 6889x6889 Logo als Overlay → 41s Freeze)
- [x] PowerShell UTF-8 Encoding Fix (`[Console]::OutputEncoding` in allen Subprocess-Aufrufen)

### 2026-03-09
- [x] Drucker-Steuerung: Software-Reset bei Papierstau (3 Stufen: Purge → Spooler → USB)
- [x] Drucker-Steuerung: Canon-Dialoge per SW_HIDE verstecken + eigene Fehlermeldungen
- [x] Drucker-Steuerung: TOPMOST-Overlay mit Bestätigungs-Button ("PAPIER EINGELEGT")
- [x] Drucker-Steuerung: Canon-Dialog-Text per WM_GETTEXT lesen
- [x] Drucker-Steuerung: PowerShell/Konsole-Fenster versteckt (CREATE_NO_WINDOW)
- [x] Dev-Mode: "DRUCKER RESET" Test-Button in Top-Bar
- [x] Template-Overlay im LiveView als Option im Admin-Menü (Kamera-Tab)

### 2026-02-26
- [x] KRITISCH: EDSDK Deadlock behoben (System-Test hing, Tablet musste hard-reboot)
- [x] System-Test: Globaler Timeout (90s) + Abbrechen-Button
- [x] Ctrl+Shift+Q funktioniert jetzt in ALLEN Dialogen (auch mit grab_set)
- [x] Kamera-Status-Anzeige in der Top-Bar (blinkend wenn keine Kamera angeschlossen)
- [x] Canon DSLR ohne SD-Karte: Host-Download entfernt (unzuverlässig), sofort LiveView-Fallback statt 10s Hänger
- [x] Taskleiste: atexit-Handler + Recovery beim App-Start (kein permanentes Verschwinden mehr nach Crash)
- [x] Fix: Permanentes `-topmost` blockierte ALLE Dialoge (USB-Sync, Export, Task-Manager)
- [x] Kiosk-Modus: topmost nur noch kurz bei Fenster-Positionierung (nicht permanent)
- [x] Windows-Benachrichtigungen via Registry unterdrücken (statt topmost-Overlay)
- [x] Notfall-Shortcut Ctrl+Shift+Q zum App-Beenden (auch im Kiosk-Modus)

### 2026-02-25
- [x] Kiosk-Modus: Taskleiste via Windows API verstecken (kein Durchblitzen mehr)
- [x] Kiosk-Modus: Fullscreen-Restore sofort nach Admin/Service-Dialog (nicht 10s Timer)
- [x] Kiosk-Modus: Escape/F11 blockiert (nur per Admin-PIN Vollbild verlassbar)
- [x] Kiosk-Modus: Sicherheitsnetz alle 5s re-assertet Taskleiste
- [x] Fix: Service-PIN Dialog hat Fullscreen nie wiederhergestellt
- [x] Fix: USB-Dialoge (Sync + Export) Vordergrund erzwingen (transient + lift + focus_force)
- [x] USB-Dialoge: Auto-Close nach Kopiervorgang (3s Erfolg, 4s Fehler)
- [x] Final-Screen: Template-Vorschau vollständig sichtbar (nicht mehr abgeschnitten)
- [x] Drucker-Lifetime-Zähler: Gesamt-Drucke im Admin-Menü anzeigen
- [x] Drucker-Lifetime-Zähler: Reset nur per Service-PIN (6588)

### 2026-02-12
- [x] Deployment-System: `deployment/` Ordner mit Clonezilla-Klon-Workflow
- [x] OTA-Update System: Service-Menü Button "Software aktualisieren"
- [x] update_from_github.bat: GitHub Releases statt Source-Archiv
- [x] build_installer.bat: Erstellt immer ZIP für OTA-Updates
- [x] Neues Modul: src/updater.py (GitHub API, Download, Update-Script)

### 2026-02-11
- [x] System-Test: Komplette Session mit Foto pro Slot + automatischer Testdruck
- [x] System-Test "Keine Template-Boxen geladen" Fix (reset_session Reihenfolge)
- [x] USB-Sync: Bestätigungsdialog statt Auto-Kopie (Fortschritt + Abbrechen)
- [x] Service-PIN 6588 Freeze behoben (Dialog-Erstellung nach wait_window)
- [x] Beenden-Button in Admin-Dialog verschoben (nicht mehr im Hauptfenster)
- [x] Galerie zeigt nur lokale Bilder (nicht USB) + No-Cache Headers
- [x] Event-Wechsel-Dialog bei neuem USB-Template (Annehmen/Ablehnen)
- [x] Automatischer System-Test nach Event-Wechsel (Kamera → Template → Druck)
- [x] FEXOSAFE Backup-Stick Erkennung und Bilder-Sicherung
- [x] Pending-Dialog-Queue (Dialoge warten auf StartScreen)
- [x] Strom-Status: Grüner/oranger Blitz in Top-Bar (Netz vs. Akku)
- [x] Drucker-Status blinkende Warnung wenn Drucker aus/offline (wie USB-Warnung)
- [x] Belastungstest-Button im Developer Mode (Top-Bar)

### 2026-02-10
- [x] Flash-Bild gecacht + update_idletasks() für zuverlässige Anzeige
- [x] Loading-Screen: "Das kann bis zu 2 Minuten dauern" Hinweis
- [x] Statistik-Texte weiß (text_primary statt text_muted)
- [x] Auto-Fullscreen nach 10s wenn nicht im Vollbild (nach Admin-Menü)
- [x] Hotspot Encoding-Fix (UnicodeDecodeError cp1252)
- [x] Desktop-Icon Fix: ICO separat in Installer kopiert (PyInstaller _internal-Pfad)
- [x] Offline-Hotspot: hotspot.py mit Multi-Methoden-Ansatz (Tethering + netsh hostednetwork)
- [x] Galerie-Deaktivierung Fix (Booking-Settings überschrieben Config)
- [x] Willkommensnachricht im VLC-Ladescreen (shipping_first_name)
- [x] `live_gallery` statt `online_gallery` als Booking-Meta-Feld
- [x] Bilder löschen: Auch Gallery-Server-Pfad leeren
- [x] Foto-Zähler "5 von 4" beim letzten Foto gefixt
- [x] Flash-Bild zuverlässiger (sofortige Anzeige statt Loop-Tick)
- [x] Template-Karten responsiv (1 Karte=groß, 2=mittel, 3+=klein)
- [x] Print-Vorschau vollständig sichtbar (padx 40→10)

### 2026-02-09
- [x] Flash-Bild Fix: CTkImage dark_image im Dark Mode (Auslöse-Bild wurde nicht angezeigt)
- [x] Redo pro Collage-Foto: "↻ NOCHMAL" Button nach jedem Einzelfoto statt am Ende
- [x] Template-Persistenz: USB-Template wird lokal gecacht (überlebt USB-Abzug + Neustart)
- [x] Final-Screen: Schwarze Container-Hintergründe entfernt (transparente Overlays)
- [x] App-Icon: Multi-Size ICO (16-256px) statt nur 16x16 (war verpixelt)
- [x] Installer: ie4uinit.exe Fehler behoben + PowerShell-Fallback + Desktop-Icon immer überschrieben
- [x] VLC-Warmup beim App-Start (57s Freeze auf Miix 310 behoben)
- [x] Hotspot Start/Stop in Hintergrund-Threads (6.3s Blockierung behoben)
- [x] LiveView immer Vollbild (Template-Overlay entfernt)
- [x] Final-Screen: Buttons größer als Overlay über Bild
- [x] App als Vordergrund-Prozess im Taskmanager (fullscreen statt overrideredirect)

### 2026-02-06
- [x] Bug Fix: Logo-Anzeige (CTkImage dark_image für Dark Mode)
- [x] Neuer Filter: "Insta Glow" (Instagram-Style)
- [x] Countdown-Ton und Foto-Beep komplett entfernt
- [x] Service-Menü: Internes Wartungsmenü über PIN 6588 (Bilder sichern, Bilder löschen)
- [x] PIN-Dialog: Responsive Größe, Zentrierung, Schließen-Button, eigene Farbe
- [x] Performance-Optimierung: Doppelter Screen-Wechsel, VLC-Cleanup, Template-Cache, Overlay-Cache

### 2026-02-05
- [x] Arbeitsumgebung erstellen (CLAUDE.md, ARBEITSWEISE.md, etc.)

### 2026-02-04
- [x] Video-Fix für schwache Hardware (MSMF Backend)
- [x] Threading für Video-Wiedergabe
- [x] Offline-Hotspot Setup überarbeiten

### 2026-02-03
- [x] Admin-Menü: Galerie-Tab
- [x] Admin-Menü: Statistik-Tab
- [x] QR-Code Widget überarbeiten
- [x] Buchung + Template Persistenz
- [x] Shared USBManager implementieren
- [x] Lokale Galerie mit Flask-Webserver
- [x] Statistik-Modul

### 2026-02-02
- [x] settings.json Support
- [x] USB-Sync Feature
