"""Webcam-Manager mit OpenCV"""

import cv2
import numpy as np
import time
import threading
from typing import Optional, Tuple

from .base import CameraManager
from src.utils.logging import get_logger

logger = get_logger(__name__)


class WebcamManager(CameraManager):
    """Verwaltet Webcam-Zugriff via OpenCV

    Funktioniert auch mit Canon Webcam Utility für DSLR-Support!
    """

    def __init__(self):
        self.cap: Optional[cv2.VideoCapture] = None
        self.camera_index: int = 0
        self._is_initialized: bool = False
        self.last_frame: Optional[np.ndarray] = None
        self.last_frame_time: float = 0
        self.frame_cache_duration: float = 0.033  # ~30fps
        self._preview_width: int = 0  # Gespeicherte Preview-Auflösung
        self._preview_height: int = 0
        self._active_width: int = 0
        self._active_height: int = 0
        self._mjpg_unsupported: bool = False  # Latch: Kamera lehnt MJPG ab
        self._camera_lock = threading.RLock()

    def initialize(self, camera_index: int, width: int, height: int) -> bool:
        """Initialisiert die Kamera"""
        with self._camera_lock:
            # Bereits initialisiert?
            if self._is_initialized and self.camera_index == camera_index:
                return True

            # Alte Verbindung schließen
            self.release()
            self.camera_index = camera_index
            self._mjpg_unsupported = False  # neue Kamera = neuer Versuch

            # Verschiedene Backends probieren
            backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]

            for backend in backends:
                logger.debug(f"Versuche Backend: {backend}")
                self.cap = cv2.VideoCapture(camera_index, backend)

                if self.cap.isOpened():
                    logger.info(f"Kamera {camera_index} geöffnet mit Backend {backend}")
                    break

            if not self.cap or not self.cap.isOpened():
                logger.error(f"Konnte Kamera {camera_index} nicht öffnen")
                return False

            # Einstellungen setzen — Codec NACH der Auflösung anfordern
            # (Messung 2.4.13: andersherum verhandelt DirectShow beim
            # Auflösungs-Setzen wieder auf YUY2 zurück)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimiert Latenz
            self._apply_mjpg()

            # Tatsächliche Auflösung loggen und als Preview-Auflösung merken
            actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self._preview_width = actual_w
            self._preview_height = actual_h
            self._active_width = actual_w
            self._active_height = actual_h
            logger.info(
                f"Kamera initialisiert: {actual_w}x{actual_h}, "
                f"fourcc={self._get_current_fourcc()}"
            )

            self._is_initialized = True
            return True

    def _apply_mjpg(self) -> bool:
        """Aktiviert den MJPG-Codec — mit VERIFIKATION und Merker bei Ablehnung.

        Warum: YUY2 (unkomprimiert) macht 1080p-Umschaltung + Auslesen über
        USB2 langsam (~1,3s + ~0,7s pro Foto, Messung Miix 310). Der erste
        Fix (2.4.13) setzte den Codec VOR der Auflösung — DirectShow
        verhandelte beim Auflösungs-Setzen zurück auf YUY2, und der nutzlose
        Versuch kostete zusätzlich ~600ms pro Foto. Daher jetzt:
        1) Codec NACH der Auflösung setzen und Ergebnis PRÜFEN,
        2) Fallback: Codec-zuerst-Variante (manche Treiber wollen es so),
        3) bei endgültiger Ablehnung dauerhaft merken → nie wieder Zeit
           pro Foto verschwenden.
        """
        if self._mjpg_unsupported or not self.cap:
            return False
        try:
            if self._get_current_fourcc() == "MJPG":
                return True
            mjpg = cv2.VideoWriter_fourcc(*"MJPG")

            # Versuch 1: Codec nach bereits gesetzter Auflösung anfordern
            self.cap.set(cv2.CAP_PROP_FOURCC, mjpg)
            if self._get_current_fourcc() == "MJPG":
                logger.info("Webcam-Codec: MJPG aktiv")
                return True

            # Versuch 2: Codec zuerst, dann dieselbe Auflösung erneut setzen
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.cap.set(cv2.CAP_PROP_FOURCC, mjpg)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            if self._get_current_fourcc() == "MJPG":
                logger.info("Webcam-Codec: MJPG aktiv (Codec-zuerst-Variante)")
                return True

            self._mjpg_unsupported = True
            logger.info(
                f"Webcam-Codec: Kamera lehnt MJPG ab, bleibt bei "
                f"{self._get_current_fourcc()} (keine weiteren Versuche)"
            )
        except Exception as e:
            self._mjpg_unsupported = True
            logger.debug(f"MJPG-Anforderung fehlgeschlagen: {e}")
        return False

    def get_frame(self, use_cache: bool = True) -> Optional[np.ndarray]:
        """Holt ein Frame von der Kamera"""
        if not self._is_initialized or not self.cap:
            return None

        with self._camera_lock:
            current_time = time.time()

            # Cache nutzen wenn möglich
            if use_cache and self.last_frame is not None:
                if current_time - self.last_frame_time < self.frame_cache_duration:
                    return self.last_frame.copy()

            # Neues Frame holen
            ret, frame = self.cap.read()

            if ret and frame is not None:
                self.last_frame = frame
                self.last_frame_time = current_time
                return frame

            logger.warning("Konnte kein Frame lesen")
            return None

    def get_high_res_frame(
        self,
        width: int = 1920,
        height: int = 1080,
        restore_preview: bool = True
    ) -> Optional[np.ndarray]:
        """Holt ein hochauflösendes Frame für Foto-Capture

        Schaltet temporär auf höhere Auflösung um und holt das Bild.
        Das Zurückschalten auf die Live-Preview-Auflösung kann verzögert
        werden, damit die sichtbare Aufnahmezeit kürzer wird.

        Optimiert für Logitech C920/C922 (native 1080p Support).

        Args:
            width: Gewünschte Breite (default: 1920 für Full HD)
            height: Gewünschte Höhe (default: 1080 für Full HD)
            restore_preview: True = direkt zurückschalten, False = später
                per restore_preview_resolution() zurückschalten.

        Returns:
            numpy array mit dem hochauflösenden Frame, oder None bei Fehler
        """
        if not self.cap:
            logger.warning("get_high_res_frame: Keine Kamera initialisiert")
            return None

        with self._camera_lock:
            total_start = time.perf_counter()
            set_ms = 0.0
            verify_ms = 0.0
            grab_ms = 0.0
            read_ms = 0.0
            restore_ms = 0.0
            switched_resolution = False
            frame = None

            preview_w, preview_h = self._get_preview_resolution()
            active_w = self._active_width or int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            active_h = self._active_height or int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            logger.info(
                "High-Res Capture Start: "
                f"preview={preview_w}x{preview_h}, active={active_w}x{active_h}, "
                f"target={width}x{height}, restore_preview={restore_preview}, "
                f"fourcc={self._get_current_fourcc()}"
            )

            try:
                if active_w >= width and active_h >= height:
                    logger.info("High-Res Capture: Zielauflösung ist bereits aktiv")
                else:
                    t0 = time.perf_counter()
                    ok_w = self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    ok_h = self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    self._apply_mjpg()
                    set_ms = (time.perf_counter() - t0) * 1000

                    t0 = time.perf_counter()
                    active_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    active_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    verify_ms = (time.perf_counter() - t0) * 1000
                    switched_resolution = True
                    self._active_width = active_w
                    self._active_height = active_h
                    self.last_frame = None
                    self.last_frame_time = 0

                    logger.info(
                        "High-Res Capture Umschaltung: "
                        f"set_ok={ok_w}/{ok_h}, actual={active_w}x{active_h}, "
                        f"set={set_ms:.0f}ms, verify={verify_ms:.0f}ms"
                    )

                # Buffer leeren mit grab() statt read() (grab bewegt nur den Pointer,
                # dekodiert nicht - deutlich schneller als read!)
                t0 = time.perf_counter()
                for _ in range(2):
                    self.cap.grab()
                grab_ms = (time.perf_counter() - t0) * 1000

                # Tatsächliches High-Res Frame holen
                t0 = time.perf_counter()
                ret, frame = self.cap.read()
                read_ms = (time.perf_counter() - t0) * 1000

                if ret and frame is not None:
                    captured_h, captured_w = frame.shape[:2]
                    logger.info(f"High-Res Frame erfolgreich: {captured_w}x{captured_h}")

                    if captured_w < width or captured_h < height:
                        logger.warning(
                            f"Kamera liefert weniger als angefordert: "
                            f"{captured_w}x{captured_h} statt {width}x{height}"
                        )
                else:
                    logger.error("High-Res Frame lesen fehlgeschlagen nach Umschaltung")
                    frame = None

            except Exception as e:
                logger.error(f"High-Res Capture Exception: {e}")
                frame = None
            finally:
                if restore_preview and switched_resolution:
                    t0 = time.perf_counter()
                    self.restore_preview_resolution()
                    restore_ms = (time.perf_counter() - t0) * 1000
                elif switched_resolution:
                    logger.info(
                        "High-Res Capture: Preview-Restore auf nachgelagerten "
                        "Background-Task verschoben"
                    )

                total_ms = (time.perf_counter() - total_start) * 1000
                logger.info(
                    "High-Res Capture Timing: "
                    f"set={set_ms:.0f}ms, verify={verify_ms:.0f}ms, "
                    f"grab={grab_ms:.0f}ms, read={read_ms:.0f}ms, "
                    f"restore={restore_ms:.0f}ms, total={total_ms:.0f}ms"
                )

            return frame

    def restore_preview_resolution(self) -> bool:
        """Schaltet zurück auf die gespeicherte Live-Preview-Auflösung."""
        if not self.cap:
            logger.warning("Preview-Restore: Keine Kamera initialisiert")
            return False

        with self._camera_lock:
            target_w, target_h = self._get_preview_resolution()
            if target_w <= 0 or target_h <= 0:
                logger.warning("Preview-Restore: Keine gültige Preview-Auflösung gespeichert")
                return False

            total_start = time.perf_counter()
            before_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            before_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            if before_w == target_w and before_h == target_h:
                self._active_width = before_w
                self._active_height = before_h
                self.last_frame = None
                self.last_frame_time = 0
                logger.debug(f"Preview-Restore: Bereits aktiv ({target_w}x{target_h})")
                return True

            t0 = time.perf_counter()
            ok_w = self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
            ok_h = self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
            self._apply_mjpg()
            set_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            verify_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            for _ in range(2):
                self.cap.grab()
            flush_ms = (time.perf_counter() - t0) * 1000

            self._active_width = actual_w
            self._active_height = actual_h
            self.last_frame = None
            self.last_frame_time = 0

            total_ms = (time.perf_counter() - total_start) * 1000
            logger.info(
                "Preview-Restore Timing: "
                f"{before_w}x{before_h} -> {actual_w}x{actual_h} "
                f"(target={target_w}x{target_h}, set_ok={ok_w}/{ok_h}), "
                f"set={set_ms:.0f}ms, verify={verify_ms:.0f}ms, "
                f"flush={flush_ms:.0f}ms, total={total_ms:.0f}ms"
            )
            return actual_w == target_w and actual_h == target_h

    def release(self):
        """Gibt Kamera-Ressourcen frei"""
        with self._camera_lock:
            if self.cap:
                self.cap.release()
                self.cap = None
            self._is_initialized = False
            self.last_frame = None
            self._active_width = 0
            self._active_height = 0
            logger.info("Kamera freigegeben")

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    def _get_preview_resolution(self) -> Tuple[int, int]:
        """Liefert die gemerkte Preview-Auflösung mit Kamera-Fallback."""
        preview_w = self._preview_width
        preview_h = self._preview_height

        if (preview_w <= 0 or preview_h <= 0) and self.cap:
            preview_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            preview_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        return preview_w, preview_h

    def _get_current_fourcc(self) -> str:
        """Liest den aktiven Kamera-Codec best-effort für Timing-Diagnose."""
        if not self.cap:
            return "unknown"

        try:
            fourcc_value = int(self.cap.get(cv2.CAP_PROP_FOURCC))
            if fourcc_value <= 0:
                return "unknown"
            chars = "".join(chr((fourcc_value >> 8 * i) & 0xFF) for i in range(4))
            return chars.strip() or str(fourcc_value)
        except Exception:
            return "unknown"

    @staticmethod
    def _get_dshow_device_names() -> list:
        """Ermittelt Webcam-Gerätenamen direkt via DirectShow COM-API.

        Nutzt C#/.NET Interop um die DirectShow-Enumeration aufzurufen.
        Die Reihenfolge entspricht EXAKT der OpenCV CAP_DSHOW Reihenfolge,
        da beide dieselbe COM-API (ICreateDevEnum) verwenden.

        Returns:
            Liste von Gerätenamen in DirectShow-Reihenfolge.
            Leere Liste wenn Abfrage fehlschlägt.
        """
        try:
            import subprocess
            # C# DirectShow-Enumeration via PowerShell Add-Type
            # Nutzt dieselbe COM-API wie OpenCV CAP_DSHOW
            csharp_code = r'''
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Collections.Generic;
public class DShowEnum {
    [ComImport, Guid("62BE5D10-60EB-11d0-BD3B-00A0C911CE86")]
    class SystemDeviceEnum {}
    [ComImport, Guid("29840822-5B84-11D0-BD3B-00A0C911CE86"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ICreateDevEnum {
        [PreserveSig] int CreateClassEnumerator(
            [In] ref Guid type, [Out] out IEnumMoniker enumMoniker, [In] int flags);
    }
    [ComImport, Guid("55272A00-42CB-11CE-8135-00AA004BB851"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyBag {
        [PreserveSig] int Read(
            [In, MarshalAs(UnmanagedType.LPWStr)] string name,
            [In, Out] ref object val, [In] IntPtr errorLog);
        [PreserveSig] int Write(
            [In, MarshalAs(UnmanagedType.LPWStr)] string name, [In] ref object val);
    }
    public static string[] GetVideoDevices() {
        var names = new List<string>();
        try {
            var devEnum = (ICreateDevEnum)new SystemDeviceEnum();
            IEnumMoniker enumMon;
            var cat = new Guid("860BB310-5D01-11D0-BD3B-00A0C911CE86");
            if (devEnum.CreateClassEnumerator(ref cat, out enumMon, 0) == 0 && enumMon != null) {
                var mon = new IMoniker[1];
                while (enumMon.Next(1, mon, IntPtr.Zero) == 0) {
                    try {
                        Guid iid = typeof(IPropertyBag).GUID;
                        object bagObj;
                        mon[0].BindToStorage(null, null, ref iid, out bagObj);
                        var bag = (IPropertyBag)bagObj;
                        object nameVal = "";
                        bag.Read("FriendlyName", ref nameVal, IntPtr.Zero);
                        names.Add(nameVal != null ? nameVal.ToString() : "");
                        Marshal.ReleaseComObject(bagObj);
                    } catch {} finally { Marshal.ReleaseComObject(mon[0]); }
                }
                Marshal.ReleaseComObject(enumMon);
            }
        } catch {}
        return names.ToArray();
    }
}
'''
            ps_command = (
                f'Add-Type -TypeDefinition @"\n{csharp_code}\n"@ -Language CSharp; '
                '[DShowEnum]::GetVideoDevices() | ForEach-Object { $_ }'
            )
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps_command],
                capture_output=True, text=True, timeout=10,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            if result.returncode == 0 and result.stdout.strip():
                names = [n.strip() for n in result.stdout.strip().split('\n') if n.strip()]
                logger.info(f"DirectShow Kamera-Namen (korrekte Reihenfolge): {names}")
                return names
            else:
                if result.stderr:
                    logger.debug(f"DirectShow-Enumeration stderr: {result.stderr[:200]}")
        except Exception as e:
            logger.debug(f"DirectShow-Enumeration fehlgeschlagen: {e}")
        return []

    @staticmethod
    def _get_pnp_device_names() -> list:
        """Fallback: Ermittelt Webcam-Gerätenamen via PnP/WMI (Windows)

        ACHTUNG: Die Reihenfolge stimmt NICHT zuverlässig mit DirectShow überein!
        Nur als Fallback verwenden wenn _get_dshow_device_names() fehlschlägt.

        Returns:
            Liste von Gerätenamen (Reihenfolge kann von DirectShow abweichen!)
        """
        try:
            import subprocess
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 'Get-PnpDevice -Class Camera,Image -Status OK '
                 '| Select-Object -ExpandProperty FriendlyName'],
                capture_output=True, text=True, timeout=5,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            if result.returncode == 0 and result.stdout.strip():
                names = [n.strip() for n in result.stdout.strip().split('\n') if n.strip()]
                logger.debug(f"PnP Kamera-Namen (Fallback, Reihenfolge unsicher): {names}")
                return names
        except Exception as e:
            logger.debug(f"PnP Kamera-Abfrage fehlgeschlagen: {e}")
        return []

    @staticmethod
    def _get_device_names() -> list:
        """Ermittelt Webcam-Gerätenamen in DirectShow-Reihenfolge.

        Primär: DirectShow COM-API (exakte Reihenfolge wie OpenCV)
        Fallback: PnP-Geräte (Reihenfolge kann abweichen!)

        Returns:
            Liste von Gerätenamen, bestmöglich in DirectShow-Reihenfolge.
        """
        # Primär: DirectShow-Enumeration (korrekte Reihenfolge)
        names = WebcamManager._get_dshow_device_names()
        if names:
            return names

        # Fallback: PnP (Reihenfolge kann abweichen!)
        logger.warning("DirectShow-Enumeration fehlgeschlagen, nutze PnP-Fallback")
        return WebcamManager._get_pnp_device_names()

    @staticmethod
    def list_cameras(max_cameras: int = 5) -> list:
        """Listet verfügbare Kameras mit echten Gerätenamen auf"""
        # Echte Gerätenamen holen (Best-Effort)
        device_names = WebcamManager._get_device_names()

        cameras = []
        for i in range(max_cameras):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()

                # Name zuordnen: WMI-Liste matcht üblicherweise die DirectShow-Reihenfolge
                name = device_names[len(cameras)] if len(cameras) < len(device_names) else ""
                if not name:
                    name = f"Kamera {i}"

                cameras.append({
                    "index": i,
                    "name": name,
                    "width": w,
                    "height": h
                })

        return cameras

    @staticmethod
    def find_best_camera(cameras: list) -> int:
        """Findet die beste externe Webcam (interne Kameras werden ignoriert!)

        Die interne Tablet-Kamera (z.B. Lenovo Miix 310) ist physisch verdeckt
        und darf NICHT als Fallback verwendet werden. Wenn keine externe Kamera
        angeschlossen ist, wird -1 zurückgegeben → Kamera-Warnung blinkt.

        Priorisierung:
        1. Logitech Kameras (bekannt gut für Fotoboxen)
        2. Andere externe USB-Kameras
        3. -1 (keine brauchbare Kamera) → NICHT auf interne Kamera fallen!

        Args:
            cameras: Liste von list_cameras() Ergebnis

        Returns:
            Kamera-Index der besten externen Kamera, oder -1 wenn keine gefunden
        """
        if not cameras:
            return -1

        internal_keywords = ["integrated", "internal", "ir camera", "infrarot",
                             "front camera", "rear camera", "built-in", "avstream"]

        # Priorität 1: Logitech
        for cam in cameras:
            name_lower = cam.get("name", "").lower()
            if "logitech" in name_lower:
                logger.info(f"Logitech Kamera bevorzugt: [{cam['index']}] {cam['name']}")
                return cam["index"]

        # Priorität 2: Andere externe Kamera (nicht intern/integriert)
        for cam in cameras:
            name_lower = cam.get("name", "").lower()
            if not any(kw in name_lower for kw in internal_keywords) and name_lower != f"kamera {cam['index']}":
                logger.info(f"Externe Kamera bevorzugt: [{cam['index']}] {cam['name']}")
                return cam["index"]

        # KEIN Fallback auf interne Kamera! Warnung soll blinken.
        internal_names = [c.get("name", "?") for c in cameras]
        logger.warning(f"Keine externe Kamera gefunden! Interne Kameras ignoriert: {internal_names}")
        return -1
