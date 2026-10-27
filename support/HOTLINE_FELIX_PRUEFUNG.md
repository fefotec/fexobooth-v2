# Felix: Prompt-Abgleich und Uebergabe

Stand: 2026-10-27. Gueltig fuer die interne FexoBooth V2 und den deutschen
Assistenten Felix, nicht automatisch fuer den niederlaendischen Mark.

## Ergebnis

`HOTLINE_PROMPT_FELIX.md` ist die vollstaendige, direkt verwendbare Prompt-Fassung.
Sie enthaelt nur Assistenten-Anweisungen; diese Uebergabe gehoert nicht in Fonio.
Grundlage ist Christians vollstaendiger Fonio-Export vom 27.10.2026, ergaenzt
um seine ausdruecklichen Antworten und den Abgleich mit dem lokalen V2-Code.
Die bisherige lokale Datei ist durch diese abgeglichene Fassung ersetzt.

Status: lokal erstellt und textlich geprueft. NICHT in Fonio installiert.
Keine Telefon-, Hardware- oder Versandtests mit dieser Fassung durchgefuehrt.
Der jeweilige Softwarestand der Kundenbox muss weiter beachtet werden.

Pruefergebnis: 26/26 statische Textpruefungen bestanden (u. a. Menue vor
Warten, kein alter Ausschaltablauf, Kassette vor Test, expliziter Druckstart,
Nachdruck-Abgrenzung, erhaltene Zustimmungsparameter, keine Kundentelefonnummern).
`git diff --check` ohne Fehler. Das belegt die Textfassung, nicht das Verhalten
des Fonio-Modells, die Aktionen oder den Erfolg einer Hardware-Reparatur.

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
| App sicher gebucht, QR fehlt | Rueckruf, keine Template-SMS als Buchungspruefung |
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
Anrufbeispiele: 22./24.10.2026 (Farbkassette/Testdruck), 23.10.2026 (Template),
25.10.2026 (Nachdruck), 02.10.2026 (QR). Keine Kundendaten in dieser Uebergabe.
