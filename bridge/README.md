# FexoNikonBridge

Unsichtbarer Hintergrundprozess für Nikon-DSLR-Steuerung in FexoBooth V2
(Zielkamera: Nikon D3300, weitere Nikon-Modelle möglich).

## Warum eine eigene Bridge?

- Das **offizielle Nikon-SDK unterstützt die D3xxx-Serie nicht** (kein MD3-Modul,
  verifiziert auf sdk.nikonimaging.com, Stand 2026-07-02). NikonCSWrapper & Co.
  brauchen genau diese Module → Sackgasse.
- Der frühere **digiCamControl-App-Ansatz ist verworfen**: sichtbares GUI-Fenster
  beim Autostart + Webserver (Port 5513), der per Standardinstallation nie
  aktiviert ist.
- dslrBooth unterstützt die D3300 inkl. LiveView — nachweislich über **rohes
  PTP/MTP per USB**, nicht über das Nikon-SDK. Genau das macht diese Bridge.

## Technik

- **Motor:** [CameraControl.Devices](https://www.nuget.org/packages/CameraControl.Devices)
  (Kern von [digiCamControl](https://github.com/dukus/digiCamControl), **MIT-Lizenz**).
  Nikon-Steuerung über Vendor-PTP-Opcodes (LiveView `0x9201`/`0x9203`,
  Capture `0x90C0`) via Windows-WPD-API (`WPD_COMMAND_MTP_EXT_EXECUTE_COMMAND_*`).
  Kein Treibertausch, kein Nikon-SDK, kein Fenster. Die D3300 ist in der
  Bibliothek explizit gemappt (`CameraDeviceManager`: `"D3300"` → `NikonD600Base`).
- **Prozessmodell:** FexoBooth startet `FexoNikonBridge.exe` mit
  `CREATE_NO_WINDOW` und spricht JSON über stdin/stdout (Binärdaten
  längenpräfixiert). Keine Ports → keine Firewall-Dialoge, kein
  Webserver-Aktivierungsschritt.
- **Ziel-Framework:** .NET Framework 4.8 (auf Windows 10/11 vorinstalliert,
  keine zusätzliche Runtime auf den Tablets nötig).

## Protokoll

Eine Anfrage gleichzeitig. Anfrage = JSON-Zeile auf stdin, Antwort = JSON-Zeile
auf stdout; Binärantworten (JPEG) tragen `"len"` im Header und liefern die
Rohbytes direkt nach der Header-Zeile.

| Kommando   | Antwort |
|------------|---------|
| `ping`     | `{"ok":true,"bridge":"FexoNikonBridge","version":"..."}` |
| `diag`     | `{"ok":true,"diagnostics":{...}}` (read-only, kein Scan) |
| `list`     | `{"ok":true,"cameras":[{"name":"...","serial":"..."}]}` |
| `init`     | `{"ok":true,"camera":"Nikon D3300"}` (verbindet Kamera, CaptureInSdRam) |
| `lv_start` | `{"ok":true}` |
| `frame`    | `{"ok":true,"len":N}` + N Bytes JPEG (LiveView-Frame) |
| `capture`  | `{"ok":true,"len":N}` + N Bytes JPEG (Vollauflösung, in den RAM) |
| `lv_stop`  | `{"ok":true}` |
| `release`  | `{"ok":true}` |
| `quit`     | `{"ok":true}` + Prozess beendet sich |

Fehler: `{"ok":false,"error":"..."}` (ohne `len`, ohne Binärdaten).

FexoBooth startet Bridge 0.2.0 im Developer Mode zusaetzlich mit
`--developer-diagnostics`. Nur dann werden interne Library-Events,
Konsolenausgaben und Scan-Messwerte begrenzt gepuffert. Im normalen Betrieb
bleibt der bisherige Pfad aktiv und verwirft Fremdausgaben weiterhin. `diag`
liest ausschliesslich vorhandenen Zustand und erzeugt keinen DeviceManager.

## Bauen

Der lokale `build_installer.bat` und **GitHub Actions** bauen die Bridge vor
jedem Installer frisch und fuehren danach den Protokolltest aus. Ein alter
Build unter `bin/Release` wird nicht mehr unbemerkt verpackt. Der lokale
Installer setzt deshalb das .NET SDK 8 voraus. Manueller Build:

```
dotnet build bridge/FexoNikonBridge/FexoNikonBridge.csproj -c Release --no-incremental
python tools/nikon_bridge_protocol_test.py
```

Output: `bridge/FexoNikonBridge/bin/Release/net48/` (EXE + abhängige DLLs —
**alles** muss zusammen deployed werden, Zielordner auf der Box:
`C:\FexoBooth\bridge\`).

## Status

- [x] Protokoll + Python-Client (`src/camera/nikon.py`) fertig
- [x] Erster Build erfolgreich (lokal, .NET SDK 8, 2026-07-02, 0 Fehler) —
  ping/list/init/quit gegen echte EXE verifiziert, Python-Client 8/8 OK
- [x] Hardware-Test mit echter D3300: LiveView + 6000x4000-Capture; spaeterer
  Langlauf mit 470 von 470 Aufnahmen erfolgreich (Juli 2026)
- [x] Bridge 0.2.0: read-only `diag`, begrenzte interne WPD-/WIA-/Console-
  Diagnose und Protokolltest fuer Developer- und Produktionspfad; Sammlung
  nur im Developer Mode aktiviert
- [ ] Aktuellen Regressionstest auf Box 252 mit 2.4.63 auswerten: Windows-PnP,
  Library-Ausnahme, Scanstatus und Bridge-Dateihashes
- [ ] Erst bei belegtem Library-Problem einen Source-Build aus
  dukus/digiCamControl pruefen (Solution `CameraControlDevices.sln`)
