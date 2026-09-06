# Erkenntnisse - Fexobooth V2

Lessons Learned und Technologie-Entscheidungen für zukünftige Referenz.

---

## Technologie-Entscheidungen

### Ein Design-Handoff wird übersetzt, nicht abgeschrieben (2.4.70)

| | |
|---|---|
| **Kontext** | UI-Redesign nach Claude-Design-Handoff (HTML-Referenz + README mit exakten Tokens). Umsetzung in CustomTkinter auf Miix 310. |
| **Entscheidung** | Werte 1:1 übernehmen (Farben, Radien, Fonts, Maße), aber an drei Stellen bewusst abweichen: (1) Drucker-Texte bleiben Handlungsaufforderungen — Selbstbedienungs-Realität schlägt Design-Beispieltext. (2) Glow-PNG mit rein-flachen Textzonen, weil Tk-Labels keine echte Transparenz können — sonst dunkle Rechtecke im Verlauf. (3) Logo in die bestehende Top-Bar statt doppelt auf den Screen. |
| **Merke** | Verläufe/Schatten in PNGs einbacken kostet zur Laufzeit nichts — aber jede Fläche, auf der DYNAMISCHER Text liegt, muss im Asset einfarbig sein. Gedrückt-Feedback via bind auf ButtonPress/Release braucht einen Disabled-Wächter, sonst färbt ein Touch den grauen Button ein. Und: Vor dem Abschreiben eines Handoff-Texts prüfen, ob er zur Betriebsrealität passt. |

### Tkinter + Threads + automatischer GC = Deadlock-Lotterie (2.4.68)

| | |
|---|---|
| **Feldbefund** | Box 101, 06.09.2026, dritter Freeze — Stack-Dump des Haenge-Waechters: MainThread wartet in `Thread.start()` (LiveView-Worker-Geburt beim Session-Wiedereinstieg), der neue Thread haengt in `tkinter\font.py __del__`, ausgeloest vom automatischen Zyklen-Sammler mitten in `threading._set_tstate_lock`. Tk nimmt Befehle aus fremden Threads nur an, wenn der Hauptthread im Tcl-Event-Loop steht — der wartete aber auf den neuen Thread. Beide fuer immer. |
| **Entscheidung** | `gc.disable()` beim Start der Hauptschleife; `_gc_takt()` sammelt alle 30 s per `gc.collect()` im Tk-Hauptthread. Tkinter-Finalizer laufen damit garantiert nur noch dort, wo Tcl-Aufrufe erlaubt sind. Dauer wird im Dev-Log ueberwacht (>100 ms auffaellig). |
| **Alternativen** | Font-Churn reduzieren/cachen (lindert nur die Wahrscheinlichkeit — customtkinter erzeugt intern selbst Fonts). `Thread.start()` aus dem after()-Kontext verlegen (verschiebt das Fenster nur). tkinter-Objekte nie zyklisch referenzieren (nicht durchsetzbar, Fremdcode). |
| **Merke** | Der Zyklen-Sammler laeuft in DEM Thread, der zufaellig die Allokations-Schwelle reisst — auch in einem halb geborenen. Jedes Tk-Objekt mit `__del__` (Font, Variable, PhotoImage) ist dann eine Mine. In jeder Tk-App mit Threads: Auto-GC aus, Sammeln in den Hauptthread-Takt. Und: Der Haenge-Waechter (2.4.67) hat sich beim ERSTEN Einsatz bezahlt gemacht — Diagnose-Werkzeuge vor Rate-Fixes. |

### Einen Freeze ohne Beweisfoto fixt man nicht — man faengt erst das Foto (2.4.67)

