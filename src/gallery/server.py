"""Lokaler Galerie-Webserver für Fotobox

Ermöglicht Gästen, Bilder per QR-Code auf dem Handy anzusehen und herunterzuladen.
Läuft über den Windows Mobile Hotspot der Fotobox.

Wichtig: Standardmäßig HTTP statt selbst-signiertem HTTPS.
Ein selbst-signiertes Zertifikat erzeugt auf Smartphones eine Warnseite
("Verbindung nicht privat"). Für Gäste ist HTTP im lokalen Hotspot die bessere
UX; Download funktioniert weiterhin, natives File-Sharing fällt per JS zurück.
"""

import io
import os
import secrets
import ssl
import ipaddress
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple
from urllib.parse import quote, urlencode
from PIL import Image

from src.utils.logging import get_logger
from src.i18n import get_gallery_texts, normalize_locale

logger = get_logger(__name__)

# Flask wird lazy importiert (nicht jeder braucht die Galerie)
flask_app = None
server_thread: Optional[threading.Thread] = None
_is_running = False
_is_https = False
_gallery_path: Optional[Path] = None
_gallery_locale = "de-DE"
_gallery_context: Dict[str, Any] = {}
_gallery_pairing_token = secrets.token_urlsafe(12)
_gallery_server_started_at = int(time.time())

# Standard-Konfiguration
DEFAULT_PORT = 8080
DEFAULT_HOST = "0.0.0.0"  # Alle Interfaces (wichtig für Hotspot)
THUMBNAIL_SIZE = (300, 300)


def set_locale(locale: str) -> None:
    """Aktualisiert die Sprache der Galerie-Seite zur Laufzeit."""
    global _gallery_locale
    _gallery_locale = normalize_locale(locale)
    logger.info(f"Galerie-Sprache gesetzt: {_gallery_locale}")


