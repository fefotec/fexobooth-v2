# Arbeitsweise - KI-Zusammenarbeit

Diese Regeln gelten für die Zusammenarbeit zwischen Mensch und KI in diesem Projekt.

---

## Projektabgrenzung

`fexobooth-v2` ist die interne Live-Flotten-Software. Sie darf nicht mit
`fexobooth-consumer`, Backend, Web, Portal, Checkout oder Lizenzierung vermischt werden,
wenn Christian ausdrücklich an der internen V2 arbeitet.

Für V2-Aufgaben:
- nur `fexobooth-v2` als Zielrepo behandeln, außer Christian nennt ein weiteres Repo,
- keine Consumer-/Backend-/Web-Pflichtprüfungen erzwingen,
- keine Folgeprompts für das Consumer-Projekt anhängen,
- Abschluss kurz und praktisch halten: V2-Dateien, Checks, Hardware-/Tablet-Blocker.

---

## Kernprinzipien

### 1. Niemals mutmaßen - immer nachfragen

- Bei Unklarheiten: Frage stellen, nicht raten
- Lieber eine Frage zu viel als falscher Code
- Anforderungen klären bevor du loslegst

### 2. Kritisch hinterfragen und bessere Wege aufzeigen

- Wenn es einen besseren Ansatz gibt: Sag es
- Potenzielle Probleme ansprechen
- Alternativen vorschlagen mit Vor-/Nachteilen

### 3. Richtige Antworten vor schnellen Antworten

- Lieber gründlich recherchieren als oberflächlich antworten
- Bestehenden Code verstehen bevor Änderungen vorgeschlagen werden
- Performance-Auswirkungen bedenken (schwache Ziel-Hardware!)

### 4. Code-Qualität

- **Komplette Dateien/Funktionen** - Nichts weglassen oder kürzen
- **Anfängerfreundlich erklären** - Warum wurde etwas so gemacht?
- **Keine halben Sachen** - Code muss lauffähig sein
- **Bestehende Patterns respektieren** - An vorhandenen Stil anpassen

### 5. Fehlersuche

- Ausschlussverfahren anwenden
- Ein Schritt nach dem anderen
- Hypothesen aufstellen und testen
- Logs prüfen: `logs/fexobooth_YYYYMMDD.log`

### 6. Selbstständige Dokumentation

Ohne Aufforderung aktualisieren:
- `FORTSCHRITT.md` - Nach jeder abgeschlossenen Änderung
- `ERKENNTNISSE.md` - Bei neuen Erkenntnissen
- `TODO.md` - Aufgaben hinzufügen/abhaken
- `CHANGELOG.md` - Release-relevante Änderungen

### 7. Kommunikation

- **Sprache:** Deutsch
- **Stil:** Kurz und prägnant
- **Niveau:** Anfängerfreundlich erklären

### 8. Dev-Mode-Logging & Test-First (PFLICHT bei jeder Code-Änderung)

**Grundregel:** Bei **jeder** Änderung an der Software wird **sofort** das Dev-Mode-Logging
mit erweitert – nicht erst, wenn etwas nicht funktioniert. Neue Funktionen werden **immer
zuerst im Dev-Mode getestet**, bevor sie als fertig gelten.

**Warum:** Im Feld stehen 200+ Boxen ohne Internet. Wenn dort etwas hakt, ist das Log
(`logs/fexobooth_*.log`) oft die einzige Spur. Logs, die schon **beim Bauen** mitgeschrieben
werden, sparen später stundenlange Ferndiagnose. Im Produktivbetrieb kosten sie nichts –
Logging ist dort komplett aus (NullHandler), Overhead = 0.

**So funktioniert der Dev-Mode (Fakten):**
- Aktivieren: `python src/main.py --dev` (oder `-d`, bzw. `start_dev.bat`). Setzt
  `config["developer_mode"] = True` ([src/main.py](src/main.py)).
- Logging ist **nur** im Dev-Mode aktiv → Datei `logs/fexobooth_YYYYMMDD_HHMMSS.log`
  + Konsole. Im Live-Betrieb: NullHandler, kein RAM-/CPU-Kosten.
- On-Screen: Performance-Overlay (CPU/RAM, oben rechts) – [src/ui/performance_overlay.py](src/ui/performance_overlay.py).

**Pflicht-Ablauf bei jeder Änderung/neuen Funktion:**
1. **Funktion schreiben.**
2. **Logging gleich mit einbauen** – am Dateikopf:
   ```python
   from src.utils.logging import get_logger
   logger = get_logger(__name__)
   ```
   Dann an den wichtigen Stellen:
   - `logger.info(...)` = Einstieg, Erfolg, Status-Wechsel (Meilensteine)
   - `logger.debug(...)` = Zwischenschritte, Variablen, Hardware-State
   - `logger.warning(...)` = erwartbare Fehler/Fallbacks (fehlende HW, kaputte Datei)
   - `logger.error(..., exc_info=True)` = unerwartete Exceptions (mit Stacktrace)

   Logge **das, was beim Fehlersuchen zählt**: welcher Pfad/welche Datei/welcher Wert
   wirklich genommen wurde (z.B. „lade Template aus USB D:\… statt Cache"). Genau solche
   Logs lösen Bugs wie „Template wechselt nicht" in Minuten statt Stunden.
3. **Im Dev-Mode starten** (`--dev`) und die neue Funktion **manuell durchklicken**.
4. **Log-Output prüfen** – kommt die erwartete Reihenfolge? Tauchen unerwartete
   Warnungen/Errors auf?
5. **Erst dann** gilt die Funktion als fertig → `FORTSCHRITT.md`/`CHANGELOG.md` aktualisieren.

**Faustregel:** Wer Code ändert, ohne das passende Log mitzuziehen, ist nicht fertig.

---

## Spezielle Regeln für Fexobooth

### Performance ist kritisch!

- Ziel-Hardware: Lenovo Miix 310 (Atom CPU, 4GB RAM)
- Jede Zeile Code muss ressourcenschonend sein
- Keine unnötigen Bibliotheken
- Bilder nicht im RAM ansammeln

### Offline-Betrieb

- Software läuft ohne Internet
- Keine Online-APIs nutzen
- Alle Assets lokal vorhanden

### Debugging im Feld

- 200+ Fotoboxen im Einsatz
- Gute Logs sind essentiell
- Code muss ohne Internet debuggbar sein
