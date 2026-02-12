# Nach dem Klonen (optional)

Nach dem Klonen sind die Tablets sofort einsatzbereit.
Die folgenden Schritte sind **optional** und nur noetig wenn du
individuelle Anpassungen pro Tablet brauchst.

---

## Optionale Anpassungen

### Computername aendern

Standardmaessig haben alle geklonten Tablets den gleichen Windows-Computernamen.
Das ist **kein Problem** solange die Tablets nie im gleichen Netzwerk sind
(und das sind sie nicht - jedes hat seinen eigenen Hotspot).

Falls du trotzdem individuelle Namen willst (z.B. fuer Inventar):

1. Kopiere `set_computername.bat` auf das Tablet
2. Rechtsklick > "Als Administrator ausfuehren"
3. Namen eingeben (z.B. `FEXOBOX-001`)
4. Tablet startet neu

### config.json anpassen

Falls ein bestimmtes Tablet andere Einstellungen braucht
(z.B. anderen Drucker, andere Kamera):

1. Oeffne `C:\FexoBooth\config.json` mit Notepad
2. Gewuenschte Einstellungen aendern
3. Speichern
4. FexoBooth neu starten

### Windows-Updates

Die geklonten Tablets haben den Update-Stand des Referenz-Tablets.
Fuer spaetere Windows-Updates:
- Internet anschliessen
- Einstellungen > Update > Nach Updates suchen
- Updates installieren und neustarten

**Hinweis:** Windows-Updates sind optional. Die Tablets laufen im Offline-Hotspot-Modus
und brauchen keine regelmaessigen Updates.

---

## FexoBooth-Updates (ohne neu zu klonen!)

Fuer Software-Updates musst du NICHT neu klonen!
Es gibt zwei Wege:

### Weg 1: Ueber das Service-Menu (empfohlen)
1. Internet am Tablet anschliessen (WLAN oder USB-Ethernet)
2. FexoBooth starten
3. Service-PIN eingeben: **6588**
4. "Software aktualisieren" druecken
5. Update wird automatisch heruntergeladen und installiert

### Weg 2: Per USB-Stick
1. `update_from_github.bat` auf einen USB-Stick kopieren
2. Am Tablet ausfuehren
3. Laedt das neueste Release von GitHub herunter