def set_app_context(context: Optional[Dict[str, Any]] = None) -> None:
    """Aktualisiert Metadaten fuer die spaetere Smartphone-App."""
    global _gallery_context
    safe_context: Dict[str, Any] = {}
    for key, value in (context or {}).items():
        if value is None:
            safe_context[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            safe_context[key] = value
        else:
            safe_context[key] = str(value)
    _gallery_context = safe_context
    logger.info(
        "Galerie-App-Kontext aktualisiert: "
        f"box_id={safe_context.get('box_id', '') or '-'} "
        f"booking_id={safe_context.get('booking_id', '') or '-'}"
    )


def _six_digit_code_from_value(value: Any) -> str:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits if len(digits) == 6 else ""


def _get_display_event_code(context: Optional[Dict[str, Any]] = None) -> str:
    """Six digit code shown below the QR code for the smartphone app."""
    data = context if context is not None else _gallery_context
    return _six_digit_code_from_value(data.get("event_pin", ""))


def _build_app_pairing_url(base_url: str) -> str:
    """Baut den kompakten App-Pairing-Payload fuer eine konkrete Base-URL."""
    event_code = _get_display_event_code()
    params = {
        "v": "1",
        "a": f"{base_url}/api/v1",
        "t": _gallery_pairing_token,
    }
    if event_code:
        params["c"] = event_code
    elif _gallery_context.get("booking_id", ""):
        params["e"] = _gallery_context.get("booking_id", "")
    return f"fexobox://g?{urlencode(params, safe=':/')}"


def get_app_pairing_url(port: int = DEFAULT_PORT) -> str:
    """QR-Payload fuer die spaetere fexobox Smartphone-App.

    Der Payload ist bewusst als Custom-Scheme kurz gehalten. Die App kann ihn
    direkt aus dem QR-Code lesen und bekommt damit API-Adresse, Token, Box und
    WLAN-Daten, ohne die Box erneut aktualisieren zu muessen.
    """
    return _build_app_pairing_url(get_gallery_url(port))


def get_app_display_code() -> str:
    """6-stelliger Event-Code fuer die Anzeige unter dem QR-Code."""
    return _get_display_event_code()


def get_app_landing_url(port: int = DEFAULT_PORT) -> str:
    """HTTP-Fallback-URL fuer Tests oder manuelle App-Entwicklung."""
    return f"{get_gallery_url(port)}/app?token={quote(_gallery_pairing_token)}"


def _create_flask_app(locale: str = "de-DE"):
    """Erstellt die Flask-App mit allen Routes"""
    from flask import Flask, send_file, render_template_string, abort, jsonify, request

    set_locale(locale)
    app = Flask(__name__)

    @app.after_request
    def add_api_headers(response):
        """Erlaubt spaetere native/WebView-Apps ohne extra Server-Setup."""
        response.headers.setdefault("Access-Control-Allow-Origin", "*")
        response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        response.headers.setdefault(
            "Access-Control-Allow-Headers",
            "Authorization, Content-Type, X-FexoBox-Token, X-FexoBox-App"
        )
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.after_request
    def add_no_cache_headers(response):
        """Verhindert Browser-Caching damit gelöschte Bilder sofort verschwinden"""
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response
    
    # HTML-Template für die Galerie (responsive, modern, mit Sharing)
    GALLERY_HTML = '''
<!DOCTYPE html>
<html lang="{{ i18n.html_lang }}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ i18n.title }}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            padding: 15px;
        }

        .header {
            text-align: center;
            padding: 15px;
            background: rgba(255,255,255,0.08);
            border-radius: 15px;
            margin-bottom: 15px;
        }

        .header h1 { font-size: 1.5em; margin-bottom: 4px; }
        .header .sub { color: #aaa; font-size: 0.85em; }

        .gallery {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 12px;
            max-width: 1200px;
            margin: 0 auto;
        }

        .photo {
            position: relative;
            aspect-ratio: 3/2;
            border-radius: 12px;
            overflow: hidden;
            background: rgba(255,255,255,0.05);
            cursor: pointer;
            transition: transform 0.2s;
        }

        .photo:active { transform: scale(0.97); }

        .photo img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .empty {
            text-align: center;
            padding: 50px;
            color: #888;
            font-size: 1.2em;
            grid-column: 1 / -1;
        }

        /* Lightbox */
        .lightbox {
            display: none;
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: rgba(0,0,0,0.97);
            z-index: 1000;
            flex-direction: column;
            align-items: center;
            overflow-y: auto;
            -webkit-overflow-scrolling: touch;
        }

        .lightbox.active { display: flex; }

        .lightbox .close {
            position: fixed;
            top: 10px; right: 15px;
            font-size: 36px;
            color: white;
            cursor: pointer;
            z-index: 1001;
            background: rgba(0,0,0,0.5);
            border-radius: 50%;
            width: 44px; height: 44px;
            display: flex; align-items: center; justify-content: center;
        }

        .lightbox .lb-img {
            max-width: 95%;
            max-height: 55vh;
            border-radius: 10px;
            margin-top: 60px;
        }

        .actions {
            display: flex;
            flex-direction: column;
            gap: 10px;
            width: 90%;
            max-width: 400px;
            margin: 20px auto;
            padding-bottom: 30px;
        }

        .action-btn {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 14px 18px;
            border-radius: 14px;
            border: none;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            color: white;
            transition: opacity 0.2s;
        }

        .action-btn:active { opacity: 0.8; }
        .action-btn .icon { font-size: 22px; }

        .btn-download { background: #00c853; }
        .btn-whatsapp { background: #25D366; }
        .btn-instagram { background: linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888); }
        .btn-share { background: #1DA1F2; }
        .btn-facebook { background: #1877F2; }

        .promo {
            text-align: center;
            margin-top: 10px;
            padding: 12px;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            font-size: 0.8em;
            color: #aaa;
        }

        .promo a { color: #7eb8ff; text-decoration: none; }

        .refresh-btn {
            display: block;
            margin: 15px auto;
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            color: white;
            padding: 10px 22px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 15px;
        }

        .footer {
            text-align: center;
            padding: 15px;
            margin-top: 10px;
        }

        .footer a {
            color: #7eb8ff;
            text-decoration: none;
            margin: 0 8px;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ i18n.title }}</h1>
        <div class="sub">{{ i18n.subtitle }}</div>
    </div>

    <div class="gallery">
        {% if photos %}
            {% for photo in photos %}
            <div class="photo" onclick="openLightbox('{{ photo.url }}', '{{ photo.download }}', '{{ photo.name }}')">
                <img src="{{ photo.thumb }}" alt="{{ photo.name }}" loading="lazy">
            </div>
            {% endfor %}
        {% else %}
            <div class="empty">{{ i18n.empty|safe }}</div>
        {% endif %}
    </div>

    <button class="refresh-btn" onclick="location.reload()">{{ i18n.refresh }}</button>

    <div class="footer">
        <a href="https://www.instagram.com/fexobox/" target="_blank">📸 @fexobox</a>
        <a href="https://fexobox.de/" target="_blank">🌐 fexobox.de</a>
    </div>

    <div class="lightbox" id="lightbox">
        <span class="close" onclick="closeLightbox()">×</span>
        <img class="lb-img" id="lightbox-img" src="" alt="">

        <div class="actions">
            <a id="btn-download" class="action-btn btn-download" href="" download>
                <span class="icon">📥</span> {{ i18n.save }}
            </a>

            <button id="btn-share" class="action-btn btn-share" onclick="nativeShare()" style="display:none;">
                <span class="icon">📤</span> {{ i18n.share }}
            </button>

            <p id="share-hint" style="display:none; color:#aaa; font-size:13px; text-align:center; margin:6px 0;">
                {{ i18n.share_hint }}
            </p>

            <div id="fallback-share" style="display:none;">
                <a id="btn-whatsapp" class="action-btn btn-whatsapp" href="" target="_blank">
                    <span class="icon">💬</span> {{ i18n.whatsapp }}
                </a>

                <a id="btn-facebook" class="action-btn btn-facebook" href="" target="_blank">
                    <span class="icon">👤</span> {{ i18n.facebook }}
                </a>
            </div>

            <a class="action-btn btn-instagram" href="https://www.instagram.com/fexobox/" target="_blank">
                <span class="icon">📸</span> {{ i18n.instagram }}
            </a>

            <div class="promo">
                {{ i18n.promo|safe }}
            </div>
        </div>
    </div>

    <script>
        var currentDownloadUrl = '';
        var currentImageUrl = '';

        var shareText = {{ i18n.share_text|tojson }};
        var shareUrl = "https://fexobox.de/";
        var shareTitle = {{ i18n.share_title|tojson }};

        var fileShareSupported = false;

        // Prüfe ob File-Sharing wirklich funktioniert (braucht HTTPS auf den meisten Browsern)
        async function checkFileShare() {
            try {
                if (!navigator.share || !navigator.canShare) return false;
                var testBlob = new Blob(["test"], {type: "image/jpeg"});
                var testFile = new File([testBlob], "test.jpg", {type: "image/jpeg"});
                return navigator.canShare({files: [testFile]});
            } catch(e) {
                return false;
            }
        }
        checkFileShare().then(function(ok) { fileShareSupported = ok; });

        function openLightbox(url, downloadUrl, name) {
            currentDownloadUrl = downloadUrl;
            currentImageUrl = url;
            document.getElementById('lightbox-img').src = url;
            document.getElementById('btn-download').href = downloadUrl;

            if (fileShareSupported) {
                // Native Share mit Bild möglich
                document.getElementById('btn-share').style.display = 'flex';
                document.getElementById('fallback-share').style.display = 'none';
                document.getElementById('share-hint').style.display = 'none';
            } else {
                // Kein File-Share (HTTP) — Download + Hinweis
                document.getElementById('btn-share').style.display = 'none';
                document.getElementById('fallback-share').style.display = 'block';
                document.getElementById('share-hint').style.display = 'block';
                var waText = encodeURIComponent(shareText + "\\n\\n" + shareUrl);
                document.getElementById('btn-whatsapp').href = "https://wa.me/?text=" + waText;
                document.getElementById('btn-facebook').href = "https://www.facebook.com/sharer/sharer.php?u=" + encodeURIComponent(shareUrl) + "&quote=" + encodeURIComponent(shareText);
            }

            document.getElementById('lightbox').classList.add('active');
            document.body.style.overflow = 'hidden';
        }

        function closeLightbox() {
            document.getElementById('lightbox').classList.remove('active');
            document.body.style.overflow = '';
        }

        async function nativeShare() {
            try {
                // Bild herunterladen und als File teilen
                var response = await fetch(currentDownloadUrl);
                var blob = await response.blob();
                var file = new File([blob], "fexobox-foto.jpg", {type: "image/jpeg"});

                if (navigator.canShare && navigator.canShare({files: [file]})) {
                    await navigator.share({
                        title: shareTitle,
                        files: [file]
                    });
                } else {
                    // Fallback: Text-only Share
                    await navigator.share({
                        title: shareTitle,
                        text: shareText,
                        url: shareUrl
                    });
                }
            } catch(e) {
                // Fallback ohne Bild
                try {
                    await navigator.share({
                        title: shareTitle,
                        text: shareText,
                        url: shareUrl
                    });
                } catch(e2) {}
            }
        }

        document.getElementById('lightbox').addEventListener('click', function(e) {
            if (e.target === this) closeLightbox();
        });

        // Auto-Refresh alle 15 Sekunden
        setTimeout(function() { location.reload(); }, 15000);
    </script>
</body>
</html>
'''
    
    def _resolve_gallery_file(filename: str) -> Optional[Path]:
        if not _gallery_path:
            return None

        try:
            base_path = _gallery_path.resolve()
            img_path = (_gallery_path / filename).resolve()
            img_path.relative_to(base_path)
        except Exception:
            return None

        if not img_path.exists() or not img_path.is_file():
            return None
        return img_path

    def _request_token() -> str:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()
        return (
            request.args.get("token", "")
            or request.headers.get("X-FexoBox-Token", "")
        ).strip()

    def _is_api_authorized() -> bool:
        return secrets.compare_digest(_request_token(), _gallery_pairing_token)

    def _require_api_token():
        if _is_api_authorized():
            return None
        return jsonify({
            "app": "fexobox-gallery",
            "api_version": 1,
            "error": "unauthorized",
            "message": "Missing or invalid pairing token",
        }), 401

    def _tokenized_api_path(path: str) -> str:
        return f"{path}?token={quote(_gallery_pairing_token)}"

    def _build_manifest(include_private: bool = False) -> dict:
        base_url = request.host_url.rstrip("/")
        context = _gallery_context.copy()
        manifest = {
            "app": "fexobox-gallery",
            "protocol": "fexobox-gallery-api-v1",
            "schema_version": 1,
            "api_version": 1,
            "server_time": int(time.time()),
            "started_at": _gallery_server_started_at,
            "locale": _gallery_locale,
            "gallery_ready": bool(_gallery_path and _gallery_path.exists()),
            "requires_pairing_token": True,
            "box": {
                "id": context.get("box_id", ""),
                "software_version": context.get("software_version", ""),
            },
            "event": {
                "booking_id": context.get("booking_id", ""),
                "code": _get_display_event_code(context),
            },
            "capabilities": {
                "photos": True,
                "thumbnails": True,
                "downloads": True,
                "polling": True,
                "since_filter": True,
                "folders": ["Prints", "Single"],
                "auth": "pairing-token",
            },
            "endpoints": {
                "status": "/api/v1/status",
                "manifest": "/api/v1/manifest",
                "pairing": "/api/v1/pairing",
                "event": "/api/v1/event",
                "photos": "/api/v1/photos",
                "thumb": "/api/v1/thumb/{folder}/{filename}",
                "image": "/api/v1/image/{folder}/{filename}",
                "download": "/api/v1/download/{folder}/{filename}",
                "legacy_gallery": "/",
                "legacy_photos": "/api/photos",
            },
        }

        if include_private:
            manifest["pairing_token"] = _gallery_pairing_token
            manifest["wifi"] = {
                "ssid": context.get("hotspot_ssid", ""),
                "password": context.get("hotspot_password", ""),
            }
            manifest["urls"] = {
                "base": base_url,
                "api": f"{base_url}/api/v1",
                "app_scheme": _build_app_pairing_url(base_url),
            }

        return manifest

    def _collect_photos(
        limit: int = 50,
        offset: int = 0,
        since: int = 0,
        folders: Optional[List[str]] = None,
        include_api_urls: bool = False
    ) -> List[dict]:
        photos = []
        if _gallery_path and _gallery_path.exists():
            # Prints = fertige Collagen oder gefilterte Einzelbilder
            # Singles = Einzelfotos aus Collage-Sessions (für Gäste interessant)
            allowed_folders = folders or ['Prints', 'Single']
            for folder in allowed_folders:
                folder_path = _gallery_path / folder
                if folder_path.exists():
                    for img_file in sorted(folder_path.glob('*.jpg'), reverse=True):
                        stat = img_file.stat()
                        if since and int(stat.st_mtime) <= since:
                            continue

                        rel_path = f'{folder}/{img_file.name}'
                        photo = {
                            'id': rel_path,
                            'name': img_file.name,
                            'folder': folder,
                            'path': rel_path,
                            'mime_type': 'image/jpeg',
                            'thumb': f'/thumb/{rel_path}',
                            'url': f'/image/{rel_path}',
                            'download': f'/download/{rel_path}',
                            'size': stat.st_size,
                            'modified': int(stat.st_mtime),
                        }
                        if include_api_urls:
                            photo['api'] = {
                                'thumb': _tokenized_api_path(f'/api/v1/thumb/{rel_path}'),
                                'url': _tokenized_api_path(f'/api/v1/image/{rel_path}'),
                                'download': _tokenized_api_path(f'/api/v1/download/{rel_path}'),
                            }
                        photos.append(photo)

        # Nach Datum sortieren (neueste zuerst, Dateiname beginnt mit Timestamp)
        photos.sort(key=lambda p: (p['modified'], p['name']), reverse=True)
        if offset > 0:
            photos = photos[offset:]
        return photos[:limit]

    @app.route('/')
    def gallery():
        """Haupt-Galerie-Seite — zeigt Prints + Einzelbilder"""
        photos = _collect_photos(limit=50)

        return render_template_string(
            GALLERY_HTML,
            photos=photos,
            i18n=get_gallery_texts(_gallery_locale)
        )  # Max 50 Bilder
    
    @app.route('/thumb/<path:filename>')
    def thumbnail(filename):
        """Generiert und liefert Thumbnail"""
        img_path = _resolve_gallery_file(filename)
        if not img_path:
            abort(404)
        
        try:
            img = Image.open(img_path)
            img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            
            # In Memory speichern
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=80)
            buffer.seek(0)
            
            return send_file(buffer, mimetype='image/jpeg')
        except Exception as e:
            logger.error(f"Thumbnail-Fehler: {e}")
            abort(500)
    
    @app.route('/image/<path:filename>')
    def full_image(filename):
        """Liefert Bild in voller Größe"""
        img_path = _resolve_gallery_file(filename)
        if not img_path:
            abort(404)
        
        return send_file(img_path)
    
    @app.route('/download/<path:filename>')
    def download_image(filename):
        """Download mit korrektem Dateinamen"""
        img_path = _resolve_gallery_file(filename)
        if not img_path:
            abort(404)
        
        return send_file(img_path, as_attachment=True, download_name=img_path.name)
    
    @app.route('/api/photos')
    def api_photos():
        """Legacy JSON-API für Foto-Liste."""
        photos = _collect_photos(limit=50)
        return jsonify({'photos': photos, 'count': len(photos), 'api_version': 1})

    @app.route('/api/v1/status')
    def api_v1_status():
        """Leichter Handshake fuer eine spaetere fexobox Smartphone-App."""
        return jsonify(_build_manifest(include_private=False))

    @app.route('/api/v1/manifest')
    @app.route('/.well-known/fexobox-gallery.json')
    def api_v1_manifest():
        """Oeffentliches App-Manifest ohne Token/Passwort."""
        return jsonify(_build_manifest(include_private=_is_api_authorized()))

    @app.route('/api/v1/pairing')
    def api_v1_pairing():
        """Privater Pairing-Handshake fuer die Smartphone-App."""
        auth_error = _require_api_token()
        if auth_error:
            return auth_error
        return jsonify(_build_manifest(include_private=True))

    @app.route('/api/v1/pair-by-code', methods=['POST', 'OPTIONS'])
    def api_v1_pair_by_code():
        """Pairing per 6-stelligem Event-Code fuer die Smartphone-App."""
        if request.method == 'OPTIONS':
            return ("", 204)

        payload = request.get_json(silent=True) or {}
        submitted_code = _six_digit_code_from_value(
            payload.get('code') or payload.get('pin') or request.args.get('code', '')
        )
        expected_code = _get_display_event_code()
        if not expected_code or not secrets.compare_digest(submitted_code, expected_code):
            return jsonify({
                'app': 'fexobox-gallery',
                'api_version': 1,
                'error': 'invalid_event_code',
                'message': 'Event-Code passt nicht zu dieser FexoBox',
            }), 403

        return jsonify(_build_manifest(include_private=True))

    @app.route('/api/v1/event')
    def api_v1_event():
        """Aktuelle Event-Information fuer App-Anzeige und Sync."""
        auth_error = _require_api_token()
        if auth_error:
            return auth_error
        return jsonify({
            'app': 'fexobox-gallery',
            'api_version': 1,
            'server_time': int(time.time()),
            'locale': _gallery_locale,
            'box': {
                'id': _gallery_context.get('box_id', ''),
                'software_version': _gallery_context.get('software_version', ''),
            },
            'event': {
                'booking_id': _gallery_context.get('booking_id', ''),
                'code': _get_display_event_code(),
            },
        })

    @app.route('/api/v1/photos')
    def api_v1_photos():
        """Versionierte Foto-API fuer App-Downloads."""
        auth_error = _require_api_token()
        if auth_error:
            return auth_error

        try:
            limit = max(1, min(int(request.args.get('limit', 100)), 500))
        except Exception:
            limit = 100
        try:
            offset = max(0, int(request.args.get('offset', 0)))
        except Exception:
            offset = 0
        try:
            since = max(0, int(request.args.get('since', 0)))
        except Exception:
            since = 0

        folder = request.args.get('folder', '').strip()
        folders = [folder] if folder in ('Prints', 'Single') else None
        photos = _collect_photos(
            limit=limit,
            offset=offset,
            since=since,
            folders=folders,
            include_api_urls=True
        )
        return jsonify({
            'app': 'fexobox-gallery',
            'api_version': 1,
            'server_time': int(time.time()),
            'count': len(photos),
            'limit': limit,
            'offset': offset,
            'next_offset': offset + len(photos) if len(photos) == limit else None,
            'photos': photos,
        })

    @app.route('/api/v1/thumb/<path:filename>')
    def api_v1_thumbnail(filename):
        auth_error = _require_api_token()
        if auth_error:
            return auth_error

        img_path = _resolve_gallery_file(filename)
        if not img_path:
            abort(404)

        try:
            img = Image.open(img_path)
            img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=80)
            buffer.seek(0)
            return send_file(buffer, mimetype='image/jpeg')
        except Exception as e:
            logger.error(f"API Thumbnail-Fehler: {e}")
            abort(500)

    @app.route('/api/v1/image/<path:filename>')
    def api_v1_full_image(filename):
        auth_error = _require_api_token()
        if auth_error:
            return auth_error

        img_path = _resolve_gallery_file(filename)
        if not img_path:
            abort(404)
        return send_file(img_path)

    @app.route('/api/v1/download/<path:filename>')
    def api_v1_download_image(filename):
        auth_error = _require_api_token()
        if auth_error:
            return auth_error

        img_path = _resolve_gallery_file(filename)
        if not img_path:
            abort(404)
        return send_file(img_path, as_attachment=True, download_name=img_path.name)

    @app.route('/app')
    def app_landing():
        """HTTP-Testpunkt fuer App-Entwicklung und QR-Fallback."""
        return jsonify(_build_manifest(include_private=_is_api_authorized()))
    
    return app


