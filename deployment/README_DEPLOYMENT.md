# FexoBooth Tablet-Klonen - Komplettanleitung

## Was macht dieses System?

Du richtest **EIN Tablet** perfekt ein (das "Referenz-Tablet").
Dann erstellst du ein **Abbild (Image)** davon.
Dieses Image spielst du auf alle anderen **199 Tablets** auf.

**Ergebnis:** Alle 200 Tablets sind identisch konfiguriert - FexoBooth, Hotspot, Autostart, alles fertig.

---

## Was du brauchst

| Was | Wozu | Wo besorgen |
|-----|------|-------------|
| 1x Lenovo Miix 310 | Referenz-Tablet einrichten | Aus deinem Bestand |
| 1-4x USB-Stick **32 GB** | Bootfaehiger Klon-Stick | USB 3.0 empfohlen (schneller) |
| 1x USB-OTG-Hub | Miix 310 hat nur 1 Port | Amazon/Elektronikmarkt |
| FexoBooth_Setup_2.0.exe | Auf Referenz-Tablet installieren | `installer_output/` im Projekt |
| Internet (einmalig) | Clonezilla herunterladen | Auf irgendeinem PC |
| Bueroklammer | BIOS-Zugang am Miix 310 | Schreibtischschublade |

---

## Ablauf (4 Schritte)

```
Schritt 1          Schritt 2          Schritt 3          Schritt 4
┌──────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐
│ Referenz │      │ USB-Stick│      │  Image   │      │ Tablets  │
│  Tablet  │ ──>  │erstellen │ ──>  │erstellen │ ──>  │  klonen  │
│einrichten│      │(Clonez.) │      │(Capture) │      │(Restore) │
└──────────┘      └──────────┘      └──────────┘      └──────────┘
   einmalig          einmalig          einmalig        199x wiederholen
```

### Schritt 1: Referenz-Tablet einrichten
Ein Tablet perfekt konfigurieren: FexoBooth installieren, Hotspot einrichten, testen.
**Anleitung:** [01_referenz-tablet/ANLEITUNG_REFERENZ.md](01_referenz-tablet/ANLEITUNG_REFERENZ.md)

### Schritt 2: Bootfaehigen USB-Stick erstellen
Clonezilla herunterladen und einen bootfaehigen USB-Stick erstellen.
**Anleitung:** [02_usb-stick-erstellen/ANLEITUNG_USB.md](02_usb-stick-erstellen/ANLEITUNG_USB.md)

### Schritt 3: Image vom Referenz-Tablet erstellen
Vom USB-Stick booten und ein Abbild des Referenz-Tablets auf den Stick speichern.
**Anleitung:** [03_image-erstellen/ANLEITUNG_CAPTURE.md](03_image-erstellen/ANLEITUNG_CAPTURE.md)

### Schritt 4: Image auf andere Tablets aufspielen
Den gleichen USB-Stick in jedes Ziel-Tablet stecken und das Image aufspielen.
**Anleitung:** [04_tablets-klonen/ANLEITUNG_DEPLOY.md](04_tablets-klonen/ANLEITUNG_DEPLOY.md)

---

## Zeitaufwand

| Phase | Dauer |
|-------|-------|
| Referenz-Tablet einrichten | ~1 Stunde |
| USB-Stick erstellen | ~30 Minuten |
| Image erstellen (Capture) | ~15-30 Minuten |
| **Pro Tablet klonen** | **~15-20 Minuten** |
| 200 Tablets mit 1 Stick | ~67 Stunden (1 Person) |
| 200 Tablets mit 4 Sticks | ~17 Stunden (4 Personen) = **~2 Arbeitstage** |

**Tipp:** Kopiere das Image auf mehrere USB-Sticks. Dann koennen mehrere Leute gleichzeitig Tablets klonen!

---

## Haeufige Fragen

**Brauchen die Tablets unterschiedliche Computer-Namen?**
Nein. Jedes Tablet laeuft alleine mit eigenem Hotspot. Sie sprechen nie miteinander. Gleiche Namen sind kein Problem. Falls du doch individuelle Namen willst: [05_nach-dem-klonen/set_computername.bat](05_nach-dem-klonen/set_computername.bat)

**Was ist mit der Windows-Lizenz?**
Die Lenovo Miix 310 haben eine OEM-Lizenz im BIOS gespeichert. Windows aktiviert sich automatisch auf identischer Hardware. Kein Problem.

**Wie gross wird das Image?**
Ca. 8-12 GB (komprimiert). Passt locker auf einen 32 GB Stick neben Clonezilla (~500 MB).

**Kann ich spaeter Updates einspielen ohne neu zu klonen?**
Ja! Ueber das FexoBooth Service-Menu (PIN 6588) > "Software aktualisieren" oder per `update_from_github.bat`. Das Klon-System ist nur fuer die Ersteinrichtung.

**Was passiert mit den Fotos auf einem geklonten Tablet?**
Das Referenz-Tablet wird vor dem Klonen aufgeraeumt (keine Fotos). Die geklonten Tablets starten also sauber ohne Bilder. Im laufenden Betrieb werden Fotos in `C:\FexoBooth\BILDER\` gespeichert - das ueberlebt natuerlich.

**Muss ich die BIOS-Einstellung an jedem Tablet aendern?**
Ja, beim ersten Mal muss an jedem Tablet Secure Boot deaktiviert und USB Boot aktiviert werden. Das dauert ~2 Minuten pro Tablet und muss nur einmal gemacht werden.

---

## Technische Details

| Detail | Wert |
|--------|------|
| Klon-Software | Clonezilla Live (Open Source) |
| Image-Format | Partclone (komprimiert mit zstd) |
| Ziel-Hardware | Lenovo Miix 310 (eMMC 32/64 GB) |
| BIOS-Zugang | Novo-Button (Pinhole an der Seite) |
| USB-Stick Format | FAT32, MBR |
| Sysprep | NICHT noetig (standalone Tablets) |
