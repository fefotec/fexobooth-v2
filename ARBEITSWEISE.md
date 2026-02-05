# Arbeitsweise - KI-Zusammenarbeit

Diese Regeln gelten für die Zusammenarbeit zwischen Mensch und KI in diesem Projekt.

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