def _generate_self_signed_cert() -> Optional[Tuple[str, str]]:
    """Generiert ein selbst-signiertes SSL-Zertifikat für HTTPS.

    Returns:
        Tuple (cert_path, key_path) oder None bei Fehler
    """
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime
        import tempfile

        # Zertifikate im temp-Verzeichnis ablegen
        cert_dir = Path(tempfile.gettempdir()) / "fexobooth_ssl"
        cert_dir.mkdir(exist_ok=True)
        cert_path = cert_dir / "cert.pem"
        key_path = cert_dir / "key.pem"

        # Nur neu generieren wenn nicht vorhanden oder älter als 30 Tage
        if cert_path.exists() and key_path.exists():
            age = datetime.datetime.now().timestamp() - cert_path.stat().st_mtime
            if age < 30 * 86400:  # 30 Tage
                logger.info("SSL-Zertifikat aus Cache verwendet")
                return str(cert_path), str(key_path)

        # RSA-Schlüssel generieren (2048 bit — schnell genug)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        # Zertifikat erstellen
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "fexobox-gallery"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "fexobox"),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.IPAddress(ipaddress.IPv4Address("192.168.137.1")),
                    x509.DNSName("fexobox-gallery"),
                ]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )

        # Dateien schreiben
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            ))
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        logger.info(f"SSL-Zertifikat generiert: {cert_path}")
        return str(cert_path), str(key_path)

    except ImportError:
        logger.info("cryptography nicht installiert — Galerie läuft ohne HTTPS")
        return None
    except Exception as e:
        logger.warning(f"SSL-Zertifikat konnte nicht erstellt werden: {e}")
        return None


