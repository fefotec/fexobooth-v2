# Schritt 4: Image auf Tablets aufspielen

Jetzt kommt der Teil der 199 mal wiederholt wird.
Jedes Ziel-Tablet wird vom USB-Stick gebootet und das Image aufgespielt.

**ACHTUNG:** Alle Daten auf dem Ziel-Tablet werden ueberschrieben!

---

## Was du brauchst

- USB-Stick mit dem FexoBooth-Image (aus Schritt 3)
- USB-OTG-Hub
- Bueroklammer (fuer Novo-Button)
- Optional: Mehrere USB-Sticks mit dem Image (fuer paralleles Arbeiten)

---

## Pro Tablet: Ablauf (~15-20 Minuten)

### 1. BIOS einstellen (nur beim allerersten Mal pro Tablet)

Falls das Tablet noch nie vom USB gebootet hat:
1. Novo-Button mit Bueroklammer druecken
2. "BIOS Setup" waehlen
3. Security > Secure Boot > **Disabled**
4. Boot > USB Boot > **Enabled**
5. F10 > Speichern

**Das muss nur EINMAL pro Tablet gemacht werden!**

### 2. USB-Stick anschliessen

- USB-Hub an Micro-USB anschliessen
- USB-Stick einstecken

### 3. Vom USB-Stick booten

1. Novo-Button druecken (Bueroklammer)
2. "Boot Menu" waehlen
3. USB-Stick auswaehlen

### 4. Image aufspielen

Im Bootmenue:

```
┌─────────────────────────────────────────────┐
│  FexoBooth IMAGE ERSTELLEN                  │
│  FexoBooth IMAGE AUFSPIELEN                 │  ← DAS waehlen!
│  Clonezilla Live (Experten-Modus)           │
└─────────────────────────────────────────────┘
```

Waehle **"FexoBooth IMAGE AUFSPIELEN"**

### 5. Bestaetigen

- Das Script zeigt an welches Image aufgespielt wird
- Es fragt ob du sicher bist → **Y** druecken + Enter
- **LETZTE CHANCE!** Ab hier werden alle Daten auf dem Tablet ueberschrieben

### 6. Warten

- Fortschrittsanzeige mit Prozent und Restzeit
- Dauer: ca. 10-20 Minuten (abhaengig von USB-Geschwindigkeit)
- **Nicht den USB-Stick entfernen waehrend es laeuft!**

### 7. Fertig!

- Tablet startet automatisch neu
- Windows faehrt hoch
- FexoBooth startet automatisch
- Hotspot "fexobox-gallery" ist aktiv
- **USB-Stick entfernen** und zum naechsten Tablet

---

## Tipps fuer effizientes Arbeiten

### Mehrere USB-Sticks verwenden

Mit 4 USB-Sticks und 4 Personen schafft ihr ~12 Tablets pro Stunde:

