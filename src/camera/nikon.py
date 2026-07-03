"""Nikon DSLR Camera Manager via FexoNikonBridge (Variante 3).

Die D3300 wird vom offiziellen Nikon-SDK nicht unterstützt (kein MD3-Modul für
die gesamte D3xxx-Serie). Der frühere digiCamControl-App-Ansatz (Variante 2)
ist verworfen: sichtbares GUI-Fenster + Webserver, der per Standardinstallation
nie antwortet.

Stattdessen steuert eine eigene, unsichtbare `FexoNikonBridge.exe` (kleiner
.NET-Hintergrundprozess ohne Fenster, Motor: MIT-lizenzierte Bibliothek
CameraControl.Devices) die Nikon per rohem PTP/MTP über die Windows-WPD-API —
derselbe Weg, den auch dslrBooth für die D3xxx-Serie gehen muss.

Kommunikation FexoBooth <-> Bridge: JSON-Zeilen über stdin/stdout, Binärdaten
(JPEG) längenpräfixiert direkt nach der Antwortzeile. Keine Ports, kein
Webserver, keine Firewall-Dialoge, kein sichtbares Fremdfenster.

Protokoll (eine Anfrage gleichzeitig):
    -> {"id": 1, "cmd": "ping"}\n
    <- {"id": 1, "ok": true, "bridge": "FexoNikonBridge", "version": "..."}\n
    -> {"id": 2, "cmd": "frame"}\n
    <- {"id": 2, "ok": true, "len": 45123}\n + 45123 Bytes JPEG
Kommandos: ping, list, init, lv_start, lv_stop, frame, capture, release, quit
"""

from __future__ import annotations

import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from .base import CameraManager
from src.utils.logging import get_logger

logger = get_logger(__name__)

BRIDGE_EXE_NAME = "FexoNikonBridge.exe"