| | |
|---|---|
| **Feldbefund** | Box 101, 06.09.2026: Zwei UI-Freezes im Stress-Test (Session 1 bzw. Durchgang 166). Log endet beide Male kommentarlos an derselben Stelle (Session-Wiedereinstieg), kein Windows-Crash, kein Dump — „Anwendung reagiert nicht", von Hand beendet. `faulthandler.enable` (seit 2.4.30) half nicht: Es feuert nur bei Absturz-Signalen, ein Stillstand ist kein Signal. |
| **Entscheidung** | `faulthandler.dump_traceback_later` als Haenge-Waechter: Die Tk-Hauptschleife armiert alle 5 s neu (Timeout 30 s, exit=False). Der Waechter-Thread laeuft auf C-Ebene ohne GIL — er schreibt die Stacks ALLER Threads nach absturz.log selbst dann, wenn die komplette Python-Ebene verklemmt ist. Dazu eine Thread-Legende (faulthandler kennt nur IDs, keine Namen). |
| **Alternativen** | Sofort einen vermuteten Fix bauen (1 Ereignis in 13,5 h — jeder Fix waere geraten und unpruefbar). Externer Prozess mit py-spy (zusaetzliche Abhaengigkeit auf 219 Boxen, Installer-Aufwand). Windows-WER-Haenge-Dumps (greifen nur bei „echten" AppHangs ueber die Shell, nicht zuverlaessig im Kiosk). |
| **Merke** | Ein Haenger ist kein Absturz: `faulthandler.enable` sieht ihn nicht, WER meldet oft nichts, und beim Hand-Beenden entsteht kein Dump. Fuer Haenger braucht es einen Timer-Waechter, der die Python-Ebene NICHT braucht. exit=False nicht vergessen — der Waechter soll dokumentieren, nicht die Box abschiessen. |

### Ein Hintergrund-Worker darf keine lebenden Session-Daten lesen (2.4.66)

| | |
|---|---|
| **Feldbefund** | Dauerlauf 05.09.2026, Box 101: 9 von 30 Print-Dateien komplett weiss, alle byte-identisch (34.527 Bytes). Log-Muster in jedem Fall: „Session beendet" VOR „Print gespeichert". Der Final-Renderer laeuft seit 2.4.12 im Hintergrund; `reset_session()` leerte Fotos, Vorlagen-Felder und Overlay, waehrend der Worker noch las — der Renderer bekam leere Boxen und speicherte die weisse Vorlage. Ausloeser im Test: Stress-Test-Auto-Ende; im Feld genuegt ein Gast, der „Fertig" drueckt, waehrend „Dein Bild wird erstellt…" laeuft (2–8 s). |
| **Entscheidung** | Momentaufnahme: `on_show` kopiert Fotos, Filter, Boxen und Overlay vor dem Thread-Start und uebergibt sie als Argumente. Der Worker fasst die App-Session nie mehr an. Zusaetzlich statischer Test (AST), der jeden neuen Zugriff des Workers auf lebende Session-Felder sofort rot macht. |
| **Alternativen** | Session-Ende blockieren bis Render fertig (Gast wartet grundlos). Speichern ueberspringen, wenn Session schon beendet (Foto der Gaeste ginge verloren — die Momentaufnahme rettet es stattdessen). |
| **Merke** | Sobald Arbeit in einen Thread wandert, gehoeren ihre Eingaben ihm ALLEIN — als Kopie beim Start. Byte-identische Ausgabedateien sind ein Fingerabdruck: gleicher MD5 = gleicher (leerer) Eingabezustand, nicht Zufall. |

### Ein Hotspot, der einmal gestartet wird, laeuft nicht die ganze Feier (2.4.65)

| | |
|---|---|
| **Feldbefund** | Box 155, 04.09.2026: 10:04 Uhr `Eig. Hotspot: AN`, 11:26 Uhr aus — kein Stop im Log. Box 248, 26./27.08.: 14:22 an, 03:16 aus, ebenfalls ohne Zutun. Windows deaktiviert den mobilen Hotspot nach 5 Minuten ohne verbundenes Geraet (`PeerlessTimeout`) und bei geteilter Verbindung ohne Internet (`PublicConnectionTimeout`). Beim Kunden gibt es kein Internet und lange Pausen — beides trifft. Bis 2.4.26 fiel das nicht auf, weil `start_hotspot()` wegen des `{{ }}`-Bugs ohnehin nichts tat und der Hotspot aus der Einmal-Einrichtung stammte. |
| **Zweiter Befund** | 01.09., Box 155: Tethering meldete „On", die Box hatte aber nur `169.254.14.101` und keine `192.168.137.1`. Handys kamen ins WLAN und erreichten die Box nicht. „An" ist also kein Beweis — die **Adresse** ist der Beweis. |
| **Entscheidung** | Zwei Ebenen: (1) `setup/hotspot_keepalive.ps1` setzt beide Timeout-Schalter des Dienstes `icssvc` auf 0 — mit Admin-Rechten ueber den Installer (Pflicht-Schritt) und die bestehende SYSTEM-Boot-Aufgabe. (2) Ein Waechter in der App prueft alle 45 s die IP-Liste (kein PowerShell, 0 Last) und repariert bei fehlender `192.168.137.x` nach zwei Fehlpruefungen: Stop (falls Windows „an" sagt) + Start, dann 3 Minuten Ruhe. |
| **Alternativen** | Nur Registrierung (deckt „an ohne Adresse" nicht ab). Nur Waechter (Hotspot faellt trotzdem alle 5 Minuten um, Waechter repariert im Dauerlauf). PowerShell-Statusabfrage im Takt (mehrere Sekunden pro Aufruf, hat am 18.08. die Kamera-Erkennung in Timeouts getrieben). |
| **Merke** | Zustand ueber die Adresse pruefen, nicht ueber die Aussage des Systems. Admin-Aenderungen gehoeren in die Stellen, die ohnehin Admin sind (Installer, SYSTEM-Aufgabe) — nicht in die Kiosk-App. Postinstall-Optionen mit Haekchen werden nie geklickt; Pflicht-Schritte sind `[Run]`-Eintraege ohne `Tasks:`. |

### Der QR-Code darf nur die Hotspot-Adresse kennen (2.4.65)

| | |
|---|---|
| **Feldbefund** | Box 155, 04.09.: QR um 11:26:06 mit `a=http://192.168.2.159` (Firmen-WLAN) erzeugt, Hotspot erst 11:26:16 gestartet. Der falsche QR stand bis zum naechsten Startbildschirm-Aufbau um 12:20. App-Komplett-Test um 12:43 (Handy im Hotspot): dreimal „Could not connect to the server". Beim Kunden waere im selben Rennen eine `169.254`-Adresse moeglich. |
| **Ursache** | `get_gallery_url()` suchte „irgendeine" Adresse mit absteigender Prioritaet (Hotspot → 192.168.x → 10.x → Socket-Trick). Sinnvoll fuer die alte Browser-Galerie im selben Netz, falsch fuer die App: Die verbindet das Handy IMMER mit dem Box-Hotspot (SSID+Passwort stecken im QR). |
| **Entscheidung** | `choose_gallery_ip()`: `192.168.137.x` wenn vorhanden, sonst fest `192.168.137.1`. Kein Fallback auf andere Netze. Damit ist der QR auch vor dem Hotspot-Start richtig — die App wartet dann einfach, statt gegen die falsche Tuer zu laufen. |
| **Merke** | Wenn der Client den Weg vorgibt (Hotspot), darf der Server keinen anderen anbieten. Ein Rennen zwischen zwei Startvorgaengen loest man am sichersten, indem das Ergebnis nicht vom Zeitpunkt abhaengt. |

### Native Player pro Clip zu zerlegen erzeugt unter Last eine Ressourcenlawine (2.4.64)

| | |
|---|---|
| **Feldbeleg** | Box 155 nahm 548/548 Webcam-Fotos auf. Erst nach rund 110 Sitzungen stiegen RAM/CPU und LiveView wurde langsam. Von 608 VLC-Paaren waren 34 Cleanup-Threads noch offen; Freigaben blockierten bis ueber 300 Sekunden. |
| **Zweite Leckstelle** | `media_new()` liefert eine Caller-eigene native Referenz. `set_media()` behaelt intern eine weitere, aber python-vlc besitzt fuer die Caller-Referenz keinen automatischen Destruktor. Ohne ausdrueckliches `media.release()` bleibt pro Clip eine Referenz offen. |
| **Loesung** | Warmup und alle Videos teilen appweit genau eine Instanz und einen Player. Nur das Medium wechselt und seine Caller-Referenz wird im `finally` exakt einmal freigegeben. Ein normales Clip-Ende fuehrt keinen nativen Teardown aus. |
| **Fehlergrenze** | Ein defektes Paar wird atomar ausgemustert. Solange sein einziger Cleanup nicht vollstaendig bestaetigt ist, entsteht kein neues VLC. Nach Erfolg ist genau eine zweite Generation erlaubt; bei Haenger oder Ausnahme bleibt VLC dauerhaft im OpenCV-Fallback. |
| **UI-Lektion** | Ein persistent gewordener Screen braucht Wiedergabe-Generationen fuer jeden `after()`-Callback und muss gebundene Session-Callbacks vor deren Aufruf loesen. OpenCV-Worker brauchen pro Clip eigene Event-/Capture-/Queue-Objekte; ihr EOF-Sentinel muss auch bei voller Queue garantiert zugestellt werden. |
| **Merke** | Bei nativen Bibliotheken ist „asynchron freigeben“ allein keine Begrenzung. Erzeugungsrate, Besitz jeder nativen Referenz und maximale Zahl gleichzeitig ausgemusterter Objekte muessen explizit sein und per Langzeittest geprueft werden. |

### Ein lebender Bridge-Prozess beweist keine USB-/WPD-Kameraerkennung (2.4.63)

| | |
|---|---|
| **Befund** | Auf Box 252 startete `FexoNikonBridge.exe`, beantwortete `ping` und blieb aktiv. Trotzdem enthielt `ConnectedDevices` keine D3300 und `init` endete vor Live View/Capture. Der Admin-Platzhalter sah fuer den Nutzer wie eine gefundene Kamera aus, war aber kein Hardwarebeleg. |
| **Verlorene Ursache** | `CameraControl.Devices` faengt zentrale WPD-/WIA-Ausnahmen intern ab und meldet sie ueber eigene Log-Events. Die Bridge hatte `Console.Out` zum Schutz des JSON-/JPEG-Protokolls komplett verworfen; Prozessstatus und generischer Fehlertext konnten Windows-Sicht, Library-Verwerfung und Lock-Belegung deshalb nicht trennen. |
| **Loesung** | Fremdausgaben bleiben strikt vom Roh-stdout getrennt, landen aber in einem begrenzten, never-throw Ringpuffer. Ein read-only `diag` liefert nur bereits vorhandenen Scan-/Geraete-/Fehlerzustand. App-seitig kommen Aufruf-Timings, Bridge-Dateihashes sowie ein asynchroner Windows-PnP-/Prozess-Snapshot hinzu. |
| **Beweisgrenze** | Ein laufender Konkurrenzprozess ist nur ein Indiz. Erst zusammen mit einem passenden Busy-/Access-/Sharing-Fehler darf eine wahrscheinliche Belegung angenommen werden. `diag` selbst darf keinen Scan starten, weil Beobachtung sonst den zu untersuchenden Zustand veraendert. |
| **Build-Lektion** | Der lokale Installer kopierte zuvor eine vorhandene Bridge-Binaerdatei, ohne `Program.cs` neu zu bauen. Quellcode- und App-Versionsaenderung beweisen daher keinen neuen Hardwareadapter. Der Builder muss native/externe Teilprogramme frisch bauen und ihren Protokollstand vor dem Verpacken pruefen. |
| **Merke** | Bei einem mehrprozessigen Hardwarepfad braucht jede Grenze einen eigenen Nachweis: App-Version, tatsaechliche Bridge-Binaerdatei, Pipe/Lock, Bibliotheks-Scan und Windows-PnP. `Prozess lebt` ist nur einer davon. |

### `AvailableShots` ist ohne Karte kein Host-Readiness-Beweis (2.4.62)

| | |
|---|---|
| **Hardwarebefund** | Box 248 fand und oeffnete eine EOS 2000D im Fotomodus `P` ohne SD-Karte. `SaveTo=Host`, UI-Lock, `EdsSetCapacity`, UI-Unlock und `SaveTo`-Readback gelangen; `AvailableShots` blieb trotzdem dauerhaft null. 2.4.61 verwarf deshalb die funktionierende Verbindung. |
| **Herstellervertrag** | Canon verlangt nach `SaveTo=Host` eine Capacity-Meldung. Laut mitgeliefertem Header koennen manche Bodies daraus eine verbleibende Bildzahl anzeigen; ein positiver `AvailableShots`-Readback ist keine Voraussetzung des Hosttransfers. |
| **Loesung** | Null wird weiterhin eine Sekunde lang als Kaltstartsignal beobachtet. Bleibt sie bestehen, reicht die bestaetigte Pflichtfolge `SaveTo=Host + SetCapacity + SaveTo-Readback`; der kartelose Weg wird deutlich gewarnt und als host-ready markiert. Andere unplausible Werte bleiben fatal. |
| **Sicherheitsgrenze** | Kein Dummyfoto und kein Retry. Ein echtes `CARD_NG` invalidiert den Zustand weiterhin. Die Lockerung betrifft nur den Null-Readback nach vollstaendig erfolgreicher Hostkonfiguration, nicht deren Pflichtschritte. |
| **Merke** | Eine Anzeige-Property darf nicht zum harten Verbindungsbeweis werden, wenn der Hersteller sie nur fuer manche Bodies garantiert. Erst Pflichtaufrufe, Hardwarevergleich und der tatsaechliche Transfer bestimmen den Vertrag. |

### Ein UI-Blitz braucht einen belegbaren Kamera-Meilenstein und einen Capture-Token (2.4.61)

| | |
|---|---|
| **Hardwarebefund** | Beim 2.4.60-Test lag der am Countdown-Ende gezeigte Canon-Softwareblitz 1.497 bis 1.569 ms vor der Rueckkehr von `ShutterButton_Completely`. Der mechanische Klick kam hoerbar spaeter; eine Bewegung nach dem Blitz veraenderte deshalb noch das echte Foto. |
| **API-Grenze** | EDSDK liefert kein exaktes Ereignis fuer den physikalischen Verschluss. Ein erfolgreicher synchroner Press-Return ist die beste verfuegbare Naeherung, aber noch kein Beweis fuer Verschluss, Transfer oder JPEG. Ein spaeterer `CaptureError`, Release-, Transfer- oder Decode-Fehler bleibt moeglich. |
| **Loesung** | Der EDSDK-Owner gibt ein eingefrorenes Press-/Release-Ergebnis zurueck. Der Canon-Manager meldet `press_ok=True` erst im aufrufenden Capture-Worker; nur dieser reiht den 90-ms-Blitz per `after(0)` in Tk ein. Das echte Canon-Foto wird beim Completion sofort angezeigt. |
| **Release-Vertrag** | Sobald der native Press begonnen hat, wird `ShutterButton_OFF` in einem `finally` genau einmal versucht, auch wenn Press eine Exception wirft. Press-Erfolg und Gesamterfolg bleiben getrennt: Press-OK darf den Blitz anfordern, ein OFF-Fehler laesst den Capture trotzdem scheitern. |
| **Race-Vertrag** | `is_live` und `_capture_in_progress` reichen nicht. Ein alter Callback koennte sonst waehrend des naechsten Captures wieder gueltig aussehen. Kameraart, Generation-Token und Einmal-Guard gehoeren deshalb zum einzelnen Capture; Screen-Wechsel, neuer Capture und Completion entwerten ihn. |
| **Merke** | Sichtbare Rueckmeldung nie an einen bequemen UI-Zeitpunkt koppeln. Den bestmoeglichen Hardware-Meilenstein ehrlich benennen, Threadgrenzen respektieren und jede spaete Rueckmeldung an eine unverwechselbare Operation binden. |

### Host-Bereitschaft ist ein Session-Vertrag, kein Capture-Ritual (2.4.60)

| | |
|---|---|
| **Hardwarebefund** | 2.4.59 stellte `SaveTo=Host` ein und meldete Capacity unmittelbar vor jedem Foto. Beim ersten Capture nach dem Kaltstart antwortete die EOS 2000D trotzdem mit `TAKE_PICTURE_CARD_NG`; danach kamen sieben echte 6000-x-4000-JPEGs fehlerfrei. |
| **Ursache** | Ein erfolgreicher Setter beweist noch nicht, dass das Speicherziel in der Kamera bereits wirksam und aufnahmebereit ist. Die vorherige Folge verteilte Konfiguration und Nutzung zudem auf zwei Zeitpunkte statt sie als abgeschlossenen Initialisierungsschritt zu behandeln. |
| **Lösung** | `SaveTo=Host`, `UILock`, genau ein `EdsSetCapacity(reset=1)`, garantiertes `UIUnlock` und begrenzte Readbacks laufen atomar nach `OpenSession`. Erst danach gilt die Session als Host-ready. Vor einem Foto wird nur dieses Flag geprueft; Capacity wird nicht jedes Mal neu initialisiert. |
| **Fehlervertrag** | Ohne bestaetigtes Host-Ziel kein Shutter. Ein `CARD_NG` invalidiert die Bereitschaft fuer den naechsten kontrollierten Aufbau, fuehrt aber niemals zu einem automatischen zweiten Shutter. Seit 2.4.62 blockieren auch dauerhafte null, nicht lesbare oder unbekannte `AvailableShots` nicht, wenn Setter, Capacity und `SaveTo`-Readback erfolgreich waren. |
| **Merke** | Hardware-Initialisierung braucht einen pruefbaren Abschlusszustand. Wiederholtes Setzen direkt vor der Nutzung ersetzt diesen Nachweis nicht und kann selbst ein Race erzeugen. |

### Gemeinsamer UI-Code braucht eine explizite Kameratyp-Grenze (2.4.60)

| | |
|---|---|
| **Problem** | Der fuer langsame DSLR-Captures gedachte schwarze Wartehinweis erschien nach 900 ms auch bei jedem funktionierenden Canon-Foto. Gleichzeitig lief ein bereits dekodiertes Canon-PIL-Bild ohne sichtbaren Nutzen durch NumPy, zwei Farbkonvertierungen und wieder zurueck nach PIL. |
| **Lösung** | Nur Canon plant den Balken nicht mehr und bleibt fuer Anzeige sowie 180-Grad-Drehung im PIL-Pfad. Nikon behaelt seinen Hinweis. Der Webcam-Zweig und `webcam.py` bleiben semantisch unveraendert. |
| **Merke** | `DSLR` ist keine ausreichende Verhaltenskategorie, wenn Canon und Nikon unterschiedliche Laufzeiten und Datenformate haben. Gemeinsamer Code muss an der kleinsten fachlich richtigen Grenze verzweigen. |

### Der installierte Build ist ein eigener Laufzeitkontext (2.4.59)

| | |
|---|---|
| **Problem** | Canon konnte im Quellbaum vorhanden sein und nach einer Neuinstallation trotzdem verschwinden. dslrBooth funktionierte auf demselben Gerät weiter. |
| **Ursache** | Der PyInstaller-One-Folder-Build packte `EDSDK.dll` und `EdsImage.dll` ausschließlich nach `_internal`. Der Loader suchte Repo-/Altpfade und den EXE-Root, aber nicht `sys._MEIPASS`. Zusätzlich wurde das Handle von `os.add_dll_directory()` nicht gehalten und konnte den Abhängigkeitspfad wieder entfernen. |
| **Lösung** | `_MEIPASS` zuerst prüfen, danach Frozen-Fallbacks; beide Canon-DLLs am selben Ort verlangen; das DLL-Directory-Handle für die Prozesslebensdauer halten. `tests/test_dll_loader.py` simuliert exakt den installierten Aufbau. |
| **Merke** | Ein grüner Quelltest beweist nicht, dass eine native DLL im Paket auffindbar ist. Bei jeder PyInstaller-Nativanbindung gehören Paketinhalt, `_MEIPASS` und Abhängigkeits-DLLs in einen eigenen Regressionstest. |

### Ein teilweise zentralisierter Hardware-Faden ist weiterhin Mehrfadenbetrieb (2.4.59)

| | |
|---|---|
| **Problem** | 2.4.57 hieß „ein Faden“, routete aber nur SDK-Start, Kameraliste und `OpenSession` dorthin. Handler, Properties, Live-View, Shutter, Events, Download und Release liefen weiter verteilt. |
| **Entscheidung** | Genau ein COM-STA-Owner besitzt ausnahmslos SDK, Session, Referenzen und jeden `EDSDK_DLL.*`-Aufruf. Öffentliche Wrapper dispatchen dorthin; ein AST-Test verhindert neue undekorierte DLL-Einstiege. |
| **Callback-Vertrag** | Der native Callback macht keinen reentranten Download. Er legt nur einen priorisierten Auftrag ab und kehrt sofort zur DLL zurück. Download/Complete/Cancel/Release folgen danach im Owner. Object- und State-Handler werden vor `OpenSession` registriert. |
| **Fail-closed** | Parallele Starter warten auf dasselbe Ready-Event. Nach einem nativen Timeout gilt der Owner als ungesund und nimmt nichts Neues an. Queuezustände wechseln unter Lock, damit ein gecancelter Auftrag niemals später doch noch auslöst. |
| **Merke** | „Fast alle“ nativen Aufrufe auf einem Faden ist bei einer STA-Bibliothek keine Architektur. Owner-Grenze, Callback-Reentranz und Timeoutverhalten müssen maschinell geprüft werden. |

### Canon-Konstanten sind Herstellervertrag, keine Modellbesonderheit (2.4.59)

| | |
|---|---|
| **Ursache** | Object-Events waren im Code um `0x100` verschoben und JPEG-Qualitäten falsch. `0x208` wurde deshalb als EOS-2000D-Sonderwert behandelt, obwohl `EDSDKTypes.h` ihn offiziell als `DirItemRequestTransfer` definiert. State-Event `0x301` war zeitweise im Object-Handler vermischt. |
| **Lösung** | Konstanten direkt aus `EDSDKTypes.h`: Object-All `0x200`, Transfer `0x208`, State-All `0x300`, Shutdown `0x301`, CaptureError `0x305`, InternalError `0x306`; Object und State haben getrennte Handler. |
| **Merke** | Headerwerte nicht aus Erinnerungen, alten Wrappern oder vermeintlichen Kameraspezialfällen ableiten. Ein Test gleicht die produktionskritischen Werte direkt gegen den mitgelieferten Header ab. |

### Eine gemeinsame Capture-Abstraktion darf keine zweite Hardwareaufnahme verstecken (2.4.59)

| | |
|---|---|
| **Problem** | Nach einem fehlgeschlagenen Canon-`capture_photo()` lief der generische High-Res-Fallback weiter. Bei Canon führte auch dieser wieder zu `capture_photo()` und konnte ein zweites DSLR-Foto auslösen. Die Webcam-Optimierung aus `841de6c` hatte damit unbeabsichtigt den Canon-Vertrag verändert. |
| **Lösung** | Nur Canon wird am generischen Fallback vorbeigeführt; der Webcam-Pfad bleibt semantisch unverändert. Canon sendet genau einen Capture-Befehl plus geprüftes Shutter-OFF. AF_NG wird sichtbar gemeldet, nicht automatisch mit NonAF wiederholt. |
| **Queue-Vertrag** | Die Host-Queue wird im Owner unmittelbar vor dem Shutter für eine Capture-ID scharfgeschaltet. Verspätete Events außerhalb dieses Fensters werden gecancelt; Queueeinträge einer anderen ID werden verworfen. |
| **Merke** | Eine Optimierung in gemeinsamem Capture-Code braucht explizite Verträge pro Kameratyp. Bei Hardware bedeutet ein harmlos wirkender Fallback eventuell eine zweite physische Aktion. |

### Eine geaenderte ctypes-Signatur ohne Aufrufstellen-Pruefung ist eine Zeitbombe (2.4.58)

| | |
|---|---|
| **Problem** | Nach der Korrektur der 64-Bit-Signaturen (2.4.55) gab es auf der Box gar keinen Live-View mehr — 166 Fehler pro Sitzung. |
| **Ursache** | Die Signatur von `EdsGetLength` wurde richtig auf 64 Bit gestellt, eine von zwei Aufrufstellen blieb aber auf `c_uint`. ctypes prueft Argumenttypen erst beim tatsaechlichen Aufruf: Syntaxpruefung, Import und Start laufen sauber durch, der Fehler zeigt sich erst auf der Hardware. |
| **Lösung** | `tests/test_edsdk_typen.py` — prueft ohne Kamera (a) Signaturen gegen den Hersteller-Header und (b) alle Aufrufstellen gegen die Signaturen. Gegenprobe: Der kuenstlich wieder eingebaute Fehler wird mit Zeilennummer gemeldet. |
| **Merke** | Bei ctypes gehoert zu jeder Signaturaenderung ein Durchgang durch ALLE Aufrufstellen — der Compiler uebernimmt das hier nicht. Und wenn derselbe Fehlertyp mehr als zweimal auftritt, ist ein automatischer Pruefer billiger als die naechste Testrunde beim Nutzer: Vier Fundstellen kosteten je einen Bau- und Testzyklus auf der Box, der Pruefer braucht Sekunden und findet alle auf einmal. |


### 64-Bit-Werte als 32 Bit: derselbe Fehler an vier Stellen (2.4.55)

| | |
|---|---|
| **Problem** | Ueber Wochen kam kein DSLR-Foto an. Vier aufeinanderfolgende Ursachen wurden gefunden und behoben — jede erklaerte den Ausfall, keine loeste ihn. |
| **Gemeinsamer Nenner** | Alle vier waren derselbe Fehlertyp: ein 64-Bit-Wert der Canon-Schnittstelle wurde als 32 Bit behandelt. Einmal im Speicher-Layout (`EdsDirectoryItemInfo.size`, 2.4.48), dreimal in Funktionssignaturen (`EdsCreateMemoryStream`, `EdsDownload`, `EdsGetLength`, 2.4.55). |
| **Warum das so lange dauerte** | Ein falscher Datentyp wirft keine Ausnahme. Er liefert plausible falsche Werte oder bricht mit einem nichtssagenden INTERNAL_ERROR ab — und die Suche wandert zur naechsten Schicht, statt den Typ zu pruefen. |
| **Lösung** | Alle Signaturen automatisch gegen den Hersteller-Header abgeglichen (`EDSDK.h` liegt im Repo). Der Abgleich ist wiederholbar und findet in Sekunden, was manuell wochenlang uebersehen wurde. |
| **Merke** | Wenn eine ctypes-Anbindung an eine fremde DLL Aerger macht, ist die ERSTE Massnahme ein vollstaendiger Abgleich aller Strukturen und Signaturen gegen den Original-Header — nicht die Suche nach dem einen kaputten Aufruf. Bei einer 64-Bit-DLL ist jedes `EdsUInt64` im Header, das im Code `c_uint` heisst, ein Fehler. Solche Fehler treten fast nie einzeln auf: Wer eine Stelle abgeschrieben hat, hat meist mehrere abgeschrieben. |


### "Lief frueher mal so" ersetzt keinen Beweis, dass es funktioniert hat (2.4.54)

| | |
|---|---|
| **Problem** | Die Box fror beim Start jeder Session ein. |
| **Ursache** | In 2.4.49 wurde ein schuetzender Nebenfaden um `EdsSetObjectEventHandler` entfernt — mit der Begruendung, eine aeltere Fassung habe den Aufruf direkt gemacht und "lief frueher zuverlaessig". Der Aufruf kehrt aber nicht von allein zurueck: Er wartet darauf, dass der Programmfaden Windows-Nachrichten abarbeitet, und blockiert genau diesen Faden. |
| **Der Fehlschluss** | Die aeltere Fassung lief tatsaechlich — aber in ihr wurde der Direktbetrieb praktisch nie benutzt, der problematische Aufruf kam also kaum vor. Aus "die Version lief" wurde faelschlich "diese Zeile in der Version war richtig". |
| **Lösung** | **Korrigiert in 2.4.59:** Kein Wegwerf-Nebenfaden und kein Pump im Hauptfaden. Der Handler wird im einzigen STA-Owner vor `OpenSession` registriert; ein Timeout sperrt diesen Owner fail-closed, statt den nativen Aufruf im Hintergrund weiterlaufen und einen zweiten Versuch zuzulassen. |
| **Merke** | Ein Hinweis wie "frueher lief das" grenzt den Suchraum ein — er beweist aber nicht, dass jede einzelne Zeile jener Fassung richtig war. Vor dem Zurueckbauen pruefen, ob der fragliche Pfad damals ueberhaupt durchlaufen wurde. Ein nativer Timeout darf nie zu einem weiterlebenden Zombie-Aufruf plus Retry fuehren. |


### Die Fotos gehen direkt in den Rechner, nicht ueber die Karte (2.4.53)

| | |
|---|---|
| **Entscheidung** | Die Kamera liefert jedes Foto direkt an den Box-Rechner (`SaveTo = Host`). Die Speicherkarte ist nur noch Notnagel, falls sich der Rueckkanal nicht einrichten laesst. |
| **Vorher** | Im Code stand "SD-Karte bevorzugt, Host-Download als Fallback". Steckte eine Karte in der Kamera, nahm die Box den Umweg: Kamera schreibt auf die Karte, Box fragt die Karte per USB staendig ab. |
| **Begruendung** | Fuer eine Fotobox ist der Kartenweg in jeder Hinsicht schlechter: Er schreibt erst und liest dann wieder, haengt am Zustand und Tempo der Karte, und die Bilder liegen doppelt. Der Direktweg ist das, was Fotobox-Software ueblicherweise tut. |
| **Merke** | Der Vorrang war nicht nur langsam, er hat auch die Fehlersuche verfaelscht: Weil in der Testbox zufaellig eine Karte lag, lief die Box ueber Wochen auf dem Notweg — und eine Reparatur am eigentlich gewollten Weg blieb ungetestet, ohne dass es auffiel. **Wenn es zwei Wege zum selben Ziel gibt, muss im Log stehen, welcher gerade genommen wird und warum.** Und der bevorzugte Weg gehoert dorthin, wo die Anforderung ihn hinstellt — nicht dorthin, wo die Testhardware ihn zufaellig hindraengt. |

### Capacity initialisiert den Host-Speicher einmal pro Session (korrigiert in 2.4.60)

| | |
|---|---|
| **Problem** | Die Kamera loeste hoerbar aus ("ich hoere den spiegel"), legte das Bild aber nirgends ab. |
| **Fruehere Annahme (2.4.53)** | `EdsSetCapacity` muesse vor jeder Aufnahme erneuert werden. Diese Annahme war nicht durch den Canon-Vertrag oder einen erfolgreichen Hardwarevergleich belegt. |
| **Neue Evidenz** | 2.4.59 meldete Capacity vor jedem Foto. Trotzdem scheiterte nur der erste Kaltstart-Versuch mit `CARD_NG`; sieben weitere Fotos derselben Session funktionierten. Das spricht fuer eine unvollstaendig bestaetigte Initialisierung, nicht fuer eine pro Foto verfallende Freigabe. |
| **Lösung** | Capacity nach `SaveTo=Host` genau einmal im geschuetzten Initialisierungsblock setzen und die Wirksamkeit danach begrenzt zuruecklesen. Nach Neuverbindung oder Recovery wird der gesamte Block erneut ausgefuehrt. |
| **Merke** | Eine wiederholte Massnahme darf nicht allein deshalb zum Vertrag werden, weil sie billig wirkt. Erst Herstellerfolge und Hardwaredaten entscheiden, ob ein Zustand pro Session oder pro Aktion hergestellt werden muss. |


### Vier Runden "eine Vermutung pro Build" sind teurer als ein Messlauf (2.4.51)

| | |
|---|---|
| **Problem** | Der DSLR-Ausfall wurde ueber vier Testrunden bearbeitet. Jede Runde fand eine echte Ursache, behob sie — und der Ausfall blieb. Jede Runde kostete Christian einen Build, einen Aufbau und einen Testlauf. |
| **Ursache des Vorgehens** | Jede gefundene Ursache erklaerte das Symptom vollstaendig und wirkte deshalb wie DIE Loesung. Tatsaechlich lagen mehrere Fehler uebereinander, und der Code wich beim Scheitern eines Weges automatisch auf den anderen aus — was den Blick auf die jeweils naechste Schicht verstellte. |
| **Lösung** | Ein Messmodus (`--dslr-test`), der alle plausiblen Varianten in einem Durchlauf durchprobiert und misst, statt eine pro Build zu raten. |
| **Merke** | Wenn zwei Reparaturrunden am selben Symptom scheitern, ist die dritte Vermutung nicht das Problem — die Methode ist es. Ab dem Punkt lohnt sich ein Werkzeug, das den Suchraum in einem Lauf abdeckt, fast immer: Es kostet einmal Entwicklungszeit statt jedes Mal einen kompletten Testzyklus beim Nutzer. **Und:** Der Hinweis "andere Software macht das auf derselben Hardware fluessig" ist kein Nebensatz, sondern der Beweis, dass die Hardware es kann und die eigene Herangehensweise falsch ist. |


### "Befehl erfolgreich uebermittelt" ist nicht "Aktion ausgefuehrt" (2.4.49)

| | |
|---|---|
| **Problem** | Das Box-Log meldete "✓ Kamera ausgeloest!", danach lief die Aufnahme in einen 10-Sekunden-Timeout. Die Bildanzahl auf der Karte blieb bei 1726. |
| **Ursache** | `EdsSendCommand(TakePicture)` bestaetigt nur, dass der Befehl bei der Kamera angekommen ist. Ob sie ihn ausfuehrt, steht auf einem anderen Blatt: Findet der Autofokus keinen Halt, loest sie nicht aus — ohne Fehlermeldung. |
| **Lösung** | **Korrigiert in 2.4.59:** Genau Canons Referenzfolge `Completely` → `OFF`, ohne halben Druck und ohne automatischen NonAF-Zweitausloeser. Press- und OFF-Rueckgabe werden getrennt geloggt. Erfolg gilt erst nach passendem Transfer-Event, Download und dekodiertem JPEG. |
| **Merke** | Bei Geraetesteuerung immer zwischen "Befehl angenommen" und "Wirkung eingetreten" unterscheiden — und die **Wirkung** protokollieren, nicht die Annahme. Ein automatischer Zweitausloeser ist keine harmlose Fehlerbehandlung: Das erste Bild kann nur verspaetet sein und dann entstehen zwei physische Aufnahmen. |

### Wenn der Nutzer sagt "frueher lief das", ist das ein Fahrplan, keine Meinung (2.4.49)

| | |
|---|---|
| **Problem** | Ueber mehrere Runden wurde am DSLR-Ausfall repariert, ohne die Ursache zu treffen. |
| **Wendepunkt** | Christians zwei Saetze: "canon kameras liefen immer zuverlaessig ohne sd karte" und "in einer alten version hat das schon mal viel besser funktioniert". Beides liess sich in der Git-Historie in wenigen Minuten pruefen — und beides stimmte. `git log -- src/camera/` zeigte, dass der Rueckkanal am 09.03.2026 in einem Commit umgebaut wurde, in dem es laut Betreff um Collage-Buttons und Webcam-Optimierung ging. |
| **Merke** | Eine Aussage wie "frueher ging das" grenzt den Suchraum auf einen Zeitraum ein und macht aus einer offenen Fehlersuche einen Vergleich zweier Staende. Das ist fast immer schneller, als die aktuelle Fassung weiter zu durchdenken. **Und:** Beilaeufige Aenderungen an fremden Schnittstellen gehoeren nicht in einen Commit, der laut Betreff etwas anderes tut — dort findet sie bei der spaeteren Suche niemand. |


### Ein falsches Byte-Layout sieht nicht wie ein Fehler aus — es sieht aus wie "nicht vorhanden" (2.4.48)

| | |
|---|---|
| **Problem** | Die Box meldete "Keine SD-Karte", obwohl eine Karte in der Kamera steckte. Erst Christians Zwischenruf ("bei dieser testbox ist doch eine sd karte drin!") machte klar, dass die Meldung luegt. |
| **Ursache** | In `EdsDirectoryItemInfo` war das erste Feld `size` als 32-Bit-Zahl deklariert, der Canon-Header sagt aber `EdsUInt64` (64 Bit). Dadurch waren alle folgenden Felder um 4 Bytes verschoben: `isFolder` las die oberen 32 Bit der Dateigroesse (bei normalen Dateien 0), der Dateiname kam leer an. Die Pruefung `name == "DCIM" and isFolder` konnte nie zutreffen. |
| **Lösung** | Struktur gegen `EDSDKTypes.h` korrigiert (der Header liegt im Repo). Zusaetzlich: Eine leere Karte gilt nicht mehr als "keine Karte" — DCIM entsteht erst mit dem ersten Foto. |
| **Merke** | Ein falsches Speicher-Layout wirft keine Ausnahme. Es liefert plausible, falsche Werte — und die Software zieht daraus eine plausible, falsche Schlussfolgerung ("keine Karte da"). Deshalb sucht man an der falschen Stelle weiter. **Zwei Konsequenzen:** Erstens Strukturen immer gegen den Hersteller-Header pruefen, nie aus einem Beispiel abschreiben. Zweitens: Wenn eine Software meldet, dass etwas "nicht da" ist, und ein Mensch widerspricht — dann hat der Mensch recht, bis das Gegenteil bewiesen ist. Der Zwischenruf war hier mehr wert als jede weitere Logrunde. |

### Zwei kaputte Wege ergeben einen Totalausfall, der nach einem dritten Problem aussieht (2.4.48)

| | |
|---|---|
| **Problem** | Ueber mehrere Runden hinweg kam kein einziges DSLR-Foto an. Jede gefundene Ursache erklaerte den Ausfall — und behob ihn trotzdem nicht. |
| **Ursache** | Es gab zwei voneinander unabhaengige Wege, ein Foto von der Kamera zu holen: ueber die Speicherkarte und ueber den direkten Download. **Beide waren kaputt** — die Kartenerkennung durch das falsche Byte-Layout, der Download durch einen nie eingerichteten Rueckkanal. Der Code wich beim Scheitern des einen Weges automatisch auf den anderen aus und verdeckte damit, dass es zwei Fehler waren. |
| **Merke** | Eine automatische Rueckfallebene ist eine Schuldenfalle, wenn sie stillschweigend greift: Sie macht aus zwei Fehlern einen einzigen, verwirrenden Ausfall. Wer einen Ausweichpfad einbaut, muss deutlich ins Log schreiben, DASS und WARUM ausgewichen wurde — und beim Suchen zuerst fragen, welcher Weg eigentlich gerade benutzt wird. Die Zeile "Keine SD-Karte -> Host-Download Modus" stand von Anfang an im Log; sie wurde nur als Feststellung gelesen statt als Symptom. |


### Ein Kommentar, der eine Annahme als Tatsache ausgibt, kostet Monate (2.4.47)

| | |
|---|---|
| **Problem** | Die DSLR-Boxen lieferten keine Fotos. Die Suche ging in mehreren Runden an der Ursache vorbei. |
| **Ursache** | In `edsdk.set_object_event_handler` stand: „Der DLL-Call kehrt auf manchen Systemen NIE zurueck, registriert den Handler aber trotzdem" — und die Funktion meldete Erfolg. Das war nie geprueft worden. Tatsaechlich war der Rueckkanal nicht eingerichtet: bei ueber 200 Ausloesungen kam kein einziges Ereignis an. Weil die Funktion Erfolg meldete, galt dieser Teil als „funktioniert" und wurde bei jeder Fehlersuche uebersprungen. |
| **Lösung** | Laenger pumpen (0,5 s → 4 s), und bei Fehlschlag ehrlich `False` melden. Dazu ein Zaehler, der sichtbar macht, wie oft der Rueckkanal wirklich gefeuert hat. |
| **Merke** | Ein Kommentar wie „funktioniert trotzdem" ist eine Behauptung ueber fremden Code, die man nicht beweisen kann — er gehoert nicht in eine Erfolgsmeldung. Wenn eine Funktion nicht sicher weiss, ob sie erfolgreich war, muss sie das sagen duerfen. Und: Fuer jede solche Annahme einen Zaehler mitlaufen lassen. Die Frage „ist der Rueckkanal jemals gelaufen?" war mit einer einzigen Zahl in Minuten zu beantworten — ohne sie blieb es monatelang Ratespiel. |

### Diagnosedaten muessen zum Entwickler kommen, nicht der Entwickler zu den Daten (2.4.47)

| | |
|---|---|
| **Problem** | Jede Testrunde an einer Box endete damit, dass Christian mit einem USB-Stick zur Box lief, Logs kopierte und zum PC zurueckbrachte. Bei mehreren Runden am Tag war das der groesste Zeitfresser — und bei einer Box beim Kunden gar nicht moeglich. |
| **Lösung** | Knopf im Service-Menue, der die Logs ueber den bereits vorhandenen Heartbeat-Kanal ans Dashboard schickt. Adresse wird aus dem Heartbeat-Endpunkt abgeleitet, Zugangsschluessel ist derselbe. |
| **Merke** | Wenn ein bestehender, provisionierter Kanal zwischen zwei Systemen existiert, ist er fast immer die richtige Grundlage fuer den naechsten Anwendungsfall. Ein zweites Geheimnis auf ~280 Geraete auszurollen waere Wochen Arbeit gewesen, ohne einen Sicherheitsgewinn: Der neue Endpunkt nimmt nur Text entgegen und gibt nichts oeffentlich heraus. Faustregel fuer Feldgeraete: Wenn eine Diagnose dreimal per Hand geholt wurde, ist es Zeit, sie holen zu lassen. |


### Fehlertabellen NIE aus dem Kopf schreiben — der Hersteller-Header liegt im Repo (2.4.46)

| | |
|---|---|
| **Problem** | Die Box-Logs meldeten bei jeder DSLR-Störung „EDSDK Fehler 0x81 (INVALID_PARAMETER)". Das klang nach einem Programmierfehler auf unserer Seite, also wurde monatelang im eigenen Code gesucht. |
| **Ursache** | Die Übersetzungstabelle von Fehlercode zu Klartext in `edsdk.py` war frei erfunden und an den entscheidenden Stellen falsch. `0x81` heißt in Wahrheit `DEVICE_BUSY`, `0xc1` heißt `COMM_DISCONNECTED` (USB-Verbindung abgerissen). Beides sind **Hardware**-Meldungen, keine Programmfehler. |
| **Lösung** | Tabelle 1:1 aus `EDSDK/EDSDKv132010W/.../Header/EDSDKErrors.h` erzeugt — der Header liegt seit jeher im Repo. Dazu eine Liste `VERBINDUNG_TOT`, an der die App erkennt, wann Weiterprobieren zwecklos ist. |
| **Merke** | Wenn ein fremdes System Zahlencodes liefert, ist die Übersetzung Teil der Diagnose. Eine falsche Übersetzung ist schlimmer als gar keine: Sie führt die Fehlersuche aktiv in die falsche Richtung. Bevor eine solche Tabelle von Hand gepflegt wird, erst prüfen, ob der Hersteller-Header vorliegt — und ihn dann als Quelle nehmen. |

### Ein Notnagel, der nie „nein" sagt, ist kein Notnagel (2.4.46)

| | |
|---|---|
| **Problem** | Auf den DSLR-Boxen landete dreimal exakt dasselbe Bild in einer Collage. |
| **Ursache** | `get_frame()` gab bei toter Kamera stillschweigend das zuletzt gelungene Vorschaubild zurück — auch wenn es Minuten alt war. Für die laufende Vorschau ist das richtig. Die Foto-Notlösung rief dieselbe Funktion auf, bekam sofort ein Bild, hielt es für frisch und brach ihre 10er-Wiederhol-Schleife nach dem ersten Versuch ab. |
| **Lösung** | Der Aufrufer entscheidet, ob ein Altbild zulässig ist (`allow_stale`). Vorschau: ja. Foto: nein. Zusätzlich Fingerabdruck über jedes gelieferte Notbild — zweimal dasselbe wird abgelehnt. |
| **Merke** | Eine Rückfallebene muss unterscheiden können zwischen „ich habe etwas" und „ich habe etwas Brauchbares". Wer immer irgendetwas zurückgibt, macht aus einem sichtbaren Ausfall einen unsichtbaren Datenfehler — und der fällt erst beim Kunden auf. Im Zweifel lieber ehrlich `None` liefern: `session.py` behandelt „kein Foto" seit jeher sauber. |

### Wer Arbeit in einen Neben-Faden verschiebt, verschiebt womöglich auch den Briefkasten (2.4.46)

| | |
|---|---|
| **Problem** | Zwei DSLR-Boxen, 212 Auslösungen, **null** echte Fotos. Die Kamera löste aus, aber kein Bild kam je an. |
| **Ursache** | Canons Bibliothek meldet „Bild ist fertig" über die Windows-Nachrichtenschlange an genau den Programmfaden, der die Kamera geöffnet hat — den Haupt-Faden mit der Bedienoberfläche. Abgeholt wurde die Meldung aber nur in der Warteschleife der Aufnahme. Und die wurde irgendwann in einen Hintergrund-Faden verlegt, damit die Oberfläche flüssig bleibt. Seitdem lagen die Meldungen ungelesen im Haupt-Faden. |
| **Lösung** | **Korrigiert in 2.4.59:** Der einzige Canon-Owner öffnet die Session, pumpt alle 50 ms `EdsGetEvent` und die Windows-Nachrichten. Tk- und Capture-Thread rufen EDSDK nie auf. Der native Callback stellt nur Folgearbeit in dieselbe Owner-Queue. |
| **Merke** | Verlagerung in einen Hintergrund-Faden ist bei Bibliotheken mit Ereignis-Rückruf nie folgenlos. Wenn nach so einem Umbau „alles läuft, nur die Rückmeldung kommt nicht", zuerst fragen: Welcher Faden besitzt Session, Message-Pump und Callback — und ist es wirklich derselbe? |


### Ein „Optimierung": Wer eine Arbeit einspart, kann eine unbemerkte Selbstheilung mit einsparen (2.4.44)

| | |
|---|---|
| **Kontext** | Der klassische Foto-Weg setzte vor JEDEM Foto `set(1920x1080)` und danach die Vorschau-Auflösung neu. Das galt als reine Verschwendung (1,8 s pro Foto) — der Dauerbetrieb hat es ersatzlos gestrichen. |
| **Erkenntnis** | Dieses ständige Neusetzen war zugleich eine **Selbstheilung**, die niemand bewusst gebaut hatte: Rutschte die Kamera durch USB-Wackler, Energiesparen oder Treiber-Reset auf 640x480 zurück, zog der nächste Auslöser sie wieder gerade. Ohne sie hätte die Box nach so einem Abrutscher bis Abendende still Fotos in 640x480 gespeichert und gedruckt — ohne Abbruch, ohne Fehlermeldung, weil `get_high_res_frame` allein dem gemerkten Wert glaubte. |
| **Entscheidung** | Der Ist-Zustand wird nach jedem Foto am WIRKLICH gelieferten Bild (`frame.shape`) nachgezogen, nicht an einer gemerkten Zahl und nicht an `cap.get(...)`. Bei Abweichung: Dauerbetrieb verlassen + ein sofortiger zweiter Anlauf auf dem klassischen Weg. |
| **Merke** | Vor dem Streichen einer wiederholten Arbeit fragen: **Was repariert diese Wiederholung nebenbei?** Und: Eine gemeldete Eigenschaft (`cap.get`) ist das Versprechen des Treibers, das gelieferte Bild ist die Wirklichkeit — geprüft wird immer am Bild. |

### Ein Schalter muss am Schalter hängen, nicht an einem Merkmal, das gerade zufällig mitläuft (2.4.44)

| | |
|---|---|
| **Kontext** | Etappe 2 (Dauerbetrieb HD) lag hinter einem Config-Schalter mit Grundwert AUS. Zwei gemeinsam genutzte Stellen fragten aber nicht den Schalter, sondern ein Merkmal, das im Normalfall dasselbe bedeutete: „ist die Vorschau schon so groß wie das Foto?" bzw. „wurde gerade umgeschaltet?". |
| **Folge** | Auf einer Box mit AUS hätte sich die neue Betriebsart einschalten können, sobald die Vorschau-Auflösung ≥ Foto-Auflösung ist (Foto-Auflösung ist im Admin frei eintippbar; eine Kamera ohne 640x480 ist bei der C922-Ablösung realistisch). Und die eingesparte Puffer-Leerung griff auf jeder Flottenbox, deren Preview-Restore einmal fehlgeschlagen war. |
| **Merke** | Bei Etappen-Rollouts auf Live-Systemen: Jede Verzweigung, die neues Verhalten auslöst, muss **den Schalter selbst** abfragen — auch wenn ein anderes Merkmal „im Feld immer dasselbe" bedeutet. Zusätzlich den ECHTEN Ist-Zustand der Hardware abfragen (Schalter an, aber Kamera hat abgelehnt = klassisch), nie nur den Wunsch aus der Config. |

### Bildkette: teure Pixel-Operationen ans ENDE, wo das Bild am kleinsten ist (2.4.41)

| | |
|---|---|
| **Kontext** | LiveView spiegelte und färbte jeden Frame in voller Kameragröße um und verkleinerte erst danach aufs Collagen-Fach. Bei 640x480 also 307.200 Punkte Arbeit für ein Ergebnis mit 86.880 Punkten. |
| **Entscheidung** | Reihenfolge umgedreht: verkleinern → spiegeln → beschneiden → umfärben. Spiegeln/Umfärben laufen nur noch über die Fachgröße. |
| **Warum das erlaubt ist** | `cv2.resize` ist ein separierbarer Filter mit symmetrischer Abtastung (`src=(dst+0,5)*scale-0,5`), vertauscht also mit `flip`; die Abweichung ist reine Festkomma-Rundung (max 1 von 255). `cvtColor` BGR→RGB ist eine reine Kanal-Vertauschung pro Pixel und vertauscht **exakt** mit resize/flip/Beschnitt. |
| **Merke** | Die Reihenfolge von Filter-Operationen ist oft frei wählbar — dann gehört die teure Operation dorthin, wo das Bild am kleinsten ist. Aber: **spiegeln VOR dem Beschneiden**, nie danach. Ein mittiger Beschnitt ist bei ungeradem Rest asymmetrisch (1920x1080 in ein 240x362-Fach: fit_w=643, Rest 403), ein Spiegeln danach verschiebt den Ausschnitt um einen Pixel. |

### LiveView: Producer/Consumer-Thread statt Aufbereitung im Tk-UI-Thread (2.4.16)

| | |
|---|---|
| **Kontext** | Stresstest `fexobooth_20260806_142249.log`: LiveView 2,5–5 fps statt 20, weil Spiegeln/Overlay/Skalieren/Anzeigen ~150 ms pro Frame komplett im Tk-Hauptthread liefen; >140 UI-Hitches in 16 min. Sobald Windows-Hintergrundlast (Defender/Update) dazukommt, kippt die Box in „hängt". |
| **Entscheidung** | Aufbereitung in einen Daemon-Worker-Thread; Übergabe über eine Ein-Frame-Variable (`_lv_latest`, nur der neueste Frame — bewusst KEINE Queue, kein Rückstau). Der Worker skaliert auf exakt `round(logisch*scaling)` vor: PIL `resize()` mit identischer Zielgröße ist ein `copy()` (Fastpath, verifiziert), CTkImage skaliert damit intern nichts mehr. `winfo_*` bleibt strikt im UI-Thread — der Worker bekommt die Zielgröße über eine vom UI-Takt gepflegte Variable. Kamera-Zugriff zusätzlich per `_cam_access_lock` serialisiert (nicht jedes Kamera-Backend ist intern gelockt). |
| **Alternativen** | (a) Nur Compositing optimieren: reicht nicht, die Anzeige selbst blockierte ~110 ms. (b) `tk.Label` + `ImageTk.PhotoImage` statt CTkLabel: minimal schneller, aber Umbau aller Anzeige-Pfade (Flash/Fotoanzeige) — unnötig, da der Fastpath dieselbe Wirkung hat. (c) Kamera dauerhaft 1080p (spart 3 s Umschaltung/Foto): von Christian verworfen, aktueller Weg ist auf normalen Miix schneller. |
| **Merke** | Bei Tk auf schwacher Hardware gilt: Der UI-Thread darf Bilder nur noch ANZEIGEN, nie aufbereiten. PhotoImage/CTkImage-Erzeugung muss im UI-Thread bleiben (Tk ist nicht thread-sicher) — deshalb im Worker exakt auf die Zielgröße vorskalieren, damit die UI-seitige Erzeugung nur noch ein Memcpy ist. Adaptive Taktung beidseitig: Worker schläft mind. ~1/3 der Frame-Zeit (CPU nie sättigen), UI-Takt = 3× gemessene Anzeige-Kosten. |

### Windows-Leistungsregler per API setzen statt Benutzer-Doku (2.4.16)

| | |
|---|---|
| **Kontext** | Der Miix drosselt im Standard-Energiemodus spürbar; der Schieberegler im Akku-Flyout stand in der Flotte zufällig. Kunden-Anleitung wäre fehleranfällig (>200 Geräte). |
| **Entscheidung** | Beim App-Start `PowerSetActiveOverlayScheme` (powrprof.dll) mit dem „Best Performance"-GUID `ded574b5-…` aufrufen — exakt das, was der Schieberegler tut, ohne Admin-Rechte. Windows persistiert die Wahl pro Stromquelle; einmaliges Setzen am Netz genügt. Zusätzlich Prozess-Priorität ABOVE_NORMAL (bewusst nicht HIGH — würde Treiber/Audio aushungern). |
| **Merke** | Für Slider-/Flyout-Einstellungen von Windows gibt es fast immer eine User-Mode-API — die App beim Start selbstheilen lassen ist zuverlässiger als Setup-Skripte oder Anleitungen. Scheitert die API (altes Windows), leise weitermachen und nur loggen. |

### Selbsttest muss den ECHTEN Betriebsweg testen, nicht einen eigenen (2.4.26)

| | |
|---|---|
| **Kontext** | Der Event-Selbsttest öffnete die Webcam kalt in voller Foto-Auflösung (1920×1080) und maß die Init-Zeit. Auf älteren C920 dauert dieser Kalt-1080p-Open ~7,6 s (Fehlalarm „Kamera langsam") und kann die Box sogar einfrieren (Feld-Log Box 224, 13.08. — Log endet exakt bei „Kamera geöffnet"). Die Kamera war dabei kerngesund (16 fps, Foto in 0,1 s). Der Normalbetrieb öffnet aber NIE kalt in 1080p: Vorschau 640×480, pro Foto kurz `get_high_res_frame` auf 1080p und zurück (~1,5 s, robust). |
| **Entscheidung** | Selbsttest exakt auf den Betriebsweg umgestellt: Kamera in Vorschau-Auflösung öffnen (wie `app.py`-Vor-Init), Testfoto über `get_high_res_frame`, danach `restore_preview_resolution()`. DSLR-Pfad unverändert (LiveView-Frame, kein echtes Auslösen). |
| **Merke** | Ein Diagnose-/Selbsttest, der einen ANDEREN Code-/Hardware-Pfad nimmt als der echte Betrieb, erzeugt Fehlalarme ODER trifft Fehler, die im Betrieb gar nicht vorkommen (hier sogar ein Einfrieren, das der Betrieb nie hätte). Tests müssen denselben Weg gehen wie die Sache, die sie prüfen. Kamera-„langsam/hängt" beim Umstecken lösbar = USB-Zustand, nicht Kameradefekt. |
| **NACHTRAG 2.4.43** | Der Kalt-1080p-Open ist damit **entschärft, nicht mehr verboten**: `WebcamManager.initialize()` öffnet bei angeforderter HD-Auflösung jetzt zweistufig (640x480 → ein `read()`, damit der DirectShow-Graph läuft → hochsetzen). Das ist Schritt für Schritt der Weg, den `get_high_res_frame` im Feld seit Monaten fehlerfrei fährt. Der Selbsttest öffnet deshalb wieder in der Auflösung, die die Box **wirklich** benutzt — im HD-Dauerbetrieb also 1080p, mit eigener fps-Schwelle (9,0 statt 12,0, weil 1080p gemessene 13,9 statt 29,8 Bilder/s liefert). Die Lehre von oben bleibt exakt gültig, nur die richtige Antwort hat sich gedreht: Nicht „Test auf Vorschau festnageln", sondern „Test folgt dem Betriebszustand". |

### Build-Version: Lokale Quelle ist `src/__init__.py`, GitHub-Release ist nur Veröffentlichung

| | |
|---|---|
| **Kontext** | Vor einem EXE-/Installer-Build braucht die Box bereits eine neue sichtbare Version, auch wenn noch kein GitHub-Release existiert. |
| **Entscheidung** | Die sichtbare Startscreen-Version und die API-Version kommen aus `src/__init__.py`. Der Installer liest dieselbe Quelle über `build_installer.bat` bzw. Workflow-Input. GitHub-Releases veröffentlichen später nur den bereits nummerierten Build. |
| **Merke** | Version zuerst lokal bumpen, dann EXE/Setup bauen, erst danach optional als GitHub-Release veröffentlichen. Sonst zeigt ein manuell gebauter Kandidat weiter die alte Flottenversion. |

### Top-Bar-Alarmtexte: Interne Fehlercodes bleiben stabil, Anzeige wird übersetzt

| | |
|---|---|
| **Kontext** | USB-, Kamera- und Druckerwarnungen in der oberen Status-Leiste sind kunden-/gastseitig sichtbar und müssen daher der `locale` folgen. Gleichzeitig hängen Drucker-Overlay, Klassifizierung, Logging und Support-Doku an den etablierten deutschen Fehlercodes aus `PrinterController.get_error()`. |
| **Entscheidung** | Die Fehlerquellen bleiben intern unverändert deutsch. Nur die Top-Bar-Anzeige übersetzt bekannte Codes über `TOPBAR_TRANSLATIONS`/`_translate_topbar_printer_problem()`. USB- und Kamera-Texte gehen direkt über `t(self.config, "topbar.*")`; Druckertexte werden erst unmittelbar vor `CTkLabel.configure()` in Anzeigetext umgewandelt. |
| **Merke** | Bei sicherheits-/supportrelevanten Fehlerzuständen nicht den internen Vertrag übersetzen, wenn andere Logik per String klassifiziert. Übersetzung an der UI-Kante hält Klassifizierung stabil und verhindert, dass neue Locales Drucker-Overlay oder Runbooks brechen. |

### Nikon-DSLR-Support Variante 3: eigene unsichtbare FexoNikonBridge (WPD-PTP), digiCamControl-App VERWORFEN

| | |
|---|---|
| **Kontext** | Variante 2 (digiCamControl-App, siehe verworfenen Eintrag unten) scheiterte im Realtest 2.4.10 doppelt: `CameraControl.exe` öffnet beim Autostart ein **sichtbares Fenster** vor FexoBooth (Kiosk-No-Go) und der lokale Webserver `127.0.0.1:5513` antwortet nie, weil die Webserver-Aktivierung eine persistente DCC-Einstellung ist, die die Standardinstallation nicht setzt. Multi-Agent-Webrecherche (2026-07-02, alle Kernaussagen adversarial verifiziert): Das **offizielle Nikon-SDK bietet für die gesamte D3xxx-Serie kein MD3-Modul** („SDKs not listed cannot be downloaded") → MAID/NikonCSWrapper/MekNikon sind Sackgassen; Nikon Webcam Utility unterstützt die D3300 gar nicht; Camera Control Pro 2 hat die D3xxx nie unterstützt (und ist eingestellt); libgphoto2 braucht unter Windows einen Zadig/WinUSB-Treibertausch (killt MTP, kein Hotplug) → nicht kiosk-tauglich. **dslrBooth unterstützt die D3300 inkl. LiveView** über direktes USB-PTP — muss also (mangels SDK) einen eigenen PTP-Stack nutzen. |
| **Entscheidung** | **Eigene `FexoNikonBridge.exe`** (C#, .NET Framework 4.8 = auf Win10/11 vorinstalliert): unsichtbarer Hintergrundprozess (CREATE_NO_WINDOW), Motor ist die **MIT-lizenzierte** Bibliothek `CameraControl.Devices` (Kern von digiCamControl, D3300 im Code explizit gemappt: `"D3300"` → `NikonD600Base`, LiveView `0x9201/0x9203` + Capture `0x90C0` als rohe PTP-Opcodes über die Windows-WPD-API, kein Treibertausch). Kommunikation FexoBooth↔Bridge über **stdin/stdout** (JSON-Zeilen + längenpräfixierte JPEG-Binärdaten): keine Ports, keine Firewall-Dialoge, kein Webserver-Aktivierungsschritt. `src/camera/nikon.py` ist der Bridge-Client (Drop-in-Interface wie Canon). CI (GitHub Actions) baut die Bridge, weil lokal kein .NET-SDK installiert ist. |
| **Alternativen** | (a) Offizielles Nikon-SDK/MAID: kein D3300-Modul → unmöglich. (b) digiCamControl-App + Webserver: sichtbar + unzuverlässig → verworfen. (c) pythonnet (Library im Python-Prozess): keine Crash-Isolation, .NET-Framework/PyInstaller-Kopplung → separater Prozess ist robuster. (d) libgphoto2/Windows: Treibertausch → raus. (e) Eigener PTP-Stack in Python über WPD-COM: technisch möglich, aber Neuland ohne erprobte Vorlage → unnötiges Risiko. |
| **Merke** | Wenn ein Hersteller-SDK ein Gerät nicht abdeckt, ist **rohes PTP/MTP über die Windows-WPD-API** der bewährte, unsichtbare Weg (offiziell von Microsoft dokumentierte MTP-Extensions, Standard-Treiber bleibt). Fremde Steuer-**Apps** einzubinden scheitert im Kiosk an Sichtbarkeit und Persistenz-Konfiguration — die zugrunde liegende **Bibliothek** im eigenen versteckten Prozess ist die richtige Altitude. |

### VERWORFEN (2026-07-02): Nikon-DSLR-Support über digiCamControl-App (Variante 2)

> Ersetzt durch Variante 3 (siehe oben). Grund: sichtbares DCC-Fenster beim Autostart + Webserver
> antwortet ohne manuelle Einmal-Aktivierung nie (Testlogs `D:\fexobooth_20260702_090008.log` u.a.).

| | |
|---|---|
| **Kontext** | Nikon D3300 soll als DSLR funktionieren wie bei dslrBooth. Zwei Wege: (1) Nikon Webcam Utility (Kamera erscheint als Webcam — aber nur LiveView-Auflösung, kein echtes Vollbild-Capture, kein Tethering-Steuerung), (2) digiCamControl als lokale Windows-Steuerungsschicht mit eigenem Webserver (`127.0.0.1:5513`). |
| **Entscheidung** | **Variante 2 (digiCamControl).** fexobooth bleibt ein **dünner HTTP-Adapter** (`NikonCameraManager`): LiveView über `/liveview.jpg`, Capture über Single-Command `capture` (Fallback `LiveView_Capture`), Bildübergabe über `session.folder`/`session.filenametemplate`/`lastcaptured` → lokale Datei, sonst `/image/<name>`, zuletzt `/preview.jpg`. digiCamControl darf extern installiert sein; sonst Auto-Start von `CameraControl.exe`. |
| **Begründung** | Vollbild-Capture in DSLR-Qualität + echtes Tethering ohne nativen Nikon-SDK-Aufwand. Der Adapter ist interface-kompatibel zu `CanonCameraManager` → **Drop-in** für den bestehenden Session-/App-Flow (`capture_photo`, `get_high_res_frame`, `get_frame`, `start/stop_live_view`, `release`, `is_initialized`). Keine native DLL → der Manager ist immer konstruierbar; „verfügbar" heißt nur „digiCamControl-Exe vorhanden ODER Webserver antwortet". |
| **Merke** | Externe Steuerungs-Tools mit lokalem HTTP-Vertrag (digiCamControl, dslrBooth-Pattern) sind ein sauberer Weg, fremde Hardware anzubinden, ohne den App-Kern aufzublähen. **Aber:** HTTP heißt **blockierende urlopen-Timeouts** — solche Calls niemals naiv auf den Tk-UI-Thread legen (siehe Lessons Learned: Init-Freeze). Seit dem 2026-07-02-Test gilt zusätzlich: Hardware-Runtime-Abhängigkeiten müssen im Setup mitgeliefert oder im Log eindeutig als fehlend ausgewiesen werden; sonst bleibt ein „DCC FEHLT" auf dem Tablet für den Betreiber nicht lösbar. |

### App-Plattform-Fundament: „Infrastruktur immer an" vs „Feature verkauft" sauber trennen

| | |
|---|---|
| **Kontext** | Bisher hing **alles** am Schalter `gallery_enabled`: Hotspot, Flask-Server, Foto-Routes UND die Box-Screen-UI. Folge: ohne gebuchte Galerie lief der lokale Kanal gar nicht → Template-/Settings-Korrektur unmöglich. Für das App-Fundament muss der Kanal **dauerhaft** laufen. |
| **Problem** | Sobald der Server immer läuft, wären die Foto-Routes (zahlendes Feature) auch für Nicht-Galerie-Kunden erreichbar – Produkt-/Sicherheitsverstoß. |
| **Entscheidung** | **Drei Ebenen entkoppeln:** (1) Infrastruktur (Hotspot+Flask) läuft immer; (2) das zahlende Foto-Feature wird **serverseitig pro Route** an einem eigenen Flag `_gallery_feature_enabled` gegated (403 wenn aus); (3) die **Box-Screen-UI** (QR/Banner) bleibt strikt an `gallery_enabled` – `start.py` gar nicht angefasst. Support-Routes (status/pairing/upload/apply) sind bewusst **immer** offen. |
| **Merke** | Ein „Kanal/Server läuft" ist NICHT dasselbe wie „Feature ist verkauft". Beim Entkoppeln eines Always-on-Kanals JEDE datenausliefernde Route einzeln gaten (nicht darauf verlassen, dass der Server vorher nur bei gebuchtem Feature lief). Sichtbarkeit am Gerät (Screen-UI) getrennt vom Netzwerk-Zugriff (Routes) absichern. |

### Vorwärtskompatible Feature-Flags: gemeldete Namen = settings.json-`features`-Keys, NICHT interne Config-Keys

| | |
|---|---|
| **Kontext** | `GET /api/v1/status` meldet eine `feature_flags`-Liste; die App liest sie und sendet gewünschte Flags per `apply/settings` als `{"features": {...}}` zurück. |
| **Falle** | Zuerst stand `allow_single_mode` in der Liste – das ist aber der **interne Config-Key**. `BookingSettings.from_dict` liest aus `features` nur `print_singles` und mappt das auf `config["allow_single_mode"]`. Hätte die App `allow_single_mode` gesendet, wäre es **stillschweigend ignoriert** worden. |
| **Entscheidung** | In der gemeldeten Flag-Liste ausschließlich die **JSON-Keys aus settings.json → `features`** führen, die `from_dict` wirklich liest: `live_gallery, print_enabled, print_singles, dslr_camera, max_prints`. |
| **Merke** | Bei „Box meldet, was sie kann" muss der gemeldete Name 1:1 dem Eingabe-Key entsprechen, den der Parser auswertet – sonst entsteht ein Flag, das die App anbietet, das aber nie wirkt. Interne Config-Namen ≠ API-/settings.json-Namen. |

### App-OTA: den bestehenden Updater wiederverwenden, im Idle über den Apply-Marker anwenden, hart beenden

| | |
|---|---|
| **Kontext** | Box-Software per App lokal updaten (statt USB / unzuverlässigem Firmen-WLAN-OTA). |
| **Entscheidung** | Den Update-Mechanismus **nicht neu erfinden**: Der Server verifiziert nur die **SHA256** (streamend) und stellt das ZIP bereit (`stage_software_update`), setzt einen `software`-Apply-Marker. Der **Main-Thread** wendet es nur im **Idle** (Startbildschirm) über den **bestehenden** `updater.apply_update_and_restart()` (Backup+Rollback+BAT) an. Marker **vor** dem Neustart löschen (kein Re-Apply-Loop), ZIP **nicht** vorzeitig löschen (BAT braucht es). Danach **harter Exit** (`os._exit`), sonst halten Kamera-/Flask-/USB-Threads den Prozess am Leben und das BAT kollidiert mit gelockten DLLs. |
| **Merke** | Bei selbst-ersetzender Software gilt: Verifikation und Anwendung trennen (Empfang im Server-Thread, Anwendung im UI-Thread/Idle). Ein laufendes OTA muss alle anderen Apply-Ticks sperren (`_software_update_in_progress`), damit kurz vor dem Exit kein torn write von `config.json` passiert. Staff-Auth über HMAC(PIN, Nonce) hält die PIN aus dem Klartext, ist aber bei 4-stelliger PIN nur ein Schutz im lokalen Hotspot (bewusst, Soft-Mode-Philosophie). |

### Selbst-Updater-Bootstrap: Der Fix wirkt erst beim NÄCHSTEN Update

| | |
|---|---|
| **Problem** | v2.4.5 sollte den Box-ID-Verlust beim OTA-Update beheben, im Test ging die Box-ID aber **trotzdem** verloren |
| **Ursache** | Beim OTA-Update erzeugt die **laufende (alte) Version** das BAT-Script, das danach die Dateien ersetzt (`create_update_script` in `src/updater.py`). Beim Update von v2.4.4 → v2.4.5 läuft also noch das **fehlerhafte** BAT von v2.4.4, das nur `config.json` im Root sicherte (nicht die Legacy-Config in `_internal/`). Der korrigierte BAT-Code aus v2.4.5 kommt erst beim übernächsten Update zum Einsatz |
| **Entscheidung** | Identität (Box-ID) **außerhalb des Installationsordners** persistieren: `C:\ProgramData\FexoBox\box_id.json`. Dieser Pfad wird von keinem Update-Script angefasst. `save_config()` spiegelt die ID dorthin, `load_config()` holt sie zurück wenn `config.json` keine hat |
| **Alternativen** | Windows-Registry (gleiche Wirkung, aber weniger transparent als eine Datei); nur BAT-Härtung (greift prinzipbedingt nie beim einführenden Update) |
| **Merke** | Bei selbst-aktualisierenden Programmen gilt: Ein Fix am Update-Mechanismus schützt **nie** das Update, das ihn ausliefert — immer erst das danach. Kritische Daten (Lizenzschlüssel, Geräte-IDs, Seriennummern) deshalb grundsätzlich außerhalb des ersetzbaren Programmverzeichnisses ablegen |

### DirectShow-Enumeration: PnP-Reihenfolge ≠ OpenCV-Reihenfolge

| | |
|---|---|
| **Problem** | `Get-PnpDevice -Class Camera,Image | Sort-Object InstanceId` liefert Kameranamen in einer Reihenfolge (PCI/Intel vor USB/Logitech), die NICHT der OpenCV `CAP_DSHOW` Enumeration entspricht. Dadurch wurde Index 0 der falsche Name zugeordnet → App benutzte interne Kamera statt Logitech |
| **Ursache** | PnP-InstanceIds sortieren alphabetisch (PCI\... < USB\...), DirectShow nutzt aber die COM-Enumeration über `ICreateDevEnum::CreateClassEnumerator(CLSID_VideoInputDeviceCategory)` mit eigener Reihenfolge |
| **Entscheidung** | DirectShow-Geräte direkt via C#/.NET COM-Interop abfragen (`Add-Type` in PowerShell). Nutzt exakt dieselbe API wie OpenCV intern. PnP-Abfrage (ohne Sort) als Fallback |
| **Alternativen** | ffmpeg `-list_devices` (nicht garantiert installiert), `comtypes` Python-Paket (neue Dependency), Resolution-Fingerprinting (fragil) |
| **Merke** | NIE annehmen dass PnP/WMI Gerätereihenfolge = DirectShow/OpenCV Reihenfolge. Immer dieselbe Enumeration-API nutzen wie das Framework das die Geräte öffnet |

> **Nachtrag 2.4.40:** Der PnP-Fallback ist ersatzlos gestrichen. Er war nicht nur
> in der Reihenfolge falsch, sondern in der Auswahl: `-Class Camera,Image` lieferte
> im Test **zwei Drucker und null Kameras** (die Klasse „Image" enthält Scanner und
> Multifunktionsgeräte). Diese Fremdnamen wurden positionsweise auf die cv2-Indizes
> geklebt — Index 0 (auf dem Miix die abgeklebte interne Kamera) hätte
> „HP Color LaserJet…" geheißen und wäre als „externe Kamera" ausgewählt worden.
> Ein Fallback, der falsche Daten liefert, ist schlimmer als gar keiner.

### PowerShell + `Add-Type` ist auf dieser Hardware kein Abfrageweg, sondern eine Fehlerquelle (2.4.40)

| | |
|---|---|
| **Problem** | Die DirectShow-Namensabfrage lief regelmäßig in ihre 10-Sekunden-Grenze (Box-Log 20.08.2026), die App schloss daraus „keine externe Kamera" und meldete die Box blind — obwohl die C922 angesteckt war und 11 Sekunden später problemlos gefunden wurde. |
| **Ursache** | `powershell -Command "Add-Type -TypeDefinition <C#>; …"` startet bei **jedem** Aufruf einen Prozess, lädt die CLR und ruft `csc.exe` zum Kompilieren auf. Gemessen: **~4 ms echte Arbeit in ~560–670 ms Verpackung.** Auf dem Atom x5-Z8350 mit eMMC skaliert genau diese Verpackung — nicht die Arbeit. Dazu: `subprocess.run(timeout=)` ist auf Windows **keine harte Grenze** (nach dem Kill läuft ein zweites `communicate()` ohne Timeout, während das verwaiste `csc.exe` die Pipes hält). |
| **Entscheidung** | Dieselbe COM-Kette in-process über `ctypes` (Standardbibliothek, keine neue Abhängigkeit): **2,6–6,6 ms gemessen**, über 200 Durchläufe stabil. Details, die verifiziert sind und so bleiben müssen: `ctypes.windll.ole32` statt `oledll` (sonst fliegt die Funktion bei `RPC_E_CHANGED_MODE` = 0x80010106 raus, obwohl COM in Ordnung ist — im MTA-Thread nachgestellt); `0`, `1` und `0x80010106` alle als brauchbar behandeln; `CoUninitialize` nur bei selbst durchgeführter Initialisierung; vtable-Slots CreateClassEnumerator=3, Next=3, BindToStorage=9, Read=3; `restype = c_long`, nicht `ctypes.HRESULT`. |
| **Alternativen** | `comtypes` (neue Abhängigkeit, Randbedingung); `pywin32` — **kann es nachweislich nicht**: `CoCreateInstance` auf `ICreateDevEnum` scheitert mit „There is no interface object registered that supports this IID", auch über den Umweg `IUnknown`; `pnputil` (immer noch ein Prozessstart, immer noch PnP-Reihenfolge, `/enum-devices` erst ab Win10 1903). |
| **Merke** | Auf schwacher Hardware ist nicht die Arbeit teuer, sondern die **Verpackung**. Ein Prozessstart pro Abfrage in einer Schleife, die alle 2 s läuft, ist auf einem Atom keine Kleinigkeit — er ist der Hauptposten. Bevor ein Timeout erhöht wird: nachmessen, wieviel davon überhaupt Nutzarbeit ist. Und: ein Timeout, das regelmäßig zuschlägt, verfälscht nicht nur die Laufzeit, sondern das **Ergebnis**. |

### Fehlendes Wissen darf nie als negativer Befund verbucht werden (2.4.40)

| | |
|---|---|
| **Problem** | `find_best_camera()` verwarf jede Kamera, deren Name dem Platzhalter `"Kamera {index}"` entsprach. Der Platzhalter entstand aber genau dann, wenn die **Namensabfrage** fehlschlug. Ergebnis: „Ich kenne den Namen nicht" wurde zu „Das ist die gesperrte interne Kamera" — und die Box meldete sich blind, obwohl cv2 die Kamera erfolgreich geöffnet hatte. |
| **Ursache** | Zwei Zustände (`extern` / `intern`) für drei mögliche Sachverhalte. Für „weiß ich nicht" gab es keinen Platz, also landete er beim nächstbesten — und das war ausgerechnet die Variante mit der härtesten Konsequenz. Die Platzhalter-Regel stammte vom 27.03.2026 und war gegen namenlose **Phantom-Duplikate** gebaut, nicht gegen eine gescheiterte Abfrage; beide sahen im Code identisch aus. |
| **Entscheidung** | Dritter Zustand `unbestimmt` plus ein Feld `namensquelle` (`dshow` / `luecke` / `fehlt`), das „Abfrage lief, kennt diesen Index nicht" von „Abfrage ist gar nicht gelaufen" trennt. Im unbestimmten Fall wird nicht geraten, sondern über eine **zweite, unabhängige Quelle** (Registry `KSCATEGORY_VIDEO`, nur `Linked=1`) gegengeprüft. Ein misslungener Suchlauf darf eine funktionierende Einstellung nie überschreiben. |
| **Merke** | Wenn eine Erkennung nur zwei Antworten kennt, prüfen, ob es nicht drei Sachverhalte gibt — und wo „weiß ich nicht" gerade stillschweigend hinsortiert wird. Ein Platzhalter, der aus einem **Fehlerfall** entsteht, darf niemals Entscheidungsgrundlage sein; er ist Anzeigetext. Und ein Fehlerbefund (hier `camera_index = -1`) gehört nicht in den dauerhaften Speicher — bis 2.4.39 nagelte ein einziger Aussetzer die Box über `ProgramData` **dauerhaft** in den Blindzustand. |

### Ein Indiz beantwortet oft eine ANDERE Frage als die gestellte (2.4.40, Nachbesserung)

| | |
|---|---|
| **Problem** | Der erste Entwurf der neuen Erkennung nahm ein namenloses Gerät als externe Kamera, wenn die Registry „genau eine USB-Videoquelle" meldete. Klingt zwingend, ist es aber nicht: geprüft wurde **„hängt eine USB-Kamera am Bus?"**, gebraucht wurde **„ist DIESER cv2-Index diese Kamera?"**. Ist das Kabel der C922 raus und die interne Tablet-Kamera selbst per USB angebunden (kommt vor), bestätigt die Registry die interne Kamera sich selbst — schwarze Fotos beim Kunden statt blinkender Warnung. |
| **Ursache** | Registry-Liste und DirectShow-Liste sind zwei getrennte Welten. Die Registry ist alphabetisch und kennt keine cv2-Indizes; sie kann eine Menge beschreiben, aber keine Zuordnung. Das einzige Feld, das aus **derselben** Aufzählung stammt wie der Index, ist der `DevicePath` des Geräts. |
| **Entscheidung** | Übernahme eines namenlosen Geräts nur noch aus dem Gedächtnis — und ins Gedächtnis kommt nur, was Name **und** eigenen `usb#`-DevicePath hatte. Zusätzlich muss die Zahl der aufgezählten Geräte zum gemerkten Stand passen. Die reine USB-Gegenprobe ist gestrichen. |
| **Merke** | Bei jeder Gegenprobe wörtlich aufschreiben, welche Frage sie beantwortet, und danebenlegen, welche Frage man eigentlich stellt. Sind es zwei verschiedene Sätze, ist der Schluss ein Fehlschluss — egal wie plausibel er klingt. Genauso: ein Wert, der einfach nur in der Config steht (`camera_index = 0`), ist **kein** Beweis, sondern ein Grundwert. |

### CTkImage DPI-Skalierung: winfo_width() vs CTkImage.size

**Problem:** `winfo_width()`/`winfo_height()` geben **Tk-Pixel** zurück, `CTkImage(size=...)` erwartet aber **logische (DPI-unabhängige) Pixel**. Bei 125% DPI-Skalierung (Lenovo Miix 310: 1280x800 physisch, 1024x640 logisch) waren alle Bilder 25% zu groß → Template im LiveView abgeschnitten.

**Fix:** Immer durch `_get_widget_scaling()` teilen:
```python
scaling = self._get_widget_scaling()
logical_w = int(container_w / scaling)
ctk_img = ctk.CTkImage(size=(logical_w, logical_h))
```

Betrifft: `_display_preview()`, `_build_flash_cache()`, `_show_main_preview()`, Final-Screen Preview.

### VERWORFEN 2.4.59: Handler im Wegwerfthread und Erfolg trotz Timeout

| | |
|---|---|
| **Alte Annahme** | Ein blockierter `EdsSetObjectEventHandler` wurde nach 500 ms trotzdem als Erfolg behandelt; der native Aufruf lebte in einem Daemon-Thread weiter. |
| **Warum verworfen** | Das war kein Cleanup: Die DLL konnte weiter blockiert bleiben, die Kamera danach DEVICE_BUSY melden und jeder Retry einen weiteren Zombie-Aufruf erzeugen. „Registriert vermutlich“ war nie ein belastbarer Erfolg. |
| **Aktuelle Entscheidung** | Object- und State-Handler werden im einzigen STA-Owner vor `OpenSession` registriert. Nur echte Rückgabe `EDS_ERR_OK` zählt. Hängt ein nativer Aufruf, wird der Owner gesperrt und kein weiterer EDSDK-Auftrag gestartet. |
| **Merke** | Einen nicht zurückgekehrten Hardwareaufruf nicht als Erfolg deklarieren. Ein Daemon-Thread beseitigt keinen nativen Lock. |

### Korrigiert 2.4.59: Event 0x208 ist der offizielle Host-Transfer

| | |
|---|---|
| **Kontext** | Der alte Wrapper nannte `0x108` Standard und `0x208` eine EOS-2000D-Abweichung. Der mitgelieferte `EDSDKTypes.h` definiert aber Object-All=`0x200`, DirItemCreated=`0x204` und DirItemRequestTransfer=`0x208`. |
| **Entscheidung** | Nur die offiziellen Transfer-Events `0x208`/`0x209` starten einen Download. `0x204` ist kein Transferauftrag; unbekannte Events mit Referenz werden sauber freigegeben. |
| **Merke** | Eventwerte direkt aus dem Hersteller-Header testen. „Großzügig behandeln“ kann bei Ownership-Events zu doppeltem Download, falschem Complete oder Leaks führen. |

### Canon DSLR: Kamera-Shutdown Recovery (Event 0x301)

| | |
|---|---|
| **Kontext** | Canon EOS 2000D sendet `0x00000301` (Shutdown) wenn Transfer-Events nicht beantwortet werden. Danach schlagen ALLE EDSDK-Calls mit Fehler 0x61 (UNKNOWN) fehl |
| **Entscheidung** | `_camera_shutdown` wird bei State-Event `0x301` gesetzt. Beim nächsten Capture werden Session und alte Kamera-Referenz atomar freigegeben; danach folgt eine vollständige Neu-Enumeration mit neuen Handles, Handlern und `SaveTo=Host`. |
| **Merke** | Alte EDSDK-Referenzen nach Shutdown/SDK-Störung nicht wiederverwenden. Recovery bedeutet neue Enumeration, nicht nur Close/Open auf demselben Handle. |

### Performance: Kamera zwischen Sessions offen halten!

| | |
|---|---|
| **Kontext** | Jede Session-Start dauerte 7s weil `reset_session()` die Kamera komplett freigab und `on_show()` sie neu initialisierte |
| **Entscheidung** | Kamera bleibt zwischen Sessions initialisiert. `reset_session()` stoppt nur LiveView. `on_show()` prüft `is_initialized` und überspringt Init. Kamera wird nur noch bei App-Exit und `_emergency_quit()` freigegeben |
| **Ergänzung** | Kamera-Vorinitialisierung während Start-Video: `play_video("video_start")` startet Init nach 200ms parallel. VLC spielt in eigenem Thread weiter. Wenn Video endet, ist Kamera bereit |
| **Merke** | EDSDK Session/Init ist teuer (~1-5s). Kamera-Connection zwischen Sessions wiederverwenden, nicht jedes Mal neu aufbauen |

### Korrigiert 2.4.59: EDSDK gehört ausnahmslos einem COM-STA-Owner

| | |
|---|---|
| **Kontext** | Canon EDSDK DLL nutzt Windows COM mit Single-Threaded Apartment. Wenn zwei Threads gleichzeitig EDSDK-Funktionen aufrufen (z.B. UI-Thread `list_cameras()` + Background-Thread `capture_photo()`), entsteht ein Deadlock |
| **Entscheidung** | Jeder `EDSDK_DLL.*`-Aufruf läuft im dedizierten `edsdk-kamera`-STA mit Queue, zentralem `EdsGetEvent` und Windows-Message-Pump. UI-, Capture- und Status-Threads rufen nur dispatchende Python-Wrapper auf. |
| **Verworfen** | `is_initialized` als Proxy sowie einzelne Locks. Auch Initialisierung, Statusprobe, Release und Fehlerpfade besitzen native Handles und müssen denselben Owner nutzen. |
| **Begründung** | Ein Lock verhindert Gleichzeitigkeit, aber nicht den Wechsel des COM-Apartments. Nur derselbe ausführende Thread erfüllt beide Bedingungen. |

### Kiosk-Modus: Taskleiste verstecken + Benachrichtigungen unterdrücken (KEIN permanentes topmost!)

| | |
|---|---|
| **Kontext** | App muss im Kiosk-Modus laufen: Kein Zugang zu Windows für Kunden, keine störenden Windows-Meldungen. Aber eigene App-Dialoge (USB-Sync, Export, Event-Wechsel) müssen im Vordergrund erscheinen |
| **Entscheidung** | Drei-Säulen-Ansatz: (1) Taskleiste via Windows API verstecken (`FindWindowW("Shell_TrayWnd")` + `ShowWindow(SW_HIDE)`), wird alle 5s re-assertet. (2) Windows-Benachrichtigungen via Registry unterdrücken (`NOC_GLOBAL_SETTING_TOASTS_ENABLED=0`). (3) `-topmost=True` nur KURZ beim Fenster-Positionieren, dann sofort wieder entfernt. Notfall-Shortcut Ctrl+Shift+Q zum Beenden |
| **Alternativen** | Permanentes `-topmost=True` (**SCHLECHT** - blockiert ALLE Dialoge inkl. eigener App-Dialoge, macht App unbedienbar!), `WS_EX_APPWINDOW` via `withdraw/deiconify` (Race Condition), Windows Kiosk-Modus / Assigned Access (braucht Enterprise) |
| **Begründung** | Permanentes `-topmost=True` verhindert dass Toplevel-Dialoge (auch eigene!) in den Vordergrund kommen. `transient()` + `grab_set()` reichen nicht gegen ein topmost-Elternfenster. Taskleiste-Verstecken allein ist ausreichend um Windows-Zugang zu verhindern. Benachrichtigungs-Toasts werden über Registry deaktiviert statt durch topmost überlagert |

### Webcam: Buffer-Flush mit grab() statt read(), niedrige Preview-Auflösung beibehalten

| | |
|---|---|
| **Kontext** | Webcam bei 320×240/640×480 für Preview (schwache Tablet-Hardware). Bei jedem Foto wird auf 1920×1080 umgeschaltet. Buffer-Flush mit `cap.read()` dekodiert jedes Frame komplett → langsam |
| **Entscheidung** | `cap.grab()` statt `cap.read()` für Buffer-Flush (grab bewegt nur den Pointer, dekodiert nicht). Flush-Frames von 5+3 auf 2+2 reduziert. Preview-Auflösung NICHT auf Capture-Auflösung erhöhen (LiveView wird zu laggy auf Miix 310!) |
| **Alternativen** | Webcam direkt in 1920×1080 initialisieren (LiveView zu laggy auf schwacher Hardware), gar kein Flush (alte Frames im Buffer) |
| **Merke** | `cap.grab()` ist deutlich schneller als `cap.read()` wenn man das Bild nicht braucht. Auf schwacher Hardware unbedingt niedrige Preview-Auflösung beibehalten |

### CustomTkinter: Runde Buttons auf transparentem Hintergrund → schwarze Ecken

| | |
|---|---|
| **Kontext** | CTkButton mit `corner_radius > 0` über einem Bild (via `place()`) zeigt schwarze Ecken. `bg_color="transparent"` funktioniert nicht wenn der Parent kein einheitliches `fg_color` hat |
| **Entscheidung** | Buttons auf einer schwarzen Leiste (`CTkFrame` mit `fg_color="#000000"`) platzieren statt direkt über dem Bild. Die Leiste geht über die volle Breite → Buttons mit `corner_radius` sehen sauber aus |
| **Merke** | CTk-Widgets können keine echte Transparenz über Bildern. Workaround: einheitlich farbiger Container als Basis für gerundete Buttons |

### Ueberholt 2.4.59: Canon-Produktion ist Host-only, nicht Dual-Modus

| | |
|---|---|
| **Kontext** | Canon EOS 2000D auf Fotoboxen - manche haben SD-Karte, manche nicht. Bilder müssen in voller DSLR-Auflösung auf dem Tablet landen. Host-Download hing anfangs → Ursache war der EDSDK-Deadlock (UI-Thread + Session-Thread gleichzeitig), NICHT der Host-Download selbst |
| **Entscheidung** | Die Flotte hat in der Regel keine Karte. Produktion setzt daher immer `SaveTo=Host` und nutzt Object-Event `0x208` plus Memory-Download. Kartenfunktionen bleiben nur als explizites Diagnosewerkzeug, nicht als automatische Laufzeitweiche. |
| **Verworfen** | Karte bevorzugen oder bei Fehlern still umschalten. Das machte Tests auf einer zufällig bestückten Box nicht auf die echte Flotte übertragbar und verdeckte zwei unabhängige Fehlerpfade. |
| **Begründung** | Ein verbindlicher Produktionsweg ist testbar. Das zentrale Owner-/Callback-Modell beseitigt die Architekturursache des früheren Host-Hängens. |

### Taskleiste: Crash-Sicherheit durch 3-Schichten-Schutz

| | |
|---|---|
| **Kontext** | `ShowWindow(SW_HIDE)` auf der Windows-Taskleiste ist persistent - bleibt auch nach App-Crash versteckt. Wenn die App abstürzt oder per Force-Kill beendet wird, ist die Taskleiste dauerhaft weg |
| **Entscheidung** | 3-Schichten-Schutz: (1) `atexit.register()` in `app.py` als Safety-Net bei sauberen Python-Exits. (2) `_recover_taskbar()` in `main.py` beim App-Start - stellt Taskleiste wieder her bevor die App das Fenster erstellt. (3) Global Exception Handler stellt Taskleiste bei unbehandelten Exceptions wieder her |
| **Alternativen** | Windows-Service der Taskleiste überwacht (Overkill), Scheduled Task beim Login (unzuverlässig), nur `atexit` (reicht nicht für harte Kills) |
| **Begründung** | `atexit` allein fängt keine SIGKILL/Stromausfälle ab. Die Recovery beim nächsten Start ist die zuverlässigste Lösung - selbst nach hartem Crash wird die Taskleiste beim nächsten Programmstart sofort wiederhergestellt, bevor die App sie erneut versteckt |

### OTA-Update: GitHub Releases statt Source-Archiv

| | |
|---|---|
| **Kontext** | 200 Produktions-Tablets laufen als PyInstaller-EXE (kein Python/Git installiert). Source-Download via `archive/refs/heads/main.zip` nutzlos, weil Tablets die EXE brauchen |
| **Entscheidung** | GitHub Releases API (`/repos/.../releases/latest`) + ZIP-Asset mit fertigem Build. In-App Button im Service-Menü + standalone BAT-Datei als Fallback |
| **Alternativen** | Auto-Updater mit Polling (braucht dauerhaft Internet), Inno Setup Installer erneut ausführen (braucht Admin-Rechte + User-Interaktion), eigener Update-Server (Overkill) |
| **Begründung** | Tablets sind meist offline (Hotspot-Modus). Update nur wenn manuell Internet angeschlossen. GitHub Releases ist kostenlos, versioniert, und die API ist stabil. BAT-Script als Fallback wenn App nicht startet |

### USB-Stick Erkennung: 3 Typen + Fallback

| | |
|---|---|
| **Kontext** | Verschiedene USB-Sticks können eingesteckt werden: Event-Sticks (Buchung), Backup-Sticks, oder fremde Sticks |
| **Entscheidung** | Label-basierte Erkennung: "fexobox" = Event, "FEXOSAFE" = Backup, alles andere = unbekannt → Export anbieten |
| **Alternativen** | Nur bekannte Sticks akzeptieren (kein Notfall-Export möglich) |
| **Begründung** | Wenn ein Kunden-Stick kaputt geht, muss es eine Möglichkeit geben, Bilder auf einen beliebigen USB-Stick zu exportieren. Erkennung über `GetDriveTypeW` (DRIVE_REMOVABLE) + `GetVolumeInformationW` (Label) |

### USB-Sync: Niemals automatisch, immer fragen

| | |
|---|---|
| **Kontext** | Bilder werden bei jedem Foto auf USB kopiert. Wenn der Kunde den Stick kurz abzieht und wieder einsteckt, fehlen evtl. Bilder auf USB |
| **Entscheidung** | Kein Auto-Sync. Bestätigungsdialog mit Fortschritt und Abbrechen-Button. Bei neuem Event (anderer Stick) wird NICHT kopiert |
| **Alternativen** | Auto-Sync bei jedem Einstecken (kopiert ungefragt, auch bei neuem Event), kein Sync (Bilder fehlen auf USB) |
| **Begründung** | User muss Kontrolle haben. Bei neuem Event dürfen alte Bilder nicht auf den neuen Stick. Nur bei gleichem Event ist Sync sinnvoll. Abbrechen-Option wichtig weil Kopieren auf schwacher Hardware lange dauern kann |

### Galerie-Server: Immer lokaler Pfad, nie USB

| | |
|---|---|
| **Kontext** | Bilder existieren an zwei Orten: Lokal (C:\FexoBooth\BILDER) und USB (F:\BILDER). USB ist Backup und darf nicht gelöscht werden |
| **Entscheidung** | Galerie liest immer vom lokalen Pfad. Löschen betrifft nur lokale Festplatte. No-cache Headers auf allen Gallery-Responses |
| **Alternativen** | USB-Pfad bevorzugen (Löschen wirkt nicht in Galerie), USB auch löschen (zerstört Backup) |
| **Begründung** | Lokaler Pfad = "Arbeitskopie", USB = "Backup". Galerie zeigt die Arbeitskopie. Wenn die gelöscht wird, ist die Galerie sofort leer. USB-Bilder bleiben sicher erhalten |

### Event-Wechsel: Pending-Dialog-Queue statt sofortigem Laden

| | |
|---|---|
| **Kontext** | Neuer USB-Stick kann jederzeit eingesteckt werden - auch während aktiver Foto-Session |
| **Entscheidung** | Pending-Dialog-Queue: Dialoge werden in `_pending_event_change` / `_pending_fexosafe_drive` gespeichert und erst beim Rückkehr zum StartScreen angezeigt |
| **Alternativen** | Sofort Dialog zeigen (unterbricht User-Session), Komplett im Hintergrund wechseln (User merkt nichts) |
| **Begründung** | Session nicht unterbrechen, User soll bewusst entscheiden. Event-Wechsel hat Priorität über FEXOSAFE-Dialog |

### Dual-USB-System: fexobox + FEXOSAFE

| | |
|---|---|
| **Kontext** | Bilder vom alten Event dürfen nicht auf den neuen Event-Stick, aber müssen gesichert werden |
| **Entscheidung** | Separater Sicherungs-Stick mit Volume-Label "FEXOSAFE" |
| **Alternativen** | Gleicher Stick mit Template-Erkennung (fragil), Netzwerk-Backup (offline nicht möglich) |
| **Begründung** | Klare Trennung: "fexobox" = Event-Stick, "FEXOSAFE" = Sicherungs-Stick. Erkennung über Volume-Label ist eindeutig und robust |

### Tkinter Toplevel-Dialoge: Niemals innerhalb destroy()-Callback erstellen

| | |
|---|---|
| **Kontext** | Service-PIN (6588) Eingabe im AdminDialog führte zum App-Freeze |
| **Entscheidung** | Dialog setzt nur ein Flag (`_open_service = True`) und zerstört sich via `self.destroy()`. Der aufrufende Code (nach `wait_window()`) prüft das Flag und erstellt den neuen Dialog |
| **Alternativen** | ServiceDialog direkt in `_open_service_menu()` erstellen (verursacht Freeze), `withdraw()` statt `destroy()` (Zombie-Window) |
| **Begründung** | Wenn Toplevel A sich `destroy()`t und Toplevel B innerhalb desselben Callbacks erstellt, kann B hinter dem Hauptfenster landen. Mit `grab_set()` wird dann das Hauptfenster blockiert → Freeze. Neuen Dialog immer NACH `wait_window()` im aufrufenden Code erstellen |

### Canon SELPHY Fehlererkennung: EnumWindows statt Spooler-API

| | |
|---|---|
| **Kontext** | Canon SELPHY CP1000 meldet Papier-/Kassettenfehler NICHT über win32print PRINTER_STATUS Flags |
| **Entscheidung** | Fehlererkennung über `EnumWindows` API: Canon-Treiber zeigt eigene Dialog-Fenster (Titel "Canon SELPHY CP1000 ..."), deren Child-Controls (Static Labels) den Fehlertext enthalten |
| **Alternativen** | win32print Spooler-Flags (Canon setzt diese nicht), EnumJobs pStatus (Canon befüllt das Feld nicht zuverlässig) |
| **Begründung** | Der Canon-Treiber nutzt seinen eigenen Dialog statt des Windows-Spooler-Mechanismus. EnumWindows + EnumChildWindows ist die einzige zuverlässige Methode, den Fehlertext abzugreifen |

### Canon SELPHY: SW_HIDE statt WM_CLOSE für Dialoge!

| | |
|---|---|
| **Kontext** | Canon SELPHY zeigt eigene Fehlerdialoge. `WM_CLOSE` schließt den Dialog, aber Canon erstellt ihn sofort neu → endloses Flackern jede Sekunde. Der User sieht beide Meldungen abwechselnd (Canon + unser Overlay) |
| **Entscheidung** | Canon-Dialoge per `ShowWindow(SW_HIDE)` verstecken statt `PostMessage(WM_CLOSE)`. SW_HIDE macht den Dialog unsichtbar ohne ihn zu zerstören. Canon erstellt keinen neuen. Unser TOPMOST-Overlay zeigt die eigene Meldung + Bestätigungs-Button |
| **Alternativen** | WM_CLOSE (Canon erstellt Dialog sofort neu → Flackern), SetWindowPos(HWND_BOTTOM) (funktioniert unzuverlässig mit Canon-Treiber) |
| **Merke** | NIEMALS `WM_CLOSE` auf Canon-Fehler-Dialoge! Immer `SW_HIDE`. Und periodisch wiederholen (alle 1s) falls Canon neue Dialoge erstellt |

### Canon SELPHY: Dialog-Text lesen per WM_GETTEXT (nicht GetWindowTextW!)

| | |
|---|---|
| **Kontext** | Canon SELPHY CP1000 Fehlerdialoge: `GetWindowTextW` auf Child-Controls liefert leeren Text. `EnumChildWindows` mit `GetWindowTextW` fand den Text "Kein Papier / Kassette falsch eingesetzt!" nicht. Fallback "DRUCKER PRÜFEN!" wurde als "other" klassifiziert → kein Overlay |
| **Entscheidung** | `SendMessageW(WM_GETTEXT)` statt `GetWindowTextW` verwenden. Alle Child-Controls enumerieren (nicht nur Static), den längsten Text als Fehlermeldung nehmen. Falls Text nicht lesbar: sicher als "KEIN PAPIER / KASSETTE!" (consumable) behandeln |
| **Merke** | Canon-Treiber-Dialoge nutzen vermutlich Owner-Draw oder spezielle Controls. `WM_GETTEXT` funktioniert bei mehr Control-Typen als `GetWindowTextW`. Immer ALLE Children lesen, nicht beim ersten Static stoppen |

### Canon SELPHY: Bestätigungs-Button statt Auto-Polling

| | |
|---|---|
| **Kontext** | Auto-Polling funktioniert nicht: SELPHY setzt keine Spooler-Flags, einziger Indikator ist der Canon-Dialog. Wenn wir den Dialog verstecken (SW_HIDE), können wir den Fehler nicht mehr erkennen → Overlay schließt sich sofort |
| **Entscheidung** | Kein Auto-Polling für Consumable-Fehler! Stattdessen Bestätigungs-Button ("PAPIER EINGELEGT" / "KASSETTE GEWECHSELT"). User klickt wenn Problem behoben. Dann: Canon-Dialog per WM_CLOSE schließen + Jobs purgen + 2s warten + Drucker prüfen. Falls noch Fehler: Button erneut zeigen |
| **Merke** | Für den SELPHY CP1000 ist der einzige zuverlässige "Fehler behoben"-Check: Canon-Dialoge schließen, Jobs purgen, warten, und dann schauen ob ein neuer Canon-Dialog erscheint. Das geht nur nach User-Bestätigung |

### Canon SELPHY: Software-Reset per 3-Stufen-Eskalation

| | |
|---|---|
| **Kontext** | Canon SELPHY hängt bei Papierstau. Bisher musste ein Knopf am Gerät gedrückt werden |
| **Entscheidung** | 3-Stufen-Reset: (1) Purge Jobs. (2) Spooler Restart. (3) `Disable-PnpDevice`/`Enable-PnpDevice` für echten USB-Reset (= wie Drucker aus/einstecken). Aggressiver als `pnputil /restart-device` |
| **Merke** | `pnputil /restart-device` hat das SELPHY gar nicht gefunden! PnP-FriendlyName enthält nicht immer "SELPHY". Breiter suchen nach `*Canon*` + `Class -eq 'Printer'`. Disable/Enable ist der "gold standard" laut Doku |

### PyInstaller: win32timezone für win32print.EnumJobs Level 2

| | |
|---|---|
| **Kontext** | `win32print.EnumJobs(hPrinter, 0, 10, 2)` (Level 2 = JOB_INFO_2) braucht intern `win32timezone` für DateTime-Felder. Fehlt das Modul im PyInstaller-Build, crasht der Job-Queue-Check → Druckerfehler werden NICHT erkannt |
| **Fix** | Level 1 (JOB_INFO_1) statt Level 2 verwenden. Level 1 hat `Status` + `pStatus` — reicht für Fehlererkennung. Zusätzlich `win32timezone` als `hiddenimport` im `.spec` File |
| **Merke** | pywin32 hat viele interne Abhängigkeiten die PyInstaller nicht automatisch findet. `win32timezone` ist eine davon. Bei `No module named 'win32timezone'` Fehlern: entweder als hiddenimport oder pywin32 Level reduzieren |

### Canon SELPHY: Fundamentale Limitation bei Status-Erkennung

| | |
|---|---|
| **Kontext** | Windows meldet IMMER Status 0 (ready) für USB-Drucker wenn kein Druckjob aktiv ist. Das ist ein dokumentiertes Microsoft-Verhalten (KB 160129). Der Canon-Treiber meldet Fehler NUR über sein eigenes Fenster, und NUR bei aktivem Druckjob |
| **Konsequenz** | Nach Jobs purgen + Canon-Dialog schließen gibt `get_error()` IMMER None zurück — auch wenn der SELPHY physisch "Kein Papier" anzeigt. Wir können den echten Drucker-Status NICHT lesen ohne einen Druckjob zu senden |
| **Workaround** | Bestätigungs-Button: User klickt "PAPIER EINGELEGT". Wir schließen Canon-Dialoge, purgen Jobs, warten 5-8s, prüfen ob Canon einen NEUEN Dialog erstellt. Falls kein Dialog: Overlay schließen, nächster Druckversuch zeigt ggf. erneut den Fehler |
| **Alternative (Zukunft)** | SELPHY hat 12-Byte Readback-Protokoll mit echten Fehler-Codes (Byte[2]: 0x02=Papier, 0x06=Tinte, 0x0B=Stau). Aber: braucht WinUSB/Zadig → bricht Canon-Druckertreiber. Oder: `DeviceIoControl(IOCTL_USBPRINT_VENDOR_GET_COMMAND)` — aber Canons Kommandos sind undokumentiert |

### ZIP-Validierung ist kritisch: Anwendungs-ZIPs von Template-ZIPs unterscheiden

| | |
|---|---|
| **Kontext** | Jedes ZIP auf USB wird als Template-Kandidat geprüft. Ohne Validierung kann `fexobooth.zip` (das Installationspaket mit 100+ MB, .exe, DLLs) als Template geladen werden → 30s Entpacken + 6889x6889 Logo als Overlay → 41s Freeze beim Compositing |
| **Entscheidung** | ZIPs mit `.exe`, `.dll` oder `_internal/` Ordner werden als Anwendungs-ZIPs erkannt und abgelehnt. Prüfung in `TemplateLoader` und `find_usb_template()` |
| **Merke** | Nie blind jedes ZIP als Template akzeptieren. Auf USB-Sticks können beliebige ZIPs liegen (Installer, Backups, etc.). Reject-Kriterien: `.exe`, `.dll`, `_internal/` im ZIP |

### PowerShell Output Encoding: UTF-8 explizit setzen

| | |
|---|---|
| **Kontext** | PowerShell gibt standardmäßig in der System-Codepage (cp1252 auf Deutsch-Windows) aus, nicht UTF-8. Auch mit `encoding="utf-8"` im subprocess kommt Müll raus (z.B. `durchgef�hrt` statt `durchgeführt`) |
| **Entscheidung** | `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;` am Anfang jedes PowerShell-Commands einfügen |
| **Merke** | `subprocess.run(..., encoding="utf-8")` reicht NICHT für PowerShell auf deutschem Windows. Die Console-Output-Encoding muss explizit auf UTF-8 gesetzt werden, sonst kommen Umlaute und Sonderzeichen kaputt an |

### USB-Export-Dialog darf nicht blockieren

| | |
|---|---|
| **Kontext** | Der Export-Dialog für unbekannte USB-Sticks nutzte `grab_set()` was die gesamte UI blockierte. Dazu wurden beim Start bereits vorhandene Wechseldatenträger (z.B. SD-Karten-Slot D:\) fälschlicherweise als "unbekannter Stick" erkannt |
| **Entscheidung** | Boot-Drives ignorieren + Grace Period + kein `grab_set()` |
| **Merke** | Export-Dialoge niemals mit `grab_set()` blockierend machen. Beim Start vorhandene Wechseldatenträger (SD-Karten-Slots etc.) müssen als Boot-Drives erfasst und ignoriert werden. Grace Period nach Boot verhindert Race Conditions |

### Video-Wiedergabe: VLC mit DXVA2 Hardware-Beschleunigung

| | |
|---|---|
| **Kontext** | Video-Wiedergabe auf schwacher Hardware (Atom CPU) |
| **Entscheidung** | VLC (python-vlc) mit DXVA2 Hardware-Beschleunigung |
| **Alternativen** | MSMF/OpenCV (UI-Freeze, eingeschränkte Codec-Unterstützung), FFmpeg (zusätzliche Dependency) |
| **Begründung** | VLC nutzt GPU-Beschleunigung (DXVA2), kein UI-Freeze, breite Codec-Unterstützung |

### GUI-Framework: CustomTkinter

| | |
|---|---|
| **Kontext** | Leichtgewichtiges GUI für schwache Hardware |
| **Entscheidung** | CustomTkinter |
| **Alternativen** | PyQt (zu schwer), Kivy (zu schwer), Standard Tkinter (hässlich) |
| **Begründung** | Modern aussehend, leichtgewichtig, einfache API |

### Galerie-Server: Flask

| | |
|---|---|
| **Kontext** | Lokaler Webserver für QR-Code Galerie |
| **Entscheidung** | Flask |
| **Alternativen** | FastAPI (overkill), http.server (zu primitiv) |
| **Begründung** | Leichtgewichtig (~20-30 MB RAM), einfach, bewährt |

### Persistenz: JSON-Cache statt Datenbank

| | |
|---|---|
| **Kontext** | Buchungsdaten und Settings speichern |
| **Entscheidung** | JSON-Dateien in .booking_cache/ |
| **Alternativen** | SQLite (overkill), Registry (Windows-spezifisch, unflexibel) |
| **Begründung** | Einfach, lesbar, portabel, keine zusätzliche Dependency |

---

## Lessons Learned

### Lange Kamera-Arbeit gehoert in einen eigenen PROZESS, nicht in einen Thread (20.08.2026)

| | |
|---|---|
| **Problem** | Der neue Knopf "Kamera-Messung" startete die Messung als Hintergrund-Thread in der laufenden App. Auf der Box fror daraufhin die KOMPLETTE Software ein, liess sich nicht mehr schliessen und musste hart ausgeschaltet werden. |
| **Beweis** | `fexobooth_20260820_090921.log` endet exakt nach der letzten Zeile vor dem ersten Kamerazugriff der Messung (`09:12:15.454 Kamera der App freigegeben`) — danach keine Zeile mehr, auch nicht vom UI-Hitch-Wachhund, und kein Eintrag in `absturz.log`. Also kein Absturz, sondern Stillstand. |
| **Ursache** | Zwei Effekte, die beide im Thread-Entwurf unvermeidbar sind: (1) Ein minutenlanger OpenCV-Kamerazugriff blockiert den Python-Prozess so, dass die Tk-Oberflaeche nicht mehr drankommt. (2) Die Messung hielt `camera_hardware_lock()` ueber ihre ganze Laufzeit — jeder andere Kamerazugriff der App haette minutenlang gewartet. |
| **Loesung** | Der Dialog startet die Messung als eigenen Windows-Prozess (`fexobooth.exe --kamera-test`) und pollt ihn per `after()`. Eigener Prozess = eigener Interpreter und eigene Sperren. |
| **Merke** | Als Einzelprogramm (`--kamera-test`) war derselbe Code unauffaellig — es gab ja keine Oberflaeche, die haette einfrieren koennen. **Code aus einem CLI-Werkzeug in eine laufende GUI zu uebernehmen ist kein Umzug, sondern eine neue Betriebsart.** Alles, was Sekunden bis Minuten am Stueck arbeitet und dabei Hardware anfasst, kommt in einen eigenen Prozess. |

### Abbrechen geht nur ueber die Prozessgrenze (20.08.2026)

| | |
|---|---|
| **Problem** | Christian musste die Box hart ausschalten, weil sich nichts mehr beenden liess. |
| **Ursache** | Ein blockierender `cv2`-Aufruf steckt im C-Code von OpenCV. Dorthin kommt weder ein Signal noch eine Exception — ein Thread laesst sich in Python **nicht** abbrechen, nur aufgeben. Aufgeben hilft aber nicht, wenn er die Kamera weiter besitzt. |
| **Loesung** | Als eigener Prozess ist `terminate()` (Windows: `TerminateProcess`) moeglich — das kann der Zielprozess nicht ignorieren. Gegenprobe mit einem Testprozess, der `SIGTERM` absichtlich ignoriert: trotzdem in 0,00 s beendet. |
| **Merke** | Wenn eine Aufgabe abbrechbar sein MUSS, entscheidet das die Architektur, nicht die Fehlerbehandlung. Thread = nicht abbrechbar. Prozess = abbrechbar. Diese Frage vor dem Bauen stellen. |

### Eine Messung ohne Zeitgrenze ist keine Messung (20.08.2026)

| | |
|---|---|
| **Problem** | Angekuendigt waren "ca. 2 Minuten", nach 5+ Minuten lief noch nichts fertig. |
| **Befund** | Ein gesunder Lauf kostet rechnerisch ~100 s (11 Kamera-Oeffnungen, 242 Leseversuche, 3,3 s feste Pausen). Aber: **kein einziger dieser ueber 240 Aufrufe hatte eine Zeitgrenze.** Antwortet die Kamera nicht, wartet die Messung endlos, statt den Schritt als fehlgeschlagen zu vermerken und weiterzumachen. Hauptverdacht: Media Foundation, das auf dem Entwickler-PC bei allen drei Aufloesungen "keine Bilder erhalten" lieferte — 110 Fehlversuche ohne Abbruch. |
| **Merke** | Bei Messwerkzeugen an echter Hardware gehoert zu jedem Schritt ein Zeitlimit UND ein fortlaufend geschriebenes Zwischenergebnis. Ein Bericht, der erst am Ende entsteht, macht jeden Abbruch zum Totalverlust — und ohne Lebenszeichen ist ein langsamer Lauf von einem haengenden nicht unterscheidbar. |

### `os._exit(0)` beendet KEINE Kindprozesse (20.08.2026)

| | |
|---|---|
| **Problem** | Nach „App beenden" im 3198-Menue blieb ein Prozess im Task-Manager stehen. |
| **Ursache** | `main.py` endet bewusst mit `os._exit(0)` (non-daemon Threads hielten die EXE sonst am Leben). Das beendet aber **nur den Python-Prozess**. Die unsichtbare `FexoNikonBridge.exe` ist ein eigenstaendiger Windows-Prozess und ueberlebt als Waise — und belegt weiter die Kamera, sodass der naechste Start daran scheitern kann. |
| **Loesung** | Kindprozesse explizit vor dem Ausstieg beenden (`shutdown_bridge()`), Waisen frueherer Abstuerze beim **Start** per Name wegraeumen. |
| **Merke** | Wer `os._exit()` benutzt, uebernimmt die Verantwortung fuer alle `subprocess.Popen`-Kinder selbst. Es gibt kein automatisches Aufraeumen — auch `atexit`-Handler laufen bei `os._exit()` **nicht**. |

### Zwei Wege zum selben Ziel driften auseinander (20.08.2026)

| | |
|---|---|
| **Problem** | Der Notausstieg Ctrl+Shift+Q gab die Kamera frei, der Beenden-Knopf im Service-Menue nicht — obwohl beide „die App beenden" sollten. |
| **Ursache** | Es waren zwei getrennte Methoden mit eigenem, aehnlichem Code. Als der Notausstieg um `camera_manager.release()` erweitert wurde, blieb der Knopf-Weg zurueck. Nach demselben Muster fehlten dort auch `grab_release()` und das Schliessen des Dialogs. |
| **Loesung** | Ein einziger Weg `PhotoboothApp.shutdown(grund)`; alle drei Aufrufer laufen hindurch. Der Grund kommt als Text ins Log, damit man im Feld-Log sieht, wer beendet hat. |
| **Merke** | Bei mehreren Wegen zum selben Systemzustand (beenden, zuruecksetzen, neu verbinden) **eine** gemeinsame Funktion bauen. Sonst wird jeder Fix nur an einem Weg angebracht und faellt Monate spaeter am anderen auf. |

### Beim Beenden darf nichts blockieren — `taskkill` braucht Sekunden (20.08.2026)

| | |
|---|---|
| **Problem** | Der erste Entwurf raeumte Kindprozesse mit `taskkill /IM ... /F` auf dem Beenden-Weg auf. Messung: **5,0 s** — auch wenn der Prozess gar nicht laeuft. Das lief auf dem Oberflaechen-Thread, die App waere beim Beenden sichtbar eingefroren. |
| **Ursache** | `taskkill` ist ein eigener Prozessstart. Ein `subprocess.run(..., timeout=5)` verdeckt das: Es wirft `TimeoutExpired`, die Ausnahme wird geschluckt — der Aufruf sieht „erfolgreich abgesichert" aus, kostet aber trotzdem die vollen 5 Sekunden. |
| **Loesung** | Auf dem Beenden-Weg nur der direkte Kill des eigenen Kind-Handles (`process.kill()`, sofort). `taskkill` laeuft nur noch beim **Start** in einem Daemon-Thread, fuer Waisen fremder Laeufe. |
| **Merke** | Auf Abbruch-/Beenden-Pfaden keine externen Kommandos starten. Ein `timeout=` macht einen blockierenden Aufruf nicht schnell, sondern begrenzt nur, wie lange er blockiert. Zeit messen statt annehmen. |

### Ein RLock laesst sich nicht aus dem eigenen Thread pruefen (20.08.2026)

| | |
|---|---|
| **Problem** | Der Test „laeuft die Kamera-Messung wirklich unter `camera_hardware_lock()`?" meldete **falsch** „nein". |
| **Ursache** | `camera_hardware_lock()` ist ein `threading.RLock` — **reentrant**. `acquire(blocking=False)` aus dem Thread, der die Sperre bereits haelt, ist per Definition erfolgreich. Der Test schloss daraus faelschlich, die Sperre sei frei. |
| **Loesung** | Aus einem **zweiten** Thread pruefen. Dort schlaegt `acquire(blocking=False)` fehl, solange die Sperre gehalten wird. |
| **Merke** | Aussagen ueber `RLock`-Besitz sind immer thread-relativ. Wer „ist gesperrt?" testen will, braucht dafuer einen fremden Thread — sonst testet man nur die Reentranz. |

### Der LiveView-Engpass ist die ANZEIGE, nicht die Kamera (19.08.2026)

- **Befund:** Der Gast sieht nicht die 8,5 Bilder/s aus dem Log, sondern nur **~4,7**.
  Beweis aus demselben Feld-Log (Box 044, dieselben 5 Sekunden):
  ```
  LIVEVIEW-PERF: 43 Frames in 5.0s (~8.6 fps)          <- der Worker rechnet
  LIVEVIEW-PERF: Anzeige (UI-Thread): 24x in 5.1s      <- das sieht der Gast = 4,7/s
  ```
  **45 % der berechneten Bilder erreichen den Bildschirm nie.**
- **Ursache** (`session.py:370`):
  ```python
  delay = max(self._frame_delay_ms, int(self._display_ms_ema * 3))
  self.after(min(delay, 250), self._update_live_view)
  ```
  Der UI-Takt ist absichtlich das **Dreifache** der Anzeigezeit, damit die Vorschau
  hoechstens ein Drittel des UI-Threads frisst (sonst leidet die Touch-Reaktion).
  Bei 56 ms Anzeigezeit sind das 168 ms Wartezeit — die echte Periode ist
  56 + 168 = 224 ms, also **4,4 Bilder/s als harte Obergrenze**.
- **Konsequenz — und das ist der entscheidende Punkt:** Eine schnellere Kamera,
  eine hoehere Aufloesung oder eine optimierte Bildaufbereitung aendern daran
  **NICHTS**. Solange die Anzeige 56 ms kostet, bleibt es bei ~4,5 Bildern/s.
  Wer den LiveView fluessiger machen will, muss an der ANZEIGE ansetzen
  (CTkImage-Erzeugung, Anzeigeflaeche), nicht an der Kamera.
- **Folgerung fuer einen dslrBooth-artigen Schieberegler:** Er muesste die
  **Anzeigegroesse** regeln, nicht die Kameraaufloesung. Die Anzeigekosten skalieren
  mit der Flaeche des angezeigten Bildes.
- **Merke:** Zwei Messwerte im selben Log, die nach demselben aussehen ("fps"),
  koennen voellig Verschiedenes bedeuten — Produktionsrate vs. Anzeigerate. Wir
  haben zwei Runden lang die falsche Zahl optimiert.

### GELOEST (2.4.43): Vorschau ist 4:3, das Foto ist 16:9 — der Gast richtet sich nach dem falschen Bild

**Der Befund (bis 2.4.42):**
- `live_view_resolution` ist **eine einzige Zahl**; die Hoehe wurde an drei Stellen
  fest als `int(live_res * 0.75)` gerechnet (`app.py`, `session.py`,
  `system_test.py`). Die Vorschau war damit IMMER 4:3 (z.B. 640x480), das Foto
  aber 16:9 (1920x1080).
- Zwei Folgen:
  1. **1080p war gar nicht einstellbar** — `live_view_resolution: 1920` ergibt
     1920x1440, nicht 1920x1080.
  2. Der **Bildausschnitt** der Vorschau entsprach nicht dem des Fotos. Wer sich
     nach der Vorschau ausrichtete, sah im Foto etwas anderes.
- `defaults.py` sagt 640, alle drei Aufrufstellen fielen aber auf **480** zurueck —
  Boxen ohne diesen Konfigschluessel laufen mit 480x360.

**Die Loesung (2.4.43, Etappe 2):** Die Frage „in welcher Aufloesung oeffnen wir?"
beantwortet jetzt genau EINE Funktion: `vorschau_aufloesung(config)` in
`src/config/config.py`. Klassisch liefert sie unveraendert `(live_res, live_res*0,75)`;
mit dem Schalter `camera_dauerbetrieb_hd` liefert sie die **Foto-Aufloesung selbst**
(hart gedeckelt auf 1920x1080, weil die Foto-Aufloesung im Admin-Menue frei
eintippbar ist). Damit deckt sich der Vorschau-Ausschnitt exakt mit dem Foto.

**Durchgerechnet fuer das echte Template (1800x1200, Faecher 3:2):**

| | Beschnitt Vorschau | Beschnitt gedrucktes Foto |
|---|---|---|
| klassisch (4:3-Vorschau) | 10,7 % der **Hoehe** | 15,6 % der **Breite** |
| Dauerbetrieb (16:9-Vorschau) | 15,6 % der **Breite** | 15,6 % der **Breite** |

**Merke:** Wenn dieselbe Rechnung an drei Stellen steht, ist sie nicht „dupliziert",
sondern eine **offene Frage ohne zustaendige Stelle**. Es faellt erst auf, wenn man
die Antwort aendern will — dann laeuft dieselbe Box je nach Weg (mit Intro-Video,
ohne, im Selbsttest) in unterschiedlichen Zustaenden und der Fehler ist nicht mehr
reproduzierbar.

### `initialize()` ignoriert width/height, wenn die Kamera schon offen ist (2.4.43)

- `WebcamManager.initialize()` steigt in der zweiten Zeile aus:
  `if self._is_initialized and self.camera_index == camera_index: return True`.
  **Die angeforderte Aufloesung wird dabei nicht einmal angeschaut.**
- Das ist die Stolperfalle fuer jeden Schalter, der die Oeffnungs-Aufloesung
  aendert: Ein zweiter `initialize()`-Aufruf mit neuen Massen tut **nichts**. Der
  Schalter waere scheinbar wirkungslos — und man sucht einen Fehler, den es nicht
  gibt.
- Deshalb ruft `_sync_dauerbetrieb_hd()` in `app.py` bei einer Aenderung des
  Schalters `release()` auf. Bewusst nur freigeben, **nicht** neu oeffnen: Das
  Oeffnen laeuft auf dem Tk-Thread und wuerde die Oberflaeche direkt nach dem
  Schliessen des Admin-Menues sekundenlang einfrieren. Das naechste
  `_pre_init_camera` (waehrend des Intro-Videos) holt es nach.
- **Merke:** Eine `initialize()`-Funktion mit Frueh-Ausstieg ist ein stiller
  Vertrag: „Parameter gelten nur beim ERSTEN Aufruf." Wer spaeter einen Parameter
  zur Laufzeit umstellbar macht, muss den Ausstieg mitlesen.

### Kamera-Backend: DirectShow war nie gemessen worden (Verdacht, 2026-08-19)

- **Ausgangslage:** In `webcam.py` steht `backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]`.
  DirectShow wird zuerst probiert, funktioniert immer — und damit hat nie jemand
  gemessen, ob Media Foundation schneller waere. Die Feld-Logs zeigen durchgaengig
  `Kamera 0 geoeffnet mit Backend 700` (= CAP_DSHOW).
- **Messung am Entwickler-PC (gleiche Kamera, gleicher Rechner):**

  | Backend | 640x480 | 1920x1080 | Dekodieren bei 1080p |
  |---|---|---|---|
  | DirectShow | 14,3 Bilder/s | **5,0 Bilder/s** | 200 ms |
  | Media Foundation | 30,6 Bilder/s | **30,5 Bilder/s** | **9 ms** |

  Ausserdem: Aufloesungswechsel per DirectShow = 1861 ms hoch + 460 ms erstes Bild
  = 2,3 s (deckt sich mit den Feld-Logs der Boxen: ~1,7-1,9 s).
- **Konsequenz, falls sich das auf der Box bestaetigt:** Nicht die Aufloesung ist das
  Problem, sondern der Treiberpfad. Mit MSMF koennte die Kamera dauerhaft in 1080p
  laufen, das Umschalten pro Foto entfiele — und damit auch die Luecke zwischen
  Blitz und Belichtung.
- **⚠️ RISIKO, das vorher geklaert werden muss:** Die Kamera-Erkennung dieses Projekts
  ist auf die DirectShow-Reihenfolge gebaut (siehe Eintrag "DirectShow-Enumeration:
  PnP-Reihenfolge != OpenCV-Reihenfolge"). Unter MSMF kann derselbe Index eine ANDERE
  Kamera treffen — im schlimmsten Fall die interne statt der Logitech. Ein Wechsel
  des Backends erfordert deshalb zwingend, die Zuordnung Index->Geraet neu abzusichern.
- **Merke:** Wenn eine Bibliothek mehrere Backends anbietet und der Code das erste
  nimmt, das funktioniert, ist die Wahl NICHT begruendet — sie ist zufaellig. Einmal
  messen kostet eine Stunde und kann ein Jahr Symptombekaempfung ersparen.
- **⚠️ EINSCHRAENKUNG:** Am Entwickler-PC haengt eine generische "USB 2.0 Camera",
  KEINE C922. Der gemessene Backend-Unterschied ist auf diesem Geraet real, aber
  fuer die Logitech-Kameras der Flotte NICHT bewiesen.
- **Noch offen:** Alles oben ist am Entwickler-PC gemessen, nicht auf einer Box mit
  Atom-CPU und C922. Dafuer gibt es seit 2.4.34 `fexobooth.exe --kamera-test`.
- **NACHTRAG 2.4.43:** Die Messung auf der echten Box liegt inzwischen vor und
  entlastet DirectShow deutlich: **13,9 Bilder/s bei 1080p MJPG, davon 0 ms
  Wartezeit** (die 71,9 ms pro Bild sind reines MJPG-Entpacken auf dem Atom) —
  nicht die 5,0 Bilder/s vom Entwickler-PC. Der Dauerbetrieb (Etappe 2) ist damit
  **ohne** Backend-Wechsel tragfaehig und aendert `backends` bewusst NICHT.
  Sollte der Dauerbetrieb auf der Testbox an der Vorschau-Geschwindigkeit
  scheitern, ist MSMF die naechste Frage — nicht das Zurueckdrehen von Etappe 2.

### GELOEST: Firmen-WLAN + Router — warum sich Boxen nicht im Dashboard meldeten (19.08.2026)

**Das war die eigentliche Hauptursache.** Drei Probleme hatten sich gegenseitig versteckt; dieses
hier war das groesste und lag NICHT in unserer Software.

#### Der Befund

Der DHCP-Adressbereich des Firmen-Routers umfasste **51 Adressen** (`192.168.2.200`–`.250`)
bei **200+ Fotoboxen** plus PCs, Telefonen, Access-Points und einem Haufen Smart-Home-Geraeten
(Meross-Steckdosen, Netatmo, Amazon, Apple, Netgear-Repeater). Dazu eine **Lease Time von
120 Minuten**: Eine Box, die 5 Minuten lief, blockierte ihre Adresse zwei Stunden lang.

Der Beweis stand in der Router-Oberflaeche selbst: Unter *IP/MAC-Bindung* zeigte die Liste
**"Summe der Objekte: 53"** — 51 Adressen im Haupt-Pool + 2 im Gaeste-Pool. Der Pool war zu
**100 %** belegt. Boxen, die danach kamen, bekamen nichts und landeten bei `169.254.x.x` (APIPA).

Nach aussen sah das aus wie "die Box verbindet sich nicht": Windows meldete
**"fexon WLAN — Kein Internet, gesichert"**, obwohl die Funkverbindung stand.

#### Der Router

| Feld | Wert |
|---|---|
| Geraet | **Telekom Digitalisierungsbox Premium** (= umgelabelte **bintec elmeg be.IP plus**) |
| Firmware | 11.01.03.115 (2023/09/13) |
| Betriebsmodus | PBX (Router + Telefonanlage) |
| Router-IP | `192.168.2.1` |
| LAN-Netz | `192.168.2.0/24` |
| Zugang | Weboberflaeche des Routers, Reiter *Internet & Netzwerk* |

**Netz-Aufbau (wichtig):**
- `br0` = Haupt-Bridge → **LAN UND das fexon WLAN haengen gemeinsam drin**. Die Boxen holen
  ihre Adressen also aus demselben Topf wie die Buero-PCs.
- `br0-1` = Gaeste-Bridge → Pool `fexon Gast-WLAN` (`192.168.3.251`–`.252`, nur **2** Adressen)
- Ausserhalb des Pools war fast alles frei: nur `192.168.2.1` (Router) und `192.168.2.116`
  (ein Geraet mit fester IP) waren belegt.

#### Die Aenderung (19.08.2026)

| Einstellung | vorher | nachher |
|---|---|---|
| IP-Adressbereich (Pool "DHCP Adressbereich") | `192.168.2.200` – `.250` (51) | **`192.168.2.130` – `.250` (121)** |
| Lease Time (Schnittstelle `br0`) | 120 Min. | **30 Min.** |

Start bewusst bei `.130` und nicht tiefer: Der Netzwerk-Scan sieht nur Geraete, die GERADE
eingeschaltet sind. `.2`–`.129` bleibt als Reserve fuer feste Adressen (Drucker/NAS/Server, die
zufaellig aus waren), damit es spaeter keine Adresskonflikte gibt.

#### Klickpfad im Router (unbedingt merken — man findet es sonst nicht)

Die DHCP-Einstellungen sind in der Standard-Oberflaeche **unsichtbar**. Erst die
"Navigation fuer Experten" blendet den vollen bintec-Menuebaum links ein:

1. **Home** → unten rechts **"Mehr anzeigen"** → **Globale Einstellungen**
2. Auf der Seite unten rechts nochmal **"Mehr anzeigen"** → Abschnitt **GUI-Einstellungen**
3. **"Navigation fuer Experten"** auf *Aktiviert* → **OK**
   ⚠️ Gilt **nur fuer die laufende Browser-Sitzung** — nach dem Ausloggen wieder weg.
   ⚠️ Erscheint nur bei **breitem Browserfenster** ("nur auf grossen Bildschirmen").
4. Links im Baum: **Lokale Dienste → DHCP-Server**
   - Reiter **IP-POOL-KONFIGURATION** → Adressbereich
   - Reiter **DHCP-KONFIGURATION** → Lease Time (Stift-Symbol beim Eintrag `br0`)
   - Reiter **IP/MAC-BINDUNG** → aktuelle Leases + "Summe der Objekte" (= Fuellstand!)
5. **Zum Schluss oben rechts "Konfiguration speichern"** — sonst ist beim naechsten
   Router-Neustart alles weg (Warndreieck neben dem Link = ungespeicherte Aenderungen).

#### NICHT anfassen

In der DHCP-Konfiguration von `br0` stehen Optionen, die andere Systeme brauchen:
`Zeitserver 192.168.2.1`, `CAPWAP Controller 192.168.2.1` (steuert die bintec-Access-Points),
`URL (Provisionierungsserver) http://192.168.2.1/eg_prov` und Hersteller-Option 43
"Maxwell / Gigaset-Telefone". Finger weg — das hat mit DHCP-Adressen nichts zu tun.

#### Wie man so etwas kuenftig in 2 Minuten pruefen kann

Von einem PC im selben Netz (PowerShell) — findet ALLE belegten Adressen, auch mit fester IP:

```powershell
$p = 1..199 | ForEach-Object { (New-Object System.Net.NetworkInformation.Ping).SendPingAsync("192.168.2.$_", 400) }
[Threading.Tasks.Task]::WaitAll($p) | Out-Null
$p | Where-Object { $_.Result.Status -eq 'Success' } | ForEach-Object { $_.Result.Address.ToString() }
arp -a | Select-String "192\.168\.2\."
```

#### Merke

1. **"Die Box meldet sich nicht" heisst nicht, dass die Box schuld ist.** Wir haben zwei
   Software-Runden (Hotspot, Kamera-Absturz) gebraucht, bis die Box ueberhaupt sagen KONNTE,
   dass sie keine IP-Adresse bekommt. Erst `netzwerk.log` mit der Zeile
   `Eig. Hotspot: aus` + `KEINE IP-ADRESSE` hat den Router ueberfuehrt.
2. **APIPA (`169.254.x.x`) ist immer ein DHCP-Problem** — nie ein WLAN-Passwort- oder
   Profil-Problem. Windows meldet trotzdem "verbunden".
3. **Adress-Pools skalieren mit der Flotte.** Bei 200+ Geraeten, die durch die Werkstatt
   rotieren, ist der Werks-Standardbereich von ~50 Adressen viel zu klein. Faustregel:
   Pool >= dreifache Zahl der Geraete, die an einem Tag durchlaufen; Lease kurz halten
   (30 Min.), damit Adressen schnell zurueckkommen.
4. **Fuellstand steht direkt im Router**: *IP/MAC-Bindung* → "Summe der Objekte" mit der
   Poolgroesse vergleichen. Gleich = voll = Problem.

### @staticmethod umgeht jede Instanz-Sperre — bei Hardware ist das toedlich (2.4.31)

- **Problem:** `WebcamManager` hatte `self._camera_lock` und benutzte es brav in allen
  Instanz-Methoden. `list_cameras()` ist aber eine `@staticmethod` — sie hat gar kein `self`
  und lief damit voellig ungeschuetzt. Zwei Threads (Kamera-Auto-Auswahl beim Start und der
  Kamera-Waechter) oeffneten deshalb gleichzeitig dieselbe DirectShow-Kamera.
- **Folge:** Heap-Zerstoerung im Prozess (`0xc0000374`), Windows meldet den Absturz erst
  spaeter und an ganz anderer Stelle: `ntdll.dll` / `0xc0000005`. Aus dem Windows-Ereignis-
  protokoll allein war die Ursache NICHT ableitbar — es zeigte nur den Ort des Zusammenbruchs,
  nicht den Verursacher.
- **Was es geloest hat:** `faulthandler` (2.4.30). Er schreibt im Moment des Absturzes den
  Python-Stack ALLER Threads. Erst dadurch war sichtbar, dass zwei Threads gleichzeitig in
  `cv2.VideoCapture(...)` standen. Kosten zur Laufzeit: praktisch null.
- **Merke:**
  1. Sperren fuer Hardware gehoeren auf **Modul-/Klassenebene**, nie an die Instanz — sonst
     reicht eine einzige `@staticmethod`, um alles auszuhebeln.
  2. Native Abstuerze (`0xc0000005`, `0xc0000374`) in Python-Apps IMMER mit `faulthandler`
     absichern. Ohne ihn sucht man im Windows-Ereignisprotokoll nach einer DLL, die nur das
     Opfer ist.
  3. Solche Fehler zeigen sich im Developer-Mode oft NICHT — anderes Timing, andere Last.
     „Nicht reproduzierbar" heisst bei Threads: „das Zeitfenster war zufaellig zu klein".

### BEWIESEN: Der eigene Hotspot kostet die Box die IP-Adresse im Firmen-WLAN (2.4.29)

- **Beweis** (Box 056, Log `fexobooth_20260818_114932.log` + Server-Gegenprobe):
  ```
  11:49:57 | KEINE brauchbare IP-Adresse — starte Reparatur
  11:49:57 | Stufe 1 — eigener Hotspot laeuft (192.168.137.x) und wird abgeschaltet
  11:50:00 | Hotspot gestoppt
  11:50:08 | Nach Hotspot-Aus kam die IP-Adresse (Stufe 1) ✓   → 192.168.2.208
  11:50:08 | Monitoring: Version 2.4.29 fuer Box-ID 056 gemeldet
  ```
  Dashboard-DB (`photoboxes`, Box S1116056): `software_version = 2.4.29`,
  `software_reported_at` aktuell, Payload mit `ssid = "fexon WLAN"`. Die Meldung kam also
  wirklich an — nicht nur lokal „gruen".
- **Mechanik:** Die Box hat eine WLAN-Karte. Laeuft darauf der Windows-Hotspot (ICS,
  `192.168.137.1`), bekommt der Client-Teil keine DHCP-Antwort mehr → nur noch APIPA
  (`169.254.x.x`). Windows meldet trotzdem „verbunden".
- **Wichtig:** Der Hotspot laeuft schon AB DEM BOOT (die Adresse steht im Log, bevor die App
  ihn ueberhaupt anfasst). Die App kann ihn deshalb nur abschalten, nicht verhindern. Die
  saubere Loesung waere, ihn auf betroffenen Boxen gar nicht erst automatisch starten zu lassen.
- **Merke:** „STA + AP gleichzeitig" ist eine Treiber-/Chip-Eigenschaft — sie funktioniert auf
  einem Teil der Flotte und auf dem anderen nicht. Das erklaert, warum es immer nur EINIGE Boxen
  traf und die Fehlersuche jahrelang im Kreis lief.

### Windows-Tethering: Ein gespeichertes WLAN-Profil ist KEIN Connection Profile (2.4.27)

- **Annahme (falsch):** Ein angelegtes, neutrales WLAN-Profil (`FexoBoothDummy`) könne als Anker
  für `NetworkOperatorTetheringManager.CreateFromConnectionProfile()` dienen und so verhindern,
  dass der Hotspot über die Firmen-Verbindung aufgezogen wird.
- **Realität (Feldtest 18.08., Box 200):** `GetConnectionProfiles()` liefert nur **tatsächliche
  Verbindungen**, keine gespeicherten WLAN-Profile. Das Dummy-Profil wurde sauber angelegt und
  tauchte trotzdem nie in der Liste auf. Auf einer Box mit nur einer WLAN-Karte, die im
  Firmen-WLAN hängt, bleibt `fexon WLAN` deshalb zwangsläufig der einzige mögliche Anker.
- **Konsequenz:** Der Ausschluss greift nur, wenn es eine zweite echte Verbindung gibt (z.B. LAN).
  Wirksam gegen „verbunden ohne IP" ist damit die **Reihenfolge** (erst Dashboard-Meldung und
  Update, dann Hotspot) — nicht der Anker-Tausch. Das Dummy-Profil bleibt trotzdem sinnvoll: auf
  frisch geklonten Tablets mit NULL Profilen findet die Tethering-API sonst gar nichts.
- **Merke:** Bei Windows-Runtime-APIs nie von „Profil gespeichert" auf „Profil nutzbar" schließen —
  erst im Log gegenprüfen, WELCHER Anker tatsächlich genommen wurde. Genau diese eine Log-Zeile
  (`Tethering-Anker = Profil '...'`) hat die falsche Annahme in einem einzigen Testlauf aufgedeckt.

### Doppelte geschweifte Klammern in PowerShell-Strings = stiller Blindgänger (2.4.27)

- **Problem:** In `src/gallery/hotspot.py` standen die PowerShell-Befehle mit doppelten Klammern
  (`if (...) {{ ... }}`) — Rest einer früheren `.format()`-Nutzung, die entfernt wurde, ohne die
  Klammern zurückzubauen. PowerShell versteht `{{ ... }}` aber als „Block, der einen Script-Block
  ENTHÄLT": Der innere Teil wird **nie ausgeführt**, sondern nur als Text ausgegeben. Eine
  Funktion mit doppeltem Klammerpaar liefert `ScriptBlock` statt eines Ergebnisses, ein
  `exit 1` im Fehlerzweig feuert nie.
- **Warum es so lange unentdeckt blieb:** Das Script endete mit Exit-Code 0 und gab Script-Text
  aus. Die Python-Auswertung lautete `success and "Error" not in output and output != "NO_PROFILE"`
  — also „alles, was kein bekannter Fehler ist, gilt als Erfolg". Ergebnis: Jahrelang
  „Hotspot erfolgreich gestartet (Tethering)" im Log, obwohl nichts passiert ist.
- **Lösung:** Klammern einfach schreiben (die Scripts werden nicht mehr `.format()`ed);
  Platzhalter werden per `.replace("__EXCLUDE_SSID__", ...)` ersetzt, damit die Falle nicht
  zurückkommt. Die Auswertung akzeptiert nur noch klar definierte Rückgaben (`STATUS=Success`,
  `ALREADY_ON`) — alles andere ist ein Fehler.
- **Merke:** (1) Externe Scripts (PowerShell/Batch/SQL) niemals mit `.format()` bauen — ihre
  Syntax nutzt selbst geschweifte Klammern. (2) Ergebnisse von Fremdprozessen per **Positivliste**
  auswerten („nur DAS ist Erfolg"), nie per Negativliste („alles außer Fehler ist Erfolg") —
  sonst wird jede unerwartete Ausgabe zum stillen Erfolg. (3) Verdacht auf so einen Blindgänger
  lässt sich in 10 Sekunden prüfen: Script ausführen und die Rückgabe ansehen.

### „Verbunden" ist keine Aussage über Netz — immer die IP-Adresse prüfen (2.4.27)

- **Problem:** Box 200 war laut `netsh wlan show interfaces` mit `fexon WLAN` verbunden, hatte
  aber nur `169.254.183.239` (APIPA = der Router hat KEINE Adresse vergeben) und `192.168.137.1`
  (den eigenen Hotspot). Jede Namensauflösung scheiterte (`getaddrinfo failed`). Die
  Selbstheilung aus 2.4.22 meldete trotzdem `already_connected` und tat nichts — sie schaute nur
  auf den Netzwerk-NAMEN.
- **Ursache dahinter:** Der Windows-Hotspot (ICS, `192.168.137.1`) belegt dieselbe WLAN-Karte wie
  die Firmen-Verbindung. Wird das Tethering über das Firmen-Profil aufgezogen, verliert die Box
  ihre DHCP-Adresse. Trifft nur einen Teil der Flotte, weil es vom WLAN-Chip abhängt, ob er
  gleichzeitig Client UND Access Point sein kann.
- **Lösung (2.4.27):** `src/utils/network_diag.py` bewertet IP-Adressen ehrlich — `127.*`,
  `169.254.*` (APIPA) und `192.168.137.*` (eigener Hotspot) zählen NICHT als Netz. Selbstheilung
  und Monitoring prüfen das vor jedem Melden; Reparatur in 3 Stufen (neue Adresse anfordern →
  neu verbinden → Hotspot abschalten).
- **Merke:** Bei Netzwerk-Diagnose gilt die Reihenfolge **IP-Adresse → Router-Ping → DNS →
  Zielserver**. Nur so ist unterscheidbar, ob der Router nichts vergibt, die Funkverbindung nur
  auf dem Papier steht oder wirklich das Ziel down ist. Genau diese Kette schreibt die
  NETZ-BILANZ ins Log — inklusive Klartext-Urteil, damit ein nicht wirkender Fix auffällt,
  ohne dass jemand an die Box muss.

### Exportierte WLAN-Profile sind maschinengebunden — Profile immer mit Klartext-Schlüssel selbst erzeugen

- **Problem:** 47 Flotten-Boxen buchten sich nicht ins Firmen-WLAN ein. Das Mitarbeiter-Fix-Skript importierte eine per `netsh wlan export` erzeugte Profil-XML — deren `keyMaterial` ist aber DPAPI-verschlüsselt und nur auf Maschinen mit identischem Schlüsselmaterial (= identisches Klon-Image) entschlüsselbar. Auf Boxen mit anderem Image-Stand griff der Fix nicht → „weitgehend" statt vollständig.
- **Kernursache der Anmelde-Probleme selbst:** MAC-Randomisierung an (Router/DHCP verweigert wechselnde Geräte-Adressen) und/oder Auto-Verbinden aus bzw. korrupte Profile.
- **Lösung (2.4.22):** Profil-XML zur Laufzeit mit `protected=false` + Klartext-Passphrase generieren (`src/utils/company_wlan.py`) — funktioniert auf jeder Box. Sicherer Automatik-Auslöser: „SSID im Scan sichtbar, aber nicht verbunden" (beim Kunden nie sichtbar → feuert dort nie). Sprachunabhängiges netsh-Parsing: die `SSID :`-Zeile in `show interfaces` existiert nur bei bestehender Verbindung — nie auf lokalisierte Statustexte („Verbunden") matchen.
- **Merke:** Nach `netsh wlan delete profile name=*` SOFORT wieder ein Profil anlegen — der Gäste-Hotspot (Tethering-API) braucht mindestens ein gespeichertes WLAN-Profil. Und: Installer-Postinstall-Optionen mit `unchecked`-Flag werden in der Praxis nie ausgeführt — Pflicht-Schritte gehören als [Run]-Eintrag ohne Checkbox in den Installer.

### Daten-Pfade NIE relativ zu __file__ ableiten — im PyInstaller-Build landet das in _internal (Datenverlust!)

- **Problem:** `local.py` bildete `BASE_PATH = Path(__file__).parent...` → im Build lag `BILDER` unter `_internal\BILDER`. Das Update-BAT ersetzt `_internal` atomar → **jedes OTA-Update löschte alle Fotos** (Feld-Befund Christian 2026-08-07). Der „BILDER/ wird geschützt"-Kommentar im BAT stimmte nur für den Install-Root.
- **Lösung:** Nutzdaten-Pfade wie `config.py` auflösen: `sys.frozen` → `Path(sys.executable).parent`, sonst Repo-Root. Plus Einmal-Migration alter Bestände und BAT-Sicherheitsnetz.
- **Merke:** Bei PyInstaller gilt: `__file__` = ersetzbarer Programmcode (`_internal`), `sys.executable` = Installationsort. ALLE Verzeichnisse mit Nutzdaten (Bilder, Statistiken, Caches) gehören neben die EXE oder nach ProgramData — und jeder „wird geschützt"-Claim im Update-Skript muss gegen die ECHTEN Laufzeitpfade (Log-Zeile!) geprüft werden, nicht gegen die Ordnernamen im Repo.

### Periodische Status-Checks (Kamera/Geräte) gehören NIE auf den UI-Thread

- **Problem:** `_check_camera_status` lief alle 15 s auf dem Tk-Thread. Ohne Kamera: PowerShell-Geräte-Enumeration mit 10+5 s Timeout → **16,5 s eingefrorene Oberfläche** beim Boxstart (Miix-Log 2026-08-07). Mit Kamera: `cv2.VideoCapture`-Testöffnung → ~500 ms Hänger alle 15 s im Leerlauf.
- **Ursache:** Auf dem Dev-PC sind PowerShell/Kamera-Öffnung schnell — auf dem Miix (Atom, kalter PS-Start, Defender) laufen dieselben Aufrufe in Timeouts. UI-Thread-Blockaden skalieren mit der SCHLECHTESTEN Hardware der Flotte.
- **Lösung:** Probe im Daemon-Thread, Ergebnis per `after(0)` zurück; probing nur auf Start-Screen + Kamera nicht initialisiert (verhindert EDSDK-/DirectShow-Kollision mit Session-Start); `_camera_check_running`-Flag gegen Parallel-Probes.
- **Merke:** Jeder wiederkehrende Check, der Subprozesse startet oder Geräte öffnet, ist ein UI-Freeze-Kandidat — im Zweifel Thread + after(0)-Callback. Und: Der UI-HITCH-Monitor + SYSTEM-LAST-Schnappschuss machen solche Verursacher im Feld-Log sofort sichtbar.

### ctypes: GetCurrentProcess-Pseudo-Handle (-1) nicht ohne argtypes an SetPriorityClass geben

- **Problem:** `SetPriorityClass(GetCurrentProcess(), ...)` via ctypes gab im Feld 0 zurück (Log 2026-08-07) — der -1-Pseudo-Handle wird ohne argtypes als 32-Bit-Wert übergeben und ist auf 64-Bit dann kein gültiger Handle.
- **Lösung:** `psutil.Process().nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)` — psutil ist ohnehin Abhängigkeit und macht das Handle-Handling korrekt (verifiziert: nice=32768).
- **Merke:** Windows-API über ctypes immer mit `argtypes`/`restype` deklarieren oder gleich psutil/pywin32 nutzen; „Rückgabewert 0 ohne Exception" heißt bei ctypes oft stille Parameter-Verstümmelung.

### Kamera-Manager nach JEDEM Apply-/Reload-Pfad synchronisieren — sonst läuft die Session auf dem falschen Backend

| | |
|---|---|
| **Problem** | Beim Nikon-Port kann sich `camera_type` an mehreren Stellen ändern (Admin-Speichern, Event-Wechsel, App-Upload-Reload, **Kundenmenü PIN 2015 „Settings neu laden"**, Service-Reload). Wird der live gehaltene `self.camera_manager` danach nicht neu gebaut, fährt die nächste Session auf dem alten Backend (z. B. noch `WebcamManager`, obwohl `camera_type` jetzt `nikon` ist), und `_check_camera_status` prüft das falsche Objekt. |
| **Ursache** | `apply_settings_to_config` ändert nur die Config, nicht den Manager. Es gibt **fünf** Apply-/Reload-Pfade; beim ersten Wurf fehlte der Sync ausgerechnet im PIN-2015-Kundenreload (`admin.py do_reload`) — vom Multi-Agent-Review gefunden. |
| **Lösung** | Zentrale Methode `_sync_camera_manager_with_config()` (rebaut nur bei Typ-Wechsel, sonst nur `update_config`) **an allen fünf** Pfaden aufrufen. Wichtig: `do_reload`/Service-Reload laufen auf einem **Worker-Thread** → den Sync per `self.after(0, ...)` auf den **Main-Thread** marshallen, weil er `release()`/Manager-Neubau macht. |
| **Merke** | Wenn ein abgeleiteter Laufzeit-Zustand (hier: der Manager) aus einem Config-Wert gebaut wird, muss **jeder** Pfad, der diesen Wert ändern kann, den Zustand nachziehen — am besten über **eine** idempotente Sync-Funktion statt verteilter Rebuild-Logik. Solche „eine Stelle vergessen"-Lücken findet ein adversariales Review zuverlässig (alle Schreibstellen auflisten und gegen die Sync-Aufrufe abgleichen). |

### Defensiver Import: ein optionales Kamera-Backend darf beim Import-Fehler NICHT die ganze Flotte lahmlegen

| | |
|---|---|
| **Problem** | `from .nikon import NikonCameraManager` stand zunächst **ungeschützt** am Modulkopf von `src/camera/__init__.py`. Ein künftiger Import-Fehler in `nikon.py` (z. B. jemand fügt `import requests` hinzu) hätte `import src.camera` und damit `app.py:18` zum Absturz gebracht — und damit **alle** Boxen, auch reine Webcam-/Canon-Geräte, die Nikon nie nutzen. |
| **Ursache** | Canon ist bewusst in `try/except` gekapselt (genau für diese Isolation); Nikon war es anfangs nicht — Asymmetrie. |
| **Lösung** | Nikon-Import symmetrisch zu Canon in `try/except`, `NIKON_AVAILABLE` aus dem Ergebnis ableiten, Factory mit `NikonCameraManager is not None` absichern → bei kaputtem Import sauberer Fallback auf Webcam statt Komplettausfall. |
| **Merke** | Optionale/zusätzliche Backends, die am Paket-Top-Level importiert werden, **immer** defensiv importieren — der Import-Graph eines Pakets ist eine geteilte Abhängigkeit. Eine Isolations-Maßnahme (try/except) ist nur so gut wie ihre Symmetrie: ein einziger ungeschützter Geschwister-Import hebt sie auf. |

### digiCamControl/HTTP-Adapter: blockierende `urlopen`-Timeouts gehören NICHT auf den UI-Thread

| | |
|---|---|
| **Problem** | `NikonCameraManager.initialize()` kann digiCamControl auto-starten (`CameraControl.exe`) und pollt dann bis zu `startup_timeout_seconds` (Default 15 s) + LiveView-Warten → bis ~24 s. Wird `initialize()` synchron auf dem Tk-UI-Thread aufgerufen (Pre-Init/Session-Start), friert die Kiosk-UI auf schwacher Hardware (4 GB Miix) komplett ein. Auch `_check_camera_status` (UI-Thread) kann im Nikon-Idle-Zweig ~1.5 s in `list_cameras()` (urlopen) hängen, wenn der DCC-Server nicht antwortet. |
| **Ursache** | HTTP-Calls haben echte Timeouts; anders als die lokale EDSDK-Enumeration (quasi instant) blockiert ein TCP-`urlopen` zu einem (noch) nicht laufenden `127.0.0.1:5513` bis zum Timeout. |
| **Status/Lösung** | **Entschärft per Auto-Start-Warmup:** Beim App-Start (und bei Wechsel auf Nikon) startet `_warmup_nikon_async()` digiCamControl in einem **Daemon-Thread** vor (`NikonCameraManager.ensure_server_running()`), off dem UI-/Startup-Thread. Damit läuft der Webserver beim ersten Capture i.d.R. schon → `initialize()` trifft den schnellen Pfad und der Betreiber muss DCC nicht manuell vorstarten. Restfall „DCC stirbt zur Laufzeit": dann greift wieder der Auto-Launch in `initialize()` (UI-Thread) — Komplett-Umbau (Init grundsätzlich off-thread) bewusst NICHT gemacht (Vorgabe „keine großen Refactors", Nikon-HW noch nicht ausgerollt). Auf der Hardware messen. |
| **Merke** | Sobald ein Kamera-/Geräte-Backend über HTTP/Netzwerk spricht, ist „blockiert den UI-Thread" eine reale Gefahr — solche Calls off-thread legen oder hart kurz timeouten. Das Drop-in-Interface war hier korrekt, das **Timing-Verhalten** ist die eigentliche Falle. |

### „Bei jedem Start erzwungene" Produktions-Defaults dürfen keine vom Nutzer änderbaren Werte enthalten

| | |
|---|---|
| **Problem** | Im 2015er-Menü angepasste Druck-Korrektur (`print_adjustment`) wurde zwar in `config.json` gespeichert, aber bei jedem Neustart wieder auf Produktionswerte (40/30/103) zurückgesetzt. Fatal für den Einrichtungsflow (testen → herunterfahren → Kunde startet neu). |
| **Ursache** | `print_adjustment` stand in `_PRODUCTION_DEFAULT_OVERRIDES`. Diese Liste wird bei **jedem** `load_config()` über `_apply_production_defaults()` per `_assign_if_changed` erzwungen – nach dem Deep-Merge der gespeicherten Config. Der Override gewann also immer gegen den gerade gespeicherten Wert. |
| **Lösung** | `print_adjustment` aus `_PRODUCTION_DEFAULT_OVERRIDES` entfernt. Start-Default kommt aus `defaults.py` (identische Werte) und wird durch `config.json` überschrieben; der gewollte Reset pro Eventwechsel bleibt über `reset_event_defaults()`. |
| **Merke** | „Bei-jedem-Start erzwungene" Defaults nur für Werte verwenden, die der Nutzer NICHT ändern darf (z. B. Asset-Pfade, Feature-Flags). Sobald ein Wert über die UI editierbar ist, gehört er NICHT in eine Override-Liste, die nach dem Laden noch zuschlägt – sonst ist „Speichern" wirkungslos. Persistenz immer mit einem echten Neustart-Pfad testen, nicht nur „gespeichert?" prüfen. |

### Hotline-KI: Template/Layout ≠ Live-View Overlay

| | |
|---|---|
| **Problem** | Nach V2-Rollout fragten Kunden häufig nach „Layout", „1 statt 4 Bilder", „Wunsch-Template" oder „falschem Template". Felix leitete dabei teilweise fälschlich zu `Live-View Overlay` an |
| **Ursache** | Der Prompt kannte nur wenige PIN-2015-Menüpunkte und vermischte Live-View-Anzeige mit Drucklayout/Template-Auswahl |
| **Lösung** | Prompt trennt jetzt strikt: `Live-View Overlay` nur für Kamerabild ohne Vorschau-Rahmen; Einzelbild/Multiprint sind kostenpflichtige Upgrades; fehlendes Wunsch-Template ist Callback; Default-Template/4 Bilder kann über `Template wählen` behandelt werden |
| **Merke** | Hotline-Prompts müssen Produktlogik und UI-Funktionen exakt trennen. Ein Menüpunkt mit ähnlichem Namen darf nicht als allgemeine Lösung für Layout-/Template-Probleme genutzt werden |

### Hotline-KI: „Limit erreicht" ist nicht automatisch ein Druckerfehler

| | |
|---|---|
| **Problem** | Kunden meldeten „Limit erreicht" teils zusammen mit Druckproblemen; Felix interpretierte das als technische Störung |
| **Ursache** | Die Meldung bedeutet im Normalfall, dass nur ein Ausdruck erlaubt ist und bereits 1× gedruckt wurde |
| **Lösung** | Prompt erklärt „Limit erreicht" als Hinweis auf Druckanzahl/MultiPrint. Nur wenn der Drucker tatsächlich gar nicht druckt, wird zum Drucker-Runbook gewechselt |
| **Merke** | Display-Meldungen nach Geschäftslogik und Hardwarefehler trennen. Sonst löst der Assistent kostenpflichtige Feature-Grenzen mit falschem Troubleshooting |

### Hotspot: Tethering API braucht mindestens EIN gespeichertes WLAN-Profil

| | |
|---|---|
| **Problem** | Auf frisch geklonten Tablets startete der WLAN-Hotspot nicht, `NetworkOperatorTetheringManager.CreateFromConnectionProfile()` gab immer `null` zurueck. In der Windows-UI kam die Meldung "PC hat keine Ethernet-/WLAN-/Datenverbindung". Sobald die Box sich einmal mit irgendeinem WLAN verbunden hatte (auch ohne Internet) funktionierte der Hotspot ab da dauerhaft - selbst nach Disconnect |
| **Ursache** | Die Tethering-API benoetigt mindestens EIN gespeichertes WLAN-Profil als "Ankerpunkt" fuer `CreateFromConnectionProfile()`. Frisch geklonte Tablets haben nach dem Clonezilla-Restore keine Profile. `GetConnectionProfiles()` gibt eine leere Liste zurueck, `GetInternetConnectionProfile()` gibt null - die API findet nichts zum anhaengen. Beim Realtek RTL8723BS ist zusaetzlich Hosted Network explizit "Nein", d.h. auch der `netsh wlan hostednetwork`-Fallback greift nicht |
| **Entscheidung** | `_ensure_wlan_profile_exists()` in [src/gallery/hotspot.py](src/gallery/hotspot.py) vor jedem `start_hotspot()` aufrufen. Prueft via `netsh wlan show profiles` ob mind. ein Profil existiert, falls nicht wird ein offenes, nicht-auto-verbindendes Dummy-Profil (`FexoBoothDummy`) via `netsh wlan add profile` angelegt. Passiert einmal pro Tablet, ist danach persistent |
| **Alternativen** | (1) Dummy-Profil im Referenz-Tablet speichern und mit ins Image einbacken → ueberlebt Image-Restore nicht zuverlaessig. (2) Via `netsh wlan connect` + sofortiges Disconnect ein aktives Profil erzeugen → unzuverlaessig wenn SSID nicht scant. (3) `setup_hotspot.ps1` manuell einmal laufen lassen → vergisst man bei 200 Tablets |
| **Merke** | Windows-Tethering-API ist nicht "state-less". Sie brauchen gespeicherte Profile als Referenz, selbst wenn der Hotspot gar nichts mit einem Client-WLAN zu tun haben soll. Diagnose: `GetConnectionProfiles()` liefert `[]` = kein Profil gespeichert → Tethering unmoeglich. Fix: ein leeres Dummy-Profil reicht |

### Deployment: Clonezilla "Disk too small" + ebackup/Recovery-Partitionen auf Lenovos

| | |
|---|---|
| **Problem** | Einige Lenovo-Tablets brechen beim `ocs-sr restoredisk` mit "Disk too small" ab. Betroffen sind Tablets mit OEM-Recovery-/"ebackup"-Partitionen ODER Tablets deren eMMC minimal weniger Sektoren hat als die Referenz-Disk (Herstellerchargen variieren um wenige MB). Ohne Logging war nicht erkennbar WAS genau schief ging - der User landete nur im Clonezilla "Choose mode"-Menue |
| **Ursache** | 1) `ocs-sr restoredisk` vergleicht Image-Disk-Groesse sektorgenau mit Ziel-Disk. Schon wenige fehlende Sektoren = Abbruch. 2) OEM-GPT-Schutzstrukturen (Recovery-Partitionen) koennen die Neuanlage der Partitionstabelle blockieren. 3) Das alte Script hatte KEIN Logging - Fehler verschwanden beim Reboot |
| **Entscheidung** | Dreistufige Absicherung in `custom-ocs-deploy`: (1) **Pre-Wipe**: `sgdisk --zap-all` + `wipefs -a` + `dd` 10 MB Nullen → totale Disk, jungfraeulich. (2) **ocs-sr Flags** `-icds` (ignore check disk size) + `-k1` (proportionale Partitionen). (3) **Post-Expand**: `parted resizepart 100%` + `ntfsresize` strecken C automatisch auf volle Disk-Groesse nach Restore. Plus: **Log-File auf FEXODATEN** (`/deploy-logs/deploy-YYYYMMDD-HHMMSS.log`) mit `tee`, ueberlebt Reboot, enthaelt vollstaendige ocs-sr Ausgabe + Disk-Infos VOR und NACH Pre-Wipe |
| **Alternativen** | Referenz-Tablet neu mit kleinerem C capturen (aufwaendig, manuell), `dd` statt ocs-sr (viel langsamer, komprimiert nicht), WinPE-basiertes Custom-Tool (Over-Engineering fuer 200 Tablets) |
| **Merke** | Clonezilla-Deploy-Scripts IMMER mit `2>&1 \| tee -a "$LOG_FILE"` auf einer persistenten Partition loggen - ohne Log kein Debugging. `trap cleanup EXIT` fuer garantierte Status-Zeile am Ende. Und: OEM-Recovery-Partitionen gehoeren vor dem Restore zwingend via `sgdisk --zap-all` entfernt, auch wenn `-e1 auto` das theoretisch erledigen sollte |

### Video: OpenCV Default-Backend kann H.264 nicht decodieren

| | |
|---|---|
| **Problem** | Video zeigt schwarzen Bildschirm auf Miix 310 |
| **Ursache** | OpenCV Default-Backend kann H.264/MP4 nicht decodieren |
| **Lösung** | MSMF-Backend explizit setzen: `cv2.VideoCapture(path, cv2.CAP_MSMF)` |
| **Merke** | Auf schwacher Windows-Hardware immer MSMF für Video nutzen |

### Video: Frame-Lesen blockiert Main-Thread

| | |
|---|---|
| **Problem** | UI friert während Video-Wiedergabe ein |
| **Ursache** | `cap.read()` blockiert den Main-Thread |
| **Lösung** | Threading mit Frame-Queue (Producer-Consumer Pattern) |
| **Merke** | Auf schwacher Hardware immer Video-Decoding in separaten Thread |

### Hotspot: NetworkOperatorTetheringManager braucht Internet

| | |
|---|---|
| **Problem** | Hotspot-Script schlägt fehl ohne Internetverbindung |
| **Ursache** | Windows NetworkOperatorTetheringManager braucht aktive Internetverbindung |
| **Lösung** | Fallback auf netsh hostednetwork |
| **Merke** | Für Offline-Betrieb mehrere Fallback-Methoden implementieren |

### USB: Singleton-Pattern für shared State

| | |
|---|---|
| **Problem** | Pending-Files Counter aktualisiert sich nicht live |
| **Ursache** | Verschiedene Module hatten eigene USBManager-Instanzen |
| **Lösung** | `get_shared_usb_manager()` Singleton-Funktion |
| **Merke** | Bei shared State immer Singleton oder DI nutzen |

### Persistenz: Cache für USB-Daten

| | |
|---|---|
| **Problem** | Template und Buchung nach Neustart oder USB-Abzug weg |
| **Ursache** | Daten wurden nur vom USB gelesen, nicht gecached |
| **Lösung** | Lokaler Cache in .booking_cache/ |
| **Merke** | USB-Daten immer lokal cachen für Offline-Betrieb |

---

### Event-Wechsel: reset_session() löscht gerade geladenes Template

| | |
|---|---|
| **Problem** | System-Test meldet "Keine Template-Boxen geladen", obwohl Template auf USB funktioniert |
| **Ursache** | `_execute_event_change()` lud Template in Schritt 6 (`self.template_boxes = boxes`), aber `reset_session()` in Schritt 9 setzte `self.template_boxes = []` zurück. System-Test in Schritt 12 fand leere Boxes |
| **Lösung** | `reset_session()` VOR Template-Laden verschieben (Schritt 4 statt 9) |
| **Merke** | Bei mehrstufigen Initialisierungen: Daten die im späteren Schritt gebraucht werden NICHT in einem Zwischenschritt überschreiben. Reihenfolge: Erst aufräumen, dann neu befüllen |

### Doppelter Screen-Wechsel bei Video-Callbacks

| | |
|---|---|
| **Problem** | Session-Screen wird 2x erstellt/zerstört nach jedem Zwischen-Video |
| **Ursache** | `_on_video_end()` ruft sowohl `on_complete()` (Callback navigiert) als auch `show_screen()` auf |
| **Lösung** | `show_screen()` nur aufrufen wenn KEIN Callback vorhanden, sonst übernimmt Callback |
| **Merke** | Bei Callback-Pattern: Callback ODER eigene Navigation, nie beides |

### VLC-Cleanup blockiert Kamera-Initialisierung

| | |
|---|---|
| **Problem** | ~400ms Verzögerung nach Video weil VLC und Kamera gleichzeitig DXVA2 nutzen |
| **Ursache** | VLC-Cleanup lief asynchron (fire-and-forget Thread) |
| **Lösung** | `thread.join(timeout=1.0)` - VLC muss DXVA2 freigeben bevor Kamera startet |
| **Merke** | Hardware-Ressourcen immer synchron freigeben bevor nächster Consumer startet |

### Template-ZIP Caching

| | |
|---|---|
| **Problem** | Gleiche ZIP-Datei wurde 3x entpackt beim App-Start |
| **Ursache** | Kein Modul-Level-Cache in TemplateLoader |
| **Lösung** | `_template_cache` Dictionary mit (Pfad, mtime) als Key |
| **Merke** | Teure I/O-Operationen (ZIP, Bilddateien) immer cachen |

### Service-Menü: Separater PIN statt eigener Screen

| | |
|---|---|
| **Problem** | Internes Wartungsmenü soll über anderen PIN aufrufbar sein |
| **Ursache** | Admin-PIN-Dialog ist bereits vorhanden und zentral angebunden |
| **Lösung** | Bestehenden PIN-Dialog erweitert: Service-PIN wird VOR dem Admin-PIN geprüft, öffnet eigenen Dialog |
| **Merke** | Bestehende Infrastruktur erweitern statt duplizieren. App-Referenz am Root-Widget für Dialog-übergreifenden Zugriff |

### CTkImage: dark_image Parameter nötig im Dark Mode

| | |
|---|---|
| **Problem** | Logo wird in der Top-Bar nicht angezeigt, obwohl Pfad korrekt und Datei existiert |
| **Ursache** | `CTkImage(light_image=...)` zeigt nichts im Dark Mode - CustomTkinter nutzt `dark_image` wenn Appearance Mode dark ist |
| **Lösung** | `CTkImage(light_image=img, dark_image=img, size=...)` - beide Parameter setzen |
| **Merke** | CustomTkinter CTkImage braucht IMMER beide Image-Parameter, sonst wird je nach Mode nichts angezeigt |

---

### VLC: Erste Instance-Erstellung dauert ~57s auf schwacher Hardware

| | |
|---|---|
| **Problem** | Erstes Video nach App-Start friert 57 Sekunden ein |
| **Ursache** | VLC lädt beim ersten `_vlc.Instance()` den gesamten Plugin-Cache (~200 Plugins) |
| **Lösung** | Warmup im Hintergrund-Thread direkt beim App-Start. Subtile Ladeanimation falls Video vor Warmup-Ende gestartet wird |
| **Merke** | Teure Initialisierungen immer vorziehen (Warmup-Pattern). 2. VLC-Instance ist sofort (91ms vs 57s) |

### Hotspot-Steuerung blockiert Hauptthread

| | |
|---|---|
| **Problem** | App friert ~6.3s ein beim Start weil Hotspot gestartet/gestoppt wird |
| **Ursache** | PowerShell-Aufruf für Windows Mobile Hotspot API ist synchron und langsam |
| **Lösung** | Start und Stop in daemon-Threads auslagern |
| **Merke** | Alle externen Prozessaufrufe (subprocess) in Hintergrund-Threads |

### overrideredirect(True) macht App zum Hintergrund-Prozess

| | |
|---|---|
| **Problem** | App erscheint im Windows Taskmanager als "Hintergrund-Prozess" statt "App" |
| **Ursache** | `overrideredirect(True)` entfernt das Fenster aus der Windows-Shell-Verwaltung (kein Taskbar-Eintrag) |
| **Lösung** | `overrideredirect(True)` beibehalten (deckt auf Miix 310 korrekt den ganzen Screen ab), PLUS Windows API `SetWindowLongW` mit `WS_EX_APPWINDOW` Flag setzen (erzwingt Taskbar-Eintrag) |
| **Merke** | `attributes("-fullscreen", True)` deckt auf manchen Tablets NICHT den ganzen Bildschirm ab! `overrideredirect(True)` + `WS_EX_APPWINDOW` via ctypes ist der sichere Weg |

### Foto-Zähler Off-by-One bei letztem Foto

| | |
|---|---|
| **Problem** | "Foto 5 von 4" wird beim letzten Foto einer 4er Collage angezeigt |
| **Ursache** | `_capture_photo` erhöht `current_photo_index` NACH dem Foto und ruft dann `_update_progress` auf. Beim 4. Foto: Index 3→4, Anzeige 4+1=5 |
| **Lösung** | `min(current_photo_index + 1, total_photos)` in `_update_progress` |
| **Merke** | Bei Zähler-Anzeigen immer auf Off-by-One achten, besonders wenn Index nach dem letzten Element hochgezählt wird |

### Flash-Bild intermittierend nicht sichtbar

| | |
|---|---|
| **Problem** | Auslösebild fehlt sporadisch beim 2. Foto einer Collage |
| **Ursache** | Flash wird nur per Flag (`show_flash=True`) gesetzt und erst beim nächsten `_update_live_view`-Tick (bis zu 50ms später) angezeigt. Auf langsamer Hardware kann der Tick verpasst werden |
| **Lösung** | `_display_flash()` direkt in `_take_photo()` aufrufen (sofortige Anzeige), zusätzlich zum Flag für die Loop |
| **Merke** | Zeitkritische visuelle Feedback-Elemente sofort anzeigen, nicht auf den nächsten Timer-Tick warten |

## Performance-Erkenntnisse

- **Max. 25 FPS für Video** - Mehr schafft die Hardware nicht flüssig
- **Keine 60fps GUI-Updates** - after() mit mindestens 50ms Intervall
- **Bilder nicht im RAM halten** - Sofort auf Disk schreiben, nur bei Bedarf laden
- **Flask ist OK** - Verbraucht nur ~20-30 MB RAM im Idle
- **LANCZOS-Resize cachen** - Overlay-Resize auf App-Level statt Screen-Level, überlebt Screen-Wechsel
- **Kamera nicht freigeben bei Zwischen-Videos** - Kamera bleibt warm, spart ~1.5s Reopening
- **Template-Preview im Session-Screen entfernen** - Vollbild-LiveView statt Template-Overlay spart ~200 Zeilen Code und mehrere PIL-Operationen pro Frame
- **BILINEAR statt LANCZOS für kleine Previews** - Filter-Mini-Previews brauchen keine High-Quality-Interpolation, BILINEAR reicht und ist spürbar schneller
- **Container-Größe Fallback** - `winfo_width()` gibt 0/1 zurück wenn Widget noch nicht gelayoutet wurde. Immer Fallback auf Screensize haben
- **Windows Icon-Cache** - `ie4uinit.exe` existiert nicht auf allen Geräten (z.B. Lenovo Miix 310). Icon-Cache-Dateien per PowerShell löschen UND `SHChangeNotify(SHCNE_ASSOCCHANGED)` aufrufen um den Explorer sofort zu benachrichtigen. In Inno Setup am besten direkt im Pascal-Script per `external 'SHChangeNotify@shell32.dll stdcall'`
- **ICO Multi-Size** - Windows Desktop-Icons brauchen 256x256 Auflösung. Eine ICO mit nur 16x16 wird verpixelt dargestellt. Immer alle Größen (16, 24, 32, 48, 64, 128, 256) einpacken
- **CTkImage dark_image** - CustomTkinter CTkImage braucht IMMER `dark_image` Parameter gesetzt, auch wenn identisch mit `light_image`. Ohne wird im Dark Mode NICHTS angezeigt. Betrifft ALLE Stellen wo CTkImage erzeugt wird (Flash, Preview, Final)
- **PIL paste() mit RGBA-Maske** - `Image.paste(img, pos, img)` mit RGBA-Maske funktioniert nur zuverlässig für Bilder die tatsächlich Transparenz haben (PNG). Für JPEG→RGBA-Konvertierung (Alpha=255 überall) kann die Maske Probleme machen. Besser: Bildmodus prüfen und nur für echte RGBA-Bilder die Maske verwenden, für RGB direkt ohne Maske pasten
- **CustomTkinter Overlays** - `place()` Widgets mit `fg_color="transparent"` zeigen die Hintergrundfarbe des Parent-Widgets, NICHT das darunter liegende Widget (kein echtes Alpha in tkinter). Für saubere UI: `pack()`-Layout verwenden, damit Elemente nicht überlappen. Overlays über Bildern erzeugen immer sichtbare Rechtecke
- **Booking-Settings vs. Config-Persistenz** - Booking-Settings aus settings.json werden via `apply_settings_to_config()` in die App-Config übernommen. Feature-Checks (z.B. Galerie aktiv?) müssen NUR die Config prüfen, nicht zusätzlich die Booking-Settings direkt. Sonst können Admin-Änderungen nicht greifen, weil die Booking-Settings die Config-Änderung "umgehen"
- **Gallery-Server Pfad ≠ Lokaler Bilder-Pfad** - Der Gallery-Server kann auf den USB-BILDER-Ordner zeigen, nicht auf den lokalen. Beim Löschen von Bildern muss auch der Gallery-Pfad berücksichtigt werden, sonst bleiben Bilder im Live-Server sichtbar
- **PyInstaller 6.x _internal-Ordner** - Neuere PyInstaller-Versionen legen Daten-Assets in `_internal/` ab, nicht im Root des Dist-Ordners. Desktop-Shortcuts und andere externe Referenzen auf Assets müssen den korrekten Pfad verwenden. Im Installer die ICO-Datei separat kopieren
- **Windows Mobile Hotspot braucht Internet** - `NetworkOperatorTetheringManager.GetInternetConnectionProfile()` gibt null zurück ohne Internetverbindung. Stattdessen `GetConnectionProfiles()` nutzen und ALLE Profile durchprobieren. Als Offline-Fallback: `netsh wlan hostednetwork` (braucht kein Internet, nutzt WiFi-Adapter direkt als SoftAP). Wichtig: WiFi-Adapter muss AKTIV bleiben, nur keine Verbindung zu einem Netzwerk haben
- **Flash-Timing von Capture entkoppeln** - `show_flash = False` muss AM ANFANG von `_capture_photo()` gesetzt werden (mit `update_idletasks()`), NICHT am Ende. Sonst bleibt der Flash während des gesamten blockierenden Capture-Aufrufs sichtbar (bis zu 10s bei Timeout). Die Flash-Dauer wird durch den `after(flash_duration)` Timer bestimmt, nicht durch die Capture-Dauer
- **Flash-Bild muss gecacht werden** - `_display_flash()` lädt bei jedem Foto das JPEG neu (~120ms auf Atom CPU). Zusammen mit dem blockierenden `get_high_res_frame()` bleibt kaum Zeit für die GUI den Flash tatsächlich zu malen. Lösung: Flash-PIL-Image einmalig beim Session-Start cachen, und `update_idletasks()` nach dem Setzen aufrufen um den Redraw zu erzwingen
- **subprocess text=True Encoding** - `subprocess.run(..., text=True)` nutzt `locale.getpreferredencoding()` (cp1252 auf dt. Windows). PowerShell-Output mit Sonderzeichen (Umlaute, Unicode) kann `UnicodeDecodeError` auslösen. Fix: `text=True` weglassen und stattdessen `result.stdout.decode("utf-8", errors="replace")` verwenden
- **overrideredirect(True) nach Dialog** - Auf Windows wird `overrideredirect(True)` nicht immer sofort übernommen. Die App muss `withdraw()` + `deiconify()` aufrufen (in `_set_appwindow()`). Admin-Dialog darf Fullscreen-Restore NICHT selbst machen, sondern die App übernimmt das nach `wait_window()` mit `_enter_fullscreen()`