def start_server(
    gallery_path: Path,
    port: int = DEFAULT_PORT,
    host: str = DEFAULT_HOST,
    use_https: bool = False,
    locale: str = "de-DE",
    app_context: Optional[Dict[str, Any]] = None
) -> bool:
    """Startet den Galerie-Server in einem Thread

    Args:
        gallery_path: Pfad zum BILDER-Ordner
        port: Server-Port (default: 8080)
        host: Host-Adresse (default: 0.0.0.0)
        use_https: Optional selbst-signiertes HTTPS aktivieren. Standard bleibt
                   HTTP, damit Smartphones keine Zertifikatswarnung zeigen.

    Returns:
        True wenn erfolgreich gestartet
    """
    global flask_app, server_thread, _is_running, _is_https, _gallery_path, _gallery_server_started_at

    if _is_running:
        set_locale(locale)
        set_app_context(app_context)
        logger.warning("Galerie-Server läuft bereits")
        return True

    _gallery_path = gallery_path
    _gallery_server_started_at = int(time.time())
    set_app_context(app_context)
    flask_app = _create_flask_app(locale)

    # Kein selbst-signiertes HTTPS als Standard: Smartphones zeigen sonst eine
    # Warnseite, die Gäste kaum sinnvoll wegklicken können.
    ssl_context = None
    if use_https:
        ssl_certs = _generate_self_signed_cert()
        if ssl_certs:
            cert_path, key_path = ssl_certs
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(cert_path, key_path)
            logger.info("HTTPS aktiviert (selbst-signiertes Zertifikat)")

    protocol = "https" if ssl_context else "http"

    def run_server():
        global _is_running
        try:
            logger.info(f"🌐 Galerie-Server startet auf {protocol}://{host}:{port}")
            flask_app.run(host=host, port=port, threaded=True, use_reloader=False,
                         ssl_context=ssl_context)
        except Exception as e:
            logger.error(f"Galerie-Server Fehler: {e}")
        finally:
            _is_running = False
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    _is_running = True
    _is_https = ssl_context is not None

    logger.info(f"✅ Galerie-Server gestartet: {protocol}://{host}:{port}")
    return True


