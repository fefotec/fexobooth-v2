# Schritt 2: Bootfaehigen USB-Stick erstellen

Der USB-Stick wird mit zwei Partitionen eingerichtet:
- **FEXOBOOT** (20 GB, FAT32) - Clonezilla bootfaehig + Image-Speicher
- **FEXODATEN** (Rest, NTFS) - Deployment-Dateien, Installer, Tools

---

## Was du brauchst

- 1x USB-Stick, mindestens **32 GB** (60 GB empfohlen, USB 3.0!)
- Einen Windows-PC mit **Administratorrechten**
- Internet (einmalig zum Herunterladen von Clonezilla)
- **ACHTUNG:** Alle Daten auf dem USB-Stick werden geloescht!

---

## Automatisch (empfohlen)

### 1. Clonezilla herunterladen

Fuehre `create_usb.bat` aus - laedt Clonezilla und Rufus in den `downloads/` Ordner.

Oder manuell herunterladen:
- https://clonezilla.org/downloads.php → **stable**, **amd64**, **zip** Format
- ZIP-Datei in `downloads/` ablegen (oder im Downloads-Ordner lassen)

### 2. Komplett-Script ausfuehren

**Rechtsklick** auf `prepare_usb_stick.bat` → **"Als Administrator ausfuehren"**

Das Script macht automatisch:
1. Findet die Clonezilla ZIP-Datei
2. Zeigt verfuegbare USB-Laufwerke an
3. Partitioniert den Stick (20 GB FAT32 + Rest NTFS)
4. Entpackt Clonezilla und macht den Stick bootfaehig
5. Kopiert die FexoBooth Klon-Scripts und GRUB-Menue
6. Kopiert Deployment-Dateien und Installer auf die Daten-Partition

### 3. USB-Stick testen

Stecke den USB-Stick in ein Tablet und versuche davon zu booten:
1. Tablet ausschalten
2. Novo-Button druecken (Pinhole an der Seite mit Bueroklammer)
3. "Boot Menu" waehlen
4. USB-Stick auswaehlen

Du solltest das Bootmenue mit den deutschen FexoBooth-Optionen sehen.

---

## Manuell (falls das Script nicht funktioniert)

### 1. Clonezilla herunterladen

- https://clonezilla.org/downloads.php → **stable**, **amd64**, **zip**

### 2. Stick partitionieren (Datentraegerverwaltung)

1. Win+R → `diskmgmt.msc`
2. USB-Stick finden (an der Groesse erkennen!)
3. Alle Partitionen loeschen (Rechtsklick → Volume loeschen)
4. Neues Volume 1: **20 GB**, **FAT32**, Label "FEXOBOOT"
5. Neues Volume 2: **Rest**, **NTFS**, Label "FEXODATEN"

### 3. Clonezilla entpacken

Die Clonezilla ZIP-Datei direkt auf die **FEXOBOOT** Partition entpacken:
- Rechtsklick auf ZIP → "Alle extrahieren" → FEXOBOOT Laufwerk auswaehlen
- Die Dateien muessen direkt im Root liegen (EFI/, live/, syslinux/, etc.)

### 4. Klon-Scripts kopieren

Den Ordner `custom-ocs/` kopieren nach `FEXOBOOT:\live\custom-ocs\`

### 5. Boot-Menue anpassen

1. `tools\grub_menu_patch.txt` oeffnen
2. Auf FEXOBOOT: `EFI\boot\grub.cfg` mit Notepad oeffnen
3. Inhalt von grub_menu_patch.txt **oben** einfuegen (bestehende Eintraege behalten)
4. Speichern

### 6. Deployment-Dateien kopieren

Auf die **FEXODATEN** Partition kopieren:
- Den ganzen `deployment/` Ordner
- `FexoBooth_Setup_2.0.exe` (aus installer_output/)
- `update_from_github.bat`

---

## Fertiger USB-Stick Aufbau

```
USB-Stick (60 GB, 2 Partitionen)
│
├── FEXOBOOT (20 GB, FAT32)
│   ├── EFI/                    (UEFI Boot-Dateien)
│   │   └── boot/
│   │       └── grub.cfg        (mit deutschen Menue-Eintraegen)
│   ├── live/                   (Clonezilla System)
│   │   ├── vmlinuz             (Linux Kernel)
│   │   ├── initrd.img          (Initramfs)
│   │   ├── filesystem.squashfs (Clonezilla)
│   │   └── custom-ocs/         (FexoBooth Klon-Scripts)
│   │       ├── custom-ocs-capture
│   │       └── custom-ocs-deploy
│   ├── syslinux/               (Legacy Boot)
│   └── home/
│       └── partimag/           (Image-Speicher, ~8-12 GB)
│
└── FEXODATEN (40 GB, NTFS)
    ├── deployment/             (Anleitungen + Scripts)
    ├── FexoBooth_Setup_2.0.exe (Installer)
    ├── fexobooth.zip           (OTA-Update ZIP)
    └── update_from_github.bat  (Update-Script)
```

---

## Haeufige Probleme

**"Script muss als Administrator ausgefuehrt werden":**
- Rechtsklick auf prepare_usb_stick.bat → "Als Administrator ausfuehren"

**Disk 0 Fehler:**
- Das Script verhindert das Formatieren von Disk 0 (= System-Festplatte)
- Waehle die richtige Disk-Nummer (steht in der Liste)

**Tablet bootet nicht vom USB:**
- Secure Boot muss deaktiviert sein (BIOS)
- USB Boot muss aktiviert sein (BIOS)
- Siehe BIOS-Anleitung in [03_image-erstellen/ANLEITUNG_CAPTURE.md](../03_image-erstellen/ANLEITUNG_CAPTURE.md)

**"custom-ocs" Scripts werden nicht gefunden:**
- Pruefe ob die Dateien unter `live/custom-ocs/` liegen
- Die Dateien muessen KEINE .txt oder .bat Endung haben
- Die Dateien muessen Linux-Zeilenenden haben (LF, nicht CRLF)

**FEXOBOOT oder FEXODATEN Laufwerk nicht sichtbar:**
- Windows 10 1703+ zeigt beide Partitionen automatisch
- Bei aelteren Windows-Versionen: Datentraegerverwaltung oeffnen und Laufwerksbuchstaben zuweisen
