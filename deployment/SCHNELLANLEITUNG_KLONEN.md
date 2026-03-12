# FexoBooth Tablet-Klonen - Schnellanleitung

Kompakte Anleitung mit allen Tastenkombinationen.
Ein 64 GB USB-Stick reicht fuer alles (Clonezilla + Image).

---

## Was du brauchst

- 1x Lenovo Miix 310 als **Referenz-Tablet** (perfekt eingerichtet)
- 1x USB-Stick **64 GB** (USB 3.0 empfohlen)
- 1x USB-OTG-Hub (Miix 310 hat nur 1 Micro-USB Port)
- 1x Bueroklammer oder Nadel (fuer Novo-Button)
- Optional: USB-Tastatur (in den Hub stecken, erleichtert Bedienung)

---

## Uebersicht

```
Schritt 1           Schritt 2          Schritt 3          Schritt 4
Referenz-Tablet  →  USB-Stick       →  Image           →  Tablets
einrichten          erstellen          erstellen          klonen
(einmalig, ~1h)     (einmalig, ~30m)   (einmalig, ~20m)   (pro Tablet ~15m)
```

---

## Schritt 1: Referenz-Tablet einrichten

### 1.1 Windows aufraemen

- Windows-Updates installieren
- Unnoetige Apps entfernen (Spiele, Office-Test, etc.)
- Energieoptionen: Bildschirm ausschalten → **Nie**
- Automatische Updates pausieren

### 1.2 FexoBooth installieren

