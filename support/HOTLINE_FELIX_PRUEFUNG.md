# Felix: Prompt-Abgleich und Uebergabe

Stand: 2026-11-09. Gueltig fuer die interne FexoBooth V2 und den deutschen
Assistenten Felix, nicht automatisch fuer den niederlaendischen Mark.

## Ergebnis

`HOTLINE_PROMPT_FELIX.md` ist die vollstaendige, direkt verwendbare Prompt-Fassung.
Sie enthaelt nur Assistenten-Anweisungen; diese Uebergabe gehoert nicht in Fonio.
Grundlage ist Christians vollstaendiger Fonio-Export vom 27.10.2026, ergaenzt
um seine ausdruecklichen Antworten und den Abgleich mit dem lokalen V2-Code.
Die bisherige lokale Datei ist durch diese abgeglichene Fassung ersetzt.

Status: Christian bestaetigt am 09.11., dass die Fassung vom 27.10. seit dem
27.10. in Fonio aktiv ist. Die Ergaenzungen vom 09.11. sind nur lokal erstellt
und noch NICHT in Fonio eingespielt. Keine Telefon-, Hardware- oder Versandtests
mit diesen Ergaenzungen durchgefuehrt.
Der jeweilige Softwarestand der Kundenbox muss weiter beachtet werden.

Pruefergebnis der Fassung vom 27.10.: 26/26 statische Textpruefungen bestanden (u. a. Menue vor
Warten, kein alter Ausschaltablauf, Kassette vor Test, expliziter Druckstart,
Nachdruck-Abgrenzung, erhaltene Zustimmungsparameter, keine Kundentelefonnummern).
`git diff --check` ohne Fehler. Das belegt die Textfassung, nicht das Verhalten
des Fonio-Modells, die Aktionen oder den Erfolg einer Hardware-Reparatur.

Pruefergebnis vom 09.11.: 28/28 gezielte statische Textpruefungen bestanden
(QR-Entscheidungsfolge, WLAN-Angaben, Galerie-Abgrenzung, Vorabtest,
Designaenderung und unveraenderte Rueckruf-/Versand-Aktionsbloecke).
`git diff --check` ohne Fehler. Keine Aussage ueber Live-Gespraechsverhalten.

## Optionale Kompaktfassung vom 09.11.2026

`HOTLINE_PROMPT_FELIX_KOMPAKT.md` ist ein eigenstaendiger Vergleichskandidat,
kein Zusatz zum bisherigen Prompt. Die vollstaendige Ausgangsfassung bleibt
unveraendert in `HOTLINE_PROMPT_FELIX.md`; nicht beide Fassungen zugleich einsetzen.

- Bei einheitlichen LF-Zeilenenden: 81.377 auf 54.119 Zeichen, 33,5 % kuerzer.
- Wortgleich erhalten: gesamter Callback-Block inkl. Mail-Adressen, Kamera-Runbook,
  gesamtes Template-/Upgrade-Runbook E, App-Runbook I und ergaenzende Kurzinfos.
- Gestrafft: Wiederholungen, ausformulierte Diagnosefragen, doppelte Menuewege.
  Technische Verzweigungen, Grenzwerte, Einzelschritte und Eskalationen abgeglichen.
- 53/53 statische Pruefungen bestanden (inklusive fuenf wortgleicher Abschnitte
  und gleicher 16 Hauptabschnitte). Ausgangsdatei per SHA-256 unveraendert.
- Keine bewusst entfernten Fachfaelle, keine neu konfigurierten Aktionen und
  keine Annahme, dass eine Prompt-Regel bereits durch Fonio-Einstellungen abgedeckt sei.
- Weiter ueber dem 12.500-Zeichen-Hinweis. Eine kuerzere Gespraechssteuerung mit
  separater Wissensbasis waere ein eigener Umbau; hier nicht vorgenommen.
- NICHT in Fonio eingespielt oder telefonisch getestet. Statische Abdeckung
  garantiert keine gleich gute Modellbefolgung. Vor Austausch dieselben
  Gespraechstestfaelle mit beiden Fassungen vergleichen; sonst bisherige Fassung behalten.

