# Event-Test: Kamera-Besitz und garantierter Abschluss (2.4.73)

Christian hat die Umsetzung nach Diagnose der Dev-Logs von Box 210 und 008
freigegeben. Zielrepo ist ausschliesslich die interne FexoBooth V2.

## Befund und Grenze

Beide C922-Webcams liefern beim Warmstart ein echtes 1920x1080-MJPG-Bild.
Unmittelbar danach scheitern alle Test-Reads, FOURCC ist unbekannt. Der
Status-Waechter prueft `is_initialized` vor, aber nicht nach dem Warten auf
die Hardware-Sperre. Das Rennen ist mit den unveraenderten Methoden und
einer echten RLock reproduziert. DirectShow teilt seinen nativen
Geraetezustand; ein zweiter Open/Release kann die aktive Kamera stoppen.
Zusaetzlich ueberspringt der Test bei Foto-/Initfehlern sein Cleanup.
Die physische Bestaetigung des Fixes bleibt Christians Box-Test.

## Entscheidung

Nur eine weitere Abfrage vor dem Lock wuerde das Rennen offenlassen;
ein automatischer Neuversuch wuerde es lediglich verdecken. Stattdessen:

1. Der Event-Test reserviert die Kamera vor dem Oeffnen des Dialogs bis zum
   Abschluss seines Workers einschliesslich Cleanup. Doppelte Teststarts
   werden verworfen. Eine fehlgeschlagene Dialog-/Worker-Erzeugung gibt
   die Reservierung ebenfalls frei.
2. Der Status-Waechter pausiert bei reserviertem Test. Saemtliche Webcam-
   Probewege (Kurzcheck, volle Liste, Suche bei Index -1) erwerben dieselbe
   bestehende RLock mit Zeitgrenze und pruefen danach erneut Testbesitz,
   aktive Kamera, Kamera-Messung und Startscreen. Ein schon laufender Probe
   darf unter dem Lock fertig werden; Kamera-Initialisierung wartet dort.
3. Ergebnisse aus einer alten Testgeneration oder waehrend aktiver Nutzung
   duerfen keine Kameraindizes/Statuswarnungen nachtraeglich veraendern.
4. Der Test-Worker raeumt in `finally` exakt einmal auf: die beim Start
   festgehaltene Kamera, Testdatei und Bilder. Fehler, Abbruch, Timeout und
   zerstoertes Fenster aendern diese Pflicht nicht. UI-Abbruch signalisiert
   nur; er ruft kein blockierendes `release()` auf dem Hauptthread auf.
   Ergebnis/Weiter/Schliessen erst nach Worker-Abschluss; Ctrl+Shift+Q
   merkt den Schliesswunsch vor. Ein nativer Treiberhaenger ist nicht
   gewaltsam abbrechbar: die Reservierung bleibt bis zum echten Abschluss,
   statt einen zweiten Kamerabesitzer zuzulassen. App-Shutdown bleibt
   ausserhalb dieses Fixes.

## Unveraendert

Keine Aenderung an Webcam-Warmstart, Aufloesung, Foto-/LiveView-Pfad,
Canon-Shutter, Nikon-Bridge, Drucklogik, Layout oder Kamera-Auswahlregeln.
Keine neue Abhaengigkeit und kein zusaetzlicher Dauer-Worker. Bestehende
Dialogtexte werden wiederverwendet. Das Produktionsrelease wird durch
diesen Testkandidaten nicht automatisch ersetzt.

## Nachweis und Umsetzung

- Regressionstest mit echten Produktionsmethoden, kontrollierten Threads
  und gefaelschter Hardware: wartender Probe in allen drei Pfaden;
  aktive Kamera/Test/Messung/Screenwechsel; normaler Leerlauf bleibt aktiv;
  alte Rueckmeldungen; Cleanup bei Erfolg, Init-/Fotofehler, Abbruch,
  Timeout, UI-Ausnahme und Dialogzerstoerung; spaeter Neustart moeglich.
- Dev-Logs fuer Reservierung, uebersprungene Pruefung, Worker-Abschluss
  und Kamera-Freigabe; keine Bildinhalte oder Zugangsdaten.
- Bestehende Gesamtsuite und lokaler Windows-Build 2.4.73. Manueller
  Dev-Mode-/Kamera-/Testdruck-Nachweis erfolgt auf Christians Boxen.
- Reihenfolge: Probe-Schutz, Test-Lebenszyklus, Regressionen, Version/Doku,
  gesamte Testsuite, Installer. writing-plans ist in dieser Sitzung nicht
  als Skill verfuegbar; diese Liste dient als kompakter Umsetzungsplan.