1. `FexoBooth_Setup_2.0.exe` auf das Tablet kopieren
2. Doppelklick → installiert nach `C:\FexoBooth\`
3. **Autostart-Haken setzen!**

### 1.3 Hotspot einrichten

1. Datei-Explorer oeffnen: `Win + E`
2. Navigiere zu `C:\FexoBooth\setup\`
3. Rechtsklick auf `einmalig_hotspot_einrichten.bat` → **Als Administrator ausfuehren**
4. Mit Handy pruefen: WLAN "fexobox-gallery" muss sichtbar sein

### 1.4 Config anpassen

1. Datei-Explorer: `C:\FexoBooth\config.json`
2. Rechtsklick → Oeffnen mit → **Editor (Notepad)**
3. Pruefen/Setzen:
   ```
   "start_fullscreen": true
   "developer_mode": false
   "performance_mode": true
   ```
4. Speichern: `Strg + S`

### 1.5 Testen

1. Tablet neustarten: `Win` → Ein/Aus → Neu starten
2. FexoBooth muss automatisch im Vollbild starten
3. Foto-Workflow einmal komplett durchspielen

### 1.6 Aufraeumen (WICHTIG!)

Damit das Image sauber und klein bleibt:

1. **FexoBooth-Daten loeschen:**
   - `C:\FexoBooth\BILDER\Single\` → alles markieren (`Strg + A`) → loeschen (`Entf`)
   - `C:\FexoBooth\BILDER\Prints\` → alles markieren → loeschen
   - `C:\FexoBooth\logs\` → alles markieren → loeschen

2. **Windows aufraeumen:**
   - Papierkorb leeren: Rechtsklick auf Papierkorb → Papierkorb leeren
   - Datentraegerbereinigung: `Win + R` → `cleanmgr` → `Enter` → alle Haken → OK
   - Temp-Dateien: `Win + R` → `%temp%` → `Enter` → `Strg + A` → `Entf`

3. **Pruefen:**
   - `post_install_check.bat` ausfuehren (liegt in `deployment\01_referenz-tablet\`)
   - Alle Checks muessen **[OK]** zeigen

### 1.7 Herunterfahren

**WICHTIG: Komplett herunterfahren, NICHT Neustart!**

`Win` → Ein/Aus → **Herunterfahren**

---

## Schritt 2: USB-Stick vorbereiten

Auf einem beliebigen Windows-PC (nicht auf dem Tablet):

### 2.1 Automatisch (empfohlen)

1. Im Projekt-Ordner: `deployment\02_usb-stick-erstellen\`
2. **Doppelklick** auf `create_usb.bat` → laedt Clonezilla + Rufus herunter
3. **Rechtsklick** auf `prepare_usb_stick.bat` → **Als Administrator ausfuehren**
   - Das Script partitioniert den Stick automatisch:
     - **FEXOBOOT** (20 GB, FAT32) → Clonezilla + Image-Speicher
     - **FEXODATEN** (Rest, NTFS) → Installer + Tools
   - Entpackt Clonezilla
   - Kopiert Klon-Scripts + Boot-Menue
4. Fertig! USB-Stick ist bootfaehig.

### 2.2 Manuell (falls Script nicht funktioniert)

1. **Clonezilla herunterladen:**
   - https://clonezilla.org/downloads.php
   - Waehle: **stable** → **amd64** → **zip**

2. **USB-Stick mit Rufus beschreiben:**
   - Rufus herunterladen: https://rufus.ie
   - Rufus starten → USB-Stick waehlen
   - "Startart": Klick auf AUSWAEHLEN → Clonezilla-ZIP waehlen
   - Partitionsschema: **MBR**
   - Dateisystem: **FAT32**
   - Klick auf **START**

3. **Klon-Scripts kopieren:**
   - Kopiere `deployment\02_usb-stick-erstellen\custom-ocs\` nach USB-Stick `\live\custom-ocs\`

4. **Boot-Menue anpassen:**
   - Oeffne auf dem USB-Stick: `EFI\boot\grub.cfg`
   - Oeffne im Projekt: `deployment\tools\grub_menu_patch.txt`
   - Inhalt von grub_menu_patch.txt **OBEN** in grub.cfg einfuegen
   - Bestehende Eintraege darunter lassen
   - Speichern

---

## Schritt 3: Image vom Referenz-Tablet erstellen

### 3.1 Anschliessen

- USB-OTG-Hub an den **Micro-USB Port** des Tablets
- USB-Stick in den Hub
- Optional: USB-Tastatur in den Hub

### 3.2 BIOS einstellen (einmalig pro Tablet)

```
┌──────────────────────────────────────────────────────────────┐
│  NOVO-BUTTON = kleines Loch an der Seite des Tablets        │
│  (neben den Lautstaerke-Tasten, kleines Pfeil-Symbol)       │
│                                                              │
│  Mit Bueroklammer reinstechen und kurz druecken!             │
└──────────────────────────────────────────────────────────────┘
```

1. Tablet muss **AUS** sein (komplett ausgeschaltet!)
2. **Bueroklammer in den Novo-Button** stechen → kurz druecken
3. Tablet startet → Novo-Menue erscheint
4. Mit Pfeiltasten: **"BIOS Setup"** waehlen → `Enter`

Im BIOS:

```
Schritt    Taste              Aktion
───────    ─────              ──────
1.         Pfeiltaste rechts  Navigiere zum Tab "Security"
2.         Pfeiltaste runter  "Secure Boot" auswaehlen
3.         Enter              Oeffnen → auf "Disabled" setzen → Enter
4.         Pfeiltaste rechts  Navigiere zum Tab "Boot"
5.         Pfeiltaste runter  "USB Boot" auswaehlen
6.         Enter              Auf "Enabled" setzen → Enter
7.         F10                Speichern und Beenden
8.         Enter              Bestaetigen (Yes)
```

Das Tablet startet neu. **Das muss nur EINMAL gemacht werden!**

### 3.3 Vom USB-Stick booten

1. Tablet **ausschalten**
2. **Novo-Button** mit Bueroklammer druecken
3. Novo-Menue erscheint:
   ```
   ┌─────────────────────────┐
   │  Normal Startup         │
   │  BIOS Setup             │
   │▸ Boot Menu              │  ← DAS waehlen!
   │  System Recovery        │
   └─────────────────────────┘
   ```
4. Pfeiltasten → **"Boot Menu"** → `Enter`
5. USB-Stick auswaehlen (z.B. "EFI USB Device" oder Stick-Name) → `Enter`

### 3.4 Image erstellen

Das Clonezilla-Bootmenue erscheint:

```
┌─────────────────────────────────────────────────────────────┐
│▸ FexoBooth IMAGE ERSTELLEN (Referenz-Tablet abbilden)       │  ← DAS!
│  FexoBooth IMAGE AUFSPIELEN (Tablet klonen)                 │
│  -------------------------------------------                │
│  Clonezilla Live (Experten-Modus)                           │
└─────────────────────────────────────────────────────────────┘
```

1. **"FexoBooth IMAGE ERSTELLEN"** waehlen → `Enter`
2. Warten bis Clonezilla hochgefahren ist (schwarzer Bildschirm mit Text, ~30-60 Sek.)
3. Es fragt: "Are you sure you want to continue?" → `Y` druecken → `Enter`
4. **Warten: ca. 15-30 Minuten** (Fortschrittsanzeige mit Prozent)
5. Tablet startet automatisch neu wenn fertig

### 3.5 Image pruefen

USB-Stick an einen PC stecken und pruefen:
- Ordner `home\partimag\fexobooth-image-XXXXXXXX\` existiert (XXXXXXXX = Datum)
- Gesamtgroesse: ca. 8-12 GB
- Mehrere Dateien darin (z.B. `mmcblk0-pt.sf`, `mmcblk0p1.*.zst.*`)

---

## Schritt 4: Image auf Tablets aufspielen (WIEDERHOLEN)

**Diesen Schritt fuer jedes Tablet wiederholen!**

### Pro Tablet (~15-20 Minuten):

```
Schritt  Aktion                                    Tastenkombination
──────   ──────                                    ─────────────────
1.       Tablet ausschalten                        Win → Ein/Aus → Herunterfahren
2.       USB-Hub + Stick anschliessen              (Hardware)
3.       Novo-Button druecken                      Bueroklammer ins Loch
4.       "Boot Menu" waehlen                       Pfeiltasten → Enter
5.       USB-Stick waehlen                         Pfeiltasten → Enter
6.       "FexoBooth IMAGE AUFSPIELEN" waehlen      Pfeiltasten → Enter
7.       Bestaetigen                               Y → Enter
8.       Warten (~15 Min)                          (nichts druecken!)
9.       Tablet startet automatisch neu             USB-Stick rausziehen
10.      FexoBooth startet automatisch              Fertig! Naechstes Tablet.
```

### BIOS nur beim ERSTEN Mal:

Falls das Tablet noch nie vom USB gebootet hat, vorher einmalig:

1. Novo-Button → "BIOS Setup" → `Enter`
2. `Pfeiltaste rechts` → **Security** → `Pfeiltaste runter` → **Secure Boot** → `Enter` → **Disabled** → `Enter`
3. `Pfeiltaste rechts` → **Boot** → `Pfeiltaste runter` → **USB Boot** → `Enter` → **Enabled** → `Enter`
4. `F10` → `Enter` (Speichern)

---

## FAQ / Problemloesung

### "Wo ist der Novo-Button?"

An der **Seite des Tablets** (nicht am Tastatur-Dock!). Kleines Loch neben den Lautstaerke-Tasten, manchmal mit einem gebogenen Pfeil-Symbol markiert. Du brauchst eine Bueroklammer oder Nadel.

### "Tablet bootet nicht vom USB-Stick"

| Pruefe                  | Loesung                                          |
|-------------------------|--------------------------------------------------|
| Secure Boot deaktiviert? | BIOS → Security → Secure Boot → Disabled        |
| USB Boot aktiviert?      | BIOS → Boot → USB Boot → Enabled                |
| USB-Hub funktioniert?    | Anderen Hub versuchen                            |
| Stick richtig erstellt?  | Rufus nochmal ausfuehren                         |

### "Bildschirm bleibt schwarz nach USB-Boot"

**30-60 Sekunden warten!** Clonezilla braucht Zeit zum Starten.
Falls nach 2 Minuten nichts passiert: Tablet lange aus/ein-Taste druecken (8 Sek.) zum Ausschalten, dann nochmal Novo-Button.

### "Kein FexoBooth-Image gefunden"

Wurde Schritt 3 (Capture) durchgefuehrt? Pruefe ob der Ordner `home\partimag\fexobooth-image-*` auf dem Stick existiert.

### "Disk too small"

Das Ziel-Tablet hat weniger Speicher als das Referenz-Tablet. Loesung: Referenz-Tablet mit der **kleinsten** eMMC (32 GB) verwenden.

### "Kann ich eine externe SSD statt USB-Stick nutzen?"

Ja, funktioniert genauso - ist sogar **schneller**! Einfach die SSD statt des USB-Sticks in den OTG-Hub stecken. Clonezilla erkennt sie automatisch als Speicher fuer das Image.

### "Passt das alles auf einen 64 GB Stick?"

Ja! Clonezilla braucht ~500 MB, das Image ~8-12 GB. Bei 64 GB bleiben noch ~50 GB frei.

### "Laeuft Clonezilla wirklich vom gleichen Stick?"

Ja. Clonezilla ist ein Linux-System das sich beim Booten **komplett ins RAM** laedt. Nach dem Start ist der Stick frei und wird nur noch als normaler Datentraeger fuer die Images genutzt. Das ist kein Windows — kein Konflikt.

---

## Zeitplanung

| Setup                           | Tablets pro Stunde | Fuer 200 Tablets |
|---------------------------------|--------------------|------------------|
| 1 Person, 1 Stick               | ~3                 | ~67 Stunden      |
| 1 Person, 2 Sticks              | ~5                 | ~40 Stunden      |
| 2 Personen, 2 Sticks            | ~6                 | ~33 Stunden      |
| 4 Personen, 4 Sticks            | ~12                | ~17 Stunden      |

**Tipp:** Image-Ordner vom fertigen Stick auf weitere Sticks kopieren → mehrere Leute koennen parallel klonen!
