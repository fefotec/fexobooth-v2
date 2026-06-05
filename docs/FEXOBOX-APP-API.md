# FexoBox App API

Stand: 2026-06-04

Diese Box-Version bereitet die spaetere Smartphone-App vor. Die App soll keine
Browser-Galerie oeffnen, sondern lokal im Fotobox-Hotspot mit der Box sprechen.

## QR-Payload

Der sichtbare QR-Code enthaelt keinen Browser-Link mehr, sondern ein kurzes
Custom-Scheme:

```text
fexobox://g?v=1&a=http%3A%2F%2F192.168.137.1%3A8080%2Fapi%2Fv1&t=<token>&l=de-DE&b=006&e=NX-123456&s=fexobox-gallery&p=fotobox123
```

Parameter:

- `v`: QR-Schema-Version, aktuell `1`
- `a`: Base URL der lokalen API, z. B. `http://192.168.137.1:8080/api/v1`
- `t`: Pairing-Token, muss die App bei privaten API-Endpunkten mitsenden
- `l`: Locale der Box, z. B. `de-DE`
- `b`: dreistellige Box-ID, falls gesetzt
- `e`: aktuelle Booking-ID, falls geladen
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
GET /api/v1/event
GET /api/v1/photos?limit=100&offset=0&since=0&folder=Prints
GET /api/v1/thumb/{folder}/{filename}
GET /api/v1/image/{folder}/{filename}
GET /api/v1/download/{folder}/{filename}
GET /.well-known/fexobox-gallery.json
```

`folder` ist optional und aktuell auf `Prints` oder `Single` begrenzt.
`since` ist ein Unix-Timestamp und liefert nur spaeter geaenderte Bilder.
`limit` ist auf maximal 500 begrenzt.

## App-Verhalten

Empfohlener Ablauf:

1. QR scannen.
2. Falls noch nicht im Hotspot: SSID/Passwort aus QR anzeigen oder per OS-API verbinden.
3. `GET {a}/pairing` mit Token aufrufen.
4. Fotos ueber `GET {a}/photos` pollen.
5. Bilder ueber die `api.url`, `api.thumb` und `api.download` Felder laden.

Die Box macht keine schwere Hintergrundarbeit. Bilder werden erst gelesen, wenn
die App sie anfragt.

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
