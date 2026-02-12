# Schritt 3: Image vom Referenz-Tablet erstellen

Du bootest das Referenz-Tablet vom USB-Stick und erstellst ein Abbild (Image).
Dieses Image wird auf dem USB-Stick gespeichert.

---

## Was du brauchst

- Das fertig eingerichtete Referenz-Tablet (heruntergefahren!)
- Den vorbereiteten USB-Stick (mit Clonezilla)
- Einen USB-OTG-Hub (der Miix 310 hat nur 1 Micro-USB Port)
- Optional: USB-Tastatur (erleichtert die Bedienung)

---

## BIOS-Einstellungen (einmalig pro Tablet)

Das Lenovo Miix 310 muss so eingestellt werden, dass es vom USB-Stick booten kann.
**Das muss nur EINMAL pro Tablet gemacht werden.**

### BIOS oeffnen:

1. Tablet **komplett ausschalten** (nicht Ruhezustand!)
2. Den **Novo-Button** finden: Ein kleines Pinhole an der Seite des Tablets
   (neben den Lautstaerke-Tasten, oft mit einem kleinen Pfeil-Symbol markiert)
3. Mit einer **Bueroklammer** den Novo-Button druecken und halten
4. Das Tablet startet in ein Menue

### Im Novo-Menue:

Waehle **"BIOS Setup"** (mit Pfeiltasten + Enter)

### Im BIOS:

1. Navigiere zu **Security** (Pfeiltasten)
   - **Secure Boot** → auf **Disabled** setzen

2. Navigiere zu **Boot**
   - **USB Boot** → auf **Enabled** setzen
   - **Boot Priority** → USB-Stick an erste Stelle setzen (optional)

3. **F10** druecken → Speichern und Beenden

---

## Image erstellen

### 1. USB-Stick anschliessen

- USB-OTG-Hub an den Micro-USB Port des Tablets anschliessen
- USB-Stick in den Hub stecken
- Optional: USB-Tastatur in den Hub stecken

### 2. Vom USB-Stick booten

**Methode A (empfohlen):** Novo-Button
1. Tablet ausschalten
2. Novo-Button mit Bueroklammer druecken
3. Im Menue: **"Boot Menu"** waehlen
4. USB-Stick auswaehlen

**Methode B:** Direkt booten
- Tablet einschalten und sofort **F12** druecken (funktioniert nicht immer)

### 3. Im Clonezilla-Bootmenue

Du siehst ein Menue mit diesen Optionen:

```
┌─────────────────────────────────────────────┐
│  FexoBooth IMAGE ERSTELLEN                  │  ← DAS waehlen!
│  FexoBooth IMAGE AUFSPIELEN                 │
│  Clonezilla Live (Experten-Modus)           │
└─────────────────────────────────────────────┘
```

Waehle **"FexoBooth IMAGE ERSTELLEN"** mit den Pfeiltasten und druecke Enter.

### 4. Warten

- Clonezilla bootet (schwarzer Bildschirm mit Text, das ist normal)
- Das Script erkennt automatisch die eMMC-Festplatte
- Du wirst einmal gefragt ob du fortfahren willst → **Y** druecken + Enter
- Der Capture-Vorgang laeuft (~15-30 Minuten je nach Datenmenge)
- Fortschrittsanzeige mit Prozent und geschaetzter Restzeit

### 5. Fertig!

Nach Abschluss startet das Tablet automatisch neu.
Das Image liegt jetzt auf dem USB-Stick unter:

```
USB-Stick:\home\partimag\fexobooth-image-YYYYMMDD\
```

(YYYYMMDD = heutiges Datum)

---

## Image pruefen

Stecke den USB-Stick in einen PC und pruefe:

1. Ordner `home\partimag\fexobooth-image-YYYYMMDD\` existiert
2. Darin mehrere Dateien (z.B. `mmcblk0-pt.sf`, `mmcblk0p1.ext4-ptcl-img.zst.*`)
3. Gesamtgroesse: ca. 8-12 GB

---

## Haeufige Probleme

**Tablet bootet nicht vom USB-Stick:**
- Secure Boot deaktiviert? (BIOS pruefen)
- USB Boot aktiviert? (BIOS pruefen)
- USB-Stick richtig erkannt? (in BIOS Boot-Menu sichtbar?)
- USB-Hub funktioniert? (anderen Hub versuchen)
- USB-Stick korrekt erstellt? (Rufus nochmal ausfuehren)

**"Keine Festplatte gefunden" Fehler:**
- Normal wenn eMMC als `/dev/mmcblk0` erkannt wird (das Script sucht automatisch)
- Falls trotzdem Fehler: Im Experten-Modus manuell `mmcblk0` waehlen

**Capture bricht ab:**
- USB-Stick voll? (32 GB reicht normalerweise)
- USB-Verbindung stabil? (Hub wackelt nicht?)
- Nochmal versuchen

**Bildschirm bleibt schwarz nach Boot:**
- Warten! Clonezilla braucht 30-60 Sekunden zum Starten
- Falls nach 2 Minuten nichts passiert: Tablet aus/ein, nochmal vom USB booten
