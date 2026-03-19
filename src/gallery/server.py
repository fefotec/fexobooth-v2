"""Lokaler Galerie-Webserver für Fotobox

Ermöglicht Gästen, Bilder per QR-Code auf dem Handy anzusehen und herunterzuladen.
Läuft über den Windows Mobile Hotspot der Fotobox.
HTTPS mit selbst-signiertem Zertifikat für Web Share API File-Sharing.
"""

import os
import io
import ssl
import ipaddress
import threading
from pathlib import Path
from typing import Optional, List, Tuple
from PIL import Image

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Flask wird lazy importiert (nicht jeder braucht die Galerie)
flask_app = None
server_thread: Optional[threading.Thread] = None
_is_running = False
_is_https = False
_gallery_path: Optional[Path] = None

# Standard-Konfiguration
DEFAULT_PORT = 8080
DEFAULT_HOST = "0.0.0.0"  # Alle Interfaces (wichtig für Hotspot)
THUMBNAIL_SIZE = (300, 300)


def _create_flask_app():
    """Erstellt die Flask-App mit allen Routes"""
    from flask import Flask, send_file, render_template_string, abort, jsonify
    
    app = Flask(__name__)

    @app.after_request
    def add_no_cache_headers(response):
        """Verhindert Browser-Caching damit gelöschte Bilder sofort verschwinden"""
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response
    
    # HTML-Template für die Galerie (responsive, modern, mit Sharing)
    GALLERY_HTML = '''
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>fexobox Galerie</title>
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
        <h1>fexobox Galerie</h1>
        <div class="sub">Tippe auf ein Bild zum Herunterladen & Teilen</div>
    </div>

    <div class="gallery">
        {% if photos %}
            {% for photo in photos %}
            <div class="photo" onclick="openLightbox('{{ photo.url }}', '{{ photo.download }}', '{{ photo.name }}')">
                <img src="{{ photo.thumb }}" alt="{{ photo.name }}" loading="lazy">
            </div>
            {% endfor %}
        {% else %}
            <div class="empty">Noch keine Bilder vorhanden.<br>Mach ein Foto! 📷</div>
        {% endif %}
    </div>

    <button class="refresh-btn" onclick="location.reload()">🔄 Aktualisieren</button>

    <div class="footer">
        <a href="https://www.instagram.com/fexobox/" target="_blank">📸 @fexobox</a>
        <a href="https://fexobox.de/" target="_blank">🌐 fexobox.de</a>
    </div>

    <div class="lightbox" id="lightbox">
        <span class="close" onclick="closeLightbox()">×</span>
        <img class="lb-img" id="lightbox-img" src="" alt="">

        <div class="actions">
            <a id="btn-download" class="action-btn btn-download" href="" download>
                <span class="icon">📥</span> Bild speichern
            </a>

            <button id="btn-share" class="action-btn btn-share" onclick="nativeShare()" style="display:none;">
                <span class="icon">📤</span> Foto teilen (WhatsApp, Insta, ...)
            </button>

            <p id="share-hint" style="display:none; color:#aaa; font-size:13px; text-align:center; margin:6px 0;">
                Tipp: Erst Bild speichern, dann aus deiner Galerie teilen!
            </p>

            <div id="fallback-share" style="display:none;">
                <a id="btn-whatsapp" class="action-btn btn-whatsapp" href="" target="_blank">
                    <span class="icon">💬</span> Per WhatsApp teilen (nur Text)
                </a>

                <a id="btn-facebook" class="action-btn btn-facebook" href="" target="_blank">
                    <span class="icon">👤</span> Auf Facebook teilen
                </a>
            </div>

            <a class="action-btn btn-instagram" href="https://www.instagram.com/fexobox/" target="_blank">
                <span class="icon">📸</span> fexobox auf Instagram folgen
            </a>

            <div class="promo">
                Powered by <a href="https://fexobox.de/" target="_blank">fexobox.de</a> — Deine mobile Fotobox!
            </div>
        </div>
    </div>

    <script>
        var currentDownloadUrl = '';
        var currentImageUrl = '';

        var shareText = "Schaut mal, mein Foto von der fexobox! 📸✨ Die coolste Fotobox für jede Party!\\n\\n👉 @fexobox\\n🌐 fexobox.de";
        var shareUrl = "https://fexobox.de/";

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
                        title: "Mein fexobox Foto",
                        files: [file]
                    });
                } else {
                    // Fallback: Text-only Share
                    await navigator.share({
                        title: "Mein fexobox Foto",
                        text: shareText,
                        url: shareUrl
                    });
                }
            } catch(e) {
                // Fallback ohne Bild
                try {
                    await navigator.share({
                        title: "Mein fexobox Foto",
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
    
    @app.route('/')
    def gallery():
        """Haupt-Galerie-Seite — zeigt Prints + Einzelbilder"""
        photos = []

        if _gallery_path and _gallery_path.exists():
            # Prints = fertige Collagen oder gefilterte Einzelbilder
            # Singles = Einzelfotos aus Collage-Sessions (für Gäste interessant)
            for folder in ['Prints', 'Single']:
                folder_path = _gallery_path / folder
                if folder_path.exists():
                    for img_file in sorted(folder_path.glob('*.jpg'), reverse=True):
                        photos.append({
                            'name': img_file.name,
                            'thumb': f'/thumb/{folder}/{img_file.name}',
                            'url': f'/image/{folder}/{img_file.name}',
                            'download': f'/download/{folder}/{img_file.name}'
                        })

        # Nach Datum sortieren (neueste zuerst, Dateiname beginnt mit Timestamp)
        photos.sort(key=lambda p: p['name'], reverse=True)

        return render_template_string(GALLERY_HTML, photos=photos[:50])  # Max 50 Bilder
    
    @app.route('/thumb/<path:filename>')
    def thumbnail(filename):
        """Generiert und liefert Thumbnail"""
        if not _gallery_path:
            abort(404)
        
        img_path = _gallery_path / filename
        if not img_path.exists():
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
        if not _gallery_path:
            abort(404)
        
        img_path = _gallery_path / filename
        if not img_path.exists():
            abort(404)
        
        return send_file(img_path)
    
    @app.route('/download/<path:filename>')
    def download_image(filename):
        """Download mit korrektem Dateinamen"""
        if not _gallery_path:
            abort(404)
        
        img_path = _gallery_path / filename
        if not img_path.exists():
            abort(404)
        
        return send_file(img_path, as_attachment=True, download_name=img_path.name)
    
    @app.route('/api/photos')
    def api_photos():
        """JSON-API für Foto-Liste"""
        photos = []
        if _gallery_path and _gallery_path.exists():
            for img_file in sorted(_gallery_path.rglob('*.jpg'), reverse=True)[:50]:
                rel_path = img_file.relative_to(_gallery_path)
                photos.append({
                    'name': img_file.name,
                    'path': str(rel_path),
                    'size': img_file.stat().st_size
                })
        return jsonify({'photos': photos, 'count': len(photos)})
    
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


def start_server(gallery_path: Path, port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> bool:
    """Startet den Galerie-Server in einem Thread

    Args:
        gallery_path: Pfad zum BILDER-Ordner
        port: Server-Port (default: 8080)
        host: Host-Adresse (default: 0.0.0.0)

    Returns:
        True wenn erfolgreich gestartet
    """
    global flask_app, server_thread, _is_running, _is_https, _gallery_path

    if _is_running:
        logger.warning("Galerie-Server läuft bereits")
        return True

    _gallery_path = gallery_path
    flask_app = _create_flask_app()

    # HTTPS mit selbst-signiertem Zertifikat versuchen
    ssl_context = None
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