class _NikonBridgeClient:
    """Verwaltet den versteckten FexoNikonBridge-Prozess (ein Prozess pro App).

    Threadsicher: pro Zeitpunkt genau eine Anfrage (RLock). Ein Reader-Thread
    liest Antwortzeilen + Binär-Payloads und legt sie in eine Queue, damit
    Anfragen ein echtes Timeout haben (Windows-Pipes kennen kein read-timeout).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config: Dict[str, Any] = config or {}
        self._process: Optional[subprocess.Popen] = None
        self._responses: "queue.Queue[Optional[Tuple[dict, Optional[bytes]]]]" = queue.Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._request_id = 0
        self._io_lock = threading.RLock()

    def update_config(self, config: Dict[str, Any]) -> None:
        self._config = config or {}

    # ------------------------------------------------------------------
    # Prozess-Lifecycle
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def ensure_running(self, spawn: bool = True) -> bool:
        """Startet die Bridge unsichtbar, falls sie nicht läuft. Idempotent."""
        with self._io_lock:
            if self.is_running():
                return True

            if not spawn:
                return False

            exe = find_bridge_exe(self._config)
            if not exe:
                candidates = [str(p) for p in bridge_exe_candidates(self._config)]
                logger.error(
                    f"FexoNikonBridge nicht gefunden ({BRIDGE_EXE_NAME}). "
                    f"Geprüfte Pfade: {candidates}"
                )
                return False

            try:
                creationflags = 0
                if os.name == "nt":
                    # Kein Konsolenfenster, kein sichtbares Fremdfenster im Kiosk.
                    creationflags = subprocess.CREATE_NO_WINDOW
                self._process = subprocess.Popen(
                    [str(exe)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                    cwd=str(exe.parent),
                )
            except Exception as exc:
                logger.error(f"FexoNikonBridge konnte nicht gestartet werden: {exc}")
                self._process = None
                return False

            # Queue + Prozess fest an DIESEN Reader binden: das finale None eines
            # alten Readers (EOF eines früheren Bridge-Prozesses) darf nie in der
            # Queue eines frisch gestarteten Prozesses landen.
            responses: "queue.Queue[Optional[Tuple[dict, Optional[bytes]]]]" = queue.Queue()
            self._responses = responses
            self._reader_thread = threading.Thread(
                target=self._reader_loop,
                args=(self._process, responses),
                daemon=True,
                name="nikon-bridge-reader",
            )
            self._reader_thread.start()
            logger.info(f"FexoNikonBridge gestartet (unsichtbar): {exe}")

            # Handshake: Bridge muss auf ping antworten.
            try:
                self.request("ping", timeout=self._settings().get("init_timeout_seconds", 20))
                return True
            except Exception as exc:
                logger.error(f"FexoNikonBridge antwortet nicht auf ping: {exc}")
                self.stop()
                return False

    def stop(self) -> None:
        with self._io_lock:
            process = self._process
            self._process = None
            if process is None:
                return
            try:
                if process.poll() is None:
                    try:
                        process.stdin.write(b'{"id": 0, "cmd": "quit"}\n')
                        process.stdin.flush()
                    except Exception:
                        pass
                    try:
                        process.wait(timeout=2)
                    except Exception:
                        process.kill()
            except Exception as exc:
                logger.debug(f"FexoNikonBridge stop: {exc}")

    # ------------------------------------------------------------------
    # Anfragen
    # ------------------------------------------------------------------

    def request(self, cmd: str, timeout: float, **params: Any) -> Tuple[dict, Optional[bytes]]:
        """Sendet ein Kommando und wartet auf die passende Antwort.

        Returns (header_dict, payload_bytes_oder_None). Wirft bei Timeout,
        Bridge-Ende oder ok=false eine Exception. Das Timeout deckt AUCH das
        Warten auf den Lock ab — sonst hängt z.B. der UI-Status-Check hinter
        einem laufenden 12s-Capture eines anderen Threads.
        """
        end_time = time.time() + timeout
        if not self._io_lock.acquire(timeout=timeout):
            raise TimeoutError(f"FexoNikonBridge: beschäftigt bei '{cmd}' ({timeout}s)")
        try:
            if not self.is_running():
                raise RuntimeError("FexoNikonBridge läuft nicht")

            self._request_id += 1
            request_id = self._request_id
            payload_request = {"id": request_id, "cmd": cmd}
            payload_request.update(params)
            data = (json.dumps(payload_request) + "\n").encode("utf-8")
            try:
                self._process.stdin.write(data)
                self._process.stdin.flush()
            except Exception as exc:
                raise RuntimeError(f"FexoNikonBridge stdin nicht schreibbar: {exc}") from exc

            while True:
                remaining = end_time - time.time()
                if remaining <= 0:
                    raise TimeoutError(f"FexoNikonBridge: Timeout bei '{cmd}' ({timeout}s)")
                try:
                    item = self._responses.get(timeout=remaining)
                except queue.Empty:
                    raise TimeoutError(f"FexoNikonBridge: Timeout bei '{cmd}' ({timeout}s)")
                if item is None:
                    raise RuntimeError("FexoNikonBridge wurde beendet (EOF)")
                header, payload = item
                if header.get("id") != request_id:
                    # Verspätete Antwort einer vorher per Timeout abgebrochenen
                    # Anfrage — überspringen, auf unsere Antwort warten.
                    continue
                if not header.get("ok"):
                    raise RuntimeError(
                        f"FexoNikonBridge '{cmd}' fehlgeschlagen: {header.get('error', 'unbekannt')}"
                    )
                return header, payload
        finally:
            self._io_lock.release()

    def _reader_loop(self, process: subprocess.Popen, responses: "queue.Queue") -> None:
        if process is None or process.stdout is None:
            return
        stream = process.stdout
        try:
            while True:
                line = stream.readline()
                if not line:
                    break  # EOF: Bridge-Prozess ist weg
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    header = json.loads(text)
                except Exception:
                    # Fremde Ausgabe (z.B. .NET-Warnung) — ignorieren.
                    logger.debug(f"FexoNikonBridge: unerwartete Ausgabe: {text[:200]}")
                    continue
                payload = None
                length = header.get("len")
                if header.get("ok") and isinstance(length, int) and length > 0:
                    payload = stream.read(length)
                responses.put((header, payload))
        except Exception as exc:
            logger.debug(f"FexoNikonBridge Reader beendet: {exc}")
        finally:
            # Nur in die EIGENE Queue — nie in die eines Nachfolger-Prozesses.
            responses.put(None)

    def _settings(self) -> Dict[str, Any]:
        return self._config.get("nikon_bridge", {})


# Ein Bridge-Prozess pro App: geteilt zwischen Manager-Instanz und den
# statischen Status-Checks (is_available/list_cameras in app.py/admin.py).
_shared_client: Optional[_NikonBridgeClient] = None
_shared_client_lock = threading.Lock()


def _get_client(config: Optional[Dict[str, Any]]) -> _NikonBridgeClient:
    global _shared_client
    with _shared_client_lock:
        if _shared_client is None:
            _shared_client = _NikonBridgeClient(config)
        elif config:
            _shared_client.update_config(config)
        return _shared_client


def bridge_exe_candidates(config: Optional[Dict[str, Any]]) -> List[Path]:
    """Alle Pfade, unter denen die FexoNikonBridge.exe gesucht wird."""
    settings = (config or {}).get("nikon_bridge", {})
    raw_candidates = [
        settings.get("exe_path"),
        os.environ.get("FEXOBOOTH_NIKON_BRIDGE_EXE"),
    ]

    # Installierter EXE-Build: {app}\bridge\FexoNikonBridge.exe neben fexobooth.exe
    if getattr(sys, "frozen", False):
        raw_candidates.append(str(Path(sys.executable).parent / "bridge" / BRIDGE_EXE_NAME))

    # Dev-Betrieb aus dem Repo: gebaute Bridge unter bridge\FexoNikonBridge\bin\...
    repo_root = Path(__file__).resolve().parents[2]
    raw_candidates.extend(
        [
            str(repo_root / "bridge" / BRIDGE_EXE_NAME),
            str(repo_root / "bridge" / "FexoNikonBridge" / "bin" / "Release" / "net48" / BRIDGE_EXE_NAME),
            str(repo_root / "bridge" / "FexoNikonBridge" / "bin" / "Debug" / "net48" / BRIDGE_EXE_NAME),
            r"C:\FexoBooth\bridge" + "\\" + BRIDGE_EXE_NAME,
        ]
    )

    candidates: List[Path] = []
    seen = set()
    for candidate in raw_candidates:
        if not candidate:
            continue
        candidate_text = str(candidate).strip()
        if not candidate_text:
            continue
        key = candidate_text.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(Path(candidate_text))
    return candidates


def find_bridge_exe(config: Optional[Dict[str, Any]]) -> Optional[Path]:
    for path in bridge_exe_candidates(config):
        if path.is_file():
            return path
    return None


class NikonCameraManager(CameraManager):
    """Steuert Nikon DSLRs über die unsichtbare FexoNikonBridge."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config: Dict[str, Any] = config or {}
        self._is_initialized = False
        self._live_view_active = False
        self._last_frame: Optional[np.ndarray] = None
        self._last_frame_time: float = 0
        self._frame_cache_duration = 0.033
        # Härte Grenze gegen eingefrorene LiveViews: älter darf ein Cache-Frame
        # bei Fehlern nie ausgeliefert werden — sonst würde ein Minuten alter
        # Frame als "Foto" gedruckt, wenn Bridge/Kamera mitten in der Session
        # sterben (Capture-Fallback greift auf get_frame zurück).
        self._max_stale_frame_seconds = 1.5
        self._camera_index = 0
        self._camera_name = "Nikon via FexoNikonBridge"
        self._last_diagnostics_log_time: float = 0
        self._lock = threading.RLock()

    def update_config(self, config: Dict[str, Any]) -> None:
        self._config = config
        _get_client(config)

    # ------------------------------------------------------------------
    # Statische Checks (Top-Bar-Status, Admin-Kamera-Scan)
    # ------------------------------------------------------------------

    @staticmethod
    def is_available(config: Optional[Dict[str, Any]] = None) -> bool:
        """True, wenn die Bridge-EXE existiert oder die Bridge bereits läuft."""
        client = _get_client(config)
        return client.is_running() or bool(find_bridge_exe(config))

    @staticmethod
    def list_cameras(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Fragt die laufende Bridge nach angeschlossenen Nikon-Kameras.

        Startet die Bridge NICHT selbst (kann vom UI-Thread aufgerufen werden;
        das Starten übernimmt der Warmup beim App-Start bzw. initialize()).
        """
        client = _get_client(config)
        if not client.is_running():
            return []
        try:
            header, _ = client.request("list", timeout=2.0)
        except Exception as exc:
            logger.debug(f"FexoNikonBridge Kamera-Liste nicht abrufbar: {exc}")
            return []

        cameras: List[Dict[str, Any]] = []
        for idx, cam in enumerate(header.get("cameras", []) or []):
            name = str(cam.get("name", "")).strip() if isinstance(cam, dict) else str(cam).strip()
            if not name:
                continue
            serial = cam.get("serial", name) if isinstance(cam, dict) else name
            cameras.append({"index": idx, "name": name, "serial": serial})
        return cameras

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def ensure_bridge_running(self) -> bool:
        """Best-effort: startet die unsichtbare Bridge, falls noch nicht aktiv.

        Für den Warmup beim App-Start (im Hintergrund-Thread): der erste
        Session-Start trifft dann keinen Kaltstart auf dem UI-Thread.
        Idempotent — läuft die Bridge schon, kehrt es sofort zurück.
        """
        client = _get_client(self._config)
        ok = client.ensure_running(spawn=True)
        if not ok:
            if self._dev_logging_enabled():
                self._log_bridge_diagnostics("ensure_bridge_running fehlgeschlagen")
            return False

        # Kamera-Verbindung gleich mit vorwärmen (best-effort, läuft im
        # Warmup-Thread): das init-Kommando der ersten Session kehrt dann
        # sofort zurück, statt den Kamera-Connect auf dem UI-Thread abzuwarten.
        if not self._is_initialized:
            try:
                client.request(
                    "init",
                    timeout=self._settings().get("init_timeout_seconds", 20),
                    index=self._camera_index,
                    size=self._settings().get("image_size", "M"),
                )
                logger.info("Nikon-Bridge-Warmup: Kamera vorverbunden")
            except Exception as exc:
                logger.debug(f"Nikon-Bridge-Warmup: Kamera-Vorverbindung offen ({exc})")
        return True

    def initialize(self, camera_index: int = 0, width: int = 0, height: int = 0) -> bool:
        with self._lock:
            logger.info(f"=== Nikon/FexoNikonBridge initialisieren (index={camera_index}) ===")
            self._camera_index = camera_index

            if self._is_initialized:
                return True

            client = _get_client(self._config)
            if not client.ensure_running(spawn=True):
                logger.error("FexoNikonBridge ist nicht verfügbar")
                if self._dev_logging_enabled():
                    self._log_bridge_diagnostics("initialize: Bridge nicht verfügbar")
                return False

            try:
                header, _ = client.request(
                    "init",
                    timeout=self._settings().get("init_timeout_seconds", 20),
                    index=camera_index,
                    size=self._settings().get("image_size", "M"),
                )
                self._camera_name = header.get("camera", self._camera_name)
                image_size = (header.get("image_size") or "").strip("\x00 ").strip()
                if image_size:
                    logger.info(
                        f"Nikon Bildgröße gesetzt: {image_size} "
                        f"(nikon_bridge.image_size={self._settings().get('image_size', 'M')!r})"
                    )
            except Exception as exc:
                logger.error(f"Nikon init fehlgeschlagen: {exc}")
                if self._dev_logging_enabled():
                    self._log_bridge_diagnostics("initialize: init-Kommando fehlgeschlagen", str(exc))
                return False

            self._is_initialized = True

            if not self.start_live_view():
                self._is_initialized = False
                logger.error("Nikon LiveView konnte nicht gestartet werden")
                return False

            frame = self._wait_for_live_view_frame(timeout=5.0)
            if frame is None:
                self._is_initialized = False
                logger.error("Nikon LiveView liefert kein Bild")
                return False

            logger.info(
                f"Nikon/FexoNikonBridge bereit: {self._camera_name}, "
                f"LiveView {frame.shape[1]}x{frame.shape[0]}"
            )
            return True

    def release(self) -> None:
        with self._lock:
            if self._live_view_active:
                self.stop_live_view()
            client = _get_client(self._config)
            if client.is_running():
                try:
                    client.request("release", timeout=3.0)
                except Exception as exc:
                    logger.debug(f"Nikon release: {exc}")
            self._is_initialized = False
            self._live_view_active = False
            self._last_frame = None
            logger.info("Nikon Kamera freigegeben (Bridge bleibt aktiv)")

    # ------------------------------------------------------------------
    # LiveView
    # ------------------------------------------------------------------

    def start_live_view(self) -> bool:
        if not self._is_initialized:
            return False
        try:
            _get_client(self._config).request(
                "lv_start", timeout=self._settings().get("command_timeout_seconds", 4)
            )
        except Exception as exc:
            logger.warning(f"Nikon LiveView starten fehlgeschlagen: {exc}")
            self._handle_bridge_error()
            return False
        self._live_view_active = True
        return True

    def stop_live_view(self) -> None:
        try:
            _get_client(self._config).request(
                "lv_stop", timeout=self._settings().get("command_timeout_seconds", 4)
            )
        except Exception as exc:
            logger.debug(f"Nikon LiveView stoppen fehlgeschlagen: {exc}")
            self._handle_bridge_error()
        self._live_view_active = False

    def get_frame(self, use_cache: bool = True) -> Optional[np.ndarray]:
        if not self._is_initialized:
            return None

        with self._lock:
            current_time = time.time()
            if use_cache and self._last_frame is not None:
                if current_time - self._last_frame_time < self._frame_cache_duration:
                    return self._last_frame.copy()

            if not self._live_view_active and not self.start_live_view():
                return self._recent_cached_frame()

            try:
                _, payload = _get_client(self._config).request("frame", timeout=2.0)
                frame = self._decode_jpeg_to_bgr(payload) if payload else None
            except Exception as exc:
                logger.debug(f"Nikon LiveView-Frame nicht lesbar: {exc}")
                self._handle_bridge_error()
                frame = None

            if frame is not None:
                self._last_frame = frame
                self._last_frame_time = current_time
                return frame

            return self._recent_cached_frame()

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def capture_photo(self, timeout: float = 10.0) -> Optional[Image.Image]:
        """Nimmt ein Vollauflösungs-Foto über die Bridge auf (JPEG in den RAM)."""
        if not self._is_initialized:
            logger.error("Nikon capture_photo: Kamera nicht initialisiert")
            return None

        with self._lock:
            logger.info("=== NIKON CAPTURE_PHOTO (FexoNikonBridge) ===")
            live_view_was_active = self._live_view_active
            capture_timeout = max(
                timeout, self._settings().get("capture_timeout_seconds", 12)
            )

            image: Optional[Image.Image] = None
            try:
                _, payload = _get_client(self._config).request("capture", timeout=capture_timeout)
                if payload:
                    image = self._load_image_from_bytes(payload)
            except Exception as exc:
                logger.error(f"Nikon Capture fehlgeschlagen: {exc}")
                self._handle_bridge_error()

            if image is None:
                logger.error("Nikon Capture: Kein Bild empfangen")
                return self._fallback_to_live_view(live_view_was_active)

            # Capture beendet den LiveView kameraseitig — bei Bedarf neu starten.
            if live_view_was_active:
                self._live_view_active = False
                self.start_live_view()

            logger.info(f"Nikon Capture erfolgreich: {image.size[0]}x{image.size[1]}")
            return image

    def get_high_res_frame(self, width: int = 0, height: int = 0) -> Optional[np.ndarray]:
        image = self.capture_photo()
        if image is None:
            return None

        rgb = np.array(image)
        if len(rgb.shape) == 3 and rgb.shape[2] == 3:
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return rgb

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    @property
    def camera_name(self) -> str:
        return self._camera_name

    # ------------------------------------------------------------------
    # Intern
    # ------------------------------------------------------------------

    def _recent_cached_frame(self) -> Optional[np.ndarray]:
        """Cache-Frame nur ausliefern, solange er frisch ist (sonst None).

        Verhindert, dass eine tote Bridge/Kamera unbegrenzt den letzten Frame
        als "LiveView" liefert und der Capture-Fallback daraus ein veraltetes
        Standbild als Foto macht.
        """
        if self._last_frame is None:
            return None
        if time.time() - self._last_frame_time > self._max_stale_frame_seconds:
            return None
        return self._last_frame.copy()

    def _handle_bridge_error(self) -> None:
        """Nach fehlgeschlagenem Bridge-Request: bei totem Prozess Status zurücksetzen.

        Damit ruft der nächste Session-Start wieder initialize() auf (das die
        Bridge über ensure_running neu startet) und der Top-Bar-Status-Check
        prüft wieder — statt dass die Kamera bis zum App-Neustart stumm
        "initialisiert" bleibt.
        """
        client = _get_client(self._config)
        if client.is_running():
            return
        logger.error(
            "FexoNikonBridge-Prozess ist beendet — Kamera-Status zurückgesetzt, "
            "Neustart beim nächsten initialize()"
        )
        self._is_initialized = False
        self._live_view_active = False
        self._last_frame = None

    def _wait_for_live_view_frame(self, timeout: float) -> Optional[np.ndarray]:
        end_time = time.time() + timeout
        while time.time() < end_time:
            frame = self.get_frame(use_cache=False)
            if frame is not None:
                return frame
            time.sleep(0.25)
        return None

    def _fallback_to_live_view(self, restart_live_view: bool) -> Optional[Image.Image]:
        logger.warning("Nikon Capture fallback: LiveView-Frame")
        if restart_live_view and not self._live_view_active:
            self.start_live_view()

        frame = self._wait_for_live_view_frame(timeout=3.0)
        if frame is None:
            return None

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    def _settings(self) -> Dict[str, Any]:
        return self._config.get("nikon_bridge", {})

    def _dev_logging_enabled(self) -> bool:
        return bool(self._config.get("developer_mode"))

    def _log_bridge_diagnostics(self, context: str, detail: str = "") -> None:
        """Schreibt im Developer Mode eine kompakte Bridge-Fehlerdiagnose ins Log."""
        current_time = time.time()
        if current_time - self._last_diagnostics_log_time < 3:
            return
        self._last_diagnostics_log_time = current_time

        settings = self._settings()
        client = _get_client(self._config)
        logger.info(
            "NIKON-DIAGNOSE (Developer Mode): "
            f"context={context}; camera_type={self._config.get('camera_type')}; "
            f"dslr_camera_type={self._config.get('dslr_camera_type')}; "
            f"exe_path={settings.get('exe_path')!r}; "
            f"bridge_running={client.is_running()}; "
            f"init_timeout={settings.get('init_timeout_seconds')}; "
            f"command_timeout={settings.get('command_timeout_seconds')}; "
            f"capture_timeout={settings.get('capture_timeout_seconds')}"
        )
        if detail:
            logger.info(f"NIKON-DIAGNOSE: Detail: {detail}")

        candidate_lines = []
        for path in bridge_exe_candidates(self._config):
            try:
                exists = path.exists()
                is_file = path.is_file() if exists else False
                size = path.stat().st_size if is_file else "-"
            except Exception as exc:
                exists = False
                is_file = False
                size = f"Fehler: {exc}"
            state = "OK" if is_file else ("ORDNER" if exists else "FEHLT")
            candidate_lines.append(f"  - [{state}] {path} (size={size})")
        if candidate_lines:
            logger.info("NIKON-DIAGNOSE: Bridge-EXE-Kandidaten:\n" + "\n".join(candidate_lines))
        else:
            logger.info("NIKON-DIAGNOSE: Keine Bridge-EXE-Kandidaten erzeugt")

    @staticmethod
    def _decode_jpeg_to_bgr(data: bytes) -> Optional[np.ndarray]:
        if not data:
            return None
        nparr = np.frombuffer(data, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    @staticmethod
    def _load_image_from_bytes(data: bytes) -> Optional[Image.Image]:
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
            return image.convert("RGB")
        except Exception as exc:
            logger.debug(f"Bilddaten nicht lesbar: {exc}")
            return None
