# TODO - Fexobooth V2

> Letzter Abgleich mit Ist-Stand: 06.09.2026 (Code, Git, Doku, Live-Systeme)

Aufgabenliste mit Prioritäten.

> **Flottenstand 06.09.2026** (280 Boxen, 239 melden sich): **221× 2.4.45**, 9× 2.4.33,
> Nachzügler **001/029/117 auf 2.4.14**, **237 auf 2.4.25**; Testbuilds: 245 = 2.4.61,
> 248 + 027 = 2.4.62, 252 = 2.4.63, 167 = 2.4.64. **Box 073 stumm seit 19.08.**
> Code steht auf **2.4.66**: Artefakt gebaut (Action-Run 33978302086, 05.09.), aber
> **kein GitHub-Release und keine Box im Feld** (keine 2.4.65/2.4.66 gemeldet).
> Latest Release = v2.4.45 (20.08.), Auto-Update zeigt darauf. 41 Boxen ohne Software-Meldung.

---

## ➡️ NÄCHSTER TEST: 2.4.68 DAUERLAUF, DANN ROLLOUT 🔴

Stand 06.09. nachmittags: Der Hänge-Wächter hat beim dritten Freeze (14:17,
Session 6) den Stack-Dump geliefert → Ursache Tkinter-GC-Deadlock, Fix in
2.4.68 (Müllabfuhr in den Hauptthread verlagert; Details CHANGELOG).

- [x] Freeze eingefangen: Stack-Dump in absturz.log (MainThread in
      Thread.start(), neuer Thread in tkinter font.__del__ → Deadlock).
- [x] 2.4.68 umgesetzt: gc.disable() + _gc_takt() alle 30 s im Hauptthread;
      `test_gc_hauptfaden.py` grün.
- [x] **Installer 2.4.68 gebaut + Dauerlauf bestanden** (06.09., Box 101,
      15:21–18:41): 175 Stress-Sessions OHNE Freeze (vorher fror es im
      Schnitt alle ~85 ein), sauberes Ende per Service-Menü. Beide
      Schutz-Zeilen im Startlog, kein neuer Timeout-Dump in absturz.log,
      176 neue Prints / 0 weiße, Hotspot 0 Reparaturen. Müllabfuhr: 397
      Läufe, Ø 102 ms, max 225 ms — UI-Hitches pro Session unverändert
      (9,4 vs. 9,2 im Vormittagslauf).
