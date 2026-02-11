"""Lokaler Galerie-Webserver für Fotobox

Ermöglicht Gästen, Bilder per QR-Code auf dem Handy anzusehen und herunterzuladen.
Läuft über den Windows Mobile Hotspot der Fotobox.
"""

import os
import io
import threading
from pathlib import Path
from typing import Optional, List
from PIL import Image

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Flask wird lazy importiert (nicht jeder braucht die Galerie)
flask_app = None
server_thread: Optional[threading.Thread] = None
_is_running = False
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
    
    # HTML-Template für die Galerie (responsive, modern)
    GALLERY_HTML = '''
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📸 Fotobox Galerie</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        
        h1 {
            text-align: center;
            padding: 20px;
            font-size: 1.8em;
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            margin-bottom: 20px;
        }
        
        .info {
            text-align: center;
            color: #aaa;
            margin-bottom: 20px;
            font-size: 0.9em;
        }
        
        .gallery {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 15px;
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .photo {
            position: relative;
            aspect-ratio: 1;
            border-radius: 12px;
            overflow: hidden;
            background: rgba(255,255,255,0.05);
            cursor: pointer;
            transition: transform 0.2s;
        }
        
        .photo:hover {
            transform: scale(1.03);
        }
        
        .photo img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        .photo .download-btn {
            position: absolute;
            bottom: 10px;
            right: 10px;
            background: rgba(0,200,100,0.9);
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 14px;
            cursor: pointer;
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 5px;
        }
        
        .empty {
            text-align: center;
            padding: 50px;
            color: #888;
            font-size: 1.2em;
        }
        
        /* Lightbox */
        .lightbox {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.95);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }
        
        .lightbox.active { display: flex; }
        
        .lightbox img {
            max-width: 90%;
            max-height: 80%;
            border-radius: 10px;
        }
        
        .lightbox .close {
            position: absolute;
            top: 20px;
            right: 20px;
            font-size: 40px;
            color: white;
            cursor: pointer;
        }
        
        .lightbox .download-full {
            margin-top: 20px;
            background: #00c853;
            color: white;
            padding: 15px 30px;
            border-radius: 30px;
            text-decoration: none;
            font-size: 18px;
        }
        
        .refresh-btn {
            display: block;
            margin: 20px auto;
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.3);
            color: white;
            padding: 12px 25px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 16px;
        }
        
        .refresh-btn:hover {
            background: rgba(255,255,255,0.2);
        }
    </style>
</head>
<body>
    <h1>📸 Fotobox Galerie</h1>
    <p class="info">Tippe auf ein Bild zum Vergrößern und Herunterladen</p>
    
    <div class="gallery">
        {% if photos %}
            {% for photo in photos %}
            <div class="photo" onclick="openLightbox('{{ photo.url }}', '{{ photo.download }}')">
                <img src="{{ photo.thumb }}" alt="{{ photo.name }}" loading="lazy">
            </div>
            {% endfor %}
        {% else %}
            <div class="empty">Noch keine Bilder vorhanden.<br>Mach ein Foto! 📷</div>
        {% endif %}
    </div>
    
    <button class="refresh-btn" onclick="location.reload()">🔄 Aktualisieren</button>
    
    <div class="lightbox" id="lightbox">
        <span class="close" onclick="closeLightbox()">×</span>
        <img id="lightbox-img" src="" alt="">
        <a id="lightbox-download" class="download-full" href="" download>📥 Herunterladen</a>
    </div>
    
    <script>
        function openLightbox(url, downloadUrl) {
            document.getElementById('lightbox-img').src = url;
            document.getElementById('lightbox-download').href = downloadUrl;
            document.getElementById('lightbox').classList.add('active');
        }
        
        function closeLightbox() {
            document.getElementById('lightbox').classList.remove('active');
        }
        
        document.getElementById('lightbox').addEventListener('click', function(e) {
            if (e.target === this) closeLightbox();
        });
        
        // Auto-Refresh alle 10 Sekunden
        setTimeout(function() { location.reload(); }, 10000);
    </script>
</body>
</html>
'''
    
    @app.route('/')
    def gallery():
        """Haupt-Galerie-Seite"""
        photos = []
        
        if _gallery_path and _gallery_path.exists():
            # Bilder aus allen Unterordnern sammeln
            for folder in ['Prints', 'Single', '']:
                folder_path = _gallery_path / folder if folder else _gallery_path
                if folder_path.exists():
                    for img_file in sorted(folder_path.glob('*.jpg'), reverse=True):
                        photos.append({
                            'name': img_file.name,
                            'thumb': f'/thumb/{folder}/{img_file.name}' if folder else f'/thumb/{img_file.name}',
                            'url': f'/image/{folder}/{img_file.name}' if folder else f'/image/{img_file.name}',
                            'download': f'/download/{folder}/{img_file.name}' if folder else f'/download/{img_file.name}'
                        })
                    for img_file in sorted(folder_path.glob('*.png'), reverse=True):
                        photos.append({
                            'name': img_file.name,
                            'thumb': f'/thumb/{folder}/{img_file.name}' if folder else f'/thumb/{img_file.name}',
                            'url': f'/image/{folder}/{img_file.name}' if folder else f'/image/{img_file.name}',
                            'download': f'/download/{folder}/{img_file.name}' if folder else f'/download/{img_file.name}'
                        })
        
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


def start_server(gallery_path: Path, port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> bool:
    """Startet den Galerie-Server in einem Thread
    
    Args:
        gallery_path: Pfad zum BILDER-Ordner
        port: Server-Port (default: 8080)
        host: Host-Adresse (default: 0.0.0.0)
        
    Returns:
        True wenn erfolgreich gestartet
    """
    global flask_app, server_thread, _is_running, _gallery_path
    
    if _is_running:
        logger.warning("Galerie-Server läuft bereits")
        return True
    
    _gallery_path = gallery_path
    flask_app = _create_flask_app()
    
    def run_server():
        global _is_running
        try:
            logger.info(f"🌐 Galerie-Server startet auf http://{host}:{port}")
            # Werkzeug Server (für Entwicklung/einfache Nutzung)
            flask_app.run(host=host, port=port, threaded=True, use_reloader=False)
        except Exception as e:
            logger.error(f"Galerie-Server Fehler: {e}")
        finally:
            _is_running = False
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    _is_running = True
    
    logger.info(f"✅ Galerie-Server gestartet: http://{host}:{port}")
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
                return f"http://{ip}:{port}"
        
        # Priorität 2: Andere 192.168.x.x (häufig Hotspot/WLAN)
        for ip in local_ips:
            if ip.startswith("192.168."):
                logger.info(f"🌐 Lokale IP: {ip}")
                return f"http://{ip}:{port}"
        
        # Priorität 3: 10.x.x.x Netzwerke
        for ip in local_ips:
            if ip.startswith("10."):
                logger.info(f"🌐 Private IP: {ip}")
                return f"http://{ip}:{port}"
        
        # Fallback: Socket-Trick
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        logger.info(f"🌐 Fallback-IP: {local_ip}")
        return f"http://{local_ip}:{port}"
        
    except Exception as e:
        logger.warning(f"IP-Erkennung fehlgeschlagen: {e}")
        # Standard Windows Mobile Hotspot IP
        return f"http://192.168.137.1:{port}"
