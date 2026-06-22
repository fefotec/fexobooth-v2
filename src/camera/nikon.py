"""Nikon DSLR Camera Manager via digiCamControl.

This backend is intentionally a thin adapter around digiCamControl's local
web/remote contract. Nikon D3300 tethering is handled by digiCamControl; the
FexoBooth app consumes liveview frames and full-size captures through HTTP.
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import urlopen

import cv2
import numpy as np
from PIL import Image

from .base import CameraManager
from src.utils.logging import get_logger

logger = get_logger(__name__)


class NikonCameraManager(CameraManager):
    """Controls Nikon DSLRs through a running digiCamControl instance."""

    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 5513

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config: Dict[str, Any] = config or {}
        self._is_initialized = False
        self._live_view_active = False
        self._last_frame: Optional[np.ndarray] = None
        self._last_frame_time: float = 0
        self._frame_cache_duration = 0.033
        self._camera_index = 0
        self._capture_folder: Optional[Path] = None
        self._dcc_process: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()

    def update_config(self, config: Dict[str, Any]) -> None:
        self._config = config

    @staticmethod
    def is_available(config: Optional[Dict[str, Any]] = None) -> bool:
        manager = NikonCameraManager(config)
        host, port = manager._server_host_port()
        return bool(NikonCameraManager._find_digicamcontrol_exe(config)) or NikonCameraManager._server_responds(
            host,
            port,
        )

    @staticmethod
    def list_cameras(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        manager = NikonCameraManager(config)
        try:
            response = manager._single_command("list", "cameras", timeout=1.5)
        except Exception as exc:
            logger.debug(f"digiCamControl Kamera-Liste nicht erreichbar: {exc}")
            return []

        cameras: List[Dict[str, Any]] = []
        for idx, line in enumerate(response.splitlines()):
            name = line.strip()
            if not name or name.upper() == "OK":
                continue
            cameras.append({"index": idx, "name": name, "serial": name})
        return cameras

    def initialize(self, camera_index: int = 0, width: int = 0, height: int = 0) -> bool:
        with self._lock:
            logger.info(f"=== Nikon/digiCamControl initialisieren (index={camera_index}) ===")
            self._camera_index = camera_index

            if self._is_initialized:
                return True

            self._capture_folder = self._get_capture_folder()
            self._capture_folder.mkdir(parents=True, exist_ok=True)

            if not self._ensure_digicamcontrol_ready():
                logger.error("digiCamControl ist nicht erreichbar")
                return False

            try:
                self._single_command("set", "transfer", "Save_to_PC_only", timeout=2.0)
                self._single_command("set", "session.folder", str(self._capture_folder), timeout=2.0)
            except Exception as exc:
                logger.warning(f"digiCamControl Basis-Setup fehlgeschlagen: {exc}")

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

            logger.info(f"Nikon/digiCamControl bereit: {frame.shape[1]}x{frame.shape[0]}")
            return True

    def get_frame(self, use_cache: bool = True) -> Optional[np.ndarray]:
        if not self._is_initialized:
            return None

        with self._lock:
            current_time = time.time()
            if use_cache and self._last_frame is not None:
                if current_time - self._last_frame_time < self._frame_cache_duration:
                    return self._last_frame.copy()

            if not self._live_view_active and not self.start_live_view():
                return self._last_frame

            try:
                data = self._http_bytes("liveview.jpg", timeout=2.0, cache_bust=True)
                frame = self._decode_jpeg_to_bgr(data)
            except Exception as exc:
                logger.debug(f"Nikon LiveView-Frame nicht lesbar: {exc}")
                frame = None

            if frame is not None:
                self._last_frame = frame
                self._last_frame_time = current_time
                return frame

            return self._last_frame

    def capture_photo(self, timeout: float = 10.0) -> Optional[Image.Image]:
        """Captures a full-size Nikon photo through digiCamControl."""
        if not self._is_initialized:
            logger.error("Nikon capture_photo: Kamera nicht initialisiert")
            return None

        with self._lock:
            logger.info("=== NIKON CAPTURE_PHOTO (digiCamControl) ===")
            capture_folder = self._capture_folder or self._get_capture_folder()
            capture_folder.mkdir(parents=True, exist_ok=True)
            stem = f"fexobooth_nikon_{int(time.time() * 1000)}"
            started_at = time.time()
            live_view_was_active = self._live_view_active

            try:
                self._single_command("set", "session.folder", str(capture_folder), timeout=2.0)
                self._single_command("set", "session.filenametemplate", stem, timeout=2.0)
                self._single_command("set", "transfer", "Save_to_PC_only", timeout=2.0)
            except Exception as exc:
                logger.warning(f"Nikon Capture-Setup unvollstaendig: {exc}")

            capture_triggered = False
            try:
                response = self._single_command("capture", "", "", timeout=4.0)
                capture_triggered = "error" not in response.lower()
                logger.info(f"Nikon Capture Antwort: {response!r}")
            except Exception as exc:
                logger.warning(f"Nikon Capture-Befehl fehlgeschlagen: {exc}")

            if not capture_triggered:
                try:
                    response = self._single_command("do", "LiveView_Capture", "", timeout=4.0)
                    capture_triggered = "error" not in response.lower()
                    logger.info(f"Nikon LiveView_Capture Antwort: {response!r}")
                except Exception as exc:
                    logger.error(f"Nikon LiveView_Capture fehlgeschlagen: {exc}")

            if not capture_triggered:
                return self._fallback_to_live_view(live_view_was_active)

            image = self._wait_for_captured_image(capture_folder, stem, started_at, timeout)
            if image is None:
                logger.error("Nikon Capture: Kein Bild empfangen")
                return self._fallback_to_live_view(live_view_was_active)

            if live_view_was_active and not self._live_view_active:
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

    def start_live_view(self) -> bool:
        if not self._is_initialized:
            return False

        try:
            self._http_text("", params={"CMD": "LiveViewWnd_Show"}, timeout=2.0)
        except Exception:
            try:
                self._single_command("do", "LiveViewWnd_Show", "", timeout=2.0)
            except Exception as exc:
                logger.warning(f"Nikon LiveView starten fehlgeschlagen: {exc}")
                return False

        self._live_view_active = True
        return True

    def stop_live_view(self) -> None:
        try:
            self._http_text("", params={"CMD": "LiveViewWnd_Hide"}, timeout=2.0)
        except Exception:
            try:
                self._single_command("do", "LiveViewWnd_Hide", "", timeout=2.0)
            except Exception as exc:
                logger.debug(f"Nikon LiveView stoppen fehlgeschlagen: {exc}")
        self._live_view_active = False

    def release(self) -> None:
        with self._lock:
            if self._live_view_active:
                self.stop_live_view()
            self._is_initialized = False
            self._live_view_active = False
            self._last_frame = None
            logger.info("Nikon Kamera freigegeben (digiCamControl bleibt aktiv)")

    def ensure_server_running(self) -> bool:
        """Best-effort: startet digiCamControl (Webserver) falls noch nicht aktiv.

        Für den Warmup beim App-Start (im Hintergrund-Thread): so muss der Betreiber
        digiCamControl NICHT manuell vor der App starten, und der erste Session-Start
        trifft nicht den Kaltstart-Poll auf dem UI-Thread (initialize() findet den
        Webserver dann bereits laufend vor). Idempotent: antwortet der Server schon,
        kehrt es sofort zurück, ohne einen zweiten Prozess zu starten.
        """
        with self._lock:
            return self._ensure_digicamcontrol_ready()

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    @property
    def camera_name(self) -> str:
        return "Nikon via digiCamControl"

    def _wait_for_live_view_frame(self, timeout: float) -> Optional[np.ndarray]:
        end_time = time.time() + timeout
        while time.time() < end_time:
            frame = self.get_frame(use_cache=False)
            if frame is not None:
                return frame
            time.sleep(0.25)
        return None

    def _wait_for_captured_image(
        self,
        folder: Path,
        stem: str,
        started_at: float,
        timeout: float,
    ) -> Optional[Image.Image]:
        end_time = time.time() + timeout
        last_name = ""

        while time.time() < end_time:
            local_image = self._find_local_capture(folder, stem, started_at)
            if local_image:
                return local_image

            try:
                response = self._single_command("get", "lastcaptured", "", timeout=1.0).strip()
            except Exception:
                response = ""

            if response and response != "-" and response.upper() != "OK" and response != last_name:
                last_name = response
                image = self._load_lastcaptured(folder, response)
                if image:
                    return image

            time.sleep(0.25)

        return self._download_preview_image()

    def _find_local_capture(self, folder: Path, stem: str, started_at: float) -> Optional[Image.Image]:
        patterns = [f"{stem}*.jpg", f"{stem}*.jpeg", "*.jpg", "*.jpeg"]
        newest: Optional[Path] = None
        newest_mtime = started_at - 0.5

        for pattern in patterns:
            for candidate in folder.glob(pattern):
                try:
                    mtime = candidate.stat().st_mtime
                except OSError:
                    continue
                if mtime >= newest_mtime:
                    newest = candidate
                    newest_mtime = mtime

        if newest:
            return self._load_image_from_path(newest)
        return None

    def _load_lastcaptured(self, folder: Path, name: str) -> Optional[Image.Image]:
        local_candidates = [Path(name), folder / name]
        for candidate in local_candidates:
            if candidate.exists():
                image = self._load_image_from_path(candidate)
                if image:
                    return image

        try:
            data = self._http_bytes(f"image/{quote(name)}", timeout=4.0)
            return self._load_image_from_bytes(data)
        except Exception as exc:
            logger.debug(f"Nikon lastcaptured Download fehlgeschlagen: {exc}")
            return None

    def _download_preview_image(self) -> Optional[Image.Image]:
        try:
            data = self._http_bytes("preview.jpg", timeout=4.0, cache_bust=True)
            return self._load_image_from_bytes(data)
        except Exception as exc:
            logger.debug(f"Nikon preview.jpg Download fehlgeschlagen: {exc}")
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

    def _ensure_digicamcontrol_ready(self) -> bool:
        host, port = self._server_host_port()
        if self._server_responds(host, port):
            return True

        exe = self._find_digicamcontrol_exe(self._config)
        if not exe:
            logger.error("digiCamControl nicht gefunden. Erwartet CameraControl.exe oder laufenden Webserver.")
            return False

        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            self._dcc_process = subprocess.Popen([str(exe)], creationflags=creationflags)
            logger.info(f"digiCamControl gestartet: {exe}")
        except Exception as exc:
            logger.error(f"digiCamControl konnte nicht gestartet werden: {exc}")
            return False

        end_time = time.time() + self._settings().get("startup_timeout_seconds", 15)
        while time.time() < end_time:
            if self._server_responds(host, port):
                return True
            time.sleep(0.5)
        return False

    @classmethod
    def _server_responds(cls, host: str, port: int) -> bool:
        try:
            with urlopen(f"http://{host}:{port}/session.json", timeout=1.0) as response:
                response.read(1)
            return True
        except Exception:
            return False

    @staticmethod
    def _find_digicamcontrol_exe(config: Optional[Dict[str, Any]]) -> Optional[Path]:
        settings = (config or {}).get("nikon_digicamcontrol", {})
        candidates = [
            settings.get("app_path"),
            os.environ.get("FEXOBOOTH_DIGICAMCONTROL_EXE"),
        ]

        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env_name)
            if base:
                candidates.append(str(Path(base) / "digiCamControl" / "CameraControl.exe"))

        candidates.extend(
            [
                r"C:\Program Files\digiCamControl\CameraControl.exe",
                r"C:\Program Files (x86)\digiCamControl\CameraControl.exe",
            ]
        )

        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.exists():
                return path
        return None

    def _settings(self) -> Dict[str, Any]:
        return self._config.get("nikon_digicamcontrol", {})

    def _server_host_port(self) -> tuple[str, int]:
        settings = self._settings()
        host = str(settings.get("host", self.DEFAULT_HOST))
        port = int(settings.get("port", self.DEFAULT_PORT))
        return host, port

    def _get_capture_folder(self) -> Path:
        folder = self._settings().get("capture_folder")
        if folder:
            return Path(folder)
        return Path(tempfile.gettempdir()) / "FexoBooth" / "NikonCapture"

    def _single_command(
        self,
        command: str,
        param1: str = "",
        param2: str = "",
        timeout: Optional[float] = None,
    ) -> str:
        params = {"slc": command, "param1": param1, "param2": param2}
        return self._http_text("", params=params, timeout=timeout)

    def _http_text(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> str:
        data = self._http_bytes(path, params=params, timeout=timeout)
        return data.decode("utf-8", errors="replace").strip()

    def _http_bytes(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        cache_bust: bool = False,
    ) -> bytes:
        host, port = self._server_host_port()
        clean_path = path.lstrip("/")
        url = f"http://{host}:{port}/{clean_path}"

        query = dict(params or {})
        if cache_bust:
            query["_"] = str(int(time.time() * 1000))
        if query:
            url = f"{url}?{urlencode(query)}"

        try:
            with urlopen(url, timeout=timeout or self._settings().get("http_timeout_seconds", 3.0)) as response:
                return response.read()
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} fuer {url}") from exc
        except URLError as exc:
            raise RuntimeError(f"digiCamControl nicht erreichbar: {url}") from exc

    @staticmethod
    def _decode_jpeg_to_bgr(data: bytes) -> Optional[np.ndarray]:
        if not data:
            return None
        nparr = np.frombuffer(data, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    @staticmethod
    def _load_image_from_path(path: Path) -> Optional[Image.Image]:
        try:
            with Image.open(path) as image:
                image.load()
                return image.convert("RGB")
        except Exception as exc:
            logger.debug(f"Bilddatei nicht lesbar ({path}): {exc}")
            return None

    @staticmethod
    def _load_image_from_bytes(data: bytes) -> Optional[Image.Image]:
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
            return image.convert("RGB")
        except Exception as exc:
            logger.debug(f"Bilddaten nicht lesbar: {exc}")
            return None