- [x] **2.4.70 UI-Redesign umgesetzt** (06.09. nachts, Handoff „Fexobox
      UI-Redesign Modern"): alle 5 Gäste-Screens + Drucker-Dialog, i18n
      7 Sprachen, Assets ~60 KB, `test_redesign_vertraege.py` grün.
      Details FORTSCHRITT.md (inkl. 4 dokumentierte Handoff-Abweichungen).
- [x] Erster Box-Test 2.4.70 (06.09. abends): 5 Maengel gefunden →
      alle in 2.4.71 behoben (DPI-Skalierung war Kernursache; Details
      CHANGELOG 2.4.71).
- [x] Zweiter Box-Test (2.4.71): Ueberlappung + Filter-Footer WEITER kaputt
      → 2.4.72 mit wirksamer DPI-Kompensation, gekoppelter QR-Panel-Position,
      bottom-first-Filter und Layout-Pruefstand (tools/ui_layout_probe.py,
      beide DPI-Faktoren gruen).
- [ ] **Dauertest 2.4.72 auf Box 101** (Christian): Installer laden,
      Dev-Mode, einmal ALLE Screens von Hand durchgehen (Start mit QR-Panel,
      Session mit Pills + Review-Leiste, Filter-Kacheln, Final mit
      Render-Panel + Drucken, Drucker-Dialog per Dev-Button „DRUCKER
      RESET"), DANN Stress-Test über Nacht. Erwartung: nichts mehr beschnitten/
      überlappend, LiveView wieder ~12 fps (Log: LIVEVIEW-PERF), Filter-
      Kacheln sofort da, kein Druckzähler bei Einzeldruck; 0 weiße Prints,
      0 Freezes. Danach Logs an Claude.
- [ ] **Noch offen aus dem 2.4.65-Plan:** Reparatur-Test (Hotspot in Windows
      von Hand ausschalten → nach ≤2 Min von selbst wieder an, Block in
      `netzwerk.log`) und QR-Sofort-Scan direkt nach Box-Neustart.
- [ ] Rollout: Box 248 (meldet aktuell 2.4.62), dann die nächsten 5
      Rückläufer mit Live-Upgrade fürs kommende Wochenende, dann Rest
      (221 Boxen laufen auf 2.4.45 mit dem Weiß-Print-Bug). Rollout-Stand
      ist 2.4.68 (enthält Hotspot-, Print- und Freeze-Fix + Hänge-Wächter).

Erledigt auf dem Weg hierher (Details FORTSCHRITT.md): Hotspot-Test 05.09.
grün; Weiße-Print-Fix 2.4.66 im Dauerlauf bestätigt (85 Sessions, 0 weiße);
Hänge-Wächter 2.4.67 hat beim dritten Freeze den entscheidenden Stack-Dump
geliefert.

- [ ] 🟡 Nachzügler beim Rollout mitnehmen: **001/029/117 (2.4.14)** und
      **237 (2.4.25)**. Achtung bei 001/029/117: das alte Update-BAT der 2.4.14
      löscht noch `_internal\BILDER` → vorher Bilder ziehen (BILDER-Migration
      kommt erst ab 2.4.19), am besten per Installer statt OTA.

## ➡️ NÄCHSTER TEST: VLC-LANGZEITLAUF (Stand 2.4.64, läuft auf Box 167) 🔴

- [x] Box-167-Log ausgewertet: 608 Videos, 548/548 Webcam-Aufnahmen, aber
      34 offene VLC-Cleanups und spaeter starker RAM-/CPU-Anstieg samt
      LiveView-FPS-Abfall.
- [x] 2.4.64 umgesetzt: ein persistenter VLC-Player, 608/608 explizite
      Media-Freigaben, maximal ein Fehler-Cleanup, sichere Playback-Timer,
      getrennter OpenCV-Fallback und `VLC-LIFECYCLE`-Diagnose. Keine Aenderung
      in `src/camera/webcam.py` oder an DSLR-Capturepfaden.
- [x] 2.4.64 gebaut und installiert – Stand 06.09.: **Box 167** meldet 2.4.64
      (hier stand vorher fälschlich Box 155).
- [ ] Stress-Test mindestens bis 608 Videos und 548 Aufnahmen laufen lassen.
      Erwartung: 548/548 Fotos, `creations=1`, `cleanup_pending=0`, kein
      anhaltender RAM-/CPU-Anstieg und kein spaeter LiveView-FPS-Einbruch.
      **Hinweis:** kann direkt mit 2.4.66 laufen (enthält 2.4.64 komplett),
      dann spart man sich den Extra-Build.
- [ ] Log im Service-Menue ans Dashboard senden und gemeinsam auswerten.

## DSLR-Nachweise (Stand 2.4.64) 🟡

> Vollständige Übergabe: **[DSLR-STAND.md](DSLR-STAND.md)** — dort erst lesen.
> (Stand 06.09.: laut DSLR-STAND.md ist die Hardware-Abnahme auf Box 248 noch offen.)

### Nikon D3300 auf Box 252

- [x] 2.4.62-Log ausgewertet: Bridge startet und antwortet, Admin-Liste ist
      wirklich leer, `init` endet nach rund 15 Sekunden vor Live View/Capture.
      Der UI-Eintrag `[0] Nikon via FexoNikonBridge` ist nur ein Platzhalter.
- [x] 2.4.63 als reinen Diagnosebuild umgesetzt: Bridge-`diag`, interne
      WPD-/WIA-Librarymeldungen, Scanstatus, Request-/Lock-Timings,
      Windows-PnP/Prozesse und Bridge-Dateihashes. Keine Erkennungs- oder
      Capture-Semantik geaendert.
- [x] Lokalen und GitHub-Builder gegen alte Bridge-Binaerdateien abgesichert:
      Bridge wird frisch gebaut; Developer- und normaler Produktionspfad
      werden per Protokolltest geprueft.
- [x] Lokale Abschlusspruefung: Bridge 0 Warnungen/0 Fehler, Nikon-Diagnose
      **11/11**, gesamte DSLR-Suite **20/20 Testgruppen**, echter kontrollierter
      15-Sekunden-Init ohne Kamera sowie `py_compile` und Nikon-Smoke-Test gruen.
- [x] Hardwareursache bestaetigt: Es war das USB-Kabel. Kein Nikon-Codefix aus
      diesem Ausfall erforderlich; die 2.4.63-Diagnose bleibt erhalten.
- [ ] Bei Gelegenheit einen kurzen Nikon-Smoke-Lauf machen, weil derselbe
      gemeinsame Build ausgeliefert wird. Erwartung: Erkennung, LiveView und
      Vollbild-Capture unveraendert. (Stand 06.09.: Box 252 meldet 2.4.63;
      Smoke-Lauf kann direkt mit 2.4.66 erfolgen.)

### Canon EOS 2000D auf Box 248

- [x] **2.4.61 auf Box 245 getestet:** Vier echte 6000-x-4000-JPEGs,
      einschliesslich des ersten Fotos; Press, Release, Blitz, Transfer und
      Anzeige je Capture genau einmal. Der Blitz folgte Press-Return nach
      60 bis 65 ms, kein `CARD_NG`, Retry, Doppelbild oder Notbild.
- [x] **Box-248-Fehler ohne SD-Karte belegt:** EOS 2000D erkannt, Session und
      alle Pflichtschritte des Hostwegs erfolgreich; nur `AvailableShots=0`
      wurde von 2.4.61 faelschlich als fatal behandelt. Wahlrad steht auf `P`.
- [x] 2.4.62 umgesetzt: Null nach bestehender Ein-Sekunden-Schonfrist als
      kartelosen Hostbetrieb akzeptieren; klare Warnung und
      `readiness=save_to+capacity`. Pflichtfehler und unplausible andere Werte
      bleiben fatal; kein Dummyfoto, Retry oder Kartenfallback.
- [x] Lokale Abschlusspruefung: **18/18 Windows-Tests**, integrierter
      Null-Hosttransfer, `py_compile` und `git diff --check` gruen;
      `webcam.py`, `nikon.py`, `canon.py` und `session.py` ohne Diff.
- [x] **2.4.62 gebaut und auf Box 248 installiert** – Stand 06.09.: Box 248
      meldet 2.4.62. (Beim Test: dslrBooth vorher vollstaendig schliessen,
      damit nur FexoBooth die EOS besitzt; ohne SD-Karte, `--dev`, Wahlrad `P`.)
- [ ] Im Startlog die Kette `EOS 2000D gefunden -> Session geoeffnet ->
      SaveTo=Host -> Capacity ok -> AvailableShots bleibt 0 -> CANON-HOST READY
      ... readiness=save_to+capacity` pruefen. LiveView muss erscheinen.
      (Stand 06.09.: Auswertung steht aus, Hardware-Abnahme laut DSLR-STAND offen.)
- [ ] Eine vollstaendige Session aufnehmen. Pro Foto genau einmal
      `PRESS-START`, `PRESS-RETURN`, `RELEASE-RETURN`, `CANON-FLASH REQUEST`,
      `CANON-FLASH SHOWN`, Transfer-JPEG und `CANON-PHOTO SHOWN`.
- [ ] Erwartung: echte 6000-x-4000-JPEGs; kein schwarzer Canon-Balken,
      `CARD_NG`, Retry, Doppelbild oder Live-View-Notbild.
- [ ] Log im Service-Menue ans Dashboard senden und Codex Bescheid geben.
- [ ] Bei `CARD_NG`, `CANON-OWNER TIMEOUT`, `CAPTURE TIMEOUT` oder fehlender
      Transferkette keinen Umbau auf Verdacht starten; zuerst genau dieses
      eine Dev-Log auswerten. (06.09.: nicht am Code prüfbar – braucht das
      Dev-Log der Box.)
- [ ] Nur falls der normale Host-Capture nicht eindeutig ist: danach einmal
      `fexobooth.exe --dev --dslr-test` fahren und dessen Log ebenfalls senden.

## Flotte: Nachzügler, stumme Boxen, Uhrzeit 🟡

> Neu aufgenommen beim Abgleich 06.09.2026 (Quelle: Dashboard-Meldungen + zentrale TODO).

- [ ] 🟡 **Box 027 (Normalbox) meldet den DSLR-Testbuild 2.4.62** – prüfen, wie
      der Build dort hinkam (versehentlich installiert?); beim 2.4.66-Rollout
      auf den regulären Stand bringen.
- [ ] 🟡 **Uhrzeit-Sync Box 202/036** (Punkt aus der zentralen TODO
      `fexobox-next/TODO.md`, hier bisher nicht geführt) – aus der DB nicht
      ableitbar, nur Build-seitig lösbar (Zeitabgleich in der Box-Software).
- [ ] **Box 073 stumm seit 19.08.** (letzte Meldung 2.4.33) – in der Werkstatt
      mit 2.4.66 durchtesten. (116/016 melden sich wieder.)
- [ ] 🟢 **41 Boxen (von 280) ohne Software-Meldung** im Dashboard – bei
      Rückläufern in der Werkstatt mit abgleichen.

## Offen: Standbild zeigt anderen Bildausschnitt als das finale Foto 🟡

> Mehrfach gemeldet. Zwei Anteile: Zeitversatz (schrumpft, sobald Fotos
> schnell ankommen) und unterschiedlicher Bildausschnitt zwischen Vorschau
> und Aufnahme. Letzteres ist ein eigenes Thema, noch nicht angefasst.
> (Stand 06.09.: nur noch für DSLR-Boxen relevant.)

- [ ] Erst angehen, wenn die Aufnahme steht — vorher nicht sinnvoll messbar

## Offen: Belichtung ohne Blitz 🟡

> Randbedingungen von Christian: kein Blitz, Autofokus MUSS aktiv bleiben,
> Kunde darf an der Kamera nichts einstellen. Die im 2.4.59-Test sichtbare
> Ueberbelichtung kam von der verstellten Belichtungskorrektur und ist behoben.
> 2.4.60 warnt beim Verbinden vor einem Wert ungleich null und schreibt im
> Dev-Modus EDSDK-, EXIF- und Helligkeitswerte, ohne die Kamera zu verstellen.
> (Stand 06.09.: Box 245 meldet 2.4.61, Testlauf steht aus.)

- [ ] Nach dem nächsten Testlauf Belichtungszeit, Blende, ISO,
      Belichtungskorrektur und Helligkeitsdiagnose auswerten
- [ ] Bei zu langen Belichtungszeiten Lösung suchen, die alle drei
      Randbedingungen einhält

## Falls das neue Log einen echten USB-Abbruch zeigt 🔴

> Box 248 meldete `COMM_DISCONNECTED`, Box 245 `DEVICE_BUSY`. Beides heißt:
> Die Kamera ist weg. Auf den Lenovo Miix mit Webcam gab es das nie.
> Die Software fängt den Fall jetzt ab (Neuaufbau statt Endlosschleife) —
> die Ursache ist damit aber nicht beseitigt.
> (06.09.: nicht am Code prüfbar – braucht Hardware-/Log-Befund von der Box.)

- [ ] Nur bei `COMM_DISCONNECTED`/USB-Bus-Fehler: USB-Energiesparen (USB
      Selective Suspend) im
      Geräte-Manager und im Energieplan abschalten
- [ ] Verdacht prüfen: Kamera-Ruhezustand (Auto-Power-Off) am Kameramenü aus
- [ ] Verdacht prüfen: USB-Kabel/Port am neuen Tablet (Strom über USB?)
- [ ] Prüfen ob die Abbrüche zeitlich mit etwas zusammenfallen (Akkubetrieb,
      Bildschirm aus, Standby)

## Kamera-Akku und Fokus-Art im Log prüfen 🟡

> Das neue Logging schreibt vor jedem Auslösen Akkustand, Programmwahlrad und
> Fokus-Art ins Log. Steht der Fokus auf Autofokus, kann die Kamera im dunklen
> Box-Inneren das Auslösen verweigern, ohne dass die Software etwas falsch macht.
> (06.09.: nicht am Code prüfbar – braucht ein Test-Log von der DSLR-Box.)

- [ ] Nach dem nächsten Test die Zeile `[3/5] Kamera-Zustand:` auswerten
- [ ] Autofokus **aktiv lassen**. Bei `TAKE_PICTURE_AF_NG` Beleuchtung,
      Motivabstand und AF-Hilfslicht prüfen; die Software löst bewusst kein
      zweites Foto ohne Fokus-Zwang aus.

---

## Werkstatt-Knopf „Netzwerk-Werksreset" endlich einmal testen 🟡

> Steht seit 2.4.27 unabgehakt. Der Knopf ist die einzige per Fingertipp
> erreichbare Stelle, die `netsh int ip reset` / `winsock reset` ausfuehrt —
> aber es gibt bis heute keinen Beleg, dass er je etwas geheilt hat.
> (Stand 06.09.: weiterhin ungetestet – reiner Hardware-Test in der Werkstatt.)

- [ ] In der Werkstatt (fexon WLAN in Reichweite): 3198 → Allgemein →
      1. Tippen zeigt „Prüfe Firmen-WLAN...", dann Warnung; 10 s warten →
      entschaerft sich von selbst.
- [ ] 2x tippen → Reset laeuft, Box startet neu und verbindet sich danach.
- [ ] **Ausserhalb** des Firmen-WLAN antippen → muss „Nicht möglich — fexon
      WLAN nicht in Reichweite" zeigen und NICHTS tun.
- [ ] Danach pruefen: `netsh wlan show profiles` — es muss mindestens das
      Firmen-Profil dastehen (bei 0 Profilen geht der Gaeste-Hotspot nicht).

---

## Beenden-Knopf (3198): Restpunkte aus der 2.4.36-Gegenpruefung 🟡

> 06.09.: Die Kamera-Messungs-Gegenpruefung (bedienbar, Abbrechen, Messung
> durchlaufen) ist durch 2.4.37/2.4.39 ersetzt und die Messung ist gelaufen
> (→ Erledigt). Der 2.4.35-Beenden-Knopf ist auf der Box bestaetigt. Uebrig
> bleiben zwei Punkte, die nur auf einer Box pruefbar sind.

- [ ] Nach der Messung Task-Manager pruefen: kein zweites `fexobooth.exe` uebrig.
      (06.09.: nicht am Code prüfbar – Box-Test.)
- [ ] **Nikon-Box:** Nach dem Beenden pruefen, ob `FexoNikonBridge.exe` wirklich
      verschwindet (bisher nur auf einer Webcam-Box getestet).
      (06.09.: nicht am Code prüfbar – nur auf Box 252 testbar.)

---

## Abstuerze im Normalbetrieb (2.4.30) — Restpunkt 🟡

> Kurzfassung (06.09.): Ursache gefunden (zwei Threads oeffneten dieselbe
> DirectShow-Kamera → Heap-Zerstoerung, Code `0xc0000374`), gefixt in 2.4.31 mit
> gemeinsamer Kamera-Sperre; Nachtest Box 044 bestanden; CPU-Fehlalarm beim
> Testdruck in 2.4.32 gefixt. WER-Dumps und die Dashboard-Ausloeser-Pruefung
> sind damit ueberholt (→ Erledigt). `absturz.log` + `faulthandler` bleiben aktiv.

- [ ] Verdaechtige bei `ntdll` + `0xc0000005` eingrenzen: Kamera (OpenCV/DirectShow), VLC,
      Druckertreiber. (Stand 06.09.: Ursache war der Kamera-Doppelzugriff; Punkt nur noch
      relevant, falls auf 2.4.45+ neue `ntdll`-Abstuerze in `absturz.log` auftauchen.)

## Galerie-Server: Thumbnail-Cache 🟡 (Etappe 2 des App-Plans „Offline-Galerie + Cloud-Relay", 2026-07-03)

> Detailplan: [../fexobox-app/docs/PLAN-OFFLINE-GALERIE-CLOUD-RELAY.md](../fexobox-app/docs/PLAN-OFFLINE-GALERIE-CLOUD-RELAY.md) §5.
> Hintergrund: `server.py` rechnete jedes Thumbnail bei JEDEM Abruf neu — der Cache
> `BILDER/.thumbs/` ist seit 2026-07-03 gebaut und mit der Flotte ausgeliefert (→ Erledigt).

- [ ] Optional: Thumb direkt beim Foto-Speichern erzeugen (kein Gast zahlt die Erst-Wartezeit)

## Performance vor Release 🏎️ — Restpunkte (Analyse-Lauf 2026-07-02, Fixes in 2.4.12)

> Log `fexobooth_20260702_114253.log` (Nikon-Session): 4 Bremsen identifiziert und gefixt —
> Overlay-Foto-Skalierung pro Frame, Fotoanzeige-Refresh (380 ms/Tick), Filter auf 24-MP-Originalen,
> Final-Rendern im UI-Thread. Nachtests 2.4.12–2.4.22 sind durch (→ Erledigt), Details FORTSCHRITT.md.

- [ ] ⚠️ **Rollout-Hinweis (gilt nur noch für 001/029/117 auf 2.4.14):** Beim Update
  auf ≥ 2.4.19 läuft noch das alte BAT der Vorversion → dort werden `_internal\BILDER`-Fotos
  noch gelöscht. Werkstatt-Anweisung: vor dem Update Bilder ziehen (danach ist das Problem
  dauerhaft behoben). Alle anderen Boxen sind längst über 2.4.19 hinaus.
- [ ] Bekannt, nach dem Release angehen: ~3 s UI-Hänger beim tatsächlichen SELPHY-Druck
  (Druckpfad ist live-flotten-kritisch — nicht vorher umbauen); Startscreen-Neuaufbau mit
  USB-Template ~5 s (läuft zwischen Sessions, kein Gast-Kontakt).
- [ ] Nikon-Capture-Feintuning Teil 2 (optional, falls immer noch zu langsam): `noaf`-Capture
  für vorfokussierte Box-Distanz (Bridge kann CapturePhotoNoAf bereits als AF-Fallback).

---

## Bugs 🐞 (beim nächsten Software-Update nebenbei mitfixen)

- [ ] **Box friert nach dem ersten Video ein.** Nach dem ersten Video hängt die Software; ein Tipp auf den Touchscreen löst sie wieder. Vermutlich UI-Thread / Video-Handling (evtl. Zusammenhang mit dem Galerie-Server prüfen). (06.09.: nicht am Code prüfbar – wahrscheinlich durch 2.4.45/2.4.64 (VLC-Lifecycle) behoben; beim VLC-Langzeitlauf mit beobachten, erst dann abhaken.)
- [ ] **Windows-Update-Lockdown härter machen** (nicht dringend, entschieden 2026-07-03: erstmal so lassen). `windows_update_lockdown.log` endet „mit Warnungen": `sc.exe konnte Starttyp nicht setzen: WaaSMedicSvc (Exit 5)` und `DoSvc (Exit 5)` — diese zwei besonders geschützten Dienste lassen sich per `sc.exe config` nicht deaktivieren (Exit 5 = Zugriff verweigert). Ausgerechnet **WaaSMedicSvc** (Update Medic) kann abgeschaltete Updates theoretisch reaktivieren. In der Praxis greift der Lockdown (seit 15.06. keine ungewollten Updates/Neustarts), aber nicht 100 % wasserdicht. **Fix-Idee:** in `setup/disable_windows_update.ps1` für diese zwei Dienste den `Start`-Wert direkt in der Registry (`HKLM\SYSTEM\CurrentControlSet\Services\WaaSMedicSvc` bzw. `DoSvc` → `Start=4`) setzen statt über `sc.exe`; ggf. Registry-Owner/ACL vorher übernehmen. **Live-Flotten-Boot-Script → separat + vorsichtig testen**, nicht in einen Same-Day-Build. (Stand 06.09.: Registry-Variante `Start=4` weiterhin nicht umgesetzt.)

---

## Nikon D3300 DSLR (FexoNikonBridge, Variante 3) 📷

> digiCamControl-App-Ansatz (Variante 2) am 2026-07-02 **verworfen** (sichtbares Fenster +
> Webserver antwortet nie). Neu: eigene unsichtbare `FexoNikonBridge.exe` (C#/.NET 4.8,
> Motor: MIT-Bibliothek `CameraControl.Devices`, rohes PTP über Windows-WPD — wie dslrBooth).
> Vertrag/Details: [bridge/README.md](bridge/README.md) + [ROADMAP.md](ROADMAP.md).
> (Stand 06.09.: Bridge seit 02.07.2026 hardware-validiert, Box 252 läuft auf 2.4.63 —
> die Erstinbetriebnahme-Punkte (Bridge solo, CI 2.4.11, Setup, LiveView, Capture,
> OTA-Bootstrap) sind überholt → Erledigt. Übrig: Robustheit + die Code-Restpunkte unten.)

- [ ] **Robustheit:** USB ab-/anstecken während Idle → Status-Warnung erscheint/verschwindet;
  Bridge-Prozess stirbt (Taskmanager) → nächste Session startet ihn neu (initialize-Pfad).

**Bekannte offene Punkte (Nikon-only, 0 Live-Flotten-Impact):**
- [ ] **(major, entschärft) Erste Session initialisiert auf dem UI-Thread.** Durch den Warmup
  (Bridge-Start + Kamera-Vorverbindung im Hintergrund) bleiben normal nur `lv_start` + erster
  Frame (~1–3 s). Sauberer Fix wäre `initialize()` in einen Worker-Thread in `session.py`
  (Muster `_capture_photo_worker`) — betrifft auch Canon-Flow.
  (Stand 06.09.: unverändert, `initialize()` läuft weiter im UI-Thread, `session.py:302`.)
- [ ] **(minor) Doppel-Capture** im Fehlerfall: schlägt `capture_photo()` mit `None` fehl, ruft der
  Webcam-Fallthrough in `session.py` `get_high_res_frame()` → erneut `capture_photo()`.
  (Stand 06.09.: Canon-Seite erledigt → Erledigt; der Nikon-Fallthrough ist weiterhin offen.)
- [ ] **(minor) Capture blockiert Frames:** während `capture` läuft, wartet `get_frame()` am
  Bridge-Lock (eine Anfrage gleichzeitig; Timeout deckt das Lock-Warten jetzt ab). Für den
  Booth-Flow okay (LiveView pausiert beim Auslösen sowieso). (Stand 06.09.: unverändert.)

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

**Noch offen (folgt mit den jeweiligen Features / App-Seite):** (Stand 06.09.: alle drei unverändert offen)
- [ ] **`apply/assets`-Verbraucher:** Endpunkt nimmt Asset-ZIPs sicher entgegen + legt sie ab (Staging).
  Ein konkreter Box-seitiger Verbraucher (z. B. neues Loading-Video übernehmen) wird mit dem Feature nachgezogen.
- [ ] **App-OTA auf einer echten Box testen** (M4 aus PLAN-APP-OTA.md): inkl. absichtlich kaputter ZIP →
  Rollback muss greifen (kein Brick). Vorher: M0 lokale Bandbreite messen.
- [ ] **Optional härter:** Service-PIN für OTA ist 4-stellig (HMAC schützt vor Klartext, nicht vor
  Brute-Force im lokalen Netz). Falls je nötig: zusätzlich Pairing-Token verlangen oder PIN verlängern.

---

## Hoch 🔴

- Siehe die beiden ➡️-Abschnitte ganz oben: 2.4.66-Kette (Kurztest → Hotspot-Reparatur/QR → Rollout)
  und VLC-Langzeitlauf auf Box 167.

---

## Mittel 🟡

- [ ] Hotline-Prompt: `Druck-Korrektur` erst aufnehmen, wenn die Funktion offiziell ausgerollt und der Supportablauf bestätigt ist
- [ ] Admin-Menü: "Buchung zurücksetzen" Button
- [ ] Canon DSLR Live-View erst nach dem 2.4.62-Hardware-/Flottennachweis auf
      Box 248 ohne SD-Karte weiter optimieren
      (`0xa102` ist offiziell `OBJECT_NOTREADY`, nicht EVF_INTERNAL_ERROR)
- [ ] Print-Queue Anzeige
- [ ] Deployment: Referenz-Tablet einrichten und erstes Image testen
- [ ] Werkstatt-Skripte nachziehen: `setup/setup_hotspot.ps1` und `setup/diagnose_hotspot.ps1` nutzen
      noch die alte „erstes Profil"-Logik ohne Firmen-WLAN-Ausschluss (laufen nicht im Kundenbetrieb —
      aber irgendwann an die App-Logik angleichen). (Stand 06.09.: unverändert.)

### Heim-WLAN-Workflow Phase 1 — "Bilder sichern"-Screen lokal

Details siehe ROADMAP.md Abschnitt "Heim-WLAN-Workflow". Kein Backend nötig.
(Stand 06.09.: unbegonnen.)

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
(Stand 06.09.: unbegonnen.)

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
(Stand 06.09.: unbegonnen – `src/updater.py` ~Zeile 600 löscht `_internal_OLD` weiterhin sofort.)
- [ ] `src/updater.py`: `_internal_OLD/` 24 h aufbewahren statt sofort löschen
- [ ] Beim ersten App-Start nach Update: Smoke-Test (Kamera/Drucker/Config/Galerie-Server)
- [ ] Bei Smoke-Test-Fehler: automatischer Rollback auf `_internal_OLD/`
- [ ] Markierung in `update_history.json` damit kein Endlos-Rollback-Loop entsteht

**Stufe Release-Manager (mit Phase 2):** (Stand 06.09.: unbegonnen.)
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
(Stand 06.09.: unbegonnen.)

- [ ] Datenschutz prüfen: Upload nur bei `online_gallery == True` reicht als Zustimmung?
- [ ] Workflow definieren: Mitarbeiter-Freigabe vor Sichtbarmachung in Kundengalerie?
- [ ] [laravel] `POST /api/v1/box/{barcode}/gallery-image` (idempotent per File-Hash)
- [ ] [laravel] Server-side Throttling damit Heimkehr-Welle die Leitung nicht sättigt
- [ ] Booth: Upload-Queue mit Resume bei Verbindungsabbruch
- [ ] Booth: lokale Markierung erfolgreich hochgeladener Bilder
- [ ] Booth: Auto-Upload-Trigger wenn Heim-Check sagt "Bilder fehlen für diese Buchung"

---

## Erledigt ✅

### 2026-09-06 (Abgleich mit Ist-Stand)
- [x] Installer 2.4.66 bauen – erledigt 05.09.2026, Beleg: GitHub-Action-Run 33978302086 grün, Artefakt `FexoBooth-2.4.66` (182 MB); kein Release, keine Box im Feld
- [x] 2.4.64 bauen + auf Testbox installieren – erledigt vor 06.09., Beleg: Dashboard-Meldung Box 167 = 2.4.64 (TODO nannte fälschlich Box 155)
- [x] 2.4.62 bauen + auf Box 248 installieren – erledigt vor 06.09., Beleg: Dashboard-Meldung Box 248 = 2.4.62
- [x] 2.4.43 Dauerbetrieb HD auf einer Testbox prüfen (6 Punkte) – überholt, Beleg: Schalter in 2.4.45 entfernt, Dauerbetrieb HD ist Standard in der Flotte
- [x] 2.4.36 Gegenprüfung Kamera-Messung (bedienbar, Abbrechen, `kamera-messung.txt`) – überholt/erledigt, Beleg: durch 2.4.37/2.4.39 ersetzt, Messung gelaufen
- [x] 2.4.35 Beenden-Knopf (3198) auf der Box bestätigt – erledigt 20.08.2026, Beleg: Log 09:08:52, sauber beendet in 0,3 s inkl. Kamera-Freigabe
- [x] ROUTER/DHCP-Block: Gegentest Box 19/38, Lease-Liste/MAC-Abgleich, feste-IP-Gegenprobe – erledigt/überholt 02./03.09.2026, Beleg: Boxen 19/31/38 melden sich mit 2.4.45 (Ursache Router-DHCP-Pool, 19.08. auf `.130–.250` erweitert)
- [x] Boxen 19/31/38 melden sich nicht (2.4.32-Nachstart + `netzwerk.log`-Urteil) – erledigt 02./03.09.2026, Beleg: alle drei im Dashboard mit 2.4.45
- [x] Abstürze 2.4.30: Nachtest 2.4.31 auf Box 044 bestanden; CPU-Fehlalarm beim Testdruck in 2.4.32 gefixt; WER-Dumps einsammeln + Dashboard-Auslöser-Prüfung überholt – Beleg: Ursache Kamera-Doppelzugriff (absturz.log 19.08.), Fix 2.4.31, Flotte auf 2.4.45
- [x] Vor Flotten-Rollout 2.4.29: Hotspot-Rückkehr beim Kunden – erledigt 05.09.2026, Beleg: 2.4.65-Fixes + Box-101-Test (Hotspot 12:00–18:14 stabil); GitHub-Release + Auto-Update – erledigt, Beleg: Latest v2.4.45 (20.08.), Auto-Update zeigt darauf; stumme Boxen 116/016 – erledigt, melden sich wieder (073 bleibt offen, siehe Flotte)
- [x] Firmen-WLAN 2.4.27 auf echter Hardware prüfen (Build auf stummer Box, NETZ-BILANZ-Urteil, DHCP-/Hotspot-Konflikt-Auswertung, Anker-Tausch) – überholt, Beleg: Ursache war der Router-DHCP-Pool (19.08.), Box-200-Feldtest 18.08. grün, Flotte auf 2.4.45
- [x] Galerie Thumbnail-Cache: Cache `BILDER/.thumbs/` + Aufräumen beim Event-Wechsel – erledigt 03.07.2026 (5 Tests); eigener Build-Kandidat – überholt, Beleg: mit den regulären Builds ausgeliefert, Flotte auf 2.4.45
- [x] Performance-Nachtests: 2.4.12/2.4.13/2.4.16/2.4.17 bestanden (Juli/Aug. 2026), 2.4.18/2.4.19/2.4.22 erledigt, Nachtest 2.4.14 überholt – Beleg: Flotte auf 2.4.45; Tk-Anzeigepfad (2.4.16), System-Test mit Messwerten (2.4.19), Nikon JPEG-Größe „M" umgesetzt
- [x] Bug: Filter-Screen läuft nicht automatisch ab – erledigt, Beleg: Auto-Ablauf-Timer startet beim Anzeigen (`filter.py:716`)
- [x] Bug: Drucker-Status-Log entspammen – erledigt, Beleg: Commit 17c16e6 (nur bei Status-Wechsel loggen)
- [x] Nikon-Bridge Erstinbetriebnahme (Bridge solo mit D3300, CI-Build 2.4.11, Setup 2.4.11 auf Box, LiveView, Capture, „hardware-validiert" markieren, OTA-Bootstrap 2.4.11) – überholt, Beleg: Nikon hardware-validiert 02.07.2026, Box 252 läuft auf 2.4.63
- [x] Doppel-Capture im Fehlerfall, Canon-Seite – erledigt, Beleg: 2.4.61-Test Box 245 ohne Doppelbild/Retry (Nikon-Fallthrough bleibt offen)
- [x] KRITISCH: Canon DSLR Freeze bei Host-Download behoben (EdsSetObjectEventHandler blockierte Message-Pump)
- [x] Mittel-Liste: Drucker-Reset + Fehler-Overlay auf echtem Tablet – überholt (Drucker-Steuerung seit März 2026 in der Flotte); Event-Wechsel & Systemtest auf Tablet – erledigt (System-Test 2.4.19 in der Flotte); erstes GitHub-Release + OTA-Update – erledigt (Releases bis v2.4.45, Auto-Update aktiv); Clonezilla-Stick auf Miix 310 – erledigt, Beleg: Prüfung 06.09.

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
