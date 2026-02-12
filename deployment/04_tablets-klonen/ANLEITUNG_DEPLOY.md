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

## Haeufige Probleme

**"Kein FexoBooth-Image gefunden":**
- Wurde Schritt 3 (Capture) durchgefuehrt?
- Pruefe ob `home\partimag\fexobooth-image-*\` auf dem Stick existiert
- Richtigen USB-Stick eingesteckt?

**Restore bricht ab mit "Disk too small":**
- Das Ziel-Tablet hat eine kleinere eMMC als das Referenz-Tablet
- Loesung: Referenz-Tablet mit kleinstmoeglicher eMMC verwenden (32 GB)

**Tablet startet nach Restore nicht:**
- Nochmal vom USB booten und Image nochmal aufspielen
- BIOS Boot-Reihenfolge pruefen (eMMC/Windows Boot Manager an erster Stelle)

**FexoBooth startet nicht automatisch nach dem Klonen:**
- Das ist selten aber moeglich wenn Windows den Autostart-Pfad anders behandelt
- Loesung: FexoBooth manuell starten, dann im Admin-Menu Autostart pruefen

**USB-Stick wird sehr langsam:**
- USB 2.0 Sticks sind deutlich langsamer als USB 3.0
- Kein Problem, dauert nur laenger (~30 statt ~15 Minuten)
