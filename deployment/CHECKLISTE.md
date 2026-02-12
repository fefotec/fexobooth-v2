# FexoBooth Deployment - Druckbare Checkliste

Drucke diese Seite aus und hake ab waehrend du arbeitest.

---

## Phase 1: Referenz-Tablet einrichten

- [ ] Windows aufgeraeumt (Updates installiert, unnoetige Apps entfernt)
- [ ] FexoBooth_Setup_2.0.exe ausgefuehrt
- [ ] FexoBooth startet und laeuft unter `C:\FexoBooth\`
- [ ] Hotspot eingerichtet (`einmalig_hotspot_einrichten.bat` als Admin)
- [ ] Hotspot "fexobox-gallery" mit Handy sichtbar
- [ ] config.json fuer Produktion angepasst (nicht Dev-Modus!)
- [ ] FexoBooth Autostart funktioniert (Neustart getestet)
- [ ] Kamera funktioniert
- [ ] Foto-Workflow komplett getestet
- [ ] BILDER-Ordner geleert (Singles + Prints)
- [ ] Logs geleert
- [ ] Papierkorb geleert
- [ ] Datentraegerbereinigung ausgefuehrt (cleanmgr)
- [ ] `post_install_check.bat` ausgefuehrt - alle Checks GRUEN
- [ ] Tablet HERUNTERGEFAHREN (nicht Neustart!)

---

## Phase 2: USB-Stick erstellen

- [ ] USB-Stick 32 GB+ bereit (leer, USB 3.0 empfohlen)
- [ ] `create_usb.bat` ausgefuehrt (Clonezilla + Rufus heruntergeladen)
- [ ] Rufus: Clonezilla auf USB-Stick geschrieben
- [ ] `custom-ocs/` Ordner auf USB-Stick kopiert (nach `live/`)
- [ ] GRUB-Bootmenue angepasst (grub_menu_patch.txt Eintraege kopiert)

---

## Phase 3: Image erstellen (Capture)

- [ ] USB-Stick + OTG-Hub am Referenz-Tablet angeschlossen
- [ ] BIOS: Secure Boot DEAKTIVIERT
- [ ] BIOS: USB Boot AKTIVIERT
- [ ] Vom USB-Stick gebootet
- [ ] "FexoBooth IMAGE ERSTELLEN" gewaehlt
- [ ] Capture durchgelaufen (ca. 15-30 Min)
- [ ] Image auf USB-Stick vorhanden (Ordner `fexobooth-image-YYYYMMDD`)
- [ ] Image-Groesse geprueft (sollte 8-12 GB sein)

---

## Phase 4: Tablets klonen

### Einmalig pro Tablet:
- [ ] BIOS: Secure Boot deaktiviert, USB Boot aktiviert

### Pro Tablet wiederholen:
- [ ] USB-Stick eingesteckt
- [ ] Vom USB-Stick gebootet
- [ ] "FexoBooth IMAGE AUFSPIELEN" gewaehlt
- [ ] Restore bestaetigt
- [ ] Gewartet bis fertig (~15-20 Min)
- [ ] Tablet neu gestartet
- [ ] FexoBooth startet automatisch
- [ ] USB-Stick entfernt, naechstes Tablet

---

## Fortschritt Tablets (Strichliste)

```
Tablet-Nr. | Erledigt | Bemerkung
-----------|----------|----------
001        |   [ ]    |
002        |   [ ]    |
003        |   [ ]    |
004        |   [ ]    |
005        |   [ ]    |
...        |   ...    |
```

**Tipp:** Nummeriere die Tablets (z.B. Aufkleber auf der Rueckseite) um den Ueberblick zu behalten!