## Bestaetigte Ergaenzungen vom 09.11.2026

- Fehlender App-QR: App-Option gebucht? Falls ja, Nachbuchung erst waehrend
  Versand oder nach Ankunft? Falls ja, neue settings.json aus der Nachbuchungs-Mail
  gemaess deren Anleitung aufgespielt? Erst danach den sichtbaren QR pruefen.
  Eine bereits bestaetigte Nachbuchung nicht als fehlende Buchung behandeln.
- Die neue Datei unveraendert uebernehmen; bei Bedarf vorhandenes Event-Neu
  Einlesen nutzen. Kein pauschaler Hardware-Reset wegen eines fehlenden QR.
- Pairing braucht den QR auf dem Boxdisplay, die gestartete App und das Box-WLAN.
  SSID und Passwort sind im Prompt exakt nach Christians Angabe hinterlegt und
  mit den lokalen Anzeige-Defaults abgeglichen. Keine geratenen Fundstellen,
  keine Verbindung zu einem vermeintlich offenen WLAN als Ersatz.
- App/Live-Galerie strikt von der nachtraeglichen Online-Galerie trennen.
  Letztere ist erst nach Rueckversand verfuegbar; keine konkrete Frist zugesagt.
- Vollstaendigen Funktionstest mit Testdruck direkt nach Erhalt dringend empfehlen.
  Papier und Farbfolie duerfen dafuer geoeffnet werden. Keine Pflicht oder
  Vertragsfolgen aus der Empfehlung ableiten.
- Gewuenschte Designaenderung nach Ankunft ist gebuehrenpflichtig und erfordert
  eine Freischaltung durch fexobox. Keine vollstaendige Selbstbedienung zusagen,
  keine Gebuehrenhoehe erfinden. Unveraenderter Dateineuversand ist keine Aenderung.
  Das ist keine pauschale Gebuehrenregel fuer Fehlerkorrekturen/fehlende Templates.
- OFFEN: Darf die bestehende Dateiversand-Aktion eine nicht auffindbare
  App-Nachbuchungs-Mail ersetzen? Nicht bestaetigt; bis zur Klaerung keine neue
  Versandbefugnis, in diesem Fall Rueckruf anbieten.

## Anrufpruefung 27.10. bis 08.11.2026

35 Berichte mit Betreff "Anruf bei Technik-KI" gelesen: 33 Felix, zwei Mark.
Mark nicht gegen den deutschen Felix-Prompt bewerten. Relevante Abweichungen
nach bestaetigter Aktivierung der Oktober-Fassung:

- 07.11.: Nach App/WLAN-Rueckruf Aktion "Template-Vorschau per SMS senden".
  Tatsaechlicher Empfaenger und SMS-Inhalt im Bericht nicht ersichtlich.
- 08.11.: mailbox_ok=ja ohne vorherige Mailbox-Frage.
- 06.11.: Identische Rueckruf-Aktion zweimal ausgefuehrt; doppelte Tickets
  sind dadurch allein noch nicht nachgewiesen.
- 31.10.: Knappe Zustimmung als erfolgreichen Testdruck gewertet, vom Kunden
  sofort widersprochen. Teilweise unpassende Kassettendiagnose vor Drucktest.
- 30.10.: Uebergebene Buchungsnummer weicht von vorgelesener Bestaetigung ab.
- App-Gespraeche enthalten unbelegte Passwort-Fundstellen und Hardware-Umwege.
  Christians Nachbuchungsfall laesst sich keinem Bericht sicher zuordnen.

Die meisten Ablaufregeln standen bereits im Prompt. Aktionsbedingungen,
Parameteruebernahme, Team-SMS-Zuordnung und Rueckruf-Wiederholungen in Fonio
pruefen; die neuen Fachregeln allein belegen keine Behebung dieser Fehler.

## Bestaetigte Entscheidungen