def stop_server():
    """Stoppt den Galerie-Server"""
    global _is_running
    # Flask's Werkzeug-Server kann nicht sauber gestoppt werden
    # Da der Thread daemon=True ist, wird er beim App-Ende beendet
    _is_running = False
    logger.info("Galerie-Server wird beim App-Ende beendet")


def is_running() -> bool:
    """Prüft ob Server läuft"""
    return _is_running


def get_gallery_url(port: int = DEFAULT_PORT) -> str:
    """Gibt die Galerie-URL zurück (für QR-Code)

    Versucht die beste IP für den Hotspot zu finden:
    1. Windows Mobile Hotspot (192.168.137.x Netzwerk)
    2. Andere private Netzwerke (192.168.x.x, 10.x.x.x)
    3. Fallback: Standard Hotspot-IP
    """
    import socket

    scheme = "https" if _is_https else "http"

    try:
        # Alle IP-Adressen des Systems sammeln
        hostname = socket.gethostname()
        all_ips = socket.getaddrinfo(hostname, None, socket.AF_INET)
        local_ips = list(set([ip[4][0] for ip in all_ips if not ip[4][0].startswith('127.')]))

        logger.debug(f"Gefundene IPs: {local_ips}")

        # Priorität 1: Windows Mobile Hotspot (192.168.137.x)
        for ip in local_ips:
            if ip.startswith("192.168.137."):
                logger.info(f"🌐 Hotspot-IP erkannt: {ip}")
                return f"{scheme}://{ip}:{port}"

        # Priorität 2: Andere 192.168.x.x (häufig Hotspot/WLAN)
        for ip in local_ips:
            if ip.startswith("192.168."):
                logger.info(f"🌐 Lokale IP: {ip}")
                return f"{scheme}://{ip}:{port}"

        # Priorität 3: 10.x.x.x Netzwerke
        for ip in local_ips:
            if ip.startswith("10."):
                logger.info(f"🌐 Private IP: {ip}")
                return f"{scheme}://{ip}:{port}"

        # Fallback: Socket-Trick
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        logger.info(f"🌐 Fallback-IP: {local_ip}")
        return f"{scheme}://{local_ip}:{port}"

    except Exception as e:
        logger.warning(f"IP-Erkennung fehlgeschlagen: {e}")
        return f"{scheme}://192.168.137.1:{port}"