1. Erstelle den ersten USB-Stick wie beschrieben
2. Kopiere den **gesamten Inhalt** des fertigen USB-Sticks (mit Image) auf weitere Sticks:
   - Neuen 32 GB Stick mit Rufus + Clonezilla beschreiben
   - custom-ocs/ draufkopieren + GRUB anpassen (wie bei Stick 1)
   - Den `home\partimag\fexobooth-image-YYYYMMDD\` Ordner vom ersten Stick kopieren
3. Jeder Stick ist unabhaengig einsetzbar

### Fliessband-System

Am schnellsten geht es als Fliessband:

```
Person 1: BIOS einstellen + USB einstecken + booten
Person 2: Image aufspielen ueberwachen
Person 3: Fertige Tablets pruefen + einpacken
```

### Tablet-Nummerierung

Klebe auf jedes Tablet einen kleinen Aufkleber mit einer Nummer (001-200).
So behaltst du den Ueberblick welche Tablets schon geklont sind.

---

## Zeitschaetzung

| Szenario | Tablets/Stunde | Gesamt fuer 200 |
|----------|----------------|-----------------|
| 1 Person, 1 Stick | ~3 | ~67 Stunden |
| 1 Person, 2 Sticks | ~5 | ~40 Stunden |
| 2 Personen, 4 Sticks | ~10 | ~20 Stunden |
| 4 Personen, 4 Sticks | ~12 | ~17 Stunden (~2 Tage) |

---

## Log-Dateien bei Problemen

**Alle Deploy-Vorgaenge werden automatisch geloggt!**

Die Log-Dateien liegen auf dem USB-Stick auf der Partition **FEXODATEN**:

```
FEXODATEN:\deploy-logs\deploy-YYYYMMDD-HHMMSS.log
```

Jeder Klon-Versuch erzeugt eine eigene Datei mit Zeitstempel. Die Logs enthalten:
- Erkannte USB- und Ziel-Disk
- Ziel-Disk Groesse in Sektoren und Bytes (wichtig bei "Disk too small"!)
- Komplette Clonezilla-Ausgabe inkl. Fehlermeldungen
- Exit-Code von `ocs-sr`
- Status (ERFOLG / FEHLER) am Ende

**Wenn ein Tablet nicht bootet oder der Klon fehlschlaegt:**
1. USB-Stick ins Windows am PC stecken
2. FEXODATEN-Laufwerk oeffnen
3. `deploy-logs\` Ordner → neueste Datei ansehen (Texteditor)
4. Am Ende der Datei steht der Status und der Fehler

Fuer das Capture (Image-Erstellen) gibt es das gleiche System unter `FEXODATEN:\capture-logs\`.

---

## Haeufige Probleme

**"Kein FexoBooth-Image gefunden":**
- Wurde Schritt 3 (Capture) durchgefuehrt?
- Pruefe ob `home\partimag\fexobooth-image-*\` auf dem Stick existiert
- Richtigen USB-Stick eingesteckt?

**Restore bricht ab mit "Disk too small":**
- Das Script hat drei Automatismen gegen dieses Problem:
  1. **Pre-Wipe** entfernt OEM-/Recovery-/ebackup-Partitionen vor dem Restore
  2. **`-icds` Flag** ignoriert minimale Groessenunterschiede der eMMC
  3. **Post-Expand** streckt C nach dem Restore auf volle Disk-Groesse
- **Wenn es trotzdem fehlschlaegt**: Log in `FEXODATEN:\deploy-logs\` oeffnen. Dort steht die exakte Sektorzahl von Quelle und Ziel. Falls das Ziel wirklich deutlich kleiner ist (nicht nur wenige Sektoren): Referenz-Tablet mit **kleinstmoeglicher eMMC** (32 GB) verwenden und Image neu capturen
- Nach Schritt 1 der Automatismen (Pre-Wipe) werden bestehende Partitionen auf dem Ziel-Tablet **unwiderruflich geloescht** - das ist gewollt. Auch "ebackup"-/Recovery-Partitionen von Lenovo sind danach weg und C nutzt nach Post-Expand die volle Disk-Groesse.

**Tablet startet nach Restore nicht:**
- Nochmal vom USB booten und Image nochmal aufspielen
- BIOS Boot-Reihenfolge pruefen (eMMC/Windows Boot Manager an erster Stelle)
- Log pruefen: Wenn Post-Expand eine Warnung geworfen hat, repariert Windows sich meist beim ersten Boot selbst (chkdsk automatisch)

**FexoBooth startet nicht automatisch nach dem Klonen:**
- Das ist selten aber moeglich wenn Windows den Autostart-Pfad anders behandelt
- Loesung: FexoBooth manuell starten, dann im Admin-Menu Autostart pruefen

**USB-Stick wird sehr langsam:**
- USB 2.0 Sticks sind deutlich langsamer als USB 3.0
- Kein Problem, dauert nur laenger (~30 statt ~15 Minuten)

**Clonezilla landet am Ende in einem "Choose mode"-Menue (poweroff/reboot/cmd/...):**
- Bedeutet: `ocs-sr` wurde unterbrochen oder das eigene Script hat das Reboot-Kommando nicht erreicht
- Log in `FEXODATEN:\deploy-logs\` zeigt den Grund
- Im Notfall `reboot` waehlen und das Log am PC auslesen