- Keine zusaetzliche routinemaessige Pruefung der Buchungszugehoerigkeit.
  Felix kann diese nicht selbst feststellen. Christian hat nach eigener Angabe
  E-Mails an vergangene Buchungen gesperrt; diese externe Sperre wurde hier
  nicht technisch geprueft. Aktionsablehnungen duerfen nicht umgangen werden.
- Alte Fotos vom USB-Stick oder aus abgeschlossenen Aufnahmen koennen an der
  Box nicht erneut ausgewaehlt und gedruckt werden. Ausdruck ausserhalb der
  Box moeglich. Davon getrennt: weitere erlaubte Ausdrucke des aktuellen Fotos.
- Haengendes Druckerfenster: verfuegbaren PIN-Ausgang nutzen, Kundenmenue 2015,
  zuerst Druckstau beheben. Laufende Auftraege danach bzw. nach noetigem Neustart
  bei EINGESCHALTETER Box und eingeschaltetem Drucker in Ruhe abarbeiten lassen.
  Keine zehnminuetige Ausschaltpause, keine feste Warteschlangen-Wartefrist.
- Kein neuer Reset oder zusaetzlicher Testdruck waehrend laufender Druckauftraege.

## Gezielte Korrekturen

- Entfernte Farbkassette vor Test wieder einsetzen und Klappe schliessen lassen.
- Vollstaendige Aufnahme abwarten und den Druck mit dem sichtbaren Drucken-Button
  ausloesen. Fertige Collage allein ist noch kein Druckauftrag.
- Kein erfundenes Galerie-/Fotos-ansehen-Menue fuer Nachdruck.
- Kein Windows-Neustart-Button mehr: Neustart / Ausschalten mit Auswahl.
- Event-Neu Einlesen beibehalten; Schnellhilfe und PIN-Ausgang nur bei vorhandener
  Oberflaeche. Druck-Korrektur aus der Fonio-Fassung bleibt versionsabhaengig.
- SMS-Vorschau und Dateiversand nur nach dem vollstaendigen Template-Ablauf;
  bereits als falsch bestaetigte Vorschau nicht nochmals senden.
- Template-Vorschau prueft keine App-Freischaltung. Nachtraegliche Online-Galerie
  und Live-Galerie unterscheiden; keine erfundenen Freigabe- oder Bereitstellzeiten.
- Kameraerfolg erst nach Aufnahme, nicht allein nach verschwundenem Warnsymbol.
- Wiederholende technische Kurzinfos durch Verweise ersetzt.

## Vor Freigabe in Fonio pruefen

Der Export enthaelt keine separat eingerichteten Aktionen oder deren komplette
Antwortformate. Die folgenden bestehenden Namen und Parameter wurden beibehalten:

| Aktion | Im Prompt verwendete Werte |
|---|---|
| Rueckruf anfordern | buchungsnummer, thema, mailbox_ok |
| Template Vorschau-Link erzeugen | buchungsnummer, preview_sms_confirmed |
| Template-Vorschau per SMS senden | andere Gespraechspartei; erzeugter Vorschau-Link |
| Template neu an Kunden senden | buchungsnummer, template_resend_confirmed, reason, summary |

Die deutschen Aktionsnamen stehen im Prompt mit Umlauten genau wie im Export.
Die konfigurierte Team-SMS nach Rueckruf, Nummern-/Link-Zuordnung, Ablehnungen,
Ergebniscode und agent_instruction sowie Rueckruf ohne Buchungszuordnung muessen
an der echten Fonio-Konfiguration geprueft werden. HTTP-Erfolg allein belegt
keinen erfolgten Versand. Keine echten Kundenaktionen nur zum Test ausloesen.

Die separate Startnachricht war nicht Bestandteil des Exports. In den Anrufen
fordert sie die Buchungsnummer vor dem Anliegen; der Prompt behandelt die Nummer
als freiwillig. Startnachricht separat auf diesen Widerspruch pruefen.

## Gespraechstests nach Einspielen

