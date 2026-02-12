# Schritt 1: Referenz-Tablet einrichten

Ein Lenovo Miix 310 wird als "Muster-Tablet" perfekt eingerichtet.
Von diesem Tablet wird spaeter ein Image erstellt und auf alle anderen kopiert.

---

## Was du brauchst

- 1x Lenovo Miix 310 (aus deinem Bestand)
- FexoBooth_Setup_2.0.exe (auf USB-Stick oder ueber Netzwerk)
- Internet (fuer Windows-Updates, optional)
- USB-Tastatur empfohlen (einfacher als Touchscreen)

---

## Schritt-fuer-Schritt

### 1. Windows aufraeuemen

Starte mit einem sauberen Windows. Entweder:
- **Option A:** Frisches Tablet verwenden (Werkseinstellungen)
- **Option B:** Vorhandenes Tablet zuruecksetzen: Einstellungen > Update > Wiederherstellung > "Diesen PC zuruecksetzen"

Nach dem Start:
- Windows-Updates installieren (optional, aber empfohlen)
- Unnoetige vorinstallierte Apps entfernen (Spiele, Office-Testversionen, etc.)
- Energieoptionen: "Bildschirm ausschalten" auf **Nie** setzen (wichtig fuer Photobooth!)
- Automatische Windows-Updates **deaktivieren** (verhindert ungewollte Neustarts):
  - Einstellungen > Update > Erweitert > Updates anhalten

### 2. FexoBooth installieren

1. `FexoBooth_Setup_2.0.exe` auf das Tablet kopieren (USB-Stick oder Netzwerk)
2. Doppelklick auf die EXE
3. Installationsort: `C:\FexoBooth\` (Standard beibehalten!)
4. **Autostart aktivieren** (Haken setzen im Installer)
5. Installation abschliessen

### 3. Hotspot einrichten

1. Oeffne `C:\FexoBooth\setup\einmalig_hotspot_einrichten.bat`
2. **Rechtsklick > "Als Administrator ausfuehren"**
3. Warte bis "Hotspot eingerichtet" erscheint
4. Pruefe mit deinem Handy: WLAN "fexobox-gallery" muss sichtbar sein

### 4. config.json anpassen

Oeffne `C:\FexoBooth\config.json` mit Notepad und pruefe:

```json
{
  "admin_pin": "3198",
  "start_fullscreen": true,
  "gallery_enabled": false,
  "performance_mode": true,
  "camera_type": "webcam",
  "camera_index": 0,
  "developer_mode": false
}
```

**Wichtig:**
- `start_fullscreen` muss `true` sein
- `developer_mode` muss `false` sein (oder nicht vorhanden)
- Pfade muessen **relativ** sein (z.B. `"assets/videos/start.mp4"`, NICHT `"C:/Git-Projects/..."`)
- Alle Einstellungen die fuer ALLE Tablets gelten hier setzen

### 5. Testen

1. **Neustart** des Tablets
2. FexoBooth muss automatisch starten (Fullscreen)
3. Foto-Workflow testen:
   - Startscreen > Foto machen > Filter > Drucken/Fertig
4. Mit Handy pruefen:
   - Mit "fexobox-gallery" WLAN verbinden
   - Browser oeffnen, Galerie sollte erreichbar sein (wenn aktiviert)

### 6. Aufraeumen (WICHTIG!)

Vor dem Image-Erstellen alles Unnoetige entfernen:

1. **FexoBooth-Daten loeschen:**
   - `C:\FexoBooth\BILDER\Single\` - alle Dateien loeschen
   - `C:\FexoBooth\BILDER\Prints\` - alle Dateien loeschen
   - `C:\FexoBooth\logs\` - alle Dateien loeschen
   - Falls vorhanden: `C:\FexoBooth\fexobooth_statistics.json` loeschen

2. **Windows aufraeumen:**
   - Papierkorb leeren
   - Datentraegerbereinigung: Win+R > `cleanmgr` > Alle Haken setzen > OK
   - Temporaere Dateien: Win+R > `%temp%` > Alles markieren > Loeschen
   - Browser-Verlauf loeschen (Edge: Strg+Shift+Entf)

3. **Festplattenbelegung pruefen:**
   - Rechtsklick auf C: > Eigenschaften
   - Sollte unter 20 GB belegt sein

### 7. Verifikation

Kopiere `post_install_check.bat` (aus dem `deployment/01_referenz-tablet/` Ordner) auf das Tablet und fuehre es aus.

Alle Checks muessen **GRUEN [OK]** sein. Falls ein Check **ROT [FEHLER]** zeigt, behebe das Problem zuerst.

### 8. Herunterfahren

**WICHTIG:** Das Tablet komplett **herunterfahren** (nicht Neustart, nicht Ruhezustand!).

Start > Ein/Aus > Herunterfahren

Das Tablet ist jetzt bereit fuer das Image-Erstellen (Schritt 3).

---

## Haeufige Probleme

**FexoBooth startet nicht automatisch:**
Pruefe ob der Autostart-Shortcut vorhanden ist:
`C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\FexoBooth.lnk`

**Hotspot nicht sichtbar:**
- Ist WLAN am Tablet eingeschaltet?
- Wurde das Script als Administrator ausgefuehrt?
- Nochmal ausfuehren: `einmalig_hotspot_einrichten.bat` als Admin

**"performance_mode" fehlt in config.json:**
Das ist OK - der Standardwert ist aktiv. Du kannst es manuell hinzufuegen wenn du sicher gehen willst.
