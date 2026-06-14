# FexoBox App API

Stand: 2026-06-14

Diese Box-Version bereitet die spaetere Smartphone-App vor. Die App soll keine
Browser-Galerie oeffnen, sondern lokal im Fotobox-Hotspot mit der Box sprechen.

## QR-Payload

Der sichtbare QR-Code enthaelt keinen Browser-Link mehr, sondern ein kurzes
Custom-Scheme:

```text
fexobox://g?v=1&a=http://192.168.137.1:8080/api/v1&t=<token>&c=123456
```

Parameter:

- `v`: QR-Schema-Version, aktuell `1`
- `a`: Base URL der lokalen API, z. B. `http://192.168.137.1:8080/api/v1`
- `t`: Pairing-Token, muss die App bei privaten API-Endpunkten mitsenden
- `c`: 6-stelliger Event-Code fuer die App, falls als Event-PIN in den Buchungsdaten vorhanden; kein Auth-Token

Optionale/fallback Parameter:

- `l`: Locale der Box, z. B. `de-DE`
- `b`: dreistellige Box-ID
- `e`: aktuelle Booking-ID, wird nur statt `c` genutzt, wenn kein Event-Code vorhanden ist
- `s`: Hotspot-SSID
- `p`: Hotspot-Passwort

Die App kann den QR direkt selbst scannen. Alternativ kann sie das Custom-Scheme
registrieren, damit die Smartphone-Kamera die App direkt oeffnet.

## Auth

Private API-Endpunkte erwarten das Pairing-Token aus dem QR-Code.

Erlaubte Varianten:

```http
X-FexoBox-Token: <token>
Authorization: Bearer <token>
?token=<token>
```

`/api/v1/status` und `/api/v1/manifest` sind ohne Token lesbar, enthalten dann
aber kein Passwort und kein Token.

## Endpunkte

```text
GET /api/v1/status
GET /api/v1/manifest
GET /api/v1/pairing
POST /api/v1/pair-by-code
GET /api/v1/event
GET /api/v1/photos?limit=100&offset=0&since=0&folder=Prints
GET /api/v1/thumb/{folder}/{filename}
GET /api/v1/image/{folder}/{filename}
GET /api/v1/download/{folder}/{filename}
POST /api/v1/upload/settings
POST /api/v1/upload/template
GET /.well-known/fexobox-gallery.json
```

`folder` ist optional und aktuell auf `Prints` oder `Single` begrenzt.
`since` ist ein Unix-Timestamp und liefert nur spaeter geaenderte Bilder.
`limit` ist auf maximal 500 begrenzt.

`POST /api/v1/pair-by-code` erwartet JSON `{ "code": "123456" }`. Wenn der
Code zur aktuell geladenen Buchung passt, liefert die Box dasselbe private
Manifest wie `/api/v1/pairing`, inklusive Pairing-Token. Das ist fuer den
manuellen Event-Code in der App gedacht und funktioniert nur, wenn das Handy
die Box im lokalen Hotspot erreichen kann.

## App-Verhalten

Empfohlener Ablauf:

1. QR scannen.
2. Falls noch nicht im Hotspot: Produktionswerte `fexobox-gallery` /
   `fotobox123` anzeigen oder per OS-API verbinden.
3. `GET {a}/pairing` mit Token aufrufen.
4. Fotos ueber `GET {a}/photos` pollen.
5. Bilder ueber die `api.url`, `api.thumb` und `api.download` Felder laden.

Fallback bei manuellem Event-Code:

1. Event-Code gegen die Cloud pruefen.
2. Im Box-WLAN `POST http://192.168.137.1:8080/api/v1/pair-by-code` aufrufen.
3. Bei Erfolg lokale Box-Verbindung speichern und Live-Galerie oeffnen.

Die Box macht keine schwere Hintergrundarbeit. Bilder werden erst gelesen, wenn
die App sie anfragt.

## Settings-/Template-Push per App

Die App schickt Einstellungen und Template als zwei getrennte Requests:

1. `POST /api/v1/upload/settings`
2. `POST /api/v1/upload/template`

Die Box nimmt beide Requests im Galerie-Server-Thread entgegen und setzt nur
einen lokalen Apply-Marker. Die eigentliche Uebernahme passiert im UI-Thread,
wenn die Box im Startbildschirm ist. Dadurch wird keine laufende Foto-Session
unterbrochen.

### Regressionsschutz

Diese Punkte duerfen bei spaeteren Refactorings nicht entfernt werden:

- **Apply-Marker getrennt behandeln:** Settings und Template koennen zeitlich
  versetzt ankommen. Ein Settings-Apply darf einen spaeter eintreffenden
  Template-Apply nicht loeschen. Deshalb bestaetigt
  `clear_apply_request(settings=..., template=...)` nur die Teile, die der
  aktuelle UI-Tick wirklich gesehen hat.
- **App-Template-Dateien nie auf die aktive ZIP ueberschreiben:** Unter Windows
  kann die aktuell geladene Template-ZIP noch vom Template-Loader/PIL gesperrt
  sein. Wiederholtes Ersetzen von `cached_template.zip` fuehrte im Live-Test zu
  `WinError 5 Zugriff verweigert`. App-Uploads werden deshalb als eindeutige
  Dateien `app_template_*.zip` in `.booking_cache/` gespeichert. Die aktive
  Datei steht in `.app_upload_meta.json` (`template_path`).
- **`cached_template.zip` ist Legacy/USB-Cache:** USB-Autoload darf weiterhin
  diese feste Datei nutzen. App-Korrekturen haben aber Vorrang, wenn die Meta-
  Datei `source=app` und `template=true` enthaelt.
- **Aktiv geladenes Template und Datei-Fingerprint unterscheiden:** Logs und
  `/status` muessen erkennen lassen, ob der Startscreen wirklich das neue
  Template geladen hat. `loaded_fp` beschreibt den in Memory geladenen Stand,
  `path_fp/cache_file` beschreibt die Datei auf Disk.
- **USB-Stick darf App-Korrektur nicht zurueckholen:** Wenn fuer dieselbe
  Buchung ein App-Template aktiv ist, bleibt der USB-Stick nur Referenz. Erst
  ein echter Event-Wechsel oder eine bewusste Auswahl im Kunden-/Service-Menue
  darf das USB-Template wieder aktiv machen.

### Live-Test, der bestanden bleiben muss

- Box mit eingestecktem USB-Stick starten.
- Template A per App uebertragen; Startscreen muss A zeigen.
- Ohne Neustart Template B per App uebertragen; Startscreen muss B zeigen.
- Box neu starten; App-Template B muss aktiv bleiben und darf nicht vom alten
  USB-Template ersetzt werden.
- In den Logs darf beim zweiten Upload kein `WinError 5` fuer
  `.booking_cache/cached_template.*` stehen.

## Native-App-Voraussetzungen

Die Box bleibt lokal bei HTTP im Hotspot. Die App muss deshalb selbst erlauben,
dass lokale HTTP-Adressen angesprochen werden.

iOS:

- Local-Network-Permission einplanen.
- App Transport Security so konfigurieren, dass lokale HTTP-Verbindungen zur
  Box erlaubt sind.
- Optional das Custom-Scheme `fexobox://` registrieren.

Android:

- Cleartext HTTP fuer lokale/private Netze erlauben.
- WLAN/Netzwerkstatus-Berechtigungen einplanen.
- Optional das Custom-Scheme `fexobox://` registrieren.

Das ist bewusst App-seitig geloest. Auf der Box muss dafuer spaeter kein HTTPS-
Zertifikat installiert oder erneuert werden.