| Fall | Erwartung |
|---|---|
| Farbkassette wurde entfernt | Wieder einsetzen, Klappe schliessen, erst dann Test |
| Collage fertig, aber noch nicht Drucken getippt | Bedienung erklaeren, noch kein Drucker-Reset |
| Nach Neustart kommen alte Ausdrucke | Eingeschaltet abarbeiten lassen, keine weiteren Resets/Tests |
| Druckerfenster blockiert | PIN-Ausgang falls vorhanden, dann Druckstau beheben |
| Aelteres Foto vom Stick drucken | An Box nicht vorgesehen; kein erfundenes Menue |
| Vorschau war bereits falsch | Rueckruf statt erneuter gleicher Vorschau |
| Ja zum Rueckruf, Mailbox noch offen | Gesondert fragen; nicht automatisch mailbox_ok=ja |
| Upload-Validierungsfehler | Keine USB-/Druckerdiagnose, Rueckruf |
| QR fehlt, App-Buchung unklar | Zuerst App-Buchung im Kundenbereich klaeren, kein WLAN-/Reset-Ablauf |
| App nicht gebucht, QR fehlt | Kostenpflichtige Nachbuchung erklaeren, nicht als Defekt behandeln |
| App waehrend Versand/nach Ankunft gebucht, neue Datei fehlt auf Box | Nachbuchungs-Mail, unveraenderte settings.json nach Anleitung uebernehmen, QR danach ausdruecklich pruefen |
| Nachbuchungs-Mail/Datei nicht auffindbar | Rueckruf, keine neue Versandbefugnis oder Template-SMS |
| Datei korrekt aufgespielt/eingelesen, QR fehlt weiterhin | Rueckruf, kein erneutes Aufspielen oder Reset-Schleife |
| App schon vor Versand gebucht, QR fehlt | Rueckruf nach Klaerung, keine Ursache erfinden |
| QR auf Box vorhanden | Keine erneute Buchung; App starten, exaktes Box-WLAN, Pairing pruefen |
| Nur Flyer-QR oder WLAN vorhanden | Kein Ersatz fuer den Pairing-QR auf dem Boxdisplay |
| Kunde meint nachtraegliche Online-Galerie | Erst nach Rueckversand, keine konkrete Frist, keine App/WLAN-Diagnose |
| Kunde fragt nach Test vor Veranstaltung | Vollstaendigen Test samt Testdruck direkt nach Erhalt dringend empfehlen; Material darf geoeffnet werden |
| Kunde will nach Ankunft sein Design aendern | Gebuehr und Freischaltung durch fexobox erklaeren; Rueckruf anbieten, kein unveraenderter Neuversand als Loesung |
| Versandaktion lehnt alte Buchung ab | Keine Versandzusage, Sperre nicht umgehen |
| Einmaliger korrekter Reset erfolglos | Rueckruf, keine zweite Reset-Runde |

## Aufbau und Quellen

Die Datei bleibt vorerst eine in sich vollstaendige Gesamtfassung fuer die
bestehende Fonio-Einrichtung. Eine getrennte kurze Gespraechssteuerung plus
Wissensdatenbank ist eine spaetere Konfigurationsaenderung, kein stillschweigender
Bestandteil dieser Lieferung. Fonio empfiehlt kurze Prompts, eindeutige
Wenn-Dann-Regeln und getrenntes Wissen:
https://fonio.info/en/get-started/write-a-great-prompt

Abgeglichen: src/ui/screens/admin.py (Kundenmenue), src/i18n.py (Bezeichnungen),
src/ui/screens/final.py (Druckausloesung), src/ui/dialogs/printer_error.py
(PIN-Ausgang) und ROADMAP.md (Online- vs. Live-Galerie).
Abgleich am 09.11.: Christians ausdrueckliche Ablauf-/Produktbestaetigungen,
src/storage/booking.py (live_gallery -> gallery_enabled),
src/ui/screens/start.py (QR-Anzeige und WLAN-Defaults) sowie
src/ui/screens/admin.py (Event-Neu Einlesen uebernimmt Settings).
Anrufbeispiele: 22./24.10.2026 (Farbkassette/Testdruck), 23.10.2026 (Template),
25.10.2026 (Nachdruck), 02.10.2026 (QR). Keine Kundendaten in dieser Uebergabe.
